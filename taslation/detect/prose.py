"""Lettering set across: its lines, and the paragraphs they make, found in the ink of a part of the page.

Manga lettering runs down, and the detectors are made for it. Lines set across - an explanation page's numbered
paragraphs, a contents list, a chapter's label on a band - come out of them badly: the classical text blocks
(`detect.textblocks`) take a block of rows for a list and cut it into its rows (`TextBlockConfig.list_pitch`), and a
row at its gaps, where the strokes of glyphs about 13 px high fall apart into pieces the block leaves out, so a
paragraph is read as a few pieces, some of its lines in none; the layout model finds such paragraphs with a score
under the one its text boxes are trusted from (`detect.layout.TEXT_SCORE`). Here the lines are found in the ink
itself, round lettering a reading already found (`taslation.pipeline.Pipeline._prose`): the pieces of ink of glyph
size, joined along a line across gaps up to `LINE_GAP` glyphs (no further: lines a line pitch apart stay apart), make
a line when they run across (`ACROSS`) at the height of a line of lettering (`LINE_LOW` to `LINE_HIGH` glyphs, a large
numeral among small kanji included); the lines one under the other, alike in height and lying under each other,
make a paragraph (`PARA_GAP`, `PARA_SIZE`, `PARA_OVERLAP`). Furigana over a line (a thin line just above it) is the
line's (`RUBY_REACH`). A paragraph is read as one crop, which charspot reads in line order (on the real page this
was built for, the four paragraphs read whole were their lines read one by one, character for character).

Pure image work on a part of the page: a few milliseconds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

from ..regions import Box

LINE_GAP = 1.5  # glyphs: a gap along a line up to this wide joins its parts (a heading set loose, a full-width space,
#                a full stop too thin at a small size to be ink: a character's room empty)
LINE_LOW, LINE_HIGH = 0.5, 2.5  # glyphs: the height of a line (of its tallest character) lies between these
ACROSS = 2.0  # a line is this many times as wide as it is high at least ...
LINE_PARTS = 2  # ... and is made of this many pieces of ink at least (a short last line of a paragraph needs one)
PART_TALL, PART_WIDE = 2.4, 3.0  # glyphs: a piece of ink taller or wider than this is no glyph's (a rule, a frame)
RULE_FLAT, RULE_GAP = 0.25, 0.5  # glyphs: a flat piece set off this far at a line's end is a rule (`_without_rules`)
RUBY_REACH = 0.5  # glyphs: a line lower than `LINE_LOW` this near above a line is its furigana
PARA_GAP = 1.0  # line heights: the next line of a paragraph begins this near under the last one ...
PARA_SIZE = 1.5  # ... their heights this alike (a heading and its subtitle are two paragraphs) ...
PARA_OVERLAP = 0.3  # ... and it lies under the last one for this share of the narrower's width
GRID_GAP = 0.3  # line heights: lines closer than this one under the other may be the rows of lettering set down ...
SPAN_JOIN = 0.15  # glyphs: (pieces of ink this near side by side are one glyph's, for a line's `Line.spacing`)


@dataclass(frozen=True)
class Line:
    """A line of lettering set across: its box (in the coordinates of the `Ink` it was found in) and its pieces (labels
    of that ink); *short*: too short to run across on its own (a paragraph's last line), it only continues one."""

    box: Box
    parts: tuple[int, ...]
    short: bool = False
    spacing: float = 0.0  # px: the median gap between its glyphs (0 for lettering set tight: its glyphs touch nearly)

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]


@dataclass(frozen=True)
class Paragraph:
    """Lines one under the other, top first; *rows*: lines that may be the rows of lettering set down as well, or a
    list set loose (see `paragraphs`): never a paragraph of prose."""

    lines: tuple[Line, ...]
    rows: bool = False

    @property
    def box(self) -> Box:
        return (min(ln.box[0] for ln in self.lines), min(ln.box[1] for ln in self.lines),
                max(ln.box[2] for ln in self.lines), max(ln.box[3] for ln in self.lines))

    @property
    def parts(self) -> list[int]:
        return [p for ln in self.lines for p in ln.parts]


@dataclass
class Ink:
    """The pieces of ink of a part of the page (*area*, page coordinates): its grey (inverted for light lettering on a
    dark ground, so that lettering is dark), and the pieces darker than the threshold (``cv2`` labels and stats), as the
    classical text blocks see them (`detect.textblocks.block_mask` takes them)."""

    area: Box
    gray: np.ndarray
    labels: np.ndarray
    stats: np.ndarray

    @property
    def origin(self) -> tuple[int, int]:
        return self.area[0], self.area[1]

    def on_page(self, box: Box) -> Box:
        x, y = self.origin
        return box[0] + x, box[1] + y, box[2] + x, box[3] + y


def ink_of(gray: np.ndarray, area: Box, dark: bool, dark_threshold: int = 140) -> Ink:
    """The `Ink` of *area* of the page's grey *gray*; *dark*: light lettering on a dark ground."""
    x0, y0, x1, y1 = area
    g = gray[y0:y1, x0:x1]
    if dark:
        g = 255 - g
    _n, labels, stats, _ = cv2.connectedComponentsWithStats((g < dark_threshold).astype(np.uint8), connectivity=8,
                                                            ltype=cv2.CV_32S)
    return Ink(area, np.ascontiguousarray(g), labels, stats)


def _without_rules(ids: list[int], stats: np.ndarray, glyph: float) -> list[int]:
    """The pieces *ids* of a line (left to right, by their left edges) without a rule at either end. The line falls
    into runs of pieces, a run ending where the next piece begins `RULE_GAP` glyphs or more past it; a run at an end
    that is flat (`RULE_FLAT` glyphs high at most and twice as wide at least: a rule, a dash of one, a rule printed in
    two pieces or anti-aliased into a dot and a stroke) goes, and so does the next one in while it is flat too (a long
    rule and a short dash before a contents list's label), as long as a run is left. A long vowel mark, and the kanji
    for one, lie right by their neighbours: in a run of the line's own."""
    if len(ids) < 2:
        return ids
    set_off = RULE_GAP * glyph
    runs: list[list[int]] = []
    right = 0
    for i in ids:
        x0, x1 = int(stats[i, 0]), int(stats[i, 0] + stats[i, 2])
        if runs and x0 - right < set_off:
            runs[-1].append(i)
            right = max(right, x1)
        else:
            runs.append([i])
            right = x1

    def flat(run: list[int]) -> bool:
        top = min(int(stats[i, 1]) for i in run)
        bottom = max(int(stats[i, 1] + stats[i, 3]) for i in run)
        width = max(int(stats[i, 0] + stats[i, 2]) for i in run) - min(int(stats[i, 0]) for i in run)
        return bottom - top <= RULE_FLAT * glyph and width >= 2 * (bottom - top)

    start, end = 0, len(runs)
    while end - start > 1 and flat(runs[start]):
        start += 1
    while end - start > 1 and flat(runs[end - 1]):
        end -= 1
    return [i for run in runs[start:end] for i in run]


def glyph_of(paragraph: "Paragraph", scale: float) -> float:
    """The size of *paragraph*'s lettering: the median height of its lines (a line set across is as high as its
    tallest characters), held within 0.6 and 1.6 times the *scale* it was looked for at."""
    height = float(np.median([ln.height for ln in paragraph.lines]))
    return float(min(1.6 * scale, max(0.6 * scale, height)))


def _spacing(ids: list[int], stats: np.ndarray, glyph: float) -> float:
    """The median gap between the glyphs of a line of the pieces *ids*: their spans side by side, those `SPAN_JOIN`
    glyphs apart or nearer joined (the strokes of one glyph); 0 when they make one span."""
    spans: list[list[int]] = []
    for i in sorted(ids, key=lambda i: int(stats[i, 0])):
        x0, x1 = int(stats[i, 0]), int(stats[i, 0] + stats[i, 2])
        if spans and x0 - spans[-1][1] <= SPAN_JOIN * glyph:
            spans[-1][1] = max(spans[-1][1], x1)
        else:
            spans.append([x0, x1])
    gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:])]
    return float(np.median(gaps)) if gaps else 0.0


def lines_across(ink: Ink, glyph: float) -> list[Line]:
    """The lines set across in *ink*, for lettering of about *glyph* px (a character's longer side). A piece that
    reaches the edge of the ink's area goes on past it (the drawing, a frame, a line cut off) and is left out."""
    stats = ink.stats
    h, w = ink.labels.shape
    n = len(stats)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < 2 or bh > PART_TALL * glyph or bw > PART_WIDE * glyph:
            continue
        if x <= 0 or y <= 0 or x + bw >= w or y + bh >= h:
            continue
        keep[i] = True
    if not keep.any():
        return []
    parts = keep[ink.labels]
    reach = max(3, int(round(LINE_GAP * glyph)))
    joined = cv2.dilate(parts.astype(np.uint8), np.ones((1, reach), np.uint8))
    _m, blobs = cv2.connectedComponents(joined, connectivity=8)
    owner = np.zeros(n, np.int64)
    owner[ink.labels[parts]] = blobs[parts]
    members: dict[int, list[int]] = {}
    for i in np.nonzero(keep)[0]:
        members.setdefault(int(owner[i]), []).append(int(i))
    lines: list[Line] = []
    low: list[Line] = []
    for ids in members.values():
        ids = _without_rules(sorted(ids, key=lambda i: int(stats[i, 0])), stats, glyph)
        if not ids:
            continue
        x0 = min(int(stats[i, 0]) for i in ids)
        y0 = min(int(stats[i, 1]) for i in ids)
        x1 = max(int(stats[i, 0] + stats[i, 2]) for i in ids)
        y1 = max(int(stats[i, 1] + stats[i, 3]) for i in ids)
        line = Line((x0, y0, x1, y1), tuple(ids), spacing=_spacing(ids, stats, glyph))
        if line.height < LINE_LOW * glyph:
            if len(ids) >= LINE_PARTS and line.width >= ACROSS * line.height:
                low.append(line)
            continue
        if line.height > LINE_HIGH * glyph:
            continue
        if len(ids) >= LINE_PARTS and line.width >= ACROSS * line.height:
            lines.append(line)
        else:
            lines.append(Line(line.box, line.parts, short=True, spacing=line.spacing))
    for ruby in low:  # furigana just above a line, no wider than it: the line's
        for k, line in enumerate(lines):
            gap = line.box[1] - ruby.box[3]
            if (0 <= gap <= RUBY_REACH * glyph and ruby.box[0] >= line.box[0] - RUBY_REACH * glyph
                    and ruby.box[2] <= line.box[2] + RUBY_REACH * glyph):
                b = line.box
                lines[k] = Line((min(b[0], ruby.box[0]), ruby.box[1], max(b[2], ruby.box[2]), b[3]),
                                line.parts + ruby.parts, line.short, line.spacing)
                break
    return lines


def paragraphs(lines: Sequence[Line]) -> list[Paragraph]:
    """*lines* made into paragraphs: each line goes on the paragraph whose last line lies right above it, as high as
    it nearly and over it (see the module); a short line only goes on one, it never begins one. Lettering set down on
    a grid makes lines too, the characters of its columns side by side, but one right under the other, closer than
    the gaps between them: a paragraph with two lines nearer than `GRID_GAP` line heights, or than the spacing of their
    glyphs (`Line.spacing`), is *rows* (lettering set across has more room between its lines than between its
    characters, half a line or so; a column's characters nearly touch, its columns stand apart). A list set loose,
    its rows nearer than its characters, is *rows* too: its reading tells it (`taslation.pipeline.Pipeline._prose`)."""
    out: list[list[Line]] = []
    rows: list[bool] = []
    for line in sorted(lines, key=lambda ln: (ln.box[1], ln.box[0])):
        home = None
        for k, p in enumerate(out):
            last = p[-1]
            hi, lo = max(line.height, last.height), max(1, min(line.height, last.height))
            gap = line.box[1] - last.box[3]
            over = min(line.box[2], last.box[2]) - max(line.box[0], last.box[0])
            if (-0.3 * lo <= gap <= PARA_GAP * hi and hi <= PARA_SIZE * lo
                    and over >= PARA_OVERLAP * min(line.width, last.width)):
                home = k
                rows[k] = rows[k] or gap < max(GRID_GAP * lo, line.spacing, last.spacing)
                break
        if home is not None:
            out[home].append(line)
        elif not line.short:
            out.append([line])
            rows.append(False)
    return [Paragraph(tuple(p), grid) for p, grid in zip(out, rows)]


__all__ = ["ACROSS", "Ink", "LINE_GAP", "Line", "PARA_GAP", "Paragraph", "glyph_of", "ink_of", "lines_across",
           "paragraphs"]
