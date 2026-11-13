"""Lettering beyond a bubble's interior: a column that goes on over the tone is taken into the text box, outlined
glyphs over the drawing reach the OCR as black on white, and their rings are painted the drawing's colour."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw
from test_edge_text import A, B, CX, CY, STEP, _font

from taslation.detect import BubbleDetector
from taslation.detect.bubbles import DetectorConfig
from taslation.detect.beyond import lettering_beyond, ocr_view, outlined_strokes, rings_on_dark, thin_light
from taslation.regions import TextRegion
from taslation.render import erase_region


def _glyph_column(gray: np.ndarray, x: int, ys: list[int], size: int = 12, value: int = 0) -> None:
    for y in ys:
        gray[y:y + size, x:x + size] = value
        if size >= 10:
            gray[y + 4:y + 8, x + 3:x + 9] = 255 - value  # a hole: a stroke, not a blob


def test_an_aligned_column_on_the_bubbles_own_ground_is_taken_in_but_not_one_elsewhere():
    def scene(ground: int, beyond_x: int | None, size: int = 12) -> np.ndarray:
        gray = np.full((300, 400), ground, np.uint8)  # the detector's view: what lies around a dark bubble
        gray[40:260, 120:260] = 255  # the bubble's (inverted) interior
        _glyph_column(gray, 236, [60, 80, 100, 120, 140])  # its own last column, near the edge
        if beyond_x is not None:
            _glyph_column(gray, beyond_x, [60, 80, 100, 120, 140], size=size)
        return gray

    inside = np.full((220, 140), 255, np.uint8)
    text_box = (236, 60, 248, 152)
    box, taken, pieces = lettering_beyond(scene(245, 266), (120, 40, 140, 220), inside, text_box, 12.0)  # beyond, same ground
    assert taken == 5 and len(pieces) == 5 and box[2] >= 278 and box[:2] == (236, 60)
    two = scene(245, None)
    _glyph_column(two, 266, [60, 80])  # two pieces are not a column
    assert lettering_beyond(two, (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)
    lines = scene(245, None)
    for yy in range(56, 160, 6):
        lines[yy:yy + 2, 262:290] = 0  # speed lines beside the text: thin, long
    assert lettering_beyond(lines, (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)
    other = scene(245, 266)
    exclude = np.zeros((300, 400), bool)
    exclude[50:170, 260:290] = True  # the column lies inside another bubble's interior
    assert lettering_beyond(other, (120, 40, 140, 220), inside, text_box, 12.0, exclude=exclude)[:2] == (text_box, 0)
    busy = scene(245, 266)
    busy[40:260, 260:300:3] = 180  # the ground under the column is streaked: a drawing, not the bubble's black
    assert lettering_beyond(busy, (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)
    crossed = scene(245, 266)
    for yy in range(58, 160, 4):
        crossed[yy, 262:284] = 0  # hairlines through the column: strokes between the pieces, as speed lines leave
    assert lettering_beyond(crossed, (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)
    assert lettering_beyond(scene(245, 320), (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)  # six glyphs away
    assert lettering_beyond(scene(130, 266), (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)  # on a tone
    assert lettering_beyond(scene(0, 266), (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)  # on the page
    assert lettering_beyond(scene(245, 266, size=2), (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)  # specks
    assert lettering_beyond(scene(245, None), (120, 40, 140, 220), inside, text_box, 12.0)[:2] == (text_box, 0)


def _dark_page() -> tuple[np.ndarray, int]:
    """A black bubble with white columns on a white page; its black goes on past the interior the detector finds,
    and the leftmost column stands there, outside the interior on the bubble's own black. (rgb, that column's x)."""
    font = _font()
    img = Image.new("RGB", (600, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    beyond_x = CX - A - 30  # the next column, a glyph's pitch past the bubble's edge
    # a strip of the bubble's black under that column, cut from the ellipse by a sliver of white (as a badly closed
    # blob is): too narrow to be a bubble of its own, so the column stands outside every interior
    draw.rectangle((beyond_x - 4, CY - 50, CX - A - 6, CY - 40 + 3 * STEP + 10), fill=(12, 12, 12))
    draw.ellipse((CX - A, CY - B, CX + A, CY + B), fill=(0, 0, 0))
    for x, text in ((CX + 14, "こんにちは"), (CX - 14, "ありがとう"), (CX - 42, "大丈夫")):
        for i, ch in enumerate(text):
            draw.text((x, CY - 70 + i * STEP), ch, font=font, fill=(255, 255, 255))
    for i, ch in enumerate("大丈夫"):
        draw.text((beyond_x, CY - 40 + i * STEP), ch, font=font, fill=(255, 255, 255))
    return np.asarray(img).copy(), beyond_x


def test_the_detector_reads_a_dark_bubbles_column_that_stands_past_its_interior():
    rgb, beyond_x = _dark_page()
    plain = max(BubbleDetector().detect(rgb, inverted=True), key=lambda q: q.area)
    assert plain.text_box[0] > CX - A and plain.beyond_box is None  # off unless asked for
    regions = BubbleDetector(DetectorConfig(take_columns_beyond=True)).detect(rgb, inverted=True)
    r = max(regions, key=lambda q: q.area)
    assert r.kind == "dark-bubble" and r.text_box[0] <= beyond_x + 2 and r.edge_pieces >= 3
    assert r.core_box is not None and r.core_box[0] > CX - A  # judged on what lies inside the bubble
    out = rgb.copy()
    erase_region(out, r, dark=True)
    gray = cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)
    assert gray[CY - 40:CY - 40 + 3 * STEP, beyond_x:beyond_x + 24].max() < 60  # the column is painted the black
    assert gray[CY - 48:CY - 42, beyond_x - 2:CX - A - 8].max() <= 30  # the black strip itself is still there


def _hair_page() -> tuple[np.ndarray, np.ndarray]:
    """A white bubble interior (left half) beside black hair (right half) with outlined glyph strokes on the hair."""
    img = np.full((120, 160, 3), 255, np.uint8)
    img[:, 80:] = 0

    def glyph(x: int, y: int) -> None:
        cv2.rectangle(img, (x - 2, y - 2), (x + 13, y + 13), (255, 255, 255), -1)
        cv2.rectangle(img, (x, y), (x + 11, y + 11), (0, 0, 0), -1)
        cv2.rectangle(img, (x + 3, y + 3), (x + 8, y + 8), (0, 0, 0), -1)

    glyph(95, 30)
    glyph(95, 60)
    img[:, 150:] = 255  # highlights: a white strip in the hair (a thick one, not a ring)
    mask = np.zeros((120, 160), np.uint8)
    mask[:, :80] = 255
    return img, mask


def test_outlined_glyphs_over_the_hair_reach_the_ocr_as_black_on_white():
    img, mask = _hair_page()
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    assert thin_light(gray)[28:30, 93:109].all() and not thin_light(gray)[50:70, 20:60].any()  # the ring, not the interior
    strokes = outlined_strokes(gray, mask, (20, 20, 115, 80))
    assert strokes[30:42, 95:107].any() and not strokes[:, :80].any() and not strokes[90:110, 85:140].any()
    view = ocr_view(img, mask, (20, 20, 115, 80))
    assert view is not None
    g = cv2.cvtColor(view, cv2.COLOR_RGB2GRAY)
    assert (g[:, :80] == 255).all() and g[30:42, 95:107].min() == 0  # the interior as it was, the strokes kept
    assert (g[18:20, 85:117] == 255).all() and (g[18:82, 85:117] == 255).sum() > 0.2 * 64 * 32  # the hair in the box gives way
    assert (g[90:118, 85:148] == 0).all() and (g[18:82, 120:148] == 0).all()  # outside the box nothing changes
    assert ocr_view(img, mask, (20, 20, 60, 80)) is None  # a box inside the interior needs no view


def test_rings_against_the_hair_are_painted_dark():
    img, mask = _hair_page()
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    rings = rings_on_dark(gray, mask, (20, 20, 115, 80))
    assert rings[28:30, 93:109].all() and not rings[:, 150:].any()
    r = TextRegion(0, 0, 160, 120, mask, (20, 20, 115, 80), kind="bubble")
    erase_region(img, r, "fill")
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    assert g[26:46, 91:111].max() < 40  # ring and stroke alike: the hair's black
    assert (g[:, 150:] == 255).all()  # the highlight strip stays


class _WidthOcr:
    """What the OCR reads: the bubble's text, and *extra* in front of it when the crop is wide enough to hold the
    column too (or *garbled* instead, when given)."""

    def __init__(self, wide: int, extra: str, garbled: str = ""):
        self.wide, self.extra, self.garbled = wide, extra, garbled

    def read(self, image: Image.Image) -> str:
        if image.width >= self.wide:
            return self.garbled or (self.extra + "ありがとうこんにちは")
        return "ありがとうこんにちは"


def test_the_column_is_kept_only_when_the_reading_with_it_extends_the_reading_without_it(settings):
    from taslation.pipeline import Pipeline

    rgb, beyond_x = _dark_page()
    for extra, garbled, kept in (("大丈夫", "", True), ("", "", False), ("", "全然違う文章ですよ", False)):
        regions = BubbleDetector(DetectorConfig(take_columns_beyond=True)).detect(rgb, inverted=True)
        r = max(regions, key=lambda q: q.area)
        assert r.beyond_box is not None and r.text_box[0] <= beyond_x + 2
        before = r.before_beyond[0]
        b = r.before_beyond[1]
        pad = max(4, int(0.08 * min(r.width, r.height)))
        narrow = min(r.x1, b[2] + pad) - max(r.x0, b[0] - pad)  # the crop without the column
        p = Pipeline(settings, ocr=_WidthOcr(narrow + 8, extra, garbled), translator=None)
        p._ocr_regions(rgb, [r], lambda _m: None)
        assert (r.beyond_box is not None) == kept, (extra, garbled)
        assert (r.text_box[0] <= beyond_x + 2) == kept and (r.bbox == before) != kept
        assert r.status == "untranslated"
        if not kept:
            assert r.core_box is None and r.edge_pieces == 0 and r.mask.shape == (before[3] - before[1], before[2] - before[0])
