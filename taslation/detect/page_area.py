"""Where the page is in a capture of a reader window: the page panel inside the reader's frame.

A reader that is a browser tab (a browser-based viewer in Chrome, dark theme) is captured with the tab strip, the
address bar, the reader's header and side arrows around the page: the manga page is one bright rectangle (two side
by side for a spread) in a dark surround. Read as it is, the capture gives the browser's lettering to the detector as
"bubbles" and the translated page shows the whole browser. find_page_area finds the page so that only it is read.

How it is found, on a copy whose long side is 640 px, then refined at full resolution:

* The frame's level is measured, not assumed: the commonest grey levels of the capture's border, dark ones first
  (a black reader under a dark-grey browser bar gives two). Each is tried; when the boxes found nest (dark bars
  around the reader's own black frame), the innermost is the page. The tolerance follows the border's own noise,
  at least 12 grey levels.
* The frame is every pixel at that level connected to the border (4-connected), so black lettering and black art
  enclosed by the paper stay page. The viewport is the frame's bounding box: browser bars outside the dark frame
  (a light tab strip and toolbar) are not looked at.
* The page is the largest content component inside the viewport. Pieces of about the same extent beside it across a
  thin gap join it (the two pages of a spread with a dark gutter, a page cut by a black band). The box is tightened
  by the page's own components: an outer column or row with little content next to the page's dense ones goes (an
  arrow or a slider line touching the page), one whose content spans it stays (a sparse dark page keeps its edges),
  and rows where the viewport on both sides is a bar rather than frame are cut off (a toolbar glued to the page).
* It must convince: at least *min_fraction* of the capture, page-shaped (aspect 1:4 to 4:1), frame on two opposite
  sides, little content anywhere else in the viewport (a library grid or a web page has plenty; bars spanning the
  viewport, such as a toolbar or the reader's header and slider, do not count), on a dark frame some light content
  (paper, lettering), on a light or grey frame a paper step inside every framed side (the page's own paper at a
  level clearly off the frame's).
* A page that is itself mostly dark, whose black reaches its edges at the frame's level, may give only part of it
  as a box: when that box's surroundings are crowded with the page's own pieces, the content (bars left out) is
  closed with a kernel of 4% of the viewport and the closed box is taken when it grows the first one: the brightest
  plausible box.
* Every side is refined at full resolution: from the coarse edge, the nearest change between frame and page; a page
  that touches a bar ends where the frame beside it starts.

How the app is meant to use it: call it on the whole capture of the viewer window, before any margins, while the
user has set no area for that viewer. A manual area (the Set area dialog) is the outer bound, not the end of the
story: call it on the capture cropped to that area as well (an area that trims only a browser's tabs and address
bar still holds the reader's own header, links and page slider); a panel found there, inside the area and at least
min_fraction of it, gives the capture area as what the two have in common, the manual area alone applying while
none is found, and an area drawn tightly around the page (the panel found is the area within a few pixels) is
left as it is. Clearing the manual area goes back to the panel found on the whole capture. page_area_margins turns
the box into the (left, top, right, bottom) margins the app stores per viewer. Margins are pixels, so detect again
whenever the capture size changes (window resized or maximised, display scale changed). Once per viewer is enough
for a reader that shows every page alike, but a reader that shows the cover alone and the rest as spreads gives a
narrower box on the cover: keep, per viewer and capture size (and manual area), the union of the boxes found (a
spread then widens the area, and a box that came out too small on one page is mended by the next; the union never
cuts what one of the captures showed as page). None means "no frame found": leave the area as it is (the whole
capture, or the manual area, when nothing was found yet). A 1920x1080 capture takes about 8 ms as a numpy array and
12 ms as a PIL image (the first call in a process some 10 ms more, while OpenCV starts), so running it on every
capture is affordable.

What the window and a whole-book run share of that use is here: `panel_inside` (the panel inside a hand-set area,
`TIGHT_PX`), `joined` (the union of the boxes found), `area_margins` (the capture area the boxes found give, within
the hand-set area when there is one), `page_panel` (a frame's panel as the capture area takes it in) and
`JoinedArea`, the capture area of a whole-book run that follows the reader: it widens with the page panel of every
page the run takes, before the run reads that page, and never narrows (`batch.BatchReader`).

Known limits (pixels alone cannot tell these apart):

* A page whose own edge is solid black at the frame's level (a bleed at the page's edge, a black page without a
  light margin): the box stops where the page's lighter content starts and can be smaller than the page; a black
  band at the page's top or bottom is left out. A page of scattered small pieces only (stars on black) gives None.
* A capture without any frame of a page whose black areas reach two opposite edges of the capture (a flashback page
  with black margins) looks like a page in a dark frame: the box is then the page's light part. The union of boxes
  over several pages (above) mends it.
* A light frame: a white page on a white frame gives None (it looks exactly like a full-page capture without a
  frame); a page is found only where its paper differs from the frame by a clear step (more than 18 grey levels
  on a clean capture), so a dark page whose white margin melts into a white frame gives the box inside that margin.
* A dialog or panel larger than the page (an end-of-book panel), a library grid with a row of large covers: None or
  a wrong box. Call it on a capture that shows a page.
* Axis-aligned pages only (no rotation, no perspective).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..regions import Box

Margins = tuple[int, int, int, int]  # left, top, right, bottom pixels of the capture left out
Size = tuple[int, int]  # width, height of a capture
TIGHT_PX = 6  # a page panel found within this many px of every side of a hand-set area is that area itself

WORK = 640  # px: long side of the working copy
BORDER = 3  # px of the working copy's edge in which the frame is looked for (a 1-2 px window line is passed over)
BAND = 2  # px just outside a side that must be frame for the side to be framed
EDGE = 1  # px: a side this near the capture's edge is at the edge
PEAK = 6  # grey levels on either side of a histogram level counted with it
DARK_FRAME = 100  # a frame at or below this level is a dark theme's
MIN_DARK_SHARE = 0.15  # a dark level must hold this share of the border to be the frame's
MIN_SHARE = 0.30  # another level must hold this share
MIN_TOL = 12  # grey levels a frame pixel may differ from the frame's level (more on a noisy capture)
MIN_FRAME_PIECE = 0.002  # of the working copy: a smaller border-connected piece at the level is not frame
MIN_FRAME = 0.04  # of the working copy: less frame than this is no frame
MIN_PIECE = 0.01  # of the viewport: a smaller content component is not a piece of a page
JOIN = 0.1  # a piece joins the page when it is at least this share of the largest piece ...
ALIGN = 0.8  # ... overlaps it on one axis by this share of the shorter extent ...
LONGER = 1.5  # ... the longer of the two extents being at most this many times the shorter ...
GAP = 0.06  # ... and the gap between them is at most this share of their joint extent
MAX_PIECES = 4  # a page, or a spread, is made of at most this many pieces
SHRINK = 0.9  # a row or column this much frame is not page ...
DENSE = 0.25  # ... nor one with less content than this share of the box's dense ones (its 90th percentile) ...
SPREAD, MIN_COVER = 0.6, 0.01  # ... unless its content (this much) is in its middle third and spans this much
FRAMED = 0.85  # share of frame just outside a side for the side to be framed
BAR = 0.5  # a row beside the page with less frame than this is a bar, not page
MAX_BAR = 0.25  # of the box: at most this much is cut off as bars
DOMINANCE = 0.3  # content outside the page may be at most this share of the content inside it
RING = 0.08  # of the box's shorter side: the ring around it looked at for crowding content
RING_BUSY = 0.05  # content in that ring above this share: a dark page's own pieces, try the closed mask
BAR_SPAN = 0.9  # of the viewport's width or height: content this long is a bar, never a page's piece
CLOSE = 0.04  # of the viewport's shorter side: the closing kernel for a dark page ...
GROWN = 0.25  # ... whose closed box must hold a piece found without closing of at least this share of its area
PAPER = 0.02  # of the box: depth of the band inside a side where a light frame's page must show its paper
MIN_ASPECT, MAX_ASPECT = 0.25, 4.0
LIGHT, MIN_LIGHT = 64, 0.01  # on a dark frame a page holds this share of pixels this much above the frame's level


def find_page_area(image: Image.Image | np.ndarray, *, min_fraction: float = 0.15,
                   debug: dict | None = None) -> Box | None:
    """The page panel's bounding box (x0, y0, x1, y1; x1 and y1 exclusive, image coordinates) when *image* is a
    reader frame around a page (or a spread: the union of both pages), or None when it looks like a full page
    already (no frame) or no convincing panel exists. The panel must cover at least *min_fraction* of the image.

    *image* is a PIL image or an RGB, RGBA or grey uint8 numpy array. *debug*, when given, receives the levels tried,
    for each the frame's level and tolerance, the viewport, the boxes and side states (working copy coordinates),
    and why the level gave no box ("result").
    """
    if not 0.0 < min_fraction < 1.0:
        raise ValueError("min_fraction must be between 0 and 1")
    dbg = debug if debug is not None else {}
    dbg["tried"] = []
    gray = _gray(image)
    height, width = gray.shape
    if height < 48 or width < 48:
        dbg["result"] = "too small an image"
        return None
    scale = min(1.0, WORK / max(height, width))
    if scale < 1.0:
        small = cv2.resize(gray, (max(1, round(width * scale)), max(1, round(height * scale))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = gray
    sx, sy = width / small.shape[1], height / small.shape[0]
    levels = _frame_levels(small)
    dbg["levels"] = levels
    if not levels:
        dbg["result"] = "no uniform surround"
        return None
    boxes: list[Box] = []
    for level, tol in levels:
        info: dict = {"level": level, "tol": tol}
        dbg["tried"].append(info)
        found = _find(small, level, tol, min_fraction, info)
        if found is None:
            continue
        box, sides, viewport = found
        refined = _refine(gray, box, sides, viewport, level, sx, sy)
        info["refined"] = refined
        x0, y0, x1, y1 = refined
        if (x1 - x0) * (y1 - y0) < min_fraction * width * height:
            info["result"] = "too small after refining"
            continue
        info["result"] = "found"
        boxes.append(refined)
    if not boxes:
        dbg["result"] = "; ".join(f"{t['level']}: {t.get('result', '')}" for t in dbg["tried"])
        return None
    # A frame inside a frame (dark bars around the reader's own black frame) gives nested boxes: the page is the
    # innermost one. Boxes that do not nest: the first level's (the border's commonest dark level).
    slack = max(sx, sy) * 2
    inner = [b for b in boxes if all(_within(b, o, slack) for o in boxes)]
    dbg["result"] = "found"
    return min(inner, key=_area) if inner else boxes[0]


def page_area_margins(box: Box | None, size: tuple[int, int]) -> Margins:
    """The (left, top, right, bottom) margins that leave *box* of a capture of *size* (width, height): what the app
    stores per viewer. The box is clamped to the capture; None (no page found) gives (0, 0, 0, 0), the whole
    capture."""
    width, height = size
    if box is None:
        return (0, 0, 0, 0)
    xa, xb = sorted((min(max(int(box[0]), 0), width), min(max(int(box[2]), 0), width)))
    ya, yb = sorted((min(max(int(box[1]), 0), height), min(max(int(box[3]), 0), height)))
    return (xa, ya, width - xb, height - yb)


# ---------------------------------------------------------------------------------------------------- the area read
def margins_box(margins: Any, size: Size) -> Box:
    """The part of a capture of *size* that *margins* (left, top, right, bottom) leave, as the pipeline reads it (at
    least one pixel)."""
    width, height = size
    left, top, right, bottom = (max(0, int(m)) for m in margins)
    x0, y0 = min(left, width - 1), min(top, height - 1)
    return (x0, y0, max(x0 + 1, width - right), max(y0 + 1, height - bottom))


def _found_inside(image: Image.Image, box: Box) -> tuple[Box | None, bool]:
    """`find_page_area` on the part *box* of *image* alone: the panel found, in *image*'s pixels (None: none), and
    whether it is *box* itself within TIGHT_PX on every side."""
    x0, y0, x1, y1 = (int(v) for v in box)
    try:
        found = find_page_area(image.crop((x0, y0, x1, y1)))
    except Exception:  # noqa: BLE001 - a frame the finder cannot take: the area alone
        return None, False
    if found is None:
        return None, False
    inner = (x0 + int(found[0]), y0 + int(found[1]), x0 + int(found[2]), y0 + int(found[3]))
    return inner, all(abs(a - b) <= TIGHT_PX for a, b in zip(inner, (x0, y0, x1, y1)))


def panel_inside(image: Image.Image, box: Box) -> Box | None:
    """The page panel inside the part *box* of *image* - a capture area the reader set by hand -, in *image*'s
    pixels: `find_page_area` on that part alone (a panel of at least 15 % of it, as on a whole capture). None when it
    finds none, or when the panel is the area itself within TIGHT_PX on every side (an area drawn tightly around
    the page is read as it is)."""
    inner, tight = _found_inside(image, box)
    return None if tight else inner


def joined(box: Box | None, found: Any) -> Box | None:
    """*box* widened to take in *found* (a page panel found in a frame; either may be None)."""
    if found is None:
        return box
    if box is None:
        return tuple(int(v) for v in found)  # type: ignore[return-value]
    return (min(box[0], found[0]), min(box[1], found[1]), max(box[2], found[2]), max(box[3], found[3]))


def area_margins(found: Box | None, size: Size, hand: Any = None) -> Margins:
    """The capture area that the page panels found so far in a viewer's frames (*found*, their union: `joined`) give
    a capture of *size*. While the reader has set no area (*hand* None): the panels' own margins, the whole capture
    while none is found. With the reader's area (its margins) as the outer bound: what the panels and the area have in
    common, the area itself while none is found or the two have nothing in common - a panel never takes the capture
    area outside the reader's."""
    if hand is None:
        return page_area_margins(found, size)
    hand = tuple(int(m) for m in hand)
    if found is None:
        return hand  # type: ignore[return-value]
    outer = margins_box(hand, size)
    common = (max(found[0], outer[0]), max(found[1], outer[1]), min(found[2], outer[2]), min(found[3], outer[3]))
    if common[2] <= common[0] or common[3] <= common[1]:
        return hand  # type: ignore[return-value]
    return page_area_margins(common, size)


def widest(a: Any, b: Any) -> Margins:
    """The capture area that holds both areas *a* and *b* (margins of one capture size): the smaller margin on every
    side."""
    return tuple(min(int(x), int(y)) for x, y in zip(a, b))  # type: ignore[return-value]


def page_panel(image: Image.Image, hand: Any = None) -> Box | None:
    """The page panel of the frame *image* as the capture area takes it in, in *image*'s pixels: `find_page_area` on
    the whole capture while the reader has set no area (*hand* None), else the panel inside that area
    (`panel_inside`) - the area itself when the panel fills it within TIGHT_PX (the page is the area: joined with
    the panels of other pages, such as a cover narrower than the spreads the area was drawn around, it is the area
    that counts). None when none is found, or the frame is one the finder cannot take."""
    if hand is not None:
        box = margins_box(hand, image.size)
        inner, tight = _found_inside(image, box)
        return box if tight else inner
    try:
        return find_page_area(image)
    except Exception:  # noqa: BLE001 - a frame the finder cannot take changes nothing
        return None


@dataclass
class JoinedArea:
    """The capture area of a whole-book run that follows the reader (`batch.BatchReader`'s *page_area*): the page
    panels found in the frames the run takes as pages, joined (`joined`), and the area they give (`area_margins`), as
    the window joins the panels of its own frames (`ui.live.LiveViewMixin._find_page`) - for one run, growing as the
    pages come. A run that starts while the viewer shows a single page (a cover, narrower than the spreads after it)
    takes in the wider panel of each spread as it comes, before it reads that spread.

    *margins*: the area read now (left, top, right, bottom). *hand*: the reader's own area, the outer bound (None:
    none, the panel is looked for on the whole capture); never exceeded, and a panel within `TIGHT_PX` of it is the
    area itself. *size* and *found*: the capture size the panels are in and their union so far (None: none found yet),
    as the window's record of the viewer has them when the run starts.

    `meet` takes in a frame the run takes as a page, before the run reads it. The area only grows: every page is read
    in an area that holds its own panel and those of the pages before it, so no page already read needs reading
    again, and a page read once more (the reader went back) is read in an area that holds its panel as the first
    time. A frame where no panel is found changes nothing. Two exceptions, both before any page is read in the area
    they leave: while no panel is known (the area is the whole capture, or the reader's area with nothing found in
    it), the first page's panel gives the area, as the window would have given it; and a capture of another size than
    the panels found so far (the viewer's window resized) starts them over, margins being pixels.

    One thread alone calls `meet` (the run's packer); the others read *margins*, which it replaces whole."""

    margins: Margins
    hand: Margins | None = None
    size: Size | None = None
    found: Box | None = None
    # a page has been taken in the area, or a panel gave it: from then on it only grows
    settled: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.margins = tuple(int(m) for m in self.margins)  # type: ignore[assignment]
        self.hand = tuple(int(m) for m in self.hand) if self.hand is not None else None  # type: ignore[assignment]
        self.size = (int(self.size[0]), int(self.size[1])) if self.size is not None else None
        self.found = tuple(int(v) for v in self.found) if self.found is not None else None  # type: ignore[assignment]
        self.settled = self.found is not None

    def meet(self, image: Image.Image) -> bool:
        """*image*, a frame the run takes as a page: the panel found in it (`page_panel`) joined in, and the area
        widened to hold it. Whether the panels found changed (the window's record of them follows them)."""
        size = (int(image.size[0]), int(image.size[1]))
        if size != self.size:
            self.size, self.found, self.settled = size, None, False
        panel = page_panel(image, self.hand)
        if panel is None:
            self.settled = True  # (the page is read in the area as it is: from now on it only grows)
            return False
        found = joined(self.found, panel)
        area = area_margins(found, size, self.hand)
        self.margins = widest(self.margins, area) if self.settled else area
        self.settled = True
        changed, self.found = found != self.found, found
        return changed


# ---------------------------------------------------------------------------------------------------- measuring
def _gray(image: Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, Image.Image):
        return np.asarray(image if image.mode == "L" else image.convert("L"))
    a = np.asarray(image)
    if a.dtype == bool:
        a = a.astype(np.uint8) * 255
    elif a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    if a.ndim == 3 and a.shape[2] == 1:
        a = a[:, :, 0]
    if a.ndim == 2:
        return a
    if a.ndim == 3 and a.shape[2] == 3:
        return cv2.cvtColor(np.ascontiguousarray(a), cv2.COLOR_RGB2GRAY)
    if a.ndim == 3 and a.shape[2] == 4:
        return cv2.cvtColor(np.ascontiguousarray(a), cv2.COLOR_RGBA2GRAY)
    raise ValueError(f"not an image: shape {a.shape}")


def _median(values: np.ndarray) -> float:
    """The median of *values* (np.median imports numpy.ma on its first use: milliseconds)."""
    flat = np.asarray(values).ravel()
    if not flat.size:
        return 0.0
    k = flat.size // 2
    if flat.size % 2:
        return float(np.partition(flat, k)[k])
    part = np.partition(flat, (k - 1, k))
    return (float(part[k - 1]) + float(part[k])) / 2.0


def _border(g: np.ndarray, depth: int) -> np.ndarray:
    return np.concatenate([g[:depth].ravel(), g[-depth:].ravel(), g[depth:-depth, :depth].ravel(),
                           g[depth:-depth, -depth:].ravel()])


def _frame_levels(g: np.ndarray) -> list[tuple[int, int]]:
    """Candidate levels of the reader's frame with their tolerances: up to three dark levels holding a good share of
    the capture's border (a black reader under a dark-grey browser bar and the reader's own dark-grey bars), then the
    commonest other level."""
    border = _border(g, BORDER)
    hist = np.bincount(border, minlength=256).astype(np.float64)
    near = np.convolve(hist, np.ones(2 * PEAK + 1), mode="same")  # pixels within PEAK levels of each level
    n = float(border.size)
    picks: list[int] = []
    for limit, share in ((DARK_FRAME, MIN_DARK_SHARE),) * 3 + ((255, MIN_SHARE),):
        free = near.copy()
        free[limit + 1:] = 0
        for p in picks:
            free[max(0, p - 2 * PEAK):p + 2 * PEAK + 1] = 0
        peak = int(np.argmax(free))
        if free[peak] >= share * n:
            picks.append(peak)
    out: list[tuple[int, int]] = []
    for peak in picks:
        values = border[np.abs(border.astype(np.int16) - peak) <= 2 * PEAK].astype(np.float64)
        level = int(round(float(_median(values))))
        if any(abs(level - other) <= PEAK for other, _tol in out):
            continue  # two peaks that are one level
        sigma = 1.4826 * float(_median(np.abs(values - level)))
        out.append((level, max(MIN_TOL, int(np.ceil(4.0 * sigma)))))
    return out


# ---------------------------------------------------------------------------------------------------- the page
def _find(small: np.ndarray, level: int, tol: int, min_fraction: float,
          info: dict) -> tuple[Box, dict[str, str], Box] | None:
    """The page's box in the working copy for a frame at *level*, its sides' states and the viewport; None (with
    the reason in *info*) when there is no convincing page."""
    h, w = small.shape
    like = cv2.inRange(small, max(0, level - tol), min(255, level + tol))
    n, lab, st, _ = cv2.connectedComponentsWithStats(like, connectivity=4, ltype=cv2.CV_32S)
    # the labels on the border (np.unique would import numpy.ma on its first use: milliseconds)
    edge = np.flatnonzero(np.bincount(_border(lab, BORDER), minlength=n))
    edge = edge[(edge > 0) & (st[edge, cv2.CC_STAT_AREA] >= MIN_FRAME_PIECE * h * w)]
    if not edge.size:
        info["result"] = "no frame"
        return None
    if st[edge, cv2.CC_STAT_AREA].sum() < MIN_FRAME * h * w:
        info["result"] = "too little frame"
        return None
    lut = np.zeros(n, bool)
    lut[edge] = True
    frame = lut[lab]
    x0s, y0s = st[edge, cv2.CC_STAT_LEFT], st[edge, cv2.CC_STAT_TOP]
    viewport = (int(x0s.min()), int(y0s.min()), int((x0s + st[edge, cv2.CC_STAT_WIDTH]).max()),
                int((y0s + st[edge, cv2.CC_STAT_HEIGHT]).max()))
    info["viewport"] = viewport
    vx0, vy0, vx1, vy1 = viewport
    content = np.zeros((h, w), bool)
    content[vy0:vy1, vx0:vx1] = ~frame[vy0:vy1, vx0:vx1]
    dark = level <= DARK_FRAME

    parts = cv2.connectedComponentsWithStats(content.astype(np.uint8), connectivity=8, ltype=cv2.CV_32S)
    n, lab, st, _ = parts
    # bars: content spanning most of the viewport (a toolbar, the reader's header or slider) is the reader's, never
    # a page's piece: it does not count as content elsewhere, nor as a dark page's pieces around its box
    bar = (st[:, cv2.CC_STAT_WIDTH] >= BAR_SPAN * (vx1 - vx0)) | (st[:, cv2.CC_STAT_HEIGHT] >= BAR_SPAN * (vy1 - vy0))
    bar[0] = False
    unbarred = content & ~bar[lab] if bar.any() else content
    raw = _candidate(parts, content, viewport)
    raw_sides, raw_reason = _check(raw, small, frame, content, unbarred, level, tol, dark, min_fraction)
    info["raw"], info["raw_result"], info["raw_sides"] = raw, raw_reason, raw_sides
    if not dark or raw is None:  # closing is for a dark page's scattered pieces, grown from a piece found without it
        if raw_reason:
            info["result"] = raw_reason
            return None
        info["box"], info["sides"] = raw, raw_sides
        return raw, raw_sides, viewport
    if not raw_reason:
        busy = _ring_busy(unbarred, raw, viewport)
        info["ring"] = round(busy, 4)
        if busy <= RING_BUSY:
            info["box"], info["sides"] = raw, raw_sides
            return raw, raw_sides, viewport
    # a bar lying over the page (a slider over its foot) is closed with it; the tightening takes off what sticks out
    x0, y0, x1, y1 = raw
    left, top = st[:, cv2.CC_STAT_LEFT], st[:, cv2.CC_STAT_TOP]
    over = (left < x1) & (left + st[:, cv2.CC_STAT_WIDTH] > x0) & (top < y1) & (top + st[:, cv2.CC_STAT_HEIGHT] > y0)
    pieces = content & ~(bar & ~over)[lab]
    k = max(5, int(round(CLOSE * min(vx1 - vx0, vy1 - vy0)))) | 1
    closed = cv2.morphologyEx(pieces.astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    closed[:vy0] = 0
    closed[vy1:] = 0
    closed[:, :vx0] = 0
    closed[:, vx1:] = 0
    shut = _candidate(cv2.connectedComponentsWithStats(closed, connectivity=8, ltype=cv2.CV_32S), content, viewport)
    shut_sides, shut_reason = _check(shut, small, frame, content, unbarred, level, tol, dark, min_fraction)
    info["closed"], info["closed_result"], info["closed_sides"] = shut, shut_reason, shut_sides
    grows = shut is not None and _area(raw) >= GROWN * _area(shut)
    if not shut_reason and grows and (raw_reason or _area(shut) > _area(raw)):
        info["box"], info["sides"] = shut, shut_sides
        return shut, shut_sides, viewport
    if not raw_reason:
        info["box"], info["sides"] = raw, raw_sides
        return raw, raw_sides, viewport
    info["result"] = raw_reason
    return None


def _candidate(parts: tuple, content: np.ndarray, viewport: Box) -> Box | None:
    """The box of the largest of the components *parts* (connectedComponentsWithStats of the content inside the
    viewport, or of that content closed) with the pieces aligned with it, tightened by their own content (other
    content inside the box, such as a header's letters next to the page, does not hold its sides out; the closing
    only joins a dark page's pieces)."""
    n, lab, st, _ = parts
    if n <= 1:
        return None
    vx0, vy0, vx1, vy1 = viewport
    areas = st[1:, cv2.CC_STAT_AREA]
    ids = np.flatnonzero(areas >= MIN_PIECE * (vx1 - vx0) * (vy1 - vy0)) + 1
    if not ids.size:
        return None
    ids = ids[np.argsort(-st[ids, cv2.CC_STAT_AREA], kind="stable")]
    boxes = {int(i): (int(st[i, 0]), int(st[i, 1]), int(st[i, 0] + st[i, 2]), int(st[i, 1] + st[i, 3]))
             for i in ids}
    main = int(ids[0])
    x0, y0, x1, y1 = boxes[main]
    # the main piece is tightened first: a slider over its foot would make it as wide as a toolbar, which would
    # then pass for a piece beside it
    others = np.ones(content.shape, bool)
    others[y0:y1, x0:x1] = ~(content[y0:y1, x0:x1] & (lab[y0:y1, x0:x1] == main))
    box = _tighten(others, boxes[main])
    members = [main]
    grew = True
    while grew and len(members) < MAX_PIECES:
        grew = False
        for i in ids[1:]:
            b = boxes[int(i)]
            if st[i, cv2.CC_STAT_AREA] < JOIN * st[main, cv2.CC_STAT_AREA] or _within(b, box):
                continue
            if _beside(box, b):
                box = (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
                members.append(int(i))
                grew = True
                if len(members) >= MAX_PIECES:
                    break
    if len(members) > 1:
        lut = np.zeros(n, bool)
        lut[members] = True
        x0, y0, x1, y1 = box
        others = np.ones(content.shape, bool)  # what does not count for the tightening: all but the page's pieces
        others[y0:y1, x0:x1] = ~(content[y0:y1, x0:x1] & lut[lab[y0:y1, x0:x1]])
        box = _tighten(others, box)
    return _trim_bars(~content, box, viewport)


def _within(inner: Box, outer: Box, slack: float = 0) -> bool:
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack and inner[2] <= outer[2] + slack
            and inner[3] <= outer[3] + slack)


def _beside(a: Box, b: Box) -> bool:
    """Whether *b* lies beside *a* (side by side or one above the other) as another part of the same page or the
    other page of a spread: of about the same extent on one axis and overlapping there by most of it, across a thin
    gap on the other (or a wider one when both ends line up exactly: one page cut by a black band)."""
    for lo, hi in ((0, 2), (1, 3)):  # the axis of the gap: x (side by side), then y (stacked)
        olo, ohi = 1 - lo, 5 - hi  # the other axis
        overlap = min(a[ohi], b[ohi]) - max(a[olo], b[olo])
        shorter, longer = sorted((a[ohi] - a[olo], b[ohi] - b[olo]))
        gap = max(b[lo] - a[hi], a[lo] - b[hi])
        span = max(a[hi], b[hi]) - min(a[lo], b[lo])
        ends = max(abs(a[olo] - b[olo]), abs(a[ohi] - b[ohi]))
        if overlap < ALIGN * shorter or longer > LONGER * shorter:
            continue  # not side by side: a bar wider than the page above it is not another part of it
        if gap <= max(3, GAP * span) or (ends <= 2 and gap <= 0.5 * span):
            return True
    return False


def _tighten(frame: np.ndarray, box: Box) -> Box:
    """*box* without its outer rows and columns that are mostly frame (an icon or a line touching the page). What
    is "mostly" follows the box's own dense rows and columns, and a sparse column stays when its content reaches its
    middle third and spans most of it or lies in each third: a page that is sparse all over (a black page with thin
    art) keeps its sparse edges, while a slider line, an arrow, or a toolbar at the top and a slider at the bottom
    of the same columns beside a page of paper go. *frame* is what does not count: everything but the page's own
    pieces."""
    x0, y0, x1, y1 = box
    for _ in range(2):
        before = (x0, y0, x1, y1)
        for axis in (0, 1):
            sub = ~frame[y0:y1, x0:x1]
            if not sub.size:
                return (x0, y0, x1, y1)
            cover = sub.mean(axis=axis)  # content per column (axis 0) or row (axis 1)
            length = sub.shape[axis]
            first = np.argmax(sub, axis=axis)
            last = length - 1 - np.argmax(np.flip(sub, axis=axis), axis=axis)
            spread = (cover > 0) & ((last - first + 1) >= SPREAD * length)  # from near one end to near the other
            third = max(1, length // 3)
            thirds = []  # content in the column's (row's) top, middle and bottom thirds
            for k in range(3):
                stop = (k + 1) * third if k < 2 else length
                part = sub[k * third:stop] if axis == 0 else sub[:, k * third:stop]
                thirds.append(part.any(axis=axis))
            q = int(0.9 * (cover.size - 1))  # the 90th percentile (np.percentile costs milliseconds on first use)
            dense = cover >= min(1.0 - SHRINK, DENSE * float(np.partition(cover, q)[q]))
            sparse = (cover >= MIN_COVER) & thirds[1] & (spread | (thirds[0] & thirds[2]))  # not two bars' ends
            page = np.flatnonzero(dense | sparse)
            if page.size and page[-1] + 1 - page[0] > 8:
                if axis == 0:
                    x0, x1 = x0 + int(page[0]), x0 + int(page[-1]) + 1
                else:
                    y0, y1 = y0 + int(page[0]), y0 + int(page[-1]) + 1
        if (x0, y0, x1, y1) == before:
            break
    return (x0, y0, x1, y1)


def _zones(lo: int, hi: int, x0: int, x1: int, away: int = 2, least: int = 6) -> list[np.ndarray]:
    """The columns (or rows) of the viewport [lo, hi) beside a box spanning [x0, x1), one array per side that has
    at least *least* of them, *away* from the box (its edge's anti-aliasing is not frame)."""
    zones = []
    if x0 - away - lo >= least:
        zones.append(np.arange(lo, x0 - away))
    if hi - x1 - away >= least:
        zones.append(np.arange(x1 + away, hi))
    return zones


def _trim_bars(frame: np.ndarray, box: Box, viewport: Box) -> Box:
    """*box* without the rows (columns) at its top and bottom (left and right) where the viewport on both sides of
    the page is not frame: a bar spanning the viewport that touches the page (a toolbar glued to the page's top)."""
    x0, y0, x1, y1 = box
    vx0, vy0, vx1, vy1 = viewport
    zones = _zones(vx0, vx1, x0, x1)
    if zones:
        bar = np.logical_and.reduce([frame[:, z].mean(axis=1) < BAR for z in zones])
        limit = int(MAX_BAR * (y1 - y0))
        top, bottom = y0, y1
        while top < y0 + limit and bar[top]:
            top += 1
        while bottom > y1 - limit and bar[bottom - 1]:
            bottom -= 1
        if bottom - top > 8:
            y0, y1 = top, bottom
    zones = _zones(vy0, vy1, y0, y1)
    if zones:
        bar = np.logical_and.reduce([frame[z].mean(axis=0) < BAR for z in zones])
        limit = int(MAX_BAR * (x1 - x0))
        left, right = x0, x1
        while left < x0 + limit and bar[left]:
            left += 1
        while right > x1 - limit and bar[right - 1]:
            right -= 1
        if right - left > 8:
            x0, x1 = left, right
    return (x0, y0, x1, y1)


def _sides(frame: np.ndarray, box: Box) -> dict[str, str]:
    """Each side of *box*: "edge" (at the capture's edge), "framed" (frame just outside it) or "open"."""
    h, w = frame.shape
    x0, y0, x1, y1 = box
    iy, ix = max(1, (y1 - y0) // 20), max(1, (x1 - x0) // 20)

    def state(at_edge: bool, band: np.ndarray) -> str:
        if at_edge:
            return "edge"
        return "framed" if band.size and band.mean() >= FRAMED else "open"

    return {"left": state(x0 <= EDGE, frame[y0 + iy:y1 - iy, max(0, x0 - BAND):x0]),
            "right": state(x1 >= w - EDGE, frame[y0 + iy:y1 - iy, x1:x1 + BAND]),
            "top": state(y0 <= EDGE, frame[max(0, y0 - BAND):y0, x0 + ix:x1 - ix]),
            "bottom": state(y1 >= h - EDGE, frame[y1:y1 + BAND, x0 + ix:x1 - ix])}


def _check(box: Box | None, small: np.ndarray, frame: np.ndarray, content: np.ndarray, unbarred: np.ndarray,
           level: int, tol: int, dark: bool, min_fraction: float) -> tuple[dict[str, str], str]:
    """The sides of *box* and why it is not a convincing page ("" when it is). *unbarred* is the content without
    the bars spanning the viewport."""
    if box is None:
        return {}, "no page-sized content"
    h, w = small.shape
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if bw * bh < min_fraction * h * w:
        return {}, "too small"
    if not MIN_ASPECT <= bw / bh <= MAX_ASPECT:
        return {}, "not page-shaped"
    sides = _sides(frame, box)
    if not ((sides["left"] == "framed" and sides["right"] == "framed")
            or (sides["top"] == "framed" and sides["bottom"] == "framed")):
        return sides, "no frame on two opposite sides"
    inside = int(content[y0:y1, x0:x1].sum())
    if int(unbarred.sum()) - int(unbarred[y0:y1, x0:x1].sum()) > DOMINANCE * inside:
        return sides, "much content outside"
    if dark and (small[y0:y1, x0:x1] >= level + LIGHT).mean() < MIN_LIGHT:
        return sides, "nothing light in it"
    if not dark and not _paper_edges(small, box, sides, level, tol):
        return sides, "no paper edge on a light frame"
    return sides, ""


def _paper_edges(small: np.ndarray, box: Box, sides: dict[str, str], level: int, tol: int) -> bool:
    """On a light or grey frame: whether, inside every framed side, the page shows paper of its own: a band (its
    first pixel left out, the edge's blend) mostly at one level clearly off the frame's; a slider line across it is
    let pass. The panels of a full page on white paper fail it: inside their outline is the same white as the
    margins taken for a frame."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    dx, dy = max(3, int(PAPER * bw)), max(3, int(PAPER * bh))
    iy, ix = max(1, bh // 20), max(1, bw // 20)
    bands = {"left": small[y0 + iy:y1 - iy, x0 + 1:x0 + 1 + dx], "right": small[y0 + iy:y1 - iy, x1 - 1 - dx:x1 - 1],
             "top": small[y0 + 1:y0 + 1 + dy, x0 + ix:x1 - ix], "bottom": small[y1 - 1 - dy:y1 - 1, x0 + ix:x1 - ix]}
    for side, band in bands.items():
        if sides[side] != "framed":
            continue
        if not band.size:
            return False
        paper = float(_median(band))
        if abs(paper - level) <= tol + 6:
            return False
        if (np.abs(band.astype(np.float64) - paper) <= max(tol, 16)).mean() < 0.5:
            return False
    return True


def _ring_busy(content: np.ndarray, box: Box, viewport: Box) -> float:
    """Share of content (bars left out) in a ring around *box* within the viewport: a page in a reader frame has
    little there (a few letters of the header), a dark page whose box took only a light part of it has its own
    pieces there."""
    x0, y0, x1, y1 = box
    r = max(3, int(RING * min(x1 - x0, y1 - y0)))
    vx0, vy0, vx1, vy1 = viewport
    rx0, ry0, rx1, ry1 = max(vx0, x0 - r), max(vy0, y0 - r), min(vx1, x1 + r), min(vy1, y1 + r)
    ring = (rx1 - rx0) * (ry1 - ry0) - (x1 - x0) * (y1 - y0)
    if ring <= 0:
        return 0.0
    return float(content[ry0:ry1, rx0:rx1].sum() - content[y0:y1, x0:x1].sum()) / ring


def _area(box: Box | None) -> int:
    return 0 if box is None else (box[2] - box[0]) * (box[3] - box[1])


# ---------------------------------------------------------------------------------------------------- refining
def _refine(gray: np.ndarray, box: Box, sides: dict[str, str], viewport: Box, level: int, sx: float,
            sy: float) -> Box:
    """*box* (working copy) in the capture's pixels, each side moved to the page's edge at full resolution.

    From the coarse edge, a walk to the nearest change between frame (rows or columns at least 90% at the frame's
    level) and page. A side against a bar goes no further out than where the frame on both sides of the page starts
    (the page touches a toolbar, whose address field may be at the frame's level); a side at the capture's edge
    whose page runs on to the end of the search band goes to the edge. Otherwise the coarse edge stays."""
    height, width = gray.shape
    x0, y0, x1, y1 = int(round(box[0] * sx)), int(round(box[1] * sy)), int(round(box[2] * sx)), int(round(box[3] * sy))
    vx0, vy0, vx1, vy1 = (int(round(viewport[0] * sx)), int(round(viewport[1] * sy)), int(round(viewport[2] * sx)),
                          int(round(viewport[3] * sy)))
    reach = int(np.ceil(2 * max(sx, sy))) + 2
    tol = _full_tolerance(gray, level)

    def like(a: np.ndarray) -> np.ndarray:
        return np.abs(a.astype(np.int16) - level) <= tol

    def span(lo: int, hi: int) -> slice:  # the box's extent on the other axis, less the corners, at most ~512 samples
        a, b = min(lo + reach, hi - 1), max(hi - reach, lo + 1)
        return slice(a, b, max(1, (b - a) // 512))

    rows, cols = span(y0, y1), span(x0, x1)
    out = [x0, y0, x1, y1]
    for side, idx, axis, outward in (("left", 0, 1, -1), ("right", 2, 1, 1), ("top", 1, 0, -1),
                                     ("bottom", 3, 0, 1)):
        size = width if axis == 1 else height
        edge = out[idx]
        lo, hi = max(0, edge - reach), min(size, edge + reach)
        if hi - lo < 2:
            continue
        band = gray[rows, lo:hi] if axis == 1 else gray[lo:hi, cols]
        moved = _walk(like(band).mean(axis=0 if axis == 1 else 1) < SHRINK, edge - lo, outward)
        zones = _zones(vx0, vx1, x0, x1, reach) if axis == 0 else _zones(vy0, vy1, y0, y1, reach)
        if sides.get(side) == "open" and zones:
            beside = []  # against a bar: the page lies where there is frame on both sides of it
            for z in zones:
                z = z[:: max(1, z.size // 128)]
                part = gray[lo:hi][:, z] if axis == 0 else gray[z][:, lo:hi]
                beside.append(like(part).mean(axis=1 if axis == 0 else 0) >= BAR)
            within = _walk(np.logical_and.reduce(beside), edge - lo, outward)
            if within is not None:  # a bar's own patch at the frame's level is not frame before the page
                moved = within if moved is None else (max(moved, within) if outward < 0 else min(moved, within))
        if moved is not None:
            out[idx] = lo + moved
        elif sides.get(side) == "edge":
            out[idx] = 0 if outward < 0 else size
    x0, y0, x1, y1 = out
    x0, x1 = max(0, min(x0, width - 1)), min(width, max(x1, x0 + 1))
    y0, y1 = max(0, min(y0, height - 1)), min(height, max(y1, y0 + 1))
    return (int(x0), int(y0), int(x1), int(y1))


def _walk(page: np.ndarray, at: int, outward: int) -> int | None:
    """In a band of rows (columns) flagged *page*, from position *at* (the coarse edge: the page's first element
    for an outward -1 side, one past its last for +1), the nearest change between page and not page: the page's
    first element (one past its last) there. None when the page runs on to the band's outer end or no page is
    found inward."""
    n = page.size
    if outward < 0:
        i = min(max(at, 0), n - 1)
        if page[i]:
            while i > 0 and page[i - 1]:
                i -= 1
            return i if i > 0 else None
        while i < n and not page[i]:
            i += 1
        return i if i < n else None
    i = min(max(at - 1, 0), n - 1)
    if page[i]:
        while i < n - 1 and page[i + 1]:
            i += 1
        return i + 1 if i < n - 1 else None
    while i >= 0 and not page[i]:
        i -= 1
    return i + 1 if i >= 0 else None


def _full_tolerance(gray: np.ndarray, level: int) -> int:
    """The frame's tolerance at full resolution, from the noise of the capture's border near *level*."""
    depth = 4
    border = np.concatenate([gray[:depth, ::2].ravel(), gray[-depth:, ::2].ravel(), gray[::2, :depth].ravel(),
                             gray[::2, -depth:].ravel()]).astype(np.int16)
    values = border[np.abs(border - level) <= 2 * PEAK].astype(np.float64)
    if values.size < 16:
        return MIN_TOL
    sigma = 1.4826 * float(_median(np.abs(values - _median(values))))
    return max(MIN_TOL, int(np.ceil(4.0 * sigma)))
