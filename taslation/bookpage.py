"""Whether one frame of the viewer's window shows a page of a book, from the frame's layout alone - no reader, no
model, nothing kept: what a browser window the person picked is judged by before anything of its tab is read
(`ui.viewers.ViewerMixin._pick_lets`; a tab in front that is no book's - a page of text, a shop, a blank tab - is not
read, and the right pane says so).

The frame's capture area is looked at as one page (`layout`): the page on a flat ground found as the side panes find
it (`seethrough.look`: the box, the bars across it left out; the whole area where no box is found - a capture area
that is the page itself, or a window narrower than the page), brought to WORK_H rows at the most, and on a dark paper
looked at as light ink on dark. What is measured:

* the ink: the share of dark pixels (INK_LEVEL);
* the drawing: of the ink, the share in pieces that reach far (DRAWN_REACH of the page's height or width) - a page of
  text has its ink in letters and words only;
* the panels: closed frames of long straight lines (LINE_RUN of the page's width or height), or LINES_ENOUGH thin
  lines (LINE_THIN thick at the most) across and as many down;
* the lettering in bubbles: closed light regions of a bubble's size and shape (BUBBLE_AREA, BUBBLE_SHAPE) that hold
  GLYPHS_LEAST small dark pieces and nothing large - BUBBLES_LEAST of them in closed frames, BUBBLES_LINES where the
  panels are lines only;
* what a web page has and a page of a book has not: a row of GRID_ROW frames or more of one size side by side (a
  shop's cards, a shelf of covers), and colour (COLOUR_SHARE of the pixels) where no page of a page's shape is on a
  ground (`PAGE_SHAPES`) with its paper unlike the ground (PAPER_EDGE).

`judge` says "book" for a drawing in panels with lettering in bubbles and no sign of a web page; "not" for a frame
with next to no ink or with no drawing (a page of text, a document, a blank tab); "unsure" for anything else (a
splash page with no panels, a page with one bubble or none, a colour page off a ground, a shop's or a gallery's
pictures): the window waits for the next page then. Measured with tools/bookpage_eval.py on the sample set's 214
pages as a viewer shows them, the repository's made-up pages and made-up pages of no book (`docs/DEVELOPMENT.md`): no
page of no book taken for a book's, no page of a book taken for no book's; some one page of a book in eight
"unsure", one in three of a soft first picture. Some 25-30 ms a full-HD frame (100 ms at the most), on the Tk thread,
once per frame, and only while a pick is on trial."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from . import seethrough as st

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 is a dependency of the package
    cv2 = None  # type: ignore[assignment]

WORK_H = 900  # the page is looked at with so many rows at the most (some 25-30 ms a full-HD frame)
INK_LEVEL = 110  # a pixel darker than this (of 255) is ink
LINE_LEVEL = 150  # ... and one darker than this may be part of a panel's line (thin lines come out grey when scaled)
LEAST_INK = 0.004  # a page with less ink than this share is blank
SPARSE = 0.03  # ... and so is a capture area with less ink than this share, no panel and no bubble (a new tab)
DRAWN_REACH = 0.08  # a piece of ink that reaches this share of the page's height or width is drawing, not lettering
NO_DRAWING = 0.3  # with less than this share of the ink in such pieces the page is text, not drawing
DRAWING = 0.6  # ... and with this much or more it is drawing
LINE_RUN = 0.12  # a panel's line runs this share of the page's width (across) or height (down) at the least
LINE_THIN = 0.012  # ... and is this share of the page's height (or width) thick at the most (4 px at the least)
PANELS_LEAST = 2  # closed frames of such lines that make panels
LINES_ENOUGH = 4  # ... or so many lines across and so many down
BUBBLE_AREA = (0.003, 0.08)  # a bubble's light region is this share of the page's area, at the least and the most
BUBBLE_FILL = 0.45  # ... fills this share of its box at the least (an oval about 0.79, a box 1)
BUBBLE_SHAPE = (0.25, 4.0)  # ... and its box is this many times as wide as high (a button's or a quote's is wider)
GLYPH_REACH = 0.06  # a piece inside it this share of the page's height across and down at the most is a letter
GLYPHS_LEAST = 4  # ... and a bubble holds so many letters at the least, and no piece of more than
LARGEST_PIECE = 0.2  # this share of its area
BUBBLES_LEAST = 2  # bubbles with lettering that make a page with lettering
BUBBLES_LINES = 4  # ... where the panels are lines only, no closed frames (a shelf of covers has lines)
GRID_ROW = 3  # so many frames of one size side by side are a grid of a web page (cards, covers)
GRID_SLACK = (0.02, 0.05)  # ... their tops within this share of the page's height, their sizes within this share
COLOUR_SHARE = 0.06  # a page with more than this share of colourful pixels is no page of a black-and-white book
PAGE_SHAPES = ((0.55, 0.8), (1.15, 1.6))  # a page's width to its height, and a spread's
PAPER_EDGE = 0.5  # a page whose box edge is unlike the ground for this share of it is a page laid on the ground


@dataclass(frozen=True)
class Layout:
    """What one look at a frame's layout found (`layout`): the page box on a ground (whether one was found, of a
    page's shape, and the share of its edge unlike the ground), and the share of ink, of the ink in drawing, the
    panels (closed frames), the lines across and down, the most frames of one size side by side, the bubbles with
    lettering and the share of colourful pixels."""

    box: bool
    page_shaped: bool
    paper: float
    ink: float
    drawn: float
    panels: int
    across: int
    down: int
    grid: int
    bubbles: int
    colour: float
    area_ink: float = 0.0


def _pieces(mask: np.ndarray) -> np.ndarray:
    """The 8-connected pieces of *mask*: one row (left, top, width, height, area) each."""
    _n, _labels, stats, _centres = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return stats[1:]


def _part(rgb: np.ndarray, look: st.Look) -> np.ndarray:
    """The page of the frame *rgb* as it is judged: the look's page box (the whole frame without one), the rows of
    its bars left out, brought to WORK_H rows at the most."""
    height, width = rgb.shape[:2]
    top, bottom = 0, height
    for start, end in look.bands:
        if start == 0:
            top = max(top, end)
        else:
            bottom = min(bottom, start)
    left, right = 0, width
    if look.box is not None:
        left, box_top, right, box_bottom = look.box
        top, bottom = max(top, box_top), min(bottom, box_bottom)
    part = rgb[top:bottom, left:right]
    if part.shape[0] > WORK_H:
        scale = WORK_H / part.shape[0]
        part = cv2.resize(part, (max(1, round(part.shape[1] * scale)), WORK_H), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(part)


def _paper(rgb: np.ndarray, look: st.Look) -> float:
    """The share of the page box's edge (a 3 px strip inside it, bars' rows left out) unlike the ground's colour: a
    page laid on the ground has paper of its own there; a white page on white gives the box of what is drawn on it."""
    if look.box is None or look.ground is None:
        return 0.0
    left, top, right, bottom = look.box
    for start, end in look.bands:
        if start == 0:
            top = max(top, end)
        else:
            bottom = min(bottom, start)
    if bottom - top < 8 or right - left < 8:
        return 0.0
    ground = np.array(look.ground, np.int16)
    sides = (rgb[top:bottom, left:left + 3], rgb[top:bottom, right - 3:right], rgb[top:top + 3, left:right],
             rgb[bottom - 3:bottom, left:right])
    strip = np.concatenate([side.reshape(-1, 3) for side in sides])
    return float((np.abs(strip.astype(np.int16) - ground).max(axis=1) > 4 * st.GROUND_TOL).mean())


def _bubbles(grey: np.ndarray) -> int:
    """The bubbles with lettering on the page *grey* (dark ink on light): light regions not at the page's edge, of
    BUBBLE_AREA, BUBBLE_FILL and BUBBLE_SHAPE, whose holes are GLYPHS_LEAST letters at the least and none larger than
    LARGEST_PIECE of the region (a box round a picture is no bubble)."""
    height, width = grey.shape
    area = height * width
    count, labels, stats, _centres = cv2.connectedComponentsWithStats((grey > 200).astype(np.uint8), connectivity=4)
    found = 0
    for i in range(1, count):
        x, y, w, h, size = (int(v) for v in stats[i])
        if not BUBBLE_AREA[0] * area <= size <= BUBBLE_AREA[1] * area:
            continue
        if not BUBBLE_SHAPE[0] <= w / h <= BUBBLE_SHAPE[1]:
            continue
        if x == 0 or y == 0 or x + w >= width or y + h >= height:
            continue
        region = (labels[y:y + h, x:x + w] == i).astype(np.uint8)
        contours, _tree = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(region)
        cv2.drawContours(filled, contours, -1, 1, thickness=-1)
        inside = int(filled.sum())
        if inside == 0 or inside < BUBBLE_FILL * w * h:
            continue
        holes = _pieces((filled > 0) & (region == 0))
        if len(holes) == 0 or int(holes[:, 4].max()) > LARGEST_PIECE * inside:
            continue
        reach = GLYPH_REACH * height
        letters = int(((holes[:, 2] <= reach) & (holes[:, 3] <= reach) & (holes[:, 4] >= 3)).sum())
        if letters >= GLYPHS_LEAST:
            found += 1
    return found


def layout(rgb: np.ndarray) -> Layout:
    """The layout of the frame *rgb* (H, W, 3, the capture area) as `judge` weighs it (the module's text)."""
    look = st.look(rgb)
    part = _part(rgb, look)
    aspect = part.shape[1] / max(1, part.shape[0])
    shaped = look.box is not None and any(lo <= aspect <= hi for lo, hi in PAGE_SHAPES)
    paper = _paper(rgb, look)
    if part.shape[0] < 20 or part.shape[1] < 20:
        return Layout(look.box is not None, shaped, paper, 0.0, 0.0, 0, 0, 0, 0, 0, 0.0)
    grey = cv2.cvtColor(part, cv2.COLOR_RGB2GRAY)
    dark_paper = float(np.median(grey)) < 128
    if dark_paper:
        grey = 255 - grey  # (a dark paper: light ink on it)
    height, width = grey.shape
    ink = grey < INK_LEVEL
    ink_share = float(ink.mean())
    pieces = _pieces(ink)
    far = (pieces[:, 3] >= DRAWN_REACH * height) | (pieces[:, 2] >= DRAWN_REACH * width) if len(pieces) else []
    drawn = float(pieces[far, 4].sum()) / max(1, int(ink.sum())) if len(pieces) else 0.0
    # the panels' lines: runs of LINE_RUN kept by an opening, thin ones counted, closed frames of them
    lines = (grey < LINE_LEVEL).astype(np.uint8)
    run_across, run_down = max(8, int(LINE_RUN * width)), max(8, int(LINE_RUN * height))
    across = cv2.morphologyEx(lines, cv2.MORPH_OPEN, np.ones((1, run_across), np.uint8))
    down = cv2.morphologyEx(lines, cv2.MORPH_OPEN, np.ones((run_down, 1), np.uint8))
    thin_across, thin_down = max(4, int(LINE_THIN * height)), max(4, int(LINE_THIN * width))
    rows, columns = _pieces(across), _pieces(down)
    n_across = int((rows[:, 3] <= thin_across).sum()) if len(rows) else 0
    n_down = int((columns[:, 2] <= thin_down).sum()) if len(columns) else 0
    frames = [f for f in _pieces(cv2.bitwise_or(across, down)) if f[2] >= run_across and f[3] >= run_down]
    grid = 0
    for f in frames:  # (frames of one size side by side)
        alike = sum(1 for g in frames if abs(int(g[1]) - int(f[1])) <= GRID_SLACK[0] * height
                    and abs(int(g[2]) - int(f[2])) <= GRID_SLACK[1] * f[2]
                    and abs(int(g[3]) - int(f[3])) <= GRID_SLACK[1] * f[3])
        grid = max(grid, alike)
    hsv = cv2.cvtColor(part, cv2.COLOR_RGB2HSV)
    colour = float(((hsv[..., 1] > 90) & (hsv[..., 2] > 60)).mean())
    whole = cv2.cvtColor(np.ascontiguousarray(rgb[::4, ::4]), cv2.COLOR_RGB2GRAY)
    if dark_paper:
        whole = 255 - whole
    return Layout(look.box is not None, shaped, paper, ink_share, drawn, len(frames), n_across, n_down, grid,
                  _bubbles(grey), colour, float((whole < INK_LEVEL).mean()))


def verdict(found: Layout) -> str:
    """"book", "not" or "unsure" for the layout *found* (the module's text)."""
    if found.ink < LEAST_INK or found.drawn < NO_DRAWING:
        return "not"
    framed = found.panels >= PANELS_LEAST
    lined = found.across >= LINES_ENOUGH and found.down >= LINES_ENOUGH
    if found.area_ink < SPARSE and not found.bubbles and not (framed or lined):
        return "not"
    laid = found.page_shaped and found.paper >= PAPER_EDGE
    web = found.grid >= GRID_ROW or (found.colour >= COLOUR_SHARE and not laid)
    lettered = found.bubbles >= (BUBBLES_LEAST if framed else BUBBLES_LINES)
    if found.drawn >= DRAWING and (framed or lined) and lettered and not web:
        return "book"
    return "unsure"


def judge(rgb: np.ndarray) -> str:
    """Whether the frame *rgb* (H, W, 3, the capture area) shows a page of a book: "book", "not" or "unsure"."""
    if cv2 is None:  # pragma: no cover - cv2 is a dependency of the package
        return "unsure"
    return verdict(layout(rgb))


def digest(rgb: np.ndarray) -> bytes:
    """A short digest of the frame *rgb* (every eighth pixel across and down): a frame judged once is not judged
    again."""
    return hashlib.blake2b(np.ascontiguousarray(rgb[::8, ::8]).tobytes(), digest_size=12).digest()
