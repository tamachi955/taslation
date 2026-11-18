"""Lettering with a part set larger: the part of a translation whose Japanese was lettered larger than the rest of its
bubble (`TextRegion.large`: a range of the translation and how many times larger), set as its own paragraph between
the rest's, each paragraph at one size: the rest at a base size s, the part at round(s x ratio) (`parts_of` cuts the
text in up to three: before, the part, after).

The block follows the bubble's body as the one-size lettering does (`typeset._bodies`: the tail cut off, two bubbles
joined at a neck tried one by one too): each line as wide as the body is round one centre axis over the rows its ink
covers, the ink `typeset.MARGIN_EM` of its own size off the outline, the block centred on the body's centroid (or at
the top or the bottom as the reader formatted it). The words of each paragraph go on its lines in their order, as many
on a line as fit, then shared out evenly over that many lines (the narrowest rooms at which they still fit); a word is
never split nor hyphenated, and the text is never condensed here: where the part does not fit so, the bubble is set
at one size as always.

The size: the largest base s within the limits (*max_size*, the page's cap, holds the base) at which the block fits
with the part at the full ratio; where that would take the base under *floor* (the readable size), the ratio shrinks
toward 1 first, the base kept at the floor; under `MIN_RATIO` the bubble is set at one size (`layout_large` gives
None, and the caller letters the text as it does without a part). The size a bubble so lettered reports is its base's.

Vertical (stacked) lettering is `render.vertical.layout_stacked_large`, column by column the same way."""

from __future__ import annotations

import functools
import hashlib
import math
import threading
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from ..regions import Box, TextRegion
from .lettering import Lettering, emphasis_marks, styled_font

MIN_RATIO = 1.15  # a part fitting only under this many times the base's size is not set larger at all
RATIO_CAP = 2.0  # nor more than this many times larger
RATIO_PRECISION = 0.02  # how finely a ratio is shrunk to fit
LAYOUTS_KEPT = 256  # layouts remembered (a page's measure for its caps, then its lettering)
_LAYOUTS: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
_LAYOUTS_LOCK = threading.Lock()


# ------------------------------------------------------------------ the text cut in parts

def _stressed(text: str) -> list[bool | None]:
    """Per character of *text*, whether it is in a stressed run (*marked like this*, `lettering.split_runs`); None
    for an emphasis marker itself."""
    marks = emphasis_marks(text)
    out: list[bool | None] = [False] * len(text)
    if not marks:
        return out
    first = marks[0]
    before = first > 0 and not text[first - 1].isspace() and text[first - 1] != "*"
    after = first + 1 < len(text) and not text[first + 1].isspace() and text[first + 1] != "*"
    on = before and not after  # a text that begins inside a span has a closer first
    marked = set(marks)
    for i in range(len(text)):
        if i in marked:
            out[i] = None
            on = not on
        else:
            out[i] = on
    return out


def _part(text: str, stressed: list[bool | None], a: int, b: int) -> str:
    """*text*[a:b] with its stressed runs marked anew, each between its own pair of markers (a run cut by the part's
    edge closed or opened there), stripped of the spaces at its ends."""
    out: list[str] = []
    run: list[str] = []
    on = False

    def close() -> None:
        if not run:
            return
        piece = "".join(run)
        if on and piece.strip():
            core = piece.strip()
            lead = piece[: len(piece) - len(piece.lstrip())]
            tail = piece[len(piece.rstrip()):]
            out.append(f"{lead}*{core}*{tail}")
        else:
            out.append(piece)
        run.clear()

    for i in range(a, b):
        flag = stressed[i]
        if flag is None:
            continue
        if flag != on:
            close()
            on = flag
        run.append(text[i])
    close()
    return "".join(out).strip()


def _clings(ch: str) -> bool:
    """Whether *ch*, right after the part, goes with it: a mark that closes or follows (a comma, a full stop, a
    closing quote or bracket, a dash, a tilde, a symbol, a combining sign), not a letter, a digit, a space or a mark
    that opens what follows."""
    cat = unicodedata.category(ch)
    return cat in ("Po", "Pe", "Pf", "Pd", "So", "Mn", "Mc", "Me") or ch in "~～"


def _opens(text: str, i: int) -> bool:
    """Whether *text*[i], right before the part, opens it and goes with it: an opening quote or bracket, ¡ or ¿, or
    a straight quote at the text's start or after a space."""
    ch = text[i]
    if ch in "\"'":
        return i == 0 or text[i - 1].isspace()
    return unicodedata.category(ch) in ("Ps", "Pi") or ch in "¡¿"


def parts_of(text: str, large: tuple[int, int, float] | None) -> list[tuple[str, bool]] | None:
    """*text* cut where its part *large* (start, end, ratio: offsets into *text*) begins and ends: the paragraphs
    (text, set larger) in their order, the empty ones left out, each with its stressed words marked on its own; None
    when there is no part, or nothing but the part. The marks right after the part (", I ...") and an opening mark
    right before it go with the part, so that no paragraph begins with a comma or ends with an open quote."""
    if not large:
        return None
    a, b = max(0, min(int(large[0]), len(text))), max(0, min(int(large[1]), len(text)))
    if b <= a:
        return None
    while b < len(text) and _clings(text[b]):
        b += 1
    while a > 0 and _opens(text, a - 1):
        a -= 1
    stressed = _stressed(text)
    parts = [(_part(text, stressed, 0, a), False), (_part(text, stressed, a, b), True),
             (_part(text, stressed, b, len(text)), False)]
    parts = [(t, big) for t, big in parts if t]
    if not any(big for _t, big in parts) or all(big for _t, big in parts):
        return None
    return parts


def ratio_of(large: tuple[int, int, float] | None) -> float:
    """How many times larger the part of *large* is set at most (`RATIO_CAP`)."""
    return min(RATIO_CAP, float(large[2])) if large else 1.0


# ------------------------------------------------------------------ the layout

@dataclass(frozen=True, eq=False)
class LargeFit:
    """A text set with a part larger (`layout_large`): the lines as (text, x centre, y top, size, paragraph) in mask
    coordinates, the font of each size, the base size and the part's, and the bubble's body (its centroid, width and
    height, for the checks; None for text on the page)."""

    lines: tuple[tuple[str, float, float, int, int], ...]
    fonts: dict[int, Any]
    base: int
    big: int
    body: tuple[float, float, int, int] | None = None

    @property
    def ratio(self) -> float:
        return self.big / self.base if self.base else 1.0


@dataclass
class _Para:
    """One paragraph at its size: its pieces (words; characters in a script wrapped by character), the width of each
    (as a line starts with it, and as it goes on a line), the room of a line whose ink starts at each row, its centre
    there, and its ink's rows below a line's top."""

    pieces: list[str]
    first: list[float]
    width: list[float]
    glue: str
    gap: float
    room: np.ndarray
    middle: np.ndarray
    ink_top: int
    tall: int
    pitch: float
    size: int
    script: str


def _pieces(text: str, script: str) -> list[str]:
    """*text*'s pieces as a line may break between them (`typeset._units`); in a script wrapped by character a mark
    that may not start a line kept with the piece before it, and one that may not end a line with the piece after it."""
    from . import typeset as ts

    out: list[str] = []
    joined = script in ts.NO_SPACE_SCRIPTS
    for para in text.replace("\r", "").split("\n"):
        for u in ts._units(para, script):
            if joined and out and ts._no_start(u):
                out[-1] += u
            elif joined and out and len(out[-1]) == 1 and out[-1] in ts._NO_LINE_END:
                out[-1] += u
            else:
                out.append(u)
    return out


def _para(body: Any, text: str, script: str, font: Any, size: int, line_spacing: float) -> _Para | None:
    from . import typeset as ts

    pieces = _pieces(text, script)
    if not pieces:
        return None
    glue = "" if script in ts.NO_SPACE_SCRIPTS else " "
    first = [float(ts._display_width(font, ts._lead(p, script), script)) for p in pieces]
    width = [float(ts._display_width(font, p, script)) for p in pieces]
    gap = float(ts._display_width(font, "a a", script) - ts._display_width(font, "aa", script)) if glue else 0.0
    margin = max(float(ts.MARGIN_PX), ts.MARGIN_EM * size)
    left, right = body.extent(margin)
    ink_top, ink_bottom = ts._ink_rows(font, text, script)
    tall = max(1, ink_bottom - ink_top)
    if left.shape[0] < tall:
        return None
    starts = sliding_window_view(left, tall).max(axis=1)
    ends = sliding_window_view(right, tall).min(axis=1)
    room = np.floor(np.maximum(ends - starts, 0.0))
    middle = np.full(room.shape, body.cx) if body.axis else (starts + ends) / 2.0
    return _Para(pieces, first, width, glue, gap, room, middle, ink_top, tall, size * line_spacing, size, script)


def _fill(para: _Para, rooms: list[float]) -> list[tuple[int, int]] | None:
    """*para*'s pieces poured into lines of *rooms* in order, as many on each as fit (none left out): each line's
    (first, last + 1) piece; None when they do not fit."""
    out: list[tuple[int, int]] = []
    i, n = 0, len(para.pieces)
    for room in rooms:
        if i >= n:
            out.append((i, i))
            continue
        if para.first[i] > room:
            return None
        used, j = para.first[i], i + 1
        while j < n and used + para.gap + para.width[j] <= room:
            used += para.gap + para.width[j]
            j += 1
        out.append((i, j))
        i = j
    return out if i >= n else None


LONE_COST = 0.5  # a line of one short word (`LONE_LETTERS` letters or fewer) in a paragraph of several lines ...
LONE_LETTERS = 3  # ... against each line's empty share of its room, squared
COST_OFF = 0.08  # the block off the body's centre, per line's height squared (as `typeset.COST_OFF`)
COST_LINE = 0.05  # a paragraph set on a line more than it fits on


def _lone(para: _Para, a: int, b: int) -> bool:
    return para.glue != "" and b == a + 1 and sum(ch.isalnum() for ch in para.pieces[a]) <= LONE_LETTERS


def _defects(paras: list[_Para], got: list[tuple[int, int, int, float]]) -> int:
    """What is wrong with a block, as the checks of the lettering count it (`typeset.lettering_flags`): in a script
    with spaces, a line of one short word in a paragraph of several lines (`typeset.LONE_WORDS` words or more), and
    an inner line under `typeset.HOURGLASS` of the narrower of its neighbours."""
    from . import typeset as ts

    found = 0
    for k, para in enumerate(paras):
        mine = [(a, b) for kk, a, b, _r in got if kk == k and b > a]
        if para.glue == "" or len(mine) < 2:
            continue
        if len(para.pieces) >= ts.LONE_WORDS:
            found += sum(1 for a, b in mine if _lone(para, a, b))
        widths = [para.first[a] + sum(para.gap + para.width[j] for j in range(a + 1, b)) for a, b in mine]
        found += sum(1 for j in range(1, len(widths) - 1)
                     if widths[j] < ts.HOURGLASS * min(widths[j - 1], widths[j + 1]))
    return found


def _cost(para: _Para, rooms: list[float], breaks: list[tuple[int, int]]) -> float:
    """What a paragraph's lines cost (`_even`): each line's empty share of its room squared, and `LONE_COST` for a
    line of one short word among several."""
    cost = 0.0
    for room, (a, b) in zip(rooms, breaks):
        if b <= a or room <= 0:
            continue
        w = para.first[a] + sum(para.gap + para.width[k] for k in range(a + 1, b))
        cost += ((room - w) / room) ** 2 + (LONE_COST if len(breaks) > 1 and _lone(para, a, b) else 0.0)
    return cost


def _even(para: _Para, rooms: list[float]) -> list[tuple[int, int]] | None:
    """`_fill`, the pieces shared out evenly over all the lines: each line as full of its room as the others (the
    least sum of their empty shares squared), a line of one short word avoided (`LONE_COST`); as `_fill` leaves them
    when they cannot fill every line."""
    found = _fill(para, rooms)
    n, m = len(rooms), len(para.pieces)
    if found is None or n < 2 or m < n:
        return found
    cum = [0.0]
    for k in range(m):
        cum.append(cum[-1] + para.width[k])

    def width(a: int, b: int) -> float:  # pieces a..b-1 on one line
        return para.first[a] + (cum[b] - cum[a + 1]) + para.gap * (b - a - 1)

    lone = functools.partial(_lone, para)
    inf = float("inf")
    best = [[inf] * (m + 1) for _ in range(n + 1)]
    back = [[-1] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for i in range(n):
        room = rooms[i]
        for a in range(m):
            if best[i][a] == inf:
                continue
            for b in range(a + 1, m - (n - i - 1) + 1):  # leaves a piece at least for each line after
                w = width(a, b)
                if w > room:
                    break
                cost = best[i][a] + ((room - w) / room) ** 2 + (LONE_COST if lone(a, b) else 0.0)
                if cost < best[i + 1][b]:
                    best[i + 1][b], back[i + 1][b] = cost, a
    if best[n][m] == inf:
        return found
    out, b = [], m
    for i in range(n, 0, -1):
        a = back[i][b]
        out.append((a, b))
        b = a
    return out[::-1]


def _line(para: _Para, a: int, b: int) -> str:
    from . import typeset as ts

    if b <= a:
        return ""
    return ts._lead(para.pieces[a], para.script) + "".join(para.glue + p for p in para.pieces[a + 1:b])


def _tops(paras: list[_Para], counts: list[int], start: float) -> list[tuple[int, float]]:
    """Each line's paragraph and the row its ink starts at, from *start*: a paragraph's lines its own pitch apart,
    and between two paragraphs the larger of their gaps between the ink of two lines."""
    out: list[tuple[int, float]] = []
    y = start
    prev = -1
    for k, (para, n) in enumerate(zip(paras, counts)):
        for _ in range(n):
            if prev >= 0:
                p = paras[prev]
                y += p.pitch if prev == k else p.tall + max(p.pitch - p.tall, para.pitch - para.tall)
            out.append((k, y))
            prev = k
    return out


def _try(paras: list[_Para], counts: list[int], start: float, h: int, even: bool
         ) -> tuple[list[tuple[int, int, int, float]] | None, int]:
    """The lines with the block's ink starting at *start*: (paragraph, first piece, last piece + 1, ink top row) for
    each; or None and the paragraph that did not fit (-1: the block runs off the rows)."""
    tops = _tops(paras, counts, start)
    rooms: list[list[float]] = [[] for _ in paras]
    rows: list[list[int]] = [[] for _ in paras]
    for k, y in tops:
        r = int(round(y))
        if r < 0 or r >= paras[k].room.shape[0]:
            return None, -1
        rooms[k].append(float(paras[k].room[r]))
        rows[k].append(r)
    out: list[tuple[int, int, int, float]] = []
    for k, para in enumerate(paras):
        got = (_even if even else _fill)(para, rooms[k])
        if got is None:
            return None, k
        out.extend((k, a, b, float(r)) for (a, b), r in zip(got, rows[k]))
    return out, -2


def _height(paras: list[_Para], counts: list[int]) -> float:
    tops = _tops(paras, counts, 0.0)
    k, y = tops[-1]
    return y + paras[k].tall


def _place(body: Any, parts: list[tuple[str, bool]], base: int, big: int, font_path: Any, bold_variation: bool,
           script: str, line_spacing: float, valign: str) -> tuple[list[Any], dict[int, Any], int] | None:
    """*parts* in *body* at *base* (and *big* for the part set larger): the lines (text, x centre, y top, size,
    paragraph), the fonts and the block's defects (`_defects`); None when they do not fit. Each paragraph on the
    fewest lines it fits on at some place (from the centre out, `typeset._plan`'s places), then of those, one more
    line for a paragraph, and the places tried, the block whose lines are shared out best (`best_of`)."""
    from . import typeset as ts

    fonts = {z: styled_font(font_path, z, bold_variation) for z in {base, big}}
    paras = []
    for text, larger in parts:
        z = big if larger else base
        para = _para(body, text, script, fonts[z], z, line_spacing)
        if para is None:
            return None
        paras.append(para)
    h = body.depth.shape[0]
    left, right = body.extent(max(float(ts.MARGIN_PX), ts.MARGIN_EM * base))
    wide = np.flatnonzero(right - left >= base)
    if wide.size == 0:
        return None
    y_lo, y_hi = int(wide[0]), int(wide[-1]) + 1
    counts = []
    for p in paras:
        widest = float(p.room.max()) if p.room.size else 0.0
        if widest <= 0 or max(p.first) > widest:
            return None
        total = sum(p.width) + p.gap * (len(p.pieces) - 1)
        counts.append(max(1, int(math.ceil(total / widest))))
    step = max(1, int(paras[0].pitch / 6))
    pitch = min(p.pitch for p in paras)

    def starts_for(tall: float) -> list[float]:
        if valign == "top":
            return [float(y) for y in range(y_lo, int(y_hi - tall) + 1, step)]
        if valign == "bottom":
            return [float(y) for y in range(int(y_hi - tall), y_lo - 1, -step)]
        mid = body.cy - tall / 2.0
        return [mid + d * pitch for d in (0.0, 0.25, -0.25, 0.5, -0.5)]

    def first_fit(counts: list[int]) -> tuple[list[tuple[int, int, int, float]] | None, list[int]]:
        whys = []
        for start in starts_for(_height(paras, counts)):
            got, why = _try(paras, counts, start, h, False)
            if got is not None:
                return got, whys
            whys.append(why)
        return None, whys

    def best_of(counts: list[int]) -> list[tuple[int, int, int, float]] | None:
        """Of the blocks on *counts* lines, or on one more line for a paragraph, at each place tried, the one whose
        lines are shared out best (`_even`'s cost) and that sits nearest the centre (`COST_OFF`)."""
        tried = [list(counts)] + [[n + (k == j) for k, n in enumerate(counts)] for j in range(len(counts))]
        best: tuple[float, list[tuple[int, int, int, float]]] | None = None
        for option in tried:
            tall = _height(paras, option)
            if tall > y_hi - y_lo + 1:
                continue
            for n, start in enumerate(starts_for(tall)):
                got, _why = _try(paras, option, start, h, True)
                if got is None or any(b <= a for _k, a, b, _r in got):
                    continue
                off = (start - (body.cy - tall / 2.0)) / pitch if valign == "middle" else 0.0
                cost = sum(_cost(paras[k], [paras[k].room[int(r)] for kk, _a, _b, r in got if kk == k],
                                 [(a, b) for kk, a, b, _r in got if kk == k]) for k in range(len(paras)))
                cost += COST_OFF * off * off + COST_LINE * (sum(option) - sum(counts))
                if best is None or cost < best[0]:
                    best = (cost, got)
        return best[1] if best is not None else None

    for _ in range(64):
        if _height(paras, counts) > y_hi - y_lo + 1:
            return None
        got, whys = first_fit(counts)
        if got is not None:
            used = [sum(1 for kk, a, b, _r in got if kk == k and b > a) for k in range(len(paras))]
            if used != counts and first_fit(used)[0] is not None:  # a line left empty: as many as are used
                counts = used
            got = best_of(counts) or got
            lines = []
            for k, a, b, r in got:
                if b > a:
                    para = paras[k]
                    lines.append((_line(para, a, b), float(para.middle[int(r)]), r - para.ink_top, para.size, k))
            return lines, fonts, _defects(paras, got)
        failed = next((w for w in whys if w >= 0), -1)
        if failed < 0:  # the block runs off the rows wherever it is set: more lines only make it taller
            return None
        counts[failed] += 1
    return None


def _largest(sizes: list[int], fits: Callable[[int], Any]) -> tuple[int, Any] | None:
    """The largest of *sizes* (from the largest down) at which *fits* gives something, taken to fit at every size
    below one that fits: (size, what it gave); None when the smallest does not fit."""
    got = fits(sizes[0])
    if got is not None:
        return sizes[0], got
    last = fits(sizes[-1])
    if last is None:
        return None
    lo, hi, best = 0, len(sizes) - 1, (sizes[-1], last)  # sizes[lo] does not fit, sizes[hi] does
    while hi - lo > 1:
        mid = (lo + hi) // 2
        got = fits(sizes[mid])
        if got is not None:
            hi, best = mid, (sizes[mid], got)
        else:
            lo = mid
    return best


def _big(base: int, ratio: float) -> int:
    return max(base + 1, int(round(base * ratio)))


def search(sizes: list[int], ratio: float, at: Callable[[int, float], Any]) -> tuple[int, int, Any] | None:
    """The base, the part's size and what *at*(base, ratio) gives where the text fits (None where it does not): the
    largest base of *sizes* (from the largest down) at *ratio*, else at the smallest base the largest ratio from
    `MIN_RATIO` up that fits (to `RATIO_PRECISION`); None when none does."""
    found = _largest(sizes, lambda s: at(s, ratio))
    if found is not None:
        return found[0], _big(found[0], ratio), found[1]
    base = sizes[-1]
    lo, hi = MIN_RATIO, ratio
    got = at(base, lo)
    if got is None:
        return None
    best = (_big(base, lo), got)
    while hi - lo > RATIO_PRECISION:
        mid = (lo + hi) / 2.0
        tried = at(base, mid)
        if tried is not None:
            lo, best = mid, (_big(base, mid), tried)
        else:
            hi = mid
    return base, best[0], best[1]


def _fit_body(body: Any, parts: list[tuple[str, bool]], ratio: float, sizes: list[int], font_path: Any,
              bold_variation: bool, script: str, line_spacing: float, valign: str) -> tuple[int, int, Any] | None:
    """`search` in *body*: the base, the part's size and the lines, fonts and defects (`_place`); a block with
    defects (`_defects`) may give up to `typeset.SIZE_TRADE` of its base for fewer, `typeset.TRADE_PER_DEFECT` of
    it for each (as the one-size lettering does, `typeset._fit_body`)."""
    from . import typeset as ts

    def at(base: int, r: float) -> Any:
        return _place(body, parts, base, _big(base, r), font_path, bold_variation, script, line_spacing, valign)

    found = search(sizes, ratio, at)
    if found is None or found[2][2] == 0:
        return found
    base, big, got = found
    r = big / base
    score, chosen = float(got[2]), found
    for s in [s for s in sizes if s < base and s >= base * (1.0 - ts.SIZE_TRADE)][:ts.TRADE_TRIES]:
        other = at(s, r)
        if other is None:
            continue
        mine = other[2] + (1.0 - s / base) / ts.TRADE_PER_DEFECT
        if mine < score - 1e-9:
            score, chosen = mine, (s, _big(s, r), other)
        if other[2] == 0:
            break
    return chosen


def layout_large(mask: np.ndarray, parts: list[tuple[str, bool]], ratio: float, font_path: str | Lettering | None,
                 min_size: int = 9, max_size: int = 64, line_spacing: float = 1.12, bold_variation: bool = False,
                 script: str = "lgc", on_page: bool = False, anchor: Box | None = None, floor: int = 0,
                 valign: str = "middle", fixed: int = 0) -> LargeFit | None:
    """Where and how large *parts* (`parts_of`) are set inside *mask*, the part set larger *ratio* times (see the
    module): the base the largest from *max_size* down to the larger of *min_size* and *floor* (*fixed*: that size,
    never shrunk), the ratio shrunk at that floor where it must, never under `MIN_RATIO`; None when the part cannot be
    set larger so (the caller sets the text at one size). Remembered as `typeset.layout_text` is."""
    from . import typeset as ts

    ratio = min(RATIO_CAP, float(ratio))
    if ratio < MIN_RATIO or not parts:
        return None
    m = np.ascontiguousarray(mask)
    try:
        key: tuple[Any, ...] | None = (
            m.shape, str(m.dtype), hashlib.blake2b(m.data, digest_size=16).digest(), tuple(parts), round(ratio, 4),
            font_path, min_size, max_size, line_spacing, bold_variation, script, on_page,
            tuple(anchor) if anchor is not None else None, floor, valign, fixed, ts._tunables(), MIN_RATIO,
            RATIO_CAP)
        hash(key)
    except TypeError:
        key = None
    if key is not None:
        with _LAYOUTS_LOCK:
            if key in _LAYOUTS:
                _LAYOUTS.move_to_end(key)
                return _LAYOUTS[key]
    fit = _layout_large(mask, parts, ratio, font_path, min_size, max_size, line_spacing, bold_variation, script,
                        on_page, anchor, floor, valign, fixed)
    if key is not None:
        with _LAYOUTS_LOCK:
            _LAYOUTS[key] = fit
            while len(_LAYOUTS) > LAYOUTS_KEPT:
                _LAYOUTS.popitem(last=False)
    return fit


def _layout_large(mask: np.ndarray, parts: list[tuple[str, bool]], ratio: float, font_path: Any, min_size: int,
                  max_size: int, line_spacing: float, bold_variation: bool, script: str, on_page: bool,
                  anchor: Box | None, floor: int, valign: str, fixed: int) -> LargeFit | None:
    from . import typeset as ts

    centre = ts._text_centre(on_page, anchor)
    bodies = ts._bodies(mask, centre)
    if not bodies:
        return None
    hi = fixed or max(min_size, max_size)
    lo = fixed or min(hi, max(min_size, floor))
    sizes = ts._sizes(lo, hi)
    best: tuple[float, int, int, Any] | None = None
    for body in bodies:
        got = _fit_body(body, parts, ratio, sizes, font_path, bold_variation, script, line_spacing, valign)
        if got is None:
            continue
        base, big, (lines, fonts, _defects_found) = got
        score = (base + big) * (1.0 - 0.1 * min(1.0, body.straddle))  # a block across a neck: only when much larger
        if best is None or score > best[0]:
            best = (score, base, big, (lines, fonts))
    if best is None:
        return None
    _score, base, big, (lines, fonts) = best
    shape = None
    if centre is None:  # a bubble: its body's centroid and size, for the checks (as `typeset._layout_text` gives them)
        room = bodies[0]
        cols = np.flatnonzero((room.depth > 0).any(axis=0))
        shape = (room.cx, room.cy, int(cols[-1] - cols[0] + 1) if cols.size else 1, room.rows[1] - room.rows[0])
    return LargeFit(tuple(lines), fonts, base, big, shape)


# ------------------------------------------------------------------ lettering

def letter_large(image: Image.Image | None, region: TextRegion, parts: list[tuple[str, bool]], ratio: float,
                 font_path: str | Lettering | None, min_size: int, max_size: int, line_spacing: float,
                 bold_variation: bool, script: str, outline: bool | None, fmt: Any, direction: str,
                 color: tuple[int, int, int], outline_color: tuple[int, int, int] | None, on_page: bool,
                 anchor: Box | None, floor: int) -> Any:
    """`typeset.letter_text` for a text with a part set larger (*parts*, `parts_of`), upright (a slant is the
    caller's): across (`layout_large`) or stacked (`vertical.layout_stacked_large`), as the reader formatted it
    (*fmt*: its block at the top, middle or bottom, its line spacing, its size fixed; a text aligned left or right is
    set at one size); returns what `letter_text` returns (`typeset.Lettered`, the base's size, "large" or "stacked"
    for the layout), or None when the part cannot be set larger (nothing drawn: the caller sets the text at one
    size)."""
    from . import typeset as ts

    fixed = fmt.size if fmt is not None and fmt.size else 0
    spacing = fmt.line_spacing if fmt is not None and fmt.line_spacing else line_spacing
    valign = fmt.valign if fmt is not None else "middle"
    if direction == "stacked":
        from . import vertical

        size = vertical.letter_stacked_large(image, region, parts, ratio, font_path, min_size, fixed or max_size,
                                             spacing, color, bold_variation, outline,
                                             ts._text_centre(on_page, anchor), fixed, valign, ts.busy_under,
                                             outline_color, floor)
        return None if size is None else ts.Lettered(size, (), "stacked")
    if fmt is not None and fmt.align != "center":
        return None
    fit = layout_large(region.mask, parts, ratio, font_path, min_size, max_size, spacing, bold_variation, script,
                       on_page, anchor, floor, valign, fixed)
    if fit is None:
        return None
    if image is None:
        return ts.Lettered(fit.base, (), "large")
    flags, _outlined = draw_large(image, region, fit, script, color, outline, outline_color, spacing, on_page)
    return ts.Lettered(fit.base, flags if fmt is None else (), "large")


# ------------------------------------------------------------------ drawing

def draw_large(image: Image.Image, region: TextRegion, fit: LargeFit, script: str, color: tuple[int, int, int],
               outline: bool | None, outline_color: tuple[int, int, int] | None, line_spacing: float,
               on_page: bool) -> tuple[tuple[str, ...], bool]:
    """The lines of *fit* drawn in *region* on *image*, each at its size in *color*, with an outline as wide as its
    own size wants (`typeset._contour`) as *outline* says (None: where the lines lie on a drawing or a tone,
    `typeset.busy_under`); returns what the checks of the lettering found (`typeset.lettering_flags`, each paragraph's
    lines measured at their own size, the block's place against the body as a whole) and whether it was outlined."""
    from . import typeset as ts

    shown = [(ts.display_form(t, script), x, top, z) for t, x, top, z, _k in fit.lines]
    widths = [fit.fonts[z].width(s) for s, _x, _t, z in shown]
    if outline is None and shown:
        box = (int(region.x0 + min(x - w / 2.0 for (_s, x, _t, _z), w in zip(shown, widths))),
               int(region.y0 + min(top for _s, _x, top, _z in shown)),
               int(region.x0 + max(x + w / 2.0 for (_s, x, _t, _z), w in zip(shown, widths))) + 1,
               int(region.y0 + max(top + z * line_spacing for _s, _x, top, z in shown)) + 1)
        outline = ts.busy_under(image, box)
    ground = np.asarray(image.crop((region.x0, region.y0, region.x1, region.y1)).convert("RGB"))
    for (s, x, top, z), w in zip(shown, widths):
        contour = ts._contour(color, outline_color, z, outline)
        fit.fonts[z].draw(image, region.x0 + x - w / 2.0, region.y0 + top, s, color, contour)
    found: set[str] = set()
    for k in sorted({k for *_rest, k in fit.lines}):  # each paragraph's lines checked at their own size
        z = next(z for *_r, z, kk in fit.lines if kk == k)
        mine = [(s, x, top) for (s, x, top, _z), line in zip(shown, fit.lines) if line[4] == k]
        plain = [(t, x, top) for t, x, top, _z, kk in fit.lines if kk == k]
        part = ts.Fit(fit.fonts[z], plain, z, z * line_spacing, "large")
        found.update(ts.lettering_flags(ground, region.mask, part, mine, script, color, bool(outline), True))
    if not on_page and fit.body is not None and shown:
        found.discard(ts.OFF_CENTRE)
        cx, cy, bw, bh = fit.body
        xs0 = [x - w / 2.0 for (_s, x, _t, _z), w in zip(shown, widths)]
        xs1 = [x + w / 2.0 for (_s, x, _t, _z), w in zip(shown, widths)]
        ys0 = [top + ts._ink_rows(fit.fonts[z], s, script)[0] for s, _x, top, z in shown]
        ys1 = [top + ts._ink_rows(fit.fonts[z], s, script)[1] for s, _x, top, z in shown]
        mid_x, mid_y = (min(xs0) + max(xs1)) / 2.0, (min(ys0) + max(ys1)) / 2.0
        if max(abs(mid_x - cx) / max(1, bw), abs(mid_y - cy) / max(1, bh)) > ts.OFF_SHARE:
            found.add(ts.OFF_CENTRE)
    return tuple(f for f in ts.LETTER_CHECKS if f in found), bool(outline)
