"""Lettering of two sizes in one bubble: whether a region's Japanese sets part of its text larger than the rest (a
word cried out, a name stressed: whole columns of a larger size beside the others), measured from the first reader's
character boxes (`ocr.charspot`), so that the translation can set its counterpart larger too (`TextRegion.large`,
`render.typeset`). Pure: no model, no pixels.

The rule (`find_mix`; measured on the dataset's 1,591 regions and 757 regions of real pages, 2 and 10 mixed by it, every
one right to the eye, no false one among them):

* only full-size kana and kanji measure a size (`category`): small kana, punctuation, long-vowel marks, dots, Latin
  letters and digits are set smaller, thinner or sideways;
* lettering is set one character to a cell of the size, whatever the glyph's own shape, so a line's size is its
  *pitch*: the median distance between the centres of neighbouring cell characters along it (`steps`: a step counts
  between `PITCH_LOW` and `PITCH_HIGH` times the larger box, not a gap, not two lines taken for one); a line without
  such a step measures nothing;
* the sizes measured part in two groups at the widest step in log size; the region is mixed when the big group's
  median is at least `RATIO` times the small group's (the base), the big group's characters run contiguous in reading
  order for `MIN_SPAN` full-size characters or more, the base's for `MIN_BASE` or more, and the glyphs themselves are
  larger too (`CONFIRM`: the span's own boxes, each over its class's share of a cell, `CELL_SHARE`) - a line set
  farther apart is no larger lettering;
* the span takes the punctuation that ends its last line along ("!!", "...").

The span is found in charspot's characters and given as a range of the region's settled text (`text_range`: the
readers may have changed a character or two), with its ratio capped at `CAP`. Kept on the region in memory only: it
indexes the Japanese, which is never written."""

from __future__ import annotations

import difflib
import math
import statistics
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

RATIO = 1.25  # the big part's size at least this many times the base's
CAP = 2.0  # the largest ratio kept (a cry four times the size is set twice)
MIN_SPAN = 2  # full-size characters in the big part at least ...
MIN_BASE = 2  # ... and in the base, each contiguous in reading order
CONFIRM = 1.15  # the big part's own glyphs (`cell_size`) at least this many times the base's
PITCH_LOW, PITCH_HIGH = 0.7, 1.8  # a step between two characters is a cell when this many times their larger box
MIN_CHARS = MIN_SPAN + MIN_BASE  # a reading shorter than this is never mixed

SMALL_KANA = frozenset("ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿｧｨｩｪｫｬｭｮｯ")
LONG_MARKS = frozenset("ー〜～―‐−-─━ｰ~")
SENTENCE_ENDS = frozenset("。．！？!?‼⁉｡")
COMMAS = frozenset("、，,､")
DOTS = frozenset("…‥・.･:：")
BRACKETS = frozenset("「」『』（）()【】〈〉《》［］[]〔〕\"'“”‘’")
CELL_CLASSES = frozenset("KHTs")  # set one to a cell of the size: kanji, hiragana, katakana, small kana
# A full-size character's box (its longer side) over the cell it is set in (the pitch of its line): the medians over
# the dataset's regions of four characters or more. A kana's ink is smaller than a kanji's at the same size.
CELL_SHARE = {"K": 0.943, "H": 0.870, "T": 0.843, "s": 0.692}


def category(ch: str) -> str:
    """The class of a character: "K" kanji, "H" hiragana, "T" katakana, "s" small kana, "L" a long-vowel mark or a
    dash, "E" a sentence end (a combined !? glyph too), "C" a comma, "D" dots, "Q" a bracket, "A" a Latin letter, "9" a
    digit, "O" anything else."""
    if not ch:
        return "O"
    if len(ch) > 1:
        return "E" if all(c in "!?！？" for c in ch) else category(ch[0])
    if ch in SMALL_KANA:
        return "s"
    c = unicodedata.normalize("NFKC", ch)
    for cls, members in (("L", LONG_MARKS), ("E", SENTENCE_ENDS), ("C", COMMAS), ("D", DOTS), ("Q", BRACKETS)):
        if ch in members or c in members:
            return cls
    if c.isdigit():
        return "9"
    if c.isascii() and c.isalpha():
        return "A"
    o = ord(ch)
    if 0x3041 <= o <= 0x309F:
        return "H"
    if 0x30A1 <= o <= 0x30FF or 0xFF66 <= o <= 0xFF9F:
        return "T"
    if 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or ch in "々〆ヶ":
        return "K"
    return "O"


def _full(cat: str) -> bool:
    return cat in ("K", "H", "T")


@dataclass(frozen=True)
class Glyph:
    """One character as the first reader found it: the character, its box on the page and its box's sides as read
    (upright, for a slanted region read turned)."""

    char: str
    box: tuple[float, float, float, float]
    w: float
    h: float

    @property
    def cat(self) -> str:
        return category(self.char)

    @property
    def side(self) -> float:
        """Its own size: the longer side of its box as read."""
        return max(self.w, self.h)

    @property
    def centre(self) -> tuple[float, float]:
        return (self.box[0] + self.box[2]) / 2.0, (self.box[1] + self.box[3]) / 2.0


@dataclass(frozen=True)
class SizeMix:
    """A region's big part: characters [start, end) of its settled text, *ratio* times the base's size (capped at
    `CAP`), the base's size (*base*, px: the pitch of its lines) and the base's glyphs' share of the region's median
    glyph (*base_share*: the size of the original lettering, `TextRegion.glyph`, times it is the base's); with the
    characters it was measured from and the part among them (*chars*, *span*), so that it maps onto another reading
    of the region too (`on`)."""

    start: int
    end: int
    ratio: float
    base: float
    base_share: float = 1.0
    chars: tuple[Glyph, ...] = field(default=(), compare=False, repr=False)
    span: tuple[int, int] = (0, 0)

    def on(self, text: str) -> "SizeMix | None":
        """The same part as a range of *text*, another reading of the region (the person's, corrected); None when
        it maps onto no part of it."""
        if not self.chars:
            return None
        at = _mapped(self.chars, self.span, text)
        return None if at is None else replace(self, start=at[0], end=at[1])


@dataclass
class Mix:
    """What `find_mix` found: per line the characters' indices in reading order, per character the size measured
    (None: none), the base's size, the big part's, and the big spans as character ranges [a, b)."""

    vertical: bool
    lines: list[list[int]]
    sizes: list[float | None]
    base: float
    big: float
    spans: list[tuple[int, int]]

    @property
    def ratio(self) -> float:
        return self.big / self.base if self.base else 1.0


def glyphs_of(chars: Sequence[Any], boxes: Sequence[Sequence[float]]) -> list[Glyph]:
    """The first reader's characters (`CharspotChar`: the character and its box in the crop) with their boxes on the
    page (*boxes*, `Pipeline._char_boxes`), as `Glyph`s."""
    return [Glyph(c.char, tuple(float(v) for v in b), float(c.box[2] - c.box[0]), float(c.box[3] - c.box[1]))
            for c, b in zip(chars, boxes)]


def is_vertical(chars: Sequence[Glyph]) -> bool:
    """Whether the characters run in columns: more steps from one to the next go down than go right."""
    down = right = 0
    for a, b in zip(chars, chars[1:]):
        (ax, ay), (bx, by) = a.centre, b.centre
        dx, dy = bx - ax, by - ay
        if abs(dy) > abs(dx):
            down += dy > 0
        else:
            right += dx > 0
    return down >= right


def split_lines(chars: Sequence[Glyph], vertical: bool) -> list[list[int]]:
    """The lines of *chars* in reading order: a new one where the next character does not follow on this one (in a
    column below it and not far aside, in a row right of it and not far up or down)."""
    if not chars:
        return []
    lines = [[0]]
    for i in range(1, len(chars)):
        a, b = chars[i - 1], chars[i]
        (ax, ay), (bx, by) = a.centre, b.centre
        s = max(a.side, b.side, 1.0)
        along, across = (by - ay, bx - ax) if vertical else (bx - ax, by - ay)
        if along > -0.3 * s and abs(across) < 0.6 * s:
            lines[-1].append(i)
        else:
            lines.append([i])
    return lines


def steps(chars: Sequence[Glyph], line: Sequence[int], vertical: bool) -> list[float]:
    """The steps that measure a *line*'s size: the distances along it between the centres of two cell characters one
    after the other that are a cell apart (`PITCH_LOW` to `PITCH_HIGH` times the larger of their boxes)."""
    out = []
    for i, j in zip(line, line[1:]):
        a, b = chars[i], chars[j]
        if a.cat not in CELL_CLASSES or b.cat not in CELL_CLASSES:
            continue
        (ax, ay), (bx, by) = a.centre, b.centre
        d = abs(by - ay) if vertical else abs(bx - ax)
        if PITCH_LOW * max(a.side, b.side, 1.0) <= d <= PITCH_HIGH * max(a.side, b.side, 1.0):
            out.append(d)
    return out


def line_sizes(chars: Sequence[Glyph], lines: Sequence[Sequence[int]], vertical: bool) -> list[float | None]:
    """Per character the size of its line, its pitch (the median of its steps), for the full-size kana and kanji of
    a line with a step; None for every other character."""
    out: list[float | None] = [None] * len(chars)
    for line in lines:
        st = steps(chars, line, vertical)
        if not st:
            continue
        pitch = statistics.median(st)
        for i in line:
            if _full(chars[i].cat):
                out[i] = pitch
    return out


def cell_size(c: Glyph) -> float:
    """The size a character was set at as its own box tells it: its longer side over its class's `CELL_SHARE`."""
    return c.side / CELL_SHARE.get(c.cat, 1.0)


def two_groups(values: Sequence[float]) -> tuple[list[float], list[float]]:
    """*values* parted in two at the widest step between neighbours in log size (the small group first)."""
    v = sorted(values)
    if len(v) < 2:
        return list(v), []
    gaps = [math.log(v[i + 1] / max(1e-6, v[i])) for i in range(len(v) - 1)]
    k = max(range(len(gaps)), key=lambda i: gaps[i])
    return v[: k + 1], v[k + 1:]


def _runs(sizes: Sequence[float | None], keep: Any, least: int) -> list[tuple[int, int]]:
    """The runs [a, b) of characters contiguous in reading order (those measuring nothing passed over) whose sizes
    *keep* says yes to, of at least *least* measured characters."""
    out: list[tuple[int, int]] = []
    start = last = None
    count = 0
    for i, s in enumerate(sizes):
        if s is None:
            continue
        if keep(s):
            if start is None:
                start, count = i, 0
            last, count = i, count + 1
        else:
            if start is not None and count >= least:
                out.append((start, last + 1))
            start = None
    if start is not None and count >= least:
        out.append((start, last + 1))
    return out


def find_mix(chars: Sequence[Glyph], ratio: float = RATIO) -> Mix:
    """Whether *chars* mix two sizes of lettering, and where the big spans are (see the module): the lines' sizes
    parted in two groups, mixed when the big group's median is *ratio* times the base's or more, a run of each group
    long enough and the big part's glyphs larger too. A span takes in what measures nothing inside it and the
    punctuation that ends its last line."""
    vertical = is_vertical(chars)
    lines = split_lines(chars, vertical)
    sizes = line_sizes(chars, lines, vertical)
    measured = [s for s in sizes if s is not None]
    same = statistics.median(measured) if measured else 0.0
    alike = Mix(vertical, lines, sizes, same, same, [])
    small, big = two_groups(measured)
    if not big:
        return alike
    base = statistics.median(small)
    cut = min(big)
    spans = _runs(sizes, lambda s: s >= cut, MIN_SPAN)
    if not spans or not _runs(sizes, lambda s: s < cut, MIN_BASE) or statistics.median(big) < ratio * base:
        return alike
    inside = {i for a, b in spans for i in range(a, b)}
    own_big = [cell_size(chars[i]) for i in inside if sizes[i] is not None]
    own_base = [cell_size(chars[i]) for i, s in enumerate(sizes) if s is not None and i not in inside]
    if not own_big or not own_base or statistics.median(own_big) < CONFIRM * statistics.median(own_base):
        return alike  # set farther apart, not larger: a space, a gap
    line_of = {i: k for k, line in enumerate(lines) for i in line}
    grown = []
    for a, b in spans:  # the punctuation that ends a span's last line ("!!", "...") belongs to it
        nxt = next((i for i in range(b, len(chars)) if sizes[i] is not None), len(chars))
        if nxt == len(chars) or line_of[nxt] != line_of[b - 1]:
            while b < nxt and line_of[b] == line_of[b - 1]:
                b += 1
        grown.append((a, b))
    return Mix(vertical, lines, sizes, base, statistics.median(big), grown)


def text_range(chars: Sequence[Glyph], a: int, b: int, text: str) -> tuple[int, int]:
    """The characters [a, b) of *chars* as a range of *text*, the region's settled reading: each character written as
    the OCR writes its text (`charspot.written`), aligned to *text*, so that a reading the other readers changed a
    little still maps."""
    from .ocr.charspot import written

    pieces = [written(c.char) if c.char.strip() else c.char for c in chars]
    starts = [0]
    for p in pieces:
        starts.append(starts[-1] + len(p))
    whole = "".join(pieces)
    to_text = [0] * (len(whole) + 1)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, whole, text, autojunk=False).get_opcodes():
        for k in range(i1, i2 + 1):
            if tag == "equal":
                to_text[k] = j1 + (k - i1)
            elif tag == "replace":
                to_text[k] = j1 + round((k - i1) * (j2 - j1) / max(1, i2 - i1))
            elif tag == "delete":
                to_text[k] = j1
            else:  # an insert: no character of the reader's here
                to_text[k] = j2 if k == i2 else j1
    to_text[len(whole)] = len(text)
    return to_text[starts[a]], to_text[starts[b]]


def _mapped(chars: Sequence[Glyph], span: tuple[int, int], text: str) -> tuple[int, int] | None:
    """The characters *span* of *chars* as a range of *text* (`text_range`); None when that is nothing but spaces,
    or all of the text."""
    start, end = text_range(chars, span[0], span[1], text)
    if not text[start:end].strip() or not (text[:start].strip() or text[end:].strip()):
        return None
    return start, end


def measure(chars: Sequence[Glyph], text: str, ratio: float = RATIO, cap: float = CAP) -> SizeMix | None:
    """The big part of the region read as *text* from *chars* (`find_mix`), the largest when there are several, as a
    range of *text* (`text_range`) with its ratio capped at *cap* (0: not capped); None when its lettering is of one
    size, or the part does not map to a part of *text* (all of it, or nothing but spaces)."""
    if len(chars) < MIN_CHARS or not text.strip():
        return None
    mix = find_mix(chars, ratio)
    if not mix.spans:
        return None
    a, b = max(mix.spans, key=lambda s: sum(1 for i in range(*s) if mix.sizes[i] is not None))
    at = _mapped(chars, (a, b), text)
    if at is None:
        return None
    inside = set(range(a, b))
    base_sides = [chars[i].side for i, s in enumerate(mix.sizes) if s is not None and i not in inside]
    all_sides = [c.side for c in chars]
    share = statistics.median(base_sides) / max(1e-6, statistics.median(all_sides)) if base_sides else 1.0
    r = mix.ratio if not cap else min(cap, mix.ratio)
    return SizeMix(at[0], at[1], round(r, 3), round(mix.base, 2), round(min(1.0, share), 3), tuple(chars), (a, b))
