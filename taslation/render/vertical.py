"""Stacked lettering: vertical writing set column by column, the glyphs upright and one below the other, the columns
running from right to left (`RegionStyle.direction` "stacked", a word processor's "Stacked" text direction).

For Japanese, Chinese and Korean translations, and for Latin letters stacked one per row (a book's spine, a sign).
Each glyph takes a square cell of the font size; a column is as many cells as the region's mask is high at that
column (the bubble's shape followed, as `typeset.shape_layout` follows it for rows), kept `STACK_PAD` off its edge,
and the columns sit side by side round the middle of the mask (or of the original lettering, for text on the page).
The size is the largest between the limits at which the text fits in as many columns as the mask is wide; a fixed
size from the editor is never shrunk. A line break starts a new column.

The vertical rules followed: a long-vowel mark, a dash, a wave dash, an ellipsis and brackets take their vertical
form - the Unicode presentation form (U+FE10-FE19, U+FE30-FE4F) when the font has it, else the horizontal glyph
turned a quarter clockwise (what a font's ``vert`` feature does; Pillow cannot ask for that feature without libraqm,
so it is not used); small kana sit to the upper right of their cell and the ideographic comma and full stop in its
upper right corner, unless the font has their vertical forms; a mark that may not start a line (`_NO_LINE_START`)
hangs at the foot of the column before rather than heading a new one; Latin letters and digits stand upright, one
per cell. Not handled: tate-chu-yoko (two or three digits set across one cell), ruby, proportional vertical
metrics (``vmtx``) and the font's own ``vert`` substitutions, emphasis marks (*stressed words* are set plain), and
the reader's alignment left, centre or right (the columns are centred; top, middle and bottom move each column in
its run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..regions import Box, TextRegion
from .fonts import covers
from .lettering import Lettering, strip_marks, styled_font

# the vertical presentation form of a horizontal character (used when the font has it)
VERTICAL_FORMS = {
    "，": "︐", "、": "︑", "。": "︒", "：": "︓", "；": "︔", "！": "︕", "？": "︖",
    "〖": "︗", "〗": "︘", "…": "︙", "‥": "︰", "—": "︱", "–": "︲", "＿": "︳",
    "（": "︵", "）": "︶", "(": "︵", ")": "︶", "｛": "︷", "｝": "︸", "{": "︷",
    "}": "︸", "〔": "︹", "〕": "︺", "【": "︻", "】": "︼", "《": "︽", "》": "︾",
    "〈": "︿", "〉": "﹀", "「": "﹁", "」": "﹂", "『": "﹃", "』": "﹄", "［": "﹇",
    "］": "﹈", "[": "﹇", "]": "﹈",
}
# turned a quarter clockwise when the font has no vertical form for them (the long-vowel mark never has one)
TURNED = frozenset("ー－-‐―—–~～〜…‥=＝<>＜＞→←") | frozenset(VERTICAL_FORMS) - frozenset("，、。：；！？")
SMALL_KANA = frozenset("ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ")
CORNER_MARKS = frozenset("、。，．､｡")  # in the upper right corner of their cell
NO_COLUMN_START = frozenset("、。，．・：；！？!?)）」』】〉》〕］}｝ー〜～…‥ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ")
STACK_PAD = 0.05  # of the mask's smaller side: how far the columns keep off its edge
SMALL_SHIFT = 0.12  # of the size: how far a small kana moves right and up in its cell
CORNER_SHIFT = 0.5  # of the size: how far a comma or full stop moves right and up (no vertical form)


@dataclass
class Cell:
    """One glyph of stacked lettering: what is drawn (*shown*), whether it is turned a quarter clockwise, and its
    cell's top left corner (mask coordinates)."""

    shown: str
    turned: bool
    x: float
    y: float
    shift: tuple[float, float] = (0.0, 0.0)  # of the size, right and up


@dataclass
class Stacked:
    """Where stacked lettering is set in a mask: the font, its size (a cell's side), the cells, the room between two
    columns' middles, and whether the text overflows its room (set at the smallest or the fixed size past it: the
    caller cuts it at the mask)."""

    font: Any
    size: int
    cells: list[Cell] = field(default_factory=list)
    advance: float = 0.0
    overflow: bool = False

    def box(self) -> Box | None:
        """The box the cells take (mask coordinates)."""
        if not self.cells:
            return None
        return (int(min(c.x for c in self.cells)), int(min(c.y for c in self.cells)),
                int(max(c.x for c in self.cells) + self.size) + 1, int(max(c.y for c in self.cells) + self.size) + 1)


def vertical_glyph(ch: str, path: str | None) -> tuple[str, bool]:
    """What stands for *ch* in a column: its vertical presentation form when the font at *path* has it, else the
    character itself, turned a quarter clockwise when it is one of `TURNED`."""
    form = VERTICAL_FORMS.get(ch)
    if form is not None and path and covers(path, form):
        return form, False
    return ch, ch in TURNED


def stack_cells(text: str) -> list[list[str]]:
    """The characters of *text* as stacked lettering sets them, one paragraph per line of the text: emphasis markers
    dropped, "..." as an ellipsis, a run of spaces one empty cell, none at a paragraph's ends."""
    paras = []
    for line in strip_marks(text).replace("...", "…").split("\n"):
        cells: list[str] = []
        for ch in line.strip():
            if ch.isspace():
                if cells and cells[-1] != " ":
                    cells.append(" ")
            else:
                cells.append(ch)
        paras.append(cells)
    return paras


def fill_columns(paras: list[list[str]], rooms: list[int]) -> list[list[str]] | None:
    """The cells of *paras* poured into columns of *rooms* cells each (the first column the rightmost): a paragraph
    starts a new column, a space does not head one, and a mark that may not start a line hangs at the foot of the
    column before. None when the columns run out."""
    columns: list[list[str]] = []
    room_at = 0
    for cells in paras:
        if room_at >= len(rooms):
            return None
        columns.append([])
        room_at += 1
        for ch in cells:
            column = columns[-1]
            if len(column) >= rooms[room_at - 1]:
                if ch == " ":
                    continue
                if ch in NO_COLUMN_START and column:
                    column.append(ch)  # hung at the foot of the full column
                    continue
                if room_at >= len(rooms):
                    return None
                columns.append([])
                room_at += 1
                column = columns[-1]
            if ch == " " and not column:
                continue
            column.append(ch)
    for column in columns:
        while column and column[-1] == " ":
            column.pop()
    return columns


def _runs(inside: np.ndarray, x0: int, x1: int, cy: float, pad: int) -> tuple[int, int]:
    """The rows (top, bottom) of the run of the mask that holds the band of columns x0..x1 whole and is nearest the
    row *cy*, *pad* kept off its ends; (0, 0) when there is none."""
    h, w = inside.shape
    x0, x1 = max(0, x0), min(w, x1)
    if x1 <= x0:
        return (0, 0)
    rows = inside[:, x0:x1].all(axis=1)
    if not rows.any():
        return (0, 0)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], rows.astype(np.int8), [0]))))
    spans = list(zip(edges[0::2], edges[1::2]))
    top, bottom = min(spans, key=lambda s: 0 if s[0] <= cy < s[1] else min(abs(cy - s[0]), abs(cy - s[1])))
    return (int(top) + pad, int(bottom) - pad)


def _place(columns: list[list[str]], spans: list[tuple[int, int]], xs: list[float], size: int, valign: str,
           path: str | None) -> list[Cell]:
    """The cells of *columns*, each column at its middle *xs* in its run of *spans*, at the top, the middle or the
    bottom of it as *valign* says."""
    out: list[Cell] = []
    for column, (top, bottom), x in zip(columns, spans, xs):
        tall = len(column) * size
        y = float(top) if valign == "top" else bottom - tall if valign == "bottom" else (top + bottom - tall) / 2.0
        for i, ch in enumerate(column):
            if ch == " ":
                continue
            shown, turned = vertical_glyph(ch, path)
            shift = (0.0, 0.0)
            if shown == ch and ch in CORNER_MARKS:
                shift = (CORNER_SHIFT, CORNER_SHIFT)
            elif ch in SMALL_KANA:
                shift = (SMALL_SHIFT, SMALL_SHIFT)
            out.append(Cell(shown, turned, x - size / 2.0, y + i * size, shift))
    return out


def layout_stacked(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int = 9,
                   max_size: int = 64, line_spacing: float = 1.12, bold_variation: bool = False,
                   centre: tuple[float, float] | None = None, size: int = 0, valign: str = "middle") -> Stacked:
    """Where and how large *text* is set in *mask* as stacked lettering (see the module): the largest size between
    *min_size* and *max_size* (or *size*, fixed) at which its columns, *line_spacing* times the size apart, fit the
    mask round *centre* (the mask's centroid by default); at the smallest or the fixed size, a text that does not fit
    is set in the mask's bounding box all the same, marked as overflowing."""
    paras = stack_cells(text)
    inside = mask > 0
    h, w = inside.shape
    ys, xs = np.nonzero(inside)
    if centre is None:
        centre = (float(xs.mean()), float(ys.mean())) if xs.size else (w / 2.0, h / 2.0)
    cx, cy = centre
    pad = int(round(STACK_PAD * min(h, w)))
    path = font_path.path if isinstance(font_path, Lettering) else font_path
    lo, hi = (size, size) if size else (min_size, max(min_size, max_size))
    s = hi
    while s >= lo:
        advance = max(1.0, s * line_spacing)
        most = max(1, int((w - 2 * pad) // advance))
        for k in range(1, most + 1):
            mids = [cx + (k - 1) / 2.0 * advance - i * advance for i in range(k)]
            spans = [_runs(inside, int(round(m - s / 2.0)), int(round(m + s / 2.0)), cy, pad) for m in mids]
            rooms = [max(0, (b - t) // s) for t, b in spans]
            columns = fill_columns(paras, rooms)
            if columns is not None and all(len(c) <= r + 1 for c, r in zip(columns, rooms)):
                font = styled_font(font_path, s, bold_variation)
                return Stacked(font, s, _place(columns, spans, mids[:len(columns)], s, valign, path), advance)
        s -= 1 if s <= 24 else 2
    # it does not fit: at the smallest (or the fixed) size in the bounding box, cut at the mask by the caller
    s = lo
    advance = max(1.0, s * line_spacing)
    bx0, by0, bx1, by1 = ((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if xs.size
                          else (0, 0, w, h))
    per = max(1, (by1 - by0) // s)
    total = sum(len(p) for p in paras) + len(paras)
    k = max(1, -(-total // per))
    columns = None
    while columns is None and k < 4096:
        columns = fill_columns(paras, [per] * k)
        k *= 2
    columns = columns or []
    mids = [cx + (len(columns) - 1) / 2.0 * advance - i * advance for i in range(len(columns))]
    font = styled_font(font_path, s, bold_variation)
    return Stacked(font, s, _place(columns, [(by0, by1)] * len(columns), mids, s, valign, path), advance, True)


def _draw_cell(image: Image.Image, font: Any, size: int, cell: Cell, x0: float, y0: float,
               fill: Any, outline: tuple[Any, int] | None) -> None:
    """One cell drawn on *image* at (x0, y0) plus its place: the glyph in the middle of its cell (moved by its
    shift), or turned a quarter clockwise about the middle."""
    ascent, descent = font.getmetrics()
    tall = ascent + descent
    wide = font.width(cell.shown)
    left = x0 + cell.x + cell.shift[0] * size
    top = y0 + cell.y - cell.shift[1] * size
    if not cell.turned:
        font.draw(image, left + (size - wide) / 2.0, top + (size - tall) / 2.0, cell.shown, fill, outline)
        return
    side = 3 * max(size, tall, wide)
    mid = side / 2.0
    layers = ([(outline[0], (255, outline[1]))] if outline is not None else []) + [(fill, None)]
    for colour, contour in layers:
        mask = Image.new("L", (side, side), 0)
        font.draw(mask, mid - wide / 2.0, mid - tall / 2.0, cell.shown, 255, contour)
        mask = mask.rotate(-90, resample=Image.BICUBIC, center=(mid, mid))
        image.paste(colour, (int(round(left + size / 2.0 - mid)), int(round(top + size / 2.0 - mid))), mask)


def draw_stacked(image: Image.Image, region: TextRegion, stacked: Stacked, color: tuple[int, int, int],
                 outline: bool | None, busy: Any, outline_color: tuple[int, int, int] | None = None) -> None:
    """The cells of *stacked* drawn in *region* on *image* in *color*, with an outline on a drawing in *outline_color*
    (None: the opposite colour, white round dark letters and black round light ones; *outline* None: as *busy* says
    of the box the cells take on the page); overflowing lettering is drawn on a copy of the region and only what lies
    inside its mask goes on the page."""
    font, size = stacked.font, stacked.size
    box = stacked.box()
    if box is None:
        return
    if outline is None:
        outline = busy(image, (region.x0 + box[0], region.y0 + box[1], region.x0 + box[2], region.y0 + box[3]))
    if outline_color is None:
        light = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2] >= 128
        outline_color = (0, 0, 0) if light else (255, 255, 255)
    contour = (tuple(outline_color), max(1, round(size / 12))) if outline else None
    if not stacked.overflow:
        for cell in stacked.cells:
            _draw_cell(image, font, size, cell, region.x0, region.y0, color, contour)
        return
    part = image.crop((region.x0, region.y0, region.x1, region.y1))
    for cell in stacked.cells:
        _draw_cell(part, font, size, cell, 0, 0, color, contour)
    mask = region.mask
    if mask.shape != (part.height, part.width):
        mask = cv2.resize(mask, (part.width, part.height), interpolation=cv2.INTER_NEAREST)
    image.paste(part, (region.x0, region.y0), Image.fromarray(np.where(mask > 0, 255, 0).astype(np.uint8)))


def letter_stacked(image: Image.Image | None, region: TextRegion, text: str, font_path: str | Lettering | None,
                   min_size: int = 9, max_size: int = 64, line_spacing: float = 1.12,
                   color: tuple[int, int, int] = (0, 0, 0), bold_variation: bool = False,
                   outline: bool | None = None, centre: tuple[float, float] | None = None, size: int = 0,
                   valign: str = "middle", busy: Any = None,
                   outline_color: tuple[int, int, int] | None = None) -> tuple[int, bool]:
    """Letter *text* in *region* as stacked lettering (`layout_stacked`; on no *image*: only how large), in *color*
    with an outline in *outline_color* (None: the opposite colour) as *outline* says (`draw_stacked`). Returns the
    size and whether it overflowed its room."""
    stacked = layout_stacked(region.mask, text, font_path, min_size, max_size, line_spacing, bold_variation, centre,
                             size, valign)
    if image is not None:
        draw_stacked(image, region, stacked, color, outline, busy or (lambda _im, _box: False), outline_color)
    return stacked.size, stacked.overflow


def stacked_room(mask: np.ndarray, size: int, line_spacing: float = 1.12,
                 centre: tuple[float, float] | None = None) -> int:
    """How many cells of stacked lettering at *size* the mask holds (`layout_stacked`'s columns, as many as fit)."""
    inside = mask > 0
    h, w = inside.shape
    ys, xs = np.nonzero(inside)
    if centre is None:
        centre = (float(xs.mean()), float(ys.mean())) if xs.size else (w / 2.0, h / 2.0)
    pad = int(round(STACK_PAD * min(h, w)))
    advance = max(1.0, size * line_spacing)
    k = max(1, int((w - 2 * pad) // advance))
    mids = [centre[0] + (k - 1) / 2.0 * advance - i * advance for i in range(k)]
    total = 0
    for m in mids:
        t, b = _runs(inside, int(round(m - size / 2.0)), int(round(m + size / 2.0)), centre[1], pad)
        total += max(0, (b - t) // size)
    return total
