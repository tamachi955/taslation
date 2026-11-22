"""A frame packed in memory without loss (`pageimages.pack`, `unpack`), as the backlog holds the frames of the pages
turned past until it has read them: it comes back bit for bit, and it never goes to a file."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from taslation.pageimages import pack, unpack


def _page() -> Image.Image:
    """Paper with ink here and there."""
    rng = np.random.default_rng(2)
    a = np.full((800, 600, 3), 255, np.uint8)
    for x, y, w, h in zip(rng.integers(20, 500, 60), rng.integers(20, 700, 60), rng.integers(10, 80, 60),
                          rng.integers(10, 80, 60)):
        a[y:y + h, x:x + w] = 0
    return Image.fromarray(a)


def test_a_packed_page_comes_back_bit_for_bit():
    rng = np.random.default_rng(3)
    rgb = rng.integers(0, 256, (123, 77, 3), dtype=np.uint8)
    for image in (Image.fromarray(rgb), Image.fromarray(rgb[..., 0]), Image.fromarray(np.dstack([rgb, rgb[..., :1]])),
                  Image.fromarray(rgb).convert("P"), Image.fromarray(rgb).convert("CMYK")):
        packed = pack(image)
        back = unpack(packed)
        assert back.mode == image.mode and back.size == image.size
        assert back.tobytes() == image.tobytes(), image.mode
        assert packed.nbytes == len(packed.data) and isinstance(packed.data, bytes)


def test_a_page_is_packed_in_memory_and_never_written(monkeypatch):
    def no_file(*_a, **_k):
        raise AssertionError("a page image went to a file")

    save = Image.Image.save
    monkeypatch.setattr(Image.Image, "save", lambda self, fp, *a, **k: no_file() if isinstance(fp, (str, Path))
                        else save(self, fp, *a, **k))
    import cv2

    monkeypatch.setattr(cv2, "imwrite", no_file)
    unpack(pack(_page()))
    unpack(pack(_page().convert("P")))
