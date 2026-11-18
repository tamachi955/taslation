"""The rooms the regions of a page are lettered in, shared out where they overlap.

Each region is lettered inside its mask (`typeset.letter_text`). Two masks can overlap: bubbles drawn fused into each
other whose regions each took the white of both (the layout model's boxes of two touching bubbles, a classical shape
made from a crop that holds the neighbour too), a block of text found beside a bubble whose box reaches into it, the
grown room of display lettering on the art (`pipeline._art_room`), a reader's rectangle drawn over a bubble. Lettered
as they are, two translations would be set over each other there. Balloons may be joined, but the texts in them never
overlap, so neither do the rooms they are lettered in: a pixel two or more rooms hold goes to the region whose own
lettering (its letter box: the Japanese it replaces) is nearest, so that the shared white is cut between the texts -
across the waist of two fused balloons, round a small caption inside a larger region's box - and each translation is
set in its own part. The rest of each mask stays its own: an ordinary bubble that overlaps nothing keeps all of it.

Only the regions whose text is lettered or is to be (`holds_text`: translated, read as Japanese, or made "erase
only") take part: a candidate the reading turned down takes nothing from a neighbour. The part a region gives up is
kept on it (`TextRegion.ceded`, page coordinates, memory only) and taken out of its mask where its translation is set
and its room is measured (`room_mask`); its erase is left alone (each region still erases its own lettering), and
nothing of it is stored: a page from the cache is shared out afresh each time it is lettered.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np

from ..regions import ERASED, Box, TextRegion

LETTERED = ("translated", "untranslated", ERASED)  # the statuses of a region whose text is lettered or is to be


def holds_text(region: Any) -> bool:
    """Whether *region*'s text is lettered, or is to be: it has a room to defend."""
    return getattr(region, "status", "") in LETTERED


def _mask_of(r: TextRegion) -> np.ndarray:
    mask = r.mask
    if mask.shape != (r.height, r.width):
        mask = cv2.resize(mask, (max(1, r.width), max(1, r.height)), interpolation=cv2.INTER_NEAREST)
    return mask > 0


def _meet(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _distance_to(box: Box, frame: Box) -> np.ndarray:
    """Each pixel of *frame*'s distance to the rectangle *box* (0 inside it), both in page coordinates."""
    fx0, fy0, fx1, fy1 = frame
    xs = np.arange(fx0, fx1, dtype=np.float32) + 0.5
    ys = np.arange(fy0, fy1, dtype=np.float32) + 0.5
    dx = np.maximum(np.maximum(box[0] - xs, xs - box[2]), 0.0)
    dy = np.maximum(np.maximum(box[1] - ys, ys - box[3]), 0.0)
    return np.hypot(dy[:, None], dx[None, :])


def _centre_distance(box: Box, frame: Box) -> np.ndarray:
    fx0, fy0, fx1, fy1 = frame
    xs = np.arange(fx0, fx1, dtype=np.float32) + 0.5 - (box[0] + box[2]) / 2.0
    ys = np.arange(fy0, fy1, dtype=np.float32) + 0.5 - (box[1] + box[3]) / 2.0
    return np.hypot(ys[:, None], xs[None, :])


def lettering_of(r: TextRegion) -> Box:
    """The box of the lettering a region's translation replaces: its lettering box, else its text box."""
    return tuple(r.letter_box or r.text_box)  # type: ignore[return-value]


def share_rooms(regions: Sequence[TextRegion], rooms: dict[int, TextRegion] | None = None,
                among: Sequence[TextRegion] = ()) -> int:
    """Share out the rooms of *regions* (one page's, in page coordinates) where they overlap: every pixel that the
    rooms of two or more regions holding text (`holds_text`) take goes to the one whose lettering (`lettering_of`) is
    nearest (on a tie, whose lettering's centre is); the others give it up (`TextRegion.ceded`). *rooms*: the room a
    region is lettered in where it is not its own box and mask (display lettering on the art grows one,
    `pipeline._art_room`), by the region's id. *among*: more regions of the page whose text is or will be lettered
    there (whatever their status) that keep their part of a shared room but are not changed here (lettered
    elsewhere, held by another thread). Every region of *regions* gets its `ceded` set anew (None: it gives up
    nothing; the part it gave up before, the very object, when it gives up the same). Returns the number of regions
    that gave something up."""
    before = {id(r): getattr(r, "ceded", None) for r in regions}
    for r in regions:
        r.ceded = None
    mine = [r for r in regions if holds_text(r)]
    holders = mine + [r for r in among if all(r is not q for q in mine)]
    if len(holders) < 2 or not mine:
        return 0
    rooms = rooms or {}
    shapes = [rooms.get(id(r), r) for r in holders]
    n = len(holders)
    # clusters of rooms that overlap: shared out together (three fused balloons, a caption between two)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    masks = [_mask_of(q) for q in shapes]
    for a in range(n):
        for b in range(a + 1, n):
            qa, qb = shapes[a], shapes[b]
            if not _meet(qa.bbox, qb.bbox):
                continue
            x0, y0 = max(qa.x0, qb.x0), max(qa.y0, qb.y0)
            x1, y1 = min(qa.x1, qb.x1), min(qa.y1, qb.y1)
            ma = masks[a][y0 - qa.y0:y1 - qa.y0, x0 - qa.x0:x1 - qa.x0]
            mb = masks[b][y0 - qb.y0:y1 - qb.y0, x0 - qb.x0:x1 - qb.x0]
            if (ma & mb).any():
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    gave = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        frame = (min(shapes[i].x0 for i in members), min(shapes[i].y0 for i in members),
                 max(shapes[i].x1 for i in members), max(shapes[i].y1 for i in members))
        fx0, fy0, fx1, fy1 = frame
        held = np.zeros((len(members), fy1 - fy0, fx1 - fx0), bool)
        for k, i in enumerate(members):
            q = shapes[i]
            held[k, q.y0 - fy0:q.y1 - fy0, q.x0 - fx0:q.x1 - fx0] = masks[i]
        shared = held.sum(axis=0) >= 2
        if not shared.any():
            continue
        ys, xs = np.nonzero(shared)
        sub = (fx0 + int(xs.min()), fy0 + int(ys.min()), fx0 + int(xs.max()) + 1, fy0 + int(ys.max()) + 1)
        sx0, sy0, sx1, sy1 = sub[0] - fx0, sub[1] - fy0, sub[2] - fx0, sub[3] - fy0
        here = held[:, sy0:sy1, sx0:sx1]
        cost = np.stack([_distance_to(lettering_of(holders[i]), sub) + 1e-3 * _centre_distance(lettering_of(holders[i]), sub)
                         for i in members])
        cost = np.where(here, cost, np.inf)
        owner = np.argmin(cost, axis=0)
        overlap = shared[sy0:sy1, sx0:sx1]
        for k, i in enumerate(members):
            if i >= len(mine):
                continue  # (one of *among*: left as it is)
            lost = overlap & here[k] & (owner != k)
            if lost.any():
                ys, xs = np.nonzero(lost)
                bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
                ceded = ((sub[0] + bx0, sub[1] + by0, sub[0] + bx1, sub[1] + by1),
                         np.ascontiguousarray(lost[by0:by1, bx0:bx1]))
                old = before.get(id(holders[i]))
                if old is not None and old[0] == ceded[0] and np.array_equal(old[1], ceded[1]):
                    ceded = old  # (the same part as before, the very object: a measure kept by it stays kept)
                holders[i].ceded = ceded
                gave += 1
    return gave


def shifted(ceded: Any, dx: int, dy: int) -> Any:
    """A region's `TextRegion.ceded` as seen from a corner moved by (-dx, -dy): its box shifted by (dx, dy)."""
    if ceded is None:
        return None
    (x0, y0, x1, y1), lost = ceded
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy), lost


def room_mask(region: TextRegion) -> np.ndarray:
    """*region*'s mask without the part it gave up to its neighbours (`share_rooms`): where its translation is set and
    its room measured. Its mask itself when it gave up nothing, or when nothing would be left of it."""
    ceded = getattr(region, "ceded", None)
    mask = region.mask
    if ceded is None:
        return mask
    (cx0, cy0, cx1, cy1), lost = ceded
    x0, y0, x1, y1 = max(cx0, region.x0), max(cy0, region.y0), min(cx1, region.x1), min(cy1, region.y1)
    if x1 <= x0 or y1 <= y0 or mask.shape != (region.height, region.width):
        return mask
    out = mask.copy()
    part = out[y0 - region.y0:y1 - region.y0, x0 - region.x0:x1 - region.x0]
    part[lost[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0]] = 0
    return out if out.any() else mask


def in_own_room(region: TextRegion) -> TextRegion:
    """*region* as its translation is set: a copy with `room_mask` as its mask when it gave something up, else
    *region* itself."""
    if getattr(region, "ceded", None) is None:
        return region
    mask = room_mask(region)
    if mask is region.mask:
        return region
    import copy

    q = copy.copy(region)
    q.mask = mask
    q.ceded = None
    return q
