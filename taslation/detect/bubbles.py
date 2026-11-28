"""Speech-bubble detection with classical computer vision (no model, no network).

Why no neural detector: the strong manga text detectors around are GPL-3.0
(dmMaze/comic-text-detector) or AGPL (Ultralytics), and TASlation stays MIT.
So it finds bubbles the old-fashioned way: a speech bubble (or caption box) is a
closed, bright shape with dark text inside, which is exactly what connected
component analysis is good at. Text drawn directly over artwork (most sound
effects) is out of scope for this detector.

The stage order of the whole pipeline (detect -> OCR -> translate -> erase ->
typeset) follows the same shape as manga-image-translator and
BallonsTranslator (both GPL-3.0; studied for design only, no code reused).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from .. import analysis
from .beyond import lettering_beyond
from .panels import find_panels, order_panels, panel_of
from ..regions import Box, TextRegion


@dataclass
class DetectorConfig:
    white_threshold: int = 225  # bubble interior is at least this bright
    dark_threshold: int = 140  # text strokes are at most this bright
    min_area_ratio: float = 0.0006  # of the image area
    max_area_ratio: float = 0.20
    min_size: int = 24  # px, both sides (at the page's scale: `BubbleDetector.detect`)
    max_aspect: float = 6.0
    min_fill: float = 0.35  # filled bubble area / bounding box area
    min_dark_ratio: float = 0.01  # text (holes) share of the bubble interior
    max_dark_ratio: float = 0.45
    min_text_pixels: int = 24
    outline_erosion: int = 3  # px kept clear of the bubble outline
    tone_min_pieces: int = 12  # a region with this many dark pieces ...
    tone_max_cv: float = 0.3  # ... of nearly equal size is a screentone, not text
    line_max_thickness: int = 6  # px; thinner-and-long pieces are art lines
    min_ink_coverage: float = 0.06  # dark pixels / text box area
    glyph_max_share_of_image: float = 0.04  # a piece taller than this share of the image is not a glyph
    blob_min_solidity: float = 0.72  # a compact piece filling this much of its box is a blob (an eye), not a glyph
    blob_max_pieces: int = 12  # the blob rule applies to regions with few pieces (a face), not to text
    recover_edge_text: bool = True  # also erase lettering that touches the outline (see recover_edge_text)
    take_columns_beyond: bool = False  # dark bubbles: take in a column that goes on past the interior (see beyond.py)
    edge_margin: int = 8  # px around the bubble looked at to tell the outside from the inside
    edge_max_glyph: float = 2.0  # recovered pieces are at most this many glyph sizes long
    split_lobes: bool = True  # bubbles that touch or overlap (one white area): one region per bubble (split_lobes)
    lobe_neck: float = 0.5  # a neck: the white narrows to this share of the shallower block's depth between blocks
    lobe_notch: float = 0.15  # overlapping bubbles: both notches of the junction this deep (share of the area's depth)
    lobe_link: float = 0.6  # pieces within this many glyphs of each other are one block of lettering


Sides = tuple[bool, bool, bool, bool]  # top, bottom, left, right
OPEN: Sides = (False, False, False, False)
GAP_SHARE = 1 / 3  # a closed side closes a gap in the shape along it of at most this share of the shape's reach there


def fill_holes(mask: np.ndarray, closed: Sides = OPEN) -> np.ndarray:
    """Return *mask* (uint8 0/255) with all enclosed holes filled.

    *closed*: the sides of *mask* (top, bottom, left, right) that lie on a boundary of what is looked at - the capture
    area's edge where the frame goes on beyond it (`sides_of`). The area's edge closes a bubble cut by it as the
    bubble's own outline would: where the shape meets such a side, the gaps between its pixels along it (the lettering
    cut with the bubble) are closed, and what they let out becomes a hole - not a gap wider than `GAP_SHARE` of the
    shape's reach along that side (the stretch between two shapes that both meet it)."""
    h, w = mask.shape
    padded = np.zeros((h + 2, w + 2), np.uint8)
    padded[1:-1, 1:-1] = mask
    if not any(closed):
        inv = cv2.bitwise_not(padded)  # outside + holes = 255, shape = 0
        ff_mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(inv, ff_mask, (0, 0), 0)  # outside -> 0, holes stay 255
        return cv2.bitwise_or(mask, inv[1:-1, 1:-1])
    edges = ((padded[1, 1:-1], padded[0, 1:-1]), (padded[-2, 1:-1], padded[-1, 1:-1]),
             (padded[1:-1, 1], padded[1:-1, 0]), (padded[1:-1, -2], padded[1:-1, -1]))
    for (line, pad), on in zip(edges, closed):
        if on:
            pad[_closing(line)] = 255
    inv = (padded == 0).astype(np.uint8)  # outside + holes = 1, shape and the closed sides = 0
    _n, labels = cv2.connectedComponents(inv, connectivity=4)
    border = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    outside = np.isin(labels, np.unique(border[border > 0]))
    holes = (inv > 0) & ~outside
    return cv2.bitwise_or(mask, holes[1:-1, 1:-1].astype(np.uint8) * 255)


def _closing(line: np.ndarray) -> np.ndarray:
    """Where a closed side closes the shape whose pixels along it are *line*'s (`fill_holes`): from its first pixel to
    its last, but for gaps wider than `GAP_SHARE` of that reach."""
    out = np.zeros(line.shape, bool)
    on = np.flatnonzero(line)
    if on.size < 2:
        return out
    out[on] = True
    reach = int(on[-1] - on[0] + 1)
    for a, b in zip(on[:-1], on[1:]):
        if 1 < b - a <= GAP_SHARE * reach + 1:
            out[a + 1:b] = True
    return out


def sides_of(box: tuple[int, int, int, int], bounds: tuple[int, int, int, int] | None,
             frame: tuple[int, int]) -> Sides:
    """The sides of the crop *box* (x0, y0, x1, y1 in the frame) that the capture area *bounds* closes (`fill_holes`):
    those lying on an edge of it that is not the frame's (*frame*: width, height), the frame going on beyond it. None
    for *bounds*: no side."""
    if bounds is None:
        return OPEN
    w, h = frame
    return box[1] == bounds[1] > 0, box[3] == bounds[3] < h, box[0] == bounds[0] > 0, box[2] == bounds[2] < w


def recover_edge_text(gray: np.ndarray, box: tuple[int, int, int, int], filled: np.ndarray, inner: np.ndarray,
                      glyph: float, dark_threshold: int, margin: int = 8, max_glyph: float = 2.0,
                      white_threshold: int = 225, debug: dict | None = None,
                      limit: tuple[int, int, int, int] | None = None, scale: float = 1.0, closed: Sides = OPEN,
                      ) -> tuple[tuple[int, int, int, int], np.ndarray, tuple[int, int, int, int], int] | None:
    """Find the lettering a bubble's white area does not enclose: glyphs that touch the outline.

    The bubble is a white area and its text is the holes in it. A glyph that
    touches the outline (narrow bubbles, columns set close to the curve) is not
    a hole: through its anti-aliasing it joins the outline, and with it the
    outside. It is then left out of the text box and of the erase mask, and
    the Japanese stays on the page next to the translation.

    What tells such a glyph from artwork is where it sits and what it looks
    like. In a window around the bubble, everything that can be reached from
    the window's border without crossing a dark pixel or the bubble's edge is
    outside, and dark pieces touching the outside or the border are the
    outline (with the art joined to it, or the dark page around a dark
    bubble). The bubble's edge is the light-gray band just around its white
    area plus the one-pixel ring the detector's erosion cut it apart with; it
    closes the small gaps a thin anti-aliased outline has at the dark
    threshold. Of the other dark pieces in the same enclosed area as the
    bubble, those that look like the bubble's own lettering (at least a fifth
    of its typical piece's ink and 3 px thick: not a tone dot, not a dash of a
    hairline broken up by anti-aliasing) and lie against the white area are
    taken, then such pieces next to them (the rest of a column), then the
    small marks beside what was taken (dots, dakuten, thin strokes). Where the
    outline is really open, the inside reaches the window's border and the
    bubble is left as it was.

    *box* is the bubble's bounding box (x, y, w, h) in *gray*; *filled* and
    *inner* are its filled area and erase mask in that box; *limit* (x0, y0,
    x1, y1), when given, is where pieces may be taken from (a large white area
    is cut down to its text's neighbourhood: nothing outside it is lettering
    of that text). Returns
    (new box, new erase mask for it, box of the recovered pieces, piece count),
    or None when there is nothing to add. *debug*, when given, receives the
    window's origin, its dark-piece labels, the ids judged outline, inside,
    candidate and taken, and the reason for returning None. The measures in
    pixels (the edge band, the distances, a piece's least ink and thickness,
    the closing) are taken at the page's *scale* (`render.pagescale`); the
    one-pixel rings are not. *closed*: the sides of *gray* that are the capture
    area's edge (`fill_holes`): where the window lies on one, nothing beyond it
    is outside, and a glyph cut by it is no piece of the outline.
    """
    from ..render import pagescale  # (here: the render package imports this module)

    dbg = debug if debug is not None else {}
    x, y, bw, bh = box
    H, W = gray.shape[:2]
    margin = max(margin, int(round(glyph)))  # a glyph against the outline can stick out of the white area's box
    wx0, wy0, wx1, wy1 = max(0, x - margin), max(0, y - margin), min(W, x + bw + margin), min(H, y + bh + margin)
    g = gray[wy0:wy1, wx0:wx1]
    ox, oy = x - wx0, y - wy0  # the bubble's box inside the window
    dark = (g < dark_threshold).astype(np.uint8)
    filled_w = np.zeros(dark.shape, bool)
    filled_w[oy : oy + bh, ox : ox + bw] = filled > 0
    fw8 = filled_w.astype(np.uint8)
    near = cv2.dilate(fw8, pagescale.disc(7, scale)) > 0
    ring = (cv2.dilate(fw8, np.ones((3, 3), np.uint8)) > 0) & ~filled_w
    edge_band = (near & ~filled_w & (g < white_threshold)) | ring  # the bubble's edge: what kept its white area apart
    barrier = (dark > 0) | edge_band
    _n_nd, lab_nd = cv2.connectedComponents((~barrier).astype(np.uint8), connectivity=4)
    shut = (closed[0] and wy0 == 0, closed[1] and wy1 == H, closed[2] and wx0 == 0, closed[3] and wx1 == W)

    def borders(lab: np.ndarray) -> np.ndarray:  # the window's sides that are not the capture area's edge
        lines = [lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]
        return np.concatenate([line for line, off in zip(lines, shut) if not off] or [lab[:0, 0]])

    edge = borders(lab_nd)
    edge = edge[edge > 0]
    outside = np.isin(lab_nd, np.unique(edge)) if edge.size else np.zeros(dark.shape, bool)
    _n_d, lab_d, st_d, _ = cv2.connectedComponentsWithStats(dark, connectivity=8, ltype=cv2.CV_32S)
    touching = cv2.dilate(outside.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    on_border = borders(lab_d)
    rim_ids = np.union1d(np.unique(lab_d[touching & (dark > 0)]), np.unique(on_border))
    rim = np.isin(lab_d, rim_ids[rim_ids > 0])
    dbg.update(origin=(wx0, wy0), labels=lab_d, rim=set(int(v) for v in rim_ids if v > 0), result="")
    enclosed = (~(outside | rim)).astype(np.uint8)
    _n_e, lab_e = cv2.connectedComponents(enclosed, connectivity=4)
    ids, counts = np.unique(lab_e[filled_w & (enclosed > 0)], return_counts=True)
    keep = ids > 0
    ids, counts = ids[keep], counts[keep]
    if not ids.size or counts.max() < 0.5 * int(filled_w.sum()):
        dbg["result"] = "open outline"
        return None  # the outline is open (or not dark): no inside to speak of
    inside = lab_e == ids[np.argmax(counts)]
    dbg["inside"] = set(int(v) for v in np.unique(lab_d[inside & (dark > 0)]) if v > 0)
    if borders(inside).any():
        dbg["result"] = "inside reaches the border"
        return None  # the inside reaches the window's border: nothing encloses it
    inner_w = np.zeros(dark.shape, bool)
    inner_w[oy : oy + bh, ox : ox + bw] = inner > 0
    candidates: list[int] = []
    for j in np.unique(lab_d[inside & (dark > 0)]):
        if j == 0:
            continue
        px, py, pw, ph, area = (int(v) for v in st_d[j])
        if max(pw, ph) > max_glyph * glyph or area < 3:
            continue
        piece = lab_d[py : py + ph, px : px + pw] == j
        if inner_w[py : py + ph, px : px + pw][piece].all():
            continue  # a hole of the white area: already erased
        if limit is not None and not (limit[0] <= wx0 + px + pw / 2.0 < limit[2]
                                      and limit[1] <= wy0 + py + ph / 2.0 < limit[3]):
            continue  # outside the neighbourhood the area is cut down to
        candidates.append(int(j))
    # Lettering against the outline lines the white area: take glyph-like pieces within a few pixels of it, then
    # glyph-like pieces next to those (a column whose glyphs follow one another), then the small parts of what was
    # taken (dots, dakuten, thin strokes); never something across a stretch of other ground.
    def nearest(src: np.ndarray, j: int) -> float:  # distance from piece j to the nearest pixel of *src*
        px, py, pw, ph, _area = (int(v) for v in st_d[j])
        piece = lab_d[py : py + ph, px : px + pw] == j
        return float(src[py : py + ph, px : px + pw][piece].min())

    n_t, _l_t, st_t, _ = cv2.connectedComponentsWithStats(((dark > 0) & inner_w).astype(np.uint8), connectivity=8)
    least_ink, thick, against = pagescale.area(6.0, scale), pagescale.px(3, scale), 4.0 * scale
    seed_area = max(least_ink, 0.2 * float(np.median(st_t[1:, cv2.CC_STAT_AREA]))) if n_t > 1 else least_ink

    def glyph_like(j: int) -> bool:  # a glyph or a good part of one: not a tone dot, not a hairline's dash
        return int(st_d[j][4]) >= seed_area and min(int(st_d[j][2]), int(st_d[j][3])) >= thick

    to_white = cv2.distanceTransform((~filled_w).astype(np.uint8), cv2.DIST_L2, 3)
    accepted = [j for j in candidates if glyph_like(j) and nearest(to_white, j) <= against]
    step = max(against, 0.5 * glyph)
    for _ in range(3):
        rest = [j for j in candidates if j not in accepted and glyph_like(j) and nearest(to_white, j) <= 2.0 * glyph]
        if not accepted or not rest:
            break
        to_taken = cv2.distanceTransform((~np.isin(lab_d, accepted)).astype(np.uint8), cv2.DIST_L2, 3)
        taken = [j for j in rest if nearest(to_taken, j) <= step]
        if not taken:
            break
        accepted.extend(taken)
    if accepted:
        to_taken = cv2.distanceTransform((~np.isin(lab_d, accepted)).astype(np.uint8), cv2.DIST_L2, 3)
        beside = max(against, 0.35 * glyph)
        accepted += [j for j in candidates if j not in accepted and nearest(to_taken, j) <= beside]
    dbg.update(candidates=set(candidates), accepted=set(accepted), too_big={
        int(j) for j in dbg["inside"] if max(int(st_d[j][2]), int(st_d[j][3])) > max_glyph * glyph})
    if not accepted:
        dbg["result"] = "nothing next to the white area"
        return None
    acc = np.isin(lab_d, accepted)
    add = (cv2.dilate(acc.astype(np.uint8), pagescale.disc(5, scale)) > 0) & inside
    mask = inner_w | add
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, pagescale.disc(7, scale)) > 0
    mask = mask | (closed & inside)  # no slivers between the old mask and the recovered glyphs
    ys, xs = np.nonzero(mask)
    nx0, ny0 = min(int(xs.min()), ox), min(int(ys.min()), oy)
    nx1, ny1 = max(int(xs.max()) + 1, ox + bw), max(int(ys.max()) + 1, oy + bh)
    new_mask = mask[ny0:ny1, nx0:nx1].astype(np.uint8) * 255
    ays, axs = np.nonzero(acc)
    rec_box = (wx0 + int(axs.min()), wy0 + int(ays.min()), wx0 + int(axs.max()) + 1, wy0 + int(ays.max()) + 1)
    return (wx0 + nx0, wy0 + ny0, nx1 - nx0, ny1 - ny0), np.ascontiguousarray(new_mask), rec_box, len(accepted)


class BubbleDetector:
    def __init__(self, config: DetectorConfig | None = None):
        self.cfg = config or DetectorConfig()

    @analysis.timed("bubbles")
    def detect(self, rgb: np.ndarray, inverted: bool = False, scale: float = 1.0,
               closed: Sides = OPEN) -> list[TextRegion]:
        """Find bubbles in an RGB uint8 image. Returned regions are not yet ordered.

        With ``inverted=True`` the image is negated first, which finds dark
        bubbles with light lettering (regions come back with kind "dark-bubble").
        *scale* is the page's (`render.pagescale.page_scale`): the measures in
        pixels set on the sample set's pages are taken at it (1: as set).
        *closed*: the sides of the image (top, bottom, left, right) that are the
        capture area's edge, the frame going on beyond (`fill_holes`): a bubble
        cut by one is closed by it, its lettering up to it.
        """
        from ..render import pagescale  # (here: the render package imports this module)

        cfg = self.cfg
        if rgb.ndim == 3:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        else:
            gray = rgb
        if inverted:
            gray = 255 - gray
        kind = "dark-bubble" if inverted else "bubble"
        h, w = gray.shape
        img_area = float(h * w)
        min_size = pagescale.px(cfg.min_size, scale)
        min_area = max(min_size * min_size, cfg.min_area_ratio * img_area)
        max_area = cfg.max_area_ratio * img_area

        white = (gray >= cfg.white_threshold).astype(np.uint8) * 255
        # A one pixel erosion breaks weak links through anti-aliased outlines.
        white = cv2.erode(white, np.ones((3, 3), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=4, ltype=cv2.CV_32S)

        erode_kernel = pagescale.disc(2 * cfg.outline_erosion + 1, scale)
        least_ink = pagescale.area(cfg.min_text_pixels, scale)
        regions: list[TextRegion] = []
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if area < min_area or area > max_area:
                continue
            if bw < min_size or bh < min_size:
                continue
            aspect = bw / bh
            if aspect > cfg.max_aspect or aspect < 1.0 / cfg.max_aspect:
                continue

            comp = (labels[y : y + bh, x : x + bw] == i).astype(np.uint8) * 255
            sides = (closed[0] and y == 0, closed[1] and y + bh == h, closed[2] and x == 0, closed[3] and x + bw == w)
            filled = fill_holes(comp, sides)
            filled_area = int(cv2.countNonZero(filled))
            if filled_area / float(bw * bh) < cfg.min_fill:
                continue
            hole_ratio = (filled_area - area) / float(filled_area)
            if hole_ratio < cfg.min_dark_ratio or hole_ratio > cfg.max_dark_ratio:
                continue

            inner = cv2.erode(filled, erode_kernel)
            gray_crop = gray[y : y + bh, x : x + bw]
            dark = ((gray_crop < cfg.dark_threshold) & (inner > 0)).astype(np.uint8)
            if int(dark.sum()) < least_ink:
                continue
            # bubbles that touch or overlap: one region each (white bubbles only: the black areas of a page join up
            # into shapes of every kind, and a dark bubble's lettering split that way loses its columns)
            parts = (split_lobes(filled, inner, dark, cfg.lobe_neck, cfg.lobe_notch, cfg.lobe_link)
                     if cfg.split_lobes and not inverted else None)
            whole = None
            if parts:
                found = [self._region(gray, (x + px, y + py, pw_, ph_), p_filled, p_inner, p_dark, kind, scale,
                                      closed) for px, py, pw_, ph_, p_filled, p_inner, p_dark in parts]
                if any(r is None for r in found):
                    # a bubble's lettering would not pass on its own (a line of dots, two glyphs): read the area
                    # whole, as before, rather than lose that line; when the whole does not pass either, the parts
                    # that do are kept
                    whole = self._region(gray, (x, y, bw, bh), filled, inner, dark, kind, scale, closed)
                regions.extend([whole] if whole is not None else [r for r in found if r is not None])
            else:
                whole = self._region(gray, (x, y, bw, bh), filled, inner, dark, kind, scale, closed)
                if whole is not None:
                    regions.append(whole)
        if inverted and cfg.recover_edge_text and cfg.take_columns_beyond:
            take_columns_beyond(gray, regions, cfg.dark_threshold, scale)
        return regions

    def _region(self, gray: np.ndarray, box: tuple[int, int, int, int], filled: np.ndarray, inner: np.ndarray,
                dark: np.ndarray, kind: str, scale: float = 1.0, closed: Sides = OPEN) -> TextRegion | None:
        """The text region of one white area (*box* x, y, w, h in *gray*; its filled shape, erase mask and dark
        pixels inside, in that box), or None when what is inside it is a drawing rather than lettering. Measures in
        px at the page's *scale*; *closed*: the sides of *gray* that are the capture area's edge (`detect`)."""
        from ..render import pagescale  # (here: the render package imports this module)

        cfg = self.cfg
        x, y, bw, bh = box
        h = gray.shape[0]
        dark_count = int(dark.sum())
        if dark_count < pagescale.area(cfg.min_text_pixels, scale):
            return None
        # Text is many small pieces; artwork tends to be one big connected stroke.
        n_d, _, st_d, _ = cv2.connectedComponentsWithStats(dark, connectivity=8, ltype=cv2.CV_32S)
        if n_d <= 2:
            return None  # a single dark blob is a drawing, not text (even "!" has two pieces)
        pieces = st_d[1:, cv2.CC_STAT_AREA].astype(np.float64)
        largest = int(pieces.argmax())
        largest_dim = max(int(st_d[1 + largest, cv2.CC_STAT_WIDTH]), int(st_d[1 + largest, cv2.CC_STAT_HEIGHT]))
        if pieces.max() > 0.6 * pieces.sum() and largest_dim > cfg.glyph_max_share_of_image * h:
            return None  # one big blob dominates: a drawing, not a one-character bubble
        if np.median(st_d[1:, cv2.CC_STAT_HEIGHT]) > 0.5 * bh or np.median(st_d[1:, cv2.CC_STAT_WIDTH]) > 0.5 * bw:
            return None
        # Screentone: dozens of near-identical dots. Glyph strokes vary a lot in size.
        if len(pieces) >= cfg.tone_min_pieces and pieces.std() / max(pieces.mean(), 1e-6) < cfg.tone_max_cv:
            return None
        # Fragments of thin art lines (very thin and long) are not glyphs.
        pw = st_d[1:, cv2.CC_STAT_WIDTH].astype(np.float64)
        ph = st_d[1:, cv2.CC_STAT_HEIGHT].astype(np.float64)
        thin = pagescale.px(cfg.line_max_thickness, scale)
        line_like = (np.minimum(pw, ph) <= thin) & (np.maximum(pw, ph) >= 4 * np.minimum(pw, ph))
        if pieces[line_like].sum() > 0.7 * pieces.sum():
            return None
        # Eyes, dots and blush marks are solid blobs; glyphs are strokes that fill little of their box.
        compact = (np.minimum(pw, ph) >= pagescale.px(4, scale)) & (np.maximum(pw, ph) < 3 * np.minimum(pw, ph))
        solidity = pieces / np.maximum(pw * ph, 1.0)
        blobs = compact & (solidity >= cfg.blob_min_solidity)
        if len(pieces) <= cfg.blob_max_pieces and pieces[blobs].sum() > 0.5 * pieces.sum():
            return None

        ys, xs = np.nonzero(dark)
        tx0, ty0, tx1, ty1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        if dark_count / float((tx1 - tx0) * (ty1 - ty0)) < cfg.min_ink_coverage:
            return None  # a few specks spread over a large area, not a block of text
        text_box = (x + tx0, y + ty0, x + tx1, y + ty1)
        core_box, extra = None, 0
        n_pieces = int(n_d - 1)
        glyph = max(8.0 * scale, float(np.percentile(np.maximum(pw, ph), 90)))
        if cfg.recover_edge_text:
            found = recover_edge_text(gray, (x, y, bw, bh), filled, inner, glyph, cfg.dark_threshold,
                                      pagescale.px(cfg.edge_margin, scale), cfg.edge_max_glyph, cfg.white_threshold,
                                      limit=focus_window(text_box, (x, y, x + bw, y + bh)), scale=scale,
                                      closed=closed)
            if found is not None:
                (x, y, bw, bh), inner, rb, extra = found
                core_box = text_box
                text_box = (min(text_box[0], rb[0]), min(text_box[1], rb[1]), max(text_box[2], rb[2]),
                            max(text_box[3], rb[3]))
                n_pieces += extra
        return TextRegion(x0=x, y0=y, x1=x + bw, y1=y + bh, mask=inner, text_box=text_box, kind=kind,
                          pieces=n_pieces, core_box=core_box, edge_pieces=extra, glyph=glyph)


def _piece_groups(stats: np.ndarray, link: float) -> list[list[int]]:
    """Pieces (rows of connectedComponentsWithStats without the background row) whose boxes come within *link*
    pixels of each other, chained: the blocks of lettering, as lists of row indices."""
    n = len(stats)
    x0, y0 = stats[:, 0].astype(np.float64), stats[:, 1].astype(np.float64)
    x1, y1 = x0 + stats[:, 2], y0 + stats[:, 3]
    gx = np.maximum(0.0, np.maximum(x0[:, None], x0[None, :]) - np.minimum(x1[:, None], x1[None, :]))
    gy = np.maximum(0.0, np.maximum(y0[:, None], y0[None, :]) - np.minimum(y1[:, None], y1[None, :]))
    near = np.maximum(gx, gy) <= link
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in zip(*np.nonzero(np.triu(near, 1))):
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[rb] = ra
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


Part = tuple[int, int, int, int, np.ndarray, np.ndarray, np.ndarray]  # x, y, w, h, filled, inner, dark


def _blocks(dark: np.ndarray, link: float) -> tuple[list[list[int]], np.ndarray, np.ndarray, float]:
    """The blocks of lettering among the dark pieces: chains of pieces within *link* glyphs of one another holding
    at least a glyph's worth of ink (specks and dots alone are no block). Returns (blocks as lists of piece rows,
    the piece labels, the piece stats without the background row, the glyph size)."""
    n_d, labels, st_d, _ = cv2.connectedComponentsWithStats(dark, connectivity=8, ltype=cv2.CV_32S)
    stats = st_d[1:]
    if n_d <= 3:
        return [], labels, stats, 0.0
    glyph = max(8.0, float(np.percentile(np.maximum(stats[:, 2], stats[:, 3]), 90)))
    blocks = [g for g in _piece_groups(stats, link * glyph)
              if float(stats[g, cv2.CC_STAT_AREA].sum()) >= 0.25 * glyph * glyph]
    return blocks, labels, stats, glyph


def _block_box(stats: np.ndarray, block: list[int]) -> tuple[int, int, int, int]:
    return (int(stats[block, 0].min()), int(stats[block, 1].min()), int((stats[block, 0] + stats[block, 2]).max()),
            int((stats[block, 1] + stats[block, 3]).max()))


def _neck_owner(inside: np.ndarray, depth: np.ndarray, blocks: list[list[int]], stats: np.ndarray,
                neck: float) -> np.ndarray | None:
    """Which lobe every pixel of the area belongs to (-1 outside it) when its blocks lie in lobes joined by a
    neck, else None. Two blocks share a lobe when a path joins them that never comes nearer the outline than
    *neck* times the depth of the shallower one (the largest distance from the outline within its box)."""
    points: list[tuple[int, int]] = []
    radii: list[float] = []
    for block in blocks:
        bx0, by0, bx1, by1 = _block_box(stats, block)
        sub = depth[by0:by1, bx0:bx1]
        py, px = divmod(int(np.argmax(sub)), sub.shape[1])
        points.append((bx0 + px, by0 + py))
        radii.append(float(sub.max()))
    parent = list(range(len(blocks)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    order = sorted(range(len(blocks)), key=lambda i: radii[i])
    for pos, a in enumerate(order):
        if radii[a] <= 0:
            continue
        _n, lobe = cv2.connectedComponents((depth >= neck * radii[a]).astype(np.uint8), connectivity=8)
        ax, ay = points[a]
        for b in order[pos + 1:]:
            bx, by = points[b]
            if lobe[ay, ax] and lobe[ay, ax] == lobe[by, bx]:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    lobes: dict[int, list[int]] = {}
    for i in range(len(blocks)):
        lobes.setdefault(find(i), []).append(i)
    if len(lobes) < 2:
        return None
    # every lobe's core is the deep part around its blocks; each pixel of the area goes to the nearest core
    cores = []
    for members in lobes.values():
        _n, deep = cv2.connectedComponents((depth >= neck * min(radii[i] for i in members)).astype(np.uint8),
                                           connectivity=8)
        ids = {int(deep[points[i][1], points[i][0]]) for i in members} - {0}
        if not ids:
            return None
        cores.append(np.isin(deep, list(ids)))
    for a in range(len(cores)):
        for b in range(a + 1, len(cores)):
            if (cores[a] & cores[b]).any():
                return None  # the lobes' cores meet: no clean cut between them
    dist = np.stack([cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 5) for core in cores])
    return np.where(inside, np.argmin(dist, axis=0), -1)


def _notch_owner(inside: np.ndarray, depth: np.ndarray, dark: np.ndarray, blocks: list[list[int]],
                 labels: np.ndarray, notch: float, dominance: float = 0.5) -> np.ndarray | None:
    """Which bubble every pixel of the area belongs to (0 or 1, -1 outside it) when the area is two bubbles that
    overlap, else None. Where two bubbles overlap and the outline between them is left out, the outline turns
    sharply inward on both sides of the junction: two notches, each deeper than *notch* times the area's depth
    (the largest distance from the outline). When they are much deeper than any other bend (every other one at
    most *dominance* times the shallower notch), the cut is the straight line between them, when it runs across
    the white, crosses no lettering and leaves blocks on both sides (the base of a tail leaves none on its side).
    Else (a tail's base as deep as the junction's notches, or two bubbles fused so wide that their texts sit offset
    and the line clips one of them) the cut runs between the texts (`_between_texts`) from one deep notch to
    another; an outline with more than `NOTCH_BENDS` deep bends (a cloud, a spiky shout) is never cut there, as
    its bends say nothing about bubbles."""
    R = float(depth.max())
    if R <= 0:
        return None
    contours, _ = cv2.findContours(inside.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if len(contour) < 8:
        return None
    try:
        defects = cv2.convexityDefects(contour, cv2.convexHull(contour, returnPoints=False))
    except cv2.error:
        return None  # a self-touching outline
    if defects is None:
        return None
    found = sorted(((float(d[3]) / 256.0, tuple(int(v) for v in contour[int(d[2])][0]))
                    for d in np.asarray(defects).reshape(-1, 4)), reverse=True)
    if len(found) < 2 or found[1][0] < notch * R:
        return None
    if len(blocks) >= 2 and (len(found) == 2 or found[2][0] <= dominance * found[1][0]):
        owner = _straight_cut(inside, dark, blocks, labels, found[0][1], found[1][1])
        if owner is not None:
            return owner
    deep = [p for d, p in found if d >= notch * R]
    if len(deep) > NOTCH_BENDS:
        return None  # a cloud, a spiky outline
    for a in range(len(deep)):
        for b in range(a + 1, len(deep)):
            owner = _between_texts(inside, dark, blocks, deep[a], deep[b], R)
            if owner is not None:
                return owner
    return None


def _straight_cut(inside: np.ndarray, dark: np.ndarray, blocks: list[list[int]], labels: np.ndarray,
                  pa: tuple[int, int], pb: tuple[int, int]) -> np.ndarray | None:
    """`_notch_owner`'s straight cut from notch *pa* to notch *pb*, or None when the line leaves the white, runs
    through lettering, or leaves blocks on one side only."""
    n = int(np.hypot(pa[0] - pb[0], pa[1] - pb[1])) + 1
    xs = np.round(np.linspace(pa[0], pb[0], n)).astype(int)
    ys = np.round(np.linspace(pa[1], pb[1], n)).astype(int)
    if inside[ys, xs].mean() < 0.9:
        return None  # the line leaves the white
    if int((dark[ys, xs] > 0).sum()) > 2:
        return None  # the line runs through lettering
    cut = inside.astype(np.uint8)
    cv2.line(cut, pa, pb, 0, 3)
    _n, sides = cv2.connectedComponents(cut, connectivity=4)
    owners = []
    for block in blocks:
        ids, counts = np.unique(sides[np.isin(labels, [i + 1 for i in block]) & (cut > 0)], return_counts=True)
        keep = ids > 0
        if not keep.any():
            return None
        owners.append(int(ids[keep][np.argmax(counts[keep])]))
    if len(set(owners)) != 2:
        return None  # blocks on one side only (a tail cut off), or on more than two
    dist = np.stack([cv2.distanceTransform((sides != side).astype(np.uint8), cv2.DIST_L2, 5)
                     for side in sorted(set(owners))])
    return np.where(inside, np.argmin(dist, axis=0), -1)


NOTCH_BENDS = 4  # deep bends of joined bubbles' outline: the junction's two notches and the two at a tail's base
NOTCH_REACH = 0.5  # of the area's depth: a cut between two texts passes this near both notches of the junction
LINE_ACROSS = 1 / 3  # a line of lettering with this share of its ink on the far side of the junction crosses it
WAIST = 0.9  # a junction is at most this share of each bubble's reach along it


def _between_texts(inside: np.ndarray, dark: np.ndarray, blocks: list[list[int]], pa: tuple[int, int],
                   pb: tuple[int, int], depth: float) -> np.ndarray | None:
    """Which bubble every pixel belongs to (0 or 1, -1 outside the area) when *pa* and *pb* are the two notches of
    a junction between two bubbles whose texts the straight line between the notches does not keep apart: two
    bubbles fused wide whose texts are offset (one lobe's text above and beside the other's, the line clipping a
    corner of one), two texts set so close that they chain up into one block of lettering.

    The texts fall on either side of the line: a block of lettering (`_blocks`) on the side that holds most of its
    ink; a single block line by line (its columns or rows, `textblocks.letter_lines`), and when a line has
    `LINE_ACROSS` of its ink or more on the far side, it is one text that runs across the junction and nothing is
    cut. Each side must hold lettering (the base of a tail holds none). Every pixel then goes to the side whose
    lettering is nearer, so that the cut runs through the white between the texts. It must be a junction: it passes
    within `NOTCH_REACH` of the area's *depth* of both notches, and the notches are nearer each other than `WAIST`
    times each part's reach along the line between them (one bubble's two halves reach no further along the cut
    than the cut itself). None when any of this fails."""
    from .textblocks import letter_lines  # (textblocks imports this module)

    n, lab, stats, cents = cv2.connectedComponentsWithStats(dark, connectivity=8, ltype=cv2.CV_32S)
    if n <= 3:
        return None
    stats, cents = stats[1:], cents[1:]
    ink = stats[:, cv2.CC_STAT_AREA].astype(np.float64)
    glyph = max(8.0, float(np.percentile(np.maximum(stats[:, 2], stats[:, 3]), 90)))
    (ax, ay), (bx, by) = pa, pb
    side = ((bx - ax) * (cents[:, 1] - ay) - (by - ay) * (cents[:, 0] - ax)) > 0  # per piece: which side of the line

    def lean(members: list[int]) -> float:  # the share of their ink on the line's positive side
        return float(ink[members][side[members]].sum()) / max(1.0, float(ink[members].sum()))

    groups: list[list[int]] = [[], []]
    if len(blocks) >= 2:
        for block in blocks:
            groups[0 if lean(block) >= 0.5 else 1].extend(block)
    elif blocks:
        block = blocks[0]
        boxes = [(int(stats[i, 0]), int(stats[i, 1]), int(stats[i, 0] + stats[i, 2]), int(stats[i, 1] + stats[i, 3]))
                 for i in block]
        lines, _vertical = letter_lines(boxes, glyph)
        if not lines:
            return None
        spans: list[list[tuple[int, int, int, int]]] = [[], []]
        for line in lines:
            members = [block[i] for i in line]
            share = lean(members)
            if LINE_ACROSS <= share <= 1.0 - LINE_ACROSS:
                return None  # a line of lettering runs across the junction: one text
            groups[0 if share > 0.5 else 1].extend(members)
            spans[0 if share > 0.5 else 1].append((min(boxes[i][0] for i in line), min(boxes[i][1] for i in line),
                                                   max(boxes[i][2] for i in line), max(boxes[i][3] for i in line)))
        if not _apart(spans, glyph):
            return None  # the lines on the two sides are set as one text's (a caption's step): one text
    if not groups[0] or not groups[1] or min(float(ink[g].sum()) for g in groups) < 0.25 * glyph * glyph:
        return None  # lettering on one side only (a tail's base), or a speck on the other
    near = []
    for group in groups:
        own = np.isin(lab, np.asarray(group) + 1)
        near.append(cv2.distanceTransform((~own).astype(np.uint8), cv2.DIST_L2, 5))
    owner = np.where(inside, (near[1] < near[0]).astype(np.int64), -1)
    edge = np.zeros(inside.shape, bool)
    edge[:, 1:] |= (owner[:, 1:] != owner[:, :-1]) & inside[:, 1:] & inside[:, :-1]
    edge[1:, :] |= (owner[1:, :] != owner[:-1, :]) & inside[1:, :] & inside[:-1, :]
    if not edge.any():
        return None
    to_edge = cv2.distanceTransform((~edge).astype(np.uint8), cv2.DIST_L2, 5)
    if max(float(to_edge[ay, ax]), float(to_edge[by, bx])) > NOTCH_REACH * depth:
        return None  # the cut between the texts leaves the junction: it would cut across a bubble
    if _waist_share(owner, pa, pb) > WAIST:
        return None  # no narrowing: one bubble's two halves
    return owner


LINES_APART = 2.0  # two texts' lines lie this many times further apart than the lines within each text, at least


def _apart(spans: list[list[tuple[int, int, int, int]]], glyph: float) -> bool:
    """Whether the lines of lettering *spans* (two groups of line boxes) are set as two texts: the nearest two lines
    of different groups at least `LINES_APART` times as far apart as neighbouring lines within a group are (and half
    a glyph at least), so that two columns set at a text's own spacing on either side of a junction are one text."""

    def gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        return float(max(0, max(a[0], b[0]) - min(a[2], b[2]), max(a[1], b[1]) - min(a[3], b[3])))

    if not spans[0] or not spans[1]:
        return False
    between = min(gap(a, b) for a in spans[0] for b in spans[1])
    within = [min(gap(a, b) for b in group if b is not a) for group in spans if len(group) >= 2 for a in group]
    spacing = float(np.median(within)) if within else 0.0
    return between >= max(LINES_APART * spacing, 0.5 * glyph)


def _waist_share(owner: np.ndarray, pa: tuple[int, int], pb: tuple[int, int]) -> float:
    """The length of the junction from *pa* to *pb* over the shorter reach of the two parts of *owner* (0 and 1)
    along it (the extent of each part's pixels on the line through the notches)."""
    (ax, ay), (bx, by) = pa, pb
    length = float(np.hypot(bx - ax, by - ay))
    if length <= 0:
        return 1.0
    ux, uy = (bx - ax) / length, (by - ay) / length
    reach = []
    for li in (0, 1):
        ys, xs = np.nonzero(owner == li)
        if xs.size == 0:
            return 1.0
        along = xs * ux + ys * uy
        reach.append(float(along.max() - along.min()) + 1.0)
    return length / min(reach)


def _solidity(part: np.ndarray) -> float:
    """Area of a shape over the area of its convex hull (1 for a convex shape)."""
    contours, _ = cv2.findContours(part.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    hull = cv2.contourArea(cv2.convexHull(np.vstack(contours)))
    return float(np.count_nonzero(part)) / hull if hull > 0 else 0.0


def split_lobes(filled: np.ndarray, inner: np.ndarray, dark: np.ndarray, neck: float = 0.5, notch: float = 0.15,
                link: float = 0.6, rounds: int = 2, drawing: float = 0.2, convex: float = 0.85) -> list[Part] | None:
    """Cut a white area made of several bubbles that touch or overlap into one part per bubble.

    Bubbles drawn touching or overlapping often share one white area: the outline between them is left out, or
    broken where they meet. Their lines are two texts (one speaker going on, or two speakers), each set in its own
    bubble; read as one region they are translated as one line and lettered across both. What tells them from
    one bubble holding two blocks of lettering is the shape between the blocks. Inside one bubble the white is
    as wide between the blocks as around them and the outline bends outward all round; between two bubbles the
    white narrows to a neck (see _neck_owner) or, where they overlap, the outline turns sharply inward on both
    sides of the junction (see _notch_owner). A block is a chain of dark pieces within *link* glyphs of one
    another holding at least a glyph's worth of ink; specks go with the part they fall in. Two texts set close
    enough to chain into one block are told apart at the notches by their lines (_between_texts): two groups of
    lines, one on each side of the junction, set further apart than the lines within each. A part is cut again,
    up to *rounds* times in all (three bubbles in a row). Only bubbles are cut apart: when more than *drawing* of
    the area's ink lies in strokes far longer than a glyph, or a part would not be convex (its area under *convex*
    times its convex hull's, where a bubble's is nearly all of it), the area is a stretch of page or of the drawing,
    whose bends say nothing about bubbles; its text is left to the cut-down of focus_oversized and to the text
    blocks.

    *filled* is the area's filled shape, *inner* its erase mask and *dark* the dark pixels inside that, all in
    its box. Returns one (x, y, w, h, filled, inner, dark) per bubble holding lettering (the part's offset and size
    in the area's box and the three arrays cut to it; the erase mask keeps its erosion along the outline, none
    along the cut), or None when the area is one bubble."""
    blocks, labels, stats, glyph = _blocks(dark, link)
    if not blocks:
        return None
    ink = stats[:, cv2.CC_STAT_AREA].astype(np.float64)
    if ink[np.maximum(stats[:, 2], stats[:, 3]) > 2.5 * glyph].sum() > drawing * ink.sum():
        return None  # strokes far longer than a glyph: a drawing on a stretch of white page, not bubbles
    inside = filled > 0
    depth = cv2.distanceTransform(np.pad(inside.astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]  # box edge: outline
    owner = _neck_owner(inside, depth, blocks, stats, neck) if len(blocks) >= 2 else None
    if owner is None:
        owner = _notch_owner(inside, depth, dark, blocks, labels, notch)
    if owner is None:
        return None
    out: list[Part] = []
    for li in range(int(owner.max()) + 1):
        part = owner == li
        ys, xs = np.nonzero(part)
        if xs.size == 0:
            continue
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        cut = part[y0:y1, x0:x1]
        p_dark = ((dark[y0:y1, x0:x1] > 0) & cut).astype(np.uint8)
        if not p_dark.any():
            continue
        p_filled = cut.astype(np.uint8) * 255
        p_inner = np.where(cut, inner[y0:y1, x0:x1], 0).astype(np.uint8)  # the cut between the parts is no outline
        again = (split_lobes(p_filled, p_inner, p_dark, neck, notch, link, rounds - 1, drawing, convex)
                 if rounds > 1 else None)
        if again is None:
            if _solidity(cut) < convex:
                return None  # not a bubble: the area is a stretch of page or of the drawing
            out.append((x0, y0, x1 - x0, y1 - y0, p_filled, p_inner, p_dark))
        else:
            out.extend((x0 + px, y0 + py, pw, ph, f, i, d) for px, py, pw, ph, f, i, d in again)
    return out if len(out) >= 2 else None


def take_columns_beyond(gray: np.ndarray, regions: list[TextRegion], dark_threshold: int,
                        scale: float = 1.0) -> int:
    """Dark bubbles whose lettering goes on past the interior on the bubble's own black (a badly closed blob): the
    text box, the region and the erase mask grow over such a column, which is read with the bubble and judged
    without it; a column inside another bubble is never taken. Returns how many regions grew. Measures in px at the
    page's *scale*."""
    h, w = gray.shape[:2]
    union = np.zeros((h, w), bool)
    for r in regions:
        union[r.y0:r.y1, r.x0:r.x1] |= r.mask > 0
    grew = 0
    for r in regions:
        if not r.glyph:
            continue
        own = np.zeros((h, w), bool)
        own[r.y0:r.y1, r.x0:r.x1] = r.mask > 0
        beyond, more, pieces = lettering_beyond(gray, (r.x0, r.y0, r.width, r.height), r.mask, r.text_box, r.glyph,
                                                dark_threshold, exclude=union & ~own, scale=scale)
        if not more:
            continue
        r.before_beyond = ((r.x0, r.y0, r.x1, r.y1), r.text_box, r.mask, more)
        r.core_box = r.core_box or r.text_box
        r.text_box = beyond
        r.pieces += more
        r.edge_pieces += more
        gx0, gy0 = max(0, min(r.x0, beyond[0] - 4)), max(0, min(r.y0, beyond[1] - 4))
        gx1, gy1 = min(w, max(r.x1, beyond[2] + 4)), min(h, max(r.y1, beyond[3] + 4))
        grown = np.zeros((gy1 - gy0, gx1 - gx0), np.uint8)
        grown[r.y0 - gy0:r.y1 - gy0, r.x0 - gx0:r.x1 - gx0] = r.mask
        cx0, cy0 = max(gx0, min(b[0] for b in pieces) - 4), max(gy0, min(b[1] for b in pieces) - 4)
        cx1, cy1 = min(gx1, max(b[2] for b in pieces) + 4), min(gy1, max(b[3] for b in pieces) + 4)
        grown[cy0 - gy0:cy1 - gy0, cx0 - gx0:cx1 - gx0] = 255  # the column: its glyphs and the ground under them
        r.beyond_box = (cx0, cy0, cx1, cy1)
        r.x0, r.y0, r.x1, r.y1, r.mask = gx0, gy0, gx1, gy1, grown
        union[gy0:gy1, gx0:gx1] |= grown > 0
        grew += 1
    return grew


FOCUS_MARGIN = 1.0  # glyphs of room the cut keeps on every side of the text (see focus_oversized)
# a cut that would keep this share of the area's box or more is none: the area is the text's own bubble - a tall
# narrow one round a single column, whose text is a small share of it - and stays a bubble (cut down to text on the
# page, its lettering went to the erase for lettering on the page, judged on a ring round the column that reached its
# outline on a page shown small: the inpainting there left the strokes' cores as a dotted line). The made-up narrow
# bubbles keep 0.93-0.99 of their area at every size from 800 to 1754 px of height; the tests' sample page has a bubble
# with three columns that keeps 0.90 at every size and is cut, as it always was.
FOCUS_WHOLE = 0.92
# the cut's own pad round the room it keeps, in glyphs: 6 px at the 24 px glyphs it was set at, so that the cut, and
# whether it is made at all, is the same on the page shown at any size (6 px fixed were a larger share of a page shown
# smaller: a bubble's cut kept 87 % of it at full size and 90 % at 0.8 of it, a bubble at one size and lettering on
# the page at the other)
FOCUS_PAD = 0.25


def focus_window(text_box: tuple[int, int, int, int], area: tuple[int, int, int, int],
                 max_text_share: float = 0.30, margin: float = 0.0,
                 pad: float = 6.0) -> tuple[int, int, int, int] | None:
    """The neighbourhood of *text_box* that a large white *area* is cut down to, or None when the text fills it:
    room for the translation (wider than vertical Japanese) and at least *margin* pixels on every side of the text
    (a short line keeps the room a bubble round it would give), and *pad* pixels more."""
    tx0, ty0, tx1, ty1 = text_box
    x0, y0, x1, y1 = area
    tw, th = tx1 - tx0, ty1 - ty0
    if tw <= 0 or th <= 0 or (tw * th) >= max_text_share * (x1 - x0) * (y1 - y0):
        return None
    side = max(tw, th)
    m = int(round(2 * margin))
    p = max(1, int(round(pad)))
    want_w, want_h = max(tw + m, int(side * 0.9)), max(th + m, int(side * 0.6))
    cx, cy = (tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0
    nx0 = max(x0, int(cx - want_w / 2) - p)
    nx1 = min(x1, int(cx + want_w / 2) + p)
    ny0 = max(y0, int(cy - want_h / 2) - p)
    ny1 = min(y1, int(cy + want_h / 2) + p)
    if nx1 - nx0 < 8 or ny1 - ny0 < 8:
        return None
    return nx0, ny0, nx1, ny1


def focus_oversized(regions: list[TextRegion], max_text_share: float = 0.30,
                    margin: float = FOCUS_MARGIN) -> list[TextRegion]:
    """Shrink regions that are large white areas with a small text block in them.

    Dialogue is sometimes drawn straight onto the white page background instead
    of a bubble; the detector then returns the whole white area. Erasing all of
    it would wipe artwork, so the region is cut down to the text's neighbourhood
    (with room for the translation, which is wider than vertical Japanese, and
    *margin* glyphs of room on every side of the text: the cut never leaves a
    short line, an exclamation in a small bubble, less room than its bubble).
    Whether, and where, is decided on the text as detected before lettering
    against the outline was taken in, so taking it in never widens the cut.
    A cut that would keep nearly all of the area (`FOCUS_WHOLE`) is none: a
    narrow bubble round one column of text stays a bubble.
    """
    for r in regions:
        win = focus_window(r.core_box or r.text_box, r.bbox, max_text_share, margin * r.glyph, FOCUS_PAD * r.glyph)
        if win is None:
            continue
        nx0, ny0, nx1, ny1 = win
        if (nx1 - nx0) * (ny1 - ny0) >= FOCUS_WHOLE * r.width * r.height:
            continue
        r.mask = np.ascontiguousarray(r.mask[ny0 - r.y0 : ny1 - r.y0, nx0 - r.x0 : nx1 - r.x0])
        r.x0, r.y0, r.x1, r.y1 = nx0, ny0, nx1, ny1
        r.kind = "text-on-dark" if r.kind == "dark-bubble" else "text-on-page"
    return regions


def drop_nested(regions: list[TextRegion], gray: np.ndarray, dark_threshold: int = 140,
                tolerance: int = 4, scale: float = 1.0) -> list[TextRegion]:
    """Of two regions where one lies inside the other together with its text, keep one (*gray*: the page as the
    regions were found on it, inverted for dark bubbles).

    A white area around a bubble (the page between the panels, the ring of a double outline) is found as a region
    of its own whose text is the bubble: its outline and its lettering. When nearly all of the outer region's
    glyph-sized ink lies inside the inner region's outline (its convex hull), the outer region is that white area
    and gives way: its mask would take in the bubble's outline. Glyphs inside the outline that the inner region
    missed (one touching a broken outline) are added to it. Otherwise the inner region is part of the outer one's
    text and gives way. Either way the text is lettered once. The *tolerance* and the sizes told apart are in px at
    the page's *scale* (`render.pagescale`).
    """
    from ..render import pagescale  # (here: the render package imports this module)

    tolerance = pagescale.px(tolerance, scale)
    drop: set[int] = set()
    for i, a in enumerate(regions):
        for j, b in enumerate(regions):
            if i == j or i in drop or j in drop:
                continue
            if b.x0 < a.x0 - tolerance or b.y0 < a.y0 - tolerance or b.x1 > a.x1 + tolerance or b.y1 > a.y1 + tolerance:
                continue  # b does not lie inside a
            at, bt = a.text_box, b.text_box
            shared = max(0, min(at[2], bt[2]) - max(at[0], bt[0])) * max(0, min(at[3], bt[3]) - max(at[1], bt[1]))
            if shared < 0.9 * max(1, (bt[2] - bt[0]) * (bt[3] - bt[1])):
                continue  # b's text is not part of a's
            if _take_in_from(b, a, gray, dark_threshold, scale):
                drop.add(i)
            else:
                drop.add(j)
    return [r for k, r in enumerate(regions) if k not in drop]


def _take_in_from(inner: TextRegion, outer: TextRegion, gray: np.ndarray, dark_threshold: int,
                  scale: float = 1.0) -> bool:
    """If nearly all (at least 3/4) of *outer*'s glyph-sized ink lies inside *inner*'s outline, add to *inner* the
    glyphs inside its outline that it missed and return True; otherwise leave *inner* alone and return False."""
    from ..render import pagescale  # (here: the render package imports this module)

    outline, glyph_least = pagescale.px(56, scale), pagescale.px(5, scale)
    contours, _ = cv2.findContours((inner.mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False
    hull = cv2.convexHull(np.vstack(contours)) + np.array([inner.x0, inner.y0])
    mask = outer.mask
    if mask.shape != (outer.height, outer.width):
        mask = cv2.resize(mask, (outer.width, outer.height), interpolation=cv2.INTER_NEAREST)
    ink = ((gray[outer.y0 : outer.y1, outer.x0 : outer.x1] < dark_threshold) & (mask > 0)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8, ltype=cv2.CV_32S)
    covered = np.zeros(ink.shape, bool)  # inner's mask in outer's frame
    ox, oy = inner.x0 - outer.x0, inner.y0 - outer.y0
    y0, x0 = max(0, oy), max(0, ox)
    y1, x1 = min(outer.height, oy + inner.height), min(outer.width, ox + inner.width)
    if y1 > y0 and x1 > x0:
        covered[y0:y1, x0:x1] = inner.mask[y0 - oy : y1 - oy, x0 - ox : x1 - ox] > 0
    in_mask = np.bincount(labels[covered & (ink > 0)], minlength=n)
    inside = outside = 0
    missed: list[int] = []
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        longest, shortest = max(w, h), min(w, h)
        if longest > outline or area < 2:
            continue  # an outline, or a stray pixel
        in_hull = cv2.pointPolygonTest(hull, (outer.x0 + x + w / 2.0, outer.y0 + y + h / 2.0), False) >= 0
        if in_hull and in_mask[k] < 0.5 * area:
            missed.append(k)  # inside the outline, outside inner's mask: lettering inner missed
        if longest < glyph_least or shortest < 2 or area < 6 or longest > 4 * shortest:
            continue  # not glyph-sized
        if in_hull:
            inside += area
        else:
            outside += area
    if inside == 0 or outside > 0.25 * (inside + outside):
        return False
    tx0, ty0, tx1, ty1 = inner.text_box
    if missed:
        add = cv2.dilate(np.isin(labels, missed).astype(np.uint8) * 255, pagescale.disc(5, scale))
        ys, xs = np.nonzero(add)
        ys, xs = ys - oy, xs - ox  # into inner's frame
        keep = (ys >= 0) & (ys < inner.height) & (xs >= 0) & (xs < inner.width)
        if keep.any():
            inner.mask = np.ascontiguousarray(inner.mask)
            inner.mask[ys[keep], xs[keep]] = 255
            boxes = [(outer.x0 + int(stats[k][0]), outer.y0 + int(stats[k][1]),
                      outer.x0 + int(stats[k][0] + stats[k][2]), outer.y0 + int(stats[k][1] + stats[k][3])) for k in missed]
            inner.text_box = (max(inner.x0, min([tx0] + [b[0] for b in boxes])),
                              max(inner.y0, min([ty0] + [b[1] for b in boxes])),
                              min(inner.x1, max([tx1] + [b[2] for b in boxes])),
                              min(inner.y1, max([ty1] + [b[3] for b in boxes])))
            inner.pieces += len(missed)
    return True


DARK_KINDS = frozenset({"dark-bubble", "text-on-dark", "text-dark", "manual-dark"})


def is_dark(region: TextRegion) -> bool:
    """True for regions with light lettering on a dark background."""
    return region.kind in DARK_KINDS


def _over(a: TextRegion, b: TextRegion) -> bool:
    """Whether *b* lies under *a*: the two overlap side to side by more than half the narrower one's width, and *b*'s
    centre is lower."""
    return min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5 * min(a.width, b.width) and a.y0 + a.y1 < b.y0 + b.y1


def _in_rows(regions: Sequence[TextRegion], rtl: bool) -> list[TextRegion]:
    """Rows top to bottom, right to left inside a row (left to right without *rtl*). Rows are clusters of vertically
    overlapping bubbles. A region under another (`_over`) comes after it, also where a tall region beside them put the
    two in one row and the lower one is further right: the order is the rows' one, but each time the first region with
    none over it still to come. On the 199 OpenMantra pages with two or more gold boxes (their own boxes, the panels
    found) that took the pages wholly right from 160 to 162, and no page that was right went wrong."""
    rows: list[list[TextRegion]] = []
    for r in sorted(regions, key=lambda q: q.y0):
        for row in rows:
            ry0 = min(q.y0 for q in row)
            ry1 = max(q.y1 for q in row)
            overlap = min(r.y1, ry1) - max(r.y0, ry0)
            if overlap > 0.3 * min(r.height, ry1 - ry0):
                row.append(r)
                break
        else:
            rows.append([r])
    rows.sort(key=lambda row: min(q.y0 for q in row))
    ordered: list[TextRegion] = []
    for row in rows:
        row.sort(key=(lambda q: -(q.x0 + q.x1)) if rtl else (lambda q: q.x0 + q.x1))
        ordered.extend(row)
    n = len(ordered)
    under = [[j for j in range(n) if _over(ordered[i], ordered[j])] for i in range(n)]
    over = [0] * n  # per region, the regions over it not yet taken
    for below in under:
        for j in below:
            over[j] += 1
    taken = [False] * n
    out: list[TextRegion] = []
    for _ in range(n):  # under means a lower centre: there is always one with none over it
        i = next(i for i in range(n) if not taken[i] and not over[i])
        taken[i] = True
        out.append(ordered[i])
        for j in under[i]:
            over[j] -= 1
    return out


def order_regions(regions: list[TextRegion], rtl: bool = True, panels: Sequence[Box] | None = None) -> list[TextRegion]:
    """Manga reading order. With two or more *panels*: panel by panel (`order_panels`), the rows inside each one; a
    region belongs to the panel its centre is in, and keeps that panel's box (`TextRegion.panel`). Without them (no
    pixels at hand, a page without gutters) the rows of the whole page, an approximation of panel order that gives the
    translator coherent context, and no panel."""
    if panels is not None and len(panels) >= 2:
        boxes = order_panels(panels, rtl)
        groups: list[list[TextRegion]] = [[] for _ in boxes]
        for r in regions:
            i = panel_of(boxes, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
            groups[i].append(r)
            r.panel = (int(boxes[i][0]), int(boxes[i][1]), int(boxes[i][2]), int(boxes[i][3]))
        ordered = [r for group in groups for r in _in_rows(group, rtl)]
    else:
        ordered = _in_rows(regions, rtl)
        for r in ordered:
            r.panel = None
    for i, r in enumerate(ordered):
        r.order = i
    return ordered


def order_on_page(image: np.ndarray, box: Box, regions: list[TextRegion], rtl: bool = True) -> list[TextRegion]:
    """`order_regions` for the regions of the page unit *box* of *image*, with the panels found there. What may lie on a
    gutter, and so counts as gutter, is the regions' lettering (their text boxes), not their boxes: a line through a
    row of bubbles was gutter for the width of their boxes, and the layout model's boxes take in whole bubbles. On the
    OpenMantra pages, the regions read as text ordered so, that took the found panels that are a gold one from 73.0 to
    82.8 % (66.0 to 76.3 % with the layout model), the pages fully right from 83.8 to 84.8 % (75.1 to 82.9 %).
    A lone region's panel is found too: it bounds that region's lettering (`TextRegion.panel`)."""
    return order_regions(regions, rtl, find_panels(image, box, [r.text_box for r in regions]) if regions else None)
