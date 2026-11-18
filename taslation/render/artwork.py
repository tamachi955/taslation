"""Lettering set on the drawing: taken out by an inpainting model, the drawing under it made up.

Paint cannot do this: a bubble has paper to fill, lettering on hatching, tone or a face has none. A region whose ground,
in a ring round its box, is not one flat colour (`on_art`) goes here: `art_mask` finds its lettering, the dark pieces
ringed by white with their rings (`ring_comp`, on the negative too for light lettering), wherever the ring lies (past
the box too, `with_ring`) and a little more (`GROW`), and LaMa (`lama`) fills just that. Everything else stays with
`erase_region`, bubbles on their paper; so does a region whose box holds too little of such lettering to be sure. A
layout model's region that took the shape of a classical region is judged as that region was without the model, on its
lettering box (`as_judged`); only the hole the model fills takes in the model's text box too (`box_of`).

A model "bubble" that the classical detectors could not close is judged here too: with its plain box as the mask (tier
3) always, with a white area (tier 2) when its ground is not flat; one that has paper between its strokes after all
(`on_paper`: an open or a thin outline) goes back to the paper fill. So does lettering whose ground right round it is
one flat colour or a smooth shading (`plain_ground`: a black or white panel, a gradient), where the model only
blotches what a fill paints as it was: its hole, ring and all, is painted with that ground (`fill_ground`) first. So is
the hole of outlined lettering on a flat ground, which is no art (`FLAT_RINGS`): the paper fill took a thick white ring
for paper and left it.

A rectangle the reader drew, or a region they resized or moved, is judged as a detected region is (`drawn_on_art`): on
the drawing - a gradient, a tone or hatching the paper fill took for paper too - its lettering comes here, and where the
model does not fill it in only its strokes go (`erase.erase_strokes`), never the whole rectangle in one colour; in a
bubble, reaching out of one, or on a flat box it is wiped on its paper as before.

What the model filled is pasted as it came, the hole alone (`paste`): no tone matching against the ring round the hole
and no feathered edge, since neither helped on `tools/erase_eval.py`'s grounds (docs/OFFLINE_VERIFICATION.md, "The
erase on the art", 2026-11-15).

LaMa runs in torch, on the GPU when torch has one (about 0.6 s a screen) and on the CPU otherwise (about 4 s). Where
it runs at all is the setting `art_erase`, read by one rule (`runs_here`, and `available` for the weights too): "auto",
the default, only where torch has a CUDA GPU, so that a computer without one erases exactly as with "off" and never
loads the model; "lama" everywhere, on the CPU too; "off" nowhere. It is loaded on first use; `ArtEraser.release`
gives its memory back and the next erase loads it again. A failure on the GPU moves the work to the CPU for the rest
of the session (a fallback, not the rule's choice), one on the CPU leaves the regions to `erase_region`.

``erase_mode = "fill"`` only: "inpaint" and "classic" stay as they are, whole pages of them.
"""

from __future__ import annotations

import copy
import gc
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from ..config import LAMA_MODEL
from ..regions import TextRegion
from .erase import MANUAL_KINDS, erase_region, paper_colour, paper_surface, within_paper

LOG = logging.getLogger(__name__)

ART_ERASES = ("auto", "lama", "off")
ART_KINDS = ("text", "text-on-page", "text-dark", "text-on-dark")
FLAT_GROUND = 6.0  # grey levels: nine in ten pixels of a ring this close to its median are one flat colour
RING_OUT, RING_IN = 14, 2  # px: the ring round a region's box its ground is judged on
PIECE = 80  # px: a dark piece longer than this, or than 1.15 times the box's short side, is not a glyph ...
WIDE_GLYPH = 1.15  # ... (big lettering: a glyph as wide as its column)
DARK, RINGED = 150, 200  # grey levels of a stroke, and of the white ring round it
RING_SHARE = 0.55  # the share of a piece's edge that is white when it is ringed
LIGHT_REACH, LIGHT = 6, 190  # px round a stroke in which the pixels at least this light are its white ring ...
FRINGE = 215  # ... and the grey level under which the pixel right round it is its anti-aliasing
GROW = 2  # px the hole is grown past all that: one that ends on the ring's anti-aliasing has LaMa draw it back
MIN_MASK = 0.03  # of the box: less lettering than this is not worth a model
REACH = 8  # px (or a tenth of the box's short side) past the box the lettering is followed
EDGE = 4  # px along a model bubble's box edge where a piece is its outline ...
ALONG = 0.6  # ... when this share of it lies there (a glyph near the edge only touches it)
OUTLINE_LEVEL = 215  # grey level under which a pixel is ink, a thin grey outline's too (`on_paper`)
GROUND_BAND = 9  # px (a disc): the ground right round the hole, on which a flat or shaded ground is told ...
GROUND_FIT = 8.0  # ... when nine in ten of its pixels lie this close (RGB) to a smooth surface fitted to it
GROUND_FILL = True  # the hole on such a ground is painted with that surface before the paper fill takes the rest
FLAT_RINGS = True  # so is lettering's on a flat ground (not `on_art`): the paper fill took a thick white ring for paper
EDGE_INK = 0.15  # ... and the ink reaching in from its box's edge at most this share: a thin outline, not the art
PAPER_SHARE = 0.3  # of an unclosed model bubble's lettering box: the ground between its strokes, when it is paper
PAPER_LEVELS, PAPER_EVEN = 12, 0.75  # grey levels: the paper a reader's rectangle is cut back to is a bubble's when
# three in four of its pixels (its lettering and a fringe of 3 px left out) lie this close to its median; a gradient,
# a tone, the light of a drawing do not (`drawn_on_art`) ...
PAPER_SURE = 0.95  # ... and a rectangle whose own ground, white (`RINGED` or lighter), is this even lies on a bubble's
WINDOW = 512  # px: the part of the page the model sees (at least)
SMALLEST = 256  # px: a page narrower than this is left to the paper fill (the network pads by reflection)

Erase = Callable[..., tuple[int, int, int]]


def is_dash(st: np.ndarray, i: int, width: int, height: int) -> bool:
    """A long dash of the lettering: a straight stroke (2-16 px wide, up to 300 long) off the box's edges, in line with
    a glyph-sized piece at one of its ends. Lines of the drawing and bubble outlines touch the box's edge or stand
    alone. *st*: `connectedComponentsWithStats`'s stats of the box."""
    x, y, w, h, a = (int(v) for v in st[i])
    long, short = max(w, h), min(w, h)
    if not (2 <= short <= 16 and long >= 5 * short and long <= 300 and a >= 0.4 * w * h):
        return False
    if x < 2 or y < 2 or x + w > width - 2 or y + h > height - 2:
        return False
    down = h >= w
    cx, cy = x + w / 2, y + h / 2
    for j in range(1, len(st)):
        if j == i:
            continue
        ox, oy, ow, oh, _a = (int(v) for v in st[j])
        if max(ow, oh) > 60 or max(ow, oh) < 6:
            continue
        if down and abs(ox + ow / 2 - cx) <= 18 and min(abs(oy - (y + h)), abs(y - (oy + oh))) <= 40:
            return True
        if not down and abs(oy + oh / 2 - cy) <= 18 and min(abs(ox - (x + w)), abs(x - (ox + ow))) <= 40:
            return True
    return False


def ring_comp(gray: np.ndarray, short: int = 0) -> np.ndarray:
    """The lettering of the box *gray*: dark pieces of a glyph's size (`PIECE`, or `WIDE_GLYPH` times the box's short
    side, *short* when the crop is wider than the box; a long dash too) ringed by white, even on black art, and the ring
    goes with them."""
    return ringed(gray, short)[0]


def ringed(gray: np.ndarray, short: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """`ring_comp`'s mask, and its strokes alone (the dark pieces it took, without their rings)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats((gray < DARK).astype(np.uint8), connectivity=8)
    keep = np.zeros(gray.shape, np.uint8)
    limit = max(PIECE, WIDE_GLYPH * (short or min(gray.shape)))
    edge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 4 or (max(w, h) > limit and not is_dash(stats, i, gray.shape[1], gray.shape[0])):
            continue
        x0, y0 = max(0, x - 3), max(0, y - 3)
        piece = (labels[y0:y + h + 3, x0:x + w + 3] == i).astype(np.uint8)
        band = (cv2.dilate(piece, edge) > 0) & (piece == 0)
        if band.sum() and (gray[y0:y + h + 3, x0:x + w + 3][band] >= RINGED).mean() >= RING_SHARE:
            keep[y0:y + h + 3, x0:x + w + 3] |= piece
    return with_ring(gray, keep > 0), keep > 0


def with_ring(gray: np.ndarray, strokes: np.ndarray) -> np.ndarray:
    """*strokes* (bool, of *gray*) with what goes with them: the pixel right round them darker than `FRINGE` (their
    anti-aliasing) and the light pixels (`LIGHT`) within `LIGHT_REACH` of them (their white ring)."""
    s = strokes.astype(np.uint8)
    grown = cv2.dilate(s, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * LIGHT_REACH + 1,) * 2)) > 0
    fringe = cv2.dilate(s, np.ones((3, 3), np.uint8)) > 0
    return strokes | (fringe & (gray < FRINGE)) | (grown & (gray >= LIGHT))


def reach_of(box: tuple[int, int, int, int]) -> int:
    """How far past the lettering box *box* its lettering is followed (`REACH`, or a tenth of its short side)."""
    return max(REACH, int(0.1 * min(box[2] - box[0], box[3] - box[1])))


def around(image: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """The part of the page `art_mask` looks at for the lettering box *box*, and the most its hole takes: the box and
    `reach_of` past it, room for the white ring and growth (`LIGHT_REACH`, `GROW`) of the strokes in the box. (Room for
    the rings of the pieces followed to its edge as well took more of the drawing they are mostly part of: on the line
    art of `tools/erase_eval.py`'s grounds the MAE round the lettering rose by 1 to 7.)"""
    pad = reach_of(box)
    h, w = image.shape[:2]
    return max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad)


def box_of(image: np.ndarray, region: TextRegion) -> tuple[int, int, int, int]:
    """The region's lettering box, within the page; a model region's also takes in the model's own text box (a
    classical block it took its shape from may hold only part of its lettering)."""
    b = region.letter_box or region.text_box
    if region.from_model and region.letter_box is not None:
        t = region.text_box
        b = (min(b[0], t[0]), min(b[1], t[1]), max(b[2], t[2]), max(b[3], t[3]))
    h, w = image.shape[:2]
    return max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3])


def on_art(image: np.ndarray, region: TextRegion, flat: float = FLAT_GROUND) -> bool:
    """Whether *region* is lettering on the page whose ground, in a ring round its box, is not one flat colour; a
    bubble the classical detectors could not close, and a rectangle of the reader's (`drawn_on_art`), are judged as
    the module's docstring says."""
    if region.kind in ("bubble", "dark-bubble"):
        if region.tier == 3:
            return True
        if region.tier != 2:
            return False
    elif region.kind in MANUAL_KINDS:
        return drawn_on_art(image, region, flat)
    elif region.kind not in ART_KINDS:
        return False
    return _ring_not_flat(image, region, flat)


def as_judged(region: TextRegion) -> TextRegion:
    """*region* as its ground is judged (`on_art`, the lettering `plain_ground` is judged round): a layout model's
    region that took its shape from a classical region (tier 0, `adopted`) as that region was judged without the model,
    on its own lettering box (the classical region's, as far as it lies in it); any other as it is. The model's text box
    round lettering on white paper often reaches the bubble's outline, whose ring is never flat, and the lettering
    followed in it reaches the outline's band: such lettering went to the inpainting for the outline alone (on
    OpenMantra's 214 pages with both page models, 593 regions on paper, 68 with the layout model off, 69 since), where
    the paper fill takes it as before. Only the hole the inpainting fills takes in the model's text box as well
    (`box_of`)."""
    if region.from_model and region.adopted is not None and region.letter_box is not None:
        own = copy.copy(region)
        own.from_model = False
        return own
    return region


def _ring_not_flat(image: np.ndarray, region: TextRegion, flat: float) -> bool:
    """Whether the ground in a ring round *region*'s lettering box (`as_judged`) is not one flat colour (`on_art`)."""
    x0, y0, x1, y1 = box_of(image, as_judged(region))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return False
    h, w = image.shape[:2]
    ox0, oy0, ox1, oy1 = max(0, x0 - RING_OUT), max(0, y0 - RING_OUT), min(w, x1 + RING_OUT), min(h, y1 + RING_OUT)
    gray = cv2.cvtColor(image[oy0:oy1, ox0:ox1], cv2.COLOR_RGB2GRAY).astype(np.float32)
    ring = np.ones(gray.shape, bool)
    ring[max(0, y0 - RING_IN - oy0):y1 + RING_IN - oy0, max(0, x0 - RING_IN - ox0):x1 + RING_IN - ox0] = False
    ground = gray[ring]
    if ground.size < 16:
        return False
    return float(np.percentile(np.abs(ground - np.median(ground)), 90)) >= flat


def art_mask(image: np.ndarray, region: TextRegion) -> np.ndarray | None:
    """The lettering of *region* as a boolean mask of the page; None when its box holds too little of it. Its strokes
    are found in the box (`ringed`), and past the box (by `reach_of`) what continues a stroke it took: a glyph-sized
    dark piece the box's edge cut off. Each stroke takes its ring and anti-aliasing with it (`with_ring`) wherever they
    lie, past the box too: a box drawn round the strokes alone (a text block's) cuts the white ring of outlined
    lettering, and the ring left round the hole had LaMa draw the glyphs back as grey shapes. The hole is grown by
    `GROW` more, and a pixel for anti-aliasing. A model bubble's own box edge is its outline: a piece lying along it
    (`ALONG` of it within `EDGE` px) is left out, with the ring round it; None too when that leaves too little."""
    x0, y0, x1, y1 = box_of(image, region)
    gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    inner, strokes = ringed(gray)
    negative = None
    if region.dark:  # light lettering ringed by dark: the same test on the negative
        dark_inner, negative = ringed(255 - gray)
        inner = inner | dark_inner
    if inner.sum() < MIN_MASK * inner.size:
        return None
    ox0, oy0, ox1, oy1 = around(image, (x0, y0, x1, y1))
    near = cv2.cvtColor(image[oy0:oy1, ox0:ox1], cv2.COLOR_RGB2GRAY)
    mask = np.zeros(near.shape, bool)
    limit = max(PIECE, WIDE_GLYPH * min(x1 - x0, y1 - y0))
    for flip, found in ((False, strokes), (True, negative)):
        if found is None:
            continue
        level = 255 - near if flip else near
        taken = np.zeros(mask.shape, bool)
        taken[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0] = found
        ink = level < DARK
        n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
        go_on = np.zeros(n, bool)
        go_on[np.unique(labels[taken & ink])] = True
        go_on[0] = False
        go_on &= np.maximum(stats[:, 2], stats[:, 3]) <= limit
        mask |= with_ring(level, taken | go_on[labels])
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * GROW + 1,) * 2)
    mask = cv2.dilate(cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)), grow) > 0  # (within `around`)
    if region.from_model and region.kind in ("bubble", "dark-bubble"):
        dark = (near > 255 - DARK) if region.dark else (near < DARK)
        n, labels = cv2.connectedComponents(dark.astype(np.uint8), connectivity=8)  # the dark pieces round the box
        border = np.ones(mask.shape, bool)
        bx0, by0, bx1, by1 = region.x0 - ox0, region.y0 - oy0, region.x1 - ox0, region.y1 - oy0
        border[max(0, by0 + EDGE):max(0, by1 - EDGE), max(0, bx0 + EDGE):max(0, bx1 - EDGE)] = False
        on_border = np.bincount(labels[border & dark].ravel(), minlength=n)
        every = np.bincount(labels.ravel(), minlength=n)
        along = on_border >= ALONG * np.maximum(1, every)  # a piece lying mostly in the band is the outline's
        along[0] = False
        if along.any():  # it stays, and so does the ring round it
            outline = along[labels]
            mask &= ~(cv2.dilate(outline.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))) > 0)
        if mask.sum() < MIN_MASK * inner.size:
            return None
    full = np.zeros(image.shape[:2], bool)
    full[oy0:oy1, ox0:ox1] = mask
    return full


def plain_ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None = None,
                 within: np.ndarray | None = None) -> bool:
    """Whether the ground right round the lettering's *hole* (bool, the page; `GROUND_BAND`), within *box* when given,
    is one colour or a smooth shading of it: a black or white panel, a flat tone, a gradient. There the hole is painted
    with that ground (`fill_ground`) and a model, which makes up a texture, would only blotch it. The erase gives no
    box: the hole holds the white ring of outlined lettering, so the band round it is the ground past the ring. (Within
    the lettering box, a box drawn round the strokes alone, the ring was all the ground there was: lettering on a
    drawing passed for lettering on white paper, and was painted white.) *within* (bool, the page): the band is taken
    there alone (a reader's rectangle: `drawn_on_art`)."""
    found = _ground(image, hole, box, within)
    if found is None:
        return False
    crop, _part, band, surface = found
    off = np.sqrt(((crop[band].astype(np.float32) - surface[band]) ** 2).sum(axis=1))
    return float(np.percentile(off, 90)) < GROUND_FIT


def _ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None,
            within: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """The part of the page round *hole* (`GROUND_BAND`, within *box*), the hole and the ground band in it (bool, and
    in *within* when given), and the smooth surface fitted to the band (`paper_surface`); None when there is too
    little of it."""
    ys, xs = np.nonzero(hole)
    if not xs.size:
        return None
    h, w = hole.shape[:2]
    pad = GROUND_BAND
    x0, y0, x1, y1 = max(0, xs.min() - pad), max(0, ys.min() - pad), min(w, xs.max() + 1 + pad), min(h, ys.max() + 1 + pad)
    if box is not None:
        x0, y0, x1, y1 = max(x0, box[0]), max(y0, box[1]), min(x1, box[2]), min(y1, box[3])
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
    part = hole[y0:y1, x0:x1]
    band = (cv2.dilate(part.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (GROUND_BAND,) * 2)) > 0) & ~part
    if within is not None:
        band &= within[y0:y1, x0:x1]
    if int(band.sum()) < 16:
        return None
    crop = image[y0:y1, x0:x1, :3]
    return crop, part, band, paper_surface(crop, band)


def fill_ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None = None) -> bool:
    """Paint *hole* (bool, the page) in place with its plain ground as `plain_ground` judged it (within *box*): the
    smooth surface fitted to the band right round it, so a gradient stays a gradient and the white ring of outlined
    lettering goes with its strokes. Whether it was painted."""
    found = _ground(image, hole, box)
    if found is None:
        return False
    crop, part, _band, surface = found
    crop[part] = np.clip(np.round(surface[part]), 0, 255).astype(np.uint8)
    return True


def on_paper(image: np.ndarray, region: TextRegion) -> bool:
    """Whether a layout model's bubble that the classical detectors could not close (tier 2 or 3) has paper under its
    lettering after all: the ground of its lettering box, all ink (`OUTLINE_LEVEL`, grown a little) left out, is one
    flat colour or a smooth shading of it (`GROUND_FIT`, as `plain_ground`) and `PAPER_SHARE` of the box, and the ink
    that reaches in from the box's edge (its outline, the drawing beyond) is no more than `EDGE_INK` of it. Its open or
    thin outline was what the detectors missed; the paper fill paints its lettering alone (`Pipeline._paper_erase`)."""
    if not region.from_model or region.kind not in ("bubble", "dark-bubble") or region.tier < 2:
        return False
    x0, y0, x1, y1 = box_of(image, region)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return False
    crop = image[y0:y1, x0:x1, :3]
    gray = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_RGB2GRAY)
    ink = (gray > 255 - OUTLINE_LEVEL) if region.dark else (gray < OUTLINE_LEVEL)
    _n, labels = cv2.connectedComponents(ink.astype(np.uint8), connectivity=8)
    rim = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    if float(np.isin(labels, rim[rim > 0]).mean()) > EDGE_INK:
        return False  # the drawing reaches in from the box's edge: lettering on the art, its white the drawing's
    ground = ~(cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    if int(ground.sum()) < PAPER_SHARE * ground.size:
        return False
    surface = paper_surface(crop, ground)
    off = np.sqrt(((crop[ground].astype(np.float32) - surface[ground]) ** 2).sum(axis=1))
    return float(np.percentile(off, 90)) < GROUND_FIT


def drawn_on_art(image: np.ndarray, region: TextRegion, flat: float = FLAT_GROUND, dark_threshold: int = 140) -> bool:
    """Whether a rectangle the reader drew, or a region they resized or moved (`MANUAL_KINDS`), lies on the drawing,
    judged as a region the detectors found is: the ground in a ring round its box is not one flat colour (`on_art`),
    and the ground right round its lettering (`art_mask`; the rectangle's dark, or light, pixels when that finds too
    little) is no plain ground either (`plain_ground`: a bubble's paper, a flat or shaded box), taken within the
    rectangle, so that a bubble's outline or the drawing past it is not taken for its ground - unless the rectangle's
    own ground is white and as even as a bubble's (`PAPER_SURE`). One that the paper fill cuts back to the paper its
    lettering stands on (`within_paper`: it reaches out of a bubble, or across the light of a drawing) is on the art
    when that paper is not even (`PAPER_EVEN`): a gradient, a tone, hatching. Then its lettering goes as lettering on
    the art goes - LaMa fills it where it runs, else its strokes alone are filled in from round them
    (`erase.erase_strokes`, `Pipeline._paper_erase`) - and the rectangle is never wiped as drawn: a flat box of one
    colour over the drawing."""
    if region.kind not in MANUAL_KINDS or not _ring_not_flat(image, region, flat):
        return False
    crop = image[region.y0:region.y1, region.x0:region.x1]
    mask = region.mask
    if crop.shape[:2] != mask.shape:
        mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
    inside = mask > 0
    if region.kind == "manual":
        part = within_paper(crop, inside, dark_threshold)
        even = _evenness(crop, part, dark_threshold)
        if part is not inside:  # cut back to the paper it stands on: on the art only when that is no paper
            return even is None or even[0] < PAPER_EVEN  # (none of it clear of the ink: the light of a drawing)
        if even is not None and even[0] >= PAPER_SURE and even[1] >= RINGED:
            return False  # a bubble's white, its outline or the drawing past it in the ring round the lettering
    else:
        part = inside
    hole = art_mask(image, region)
    if hole is None:
        gray = cv2.cvtColor(np.ascontiguousarray(crop[..., :3]), cv2.COLOR_RGB2GRAY)
        ink = ((gray > 255 - DARK) if region.dark else (gray < DARK)) & inside
        if not ink.any():
            return True  # nothing to tell paper by: the erase of lettering on the art paints no more than strokes
        hole = np.zeros(image.shape[:2], bool)
        hole[region.y0:region.y1, region.x0:region.x1] = cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    within = np.zeros(image.shape[:2], bool)
    within[region.y0:region.y1, region.x0:region.x1] = part
    return not plain_ground(image, hole, within=within)


def _evenness(crop: np.ndarray, part: np.ndarray, dark_threshold: int) -> tuple[float, float] | None:
    """The share of *part*'s light ground (bool, of *crop*: the ink, darker than *dark_threshold*, and 3 px round it
    left out) within `PAPER_LEVELS` of its median, and that median; None when less than 16 px of it is clear of the
    ink."""
    gray = cv2.cvtColor(np.ascontiguousarray(crop[..., :3]), cv2.COLOR_RGB2GRAY).astype(np.int16)
    ground = part & ~(cv2.dilate((gray < dark_threshold).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0)
    if int(ground.sum()) < 16:
        return None
    level = gray[ground]
    median = float(np.median(level))
    return float((np.abs(level - median) <= PAPER_LEVELS).mean()), median


def paste(part: np.ndarray, filled: np.ndarray, hole: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """What of the model's *filled* goes onto *part* (the window it saw) for *hole*: the pixels changed (bool) and
    their values."""
    return hole, filled[hole]


def window(mask_shape: tuple[int, ...], x: int, y: int, h: int, w: int) -> tuple[int, int, int, int]:
    """The part of the page the model sees for a box at (*x*, *y*), *h* by *w*: `WINDOW` px, more for a larger box."""
    height, width = mask_shape[:2]
    side_h, side_w = min(max(WINDOW, h + 64), height), min(max(WINDOW, w + 64), width)
    y0 = int(np.clip(y + h // 2 - side_h // 2, 0, height - side_h))
    x0 = int(np.clip(x + w // 2 - side_w // 2, 0, width - side_w))
    return x0, y0, x0 + side_w, y0 + side_h


# ------------------------------------------------------------------ the model
_cuda: bool | None = None  # torch's answer to whether it has a CUDA GPU, once asked (`has_cuda`)


def has_cuda() -> bool:
    """Whether torch has a CUDA GPU on this computer, as the System page counts one (`devices.cuda_available`: only
    CUDA, torch imported if it is not yet, nothing loaded and no CUDA context made). Asked once, the first time an
    answer is needed (never when the config is read), and kept for the session."""
    global _cuda
    if _cuda is None:
        from ..devices import cuda_available

        _cuda = cuda_available()
    return _cuda


def runs_here(setting: str, cuda: bool | None = None) -> bool:
    """THE RULE for `art_erase`, which everything that asks whether the erase on the art runs goes by (`available`,
    `devices.stage_devices`, `health.page_models_missing`, the Settings dialog): "off" never; "lama" always, on the
    CPU too; "auto" (the default) only where torch has a CUDA GPU: *cuda* when the caller knows it, else `has_cuda`,
    asked only for "auto". The weights are `available`'s to check. A GPU that fails at run time moves the work to the
    CPU until the model is next let go (`ArtEraser._fill`, `ArtEraser.release`): a fallback, not this rule's choice."""
    if setting == "off":
        return False
    if setting == "auto":
        return has_cuda() if cuda is None else bool(cuda)
    return True


def installed(models_dir: Path) -> bool:
    """Whether LaMa's weights are in the models folder (the file is there; nothing is read or loaded for it)."""
    return not LAMA_MODEL.missing(Path(models_dir))


IDLE_MIB = 128  # what torch's cache may keep idle after a window filled on the GPU (`give_back_idle`)


def give_back_idle(limit_mib: int = IDLE_MIB) -> bool:
    """The GPU memory torch's caching allocator keeps idle given back when it is more than *limit_mib*, after a window
    was filled there: each window size leaves blocks of its own (a window 1188 px long, 588 MiB), and over a session
    they piled up to 2.4 GB (measured 2026-11-19), for on Windows the driver lets a process's GPU memory go on into the
    computer's own memory rather than run out, so that no out of memory ever asks them back. With it, a session held
    872 MiB between windows, and the placing rule's figure for LaMa holds (`ocr.place.LAMA_MIB`). It takes about 2 ms,
    after nearly every window (one takes 140 ms on the 6 GB card), and the next window 2-3 ms more to take its memory
    again. Whether it gave any back; never raises."""
    try:
        import torch

        if not torch.cuda.is_initialized():
            return False
        if torch.cuda.memory_reserved() - torch.cuda.memory_allocated() <= limit_mib * 1024 * 1024:
            return False
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 - the memory stays as it is
        return False
    return True


def available(models_dir: Path, setting: str = "auto", cuda: bool | None = None) -> bool:
    """Whether the erase can run: LaMa's weights are here (`installed`) and the setting runs it on this computer
    (`runs_here`; *cuda* as there). The weights are looked at first, so that a computer without them never asks
    torch; nothing is loaded for it either way."""
    return setting != "off" and installed(models_dir) and runs_here(setting, cuda)


class ArtEraser:
    """`erase` for regions on the art, with LaMa in *models_dir*, loaded on first use."""

    def __init__(self, models_dir: Path, setting: str = "auto", fallback: Erase = erase_region):
        self.models_dir = Path(models_dir)
        self.setting = setting
        self.fallback = fallback
        self.failed = False  # LaMa could not run: `erase_region` does it all from then on
        self.counts = {"art": 0, "plain": 0, "weak": 0, "ground": 0}  # what the regions went to
        self._model: Any = None
        self._checked = False
        self._release_asked = False  # a release that came while the model was at work: done once it is free
        self._lock = threading.Lock()
        # called (it may wait) before the model runs on the GPU, once per region: the batch pauses the GPU while the
        # reader turns pages (`Pipeline.gpu_gate`); never on the CPU
        self.before_gpu: Callable[[], None] | None = None

    def ready(self) -> bool:
        """Whether the erase can run as far as can be known without loading it: the weights file is LaMa's (the names
        and shapes of its tensors, read from its header), and nothing failed. What lets the layout model run."""
        if not self.failed and not self._checked:
            from .lama import check

            try:
                check(self.models_dir / LAMA_MODEL.dirname / LAMA_MODEL.installed[0])
                self._checked = True
            except Exception as e:  # noqa: BLE001 - a broken or foreign file: the paper fill, and no layout model
                LOG.warning("LaMa's weights cannot be used (%s): no inpainting", type(e).__name__)
                self.failed = True
        return not self.failed

    def uses_gpu(self) -> bool:
        """Whether the model runs on the GPU: where it is loaded, else where it would load."""
        model = self._model
        return (model.device if model is not None else self._device()) != "cpu"

    @staticmethod
    def _device() -> str:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load(self, device: str) -> None:
        from .lama import LamaInpainter

        self._model = LamaInpainter(self.models_dir / LAMA_MODEL.dirname / LAMA_MODEL.installed[0], device)

    def _try(self, device: str, part: np.ndarray, hole: np.ndarray) -> tuple[np.ndarray | None, str]:
        """LaMa on *device* (loaded there first when it is not): the filled part, or None and why not. The exception is
        let go here, before anything is freed: its traceback holds the tensors of the failed step."""
        try:
            if self._model is None:
                self._load(device)
            return self._model.run(part, hole), ""
        except Exception as e:  # noqa: BLE001 - out of memory, a broken file: not worth a page
            return None, type(e).__name__

    def _fill(self, part: np.ndarray, hole: np.ndarray) -> np.ndarray | None:
        """*part* with *hole* filled; None when LaMa cannot do it. A failure on the GPU (its memory is shared with
        Ollama), loading or running, moves to the CPU until the model is next let go (`release`: before Ollama loads
        its model, Tools > Release the model now), when the next erase loads it on the GPU again; a failure on the CPU
        leaves the paper fill for the session. After a window on the GPU the idle cache is given back
        (`give_back_idle`)."""
        gate = self.before_gpu
        if gate is not None and not self.failed and self.uses_gpu():
            gate()
        with self._lock:
            if self.failed:
                return None
            device = self._model.device if self._model is not None else self._device()
            filled, why = self._try(device, part, hole)
            if filled is not None and device != "cpu":
                give_back_idle()
            if filled is None and device != "cpu":
                LOG.info("inpainting failed on the GPU (%s): on the CPU until the model is let go", why)
                self._drop(device)
                filled, why = self._try("cpu", part, hole)
            if filled is None:
                LOG.warning("inpainting failed (%s): the paper fill from now on", why)
                self._drop("cpu")
                self.failed = True
            if self._release_asked:
                self._release_asked = False
                self._drop(device)
            return filled

    def warm(self) -> bool:
        """Loaded, and run once on a small blank part, ahead of the first page (`Pipeline.warm_page_models`), after the
        gate like any erase. A release asked meanwhile is done once it is over (`release`). Whether it worked."""
        if self.failed or not self.ready():
            return False
        part = np.full((64, 64, 3), 255, np.uint8)
        hole = np.zeros((64, 64), bool)
        hole[16:48, 16:48] = True
        return self._fill(part, hole) is not None

    def erase(self, image: np.ndarray, region: TextRegion, mode: str = "fill", white_threshold: int = 225,
              dark_threshold: int = 140, dark: bool = False) -> tuple[int, int, int]:
        """`erase_region`, but for lettering on the art: there the model fills the lettering in place, and the region's
        paper colour is what its lettering is drawn against. What the model filled is kept on the region (memory only)
        and used again while the part of the page it saw is the same (a page lettered again, a preview)."""
        app = lambda: self.fallback(image, region, mode, white_threshold, dark_threshold, dark)  # noqa: E731
        judged = as_judged(region)
        if self.failed or not on_art(image, region):
            self.counts["plain"] += 1
            if not self.failed and FLAT_RINGS and region.kind in ART_KINDS:
                full = art_mask(image, judged)  # outlined lettering on a flat ground: its ring painted that ground
                if full is not None and plain_ground(image, full):
                    fill_ground(image, full)
            return app()
        if on_paper(image, region):
            self.counts["ground"] += 1
            return app()
        full = art_mask(image, judged)
        if full is None:
            self.counts["weak"] += 1
            return app()
        if plain_ground(image, full):
            self.counts["ground"] += 1
            if GROUND_FILL:
                fill_ground(image, full)  # (strokes, ring and all; the paper fill takes what is left)
            return app()
        if judged is not region:  # the hole takes in the model's text box too
            wider = art_mask(image, region)
            if wider is not None:
                full = full | wider
        x0, y0, x1, y1 = box_of(image, region)
        wx0, wy0, wx1, wy1 = window(image.shape, x0, y0, y1 - y0, x1 - x0)
        part, hole = image[wy0:wy1, wx0:wx1], full[wy0:wy1, wx0:wx1]
        key = hashlib.sha1(np.ascontiguousarray(part).tobytes() + np.packbits(hole).tobytes()).digest()
        kept = region.inpainted
        if kept is not None and kept[0] == key:
            pixels, where = kept[1], kept[2]
        else:
            filled = self._fill(part, hole) if min(part.shape[:2]) >= SMALLEST else None
            if filled is None:
                self.counts["plain"] += 1
                return app()
            where, pixels = paste(part, filled, hole)
            region.inpainted = (key, pixels, where)
        self.counts["art"] += 1
        part[where] = pixels
        crop = image[region.y0:region.y1, region.x0:region.x1]
        mask = region.mask
        if crop.shape[:2] != mask.shape:
            mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
        return paper_colour(crop, mask > 0, dark)

    def _drop(self, device: str) -> None:
        self._model = None
        gc.collect()
        if device != "cpu":
            import torch

            torch.cuda.empty_cache()

    def release(self) -> None:
        """Give the model's memory back; the next erase loads it again. Never waits: while the model is at work the
        release is done as soon as it is free."""
        if not self._lock.acquire(blocking=False):
            self._release_asked = True
            return
        try:
            if self._model is not None:
                self._drop(self._model.device)
        finally:
            self._lock.release()


__all__ = ["ART_ERASES", "ArtEraser", "around", "art_mask", "available", "drawn_on_art", "fill_ground", "has_cuda",
           "installed", "is_dash", "on_art", "on_paper", "paste", "plain_ground", "reach_of", "ring_comp", "runs_here",
           "window", "with_ring"]
