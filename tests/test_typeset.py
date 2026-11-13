from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from taslation.regions import TextRegion
from taslation.render import letter_text, find_font, fit_text, inner_rect, layout_text, load_font, shape_layout, wrap_lines
from taslation.render.erase import erase_region


def _ellipse_mask(w=200, h=300):
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def test_inner_rect_lies_inside_mask():
    mask = _ellipse_mask()
    x0, y0, x1, y1 = inner_rect(mask)
    assert x1 > x0 and y1 > y0
    assert mask[y0:y1, x0:x1].min() == 255
    assert (x1 - x0) * (y1 - y0) > 0.3 * mask.sum() / 255


def test_wrap_and_fit():
    font_path = find_font()
    font = load_font(str(font_path) if font_path else None, 20)
    lines = wrap_lines("one two three four five six seven", font, 120)
    assert len(lines) >= 2
    assert all(font.getlength(ln) <= 120 for ln in lines)
    assert wrap_lines("supercalifragilistic", font, 60)  # long word is broken, not dropped
    f, lines, size = fit_text("It isn't over yet. Not even close!", str(font_path) if font_path else None, 160, 120, 9, 60)
    assert 9 <= size <= 60 and lines
    assert all(f.getlength(ln) <= 160 for ln in lines)
    _, _, small = fit_text("x" * 400, str(font_path) if font_path else None, 60, 40, 9, 60)
    assert small == 9


def _small_font():
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return load_font(spec.path, 20)


def test_a_short_word_stays_whole_where_it_fits_nowhere():
    font = _small_font()
    narrow = int(font.getlength("Dam")) + 1  # "Dam" fits, "Damn" does not
    assert wrap_lines("Damn it", font, narrow) == ["Damn", "it"]
    for word in ("Damn!", "*Damn*", "Hmph.", "don't", "R2D2R2D2R2D2", "1234567890"):
        assert wrap_lines(word, font, 12) == [word], word  # under six letters, or no two letters side by side


def test_a_word_split_as_the_last_resort_shows_its_hyphen_and_three_letters_on_each_side():
    font = _small_font()
    width = lambda text: int(font.getlength(text)) + 1  # noqa: E731
    assert wrap_lines("Dammit", font, width("Damm-")) == ["Dam-", "mit"]  # the shortest word that may be split
    assert wrap_lines("Dammit", font, 12) == ["Dam-", "mit"]  # past the line rather than a shorter part
    assert wrap_lines("Bastard!", font, width("Basta-")) == ["Bast-", "ard!"]  # not "Basta-", "rd!"
    assert wrap_lines("well-known", font, width("well-")) == ["well-", "known"]  # its own hyphen, not another
    lines = wrap_lines("Extraordinarily", font, width("Extra-"))
    assert len(lines) > 2 and "".join(ln.removesuffix("-") for ln in lines) == "Extraordinarily"
    assert all(ln.endswith("-") for ln in lines[:-1]) and not lines[-1].endswith("-")
    assert all(len(ln.removesuffix("-")) >= 3 for ln in lines)
    assert wrap_lines("пиши-пиши", font, 1)[0].endswith("-")  # Cyrillic as Latin


def test_another_script_splits_as_before_without_a_hyphen():
    font = _small_font()
    assert "".join(wrap_lines("안녕하세요", font, 30, script="kr")) == "안녕하세요"
    assert all("-" not in ln for ln in wrap_lines("안녕하세요", font, 30, script="kr"))
    assert "".join(wrap_lines("こんにちは", font, 30, script="jp")) == "こんにちは"


def test_damn_it_in_a_narrow_bubble_is_condensed_or_set_whole_never_split():
    fp = find_font().path
    if not fp:
        pytest.skip("no font file on this computer")
    fits = [layout_text(_ellipse_mask(w, 90), "Damn it", fp, 9, 64) for w in range(14, 70)]
    assert all(" ".join(ln for ln, _x, _y in fit.lines).split() == ["Damn", "it"] for fit in fits)
    assert any(fit.condense < 1.0 for fit in fits)  # where a little narrower is enough, it is set narrower
    laid = shape_layout(_ellipse_mask(24, 90), "Damn it", fp, 9, 9)  # along the shape too
    assert laid is not None and [ln for ln, _x, _y in laid[1]] == ["Damn", "it"]
    long_word = layout_text(_ellipse_mask(30, 200), "Extraordinarily", fp, 9, 64, hyphenate=False, condense=False)
    assert long_word.size == 9 and all(ln.endswith("-") for ln, _x, _y in long_word.lines[:-1])
    assert len(long_word.lines) > 1  # a long word may still be split


def test_erase_and_draw_change_only_the_bubble():
    img = np.full((400, 300, 3), 255, np.uint8)
    img[150:160, 120:180] = 0  # fake text strokes
    mask = _ellipse_mask(200, 300)
    region = TextRegion(50, 50, 250, 350, mask, (120, 150, 180, 160))
    before = img.copy()
    bg = erase_region(img, region)
    assert bg == (255, 255, 255)
    assert img[150:160, 120:180].min() == 255  # strokes gone
    assert (img[:50] == before[:50]).all() and (img[350:] == before[350:]).all()
    pil = Image.fromarray(img)
    font_path = find_font()
    size = letter_text(pil, region, "Hello there", str(font_path) if font_path else None, 9, 60).size
    assert size >= 9
    out = np.asarray(pil)
    assert out[50:350, 50:250].min() < 100  # text drawn
    assert (out[:50] == 255).all()


def _ink_outside(img: Image.Image, mask: np.ndarray) -> int:
    ink = np.asarray(img.convert("L")) < 128
    return int((ink & (mask == 0)).sum())


def test_lines_along_the_shape_give_a_larger_font_than_the_rectangle():
    from taslation.render import shape_layout

    mask = _ellipse_mask(200, 300)
    text = "Why on earth did you weld the hatch shut, Pyo?! That really hurt, you know!"
    font_path = find_font()
    fp = str(font_path) if font_path else None
    x0, y0, x1, y1 = inner_rect(mask)
    _f, _lines, rect_size = fit_text(text, fp, x1 - x0, y1 - y0, 9, 60)
    shaped = shape_layout(mask, text, fp, 9, 60)
    assert shaped is not None
    font, placed, size = shaped
    assert size > rect_size
    # every line lies inside the mask, words are whole, and the block sits around the centre
    words = text.split()
    for ln, xc, top in placed:
        assert all(w in words for w in ln.split())
        half = font.getlength(ln) / 2.0
        band = mask[top : int(top + size * 1.12), int(xc - half) : int(xc + half) + 1]
        assert band.size and band.min() == 255
    mid = (placed[0][2] + placed[-1][2] + size * 1.12) / 2.0
    assert abs(mid - 150) < 0.12 * 300
    region = TextRegion(0, 0, 200, 300, mask, (60, 100, 140, 200))
    img = Image.new("RGB", (200, 300), "white")
    assert letter_text(img, region, text, fp, 9, 60, hyphenate=False, condense=False).size == size
    assert _ink_outside(img, mask) == 0
    img = Image.new("RGB", (200, 300), "white")
    assert letter_text(img, region, text, fp, 9, 60).size >= size  # at the limit it may be condensed: not smaller
    assert _ink_outside(img, mask) == 0


def test_shape_layout_breaks_words_only_at_the_minimum_size():
    from taslation.render import shape_layout

    mask = _ellipse_mask(70, 90)
    font_path = find_font()
    fp = str(font_path) if font_path else None
    shaped = shape_layout(mask, "an extraordinarily long word", fp, 9, 60)
    assert shaped is not None
    font, placed, size = shaped
    assert size == 9 and len(placed) >= 2  # the long word had to be broken, at the minimum size only
    assert shape_layout(mask, "x" * 400, fp, 9, 60) is None  # does not fit at all: the caller falls back


def test_shape_layout_wraps_cjk_by_character():
    from pathlib import Path

    from taslation.render import shape_layout

    fonts = [r"C:\Windows\Fonts\msgothic.ttc", r"C:\Windows\Fonts\meiryo.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    fp = next((f for f in fonts if Path(f).is_file()), None)
    if fp is None:
        import pytest

        pytest.skip("no CJK font available")
    mask = _ellipse_mask(160, 200)
    shaped = shape_layout(mask, "今天天气真好，我们去散步吧。然后吃点东西。", fp, 9, 60, script="sc")
    assert shaped is not None
    _font, placed, _size = shaped
    assert len(placed) >= 2 and all(not ln[0] in "，。" for ln in placed)  # no line starts with a stop


def test_text_room_grows_with_the_bubble_and_shrinks_with_the_size():
    from taslation.render import text_room

    font_path = find_font()
    fp = str(font_path) if font_path else None
    small = text_room(_ellipse_mask(60, 40), fp, 11)
    big = text_room(_ellipse_mask(200, 300), fp, 11)
    assert 0 <= small < 30 < big
    assert text_room(_ellipse_mask(200, 300), fp, 20) < big
