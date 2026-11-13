from __future__ import annotations

import random
import time

import numpy as np
from PIL import Image, ImageDraw

from taslation import fingerprint as fp


def test_same_page_at_other_size_and_background_matches(sample_page, sample_page2):
    base = fp.analyze(np.asarray(sample_page))
    other = fp.analyze(np.asarray(sample_page2))
    assert len(base) == 1 and len(other) == 1
    small = sample_page.resize((sample_page.width * 3 // 5, sample_page.height * 3 // 5), Image.LANCZOS)
    canvas = Image.new("RGB", (small.width + 320, small.height + 180), (35, 35, 35))
    canvas.paste(small, (160, 90))
    scaled = fp.analyze(np.asarray(canvas))
    assert len(scaled) == 1
    assert fp.hamming(base[0].fingerprint, scaled[0].fingerprint) <= 14
    assert fp.hamming(base[0].fingerprint, other[0].fingerprint) >= 60
    assert abs(base[0].aspect - scaled[0].aspect) < 0.05


def test_spread_is_split_right_page_first(sample_page, sample_page2):
    w, h = sample_page.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(sample_page2, (0, 20))
    spread.paste(sample_page, (w + 60, 20))
    units = fp.analyze(np.asarray(spread))
    assert [u.index for u in units] == [0, 1]
    right, left = units
    assert right.box[0] > left.box[2]
    single1 = fp.analyze(np.asarray(sample_page))[0].fingerprint
    single2 = fp.analyze(np.asarray(sample_page2))[0].fingerprint
    assert fp.hamming(right.fingerprint, single1) <= 12
    assert fp.hamming(left.fingerprint, single2) <= 12


def test_viewer_widgets_do_not_move_the_page_box(sample_page):
    """A dark viewer with a white toolbar, a small button and a progress bar around the page."""
    w, h = sample_page.size
    small = sample_page.resize((w * 3 // 5, h * 3 // 5), Image.LANCZOS)
    canvas = Image.new("RGB", (small.width + 500, small.height + 260), (0, 0, 0))
    canvas.paste((255, 255, 255), (0, 0, canvas.width, 90))  # toolbar
    canvas.paste((255, 255, 255), (0, canvas.height // 2 - 40, 36, canvas.height // 2 + 40))  # "<" button
    canvas.paste((230, 230, 230), (40, canvas.height - 20, canvas.width - 40, canvas.height - 17))  # progress bar
    canvas.paste(small, (250, 120))
    units = fp.analyze(np.asarray(canvas))
    assert len(units) == 1
    box = units[0].box
    assert 250 <= box[0] and box[2] <= 250 + small.width and 120 <= box[1] and box[3] <= 120 + small.height
    plain = fp.analyze(np.asarray(sample_page))[0]
    assert fp.hamming(units[0].fingerprint, plain.fingerprint) <= 14


def test_gapless_spread_is_split_in_the_middle(sample_page, sample_page2):
    w, h = sample_page.size
    spread = Image.new("RGB", (w * 2, h), (0, 0, 0))
    spread.paste(sample_page2, (0, 0))
    spread.paste(sample_page, (w, 0))
    units = fp.analyze(np.asarray(spread))
    assert [u.index for u in units] == [0, 1]
    right, left = units
    assert right.box[0] >= w - 2 and left.box[2] <= w + 2
    assert fp.hamming(right.fingerprint, fp.analyze(np.asarray(sample_page))[0].fingerprint) <= 8
    assert fp.hamming(left.fingerprint, fp.analyze(np.asarray(sample_page2))[0].fingerprint) <= 8


def test_margins_restrict_the_analysed_area(sample_page):
    rgb = np.asarray(sample_page)
    full = fp.analyze(rgb)[0]
    cropped = fp.analyze(rgb, margins=(0, 0, 0, rgb.shape[0] // 2))[0]
    assert cropped.box[3] <= rgb.shape[0] // 2
    assert cropped.fingerprint != full.fingerprint


def test_blank_capture_has_no_units():
    assert fp.analyze(np.full((300, 200, 3), 255, np.uint8)) == []
    assert fp.analyze(np.zeros((300, 200, 3), np.uint8)) == []


def test_normalize_roundtrip():
    unit = fp.PageUnit(box=(100, 50, 600, 850), fingerprint="0" * fp.FINGERPRINT_HEX_LEN)
    box = (150, 100, 350, 400)
    assert unit.denormalize(unit.normalize(box)) == box


def test_fingerprint_format():
    s = fp.compute_fingerprint(np.random.default_rng(1).integers(0, 255, (200, 150), dtype=np.uint8))
    assert len(s) == fp.FINGERPRINT_HEX_LEN
    int(s, 16)
    assert fp.hamming(s, s) == 0


# ------------------------------------------------------------------ pages that are black panels in part
PAGE = (600, 840)  # the drawn pages' size
BUBBLES = ((40, 430, 170, 600), (400, 455, 540, 625), (215, 650, 345, 820))  # in the black lower half of _dark_page


def _bubble(draw: ImageDraw.ImageDraw, box, rng: random.Random) -> None:
    """A white speech bubble with an outline and a column of letter-like strokes."""
    x0, y0, x1, y1 = box
    draw.ellipse(box, fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    cx = (x0 + x1) // 2
    for y in range(y0 + 30, y1 - 40, 22):
        draw.line((cx - 8, y + rng.randint(0, 6), cx + 8, y + rng.randint(8, 14)), fill=(0, 0, 0), width=3)


def _speed_lines(draw: ImageDraw.ImageDraw, box, rng: random.Random, n: int = 14) -> None:
    """Thin grey lines across a black area: the art a page's black panels carry (the viewer's background has none)."""
    x0, y0, x1, y1 = box
    for i in range(n):
        y = y0 + (y1 - y0) * i // n
        draw.line((x0, y, x1, min(y1, y + rng.randint(120, 260))), fill=(rng.randint(70, 130),) * 3, width=2)


def _dark_page(seed: int = 5, top: bool = True) -> Image.Image:
    """A page of PAGE size whose upper half (with *top*) is white paper with two panels of art and whose lower half
    is black panels with speed lines, holding the white BUBBLES; without *top* the whole page is black panels, with
    bubbles in its upper half too."""
    rng = random.Random(seed)
    w, h = PAGE
    page = Image.new("RGB", PAGE, (0, 0, 0))
    draw = ImageDraw.Draw(page)
    split = 380 if top else 0
    if top:
        draw.rectangle((0, 0, w - 1, split - 1), fill=(255, 255, 255))
        for box in ((10, 10, w - 11, 180), (10, 190, w - 11, split - 11)):
            draw.rectangle(box, outline=(0, 0, 0), width=3)
            for _ in range(6):
                x, y = rng.randint(box[0] + 10, box[2] - 90), rng.randint(box[1] + 10, box[3] - 60)
                draw.ellipse((x, y, x + rng.randint(30, 80), y + rng.randint(20, 50)), fill=(rng.randint(60, 180),) * 3)
    _speed_lines(draw, (0, split, w, h), rng)
    bubbles = BUBBLES if top else BUBBLES + ((60, 40, 190, 210), (380, 90, 510, 260), (230, 260, 360, 410))
    for box in bubbles:
        _bubble(draw, box, rng)
    return page


def _black_gutter_page(seed: int = 11) -> Image.Image:
    """A page of PAGE size on black: framed white panels with art, 45 px of plain black between them (no art at
    all), one panel tall enough to be a large blob of its own, the other three not."""
    rng = random.Random(seed)
    page = Image.new("RGB", PAGE, (0, 0, 0))
    draw = ImageDraw.Draw(page)
    for box in ((20, 20, 580, 290), (20, 335, 280, 555), (325, 335, 580, 555), (20, 600, 580, 820)):
        draw.rectangle(box, fill=(255, 255, 255), outline=(40, 40, 40), width=3)
        for _ in range(5):
            x, y = rng.randint(box[0] + 10, box[2] - 70), rng.randint(box[1] + 10, box[3] - 50)
            draw.rectangle((x, y, x + rng.randint(20, 60), y + rng.randint(15, 40)), fill=(rng.randint(0, 150),) * 3)
    return page


def _viewer(*pages: Image.Image, size=(1100, 1000), at=(250, 80)) -> tuple[Image.Image, list[fp.Box]]:
    """A black viewer showing the *pages* right page first (side by side, touching, as a browser-based viewer shows
    a spread); the capture and each page's box, right page first."""
    img = Image.new("RGB", size, (0, 0, 0))
    x, y = at
    boxes = []
    for page in reversed(pages):
        img.paste(page, (x, y))
        boxes.append((x, y, x + page.width, y + page.height))
        x += page.width
    return img, boxes[::-1]


def _bright_page(sample_page: Image.Image) -> Image.Image:
    return sample_page.resize(PAGE, Image.LANCZOS)


def _lowest(page: tuple[int, int, int, int]) -> int:
    return page[1] + max(b[3] for b in BUBBLES)


def test_a_page_whose_lower_half_is_black_panels_reaches_its_lowest_bubble():
    """The white upper panels are the page's one large blob; the bubbles in the black panels below are small, and
    were left out (the unit stopped at the upper panels and, landscape then, was split as if it were a spread)."""
    img, (page,) = _viewer(_dark_page())
    (unit,) = fp.analyze(np.asarray(img))
    assert unit.box[0] >= page[0] and unit.box[2] <= page[2] and unit.box[1] >= page[1]
    assert _lowest(page) - 2 <= unit.box[3] <= page[3], (unit.box, page)
    assert fp.paper_box(np.asarray(img))[3] >= _lowest(page) - 2  # the batch's paper check sees the whole page too


def test_panels_across_plain_black_gutters_are_one_page():
    """Panels kept apart by gutters of plain black, wider than a knob or a button would need to be from the page to
    stay out: a panel is far larger than the gutter is wide, so it is the page's."""
    img, (page,) = _viewer(_black_gutter_page())
    (unit,) = fp.analyze(np.asarray(img))
    assert max(abs(a - b) for a, b in zip(unit.box, (page[0] + 20, page[1] + 20, page[0] + 581, page[1] + 821))) <= 2


def test_the_viewers_bars_buttons_and_knobs_stay_out_of_a_dark_page():
    """A slider with its knob under the page, a knob beside it, the side arrows, a thin strip over the page's
    columns and a header across the window: none of them grows the page, however black its lower half."""
    img, (page,) = _viewer(_dark_page(), size=(1100, 1040), at=(250, 100))
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.rectangle((page[0] + 20, page[3] + 25, page[2] - 20, page[3] + 34), fill=(150, 150, 150))  # the slider ...
    d.ellipse((page[0] + 200, page[3] + 20, page[0] + 220, page[3] + 40), fill=(230, 230, 230))  # ... and its knob
    d.ellipse((page[2] + 40, page[3] - 60, page[2] + 60, page[3] - 40), fill=(230, 230, 230))  # a knob beside it
    for x0 in (0, w - 36):  # the page-turn arrows at the window's sides
        d.rounded_rectangle((x0, h // 2 - 40, x0 + 35, h // 2 + 40), 6, fill=(255, 255, 255))
        d.line((x0 + 22, h // 2 - 14, x0 + 12, h // 2, x0 + 22, h // 2 + 14), fill=(40, 40, 40), width=3)
    d.rectangle((page[0] + 10, page[1] - 30, page[2] - 10, page[1] - 12), fill=(220, 220, 220))  # a strip over it
    d.rectangle((0, 0, w - 1, 50), fill=(255, 255, 255))  # a header across the window
    for x in range(40, w - 40, 30):
        d.line((x, 20, x + 12, 32), fill=(30, 30, 30), width=2)
    (unit,) = fp.analyze(np.asarray(img))
    assert page[0] <= unit.box[0] and unit.box[2] <= page[2] and page[1] <= unit.box[1], (unit.box, page)
    assert _lowest(page) - 2 <= unit.box[3] <= page[3], (unit.box, page)


def test_a_spread_with_a_dark_page_gives_two_full_pages_in_any_capture_area(sample_page):
    """The right page black in its lower half; the left page black panels all over (no large blob of its own, so
    the spread was one page): two units, the dark one reaching its bubbles; the same units in the whole capture
    and in the spread's panel."""
    bright = _bright_page(sample_page)
    for right, left, dark in ((_dark_page(), bright, 0), (bright, _dark_page(9, top=False), 1)):
        img, boxes = _viewer(right, left, size=(1500, 1000), at=(150, 80))
        whole = fp.analyze(np.asarray(img))
        assert [u.index for u in whole] == [0, 1], [u.box for u in whole]
        for unit, page in zip(whole, boxes):
            assert page[0] - 2 <= unit.box[0] and unit.box[2] <= page[2] + 2, (unit.box, page)
        box, page = whole[dark].box, boxes[dark]
        assert _lowest(page) - 2 <= box[3] <= page[3] and box[1] <= page[1] + 45, (box, page)
        assert box[2] - box[0] >= 0.75 * PAGE[0], (box, page)
        x0, y0, x1, y1 = boxes[1][0], boxes[0][1], boxes[0][2], boxes[0][3]
        panel = fp.analyze(np.asarray(img), (x0, y0, img.width - x1, img.height - y1))
        assert [u.fingerprint for u in panel] == [u.fingerprint for u in whole]


def test_analyze_stays_fast_on_a_full_hd_capture_with_dark_pages(sample_page):
    """It runs at every look at the viewer."""
    img, _boxes = _viewer(_dark_page(), _bright_page(sample_page), size=(1920, 1080), at=(360, 120))
    rgb = np.asarray(img)
    fp.analyze(rgb)
    times = []
    for _ in range(5):
        start = time.perf_counter()
        fp.analyze(rgb)
        times.append(time.perf_counter() - start)
    assert min(times) < 0.030, times
