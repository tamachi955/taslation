"""Remove the original text from a bubble before the translation is drawn.

A bubble's mask is its interior; lettering that runs past it onto the drawing (over hair, over tone, across
the outline) would stay. The glyph-sized pieces inside the text box but outside the mask are the stray
lettering: each is painted, outline and all, with the colour of the drawing around it (black over hair, the
grey of a tone, white past the outline), so the drawing is kept and the glyphs go.

Light and dark alone do not tell the lettering from the page. A thin outline is broken into short pieces wherever
its anti-aliasing is lighter than the dark threshold, and such a piece inside the text box passed for a glyph; a
piece of a light ground (cream or pastel paper, the white between two bubbles read as one, a window in the drawing)
passed for the white ring of an outlined glyph. Painted with the colour around them, they left patches of paper on
the ground, gaps in the outline and blots on the drawing. And the detector's mask, everything at least as light as
``white_threshold``, can run out through a gap in the outline over a ground that light. So the erase stays within
the bubble's outline (`within_outline`: the outline's small gaps are closed first), takes the bubble's own paper
colour judged against that paper rather than a fixed grey level (`paper_colour`), paints it flat, or along the
paper's shading where it is shaded (`fill_paper`; of lettering set on the page only the lettering and the ground
right round it), and takes only pieces that look like lettering for stray lettering (`StrayJudge`). The erase of
before stays as ``erase_mode = "classic"``, byte for byte.
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from ..detect.beyond import big_dark, rings_on_dark
from ..detect.bubbles import fill_holes
from ..regions import Box, TextRegion

STRAY_KINDS = frozenset({"bubble", "dark-bubble"})  # regions whose mask is an interior the lettering can leave
_HALO = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))  # takes a glyph's outline (2-3 px) with it
_AROUND = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))  # the drawing just beyond the outline

PAPER_DE = 10.0  # CIELAB distance within which a pixel is the bubble's own paper
RING_DE = 12.0  # ... within which the ring of an outlined glyph is white or the paper's colour
GLYPH_REACH = 1.6  # a piece of stray lettering is at most this many glyphs long
LINK_LEVELS = 30  # grey levels past the dark threshold at which the pieces of a thin line still join up
SEAL_SIZES = (5, 7, 9, 11, 13)  # closings that seal a gap in a thin outline, the narrowest first
OUTLINE_GLYPHS = 2.0  # a dark piece longer than this many glyphs is a line (the outline, the drawing), not lettering
MARGIN = 8  # px around a region looked at for its outline and its surroundings
INTERIOR_SHARE = 0.5  # of what a light piece encloses: this much of the mask makes it the paper round the interior
MANUAL_KINDS = frozenset({"manual", "manual-dark"})  # a rectangle the reader drew
ON_PAGE_KINDS = frozenset({"text", "text-dark", "text-on-page", "text-on-dark"})  # lettering set on the page's ground
_REACH = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))  # a mask's erosion margin and anti-aliasing
LEAK_BEYOND = 20  # px of a cut-off part lying beyond the mask's reach that make it part of the page beyond
LEAK_GROUND = 12  # px of a cut-off part from which its ground, when it is not the bubble's paper, makes it so too
LETTER_SHARE = 0.1  # glyph-sized ink in the text box, a tenth of a glyph's square, makes a cut-off part lettering
LEAK_MIN = 60  # px: a closing that cuts off less than this from the lettering seals nothing worth taking out

# (light, x, y, w, h, the piece's own pixels and the piece with its holes, both in its box) -> lettering or not
PieceTest = Callable[[bool, int, int, int, int, np.ndarray, np.ndarray], bool]


def _lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.ascontiguousarray(rgb[..., :3]).astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def _disc(size: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def _window(image: np.ndarray, region: TextRegion, margin: int = MARGIN) -> Box:
    h, w = image.shape[:2]
    return (max(0, region.x0 - margin), max(0, region.y0 - margin),
            min(w, region.x1 + margin), min(h, region.y1 + margin))


def bubble_background(crop: np.ndarray, mask: np.ndarray, white_threshold: int = 225,
                      dark: bool = False) -> tuple[int, int, int]:
    """Median colour of the bubble interior away from the lettering.

    Light bubbles: the bright part (white for most bubbles). Dark bubbles
    (``dark=True``): the dark part, with the light lettering left out.
    """
    inside = mask > 0
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    if dark:
        chosen = inside & (gray <= 255 - white_threshold)
    else:
        chosen = inside & (gray >= white_threshold)
    if chosen.sum() < 16:
        # Toned bubble: use the half of the interior that is further from the lettering.
        vals = gray[inside]
        if vals.size == 0:
            return (0, 0, 0) if dark else (255, 255, 255)
        chosen = inside & ((gray <= np.percentile(vals, 50)) if dark else (gray >= np.percentile(vals, 50)))
    pix = crop[chosen]
    if pix.size == 0:
        return (0, 0, 0) if dark else (255, 255, 255)
    med = np.median(pix.reshape(-1, 3), axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


def paper_colour(crop: np.ndarray, mask: np.ndarray, dark: bool = False) -> tuple[int, int, int]:
    """The colour of the bubble's own paper: the median of the pixels of *mask* that lie within
    `PAPER_DE` of the median of its lighter half (its darker half for a dark bubble). The paper is judged against
    its own colour rather than a fixed grey level, so a cream, pastel or toned bubble gets its own colour, and a
    ground of another colour that the mask took in does not pull the fill towards it."""
    pix = crop[mask > 0].reshape(-1, 3)
    if pix.shape[0] == 0:
        return (0, 0, 0) if dark else (255, 255, 255)
    lab = _lab(pix[None])[0]
    light = lab[:, 0]
    half = light <= np.median(light) if dark else light >= np.median(light)
    first = np.median(pix[half], axis=0)
    first_lab = _lab(np.clip(np.round(first), 0, 255).astype(np.uint8)[None, None])[0, 0]
    near = np.sqrt(((lab - first_lab) ** 2).sum(axis=1)) < PAPER_DE
    med = np.median(pix[near] if int(near.sum()) >= 16 else pix[half], axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


def _glyph(region: TextRegion) -> float:
    return region.glyph if region.glyph > 0 else 24.0


def within_outline(image: np.ndarray, region: TextRegion, mask: np.ndarray, dark_threshold: int = 140,
                   dark: bool = False) -> np.ndarray:
    """The part of *mask* (bool, the region's box) that lies within the bubble's outline.

    The outline is the dark pieces that reach out of the mask or are longer than `OUTLINE_GLYPHS` glyphs (the
    bubble's line, even where the mask runs round it, the panel's border, the drawing around). Closed with growing
    sizes (`SEAL_SIZES`) so that a gap of a few pixels is sealed, it may cut a part of the mask off from the
    lettering. A part that belongs to the page beyond is taken out, with what lies in it, the stretch of outline it
    runs round and the ground of another colour that the closing left joined to the bubble at the gap: a part that
    holds no lettering (`LETTER_SHARE`) and whose ground is not the bubble's paper (`PAPER_DE`) or that reaches well
    past the mask (`LEAK_BEYOND`). A part with lettering in it (a column the region grew over, the end of a column
    set across the outline), a part of the bubble's own paper that the closing cuts off (a lobe behind a narrow
    neck, a corner) and lettering against the outline stay. *mask* is returned as it is when nothing is cut off,
    when the cut would leave less than a third of it, and for a region that is no bubble (lettering on the page,
    the reader's rectangle: no outline encloses it)."""
    if region.kind not in STRAY_KINDS or not mask.any():
        return mask
    wx0, wy0, wx1, wy1 = _window(image, region)
    window = np.ascontiguousarray(image[wy0:wy1, wx0:wx1, :3])
    gray = cv2.cvtColor(window, cv2.COLOR_RGB2GRAY)
    if dark:
        gray = 255 - gray
    ox, oy = region.x0 - wx0, region.y0 - wy0
    mh, mw = mask.shape
    mk = np.zeros(gray.shape, bool)
    mk[oy:oy + mh, ox:ox + mw] = mask
    ink = gray < dark_threshold
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    near = cv2.dilate(mk.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    total = np.bincount(labels.ravel(), minlength=n)
    out_of = np.bincount(labels[~near].ravel(), minlength=n)
    longest = max(OUTLINE_GLYPHS * _glyph(region), 2 * MARGIN)
    lines = (out_of >= np.maximum(4, 0.2 * total)) | (np.maximum(stats[:, 2], stats[:, 3]) > longest)
    lines[0] = False
    outline = lines[labels].astype(np.uint8)
    side = np.maximum(stats[:, 2], stats[:, 3])
    glyphs = ~lines & (side >= max(5.0, 0.3 * _glyph(region))) & (stats[:, 4] >= 8)  # pieces the size of lettering
    glyphs[0] = False
    letter_ink = LETTER_SHARE * _glyph(region) ** 2  # a stroke or two of a glyph: a part holding it holds lettering
    tb = region.text_box or (region.x0, region.y0, region.x1, region.y1)
    box = np.zeros(gray.shape, bool)
    box[max(0, tb[1] - wy0):max(0, tb[3] - wy0), max(0, tb[0] - wx0):max(0, tb[2] - wx0)] = True
    core = mk & box & ~ink
    if int(core.sum()) < 16:
        core = mk & ~ink
    reach = cv2.dilate(mk.astype(np.uint8), _REACH) > 0
    lab: np.ndarray | None = None
    for size in SEAL_SIZES:
        barrier = ink | (cv2.morphologyEx(outline, cv2.MORPH_CLOSE, _disc(size)) > 0)
        nf, free = cv2.connectedComponents((~barrier).astype(np.uint8), connectivity=4)
        ids, counts = np.unique(free[core & ~barrier], return_counts=True)
        if not ids.size:
            continue
        inner = free == ids[int(np.argmax(counts))]
        cut = mk & ~barrier & ~inner
        if int(cut.sum()) < LEAK_MIN:
            continue
        in_mask = np.bincount(free[mk].ravel(), minlength=nf)
        beyond = np.bincount(free[~reach].ravel(), minlength=nf)
        rest = mk & ~(fill_holes(inner.astype(np.uint8) * 255) > 0)
        nr, parts = cv2.connectedComponents(rest.astype(np.uint8), connectivity=8)
        # the glyph-sized pieces of ink each part of the rest holds: a part with lettering in it is the text's
        letters = np.bincount(parts[rest & box & glyphs[labels]], minlength=nr) if glyphs.any() else np.zeros(nr, int)
        leaks: list[int] = []
        paper: np.ndarray | None = None
        for i in (int(v) for v in np.unique(free[cut])):
            if in_mask[i] < LEAK_GROUND or int(letters[np.unique(parts[rest & (free == i)])].sum()) >= letter_ink:
                continue  # too small to matter, or it holds lettering: part of the text, whatever lies under it
            if lab is None:
                lab = _lab(window)
            if paper is None:
                paper = np.median(lab[inner & mk], axis=0)
            ground = np.median(lab[(free == i) & mk], axis=0)
            if float(np.sqrt(((paper - ground) ** 2).sum())) >= PAPER_DE or beyond[i] >= LEAK_BEYOND:
                leaks.append(i)  # another ground than the bubble's paper, or the page beyond the bubble
        if not leaks:
            continue
        hit = np.unique(parts[rest & np.isin(free, leaks)])
        gone = np.isin(parts, hit[hit > 0])
        # the ground that the closing left joined to the bubble right at the gap goes with the rest of it: what of
        # the mask is not ink, not the bubble's paper, and touches what was taken out
        if lab is None:
            lab = _lab(window)
        if paper is None:
            paper = np.median(lab[inner & mk], axis=0)
        foreign = mk & ~gone & ~ink & (np.sqrt(((lab - paper) ** 2).sum(axis=2)) >= PAPER_DE)
        _nf, pieces = cv2.connectedComponents(foreign.astype(np.uint8), connectivity=8)
        touch = np.unique(pieces[(cv2.dilate(gone.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & foreign])
        gone |= np.isin(pieces, touch[touch > 0])
        kept = mask & ~gone[oy:oy + mh, ox:ox + mw]
        if int(kept.sum()) < int(mask.sum()) / 3:
            return mask
        return kept
    return mask


FILL_SIGMAS = (1.5, 3.0, 6.0, 12.0, 24.0)  # px: the ground a stroke is painted from, nearest first
INK_DROP = 10.0  # CIELAB lightness below the paper's around it from which a pixel is lettering or its anti-aliasing
STROKE_DROP = 25.0  # ... and from which it is a stroke (the faint marks of a ground stay unless next to one)
DEEP_DROP = 30.0  # CIELAB lightness below the paper's own from which a pixel is lettering, whatever lies around it
FLAT_DE = 4.0  # paper whose pixels (nine in ten) lie this close to its colour is flat: painted in that one colour
FOREIGN_SHARE = 0.01  # lettering on the page: a ground with this share of other colours holds some of the drawing
SHADE_DE = 25.0  # CIELAB distance from the paper's colour within which a bubble's shading is followed
SURFACE_POINTS = 6000  # paper pixels the shading of a bubble is fitted to (at most)


def paper_surface(crop: np.ndarray, paper: np.ndarray) -> np.ndarray:
    """The shading of the paper pixels *paper* (bool) of *crop* as a smooth surface over the whole crop (float32 RGB):
    a quadratic in x and y per channel, fitted by least squares, refitted once without the pixels far off the first
    fit (the anti-aliasing and noise of lettering), so a gradient is followed and no ghost of the lettering stays."""
    h, w = crop.shape[:2]
    ys, xs = np.nonzero(paper)
    if xs.size > SURFACE_POINTS:
        pick = np.linspace(0, xs.size - 1, SURFACE_POINTS).astype(int)
        ys, xs = ys[pick], xs[pick]
    cx, cy, sx, sy = w / 2.0, h / 2.0, max(1.0, w / 2.0), max(1.0, h / 2.0)

    def terms(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        u, v = (x - cx) / sx, (y - cy) / sy
        return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)

    a = terms(xs.astype(np.float32), ys.astype(np.float32))
    b = crop[ys, xs, :3].astype(np.float32)
    coef = np.linalg.lstsq(a, b, rcond=None)[0]
    off = np.sqrt(((a @ coef - b) ** 2).sum(axis=1))
    near = off <= max(6.0, 2.5 * float(np.median(off)))
    if 12 <= int(near.sum()) < near.size:
        coef = np.linalg.lstsq(a[near], b[near], rcond=None)[0]
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    return terms(gx, gy) @ coef


def fill_paper(crop: np.ndarray, mask: np.ndarray, colour: tuple[int, int, int], dark: bool = False,
               whole: bool = True) -> None:
    """Paint *mask* (bool) in *crop* with its paper as it is there.

    The paper is the pixels of the mask that are not lettering: the lettering is what is darker than the paper's
    lightness around it by `INK_DROP`, or than the paper's own (*colour*'s) by `DEEP_DROP` (strokes too thick for
    the lightness around them to show), lighter in a dark bubble, with a fringe of three pixels for its
    anti-aliasing. Flat paper (`FLAT_DE`) is painted in *colour* (its own colour: cream for a cream bubble); shaded
    paper follows its shading (`paper_surface`, fitted to the paper within `SHADE_DE` of its colour, and *colour*
    again where the fit strays further), so a gradient keeps its gradient. *whole*: the whole mask is painted
    (a bubble's interior). Otherwise (lettering set on the page) on a flat ground with next to nothing else in it
    (`FOREIGN_SHARE`) the lettering and six pixels round it are painted in the ground's colour; on any other ground
    only the lettering next to a stroke (`STROKE_DROP`) and its fringe are painted, each pixel from the nearest
    ground (a blur of the ground alone, at the smallest of `FILL_SIGMAS` that reaches some), and the rest of the
    ground (a pattern, the light parts of a drawing) stays as it is."""
    if not mask.any():
        return
    lab = _lab(crop)
    light = 100.0 - lab[..., 0] if dark else lab[..., 0]
    ref = _lab(np.array([[colour]], np.uint8))[0, 0]
    own = 100.0 - ref[0] if dark else ref[0]  # the paper's own lightness
    level = cv2.morphologyEx(light, cv2.MORPH_CLOSE, _disc(15))  # the paper's lightness, strokes closed over
    deep = light < own - DEEP_DROP  # far darker than the paper: lettering, however thick its strokes
    ink = mask & ((light < level - INK_DROP) | deep)
    fringe = cv2.dilate(ink.astype(np.uint8), _disc(7)) > 0
    if whole:
        hole = mask.copy()
    else:
        strokes = cv2.dilate((mask & ((light < level - STROKE_DROP) | deep)).astype(np.uint8), _disc(7)) > 0
        hole = mask & (cv2.dilate((ink & strokes).astype(np.uint8), _disc(7)) > 0)
        if not hole.any():
            return
    clean = mask & ~fringe
    if int(clean.sum()) < 12:
        crop[hole] = colour
        return
    off = np.sqrt(((lab - ref) ** 2).sum(axis=2))
    flat = float(np.percentile(off[clean], 90)) < FLAT_DE
    if flat and whole:
        crop[hole] = colour  # flat paper: its own colour, as one
        return
    if flat and float((off[clean] >= PAPER_DE).mean()) < FOREIGN_SHARE:
        # a flat ground and nothing else: the lettering and the ground around it, its faint anti-aliasing with it,
        # in the ground's own colour (the ground further off stays as it is)
        crop[mask & (cv2.dilate(ink.astype(np.uint8), _disc(13)) > 0)] = colour
        return
    if whole:
        near = clean & (off < SHADE_DE)  # the paper's shading, not a drawing the mask holds
        surface = paper_surface(crop, near) if int(near.sum()) >= 12 else None
        if surface is None or float(np.percentile(np.sqrt(((_lab(np.clip(surface, 0, 255).astype(np.uint8))[hole]
                                                              - ref) ** 2).sum(axis=1)), 95)) > SHADE_DE:
            crop[hole] = colour  # no shading to follow, or none that stays near the paper: its own colour
        else:
            crop[hole] = np.clip(np.round(surface[hole]), 0, 255).astype(np.uint8)
        return
    paper = clean.astype(np.float32)
    src = crop[..., :3].astype(np.float32) * paper[..., None]
    out = np.empty(crop.shape[:2] + (3,), np.float32)
    out[:] = colour
    todo = hole.copy()
    for sigma in FILL_SIGMAS:
        weight = cv2.GaussianBlur(paper, (0, 0), sigma)
        reached = todo & (weight > 0.02)
        if reached.any():
            total = cv2.GaussianBlur(src, (0, 0), sigma)
            out[reached] = total[reached] / weight[reached][:, None]
            todo &= ~reached
        if not todo.any():
            break
    crop[hole] = np.clip(np.round(out[hole]), 0, 255).astype(np.uint8)


class StrayJudge:
    """What passes for stray lettering (the tests `stray_pieces` and `erase_rings` take).

    A piece of the lettering's own polarity (dark strokes; light ones in a dark bubble) is lettering when it is no
    longer than `GLYPH_REACH` glyphs (*glyph* px each), also as part of what joins up a little past the dark
    threshold (`LINK_LEVELS`): the pieces of a thin outline broken by its anti-aliasing, and of the drawing, are
    longer, and `drawing` (never painted) holds them. A piece of the other polarity, and a thin light ring against
    the drawing's dark, is the ring of an outlined glyph when it encloses strokes and is the ring's colour
    (`RING_DE` of white, black in a dark bubble, or the paper's colour): a piece of a cream ground, of a pale
    drawing or of a window, or the sliver of paper where two lobes of an outline meet, is not. With *rings_interior*
    (a layout model's region, whose mask may stop a few pixels short of its outline) neither is a light piece that
    encloses the mask itself: the bubble's own paper between the mask and its outline, which a small bubble's text
    box takes in whole."""

    def __init__(self, crop: np.ndarray, mask: np.ndarray, glyph: float, paper: tuple[int, int, int],
                 dark_threshold: int = 140, white_threshold: int = 225, dark: bool = False,
                 rings_interior: bool = False):
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        self.interior = mask > 0 if rings_interior else None
        self.lab = _lab(crop)
        self.dark = dark
        self.strokes = gray > white_threshold if dark else gray < dark_threshold
        self.reach = max(12.0, GLYPH_REACH * glyph)
        # a thin line's anti-aliasing breaks it at the dark threshold, not a little above it (a glyph's ring does)
        linked = (gray > white_threshold - LINK_LEVELS) if dark else (gray < dark_threshold + LINK_LEVELS)
        n, labels, stats, _ = cv2.connectedComponentsWithStats((linked & (mask == 0)).astype(np.uint8),
                                                               connectivity=8)
        long = np.zeros(n, bool)
        long[1:] = np.maximum(stats[1:, 2], stats[1:, 3]) > self.reach
        self.drawing = self.strokes & long[labels]
        ring = (0.0 if dark else 100.0, 0.0, 0.0)
        self.colours = (np.array(ring, np.float32), _lab(np.array([[paper]], np.uint8))[0, 0])

    def _ring_coloured(self, pixels: np.ndarray) -> bool:
        if not pixels.any():
            return False
        own = np.median(self.lab[pixels], axis=0)
        return min(float(np.sqrt(((own - ref) ** 2).sum())) for ref in self.colours) < RING_DE

    def piece(self, light: bool, x: int, y: int, w: int, h: int, own: np.ndarray, filled: np.ndarray) -> bool:
        if light == self.dark:  # the strokes' own polarity
            return max(w, h) <= self.reach and not self.drawing[y:y + h, x:x + w][own].any()
        if int((filled & ~own & self.strokes[y:y + h, x:x + w]).sum()) < 4:
            return False  # encloses no strokes: not a glyph's ring
        if self.interior is not None:
            enclosed = filled & ~own
            if int((enclosed & self.interior[y:y + h, x:x + w]).sum()) >= INTERIOR_SHARE * max(1, int(enclosed.sum())):
                return False  # it rings the mask: the bubble's paper round its interior, not a glyph's ring
        whole = np.zeros(self.strokes.shape, bool)
        whole[y:y + h, x:x + w] = own
        return self._ring_coloured(whole)

    def ring(self, ring: np.ndarray) -> bool:
        ys, xs = np.nonzero(ring)
        if not xs.size:
            return False
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        own = ring[y0:y1, x0:x1]
        filled = fill_holes(own.astype(np.uint8) * 255) > 0
        if int((filled & ~own & self.strokes[y0:y1, x0:x1]).sum()) < 4:
            return False  # encloses no strokes: not a glyph's ring
        return self._ring_coloured(ring)


def stray_pieces(gray: np.ndarray, mask: np.ndarray, box: Box, dark_threshold: int = 140,
                 white_threshold: int = 225, min_size: int = 5, max_size: int = 90,
                 accept: PieceTest | None = None) -> list[np.ndarray]:
    """The pieces of lettering that lie outside *mask* but inside the text *box* (crop coordinates), each as a
    boolean mask of the crop: glyph-sized pieces of either polarity (dark strokes, or the light rings of outlined
    glyphs on a dark drawing), each with the holes it encloses, grown to take its outline. Art is larger than a
    glyph or outside the box, so it stays. *accept*, when given, has the last word on each piece."""
    h, w = gray.shape
    x0, y0, x1, y1 = max(0, box[0] - 2), max(0, box[1] - 2), min(w, box[2] + 2), min(h, box[3] + 2)
    if x1 <= x0 or y1 <= y0:
        return []
    outside = mask == 0
    pieces: list[np.ndarray] = []
    for light, ink in ((False, gray < dark_threshold), (True, gray > white_threshold)):  # pieces of the whole crop:
        n, labels, stats, _ = cv2.connectedComponentsWithStats((ink & outside).astype(np.uint8), connectivity=8)
        for i in range(1, n):  # a drawing cut by the box's edge still counts as large
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if max(bw, bh) < min_size or max(bw, bh) > max_size or area < 8:
                continue
            overlap = max(0, min(x + bw, x1) - max(x, x0)) * max(0, min(y + bh, y1) - max(y, y0))
            if overlap < 0.5 * bw * bh:  # mostly outside the text box: not its lettering
                continue
            piece = (labels[y:y + bh, x:x + bw] == i).astype(np.uint8)
            padded = np.pad(piece, 1)
            holes = np.zeros((bh + 4, bw + 4), np.uint8)
            cv2.floodFill(padded, holes, (0, 0), 2)  # what the flood from outside cannot reach is enclosed
            filled = (padded != 2)[1:-1, 1:-1]
            if accept is not None and not accept(light, x, y, bw, bh, piece > 0, filled):
                continue
            full = np.zeros((h, w), np.uint8)
            full[y:y + bh, x:x + bw] = filled
            pieces.append(cv2.dilate(full, _HALO) > 0)
    return pieces


def erase_stray(crop: np.ndarray, mask: np.ndarray, box: Box, dark_threshold: int = 140,
                white_threshold: int = 225, accept: PieceTest | None = None,
                keep: np.ndarray | None = None) -> int:
    """Paint each stray piece of lettering outside *mask* with the colour of the drawing around it (the median
    of a band just beyond the piece, the interior and other pieces left out). Returns how many were painted.
    *accept* is passed on to `stray_pieces`; the pixels of *keep* are never painted."""
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    pieces = stray_pieces(gray, mask, box, dark_threshold, white_threshold, accept=accept)
    if not pieces:
        return 0
    interior = mask > 0
    taken = np.zeros(interior.shape, bool)
    for piece in pieces:
        taken |= piece
    dark = big_dark(gray, dark_threshold)  # the drawing's dark: the hair, the outline
    big = dark.copy()  # with the large light areas: never painted over
    n, labels, stats, _ = cv2.connectedComponentsWithStats((gray > white_threshold).astype(np.uint8), connectivity=8)
    for i in range(1, n):
        if max(int(stats[i][2]), int(stats[i][3])) > 90:
            big |= labels == i
    if keep is not None:
        big |= keep
    painted = 0
    for piece in pieces:
        around = cv2.dilate(piece.astype(np.uint8), _AROUND) > 0
        band = around & ~piece & ~interior & ~taken
        if band.sum() < 12:
            continue
        on_dark = band & dark
        source = on_dark if on_dark.sum() >= 12 else band  # a glyph against the drawing takes the drawing's colour
        colour = np.median(crop[source].reshape(-1, 3), axis=0)
        crop[piece & ~interior & ~big] = colour
        painted += 1
    return painted


def erase_rings(crop: np.ndarray, mask: np.ndarray, box: Box, dark_threshold: int = 140,
                white_threshold: int = 225, accept: Callable[[np.ndarray], bool] | None = None) -> int:
    """Paint the white rings of outlined glyphs that lie against the drawing's dark (over hair, over black) with
    that dark's colour, so the glyphs merge into the drawing. Returns how many rings were painted. *accept*, when
    given, has the last word on each ring (a boolean mask of the crop)."""
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    rings = rings_on_dark(gray, mask, box, dark_threshold, white_threshold)
    if not rings.any():
        return 0
    dark = big_dark(gray, dark_threshold)
    n, labels, _stats, _ = cv2.connectedComponentsWithStats(rings.astype(np.uint8), connectivity=8)
    painted = 0
    for i in range(1, n):
        ring = labels == i
        near = (cv2.dilate(ring.astype(np.uint8), _AROUND) > 0) & dark
        if near.sum() < 12:
            continue
        if accept is not None and not accept(ring):
            continue
        crop[ring] = np.median(crop[near].reshape(-1, 3), axis=0)
        painted += 1
    return painted


def _inpaint(crop: np.ndarray, mask: np.ndarray, dark_threshold: int, dark: bool) -> None:
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    if dark:
        text = ((gray > 255 - dark_threshold - 40) & (mask > 0)).astype(np.uint8) * 255
    else:
        text = ((gray < dark_threshold + 40) & (mask > 0)).astype(np.uint8) * 255
    text = cv2.dilate(text, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    text = cv2.bitwise_and(text, mask)
    if cv2.countNonZero(text):
        crop[:] = cv2.inpaint(np.ascontiguousarray(crop), text, 3, cv2.INPAINT_TELEA)


def _local_box(region: TextRegion) -> Box:
    tb = region.text_box
    return (tb[0] - region.x0, tb[1] - region.y0, tb[2] - region.x0, tb[3] - region.y0)


def erase_region(image: np.ndarray, region: TextRegion, mode: str = "fill", white_threshold: int = 225,
                 dark_threshold: int = 140, dark: bool = False) -> tuple[int, int, int]:
    """Erase the text inside *region* in place, and the lettering that ran past a bubble's interior onto the
    drawing. Returns the background colour used.

    *mode* (``Settings.erase_mode``): "fill" paints the bubble's own paper and "inpaint" inpaints the lettering,
    both within the bubble's outline and with only lettering-like pieces taken for stray lettering (see the
    module's docstring); when the outline cuts the mask back, ``region.mask`` is set to what was erased, so that
    the translation is set inside the bubble too. "classic" is the erase of before, byte for byte: the median of
    the bubble's light pixels over the whole mask, and stray lettering told by light and dark alone."""
    crop = image[region.y0 : region.y1, region.x0 : region.x1]
    mask = region.mask
    if crop.shape[:2] != mask.shape:
        mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
    if mode != "classic":
        return _erase(image, crop, region, mask, mode, white_threshold, dark_threshold, dark)
    bg = bubble_background(crop, mask, white_threshold, dark)
    if region.kind in STRAY_KINDS and region.text_box is not None:
        local = _local_box(region)
        erase_stray(crop, mask, local, dark_threshold, white_threshold)
        if not dark:
            erase_rings(crop, mask, local, dark_threshold, white_threshold)
    crop[mask > 0] = bg
    return bg


def _erase(image: np.ndarray, crop: np.ndarray, region: TextRegion, mask: np.ndarray, mode: str,
           white_threshold: int, dark_threshold: int, dark: bool) -> tuple[int, int, int]:
    """`erase_region` in the modes "fill" and "inpaint" (see the module's docstring)."""
    inside = within_outline(image, region, mask > 0, dark_threshold, dark)
    cut = not np.array_equal(inside, mask > 0)
    bg = paper_colour(crop, inside, dark)
    if region.kind in STRAY_KINDS and region.text_box is not None:
        kept = inside.astype(np.uint8) * 255 if cut else mask
        local = _local_box(region)  # also over what was cut off: the judge keeps the drawing there
        judge = StrayJudge(crop, kept, _glyph(region), bg, dark_threshold, white_threshold, dark, region.from_model)
        erase_stray(crop, kept, local, dark_threshold, white_threshold, accept=judge.piece, keep=judge.drawing)
        if not dark:
            erase_rings(crop, kept, local, dark_threshold, white_threshold, accept=judge.ring)
    if mode == "inpaint":
        _inpaint(crop, inside.astype(np.uint8) * 255, dark_threshold, dark)
    elif region.kind in MANUAL_KINDS:
        crop[inside] = bg  # the reader's own rectangle: wiped, as drawn
    else:
        fill_paper(crop, inside, bg, dark, whole=region.kind not in ON_PAGE_KINDS)
    if cut:
        region.mask = inside.astype(np.uint8) * 255
    return bg
