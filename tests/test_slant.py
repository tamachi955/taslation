"""Lettering set at a slant: measured (`detect.tilt`), read turned upright, erased and lettered at its slant, kept in
the cache, set by the reader; and a region without a slant takes the straight path of before."""

from __future__ import annotations

import copy
import json
import random

import cv2
import numpy as np
import pytest
from PIL import Image

from taslation.annotations import RegionStyle
from taslation.cache import CachedBubble
from taslation.detect.tilt import (DEAD_ZONE, Upright, ink_frame, lettering_tilt, region_ink, turned_corners)
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.render import find_font, letter_text
from taslation.render.slant import slanted_outline, upright_region


def glyph(rng: random.Random, size: int) -> np.ndarray:
    """A glyph-like mark: a few strokes in a cell (white ground, black ink)."""
    cell = np.full((size, size), 255, np.uint8)
    m = max(2, size // 8)
    for _ in range(rng.randint(3, 5)):
        if rng.random() < 0.5:
            y = rng.randint(m, size - m)
            cv2.line(cell, (rng.randint(m, size // 3), y), (rng.randint(2 * size // 3, size - m), y), 0, max(2, size // 10))
        else:
            x = rng.randint(m, size - m)
            cv2.line(cell, (x, rng.randint(m, size // 3)), (x, rng.randint(2 * size // 3, size - m)), 0, max(2, size // 10))
    return cell


def lettering(columns: list[int], size: int = 24, vertical: bool = True, seed: int = 1, pad: int = 16) -> np.ndarray:
    """Upright lettering: *columns* (glyphs per line), right to left in columns (or top to bottom in rows)."""
    rng = random.Random(seed)
    pitch = int(size * 1.3)
    n = max(columns)
    w, h = (pitch * len(columns), size * n) if vertical else (size * n, pitch * len(columns))
    img = np.full((h + 2 * pad, w + 2 * pad), 255, np.uint8)
    for i, count in enumerate(columns):
        for j in range(count):
            if vertical:
                x, y = pad + w - (i + 1) * pitch + (pitch - size) // 2, pad + j * size
            else:
                x, y = pad + j * size, pad + i * pitch
            img[y:y + size, x:x + size] = np.minimum(img[y:y + size, x:x + size], glyph(rng, size))
    return img


def turned(gray: np.ndarray, angle: float) -> np.ndarray:
    """*gray* turned by *angle* degrees counter-clockwise (white round it)."""
    return Upright(gray.shape, -angle).turn(gray, 255)


# ---------------------------------------------------------------- the measure


@pytest.mark.parametrize("angle", [-30.0, -15.0, -8.0, 6.0, 12.0, 20.0, 35.0])
@pytest.mark.parametrize("vertical", [True, False])
def test_the_slant_of_lettering_is_measured_within_a_degree(angle, vertical):
    gray = turned(lettering([6, 5, 7], vertical=vertical), angle)
    tilt = lettering_tilt(gray < 140)
    assert abs(tilt.angle - angle) <= 1.0, tilt
    assert tilt.vertical is vertical


def test_upright_lettering_and_a_slight_slant_count_as_none():
    for angle in (0.0, 1.5, -2.0, DEAD_ZONE):
        tilt = lettering_tilt(turned(lettering([6, 5, 7]), angle) < 140)
        assert tilt.angle == 0.0, (angle, tilt)
    assert abs(lettering_tilt(turned(lettering([6, 5, 7]), 2.0) < 140).measured - 2.0) <= 1.5  # measured all the same


def test_a_lone_glyph_or_a_square_block_shows_no_slant():
    for columns in ([1], [2, 2]):
        for seed in range(1, 6):
            assert lettering_tilt(turned(lettering(columns, seed=seed), 15.0) < 140).angle == 0.0, (columns, seed)
    assert lettering_tilt(np.zeros((40, 40), bool)).angle == 0.0


# ---------------------------------------------------------------- short words


WORDS = ("目元", "馬鹿か", "本当に", "なるほど", "アンタは", "社長室", "待て", "行くぞ", "何だと", "まさか")


def word(text: str, size: int = 28, vertical: bool = True, pad: int = 14) -> np.ndarray:
    """*text* set upright in a Japanese font, one glyph per cell (as lettering is set), white ground."""
    from PIL import ImageDraw, ImageFont

    from taslation.render.fonts import covers

    spec = find_font(text="日本語", language="Japanese")
    if not spec.path or not covers(spec.path, text):
        pytest.skip("no Japanese font on this computer")
    font = ImageFont.truetype(spec.path, size)
    n = len(text)
    w, h = (size + 2 * pad, size * n + 2 * pad) if vertical else (size * n + 2 * pad, size + 2 * pad)
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    for j, ch in enumerate(text):
        draw.text((pad, pad + j * size) if vertical else (pad + j * size, pad), ch, font=font, fill=0)
    return np.asarray(img)


@pytest.mark.parametrize("angle", [-20.0, -8.0, 5.0, 12.0])
@pytest.mark.parametrize("vertical", [True, False])
def test_the_slant_of_a_short_word_is_measured(angle, vertical):
    found = 0
    for text in (t for t in WORDS if len(t) <= 3):  # (four glyphs in five pieces or more: the long lines' search)
        tilt = lettering_tilt(turned(word(text, vertical=vertical), angle) < 140)
        if tilt.angle:
            found += 1
            assert tilt.short and abs(tilt.angle - angle) <= 1.5, (len(text), tilt)
            assert tilt.vertical is vertical, tilt
    # a word whose glyphs lean its shape this way or that stays upright: a missed slant, never a wrong one; at 5
    # degrees, near the dead zone, most are missed
    assert found >= (1 if abs(angle) < 8 else 2), found


def test_a_short_words_slant_comes_from_the_short_measure():
    tilt = lettering_tilt(turned(word("目元"), 10.0) < 140)
    assert tilt.short and abs(tilt.angle - 10.0) <= 1.5, tilt


@pytest.mark.parametrize("vertical", [True, False])
def test_an_upright_short_word_and_a_slight_slant_stay_upright(vertical):
    for text in (*WORDS, "あっ", "えっ!?", "はぁ", "くそっ", "ちょっと"):
        for angle in (0.0, 1.0, -2.0):
            tilt = lettering_tilt(turned(word(text, vertical=vertical), angle) < 140)
            assert not tilt.short, (len(text), angle, tilt)  # (the long lines' search is as it was)
            assert tilt.angle == 0.0 or angle, (len(text), tilt)


def test_a_small_kana_set_off_the_column_does_not_slant_an_upright_word():
    for seed in range(1, 11):
        rng = random.Random(seed)
        img = np.full((24 * 3 + 32, 24 + 32), 255, np.uint8)
        img[16:40, 16:40] = glyph(rng, 24)
        img[44:60, 26:42] = glyph(rng, 16)  # a small kana: smaller, to the right and up in its cell, as set
        img[64:88, 16:40] = glyph(rng, 24)
        assert lettering_tilt(img < 140).angle == 0.0, seed


def test_two_columns_set_off_from_each_other_are_no_slanted_line():
    img = np.full((140, 110), 255, np.uint8)
    img[16:64, 60:84] = np.vstack([glyph(random.Random(1), 24), glyph(random.Random(2), 24)])
    img[60:108, 24:48] = np.vstack([glyph(random.Random(3), 24), glyph(random.Random(4), 24)])
    assert lettering_tilt(img < 140).angle == 0.0


def test_specks_and_strokes_of_the_drawing_show_no_short_slant():
    rng = np.random.default_rng(3)
    for _ in range(20):
        ink = rng.random((80, 60)) < 0.04  # specks
        assert lettering_tilt(ink).angle == 0.0
    for k in range(10):  # a few curved strokes, as of hair
        img = np.full((90, 70), 255, np.uint8)
        for j in range(3):
            cv2.ellipse(img, (35 + 6 * j, 45), (30, 12 + 4 * k), 60 + 7 * k, 0, 140, 0, 2)
        assert lettering_tilt(img < 140).angle == 0.0, k



def test_a_long_line_of_the_drawing_is_no_lettering():
    gray = turned(lettering([6, 5, 7]), 12.0)
    cv2.line(gray, (0, 5), (gray.shape[1] - 1, gray.shape[0] // 2), 0, 3)  # a speed line across the box
    assert abs(lettering_tilt(gray < 140).angle - 12.0) <= 1.0


def test_the_turn_maps_points_there_and_back():
    turn = Upright((80, 120), 17.0, origin=(300, 200))
    for x, y in ((300, 200), (419, 279), (350.5, 230.25)):
        u, v = turn.forward(x, y)
        bx, by = turn.back(u, v)
        assert abs(bx - x) < 1e-6 and abs(by - y) < 1e-6
    assert turn.width > 120 and turn.height > 80
    corners = turned_corners((0, 0, 100, 40), 90.0)
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    assert max(xs) - min(xs) == pytest.approx(40) and max(ys) - min(ys) == pytest.approx(100)


def test_the_ink_frame_is_the_lettering_upright_without_the_room_the_slant_left():
    gray = lettering([6, 5, 7])
    ys, xs = np.nonzero(gray < 140)
    w, h = xs.max() + 1 - xs.min(), ys.max() + 1 - ys.min()
    slanted = turned(gray, 20.0)
    fx0, fy0, fx1, fy1 = ink_frame(slanted < 140, 20.0)
    assert abs((fx1 - fx0) - w) <= 4 and abs((fy1 - fy0) - h) <= 4
    sx0, sy0, sx1, sy1 = ink_frame(slanted < 140, 0.0)  # the upright box round it is far larger
    assert (sx1 - sx0) * (sy1 - sy0) > 1.3 * w * h


def test_the_ink_is_taken_inside_the_mask_and_the_page_only():
    rgb = np.full((50, 60, 3), 255, np.uint8)
    rgb[10:20, 10:20] = 0
    rgb[30:40, 30:40] = 0
    mask = np.zeros((40, 40), np.uint8)
    mask[:, :25] = 255  # the region starts at (5, 5): the first square is inside its mask, the second is not
    ink = region_ink(rgb, mask, (0, 0, 70, 70), (5, 5))
    assert ink.shape == (70, 70)
    assert ink[10:20, 10:20].all() and not ink[30:40, 30:40].any() and not ink[50:, :].any()


# ---------------------------------------------------------------- the pipeline


class CropOcr:
    """Reads one canned line and keeps every crop it was given; surer of a crop whose lettering stands upright
    (*upright_surer*) or of one at a slant."""

    def __init__(self, text: str = "まだ終わってない", upright_surer: bool = True):
        self.text = text
        self.upright_surer = upright_surer
        self.crops: list[Image.Image] = []

    def read_with_confidence(self, image: Image.Image) -> tuple[str, float]:
        self.crops.append(image.copy())
        tilt = abs(lettering_tilt(np.asarray(image.convert("L")) < 140).measured)
        upright = tilt < 3.0
        return self.text, 0.9 if upright == self.upright_surer else 0.7


def slanted_page(angle: float, columns=(6, 5, 7)) -> tuple[np.ndarray, TextRegion]:
    """A white page with one bubble (an ellipse) holding lettering at *angle*, and the region a detector gives it."""
    page = np.full((420, 420, 3), 255, np.uint8)
    cv2.ellipse(page, (210, 210), (170, 190), 0, 0, 360, (0, 0, 0), 3)
    text = turned(lettering(list(columns), size=22, pad=4), angle)
    th, tw = text.shape
    y0, x0 = 210 - th // 2, 210 - tw // 2
    page[y0:y0 + th, x0:x0 + tw] = np.minimum(page[y0:y0 + th, x0:x0 + tw], text[..., None])
    inside = np.zeros((420, 420), np.uint8)
    cv2.ellipse(inside, (210, 210), (165, 185), 0, 0, 360, 255, -1)
    ys, xs = np.nonzero((page[..., 0] < 140) & (inside > 0))
    region = TextRegion(x0=40, y0=20, x1=380, y1=400, mask=inside[20:400, 40:380].copy(),
                        text_box=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    return page, region


def test_slanted_lettering_is_read_turned_upright(settings):
    page, region = slanted_page(15.0)
    ocr = CropOcr()
    p = Pipeline(settings, ocr=ocr, translator=None)
    p._measure_slants(page, [region])
    assert abs(region.angle - 15.0) <= 2.5
    reading = p._read(page, region, region.text_box)
    assert reading.text == ocr.text and reading.score == 0.9  # read both ways: turned upright, the surer
    assert len(ocr.crops) == 2
    crop = np.asarray(ocr.crops[0].convert("L"))  # (the turned crop is read first)
    assert lettering_tilt(crop < 140).measured == pytest.approx(0.0, abs=1.5)  # the readers see it upright
    # ... and cut to the lettering: no wider than its columns and a margin
    assert crop.shape[1] < region.text_box[2] - region.text_box[0]
    assert p._chosen(page, region, region.text_box)[2]
    p._read(page, region, region.text_box)
    assert len(ocr.crops) == 2  # (both readings memoised)


def test_a_slant_the_readers_read_better_as_cut_is_read_as_cut(settings):
    page, region = slanted_page(15.0)
    ocr = CropOcr(upright_surer=False)
    p = Pipeline(settings, ocr=ocr, translator=None)
    p._measure_slants(page, [region])
    assert p._read(page, region, region.text_box).score == 0.9
    chosen = p._chosen(page, region, region.text_box)
    assert not chosen[2]
    pad = max(4, int(0.08 * min(region.width, region.height)))
    assert np.array_equal(np.asarray(chosen[0]), np.asarray(region.crop(page, box=region.text_box, pad=pad)))


def test_upright_lettering_is_read_as_before_byte_for_byte(settings):
    page, region = slanted_page(0.0)
    ocr = CropOcr()
    p = Pipeline(settings, ocr=ocr, translator=None)
    p._measure_slants(page, [region])
    assert region.angle == 0.0 and region.tilt is not None
    p._read(page, region, region.text_box)
    pad = max(4, int(0.08 * min(region.width, region.height)))
    expected = region.crop(page, box=region.text_box, pad=pad)
    assert np.array_equal(np.asarray(ocr.crops[-1]), np.asarray(expected))


def test_with_the_setting_off_nothing_is_measured(settings):
    settings.slant_text = False
    page, region = slanted_page(15.0)
    Pipeline(settings, ocr=CropOcr(), translator=None)._measure_slants(page, [region])
    assert region.angle == 0.0 and region.tilt is None


def test_a_slant_that_came_with_the_region_is_kept(settings):
    page, region = slanted_page(15.0)
    region.angle, region.tilt = -7.0, "set"
    Pipeline(settings, ocr=CropOcr(), translator=None)._measure_slants(page, [region])
    assert region.angle == -7.0


def test_the_characters_of_a_slanted_reading_land_on_the_lettering(settings):
    from taslation.ocr.charspot import CharspotReading

    page, region = slanted_page(20.0)
    p = Pipeline(settings, ocr=CropOcr(), translator=None)
    p._measure_slants(page, [region])
    prepared = p._ocr_crop(page, region, region.text_box, turned=True)
    assert prepared is not None
    crop = np.asarray(prepared[0].convert("L"))
    ys, xs = np.nonzero(crop < 100)

    class Char:  # a character the reading found: a pixel of ink in the crop, and the one at the far end
        def __init__(self, x: int, y: int):
            self.box = (float(x), float(y), float(x) + 1, float(y) + 1)

    picks = [0, len(xs) // 2, len(xs) - 1]
    boxes, quads = p._char_boxes(page, region, region.text_box, [Char(xs[i], ys[i]) for i in picks])
    assert len(quads) == 3 and all(len(q) == 4 for q in quads)
    gray = page[..., 0]
    for x0, y0, x1, y1 in boxes:  # each lands on the page's ink (within a pixel or two)
        assert (gray[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2] < 140).any()
    assert CharspotReading  # (the reading's characters carry their boxes in the crop)


def test_a_model_regions_slanted_characters_are_erased_in_their_own_boxes(monkeypatch):
    import taslation.pipeline as pipeline_module

    page, region = slanted_page(20.0)
    region.from_model, region.tier, region.kind, region.glyph = True, 3, "bubble", 22.0
    region.angle = 20.0
    cx, cy = 210.0, 210.0
    quad = turned_corners((cx - 11, cy - 60, cx + 11, cy + 60), 20.0)
    region.char_quads = [quad]
    region.char_boxes = [(int(min(p[0] for p in quad)), int(min(p[1] for p in quad)),
                          int(max(p[0] for p in quad)) + 1, int(max(p[1] for p in quad)) + 1)]
    erased: list[np.ndarray] = []
    monkeypatch.setattr(pipeline_module, "erase_region", lambda image, q, *a: (erased.append(q.mask), (255, 255, 255))[1])
    Pipeline._paper_erase(page.copy(), region, "fill")
    painted = erased[0] > 0
    bx0, by0, bx1, by1 = (v - o for v, o in zip(region.char_boxes[0], (region.x0, region.y0, region.x0, region.y0)))
    corner = painted[by0:by0 + 3, bx0:bx0 + 3]  # the corner of the upright box round the turned one lies outside it
    assert painted[int(cy) - region.y0, int(cx) - region.x0] and not corner.any()
    region.char_quads = []  # (an upright region's characters: their boxes, as before)
    Pipeline._paper_erase(page.copy(), region, "fill")
    assert (erased[1][by0:by0 + 6, bx0:bx0 + 6] > 0).all()


# ---------------------------------------------------------------- the lettering


def test_a_slanted_region_is_lettered_in_its_own_frame(settings):
    font = find_font()
    if font is None:
        pytest.skip("no font")
    page, region = slanted_page(18.0)
    region.angle = 18.0
    region.text_box = region.bbox
    blank = np.full_like(page, 255)
    image = Image.fromarray(blank)
    done = letter_text(image, region, "This is a longer translation, set at a slant like the original.", str(font))
    assert done.size > 0
    drawn = np.asarray(image.convert("L"))
    assert (drawn < 128).any()
    assert lettering_tilt(drawn < 128).measured == pytest.approx(18.0, abs=2.0)
    # nothing is drawn outside the region's mask
    outside = np.ones(drawn.shape, bool)
    outside[region.y0:region.y1, region.x0:region.x1] = region.mask == 0
    assert not (drawn[outside] < 200).any()
    # sizing alone (no image) goes the same way
    assert letter_text(None, region, "This is a longer translation, set at a slant like the original.", str(font)).size == done.size


def test_a_steep_slant_the_rotate_handle_sets_is_lettered_inside_the_region(settings):
    font = find_font()
    if font is None:
        pytest.skip("no font")
    from taslation.pipeline import manual_region

    blank = np.full((400, 400, 3), 255, np.uint8)
    region = manual_region(blank, (120, 60, 280, 340))
    region.angle = 80.0  # (past the 45 degrees the measure looks at: the reader's own slant)
    image = Image.fromarray(blank)
    done = letter_text(image, region, "A line the reader turned nearly on its side.", str(font))
    drawn = np.asarray(image.convert("L")) < 128
    assert done.size > 0 and drawn.any()
    ys, xs = np.nonzero(drawn)
    assert xs.min() >= 120 and xs.max() < 280 and ys.min() >= 60 and ys.max() < 340
    assert np.ptp(ys) > 1.5 * np.ptp(xs)  # rows turned nearly upright run down the tall box


def test_an_upright_region_is_lettered_as_before(settings, monkeypatch):
    from taslation.render import slant

    font = find_font()
    if font is None:
        pytest.skip("no font")
    monkeypatch.setattr(slant, "letter_slanted", lambda *a, **k: (_ for _ in ()).throw(AssertionError("slanted")))
    page, region = slanted_page(0.0)
    letter_text(Image.fromarray(page), region, "Upright as ever.", str(font))


def test_the_upright_picture_of_a_region_holds_its_mask_turned():
    page, region = slanted_page(25.0)
    region.angle = 25.0
    local, turn = upright_region(region)
    assert local.angle == 0.0 and 0 <= local.x0 < local.x1 <= turn.width and 0 <= local.y0 < local.y1 <= turn.height
    assert local.mask.shape == (local.height, local.width) and local.mask[local.height // 2, local.width // 2] == 255
    assert abs(int((local.mask > 0).sum()) - int((region.mask > 0).sum())) < 0.02 * int((region.mask > 0).sum())
    outline = slanted_outline(region)
    assert len(outline) == 4 and slanted_outline(region, 0.0)[0] == (region.x0, region.y0)


# ---------------------------------------------------------------- what is kept


def test_the_cache_keeps_a_bubbles_slant_and_an_old_one_has_none():
    b = CachedBubble(box=(0.1, 0.1, 0.3, 0.3), text="Hi", angle=12.5)
    d = b.to_json()
    assert d["angle"] == 12.5 and CachedBubble.from_json(json.loads(json.dumps(d))).angle == 12.5
    old = {"box": [0.1, 0.1, 0.3, 0.3], "text": "Hi"}
    assert CachedBubble.from_json(old).angle == 0.0
    assert "angle" not in CachedBubble(box=(0.1, 0.1, 0.3, 0.3), text="Hi").to_json()  # (files as before)


def test_the_readers_slant_is_a_formatting_of_its_own():
    style = RegionStyle.make(slant=-12.0)
    assert style.slant == -12.0 and not style.is_empty and style.formats_nothing
    assert RegionStyle.from_json(style.to_json()) == style
    assert RegionStyle.make(slant=80).slant == 80.0 and RegionStyle.make(slant=-120).slant == -89.0  # (|angle| < 90)
    assert RegionStyle.make(slant="x").slant is None and "slant" not in RegionStyle().to_json()
    assert not RegionStyle.make(slant=5.0, size=20).formats_nothing


def test_the_readers_slant_turns_the_lettering(settings):
    page, region = slanted_page(0.0)
    p = Pipeline(settings, ocr=None, translator=None)
    seen: list[float] = []
    import taslation.pipeline as pipeline_module

    real = pipeline_module.letter_text

    def spy(image, r, *a, **k):
        seen.append(r.angle)
        return real(image, r, *a, **k)

    pipeline_module.letter_text = spy
    try:
        p._set_text(None, region, "Hello there", (255, 255, 255), RegionStyle.make(slant=10.0))
        p._set_text(None, region, "Hello there", (255, 255, 255), None)
        region.angle = 14.0
        p._set_text(None, region, "Hello there", (255, 255, 255), RegionStyle.make(slant=0.0))
    finally:
        pipeline_module.letter_text = real
    assert seen == [10.0, 0.0, 0.0]
    assert region.angle == 14.0  # (the region itself is left as it is)


def test_a_cached_bubbles_slant_comes_back_with_it(sample_page, settings):
    from helpers import EN_TEXTS, FakeOcr

    from taslation.cache import BookCache, CacheStore
    from taslation.translate import DictTranslator

    cache = CacheStore(settings.cache_dir).open("Slant Book", "fake")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    res = p.process(sample_page)
    assert res.translated
    for page in cache.pages:
        for b in page.bubbles:
            b.angle = 9.0
    cache.save()
    res2 = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS),
                    cache=BookCache.load(cache.path)).process(sample_page)
    assert res2.cache_hits == 1 and all(r.angle == 9.0 for r in res2.translated)
    assert copy  # (copies of regions keep their slant: `copy.copy`)


# ---------------------------------------------------------------- the region editor and translator mode


def test_the_editor_shows_the_measured_slant_and_gives_the_readers_back(hidden_root):
    from taslation.pipeline import manual_region
    from taslation.ui.dialogs import review

    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text, r.angle = "translated", "Hi there", "やあ", 12.5
    d = review.EditBubbleDialog(hidden_root, r, [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.slant_auto.get() and d.slant_var.get() == "12.5" and str(d.slant_spin.cget("state")) == "disabled"
    assert d.style() == RegionStyle()  # Auto: as measured
    d.slant_auto.set(False)
    d._slant_mode()
    d.slant_var.set("-8")
    assert d.style() == RegionStyle(slant=-8.0)
    d.slant_var.set("0")
    assert d.style().slant == 0.0  # straight, whatever was measured
    d.reset_btn.invoke()
    assert d.style() == RegionStyle() and d.slant_var.get() == "12.5"
    d.destroy()
    r.style = RegionStyle(slant=20.0)
    d = review.EditBubbleDialog(hidden_root, r, [], on_save=lambda data: None, on_drop=lambda: None)
    assert not d.slant_auto.get() and d.slant_var.get() == "20" and d.style() == RegionStyle(slant=20.0)
    d.destroy()


def test_translator_mode_draws_the_chosen_region_in_its_turned_frame():
    from types import SimpleNamespace

    from taslation.ui import area
    from taslation.ui.translator import TranslatorMixin

    drawn: list[tuple] = []
    canvas = SimpleNamespace(delete=lambda tag: drawn.clear(),
                             draw_frame=lambda box, tag, colour: drawn.append(("frame", box)),
                             draw_turned_frame=lambda pts, tag, colour: drawn.append(("turned", pts)),
                             draw_rotate_handle=lambda pts, tag, colour: drawn.append(("rotate", pts)))
    page, region = slanted_page(15.0)
    region.angle = 15.0
    host = SimpleNamespace(canvas=canvas, _chosen_region=region, _grip_box=None, _turn=None, _frame_cache=None,
                           last_result=object(), _editing=lambda: True)
    for name in ("_turn_of", "_frame_of", "_shown_frame"):
        setattr(host, name, getattr(TranslatorMixin, name).__get__(host))
    TranslatorMixin._draw_frame(host)
    assert [k for k, _v in drawn] == ["turned", "rotate"] and drawn[0][1] == slanted_outline(region, 15.0)
    assert drawn[1][1] == drawn[0][1] and area.frame_angle(drawn[0][1]) == pytest.approx(15.0, abs=1.0)
    region.style = RegionStyle(slant=0.0)  # the reader set it straight: the box, as an upright region's
    TranslatorMixin._draw_frame(host)
    assert drawn == [("frame", region.bbox), ("rotate", area.box_corners(region.bbox))]
