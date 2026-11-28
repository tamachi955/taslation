"""Lettering set on the drawing: taken out by an inpainting model, the drawing under it made up.

Paint cannot do this: a bubble has paper to fill, lettering on hatching, tone or a face has none. A region whose ground,
in a ring round its box, is not one flat colour (`on_art`) goes here: `art_mask` finds its lettering, the dark pieces
ringed by white with their rings (`ring_comp`, on the negative too for light lettering), wherever the ring lies (past
the box too, `with_ring`) and a little more (`GROW`), and LaMa (`lama`) fills just that. Everything else stays with
`erase_region`, bubbles on their paper; so does a region whose box holds too little of such lettering to be sure. A
layout model's region that took the shape of a classical region is judged as that region was without the model, on its
lettering box (`as_judged`); only the hole the model fills takes in the model's text box too (`box_of`). The measures
in pixels are taken at the scale of the region's page (`pagescale`: a page shown smaller than the sample set's has
its ring, reach and bands shrunk with it).

A model "bubble" that the classical detectors could not close is judged here too: with its plain box as the mask (tier
3; or the paper closed round its lettering, the room it is set in, `closed_room`) unless it lies on paper closed all
round, with a white area (tier 2) when its ground is not flat; one that has paper between its strokes after all
(`on_paper`: an open or a thin outline) goes back to the paper fill. So does lettering on paper closed all round
(`closed_interior`: a bubble, whatever found it, a white area the layout model called text on the page), judged
on that paper alone, never on a ring that crosses the bubble's outline: round a tall narrow bubble's column the ring
always reached the outline, and the inpainting left grey ghosts of the glyphs on its paper. So does lettering whose
ground right round it is one flat colour or a smooth shading (`plain_ground`: a black or white panel, a gradient),
where the model only blotches what a fill paints as it was: its hole, ring and all, is painted with that ground
(`fill_ground`) first. So is the hole of outlined lettering on a flat ground, which is no art (`FLAT_RINGS`): the paper
fill took a thick white ring for paper and left it.

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
loads the model; "lama" everywhere, on the CPU too; "off" nowhere. On the GPU unless the judgement at the start sent
it to the processor (`taslation.ocr.place`). It is loaded at the start with the other models (`ArtEraser.warm`);
`ArtEraser.release` gives its memory back and the next erase loads it again. A failure on the GPU moves the work to
the CPU for the rest of the session (a fallback, not the rule's choice), one on the CPU leaves the regions to
`erase_region`.

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

from .. import analysis
from ..config import LAMA_MODEL
from ..detect.bubbles import fill_holes, sides_of
from ..regions import TextRegion
from . import pagescale
from .erase import MANUAL_KINDS, erase_region, line_pixels, paper_colour, paper_surface, within_paper

LOG = logging.getLogger(__name__)

ART_ERASES = ("auto", "lama", "off")
ART_KINDS = ("text", "text-on-page", "text-dark", "text-on-dark")
FLAT_GROUND = 6.0  # grey levels: nine in ten pixels of a ring this close to its median are one flat colour
RING_OUT, RING_IN = 14, 2  # px: the ring round a region's box its ground is judged on
COLOUR_SPREAD = 24  # a pixel with a channel this far from another is colour (as the analysis log's facts) ...
COLOUR_SHARE = 0.35  # ... and a ring with this share of such pixels lies on a picture in colour (`on_colour_picture`)
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
CLOSED_REACH = 3.0  # of the lettering box's own size, each way: where the paper closed round it is looked for (a
#                     bubble and its tail; at once the box's size, a tail reaching past it left most bubbles open) ...
CLOSED_WIDE = 10.0  # ... and, where the paper runs out of that, this (two bubbles joined into one) ...
CLOSED_SHARE = 0.9  # ... which holds this share of the light pixels in the box ...
CLOSED_PAPER = 0.03  # ... and of the box's area at least this much paper clear of the ink (`closed_interior`; the
#                      white rings of outlined lettering closed on the made-up layouts' tones and gradients had none)
PAPER_SURE = 0.95  # ... and a rectangle whose own ground, white (`RINGED` or lighter), is this even lies on a bubble's
THROUGH_HOLE = 0.15  # of a glyph past the reading's characters: the hole of a plain box's lettering (as
#                      `pipeline.CHAR_GROW`); the ink joined to it (`THROUGH_LEVEL`) that runs on past ...
THROUGH_GROW = 0.45  # ... this much of a glyph, inside the paper closed round it less a band of ...
THROUGH_CORE = 0.3  # ... this much of a glyph along its edge (the outline's, and where it touches a glyph) ...
THROUGH_SHARE = 0.015  # ... this share of the hole at the least, is the drawing seen through the bubble (`see_through`)
THROUGH_LEVEL = 170  # grey level under which that ink is followed: the dark threshold (140) and a thin line's
#                      anti-aliasing (`erase.LINK_LEVELS`)
ROOM_HOLD = 0.8  # of a model bubble's text box at the least: the paper closed round it, its holes filled, that is
#                  its room (`closed_room`; less holds part of its lettering: the paper between the lines of a
#                  bubble drawn see-through, where the translation came out tiny) ...
ROOM_IN = 7  # ... drawn in by an ellipse this wide (px at the page's scale), as a white area's (tier 2)
OWN_PAPER = 0.1  # of the paper in that text box: less, on a piece lying mostly outside the box, is a neighbour's paper
ROOM_CLOSE = 0.2  # of a glyph: the room closed by a disc of this radius first (strokes of glyphs touching the outline)
TONE_FILL = True  # a hole on a ground that repeats itself (a screentone, a hatching) is painted from it (`fill_tone`)
TONE_BAND = 24  # px of ground round the hole its repeats are measured on (`tone_shifts`) ...
TONE_REPEAT, TONE_DIP = 0.8, 0.3  # ... where it repeats (normalised autocorrelation), after falling under this
TONE_LEAST, TONE_PITCH = 3, 40  # px: the nearest repeat lies this far at the least and at the most
TONE_CONTRAST = 6.0  # grey levels (RMS) of the ground at the least: an even ground has no pattern
TONE_GROUND, TONE_OVERLAP = 400, 300  # pixels of ground, and of it overlapping itself at a shift, at the least
TONE_OVERLAP_SHARE = 0.2  # ... and that share of the ground (a few pixels overlapping make a peak of noise)
TONE_SHIFTS = 600  # repeats the hole is painted from, nearest first
TONE_PEAKS = 200  # repeats looked at, nearest first, for one past a dip
TONE_NEAR = 12  # the nearest repeats, painted with again and again from the hole's edge inwards
TONE_GROW = 2  # px the hole is taken wider by (anti-aliasing)
TONE_MOST_PX = 900_000  # px of the window its repeats are measured on at the most (four FFTs of four times it)
TONE_ROUNDS = 400  # rounds of painting from the hole's edge inwards at the most (a hole left unpainted: LaMa's)
WINDOW = 512  # px: the part of the page the model sees (at least)
# The pixels the model is run on at the most, on the GPU and on the processor: a larger part is scaled down to them
# for the run and its fill scaled back up into the hole alone (`ArtEraser._fill`). Measured 2026-11-28 (GTX 1660
# Ti, a hole of a quarter of the part): 768 x 768 0.29 s and 576 MiB at the peak on the GPU (LAMA_MIB holds it),
# 1400 x 1400 0.96 s and 1456 MiB; on the processor 512 x 512 1.1 s, 768 x 768 3.2 s, 1400 x 1400 10.5 s.
LAMA_PART_PX = 768 * 768
LAMA_PART_CPU_PX = 512 * 640
TELEA_RADIUS = 5  # px: OpenCV's inpainting of a hole LaMa is refused for (`budget.lama_refused`)
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


def ring_comp(gray: np.ndarray, short: int = 0, scale: float = 1.0) -> np.ndarray:
    """The lettering of the box *gray*: dark pieces of a glyph's size (`PIECE` at the page's *scale*, or `WIDE_GLYPH`
    times the box's short side, *short* when the crop is wider than the box; a long dash too) ringed by white, even on
    black art, and the ring goes with them."""
    return ringed(gray, short, scale)[0]


def ringed(gray: np.ndarray, short: int = 0, scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """`ring_comp`'s mask, and its strokes alone (the dark pieces it took, without their rings)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats((gray < DARK).astype(np.uint8), connectivity=8)
    keep = np.zeros(gray.shape, np.uint8)
    limit = max(PIECE * scale, WIDE_GLYPH * (short or min(gray.shape)))
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
    return with_ring(gray, keep > 0, scale), keep > 0


def with_ring(gray: np.ndarray, strokes: np.ndarray, scale: float = 1.0) -> np.ndarray:
    """*strokes* (bool, of *gray*) with what goes with them: the pixel right round them darker than `FRINGE` (their
    anti-aliasing) and the light pixels (`LIGHT`) within `LIGHT_REACH` of them at the page's *scale* (their white
    ring)."""
    s = strokes.astype(np.uint8)
    grown = cv2.dilate(s, pagescale.disc(2 * LIGHT_REACH + 1, scale)) > 0
    fringe = cv2.dilate(s, np.ones((3, 3), np.uint8)) > 0
    return strokes | (fringe & (gray < FRINGE)) | (grown & (gray >= LIGHT))


def reach_of(box: tuple[int, int, int, int], scale: float = 1.0) -> int:
    """How far past the lettering box *box* its lettering is followed (`REACH` at the page's *scale*, or a tenth of its
    short side)."""
    return max(pagescale.px(REACH, scale), int(0.1 * min(box[2] - box[0], box[3] - box[1])))


def around(image: np.ndarray, box: tuple[int, int, int, int], scale: float = 1.0) -> tuple[int, int, int, int]:
    """The part of the page `art_mask` looks at for the lettering box *box*, and the most its hole takes: the box and
    `reach_of` past it, room for the white ring and growth (`LIGHT_REACH`, `GROW`) of the strokes in the box. (Room for
    the rings of the pieces followed to its edge as well took more of the drawing they are mostly part of: on the line
    art of `tools/erase_eval.py`'s grounds the MAE round the lettering rose by 1 to 7.)"""
    pad = reach_of(box, scale)
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


@analysis.timed("on_art")
def on_art(image: np.ndarray, region: TextRegion, flat: float = FLAT_GROUND) -> bool:
    """Whether *region* is lettering on the page whose ground, in a ring round its box, is not one flat colour; a
    bubble the classical detectors could not close, and a rectangle of the reader's (`drawn_on_art`), are judged as
    the module's docstring says. Lettering on paper closed all round (`closed_interior`) is judged within that paper
    (`_ring_not_flat`), and a model bubble with no shape of its own is on the art off such paper, or where the drawing
    shows through it (`see_through`)."""
    if region.kind in ("bubble", "dark-bubble"):
        if region.tier == 3:
            closed = closed_interior(image, box_of(image, region), region.dark, pagescale.of(region), region.bounds)
            return closed is None or see_through(image, region, closed)
        if region.tier != 2:
            return False
    elif region.kind in MANUAL_KINDS:
        return drawn_on_art(image, region, flat)
    elif region.kind not in ART_KINDS:
        return False
    return _ring_not_flat(image, region, flat)


def on_colour_picture(image: np.ndarray, region: TextRegion) -> bool:
    """Whether the ring round *region*'s lettering box (`RING_OUT` px past it at the page's scale, `RING_IN` into it)
    is a picture in colour: `COLOUR_SHARE` of its pixels or more have a channel `COLOUR_SPREAD` from another, and the
    ring is not one flat colour (`FLAT_GROUND`: a coloured bubble's paper is). `Pipeline._big_unsure` asks it."""
    x0, y0, x1, y1 = box_of(image, region)
    h, w = image.shape[:2]
    out = pagescale.px(RING_OUT, pagescale.of(region))
    ox0, oy0, ox1, oy1 = max(0, x0 - out), max(0, y0 - out), min(w, x1 + out), min(h, y1 + out)
    if ox1 - ox0 < 4 or oy1 - oy0 < 4 or image.ndim < 3:
        return False
    ring = np.ones((oy1 - oy0, ox1 - ox0), bool)
    iy0, iy1 = max(0, y0 + RING_IN - oy0), max(0, y1 - RING_IN - oy0)
    ring[iy0:iy1, max(0, x0 + RING_IN - ox0):max(0, x1 - RING_IN - ox0)] = False
    px = image[oy0:oy1, ox0:ox1, :3][ring].astype(np.int16)
    if px.shape[0] < 16:
        return False
    if float(((px.max(axis=1) - px.min(axis=1)) >= COLOUR_SPREAD).mean()) < COLOUR_SHARE:
        return False
    grey = px.mean(axis=1)
    return float((np.abs(grey - np.median(grey)) <= FLAT_GROUND).mean()) < 0.9


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
    """Whether the ground in a ring round *region*'s lettering box (`as_judged`) is not one flat colour (`on_art`).
    Lettering on paper closed all round (`closed_interior`: a bubble, whatever found it or missed it) is judged on the
    ring's part inside that paper alone: round a box that nearly fills its bubble (a tall narrow one) the ring reaches
    the outline and the ground beyond, which are no ground of the lettering's, and the inpainting it was sent to left
    grey ghosts of the glyphs on the bubble's paper."""
    x0, y0, x1, y1 = box_of(image, as_judged(region))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return False
    h, w = image.shape[:2]
    scale = pagescale.of(region)
    out, inn = pagescale.px(RING_OUT, scale), pagescale.px(RING_IN, scale)
    ax0, ay0, ax1, ay1 = region.bounds or (0, 0, w, h)  # (the ring inside the capture area, as its paper is)
    ox0, oy0, ox1, oy1 = max(ax0, x0 - out), max(ay0, y0 - out), min(ax1, x1 + out), min(ay1, y1 + out)
    if ox1 - ox0 < 4 or oy1 - oy0 < 4:
        return False
    gray = cv2.cvtColor(image[oy0:oy1, ox0:ox1], cv2.COLOR_RGB2GRAY).astype(np.float32)
    ring = np.ones(gray.shape, bool)
    ring[max(0, y0 - inn - oy0):y1 + inn - oy0, max(0, x0 - inn - ox0):x1 + inn - ox0] = False
    closed = closed_interior(image, (x0, y0, x1, y1), region.dark, scale, region.bounds)
    if closed is not None:
        (wx0, wy0, wx1, wy1), inside, paper = closed
        # (its paper clear of the ink: the rim of a bubble with no outline, white on black, shades off into the black
        # within it, and the ring of a small one reached it)
        ring &= paper[oy0 - wy0:oy1 - wy0, ox0 - wx0:ox1 - wx0]
        if int(ring.sum()) < 16:  # lettering that fills its paper: judged on the paper clear of it
            ground = cv2.cvtColor(image[wy0:wy1, wx0:wx1], cv2.COLOR_RGB2GRAY).astype(np.float32)[paper]
            return float(np.percentile(np.abs(ground - np.median(ground)), 90)) >= flat
    ground = gray[ring]
    if ground.size < 16:
        return False
    return float(np.percentile(np.abs(ground - np.median(ground)), 90)) >= flat


@analysis.timed("closed_interior")
def closed_interior(image: np.ndarray, box: tuple[int, int, int, int], dark: bool = False, scale: float = 1.0,
                    bounds: tuple[int, int, int, int] | None = None
                    ) -> tuple[tuple[int, int, int, int], np.ndarray, np.ndarray] | None:
    """The light paper closed all round that the lettering box *box* lies on (a bubble's interior, whatever tier of
    the detectors found it or none did), as (window, bool mask of the window, the part of it clear of the ink), or
    None. Looked at in the box grown by
    its own size each way (`CLOSED_REACH`, at least `RING_OUT`): the pixels at least `OUTLINE_LEVEL` light (dark ones
    for light lettering on black) joined to those in the box without crossing ink (four-connected), where none of them
    reaches the window's edge; they must hold `CLOSED_SHARE` of the light pixels in the box (lettering that runs out
    of its bubble lies on what is beyond too), and `CLOSED_PAPER` of the box must be paper further than `LIGHT_REACH`
    from any ink - not the white rings of outlined lettering set on the drawing, which close on it too. Where the
    paper the box lies on runs out of that window, it is looked for again in the box grown by `CLOSED_WIDE` times its
    size: the paper of two bubbles joined into one, whose lettering lies in the smaller (the closed paper was not found
    round it, the inpainting took it, and its hole the line where the bubbles join). Pixels at the page's *scale*
    (`pagescale`). *bounds*: the capture area where the frame goes on beyond it (`TextRegion.bounds`): the window stays
    inside it, and paper that reaches its edge there is closed by it, as by an outline."""
    found, open_ = _closed_at(image, box, dark, scale, CLOSED_REACH, bounds)
    if found is None and open_:
        with analysis.timing("closed_interior.wide"):
            found, _open = _closed_at(image, box, dark, scale, CLOSED_WIDE, bounds)
        if found is not None:  # (the wide look closed what the first left open: the analysis log's count)
            analysis.acted_box("closed_interior.wide", box)
    return found


@analysis.timed("closed_room")
def closed_room(image: np.ndarray, region: TextRegion, scale: float = 1.0) -> np.ndarray | None:
    """The room of a model bubble with no shape of its own (tier 3, whose mask is its plain box), as a mask of its
    box: the paper closed round its lettering (`closed_interior`), its holes (the lettering) filled, within the box,
    drawn in by `ROOM_IN` - where its translation is set, as in a white area's (tier 2), not over the outline and past
    it where the box's corners reach. None where there is no such paper, or it holds less than `ROOM_HOLD` of the
    text box. Pixels at the page's *scale* (`pagescale`)."""
    closed = closed_interior(image, box_of(image, region), region.dark, scale, region.bounds)
    if closed is None:
        return None
    (wx0, wy0, wx1, wy1), inside, _far = closed
    x0, y0, x1, y1 = max(region.x0, wx0), max(region.y0, wy0), min(region.x1, wx1), min(region.y1, wy1)
    if x1 <= x0 or y1 <= y0:
        return None
    inside = _own_paper(inside, region, (wx0, wy0))
    room = np.zeros((region.height, region.width), np.uint8)
    sides = sides_of((wx0, wy0, wx1, wy1), region.bounds, (image.shape[1], image.shape[0]))
    filled = fill_holes(inside.astype(np.uint8) * 255, sides)
    room[y0 - region.y0:y1 - region.y0, x0 - region.x0:x1 - region.x0] = filled[y0 - wy0:y1 - wy0, x0 - wx0:x1 - wx0]
    # (the text box as far as the paper reaches: a model's box round a column by the outline took in the outline)
    ys, xs = np.nonzero(filled)
    if not xs.size:
        return None
    tx0, ty0, tx1, ty1 = region.text_box
    tx0, ty0 = max(tx0, wx0 + int(xs.min())), max(ty0, wy0 + int(ys.min()))
    tx1, ty1 = min(tx1, wx0 + int(xs.max()) + 1), min(ty1, wy0 + int(ys.max()) + 1)
    held = room[max(0, ty0 - region.y0):max(0, ty1 - region.y0), max(0, tx0 - region.x0):max(0, tx1 - region.x0)]
    if not held.size or cv2.countNonZero(held) < ROOM_HOLD * held.size:
        return None
    # (closed over the strokes of glyphs that touch the outline: no bay of the lettering's own drawn in further; the
    # box's edge carried on beyond it, so that the paper is not grown to an edge it came near)
    glyph = float(region.glyph or 20.0 * scale)
    reach = max(1, int(ROOM_CLOSE * glyph))
    room = cv2.morphologyEx(cv2.copyMakeBorder(room, reach, reach, reach, reach, cv2.BORDER_REPLICATE),
                            cv2.MORPH_CLOSE, pagescale.disc(2 * reach + 1, 1.0))[reach:-reach, reach:-reach]
    room = cv2.erode(room, pagescale.disc(ROOM_IN, scale))
    return room if cv2.countNonZero(room) else None


def _own_paper(inside: np.ndarray, region: TextRegion, corner: tuple[int, int]) -> np.ndarray:
    """*inside* (the paper `closed_interior` found round *region*'s lettering, a window whose corner lies at *corner* on
    the page) but for a neighbour's: a piece of it that lies mostly outside *region*'s box and holds under
    `OWN_PAPER` of the paper in its text box - a bubble joined to it, the outline between them, that the model's text
    box reached into (its room ran over that outline)."""
    n, labels = cv2.connectedComponents(inside.astype(np.uint8), connectivity=4)
    if n <= 2:
        return inside
    x0, y0 = corner
    h, w = inside.shape
    tx0, ty0, tx1, ty1 = region.text_box
    tb = labels[max(0, min(h, ty0 - y0)):max(0, min(h, ty1 - y0)), max(0, min(w, tx0 - x0)):max(0, min(w, tx1 - x0))]
    bx = labels[max(0, min(h, region.y0 - y0)):max(0, min(h, region.y1 - y0)),
                max(0, min(w, region.x0 - x0)):max(0, min(w, region.x1 - x0))]
    in_tb = np.bincount(tb.ravel(), minlength=n)
    in_box = np.bincount(bx.ravel(), minlength=n)
    total = np.bincount(labels.ravel(), minlength=n)
    paper = int(in_tb[1:].sum())
    gone = (2 * in_box < total) & (in_tb < OWN_PAPER * paper)
    gone[0] = False
    if not gone.any() or gone[1:].all():
        return inside
    return inside & ~gone[labels]


def _closed_at(image: np.ndarray, box: tuple[int, int, int, int], dark: bool, scale: float, reach: float,
               bounds: tuple[int, int, int, int] | None = None
               ) -> tuple[tuple[tuple[int, int, int, int], np.ndarray, np.ndarray] | None, bool]:
    """`closed_interior` in the box grown by *reach* times its size (within *bounds*), and whether the paper the box
    lies on ran out of that window where it holds less than the whole page (it may close in a wider one)."""
    h, w = image.shape[:2]
    ax0, ay0, ax1, ay1 = bounds if bounds is not None else (0, 0, w, h)
    x0, y0, x1, y1 = max(box[0], ax0), max(box[1], ay0), min(box[2], ax1), min(box[3], ay1)
    bw, bh = x1 - x0, y1 - y0
    if bw < 4 or bh < 4:
        return None, False
    least = pagescale.px(RING_OUT, scale)
    gx, gy = max(least, int(reach * bw)), max(least, int(reach * bh))
    wx0, wy0, wx1, wy1 = max(ax0, x0 - gx), max(ay0, y0 - gy), min(ax1, x1 + gx), min(ay1, y1 + gy)
    gray = cv2.cvtColor(np.ascontiguousarray(image[wy0:wy1, wx0:wx1, :3]), cv2.COLOR_RGB2GRAY)
    light = (gray <= 255 - OUTLINE_LEVEL) if dark else (gray >= OUTLINE_LEVEL)
    n, labels = cv2.connectedComponents(light.astype(np.uint8), connectivity=4)
    inner = labels[y0 - wy0:y1 - wy0, x0 - wx0:x1 - wx0]
    seeds = np.unique(inner[inner > 0])
    if not seeds.size:
        return None, False
    shut = sides_of((wx0, wy0, wx1, wy1), bounds, (w, h))  # (the window's sides on the area's edge: closed)
    lines = [line for line, off in zip((labels[0], labels[-1], labels[:, 0], labels[:, -1]), shut) if not off]
    edge = np.unique(np.concatenate(lines)) if lines else np.zeros(0, labels.dtype)
    closed = np.zeros(n, bool)
    closed[seeds] = True
    closed[edge] = False
    held = closed[inner]
    if int(held.sum()) < CLOSED_SHARE * int((inner > 0).sum()):
        whole = (wx0, wy0, wx1, wy1) == (ax0, ay0, ax1, ay1)
        return None, not whole and bool(np.isin(seeds, edge).any())
    inside = closed[labels]
    ink = (~light).astype(np.uint8)
    far = inside & (cv2.dilate(ink, pagescale.disc(2 * LIGHT_REACH + 1, scale)) == 0)
    if int(far.sum()) < CLOSED_PAPER * bw * bh:
        return None, False
    return ((wx0, wy0, wx1, wy1), inside, far), False


def _char_hole(region: TextRegion, shape: tuple[int, ...], x0: int, y0: int, grow: int) -> np.ndarray:
    """The reading's characters of *region* (`char_boxes`), each grown by *grow* px, as a bool mask of *shape* whose
    corner lies at (*x0*, *y0*) on the page."""
    hole = np.zeros(shape[:2], bool)
    for cx0, cy0, cx1, cy1 in region.char_boxes:
        hole[max(0, cy0 - grow - y0):max(0, cy1 + grow - y0), max(0, cx0 - grow - x0):max(0, cx1 + grow - x0)] = True
    return hole


def _own_seeds(region: TextRegion, labels: np.ndarray, reached: np.ndarray, corner: tuple[int, int]) -> np.ndarray:
    """The light pieces (*labels*, of a window whose corner lies at *corner* on the page) the grown hole of *region*'s
    characters reaches (*reached*), but for a neighbour's paper: one it reaches only past the characters' own boxes
    that lies mostly outside *region*'s box - the paper of a bubble joined to it, whose outline its column touches
    (the grown hole crossed that outline, and the outline and the neighbour's lettering were taken for the drawing
    seen through the bubble)."""
    seeds = np.unique(labels[reached])
    seeds = seeds[seeds > 0]
    if seeds.size < 2:
        return seeds
    x0, y0 = corner
    bare = _char_hole(region, labels.shape, x0, y0, 0)
    box = np.zeros(labels.shape, bool)
    box[max(0, region.y0 - y0):max(0, region.y1 - y0), max(0, region.x0 - x0):max(0, region.x1 - x0)] = True
    held = np.bincount(labels[bare].ravel(), minlength=int(labels.max()) + 1)
    total = np.bincount(labels.ravel(), minlength=int(labels.max()) + 1)
    in_box = np.bincount(labels[box].ravel(), minlength=int(labels.max()) + 1)
    kept = seeds[(held[seeds] > 0) | (2 * in_box[seeds] >= total[seeds])]
    return kept if kept.size else seeds


@analysis.timed("see_through")
def see_through(image: np.ndarray, region: TextRegion,
                closed: tuple[tuple[int, int, int, int], np.ndarray, np.ndarray]) -> bool:
    """Whether the drawing shows through the paper closed round a model bubble's lettering (*closed*, from
    `closed_interior`): a bubble drawn see-through over hair, a hand, a gun, a caption box over a flower - lettering on
    the drawing, whose lines the paper fill cut (white boxes over them, ends of glyphs left outside the boxes). Its
    lines cross the lettering: the ink joined to the hole of its characters (`THROUGH_HOLE`, at `THROUGH_LEVEL`) runs on
    past them (`THROUGH_GROW`) inside that paper - the light pixels the hole holds and those joined to them, the strokes
    between them closed over (a disc of a glyph) - away from its edge (`THROUGH_CORE`), over `THROUGH_SHARE` of the
    hole. A white bubble's lettering runs on nowhere, and its outline, however close, lies on that edge (a bubble with
    a white rim round its outline, a bubble in a white panel); on the audit's cached sample pages none of the 415
    closed bubbles but one drawn see-through has any of it. Without the reading's characters: no."""
    if not region.char_boxes:
        return False
    (wx0, wy0, wx1, wy1), inside, _far = closed
    gray = cv2.cvtColor(np.ascontiguousarray(image[wy0:wy1, wx0:wx1, :3]), cv2.COLOR_RGB2GRAY)
    if region.dark:
        gray = 255 - gray
    glyph = float(region.glyph or 20.0 * pagescale.of(region))
    hole = _char_hole(region, gray.shape, wx0, wy0, max(2, int(THROUGH_HOLE * glyph)))
    if not hole.any():
        return False
    _n, labels = cv2.connectedComponents((gray >= OUTLINE_LEVEL).astype(np.uint8), connectivity=4)
    seeds = _own_seeds(region, labels, hole & inside, (wx0, wy0))
    own = np.isin(labels, seeds) & inside  # the paper the lettering lies on (not a white rim beyond)
    disc = lambda r: pagescale.disc(2 * r + 1, 1.0)  # noqa: E731 - (radii in px of the page, glyphs already at its scale)
    paper = fill_holes(cv2.morphologyEx(own.astype(np.uint8) * 255, cv2.MORPH_CLOSE, disc(int(glyph) // 2))) > 0
    core = cv2.erode(paper.astype(np.uint8), disc(max(1, int(THROUGH_CORE * glyph)))) > 0
    ink = gray < THROUGH_LEVEL
    _k, parts = cv2.connectedComponents(ink.astype(np.uint8), connectivity=8)
    joined = np.unique(parts[hole & ink])
    on = np.isin(parts, joined[joined > 0]) & core & ~_char_hole(region, gray.shape, wx0, wy0,
                                                                  max(2, int(THROUGH_GROW * glyph)))
    through = int(on.sum()) >= THROUGH_SHARE * int(hole.sum())
    if through:
        analysis.acted(region, "see_through")
    return through


@analysis.timed("art_mask")
def art_mask(image: np.ndarray, region: TextRegion) -> np.ndarray | None:
    """The lettering of *region* as a boolean mask of the page; None when its box holds too little of it. Its strokes
    are found in the box (`ringed`), and past the box (by `reach_of`) what continues a stroke it took: a glyph-sized
    dark piece the box's edge cut off. Each stroke takes its ring and anti-aliasing with it (`with_ring`) wherever they
    lie, past the box too: a box drawn round the strokes alone (a text block's) cuts the white ring of outlined
    lettering, and the ring left round the hole had LaMa draw the glyphs back as grey shapes. The hole is grown by
    `GROW` more, and a pixel for anti-aliasing. A model bubble's own box edge is its outline: a piece lying along it
    (`ALONG` of it within `EDGE` px) is left out, with the ring round it; None too when that leaves too little."""
    x0, y0, x1, y1 = box_of(image, region)
    scale = pagescale.of(region)
    gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    inner, strokes = ringed(gray, scale=scale)
    negative = None
    if region.dark:  # light lettering ringed by dark: the same test on the negative
        dark_inner, negative = ringed(255 - gray, scale=scale)
        inner = inner | dark_inner
    if inner.sum() < MIN_MASK * inner.size:
        return None
    ox0, oy0, ox1, oy1 = around(image, (x0, y0, x1, y1), scale)
    near = cv2.cvtColor(image[oy0:oy1, ox0:ox1], cv2.COLOR_RGB2GRAY)
    mask = np.zeros(near.shape, bool)
    limit = max(PIECE * scale, WIDE_GLYPH * min(x1 - x0, y1 - y0))
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
        mask |= with_ring(level, taken | go_on[labels], scale)
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * GROW + 1,) * 2)
    mask = cv2.dilate(cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)), grow) > 0  # (within `around`)
    if region.from_model and region.kind in ("bubble", "dark-bubble"):
        dark = (near > 255 - DARK) if region.dark else (near < DARK)
        n, labels = cv2.connectedComponents(dark.astype(np.uint8), connectivity=8)  # the dark pieces round the box
        border = np.ones(mask.shape, bool)
        bx0, by0, bx1, by1 = region.x0 - ox0, region.y0 - oy0, region.x1 - ox0, region.y1 - oy0
        edge = pagescale.px(EDGE, scale)
        border[max(0, by0 + edge):max(0, by1 - edge), max(0, bx0 + edge):max(0, bx1 - edge)] = False
        on_border = np.bincount(labels[border & dark].ravel(), minlength=n)
        every = np.bincount(labels.ravel(), minlength=n)
        along = on_border >= ALONG * np.maximum(1, every)  # a piece lying mostly in the band is the outline's
        along[0] = False
        if along.any():  # it stays, and so does the ring round it
            outline = along[labels]
            mask &= ~(cv2.dilate(outline.astype(np.uint8), pagescale.disc(13, scale)) > 0)
        if mask.sum() < MIN_MASK * inner.size:
            return None
    full = np.zeros(image.shape[:2], bool)
    full[oy0:oy1, ox0:ox1] = mask
    return full


def plain_ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None = None,
                 within: np.ndarray | None = None, scale: float = 1.0) -> bool:
    """Whether the ground right round the lettering's *hole* (bool, the page; `GROUND_BAND`), within *box* when given,
    is one colour or a smooth shading of it: a black or white panel, a flat tone, a gradient. There the hole is painted
    with that ground (`fill_ground`) and a model, which makes up a texture, would only blotch it. The erase gives no
    box: the hole holds the white ring of outlined lettering, so the band round it is the ground past the ring. (Within
    the lettering box, a box drawn round the strokes alone, the ring was all the ground there was: lettering on a
    drawing passed for lettering on white paper, and was painted white.) *within* (bool, the page): the band is taken
    there alone (a reader's rectangle: `drawn_on_art`). *scale*: the page's (`pagescale`), the band's width at it."""
    found = _ground(image, hole, box, within, scale)
    if found is None:
        return False
    crop, _part, band, surface = found
    off = np.sqrt(((crop[band].astype(np.float32) - surface[band]) ** 2).sum(axis=1))
    return float(np.percentile(off, 90)) < GROUND_FIT


def _ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None,
            within: np.ndarray | None = None, scale: float = 1.0
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """The part of the page round *hole* (`GROUND_BAND`, within *box*), the hole and the ground band in it (bool, and
    in *within* when given), and the smooth surface fitted to the band (`paper_surface`); None when there is too
    little of it."""
    ys, xs = np.nonzero(hole)
    if not xs.size:
        return None
    h, w = hole.shape[:2]
    pad = pagescale.px(GROUND_BAND, scale)
    x0, y0, x1, y1 = max(0, xs.min() - pad), max(0, ys.min() - pad), min(w, xs.max() + 1 + pad), min(h, ys.max() + 1 + pad)
    if box is not None:
        x0, y0, x1, y1 = max(x0, box[0]), max(y0, box[1]), min(x1, box[2]), min(y1, box[3])
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
    part = hole[y0:y1, x0:x1]
    band = (cv2.dilate(part.astype(np.uint8), pagescale.disc(GROUND_BAND, scale)) > 0) & ~part
    if within is not None:
        band &= within[y0:y1, x0:x1]
    if int(band.sum()) < 16:
        return None
    crop = image[y0:y1, x0:x1, :3]
    return crop, part, band, paper_surface(crop, band)


@analysis.timed("ground_fill")
def fill_ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None = None,
                scale: float = 1.0) -> bool:
    """Paint *hole* (bool, the page) in place with its plain ground as `plain_ground` judged it (within *box*): the
    smooth surface fitted to the band right round it, so a gradient stays a gradient and the white ring of outlined
    lettering goes with its strokes. Whether it was painted."""
    found = _ground(image, hole, box, scale=scale)
    if found is None:
        return False
    crop, part, _band, surface = found
    crop[part] = np.clip(np.round(surface[part]), 0, 255).astype(np.uint8)
    return True


@analysis.timed("tone_look")
def tone_shifts(image: np.ndarray, hole: np.ndarray, scale: float = 1.0
                ) -> tuple[tuple[int, int, int, int], list[tuple[int, int]]] | None:
    """The shifts at which the ground round *hole* (bool, the page) repeats itself, as (the window looked at, the
    shifts (dy, dx) nearest first), when that ground is a pattern that repeats - a screentone's dots, a hatching's
    lines; None otherwise. Measured on the ground within `TONE_BAND` px of the hole (at the page's *scale*), the hole
    and a pixel round it left out: its normalised autocorrelation. A pattern repeats where it climbs back to
    `TONE_REPEAT` at a shift of at least `TONE_LEAST` px after falling under `TONE_DIP` on the way there (a dot's
    width; a drawing's smooth parts correlate at a short shift too, but never fall and climb back); the shifts taken
    are those it repeats at, `TONE_SHIFTS` at the most. What the hole encloses (`_closed`) is no ground."""
    ys, xs = np.nonzero(hole)
    if not xs.size:
        return None
    h, w = hole.shape[:2]
    band = pagescale.px(TONE_BAND, scale)
    x0, y0 = max(0, int(xs.min()) - band), max(0, int(ys.min()) - band)
    x1, y1 = min(w, int(xs.max()) + 1 + band), min(h, int(ys.max()) + 1 + band)
    if (x1 - x0) * (y1 - y0) > TONE_MOST_PX:
        analysis.count("tone_look.too_large")
        return None  # (LaMa, or the fill past it, takes so large a hole)
    part = _closed(hole[y0:y1, x0:x1])
    near = cv2.dilate(part.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    ground = ~near & (cv2.dilate(part.astype(np.uint8), pagescale.disc(2 * band + 1, 1.0)) > 0)
    if int(ground.sum()) < TONE_GROUND:
        return None
    gray = cv2.cvtColor(np.ascontiguousarray(image[y0:y1, x0:x1, :3]), cv2.COLOR_RGB2GRAY).astype(np.float64)
    m = ground.astype(np.float64)
    z = (gray - float(gray[ground].mean())) * m
    if float(np.sqrt((z[ground] ** 2).mean())) < TONE_CONTRAST:
        return None  # an even ground: no pattern to repeat
    hh, ww = part.shape
    size = (2 * hh, 2 * ww)
    fz, fm, fq = np.fft.rfft2(z, size), np.fft.rfft2(m, size), np.fft.rfft2(z * z, size)
    # sums over the pixels p of the ground whose p + d lies on the ground too, for every shift d
    cross = np.fft.irfft2(np.conj(fz) * fz, size)
    there = np.fft.irfft2(np.conj(fm) * fq, size)  # the energy at p + d
    here = np.fft.irfft2(np.conj(fq) * fm, size)  # the energy at p
    count = np.fft.irfft2(np.conj(fm) * fm, size)
    least_overlap = max(TONE_OVERLAP, TONE_OVERLAP_SHARE * float(ground.sum()))
    ncc = np.where((count > least_overlap) & (here > 1e-6) & (there > 1e-6),
                   cross / np.sqrt(np.maximum(here * there, 1e-12)), -1.0)
    ncc = np.fft.fftshift(ncc)  # shift (0, 0) at (hh, ww)
    least = max(2.0, TONE_LEAST * scale)
    dy, dx = np.mgrid[-hh:hh, -ww:ww]
    far = np.hypot(dy, dx)
    peak = (ncc >= TONE_REPEAT) & (far >= least) & (far <= TONE_PITCH * max(scale, 0.5))
    if not peak.any():
        return None
    # one such shift must lie past a dip: the pattern falls off between its repeats (a hatching's lines do not along
    # themselves, only across)
    k = np.flatnonzero(peak.ravel())
    k = k[np.argsort(far.ravel()[k], kind="stable")][:TONE_PEAKS]

    def dips(at: int) -> bool:
        by, bx = int(dy.ravel()[at]), int(dx.ravel()[at])
        steps = int(max(abs(by), abs(bx)))
        path = [ncc[hh + round(by * t / steps), ww + round(bx * t / steps)] for t in range(1, steps)]
        return bool(path) and min(path) <= TONE_DIP

    if not any(dips(int(at)) for at in k):
        return None
    good = (ncc >= TONE_REPEAT) & (far >= least)
    order = np.argsort(far[good], kind="stable")[:TONE_SHIFTS]
    shifts = list(zip(dy[good][order].tolist(), dx[good][order].tolist()))
    return (x0, y0, x1, y1), shifts


def _closed(hole: np.ndarray) -> np.ndarray:
    """*hole* (bool) with what it encloses: the counters of its glyphs (the white inside a ringed glyph's loops)."""
    return fill_holes(hole.astype(np.uint8) * 255) > 0


@analysis.timed("tone_fill")
def fill_tone(image: np.ndarray, hole: np.ndarray, scale: float = 1.0) -> bool:
    """Paint *hole* (bool, the page) in place from the pattern round it, when that ground repeats itself
    (`tone_shifts`): each pixel of the hole takes the pixel at the nearest shift the pattern repeats at that is ground
    or already painted (from the hole's edge inwards: the nearest `TONE_NEAR` shifts again and again, then the
    others), so a screentone's dots go on through where the lettering was. LaMa made rows of stripes of a dot tone
    round lettering with a white ring, a rectangle of it clearly seen at every size. The hole is taken `TONE_GROW` px
    wider (the ring's anti-aliasing, lighter than the tone, is no ground of it), with what it encloses (the counters of
    ringed glyphs, white like their ring). Whether all of it was painted (nothing is painted otherwise)."""
    grown = cv2.dilate(hole.astype(np.uint8), np.ones((2 * TONE_GROW + 1,) * 2, np.uint8)) > 0
    found = tone_shifts(image, grown, scale)
    if found is None:
        return False
    (x0, y0, x1, y1), shifts = found
    part = image[y0:y1, x0:x1]
    taken = _closed(grown[y0:y1, x0:x1])
    source = ~(cv2.dilate(taken.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    painted = part.copy()
    ys, xs = np.nonzero(taken)
    hh, ww = taken.shape

    def paint(sy: int, sx: int) -> bool:
        nonlocal ys, xs
        py, px_ = ys + sy, xs + sx
        ok = (py >= 0) & (py < hh) & (px_ >= 0) & (px_ < ww)
        ok[ok] = source[py[ok], px_[ok]]
        if not ok.any():
            return False
        painted[ys[ok], xs[ok]] = painted[py[ok], px_[ok]]
        source[ys[ok], xs[ok]] = True
        ys, xs = ys[~ok], xs[~ok]
        return True

    rounds = 0
    while ys.size and rounds < TONE_ROUNDS and any([paint(sy, sx) for sy, sx in shifts[:TONE_NEAR]]):
        rounds += 1
    for sy, sx in shifts[TONE_NEAR:]:
        if not ys.size:
            break
        paint(sy, sx)
    if ys.size:
        return False
    part[taken] = painted[taken]
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
    return not plain_ground(image, hole, within=within, scale=pagescale.of(region))


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


def scaled_part(part: np.ndarray, hole: np.ndarray, most: int) -> tuple[np.ndarray, np.ndarray]:
    """*part* and *hole* as LaMa is run on them: as they are within *most* pixels, else scaled down to them (the
    hole taken at every pixel it touches, and two pixels wider: the cubic that scales the fill back up reaches two
    pixels, so every pixel of the hole comes from the fill alone, none of the lettering's edge with it)."""
    h, w = part.shape[:2]
    if h * w <= most:
        return part, hole
    f = (most / float(h * w)) ** 0.5
    size = (max(1, int(w * f)), max(1, int(h * f)))
    small = cv2.resize(np.ascontiguousarray(part), size, interpolation=cv2.INTER_AREA)
    taken = cv2.resize(hole.astype(np.uint8) * 255, size, interpolation=cv2.INTER_AREA) > 0
    taken = cv2.dilate(taken.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return small, taken


def telea(part: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """*part* with *hole* filled from round it by OpenCV's inpainting (Telea's), within the hole's box and
    `TELEA_RADIUS` round it: what the lettering on the drawing gets once the page's budget for LaMa is spent
    (milliseconds; smoother than LaMa's fill)."""
    out = part.copy()
    ys, xs = np.nonzero(hole)
    if not xs.size:
        return out
    m = 4 * TELEA_RADIUS
    y0, y1 = max(0, int(ys.min()) - m), min(part.shape[0], int(ys.max()) + 1 + m)
    x0, x1 = max(0, int(xs.min()) - m), min(part.shape[1], int(xs.max()) + 1 + m)
    crop = np.ascontiguousarray(part[y0:y1, x0:x1, :3])
    mask = hole[y0:y1, x0:x1].astype(np.uint8) * 255
    out[y0:y1, x0:x1, :3] = cv2.inpaint(crop, mask, TELEA_RADIUS, cv2.INPAINT_TELEA)
    return out


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
    CPU for the rest of the session (`ArtEraser._fill`): a fallback, not this rule's choice."""
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


Kept = tuple[tuple[int, int, int, int], np.ndarray, np.ndarray]


@analysis.timed("keep_lines")
def _keep_lines(image: np.ndarray, region: TextRegion, dark: bool, dark_threshold: int) -> Kept | None:
    """The straight lines of the drawing that run through the box of lettering set on the page (`erase.line_pixels`:
    a bubble's tail crossing it) and their pixels as they are, to be put back (`_put_back`) after a fill that took
    them with the lettering's ring; the paper fill keeps them too. (Left out of the hole, they made the ground fitted
    round it darker.) So are those through the lettering box of a model bubble with no shape of its own (tier 3) on
    the drawing (`on_art`: no paper closed round it, or the drawing seen through it): its plain box holds the drawing."""
    if dark:
        return None
    if region.kind in ("bubble", "dark-bubble") and region.tier == 3:
        lettering = copy.copy(region)
        lettering.x0, lettering.y0, lettering.x1, lettering.y1 = box_of(image, region)
        region = lettering
    elif region.kind not in ART_KINDS:
        return None
    found = line_pixels(image, region, dark_threshold)
    if found is None:
        return None
    (x0, y0, x1, y1), lines = found
    return (x0, y0, x1, y1), lines, image[y0:y1, x0:x1][lines].copy()


def _put_back(image: np.ndarray, kept: Kept | None, region: TextRegion | None = None) -> None:
    """The lines `_keep_lines` kept put back on *image*; the pixels that differed from the fill counted for the
    analysis log (*region*: the one whose erase it follows)."""
    if kept is not None:
        (x0, y0, x1, y1), lines, pixels = kept
        if region is not None and analysis.on():
            back = int(np.any(image[y0:y1, x0:x1][lines] != pixels, axis=-1).sum())
            if back:
                analysis.acted(region, "keep_lines")
                analysis.count("keep_lines.px", back)
        image[y0:y1, x0:x1][lines] = pixels


def _hole(image: np.ndarray, region: TextRegion, judged: TextRegion, full: np.ndarray) -> np.ndarray:
    """The hole the art's erase fills for *region* (*full*, `art_mask` of the region as judged), taking in the model's
    text box too where the region is judged as another one (`as_judged`)."""
    if judged is not region:
        wider = art_mask(image, region)
        if wider is not None:
            full = full | wider
    return full


def tone_erase(image: np.ndarray, region: TextRegion, dark: bool = False) -> tuple[int, int, int] | None:
    """The tone fill with no inpainting model (`Pipeline._erase` where LaMa is not set to run, as on a computer without
    a GPU): lettering on the art (`on_art`, not on paper: `on_paper`) whose ground round it is no flat colour or smooth
    shading (`plain_ground`) but repeats itself - a screentone's dots, a hatching, stripes - is painted over with that
    ground (`fill_tone`), as the art eraser does (`ArtEraser.erase`), and its paper colour is returned; None, nothing
    touched, where the tone fill does not take it: the paper fill erases it as before."""
    if not TONE_FILL or not on_art(image, region) or on_paper(image, region):
        return None
    judged = as_judged(region)
    full = art_mask(image, judged)
    scale = pagescale.of(region)
    if full is None or plain_ground(image, full, scale=scale):
        return None
    if not fill_tone(image, _hole(image, region, judged, full), scale):
        return None
    analysis.acted(region, "tone_fill")
    return paper_colour(*ArtEraser._crop_mask(image, region), dark)


class ArtEraser:
    """`erase` for regions on the art, with LaMa in *models_dir*, loaded on first use."""

    def __init__(self, models_dir: Path, setting: str = "auto", fallback: Erase = erase_region):
        self.models_dir = Path(models_dir)
        self.setting = setting
        self.fallback = fallback
        self.failed = False  # LaMa could not run: `erase_region` does it all from then on
        self.counts = {"art": 0, "plain": 0, "weak": 0, "ground": 0, "tone": 0, "telea": 0}  # what the regions went to
        self._model: Any = None
        self._checked = False
        self._release_asked = False  # a release that came while the model was at work: done once it is free
        self._lock = threading.Lock()

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
        """Where the model loads: the GPU where torch has CUDA and the session's plan has it there
        (`ocr.place.on_gpu`: not sent to the processor for the room, no failure there this session)."""
        import torch

        from ..ocr import place

        return "cuda" if torch.cuda.is_available() and place.on_gpu(place.LAMA) else "cpu"

    def _load(self, device: str) -> None:
        from .lama import LamaInpainter

        with analysis.timing("lama.load"):
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

    @analysis.timed("lama")
    def _fill(self, part: np.ndarray, hole: np.ndarray) -> np.ndarray | None:
        """*part* with *hole* filled; None when LaMa cannot do it. A failure on the GPU, loading or running, moves it
        to the CPU for the rest of the session (`ocr.place.failed`); a failure on the CPU leaves the paper fill for the
        session. After a window on the GPU the idle cache is given back (`give_back_idle`)."""
        with self._lock:
            if self.failed:
                return None
            device = self._model.device if self._model is not None else self._device()
            full_part = part
            part, hole = scaled_part(part, hole, LAMA_PART_PX if device != "cpu" else LAMA_PART_CPU_PX)
            if part is not full_part:
                analysis.count("lama.scaled")
            if analysis.on():  # (the analysis log: LaMa's windows, their pixels and hole, those on the GPU)
                analysis.count("lama.windows")
                analysis.count("lama.window_px", int(part.shape[0] * part.shape[1]))
                analysis.count("lama.hole_px", int(np.count_nonzero(hole)))
                if device != "cpu":
                    analysis.count("lama.gpu_windows")
                elif has_cuda():
                    analysis.count("lama.cpu_windows_with_gpu")  # (moved there for the room, or a failure)
            filled, why = self._try(device, part, hole)
            if filled is not None and device != "cpu":
                give_back_idle()
            if filled is None and device != "cpu":
                from ..ocr import place

                place.failed(place.LAMA, why)
                self._drop(device)
                filled, why = self._try("cpu", part, hole)
            if filled is None:
                LOG.warning("inpainting failed (%s): the paper fill from now on", why)
                self._drop("cpu")
                self.failed = True
            if self._release_asked:
                self._release_asked = False
                self._drop(device)
            if filled is not None and part is not full_part:  # (back to the part's size: its hole alone is taken)
                filled = cv2.resize(filled, (full_part.shape[1], full_part.shape[0]), interpolation=cv2.INTER_CUBIC)
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
        region.toned = False
        judged = as_judged(region)
        scale = pagescale.of(region)
        if self.failed or not on_art(image, region):
            self.counts["plain"] += 1
            if not self.failed and FLAT_RINGS and region.kind in ART_KINDS:
                full = art_mask(image, judged)  # outlined lettering on a flat ground: its ring painted that ground
                if full is not None and plain_ground(image, full, scale=scale):
                    kept = _keep_lines(image, region, dark, dark_threshold)
                    fill_ground(image, full, scale=scale)
                    analysis.acted(region, "ground_fill")
                    _put_back(image, kept, region)
            return app()
        if on_paper(image, region):
            self.counts["ground"] += 1
            return app()
        full = art_mask(image, judged)
        if full is None:
            self.counts["weak"] += 1
            return app()
        if plain_ground(image, full, scale=scale):
            self.counts["ground"] += 1
            if GROUND_FILL:
                kept = _keep_lines(image, region, dark, dark_threshold)
                fill_ground(image, full, scale=scale)  # (strokes, ring and all; the paper fill takes what is left)
                analysis.acted(region, "ground_fill")
                _put_back(image, kept, region)
            return app()
        full = _hole(image, region, judged, full)  # (the model's text box too)
        if TONE_FILL and fill_tone(image, full, scale):  # a screentone, a hatching: painted on from round the hole
            self.counts["tone"] += 1
            region.toned = True
            analysis.acted(region, "tone_fill")
            return paper_colour(*self._crop_mask(image, region), dark)
        x0, y0, x1, y1 = box_of(image, region)
        wx0, wy0, wx1, wy1 = window(image.shape, x0, y0, y1 - y0, x1 - x0)
        part, hole = image[wy0:wy1, wx0:wx1], full[wy0:wy1, wx0:wx1]
        key = hashlib.sha1(np.ascontiguousarray(part).tobytes() + np.packbits(hole).tobytes()).digest()
        kept = region.inpainted
        if kept is not None and kept[0] == key:
            pixels, where = kept[1], kept[2]
        else:
            refused = self._refused(part, hole) if min(part.shape[:2]) >= SMALLEST else ""
            if refused:  # (the page's budget for LaMa spent: OpenCV's fill, not kept on the region)
                self.counts["telea"] += 1
                analysis.count(f"lama.refused.{refused}")
                analysis.acted(region, "telea")
                where, pixels = paste(part, telea(part, hole), hole)
                part[where] = pixels
                return paper_colour(*self._crop_mask(image, region), dark)
            filled = self._fill(part, hole) if min(part.shape[:2]) >= SMALLEST else None
            if filled is None:
                self.counts["plain"] += 1
                return app()
            where, pixels = paste(part, filled, hole)
            region.inpainted = (key, pixels, where)
        self.counts["art"] += 1
        analysis.acted(region, "lama")
        part[where] = pixels
        return paper_colour(*self._crop_mask(image, region), dark)

    def _refused(self, part: np.ndarray, hole: np.ndarray) -> str:
        """Why the page's budget refuses LaMa this *part* (`budget.lama_refused`: "" where it may run), counted
        at the pixels it would be run on."""
        from .. import budget

        if budget.current() is None:  # (no page's budget: a tool, a region erased alone)
            return ""
        model = self._model
        on_gpu = (model.device if model is not None else self._device()) != "cpu"
        cap = LAMA_PART_PX if on_gpu else LAMA_PART_CPU_PX
        return budget.lama_refused(min(cap, int(part.shape[0] * part.shape[1])), int(np.count_nonzero(hole)), on_gpu)

    @staticmethod
    def _crop_mask(image: np.ndarray, region: TextRegion) -> tuple[np.ndarray, np.ndarray]:
        """The region's crop of *image* and its mask (bool, the crop's size): what its paper colour is judged on."""
        crop = image[region.y0:region.y1, region.x0:region.x1]
        mask = region.mask
        if crop.shape[:2] != mask.shape:
            mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
        return crop, mask > 0

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
