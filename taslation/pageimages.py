"""Page images in memory: a frame packed without loss (`pack`, `unpack`: PNG data in RAM, `cv2.imencode` of the very
array, so `unpack` gives back the same pixels, bit for bit), as the backlog holds the frames of the pages turned past
until it has read them (`backlog`), and what erasing one region did (`ErasedRegion`, `packed_mask`, `region_digest`),
as this session's erases keep it (`render.memo.ErasedRegions`). Nothing here is ever written anywhere, and nothing is
logged.

Frame sizes measured on the development machine (2026-11-03): an OpenMantra page (830 x 1170) is 2.85 MB raw and
0.66 MB packed (40 ms to pack at PNG level 1, 10 ms to unpack); a two-page spread of a browser viewer (1920 x 1032)
about 1.5 MB packed.
"""

from __future__ import annotations

import hashlib
import io
import zlib
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image

MB = 1024 * 1024
PNG_LEVEL = 1  # zlib level of the packing: 1 packs a page in 40 ms to 0.66 MB, 3 in 57 ms to 0.60 MB (measured)


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
class ErasedRegion:
    """What erasing one region did to its page: *key* (`Pipeline.erase_key`: the region and the pixels around it, as
    the render sees them), *background* (the paper colour `Pipeline._erase` returned, what the lettering is set against),
    *box* (the part of the page the erase changed) and *changed* (`np.packbits` of the pixels it changed there, row by
    row). *new_mask*: the region's mask as the erase left it, when it cut the mask back to the bubble's outline
    (`erase_region` sets it; the lettering is fitted to it), zlib-packed, with *mask_shape*; empty when the erase left
    the mask alone."""

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


__all__ = ["ErasedRegion", "MB", "Packed", "pack", "packed_mask", "region_digest", "unpack"]
