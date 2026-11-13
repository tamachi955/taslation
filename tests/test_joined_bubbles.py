"""Bubbles that touch or overlap share one white area: each still becomes a region of its own (split_lobes),
while one bubble holding two blocks of lettering stays one region."""
from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from taslation.detect import BubbleDetector, focus_oversized
from taslation.detect.bubbles import DetectorConfig, fill_holes, split_lobes
from taslation.regions import TextRegion

SIZE = 24  # glyph size of the lettering


def _letter(img: Image.Image, columns: list[tuple[str, int, int]]) -> np.ndarray:
    from test_detect import _draw_vertical  # skips the test when no Japanese font is installed

    rgb = np.asarray(img).copy()
    for text, x, y in columns:
        rgb = _draw_vertical(rgb, text, x, y, SIZE)
    return rgb


def _shapes(draw: ImageDraw.ImageDraw, ellipses=(), polygons=(), rects=(), outline: int = 3) -> None:
    """One white area with a black outline round the union of the shapes (the outlines between them left out)."""
    for grow, fill in ((outline, (0, 0, 0)), (0, (255, 255, 255))):
        for x0, y0, x1, y1 in ellipses:
            draw.ellipse((x0 - grow, y0 - grow, x1 + grow, y1 + grow), fill=fill)
        for x0, y0, x1, y1 in rects:
            draw.rectangle((x0 - grow, y0 - grow, x1 + grow, y1 + grow), fill=fill)
        for pts in polygons:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            grown = [(cx + (px - cx) * (1 + grow / 40.0), cy + (py - cy) * (1 + grow / 40.0)) for px, py in pts]
            draw.polygon(grown, fill=fill)


def _page(**shapes) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (1000, 1200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    _shapes(draw, **shapes)
    return img, draw


def _ink(rgb: np.ndarray, box) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    ys, xs = np.nonzero(cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY) < 140)
    return x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1


def _page_mask(r: TextRegion, shape) -> np.ndarray:
    out = np.zeros(shape[:2], bool)
    out[r.y0:r.y1, r.x0:r.x1] = r.mask > 0
    return out


def _covers(outer, inner) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _two_columns_apart():
    return [("こんにちは", 238, 230), ("ありがとう", 398, 310)]


def test_overlapping_bubbles_become_one_region_each():
    """Two upright bubbles overlapping, the outline between them left out: two notches mark the junction."""
    img, _ = _page(ellipses=[(150, 120, 350, 520), (310, 200, 510, 600)])
    rgb = _letter(img, _two_columns_apart())
    left, right = _ink(rgb, (230, 225, 270, 370)), _ink(rgb, (390, 305, 430, 450))
    regions = sorted(BubbleDetector().detect(rgb), key=lambda r: r.x0)
    assert len(regions) == 2, [r.bbox for r in regions]
    a, b = regions
    assert _covers(a.text_box, left) and _covers(b.text_box, right)
    assert a.text_box[2] < right[0] and b.text_box[0] > left[2]  # each holds its own column only
    assert a.kind == b.kind == "bubble"
    ma, mb = _page_mask(a, rgb.shape), _page_mask(b, rgb.shape)
    assert not (ma & mb).any()  # the parts share the white out, they do not overlap
    whole = BubbleDetector(DetectorConfig(split_lobes=False)).detect(rgb)
    assert whole == []  # unsplit, the two columns far apart in one area read as specks (the old miss)


def test_a_bubble_whose_lettering_fails_on_its_own_keeps_the_area_whole():
    """When one bubble's mark would not pass as lettering on its own (here a single solid mark), the area is read
    whole as before rather than that bubble lost; the cut is used when every part passes."""
    img, draw = _page(ellipses=[(150, 120, 350, 520), (310, 200, 510, 600)])
    draw.ellipse((352, 300, 376, 324), fill=(0, 0, 0))  # one solid mark in the right bubble
    rgb = _letter(img, [("こんにちは", 288, 230)])
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 1, [r.bbox for r in regions]
    tb = regions[0].text_box
    assert tb[0] <= 290 and tb[2] >= 376  # the column and the mark: the whole area, as without the cut
    assert len(BubbleDetector(DetectorConfig(split_lobes=False)).detect(rgb)) == 1


def test_bubbles_joined_by_a_neck_become_one_region_each():
    """Two bubbles joined by a short, narrow channel of white."""
    img, _ = _page(ellipses=[(150, 240, 330, 560), (400, 260, 580, 580)], rects=[(320, 385, 410, 425)])
    rgb = _letter(img, [("こんにちは", 228, 300), ("大丈夫だよ", 478, 320)])
    regions = sorted(BubbleDetector().detect(rgb), key=lambda r: r.x0)
    assert len(regions) == 2, [r.bbox for r in regions]
    a, b = regions
    assert 330 <= a.x1 <= 400 and b.x0 >= a.x1 - 1  # cut across the channel, not through a bubble
    assert a.text_box[2] < 330 and b.text_box[0] > 400
    assert not (_page_mask(a, rgb.shape) & _page_mask(b, rgb.shape)).any()


def test_a_stretch_of_page_is_not_cut():
    """Two stretches of white page round a drawing, joined by a narrow gap: the neck is there, but the parts are
    no bubbles (not convex), and nothing is cut (the texts are left to the cut-down and the text blocks)."""
    img, _ = _page(rects=[(100, 100, 300, 300), (100, 300, 180, 600), (500, 100, 700, 300), (620, 300, 700, 600),
                          (300, 180, 500, 220)])
    rgb = _letter(img, [("こんにちは", 188, 130), ("ありがとう", 588, 130)])
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    white = cv2.erode((gray >= 225).astype(np.uint8) * 255, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=4)
    i = 1 + int(np.argsort(stats[1:, cv2.CC_STAT_AREA])[-2])
    x, y, w, h, _a = (int(v) for v in stats[i])
    filled = fill_holes((labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255)
    inner = cv2.erode(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    dark = ((gray[y:y + h, x:x + w] < 140) & (inner > 0)).astype(np.uint8)
    assert split_lobes(filled, inner, dark) is None
    assert split_lobes(filled, inner, dark, convex=0.0) is not None  # its bends alone would have cut it


def test_joined_bubbles_are_read_and_lettered_one_by_one(settings):
    from helpers import EN_TEXTS, FakeOcr

    from taslation.pipeline import Pipeline
    from taslation.translate import DictTranslator

    img, _ = _page(ellipses=[(150, 120, 350, 520), (310, 200, 510, 600)])
    rgb = _letter(img, _two_columns_apart())
    res = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).process(Image.fromarray(rgb),
                                                                                         use_cache=False)
    assert len(res.translated) == 2
    a, b = sorted(res.translated, key=lambda r: r.x0)
    assert a.translated_text != b.translated_text
    assert not (_page_mask(a, rgb.shape) & _page_mask(b, rgb.shape)).any()
    assert [r.order for r in res.regions] == [0, 1] and res.regions[0] is b  # right to left: the right bubble first


def test_one_bubble_with_two_blocks_stays_one_region():
    """A wide oval holding two groups of columns: one text with a pause, lettered in one bubble."""
    img, _ = _page(ellipses=[(150, 150, 650, 550)])
    rgb = _letter(img, [("こんにちは", 470, 250), ("ありがと", 440, 250), ("大丈夫だよ", 330, 260),
                        ("まだまだ", 300, 260)])
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 1
    tb = regions[0].text_box
    assert tb[0] < 330 and tb[2] > 480  # both groups


def test_a_tail_is_no_junction():
    """The base of a bubble's tail bends the outline inward too, but on one side only: nothing is cut."""
    img, _ = _page(ellipses=[(150, 150, 650, 550)], polygons=[[(420, 520), (500, 520), (360, 700)]])
    rgb = _letter(img, [("こんにちは", 470, 250), ("ありがと", 440, 250), ("大丈夫だよ", 330, 260),
                        ("まだまだ", 300, 260)])
    assert len(BubbleDetector().detect(rgb)) == 1


def test_a_cloud_is_one_bubble():
    """A thought bubble's outline bends inward between every pair of bumps: no two bends stand out, no cut."""
    bumps = []
    for k in range(14):
        t = 2 * math.pi * k / 14
        cx, cy = 400 + 215 * math.cos(t), 360 + 165 * math.sin(t)
        bumps.append((cx - 45, cy - 45, cx + 45, cy + 45))
    img, _ = _page(ellipses=[(170, 180, 630, 540)] + bumps)
    rgb = _letter(img, [("こんにちは", 480, 250), ("ありがと", 450, 250), ("大丈夫だよ", 330, 260),
                        ("まだまだ", 300, 260)])
    assert len(BubbleDetector().detect(rgb)) == 1


def test_a_spiky_shout_is_one_bubble():
    pts = []
    for k in range(32):
        t = 2 * math.pi * k / 32
        rad = 1.0 if k % 2 == 0 else 0.78
        pts.append((400 + 260 * rad * math.cos(t), 380 + 200 * rad * math.sin(t)))
    img, _ = _page(polygons=[pts])
    rgb = _letter(img, [("こんにちは", 470, 270), ("ありがと", 440, 270), ("大丈夫だよ", 330, 280),
                        ("まだまだ", 300, 280)])
    assert len(BubbleDetector().detect(rgb)) == 1


def test_split_lobes_shares_out_the_area():
    """The parts cover the area's erase mask between them, each once, and each holds its own lettering."""
    img, _ = _page(ellipses=[(150, 120, 350, 520), (310, 200, 510, 600)])
    rgb = _letter(img, _two_columns_apart())
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    white = cv2.erode((gray >= 225).astype(np.uint8) * 255, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=4)
    i = 1 + int(np.argsort(stats[1:, cv2.CC_STAT_AREA])[-2])  # the bubbles' area (the page is the largest)
    x, y, w, h, _a = (int(v) for v in stats[i])
    filled = fill_holes((labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255)
    inner = cv2.erode(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    dark = ((gray[y:y + h, x:x + w] < 140) & (inner > 0)).astype(np.uint8)
    parts = split_lobes(filled, inner, dark)
    assert parts is not None and len(parts) == 2
    total = np.zeros((h, w), np.int32)
    for px, py, pw, ph, p_filled, p_inner, p_dark in parts:
        assert p_filled.shape == p_inner.shape == p_dark.shape == (ph, pw)
        total[py:py + ph, px:px + pw] += p_inner > 0
        assert p_dark.sum() > 200
    assert total.max() == 1
    assert ((total > 0) == (inner > 0)).all()
    assert split_lobes(filled, inner, dark, notch=0.9) is None  # notches that shallow: one bubble


def test_focus_keeps_a_glyph_of_room_round_a_short_line():
    """A short exclamation in a small bubble: cut down to its neighbourhood, it keeps the room a bubble gives it
    (a cut to the glyphs alone left a box smaller than the bubble's text area, which the OCR's judgement then took
    for a speck of noise)."""
    img, _ = _page(ellipses=[(300, 300, 430, 470)])
    rgb = _letter(img, [("えっ", 353, 345)])
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 1
    tb = regions[0].core_box or regions[0].text_box
    glyph = regions[0].glyph
    bubble = regions[0].bbox
    focus_oversized(regions)
    r = regions[0]
    assert r.kind == "text-on-page"
    assert r.x0 <= tb[0] - glyph and r.x1 >= tb[2] + glyph and r.y0 <= tb[1] - glyph and r.y1 >= tb[3] + glyph
    assert max(r.width, r.height) >= 60  # not cut to a sliver the OCR's judgement takes for noise
    assert r.width < bubble[2] - bubble[0] and r.height < bubble[3] - bubble[1]  # still cut down
    assert r.mask.shape == (r.height, r.width)


def test_split_joined_bubbles_setting(settings, tmp_path):
    from taslation.config import Settings
    from taslation.pipeline import detector_from_settings

    assert detector_from_settings(settings).cfg.split_lobes
    assert not detector_from_settings(settings.with_overrides(split_joined_bubbles=False)).cfg.split_lobes
    toml = tmp_path / "taslation.toml"
    toml.write_text("split_joined_bubbles = false\n", encoding="utf-8")
    assert Settings.from_toml(toml).split_joined_bubbles is False
