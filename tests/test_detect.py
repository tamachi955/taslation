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


def test_a_bubble_s_least_size_is_taken_at_the_page_s_scale():
    """A white area 18 px across (after the one-pixel erosion) is under `min_size` (24 px) on a page as high as the
    sample set's; on a page shown half as high (scale 0.5: 12 px) it is a bubble, as one 36 px across is at full
    size."""
    img = np.full((400, 400, 3), 200, np.uint8)  # a grey panel: the bubble is a white area of its own
    img[188:208, 188:208] = 255
    for x, y in ((192, 192), (198, 192), (195, 198)):  # three L-shaped strokes: lettering, not a blob nor a line
        img[y:y + 5, x:x + 2] = 0
        img[y + 3:y + 5, x:x + 5] = 0
    assert BubbleDetector().detect(img) == []
    (found,) = BubbleDetector().detect(img, scale=0.5)
    assert found.x0 < 197 < found.x1 and found.y0 < 197 < found.y1


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


def test_a_narrow_bubble_round_one_column_stays_a_bubble():
    """A tall narrow bubble round one column of bold characters, as a page shown 1000 px high has it (about 60 px wide,
    225 high, characters of 15 px): its text is a small share of its box, but the cut would keep nearly all of it
    (`FOCUS_WHOLE`), so it is no white area round a small text - it stays a bubble, erased with its paper on its
    interior (cut down to text on the page, its lettering was judged on a ring round the column that reached its
    outline, went to the inpainting and kept the strokes' cores as a dotted line)."""
    import cv2

    from taslation.detect import focus_oversized
    from taslation.render import artwork
    from taslation.render.erase import erase_region

    img = np.full((600, 400, 3), 255, np.uint8)
    img[40:560, 40:360] = 190  # a toned panel: the bubble is a white area of its own
    cv2.ellipse(img, (200, 300), (31, 114), 0, 0, 360, (0, 0, 0), -1)
    cv2.ellipse(img, (200, 300), (28, 111), 0, 0, 360, (255, 255, 255), -1)
    img = _draw_vertical(img, "まさかここまで来るなん", 192, 300 - 11 * 16 // 2, 15)
    (r,) = BubbleDetector().detect(img)
    tb = r.text_box
    assert (tb[2] - tb[0]) * (tb[3] - tb[1]) < 0.3 * r.width * r.height  # a small share of its box ...
    focus_oversized([r])
    assert r.kind == "bubble" and r.width >= 50 and r.height >= 210  # ... and still the bubble, whole
    assert not artwork.on_art(img, r)  # its paper erases it, not the inpainting
    out = img.copy()
    erase_region(out, r)
    inside = np.zeros(img.shape[:2], np.uint8)
    cv2.ellipse(inside, (200, 300), (25, 108), 0, 0, 360, 255, -1)
    gray = cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)
    assert int(((gray < 160) & (inside > 0)).sum()) == 0  # nothing of the column left


def test_the_cut_of_a_white_area_keeps_the_same_share_of_it_on_the_page_shown_at_any_size():
    """The cut's pad goes with the glyphs (`FOCUS_PAD`): with 6 px fixed, a bubble of the tests' sample page kept 87 %
    of its area at full size and 90 % at 0.8 of it - lettering on the page at one size, a bubble at the other, and the
    region editor lost its region when the page was taken again at the other size."""
    from pathlib import Path

    from PIL import Image

    from taslation.detect.bubbles import FOCUS_MARGIN, FOCUS_PAD, focus_window

    page = Image.open(Path(__file__).parent / "fixtures" / "sample_page.png").convert("RGB")
    shares = {}
    for f in (1.0, 0.8, 0.6):
        img = page if f == 1.0 else page.resize((round(page.width * f), round(page.height * f)))
        for r in BubbleDetector().detect(np.asarray(img)):
            win = focus_window(r.core_box or r.text_box, r.bbox, 0.30, FOCUS_MARGIN * r.glyph, FOCUS_PAD * r.glyph)
            if win is not None:
                key = (round(r.x0 / img.width, 1), round(r.y0 / img.height, 1))
                share = (win[2] - win[0]) * (win[3] - win[1]) / (r.width * r.height)
                shares.setdefault(key, []).append(share)
    assert len(shares) == 6 and all(len(s) == 3 for s in shares.values())
    assert all(max(s) - min(s) < 0.045 for s in shares.values())  # (6 px fixed: up to 0.07 apart)


def _region(x0, y0, x1, y1):
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), (x0, y0, x1, y1))


def test_reading_order_is_right_to_left_then_down():
    top_right = _region(600, 10, 700, 100)
    top_left = _region(10, 20, 110, 110)
    bottom = _region(300, 300, 400, 400)
    ordered = order_regions([bottom, top_left, top_right])
    assert ordered == [top_right, top_left, bottom]
    assert [r.order for r in ordered] == [0, 1, 2]


def test_a_region_under_another_comes_after_it_also_in_one_row():
    """A tall region on the left puts all three in one row; the lower right one, under the upper one and a little
    further right, still comes after it, and the tall one keeps its place after both."""
    tall = _region(100, 100, 160, 500)
    upper = _region(400, 100, 500, 200)
    lower = _region(420, 300, 520, 400)  # centre further right than upper's
    assert order_regions([lower, tall, upper]) == [upper, lower, tall]
    mirrored = [_region(640 - r.x1, r.y0, 640 - r.x0, r.y1) for r in (tall, upper, lower)]
    assert order_regions(list(reversed(mirrored)), rtl=False) == [mirrored[1], mirrored[2], mirrored[0]]


def test_a_region_under_another_comes_after_it_inside_its_panel():
    """The same inside a panel. In the other panel a lower region overlaps the upper one side to side by less than half
    the narrower one's width: it is beside it, not under it, and keeps the rows' order (right first)."""
    left_panel, right_panel = (0, 0, 300, 900), (300, 0, 640, 900)
    tall, upper, lower = _region(320, 100, 380, 500), _region(500, 100, 600, 200), _region(520, 300, 620, 400)
    tall_left, high, low_right = _region(20, 100, 60, 500), _region(100, 100, 200, 200), _region(170, 250, 290, 350)
    ordered = order_regions([low_right, lower, high, tall, tall_left, upper], panels=[left_panel, right_panel])
    assert ordered == [upper, lower, tall, low_right, high, tall_left]
