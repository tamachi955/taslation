"""Lettering set at a slant: how far a region's lettering is turned, and its pixels turned upright.

Most lettering stands straight: columns of vertical Japanese, rows of horizontal text. Some is set at a slant (a
shout across a panel, a caption tilted with its box, a column that follows a leaning bubble). The detectors find
the slanted lettering all the same - the boxes then hold it, and room round it - but the OCR reads crops of
upright text best (manga-ocr was trained with turns of up to about 5 degrees), and the translation set in straight
lines no longer follows the bubble.

The angle is found from the lettering's ink alone (`lettering_tilt`): the ink is turned through every angle in
``±MAX_TILT`` and projected onto both axes; at the lettering's own angle the projection across its lines (the
columns, or the rows) is the sharpest, with the ink piled into the lines and nothing between them. Of the two axes,
the one whose sharpness the turning changes the most is the one across the lines. (The same search as in other
manga tools, done here anew; the projections, not one rectangle round the ink, so that a block of several lines is
not mistaken for one line running the other way.) An angle within ``DEAD_ZONE`` counts as none, and so does one
the ink does not clearly show (``MIN_CONFIDENCE``): too few pieces, one glyph, a round shape. A region without a
slant takes the straight path of before, byte for byte.

A short word (two to four glyphs, a short column or row: too few pieces or too short lines for the search) is
measured as a text detector measures a line (`short_tilt`): the minimum-area rectangle round its ink, checked
against the axis of its ink's moments and the sharpest projection across it; only when all three agree is it slanted.
On OpenMantra, whose lettering stands straight, that calls 3 of its 390 short regions read as text slanted (0.8 %;
the long lines' search 4 of 1139), and of its two- to four-glyph words turned by 8 to 20 degrees it finds four in
ten, nine in ten of those within 2 degrees (most four-glyph words, few two-glyph ones: a small kana or a mark set off
the line pulls every measure, and the word then stays upright).

``angle`` is in degrees, counter-clockwise on the screen: the right end of a row is higher, the foot of a column
further right, for a positive angle. `Upright` turns a crop by ``-angle`` and maps its points back to the page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

DEAD_ZONE = 3.0  # degrees: a slant this small or smaller counts as none (other manga tools snap at 3 too; the OCR takes 5)
MAX_TILT = 45.0  # degrees either way searched (past 45 a row is a column turned the other way)
COARSE_STEP = 1.0  # degrees between the angles of the first search ...
FINE_STEP = 0.25  # ... and of the second, round the best of the first
MIN_CONFIDENCE = 0.15  # how much sharper the lettering is at its angle than upright, at the least (`lettering_tilt`)
MIN_PIECES = 5  # pieces of a glyph's size (`WHOLE_GLYPH` of it at least) the lettering needs to show a slant
WHOLE_GLYPH = 0.6
MIN_RUN = 3.0  # the lettering runs at least this many line widths along its lines
MAX_POINTS = 12000  # ink pixels the search looks at, at most (an even sample of them)
# A short word (`short_tilt`): fewer pieces or shorter lines than the gates above let through
SHORT_ELONGATION = 1.5  # its rectangle at least this many times as long as wide (a lone glyph or a square: no line)
SHORT_AGREE = 2.0  # degrees: the moments' axis and the sharpest projection within this of the rectangle's
SHORT_GAIN = 0.10  # the turned rectangle at least this much smaller than the upright box round the same ink
SHORT_SEARCH = 25.0  # degrees either way the projection across the line is searched


@dataclass(frozen=True)
class Tilt:
    """The slant of a region's lettering: *angle* (degrees, counter-clockwise; 0 = upright or not clear), how sure
    the measure is (*confidence*, 0..1: the share of the lines' sharpness the slant adds), and whether the lines are
    columns (*vertical*)."""

    angle: float = 0.0
    confidence: float = 0.0
    vertical: bool = True
    measured: float = 0.0  # the angle as measured, before the dead zone and the confidence had their say
    pieces: int = 0  # glyph-sized pieces measured
    run: float = 0.0  # how many glyphs long the lettering runs along its lines
    short: bool = False  # the angle is a short word's (`short_tilt`), not the long lines' search


def glyph_ink(ink: np.ndarray, glyph: float = 0.0) -> tuple[np.ndarray, int, float]:
    """The glyph-sized pieces of *ink* (bool): pieces of a line (an outline, speed lines) and specks left out. Also
    their number and the glyph size (*glyph*, or the pieces' own when it is 0)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros(ink.shape, bool), 0, glyph
    sizes = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]).astype(np.float64)
    areas = stats[1:, cv2.CC_STAT_AREA]
    if glyph <= 0:
        big = sizes[areas >= 6]
        glyph = float(np.percentile(big, 75)) if big.size else 0.0
    if glyph <= 0:
        return np.zeros(ink.shape, bool), 0, 0.0
    keep = (sizes <= 2.0 * glyph) & (areas >= 3)
    pieces = int(np.count_nonzero(keep & (sizes >= WHOLE_GLYPH * glyph)))
    lut = np.concatenate([[False], keep])
    return lut[labels], pieces, glyph


def _sharpness(points: np.ndarray, angle: float) -> tuple[float, float]:
    """How sharp the projections of *points* (N, 2: x, y about their centre) are, turned upright from *angle*: onto
    the x axis (across columns) and onto the y axis (across rows); the sum of the squared counts per pixel."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    u = points[:, 0] * c - points[:, 1] * s
    v = points[:, 0] * s + points[:, 1] * c
    hu = np.bincount(np.round(u - u.min()).astype(np.int64))
    hv = np.bincount(np.round(v - v.min()).astype(np.int64))
    return float(np.dot(hu, hu)), float(np.dot(hv, hv))


def _lines(across: np.ndarray) -> np.ndarray:
    """The widths of the lines of lettering, from the ink's positions *across* the lines (turned upright): the lines
    are the runs of the projection above a tenth of its peak."""
    hist = np.bincount(np.round(across - across.min()).astype(np.int64)).astype(np.float64)
    if hist.size < 3:
        return np.array([hist.size])
    hist = np.convolve(hist, np.ones(3) / 3.0, mode="same")
    on = hist > 0.1 * hist.max()
    edges = np.flatnonzero(np.diff(np.concatenate([[0], on.astype(np.int8), [0]])))
    runs = edges[1::2] - edges[0::2]
    return runs[runs >= 0.3 * runs.max()]  # (a dot or a stroke beside a line is no line)


def _line_width(across: np.ndarray) -> float:
    """The width of one line of lettering (`_lines`): the median line's."""
    return float(np.median(_lines(across)))


def _search(points: np.ndarray, lo: float, hi: float, step: float) -> list[tuple[float, float, float]]:
    count = int(round((hi - lo) / step)) + 1
    return [(lo + k * step, *_sharpness(points, lo + k * step)) for k in range(count)]


def lettering_tilt(ink: np.ndarray, glyph: float = 0.0) -> Tilt:
    """The slant of the lettering whose ink is *ink* (bool, the region's text box; only its glyph-sized pieces count,
    `glyph_ink`; *glyph*: their usual size, 0 = measured here).

    For each angle the ink is turned upright and projected onto both axes (`_sharpness`): across the lines the ink
    piles up into the lines at the lettering's angle, and along them into the glyphs set in step; the angle is where
    the product of the two sharpnesses peaks. The axis the turning sharpens the most is across the lines: *vertical*
    when that is the x axis. *confidence* is ``1 - upright / best``: 0 when the lettering is sharpest upright, near 1
    when the slant alone lines it up. The angle stays 0 within `DEAD_ZONE`, under `MIN_CONFIDENCE`, with fewer than
    `MIN_PIECES` pieces or lines shorter than `MIN_RUN` line widths (a short word: its glyphs' shapes, not its
    lines, decide the sharpest angle); such a short word is measured by `short_tilt` instead, and stays upright
    unless that finds its slant for sure."""
    pieces_ink, pieces, glyph = glyph_ink(ink, glyph)
    ys, xs = np.nonzero(pieces_ink)
    if pieces < MIN_PIECES or xs.size < 10 or glyph <= 0:
        return short_tilt(pieces_ink, pieces) or Tilt(pieces=pieces)
    if xs.size > MAX_POINTS:
        pick = np.linspace(0, xs.size - 1, MAX_POINTS).astype(np.int64)
        xs, ys = xs[pick], ys[pick]
    points = np.stack([xs - xs.mean(), ys - ys.mean()], axis=1).astype(np.float64)
    coarse = _search(points, -MAX_TILT, MAX_TILT, COARSE_STEP)
    upright = next(c for c in coarse if c[0] == 0.0)
    # the axis across the lines is the one the turning sharpens the most
    sweep_u = max(c[1] for c in coarse) / max(1.0, min(c[1] for c in coarse))
    sweep_v = max(c[2] for c in coarse) / max(1.0, min(c[2] for c in coarse))
    vertical = sweep_u >= sweep_v

    def score(c: tuple[float, float, float]) -> float:  # both axes: the lines, and the glyphs in step along them
        return c[1] * c[2]

    best = max(coarse, key=score)
    fine = _search(points, best[0] - COARSE_STEP, best[0] + COARSE_STEP, FINE_STEP)
    best = max([best, *fine], key=score)
    angle = float(best[0])
    confidence = max(0.0, 1.0 - score(upright) / score(best)) if score(best) > 0 else 0.0
    # how far the lettering runs along its lines, turned upright: a lone glyph or a square of them shows no slant
    a = math.radians(angle)
    u = points[:, 0] * math.cos(a) - points[:, 1] * math.sin(a)
    v = points[:, 0] * math.sin(a) + points[:, 1] * math.cos(a)
    along, across = (v, u) if vertical else (u, v)
    run = float(np.percentile(along, 98) - np.percentile(along, 2)) / max(1.0, _line_width(across))
    measured = angle
    if run < MIN_RUN:  # a short word: its lines too short for the search, the short word's own measure instead
        short = short_tilt(pieces_ink, pieces)
        if short is not None:
            return short
    if abs(angle) <= DEAD_ZONE or confidence < MIN_CONFIDENCE or run < MIN_RUN or abs(angle) >= MAX_TILT:
        angle = 0.0
    return Tilt(round(angle, 2), round(confidence, 3), vertical, round(measured, 2), pieces, round(run, 2))


def _line_angle(dx: float, dy: float) -> tuple[float, bool]:
    """A direction on the screen (*dx*, *dy*: pixels, y down) as a line of lettering: its angle (degrees,
    counter-clockwise: the foot of a column further right, the right end of a row higher) from the axis it is nearer,
    and whether that axis is the vertical one (a column)."""
    vertical = abs(dy) >= abs(dx)
    if vertical:
        if dy < 0:
            dx, dy = -dx, -dy
        return math.degrees(math.atan2(dx, dy)), True
    if dx < 0:
        dx, dy = -dx, -dy
    return math.degrees(math.atan2(-dy, dx)), False


def short_tilt(pieces_ink: np.ndarray, pieces: int) -> Tilt | None:
    """The slant of a short word (two to four glyphs, a short column or row) from its glyph-sized ink *pieces_ink*
    (`glyph_ink`; *pieces*: their number), or None when it shows none for sure.

    Too short for the projections' search, a word's slant is the direction of its line, measured three ways that
    err differently: the minimum-area rectangle round its ink (the line quad a text detector draws round a line, as in
    DBNet, PaddleOCR and the comic text detector), the principal axis of its ink's second moments (the image moments'
    orientation), and the angle where the projection across the line is the sharpest (`_sharpness`). The glyphs' own
    shapes pull each a little (a small kana set off the line's middle, a question mark), never all three the same way:
    the word is slanted only when the three agree within ``SHORT_AGREE``, its rectangle is clearly longer than wide
    (``SHORT_ELONGATION``) and fits the ink clearly tighter than the upright box (``SHORT_GAIN``), and their mean lies
    past `DEAD_ZONE`. The rectangle's angle is taken from its corners: OpenCV's own angle changed its convention in
    4.5.1. *confidence* is the share by which the turned rectangle is smaller than the upright box."""
    ys, xs = np.nonzero(pieces_ink)
    if pieces < 2 or xs.size < 10:
        return None
    if xs.size > MAX_POINTS:
        pick = np.linspace(0, xs.size - 1, MAX_POINTS).astype(np.int64)
        xs, ys = xs[pick], ys[pick]
    # the rectangle round the ink
    corners = cv2.boxPoints(cv2.minAreaRect(np.stack([xs, ys], axis=1).astype(np.float32)))
    e1, e2 = corners[1] - corners[0], corners[2] - corners[1]
    l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
    side, long_side, short_side = (e1, l1, l2) if l1 >= l2 else (e2, l2, l1)
    rect, vertical = _line_angle(float(side[0]), float(side[1]))
    box = float(xs.max() - xs.min()) * float(ys.max() - ys.min())
    gain = 1.0 - l1 * l2 / max(1.0, box)
    if long_side < SHORT_ELONGATION * max(1.0, short_side) or gain < SHORT_GAIN:
        return None
    # the moments' axis
    points = np.stack([xs - xs.mean(), ys - ys.mean()], axis=1).astype(np.float64)
    cov = points.T @ points / len(points)
    _values, vectors = np.linalg.eigh(cov)
    moments, moments_vertical = _line_angle(float(vectors[0, 1]), float(vectors[1, 1]))
    if moments_vertical is not vertical or abs(moments - rect) > SHORT_AGREE:
        return None
    # the sharpest projection across the line
    def across(c: tuple[float, float, float]) -> float:
        return c[1] if vertical else c[2]

    coarse = _search(points, -SHORT_SEARCH, SHORT_SEARCH, COARSE_STEP)
    best = max(coarse, key=across)
    best = max([best, *_search(points, best[0] - COARSE_STEP, best[0] + COARSE_STEP, FINE_STEP)], key=across)
    if abs(best[0] - rect) > SHORT_AGREE:
        return None
    angle = (rect + moments + best[0]) / 3.0
    if abs(angle) <= DEAD_ZONE or abs(angle) >= MAX_TILT:
        return None
    a = math.radians(angle)
    u = points[:, 0] * math.cos(a) - points[:, 1] * math.sin(a)
    v = points[:, 0] * math.sin(a) + points[:, 1] * math.cos(a)
    along, cross = (v, u) if vertical else (u, v)
    lines = _lines(cross)
    if len(lines) != 1:  # one line only: of two lines set off from each other, the block's edge is no line's
        return None
    run = float(np.percentile(along, 98) - np.percentile(along, 2)) / max(1.0, float(lines[0]))
    return Tilt(round(angle, 2), round(gain, 3), vertical, round(angle, 2), pieces, round(run, 2), short=True)


def region_ink(rgb: np.ndarray, mask: np.ndarray, box: tuple[int, int, int, int], origin: tuple[int, int],
               dark_threshold: int = 140, dark: bool = False) -> np.ndarray:
    """The ink of the lettering in *box* (page coordinates) of a region whose *mask* starts at *origin*: the pixels
    darker than *dark_threshold* (lighter than its mirror on a *dark* ground) inside the mask, in the box's frame
    (what of the box lies past the mask or the page is no ink)."""
    x0, y0, x1, y1 = box
    ox, oy = origin
    h, w = rgb.shape[:2]
    out = np.zeros((max(0, y1 - y0), max(0, x1 - x0)), bool)
    cx0, cy0 = max(x0, ox, 0), max(y0, oy, 0)
    cx1, cy1 = min(x1, ox + mask.shape[1], w), min(y1, oy + mask.shape[0], h)
    if cx1 <= cx0 or cy1 <= cy0:
        return out
    gray = cv2.cvtColor(np.ascontiguousarray(rgb[cy0:cy1, cx0:cx1, :3]), cv2.COLOR_RGB2GRAY)
    ink = (gray > 255 - dark_threshold) if dark else (gray < dark_threshold)
    out[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] = ink & (mask[cy0 - oy:cy1 - oy, cx0 - ox:cx1 - ox] > 0)
    return out


class Upright:
    """A crop turned by ``-angle`` (counter-clockwise *angle* undone), with the room it needs, and the way back: page
    points of the crop to the upright picture (`forward`) and back (`back`)."""

    def __init__(self, shape: tuple[int, int], angle: float, origin: tuple[int, int] = (0, 0)):
        h, w = shape[:2]
        self.angle = angle
        self.origin = origin
        m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -angle, 1.0)
        a = math.radians(angle)
        c, s = abs(math.cos(a)), abs(math.sin(a))
        self.width, self.height = int(math.ceil(w * c + h * s)), int(math.ceil(w * s + h * c))
        m[0, 2] += self.width / 2.0 - w / 2.0
        m[1, 2] += self.height / 2.0 - h / 2.0
        self.matrix = m  # crop -> upright
        self.inverse = cv2.invertAffineTransform(m)  # upright -> crop

    def turn(self, image: np.ndarray, fill: int | tuple[int, ...] = 255, nearest: bool = False) -> np.ndarray:
        """*image* (the crop's size) turned upright, the room round it *fill*."""
        flags = cv2.INTER_NEAREST if nearest else cv2.INTER_CUBIC
        return cv2.warpAffine(image, self.matrix, (self.width, self.height), flags=flags,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=fill)

    def turn_back(self, image: np.ndarray, size: tuple[int, int], fill: int | tuple[int, ...] = 0,
                  nearest: bool = False) -> np.ndarray:
        """An upright *image* turned back into the crop's frame (*size*: width, height)."""
        flags = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR
        return cv2.warpAffine(image, self.inverse, size, flags=flags, borderMode=cv2.BORDER_CONSTANT,
                              borderValue=fill)

    def forward(self, x: float, y: float) -> tuple[float, float]:
        """A page point in the upright picture."""
        m = self.matrix
        x, y = x - self.origin[0], y - self.origin[1]
        return m[0, 0] * x + m[0, 1] * y + m[0, 2], m[1, 0] * x + m[1, 1] * y + m[1, 2]

    def forward_box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        """The box of the upright picture round a page box (its four corners turned)."""
        x0, y0, x1, y1 = box
        pts = [self.forward(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        return (max(0, int(math.floor(min(p[0] for p in pts)))), max(0, int(math.floor(min(p[1] for p in pts)))),
                min(self.width, int(math.ceil(max(p[0] for p in pts)))),
                min(self.height, int(math.ceil(max(p[1] for p in pts)))))

    def back(self, x: float, y: float) -> tuple[float, float]:
        """A point of the upright picture on the page."""
        m = self.inverse
        return (self.origin[0] + m[0, 0] * x + m[0, 1] * y + m[0, 2],
                self.origin[1] + m[1, 0] * x + m[1, 1] * y + m[1, 2])

    def back_box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        """The page box round a box of the upright picture (its four corners turned back)."""
        x0, y0, x1, y1 = box
        pts = [self.back(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        return (int(math.floor(min(p[0] for p in pts))), int(math.floor(min(p[1] for p in pts))),
                int(math.ceil(max(p[0] for p in pts))), int(math.ceil(max(p[1] for p in pts))))


def turned_corners(box: tuple[float, float, float, float], angle: float) -> list[tuple[float, float]]:
    """The four corners of *box* turned by *angle* (counter-clockwise on the screen) about its centre: the outline of
    a slanted frame whose upright size is the box's."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    out = []
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        dx, dy = x - cx, y - cy
        out.append((cx + dx * c + dy * s, cy - dx * s + dy * c))
    return out


def ink_frame(ink: np.ndarray, angle: float) -> tuple[float, float, float, float]:
    """The box of *ink* (bool, a crop) in the upright picture `Upright` turns the crop into: the lettering's own
    frame, without the room the slant left round it in the crop's box."""
    turn = Upright(ink.shape, angle)
    ys, xs = np.nonzero(ink)
    if not xs.size:
        return (0.0, 0.0, float(turn.width), float(turn.height))
    m = turn.matrix
    u = m[0, 0] * xs + m[0, 1] * ys + m[0, 2]
    v = m[1, 0] * xs + m[1, 1] * ys + m[1, 2]
    return float(u.min()), float(v.min()), float(u.max()) + 1.0, float(v.max()) + 1.0
