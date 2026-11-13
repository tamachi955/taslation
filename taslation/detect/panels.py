"""Panels of a page, for the reading order: classical image processing, no model, nothing written to disk.

A page is cut along its gutters: runs of lines across the part looked at that are paper, or black on a page with
black gutters, from end to end (recursive XY-cut, across before down, so a row of panels stays together), and along
rules: dark straight lines right across, between panels that have no gutter. A blank stretch inside a framed panel
does not count: its lines end on the panel's frame. A page without gutters gives one panel, and the caller keeps the
rows of `order_regions`; so does a part of a page cut no further (art across a gutter).

A part with no straight gutter right across may have a slanted one: the division lines of a page's layout tree need
not be level (Tanaka et al., "Layout analysis of tree-structured scene frames in comic images", IJCAI 2007). The lines
from edge to edge of the part, rising or falling by up to `MAX_SLANT` of their length, are looked at the same way (a
run of them thick enough that are gutter or rule, a panel's worth on both sides), and the two pieces are cut further
like any part, what lies outside a piece counting as gutter. Their panels (`Panel`) keep the slanted sides, for which
panel a point is in, and the order of the cutting, which then is the reading order: their boxes overlap, and an order
of boxes would mix them up. A piece of a piece smaller than a panel either way is left out: a sliver between a slanted
gutter and a level one holds next to nothing. A slanted gutter runs between frames (`_framed`: ink near both edges of
its run along `FRAME_ALONG` of it), as the division lines of a layout tree do; on a page without frames a pale line
between two letterings of one balloon, which crosses only the outline, is none. On the 214 OpenMantra pages that took
the finder from 71.6 % of the gold panels to 76.8 % (precision 76.4 to 77.7 %), the gold boxes' order from 78.9 to
80.4 % of the pages right (4 pages better, 1 worse), at about 11 ms a page in place of 4.5 (median 8; the pages with
wide pale stretches up to about 90).

`find_panels` finds them, `order_panels` puts boxes (found or known) in reading order the same way, on the boxes alone
(in the order of the cutting when a found panel has a slanted side).
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from ..regions import Box

WORK_HEIGHT = 720  # px: pages are looked at no larger than this
PAPER_DROP = 30  # paper: this close to the page's brightest level
PAPER_MIN = 170
BLACK_MAX = 60  # black gutters
RULE_MAX = 80  # rules stay this dark once scaled down
MAX_FOREIGN = 0.04  # share of a gutter line that may be something else (the outline of a bubble across it)
RULE_FOREIGN = 0.08  # the same for a rule: a line drawn between two panels that have no gutter
LINE_END = 3  # px (work scale) at both ends of a gutter line that must be gutter: a panel's frame fails this
MIN_GUTTER = 0.004  # of the page's side
MIN_PANEL = 0.08  # of the page's side
OVERLAP = 0.08  # boxes ordered: of the shorter side, how far two may overlap and still be on two sides of a cut
MAX_SLANT = 0.27  # a slanted gutter rises or falls at most this much of its length (15 degrees)
SLANT_STEP = 3  # px (work scale) between the slants looked at, and between the points looked at along a line
SLANT_COARSE = 4  # every this many points first: a line far from gutter there is not looked at further
SLANT_INSIDE = 0.5  # of a slanted line's points at least this share inside the piece cut (no corner shaved off)
SLANT_REACH = 40  # px (work scale): the lines this near one that passed first are looked at in full
FRAME_REACH = 4 * SLANT_STEP  # px (work scale): a slanted gutter's frames lie this near the edges of its run
FRAME_ALONG = 0.3  # of its length on both sides (a line through a balloon between two letterings has none)


class Panel(tuple):
    """A panel `find_panels` found: its box (x0, y0, x1, y1) in image pixels, as a tuple; *sides* the slanted gutters
    that bound it, as (a, b, c) for a * x + b * y < c on its side, in image pixels (none for a rectangle); *rank* where
    it came in the cutting (`order_panels` takes that order when a panel has slanted sides): per cut, across or down
    and which part, top first and left first."""

    sides: tuple[tuple[float, float, float], ...]
    rank: tuple[tuple[bool, int], ...]

    def __new__(cls, box: Box, sides: tuple = (), rank: tuple = ()) -> Panel:
        self = super().__new__(cls, tuple(box))
        self.sides, self.rank = tuple(sides), tuple(rank)
        return self

    def holds(self, x: float, y: float) -> bool:
        """Whether the point lies in the panel: in its box and on its side of every slanted gutter."""
        return self[0] <= x < self[2] and self[1] <= y < self[3] and all(a * x + b * y < c for a, b, c in self.sides)


def _line_sums(sums: np.ndarray, rect: Box, across: bool) -> np.ndarray:
    """Pixels set per row (*across*) or column of *rect*, from a summed-area table."""
    x0, y0, x1, y1 = rect
    if across:
        return sums[y0 + 1:y1 + 1, x1] - sums[y0:y1, x1] - sums[y0 + 1:y1 + 1, x0] + sums[y0:y1, x0]
    return sums[y1, x0 + 1:x1 + 1] - sums[y1, x0:x1] - sums[y0, x0 + 1:x1 + 1] + sums[y0, x0:x1]


def _bridged(edges: list[int], i: int) -> bool:
    """Is this edge of a run (they alternate, starts and ends) one side of a gap of a line or two between runs?"""
    if i % 2:
        return i + 1 < len(edges) and edges[i + 1] - edges[i] <= 2
    return i > 0 and edges[i] - edges[i - 1] <= 2


_Side = tuple[float, float, float]
_Found = tuple[Box, tuple[_Side, ...], tuple[tuple[bool, int], ...]]  # box, slanted sides, rank (work scale)


class _Page:
    """A work-scale page in one polarity: *gutter* the colour of what lies between panels, *rule* the other one. A
    piece cut off by a slanted gutter is a page of its own: *inside* its pixels, *origin* where its array lies on the
    page, *like* the page whose sizes count."""

    def __init__(self, gutter: np.ndarray, rule: np.ndarray, inside: np.ndarray | None = None,
                 origin: tuple[int, int] = (0, 0), like: _Page | None = None) -> None:
        self.h, self.w = gutter.shape
        if inside is not None:
            gutter, rule = gutter | ~inside, rule & inside
        self.raw_gutter, self.raw_rule, self.inside, self.origin = gutter, rule, inside, origin
        self.gutter = cv2.integral(gutter.astype(np.uint8), sdepth=cv2.CV_32S)
        self.rule = cv2.integral(rule.astype(np.uint8), sdepth=cv2.CV_32S)
        if like is None:
            self.min_gutter = (max(2, round(MIN_GUTTER * self.h)), max(2, round(MIN_GUTTER * self.w)))
            self.min_panel = (MIN_PANEL * self.h, MIN_PANEL * self.w)
        else:
            self.min_gutter, self.min_panel = like.min_gutter, like.min_panel

    def gutter_lines(self, rect: Box, across: bool) -> np.ndarray:
        """Per row (*across*) or column of *rect*: gutter from end to end?"""
        x0, y0, x1, y1 = rect
        length = x1 - x0 if across else y1 - y0
        end = min(LINE_END, length)
        first = (x0, y0, x0 + end, y1) if across else (x0, y0, x1, y0 + end)
        last = (x1 - end, y0, x1, y1) if across else (x0, y1 - end, x1, y1)
        return ((_line_sums(self.gutter, rect, across) >= (1 - MAX_FOREIGN) * length)
                & (_line_sums(self.gutter, first, across) == end) & (_line_sums(self.gutter, last, across) == end))

    def trimmed(self, rect: Box) -> Box | None:
        """*rect* without the gutter lines round it, or None when nothing is left."""
        for _ in range(2):  # a side trimmed can shorten the lines of the other two
            x0, y0, x1, y1 = rect
            rows = np.flatnonzero(~self.gutter_lines(rect, True))
            if rows.size == 0:
                return None
            y0, y1 = y0 + int(rows[0]), y0 + int(rows[-1]) + 1
            cols = np.flatnonzero(~self.gutter_lines((x0, y0, x1, y1), False))
            if cols.size == 0:
                return None
            rect = (x0 + int(cols[0]), y0, x0 + int(cols[-1]) + 1, y1)
        return rect

    def cuts(self, rect: Box, across: bool) -> list[int]:
        """Where *rect* is cut: the middle of every run of gutter lines thick enough, or of a rule with or without
        gutter along it, that leaves a panel's worth on both sides. Pixels along the axis of the cut."""
        gutter = self.gutter_lines(rect, across)
        length = rect[2] - rect[0] if across else rect[3] - rect[1]
        rule = _line_sums(self.rule, rect, across) >= (1 - RULE_FOREIGN) * length
        flags = np.concatenate(([0], (gutter | rule).astype(np.int8), [0]))
        edges = np.flatnonzero(np.diff(flags)).tolist()
        edges = [e for i, e in enumerate(edges) if not _bridged(edges, i)]  # a frame's blurred edge splits no gutter
        start, stop = (rect[1], rect[3]) if across else (rect[0], rect[2])
        side = 0 if across else 1
        out: list[int] = []
        last = start
        for a, b in zip(edges[::2], edges[1::2]):
            if int(gutter[a:b].sum()) < self.min_gutter[side] and not rule[a:b].any():
                continue
            if start + a - last >= self.min_panel[side] and stop - (start + b) >= self.min_panel[side]:
                out.append(start + (a + b) // 2)
                last = start + b
        return out

    def slant(self, rect: Box, across: bool) -> tuple[int, int] | None:
        """The slanted cut of *rect* (`MAX_SLANT`), across or down: where its line meets the first edge and the last
        one (rows when *across*, columns otherwise, in *rect*), the middle of the thickest run of such lines that are
        gutter or rule nearly all along; None when there is none. Lines start and end on gutter (`LINE_END`); every
        `SLANT_COARSE`-th point of every line a run's thickness apart is looked at first, then all the points of the
        lines near those that passed."""
        x0, y0, x1, y1 = rect
        gutter = self.raw_gutter[y0:y1, x0:x1]
        code = gutter.astype(np.uint8) | (self.raw_rule[y0:y1, x0:x1].astype(np.uint8) << 1)
        code |= np.uint8(4) if self.inside is None else self.inside[y0:y1, x0:x1].astype(np.uint8) << 2
        if not across:
            gutter, code = gutter.T, code.T
        span, length = gutter.shape
        side = 0 if across else 1
        thick, room = self.min_gutter[side], self.min_panel[side]
        if span < 2 * room or length < 4 * SLANT_STEP:
            return None
        end = min(LINE_END, length)
        first, last = _runs_of(gutter[:, :end].all(1), thick), _runs_of(gutter[:, length - end:].all(1), thick)
        starts = np.flatnonzero(first)
        starts = starts[(starts >= room) & (starts <= span - room)]
        if starts.size < thick or int(last.sum()) < thick:
            return None
        along = np.arange(0, length, SLANT_STEP)
        frac = along / max(1, length - 1)
        coarse = np.arange(0, along.size, SLANT_COARSE)
        reach = int(MAX_SLANT * length)
        slants = np.arange(-(reach // SLANT_STEP) * SLANT_STEP, reach + 1, SLANT_STEP)
        slants = slants[slants != 0]  # level lines were looked at
        grid = starts[starts % thick == 0]  # a run of `thick` lines has one of these
        ends = grid[:, None] + slants[None, :]
        pairs = (ends >= room) & (ends <= span - room)  # a panel's worth on both sides
        pairs[pairs] = last[ends[pairs]]
        gi, si = np.nonzero(pairs)
        if gi.size == 0:
            return None
        rows = np.rint(grid[gi, None] + slants[si, None] * frac[None, coarse]).astype(np.intp)
        passed = _line_share(code, rows, along[coarse], 2 * MAX_FOREIGN, 2 * RULE_FOREIGN)
        # a run of T lines that pass holds T // thick lines of the grid, one after the other: at most (n + 1) * thick
        # - 1 lines where n of them passed in a row; the slants that may hold the thickest run come first
        bounds = []
        for k in np.unique(si[passed]):
            hits = grid[gi[passed & (si == k)]]
            steps = np.flatnonzero(np.diff(hits) != thick)
            chain = int(np.diff(np.concatenate(([-1], steps, [hits.size - 1]))).max())
            bounds.append(((chain + 1) * thick - 1, int(k), hits))
        bounds.sort(key=lambda b: (-b[0], b[1]))
        best: tuple[int, int, int] | None = None
        for bound, k, hits in bounds:
            if best is not None and bound <= best[0]:
                break
            d = int(slants[k])
            s = starts[(starts + d >= room) & (starts + d <= span - room)]
            s = s[last[s + d]]
            near = np.zeros(span + 1, np.int32)
            np.add.at(near, np.clip(hits - SLANT_REACH, 0, span), 1)
            np.add.at(near, np.clip(hits + SLANT_REACH + 1, 0, span), -1)
            s = s[np.cumsum(near)[s] > 0]
            rows = np.rint(s[:, None] + d * frac[None, coarse]).astype(np.intp)
            s = s[_line_share(code, rows, along[coarse], 2 * MAX_FOREIGN, 2 * RULE_FOREIGN)]
            if s.size < thick:
                continue
            rows = np.rint(s[:, None] + d * frac[None, :]).astype(np.intp)
            s = s[_line_share(code, rows, along, MAX_FOREIGN, RULE_FOREIGN)]
            if s.size < thick:
                continue
            breaks = np.flatnonzero(np.diff(s) != 1)
            for a, b in zip(np.concatenate(([0], breaks + 1)), np.concatenate((breaks + 1, [s.size]))):
                if b - a < thick:
                    continue
                mid = int(s[a] + s[b - 1]) // 2
                if min(mid, mid + d) < room or span - max(mid, mid + d) < room:
                    continue
                if not _framed(code, int(s[a]), int(s[b - 1]), d, frac, along):
                    continue
                if best is None or b - a > best[0]:
                    best = (int(b - a), mid, mid + d)
        return None if best is None else (best[1], best[2])

    def split(self, rect: Box, out: list[_Found], sides: tuple[_Side, ...] = (),
              rank: tuple[tuple[bool, int], ...] = ()) -> None:
        trimmed = self.trimmed(rect)
        if trimmed is None:
            return
        x0, y0, x1, y1 = trimmed
        if self.inside is not None and (x1 - x0 < self.min_panel[1] or y1 - y0 < self.min_panel[0]):
            return  # a sliver of a piece a slanted gutter cut off: what it holds is the next panel's
        cuts = self.cuts(trimmed, True)
        if cuts:
            edges = [y0, *cuts, y1]
            for i, (a, b) in enumerate(zip(edges, edges[1:])):
                self.split((x0, a, x1, b), out, sides, (*rank, (True, i)))
            return
        cuts = self.cuts(trimmed, False)
        if cuts:
            edges = [x0, *cuts, x1]
            for i, (a, b) in enumerate(zip(edges, edges[1:])):
                self.split((a, y0, b, y1), out, sides, (*rank, (False, i)))
            return
        for across in (True, False):
            line = self.slant(trimmed, across)
            if line is not None:
                self._split_slanted(trimmed, across, line, out, sides, rank)
                return
        ox, oy = self.origin
        out.append(((x0 + ox, y0 + oy, x1 + ox, y1 + oy), sides, rank))

    def _split_slanted(self, rect: Box, across: bool, line: tuple[int, int], out: list[_Found],
                       sides: tuple[_Side, ...], rank: tuple[tuple[bool, int], ...]) -> None:
        """*rect* cut along the slanted *line* (`slant`): each piece a page of its own, cut further (top or left one
        first)."""
        x0, y0, x1, y1 = rect
        ox, oy = self.origin
        if across:  # from (x0, y0 + first) to (x1 - 1, y0 + last)
            px, py, qx, qy = x0, y0 + line[0], x1 - 1, y0 + line[1]
        else:  # from (x0 + first, y0) to (x0 + last, y1 - 1)
            px, py, qx, qy = x0 + line[0], y0, x0 + line[1], y1 - 1
        dx, dy = qx - px, qy - py
        # top (across) or left (down) piece: a * x + b * y < c, in the page's work pixels
        a, b = (-dy, dx) if across else (dy, -dx)
        c = a * px + b * py
        yy, xx = np.mgrid[y0:y1, x0:x1]
        near_side = a * xx + b * yy < c
        here = np.ones_like(near_side) if self.inside is None else self.inside[y0:y1, x0:x1]
        g, r = self.raw_gutter[y0:y1, x0:x1], self.raw_rule[y0:y1, x0:x1]
        for i, (piece, side) in enumerate(((here & near_side, (a, b, c)), (here & ~near_side, (-a, -b, -c)))):
            if not piece.any():
                continue
            page = _Page(g, r, piece, (ox + x0, oy + y0), self)
            on_page = (float(side[0]), float(side[1]), float(side[2] + side[0] * ox + side[1] * oy))
            page.split((0, 0, x1 - x0, y1 - y0), out, (*sides, on_page), (*rank, (across, i)))


def _runs_of(flags: np.ndarray, n: int) -> np.ndarray:
    """*flags* without the runs of fewer than *n*."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], flags.astype(np.int8), [0]))))
    out = np.zeros_like(flags, dtype=bool)
    for a, b in zip(edges[::2], edges[1::2]):
        if b - a >= n:
            out[a:b] = True
    return out


def _framed(code: np.ndarray, low: int, high: int, d: int, frac: np.ndarray, along: np.ndarray) -> bool:
    """Whether the run of slanted lines from *low* to *high* (their rows of *code* at the first point, *d* further at
    the last one) has a frame along both sides: ink (neither gutter nor outside the piece) within `FRAME_REACH`
    lines beyond its edge at `FRAME_ALONG` of the points along it that are inside."""
    span = code.shape[0]
    shift = np.rint(d * frac).astype(np.intp)
    for edge, step in ((low, -1), (high, 1)):
        rows = edge + step * np.arange(1, FRAME_REACH + 1)[:, None] + shift[None, :]
        rows = np.clip(rows, 0, span - 1)
        seen = code[rows, along[None, :]]
        inside = ((seen & 4) > 0).any(axis=0)
        ink = ((seen & 5) == 4).any(axis=0)
        if np.count_nonzero(ink) < FRAME_ALONG * max(1, np.count_nonzero(inside)):
            return False
    return True


def _line_share(code: np.ndarray, rows: np.ndarray, along: np.ndarray, foreign: float,
                rule_foreign: float) -> np.ndarray:
    """Per line (its *rows* at the points *along* of *code*: 1 gutter, 2 rule, 4 inside the piece): gutter, or rule,
    at all but *foreign* (*rule_foreign*) of its points inside, with at least `SLANT_INSIDE` of them inside."""
    seen = code[rows, along[None, :]]
    n = np.count_nonzero(seen & 4, axis=1)
    g = np.count_nonzero((seen & 5) == 5, axis=1)
    r = np.count_nonzero((seen & 6) == 6, axis=1)
    return (n >= SLANT_INSIDE * along.size) & ((g >= (1 - foreign) * n) | (r >= (1 - rule_foreign) * n))


def find_panels(image: np.ndarray, box: Box | None = None, ignore: Sequence[Box] = ()) -> list[Panel]:
    """The panels of the page in *box* of *image* (RGB or gray; the whole image without *box*), in image pixels; at
    most one box when the page shows no gutters. What lies in the *ignore* boxes (the regions of text: a bubble may
    sit on a gutter) counts for any gutter."""
    x0, y0, x1, y1 = box if box is not None else (0, 0, image.shape[1], image.shape[0])
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape
    scale = min(1.0, WORK_HEIGHT / h)
    if scale < 1.0:
        gray = cv2.resize(gray, (max(1, round(w * scale)), WORK_HEIGHT), interpolation=cv2.INTER_AREA)
    wh, ww = gray.shape
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    bright = int(np.searchsorted(np.cumsum(hist), 0.98 * gray.size))
    paper, black, rule = gray >= max(PAPER_MIN, bright - PAPER_DROP), gray <= BLACK_MAX, gray <= RULE_MAX
    for bx0, by0, bx1, by1 in ignore:
        a, b = max(0, round((bx0 - x0) * scale)), max(0, round((by0 - y0) * scale))
        c, d = min(ww, round((bx1 - x0) * scale)), min(wh, round((by1 - y0) * scale))
        if c > a and d > b:
            paper[b:d, a:c] = black[b:d, a:c] = rule[b:d, a:c] = True
    found: list[_Found] = []
    _Page(paper, rule).split((0, 0, ww, wh), found)
    if len(found) < 2:  # no gutters of paper: black ones?
        on_black: list[_Found] = []
        _Page(black, np.zeros_like(black)).split((0, 0, ww, wh), on_black)
        if len(on_black) >= 2:
            found = on_black
    # a work pixel (u, v) is image pixel (x0 + u / scale, y0 + v / scale)
    return [Panel((x0 + round(a / scale), y0 + round(b / scale), x0 + round(c / scale), y0 + round(d / scale)),
                  tuple((sa * scale, sb * scale, sc + sa * scale * x0 + sb * scale * y0) for sa, sb, sc in sides), rank)
            for (a, b, c, d), sides, rank in found]


def _sides(boxes: Sequence[Box], low: int, high: int) -> list[float]:
    """Where boxes lying along an axis (their *low* and *high* coordinates) can be told apart: gaps, or overlaps of
    at most `OVERLAP` of the shorter of the two sides."""
    spans = sorted((b[low], b[high]) for b in boxes)
    first, end = spans[0]
    out: list[float] = []
    for a, b in spans[1:]:
        if a >= end - OVERLAP * min(b - a, end - first):
            out.append((a + end) / 2)
        end = max(end, b)
    return out


def _in_rows(panels: Sequence[Box], rtl: bool) -> list[Box]:
    """Panels no cut separates: rows of boxes that overlap by half of the shorter, right to left inside a row."""
    rows: list[list[Box]] = []
    for p in sorted(panels, key=lambda q: q[1]):
        for row in rows:
            y0, y1 = min(q[1] for q in row), max(q[3] for q in row)
            if min(p[3], y1) - max(p[1], y0) > 0.5 * min(p[3] - p[1], y1 - y0):
                row.append(p)
                break
        else:
            rows.append([p])
    rows.sort(key=lambda row: min(q[1] for q in row))
    return [p for row in rows for p in sorted(row, key=lambda q: -(q[0] + q[2]) if rtl else q[0] + q[2])]


def order_panels(panels: Sequence[Box], rtl: bool = True) -> list[Box]:
    """*panels* in reading order: recursive XY-cut on the boxes, top first, then right first (left first without *rtl*).
    Panels of one `find_panels` with a slanted side among them come in the order of the cutting, mirrored the same
    way."""
    if len(panels) < 2:
        return list(panels)
    if any(getattr(p, "sides", ()) for p in panels) and all(getattr(p, "rank", ()) for p in panels):
        return sorted(panels, key=lambda p: tuple(i if across or not rtl else -i for across, i in p.rank))
    cuts = _sides(panels, 1, 3)
    if cuts:
        top = [p for p in panels if (p[1] + p[3]) / 2 < cuts[0]]
        rest = [p for p in panels if (p[1] + p[3]) / 2 >= cuts[0]]
        if top and rest:
            return order_panels(top, rtl) + order_panels(rest, rtl)
    cuts = _sides(panels, 0, 2)
    if cuts:
        cut = cuts[-1] if rtl else cuts[0]
        near = [p for p in panels if ((p[0] + p[2]) / 2 >= cut) == rtl]
        far = [p for p in panels if ((p[0] + p[2]) / 2 >= cut) != rtl]
        if near and far:
            return order_panels(near, rtl) + order_panels(far, rtl)
    return _in_rows(panels, rtl)


def panel_of(panels: Sequence[Box], x: float, y: float) -> int:
    """Index of the panel a point belongs to: the smallest holding it (on its side of a slanted gutter, `Panel.holds`),
    else the nearest."""
    inside = [i for i, p in enumerate(panels) if (p.holds(x, y) if isinstance(p, Panel) and p.sides
                                                  else p[0] <= x < p[2] and p[1] <= y < p[3])]
    if inside:
        return min(inside, key=lambda i: (panels[i][2] - panels[i][0]) * (panels[i][3] - panels[i][1]))

    def distance(i: int) -> float:
        p = panels[i]
        return max(p[0] - x, 0, x - p[2]) ** 2 + max(p[1] - y, 0, y - p[3]) ** 2

    return min(range(len(panels)), key=distance)
