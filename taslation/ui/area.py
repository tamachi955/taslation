"""Rectangles a pointer takes hold of: the capture area of the Set area dialog and the regions of translator mode.

Margins and boxes, the eight handles that resize a box, moving it, drawing a new one, a turned frame's handles and
its rotate handle (the round one over the middle of its top side, as a word processor's shapes have), the angle a
drag of that handle sets, whether a point is inside a turned frame, several regions moved together and those a rubber
band takes in (translator mode's selection of several), the change between the
canvas's pixels and the image's for a picture fitted into a window (kept clear of the canvas's edges so that handles
there show whole), where a region's label goes so that it covers no other region (`place_label`), and groups of
controls flowing into rows (the window's toolbar). Pure geometry, tested without a display.
"""

from __future__ import annotations

import math
from typing import Sequence

Box = tuple[int, int, int, int]  # left, top, right, bottom in image pixels (right and bottom exclusive)
Margins = tuple[int, int, int, int]  # pixels left out at the left, top, right and bottom of a capture
Size = tuple[int, int]  # width, height
Point = tuple[float, float]

HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
REACH = 7  # how near (canvas pixels) a press must come to a handle or a side to take hold of it
HANDLE = 8  # a handle's side in canvas pixels; a picture whose edges carry handles is drawn this far inside its canvas
MIN_AREA = 24  # the capture area's shortest side, in image pixels
MIN_REGION = 8  # a region's shortest side, in image pixels (a smaller rectangle is not added either)
CURSORS = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw", "n": "size_ns",
           "s": "size_ns", "e": "size_we", "w": "size_we", "move": "fleur", None: "crosshair"}  # Windows cursors
ROTATE_CURSORS = ("exchange", "circle")  # over the rotate handle: the first this Tk has (circling arrows, a ring)
ROTATE_GAP = 20  # canvas pixels from the middle of a frame's top side to the middle of its rotate handle
ROTATE_RADIUS = 5  # the rotate handle's radius, in canvas pixels
ROTATE_REACH = 9  # how near (canvas pixels) to the rotate handle's middle a press takes hold of it
SNAP_STEP = 15.0  # degrees: the steps a rotation takes with Shift held
SNAP_ZERO = 3.0  # degrees: a rotation this near upright is upright (`detect.tilt.DEAD_ZONE`)
MAX_TURN = 89.0  # degrees either way a frame may be turned (the cache and the lettering take |angle| < 90)
Corners = list[Point]  # a frame's four corners: top left, top right, bottom right, bottom left (in its own up)


def _limit(value: float, low: float, high: float) -> int:
    return int(round(max(low, min(high, value))))


def margins_to_box(margins: Margins, size: Size) -> Box:
    """The part of a capture of *size* that *margins* leave, as the pipeline reads it (at least one pixel)."""
    width, height = size
    left, top, right, bottom = (max(0, int(m)) for m in margins)
    x0, y0 = min(left, width - 1), min(top, height - 1)
    return (x0, y0, max(x0 + 1, width - right), max(y0 + 1, height - bottom))


def box_to_margins(box: Box, size: Size) -> Margins:
    """The margins that leave *box* of a capture of *size*."""
    x0, y0, x1, y1 = clamp(box, size)
    return (x0, y0, size[0] - x1, size[1] - y1)


def clamp(box: tuple[float, float, float, float], size: Size) -> Box:
    """*box* in whole pixels, its corners in order and inside an image of *size*."""
    width, height = size
    xa, xb = sorted((_limit(box[0], 0, width), _limit(box[2], 0, width)))
    ya, yb = sorted((_limit(box[1], 0, height), _limit(box[3], 0, height)))
    return (xa, ya, xb, yb)


def handles(box: tuple[float, float, float, float]) -> dict[str, Point]:
    """Where the eight handles of *box* are: its corners and the middles of its sides."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {"nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0), "e": (x1, cy),
            "se": (x1, y1), "s": (cx, y1), "sw": (x0, y1), "w": (x0, cy)}


def grip_at(box: tuple[float, float, float, float], x: float, y: float, reach: float = REACH) -> str | None:
    """What a press at (x, y) takes hold of, in the coordinates of *box*: a handle (corners first), a side (as its
    middle handle), "move" inside the box, or None outside it. On a small box the reach shrinks, so that its
    middle still moves it."""
    x0, y0, x1, y1 = box
    reach = min(reach, max(2.0, min(x1 - x0, y1 - y0) / 4))
    points = handles(box)
    for name in ("nw", "ne", "se", "sw", "n", "e", "s", "w"):
        px, py = points[name]
        if abs(x - px) <= reach and abs(y - py) <= reach:
            return name
    if x0 <= x <= x1:
        if abs(y - y0) <= reach:
            return "n"
        if abs(y - y1) <= reach:
            return "s"
    if y0 <= y <= y1:
        if abs(x - x0) <= reach:
            return "w"
        if abs(x - x1) <= reach:
            return "e"
    return "move" if x0 < x < x1 and y0 < y < y1 else None


def resize(box: Box, handle: str, dx: float, dy: float, size: Size, min_size: int) -> Box:
    """*box* with the sides *handle* holds moved by (dx, dy) image pixels, inside the image and at least
    *min_size* wide and high: a side stops short of the opposite one instead of passing it."""
    width, height = size
    min_w, min_h = min(min_size, width), min(min_size, height)
    x0, y0, x1, y1 = box
    if "w" in handle:
        x0 = _limit(x0 + dx, 0, max(0, x1 - min_w))
    if "e" in handle:
        x1 = _limit(x1 + dx, min(width, x0 + min_w), width)
    if "n" in handle:
        y0 = _limit(y0 + dy, 0, max(0, y1 - min_h))
    if "s" in handle:
        y1 = _limit(y1 + dy, min(height, y0 + min_h), height)
    return (x0, y0, x1, y1)


def move(box: Box, dx: float, dy: float, size: Size) -> Box:
    """*box* shifted by (dx, dy) image pixels, stopping at the image's edges; its size stays."""
    width, height = size
    x0, y0, x1, y1 = box
    w, h = min(x1 - x0, width), min(y1 - y0, height)
    nx, ny = _limit(x0 + dx, 0, width - w), _limit(y0 + dy, 0, height - h)
    return (nx, ny, nx + w, ny + h)


def drag(box: Box, grip: str | None, start: Point, now: Point, size: Size, min_size: int) -> Box:
    """*box* after a drag from *start* to *now* (image pixels) holding *grip*: a handle resizes it, "move" moves
    it, None draws a new box from *start*."""
    dx, dy = now[0] - start[0], now[1] - start[1]
    if grip == "move":
        return move(box, dx, dy, size)
    if grip in HANDLES:
        return resize(box, grip, dx, dy, size, min_size)
    return clamp((start[0], start[1], now[0], now[1]), size)


def box_corners(box: tuple[float, float, float, float]) -> Corners:
    """The four corners of an upright *box*, in the order of a turned frame's."""
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def frame_axes(corners: Corners) -> tuple[Point, Point, float, float]:
    """A frame's own axes: the unit vector along its top side (its "right"), the one down its left side (its
    "down"), its width and its height. A frame with no width or height takes the page's axes for them."""
    (ax, ay), (bx, by), _c, (dx, dy) = corners
    w, h = math.hypot(bx - ax, by - ay), math.hypot(dx - ax, dy - ay)
    right = ((bx - ax) / w, (by - ay) / w) if w > 1e-9 else (1.0, 0.0)
    down = ((dx - ax) / h, (dy - ay) / h) if h > 1e-9 else (-right[1], right[0])
    return right, down, w, h


def frame_angle(corners: Corners) -> float:
    """How far a frame is turned, in degrees counter-clockwise on the screen (`TextRegion.angle`)."""
    right = frame_axes(corners)[0]
    return math.degrees(math.atan2(-right[1], right[0]))


def frame_centre(corners: Corners) -> Point:
    return (sum(x for x, _y in corners) / 4.0, sum(y for _x, y in corners) / 4.0)


def frame_handles(corners: Corners) -> dict[str, Point]:
    """Where the eight handles of a frame are, named in its own directions: its corners and the middles of its
    sides. An upright frame's are `handles` of its box."""
    tl, tr, br, bl = corners

    def mid(a: Point, b: Point) -> Point:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    return {"nw": tl, "n": mid(tl, tr), "ne": tr, "e": mid(tr, br), "se": br, "s": mid(br, bl), "sw": bl,
            "w": mid(bl, tl)}


def rotate_handle(corners: Corners, gap: float = ROTATE_GAP, room: tuple[float, float, float, float] | None = None
                  ) -> tuple[Point, Point]:
    """The rotate handle of a frame (canvas pixels): where its stalk leaves the frame, the middle of the top side,
    and the handle's middle, *gap* further on in the frame's own up, so that it turns with the frame. When that
    lies outside *room* (the canvas: a region at the top of the page) it goes under the bottom side instead."""
    down = frame_axes(corners)[1]
    points = frame_handles(corners)
    (nx, ny), (sx, sy) = points["n"], points["s"]
    knob = (nx - down[0] * gap, ny - down[1] * gap)
    if room is not None and not (room[0] <= knob[0] <= room[2] and room[1] <= knob[1] <= room[3]):
        under = (sx + down[0] * gap, sy + down[1] * gap)
        if room[0] <= under[0] <= room[2] and room[1] <= under[1] <= room[3]:
            return (sx, sy), under
    return (nx, ny), knob


def grip_on_frame(corners: Corners, x: float, y: float, reach: float = REACH,
                  room: tuple[float, float, float, float] | None = None) -> str | None:
    """What a press at (x, y) takes hold of on a frame (canvas pixels): "rotate" on its rotate handle, else what
    `grip_at` finds in the frame's own axes - a handle named in the frame's own directions, a side, "move" inside
    the frame, None outside it. An upright frame's are `grip_at`'s of its box."""
    knob = rotate_handle(corners, room=room)[1]
    if math.hypot(x - knob[0], y - knob[1]) <= ROTATE_REACH:
        return "rotate"
    right, down, w, h = frame_axes(corners)
    ox, oy = corners[0]
    px, py = x - ox, y - oy
    return grip_at((0.0, 0.0, w, h), px * right[0] + py * right[1], px * down[0] + py * down[1], reach)


# a handle's way from the middle of its frame, in the frame's own axes (x right, y down)
_HANDLE_WAYS = {"n": (0, -1), "ne": (1, -1), "e": (1, 0), "se": (1, 1), "s": (0, 1), "sw": (-1, 1), "w": (-1, 0),
                "nw": (-1, -1)}


def page_handle(name: str, corners: Corners) -> str:
    """The handle of the upright box that the handle *name* of a turned frame stands for: the one whose way from
    the middle is nearest the way the turned handle points on the page. An upright frame's handle is itself; a
    frame turned by 90 degrees has its "n" handle on the page's left ("w")."""
    if name not in _HANDLE_WAYS:
        return name
    right, down, _w, _h = frame_axes(corners)
    hx, hy = _HANDLE_WAYS[name]
    at = math.atan2(hx * right[1] + hy * down[1], hx * right[0] + hy * down[0])

    def off(other: str) -> float:
        ox, oy = _HANDLE_WAYS[other]
        d = abs(at - math.atan2(oy, ox)) % (2 * math.pi)
        return min(d, 2 * math.pi - d)

    return min(_HANDLE_WAYS, key=lambda other: (round(off(other), 9), other != name))


def inside_frame(corners: Corners, x: float, y: float) -> bool:
    """Whether the point (x, y) lies inside the frame through *corners* (its edges included), in the frame's own
    axes: inside a turned frame, not merely inside the box round it."""
    right, down, w, h = frame_axes(corners)
    ox, oy = corners[0]
    px, py = x - ox, y - oy
    across, along = px * right[0] + py * right[1], px * down[0] + py * down[1]
    return 0.0 <= across <= w and 0.0 <= along <= h


def shift_within(boxes: Sequence[Box], dx: float, dy: float, size: Size) -> tuple[int, int]:
    """How far *boxes* (several regions moved together) go for a move by (dx, dy) image pixels: all of them by the
    same amount, stopping where the first of them meets the image's edge, so that their places among each other stay
    (`move` of the box round them all). (0, 0) for no boxes."""
    if not boxes:
        return (0, 0)
    whole = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    moved = move(whole, dx, dy, size)
    return (moved[0] - whole[0], moved[1] - whole[1])


def boxes_within(band: tuple[float, float, float, float], boxes: Sequence[Sequence[float]]) -> list[int]:
    """The places in *boxes* of those that lie wholly inside *band* (a rubber band dragged over them; its corners in
    any order), as an office program selects the shapes a band takes in."""
    x0, x1 = sorted((band[0], band[2]))
    y0, y1 = sorted((band[1], band[3]))
    return [i for i, b in enumerate(boxes) if x0 <= b[0] and y0 <= b[1] and b[2] <= x1 and b[3] <= y1]


def turn_corners(corners: Corners, degrees: float, about: Point | None = None) -> Corners:
    """*corners* turned by *degrees* counter-clockwise on the screen about *about* (None: their middle)."""
    cx, cy = about if about is not None else frame_centre(corners)
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c + (y - cy) * s, cy - (x - cx) * s + (y - cy) * c) for x, y in corners]


def shift_corners(corners: Corners, dx: float, dy: float) -> Corners:
    return [(x + dx, y + dy) for x, y in corners]


def full_frame(box: tuple[float, float, float, float], angle: float) -> Corners:
    """The frame a box filled whole (a rectangle of the reader's) is lettered in at *angle*: the box round the box
    turned upright, turned back about its middle (`render.slant.slanted_outline` of such a region, without its
    pixels)."""
    if not angle:
        return box_corners(box)
    x0, y0, x1, y1 = box
    a = math.radians(angle)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    w, h = x1 - x0, y1 - y0
    fw, fh = w * c + h * s, w * s + h * c
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return turn_corners(box_corners((cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2)), angle, (cx, cy))


def pointer_angle(centre: Point, point: Point) -> float:
    """The way from *centre* to *point* (canvas pixels), in degrees counter-clockwise from straight up: the angle of
    a frame whose rotate handle is at *point*."""
    return math.degrees(math.atan2(-(point[0] - centre[0]), -(point[1] - centre[1])))


def turn_angle(start: float, centre: Point, press: Point, now: Point, steps: bool = False) -> float:
    """The angle a drag of the rotate handle sets: the frame's angle at the press (*start*) turned as far as the
    pointer went round *centre* from *press* to *now* (counter-clockwise positive), as `snap_angle` gives it."""
    angle = start + pointer_angle(centre, now) - pointer_angle(centre, press)
    return snap_angle((angle + 180.0) % 360.0 - 180.0, steps)


def snap_angle(angle: float, steps: bool = False) -> float:
    """*angle* (degrees, within -180..180) in whole degrees: with *steps* (Shift) at the nearest `SNAP_STEP`, else
    upright within `SNAP_ZERO` of it; never past `MAX_TURN` either way."""
    if steps:
        angle = SNAP_STEP * round(angle / SNAP_STEP)
    elif abs(angle) <= SNAP_ZERO:
        angle = 0.0
    return float(round(max(-MAX_TURN, min(MAX_TURN, angle)))) + 0.0  # (+ 0.0: never -0.0)


def big_enough(box: Box, min_size: int) -> bool:
    return box[2] - box[0] >= min_size and box[3] - box[1] >= min_size


def to_image(x: float, y: float, scale: float, offset: Point) -> Point:
    """A point of the canvas in image pixels, for a picture drawn at *offset* with *scale* (not clamped)."""
    scale = scale if scale > 0 else 1.0
    return ((x - offset[0]) / scale, (y - offset[1]) / scale)


def to_canvas(x: float, y: float, scale: float, offset: Point) -> Point:
    """A point of the image in the canvas's pixels."""
    return (offset[0] + x * scale, offset[1] + y * scale)


def box_to_canvas(box: tuple[float, float, float, float], scale: float, offset: Point) -> tuple[float, float, float, float]:
    (x0, y0), (x1, y1) = to_canvas(box[0], box[1], scale, offset), to_canvas(box[2], box[3], scale, offset)
    return (x0, y0, x1, y1)


def outside(box: tuple[float, float, float, float], frame: tuple[float, float, float, float]
            ) -> list[tuple[float, float, float, float]]:
    """The parts of *frame* that *box* leaves out (above, below, left, right; empty ones skipped)."""
    fx0, fy0, fx1, fy1 = frame
    x0, y0 = max(fx0, min(fx1, box[0])), max(fy0, min(fy1, box[1]))
    x1, y1 = max(x0, min(fx1, box[2])), max(y0, min(fy1, box[3]))
    parts = [(fx0, fy0, fx1, y0), (fx0, y1, fx1, fy1), (fx0, y0, x0, y1), (x1, y0, fx1, y1)]
    return [p for p in parts if p[2] > p[0] and p[3] > p[1]]


def fit(size: Size, room: Size, inset: int = 0, enlarge: bool = False) -> tuple[Size, Point]:
    """How a picture of *size* is drawn in a canvas of *room* that keeps *inset* pixels clear on every side: its
    drawn size (its aspect kept; never larger than it is unless *enlarge*) and where its top-left corner goes, in the
    middle of the canvas."""
    width, height = max(1, size[0]), max(1, size[1])
    space_w, space_h = max(1, room[0] - 2 * inset), max(1, room[1] - 2 * inset)
    scale = min(space_w / width, space_h / height)
    if not enlarge:
        scale = min(scale, 1.0)
    drawn = (max(1, int(width * scale)), max(1, int(height * scale)))
    return drawn, ((room[0] - drawn[0]) // 2, (room[1] - drawn[1]) // 2)


def flow(sizes: Sequence[Size], width: float, gap: int = 0, row_gap: int = 0) -> tuple[list[tuple[int, int]], int, int]:
    """Items of *sizes* laid out left to right in rows of *width*, *gap* apart: a new row starts whenever the next
    item would not fit (an item wider than a row gets a row of its own, never a cut), and each item sits in the
    middle of its row's height. Returns every item's place (x, y), the height of the rows with *row_gap* between
    them, and how many rows there are."""
    rows: list[list[int]] = [[]]
    x = 0
    for i, (w, _h) in enumerate(sizes):
        if rows[-1] and x + w > width:
            rows.append([])
            x = 0
        rows[-1].append(i)
        x += w + gap
    places = [(0, 0)] * len(sizes)
    y = 0
    filled = [row for row in rows if row]
    for row in filled:
        height = max(sizes[i][1] for i in row)
        x = 0
        for i in row:
            w, h = sizes[i]
            places[i] = (x, y + (height - h) // 2)
            x += w + gap
        y += height + row_gap
    return places, (y - row_gap if filled else 0), len(filled)


# ---------------------------------------------------------------------------------------------- the page on show
PLAIN_RING = 0.9  # a side of a frame is plain when this share of its edge is the ground colour (within GROUND_SPREAD)
GROUND_SPREAD = 24  # grey levels a pixel of the ground may differ from the ground's level
TRIM_PAD = 0.012  # of the frame's longer side: how much of the ground is left round the page drawn
TRIM_GAIN = 0.85  # the page is drawn alone only when it takes at most this share of the frame's area ...
TRIM_LEAST = 0.15  # ... and at least this share of its width and of its height (else it is not a page)
TRIM_WORK = 960  # the frame is looked at this many pixels across at most (a page panel is large)


def page_bounds(image) -> Box | None:
    """Where the page is on a frame whose ground round it is plain - dark (a full-screen viewer's black or grey) or
    light (white) -, in the frame's pixels and with a little of the ground left round it (`TRIM_PAD`): what the window
    draws of the frame so that the page itself shows large. On a dark ground the page is the paper (`fingerprint.
    page_box`: the large blobs, the bubbles in line with them, never the viewer's bars, buttons and page counter), on a
    light one what is not ground, small specks left out. A two-page spread is one box over both pages. None when the
    ground is not plain on two opposite sides of the frame (a desktop, a browser's toolbars), when no page is found, or when the page fills
    the frame nearly whole (`TRIM_GAIN`): the frame is drawn as it is then."""
    import cv2
    import numpy as np

    from .. import fingerprint as fp

    rgb = np.asarray(image)
    if rgb.ndim == 3:
        gray = cv2.cvtColor(np.ascontiguousarray(rgb[..., :3]), cv2.COLOR_RGB2GRAY)
    else:
        gray = np.ascontiguousarray(rgb)
    if gray.dtype != np.uint8:
        gray = np.clip(gray, 0, 255).astype(np.uint8)
    height, width = gray.shape[:2]
    if width < 32 or height < 32:
        return None
    f = max(1.0, max(width, height) / TRIM_WORK)
    small = gray if f == 1.0 else cv2.resize(gray, (max(8, int(width / f)), max(8, int(height / f))),
                                             interpolation=cv2.INTER_AREA)
    sh, sw = small.shape
    ground = fp.background_level(small)

    def plain(side: np.ndarray) -> bool:
        return bool(np.mean(np.abs(side.astype(np.int16) - ground) <= GROUND_SPREAD) >= PLAIN_RING)

    # the ground shows plain on two opposite sides at least (a page fitted to the height touches the top and bottom)
    if not ((plain(small[:, :2]) and plain(small[:, -2:])) or (plain(small[:2]) and plain(small[-2:]))):
        return None
    if ground < 128:
        box = fp.page_box(small, bg=ground)
    else:
        off = (np.abs(small.astype(np.int16) - ground) > GROUND_SPREAD).astype(np.uint8)
        off = cv2.morphologyEx(off, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        x, y, w, h = cv2.boundingRect(off)
        box = (x, y, x + w, y + h) if w and h else None
    if box is None:
        return None
    x0, y0, x1, y1 = box
    if x1 - x0 < TRIM_LEAST * sw or y1 - y0 < TRIM_LEAST * sh:
        return None
    pad = TRIM_PAD * max(width, height)
    out = clamp((x0 * f - pad, y0 * f - pad, x1 * f + pad, y1 * f + pad), (width, height))
    if (out[2] - out[0]) * (out[3] - out[1]) > TRIM_GAIN * width * height:
        return None
    return out


def joined(a: Box | None, b: Box | None) -> Box | None:
    """The box that holds both *a* and *b* (either may be None)."""
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


LABEL_GAP = 3  # canvas pixels between a region's outline and its label
LABEL_GRAZE = 0.25  # an outside place that covers at most this share of the label beats a place inside the region


def _overlap(a: Sequence[float], b: Sequence[float]) -> float:
    """The area two boxes (left, top, right, bottom) have in common."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def place_label(size: tuple[float, float], box: Sequence[float], others: Sequence[Sequence[float]],
                bounds: Sequence[float], gap: float = LABEL_GAP) -> tuple[float, float]:
    """Where a region's label of *size* (width, height) goes, its top left corner (canvas pixels): just outside the
    region's *box* where it covers none of the *others* (the other regions and the labels already placed) and stays
    within *bounds* (the picture), in this order - above it at its left, above at its right, below at its left, below
    at its right, beside it on the left, beside it on the right; where every one of them covers something, the one
    that covers least, when that is no more than a corner of the label (`LABEL_GRAZE`), else just inside the region's
    top left corner when that covers less (it covers the region's own lettering then); just inside too when none fits
    within the bounds."""
    w, h = size
    x0, y0, x1, y1 = box
    candidates = [(x0, y0 - gap - h), (x1 - w, y0 - gap - h), (x0, y1 + gap), (x1 - w, y1 + gap),
                  (x0 - gap - w, y0), (x1 + gap, y0)]
    best: tuple[float, tuple[float, float]] | None = None
    for lx, ly in candidates:
        if lx < bounds[0] or ly < bounds[1] or lx + w > bounds[2] or ly + h > bounds[3]:
            continue
        covered = sum(_overlap((lx, ly, lx + w, ly + h), other) for other in others)
        if covered == 0:
            return lx, ly
        if best is None or covered < best[0]:
            best = (covered, (lx, ly))
    if best is not None and best[0] <= LABEL_GRAZE * w * h:
        return best[1]
    if best is not None:
        inside = (x0 + gap, y0 + gap)
        covered_inside = sum(_overlap((inside[0], inside[1], inside[0] + w, inside[1] + h), other) for other in others)
        return inside if covered_inside < best[0] else best[1]
    return x0 + gap, y0 + gap
