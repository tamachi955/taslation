"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: a book's first five screens, made up, as a browser-based reader shows
them in a maximised window (1920 x 1032 at 100 %, the browser's own bar in the client area's first BAR_ROWS rows):

1. the cover, a single colour page in the middle (flat colour areas, large outlined lettering, a bubble);
2. a dark colour page with a bubble beside a page as black as the viewer's ground holding a small plate of lettering;
3. a spread of colour pictures to the pages' edges with a bubble, the right page a column of six squares of one size,
   each with a round badge and lines of small lettering beside it;
4. a greyscale page with panels and a bubble beside a black page holding a small colour picture;
5. a greyscale spread running off the window's foot, a bubble cut by the content's top (the browser's bar over all
   above it), one of its two columns of lettering cut with it.

Shared by tests/test_see_book_walk.py (the side panes, the page box, the fifth screen read and shown),
tests/test_bookpage.py and tools/bookpage_eval.py (whether each screen is judged a page of a book), and
tools/standin_e2e.py's scenario bw (`pages`: the screens' pages, shown by the stand-in viewer one screen after the
other). A harder cover beside them, not one of the five (`hard_cover`: a saturated picture, six pieces of large
outlined lettering in several colours, a bubble), is the page budget's (tests/test_page_budget.py). Flat colour areas
and made-up lettering: *lettering* "strokes" draws glyphs of strokes (no font needed, the same on every computer: the
tests'), "font" made-up Japanese lines in a Japanese font (`make_sample_page.LINES_A`: lettering a reader reads, for
the stand-in). No real page, no book's line; nothing is written but by `write_pages` and `main`, into the folder
given.

    python tools/book_screens.py --out DIR [--lettering font]   # the five screens, the pages and the hard cover
"""

from __future__ import annotations

import argparse
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1032  # a maximised window's client area at 100 %
BAR_ROWS = 88  # rows 0-87: the browser's tab strip and address bar, in the client area
CONTENT_TOP = 87  # the pages' first row on the screens (the bar's last row, where a page is drawn over it)
SPREAD = (294, 1626)  # the pages' columns on the screen (a spread of two pages 666 px wide)
GUTTER = 960  # where a spread's two pages meet
HAND = (296, 85, 292, 0)  # margins of a capture area set by hand about the spread (its top 3 px over the bar's foot)
BARS_ONLY = (0, 85, 0, 0)  # margins of one that trims only the browser's bar
CUT_COLUMN = (1500, 1526)  # (`grey_spread`) the columns of the bubble's lettering the content's top cuts
PLATE = (1313, 805, 1591, 996)  # (`dark_and_black`) the plate on the black page, on the screen
COVER = (629, 88, 1291, 1030)  # (`cover`) the cover on the screen
LETTERINGS = ("strokes", "font")
GLYPH = 26  # a made-up glyph's size (px), and a font's
# the made-up lines the font draws, a different one at each place (`make_sample_page`'s: lines of no book)
FONT_LINES = ("こんにちは", "ありがとう", "どこへ行くの", "大丈夫だよ", "急いで", "気をつけて", "やっぱりそうか",
              "ここで待ってて")


def blank() -> np.ndarray:
    out = np.zeros((H, W, 3), np.uint8)  # the viewer's black ground
    out[:BAR_ROWS] = (222, 225, 230)
    out[44:76, 200:1400] = 255  # (an address bar)
    return out


def blocks(out, x0, y0, n, w, h, gap, colour, outline=None):
    """*n* blocks for lettering in a row (with an *outline* round each: large decorative lettering)."""
    for i in range(n):
        x = x0 + i * (w + gap)
        if outline is not None:
            out[y0 - 4:y0 + h + 4, x - 4:x + w + 4] = outline
        out[y0:y0 + h, x:x + w] = colour


def disc(out, cx, cy, r, colour):
    ys, xs = np.ogrid[:H, :W]
    out[(ys - cy) ** 2 + (xs - cx) ** 2 <= r * r] = colour


def oval(out, cx, cy, rx, ry, line):
    """A bubble: white inside an outline *line* px wide."""
    ys, xs = np.ogrid[:H, :W]
    out[((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1] = 0
    out[((xs - cx) / (rx - line)) ** 2 + ((ys - cy) / (ry - line)) ** 2 <= 1] = 255


def glyphs(out, x, y, n, seed, size=GLYPH):
    """*n* made-up glyphs in a column from (*x*, *y*): strokes whose lengths change from glyph to glyph (lettering,
    not a tone of equal dots)."""
    for k in range(n):
        top, v = y + k * (size + 6), (seed + k * 7) % 5
        out[top + 2:top + 5, x + 2 + v:x + size - 2] = 20
        out[top + 2 + v:top + size - 2, x + size // 2 - 2:x + size // 2 + 1] = 20
        out[top + size - 8:top + size - 5, x + 4:x + size - 4 - 2 * v] = 20
        if (seed + k) % 2:
            out[top + 9:top + 13, x + 5:x + 11] = 20
        else:
            out[top + 8:top + 18, x + size - 7:x + size - 4] = 20


@lru_cache(maxsize=None)
def _font(size: int):
    """A Japanese font for the "font" lettering: the system's (`make_sample_page.JP_FONT_CANDIDATES`), else the Noto
    Sans JP setup_models.py puts into the models folder (TASLATION_MODELS_DIR, or models/ in the repository); with
    neither, SystemExit."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_sample_page as msp

    models = Path(os.environ.get("TASLATION_MODELS_DIR") or Path(__file__).resolve().parents[1] / "models")
    for path in (*msp.JP_FONT_CANDIDATES, models / "fonts" / "NotoSansJP[wght].ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(str(path), size)
    raise SystemExit("no Japanese font found (none of the system's, no models/fonts/NotoSansJP[wght].ttf)")


def column(out, x, y, n, seed, lettering, colour=(20, 20, 20), size=GLYPH):
    """A column of *n* characters of lettering from (*x*, *y*), *size* px each (`glyphs` for "strokes"; for "font"
    the first *n* characters of a made-up line, *seed* choosing it, drawn into *out* in *colour*)."""
    if lettering == "strokes":
        glyphs(out, x, y, n, seed, size)
        return
    text = (FONT_LINES[seed % len(FONT_LINES)] * 2)[:n]
    picture = Image.fromarray(out)
    draw = ImageDraw.Draw(picture)
    face = _font(size)
    for k, ch in enumerate(text):
        box = draw.textbbox((0, 0), ch, font=face)
        draw.text((x + (size - (box[2] - box[0])) / 2 - box[0], y + k * (size + 6) - box[1]), ch, font=face,
                  fill=colour)
    out[:] = np.asarray(picture)


def row(out, x, y, n, seed, lettering, colour, size):
    """A row of *n* characters of lettering from (*x*, *y*) (`blocks` for "strokes")."""
    if lettering == "strokes":
        blocks(out, x, y, n, size, size * 20 // 11, size * 4 // 11, colour)
        return
    text = (FONT_LINES[seed % len(FONT_LINES)] * 2)[:n]
    picture = Image.fromarray(out)
    ImageDraw.Draw(picture).text((x, y), text, font=_font(size), fill=colour)
    out[:] = np.asarray(picture)


def bubble(out, cx, cy, rx, ry, columns, n, seed, lettering):
    """A white bubble with *columns* columns of *n* characters each, right to left, in its middle."""
    oval(out, cx, cy, rx, ry, 4)
    step = GLYPH + 6
    right = cx + (columns * step) // 2 - step
    top = cy - (n * step) // 2
    for k in range(columns):
        column(out, right - k * step, top, n, seed + k, lettering)


def cover(lettering: str = "strokes") -> np.ndarray:
    """A single colour page in the middle (629..1291 x 88..1030): flat colour areas, large outlined lettering, a
    bubble."""
    out = blank()
    x0, y0, x1, y1 = COVER
    out[y0:y1, x0:x1] = (90, 160, 230)
    out[y0 + 380:y0 + 700, x0:x1] = (200, 40, 50)
    out[y0 + 700:y1, x0:x1] = (240, 200, 40)
    blocks(out, x0 + 60, y0 + 90, 6, 70, 110, 22, (20, 20, 60), outline=(255, 255, 255))
    bubble(out, 1120, 640, 80, 120, 2, 3, 1, lettering)
    return out


def dark_and_black(lettering: str = "strokes") -> np.ndarray:
    """A dark colour page with a bubble (294..960, the full height) beside a page as black as the ground holding a
    small plate (`PLATE`) of lettering."""
    out = blank()
    out[87:1032, 294:960] = (50, 30, 80)
    out[300:700, 400:800] = (90, 60, 140)
    disc(out, 620, 820, 120, (140, 90, 60))
    bubble(out, 470, 195, 80, 95, 2, 4, 3, lettering)
    x0, y0, x1, y1 = PLATE
    out[y0:y1, x0:x1] = (200, 160, 60)
    out[y0 + 10:y1 - 10, x0 + 10:x1 - 10] = (40, 30, 20)
    row(out, 1340, 860, 4, 5, lettering, (220, 180, 70), 44)
    return out


def colour_spread(lettering: str = "strokes") -> np.ndarray:
    """A spread of colour pictures to the pages' edges, no gutter, a bubble on the left one; on the right one a column
    of six squares of one size, each with a round badge and lines of small lettering beside it, a plate at its top
    left."""
    out = blank()
    for i, colour in enumerate([(255, 120, 40), (40, 200, 120), (250, 230, 60), (60, 120, 240)]):
        out[87 + i * 236:87 + (i + 1) * 236, 294:960] = colour
    blocks(out, 340, 160, 5, 80, 120, 30, (250, 250, 250), outline=(10, 10, 10))
    bubble(out, 780, 700, 80, 120, 2, 3, 2, lettering)
    out[87:1032, 960:1626] = (30, 20, 50)
    out[110:180, 975:1200] = (200, 170, 90)
    for k in range(6):
        y = 303 + 119 * k
        out[y:y + 108, 983:1091] = [(180, 90, 90), (90, 180, 90), (90, 90, 180), (180, 180, 90), (90, 180, 180),
                                    (180, 90, 180)][k]
        disc(out, 1091, y + 100, 14, (240, 240, 240))
        for line in range(3):
            out[y + 20 + line * 22:y + 32 + line * 22, 1110:1300 - line * 40] = (230, 200, 120)
    return out


def grey_and_picture(lettering: str = "strokes") -> np.ndarray:
    """A greyscale page with panels and a bubble (294..960) beside a black page holding a small colour picture."""
    out = blank()
    out[87:1032, 294:960] = 245
    out[100:400, 310:944] = 128
    out[104:396, 314:940] = 200
    out[420:1020, 310:620] = 90
    out[420:1020, 640:944] = 180
    disc(out, 800, 250, 70, (255, 255, 255))
    for k in range(2):
        column(out, 805 - k * 32, 205, 3, 4 + k, lettering)
    out[570:1007, 1291:1599] = (160, 110, 70)
    out[620:900, 1340:1550] = (60, 140, 200)
    return out


def grey_spread(lettering: str = "strokes") -> np.ndarray:
    """A greyscale spread (294..915 | 960..1626, a white gutter) running off the window's foot, a bubble cut by the
    content's top - the browser's bar over all above it -, one of its two columns of lettering cut with it, and a
    round bubble low on the left page."""
    out = blank()
    out[CONTENT_TOP:BAR_ROWS] = 0  # (the content from that row on, the viewer's ground beside the page too)
    out[CONTENT_TOP:1032, 294:1626] = 250
    for x0, x1 in ((294, 915), (960, 1626)):
        out[110:500, x0 + 16:x1 - 16] = 30
        out[114:496, x0 + 20:x1 - 20] = 210
        out[520:1032, x0 + 16:x1 - 16] = 30
        out[524:1032, x0 + 20:x1 - 20] = 150
    oval(out, 1490, 130, 85, 120, 5)
    column(out, CUT_COLUMN[0], 70, 5, 1, lettering)
    column(out, 1462, 95, 4, 2, lettering)
    disc(out, 400, 700, 60, (255, 255, 255))
    for k in range(2):
        column(out, 404 - k * 32, 655, 3, 6 + k, lettering)
    out[:CONTENT_TOP] = blank()[:CONTENT_TOP]  # (the bar over the page and the bubble above the content's top)
    return out


def picture(w: int, h: int, seed: int = 3) -> np.ndarray:
    """A saturated made-up picture *w* x *h*: waves of colour with discs, strokes and polygons in strong colours over
    them, outlined in black, softened a little and with a little noise (a colour cover's drawing, no real one)."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[:h, :w].astype(np.float32)
    waves = np.stack([128 + 120 * np.sin(xs / 97 + ys / 211), 128 + 120 * np.sin(ys / 73 - xs / 150 + 1),
                      128 + 120 * np.cos((xs + ys) / 120)], axis=-1)
    img = Image.fromarray(np.clip(waves, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for _ in range(60):
        colour = tuple(int(v) for v in rng.integers(0, 256, 3))
        x, y, r = int(rng.integers(0, w)), int(rng.integers(0, h)), int(rng.integers(10, 90))
        kind = int(rng.integers(0, 3))
        if kind == 0:
            draw.ellipse((x - r, y - r, x + r, y + r), fill=colour, outline=(20, 20, 20), width=3)
        elif kind == 1:
            draw.line((x, y, x + int(rng.integers(-300, 300)), y + int(rng.integers(-300, 300))), fill=colour,
                      width=r // 6 + 2)
        else:
            draw.polygon([(x + int(rng.integers(-r, r)), y + int(rng.integers(-r, r))) for _ in range(5)],
                         fill=colour, outline=(10, 10, 10))
    soft = np.asarray(img.filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32)
    return np.clip(soft + rng.normal(0, 9, (h, w, 3)), 0, 255).astype(np.uint8)


def outlined(out, x, y, n, seed, lettering, size, fill, stroke, width, down=False):
    """*n* characters of large lettering from (*x*, *y*), *size* px each, in *fill* with an outline *width* px wide in
    *stroke*, across or *down* (for "strokes" `glyphs` drawn at *size*, for "font" a made-up line)."""
    h, w = out.shape[:2]
    ink = np.zeros((h, w), bool)
    step = size + size // 10
    text = (FONT_LINES[seed % len(FONT_LINES)] * 2)[:n]
    for k in range(n):
        cx, cy = (x, y + k * step) if down else (x + k * step, y)
        if lettering == "strokes":
            small = np.full((GLYPH + 6, GLYPH + 6, 3), 255, np.uint8)
            glyphs(small, 0, 0, 1, seed + k)
            mark = _nearest(small[..., 0] < 128, size)
        else:
            canvas = Image.new("L", (size + 8, size + 8), 0)
            ImageDraw.Draw(canvas).text((4, 4), text[k], font=_font(size), fill=255)
            mark = np.asarray(canvas)[:size, :size] > 128  # (the measures of 2026-11-28 were taken on this drawing)
        mh, mw = min(mark.shape[0], h - cy), min(mark.shape[1], w - cx)
        if mh > 0 and mw > 0:
            ink[cy:cy + mh, cx:cx + mw] |= mark[:mh, :mw]
    ring = np.asarray(Image.fromarray(ink.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * width + 1))) > 0
    out[ring & ~ink] = stroke
    out[ink] = fill


def _nearest(mask: np.ndarray, size: int) -> np.ndarray:
    """*mask* (bool) scaled to *size* x *size*, nearest neighbour."""
    ys = (np.arange(size) * mask.shape[0] / size).astype(int)
    xs = (np.arange(size) * mask.shape[1] / size).astype(int)
    return mask[ys][:, xs]


def hard_cover(lettering: str = "strokes") -> np.ndarray:
    """A colour cover harder than `cover`, in the same place (`COVER`): a saturated picture to the page's edges
    (`picture`), large outlined lettering in several colours, across and in columns - six pieces of 150 to 400 px -,
    and a small bubble of body lettering. Not one of the walk's screens (`SCREENS`): the page budget's tests and
    measures (tests/test_page_budget.py) take it."""
    out = blank()
    x0, y0, x1, y1 = COVER
    out[y0:y1, x0:x1] = picture(x1 - x0, y1 - y0)
    for (dx, dy, n, size, fill, stroke, width, down), seed in zip((
            (40, 40, 4, 84, (230, 30, 40), (255, 255, 255), 8, False),  # ~ 370 x 84
            (60, 170, 5, 64, (255, 230, 40), (20, 20, 120), 6, False),  # ~ 350 x 64
            (560, 280, 4, 90, (255, 255, 255), (200, 20, 160), 9, True),  # 90 x ~ 390
            (440, 330, 4, 70, (40, 220, 255), (0, 0, 0), 7, True),  # 70 x ~ 300
            (60, 760, 5, 58, (255, 140, 0), (255, 255, 255), 6, False),  # ~ 315 x 58
            (80, 870, 4, 40, (250, 250, 250), (30, 30, 30), 4, False)), range(6, 12)):  # ~ 175 x 40
        outlined(out, x0 + dx, y0 + dy, n, seed, lettering, size, fill, stroke, width, down)
    bubble(out, 1120, 640, 70, 100, 2, 3, 0, lettering)
    return out


# the screens, and the page box the look finds in each with no area set by hand or one that trims only the bar
# (to LOOK_STEP: on every fourth pixel); the plate and the small picture on the black pages are the page's edge there
SCREENS: list[tuple[str, Callable[..., np.ndarray], tuple[int, int]]] = [
    ("cover", cover, (632, 1292)), ("dark page and black page", dark_and_black, (296, 1592)),
    ("colour spread", colour_spread, (296, 1628)), ("grey page and black page", grey_and_picture, (296, 1600)),
    ("grey spread", grey_spread, (296, 1628))]


def pages(lettering: str = "font") -> list[Image.Image]:
    """The screens' pages in reading order, as a viewer that draws them fitted to its height shows them one screen
    after the other (the stand-in viewer, `standin_e2e`'s scenario bw): the cover alone, then each spread's right
    page and its left one, cut from the screens from the content's top (the fifth's bubble cut by the page's top as
    by the content's)."""
    out = [Image.fromarray(cover(lettering)[COVER[1]:COVER[3], COVER[0]:COVER[2]])]
    for _name, make, _columns in SCREENS[1:]:
        screen = make(lettering)
        out.append(Image.fromarray(screen[CONTENT_TOP:H, GUTTER:SPREAD[1]]))
        out.append(Image.fromarray(screen[CONTENT_TOP:H, SPREAD[0]:GUTTER]))
    return out


def write_pages(folder: Path, lettering: str = "font") -> list[Path]:
    """`pages` written as PNG into *folder* (made if it is not there): their paths, in reading order."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, page in enumerate(pages(lettering)):
        path = folder / f"screen-page-{k:02d}.png"
        page.save(path)
        paths.append(path)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="the folder the PNGs go into")
    ap.add_argument("--lettering", choices=LETTERINGS, default="strokes")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for k, (_name, make, _columns) in enumerate(SCREENS):
        Image.fromarray(make(args.lettering)).save(args.out / f"screen-{k + 1}.png")
    write_pages(args.out, args.lettering)
    Image.fromarray(hard_cover(args.lettering)).save(args.out / "hard-cover.png")
    print(f"the five screens, their pages and the hard cover in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
