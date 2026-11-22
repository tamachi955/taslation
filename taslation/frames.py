"""Frames of the viewer compared, in memory: a small grey `thumbnail` that tells two pages apart (`frames_differ`),
the fine `detail` of a frame cell by cell that tells a soft picture of a page from its sharp one (`sharper`), and how
crisp a picture's edges are whatever it shows (`crispness`, `looks_sharp`, and `SharpSeen` for the pages whose sharp
picture the live view has seen): how the live view (`ui.live`) and the window's other looks at the viewer judge its
frames. `thumb_of` makes the small picture of a screen that the indicator beside the page shows (`backlog`: too
small to read). Nothing here captures, keeps or writes anything: the frames are given."""

from __future__ import annotations

from collections import deque
from typing import Sequence

import cv2
import numpy as np
from PIL import Image

from . import fingerprint


def thumbnail(image: Image.Image, size: int = 64) -> np.ndarray:
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


DETAIL_GRID = 4  # a frame's capture area is looked at in this many cells across and down for its fine detail
DETAIL_FLOOR = 3.0  # a cell with less detail than this (grey levels between neighbouring pixels) is blank
SHARPER = 1.25  # a frame is sharper than another when most of its cells, and all of them together, hold this much more
CRISP_SPAN = 4  # px: `crispness` sets the steps between neighbouring pixels against the steps over this many
CRISP_KEPT = 50  # the crispness of so many soft and sharp pictures of the viewer is what a picture is judged by
# a page whose sharp picture the live view has seen is judged by that picture (`SharpSeen`): a frame of it less crisp
# than PAGE_SHARP_SHARE of it is soft (a soft picture measures 0.3-0.6 of its sharp one, the same picture again the
# same); the newest SHARP_SEEN_KEPT such pages are kept, in memory
PAGE_SHARP_SHARE = 0.85
SHARP_SEEN_KEPT = 256
THUMB_HEIGHT = 96  # px: the thumbnail of a screen told to the window (`backlog`)


def thumb_of(image: Image.Image, height: int = THUMB_HEIGHT) -> Image.Image:
    """A thumbnail of *image* at most *height* px high (RGB)."""
    small = image.convert("RGB")
    if small.height > height:
        small = small.resize((max(1, round(small.width * height / small.height)), height), Image.BILINEAR,
                             reducing_gap=2.0)
    return small.copy() if small is image else small


def detail(image: Image.Image, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """How much fine detail *image* (its part *box*) holds, cell by cell of a DETAIL_GRID x DETAIL_GRID grid: the
    root mean square of the steps in grey levels between neighbouring pixels (along every other row and every other
    column, to be quick). A page drawn from a smaller picture first holds far less of it than the sharp page that
    follows (from half the size: about 2.3 times less on the test pages, from a third 3.3 times), while their
    thumbnails are all but the same; the viewer's toolbar over the page changes it in a few cells only."""
    gray = np.asarray((image.crop(box) if box is not None else image).convert("L"), dtype=np.float32)
    out = np.zeros((DETAIL_GRID, DETAIL_GRID), np.float32)
    h, w = gray.shape[:2]
    if h < 4 * DETAIL_GRID or w < 4 * DETAIL_GRID:
        return out
    across = np.square(np.diff(gray[::2], axis=1))  # row r is the frame's row 2r
    down = np.square(np.diff(gray[:, ::2], axis=0))  # column c is the frame's column 2c
    for i in range(DETAIL_GRID):
        y0, y1 = i * h // DETAIL_GRID, (i + 1) * h // DETAIL_GRID
        for j in range(DETAIL_GRID):
            x0, x1 = j * w // DETAIL_GRID, (j + 1) * w // DETAIL_GRID
            a = across[(y0 + 1) // 2:(y1 + 1) // 2, x0:x1 - 1]
            d = down[y0:y1 - 1, (x0 + 1) // 2:(x1 + 1) // 2]
            out[i, j] = np.sqrt((float(a.mean()) + float(d.mean())) / 2)
    return out


def sharper(before: np.ndarray | None, after: np.ndarray | None) -> bool:
    """Whether the frame whose `detail` is *after* is sharper than the one of *before* (the same page, its sharp
    picture come in): of the cells that are not blank in either, more than half hold SHARPER times more detail, and
    so do they all together. An overlay (the viewer's toolbar) adds detail in a few cells only, noise a little in
    each."""
    if before is None or after is None or before.shape != after.shape:
        return False
    cells = np.maximum(before, after) >= DETAIL_FLOOR
    if not cells.any():
        return False
    b, a = before[cells], after[cells]
    return 2 * int((a >= b * SHARPER).sum()) > int(cells.sum()) and float(a.sum()) >= float(b.sum()) * SHARPER


def frames_differ(a: np.ndarray | None, b: np.ndarray | None, threshold: float = 2.0) -> bool:
    if a is None or b is None or a.shape != b.shape:
        return True
    return float(np.abs(a - b).mean()) > threshold


def crispness(image: Image.Image, box: tuple[int, int, int, int] | None = None) -> float:
    """How crisp the edges of *image* (its part *box*) are, whatever it shows: the mean square step in grey levels
    between neighbouring pixels set against the one over `CRISP_SPAN` pixels (along every other row and column). An
    edge drawn sharp is a step of a pixel or two, one drawn from a smaller picture is spread over several, so a soft
    picture has far less of the first for as much of the second, dense page or sparse: on 40 OpenMantra pages in the
    stand-in viewer the sharp ones measured 0.22-0.34, the same pages drawn from a picture 1.5-3 times smaller
    0.09-0.14 (`tools/fast_turn_eval.py`). A viewer's own scale changes it too, so the live view judges a picture only by
    the soft and sharp pictures its viewer has drawn (`ui.live._drew_soft`)."""
    gray = np.asarray((image.crop(box) if box is not None else image).convert("L"), dtype=np.float32)
    k = CRISP_SPAN
    if gray.shape[0] <= 2 * k or gray.shape[1] <= 2 * k:
        return 0.0
    rows, cols = gray[::2], gray[:, ::2]
    fine = float(np.square(np.diff(rows, axis=1)).mean()) + float(np.square(np.diff(cols, axis=0)).mean())
    wide = float(np.square(rows[:, k:] - rows[:, :-k]).mean()) + float(np.square(cols[k:] - cols[:-k]).mean())
    return fine / wide if wide > 0 else 0.0


def looks_sharp(crisp: float, soft: Sequence[float], sharp: Sequence[float]) -> bool:
    """Whether a picture whose `crispness` is *crisp* is nearer that of the sharp pictures a viewer drew (*sharp*) than
    that of the soft ones it drew first (*soft*), on a geometric scale: how the live view (`ui.live`) judges a picture
    of a viewer that draws a page soft first. False while either is not known."""
    if not soft or not sharp:
        return False
    lo, hi = float(np.median(soft)), float(np.median(sharp))
    return hi > lo and crisp >= (lo * hi) ** 0.5


class SharpSeen:
    """The `crispness` of the sharp pictures a viewer drew of pages it drew soft first (the live view's,
    `ui.live._drew_soft`), by the fingerprint of the picture's first page unit and the picture's size: a frame of one
    of those pages less crisp than its own page's sharp picture (`judge`) is soft, besides those the viewer's pictures
    of all pages find soft (`looks_sharp`) - the soft picture of a page with much fine detail can be as crisp as the
    sharp picture of a page with little. The newest SHARP_SEEN_KEPT pages, in memory only."""

    def __init__(self, kept: int = SHARP_SEEN_KEPT) -> None:
        self._pages: deque[tuple[str, tuple[int, int], float]] = deque(maxlen=kept)

    def note(self, key: str, size: tuple[int, int], crisp: float) -> None:
        self._pages.appendleft((key, (int(size[0]), int(size[1])), float(crisp)))

    def judge(self, key: str, size: tuple[int, int], crisp: float, distance: int) -> bool | None:
        """Whether a picture of *size* whose first page unit's fingerprint is *key* and whose crispness is *crisp* is
        sharp, by the sharp picture seen last of that page (`fingerprint.hamming` within *distance*, at that size):
        at least PAGE_SHARP_SHARE as crisp. None when no picture of the page is kept."""
        size = (int(size[0]), int(size[1]))
        for seen, at, sharp in self._pages:  # (the newest first)
            if at == size and fingerprint.hamming(seen, key) <= distance:
                return crisp >= sharp * PAGE_SHARP_SHARE
        return None

    def clear(self) -> None:
        self._pages.clear()
