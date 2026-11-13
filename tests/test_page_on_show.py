"""The window draws the page itself large: a frame's plain ground round the page is left out (`area.page_bounds`)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from taslation.ui import area
from taslation.ui.preview import ImageCanvas

GROUND = (0x2B, 0x2B, 0x2B)


def _page(w: int, h: int, seed: int = 0) -> Image.Image:
    """A manga-like page: white paper, black panel lines, a few dark blobs."""
    rng = np.random.default_rng(seed)
    page = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(page)
    d.rectangle((8, 8, w - 9, h // 2 - 4), outline="black", width=4)
    d.rectangle((8, h // 2 + 4, w - 9, h - 9), outline="black", width=4)
    for _ in range(12):
        x, y = int(rng.integers(20, w - 60)), int(rng.integers(20, h - 60))
        d.ellipse((x, y, x + 40, y + 30), fill="black")
    return page


def _screen(pages: list[Image.Image], size=(1920, 1080), ground=GROUND, counter: bool = True) -> Image.Image:
    """*pages* side by side (right to left as a spread shows them) fitted to a full-screen viewer's height."""
    out = Image.new("RGB", size, ground)
    h = size[1]
    shown = [p.resize((int(p.width * h / p.height), h)) for p in pages]
    total = sum(p.width for p in shown)
    x = (size[0] - total) // 2
    for p in shown:
        out.paste(p, (x, 0))
        x += p.width
    if counter:  # the viewer's page counter and a row of small marks, on the ground
        d = ImageDraw.Draw(out)
        d.text((size[0] - 80, h - 24), "12 / 36", fill=(0x8A, 0x8A, 0x8A))
        for k in range(24):
            d.rectangle((8 + k * 8, h - 16, 13 + k * 8, h - 11), fill=(0x90, 0x90, 0x90) if k % 3 else (0x10, 0x10, 0x10))
    return out


def test_a_page_on_a_dark_full_screen_viewer_is_the_page_alone():
    frame = _screen([_page(830, 1170)])
    box = area.page_bounds(frame)
    page_w = int(830 * 1080 / 1170)
    left = (1920 - page_w) // 2
    pad = area.TRIM_PAD * 1920
    assert box is not None
    assert abs(box[0] - (left - pad)) <= 6 and abs(box[2] - (left + page_w + pad)) <= 6
    assert box[1] == 0 and box[3] == 1080  # the page fills the height: nothing to leave out there


def test_a_spread_stays_whole():
    frame = _screen([_page(830, 1170, 1), _page(830, 1170, 2)])
    box = area.page_bounds(frame)
    both = 2 * int(830 * 1080 / 1170)
    assert box is not None and box[2] - box[0] >= both and box[0] <= (1920 - both) // 2
    assert box[2] >= (1920 + both) // 2


def test_a_page_on_white_and_frames_that_are_no_plain_ground():
    frame = _screen([_page(830, 1170)], ground=(250, 250, 250), counter=False)
    frame = frame.copy()
    ImageDraw.Draw(frame).rectangle((0, 0, 1919, 1079), outline=(250, 250, 250), width=3)
    box = area.page_bounds(frame)
    assert box is not None and box[2] - box[0] < 1000  # the panels and their ink: the white round them goes
    busy = Image.fromarray(np.random.default_rng(0).integers(0, 255, (600, 900, 3), np.uint8))
    assert area.page_bounds(busy) is None  # a desktop, a browser's toolbars all round: drawn whole
    full = _page(900, 1200).resize((900, 1200))
    assert area.page_bounds(full) is None  # the page is the frame: nothing to leave out
    assert area.page_bounds(Image.new("RGB", (800, 600), GROUND)) is None  # no page at all
    assert area.page_bounds(Image.new("RGB", (20, 20), GROUND)) is None


def test_the_canvas_draws_the_page_large_and_keeps_it_put(hidden_root):
    canvas = ImageCanvas(hidden_root)
    canvas.winfo_width, canvas.winfo_height = (lambda: 960), (lambda: 860)
    frame = _screen([_page(830, 1170)])
    canvas.set_image(frame)
    box = canvas.shown_box()
    assert box != (0, 0, 1920, 1080) and box[2] - box[0] < 900
    page_w = int(830 * 1080 / 1170)
    assert canvas.scale * page_w > 600  # was 960/1920 of it: some 380 px
    x, y = canvas.from_image_coords(box[0], box[1])  # the mapping follows the part drawn
    assert canvas.to_image_coords(x, y) == (box[0], box[1])
    canvas.set_image(_screen([_page(830, 1170, 5)]))
    assert canvas.shown_box() == box  # the next page: the same part
    canvas.crop = (0, 0, 1920, 1080)  # a crop asked for (the reading window's area) wins
    canvas.set_image(frame)
    assert canvas.shown_box() == (0, 0, 1920, 1080)
    canvas.crop = None
    canvas.trim = False  # the Set area dialog: the whole capture
    canvas.set_image(frame)
    assert canvas.shown_box() == (0, 0, 1920, 1080) and canvas.scale == 0.5
    canvas.destroy()
