from __future__ import annotations

import numpy as np
import pytest

from taslation.detect import BubbleDetector, order_regions
from taslation.regions import TextRegion, box_iou


def _match(regions, truth, iou_min=0.7):
    matched = []
    for t in truth:
        best = max((box_iou(r.bbox, tuple(t["bbox"])) for r in regions), default=0.0)
        matched.append(best >= iou_min)
    return matched


def test_detects_all_bubbles_on_sample_page(sample_page, sample_truth):
    regions = BubbleDetector().detect(np.asarray(sample_page))
    matched = _match(regions, sample_truth)
    assert all(matched), matched
    false_positives = [r for r in regions if max(box_iou(r.bbox, tuple(t["bbox"])) for t in sample_truth) < 0.3]
    assert len(false_positives) <= 1, [r.bbox for r in false_positives]


def test_detects_all_bubbles_on_second_page(sample_page2, sample_truth2):
    regions = BubbleDetector().detect(np.asarray(sample_page2))
    assert all(_match(regions, sample_truth2))


def test_text_box_inside_bubble_and_mask_shape(sample_page):
    for r in BubbleDetector().detect(np.asarray(sample_page)):
        assert r.x0 <= r.text_box[0] < r.text_box[2] <= r.x1
        assert r.y0 <= r.text_box[1] < r.text_box[3] <= r.y1
        assert r.mask.shape == (r.height, r.width)
        assert r.mask.max() == 255


def test_face_with_solid_eyes_is_not_a_bubble():
    """A white blob with two solid eye blobs and a mouth stroke must not pass as text."""
    img = np.full((1000, 800, 3), 255, np.uint8)
    img[100:900, 50:750] = 200
    yy, xx = np.mgrid[0:1000, 0:800]
    face = ((xx - 400) / 150.0) ** 2 + ((yy - 500) / 120.0) ** 2 <= 1.0
    outline = ((xx - 400) / 154.0) ** 2 + ((yy - 500) / 124.0) ** 2 <= 1.0
    img[outline] = 0
    img[face] = 255
    for ex in (340, 460):  # solid round eyes
        eye = ((xx - ex) / 16.0) ** 2 + ((yy - 470) / 20.0) ** 2 <= 1.0
        img[eye] = 0
    img[540:544, 380:420] = 0  # mouth stroke
    assert BubbleDetector().detect(img) == []


def test_one_character_bubble_is_kept():
    """A bubble holding a single big glyph plus a question mark must not count as 'one blob'."""
    img = np.full((1000, 800, 3), 255, np.uint8)
    img[100:900, 50:750] = 200  # gray panel so the bubble is a separate white component
    yy, xx = np.mgrid[0:1000, 0:800]
    inside = ((xx - 400) / 60.0) ** 2 + ((yy - 500) / 90.0) ** 2 <= 1.0
    border = ((xx - 400) / 64.0) ** 2 + ((yy - 500) / 94.0) ** 2 <= 1.0
    img[border] = 0
    img[inside] = 255
    img = _draw_vertical(img, "あ？", 378, 440, 44)  # one big glyph and a question mark
    regions = BubbleDetector().detect(img)
    assert len(regions) == 1
    assert regions[0].x0 < 400 < regions[0].x1


def test_blank_and_noise_images_give_nothing():
    det = BubbleDetector()
    assert det.detect(np.full((400, 300, 3), 255, np.uint8)) == []
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (400, 300, 3), dtype=np.uint8)
    assert det.detect(noise) == []


def _draw_vertical(img: np.ndarray, text: str, x: int, y: int, size: int, color=(0, 0, 0)) -> np.ndarray:
    """Render a vertical column of real glyphs (needs a Japanese font; skips the test otherwise)."""
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    fonts = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
    path = next((p for p in fonts if Path(p).is_file()), None)
    if path is None:
        pytest.skip("no Japanese font available")
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    font = ImageFont.truetype(path, size)
    for i, ch in enumerate(text):
        draw.text((x, y + i * int(size * 1.1)), ch, font=font, fill=color)
    return np.asarray(pil).copy()


def test_oversized_white_area_is_focused_on_its_text():
    from taslation.detect import focus_oversized

    img = np.full((1400, 1400, 3), 255, np.uint8)
    # a closed white panel (about 13% of the image, so it passes the size filter) ...
    img[38:40, 38:542] = 0
    img[540:542, 38:542] = 0
    img[38:542, 38:40] = 0
    img[38:542, 540:542] = 0
    # ... with a small vertical text column near its right edge
    img = _draw_vertical(img, "オイ人間どこへ行く", 460, 120, 24)
    regions = BubbleDetector().detect(img)
    assert len(regions) == 1
    big = regions[0]
    assert big.width > 450 and big.height > 450
    focus_oversized(regions)
    r = regions[0]
    assert r.kind == "text-on-page"
    assert r.width < 320 and r.height < 420
    assert r.x0 <= 460 and r.x1 >= 484 and r.y0 <= 125 and r.y1 >= 120 + 8 * 26
    assert r.mask.shape == (r.height, r.width)


def _region(x0, y0, x1, y1):
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), (x0, y0, x1, y1))


def test_reading_order_is_right_to_left_then_down():
    top_right = _region(600, 10, 700, 100)
    top_left = _region(10, 20, 110, 110)
    bottom = _region(300, 300, 400, 400)
    ordered = order_regions([bottom, top_left, top_right])
    assert ordered == [top_right, top_left, bottom]
    assert [r.order for r in ordered] == [0, 1, 2]
