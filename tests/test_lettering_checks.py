"""The checks of an automatic lettering (`typeset.lettering_flags`): what is still wrong with a block once it is set
(letters at the bubble's edge, the block off the bubble's centre, a word split with a hyphen, a lone short word, an
hourglass, letters hard to see on their ground) is said in the region's lettering flags and so in the review list, in
every language of the window; a bubble set well says nothing, and a column of a word or two a line is no lone word."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation.i18n import CATALOGS
from taslation.regions import TextRegion
from taslation.render import find_font, letter_text, typeset
from taslation.render.typeset import (HOURGLASS_LINE, HYPHENATED, LETTER_CHECKS, LONE_WORD, LOW_CONTRAST, OFF_CENTRE,
                                      TIGHT, layout_text, lettering_flags)
from taslation.ui.dialogs import review


def _font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ellipse(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - w / 2 + 0.5) / (w / 2)) ** 2 + ((yy - h / 2 + 0.5) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _joined(w: int = 380, h: int = 200) -> np.ndarray:
    """Two round bubbles side by side, joined at a neck."""
    yy, xx = np.mgrid[0:h, 0:w]
    r = h / 2
    left = (xx - r) ** 2 + (yy - r) ** 2 <= r * r
    right = (xx - (w - r)) ** 2 + (yy - r) ** 2 <= r * r
    return ((left | right) * 255).astype(np.uint8)


def _letter(mask: np.ndarray, text: str, ground=(255, 255, 255), **kwargs):
    h, w = mask.shape
    region = TextRegion(0, 0, w, h, mask, (w // 4, h // 4, 3 * w // 4, 3 * h // 4))
    image = Image.new("RGB", (w, h), ground)
    return letter_text(image, region, text, _font(), 9, 64, background=ground, **kwargs)


def test_a_bubble_set_well_says_nothing():
    assert _letter(_ellipse(240, 200), "Where did everyone go all of a sudden?").flags == ()
    assert _letter(_ellipse(200, 160), "Hey!").flags == ()


def test_a_translation_set_in_one_of_two_joined_bubbles_is_off_centre():
    done = _letter(_joined(), "I told you so. Now we have to walk all the way home in the rain, the two of us.")
    assert OFF_CENTRE in done.flags


def test_a_word_split_at_the_limit_is_said():
    done = _letter(_ellipse(60, 120), "Extraordinarily")
    assert HYPHENATED in done.flags


def test_letters_hard_to_see_on_their_ground_unless_outlined():
    grey, mask, text = (120, 120, 120), _ellipse(240, 200), "Where did everyone go?"
    assert LOW_CONTRAST in _letter(mask, text, grey, color=(150, 150, 150), outline=False).flags
    assert LOW_CONTRAST not in _letter(mask, text, grey, color=(150, 150, 150), outline=True).flags
    assert LOW_CONTRAST not in _letter(mask, text, grey).flags  # the automatic ink: black on a light grey


def _checked(mask: np.ndarray, fit, lines=None) -> tuple[str, ...]:
    h, w = mask.shape
    lines = fit.lines if lines is None else lines
    return lettering_flags(np.full((h, w, 3), 255, np.uint8), mask, fit, lines, "lgc", (0, 0, 0), False, True)


def test_letters_at_the_edge_are_said():
    mask = np.full((60, 220), 255, np.uint8)
    fit = layout_text(mask, "Hello there", _font(), 9, 30)
    assert TIGHT not in _checked(mask, fit)
    at_edge = [(t, fit.font.width(t) / 2.0 - 4, top) for t, _x, top in fit.lines]  # each line run past the left
    assert TIGHT in _checked(mask, fit, at_edge)


def test_a_lone_word_and_an_hourglass_but_not_in_a_column():
    mask = np.full((200, 400), 255, np.uint8)
    fit = layout_text(mask, "I have to go now or I will be late", _font(), 9, 20)

    def set_as(*texts: str):
        return replace(fit, lines=[(t, 200.0, 20 + k * fit.line_height) for k, t in enumerate(texts)])

    found = _checked(mask, set_as("I have to go", "now", "or I will be late"))
    assert LONE_WORD in found and HOURGLASS_LINE in found
    found = _checked(mask, set_as("You", "call", "this", "a plan?"))
    assert LONE_WORD not in found and HOURGLASS_LINE not in found  # a narrow bubble is set so


def test_the_review_list_says_each_check_in_every_language():
    assert set(LETTER_CHECKS) <= set(review.FIT_REASONS)
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(review.FIT_REASONS[c] in catalog for c in LETTER_CHECKS), code
    region = SimpleNamespace(status="translated", flags=[], reader_note="", letter_flags=(OFF_CENTRE, HYPHENATED),
                             translated_text="Hi")
    rows = review.review_rows([region])
    assert rows and "centre" in rows[0][1] and "hyphen" in rows[0][1]
    assert typeset.Lettered(12, (OFF_CENTRE,)).flags == (OFF_CENTRE,)
