"""What a page's text is not, and what lettering must not show: a credit on a cover is left alone, and a character no font
has is left out rather than drawn as a box."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from taslation.config import Settings
from taslation.pipeline import Pipeline, looks_like_credit, looks_like_print
from taslation.regions import TextRegion
from taslation.render import covers, drawable, fonts


def region(kind="text", box=(100, 100, 200, 300), **more):
    x0, y0, x1, y1 = box
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box=box, kind=kind, **more)


# ------------------------------------------------------------------ credits are not dialogue
HORIZONTAL, VERTICAL = (0, 0, 154, 83), (0, 0, 40, 200)


@pytest.mark.parametrize("text, box, expected", [
    ("小学館", HORIZONTAL, True),  # a name set across: no kana, no mark
    ("田中一郎", VERTICAL, False),  # the same down: could be anything
    ("原作 山田太郎", VERTICAL, True),  # a label of the colophon, whichever way it runs
    ("発行所 集英社", VERTICAL, True),
    ("©山田太郎", VERTICAL, True),
    ("東京へ", HORIZONTAL, False),  # kana: speech
    ("本当!", HORIZONTAL, False),  # a mark of speech
    ("本当…", HORIZONTAL, False),
    ("漫画を読む", VERTICAL, False),  # a label's word in a sentence
])
def test_a_credit_names_and_does_not_say(text, box, expected):
    assert looks_like_credit(text, box) is expected


def test_only_loose_lettering_is_asked(settings):
    p = Pipeline(settings, translator=None, cache=None)
    assert p._judge(region("text", (0, 0, 154, 83)), "小学館", 0.9, 0) == "print"
    assert p._judge(region("text-dark", (0, 0, 154, 83)), "小学館", 0.9, 0) == "print"
    assert p._judge(region("text-on-page", (0, 0, 154, 83)), "小学館", 0.9, 0) == "untranslated"  # a caption in a box
    assert p._judge(region("bubble", (0, 0, 154, 83)), "小学館", 0.9, 0) == "untranslated"
    assert p._judge(region("manual", (0, 0, 154, 83)), "小学館", 0.9, 0) == "untranslated"  # the reader marked it


def test_a_model_bubble_with_no_outline_to_it_counts_as_loose(settings):
    p = Pipeline(settings, translator=None, cache=None)
    r = region("bubble", (0, 0, 154, 83), from_model=True)
    r.after = region("bubble", (0, 0, 154, 83), tier=3)
    assert p._judge(r, "小学館", 0.9, 0) == "print"
    r.after.tier = 0
    assert p._judge(r, "小学館", 0.9, 0) == "untranslated"


def test_what_was_print_stays_print():
    assert looks_like_print("Rating 4.5 store", (0, 0, 300, 30))
    assert not looks_like_print("そうだね", (0, 0, 40, 200))


# ------------------------------------------------------------------ no box for a missing glyph
@pytest.fixture
def sans(monkeypatch):
    """A font that has ASCII only."""
    monkeypatch.setattr(fonts, "_coverage", lambda path: (((0x20,), (0x7e,)) if path == "ascii.ttf"
                                                          else ((0x20,), (0x2fff,)) if path == "signs.ttf" else None))


def test_a_character_the_font_lacks_is_left_out_of_the_lettering(sans):
    assert not covers("ascii.ttf", "Love ♥")
    assert drawable("ascii.ttf", "Love ♥ you") == "Love  you"
    assert drawable("ascii.ttf", "plain") == "plain"


def test_a_font_that_cannot_be_read_says_nothing_about_its_glyphs(sans):
    assert drawable("broken.ttf", "Love ♥") == "Love ♥"
    assert drawable(None, "Love ♥") == "Love ♥"


def test_a_sign_no_scripts_font_has_goes_to_a_font_that_has_it(sans, tmp_path, monkeypatch):
    sign = tmp_path / "signs.ttf"
    sign.write_bytes(b"x")
    monkeypatch.setattr(fonts, "_by_script", lambda *a: fonts.FontSpec("ascii.ttf"))
    monkeypatch.setattr(fonts, "_system_candidates", lambda script: [Path("nowhere.ttf"), sign])
    real = fonts._coverage
    monkeypatch.setattr(fonts, "_coverage", lambda path: real("signs.ttf") if str(path) == str(sign) else real(path))
    assert fonts.find_font("", tmp_path, "Love ♥").path == str(sign)
    assert fonts.find_font("", tmp_path, "Love").path == "ascii.ttf"


def test_the_lettering_of_a_real_font_loses_no_letters():
    font = fonts.find_font("", Settings().fonts_dir, "Hello, world!")
    assert not font or drawable(font.path, "Hello, world!") == "Hello, world!"


def test_a_region_with_a_sign_no_font_has_is_lettered_without_it(settings, monkeypatch):
    p = Pipeline(settings, translator=None, cache=None)
    seen = []
    monkeypatch.setattr("taslation.pipeline.drawable", lambda path, text: seen.append(text) or text.replace("♥", ""))
    p._set_text(None, region("bubble", (0, 0, 200, 200)), "Love ♥", (255, 255, 255), None)
    assert seen == ["Love ♥"]
