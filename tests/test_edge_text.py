"""Lettering that touches a bubble's outline is part of the bubble: read with it and erased with it."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from taslation.detect import BubbleDetector
from taslation.detect.bubbles import DetectorConfig, fill_holes, recover_edge_text
from taslation.render import erase_region

FONTS = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\msgothic.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
CX, CY, A, B = 300, 350, 62, 170  # the bubble: an upright ellipse, white inside a 3 px black outline
SIZE = 24
STEP = int(SIZE * 1.1)


def _font() -> ImageFont.FreeTypeFont:
    path = next((p for p in FONTS if Path(p).is_file()), None)
    if path is None:
        pytest.skip("no Japanese font available")
    return ImageFont.truetype(path, SIZE)


def _ink_box(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(gray[y0:y1, x0:x1] < 140)
    return x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1


def _narrow_bubble(page: int = 190, outside_text: bool = False):
    """A narrow bubble with three columns. The left one sits 3 px from the outline, joined to it by a light-gray
    fringe (as anti-aliasing does), not by dark pixels. Returns (rgb, ink box of the left column, outline mask,
    ink box of a glyph drawn outside the bubble or None)."""
    font = _font()
    # where does the left column's ink start, relative to where it is drawn?
    probe = Image.new("L", (60, 4 * STEP), 255)
    for i, ch in enumerate("大丈夫"):
        ImageDraw.Draw(probe).text((10, i * STEP), ch, font=font, fill=0)
    lead = int(np.nonzero((np.asarray(probe) < 140).any(axis=0))[0].min()) - 10

    img = Image.new("RGB", (600, 700), (page,) * 3)
    draw = ImageDraw.Draw(img)
    draw.ellipse((CX - A - 3, CY - B - 3, CX + A + 3, CY + B + 3), fill=(0, 0, 0))
    draw.ellipse((CX - A, CY - B, CX + A, CY + B), fill=(255, 255, 255))
    outline = np.asarray(img.convert("L")) < 140
    for x, text in ((CX + 14, "こんにちは"), (CX - 14, "ありがとう")):
        for i, ch in enumerate(text):
            draw.text((x, CY - 70 + i * STEP), ch, font=font, fill=(0, 0, 0))
    left_x = CX - A + 6 - lead  # ink 3+ px from the outline's inner edge over the column's height
    layer = Image.new("L", img.size, 255)
    for i, ch in enumerate("大丈夫"):
        draw.text((left_x, CY - 40 + i * STEP), ch, font=font, fill=(0, 0, 0))
        ImageDraw.Draw(layer).text((left_x, CY - 40 + i * STEP), ch, font=font, fill=0)
    col = _ink_box(np.asarray(layer), 0, 0, img.width, img.height)
    rgb = np.asarray(img).copy()
    # the fringe: light gray over the white between the outline and the column, along the column
    strip = rgb[col[1]:col[3], CX - A - 1:col[0]]
    strip[(strip >= 250).all(axis=2)] = 200
    out_box = None
    if outside_text:  # a glyph outside the bubble, in the corner of its box
        pil = Image.fromarray(rgb)
        ImageDraw.Draw(pil).text((CX - A - 6, CY - B - 6), "外", font=font, fill=(0, 0, 0))
        rgb = np.asarray(pil).copy()
        layer = Image.new("L", pil.size, 255)
        ImageDraw.Draw(layer).text((CX - A - 6, CY - B - 6), "外", font=font, fill=0)
        out_box = _ink_box(np.asarray(layer), 0, 0, pil.width, pil.height)
    return rgb, col, outline, out_box


def _dark(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) < 140


@pytest.mark.parametrize("page", [190, 255])
def test_column_against_the_outline_is_in_the_text_box_and_erased(page):
    rgb, col, outline, _ = _narrow_bubble(page)
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 1
    r = regions[0]
    assert r.text_box[0] <= col[0] and r.text_box[1] <= col[1] + 2 and r.text_box[3] >= col[3] - 2
    out = rgb.copy()
    erase_region(out, r)
    x0, y0, x1, y1 = col
    assert not _dark(out)[y0:y1, x0:x1].any()  # the whole left column is gone ...
    assert _dark(out)[outline].all()  # ... and the outline is untouched


def test_without_recovery_the_column_stays():
    """The failure this guards against: the column is no hole of the white area, so it was left on the page."""
    rgb, col, _outline, _ = _narrow_bubble()
    (r,) = BubbleDetector(DetectorConfig(recover_edge_text=False)).detect(rgb)
    assert r.text_box[0] > col[2]
    out = rgb.copy()
    erase_region(out, r)
    x0, y0, x1, y1 = col
    assert _dark(out)[y0:y1, x0:x1].sum() > 100


@pytest.mark.parametrize("page", [190, 255])
def test_lettering_outside_the_outline_is_left_alone(page):
    rgb, col, outline, out_box = _narrow_bubble(page, outside_text=True)
    (r,) = BubbleDetector().detect(rgb)
    assert r.text_box[0] <= col[0]
    assert not (r.text_box[0] <= out_box[0] and r.text_box[1] <= out_box[1])  # the outside glyph is not text of it
    out = rgb.copy()
    erase_region(out, r)
    x0, y0, x1, y1 = out_box
    assert (_dark(out)[y0:y1, x0:x1] == _dark(rgb)[y0:y1, x0:x1]).all()
    assert _dark(out)[outline].all()
    assert not _dark(out)[col[1]:col[3], col[0]:col[2]].any()


def test_art_beyond_a_crack_in_the_outline_is_left_alone():
    """A small framed panel next to the bubble, joined to it by a 2 px crack through the outline, with a mark in
    it: as enclosed as the lettering, but it does not line the bubble's white area, so it stays."""
    rgb, col, _outline, _ = _narrow_bubble()
    img = rgb.copy()
    fx0, fy0, fx1, fy1 = CX + A + 2, CY - 10, CX + A + 16, CY + 6  # on the outline, inside the window looked at
    img[fy0:fy1, fx0:fx1] = 0
    img[fy0 + 2 : fy1 - 2, fx0 + 2 : fx1 - 2] = 255
    img[CY - 4 : CY - 2, CX + A - 3 : fx0 + 3] = 255  # the crack: through the outline and the panel's frame
    mark = (slice(CY - 6, CY - 1), slice(fx0 + 5, fx0 + 10))
    img[mark] = 0
    (r,) = BubbleDetector().detect(img)
    assert r.text_box[0] <= col[0]  # the column against the outline is still taken in ...
    assert r.text_box[2] <= CX + A and r.x1 <= fx0 + 4  # ... the mark is not
    out = img.copy()
    erase_region(out, r)
    assert _dark(out)[mark].all()


def test_hairline_and_tone_next_to_the_white_area_stay():
    """Art inside the outline that borders the white area is not lettering: a hairline across the top of the
    bubble (cutting off a small cap of it), broken into short dashes by its anti-aliasing at the dark threshold,
    and a dot tone on light gray along the bottom. Neither is erased, while the column against the outline is."""
    rgb, col, _outline, _ = _narrow_bubble(page=255)
    img = rgb.copy()
    line = np.zeros(img.shape[:2], bool)
    y_line = CY - B + 14  # the cap above the line is shorter than the margin looked at around the bubble
    for k, xx in enumerate(range(CX - A, CX + A)):
        yy = y_line + k // 12  # a shallow slope
        if img[yy, xx].min() >= 250:
            img[yy, xx] = 90 if (k // 4) % 2 == 0 else 175  # 4 px dashes, 4 px gaps (anti-aliased, light)
            line[yy, xx] = True
    tone = np.zeros(img.shape[:2], bool)
    for yy in range(CY + B - 40, CY + B):
        for xx in range(CX - A, CX + A):
            if img[yy, xx].min() >= 250:
                img[yy, xx] = 205  # light gray ground ...
                if yy % 4 < 2 and xx % 4 < 2:
                    img[yy, xx] = 60  # ... with 2 px dots
                    tone[yy, xx] = True
    regions = BubbleDetector().detect(img)
    r = max(regions, key=lambda q: q.area)
    assert r.text_box[0] <= col[0]
    out = img.copy()
    erase_region(out, r)
    assert not _dark(out)[col[1]:col[3], col[0]:col[2]].any()
    dashes = line & _dark(img)
    assert dashes.sum() > 20
    assert (_dark(out) & dashes).sum() == dashes.sum()  # every dash of the hairline is still there
    assert (_dark(out) & tone).sum() == tone.sum()  # and every dot of the tone
    assert r.text_box[1] > y_line + 6 and r.text_box[3] < CY + B - 40  # neither stretches the text box


def test_dark_bubble_column_against_the_edge_is_recovered():
    """A black bubble with white lettering on a white page: inverted, the page is all dark around the bubble."""
    internal, col, _outline, _ = _narrow_bubble(page=0)
    visible = 255 - internal
    regions = BubbleDetector().detect(visible, inverted=True)
    assert len(regions) == 1
    r = regions[0]
    assert r.kind == "dark-bubble" and r.text_box[0] <= col[0]
    out = visible.copy()
    erase_region(out, r, dark=True)
    x0, y0, x1, y1 = col
    assert not (cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)[y0:y1, x0:x1] > 140).any()


def test_dark_page_art_is_not_taken_for_text():
    """Around a dark bubble (inverted) nothing is reachable from outside; specks out there must stay."""
    internal, _col, _outline, _ = _narrow_bubble(page=0)
    internal[CY - 30:CY - 20, CX + A + 8:CX + A + 18] = 255  # a light frame on the dark page ...
    internal[CY - 28:CY - 22, CX + A + 10:CX + A + 16] = 0  # ... around a glyph-sized dark speck
    regions = BubbleDetector().detect(255 - internal, inverted=True)
    (r,) = regions
    assert r.x1 <= CX + A + 8 and r.text_box[2] <= CX + A


def test_open_outline_recovers_nothing():
    """Where the white area reaches the window's border, nothing encloses it: the bubble stays as detected."""
    gray = np.full((60, 60), 255, np.uint8)
    gray[20:24, 20:40] = 0  # a stroke on open white
    filled = np.full((40, 40), 255, np.uint8)
    assert recover_edge_text(gray, (10, 10, 40, 40), fill_holes(filled), filled.copy(), 12.0, 140) is None


class _SequenceOcr:
    """Returns the given readings in call order; records the width of each crop it was shown."""

    def __init__(self, readings: list[tuple[str, float]]):
        self.readings = list(readings)
        self.widths: list[int] = []

    def read_with_confidence(self, image) -> tuple[str, float]:
        self.widths.append(image.width)
        return self.readings[len(self.widths) - 1]

    def read(self, image) -> str:
        return self.read_with_confidence(image)[0]


def _read_bubble(settings, readings):
    from taslation.pipeline import Pipeline

    rgb, col, _outline, _ = _narrow_bubble()
    (r,) = BubbleDetector().detect(rgb)
    assert r.core_box is not None and r.core_box[0] > col[2] and r.edge_pieces > 0
    ocr = _SequenceOcr(readings)
    Pipeline(settings, ocr=ocr, translator=None)._ocr_regions(rgb, [r], lambda _m: None)
    return r, ocr


def test_completed_reading_is_used_when_both_readings_pass(settings):
    r, ocr = _read_bubble(settings, [("こんにちはありがとう大丈夫", 0.9), ("こんにちはありがとう", 0.9)])
    assert len(ocr.widths) == 2 and ocr.widths[0] > ocr.widths[1]  # the whole text first, then the core
    assert r.status == "untranslated" and r.source_text == "こんにちはありがとう大丈夫"


def test_taking_in_lettering_never_turns_junk_into_text(settings):
    """Artwork read as nothing (or as junk) on the box as detected stays junk, whatever the wider box reads."""
    r, _ocr = _read_bubble(settings, [("こんにちはありがとう大丈夫", 0.9), ("", 0.9)])
    assert r.status == "ocr-empty" and r.source_text == ""
    r, _ocr = _read_bubble(settings, [("こんにちはありがとう大丈夫", 0.9), ("あ", 0.2)])
    assert r.status == "low-confidence"


def test_a_worse_completed_reading_falls_back_to_the_core(settings):
    r, _ocr = _read_bubble(settings, [("こんに", 0.3), ("こんにちはありがとう", 0.9)])
    assert r.status == "untranslated" and r.source_text == "こんにちはありがとう"


def test_core_box_follows_the_capture_margins(settings):
    """Detection runs inside the capture's margins; both boxes come back in capture coordinates."""
    from taslation.pipeline import Pipeline

    rgb, col, _outline, _ = _narrow_bubble()
    framed = np.concatenate([np.full((40, rgb.shape[1], 3), 255, np.uint8), rgb])  # a toolbar strip on top
    settings.margins = (0, 40, 0, 0)
    pipeline = Pipeline(settings, ocr=_SequenceOcr([("こんにちはありがとう大丈夫", 0.9), ("こんにちはありがとう", 0.9)]))
    (r,) = pipeline._detect(framed)
    tb, cb = r.text_box, r.core_box
    assert tb[0] <= col[0] and tb[1] <= col[1] + 40 + 2  # the whole text, shifted by the margin ...
    assert cb is not None and tb[0] < cb[0] and tb[1] <= cb[1] and cb[2] <= tb[2] and cb[3] <= tb[3]  # ... and the core in it
    pipeline._ocr_regions(framed, [r], lambda _m: None)
    assert r.status == "untranslated" and r.source_text == "こんにちはありがとう大丈夫"


def test_large_white_area_is_still_cut_down_to_its_text():
    """A large white area of the drawing with a short column in it is cut down to the column's neighbourhood.
    A blob of the drawing against its edge, far from the column, must not join the text: it would widen the cut
    and be erased, with whatever else of the drawing the wider cut takes."""
    from taslation.detect import focus_oversized

    font = _font()
    img = Image.new("RGB", (600, 700), (190, 190, 190))
    draw = ImageDraw.Draw(img)
    draw.rectangle((147, 147, 453, 403), fill=(0, 0, 0))
    draw.rectangle((150, 150, 450, 400), fill=(255, 255, 255))
    for i, ch in enumerate("こんにちは"):
        draw.text((280, 190 + i * STEP), ch, font=font, fill=(0, 0, 0))
    rgb = np.asarray(img).copy()
    blob = (slice(240, 256), slice(431, 447))  # a solid blob of the drawing, against the right edge ...
    rgb[blob] = 0
    rgb[240:256, 447:450] = 200  # ... joined to it by a light-gray fringe
    (before,) = focus_oversized(BubbleDetector(DetectorConfig(recover_edge_text=False)).detect(rgb))
    (r,) = BubbleDetector().detect(rgb)
    assert r.text_box[2] < 431  # the blob did not join the text
    (r,) = focus_oversized([r])
    assert r.kind == "text-on-page" and r.bbox == before.bbox  # cut down exactly as before
    out = rgb.copy()
    erase_region(out, r)
    assert _dark(out)[blob].all()
