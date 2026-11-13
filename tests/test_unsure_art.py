"""Translator mode neither outlines nor labels the pieces of the drawing the OCR read unsure ("unsure reading" over a
sweat drop, an eye, a chin, a floor drain: `progress.unsure_art`), and keeps the unsure lines labelled. The numbers
are those measured on the OpenMantra pages of the second end-to-end check (page 11 and page 31 of the tojime volume,
in a full-HD viewer); the real pages are read again when the dataset is there (TASLATION_REALDATA=1)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation.ui import app as app_mod
from taslation.ui.progress import UNSURE_BIG, unsure_art, usual_char

from conftest import requires_ocr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import openmantra  # noqa: E402


def _region(text, box, char, status="low-confidence", kind="text", glyph=0.0, conf=0.5):
    x0, y0, x1, y1 = box
    return SimpleNamespace(status=status, kind=kind, source_text=text, text_box=box, bbox=box, char_size=char,
                           glyph=glyph, ocr_confidence=conf, x0=x0, y0=y0, x1=x1, y1=y1, area=(x1 - x0) * (y1 - y0))


USUAL = 17.0  # the book's usual character, as measured on the tojime volume
ART = [  # (what it is, its reading, its text box, the size of its largest character)
    ("page 11: hair over the body", "ー", (1083, 652, 1100, 715), 55.4),
    ("page 11: a chin", "しこ", (925, 648, 1003, 688), 50.8),
    ("page 11: the floor drain", "スにー", (836, 856, 905, 936), 63.4),
    ("page 31: a face", "こ", (909, 680, 936, 707), 21.3),
    ("page 31: a sweat drop", "し", (660, 665, 668, 687), 20.5),
    ("page 31: an eye", "ン", (741, 917, 792, 951), 42.8),
    ("a line of hatching", "ーー・ー", (817, 990, 871, 997), 21.3),  # thinner than half a character
]
LINES = [  # unsure readings over a line of the book (OpenMantra's text boxes)
    ("a scream five times the usual size", "ああぁああ", (0, 0, 117, 203), 89.0, 0.49),
    ("a short question", "ここ！？", (0, 0, 62, 131), 26.0, 0.49),
    ("a title", "ドルーンん", (0, 0, 229, 176), 77.0, 0.62),
]


@pytest.mark.parametrize("what,text,box,char", ART, ids=[a[0] for a in ART])
def test_an_unsure_reading_of_the_drawing_is_no_region_to_show(what, text, box, char):
    assert unsure_art(_region(text, box, char), USUAL), what


def test_large_characters_guessed_at_are_the_drawing_and_a_large_line_read_with_some_confidence_is_not():
    bodies = _region("んバリ！ト", (838, 182, 1193, 256), 79.0, conf=0.22)  # page 11 in the viewer: two bodies
    assert unsure_art(bodies, 22.8)
    assert not unsure_art(_region("んバリ！ト", (838, 182, 1193, 256), 79.0, conf=0.49), 22.8)


@pytest.mark.parametrize("what,text,box,char,conf", LINES, ids=[a[0] for a in LINES])
def test_an_unsure_line_keeps_its_label(what, text, box, char, conf):
    assert not unsure_art(_region(text, box, char, conf=conf), USUAL), what


def test_only_unsure_readings_and_never_the_readers_own_regions():
    for status in ("untranslated", "translated", "ocr-noise", "sfx"):
        assert not unsure_art(_region("し", (0, 0, 8, 22), 20.5, status=status), USUAL)
    assert not unsure_art(_region("し", (0, 0, 8, 22), 20.5, kind="manual"), USUAL)
    # with nothing to measure against, only the length tells
    assert unsure_art(_region("ン", (0, 0, 51, 34), 42.8), 0.0)
    assert not unsure_art(_region("スにー", (0, 0, 69, 80), 63.4), 0.0)
    assert unsure_art(_region("スにー", (0, 0, 69, 80), UNSURE_BIG * USUAL + 1), USUAL)


def test_the_usual_size_is_the_pages_text_then_the_books_then_the_glyphs():
    text = [_region("本文です", (0, 0, 20, 80), c, status="untranslated") for c in (18.0, 20.0, 22.0)]
    art = _region("し", (0, 0, 8, 22), 90.0)
    assert usual_char([*text, art]) == 20.0  # the unsure readings do not count
    cached = [_region("本文です", (0, 0, 20, 80), 0.0, status="translated", glyph=g) for g in (15.0, 16.0, 17.0)]
    assert usual_char(cached, [17.5, 16.5]) == 17.0  # the page's lines came from the cache: the book's so far
    assert usual_char(cached) == 16.0 and usual_char([art]) == 0.0


class Page:
    """The parts of the window translator mode's outlines and clicks use."""

    _page_regions = app_mod.App._page_regions
    _overlay_items = app_mod.App._overlay_items
    _noted_regions = app_mod.App._noted_regions
    _region_at = app_mod.App._region_at

    def __init__(self, regions, book_sizes=()):
        self.last_result = SimpleNamespace(regions=regions)
        self.pipeline = SimpleNamespace(_book_sizes=list(book_sizes))
        self.role_var = SimpleNamespace(get=lambda: "translator")
        self.reading, self._ordering = False, None


def _line(box, char=18.0):
    r = _region("こんにちは", box, char, status="untranslated", kind="bubble")
    r.speaker, r.continues, r.flags, r.reader_note = "", False, [], ""
    return r


def test_translator_mode_outlines_the_lines_and_a_click_on_the_drawing_selects_nothing():
    line, drop = _line((100, 100, 140, 220)), _region("し", (300, 300, 308, 322), 20.5)
    shout = _region("ああぁああ", (400, 100, 517, 303), 89.0)
    for r in (drop, shout):
        r.speaker, r.continues, r.flags, r.reader_note = "", False, [], ""
    page = Page([line, drop, shout], book_sizes=[17.0] * 5)
    boxes = [item[0] for item in page._overlay_items()]
    assert boxes == [line.bbox, shout.bbox]  # the sweat drop is neither outlined nor labelled
    assert page._overlay_items()[1][2] == "unsure reading"  # the unsure line keeps its label
    assert page._region_at(303, 310) is None and page._region_at(120, 150) is line


class Switched:
    """The parts of the window that translator mode coming on over a cached page uses."""

    _complete_on_show = app_mod.App._complete_on_show

    def __init__(self, statuses):
        self.last_result = SimpleNamespace(regions=[SimpleNamespace(status=s) for s in statuses])
        self.reading, self.batch, self._batching, self.ready, self.busy = False, None, False, True, False
        self.idle = []

    def after_idle(self, func):
        self.idle.append(func)

    def translate_now(self):
        pass


def test_translator_mode_over_a_cached_page_reads_what_the_cache_has_no_bubble_for():
    """In reader mode a cached page's other regions are never read ("unmatched": mostly the drawing a run judged no
    text); translator mode coming on reads the page again, so they are judged and the drawing is left out."""
    w = Switched(["translated", "unmatched"])
    w._complete_on_show()
    assert w.idle == [w.translate_now]
    for change in ({"busy": True}, {"batch": object()}, {"reading": True}, {"ready": False}):
        w = Switched(["translated", "unmatched"])
        w.__dict__.update(change)
        w._complete_on_show()
        assert w.idle == [], change
    w = Switched(["translated", "low-confidence"])  # read already: nothing to do
    w._complete_on_show()
    assert w.idle == []


# ------------------------------------------------------------------ the real pages
REAL = openmantra.DEFAULT_ROOT
real_data = pytest.mark.skipif(not (REAL / "annotation.json").is_file() or os.environ.get("TASLATION_REALDATA") != "1",
                               reason="OpenMantra not fetched, or TASLATION_REALDATA not 1")


def _viewer_frame(image: Image.Image) -> Image.Image:
    """The page as the full-HD browser viewer of the end-to-end check draws it: fitted, centred on dark grey."""
    frame = Image.new("RGB", (1920, 1080), (43, 43, 43))
    scale = min(1920 / image.width, 1080 / image.height)
    page = image.convert("RGB").resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    frame.paste(page, ((1920 - page.width) // 2, (1080 - page.height) // 2))
    return frame


@real_data
@requires_ocr
@pytest.mark.page_models
def test_on_the_real_pages_no_unsure_reading_of_the_drawing_is_outlined(tmp_path):
    from taslation.cli import build_pipeline
    from taslation.config import Settings

    # (art_erase "lama": the page models on any computer, "auto" being "only where torch has a CUDA GPU")
    settings = Settings(state_dir=tmp_path / "state", detect_model="auto", art_erase="lama")
    settings.validate()
    pipeline = build_pipeline(settings, "none", None)
    pages = [p for p in openmantra.load() if p.series == "tojime_no_siora"]
    for number in (9, 10, 11, 31):  # (9 and 10 first: the book's usual size, as in the reading)
        result = pipeline.process(_viewer_frame(pages[number - 1].open()), use_cache=False, translate=False)
        window = Page(result.regions)
        window.pipeline = pipeline
        shown = window._page_regions()
        lines = [r for r in result.regions if r.status == "untranslated"]
        assert lines and all(any(r is s for s in shown) for r in lines), number  # every line is still there
        if number in (11, 31):
            unsure = [r.source_text for r in shown if r.status == "low-confidence"]
            assert not unsure, (number, unsure)
