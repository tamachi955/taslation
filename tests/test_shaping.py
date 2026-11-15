"""Devanagari and Bengali shaped with HarfBuzz (`taslation.render.shaping`): conjuncts and reordered vowel signs, the
width measured is the width drawn, letter spacing keeps a conjunct whole, every other script is drawn by Pillow as
before, and without uharfbuzz the two scripts are drawn letter by letter as before and the window can say so.

The samples are ordinary dictionary words. The fonts are the models folder's Noto Sans and the system's (Nirmala UI
on Windows); a test skips where neither is there, and the shaping tests where uharfbuzz is not installed."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from taslation.config import Settings
from taslation.regions import TextRegion
from taslation.render import FontSpec, Lettering, find_font, letter_text, load_font, shaping, styled_font
from taslation.render import lettering as lettering_module
from taslation.render import typeset
from taslation.render.fonts import can_draw, split_face
from taslation.render.lettering import clusters
from taslation.render.typeset import _ink_rows

HINDI = "हिन्दी विद्यालय"  # Hindi school
BENGALI = "বাংলা বিদ্যালয়"  # Bengali school
WORDS = {  # word -> its script's sample; each has a conjunct or a vowel sign drawn before its consonant
    "हिन्दी": HINDI, "क्षमा": HINDI, "विद्यालय": HINDI, "धर्म": HINDI, "प्रकाश": HINDI,  # Hindi, forgiveness,
    "ক্ষমা": BENGALI, "কিন্তু": BENGALI, "বিদ্যালয়": BENGALI,  # school, religion, light; forgiveness, but, school
}


def _fonts(text: str) -> list[FontSpec]:
    """The fonts the lettering would take for *text*: the models folder's, then the system's (each once)."""
    found: list[FontSpec] = []
    for folder in (Settings().fonts_dir, None):
        spec = find_font("", folder, text)
        if spec.path and can_draw(spec.path, text) and spec not in found:
            found.append(spec)
    if not found:
        pytest.skip("no font for this script on this computer")
    return found


def _hb():
    return pytest.importorskip("uharfbuzz")


def _nominal(spec: FontSpec, ch: str) -> int:
    """The glyph the font's character map gives *ch* (what Pillow draws for it unshaped)."""
    hb = _hb()
    file, index = split_face(spec.path)
    return hb.Font(hb.Face(hb.Blob(Path(file).read_bytes()), index)).get_nominal_glyph(ord(ch))


def _ink(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L")) < 128


@pytest.fixture
def fresh_caches():
    """The shaping and lettering caches emptied before and after (a test that takes uharfbuzz away)."""
    def clear():
        for cached in (shaping.shaper, shaping._source, shaping._extents, shaping._hb_font, shaping._shaped,
                       shaping._drawing_font, lettering_module._styled):
            cached.cache_clear()
        _ink_rows.cache_clear()
        typeset._LAYOUTS.clear()
    clear()
    yield
    clear()


def test_the_scripts_shaped_are_told_by_their_letters():
    assert shaping.script_tag("हिन्दी") == "deva" and shaping.script_tag("বাংলা") == "beng"
    assert shaping.script_tag("বাংলা।") == "beng"  # the danda is Devanagari's but Bengali writes it too
    assert shaping.script_tag("OK, हिन्दी 42") == "deva"
    for other in ("Hello, world!", "こんにちは", "你好", "안녕하세요", "สวัสดี", "مرحبا", "שלום", "Привет", "।", ""):
        assert shaping.script_tag(other) is None, other
    assert not shaping.letter_by_letter("English") and not shaping.letter_by_letter("Japanese")


@pytest.mark.parametrize("word", WORDS)
def test_a_conjunct_or_a_reph_takes_fewer_glyphs_than_code_points(word):
    _hb()
    for spec in _fonts(WORDS[word]):
        glyphs = shaping.shaper(spec.path, 40, spec.bold_variation).glyphs(word)
        assert 0 not in [g for g, _x, _y in glyphs], (spec.path, word)  # no glyph missing
        if word in ("বিদ্যালয়",):  # its conjunct is a consonant and a sign beside it: as many glyphs, but reordered
            assert len(glyphs) <= len(word), (spec.path, word)
        else:
            assert len(glyphs) < len(word), (spec.path, word, len(glyphs))


@pytest.mark.parametrize("pair,consonant", [("कि", "क"), ("हि", "ह"), ("কি", "ক"), ("বি", "ব")])
def test_the_i_sign_is_drawn_before_the_consonant_it_follows_in_the_text(pair, consonant):
    _hb()
    for spec in _fonts(HINDI if consonant < "ঀ" else BENGALI):
        glyphs = shaping.shaper(spec.path, 40, spec.bold_variation).glyphs(pair)
        assert len(glyphs) == 2
        (sign, x_sign, _y0), (base, x_base, _y1) = glyphs
        assert base == _nominal(spec, consonant) and sign != base, spec.path  # unshaped: the consonant first
        assert x_sign < x_base


def test_the_bengali_o_sign_parts_go_either_side_of_its_consonant():
    _hb()
    for spec in _fonts(BENGALI):
        glyphs = [g for g, _x, _y in shaping.shaper(spec.path, 40, spec.bold_variation).glyphs("কো")]  # ka + o
        assert len(glyphs) == 3 and glyphs[1] == _nominal(spec, "ক"), spec.path  # e-sign, ka, aa-sign
        assert glyphs[2] == _nominal(spec, "া"), spec.path


@pytest.mark.parametrize("text", [HINDI, BENGALI])
def test_the_width_measured_is_the_width_drawn(text):
    _hb()
    for spec in _fonts(text):
        sf = styled_font(Lettering(spec.path, spec.bold_variation), 40)
        width = sf.width(text)
        image = Image.new("RGB", (40 + 2 * width, 100), (255, 255, 255))
        sf.draw(image, 20, 10, text, (0, 0, 0))
        columns = np.flatnonzero(_ink(image).any(axis=0))
        assert abs(int(columns[0]) - 20) <= 4, spec.path  # the first glyph's side bearing
        assert abs(int(columns[-1]) + 1 - (20 + width)) <= 4, (spec.path, int(columns[-1]) + 1, 20 + width)
        unshaped = load_font(spec.path, 40, spec.bold_variation).getlength(text)
        assert abs(unshaped - width) > 8, spec.path  # what the letter-by-letter measure got wrong


@pytest.mark.parametrize("text", [HINDI, BENGALI, "धर्म"])
def test_the_rows_measured_are_the_rows_drawn(text):
    _hb()
    for spec in _fonts(text):
        sf = styled_font(Lettering(spec.path, spec.bold_variation, emphasis=False), 40)  # one face
        top, bottom = _ink_rows(sf, text, "devanagari" if text != BENGALI else "bengali")
        image = Image.new("RGB", (400, 140), (255, 255, 255))
        sf.draw(image, 10, 30, text, (0, 0, 0))
        rows = np.flatnonzero(_ink(image).any(axis=1))
        assert abs(int(rows[0]) - (30 + top)) <= 1 and abs(int(rows[-1]) + 1 - (30 + bottom)) <= 1, spec.path


def test_letter_spacing_keeps_a_conjunct_and_its_signs_together():
    _hb()
    assert [c for _i, c in clusters("क्षमा")] == ["क्ष", "मा"]
    assert [c for _i, c in clusters("ক্ষমা")] == ["ক্ষ", "মা"]
    assert [c for _i, c in clusters("हिन्दी")] == ["हि", "न्दी"]
    assert [c for _i, c in clusters("Hello")] == list("Hello")  # Latin as before


@pytest.mark.parametrize("style", [{}, {"italic": True}, {"bold": True}, {"tracking": 3}, {"condense": 0.92}])
def test_every_style_draws_the_shaped_glyphs(style):
    _hb()
    for spec in _fonts(HINDI):
        sf = styled_font(Lettering(spec.path, spec.bold_variation, **style), 30)
        image = Image.new("RGB", (40 + 2 * sf.width(HINDI), 90), (128, 128, 128))
        sf.draw(image, 20, 20, HINDI, (0, 0, 0), ((255, 255, 255), 2))
        ink = np.asarray(image.convert("L"))
        columns = np.flatnonzero((ink < 60).any(axis=0))
        assert (ink > 200).any() and columns.size, (style, spec.path)  # the outline and the glyphs
        assert int(columns[-1]) + 1 - 20 <= sf.width(HINDI) + 12, (style, spec.path)  # set as wide as measured


@pytest.mark.parametrize("text", [HINDI + " " + "क्षमा प्रकाश धर्म", BENGALI + " " + "কিন্তু ক্ষমা"])
def test_a_bubble_of_shaped_text_keeps_its_ink_inside(text):
    _hb()
    for spec in _fonts(text):
        image = Image.new("RGB", (320, 240), (255, 255, 255))
        mask = np.zeros((200, 260), np.uint8)
        cv2.ellipse(mask, (130, 100), (125, 95), 0, 0, 360, 255, -1)
        region = TextRegion(30, 20, 290, 220, mask, (50, 40, 270, 200))
        lettered = letter_text(image, region, text, spec.path, 9, 60, bold_variation=spec.bold_variation)
        assert lettered.size >= 12, spec.path
        ink = _ink(image)[20:220, 30:290]
        assert ink.any() and not (ink & (mask == 0)).any(), spec.path


def test_latin_cjk_and_right_to_left_text_never_go_through_the_shaper(monkeypatch):
    """Every other script is laid out and drawn by Pillow exactly as before (the shaper is never asked)."""
    def refused(*_args, **_kwargs):
        raise AssertionError("shaped")

    monkeypatch.setattr(shaping, "shaper", refused)
    samples = ["Hello there, *really*?", "こんにちは、いい天気ですね。", "你好，今天天气真不错。", "안녕하세요", "สวัสดี วันนี้",
               "مرحباً، الطقس جميل", "שלום, מזג האוויר", "Привет, как дела?"]
    for text in samples:
        spec = find_font("", None, text)
        for lettering in (Lettering(spec.path, spec.bold_variation), Lettering(spec.path, spec.bold_variation, True),
                          Lettering(spec.path, spec.bold_variation, tracking=2, condense=0.94)):
            image = Image.new("RGB", (300, 200), (255, 255, 255))
            region = TextRegion(10, 10, 290, 190, np.full((180, 280), 255, np.uint8), (10, 10, 290, 190))
            letter_text(image, region, text, lettering, 9, 40)


def test_a_latin_line_is_pillows_own_drawing_pixel_for_pixel():
    spec = find_font("", None, "Hello")
    if not spec.path:
        pytest.skip("no font file on this computer")
    a, b = (Image.new("RGB", (300, 60), (255, 255, 255)) for _ in range(2))
    styled_font(Lettering(spec.path, spec.bold_variation), 30).draw(a, 5, 5, "Hello, world", (0, 0, 0), ((255, 0, 0), 2))
    draw, font = ImageDraw.Draw(b), load_font(spec.path, 30, spec.bold_variation)
    draw.text((5, 5), "Hello, world", font=font, fill=(255, 0, 0), stroke_width=2, stroke_fill=(255, 0, 0))
    draw.text((5, 5), "Hello, world", font=font, fill=(0, 0, 0), stroke_width=0, stroke_fill=(0, 0, 0))
    assert np.array_equal(np.asarray(a), np.asarray(b))


def test_without_uharfbuzz_the_scripts_are_drawn_as_before_and_the_window_can_say_so(monkeypatch, fresh_caches):
    monkeypatch.setattr(shaping, "_harfbuzz", lambda: None)
    monkeypatch.setattr(shaping, "_raqm", lambda: False)
    assert not shaping.available()
    assert shaping.letter_by_letter("Hindi") and shaping.letter_by_letter("Bengali")
    assert not shaping.letter_by_letter("English") and not shaping.letter_by_letter("Arabic")
    assert [c for _i, c in clusters("क्षमा")] == ["क्", "ष", "मा"]  # letter spacing between the letters, as before
    for text in (HINDI, BENGALI):
        spec = _fonts(text)[0]
        assert shaping.shaper(spec.path, 30, spec.bold_variation) is None
        sf = styled_font(Lettering(spec.path, spec.bold_variation), 30)
        font = load_font(spec.path, 30, spec.bold_variation)
        assert sf.width(text) == round(font.getlength(text))  # measured letter by letter
        a, b = (Image.new("RGB", (400, 70), (255, 255, 255)) for _ in range(2))
        sf.draw(a, 5, 5, text, (0, 0, 0))
        ImageDraw.Draw(b).text((5, 5), text, font=font, fill=(0, 0, 0), stroke_width=0, stroke_fill=(0, 0, 0))
        assert np.array_equal(np.asarray(a), np.asarray(b))  # and drawn as Pillow draws it
    monkeypatch.setattr(shaping, "_raqm", lambda: True)  # a Pillow with libraqm shapes by itself
    assert not shaping.letter_by_letter("Hindi")
