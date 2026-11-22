"""Page fingerprints: recognise *which* page is on screen without storing the page.

A fingerprint is 320 bits derived from the layout of ink on the page (a 16x16
difference hash plus an 8x8 average hash of the page's content box). It is
enough to tell the pages of one book apart and to recognise a page again at a
different window size, but it cannot be turned back into the picture. That is
what lets the translation cache work while deliberately *not* being an offline
copy of the book: without the real page in the viewer there is nothing to show.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .regions import Box

FINGERPRINT_BITS = 256 + 64
FINGERPRINT_HEX_LEN = FINGERPRINT_BITS // 4

# How the paper found on a dark viewer background is grown past its large blobs (`page_box`): a blob lower than
# BAR_HEIGHT of the capture and wider than BAR_WIDTH of the paper is a viewer's bar (a slider, a progress bar, a
# header strip); one reaching past the paper on both sides by more than ACROSS of its width (or above and below it,
# of its height) is a bar across the viewer; a band of nothing but background between the paper and a blob, GAP of
# the capture's height wide and at least half the blob's own size, leaves the blob out (a button beside the page, a
# knob under it; a panel across a black gutter of its page is larger than the gutter is wide).
BAR_HEIGHT = 0.03
BAR_WIDTH = 0.60
ACROSS = 0.10
GAP = 0.03


@dataclass
class PageUnit:
    """One page as shown in the viewer (a two-page spread yields two units, the page read first first: the right one,
    the left one in a book read left to right; *index* is the unit's place in that order)."""

    box: Box  # content box in capture coordinates
    fingerprint: str
    index: int = 0

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    def normalize(self, box: Box) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.box
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        return ((box[0] - x0) / w, (box[1] - y0) / h, (box[2] - x0) / w, (box[3] - y0) / h)

    def denormalize(self, nbox: tuple[float, float, float, float]) -> Box:
        x0, y0, x1, y1 = self.box
        w, h = x1 - x0, y1 - y0
        return (
            int(round(x0 + nbox[0] * w)),
            int(round(y0 + nbox[1] * h)),
            int(round(x0 + nbox[2] * w)),
            int(round(y0 + nbox[3] * h)),
        )


def _span(flags: np.ndarray) -> tuple[int, int] | None:
    idx = np.flatnonzero(flags)
    if idx.size == 0:
        return None
    return int(idx[0]), int(idx[-1]) + 1


def _counts(mask: np.ndarray, axis: int) -> np.ndarray:
    """The True pixels of the boolean *mask* per column (*axis* 0) or per row (1): ``mask.sum(axis)``, in a tenth of
    the time (analyze runs at every look at the viewer)."""
    return cv2.reduce(mask.view(np.uint8), axis, cv2.REDUCE_SUM, dtype=cv2.CV_32S).ravel()


def _off_background(gray: np.ndarray, bg: int) -> np.ndarray:
    """1 where *gray* differs from the background level *bg* by more than 24, else 0 (uint8)."""
    if gray.dtype != np.uint8:
        return (np.abs(gray.astype(np.int16) - bg) > 24).astype(np.uint8)
    table = (np.abs(np.arange(256) - bg) > 24).astype(np.uint8)
    return cv2.LUT(gray, table)


def background_level(gray: np.ndarray, ring: int = 4) -> int:
    """Typical value of the viewer background, sampled from the capture's border."""
    h, w = gray.shape
    r = max(1, min(ring, h // 4, w // 4))
    border = np.concatenate([gray[:r].ravel(), gray[-r:].ravel(), gray[:, :r].ravel(), gray[:, -r:].ravel()])
    hist = np.bincount(border // 32, minlength=8)
    bucket = int(hist.argmax())
    inside = border[(border // 32) == bucket]
    return int(np.median(inside)) if inside.size else int(np.median(border))


def page_box(gray: np.ndarray, bright_threshold: int = 200, min_height: float = 0.25, min_width: float = 0.10,
             bg: int | None = None, grow: bool = True) -> Box | None:
    """Extent of the paper inside a viewer with a dark background: the union of the large non-background blobs,
    grown by the page's other blobs (`_grown`).

    Toolbars, buttons and progress bars are not background either, but they are
    short or narrow; pages are tall. Thin structures are removed by an opening
    before the blobs are measured. A page whose lower half is black panels breaks
    into blobs, though: its upper panels are a large blob, the white bubbles in the
    black ones are small. So the large blobs only start the paper, and the blobs
    in line with it, above, below or beside it, are taken in until none is left.
    Returns None when nothing page-sized is found. *bg* is the background's level
    (default: background_level of the capture). Without *grow*, the large blobs'
    union alone: the paper as it was found before 2026-10-31 (`analyze`'s *grow*).
    """
    h, w = gray.shape
    bg = background_level(gray) if bg is None else bg
    if bg >= 128:
        return None  # bright background: pages are not separable from it this way
    content = _off_background(gray, bg)
    opened = cv2.morphologyEx(content, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    _n, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8, ltype=cv2.CV_32S)
    blobs = stats[1:, :4].astype(np.int64)  # x, y, width, height
    big = (blobs[:, 3] >= min_height * h) & (blobs[:, 2] >= min_width * w)
    if not big.any():
        return None
    x0, y0 = int(blobs[big, 0].min()), int(blobs[big, 1].min())
    x1, y1 = int((blobs[big, 0] + blobs[big, 2]).max()), int((blobs[big, 1] + blobs[big, 3]).max())
    if not grow:
        return (x0, y0, x1, y1)
    return _grown((x0, y0, x1, y1), blobs[~big], content)


def _grown(box: Box, blobs: np.ndarray, content: np.ndarray) -> Box:
    """*box* (the large blobs' union) grown by the *blobs* (x, y, width, height) in line with it, until none is.

    A blob whose centre lies within the box's columns grows it down or up, one whose centre lies within its rows
    grows it sideways; the box grows by every such blob at once, then looks again (a bubble beside the box may bring
    a column of others in line). The viewer's own furniture stays out: a bar (lower than BAR_HEIGHT of the capture
    and wider than BAR_WIDTH of the box), a bar across the viewer (past the box on both sides by more than ACROSS of
    it), and a blob kept from the box by a band of nothing but background (`_kept_apart`; *content* is the raw mask
    before the opening) - a page's black panels carry art, the viewer's background does not.
    """
    if not len(blobs):
        return box
    h = content.shape[0]
    gap = max(8, int(round(GAP * h)))
    bx0, by0 = blobs[:, 0], blobs[:, 1]
    bx1, by1 = bx0 + blobs[:, 2], by0 + blobs[:, 3]
    cx2, cy2 = bx0 + bx1, by0 + by1  # twice the centres: whole numbers
    low = blobs[:, 3] < BAR_HEIGHT * h
    todo = np.ones(len(blobs), bool)
    integral: np.ndarray | None = None
    x0, y0, x1, y1 = box
    while True:
        todo &= ~((bx0 >= x0) & (bx1 <= x1) & (by0 >= y0) & (by1 <= y1))  # inside the box already
        bw, bh = x1 - x0, y1 - y0
        bar = (low & (blobs[:, 2] > BAR_WIDTH * bw)) | ((bx0 < x0 - ACROSS * bw) & (bx1 > x1 + ACROSS * bw))
        upright = (by0 < y0 - ACROSS * bh) & (by1 > y1 + ACROSS * bh)
        vertical = todo & ~bar & (cx2 >= 2 * x0) & (cx2 < 2 * x1)
        sideways = todo & ~vertical & ~upright & (cy2 >= 2 * y0) & (cy2 < 2 * y1)
        picked = np.flatnonzero(vertical | sideways)
        if not picked.size:
            return (x0, y0, x1, y1)
        if integral is None:
            integral = cv2.integral(content)
        taken = [i for i in picked if not _kept_apart(integral, (x0, y0, x1, y1),
                                                      (int(bx0[i]), int(by0[i]), int(bx1[i]), int(by1[i])),
                                                      bool(vertical[i]), gap)]
        if not taken:
            return (x0, y0, x1, y1)
        todo[taken] = False
        x0, y0 = min(x0, int(bx0[taken].min())), min(y0, int(by0[taken].min()))
        x1, y1 = max(x1, int(bx1[taken].max())), max(y1, int(by1[taken].max()))


def _kept_apart(integral: np.ndarray, box: Box, blob: Box, vertical: bool, gap: int) -> bool:
    """Is *blob* kept from *box* by a band of background across the box, rows of it (*vertical*: the blob lies above
    or below) or columns (beside it), at least *gap* and half the blob's own height (width) wide? *integral* is the
    summed-area table of the raw content mask. A line of background may be crossed by a line or two (a slider running
    past a page to its knob): it holds at most 1 % of content."""
    x0, y0, x1, y1 = box
    if vertical:
        a, b = (y1, blob[1]) if blob[1] >= y1 else (blob[3], y0)
        need = max(gap, (blob[3] - blob[1]) // 2)
        if b - a < need:
            return False
        rows = np.arange(a, b)
        filled = (integral[rows + 1, x1] - integral[rows + 1, x0]) - (integral[rows, x1] - integral[rows, x0])
        span = x1 - x0
    else:
        a, b = (x1, blob[0]) if blob[0] >= x1 else (blob[2], x0)
        need = max(gap, (blob[2] - blob[0]) // 2)
        if b - a < need:
            return False
        cols = np.arange(a, b)
        filled = (integral[y1, cols + 1] - integral[y0, cols + 1]) - (integral[y1, cols] - integral[y0, cols])
        span = y1 - y0
    empty = np.concatenate([[0], np.cumsum(filled <= max(2, span // 100))])
    return bool((empty[need:] - empty[:-need] == need).any())


@dataclass(frozen=True)
class Nudge:
    """One pixel of ink more (*by* 1) or less (-1) that the rows or columns at one edge of a content box need to count
    as ink, as the page drawn at another scale may need it (`readings`): *where* is "box" (the capture's content box),
    "right" or "left" (a spread's page, `split_spread`) or "gutter" (the gutter's columns); *side* is the edge, 0 to 3
    for left, top, right and bottom (-1 for the gutter)."""

    where: str
    side: int
    by: int

    def at(self, where: str) -> tuple[int, int, int, int]:
        """The pixels each edge of the content box *where* needs besides the threshold (left, top, right, bottom)."""
        out = [0, 0, 0, 0]
        if where == self.where and self.side >= 0:
            out[self.side] = self.by
        return out[0], out[1], out[2], out[3]


NO_SLACK = (0, 0, 0, 0)


def _ink_box(rows: np.ndarray, cols: np.ndarray, rneed: float, cneed: float,
             slack: tuple[int, ...]) -> Box | None:
    """The extent of the ink on a paper whose rows and columns hold *rows* and *cols* dark pixels: from the first to
    the last column (row) with *cneed* (*rneed*) of them, each edge needing its *slack* (left, top, right, bottom)
    besides. None when no column or row has that many (or the edges cross)."""
    left, right = np.flatnonzero(cols >= cneed + slack[0]), np.flatnonzero(cols >= cneed + slack[2])
    top, bottom = np.flatnonzero(rows >= rneed + slack[1]), np.flatnonzero(rows >= rneed + slack[3])
    if not (left.size and right.size and top.size and bottom.size):
        return None
    box = (int(left[0]), int(top[0]), int(right[-1]) + 1, int(bottom[-1]) + 1)
    return box if box[0] < box[2] and box[1] < box[3] else None


def content_box(gray: np.ndarray, bright_threshold: int = 200, ink_threshold: int = 120,
                grow: bool = True, slack: tuple[int, ...] = NO_SLACK,
                moved: list[tuple[int, int]] | None = None) -> Box | None:
    """Bounding box of the page content inside a capture.

    First the paper is located: on a dark viewer background it is the union of
    the large non-background blobs, grown by the page's other blobs in line with
    it (`page_box`: the bubbles in black panels, not the viewer's toolbars and
    buttons); on a bright background it is where bright rows and columns are.
    Then the ink inside the paper gives the extent of the artwork. Coverage
    thresholds keep stray pixels from moving the box. *grow*: `page_box`'s.
    *slack*: the dark pixels each edge's rows or columns need besides the
    threshold (`Nudge`); *moved* gets the (edge, pixel) whose one pixel more or
    less would move that edge (`readings`).
    """
    h, w = gray.shape
    if h < 8 or w < 8:
        return None
    paper_box = page_box(gray, bright_threshold, grow=grow)
    if paper_box is None:
        bright = gray >= bright_threshold
        rows = _span(_counts(bright, 1) >= 0.02 * w)
        cols = _span(_counts(bright, 0) >= 0.02 * h)
        if rows is None or cols is None:
            return None
        paper_box = (cols[0], rows[0], cols[1], rows[1])
    px0, py0, px1, py1 = paper_box
    paper = gray[py0:py1, px0:px1]
    ph, pw = paper.shape
    ink = paper < ink_threshold
    rcounts, ccounts = _counts(ink, 1), _counts(ink, 0)
    rneed, cneed = max(2, 0.003 * pw), max(2, 0.003 * ph)
    box = _ink_box(rcounts, ccounts, rneed, cneed, slack)
    if box is None:
        return None  # blank page: nothing to read, nothing to fingerprint
    if moved is not None:
        for side in range(4):
            for by in (1, -1):
                nudged = list(slack)
                nudged[side] += by
                other = _ink_box(rcounts, ccounts, rneed, cneed, nudged)
                if other is not None and other[side] != box[side]:
                    moved.append((side, by))
    return (px0 + box[0], py0 + box[1], px0 + box[2], py0 + box[3])


def _gutter(candidate: np.ndarray, lo: int, w: int, h: int) -> tuple[int, int] | None:
    """Where a spread of *w* x *h* splits (its columns), from the columns of its middle band from column *lo* on that
    may be the gutter (*candidate*): the longest run of them, at least `split_spread`'s gap wide, else the middle of a
    landscape unit; None for a single page."""
    best: tuple[int, int] | None = None
    start = None
    for i, flag in enumerate(list(candidate) + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            run = (start, i)
            if best is None or (run[1] - run[0]) > (best[1] - best[0]):
                best = run
            start = None
    min_gap = max(3, int(0.006 * w))
    if best is None or (best[1] - best[0]) < min_gap:
        if w / h < 1.25:
            return None
        # A landscape unit without a visible gutter is a spread whose pages touch:
        # split it in the middle.
        return w // 2, w // 2
    return lo + best[0], lo + best[1]


def split_spread(gray: np.ndarray, box: Box, grow: bool = True, rtl: bool = True, nudge: Nudge | None = None,
                 moved: list[Nudge] | None = None) -> list[Box]:
    """Split a two-page spread at the gutter between the pages. The page read first comes first: the right page,
    the left one without *rtl* (a book read left to right). Only the order follows *rtl*: the boxes, and so the
    fingerprints, are the same either way.

    A gutter is a run of columns near the middle that carries no ink (white gap)
    or is perfectly uniform (viewer background). A false split on a single page
    is harmless: every reading of the page applies the same rule,
    so fingerprints still line up. *grow*: `page_box`'s, for each page's box.
    *nudge*: the gutter's columns, or an edge of a page's box, read with a pixel
    of ink more or less (`Nudge`); *moved* gets the nudges that would move the
    gutter or an edge of a page's box (`readings`).
    """
    x0, y0, x1, y1 = box
    crop = gray[y0:y1, x0:x1]
    h, w = crop.shape
    if w < 64 or h < 64:
        return [box]
    lo, hi = int(w * 0.35), int(w * 0.65)
    band = crop[:, lo:hi]
    counts = _counts(band < 120, 0)
    free = max(1, 0.002 * h) + (nudge.by if nudge is not None and nudge.where == "gutter" else 0)
    uniform = band.std(axis=0) < 4.0
    gutter = _gutter((counts <= free) | uniform, lo, w, h)
    if moved is not None:
        moved.extend(Nudge("gutter", -1, by) for by in (1, -1)
                     if _gutter((counts <= free + by) | uniform, lo, w, h) != gutter)
    if gutter is None:
        return [box]
    gx0, gx1 = gutter
    left_part = crop[:, :gx0]
    right_part = crop[:, gx1:]
    if (np.count_nonzero(left_part < 120) < 0.002 * left_part.size
            or np.count_nonzero(right_part < 120) < 0.002 * right_part.size):
        return [box]
    edges: dict[str, list[tuple[int, int]]] = {"right": [], "left": []}
    right_box = content_box(right_part, grow=grow, slack=nudge.at("right") if nudge is not None else NO_SLACK,
                            moved=edges["right"] if moved is not None else None) \
        or (0, 0, right_part.shape[1], right_part.shape[0])
    left_box = content_box(left_part, grow=grow, slack=nudge.at("left") if nudge is not None else NO_SLACK,
                           moved=edges["left"] if moved is not None else None) \
        or (0, 0, left_part.shape[1], left_part.shape[0])
    if moved is not None:
        moved.extend(Nudge(where, side, by) for where, found in edges.items() for side, by in found)
    right = (x0 + gx1 + right_box[0], y0 + right_box[1], x0 + gx1 + right_box[2], y0 + right_box[3])
    left = (x0 + left_box[0], y0 + left_box[1], x0 + left_box[2], y0 + left_box[3])
    return [right, left] if rtl else [left, right]


def compute_fingerprint(gray_crop: np.ndarray) -> str:
    """320-bit perceptual hash (16x16 dHash + 8x8 aHash) as 80 hex characters."""
    if gray_crop.size == 0:
        return "0" * FINGERPRINT_HEX_LEN
    small = cv2.resize(gray_crop, (17, 16), interpolation=cv2.INTER_AREA).astype(np.int16)
    dbits = (small[:, 1:] > small[:, :-1]).flatten()
    tiny = cv2.resize(gray_crop, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32)
    abits = (tiny > tiny.mean()).flatten()
    bits = np.concatenate([dbits, abits]).astype(np.uint8)
    return np.packbits(bits).tobytes().hex()


def hamming(a: str, b: str) -> int:
    if len(a) != len(b):
        return FINGERPRINT_BITS
    return (int(a, 16) ^ int(b, 16)).bit_count()


def capture_area(width: int, height: int, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> Box:
    """The part of a capture of *width* x *height* that *margins* (left, top, right, bottom) leave - what is read of
    it, at least one pixel."""
    left, top, right, bottom = margins
    x0, y0 = min(left, width - 1), min(top, height - 1)
    return (x0, y0, max(x0 + 1, width - right), max(y0 + 1, height - bottom))


def paper_box(rgb: np.ndarray, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> Box | None:
    """Where the paper is in a capture (capture coordinates), on a viewer with a dark background; None otherwise.

    Page units are cropped to the ink, so a page of text or a pale drawing gives a unit of any shape; the paper
    stays where the book's pages always are. The background is read from the capture's left and right edges only:
    a white page reaching its top and bottom edges would otherwise pass for a bright background.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    x0, y0, x1, y1 = capture_area(gray.shape[1], gray.shape[0], margins)
    sub = gray[y0:y1, x0:x1]
    bg = int(np.median(np.concatenate([sub[:, :4].ravel(), sub[:, -4:].ravel()])))
    if bg >= 128:
        return None
    box = page_box(sub, bg=bg)
    if box is None:
        return None
    return (box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0)


SHARED_KEEP = 2  # the latest analyses of captures whose pixels never change, kept for the next look at the same pixels
_shared: list[tuple[np.ndarray, tuple[Any, ...], tuple[PageUnit, ...]]] = []  # (pixels, arguments, units): newest first
_shared_lock = threading.Lock()


def _fixed(rgb: np.ndarray) -> bool:
    """Whether the pixels of *rgb* can never change: a read-only array over a bytes object, all the way down (what
    numpy makes of a PIL image: the window's frames, the page a job reads)."""
    base: Any = rgb
    while isinstance(base, np.ndarray):
        if base.flags.writeable:
            return False
        base = base.base
    return isinstance(base, bytes)


def same_pixels(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether *a* and *b* hold the very same pixels (a few rows compared first: two frames of a turning page differ
    there already)."""
    if a is b:
        return True
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    step = max(1, a.shape[0] // 32)
    return bool(np.array_equal(a[::step], b[::step]) and np.array_equal(a, b))


def _copies(units: Any) -> list[PageUnit]:
    return [PageUnit(u.box, u.fingerprint, u.index) for u in units]


def analyze(rgb: np.ndarray, margins: tuple[int, int, int, int] = (0, 0, 0, 0), grow: bool = True,
            known: dict[Box, str] | None = None, rtl: bool = True) -> list[PageUnit]:
    """Locate the page(s) in a capture and fingerprint each one.

    Without *grow* the paper on a dark viewer is the large blobs' union alone (`page_box`), as analyze found it
    before 2026-10-31: the units, and so the fingerprints, that the caches kept before then hold for a page whose
    black panels the paper now grows through. Only recognising a book (`bookid.page_groups`) and a cache lookup that
    missed (`Pipeline._lookup_before`) look for those; what the pipeline keeps is fingerprinted with *grow*. *known*:
    the fingerprints of boxes of this very capture computed already (by box; the ones computed here are added), for a
    capture analyzed in several areas. *rtl*: the book's reading direction, which page of a spread comes first
    (`split_spread`); the units' boxes and fingerprints do not depend on it.

    The analysis is computed once for the same pixels: the units of the latest SHARED_KEEP captures whose pixels
    never change (`_fixed`) are kept, and a capture with the very same pixels, analyzed with the same arguments, gets
    copies of them - the window's check of a frame on its thread (`ui.live`) and the page job that reads that frame
    then (`Pipeline.units_of`) share one analysis. Nothing is kept for a capture analyzed with *known*."""
    if known is not None or not isinstance(rgb, np.ndarray) or not all(type(m) is int for m in margins):
        return _analyze(rgb, margins, grow, known, rtl)
    args = (tuple(margins), bool(grow), bool(rtl))
    with _shared_lock:
        kept = list(_shared)
    for pixels, kept_args, units in kept:
        if kept_args == args and same_pixels(pixels, rgb):
            return _copies(units)
    found = _analyze(rgb, margins, grow, None, rtl)
    if _fixed(rgb):
        with _shared_lock:
            _shared[:] = [(rgb, args, tuple(_copies(found)))] + [e for e in _shared if e[0] is not rgb or e[1] != args]
            del _shared[SHARED_KEEP:]
    return found


def _analyze(rgb: np.ndarray, margins: tuple[int, int, int, int], grow: bool, known: dict[Box, str] | None,
             rtl: bool, nudge: Nudge | None = None, moved: list[Nudge] | None = None) -> list[PageUnit]:
    """`analyze`, computed: with *nudge*, one edge read with a pixel of ink more or less; *moved* gets the nudges
    that would move an edge (`readings`)."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    x0, y0, x1, y1 = capture_area(gray.shape[1], gray.shape[0], margins)
    sub = gray[y0:y1, x0:x1]
    edges: list[tuple[int, int]] | None = [] if moved is not None else None
    box = content_box(sub, grow=grow, slack=nudge.at("box") if nudge is not None else NO_SLACK, moved=edges)
    if box is None:
        return []
    if moved is not None and edges:
        moved.extend(Nudge("box", side, by) for side, by in edges)
    box = (box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0)
    units: list[PageUnit] = []
    for idx, b in enumerate(split_spread(gray, box, grow=grow, rtl=rtl, nudge=nudge, moved=moved)):
        bx0, by0, bx1, by1 = b
        if bx1 - bx0 < 16 or by1 - by0 < 16:
            continue
        fingerprint = known.get(b) if known is not None else None
        if fingerprint is None:
            fingerprint = compute_fingerprint(gray[by0:by1, bx0:bx1])
            if known is not None:
                known[b] = fingerprint
        units.append(PageUnit(box=b, fingerprint=fingerprint, index=idx))
    return units


# The pixels of the viewer's ground around the paper that `readings` reads a capture with, besides none: a sliver on
# its left and right, which a page whose edges are black art takes for paper, and enough on every side for
# `background_level`'s ring to see the ground.
SLIVER = 2
GROUND = 8
CUTS = (0.012, 0.024, 0.036, 0.048)  # the shares of its width `readings` cuts a page alone by, at either side


def _trimmed(gray: np.ndarray, box: Box, index: int) -> PageUnit | None:
    """The page unit *index* of the part *box* of a capture, trimmed to its ink as `split_spread` trims a spread's
    page (the part as it is when it holds none); None when it is under 16 pixels either way."""
    x0, y0, x1, y1 = box
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    b = content_box(gray[y0:y1, x0:x1]) or (0, 0, x1 - x0, y1 - y0)
    b = (x0 + b[0], y0 + b[1], x0 + b[2], y0 + b[3])
    if b[2] - b[0] < 16 or b[3] - b[1] < 16:
        return None
    return PageUnit(box=b, fingerprint=compute_fingerprint(gray[b[1]:b[3], b[0]:b[2]]), index=index)


def _halves(gray: np.ndarray, margins: tuple[int, int, int, int], paper: Box, rtl: bool) -> list[PageUnit]:
    """The spread in the capture area *margins* split where its two pages meet, the middle of its *paper*, rather
    than at the middle of its content box, each part trimmed to its ink: its pages much as each is read alone. Empty
    when that middle does not split the content box."""
    x0, y0, x1, y1 = capture_area(gray.shape[1], gray.shape[0], margins)
    box = content_box(gray[y0:y1, x0:x1])
    if box is None:
        return []
    bx0, by0, bx1, by1 = box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0
    mid = (paper[0] + paper[2]) // 2
    if not bx0 < mid < bx1:
        return []
    parts = [(mid, by0, bx1, by1), (bx0, by0, mid, by1)]  # the right page first
    units = []
    for idx, part in enumerate(parts if rtl else parts[::-1]):
        unit = _trimmed(gray, part, idx)
        if unit is None:
            return []
        units.append(unit)
    return units


def readings(rgb: np.ndarray, margins: tuple[int, int, int, int] = (0, 0, 0, 0),
             rtl: bool = True) -> Iterator[list[PageUnit]]:
    """The page units of the capture *rgb* as `analyze` finds them where the same page is drawn at another window
    size, each reading computed only once it is asked for: a page the cache holds as it was read at another size is
    found by one of them (`Pipeline._resolve`). Three things that decide a page's content box are not the same at
    every size, so neither is its fingerprint:

    - the capture area *margins* is joined from the page panels of all the pages seen at the size (`ui.live`'s
      `_find_page`): one wider by a few pixels than this page's paper takes in a sliver of the viewer's dark ground,
      and on a page whose edges are black art the sliver is read as paper and ink (`background_level` takes the art
      for the background) - the content box runs out to the capture area's sides, and a spread is split elsewhere.
      At another size the area may fit the paper, or run well past it - and a page whose edges are black art fit
      exactly loses that art to the background too. So the capture is read in the area fit to its paper
      (`paper_box`: in the capture area where it has ground beside the paper, else across the capture's width),
      with SLIVER pixels of ground beside the
      paper on its left and right (pages and spreads are centred; their widths differ), and with GROUND pixels of
      ground all round;
    - a line one or two pixels thick (a panel's frame across a page's margin, a page's border) that decides where
      the ink ends, or whether a gutter runs, is drawn a pixel thicker or thinner at another scale: each edge whose
      rows or columns one pixel more or less of ink would move - of the content box, of each page of a spread, the
      gutter - is read so, one at a time (`Nudge`);
    - a window too narrow for a spread shows its pages one at a time, and a spread whose pages touch is split at the
      middle of its content box (`split_spread`), which lies off the middle of its paper - where the pages meet - when
      one page's ink keeps farther from its outer edge than the other's: each page of the spread is cut there by a
      few hundredths of its width, and the page alone is not. So a spread is also read split at its paper's middle
      (`_halves`), and a page alone cut at either side by each of the CUTS of its width (that finds the page the
      split cut short; the other page took in a strip of its neighbour, which the page alone does not have).

    None of the readings is kept by `analyze`'s shared analyses."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    h, w = gray.shape
    x0, _y0, x1, _y1 = capture_area(w, h, margins)
    paper = paper_box(gray, margins)
    if paper is None or paper[0] <= x0 or paper[2] >= x1:  # no ground seen beside it: the capture's width tells
        paper = paper_box(gray, (0, margins[1], 0, margins[3]))
    if paper is not None:
        px0, py0, px1, py1 = paper
        for side, top in ((0, 0), (SLIVER, 0), (GROUND, GROUND)):
            area = (max(0, px0 - side), max(0, py0 - top), max(0, w - px1 - side), max(0, h - py1 - top))
            if area != tuple(margins):
                yield _analyze(gray, area, True, None, rtl)
    moved: list[Nudge] = []
    units = _analyze(gray, margins, True, None, rtl, moved=moved)
    for nudge in moved:
        yield _analyze(gray, margins, True, None, rtl, nudge)
    if len(units) == 2 and paper is not None:
        halves = _halves(gray, margins, paper, rtl)
        if halves:
            yield halves
    elif len(units) == 1:
        x0, y0, x1, y1 = units[0].box
        for share in CUTS:
            cut = int(round(share * (x1 - x0)))
            for box in ((x0 + cut, y0, x1, y1), (x0, y0, x1 - cut, y1)):
                unit = _trimmed(gray, box, units[0].index)
                if unit is not None:
                    yield [unit]
