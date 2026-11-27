"""Whether a frame shows a page of a book, from its layout alone (`bookpage`): the repository's test pages as a viewer
shows them are a book's, made-up pages of text, of a shop, of covers, of pictures and a blank tab are not
(tools/bookpage_eval.py measures it on the sample set's pages and many more made-up ones)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from taslation import bookpage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bookpage_eval as ev  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def pages() -> list[Image.Image]:
    return [Image.open(FIXTURES / n).convert("RGB") for n in ("sample_page.png", "sample_page2.png")]


def test_a_page_of_a_book_on_a_ground_alone_or_in_a_spread_is_a_book_s(pages):
    for ground in (ev.DARK_GROUND, ev.WHITE, ev.BLACK):
        for page in pages:
            assert bookpage.judge(ev.present([page], "single", ground)) == "book", ground
    assert bookpage.judge(ev.present(pages, "spread")) == "book"
    assert bookpage.judge(ev.present(pages[:1], "alone")) == "book"  # (a capture area that is the page itself)
    assert bookpage.judge(ev.present(pages[:1], "single", size=(600, 915))) == "book"  # (narrower than the page)
    assert bookpage.judge(ev.present(pages[:1], "soft")) != "not"  # (a soft first picture: never said to be none)


def test_what_a_page_of_a_book_is_judged_by(pages):
    found = bookpage.layout(ev.present(pages[:1], "single"))
    assert found.box and found.page_shaped and found.paper > bookpage.PAPER_EDGE  # (a page laid on the ground)
    assert found.drawn >= bookpage.DRAWING and found.panels >= bookpage.PANELS_LEAST
    assert found.bubbles >= bookpage.BUBBLES_LEAST and found.grid < bookpage.GRID_ROW and found.colour == 0


@pytest.mark.parametrize("size", [(1900, 915), (900, 915)])
def test_a_page_of_text_or_a_blank_tab_is_no_book_s(size):
    for kind, frame in (("text", ev.text_page(1, size)), ("text-japanese", ev.text_page(1, size, japanese=True)),
                        ("text-dark", ev.text_page(1, size, dark=True)), ("document", ev.document_page(1, size)),
                        ("blank", ev.blank_tab(1, size)), ("blank-empty", ev.blank_tab(1, size, empty=True)),
                        ("standin-plain", ev.standin_other(0, size)), ("standin-japanese", ev.standin_other(1, size))):
        assert bookpage.judge(frame) == "not", kind


@pytest.mark.parametrize("size", [(1900, 915), (640, 915)])
def test_a_shop_a_shelf_of_covers_and_a_grid_of_pictures_are_never_a_book_s(size):
    for kind, frame in (("shop", ev.shop_page(2, size)), ("shop-outlined", ev.shop_page(2, size, outlined=True)),
                        ("covers", ev.covers_page(2, size)), ("gallery", ev.gallery_page(2, size)),
                        ("forum", ev.forum_page(2, size)), ("text-picture", ev.text_page(2, size, photo=True))):
        assert bookpage.judge(frame) != "book", kind


def test_a_row_of_frames_of_one_size_or_colour_off_a_ground_is_a_web_page_s():
    found = bookpage.Layout(box=True, page_shaped=False, paper=0.0, ink=0.2, drawn=0.9, panels=6, across=12, down=12,
                            grid=1, bubbles=5, colour=0.0, area_ink=0.2)
    assert bookpage.verdict(found) == "book"
    assert bookpage.verdict(bookpage.Layout(**{**vars(found), "grid": bookpage.GRID_ROW})) == "unsure"
    coloured = {**vars(found), "colour": 0.3}
    assert bookpage.verdict(bookpage.Layout(**coloured)) == "unsure"
    laid = {**coloured, "page_shaped": True, "paper": 0.9}  # (a colour page laid on a viewer's ground)
    assert bookpage.verdict(bookpage.Layout(**laid)) == "book"
    assert bookpage.verdict(bookpage.Layout(**{**vars(found), "bubbles": 1})) == "unsure"
    assert bookpage.verdict(bookpage.Layout(**{**vars(found), "drawn": 0.1})) == "not"
    sparse = {**vars(found), "panels": 0, "across": 0, "down": 0, "bubbles": 0, "area_ink": 0.01}
    assert bookpage.verdict(bookpage.Layout(**sparse)) == "not"


def test_a_frame_is_known_again_by_its_digest():
    a = np.zeros((40, 64, 3), np.uint8)
    b = a.copy()
    assert bookpage.digest(a) == bookpage.digest(b)
    b[::8, ::8] = 255
    assert bookpage.digest(a) != bookpage.digest(b)
    assert bookpage.judge(a) == "not"  # (black: no ink on a dark paper)
