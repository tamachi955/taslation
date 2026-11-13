"""Lettering beyond a bubble's interior.

A bubble's lettering sometimes runs past its interior: a column of white text that goes on over the dark tone
around a dark bubble, or outlined glyphs set over the hair that reaches into a white one. Here are the pieces of
such lettering for the detector (the text box grows to take an aligned column in), for the OCR (a light bubble's
crop shows the outlined glyphs as black on white instead of a black drawing) and for the erase (the glyphs' white
rings are painted the drawing's colour).
"""

from __future__ import annotations

import cv2
import numpy as np

Box = tuple[int, int, int, int]

BIG = 90  # a component longer than this is a drawing or the outline, never a glyph
_OPEN = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))  # a ring is thinner than this; the page and a bubble are not
_NEAR = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
_STROKE = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))  # a stroke up to twelve pixels thick, ring to ring
_AGAINST = np.ones((7, 7), np.uint8)


def thin_light(gray: np.ndarray, white_threshold: int = 225) -> np.ndarray:
    """Light pixels in thin structures (the rings of outlined glyphs, hair highlights): what an opening removes."""
    light = (gray > white_threshold).astype(np.uint8)
    return (light > 0) & (cv2.morphologyEx(light, cv2.MORPH_OPEN, _OPEN) == 0)


def big_dark(gray: np.ndarray, dark_threshold: int = 140, big: int = BIG) -> np.ndarray:
    """Dark pixels of components longer than *big*: the drawing, the outline, the hair."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats((gray < dark_threshold).astype(np.uint8), connectivity=8)
    ids = [i for i in range(1, n) if max(int(stats[i][2]), int(stats[i][3])) > big]
    return np.isin(labels, ids) if ids else np.zeros(gray.shape, bool)


def _window(shape: tuple[int, ...], box: Box, pad: int = 2) -> np.ndarray:
    h, w = shape[:2]
    out = np.zeros((h, w), bool)
    x0, y0, x1, y1 = max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = True
    return out


def outlined_strokes(gray: np.ndarray, mask: np.ndarray, box: Box, dark_threshold: int = 140,
                     white_threshold: int = 225) -> np.ndarray:
    """Outside *mask* within *box*: the dark strokes of outlined glyphs on a dark drawing (dark pixels within four
    pixels of a thin light ring), which the OCR should see as ink."""
    win = _window(gray.shape, box) & (mask == 0)
    rings = thin_light(gray, white_threshold) & win
    near = cv2.dilate(rings.astype(np.uint8), _STROKE) > 0
    return near & (gray < dark_threshold) & win


def rings_on_dark(gray: np.ndarray, mask: np.ndarray, box: Box, dark_threshold: int = 140,
                  white_threshold: int = 225) -> np.ndarray:
    """Outside *mask* within *box*: the thin light rings that lie against the drawing's dark (an outlined glyph over
    hair, over black), which the erase paints with the drawing's colour. A ring against small dark alone (a glyph
    whose strokes do not touch the drawing) is left: so are hairlines and tone dots in the window."""
    win = _window(gray.shape, box) & (mask == 0)
    rings = thin_light(gray, white_threshold) & win
    if not rings.any():
        return rings
    against = cv2.dilate(big_dark(gray, dark_threshold).astype(np.uint8), _AGAINST) > 0
    return rings & against


def ocr_view(rgb: np.ndarray, mask: np.ndarray, box: Box, dark_threshold: int = 140,
             white_threshold: int = 225) -> np.ndarray | None:
    """A copy of a light bubble's pixels for the OCR: outside the mask within *box* everything is white except the
    outlined glyphs' strokes, black. None when nothing dark lies outside the mask within the box (the crop is fine
    as it is)."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    win = _window(gray.shape, box) & (mask == 0)
    if not (win & (gray < dark_threshold)).any():
        return None
    out = rgb.copy()
    out[win] = 255
    out[outlined_strokes(gray, mask, box, dark_threshold, white_threshold)] = 0
    return out


def lettering_beyond(gray: np.ndarray, box: Box, inside: np.ndarray, text_box: Box, glyph: float,
                     dark_threshold: int = 140, max_reach: float = 1.5, rounds: int = 2,
                     same_ground: int = 40, exclude: np.ndarray | None = None, flat: float = 25.0,
                     debug: dict | None = None) -> tuple[Box, int, list[Box]]:
    """The text box grown to take in a column (or row) of lettering that goes on past the bubble's interior on the
    bubble's own ground (a black bubble whose black continues under the lettering, unclosed): one column per
    round, nearest first, of at least three lettering-sized, glyph-shaped dark pieces stacked within a glyph's pitch, aligned with
    the box, not cut by the window, on a flat ground (grey-level spread under *flat*) within *same_ground* of the
    interior's own level, and never inside *exclude* (the other bubbles' interiors, as a page-sized mask). *gray*
    is the detector's image (inverted for a dark bubble, so lettering is dark); *inside* is the bubble's erase mask
    in *box* (x, y, w, h). Returns (the box, how many pieces were taken, their boxes), the box as given when none."""
    H, W = gray.shape[:2]
    x, y, bw, bh = box
    ink_level = min(dark_threshold, 100)
    reach = max(4, int(round(max_reach * glyph)))
    span = reach + int(round(2.0 * glyph)) + 2  # the window: a piece within reach lies whole inside it
    region = gray[y:y + bh, x:x + bw]
    own = region[inside[:region.shape[0], :region.shape[1]] > 0] if region.size else np.zeros(0, np.uint8)
    if own.size < 16:
        return text_box, 0, []
    interior_level = float(np.median(own))
    ys, xs = np.nonzero(inside[:bh, :bw])
    if xs.size == 0:
        return text_box, 0, []
    mask_box = (x + int(xs.min()), y + int(ys.min()), x + int(xs.max()) + 1, y + int(ys.max()) + 1)
    tx0, ty0, tx1, ty1 = text_box
    taken: list[Box] = []
    for _ in range(rounds):
        wx0, wy0, wx1, wy1 = max(0, tx0 - span), max(0, ty0 - span), min(W, tx1 + span), min(H, ty1 + span)
        g = gray[wy0:wy1, wx0:wx1]
        inner = np.zeros(g.shape, bool)
        ix0, iy0, ix1, iy1 = max(x, wx0), max(y, wy0), min(x + bw, wx1), min(y + bh, wy1)
        if ix1 > ix0 and iy1 > iy0:
            inner[iy0 - wy0:iy1 - wy0, ix0 - wx0:ix1 - wx0] = inside[iy0 - y:iy1 - y, ix0 - x:ix1 - x] > 0
        if exclude is not None:
            inner |= exclude[wy0:wy1, wx0:wx1]
        ink = ((g < ink_level) & ~inner).astype(np.uint8)
        any_ink = cv2.dilate((g < ink_level).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0  # every glyph, every stroke
        n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
        vertical = (ty1 - ty0) >= (tx1 - tx0)
        found: list[tuple[int, Box, int]] = []  # (gap to the box, piece box, ink area)
        for i in range(1, n):
            px, py, pw, ph, area = (int(v) for v in stats[i])
            if area < 6 or max(pw, ph) < 0.25 * glyph or max(pw, ph) > 2.0 * glyph:
                continue
            if min(pw, ph) < max(3, 0.2 * glyph) or max(pw, ph) > 3 * min(pw, ph) or area < 0.15 * pw * ph:
                continue  # a hairline, a speed line, a highlight: thin or long or hollow, where a glyph's piece is not
            if px == 0 or py == 0 or px + pw == g.shape[1] or py + ph == g.shape[0]:
                continue  # cut by the window: whatever it is, it is not lettering sitting beside the box
            X0, Y0, X1, Y1 = wx0 + px, wy0 + py, wx0 + px + pw, wy0 + py + ph
            if X0 < tx1 and X1 > tx0 and Y0 < ty1 and Y1 > ty0:
                continue  # overlaps the text box: the detector saw it already, or it is not beside the text
            if vertical:
                gap = max(X0 - tx1, tx0 - X1)
                if min(Y1, ty1) - max(Y0, ty0) < 0.5 * ph or gap > reach:
                    continue
                edge_gap = mask_box[2] - tx1 if X0 >= tx1 else tx0 - mask_box[0]  # the text reaches the interior's edge
            else:
                gap = max(Y0 - ty1, ty0 - Y1)
                if min(X1, tx1) - max(X0, tx0) < 0.5 * pw or gap > reach:
                    continue
                edge_gap = mask_box[3] - ty1 if Y0 >= ty1 else ty0 - mask_box[1]
            if edge_gap > 1.2 * glyph:
                continue  # the text stops well inside the interior: what lies beyond is not its continuation
            piece = (labels == i).astype(np.uint8)
            band = (cv2.dilate(piece, _NEAR) > 0) & ~any_ink & ~inner  # the ground alone, no glyph, no stroke
            if band.sum() < 8 or abs(float(np.median(g[band])) - interior_level) > same_ground:
                continue  # not the bubble's own ground: the page, a tone, a drawing
            if float(g[band].astype(np.float32).std()) > flat:
                continue  # a drawing (hair, speed lines) rather than the flat ground of the bubble
            found.append((gap, (X0, Y0, X1, Y1), area))
        dbg = debug if debug is not None else {}
        dbg["found"] = len(found)
        if not found:
            break
        found.sort()
        nearest = found[0][0]
        close = [(b, a) for gap, b, a in found if gap <= nearest + 0.5 * glyph]  # the nearest column's pieces
        axis = float(np.median([((b[0] + b[2]) if vertical else (b[1] + b[3])) / 2.0 for b, _a in close]))
        chosen = [(b, a) for _gap, b, a in found
                  if abs(((b[0] + b[2]) if vertical else (b[1] + b[3])) / 2.0 - axis) <= 0.5 * glyph]
        column = [b for b, _a in chosen]
        column.sort(key=lambda b: b[1] if vertical else b[0])
        pitch_ok = all((column[k + 1][1] - column[k][3] if vertical else column[k + 1][0] - column[k][2]) <= 1.5 * glyph
                       for k in range(len(column) - 1))
        dbg.update(chosen=len(column), pitch_ok=pitch_ok)
        if len(column) < 3 or not pitch_ok or max(max(b[2] - b[0], b[3] - b[1]) for b in column) < 0.5 * glyph:
            break  # a column is at least three pieces, one of them a good part of a glyph
        ux0, uy0 = min(b[0] for b in column), min(b[1] for b in column)
        ux1, uy1 = max(b[2] for b in column), max(b[3] for b in column)
        across = (ux1 - ux0) if vertical else (uy1 - uy0)
        box_ink = int(ink[uy0 - wy0:uy1 - wy0, ux0 - wx0:ux1 - wx0].sum())
        pieces_ink = sum(a for _b, a in chosen)
        solidity = float(np.median([a / max(1, (b[2] - b[0]) * (b[3] - b[1])) for b, a in chosen]))
        dbg.update(across=across, box_ink=box_ink, pieces_ink=pieces_ink, solidity=round(solidity, 2))
        if across > 1.3 * glyph:
            break  # wider than a column of glyphs: a drawing
        if box_ink - pieces_ink > 0.35 * pieces_ink:
            break  # strokes between the pieces (speed lines, hair) where a column of glyphs has clean ground
        tx0, ty0 = min([tx0] + [b[0] for b in column]), min([ty0] + [b[1] for b in column])
        tx1, ty1 = max([tx1] + [b[2] for b in column]), max([ty1] + [b[3] for b in column])
        taken.extend(column)
    return (tx0, ty0, tx1, ty1), len(taken), taken
