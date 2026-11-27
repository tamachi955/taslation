"""The erase's measures in pixels, held to the size of the page they are taken on.

The erase's measures in pixels - the ring round a region's lettering its ground is judged on, how far its lettering
is followed past its box, the white ring of outlined lettering, the band of ground round a hole, the closings that
seal a gap in a bubble's outline - were set on the sample set's pages, about `TUNED_HEIGHT` px high. The viewer shows
pages smaller (about 1000 px, a single page in a small window smaller still), where the same pixels reach further
round the lettering: a ring of 14 px round a white bubble's lettering reached its outline more often, and the bubble
went to the inpainting (on the sample set's 214 pages, 134 regions erased by the model at full size, 181 at 1000 px
of height). So each region carries the scale of the page it lies on (`TextRegion.scale`, from its page unit's height
where the pipeline places it on a unit: `page_scale`), and a measure is taken at that scale (`px`, `disc`, `area`).

A page as high as the sample set's or higher keeps the measures as they were set: they are never grown, so nothing
changes at the size they were set at, nor on made-up pages at print size, whose lettering has the sample set's size in
pixels. What depends on the pixels themselves and not on the page - a pixel of anti-aliasing round a stroke, the hole's
growth past it (`artwork.GROW`), the smallest pieces counted - stays as it is."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import cv2
import numpy as np

TUNED_HEIGHT = 1170  # px: the height of the sample set's pages, on which the erase's measures were set
LEAST = 0.35  # a page smaller than this share of that (a thumbnail) is taken at this scale


def page_scale(height: float) -> float:
    """The scale of a page *height* px high (its page unit's): its height against `TUNED_HEIGHT`, at most 1 and at
    least `LEAST`; 0.0 (unknown, taken as 1) for no height."""
    if height <= 0:
        return 0.0
    return max(LEAST, min(1.0, float(height) / TUNED_HEIGHT))


def of(region: Any) -> float:
    """The scale *region* is erased at: its page's (`TextRegion.scale`), 1.0 where none was set."""
    s = float(getattr(region, "scale", 0.0) or 0.0)
    return s if s > 0 else 1.0


def px(value: float, scale: float, least: int = 1) -> int:
    """*value* px at *scale*, rounded, at least *least*."""
    return max(least, int(round(value * scale)))


def area(value: float, scale: float) -> float:
    """A count of pixels (an area) of *value* at *scale*."""
    return value * scale * scale


def side(size: int, scale: float) -> int:
    """The side of a square kernel *size* px wide (odd) at *scale*: its reach past the centre held to the scale, at
    least one pixel."""
    return 2 * max(1, int(round((size - 1) / 2 * scale))) + 1


@lru_cache(maxsize=64)
def _disc(n: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def disc(size: int, scale: float) -> np.ndarray:
    """An elliptic kernel *size* px wide at *scale* (`side`). Shared: never written to."""
    return _disc(side(size, scale))
