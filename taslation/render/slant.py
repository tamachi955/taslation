"""Lettering a slanted region: the translation set in the region's own frame, then turned onto the page.

A region whose lettering is turned (``TextRegion.angle``, `taslation.detect.tilt`) is lettered as an upright one is,
in an upright picture of it: its box turned by ``-angle`` with the room that needs, its mask turned with it (so the
lines still follow the bubble's shape and the size still fits it), the drawing under it turned too (so the outline
on art is decided from what lies under the lines; the text and outline colours the reader set go with the lettering,
`typeset.letter_text` passing them on). What the lettering drew there is then turned back by ``angle``
and laid over the page, its edges blended; the rest of the page is left as it was. A region at angle 0 never comes
here: `typeset.letter_text` letters it straight, as before.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..detect.tilt import Upright
from ..regions import TextRegion

Letter = Callable[[Image.Image | None, TextRegion], Any]  # letters a region (upright) on an image, or sizes it on none


def upright_region(region: TextRegion, area: tuple[int, int, int, int] | None = None) -> tuple[TextRegion, Upright]:
    """A copy of *region* as it stands in the upright picture of *area* (a page box round the region; None: the
    region's box): the area turned by ``-angle``, the region's box the box of its turned mask in it, its mask, text
    box and lettering box turned with it, angle 0; and the turn between the two."""
    mask = upright_mask(region)
    ax0, ay0, ax1, ay1 = area if area is not None else region.bbox
    whole = np.zeros((ay1 - ay0, ax1 - ax0), np.uint8)
    whole[region.y0 - ay0:region.y1 - ay0, region.x0 - ax0:region.x1 - ax0] = mask
    turn = Upright(whole.shape, region.angle, (ax0, ay0))
    turned = np.where(turn.turn(whole, 0, nearest=True) > 0, 255, 0).astype(np.uint8)
    ys, xs = np.nonzero(turned)
    if xs.size:
        bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    else:
        bx0, by0, bx1, by1 = turn.forward_box(region.bbox)
    local = copy.copy(region)
    local.angle = 0.0
    local.x0, local.y0, local.x1, local.y1 = bx0, by0, bx1, by1
    local.mask = turned[by0:by1, bx0:bx1].copy()
    local.text_box = turn.forward_box(region.text_box)
    local.letter_box = turn.forward_box(region.letter_box) if region.letter_box is not None else None
    return local, turn


def upright_mask(region: TextRegion) -> np.ndarray:
    """The region's mask at the size of its box."""
    if region.mask.shape == (region.height, region.width):
        return region.mask
    return cv2.resize(region.mask, (region.width, region.height), interpolation=cv2.INTER_NEAREST)


def letter_slanted(image: Image.Image | None, region: TextRegion, letter: Letter) -> Any:
    """Letter *region* (slanted) on *image* with *letter* (`typeset.letter_text` with the text and the settings), in
    the upright picture of the page round it (as far round it as the region is large, for lettering that runs past
    it, as it may upright), and lay what it drew over the page turned back (on no *image*: only how it would be
    set). Returns what *letter* returned."""
    if image is None:
        return letter(None, upright_region(region)[0])
    box = (max(0, region.x0 - region.width // 2), max(0, region.y0 - region.height // 2),
           min(image.width, region.x1 + region.width // 2), min(image.height, region.y1 + region.height // 2))
    box = (min(box[0], region.x0), min(box[1], region.y0), max(box[2], region.x1), max(box[3], region.y1))
    local, turn = upright_region(region, box)
    page = np.asarray(image.convert("RGB").crop(box), dtype=np.uint8)
    h, w = page.shape[:2]
    inside = page[region.y0 - box[1]:region.y1 - box[1], region.x0 - box[0]:region.x1 - box[0]]
    paper = inside[upright_mask(region) > 0] if inside.shape[:2] == (region.height, region.width) else inside.reshape(-1, 3)
    ground = tuple(int(v) for v in np.median(paper if paper.size else page.reshape(-1, 3), axis=0))
    upright = turn.turn(page, ground)
    picture = Image.fromarray(upright)
    done = letter(picture, local)
    drawn = np.asarray(picture.convert("RGB"), dtype=np.uint8)
    changed = np.any(drawn != upright, axis=2)
    if not changed.any():
        return done
    reach = cv2.dilate(changed.astype(np.uint8) * 255, np.ones((3, 3), np.uint8))
    back = turn.turn_back(drawn, (w, h), fill=0)
    alpha = turn.turn_back(reach, (w, h), fill=0).astype(np.float32)[..., None] / 255.0
    out = np.clip(page.astype(np.float32) * (1.0 - alpha) + back.astype(np.float32) * alpha + 0.5, 0, 255)
    image.paste(Image.fromarray(out.astype(np.uint8)), (box[0], box[1]))
    return done


def slanted_outline(region: TextRegion, angle: float | None = None) -> list[tuple[float, float]]:
    """The four page corners of the frame a region is lettered in at *angle* (None: its own): the box of its mask in
    its upright picture, turned back onto the page. An upright region's is its box."""
    angle = region.angle if angle is None else angle
    x0, y0, x1, y1 = region.bbox
    if not angle:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    probe = copy.copy(region)
    probe.angle = angle
    local, turn = upright_region(probe)
    fx0, fy0, fx1, fy1 = local.bbox
    return [turn.back(x, y) for x, y in ((fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1))]
