"""See-through mode's pure parts (a prototype behind ``Settings.see_through``, off by default): TASlation's lettering
laid over the viewer's own window by a click-through window of its own (`capture.seethrough`), each patch shown only
while the viewer's pixels under it are those it was made from.

* A patch is a piece of the translated page: where the lettered page differs from the frame it was read from (the
  erased ground and the lettering), grouped into one piece per bubble (`make_patches`). It keeps the frame's pixels
  round it (its box and MARGIN px about it, every STEP-th pixel), and it may show only while the viewer's latest frame
  has those pixels there (`patch_matches`): a turn, a jump's black, a half-drawn spread, a washed-out preview, bars
  laid over it or a sharper picture of the page change them, and the patch goes at that frame; it comes back as soon
  as they are as they were. Nothing else decides it: not the page job, not the follow.
* What the overlay shows (`visible`): the patches of the newest set whose pixels match, those that match.
* The window's picture (`compose`): the frame's size, transparent but for the patches shown (premultiplied BGRA, as
  ``UpdateLayeredWindow`` wants it).
* Edit (`Marks`, `edit_grip`, `edit_drag`, `edit_compose`): the regions of the page on show, numbered, take the mouse
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
MARGIN = 6  # px of the frame round a patch that must be as they were, too (a bar's edge, a page's edge just beside it)
STEP = 2  # every so many pixels of a patch's place (and its margin) is compared, across and down
PIXEL_TOL = 24  # a pixel compared is another when one of its channels differs by more than this (of 255)
CHANGED_SHARE = 0.01  # a patch's pixels are another's when more than this share of those compared is another
GROUP_PX = 9  # changed pixels this close together are one patch (the letters of one bubble, its erased ground)
MIN_PATCH_PX = 4  # a group of fewer changed pixels is no patch (a stray pixel of the lettering's edge)
BASE_DPI = 96  # the pixel sizes here (MARGIN, GROUP_PX, LOOK_STEP) are at this DPI: `scaled` takes them to a viewer's
SETS_KEPT = 3  # the overlay keeps the patches of so many pages (a page turned back to shows at once)


@dataclass(frozen=True)
class Patch:
    """A piece of the translated page: *box* in the frame's pixels, *bgra* its picture there (premultiplied BGRA:
    opaque where the page was lettered or erased, transparent elsewhere), *near* the box with MARGIN about it (within
    the frame) and *source* the frame's pixels there, every STEP-th one (BGR), which the viewer's must be for it to
    show."""

    box: Box
    bgra: np.ndarray
    near: Box
    source: np.ndarray


@dataclass(frozen=True)
class PatchSet:
    """The patches of one page as lettered so far: *key* names the frame it was read from (a set presented again with
    the same key replaces the one before: drafts, then the final page), *size* (width, height) is that frame's,
    *serial* says which set is newer."""

    key: int
    size: tuple[int, int]
    patches: tuple[Patch, ...]
    serial: int = 0
    final: bool = False


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


def sample(pixels: np.ndarray, box: Box, step: int = STEP) -> np.ndarray:
    """Every *step*-th pixel of *pixels* (H, W, >=3) in *box*, the first three channels."""
    left, top, right, bottom = box
    return pixels[top:bottom:step, left:right:step, :3]


def scaled(px: int, dpi: int | float | None) -> int:
    """*px* at BASE_DPI as many pixels at *dpi* (a viewer's window at 125 % is at 120, at 150 % at 144; None or 0: as
    BASE_DPI), rounded half up, at least 1: what the viewer draws is that much larger in its frames."""
    return max(1, int(px * float(dpi or BASE_DPI) / BASE_DPI + 0.5))


def make_patches(original: np.ndarray, lettered: np.ndarray, margin: int = MARGIN,
                 step: int = STEP, gap: int = GROUP_PX) -> tuple[Patch, ...]:
    """The patches of the page *lettered* read from the frame *original* (both RGB, (H, W, 3) uint8): one for every
    group of pixels the lettering changed, pixels up to *gap* apart being of one (`groups`), its picture opaque where
    it changed, *margin* px round it compared too. The frame's pixels are kept as BGR, as the viewer's frames come
    (Windows.Graphics.Capture's BGRA)."""
    mask = changed_mask(original, lettered)
    height, width = mask.shape
    out = []
    bgr_frame = original[:, :, ::-1]
    for box in groups(mask, gap):
        left, top, right, bottom = box
        piece = lettered[top:bottom, left:right]
        alpha = mask[top:bottom, left:right]
        bgra = np.zeros((bottom - top, right - left, 4), np.uint8)
        bgra[..., :3] = piece[:, :, ::-1]
        bgra[..., 3] = alpha * 255
        bgra[~alpha] = 0  # premultiplied: no colour where it is transparent
        near = grow(box, margin, (width, height))
        out.append(Patch(box, bgra, near, np.ascontiguousarray(sample(bgr_frame, near, step))))
    return tuple(out)


def changed_share(patch: Patch, frame: np.ndarray, step: int = STEP, tol: int = PIXEL_TOL) -> float:
    """The share of the pixels compared round *patch* that are other in the viewer's frame *frame* (BGR or BGRA,
    (H, W, >=3), the client area as captured) than in the frame the patch was made from; 1.0 when the frame does not
    hold its place."""
    now = sample(frame, patch.near, step)
    if now.shape != patch.source.shape:
        return 1.0
    diff = np.abs(now.astype(np.int16) - patch.source.astype(np.int16)).max(axis=2)
    return float((diff > tol).mean()) if diff.size else 0.0


def patch_matches(patch: Patch, frame: np.ndarray, share: float = CHANGED_SHARE) -> bool:
    """Whether the viewer's frame *frame* has, round *patch*, the pixels it was made from (`changed_share`)."""
    return changed_share(patch, frame) <= share


def visible(sets: list[PatchSet], frame: np.ndarray, share: float = CHANGED_SHARE
            ) -> tuple[PatchSet | None, tuple[int, ...], list[float]]:
    """What the overlay shows over the viewer's frame *frame* (its client area, (H, W, >=3)): the newest set of
    *sets* of the frame's size of which a patch matches (`patch_matches`), and the indices of its patches that do;
    (None, ()) when none does. Also the changed shares of the chosen set's patches - or, with none chosen, of the
    newest set's of that size - for the overlay's log."""
    height, width = frame.shape[:2]
    newest: list[float] = []
    for s in sorted(sets, key=lambda s: -s.serial):
        if s.size != (width, height) or not s.patches:
            continue
        shares = [changed_share(p, frame) for p in s.patches]
        shown = tuple(i for i, v in enumerate(shares) if v <= share)
        if shown:
            return s, shown, shares
        newest = newest or shares
    return None, (), newest


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

    def put(self, key: int, size: tuple[int, int], patches: tuple[Patch, ...], final: bool = False) -> PatchSet:
        self.serial += 1
        new = PatchSet(key, size, patches, self.serial, final)
        self.sets = [new, *[s for s in self.sets if s.key != key]][:SETS_KEPT]
        return new

    def drop(self, key: int) -> None:
        self.sets = [s for s in self.sets if s.key != key]

    def clear(self) -> None:
        self.sets = []


# ------------------------------------------------------------------ Edit: the page's regions under the pointer
EDIT_ALPHA = 1  # a region's box in Edit, where no lettering is: next to nothing shows (1 of 255 darker), but the
# layered window takes the mouse there (a pixel of alpha 0 lets it through to the viewer)
GRIP_PX = 7  # a press this near a corner of a region's box resizes it (px at 96 DPI)
DRAG_PX = 4  # the pointer moved farther than this with the button down: a drag, not a click (px at 96 DPI)
LINE_PX = 2  # the outline round a region's box (px at 96 DPI)
HANDLE_PX = 7  # the squares at the corners of the box under the pointer (px at 96 DPI)
MIN_BOX = 8  # a region's shortest side after a resize, and the least a rectangle drawn to add one (`area.MIN_REGION`)
OUTLINE = (0, 212, 255)  # (BGR) the box under the pointer, the one in the editor and those selected (the window's
# FRAME_COLOUR, #ffd400)
ADDING = (255, 163, 77)  # (BGR) the rectangle drawn to add a region (the window's NEW_REGION_COLOUR, #4da3ff)
CORNERS = ("nw", "ne", "se", "sw")


@dataclass(frozen=True)
class Marks:
    """Edit's marks on one page, from the Tk thread (`capture.seethrough.SeeThrough.set_edit`): *key* the page's
    frame (its patches' set), *boxes* the regions a press takes hold of, in their reading order (frame pixels), each
    one's number plate (*plates*: premultiplied BGRA and its top left, or None), the regions *chosen* (outlined; a
    drag of one of them moves them all), the one in the editor (*held*: outlined, its patches shown whatever the frame
    says) and the one whose original is shown (*bare*: its patches left out), whether presses only click (*locked*:
    an editor open, a change being stored, the reading order being clicked), whether the next drag draws a region to
    add (*adding*: the whole page takes the mouse meanwhile), the boxes a change was made to, outlined until the page
    has them (*ghosts*), and the newest press the Tk thread had taken when it made these (*seen*). *serial* tells one
    set of marks from the next."""

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


def plate_box(plate: tuple[np.ndarray, tuple[int, int]] | None) -> Box | None:
    if plate is None:
        return None
    bgra, (x, y) = plate
    return (int(x), int(y), int(x) + int(bgra.shape[1]), int(y) + int(bgra.shape[0]))


def edit_grip(marks: Marks, point: tuple[int, int], reach: int, left_out: frozenset[int] = frozenset()
              ) -> tuple[int, str] | None:
    """What a press at *point* (frame pixels) takes hold of: (the index of a region's box, one of CORNERS - within
    *reach* px of that corner, it is resized - or "move"), the smallest box the point is in (or its number plate);
    None for none. The boxes of *left_out* (covered by a window over the viewer) take nothing."""
    x, y = point
    best: tuple[int, int, str] | None = None
    for i, box in enumerate(marks.boxes):
        if i in left_out:
            continue
        left, top, right, bottom = box
        corners = {"nw": (left, top), "ne": (right, top), "se": (right, bottom), "sw": (left, bottom)}
        for name in CORNERS:
            cx, cy = corners[name]
            if abs(x - cx) <= reach and abs(y - cy) <= reach:
                area = (right - left) * (bottom - top)
                if best is None or area < best[0]:
                    best = (area, i, name)
        inside = left <= x < right and top <= y < bottom
        plate = plate_box(marks.plates[i]) if i < len(marks.plates) else None
        on_plate = plate is not None and plate[0] <= x < plate[2] and plate[1] <= y < plate[3]
        if inside or on_plate:
            area = (right - left) * (bottom - top)
            if best is None or (best[2] == "move" and area < best[0]):
                best = (area, i, "move")
    return None if best is None else (best[1], best[2])


def edit_drag(marks: Marks, index: int, grip: str, start: tuple[int, int], now: tuple[int, int],
              size: tuple[int, int]) -> dict[int, Box]:
    """The boxes as a drag from *start* to *now* (frame pixels, a frame of *size*) holding *grip* of the box *index*
    leaves them: a corner resizes that box (MIN_BOX at the least), "move" moves it - and with it the others chosen
    when it is one of them, all by as much, stopping at the frame's edge (`area.shift_within`). Only the boxes that
    move, by index."""
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
                 sheet: bool, dpi: int | float, left_out: frozenset[int] = frozenset(),
                 drawing: Box | None = None) -> None:
    """Edit's marks laid on the overlay's picture *out* (premultiplied BGRA with the patches on it, changed in place):
    EDIT_ALPHA wherever nothing is drawn inside each region's box (or, with *sheet* - a press held, a region to add
    -, over the whole picture: every pointer move and the release are the window's then), the number plates, an
    outline round the box under the pointer (*hover*, with its corner handles), the one in the editor, those chosen and
    the ghosts; the boxes of a drag where it has them now (*moved*, by index), and the rectangle being drawn
    (*drawing*). The boxes of *left_out* (covered) get nothing."""
    height, width = out.shape[:2]
    alpha = out[..., 3]
    if sheet:
        alpha[alpha == 0] = EDIT_ALPHA
    else:
        for i, box in enumerate(marks.boxes):
            if i in left_out:
                continue
            left, top = max(0, box[0]), max(0, box[1])
            right, bottom = min(width, box[2]), min(height, box[3])
            if right > left and bottom > top:
                part = alpha[top:bottom, left:right]
                part[part == 0] = EDIT_ALPHA
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
    line = scaled(LINE_PX, dpi)
    outlined = {i for i in (*marks.chosen, marks.held, hover) if i is not None and i not in left_out}
    for i in sorted(outlined):
        if 0 <= i < len(marks.boxes):
            _frame(out, (moved or {}).get(i, marks.boxes[i]), OUTLINE, line)
    for i, box in (moved or {}).items():
        if i not in outlined:
            _frame(out, box, OUTLINE, line)
    for box in marks.ghosts:
        _frame(out, box, OUTLINE, line)
    if hover is not None and 0 <= hover < len(marks.boxes) and hover not in left_out and not marks.locked:
        left, top, right, bottom = (moved or {}).get(hover, marks.boxes[hover])
        side = scaled(HANDLE_PX, dpi)
        for corner in ((left, top), (right - 1, top), (right - 1, bottom - 1), (left, bottom - 1)):
            _square(out, corner, side, OUTLINE)
    if drawing is not None:
        _frame(out, drawing, ADDING, line)


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
    if page is None:
        cols = np.r_[0:EDGE_COLUMNS, width - EDGE_COLUMNS:width]
    else:
        left, _t, right, _b = page
        cols = np.r_[0:max(1, left), min(width - 1, right):width]
    strip = rgb[:, cols].astype(np.int16)
    other = (~np.all(np.abs(strip - colour) <= GROUND_TOL, axis=2)).mean(axis=1) > BAND_SHARE
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
    (None: none found), the bands across it (bars), whether it is a frame to wait out (`loading_kind`) and the ground's
    colour (RGB; None: not one colour)."""

    box: Box | None
    bands: tuple[tuple[int, int], ...]
    kind: str | None
    ground: tuple[int, int, int] | None


def look(rgb: np.ndarray, before: Box | None = None, step: int = LOOK_STEP) -> Look:
    """`ground_box`, `bands` and `loading_kind` of the capture area *rgb* (H, W, 3), on every *step*-th pixel, the
    boxes and rows given back in its own pixels (to within *step*); *before*: the page box at the last rest (for a
    half-drawn spread)."""
    small = np.ascontiguousarray(rgb[::step, ::step])
    height, width = rgb.shape[:2]
    box = ground_box(small)
    found = bands(small, box)
    shrunk = None if before is None else tuple(v // step for v in before)
    kind = loading_kind(small, box, shrunk)  # type: ignore[arg-type]
    colour = ground_colour(small)

    def up(v: int, limit: int) -> int:
        return min(limit, v * step)

    big = None if box is None else (up(box[0], width), up(box[1], height), up(box[2], width), up(box[3], height))
    if big is not None and box is not None:
        big = (big[0], big[1], width if box[2] >= small.shape[1] else big[2],
               height if box[3] >= small.shape[0] else big[3])
    rows = tuple((up(a, height), height if b >= small.shape[0] else up(b, height)) for a, b in found)
    return Look(big, rows, kind, None if colour is None else tuple(int(c) for c in colour))  # type: ignore[arg-type]


def masked(rgb: np.ndarray, rows: tuple[tuple[int, int], ...] | list[tuple[int, int]],
           colour: tuple[int, int, int] | None) -> np.ndarray:
    """A copy of *rgb* with the band *rows* painted in the ground's *colour* (black when None): a frame read with bars
    held over it reads none of their words."""
    out = rgb.copy()
    fill = np.array(colour if colour is not None else (0, 0, 0), np.uint8)
    for top, bottom in rows:
        out[top:bottom] = fill
    return out