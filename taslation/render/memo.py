"""Pages and erases lettered in this session, kept in memory so that a page shown again comes back at once.

Nothing here is written anywhere: the pixels stay in RAM, within a byte budget, and go with the process (or
`clear`).

* `ShownPages`: a page from the cache, lettered (`Pipeline.process`), by the digest of the capture's pixels in its
  capture area and a signature of everything its lettering was made from (the cache entries and the reader's
  annotations of its units, the settings, the series sheet's lettering, the models in use). Shown again - the same
  pixels, nothing of that changed - the page is the stored lettering laid over the new capture: no detection, no
  erase, no typesetting. Any change of a translation, a note, a style, a setting or a single pixel of the capture
  area gives another key, and the page is lettered from scratch.
* `ErasedRegions`: what erasing a region did (the inpainting model on the art, most of all), by `Pipeline.erase_key`
  (the region, the settings of the erase and the pixels round it), as the whole-book run's erased pages hold it
  (`pageimages.PageImages`): a page shown again whose pixels changed elsewhere (the pointer over another bubble)
  takes the erase of every other region from here.
"""

from __future__ import annotations

import copy
import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Sequence

import cv2
import numpy as np

SHOWN_BUDGET = 96 * 1024 * 1024  # bytes of lettering kept for the pages shown (a page is a few MB at most)
ERASED_BUDGET = 64 * 1024 * 1024  # bytes of erased pixels kept for the regions erased live


def pixels_digest(rgb: np.ndarray, box: tuple[int, int, int, int]) -> bytes:
    """A digest of *rgb*'s pixels in *box* (and of its shape): what tells one capture of a page from another."""
    x0, y0, x1, y1 = box
    h = hashlib.blake2b(digest_size=20)
    h.update(repr((rgb.shape, box)).encode())
    h.update(np.ascontiguousarray(rgb[y0:y1, x0:x1]).data)
    return h.digest()


def signature(*parts: Any) -> bytes:
    """A digest of the reprs of *parts*: the inputs of a page's lettering besides its pixels."""
    h = hashlib.blake2b(digest_size=20)
    for part in parts:
        h.update(repr(part).encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.digest()


@dataclass
class ShownPage:
    """A lettered page: where it differs from its capture (*box*, the packed *changed* mask in it, the *pixels*
    there) and its regions as the render left them (copies: a page handed out is never the one kept)."""

    box: tuple[int, int, int, int]
    changed: np.ndarray  # np.packbits of the changed mask in box, row-major
    pixels: np.ndarray  # (n, 3) uint8: the lettered page's pixels where it changed
    regions: list[Any]
    notes: list[str]
    seq: int | None

    @property
    def nbytes(self) -> int:
        return int(self.changed.nbytes + self.pixels.nbytes) + sum(_region_bytes(r) for r in self.regions)

    def lay_over(self, rgb: np.ndarray) -> np.ndarray:
        """The lettering on a copy of the capture *rgb* (of the page's size)."""
        out = rgb.copy()
        x0, y0, x1, y1 = self.box
        if x1 > x0 and y1 > y0:
            n = (x1 - x0) * (y1 - y0)
            mask = np.unpackbits(self.changed, count=n).reshape(y1 - y0, x1 - x0).astype(bool)
            out[y0:y1, x0:x1][mask] = self.pixels
        return out


def changed_pixels(before: np.ndarray, after: np.ndarray) -> tuple[tuple[int, int, int, int], np.ndarray | None]:
    """Where two pages of one size (H x W x 3, uint8) differ: the box of the pixels that differ and the mask of them
    in it (bool), or ((0, 0, 0, 0), None) when none does. (OpenCV's: a third of numpy's time on a full-screen frame.)"""
    diff = cv2.absdiff(np.ascontiguousarray(before), np.ascontiguousarray(after))
    if diff.ndim == 3:
        channels = cv2.split(diff)
        diff = channels[0]
        for c in channels[1:]:
            diff = cv2.max(diff, c)
    x, y, w, h = cv2.boundingRect(diff)
    if w == 0 or h == 0:
        return (0, 0, 0, 0), None
    return (x, y, x + w, y + h), diff[y:y + h, x:x + w] > 0


def _copied(regions: Sequence[Any], keep_inpainted: bool = True) -> list[Any]:
    """Deep copies of *regions*: a page handed out shares nothing with the one kept, so that what is done to its
    regions (an edit, an erase that cuts a mask back) never reaches the next showing. Without *keep_inpainted*,
    without what the inpainting model filled in for them (its erase is kept by `ErasedRegions`)."""
    out = [copy.deepcopy(r) for r in regions]
    if not keep_inpainted:
        for r in out:
            if getattr(r, "inpainted", None) is not None:
                r.inpainted = None
    return out


def _region_bytes(r: Any) -> int:
    mask = getattr(r, "mask", None)
    return int(mask.nbytes) if isinstance(mask, np.ndarray) else 0


class ShownPages:
    """The pages lettered from the cache this session (`ShownPage`), by key, within *budget* bytes (the oldest
    shown goes first). Safe to use from several threads."""

    def __init__(self, budget: int = SHOWN_BUDGET):
        self.budget = int(budget)
        self._pages: OrderedDict[bytes, ShownPage] = OrderedDict()
        self._used = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._pages)

    def get(self, key: bytes) -> tuple[list[Any], ShownPage] | None:
        """The page kept under *key* (marked as shown last) and copies of its regions; None when none is."""
        with self._lock:
            page = self._pages.get(key)
            if page is None:
                self.misses += 1
                return None
            self._pages.move_to_end(key)
            self.hits += 1
        return _copied(page.regions), page

    def put(self, key: bytes, original: np.ndarray, lettered: np.ndarray, regions: Sequence[Any],
            notes: Sequence[str], seq: int | None) -> None:
        """Keep the page *lettered* from the capture *original* under *key*, with copies of its *regions*."""
        box, part = changed_pixels(original, lettered)
        if part is not None:
            changed = np.packbits(part.ravel())
            pixels = lettered[box[1]:box[3], box[0]:box[2]][part].copy()
        else:
            changed, pixels = np.zeros(0, np.uint8), np.zeros((0, 3), np.uint8)
        page = ShownPage(box, changed, pixels, _copied(regions, keep_inpainted=False), list(notes), seq)
        size = page.nbytes
        if size > self.budget:
            return
        with self._lock:
            old = self._pages.pop(key, None)
            if old is not None:
                self._used -= old.nbytes
            while self._pages and self._used + size > self.budget:
                _k, gone = self._pages.popitem(last=False)
                self._used -= gone.nbytes
            self._pages[key] = page
            self._used += size

    def clear(self) -> None:
        with self._lock:
            self._pages.clear()
            self._used = 0


@dataclass(frozen=True)
class _Erased:
    record: Any  # pageimages.ErasedRegion
    pixels: np.ndarray  # (n, 3): the erased page's pixels where the erase changed it, in its box


class ErasedRegions:
    """What the live erases of this session did (`pageimages.ErasedRegion` and the pixels it changed), by erase key,
    within *budget* bytes (the oldest first). Safe to use from several threads. ``reused`` counts the regions taken
    from here."""

    def __init__(self, budget: int = ERASED_BUDGET):
        self.budget = int(budget)
        self._items: OrderedDict[bytes, _Erased] = OrderedDict()
        self._used = 0
        self._lock = threading.Lock()
        self.reused = 0

    def __len__(self) -> int:
        return len(self._items)

    def put(self, record: Any, erased: np.ndarray, mask: np.ndarray | None = None) -> None:
        """Keep *record* (an `ErasedRegion`) with the pixels it changed on *erased* (the page after its erase; *mask*:
        `record.mask()`, when it is at hand)."""
        x0, y0, x1, y1 = record.box
        if x1 <= x0 or y1 <= y0:
            pixels = np.zeros((0, 3), np.uint8)
        else:
            pixels = erased[y0:y1, x0:x1][record.mask() if mask is None else mask].copy()
        item = _Erased(record, pixels)
        size = int(pixels.nbytes) + len(record.changed) + len(record.new_mask) + 64
        if size > self.budget:
            return
        with self._lock:
            old = self._items.pop(record.key, None)
            if old is not None:
                self._used -= int(old.pixels.nbytes) + len(old.record.changed) + len(old.record.new_mask) + 64
            while self._items and self._used + size > self.budget:
                _k, gone = self._items.popitem(last=False)
                self._used -= int(gone.pixels.nbytes) + len(gone.record.changed) + len(gone.record.new_mask) + 64
            self._items[record.key] = item
            self._used += size

    def has(self, key: bytes) -> bool:
        with self._lock:
            return key in self._items

    def take(self, key: bytes, out: np.ndarray) -> Any | None:
        """The erase kept under *key* put on *out* (only the pixels it changed); its `ErasedRegion`, or None when
        none is kept (or it does not fit on *out*)."""
        with self._lock:
            item = self._items.get(key)
            if item is not None:
                self._items.move_to_end(key)
        if item is None:
            return None
        x0, y0, x1, y1 = item.record.box
        if x1 > out.shape[1] or y1 > out.shape[0]:
            return None
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1][item.record.mask()] = item.pixels
        self.reused += 1
        return item.record

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._used = 0
