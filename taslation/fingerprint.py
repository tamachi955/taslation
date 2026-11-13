"""Page fingerprints: recognise *which* page is on screen without storing the page.

A fingerprint is 320 bits derived from the layout of ink on the page (a 16x16
difference hash plus an 8x8 average hash of the page's content box). It is
enough to tell the pages of one book apart and to recognise a page again at a
different window size, but it cannot be turned back into the picture. That is
what lets the translation cache work while deliberately *not* being an offline
copy of the book: without the real page in the viewer there is nothing to show.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    """One page as shown in the viewer (a two-page spread yields two units, right first)."""

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


def content_box(gray: np.ndarray, bright_threshold: int = 200, ink_threshold: int = 120,
                grow: bool = True) -> Box | None:
    """Bounding box of the page content inside a capture.

    First the paper is located: on a dark viewer background it is the union of
    the large non-background blobs, grown by the page's other blobs in line with
    it (`page_box`: the bubbles in black panels, not the viewer's toolbars and
    buttons); on a bright background it is where bright rows and columns are.
    Then the ink inside the paper gives the extent of the artwork. Coverage
    thresholds keep stray pixels from moving the box. *grow*: `page_box`'s.
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
    irows = _span(_counts(ink, 1) >= max(2, 0.003 * pw))
    icols = _span(_counts(ink, 0) >= max(2, 0.003 * ph))
    if irows is None or icols is None:
        return None  # blank page: nothing to read, nothing to fingerprint
    return (px0 + icols[0], py0 + irows[0], px0 + icols[1], py0 + irows[1])


def split_spread(gray: np.ndarray, box: Box, grow: bool = True) -> list[Box]:
    """Split a two-page spread at the gutter between the pages. Right page first.

    A gutter is a run of columns near the middle that carries no ink (white gap)
    or is perfectly uniform (viewer background). A false split on a single page
    is harmless: both the batch pass and the reading pass apply the same rule,
    so fingerprints still line up. *grow*: `page_box`'s, for each page's box.
    """
    x0, y0, x1, y1 = box
    crop = gray[y0:y1, x0:x1]
    h, w = crop.shape
    if w < 64 or h < 64:
        return [box]
    lo, hi = int(w * 0.35), int(w * 0.65)
    band = crop[:, lo:hi]
    ink_free = _counts(band < 120, 0) <= max(1, 0.002 * h)
    uniform = band.std(axis=0) < 4.0
    candidate = ink_free | uniform
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
            return [box]
        # A landscape unit without a visible gutter is a spread whose pages touch:
        # split it in the middle (right page first).
        gx0 = gx1 = w // 2
    else:
        gx0, gx1 = lo + best[0], lo + best[1]
    left_part = crop[:, :gx0]
    right_part = crop[:, gx1:]
    if (np.count_nonzero(left_part < 120) < 0.002 * left_part.size
            or np.count_nonzero(right_part < 120) < 0.002 * right_part.size):
        return [box]
    right_box = content_box(right_part, grow=grow) or (0, 0, right_part.shape[1], right_part.shape[0])
    left_box = content_box(left_part, grow=grow) or (0, 0, left_part.shape[1], left_part.shape[0])
    right = (x0 + gx1 + right_box[0], y0 + right_box[1], x0 + gx1 + right_box[2], y0 + right_box[3])
    left = (x0 + left_box[0], y0 + left_box[1], x0 + left_box[2], y0 + left_box[3])
    return [right, left]


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


def analyze(rgb: np.ndarray, margins: tuple[int, int, int, int] = (0, 0, 0, 0), grow: bool = True,
            known: dict[Box, str] | None = None) -> list[PageUnit]:
    """Locate the page(s) in a capture and fingerprint each one.

    Without *grow* the paper on a dark viewer is the large blobs' union alone (`page_box`), as analyze found it
    before 2026-10-31: the units, and so the fingerprints, that the caches kept before then hold for a page whose
    black panels the paper now grows through. Only recognising a book (`bookid.page_groups`) and a cache lookup that
    missed (`Pipeline._lookup_before`) look for those; what the pipeline keeps is fingerprinted with *grow*. *known*:
    the fingerprints of boxes of this very capture computed already (by box; the ones computed here are added), for a
    capture analyzed in several areas."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    x0, y0, x1, y1 = capture_area(gray.shape[1], gray.shape[0], margins)
    sub = gray[y0:y1, x0:x1]
    box = content_box(sub, grow=grow)
    if box is None:
        return []
    box = (box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0)
    units: list[PageUnit] = []
    for idx, b in enumerate(split_spread(gray, box, grow=grow)):
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
