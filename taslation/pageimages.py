"""The page images of a whole-book run, in memory only: every turned page, compressed without loss, within a cap.

The reading pass (`taslation.batch`) never asks the reader to wait for the OCR: every frame the reader turns to is kept
here until it is read, and after that for as long as there is room, so that the erase can be done ahead
(`Pipeline.erase_page`) and the run's translation can show the page it translates (`translation_view`, the run's
progress). After the run the erased pages serve the render of a page the viewer shows (``Pipeline.erased_ahead``) and
nothing else: no page is ever shown from here to be read (reading is on the viewer). Nothing here is ever written
anywhere: the images are PNG data in RAM (`pack`, `cv2.imencode` of the very array, so `unpack` gives back the same
pixels, bit for bit), and they go with the run's `PageImages` (dropped by `clear`, by the next run, or when the window
closes). Nothing is logged.

What is held, per page (*key*: the run's order of first sight, `BatchReader`'s *seq*; a frame without a page unit gets a
negative key of its own):

* the frame, *unread* while it waits on the backlog: never let go to make room, so no page the reader turned is lost;
  once read it stays as long as there is room, *pending* while its erase is still to come;
* the erased page (`put_erased`): the frame with every region the render will erase erased, and for each region an
  `ErasedRegion` (the key the render finds it by, the paper colour, the pixels its erase changed). It takes the frame's
  place: it is the best image of the page for the render. With it goes its `Undo` (the frame's own pixels where the
  erase changed it), so that the frame can be made again from it, bit for bit (`original`): the page being translated
  is never shown as a bare erased page;
* the page's regions as the run found them (`put_regions`, `KeptRegions`: their masks packed), on which the page being
  translated is lettered (`Pipeline.page_picture`, `PageDraft`), for as long as an image of the page is held.

The cap (`cap`, bytes) holds all of it together. A frame that does not fit first makes room: frames read and not needed
for an erase go first, then erased pages, then frames still waiting for their erase (that page then erases on show, as
without the erase ahead), the oldest first; only when the unread frames alone fill the cap does `put_frame` refuse,
and the batch asks the reader to wait (``batch.backlog_full``). An erased page that does not fit is not kept: the page
erases on show.

Frame sizes measured on the development machine (2026-11-03): an OpenMantra page (830 x 1170) is 2.85 MB raw and
0.66 MB packed (40 ms to pack at PNG level 1, 10 ms to unpack); a two-page spread of a browser viewer (1920 x 1032)
about 1.5 MB packed. A volume of 200 screens holds about 130-300 MB, its erased pages as much again: the default cap
of 2 GB (`Settings.batch_memory_mb`) is a ceiling the usual book stays far below, and never more than a quarter of the
machine's memory (`memory_cap`): 2 GB on an 8 GB machine, which leaves room for the OCR, the viewer and Ollama.
"""

from __future__ import annotations

import copy
import ctypes
import hashlib
import io
import os
import sys
import threading
import zlib
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import cv2
import numpy as np
from PIL import Image

MB = 1024 * 1024
PNG_LEVEL = 1  # zlib level of the packing: 1 packs a page in 40 ms to 0.66 MB, 3 in 57 ms to 0.60 MB (measured)
RAM_SHARE = 4  # the cap is never more than this part of the machine's memory


@dataclass(frozen=True)
class Packed:
    """An image packed without loss, in memory: its PIL mode and size, and PNG data."""

    mode: str
    size: tuple[int, int]
    data: bytes

    @property
    def nbytes(self) -> int:
        return len(self.data)


def pack(image: Image.Image) -> Packed:
    """*image* as PNG data in memory (never a file). The array is packed as it is (no channel swap: `unpack` reads it
    back the same way), so the pixels come back bit for bit; a mode other than L, RGB and RGBA goes through PIL's PNG,
and one PNG has not as its bytes, deflated."""
    if image.mode in ("L", "RGB", "RGBA"):
        ok, buf = cv2.imencode(".png", np.asarray(image), [cv2.IMWRITE_PNG_COMPRESSION, PNG_LEVEL])
        if ok:
            return Packed(image.mode, image.size, buf.tobytes())
    out = io.BytesIO()
    try:
        image.save(out, format="PNG", compress_level=PNG_LEVEL)
    except OSError:  # a mode PNG has not (CMYK): its bytes, deflated
        return Packed("raw:" + image.mode, image.size, zlib.compress(image.tobytes(), PNG_LEVEL))
    return Packed("PIL", image.size, out.getvalue())


def unpack(packed: Packed) -> Image.Image:
    """The image `pack` packed, as it was."""
    if packed.mode.startswith("raw:"):
        return Image.frombytes(packed.mode[4:], packed.size, zlib.decompress(packed.data))
    if packed.mode == "PIL":
        with Image.open(io.BytesIO(packed.data)) as im:
            im.load()
            return im.copy()
    array = cv2.imdecode(np.frombuffer(packed.data, np.uint8), cv2.IMREAD_UNCHANGED)
    return Image.fromarray(array)  # (L, RGB and RGBA by the array's shape: the mode it was packed in)


@dataclass(frozen=True)
class Undo:
    """What makes a frame again from its erased page: *box*, the part of the page the erase changed, *mask*
    (`np.packbits` of the pixels it changed there, row by row) and *pixels*, the frame's own pixels at those,
    zlib-packed (an erase changes the bubbles only: a few hundred KB of a page's pixels, packed to far less)."""

    box: tuple[int, int, int, int]
    mask: bytes
    pixels: bytes

    @property
    def nbytes(self) -> int:
        return len(self.mask) + len(self.pixels)


def undo_of(frame: np.ndarray, erased: np.ndarray) -> Undo:
    """The `Undo` that makes *frame* again from *erased* (the frame with regions erased, of one size)."""
    box, mask = changed_region(frame, erased)
    x0, y0, x1, y1 = box
    if not mask:
        return Undo(box, b"", b"")
    m = np.unpackbits(np.frombuffer(mask, np.uint8), count=(x1 - x0) * (y1 - y0)).reshape(y1 - y0, x1 - x0)
    pixels = np.ascontiguousarray(frame[y0:y1, x0:x1][m.astype(bool)])
    return Undo(box, mask, zlib.compress(pixels.tobytes(), PNG_LEVEL))


def undone(erased: np.ndarray, undo: Undo) -> np.ndarray:
    """The frame again: a copy of *erased* with *undo*'s pixels put back."""
    out = np.array(erased, copy=True)
    x0, y0, x1, y1 = undo.box
    if undo.mask and x1 > x0 and y1 > y0:
        m = np.unpackbits(np.frombuffer(undo.mask, np.uint8), count=(x1 - x0) * (y1 - y0)).reshape(y1 - y0, x1 - x0)
        part = out[y0:y1, x0:x1]
        part[m.astype(bool)] = np.frombuffer(zlib.decompress(undo.pixels), np.uint8).reshape(-1, *part.shape[2:])
    return out


class KeptRegions:
    """A page's regions kept with its images: copies, their masks zlib-packed and what only the reading needed left
    out (the regions they came from, LaMa's memo); `regions` gives fresh copies with their masks back, alike to the
    last bit (`Pipeline.erase_key` finds their erase ahead by them)."""

    LEFT_OUT = ("after", "adopted", "before_beyond", "repeats", "inpainted")

    def __init__(self, regions: Sequence[Any]):
        self._kept: list[tuple[Any, bytes, tuple[int, ...], str]] = []
        for region in regions:
            mask = np.ascontiguousarray(np.asarray(region.mask))
            kept = copy.copy(region)
            kept.mask = None
            for name in self.LEFT_OUT:
                if getattr(kept, name, None) is not None:
                    setattr(kept, name, None)
            self._kept.append((kept, zlib.compress(mask.tobytes(), 1), tuple(mask.shape), str(mask.dtype)))
        self.nbytes = sum(len(packed) for _r, packed, _s, _d in self._kept) + 512 * len(self._kept)

    def __len__(self) -> int:
        return len(self._kept)

    def regions(self) -> list[Any]:
        out = []
        for kept, packed, shape, dtype in self._kept:
            region = copy.copy(kept)
            region.mask = np.frombuffer(zlib.decompress(packed), dtype).reshape(shape).copy()
            region.char_boxes = list(getattr(kept, "char_boxes", []) or [])
            region.char_quads = list(getattr(kept, "char_quads", []) or [])
            region.flags = list(getattr(kept, "flags", []) or [])
            out.append(region)
        return out


def physical_memory() -> int:
    """The machine's memory in bytes (0 when it cannot be told)."""
    try:
        if sys.platform == "win32":
            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = Status()
            status.dwLength = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                return int(status.ullTotalPhys)
            return 0
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return 0


def memory_cap(setting_mb: int) -> int:
    """The cap in bytes for the setting *setting_mb*: at most a `RAM_SHARE`-th of the machine's memory."""
    cap = max(0, int(setting_mb)) * MB
    total = physical_memory()
    return min(cap, total // RAM_SHARE) if total else cap


@dataclass(frozen=True)
class ErasedRegion:
    """What erasing one region did to its page: *key* (`Pipeline.erase_key`: the region and the pixels around it, as
    the render sees them), *background* (the paper colour `Pipeline._erase` returned, what the lettering is set against),
    *box* (the part of the page the erase changed) and *changed* (`np.packbits` of the pixels it changed there, row by
    row). The pixels themselves are on the erased page. *new_mask*: the region's mask as the erase left it, when it
    cut the mask back to the bubble's outline (`erase_region` sets it; the lettering is fitted to it), zlib-packed,
    with *mask_shape*; empty when the erase left the mask alone."""

    key: bytes
    background: tuple[int, int, int]
    box: tuple[int, int, int, int]
    changed: bytes
    new_mask: bytes = b""
    mask_shape: tuple[int, int] = (0, 0)

    def mask(self) -> np.ndarray:
        x0, y0, x1, y1 = self.box
        n = (x1 - x0) * (y1 - y0)
        return np.unpackbits(np.frombuffer(self.changed, np.uint8), count=n).reshape(y1 - y0, x1 - x0).astype(bool)

    def paste(self, out: np.ndarray, erased: np.ndarray) -> None:
        """The region's erase put on *out* from the erased page *erased*: only the pixels it changed."""
        x0, y0, x1, y1 = self.box
        if x1 <= x0 or y1 <= y0:
            return
        m = self.mask()
        out[y0:y1, x0:x1][m] = erased[y0:y1, x0:x1][m]

    def settle(self, region: Any) -> None:
        """*region* as its erase would have left it: the mask cut back, when it was."""
        if self.new_mask:
            region.mask = np.frombuffer(zlib.decompress(self.new_mask), np.uint8).reshape(self.mask_shape).copy()


def packed_mask(before: np.ndarray, after: np.ndarray) -> tuple[bytes, tuple[int, int]]:
    """`ErasedRegion.new_mask` and its shape: *after* packed when it differs from *before*, else nothing."""
    if after is before or (after.shape == before.shape and np.array_equal(after, before)):
        return b"", (0, 0)
    mask = np.ascontiguousarray(after, np.uint8)
    return zlib.compress(mask.tobytes(), 1), (int(mask.shape[0]), int(mask.shape[1]))


def changed_region(before: np.ndarray, after: np.ndarray) -> tuple[tuple[int, int, int, int], bytes]:
    """The box of the pixels that differ between two pages of one size, and their mask packed (`ErasedRegion`)."""
    diff = np.any(before != after, axis=2) if before.ndim == 3 else before != after
    ys, xs = np.nonzero(diff)
    if not xs.size:
        return (0, 0, 0, 0), b""
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return box, np.packbits(diff[box[1]:box[3], box[0]:box[2]].ravel()).tobytes()


class PageImages:
    """The page images of a run, within *cap* bytes (see the module's docstring). Safe to use from the batch's threads.
    *on_change*(used, cap) is called after every change, outside the lock."""

    def __init__(self, cap: int, on_change: Callable[[int, int], None] | None = None):
        self.cap = int(cap)
        self.on_change = on_change
        self._lock = threading.RLock()
        self._frames: dict[int, Packed] = {}
        self._erased: dict[int, Packed] = {}
        self._records: dict[int, list[ErasedRegion]] = {}
        self._index: dict[bytes, tuple[int, int]] = {}  # an ErasedRegion's key -> (its page's key, its index)
        self._unread: set[int] = set()
        self._pending: set[int] = set()
        self._shape: dict[int, tuple[int, int]] = {}  # an erased page's (height, width)
        self._undo: dict[int, Undo] = {}  # an erased page's `Undo`: its frame made again from it (`original`)
        self._regions: dict[int, KeptRegions] = {}  # a page's regions (`put_regions`), while an image of it is held
        self.largest = 0  # the largest frame packed so far, in bytes: what the next one is reckoned at
        self.reused = 0  # regions the render took from an erased page
        self.erased_live = 0  # regions the render erased itself while erased pages were here

    # ------------------------------------------------------------------ the count
    @property
    def used(self) -> int:
        with self._lock:
            return (sum(p.nbytes for p in self._frames.values()) + sum(p.nbytes for p in self._erased.values())
                    + sum(u.nbytes for u in self._undo.values()) + sum(r.nbytes for r in self._regions.values()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames.keys() | self._erased.keys())

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change(self.used, self.cap)

    def unread(self) -> int:
        with self._lock:
            return len(self._unread)

    # ------------------------------------------------------------------ making room
    def _evictable(self) -> list[tuple[str, int]]:
        """What may go to make room for a frame, in the order it goes (see the module's docstring)."""
        spare = sorted(k for k in self._frames if k not in self._unread and k not in self._pending)
        pending = sorted(k for k in self._pending if k in self._frames)
        return [("frame", k) for k in spare] + [("erased", k) for k in sorted(self._erased)] + \
               [("frame", k) for k in pending]

    def _drop(self, kind: str, key: int) -> None:
        if kind == "frame":
            self._frames.pop(key, None)
            self._pending.discard(key)
        else:
            self._erased.pop(key, None)
            self._shape.pop(key, None)
            self._undo.pop(key, None)
            for record in self._records.pop(key, []):
                if self._index.get(record.key, (None,))[0] == key:
                    del self._index[record.key]
        if key not in self._frames and key not in self._erased:
            self._regions.pop(key, None)  # (no image of the page left to letter them on)

    def room_for(self, nbytes: int) -> bool:
        """Whether *nbytes* more fit, once what may go has gone (nothing is let go here)."""
        with self._lock:
            fixed = sum(self._frames[k].nbytes for k in self._unread if k in self._frames)
            return fixed + nbytes <= self.cap

    def _make_room(self, nbytes: int, order: Sequence[tuple[str, int]]) -> bool:
        used = self.used
        for kind, key in order:
            if used + nbytes <= self.cap:
                break
            store = self._frames if kind == "frame" else self._erased
            if key in store:
                used -= store[key].nbytes
                self._drop(kind, key)
        return used + nbytes <= self.cap

    # ------------------------------------------------------------------ frames
    def put_frame(self, key: int, packed: Packed) -> bool:
        """Keep the frame *packed* of the page *key*, unread, making room as the module's docstring says. False when the
        unread frames leave no room for it: nothing is kept then."""
        with self._lock:
            self.largest = max(self.largest, packed.nbytes)
            if not self._make_room(packed.nbytes, self._evictable()):
                return False
            self._frames[key] = packed
            self._unread.add(key)
        self._changed()
        return True

    def replace_unread(self, key: int, packed: Packed) -> bool:
        """The frame of *key* replaced by *packed* (a sharper picture of the same page) while it waits to be read; False,
        and nothing changed, once it has been read, or when the new one does not fit."""
        with self._lock:
            old = self._frames.get(key)
            if old is None or key not in self._unread:
                return False
            if self.used - old.nbytes + packed.nbytes > self.cap:
                return False
            self._frames[key] = packed
            self.largest = max(self.largest, packed.nbytes)
        self._changed()
        return True

    def read(self, key: int, erase: bool) -> None:
        """The frame of *key* has been read; with *erase*, it is kept for the erase to come (*pending*)."""
        with self._lock:
            self._unread.discard(key)
            if erase and key in self._frames:
                self._pending.add(key)

    def frame(self, key: int) -> Image.Image | None:
        with self._lock:
            packed = self._frames.get(key)
        return unpack(packed) if packed is not None else None

    def drop_frame(self, key: int) -> None:
        with self._lock:
            self._unread.discard(key)
            self._drop("frame", key)
        self._changed()

    def not_erased(self, key: int) -> None:
        """The erase of *key* is not done (nothing to erase, a failure): its frame stays as any read frame."""
        with self._lock:
            self._pending.discard(key)

    # ------------------------------------------------------------------ erased pages
    def put_erased(self, key: int, packed: Packed, records: Sequence[ErasedRegion], shape: tuple[int, int],
                   undo: Undo | None = None) -> bool:
        """Keep the erased page of *key* in its frame's place, with its regions found by their keys and its *undo*
        (`undo_of`: without it the frame cannot be made again, and the window gets no picture of the page). Room is
        made from read frames not needed (the frame of *key* first); False when it does not fit: the frame stays as it
        was."""
        need = packed.nbytes + (undo.nbytes if undo is not None else 0)
        with self._lock:
            frame = self._frames.get(key)
            mine = frame.nbytes if frame is not None else 0
            spare = [("frame", k) for k in sorted(self._frames)
                     if k != key and k not in self._unread and k not in self._pending]
            used = self.used - mine
            for kind, k in spare:
                if used + need <= self.cap:
                    break
                used -= self._frames[k].nbytes
                self._drop(kind, k)
            if used + need > self.cap:
                self._pending.discard(key)
                fits = False
            else:
                regions = self._regions.get(key)
                self._drop("frame", key)
                self._drop("erased", key)
                if regions is not None:
                    self._regions[key] = regions
                self._erased[key] = packed
                self._shape[key] = shape
                if undo is not None:
                    self._undo[key] = undo
                self._records[key] = list(records)
                for i, record in enumerate(records):
                    self._index[record.key] = (key, i)
                fits = True
        self._changed()
        return fits

    def erased(self, key: int) -> Image.Image | None:
        with self._lock:
            packed = self._erased.get(key)
        return unpack(packed) if packed is not None else None

    def best(self, key: int) -> Image.Image | None:
        """The erased page of *key* when there is one, else its frame; None when neither is held."""
        with self._lock:
            packed = self._erased.get(key) or self._frames.get(key)
        return unpack(packed) if packed is not None else None

    def original(self, key: int) -> Image.Image | None:
        """The frame of *key* as it was captured: the frame when it is held, else made again from its erased page
        (`Undo`); None when neither can be had (an erased page without its undo is never handed out as the frame)."""
        with self._lock:
            frame = self._frames.get(key)
            erased, undo = self._erased.get(key), self._undo.get(key)
        if frame is not None:
            return unpack(frame)
        if erased is None or undo is None:
            return None
        image = unpack(erased)
        return Image.fromarray(undone(np.asarray(image), undo))

    def put_regions(self, key: int, regions: Sequence[Any]) -> None:
        """Keep the regions of the page *key* as the run found them (`KeptRegions`), while an image of it is held."""
        kept = KeptRegions(regions)
        with self._lock:
            if key not in self._frames and key not in self._erased:
                return
            self._regions[key] = kept
        self._changed()

    def regions(self, key: int) -> list[Any] | None:
        """Fresh copies of the regions kept for the page *key* (`put_regions`); None when none are."""
        with self._lock:
            kept = self._regions.get(key)
        return kept.regions() if kept is not None else None

    def find(self, keys: Sequence[bytes], shape: tuple[int, ...]) -> dict[int, tuple[ErasedRegion, Callable[[], np.ndarray]]]:
        """For each of *keys* (`Pipeline.erase_key` of the regions a render is about to erase) that an erased page of a
        page of *shape* holds: its index in *keys* -> (the `ErasedRegion`, a function that gives the erased page's
        pixels, unpacked once for all of them)."""
        found: dict[int, tuple[ErasedRegion, Callable[[], np.ndarray]]] = {}
        pages: dict[int, Any] = {}
        with self._lock:
            for i, key in enumerate(keys):
                where = self._index.get(key)
                if where is None or self._shape.get(where[0]) != tuple(shape[:2]):
                    continue
                page, n = where
                if page not in pages:
                    packed = self._erased[page]
                    pages[page] = _Lazy(packed)
                found[i] = (self._records[page][n], pages[page])
        return found

    def clear(self) -> None:
        """Let go of every image (the run is over for good, or the window closes)."""
        with self._lock:
            self._frames.clear()
            self._erased.clear()
            self._records.clear()
            self._index.clear()
            self._unread.clear()
            self._pending.clear()
            self._shape.clear()
            self._undo.clear()
            self._regions.clear()
        self._changed()


class _Lazy:
    """An erased page's pixels, unpacked on first use."""

    def __init__(self, packed: Packed):
        self.packed = packed
        self.array: np.ndarray | None = None

    def __call__(self) -> np.ndarray:
        if self.array is None:
            self.array = np.asarray(unpack(self.packed).convert("RGB"))
        return self.array


def region_digest(*parts: Any) -> bytes:
    """A digest of *parts* (arrays by their shape and bytes, anything else by its repr)."""
    h = hashlib.sha1()
    for part in parts:
        if isinstance(part, np.ndarray):
            h.update(repr((part.shape, str(part.dtype))).encode())
            h.update(np.ascontiguousarray(part).tobytes())
        else:
            h.update(repr(part).encode())
        h.update(b"|")
    return h.digest()


__all__ = ["ErasedRegion", "KeptRegions", "MB", "Packed", "PageImages", "Undo", "changed_region", "memory_cap", "pack",
           "packed_mask", "physical_memory", "region_digest", "undo_of", "undone", "unpack"]
