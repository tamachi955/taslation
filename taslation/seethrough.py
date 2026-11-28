"""See-through mode's pure parts (the mode is the program): TASlation's lettering laid over the viewer's own window
by a click-through window of its own (`capture.seethrough`), a page's patches shown whole while the viewer's frame is
the page they were made for.

* A patch is a piece of the translated page: where the lettered page differs from the frame it was read from (the
  erased ground and the lettering), grouped into one piece per bubble (`make_patches`). The patches of a page are
  shown or not by the page, never one by one by their own pixels: the set carries the page's sign (`PageSign`, made
  from the frame read: the steady part of its page area as a grey thumbnail, and its capture area's pixels every
  ROW_STEP-th), and while the viewer's frame has that steady part as it was (within PAGE_TOL: a soft or a sharp
  picture of the same page alike) every patch of the set shows whole, to the capture area's edge and the page's -
  but those that a bar of the viewer's lies over (`bar_rows`: rows from the area's top or bottom that are other than
  when read, across it or across the ground beside the page). A turn, a jump's black, a half-drawn spread, a page
  moved or zoomed change the steady part, and the set goes at that frame; it comes back as soon as the page is
  there again. Before, each patch was compared by its own pixels and a margin about it, and a margin that met the
  area's edge, a browser's band or a page's border row kept a bubble at the page's top hidden.
* What the overlay shows (`visible`): the newest set whose page is on show, its patches less those under a bar.
* The window's picture (`compose`): the frame's size, transparent but for the patches shown (premultiplied BGRA, as
  ``UpdateLayeredWindow`` wants it).
* Editing (`Marks`, `edit_grip`, `edit_drag`, `edit_compose`): the regions of the page on show, numbered, take the mouse
  where their boxes are - a click edits one, a drag moves it, a drag on a corner resizes it - and nowhere else.
* `steady_thumb`, `bands`, `ground_box`, `loading_kind`: what decides whether the page under the lettering is another
  page (most of the page area changed), not a band of it (bars over the page come and go), and whether a frame is a
  loading one (a black with a spinner, half a spread, a washed-out preview) to be waited out.

Everything here works on numpy arrays in memory; nothing is kept on disk."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 is a dependency of the package
    cv2 = None  # type: ignore[assignment]

Box = tuple[int, int, int, int]  # left, top, right, bottom (frame pixels)

# ------------------------------------------------------------------ the patches
GROUP_PX = 9  # changed pixels this close together are one patch (the letters of one bubble, its erased ground)
MIN_PATCH_PX = 4  # a group of fewer changed pixels is no patch (a stray pixel of the lettering's edge)
BASE_DPI = 96  # the pixel sizes here (MARGIN, GROUP_PX, BAR_REACH, LOOK_STEP) are at this DPI: `scaled` takes them to
# a viewer's
SETS_KEPT = 3  # the overlay keeps the patches of so many pages (a page turned back to shows at once)

# ------------------------------------------------------------------ the page on show
PAGE_TOL = 2.0  # the steady part's grey thumbnails (`page_sign`) differ by at most this (mean, of 255) while the frame
# is the page a set was made for: on the sample set's 214 pages in a made-up browser frame the same page drawn soft
# and sharp differed by 0.4 to 1.4, the page 2 px aside by 3.0 at the least, 4 px by 5.3, another page by 32.7
ROW_STEP = 4  # (`bar_rows`) the capture area's pixels kept with a set and compared for bars, every so many px both ways
PIXEL_TOL = 24  # a pixel compared is another when one of its channels differs by more than this (of 255)
BAR_SHARE = 0.5  # a row of the capture area is under a bar when more than this share of it is other than when read,
# or of its ground beside the page (a bar lies across the viewer's window, over the page and its ground)
BAR_REACH = 12  # px at 96 DPI: rows under a bar count only as a run from within this of the area's top or bottom
# (the viewer's bars come there; another page changes all of it, and that the steady part tells)
MARGIN = 6  # px at 96 DPI: a patch this near a bar's rows goes with them (its edge just under the bar's)
STRIP_PX = 8  # a band along the capture area's top or bottom edge no higher than this (px at 96 DPI) is a strip of
# what lies beyond the area - a browser's own bar under an area set by hand 3 px over its foot -, not a viewer's bar


@dataclass(frozen=True)
class Patch:
    """A piece of the translated page: *box* in the frame's pixels, *bgra* its picture there (premultiplied BGRA:
    opaque where the page was lettered or erased, transparent elsewhere)."""

    box: Box
    bgra: np.ndarray


@dataclass(frozen=True)
class PageSign:
    """What tells that the viewer's frame is the page a set was made for (`page_sign`): *area* the capture area of the
    frame read, *steady* the part of it a turn changes and bars never lie over (the page box's columns and the area's
    rows without their top STEADY_TOP and bottom STEADY_BOTTOM, rows painted over in the frame read left out) and
    *thumb* its grey thumbnail (THUMB x THUMB, float32), *rows* the area's pixels every ROW_STEP-th (BGR: as the
    viewer's frames come) and *page* the page box's columns (left, right; None: none found), whose ground beside them
    a bar lies across."""

    area: Box
    steady: Box
    thumb: np.ndarray
    rows: np.ndarray
    page: tuple[int, int] | None = None


@dataclass(frozen=True)
class PatchSet:
    """The patches of one page as lettered so far: *key* names the frame it was read from (a set presented again with
    the same key replaces the one before: drafts, then the final page), *size* (width, height) is that frame's,
    *serial* says which set is newer, *sign* tells its page (`PageSign`; None: never shown)."""

    key: int
    size: tuple[int, int]
    patches: tuple[Patch, ...]
    serial: int = 0
    final: bool = False
    sign: PageSign | None = None


_ONES = np.ones((1, 3), np.float32)  # (`changed_mask`: the three channels' differences summed, saturated)


def changed_mask(original: np.ndarray, lettered: np.ndarray) -> np.ndarray:
    """Where *lettered* (H, W, 3) differs from *original* (the same shape): exactly where any channel differs at all.
    For uint8 pictures with OpenCV, the channels' absolute differences summed (saturated at 255: nonzero exactly where
    one is), some 5 ms for a full-HD page against 25 ms for numpy's comparison."""
    if original.shape != lettered.shape:
        raise ValueError("the lettered page and its frame differ in size")
    if (cv2 is not None and original.dtype == np.uint8 and lettered.dtype == np.uint8 and original.ndim == 3
            and original.shape[2] == 3 and original.size):
        diff = cv2.absdiff(np.ascontiguousarray(original), np.ascontiguousarray(lettered))
        return cv2.transform(diff, _ONES).reshape(original.shape[:2]) > 0
    return np.any(original != lettered, axis=2)


def groups(mask: np.ndarray, gap: int = GROUP_PX, least: int = MIN_PATCH_PX) -> list[Box]:
    """The boxes of the groups of True pixels in *mask*, pixels up to *gap* apart being of one group; groups of fewer
    than *least* pixels left out. Ordered top to bottom, then left to right."""
    if not mask.any():
        return []
    m = mask.astype(np.uint8)
    if gap > 1 and cv2 is not None:
        joined = cv2.dilate(m, np.ones((gap, gap), np.uint8))
    else:
        joined = m
    if cv2 is None:  # pragma: no cover - one box round all
        ys, xs = np.nonzero(m)
        return [(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out: list[Box] = []
    for k in range(1, count):
        x, y, w, h, _area = (int(v) for v in stats[k])
        inside = m[y:y + h, x:x + w] & (labels[y:y + h, x:x + w] == k)
        n = int(inside.sum())
        if n < least:
            continue
        ys, xs = np.nonzero(inside)
        out.append((x + int(xs.min()), y + int(ys.min()), x + int(xs.max()) + 1, y + int(ys.max()) + 1))
    out.sort(key=lambda b: (b[1], b[0]))
    return out


def grow(box: Box, by: int, size: tuple[int, int]) -> Box:
    """*box* grown by *by* px on every side, within a frame of *size* (width, height)."""
    width, height = size
    return max(0, box[0] - by), max(0, box[1] - by), min(width, box[2] + by), min(height, box[3] + by)


def scaled(px: int, dpi: int | float | None) -> int:
    """*px* at BASE_DPI as many pixels at *dpi* (a viewer's window at 125 % is at 120, at 150 % at 144; None or 0: as
    BASE_DPI), rounded half up, at least 1: what the viewer draws is that much larger in its frames."""
    return max(1, int(px * float(dpi or BASE_DPI) / BASE_DPI + 0.5))


def make_patches(original: np.ndarray, lettered: np.ndarray, gap: int = GROUP_PX) -> tuple[Patch, ...]:
    """The patches of the page *lettered* read from the frame *original* (both RGB, (H, W, 3) uint8): one for every
    group of pixels the lettering changed, pixels up to *gap* apart being of one (`groups`), its picture opaque where
    it changed (BGRA, as the layered window takes it)."""
    mask = changed_mask(original, lettered)
    out = []
    for box in groups(mask, gap):
        left, top, right, bottom = box
        piece = lettered[top:bottom, left:right]
        alpha = mask[top:bottom, left:right]
        bgra = np.zeros((bottom - top, right - left, 4), np.uint8)
        bgra[..., :3] = piece[:, :, ::-1]
        bgra[..., 3] = alpha * 255
        bgra[~alpha] = 0  # premultiplied: no colour where it is transparent
        out.append(Patch(box, bgra))
    return tuple(out)


def _clip(box: Box, size: tuple[int, int]) -> Box:
    width, height = size
    left, top = max(0, min(width, int(box[0]))), max(0, min(height, int(box[1])))
    return left, top, max(left, min(width, int(box[2]))), max(top, min(height, int(box[3])))


def grey_thumb(pixels: np.ndarray, box: Box, bgr: bool = False, size: int | None = None) -> np.ndarray | None:
    """The grey thumbnail (*size* x *size*, float32) of *box* of the picture *pixels* (RGB, or with *bgr* BGR or BGRA:
    the viewer's frames); None for an empty box."""
    size = size or THUMB
    left, top, right, bottom = _clip(box, (pixels.shape[1], pixels.shape[0]))
    part = pixels[top:bottom, left:right, :3]
    if part.size == 0:
        return None
    if cv2 is None:  # pragma: no cover
        grey = part.mean(axis=2)
        ys = np.linspace(0, grey.shape[0] - 1, size).astype(int)
        xs = np.linspace(0, grey.shape[1] - 1, size).astype(int)
        return grey[np.ix_(ys, xs)].astype(np.float32)
    grey = cv2.cvtColor(np.ascontiguousarray(part), cv2.COLOR_BGR2GRAY if bgr else cv2.COLOR_RGB2GRAY)
    return cv2.resize(grey, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


def page_sign(rgb: np.ndarray, area: Box, page: tuple[int, int] | None = None,
              cut: tuple[tuple[int, int], ...] | list[tuple[int, int]] = ()) -> PageSign:
    """The sign of the page read from the frame *rgb* (RGB, (H, W, 3)) whose capture area is *area* (frame pixels),
    its page box's columns *page* (left, right; None: none found) and the rows *cut* painted over in it ((start, end)
    pairs: bars read with their rows painted, `ui.seethrough.reading_frame`), which the steady part keeps clear of."""
    height, width = rgb.shape[:2]
    area = _clip(area, (width, height))
    if area[2] <= area[0] or area[3] <= area[1]:
        area = (0, 0, width, height)
    cols = (area[0], area[2])
    if page is not None:
        cols = (max(area[0], int(page[0])), min(area[2], int(page[1])))
        if cols[1] - cols[0] < 8:
            cols, page = (area[0], area[2]), None
    steady = steady_box((width, height), (cols[0], area[1], cols[1], area[3]))
    top, bottom = steady[1], steady[3]
    for start, end in cut:
        if start <= top < end:
            top = int(end)
        if start < bottom <= end:
            bottom = int(start)
    if bottom - top >= 8:
        steady = (steady[0], top, steady[2], bottom)
    thumb = grey_thumb(rgb, steady)
    if thumb is None:
        thumb = np.zeros((THUMB, THUMB), np.float32)
    rows = np.ascontiguousarray(rgb[area[1]:area[3]:ROW_STEP, area[0]:area[2]:ROW_STEP, 2::-1])
    return PageSign(area, steady, thumb, rows, None if page is None else (int(cols[0]), int(cols[1])))


def page_distance(sign: PageSign, frame: np.ndarray) -> float:
    """How far the viewer's frame *frame* (its client area, BGR or BGRA (H, W, >=3)) is from the page of *sign*: the
    mean difference of the steady part's grey thumbnails (255.0 for a frame that does not hold that part)."""
    height, width = frame.shape[:2]
    if sign.steady[2] > width or sign.steady[3] > height:
        return 255.0
    now = grey_thumb(frame, sign.steady, bgr=True)
    if now is None or now.shape != sign.thumb.shape:
        return 255.0
    return float(np.abs(now - sign.thumb).mean())


def bar_rows(sign: PageSign, frame: np.ndarray, reach: int = BAR_REACH, least: int = STRIP_PX
             ) -> tuple[tuple[int, int], ...]:
    """The rows (top, bottom; frame pixels) of the capture area that a bar of the viewer's lies over in *frame* (BGR or
    BGRA): runs of rows other than in the frame read (`PageSign.rows`, PIXEL_TOL) across more than BAR_SHARE of the
    area or of the ground beside the page, higher than *least* px (a line along the area's edge drawn another shade
    is no bar), that begin within *reach* px of the area's top or end within it of its bottom (one row between two
    such rows joins them). The whole area for a frame that does not hold it."""
    left, top, right, bottom = sign.area
    now = frame[top:bottom:ROW_STEP, left:right:ROW_STEP, :3]
    if now.shape != sign.rows.shape:
        return ((top, bottom),)
    if not now.size:
        return ()
    other = np.abs(now.astype(np.int16) - sign.rows.astype(np.int16)).max(axis=2) > PIXEL_TOL
    barred = other.mean(axis=1) > BAR_SHARE
    if sign.page is not None:
        xs = left + np.arange(other.shape[1]) * ROW_STEP
        beside = (xs < sign.page[0]) | (xs >= sign.page[1])
        if int(beside.sum()) >= 4:
            barred |= other[:, beside].mean(axis=1) > BAR_SHARE
    if barred.size > 2:
        barred[1:-1] |= barred[:-2] & barred[2:]
    out: list[tuple[int, int]] = []
    k, n = 0, int(barred.size)
    while k < n:
        if not barred[k]:
            k += 1
            continue
        j = k
        while j < n and barred[j]:
            j += 1
        start, end = top + k * ROW_STEP, min(bottom, top + j * ROW_STEP)
        if end - start > least and (start - top <= reach or bottom - end <= reach):
            out.append((start, end))
        k = j
    return tuple(out)


def under_rows(box: Box, rows: tuple[tuple[int, int], ...] | list[tuple[int, int]], margin: int = 0) -> bool:
    """Whether the patch place *box* comes within *margin* px of any of the rows *rows* ((top, bottom) pairs)."""
    return any(box[1] < end + margin and start - margin < box[3] for start, end in rows)


@dataclass(frozen=True)
class Seen:
    """What a look made of the sets (`visible`): the distance of the set chosen's page (None: none chosen), the bars'
    rows over it, and each set of the frame's size looked at, newest first, with its distance ((key, distance))."""

    distance: float | None = None
    bars: tuple[tuple[int, int], ...] = ()
    looked: tuple[tuple[int, float], ...] = ()


def visible(sets: list[PatchSet], frame: np.ndarray, reach: int = BAR_REACH, margin: int = MARGIN,
            tol: float = PAGE_TOL, least: int = STRIP_PX) -> tuple[PatchSet | None, tuple[int, ...], Seen]:
    """What the overlay shows over the viewer's frame *frame* (its client area, BGR or BGRA (H, W, >=3)): the newest
    set of *sets* of the frame's size whose page is on show (`page_distance` within *tol*), and the indices of its
    patches less those within *margin* px of a bar's rows (`bar_rows`, *reach*, *least*); (None, ()) when no set's
    page is there. A set with no patches is chosen too (its regions' marks go by it while editing)."""
    height, width = frame.shape[:2]
    looked: list[tuple[int, float]] = []
    for s in sorted(sets, key=lambda s: -s.serial):
        if s.size != (width, height) or s.sign is None:
            continue
        distance = page_distance(s.sign, frame)
        looked.append((s.key, round(distance, 2)))
        if distance <= tol:
            bars = bar_rows(s.sign, frame, reach, least)
            shown = tuple(i for i, p in enumerate(s.patches) if not under_rows(p.box, bars, margin))
            return s, shown, Seen(round(distance, 2), bars, tuple(looked))
    return None, (), Seen(None, (), tuple(looked))


def compose(size: tuple[int, int], patches: list[Patch] | tuple[Patch, ...], out: np.ndarray | None = None
            ) -> np.ndarray:
    """The overlay's picture for a frame of *size* (width, height): transparent, *patches* on it (premultiplied BGRA,
    (H, W, 4)); into *out* when given (its shape must be that)."""
    width, height = size
    if out is None or out.shape != (height, width, 4):
        out = np.zeros((height, width, 4), np.uint8)
    else:
        out[...] = 0
    for p in patches:
        left, top, right, bottom = p.box
        if right > width or bottom > height:
            continue
        region = out[top:bottom, left:right]
        opaque = p.bgra[..., 3] > 0
        region[opaque] = p.bgra[opaque]
    return out


def hovered(boxes: list[Box], point: tuple[int, int], before: Box | None, grow: int, keep: int) -> int | None:
    """Which of the patch places *boxes* (frame pixels) the pointer at *point* (frame pixels) is over: the one it
    was over before (*before*, its box) as long as the pointer is within *keep* px of it - or the one of *boxes* that
    meets that box most, a page lettered again -, else the nearest one it is within *grow* px of (*keep* > *grow*: a
    pointer resting on the edge does not make it come and go); None for none."""
    x, y = point

    def gap(b: Box) -> int:  # (px from the box to the point, 0 inside it)
        return max(b[0] - x, x - (b[2] - 1), b[1] - y, y - (b[3] - 1), 0)

    if before is not None and gap(before) <= keep:
        for i, b in enumerate(boxes):
            if b == before:
                return i
        meets = [(min(b[2], before[2]) - max(b[0], before[0])) * (min(b[3], before[3]) - max(b[1], before[1]))
                 if b[0] < before[2] and before[0] < b[2] and b[1] < before[3] and before[1] < b[3] else 0
                 for b in boxes]
        best = max(range(len(boxes)), key=lambda i: meets[i], default=None)
        if best is not None and meets[best] > 0 and gap(boxes[best]) <= keep:
            return best
    near = [(gap(b), i) for i, b in enumerate(boxes) if gap(b) <= grow]
    return min(near)[1] if near else None


def covered(box: Box, offset: tuple[int, int], covers: list[Box]) -> bool:
    """Whether the patch place *box* (frame pixels; the frame's top left on the screen at *offset*) meets any of the
    screen rectangles *covers* (windows over the viewer)."""
    x, y = offset
    left, top, right, bottom = box[0] + x, box[1] + y, box[2] + x, box[3] + y
    return any(left < c[2] and c[0] < right and top < c[3] and c[1] < bottom for c in covers)


@dataclass
class SetStore:
    """The patch sets the overlay holds, newest first, SETS_KEPT at most; a set presented with a key already held
    replaces it."""

    sets: list[PatchSet] = field(default_factory=list)
    serial: int = 0

    def put(self, key: int, size: tuple[int, int], patches: tuple[Patch, ...], final: bool = False,
            sign: PageSign | None = None) -> PatchSet:
        self.serial += 1
        new = PatchSet(key, size, patches, self.serial, final, sign)
        self.sets = [new, *[s for s in self.sets if s.key != key]][:SETS_KEPT]
        return new

    def drop(self, key: int) -> None:
        self.sets = [s for s in self.sets if s.key != key]

    def clear(self) -> None:
        self.sets = []


# ------------------------------------------------------------------ editing: the page's regions under the pointer
EDIT_ALPHA = 1  # the page while editing, where no lettering is: next to nothing shows (1 of 255 darker), but the layered
# window takes the mouse there - the whole page does, the viewer has the keys alone (a pixel of alpha 0 lets the mouse
# through to the window under it: a window over the viewer, `edit_compose`'s holes)
GRIP_PX = 7  # a press this near a corner of a region's box resizes it (px at 96 DPI)
DRAG_PX = 4  # the pointer moved farther than this with the button down: a drag, not a click (px at 96 DPI)
LINE_PX = 2  # the outline round a region's box, in its colour (px at 96 DPI)
HOVER_LINE_PX = 3  # the stronger outline round the box under the pointer and the one chosen (px at 96 DPI)
HANDLE_PX = 7  # the squares at the corners of the box chosen (px at 96 DPI)
MIN_BOX = 8  # a region's shortest side after a resize, and the least a rectangle drawn to add one (`area.MIN_REGION`)
OUTLINE = (0, 212, 255)  # (BGR) the box under the pointer, the one in the editor and those selected (the window's
# FRAME_COLOUR, #ffd400)
ADDING = (255, 163, 77)  # (BGR) the rectangle drawn to add a region (the window's NEW_REGION_COLOUR, #4da3ff)
CORNERS = ("nw", "ne", "se", "sw")
PLATE = "plate"  # (a grip) a press on a box's number plate: a click types its place in the reading order, a drag
# moves the box


@dataclass(frozen=True)
class Marks:
    """the editing marks on one page, from the Tk thread (`capture.seethrough.SeeThrough.set_edit`): *key* the page's
    frame (its patches' set), *boxes* the regions a press takes hold of, in their reading order (frame pixels), each
    one's number plate (*plates*: premultiplied BGRA and its top left, or None) and the colour it is outlined in all
    the time (*colours*: BGR, the plate's; none given: outlined only as below), the regions *chosen* (outlined, one
    alone with its corner handles; a drag of one of them moves them all; the Delete key drops them), the one in the
    editor (*held*: outlined, its patches shown whatever the frame
    says) and the one whose original is shown (*bare*: its patches left out), whether presses only click (*locked*:
    an editor open, a change being stored, the reading order being clicked), whether the next drag draws a region to
    add (*adding*: in Reader mode too; the whole page takes the mouse meanwhile, as it does while editing), the boxes a
    change was made to, outlined until the page has them (*ghosts*), and the newest press the Tk thread had taken
    when it made these (*seen*). *serial* tells one set of marks from the next. *lettered* says, for each box, whether
    its region is lettered or erased (`pipeline.erases`): such a box with none of its lettering on show is outlined
    dashed (`edit_compose`'s *unshown*), never as a box translated over the page's own lettering."""

    key: int
    boxes: tuple[Box, ...]
    plates: tuple[tuple[np.ndarray, tuple[int, int]] | None, ...] = ()
    chosen: tuple[int, ...] = ()
    held: int | None = None
    bare: int | None = None
    locked: bool = False
    adding: bool = False
    ghosts: tuple[Box, ...] = ()
    seen: int = 0
    serial: int = 0
    colours: tuple[tuple[int, int, int], ...] = ()
    lettered: tuple[bool, ...] = ()


GROUND = Marks(key=0, boxes=())  # (the window's) the whole page taking the mouse while editing on a page with no marks of
# its own (not translated yet, another page): a drag draws a rectangle, a click does nothing


def plate_box(plate: tuple[np.ndarray, tuple[int, int]] | None) -> Box | None:
    if plate is None:
        return None
    bgra, (x, y) = plate
    return (int(x), int(y), int(x) + int(bgra.shape[1]), int(y) + int(bgra.shape[0]))


def edit_grip(marks: Marks, point: tuple[int, int], reach: int, left_out: frozenset[int] = frozenset()
              ) -> tuple[int, str] | None:
    """What a press at *point* (frame pixels) takes hold of: (the index of a region's box, one of CORNERS - within
    *reach* px of that corner, it is resized -, PLATE - its number plate, drawn over everything else - or "move",
    the smallest box the point is in); a corner first, then a plate, then a box; None for none (the page's empty
    ground). The boxes of *left_out* (covered by a window over the viewer) take nothing."""
    x, y = point
    corner: tuple[int, int, str] | None = None
    inside: tuple[int, int] | None = None
    plate_at: int | None = None
    for i, box in enumerate(marks.boxes):
        if i in left_out:
            continue
        left, top, right, bottom = box
        area = (right - left) * (bottom - top)
        corners = {"nw": (left, top), "ne": (right, top), "se": (right, bottom), "sw": (left, bottom)}
        for name in CORNERS:
            cx, cy = corners[name]
            if abs(x - cx) <= reach and abs(y - cy) <= reach and (corner is None or area < corner[0]):
                corner = (area, i, name)
        plate = plate_box(marks.plates[i]) if i < len(marks.plates) else None
        if plate is not None and plate[0] <= x < plate[2] and plate[1] <= y < plate[3]:
            plate_at = i  # (the last drawn: the one on top)
        if left <= x < right and top <= y < bottom and (inside is None or area < inside[0]):
            inside = (area, i)
    if corner is not None:
        return corner[1], corner[2]
    if plate_at is not None:
        return plate_at, PLATE
    return None if inside is None else (inside[1], "move")


def edit_drag(marks: Marks, index: int, grip: str, start: tuple[int, int], now: tuple[int, int],
              size: tuple[int, int]) -> dict[int, Box]:
    """The boxes as a drag from *start* to *now* (frame pixels, a frame of *size*) holding *grip* of the box *index*
    leaves them: a corner resizes that box (MIN_BOX at the least), "move" (or PLATE: the box by its number plate)
    moves it - and with it the others chosen when it is one of them, all by as much, stopping at the frame's edge
    (`area.shift_within`). Only the boxes that move, by index."""
    from .ui import area

    box = marks.boxes[index]
    if grip in CORNERS:
        moved = area.drag(box, grip, start, now, size, MIN_BOX)
        return {index: tuple(int(round(v)) for v in moved)}  # type: ignore[dict-item]
    group = list(marks.chosen) if index in marks.chosen and len(marks.chosen) > 1 else [index]
    group = [i for i in group if 0 <= i < len(marks.boxes)]
    dx, dy = area.shift_within([marks.boxes[i] for i in group], now[0] - start[0], now[1] - start[1], size)
    dx, dy = int(round(dx)), int(round(dy))
    return {i: (marks.boxes[i][0] + dx, marks.boxes[i][1] + dy, marks.boxes[i][2] + dx, marks.boxes[i][3] + dy)
            for i in group}


def drawn_box(start: tuple[int, int], now: tuple[int, int], size: tuple[int, int]) -> Box:
    """The rectangle a drag from *start* to *now* draws (adding a region), within a frame of *size*."""
    width, height = size
    x0, x1 = sorted((max(0, min(width, int(start[0]))), max(0, min(width, int(now[0])))))
    y0, y1 = sorted((max(0, min(height, int(start[1]))), max(0, min(height, int(now[1])))))
    return (x0, y0, x1, y1)


def _frame(out: np.ndarray, box: Box, bgr: tuple[int, int, int], width: int) -> None:
    """An opaque outline *width* px wide just inside *box* (clipped to *out*)."""
    height_px, width_px = out.shape[:2]
    left, top = max(0, int(box[0])), max(0, int(box[1]))
    right, bottom = min(width_px, int(box[2])), min(height_px, int(box[3]))
    if right <= left or bottom <= top:
        return
    colour = (*bgr, 255)
    w = max(1, min(width, (right - left + 1) // 2, (bottom - top + 1) // 2))
    out[top:top + w, left:right] = colour
    out[bottom - w:bottom, left:right] = colour
    out[top:bottom, left:left + w] = colour
    out[top:bottom, right - w:right] = colour


DASH_PX = 6  # (`_dashed`) a dashed outline's dashes and gaps, so long each (px at 96 DPI)


def _dashed(out: np.ndarray, box: Box, bgr: tuple[int, int, int], width: int, dash: int) -> None:
    """A dashed outline *width* px wide just inside *box* (clipped to *out*): dashes of *dash* px in *bgr* with gaps
    as long, the page showing through them."""
    height_px, width_px = out.shape[:2]
    left, top = max(0, int(box[0])), max(0, int(box[1]))
    right, bottom = min(width_px, int(box[2])), min(height_px, int(box[3]))
    if right <= left or bottom <= top:
        return
    colour = (*bgr, 255)
    w = max(1, min(width, (right - left + 1) // 2, (bottom - top + 1) // 2))
    dash = max(1, dash)
    for x in range(left, right, 2 * dash):
        out[top:top + w, x:min(right, x + dash)] = colour
        out[bottom - w:bottom, x:min(right, x + dash)] = colour
    for y in range(top, bottom, 2 * dash):
        out[y:min(bottom, y + dash), left:left + w] = colour
        out[y:min(bottom, y + dash), right - w:right] = colour


def _square(out: np.ndarray, centre: tuple[int, int], side: int, bgr: tuple[int, int, int]) -> None:
    """A corner handle: a square of *side* px about *centre*, dark with a light inside (it shows on any page)."""
    height, width = out.shape[:2]
    half = side // 2
    x0, y0 = max(0, centre[0] - half), max(0, centre[1] - half)
    x1, y1 = min(width, centre[0] - half + side), min(height, centre[1] - half + side)
    if x1 <= x0 or y1 <= y0:
        return
    out[y0:y1, x0:x1] = (32, 32, 32, 255)
    if x1 - x0 > 2 and y1 - y0 > 2:
        out[y0 + 1:y1 - 1, x0 + 1:x1 - 1] = (*bgr, 255)


def edit_compose(out: np.ndarray, marks: Marks, hover: int | None, moved: dict[int, Box] | None,
                 dpi: int | float, left_out: frozenset[int] = frozenset(), drawing: Box | None = None,
                 holes: tuple[Box, ...] = (), unshown: frozenset[int] = frozenset()) -> None:
    """the editing marks laid on the overlay's picture *out* (premultiplied BGRA with the patches on it, changed in place):
    EDIT_ALPHA wherever nothing is drawn, over the whole picture (every press, every move and every release on the
    page are the window's: the viewer gets the keys alone); every region's box outlined in its colour
    (`Marks.colours`), with its number plate; the one in the editor, those chosen, the boxes of a drag where it has
    them now (*moved*, by index) and the ghosts outlined in OUTLINE, the box under the pointer (*hover*) in OUTLINE's
    stronger line, and so the one chosen alone, with its corner handles as well (a click chose it: a drag moves it, a
    drag on a corner sizes it; none while presses only click); the rectangle being drawn (*drawing*). The boxes of
    *left_out* (covered, or under a bar of the viewer's) get nothing, those of *unshown* (lettered, none of their
    lettering on show) a dashed outline in their colour instead of the line, and the *holes* (the windows over the
    viewer, a bar's rows; frame pixels) are left at alpha 0: a press there is that window's."""
    height, width = out.shape[:2]
    alpha = out[..., 3]
    alpha[alpha == 0] = EDIT_ALPHA
    line = scaled(LINE_PX, dpi)
    for i, colour in enumerate(marks.colours[:len(marks.boxes)]):
        if i in left_out:
            continue
        if i in unshown:
            _dashed(out, (moved or {}).get(i, marks.boxes[i]), colour, line, scaled(DASH_PX, dpi))
        else:
            _frame(out, (moved or {}).get(i, marks.boxes[i]), colour, line)
    outlined = {i for i in (*marks.chosen, marks.held) if i is not None and i not in left_out}
    for i in sorted(outlined):
        if 0 <= i < len(marks.boxes):
            _frame(out, (moved or {}).get(i, marks.boxes[i]), OUTLINE, line)
    for i, box in (moved or {}).items():
        if i not in outlined:
            _frame(out, box, OUTLINE, line)
    for box in marks.ghosts:
        _frame(out, box, OUTLINE, line)
    alone = marks.chosen[0] if len(marks.chosen) == 1 else None
    for i in dict.fromkeys((hover, alone)):
        if i is None or not 0 <= i < len(marks.boxes) or i in left_out:
            continue
        left, top, right, bottom = (moved or {}).get(i, marks.boxes[i])
        _frame(out, (left, top, right, bottom), OUTLINE, scaled(HOVER_LINE_PX, dpi))
        if i == alone and not marks.locked:
            side = scaled(HANDLE_PX, dpi)
            for corner in ((left, top), (right - 1, top), (right - 1, bottom - 1), (left, bottom - 1)):
                _square(out, corner, side, OUTLINE)
    for i, plate in enumerate(marks.plates):
        if plate is None or i in left_out:
            continue
        bgra, (x, y) = plate
        h, w = bgra.shape[:2]
        x0, y0, x1, y1 = max(0, x), max(0, y), min(width, x + w), min(height, y + h)
        if x1 <= x0 or y1 <= y0:
            continue
        src = bgra[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.uint16)
        dst = out[y0:y1, x0:x1].astype(np.uint16)
        keep = 255 - src[..., 3:4]
        out[y0:y1, x0:x1] = np.minimum(255, src + (dst * keep + 127) // 255).astype(np.uint8)
    if drawing is not None:
        _frame(out, drawing, ADDING, line)
    for box in holes:
        left, top = max(0, int(box[0])), max(0, int(box[1]))
        right, bottom = min(width, int(box[2])), min(height, int(box[3]))
        if right > left and bottom > top:
            out[top:bottom, left:right] = 0


# ------------------------------------------------------------------ another page, or a band of it
STEADY_TOP = 0.15  # the steady part of the capture area: without its top and bottom so much (bars come and go there)
STEADY_BOTTOM = 0.12
THUMB = 64


def steady_box(size: tuple[int, int], box: Box | None = None) -> Box:
    """The part of a frame of *size* (width, height) whose change says another page: the capture area *box* (the whole
    frame when None) without its top STEADY_TOP and bottom STEADY_BOTTOM, where a viewer's bars come and go over the
    page (and its slider, its counter). A turn changes all of a page; bars change a band of it."""
    width, height = size
    left, top, right, bottom = box if box is not None else (0, 0, width, height)
    span = max(1, bottom - top)
    t = top + int(round(span * STEADY_TOP))
    b = bottom - int(round(span * STEADY_BOTTOM))
    if b - t < 8:
        return left, top, right, bottom
    return left, t, right, b


def steady_thumb(rgb: np.ndarray, box: Box | None = None, size: int = THUMB) -> np.ndarray:
    """The grey thumbnail (*size* x *size*, float32) of the steady part (`steady_box`) of the frame *rgb* (H, W, 3),
    the capture area being *box*: what `frames.frames_differ` compares in see-through mode."""
    height, width = rgb.shape[:2]
    left, top, right, bottom = steady_box((width, height), box)
    part = rgb[top:bottom, left:right]
    if part.size == 0:
        part = rgb
    if cv2 is None:  # pragma: no cover
        grey = part.mean(axis=2)
        ys = np.linspace(0, grey.shape[0] - 1, size).astype(int)
        xs = np.linspace(0, grey.shape[1] - 1, size).astype(int)
        return grey[np.ix_(ys, xs)].astype(np.float32)
    grey = cv2.cvtColor(np.ascontiguousarray(part), cv2.COLOR_RGB2GRAY)
    return cv2.resize(grey, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


# ------------------------------------------------------------------ the page on a flat ground
GROUND_TOL = 6  # a pixel is the ground's colour within this (of 255, every channel)
GROUND_SHARE = 0.9  # a column (or row) is ground when so much of it is the ground's colour (an arrow on it aside)
EDGE_COLUMNS = 3  # the ground's colour is taken from so many columns at each side
LEAST_SIDE = 0.02  # a page box needs at least this share of the width as ground on each side
ASPECT = (0.35, 2.4)  # a page (or a spread) is this many times as wide as high, at the least and the most
BAND_SHARE = 0.5  # a row whose ground beside the page is other for more than this share is in a band (bars over it)


def ground_colour(rgb: np.ndarray, columns: int = EDGE_COLUMNS) -> np.ndarray | None:
    """The ground's colour: the median of the frame's outermost *columns* on both sides when they are of one colour
    (within GROUND_TOL for GROUND_SHARE of them, rows of bands aside); None when they are not."""
    if rgb.shape[1] < 2 * columns + 8:
        return None
    edges = np.concatenate([rgb[:, :columns], rgb[:, -columns:]], axis=1).reshape(-1, 3).astype(np.int16)
    colour = np.median(edges, axis=0)
    near = np.all(np.abs(edges - colour) <= GROUND_TOL, axis=1)
    if near.mean() < 0.6:  # (bars over the ground take up to a third of the rows)
        return None
    return colour.astype(np.int16)


def ground_rows(rgb: np.ndarray, colour: np.ndarray, columns: int = EDGE_COLUMNS) -> np.ndarray:
    """Per row, whether the outermost *columns* on both sides are the ground's colour."""
    edges = np.concatenate([rgb[:, :columns], rgb[:, -columns:]], axis=1).astype(np.int16)
    return np.all(np.abs(edges - colour) <= GROUND_TOL, axis=2).mean(axis=1) >= GROUND_SHARE


def ground_box(rgb: np.ndarray) -> Box | None:
    """The page (or spread) on a ground of one colour - black, white or any - in the frame *rgb* (H, W, 3, the capture
    area): from the rows where the ground shows at both sides (bars across the frame aside), the outermost columns
    that are not all ground; its rows: where its columns are not all ground. None when the ground is not one colour
    at both sides, when the box leaves less than LEAST_SIDE of the width as ground on a side, or is not of a page's
    shape (ASPECT). A white page on a white ground gives the box of what is drawn on it (its blank margin is ground
    here): a capture area without it reads all of the page's text."""
    height, width = rgb.shape[:2]
    colour = ground_colour(rgb)
    if colour is None:
        return None
    rows = ground_rows(rgb, colour)
    if rows.mean() < 0.5:
        return None
    body = rgb[rows].astype(np.int16)
    is_ground = np.all(np.abs(body - colour) <= GROUND_TOL, axis=2)  # (rows kept, width)
    cols = is_ground.mean(axis=0) >= GROUND_SHARE
    inner = np.nonzero(~cols)[0]
    if inner.size == 0:
        return None
    left, right = int(inner[0]), int(inner[-1]) + 1
    if left < width * LEAST_SIDE or width - right < width * LEAST_SIDE:
        return None
    part = rgb[:, left:right].astype(np.int16)
    row_ground = np.all(np.abs(part - colour) <= GROUND_TOL, axis=2).mean(axis=1) >= GROUND_SHARE
    filled = np.nonzero(~row_ground & rows)[0]
    if filled.size == 0:
        return None
    top, bottom = int(filled[0]), int(filled[-1]) + 1
    # a band across the frame at its top or bottom (bars) hides whether the page goes on under it: it is taken to
    if not rows[:top].all():
        top = 0
    if not rows[bottom:].all():
        bottom = height
    w, h = right - left, bottom - top
    if h <= 0 or not (ASPECT[0] <= w / h <= ASPECT[1]):
        return None
    return left, top, right, bottom


def _ground_columns(width: int, page: Box | None) -> np.ndarray:
    """The columns beside the page box *page* (the frame's edges' when None) that `bands` looks along."""
    if page is None:
        return np.r_[0:EDGE_COLUMNS, width - EDGE_COLUMNS:width]
    left, _t, right, _b = page
    return np.r_[0:max(1, left), min(width - 1, right):width]


def _across(rows: np.ndarray, colour: np.ndarray) -> np.ndarray:
    """Which of *rows* (N, columns, 3: the ground's columns of each) something lies across, as a band's (`bands`)."""
    return (~np.all(np.abs(rows.astype(np.int16) - colour) <= GROUND_TOL, axis=2)).mean(axis=1) > BAND_SHARE


def bands(rgb: np.ndarray, page: Box | None = None) -> list[tuple[int, int]]:
    """The bands of rows (top, bottom) where something lies across the ground beside the page *page* (the frame's
    ground box when None): a viewer's bars over the page and its ground. Only bands that touch the frame's top or
    bottom count (bars are there); [] when the ground is not one colour."""
    colour = ground_colour(rgb)
    if colour is None:
        return []
    height, width = rgb.shape[:2]
    if page is None:
        page = ground_box(rgb)
    other = _across(rgb[:, _ground_columns(width, page)], colour)
    out: list[tuple[int, int]] = []
    if other[0]:
        end = int(np.argmin(other)) if not other.all() else height
        out.append((0, end))
    if other[-1] and not other.all():
        start = height - int(np.argmin(other[::-1]))
        out.append((start, height))
    return out


# ------------------------------------------------------------------ frames to wait out
BLACK_LEVEL = 12  # a page half darker than this on average, with almost nothing in it, is not drawn yet
FLAT_SPREAD = 6.0  # ... nothing in it: its grey levels spread less than this
WASHED_LOW = 64  # a page whose darkest one per cent is lighter than this is a washed-out picture (a preview)
WASHED_SPREAD = 40  # ... and whose grey levels spread less than this


def half_of(box: Box | None, before: Box | None) -> bool:
    """Whether the page box *box* is one half of the spread *before* (the box found at the last rest): about half as
    wide, at one of its sides - the other page of a spread not drawn yet (a single page after a spread is centred)."""
    if box is None or before is None:
        return False
    width, was = box[2] - box[0], before[2] - before[0]
    if was <= 0 or not 0.38 <= width / was <= 0.62:
        return False
    slack = max(4, was // 50)
    return abs(box[0] - before[0]) <= slack or abs(box[2] - before[2]) <= slack


def loading_kind(rgb: np.ndarray, page: Box | None = None, before: Box | None = None) -> str | None:
    """Whether the frame *rgb* (the capture area) is one to wait out rather than read: "black" (the page area nearly
    black, a spinner in it at most), "half" (one page of a spread drawn, the other not yet: the page box *page* is half
    of the one found at the last rest, *before* (`half_of`); or one side of the page box flat black while the other is
    drawn), "washed" (a pale picture with no dark ink: a preview drawn before the page). Rows of bands (`bands`: bars
    over the page) are left out. None for a page as it is read."""
    height, width = rgb.shape[:2]
    if half_of(page, before):
        return "half"
    left, top, right, bottom = page if page is not None else (0, 0, width, height)
    for start, end in bands(rgb, page):
        if start == 0:
            top = max(top, end)
        else:
            bottom = min(bottom, start)
    area = rgb[top:bottom, left:right]
    if area.size == 0:
        return None
    grey = area[::4, ::4].mean(axis=2)
    if grey.mean() < BLACK_LEVEL:
        return "black"
    mid = grey.shape[1] // 2
    halves = grey[:, :mid], grey[:, mid:]
    for a, b in (halves, halves[::-1]):
        if a.size and b.size and a.mean() < BLACK_LEVEL and a.std() < FLAT_SPREAD and b.std() > 3 * FLAT_SPREAD:
            return "half"
    low = float(np.percentile(grey, 1))
    high = float(np.percentile(grey, 99))
    if low > WASHED_LOW and high - low < 255 - WASHED_LOW and grey.std() < WASHED_SPREAD:
        return "washed"
    return None


# ------------------------------------------------------------------ one look at a frame
LOOK_STEP = 4  # a frame is looked at in every so many pixels across and down (some 3 ms for a full-HD frame)


@dataclass(frozen=True)
class Look:
    """What one look at a frame's capture area found (`look`), in the area's own pixels: the page box on a flat ground
    (None: none found), the bands across it (bars), whether it is a frame to wait out (`loading_kind`), the ground's
    colour (RGB; None: not one colour) and the strips along the area's top and bottom edges (rows of what lies beyond
    the area, the same on every frame: no bars; the page is looked for between them)."""

    box: Box | None
    bands: tuple[tuple[int, int], ...]
    kind: str | None
    ground: tuple[int, int, int] | None
    strips: tuple[tuple[int, int], ...] = ()


def look(rgb: np.ndarray, before: Box | None = None, step: int = LOOK_STEP, strip: int = STRIP_PX) -> Look:
    """`ground_box`, `bands` and `loading_kind` of the capture area *rgb* (H, W, 3), on every *step*-th pixel, the
    boxes and rows given back in its own pixels (to within *step*); *before*: the page box at the last rest (for a
    half-drawn spread). A band at the area's top or bottom no higher than *strip* px is a strip (`Look.strips`), not a
    band: the rest is looked at between the strips."""
    small = np.ascontiguousarray(rgb[::step, ::step])
    height, width = rgb.shape[:2]

    def up(v: int, limit: int) -> int:
        return min(limit, v * step)

    first, last = 0, small.shape[0]
    strips = []
    page = ground_box(small)
    for a, b in bands(small, page):
        rows = (up(a, height), height if b >= small.shape[0] else up(b, height))
        if rows[1] - rows[0] > strip or b - a >= small.shape[0] // 2:
            continue
        strips.append(_to_the_row(rgb, rows, a == 0, small, page, step))
        if a == 0:
            first = b
        else:
            last = a
    if strips:
        small = np.ascontiguousarray(small[first:last])
    box = ground_box(small)
    found = bands(small, box)
    shrunk = None if before is None else tuple(v // step - (first if k % 2 else 0) for k, v in enumerate(before))
    kind = loading_kind(small, box, shrunk)  # type: ignore[arg-type]
    colour = ground_colour(small)
    low = height if last >= rgb[::step].shape[0] else up(last, height)  # (the lower strip's top, or the area's foot)
    big = None if box is None else (up(box[0], width), up(box[1] + first, height), up(box[2], width),
                                    up(box[3] + first, height))
    if big is not None and box is not None:
        big = (big[0], big[1], width if box[2] >= small.shape[1] else big[2],
               low if box[3] >= small.shape[0] else big[3])
    rows = tuple((up(a + first, height), low if b >= small.shape[0] else up(b + first, height)) for a, b in found)
    return Look(big, rows, kind, None if colour is None else tuple(int(c) for c in colour),  # type: ignore[arg-type]
                tuple(strips))


def _to_the_row(rgb: np.ndarray, rows: tuple[int, int], top: bool, small: np.ndarray, page: Box | None,
                step: int) -> tuple[int, int]:
    """A strip's *rows* as `look` found them on every *step*-th row, to the row: its inner edge (the foot of one along
    the area's *top*, else the top of one along its foot) where the rows of the frame *rgb* beside the page stop
    differing from the ground as a band's do - the rows between two looked at are the page's as often as the strip's
    (a browser's bar 2 px into the area read as 4 took the first 2 rows of a bubble cut by the content's top)."""
    colour = ground_colour(small)
    if colour is None:
        return rows
    cols = _ground_columns(small.shape[1], page) * step
    a, b = rows
    if top:
        between = np.arange(max(a + 1, b - step + 1), b)
        across = _across(rgb[between][:, cols], colour) if between.size else np.zeros(0, bool)
        return a, int(between[np.argmin(across)]) if between.size and not across.all() else b
    between = np.arange(a - 1, max(a - step, 0), -1)  # (from the strip's top up to the row after the one looked at)
    across = _across(rgb[between][:, cols], colour) if between.size else np.zeros(0, bool)
    if not between.size:
        return rows
    return (int(between[-1]) if across.all() else int(between[np.argmin(across)]) + 1), b


def masked(rgb: np.ndarray, rows: tuple[tuple[int, int], ...] | list[tuple[int, int]],
           colour: tuple[int, int, int] | None) -> np.ndarray:
    """A copy of *rgb* with the band *rows* painted in the ground's *colour* (black when None): a frame read with bars
    held over it reads none of their words."""
    out = rgb.copy()
    fill = np.array(colour if colour is not None else (0, 0, 0), np.uint8)
    for top, bottom in rows:
        out[top:bottom] = fill
    return out