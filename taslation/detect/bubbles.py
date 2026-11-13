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

from .beyond import lettering_beyond
from .panels import find_panels, order_panels, panel_of
from ..regions import Box, TextRegion


@dataclass
class DetectorConfig:
    white_threshold: int = 225  # bubble interior is at least this bright
    dark_threshold: int = 140  # text strokes are at most this bright
    min_area_ratio: float = 0.0006  # of the image area
    max_area_ratio: float = 0.20
    min_size: int = 24  # px, both sides
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


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Return *mask* (uint8 0/255) with all enclosed holes filled."""
    h, w = mask.shape
    padded = np.zeros((h + 2, w + 2), np.uint8)
    padded[1:-1, 1:-1] = mask
    inv = cv2.bitwise_not(padded)  # outside + holes = 255, shape = 0
    ff_mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(inv, ff_mask, (0, 0), 0)  # outside -> 0, holes stay 255
    return cv2.bitwise_or(mask, inv[1:-1, 1:-1])


def recover_edge_text(gray: np.ndarray, box: tuple[int, int, int, int], filled: np.ndarray, inner: np.ndarray,
                      glyph: float, dark_threshold: int, margin: int = 8, max_glyph: float = 2.0,
                      white_threshold: int = 225, debug: dict | None = None,
                      limit: tuple[int, int, int, int] | None = None) -> tuple[tuple[int, int, int, int], np.ndarray, tuple[int, int, int, int], int] | None:
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
    candidate and taken, and the reason for returning None.
    """
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
    near = cv2.dilate(fw8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    ring = (cv2.dilate(fw8, np.ones((3, 3), np.uint8)) > 0) & ~filled_w
    edge_band = (near & ~filled_w & (g < white_threshold)) | ring  # the bubble's edge: what kept its white area apart
    barrier = (dark > 0) | edge_band
    _n_nd, lab_nd = cv2.connectedComponents((~barrier).astype(np.uint8), connectivity=4)
    edge = np.concatenate([lab_nd[0, :], lab_nd[-1, :], lab_nd[:, 0], lab_nd[:, -1]])
    edge = edge[edge > 0]
    outside = np.isin(lab_nd, np.unique(edge)) if edge.size else np.zeros(dark.shape, bool)
    _n_d, lab_d, st_d, _ = cv2.connectedComponentsWithStats(dark, connectivity=8, ltype=cv2.CV_32S)
    touching = cv2.dilate(outside.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    on_border = np.concatenate([lab_d[0, :], lab_d[-1, :], lab_d[:, 0], lab_d[:, -1]])
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
    if inside[0, :].any() or inside[-1, :].any() or inside[:, 0].any() or inside[:, -1].any():
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
    seed_area = max(6.0, 0.2 * float(np.median(st_t[1:, cv2.CC_STAT_AREA]))) if n_t > 1 else 6.0

    def glyph_like(j: int) -> bool:  # a glyph or a good part of one: not a tone dot, not a hairline's dash
        return int(st_d[j][4]) >= seed_area and min(int(st_d[j][2]), int(st_d[j][3])) >= 3

    to_white = cv2.distanceTransform((~filled_w).astype(np.uint8), cv2.DIST_L2, 3)
    accepted = [j for j in candidates if glyph_like(j) and nearest(to_white, j) <= 4.0]
    step = max(4.0, 0.5 * glyph)
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
        beside = max(4.0, 0.35 * glyph)
        accepted += [j for j in candidates if j not in accepted and nearest(to_taken, j) <= beside]
    dbg.update(candidates=set(candidates), accepted=set(accepted), too_big={
        int(j) for j in dbg["inside"] if max(int(st_d[j][2]), int(st_d[j][3])) > max_glyph * glyph})
    if not accepted:
        dbg["result"] = "nothing next to the white area"
        return None
    acc = np.isin(lab_d, accepted)
    add = (cv2.dilate(acc.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0) & inside
    mask = inner_w | add
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
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

    def detect(self, rgb: np.ndarray, inverted: bool = False) -> list[TextRegion]:
        """Find bubbles in an RGB uint8 image. Returned regions are not yet ordered.

        With ``inverted=True`` the image is negated first, which finds dark
        bubbles with light lettering (regions come back with kind "dark-bubble").
        """
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
        min_area = max(cfg.min_size * cfg.min_size, cfg.min_area_ratio * img_area)
        max_area = cfg.max_area_ratio * img_area

        white = (gray >= cfg.white_threshold).astype(np.uint8) * 255
        # A one pixel erosion breaks weak links through anti-aliased outlines.
        white = cv2.erode(white, np.ones((3, 3), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=4, ltype=cv2.CV_32S)

        kernel_size = 2 * cfg.outline_erosion + 1
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        regions: list[TextRegion] = []
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if area < min_area or area > max_area:
                continue
            if bw < cfg.min_size or bh < cfg.min_size:
                continue
            aspect = bw / bh
            if aspect > cfg.max_aspect or aspect < 1.0 / cfg.max_aspect:
                continue

            comp = (labels[y : y + bh, x : x + bw] == i).astype(np.uint8) * 255
            filled = fill_holes(comp)
            filled_area = int(cv2.countNonZero(filled))
            if filled_area / float(bw * bh) < cfg.min_fill:
                continue
            hole_ratio = (filled_area - area) / float(filled_area)
            if hole_ratio < cfg.min_dark_ratio or hole_ratio > cfg.max_dark_ratio:
                continue

            inner = cv2.erode(filled, erode_kernel)
            gray_crop = gray[y : y + bh, x : x + bw]
            dark = ((gray_crop < cfg.dark_threshold) & (inner > 0)).astype(np.uint8)
            if int(dark.sum()) < cfg.min_text_pixels:
                continue
            # bubbles that touch or overlap: one region each (white bubbles only: the black areas of a page join up
            # into shapes of every kind, and a dark bubble's lettering split that way loses its columns)
            parts = (split_lobes(filled, inner, dark, cfg.lobe_neck, cfg.lobe_notch, cfg.lobe_link)
                     if cfg.split_lobes and not inverted else None)
            whole = None
            if parts:
                found = [self._region(gray, (x + px, y + py, pw_, ph_), p_filled, p_inner, p_dark, kind)
                         for px, py, pw_, ph_, p_filled, p_inner, p_dark in parts]
                if any(r is None for r in found):
                    # a bubble's lettering would not pass on its own (a line of dots, two glyphs): read the area
                    # whole, as before, rather than lose that line; when the whole does not pass either, the parts
                    # that do are kept
                    whole = self._region(gray, (x, y, bw, bh), filled, inner, dark, kind)
                regions.extend([whole] if whole is not None else [r for r in found if r is not None])
            else:
                whole = self._region(gray, (x, y, bw, bh), filled, inner, dark, kind)
                if whole is not None:
                    regions.append(whole)
        if inverted and cfg.recover_edge_text and cfg.take_columns_beyond:
            take_columns_beyond(gray, regions, cfg.dark_threshold)
        return regions

    def _region(self, gray: np.ndarray, box: tuple[int, int, int, int], filled: np.ndarray, inner: np.ndarray,
                dark: np.ndarray, kind: str) -> TextRegion | None:
        """The text region of one white area (*box* x, y, w, h in *gray*; its filled shape, erase mask and dark
        pixels inside, in that box), or None when what is inside it is a drawing rather than lettering."""
        cfg = self.cfg
        x, y, bw, bh = box
        h = gray.shape[0]
        dark_count = int(dark.sum())
        if dark_count < cfg.min_text_pixels:
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
        line_like = (np.minimum(pw, ph) <= cfg.line_max_thickness) & (np.maximum(pw, ph) >= 4 * np.minimum(pw, ph))
        if pieces[line_like].sum() > 0.7 * pieces.sum():
            return None
        # Eyes, dots and blush marks are solid blobs; glyphs are strokes that fill little of their box.
        compact = (np.minimum(pw, ph) >= 4) & (np.maximum(pw, ph) < 3 * np.minimum(pw, ph))
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
        glyph = max(8.0, float(np.percentile(np.maximum(pw, ph), 90)))
        if cfg.recover_edge_text:
            found = recover_edge_text(gray, (x, y, bw, bh), filled, inner, glyph, cfg.dark_threshold,
                                      cfg.edge_margin, cfg.edge_max_glyph, cfg.white_threshold,
                                      limit=focus_window(text_box, (x, y, x + bw, y + bh)))
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
    (the largest distance from the outline) and much deeper than any other bend (every other one at most
    *dominance* times the shallower notch: the many bends of a cloud or of a spiky shout do not count). The cut is
    the straight line between the two notches: it runs across the white, crosses no lettering and leaves blocks on
    both sides (the base of a tail leaves none on its side)."""
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
    if len(found) > 2 and found[2][0] > dominance * found[1][0]:
        return None  # more bends as deep as the notches: a cloud, a spiky outline, a tail beside the junction
    (_da, pa), (_db, pb) = found[0], found[1]
    n = int(np.hypot(pa[0] - pb[0], pa[1] - pb[1])) + 1
    xs = np.round(np.linspace(pa[0], pb[0], n)).astype(int)
    ys = np.round(np.linspace(pa[1], pb[1], n)).astype(int)
    if inside[ys, xs].mean() < 0.9 or int((dark[ys, xs] > 0).sum()) > 2:
        return None  # the line leaves the white, or runs through the lettering
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
    another holding at least a glyph's worth of ink; specks go with the part they fall in. A part is cut again,
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
    if len(blocks) < 2:
        return None
    ink = stats[:, cv2.CC_STAT_AREA].astype(np.float64)
    if ink[np.maximum(stats[:, 2], stats[:, 3]) > 2.5 * glyph].sum() > drawing * ink.sum():
        return None  # strokes far longer than a glyph: a drawing on a stretch of white page, not bubbles
    inside = filled > 0
    depth = cv2.distanceTransform(np.pad(inside.astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]  # box edge: outline
    owner = _neck_owner(inside, depth, blocks, stats, neck)
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


def take_columns_beyond(gray: np.ndarray, regions: list[TextRegion], dark_threshold: int) -> int:
    """Dark bubbles whose lettering goes on past the interior on the bubble's own black (a badly closed blob): the
    text box, the region and the erase mask grow over such a column, which is read with the bubble and judged
    without it; a column inside another bubble is never taken. Returns how many regions grew."""
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
                                                dark_threshold, exclude=union & ~own)
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


def focus_window(text_box: tuple[int, int, int, int], area: tuple[int, int, int, int],
                 max_text_share: float = 0.30, margin: float = 0.0) -> tuple[int, int, int, int] | None:
    """The neighbourhood of *text_box* that a large white *area* is cut down to, or None when the text fills it:
    room for the translation (wider than vertical Japanese) and at least *margin* pixels on every side of the text
    (a short line keeps the room a bubble round it would give)."""
    tx0, ty0, tx1, ty1 = text_box
    x0, y0, x1, y1 = area
    tw, th = tx1 - tx0, ty1 - ty0
    if tw <= 0 or th <= 0 or (tw * th) >= max_text_share * (x1 - x0) * (y1 - y0):
        return None
    side = max(tw, th)
    m = int(round(2 * margin))
    want_w, want_h = max(tw + m, int(side * 0.9)), max(th + m, int(side * 0.6))
    cx, cy = (tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0
    nx0 = max(x0, int(cx - want_w / 2) - 6)
    nx1 = min(x1, int(cx + want_w / 2) + 6)
    ny0 = max(y0, int(cy - want_h / 2) - 6)
    ny1 = min(y1, int(cy + want_h / 2) + 6)
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
    """
    for r in regions:
        win = focus_window(r.core_box or r.text_box, r.bbox, max_text_share, margin * r.glyph)
        if win is None:
            continue
        nx0, ny0, nx1, ny1 = win
        r.mask = np.ascontiguousarray(r.mask[ny0 - r.y0 : ny1 - r.y0, nx0 - r.x0 : nx1 - r.x0])
        r.x0, r.y0, r.x1, r.y1 = nx0, ny0, nx1, ny1
        r.kind = "text-on-dark" if r.kind == "dark-bubble" else "text-on-page"
    return regions


def drop_nested(regions: list[TextRegion], gray: np.ndarray, dark_threshold: int = 140,
                tolerance: int = 4) -> list[TextRegion]:
    """Of two regions where one lies inside the other together with its text, keep one (*gray*: the page as the
    regions were found on it, inverted for dark bubbles).

    A white area around a bubble (the page between the panels, the ring of a double outline) is found as a region
    of its own whose text is the bubble: its outline and its lettering. When nearly all of the outer region's
    glyph-sized ink lies inside the inner region's outline (its convex hull), the outer region is that white area
    and gives way: its mask would take in the bubble's outline. Glyphs inside the outline that the inner region
    missed (one touching a broken outline) are added to it. Otherwise the inner region is part of the outer one's
    text and gives way. Either way the text is lettered once.
    """
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
            if _take_in_from(b, a, gray, dark_threshold):
                drop.add(i)
            else:
                drop.add(j)
    return [r for k, r in enumerate(regions) if k not in drop]


def _take_in_from(inner: TextRegion, outer: TextRegion, gray: np.ndarray, dark_threshold: int) -> bool:
    """If nearly all (at least 3/4) of *outer*'s glyph-sized ink lies inside *inner*'s outline, add to *inner* the
    glyphs inside its outline that it missed and return True; otherwise leave *inner* alone and return False."""
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
        if longest > 56 or area < 2:
            continue  # an outline, or a stray pixel
        in_hull = cv2.pointPolygonTest(hull, (outer.x0 + x + w / 2.0, outer.y0 + y + h / 2.0), False) >= 0
        if in_hull and in_mask[k] < 0.5 * area:
            missed.append(k)  # inside the outline, outside inner's mask: lettering inner missed
        if longest < 5 or shortest < 2 or area < 6 or longest > 4 * shortest:
            continue  # not glyph-sized
        if in_hull:
            inside += area
        else:
            outside += area
    if inside == 0 or outside > 0.25 * (inside + outside):
        return False
    tx0, ty0, tx1, ty1 = inner.text_box
    if missed:
        add = cv2.dilate(np.isin(labels, missed).astype(np.uint8) * 255,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
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


def _in_rows(regions: Sequence[TextRegion], rtl: bool) -> list[TextRegion]:
    """Rows top to bottom, right to left inside a row (left to right without *rtl*). Rows are clusters of vertically
    overlapping bubbles."""
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
    return ordered


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
