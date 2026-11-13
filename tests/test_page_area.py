"""Finding the page panel in a capture of a reader window (find_page_area), on synthetic captures only: the fixture
pages (synthetic themselves) or drawn pages, pasted into a drawn browser and reader frame; JPEG noise is made in
memory. Nothing is written to disk."""

from __future__ import annotations

import io
import random
import time

import numpy as np
import pytest
from PIL import Image, ImageDraw

from taslation.detect.page_area import find_page_area, page_area_margins
from taslation.ui import area

FULL_HD = (1936, 1048)  # Chrome maximised on a 1920x1080 display: a browser-based viewer's window


# ------------------------------------------------------------------------------------------------- drawing
def _glyphs(draw: ImageDraw.ImageDraw, x: float, y: float, n: int, size: int, fill, rng: random.Random,
            vertical: bool = False) -> None:
    """*n* letter-like marks of *size* px in a row (or a column): three random strokes each."""
    for i in range(n):
        cx, cy = (x, y + i * size * 1.1) if vertical else (x + i * size * 0.75, y)
        for _ in range(3):
            ax, ay = cx + rng.uniform(0, size * 0.6), cy + rng.uniform(0, size)
            bx, by = cx + rng.uniform(0, size * 0.6), cy + rng.uniform(0, size)
            draw.line((ax, ay, bx, by), fill=fill, width=max(1, size // 8))


def _browser_bars(draw: ImageDraw.ImageDraw, width: int, theme: str, rng: random.Random) -> None:
    """A tab strip (rows 0-39) and a toolbar with the address field (rows 40-84), Chrome's colours."""
    if theme == "dark":
        strip, tab, bar, field, text = (32, 33, 36), (53, 54, 58), (53, 54, 58), (32, 33, 36), (232, 234, 237)
    else:
        strip, tab, bar, field, text = (222, 225, 230), (255, 255, 255), (255, 255, 255), (241, 243, 244), (32, 33, 36)
    draw.rectangle((0, 0, width - 1, 39), fill=strip)
    draw.rounded_rectangle((70, 6, 330, 46), 8, fill=tab)
    _glyphs(draw, 110, 16, 14, 14, text, rng)  # the tab's title
    for k in range(3):
        _glyphs(draw, width - 140 + k * 46, 14, 1, 14, text, rng)  # the window's buttons
    draw.rectangle((0, 40, width - 1, 84), fill=bar)
    draw.rounded_rectangle((150, 47, width - 220, 79), 15, fill=field)
    _glyphs(draw, 190, 56, 40, 14, text, rng)  # the address
    for k in range(3):
        _glyphs(draw, 20 + k * 40, 54, 1, 16, text, rng)  # back, forward, reload


def _capture(*pages: Image.Image, size: tuple[int, int] = FULL_HD, frame: int = 0, browser: str | None = "dark",
             header: bool = True, footer: bool = True, arrows: bool = True, fit: int = 12,
             at: tuple[int, int, int, int] | None = None, gutter: int = 0, gutter_level: int | None = None,
             seed: int = 1) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """A capture of a reader: browser bars (or none), the reader's frame at level *frame*, the page(s) fitted to the
    viewport's height with *fit* px above and below (or placed at *at* = x, y, page width, page height), the
    reader's header letters, footer slider and side arrows. Returns the capture and the page's (spread's) box."""
    rng = random.Random(seed)
    width, height = size
    img = Image.new("RGB", size, (frame,) * 3)
    draw = ImageDraw.Draw(img)
    top = 0
    if browser:
        _browser_bars(draw, width, browser, rng)
        top = 85
    pw0, ph0 = pages[0].size
    if at is None:
        ph = height - top - 2 * fit
        pw = int(pw0 * ph / ph0)
        total = pw * len(pages) + gutter * (len(pages) - 1)
        x0, y0 = (width - total) // 2, top + fit
    else:
        x0, y0, pw, ph = at
        total = pw * len(pages) + gutter * (len(pages) - 1)
    x = x0
    for page in pages:
        img.paste(page.resize((pw, ph), Image.LANCZOS), (x, y0))
        x += pw + gutter
    if gutter and gutter_level is not None:
        draw.rectangle((x0 + pw, y0, x0 + pw + gutter - 1, y0 + ph - 1), fill=(gutter_level,) * 3)
    if header:  # the book's title and two icons, light grey on the frame (the title runs over the page's top)
        _glyphs(draw, width // 2 - 150, top + 14, 20, 16, (200, 200, 200), rng)
        _glyphs(draw, 20, top + 12, 1, 20, (200, 200, 200), rng)
        _glyphs(draw, width - 60, top + 12, 2, 20, (200, 200, 200), rng)
    if footer:  # a page slider across the viewport (over the page's foot), its knob and the page number
        draw.rectangle((int(width * 0.05), height - 22, int(width * 0.95), height - 20), fill=(110, 110, 110))
        draw.ellipse((int(width * 0.3) - 7, height - 28, int(width * 0.3) + 7, height - 14), fill=(220, 220, 220))
        _glyphs(draw, width - 220, height - 18, 12, 12, (170, 170, 170), rng)
    if arrows:  # the reader's page-turn chevrons at the sides
        cy = (top + height) // 2
        for ax, sign in ((26, 1), (width - 26, -1)):
            draw.line((ax + sign * 12, cy - 24, ax, cy), fill=(180, 180, 180), width=4)
            draw.line((ax, cy, ax + sign * 12, cy + 24), fill=(180, 180, 180), width=4)
    return img, (x0, y0, x0 + total, y0 + ph)


def _dark_page(width: int = 620, height: int = 880, light_border: bool = True, black: int = 0,
               seed: int = 3) -> Image.Image:
    """A page that is mostly a black panel: grey art lines and white lettering on black, inside a white margin of
    4% (or none: the black reaches the page's edges)."""
    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), (255, 255, 255) if light_border else (black,) * 3)
    draw = ImageDraw.Draw(img)
    m = int(0.04 * width) if light_border else 0
    draw.rectangle((m, m, width - 1 - m, height - 1 - m), fill=(black,) * 3)
    for _ in range(40):
        draw.line((rng.uniform(m, width - m), rng.uniform(m, height - m), rng.uniform(m, width - m),
                   rng.uniform(m, height - m)), fill=(rng.randint(60, 200),) * 3, width=rng.randint(1, 3))
    for _ in range(3):
        _glyphs(draw, rng.uniform(m + 40, width - m - 80), rng.uniform(m + 40, height - m - 300), 6, 26,
                (240, 240, 240), rng, vertical=True)
    return img


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _noisy(img: Image.Image, sigma: float, seed: int = 0) -> Image.Image:
    a = np.asarray(img).astype(np.float32) + np.random.default_rng(seed).normal(0.0, sigma, (img.height, img.width, 3))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _found(img, expected, tol: int = 2, **kw) -> tuple[int, int, int, int]:
    debug: dict = {}
    box = find_page_area(img, debug=debug, **kw)
    assert box is not None, debug
    assert max(abs(a - b) for a, b in zip(box, expected)) <= tol, (box, expected, debug)
    return box


def _none(img, **kw) -> None:
    debug: dict = {}
    box = find_page_area(img, debug=debug, **kw)
    assert box is None, (box, debug)
    assert debug["result"]


# ------------------------------------------------------------------------------------------------- dark frames
def test_a_page_in_a_dark_browser_reader_leaves_out_the_browser_and_the_reader_controls(sample_page):
    img, page = _capture(sample_page)  # dark Chrome bars, black reader, header letters, slider, arrows
    box = _found(img, page, tol=0)
    assert page_area_margins(box, img.size) == (page[0], page[1], img.width - page[2], img.height - page[3])


def test_light_browser_bars_above_a_dark_reader(sample_page):
    img, page = _capture(sample_page, browser="light")
    _found(img, page, tol=0)


def test_a_spread_is_the_union_of_its_two_pages(sample_page, sample_page2):
    img, spread = _capture(sample_page2, sample_page)  # pages touching
    _found(img, spread, tol=0)
    img, spread = _capture(sample_page2, sample_page, gutter=8, gutter_level=0)  # a dark gutter
    _found(img, spread, tol=0)
    img, spread = _capture(sample_page2, sample_page, gutter=30, gutter_level=0)  # a wide one
    _found(img, spread, tol=0)
    img, spread = _capture(sample_page2, sample_page, gutter=10, gutter_level=255)  # a white one
    _found(img, spread, tol=0)


def test_a_spread_whose_page_bleeds_black_at_the_frames_level(sample_page, sample_page2):
    left = sample_page2.copy()
    ImageDraw.Draw(left).rectangle((0, 0, 1239, 700), fill=(0, 0, 0))  # its top 40% joins the frame
    img, spread = _capture(left, sample_page, gutter=8, gutter_level=0)
    _found(img, spread, tol=0)
    img, spread = _capture(_dark_page().resize(sample_page.size), sample_page)  # a black panel page beside a white one
    _found(img, spread, tol=1)
    img, spread = _capture(_dark_page(light_border=False).resize(sample_page.size), sample_page)
    box = find_page_area(img)  # no margin on the black page: its outer edge may come in a little (the limit)
    assert box is not None and box[1:] == spread[1:], (box, spread)
    assert spread[0] <= box[0] <= spread[0] + 0.03 * (spread[2] - spread[0]), (box, spread)


def test_white_pages_with_a_thin_dark_gutter_under_jpeg_noise(sample_page, sample_page2):
    img, spread = _capture(sample_page2, sample_page, gutter=4, gutter_level=0)
    _found(_jpeg(_noisy(img, 5.0), 50), spread)


def test_a_page_narrower_than_the_frame_with_dark_bars_left_and_right(sample_page):
    img, page = _capture(sample_page, browser=None, header=False, footer=False, arrows=False)
    _found(img, page, tol=0)
    for size in ((1280, 720), (3840, 2160)):
        img, page = _capture(sample_page, size=size)
        _found(img, page, tol=1)


def test_the_fake_viewers_grey_frame(sample_page):
    """tools/fake_viewer.py: a #2b2b2b canvas, the page fitted with 20 px around it, a grey page counter."""
    img, page = _capture(sample_page, size=(900, 1100), frame=0x2B, browser=None, header=False, footer=False,
                         arrows=False, fit=20)
    ImageDraw.Draw(img).text((10, 10), "page 1/3", fill=(0x88,) * 3)
    _found(img, page, tol=1)


def test_a_page_that_touches_the_capture_or_a_bar(sample_page):
    img, page = _capture(sample_page, fit=0)  # against the toolbar above, the capture's edge below
    _found(img, page, tol=0)
    img, page = _capture(sample_page, fit=0, browser="light")
    _found(img, page, tol=0)
    img, page = _capture(sample_page, fit=0, browser=None)  # the capture's top and bottom
    assert _found(img, page, tol=0)[1] == 0
    img, page = _capture(sample_page, at=(0, 97, 660, 939))  # the capture's left edge
    assert _found(img, page, tol=0)[0] == 0


@pytest.mark.parametrize("frame", [18, 26, 33, 45])
def test_a_reader_frame_about_as_grey_as_the_browsers_bars(sample_page, frame):
    """Chrome's dark tab strip and address field are #202124 (33): a frame near that level takes them in, and the
    toolbar between them is a bar inside the frame, glued to the page when the page touches it."""
    img, page = _capture(sample_page, frame=frame)
    _found(img, page, tol=0)
    img, page = _capture(sample_page, frame=frame, fit=0)
    _found(img, page, tol=0)


@pytest.mark.parametrize("bar, level, gap", [(50, 40, 0), (60, 40, 12), (100, 26, 12), (150, 40, 12), (60, 18, 12),
                                             (60, 255, 12)])
def test_the_readers_header_and_footer_bars_are_left_out(sample_page, bar, level, gap):
    """Bars across the viewport above and below the page (the reader's header with its title and buttons, the
    footer with its slider), dark grey, nearly black or white, touching the page or not; a dark-grey browser
    toolbar above them."""
    rng = random.Random(4)
    width, height = FULL_HD
    img = Image.new("RGB", FULL_HD, (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, 84), fill=(53, 54, 58))
    page = (640, 85 + bar + gap, 1240, height - bar - gap)
    img.paste(sample_page.resize((page[2] - page[0], page[3] - page[1]), Image.LANCZOS), page[:2])
    letters = (230, 230, 230) if level < 128 else (20, 20, 20)
    draw.rectangle((0, 85, width - 1, 85 + bar - 1), fill=(level,) * 3)
    _glyphs(draw, 40, 105, 30, 18, letters, rng)
    _glyphs(draw, width - 300, 105, 6, 18, letters, rng)
    draw.rectangle((0, height - bar, width - 1, height - 1), fill=(level,) * 3)
    draw.rectangle((60, height - bar // 2, width - 300, height - bar // 2 + 3), fill=(150, 150, 150))
    _glyphs(draw, width - 220, height - bar // 2 - 8, 12, 14, letters, rng)
    _found(img, page, tol=0)


def test_reader_controls_next_to_the_page_are_left_out(sample_page):
    img, page = _capture(sample_page, size=(760, 1000))  # a narrow window: the arrows and the slider near the page
    _found(img, page, tol=0)
    img, page = _capture(sample_page, at=(40, 97, 660, 939))  # the page beside the left arrow
    _found(img, page, tol=0)


def test_a_spread_filling_a_portrait_windows_width(sample_page, sample_page2):
    img, spread = _capture(sample_page2, sample_page, size=(1000, 1600), at=(0, 128, 500, 1428))
    _found(img, spread, tol=0)


def test_stacked_pages_of_a_scrolling_reader_are_one_area(sample_page):
    img = Image.new("RGB", FULL_HD, (0, 0, 0))
    page = sample_page.resize((700, 990))
    img.paste(page.crop((0, 600, 700, 990)), (618, 0))  # the foot of one page ...
    img.paste(page.crop((0, 0, 700, 640)), (618, 408))  # ... and the head of the next, a gap between
    _found(img, (618, 0, 1318, FULL_HD[1]), tol=0)


def test_robust_to_jpeg_and_noise(sample_page):
    img, page = _capture(sample_page)
    _found(_jpeg(img, 40), page)
    _found(_jpeg(_noisy(img, 6.0), 60), page)


def test_a_mostly_dark_page_does_not_vanish():
    img, page = _capture(_dark_page())  # a black panel page: its white margin gives its edges
    _found(img, page, tol=1)
    img, page = _capture(_dark_page(light_border=False, black=30))  # black a little lighter than the frame
    _found(img, page, tol=1)
    # Black at the frame's own level up to the page's edges (no margin): the brightest plausible box, inside the
    # page and most of it (the limit: the box stops where the page's lighter content starts).
    img, page = _capture(_dark_page(light_border=False))
    box = find_page_area(img)
    assert box is not None
    assert box[0] >= page[0] - 2 and box[1] >= page[1] - 2 and box[2] <= page[2] + 2 and box[3] <= page[3] + 2, box
    covered = (box[2] - box[0]) * (box[3] - box[1]) / ((page[2] - page[0]) * (page[3] - page[1]))
    assert covered >= 0.85, covered


def test_a_black_band_at_the_pages_edge_is_lost_to_the_frame(sample_page):
    """The documented limit: a black bleed at the frame's level reaching the page's top joins the frame; the rest of
    the page is found exactly."""
    page_img = sample_page.copy()
    ImageDraw.Draw(page_img).rectangle((0, 0, 1239, 300), fill=(0, 0, 0))
    img, page = _capture(page_img)
    box = find_page_area(img)
    assert box is not None
    band = page[1] + round(301 * (page[3] - page[1]) / 1754)
    assert box[0] == page[0] and box[2] == page[2] and box[3] == page[3]
    assert abs(box[1] - band) <= 2, (box, band)


# ------------------------------------------------------------------------------------------------- no page
def test_a_full_page_image_without_a_frame_gives_none(sample_page, sample_page2):
    for img in (sample_page, sample_page2, sample_page.convert("L"), np.asarray(sample_page),
                sample_page.transpose(Image.FLIP_LEFT_RIGHT), _jpeg(sample_page, 40)):
        _none(img)


def test_flat_and_featureless_images_give_none():
    for level in (0, 5, 128, 255):
        _none(Image.new("RGB", (1920, 1080), (level,) * 3))
    _none(Image.fromarray(np.random.default_rng(1).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)))
    _none(Image.new("RGB", (40, 40), (255, 255, 255)))  # too small to tell


def test_no_convincing_panel_gives_none(sample_page):
    rng = random.Random(5)
    grid = Image.new("RGB", FULL_HD, (18, 18, 18))  # a library: rows of covers with titles
    draw = ImageDraw.Draw(grid)
    for r in range(3):
        for c in range(7):
            x, y = 120 + c * 250, 140 + r * 300
            draw.rectangle((x, y, x + 200, y + 270), fill=(rng.randint(120, 250), rng.randint(120, 250), 200))
            _glyphs(draw, x + 10, y + 280, 10, 10, (200, 200, 200), rng)
    _none(grid)
    web = Image.new("RGB", FULL_HD, (24, 24, 28))  # a dark web page of text
    draw = ImageDraw.Draw(web)
    for line in range(40):
        _glyphs(draw, 300, 100 + line * 22, rng.randint(40, 110), 12, (220, 220, 220), rng)
    _none(web)


def test_min_fraction_sets_how_large_a_panel_must_be(sample_page):
    img, page = _capture(sample_page, at=(900, 400, 200, 283))  # a page of 3% of the capture
    _none(img)
    _found(img, page, tol=0, min_fraction=0.02)
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            find_page_area(img, min_fraction=bad)


# ------------------------------------------------------------------------------------------------- light frames
def test_light_theme_frames(sample_page):
    """A light frame gives the page only where the page's own paper differs from the frame by a clear step."""
    img, _page = _capture(sample_page, frame=255, browser="light")
    _none(img)  # white page on a white frame: no different from a full page without a frame
    img, page = _capture(sample_page, frame=225, browser="light")
    _found(img, page, tol=0)  # white page on a light grey frame
    img, page = _capture(sample_page, frame=128, browser=None)
    _found(img, page, tol=0)  # on a mid-grey frame
    img, page = _capture(_dark_page(light_border=False), frame=255, browser="light")
    _found(img, page, tol=1)  # a black page on a white frame
    img, page = _capture(_dark_page(), frame=255, browser="light")  # a black panel page: its white margin melts
    mx, my = round(24 * (page[2] - page[0]) / 620), round(24 * (page[3] - page[1]) / 880)  # into the frame, the box
    _found(img, (page[0] + mx, page[1] + my, page[2] - mx, page[3] - my), tol=2)  # is the panel inside it
    outlined = sample_page.copy()
    ImageDraw.Draw(outlined).rectangle((0, 0, 1239, 1753), outline=(150, 150, 150), width=3)
    img, _page = _capture(outlined, frame=255, browser="light")
    _none(img)  # a thin outline is not paper of its own


# ------------------------------------------------------------------------------------------------- the API
def test_any_image_type_gives_the_same_box(sample_page):
    img, page = _capture(sample_page)
    for variant in (img, img.convert("RGBA"), img.convert("P"), img.convert("L"), np.asarray(img),
                    np.asarray(img.convert("RGBA")), np.asarray(img.convert("L"))):
        _found(variant, page, tol=1)


def test_the_debug_dict_says_what_was_measured_and_why(sample_page):
    img, _page = _capture(sample_page)
    debug: dict = {}
    find_page_area(img, debug=debug)
    assert debug["result"] == "found" and debug["levels"][0][0] == 0
    tried = debug["tried"][0]
    assert tried["level"] == 0 and tried["tol"] >= 12 and tried["sides"]["left"] == "framed"
    debug = {}
    find_page_area(sample_page, debug=debug)
    assert "255" in debug["result"] and "paper" in debug["result"]


def test_page_area_margins_are_what_the_app_stores():
    size = (1936, 1048)
    assert page_area_margins((636, 97, 1299, 1036), size) == (636, 97, 637, 12)
    assert page_area_margins(None, size) == (0, 0, 0, 0)  # no page: the whole capture
    assert page_area_margins((0, 0, 1936, 1048), size) == (0, 0, 0, 0)
    assert page_area_margins((-5, -9, 4000, 2000), size) == (0, 0, 0, 0)  # clamped to the capture
    assert page_area_margins((1299, 1036, 636, 97), size) == (636, 97, 637, 12)  # corners in any order
    for box in ((636, 97, 1299, 1036), (0, 85, 1936, 1048), (10, 20, 30, 40)):
        margins = page_area_margins(box, size)
        assert area.margins_to_box(margins, size) == box  # the Set area dialog reads them back as the same box
        assert area.box_to_margins(box, size) == margins


def test_fast_enough_for_every_capture(sample_page):
    img, page = _capture(sample_page, size=(1920, 1080))
    arr = np.asarray(img)
    assert find_page_area(arr) == find_page_area(img)  # the first call also starts OpenCV
    for subject in (arr, img):
        times = []
        for _ in range(5):
            start = time.perf_counter()
            find_page_area(subject)
            times.append(time.perf_counter() - start)
        assert min(times) < 0.030, times
