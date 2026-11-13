"""Text drawn straight onto the page: find it as clusters of glyph-sized dark pieces.

Not every line of dialogue sits in a closed bubble. Narration and a good deal
of dialogue in some art styles is lettered directly onto a white area, and
some bubbles have open or sketchy outlines that the bubble detector cannot
close. Those lines are still made of glyphs: small, compact dark pieces of
similar size, stacked into columns (or rows) on a light background. This
detector finds such clusters with plain connected-component analysis and
returns a region around each block, with a mask of the lettering and the
light background around it, so that erasing stays local and never takes the
drawing next to the text (see block_mask).

Guards against artwork: pieces must be glyph-sized and compact, sit on a light
background, vary in size the way glyphs do (not like a dot screen), and form a
few columns or rows rather than a grid. Hand-drawn sound effects are mostly
too large or too irregular to qualify.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from ..regions import TextRegion, box_iou
from .bubbles import fill_holes


@dataclass
class TextBlockConfig:
    white_threshold: int = 225
    dark_threshold: int = 140
    min_glyph: int = 5  # px, longest side of a piece
    max_glyph: int = 56
    max_piece_elongation: float = 4.0
    min_pieces: int = 4
    min_light_ring: float = 0.55  # share of light pixels around a piece
    link_gap: float = 1.1  # max gap between pieces along a line, in units of the larger piece size
    line_gap: float = 0.9  # max gap between neighbouring lines (columns of vertical text), same units
    pieces_per_line: float = 2.5  # a block's lines hold at least this many pieces on average
    list_pitch: float = 1.8  # horizontal lines whose pitch exceeds this many line heights are separate texts
    tone_min_pieces: int = 12
    tone_max_cv: float = 0.3
    min_block_light: float = 0.45  # share of light pixels in the block's expanded box


def letter_lines(boxes: list[tuple[int, int, int, int]], font: float) -> tuple[list[list[int]], bool]:
    """The lines of lettering among a block's pieces (lists of indices into *boxes*), and whether they are columns.

    A line is a chain of glyph-sized pieces set one after the other: in a column each piece sits centred below the
    one before, in a row beside it. The text runs in columns when the pieces' centres fall into no more columns
    than rows (as the detector decides it). Pieces of a drawing that a block took in (the eyes of a face, the tips
    of fingers, part of an outline) seldom chain up like lettering. When the block has lines of three pieces or
    more, a line of two counts only next to one of them (the last short column of a text, not a pair of marks in
    the drawing).
    """
    sized = [i for i, (x0, y0, x1, y1) in enumerate(boxes) if 0.35 * font <= max(x1 - x0, y1 - y0) <= 1.6 * font]
    vertical = (_count_lines(sorted((boxes[i][0] + boxes[i][2]) / 2.0 for i in sized), 0.5 * font)
                <= _count_lines(sorted((boxes[i][1] + boxes[i][3]) / 2.0 for i in sized), 0.5 * font))
    uf = _UnionFind(len(boxes))
    for p, a in enumerate(sized):
        ax0, ay0, ax1, ay1 = boxes[a]
        for b in sized[p + 1 :]:
            bx0, by0, bx1, by1 = boxes[b]
            if vertical:
                offset, gap = abs(ax0 + ax1 - bx0 - bx1) / 2.0, max(by0 - ay1, ay0 - by1)
            else:
                offset, gap = abs(ay0 + ay1 - by0 - by1) / 2.0, max(bx0 - ax1, ax0 - bx1)
            if offset <= 0.4 * font and gap <= 0.9 * font:
                uf.union(a, b)
    groups: dict[int, list[int]] = {}
    for i in sized:
        groups.setdefault(uf.find(i), []).append(i)
    lines = [g for g in groups.values() if len(g) >= 2]
    long = [g for g in lines if len(g) >= 3]
    if not long:
        return lines, vertical

    def span(g: list[int]) -> tuple[int, int, int, int]:
        return (min(boxes[i][0] for i in g), min(boxes[i][1] for i in g), max(boxes[i][2] for i in g),
                max(boxes[i][3] for i in g))

    kept = list(long)
    for g in lines:
        if len(g) >= 3:
            continue
        gx0, gy0, gx1, gy1 = span(g)
        for lx0, ly0, lx1, ly1 in (span(line) for line in long):
            if vertical:
                beside = abs(gx0 + gx1 - lx0 - lx1) / 2.0 <= 2.0 * font and min(gy1, ly1) > max(gy0, ly0)
            else:
                beside = abs(gy0 + gy1 - ly0 - ly1) / 2.0 <= 2.0 * font and min(gx1, lx1) > max(gx0, lx0)
            if beside:
                kept.append(g)
                break
    return kept, vertical


def block_mask(gray: np.ndarray, labels: np.ndarray, stats: np.ndarray, members: list[int],
               member_boxes: list[tuple[int, int, int, int]], text_box: tuple[int, int, int, int],
               region: tuple[int, int, int, int], glyph: float, white_threshold: int = 225, max_glyph: int = 56,
               others: frozenset[int] | set[int] = frozenset()) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Erase mask of a text block (uint8, 255 = erase and letter here, local to *region*) and the box of its lettering.

    The lettering is the block's own pieces (*members*, labels of *labels*), every dark piece lying inside the text
    box (the strokes and dots of glyphs) and small marks set in line right next to a glyph (a dash or the dots of an
    ellipsis at the end of a column). A block sometimes takes in part of the drawing next to its text (a face, a
    fist). That shows as a piece in the text box that is no glyph: longer than *max_glyph* and than 2.5 of the
    block's glyphs, not one of its pieces, and not set in one of its lines of lettering (see letter_lines). Then
    only what lies within one and a half glyphs of a line counts, and pieces far bigger than the glyphs count only
    when set in a line. Pieces of other blocks (*others*) are never this block's lettering. The mask holds the
    lettering, its anti-aliasing and the light background connected to it. Artwork stays out of it, even a thin
    line on the light background or one crossing the text box, and a hole in the mask is filled only when it holds
    no artwork, so the erase never takes part of the drawing around the text and the translation is not set over
    it.
    """
    rx0, ry0, rx1, ry1 = region
    bx0, by0, bx1, by1 = text_box
    lab = labels[ry0:ry1, rx0:rx1]
    margin = max(2, int(round(0.3 * glyph)))
    font = max(glyph, float(np.percentile([max(x1 - x0, y1 - y0) for x0, y0, x1, y1 in member_boxes], 75)))
    ids = [int(v) for v in np.unique(lab) if v > 0]
    inside = [k for k in ids if k not in others and stats[k][0] >= bx0 - margin and stats[k][1] >= by0 - margin
              and stats[k][0] + stats[k][2] <= bx1 + margin and stats[k][1] + stats[k][3] <= by1 + margin]
    lines, vertical = letter_lines(member_boxes, font)
    spans = [(min(member_boxes[i][0] for i in g), min(member_boxes[i][1] for i in g),
              max(member_boxes[i][2] for i in g), max(member_boxes[i][3] for i in g)) for g in lines]

    def near_line(x: int, y: int, w: int, h: int) -> bool:  # centre within one and a half glyphs of a line
        cx, cy, pad = x + w / 2.0, y + h / 2.0, 1.5 * font
        return any(sx0 - pad <= cx <= sx1 + pad and sy0 - pad <= cy <= sy1 + pad for sx0, sy0, sx1, sy1 in spans)

    def in_line(x: int, y: int, w: int, h: int) -> bool:  # centred on a line, in it or right before or after it
        for sx0, sy0, sx1, sy1 in spans:
            if vertical:
                offset, gap = abs(2 * x + w - sx0 - sx1) / 2.0, max(sy0 - (y + h), y - sy1)
            else:
                offset, gap = abs(2 * y + h - sy0 - sy1) / 2.0, max(sx0 - (x + w), x - sx1)
            if offset <= 0.5 * font and gap <= 0.9 * font:
                return True
        return False

    member_set = set(members)
    # a piece far bigger than the glyphs that closes round two or more others (a small figure's head round its eyes
    # and mouth) is a drawing: it and what it encloses are not lettering (a glyph's frame round one piece, as in
    # 回, is glyph-sized)
    enclosed: set[int] = set()
    for k in inside:
        x, y, w, h, _area = (int(v) for v in stats[k])
        if max(w, h) <= 1.6 * font:
            continue
        own = labels[y : y + h, x : x + w] == k
        holes = (fill_holes(own.astype(np.uint8) * 255) > 0) & ~own
        within = [int(j) for j in np.unique(labels[y : y + h, x : x + w][holes]) if j > 0 and j != k]
        within = [j for j in within if stats[j][0] >= x and stats[j][1] >= y and stats[j][0] + stats[j][2] <= x + w
                  and stats[j][1] + stats[j][3] <= y + h]
        if len(within) >= 2:
            enclosed.add(k)
            enclosed.update(within)
    drawing = bool(spans) and any(
        max(int(stats[k][2]), int(stats[k][3])) > max(2.5 * font, max_glyph)
        and not in_line(*(int(v) for v in stats[k][:4])) for k in inside if k not in member_set)
    text: set[int] = set()
    letters: list[tuple[int, int, int, int]] = []
    for k in inside:
        if k in enclosed:
            continue
        x, y, w, h, area = (int(v) for v in stats[k])
        if drawing and (not near_line(x, y, w, h) or (
                (max(w, h) > 2.0 * font or area > 1.2 * font * font) and not in_line(x, y, w, h))):
            continue  # away from the lines, or far bigger than the glyphs and not set in a line: the drawing
        text.add(k)
        letters.append((x, y, x + w, y + h))
    reach = 0.5 * glyph
    added = list(letters)
    for _round in range(2):  # a mark next to a glyph, then one next to that mark (the dots of an ellipsis)
        if not added:
            break
        ax0, ay0 = min(b[0] for b in added) - reach, min(b[1] for b in added) - reach
        ax1, ay1 = max(b[2] for b in added) + reach, max(b[3] for b in added) + reach
        found: list[tuple[int, int, int, int]] = []
        for k in ids:
            if k in text or k in others or k in enclosed:
                continue
            x, y, w, h, area = (int(v) for v in stats[k])
            if x + w < ax0 or x > ax1 or y + h < ay0 or y > ay1 or (drawing and not near_line(x, y, w, h)):
                continue
            if max(w, h) > 3 * glyph or area > 1.5 * glyph * glyph:
                continue
            for mx0, my0, mx1, my1 in added:
                # in a glyph's column just above or below it and no wider than a glyph, or in its row just before
                # or after it and no taller than one
                column = (min(x + w, mx1) - max(x, mx0) >= 0.3 * min(w, mx1 - mx0) and w <= 1.2 * glyph
                          and max(my0 - (y + h), y - my1) <= reach)
                row = (min(y + h, my1) - max(y, my0) >= 0.3 * min(h, my1 - my0) and h <= 1.2 * glyph
                       and max(mx0 - (x + w), x - mx1) <= reach)
                if column or row:
                    text.add(k)
                    found.append((x, y, x + w, y + h))
                    break
        letters.extend(found)
        added = found
    letter_box = text_box
    if letters:
        letter_box = (min(b[0] for b in letters), min(b[1] for b in letters), max(b[2] for b in letters),
                      max(b[3] for b in letters))
    text_px = np.isin(lab, list(text))
    art = (lab > 0) & ~text_px
    fringe = cv2.dilate(text_px.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    mask = ((gray[ry0:ry1, rx0:rx1] >= white_threshold) | fringe) & ~art
    # keep the parts connected to the lettering (not light patches elsewhere, nor the light inside a drawing)
    _n, parts = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
    touching = np.unique(parts[fringe & mask])
    keep = np.isin(parts, touching[touching > 0])
    # fill the holes left: counters of glyphs and specks of anti-aliasing among the lettering, tiny specks around
    # it; never a hole that holds artwork or one that opens onto the edge of the region
    nh, holes, hstats, _ = cv2.connectedComponentsWithStats((~keep).astype(np.uint8), connectivity=4,
                                                            ltype=cv2.CV_32S)
    lx0, ly0, lx1, ly1 = (letter_box[0] - rx0, letter_box[1] - ry0, letter_box[2] - rx0, letter_box[3] - ry0)
    fill = np.zeros(nh, bool)
    fill[np.unique(holes[max(0, ly0) : max(0, ly1), max(0, lx0) : max(0, lx1)])] = True
    fill |= hstats[:, cv2.CC_STAT_AREA] <= 0.25 * glyph * glyph
    fill[np.unique(holes[art])] = False
    fill[np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]]))] = False
    fill[0] = False
    keep |= fill[holes]
    return keep.astype(np.uint8) * 255, letter_box


def _split_rows(members: list[int], boxes: list[tuple[int, int, int, int]], tolerance: float) -> list[list[int]]:
    """Group pieces into rows by their vertical centres (sorted; a gap wider than *tolerance* starts a new row)."""
    ordered = sorted(members, key=lambda i: (boxes[i][1] + boxes[i][3]) / 2.0)
    rows: list[list[int]] = []
    last = None
    for i in ordered:
        cy = (boxes[i][1] + boxes[i][3]) / 2.0
        if last is None or cy - last > tolerance:
            rows.append([i])
        else:
            rows[-1].append(i)
        last = cy
    return rows


def _count_lines(sorted_centres: list[float], tolerance: float) -> int:
    """Number of clusters in sorted 1-D positions, splitting where neighbours are further apart than *tolerance*."""
    if not sorted_centres:
        return 0
    lines = 1
    for a, b in zip(sorted_centres, sorted_centres[1:]):
        if b - a > tolerance:
            lines += 1
    return lines


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class TextBlockDetector:
    def __init__(self, config: TextBlockConfig | None = None):
        self.cfg = config or TextBlockConfig()

    def detect(self, rgb: np.ndarray, inverted: bool = False, taken: Sequence[TextRegion] = ()) -> list[TextRegion]:
        """Find text blocks; ``inverted=True`` finds light lettering on dark areas (kind "text-dark").

        Pieces inside the mask of a region in *taken* (the bubbles found before) are that bubble's lettering and are
        left out, so a block never takes in a bubble's text along with the drawing next to it: the text would be
        read and translated twice.
        """
        cfg = self.cfg
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
        if inverted:
            gray = 255 - gray
        kind = "text-dark" if inverted else "text"
        h, w = gray.shape
        dark = (gray < cfg.dark_threshold).astype(np.uint8)
        light = (gray >= cfg.white_threshold).astype(np.uint8)
        light_integral = cv2.integral(light)  # (h+1, w+1)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8, ltype=cv2.CV_32S)

        def in_taken(x: int, y: int) -> bool:
            for r in taken:
                if r.x0 <= x < r.x1 and r.y0 <= y < r.y1:
                    m = r.mask
                    if m.shape != (r.height, r.width) or m[y - r.y0, x - r.x0] > 0:
                        return True
            return False

        def light_share(x0: int, y0: int, x1: int, y1: int) -> float:
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1), min(h, y1)
            area = (x1 - x0) * (y1 - y0)
            if area <= 0:
                return 0.0
            total = light_integral[y1, x1] - light_integral[y0, x1] - light_integral[y1, x0] + light_integral[y0, x0]
            return float(total) / area

        # --- glyph-sized pieces on a light background ---
        boxes: list[tuple[int, int, int, int]] = []
        ids: list[int] = []  # component label of each piece
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            longest, shortest = max(bw, bh), min(bw, bh)
            if longest < cfg.min_glyph or longest > cfg.max_glyph or shortest < 2 or area < 6:
                continue
            if longest / max(shortest, 1) > cfg.max_piece_elongation:
                continue
            if taken and in_taken(x + bw // 2, y + bh // 2):
                continue  # a bubble's lettering
            pad = max(3, longest // 2)
            ring_light = light_share(x - pad, y - pad, x + bw + pad, y + bh + pad)
            if ring_light < cfg.min_light_ring:
                continue
            boxes.append((x, y, x + bw, y + bh))
            ids.append(i)
        if len(boxes) < cfg.min_pieces:
            return []

        # --- link neighbouring pieces into blocks (vertical columns and horizontal rows) ---
        uf = _UnionFind(len(boxes))
        order = sorted(range(len(boxes)), key=lambda i: boxes[i][1])
        for a_pos, ia in enumerate(order):
            ax0, ay0, ax1, ay1 = boxes[ia]
            asize = max(ax1 - ax0, ay1 - ay0)
            for ib in order[a_pos + 1 :]:
                bx0, by0, bx1, by1 = boxes[ib]
                bsize = max(bx1 - bx0, by1 - by0)
                gap_limit = cfg.link_gap * max(asize, bsize)
                if by0 - ay1 > gap_limit:
                    break  # sorted by top edge: nothing further down can link vertically ...
                x_overlap = min(ax1, bx1) - max(ax0, bx0)
                y_overlap = min(ay1, by1) - max(ay0, by0)
                line_limit = cfg.line_gap * max(asize, bsize)
                x_gap = max(ax0, bx0) - min(ax1, bx1)
                # same column of vertical text, or the next column over
                vertical = x_overlap > 0.3 * min(ax1 - ax0, bx1 - bx0) and (by0 - ay1) <= gap_limit
                next_column = y_overlap > 0.5 * min(ay1 - ay0, by1 - by0) and 0 <= x_gap <= line_limit
                if vertical or next_column:
                    uf.union(ia, ib)
        groups: dict[int, list[int]] = {}
        for i in range(len(boxes)):
            groups.setdefault(uf.find(i), []).append(i)

        found: list[tuple[list[int], float, tuple[int, int, int, int], tuple[int, int, int, int]]] = []
        pending: list[list[int]] = [m for m in groups.values() if len(m) >= cfg.min_pieces]
        while pending:
            members = pending.pop()
            if len(members) < cfg.min_pieces:
                continue
            sizes = np.array([max(boxes[i][2] - boxes[i][0], boxes[i][3] - boxes[i][1]) for i in members], np.float64)
            areas = np.array([(boxes[i][2] - boxes[i][0]) * (boxes[i][3] - boxes[i][1]) for i in members], np.float64)
            if len(members) >= cfg.tone_min_pieces and areas.std() / max(areas.mean(), 1e-6) < cfg.tone_max_cv:
                continue  # dot screen
            glyph = float(np.median(sizes))
            bx0 = min(boxes[i][0] for i in members)
            by0 = min(boxes[i][1] for i in members)
            bx1 = max(boxes[i][2] for i in members)
            by1 = max(boxes[i][3] for i in members)
            bw, bh = bx1 - bx0, by1 - by0
            # Text is organised in lines: the pieces fall into a few columns (vertical
            # text) or a few rows, each holding several pieces. Scattered artwork and
            # dot screens do not.
            xs = sorted((boxes[i][0] + boxes[i][2]) / 2.0 for i in members)
            ys = sorted((boxes[i][1] + boxes[i][3]) / 2.0 for i in members)
            columns = _count_lines(xs, 0.5 * glyph)
            rows = _count_lines(ys, 0.5 * glyph)
            max_lines = max(1, int(len(members) / cfg.pieces_per_line))
            if min(columns, rows) > max_lines:
                continue
            # A column of widely spaced horizontal lines (a table of contents, a list)
            # is several texts, not one: split it and handle each line on its own.
            if rows >= 3 and columns >= rows:
                row_groups = _split_rows(members, boxes, 0.5 * glyph)
                if len(row_groups) >= 3:
                    centres = sorted(float(np.mean([(boxes[i][1] + boxes[i][3]) / 2.0 for i in g])) for g in row_groups)
                    heights = [max(boxes[i][3] for i in g) - min(boxes[i][1] for i in g) for g in row_groups]
                    pitch = float(np.median(np.diff(centres)))
                    if pitch >= cfg.list_pitch * float(np.median(heights)):
                        pending.extend(g for g in row_groups if len(g) >= 2)
                        continue
            # text needs a light background around it
            pad = int(glyph * 0.6) + 2
            if light_share(bx0 - pad, by0 - pad, bx1 + pad, by1 + pad) < cfg.min_block_light:
                continue
            # room for the translation (wider than vertical Japanese)
            side = max(bw, bh)
            want_w, want_h = max(bw + 2 * pad, int(side * 0.9)), max(bh + 2 * pad, int(side * 0.6))
            cx, cy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
            rx0, ry0 = max(0, int(cx - want_w / 2)), max(0, int(cy - want_h / 2))
            rx1, ry1 = min(w, int(cx + want_w / 2)), min(h, int(cy + want_h / 2))
            if rx1 - rx0 < 8 or ry1 - ry0 < 8:
                continue
            found.append((members, glyph, (bx0, by0, bx1, by1), (rx0, ry0, rx1, ry1)))
        all_pieces = {ids[i] for members, *_rest in found for i in members}
        regions: list[TextRegion] = []
        for members, glyph, text_box, (rx0, ry0, rx1, ry1) in found:
            own = [ids[i] for i in members]
            others = all_pieces.difference(own)
            mask, letter_box = block_mask(gray, labels, stats, own, [boxes[i] for i in members], text_box,
                                          (rx0, ry0, rx1, ry1), glyph, cfg.white_threshold, cfg.max_glyph, others)
            for _round in range(3):
                lx0, ly0, lx1, ly1 = letter_box
                if lx0 >= rx0 and ly0 >= ry0 and lx1 <= rx1 and ly1 <= ry1:
                    break
                # lettering reaching past the region (a dash ending a column, a big hand-drawn glyph): widen the
                # region to take it in, or the erase would stop at its edge and leave the end on the page (marks
                # further out only show once the region is wider, hence a few rounds)
                rx0, ry0 = max(0, min(rx0, lx0 - 2)), max(0, min(ry0, ly0 - 2))
                rx1, ry1 = min(w, max(rx1, lx1 + 2)), min(h, max(ry1, ly1 + 2))
                mask, letter_box = block_mask(gray, labels, stats, own, [boxes[i] for i in members], text_box,
                                              (rx0, ry0, rx1, ry1), glyph, cfg.white_threshold, cfg.max_glyph, others)
            regions.append(TextRegion(x0=rx0, y0=ry0, x1=rx1, y1=ry1, mask=mask, text_box=text_box, kind=kind,
                                      pieces=len(members), letter_box=letter_box))
        return regions


def merge_regions(bubbles: list[TextRegion], blocks: list[TextRegion], max_iou: float = 0.2) -> list[TextRegion]:
    """Earlier regions win; later ones are added where no earlier region already covers their text."""
    out = list(bubbles)
    for b in blocks:
        covered = False
        for r in out:
            tx0, ty0, tx1, ty1 = b.text_box
            cx, cy = (tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0
            if r.x0 <= cx < r.x1 and r.y0 <= cy < r.y1:
                covered = True
                break
            if box_iou(r.bbox, b.bbox) > max_iou:
                covered = True
                break
        if not covered:
            out.append(b)
    return out
