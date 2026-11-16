"""The window draws the page itself large: a frame's plain ground round the page is left out (`area.page_bounds`),
and nothing outside the capture area is drawn - a browser's own title bar, a reader's band
(`ImageCanvas.read_area_of`)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from taslation import fingerprint as fp
from taslation.ui import area
from taslation.ui.preview import ImageCanvas

GROUND = (0x2B, 0x2B, 0x2B)
# a browser window as a browser-based reader draws in it (`tools/standin_viewer`): the browser's own title bar in its
# client area, light or dark, then the reader's band, then its dark ground round the page
LIGHT_TITLE, DARK_TITLE = (0xDE, 0xE1, 0xE6), (0x20, 0x21, 0x24)
BAND, BAND_LINE, BAND_PART, COUNTER = (0x3A, 0x3D, 0x41), (0x56, 0x59, 0x5E), (0x4A, 0x4E, 0x53), (0x9A, 0x9A, 0x9A)
TITLE_ROWS, BAND_ROWS = 31, 54
READ = (0, TITLE_ROWS + BAND_ROWS, 0, 0)  # the reader's capture area there: the title bar and the band left out
NARROW, WIDE = (844, 992), (1904, 1024)  # the narrow window (single pages) and the enlarged one (spreads)


def _page(w: int, h: int, seed: int = 0, margin: int = 8) -> Image.Image:
    """A manga-like page: white paper, black panel lines *margin* px in, a few dark blobs."""
    rng = np.random.default_rng(seed)
    page = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(page)
    d.rectangle((margin, margin, w - 1 - margin, h // 2 - 4), outline="black", width=4)
    d.rectangle((margin, h // 2 + 4, w - 1 - margin, h - 1 - margin), outline="black", width=4)
    for _ in range(12):
        x, y = int(rng.integers(margin + 12, w - margin - 52)), int(rng.integers(margin + 12, h - margin - 52))
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
    assert area.page_bounds(frame, (0, 0, 1920, 1080)) == box  # the whole frame as the part: the same


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


# ---------------------------------------------------------------------------------------------------- in a browser
def _browser(pages: list[Image.Image], size: tuple[int, int], title=LIGHT_TITLE, ground=GROUND, band=BAND,
             line=BAND_LINE) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """The client area of a browser window not maximised, as a browser-based reader draws in it (the stand-in viewer's
    layout): the browser's own title bar (the site's icon, its title, its three buttons), the reader's band (its buttons
    on the right, a slider, a line under it), its ground with a page counter, *pages* side by side (right to left)
    fitted under the band; and where the pages are."""
    w, h = size
    out = Image.new("RGB", size, ground)
    d = ImageDraw.Draw(out)
    ink = (0x20, 0x20, 0x20) if sum(title) > 384 else (0xE8, 0xEA, 0xED)
    d.rectangle((0, 0, w - 1, TITLE_ROWS - 1), fill=title)
    d.rectangle((8, 8, 22, 22), fill=ink)
    d.text((30, 9), "Stand-in reader t0123456789", fill=ink)
    for k in range(3):
        x = w - 46 * (k + 1) + 17
        d.rectangle((x, 10, x + 10, 20), outline=ink)
    top = TITLE_ROWS
    d.rectangle((0, top, w - 1, top + BAND_ROWS - 1), fill=band)
    d.rectangle((0, top + BAND_ROWS - 1, w - 1, top + BAND_ROWS - 1), fill=line)
    for k in range(4):
        x = w - 44 - 40 * k
        d.rectangle((x, top + 12, x + 27, top + 39), fill=BAND_PART)
    d.rectangle((int(w * 0.3), top + 27, int(w * 0.65), top + 29), fill=BAND_PART)
    margin, foot = 14, 20
    room = h - top - BAND_ROWS - 2 * margin - foot
    tall = max(p.height for p in pages)
    widths = [p.width * tall / p.height for p in pages]
    scale = min((w - 2 * margin) / sum(widths), room / tall)
    page_h, page_ws = round(tall * scale), [round(x * scale) for x in widths]
    right = (w + sum(page_ws)) // 2
    y = top + BAND_ROWS + margin + (room - page_h) // 2
    rect = (right - sum(page_ws), y, right, y + page_h)
    for p, pw in zip(pages, page_ws):
        out.paste(p.resize((pw, page_h)), (right - pw, y))
        right -= pw
    d.text((w - 60, h - 18), "7 / 14", fill=COUNTER)
    return out, rect


def _dark_page(w: int, h: int) -> Image.Image:
    """A page of black panels with a few white bubbles in them."""
    page = Image.new("RGB", (w, h), (8, 8, 8))
    d = ImageDraw.Draw(page)
    for k in range(5):
        x, y = 40 + (k % 2) * (w // 2), 60 + k * (h // 6)
        d.ellipse((x, y, x + w // 4, y + h // 10), fill="white", outline="black", width=3)
    return page


def _canvas(root, margins) -> ImageCanvas:
    """A canvas as the window's page: drawing no more of a frame than the capture area *margins()* leave."""
    canvas = ImageCanvas(root)
    canvas.winfo_width, canvas.winfo_height = (lambda: 960), (lambda: 860)
    canvas.read_area_of = lambda image: area.margins_to_box(margins(), image.size)
    return canvas


def _holds(box, inner) -> bool:
    return box[0] <= inner[0] and box[1] <= inner[1] and box[2] >= inner[2] and box[3] >= inner[3]


@pytest.mark.parametrize("title", [LIGHT_TITLE, DARK_TITLE])
def test_a_narrow_browser_window_draws_the_page_and_none_of_the_browser_or_the_band(hidden_root, title):
    frame, page = _browser([_page(830, 1170)], NARROW, title)
    whole = area.page_bounds(frame)  # on the whole frame the paper grows past the band into the title bar
    assert whole is None or whole[1] < TITLE_ROWS + BAND_ROWS
    panel = area.box_to_margins(page, frame.size)  # the page panel found in the reader's area: the area in force
    for margins in (READ, panel):
        canvas = _canvas(hidden_root, lambda m=margins: m)
        canvas.set_image(frame)
        box = canvas.shown_box()
        assert box[1] >= TITLE_ROWS + BAND_ROWS and _holds(box, page)  # the page whole, the bars left out
        if margins == panel:
            assert box == page  # the page fills its panel: the panel drawn (as reading mode crops to it)
        else:  # the reader's area: the ground round the page left out as on a full-screen viewer
            pad = area.TRIM_PAD * max(frame.size) + 2 * max(1.0, max(frame.size) / area.TRIM_WORK)  # (working copy)
            assert all(0 <= d <= pad for d in (page[0] - box[0], page[1] - box[1], box[2] - page[2],
                                                box[3] - page[3]))
        canvas.destroy()


def test_a_spread_in_the_enlarged_browser_window_is_drawn_as_before_without_the_band(hidden_root):
    frame, spread = _browser([_page(830, 1170, 1), _page(830, 1170, 2)], WIDE)
    before = area.page_bounds(frame)  # the whole frame: the spread on its ground, and the band's last rows
    assert before is not None and before[1] < TITLE_ROWS + BAND_ROWS <= spread[1] and _holds(before, spread)
    canvas = _canvas(hidden_root, lambda: READ)
    canvas.set_image(frame)
    box = canvas.shown_box()
    assert box[1] == TITLE_ROWS + BAND_ROWS and abs(box[0] - before[0]) <= 1 and abs(box[2] - before[2]) <= 1
    assert abs(box[3] - before[3]) <= 1
    canvas.destroy()
    canvas = _canvas(hidden_root, lambda: area.box_to_margins(spread, frame.size))
    canvas.set_image(frame)
    assert canvas.shown_box() == spread  # the area in force is the spread's panel: both pages, nothing round them
    canvas.destroy()


def test_light_and_dark_page_grounds_stay_within_the_area(hidden_root):
    light, page = _browser([_page(830, 1170)], NARROW, LIGHT_TITLE, ground=(250, 250, 250), band=(0xF1, 0xF1, 0xF1),
                           line=(0xD0, 0xD0, 0xD0))
    canvas = _canvas(hidden_root, lambda: READ)
    canvas.set_image(light)
    box = canvas.shown_box()
    ink = (page[0] + 8, page[1] + 8, page[2] - 8, page[3] - 8)  # the page's white edge is the ground's colour
    assert box[1] >= TITLE_ROWS + BAND_ROWS and _holds(box, ink) and box[2] - box[0] < light.width - 100
    canvas.destroy()
    dark, page = _browser([_dark_page(830, 1170)], NARROW, DARK_TITLE)
    for margins in (READ, area.box_to_margins(page, dark.size)):
        canvas = _canvas(hidden_root, lambda m=margins: m)
        canvas.set_image(dark)
        box = canvas.shown_box()
        assert box[1] >= TITLE_ROWS + BAND_ROWS and _holds(box, page)
        canvas.destroy()


def test_a_page_with_a_wide_white_margin_is_drawn_whole_in_its_panel(hidden_root):
    # the page panel is the capture area: on a dark viewer its border is the paper's white margin, which is the page's
    frame, page = _browser([_page(830, 1170, 4, margin=70)], NARROW)
    canvas = _canvas(hidden_root, lambda: area.box_to_margins(page, frame.size))
    canvas.set_image(frame)
    assert canvas.shown_box() == page
    canvas.destroy()
    # on a white viewer the paper's margin is the viewer's ground: the ink drawn large, as on the whole frame
    white, page = _browser([_page(830, 1170, 4, margin=70)], NARROW, LIGHT_TITLE, ground=(250, 250, 250),
                           band=(0xF1, 0xF1, 0xF1), line=(0xD0, 0xD0, 0xD0))
    canvas = _canvas(hidden_root, lambda: area.box_to_margins(page, white.size))
    canvas.set_image(white)
    box = canvas.shown_box()
    assert _holds(page, box) and box != page and box[2] - box[0] > 0.7 * (page[2] - page[0])
    canvas.destroy()


def test_a_page_that_fills_the_frame_is_drawn_whole(hidden_root):
    full = _page(900, 1200)
    for margins in ((0, 0, 0, 0), None):  # no area set: the whole capture is read
        canvas = _canvas(hidden_root, lambda m=margins: m)
        if margins is None:
            canvas.read_area_of = None
        canvas.set_image(full)
        assert canvas.shown_box() == (0, 0, 900, 1200)
        canvas.destroy()
    canvas = _canvas(hidden_root, lambda: (20, 30, 40, 50))  # an area within it: that area, as reading mode shows
    canvas.set_image(full)
    assert canvas.shown_box() == (20, 30, 860, 1150)
    canvas.destroy()


def test_the_part_drawn_follows_the_area_and_the_mapping_follows_the_part(hidden_root):
    frame, page = _browser([_page(830, 1170)], NARROW)
    margins = [READ]
    canvas = _canvas(hidden_root, lambda: margins[0])
    canvas.set_image(frame)
    first = canvas.shown_box()
    bubble = (page[0] + 180, page[1] + 300, page[0] + 240, page[1] + 380)  # a bubble on the page, capture pixels
    reach = 1 + 1 / canvas.scale  # (a canvas pixel is this many of the image's, and both ways round down)
    for x, y in ((bubble[0], bubble[1]), (bubble[2], bubble[3])):
        cx, cy = canvas.from_image_coords(x, y)
        assert canvas.inside(cx, cy)
        assert all(abs(a - b) <= reach for a, b in zip(canvas.to_image_coords(cx, cy), (x, y)))
    assert not canvas.inside(*canvas.from_image_coords(400, TITLE_ROWS // 2))  # the title bar is not on show
    cover, _cover_page = _browser([_page(600, 1170, 3)], NARROW)  # a narrower page next: the part stays put
    canvas.set_image(cover)
    assert canvas.shown_box() == first
    margins[0] = area.box_to_margins(page, frame.size)  # the page panel found: the same frame drawn by it
    canvas.set_image(frame)
    assert canvas.shown_box() == page
    margins[0] = (0, 0, 0, 0)  # no area: as before there was one (this frame drawn whole)
    canvas.set_image(frame)
    assert canvas.shown_box() == (0, 0, *frame.size)
    canvas.destroy()


def test_the_page_identity_is_the_capture_areas_whatever_the_title_bar():
    light, page = _browser([_page(830, 1170)], NARROW, LIGHT_TITLE)
    dark, _page_rect = _browser([_page(830, 1170)], NARROW, DARK_TITLE)
    a, b = fp.analyze(np.asarray(light), READ), fp.analyze(np.asarray(dark), READ)
    assert [u.fingerprint for u in a] == [u.fingerprint for u in b] and len(a) == 1 and _holds(page, a[0].box)
    whole = fp.analyze(np.asarray(light))  # with no area the title bar is taken in: another fingerprint
    assert whole[0].box[1] < TITLE_ROWS and fp.hamming(whole[0].fingerprint, a[0].fingerprint) > 40


def test_a_box_clipped_to_a_bound():
    assert area.clipped((10, 10, 50, 50), (20, 0, 100, 40)) == (20, 10, 50, 40)
    assert area.clipped(None, (1, 2, 3, 4)) == (1, 2, 3, 4)
    assert area.clipped((0, 0, 5, 5), (10, 10, 20, 20)) == (10, 10, 20, 20)  # nothing in common: the bound
