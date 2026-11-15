"""Fit the translated text into a bubble.

Approach (own implementation; the auto-sizing idea is the same one every
typesetting tool uses, including BallonsTranslator, GPL-3.0, studied for
design only): find the largest centered rectangle that fits inside the bubble
interior, then shrink the font until the wrapped text fits that rectangle.
Besides the rectangle, the lines are laid out along the bubble's body
(shape_layout), and that layout wins wherever it fits at least as large: a
rectangle wastes the widest part of a round bubble.

Along the body (own implementation, the line breaking after the classic
dynamic programme over break points): the tail is cut off by an opening and
the block is centred on what is left, two bubbles joined at a neck are also
tried one by one (`_bodies`); every line is as wide as the body is round one
shared centre axis over the rows its ink covers, the ink `MARGIN_EM` of the
size off the outline. At each size the words are shared out over the lines
(`_plan_lines`): each line aims at the width that keeps all of them alike off
the outline (in an oval an oval block, short, long, short), a break is free
after a sentence, cheap after a comma, dearer inside a clause, dearer still
after a word that leans on the next one or inside a name, and a lone short
word on a line costs extra. The largest size that fits is found from an upper
bound in growing steps, then refined; a size up to `SIZE_TRADE` smaller may win
where its block has fewer defects (`_defects`: lone words, hyphens, an
hourglass; in a column of a word or two a line, hyphens alone). The checks of
the lettering (`lettering_flags`) say what is still wrong with the block chosen.

Scripts: Latin-like text wraps at spaces; Chinese, Japanese and Thai wrap
between characters; Arabic and Hebrew are laid out right-to-left (Arabic
letters are joined with ``arabic_reshaper``). Pillow builds without libraqm
cannot shape Indic scripts; those render letter by letter.

A line break in the translation ends a line wherever it is. The reader may
also format a region in the region editor, as a word processor's text box
(`TextFormat`, `layout_formatted`): the lines aligned left, centred or right
and the block at the top, middle or bottom, a fixed size that is never shrunk,
the line spacing; an empty line then keeps its height. Text that does not fit
at its size is set past the inner rectangle, up to the bubble's bounding box,
cut at the bubble's edge, and said (`NO_FIT`). Without a format the lettering
is the automatic one (`layout_text`).

At the limit (`_rescue`), for small lettering only: where the size the text
fits at is under `RESCUE_BELOW` (14; a line at 14 or more reads comfortably
and keeps its natural letter shapes), or the text does not fit even at the
smallest size, it may instead be condensed by up to 8 % or a long Latin word
hyphenated at a syllable-like point (`hyphen_points`), the largest size that
then fits winning, with the fewest hyphens and the mildest condensing there.
The `Fit` says which layout won. Lettering at 14 or more, and any text that
fits without them, is set exactly as before. A Latin, Greek or Cyrillic word
that fits nowhere even so is split only as a last resort (`_split_word`): one
of at least six letters, three or more on either side, with a hyphen; a
shorter word stays whole, past its room if it must.

In a rectangle, once the size is chosen the lines are balanced (`_balanced`):
the same lines at the same places, the words shared out over them by a dynamic
programme (least total slack cubed) instead of each line filled to the brim and
the last one left with a word. On a page, `page_caps` keeps a short line in a
big bubble from towering over its neighbours: `SIZE_CAP` times the page's
median size for its kind.

The reader may set a region's text direction (`RegionStyle.direction`), as a word processor's text box: turned a
quarter clockwise to read from the top down or a quarter the other way to read from the bottom up (the lines set as
always in the region's frame turned, its width and height swapped, then turned onto the page by `render.slant`
with the slant added: `QUARTER_TURNS`), or stacked in columns of upright glyphs (`render.vertical`). Auto and
horizontal letter the region as before, byte for byte.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import re
import threading
import unicodedata
from bisect import bisect_right
from collections import OrderedDict, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from statistics import median
from typing import Any

import cv2
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from ..regions import Box, TextRegion
from .fonts import NO_SPACE_SCRIPTS, RTL_SCRIPTS, FontT, drawable, script_of
from .lettering import Lettering, StyledFont, emphasis_marks, strip_marks, styled_font

try:  # MIT; joins Arabic letters into their contextual forms
    import arabic_reshaper  # type: ignore
except Exception:  # pragma: no cover - optional
    arabic_reshaper = None

# Characters that must not start a line in CJK text.
_NO_LINE_START = set("、。，．・：；！？!?)）」』】〉》〕］}｝ー〜～…")
_LTR_RUN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.,:/%+-]*")
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
# at the limit: how much narrower a text may be set, in the order tried, and where a long word may take a hyphen
CONDENSE_STEPS = (0.98, 0.96, 0.94, 0.92)
RESCUE_BELOW: int | None = 14  # the rescue steps in only for a plain fit under this size (None: at any size)
RESCUE_STEPS: int | None = None  # how many sizes above the plain layout's the rescue may climb (None: as far as fits)
HYPHEN_MIN_LETTERS = 8  # shorter words are never hyphenated
HYPHEN_EDGE = 3  # letters a hyphen leaves on each side of a word split as a last resort, after a hyphenation point
HYPHEN_HEAD = 2  # letters a hyphenation point leaves before it (ex-tra, re-turn: two are a syllable that reads)
HYPHENS_AVOIDABLE = 1  # at the limit, the most hyphens a layout may take where the text fits whole at a smaller size
#                        (where it does not: as many as the smallest size that fits needs, if more)
BREAK_MIN_LETTERS = 6  # a shorter word is never split, even where it fits nowhere: it stays whole
BALANCE_LINES = True  # share the words out over the lines (False: as the greedy fill leaves them)
# In a rectangle (`_balanced_lines`):
LAST_LINE_FREE = 0.1  # how much of its width a paragraph's last line may leave empty free of penalty
ORPHAN_LETTERS = 6  # a last line of one such word (with its punctuation) counts as an orphan
ORPHAN_SLACK = 1.0  # an orphan costs as much as a line this empty: only a worse way elsewhere keeps it
ORPHAN_FIRST_LETTERS = 3  # a first or inner line of one such word ("I", "Je", "Ich") is avoided the same way
SIZE_CAP: float | None = 1.3  # no lettering above this many times the page's median for its kind (None: no cap)
STANDS_OUT = 1.5  # lettering this many times its neighbours' in the original was large on purpose
UNCAPPED_KINDS = frozenset({"shout"})  # meant to be large: as large as they fit
_VOWELS = frozenset("aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿœāēīōūăĕĭŏŭąęįųőű")
_ONSETS = frozenset({"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr", "wr", "kn", "ch", "ph",
                     "sh", "th", "wh", "qu", "sc", "sk", "sl", "sm", "sn", "sp", "st", "sw", "str", "spr", "scr", "spl",
                     "thr", "chr", "shr", "sch"})  # consonants that may start a syllable together
_S_ONSETS = frozenset({"sc", "sk", "sl", "sm", "sn", "sp", "st", "sw"})  # alone between vowels they split: mas-ter
_UNSPLIT = frozenset({"ck", "gh", "ch", "sh", "th", "ph", "wh", "qu"})  # never a hyphen between these two


def inner_rect(mask: np.ndarray, pad_ratio: float = 0.06, center: tuple[float, float] | None = None) -> Box:
    """Largest rectangle (same aspect as the mask's bounding box) centred on *center* (default: the mask's centroid)."""
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        h, w = mask.shape
        return (int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75))
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    bw, bh = bx1 - bx0, by1 - by0
    cx, cy = center if center is not None else (float(xs.mean()), float(ys.mean()))
    integral = cv2.integral((mask > 0).astype(np.uint8))  # (h+1, w+1)
    h, w = mask.shape

    def all_inside(x0: int, y0: int, x1: int, y1: int) -> bool:
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
            return False
        total = integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
        return int(total) == (x1 - x0) * (y1 - y0)

    best: Box | None = None
    for scale in np.linspace(1.0, 0.2, 41):
        hw, hh = bw * scale / 2.0, bh * scale / 2.0
        rect = (int(round(cx - hw)), int(round(cy - hh)), int(round(cx + hw)), int(round(cy + hh)))
        if all_inside(*rect):
            best = rect
            break
    if best is None:
        best = (int(cx - bw * 0.2), int(cy - bh * 0.2), int(cx + bw * 0.2), int(cy + bh * 0.2))
    px = int((best[2] - best[0]) * pad_ratio)
    py = int((best[3] - best[1]) * pad_ratio)
    return (best[0] + px, best[1] + py, best[2] - px, best[3] - py)


def grown_rect(mask: np.ndarray, start: Box, pad_ratio: float = 0.06, bias: float = 1.0) -> Box | None:
    """Rectangle grown out of *start* one pixel at a time on every side that stays inside the mask.

    For lettering set straight on the page, whose mask leaves out the drawing around the text: artwork on one side
    stops that side only, so the rectangle still takes the room on the others (a rectangle centred on the text
    would shrink on every side at once). When *start* itself is not all inside (the drawing reaches into it), the
    rectangle grows from the point of *start* furthest from anything outside the mask; None when no point is in it.
    *bias* is how many pixels the sides grow for every pixel the top and bottom grow (2: favour a wide box, which
    suits horizontal lettering; 0.5: a tall one).
    """
    h, w = mask.shape
    integral = cv2.integral((mask > 0).astype(np.uint8))  # (h+1, w+1)

    def all_inside(x0: int, y0: int, x1: int, y1: int) -> bool:
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
            return False
        total = integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
        return int(total) == (x1 - x0) * (y1 - y0)

    x0, y0, x1, y1 = max(0, start[0]), max(0, start[1]), min(w, start[2]), min(h, start[3])
    if not all_inside(x0, y0, x1, y1):
        if x1 <= x0 or y1 <= y0:
            return None
        depth = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)[y0:y1, x0:x1]
        if depth.max() <= 0:
            return None
        cy, cx = np.unravel_index(int(depth.argmax()), depth.shape)
        x0, y0 = x0 + int(cx), y0 + int(cy)
        x1, y1 = x0 + 1, y0 + 1
    sideways, upright = (max(1, round(bias)), 1) if bias >= 1 else (1, max(1, round(1 / bias)))
    grown = True
    while grown:
        grown = False
        for steps, moves in ((sideways, ((-1, 0, 0, 0), (0, 0, 1, 0))), (upright, ((0, -1, 0, 0), (0, 0, 0, 1)))):
            for _ in range(steps):
                for dx0, dy0, dx1, dy1 in moves:
                    if all_inside(x0 + dx0, y0 + dy0, x1 + dx1, y1 + dy1):
                        x0, y0, x1, y1 = x0 + dx0, y0 + dy0, x1 + dx1, y1 + dy1
                        grown = True
    px = int((x1 - x0) * pad_ratio)
    py = int((y1 - y0) * pad_ratio)
    return (x0 + px, y0 + py, x1 - px, y1 - py)


# --- script handling -------------------------------------------------------------

def display_form(line: str, script: str) -> str:
    """Convert a logical line into the string that is actually drawn.

    Right-to-left scripts are reversed for drawing (Pillow draws left to right);
    runs of digits/Latin keep their order and brackets are mirrored. Arabic
    letters are first joined into contextual forms.
    """
    if script not in RTL_SCRIPTS:
        return line
    if script == "arabic" and arabic_reshaper is not None:
        try:
            line = arabic_reshaper.reshape(line)
        except Exception:
            pass
    pieces: list[str] = []
    pos = 0
    for m in _LTR_RUN.finditer(line):
        if m.start() > pos:
            pieces.append(line[pos : m.start()][::-1].translate(_MIRROR))
        pieces.append(m.group(0))
        pos = m.end()
    if pos < len(line):
        pieces.append(line[pos:][::-1].translate(_MIRROR))
    return "".join(reversed(pieces))


def text_width(font: FontT | StyledFont, text: str) -> int:
    """The advance width of *text* in *font*; a StyledFont measures its stressed runs in their own face."""
    if isinstance(font, StyledFont):
        return font.width(text)
    try:
        return int(round(font.getlength(text)))
    except AttributeError:  # pragma: no cover
        left, _, right, _ = font.getbbox(text)
        return right - left


def _display_width(font: FontT, line: str, script: str) -> int:
    return text_width(font, display_form(line, script))


def _split_word(word: str, font: FontT, max_width: int, script: str) -> tuple[str, str] | None:
    """A word wider than its line at the smallest size, split as a last resort: (its first part, the rest), the
    first part as long as *max_width* allows (the shortest there is when none fits); None when it stays whole. In
    Latin, Greek and Cyrillic only a word of BREAK_MIN_LETTERS letters or more is split, only between two letters
    (or after a hyphen it has), HYPHEN_EDGE letters or more on either side, and the break shows a hyphen; "Damn" stays
    whole. Other scripts take no hyphen and break between any two letters."""
    lgc = script == "lgc"
    edge = HYPHEN_EDGE if lgc else 1
    letters = [i for i, ch in enumerate(word) if ch.isalpha()]
    if len(letters) < (BREAK_MIN_LETTERS if lgc else 2):
        return None
    cuts = [i for i in letters[edge : len(letters) - edge + 1] if word[i - 1].isalpha() or word[i - 1] == "-"]

    def head(cut: int) -> str:
        return word[:cut] if word[cut - 1] == "-" or not lgc else f"{word[:cut]}-"

    for cut in reversed(cuts):
        if _display_width(font, head(cut), script) <= max_width:
            return head(cut), word[cut:]
    return (head(cuts[0]), word[cuts[0] :]) if cuts else None


def _break_word(word: str, font: FontT, max_width: int, script: str) -> list[str]:
    """*word*, wider than *max_width*, in the parts `_split_word` gives; alone when it stays whole."""
    parts: list[str] = []
    while _display_width(font, word, script) > max_width:
        split = _split_word(word, font, max_width, script)
        if split is None:
            break
        parts.append(split[0])
        word = split[1]
    return [*parts, word]


def _wrap_chars(text: str, font: FontT, max_width: int) -> list[str]:
    """Wrap between characters (Chinese, Japanese, Thai): no spaces to break at."""
    lines: list[str] = []
    cur = ""
    for ch in text.replace(" ", ""):
        cand = cur + ch
        if not cur or text_width(font, cand) <= max_width or ch in _NO_LINE_START:
            cur = cand
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


# --- hyphenation at the limit ---------------------------------------------------------------------

def _latin_letter(ch: str) -> bool:
    return ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN")


def hyphen_points(word: str) -> list[int]:
    """Where a word may take a hyphen, cheaply and without a dictionary: at the syllable-like boundary between a
    vowel group and the consonants that follow it, before the longest of those that may start a syllable together
    (won-der, ma-gic, chil-dren, mas-ter), never between two letters that are one sound (ck, gh, ch, sh, th, ph, wh,
    qu) and never leaving fewer than `HYPHEN_HEAD` letters before it or `HYPHEN_EDGE` after it (ex-tra, not
    extraordinar-ily). None for a word of fewer than eight letters, for
    one with anything but Latin letters (a digit, an apostrophe, another script), or in capitals only (a shouted
    name)."""
    n = len(word)
    if n < HYPHEN_MIN_LETTERS or word.isupper() or not all(_latin_letter(c) for c in word):
        return []
    low = word.lower()
    vowel = [c in _VOWELS for c in low]
    if low[0] == "y":  # a consonant at the start
        vowel[0] = False
    for i in range(1, n):
        if low[i] == "u" and low[i - 1] == "q":
            vowel[i] = False
    points: list[int] = []
    i = 0
    while i < n:
        if not vowel[i]:
            i += 1
            continue
        j = i
        while j < n and vowel[j]:
            j += 1
        k = j
        while k < n and not vowel[k]:
            k += 1
        if j < n and k < n:  # consonants between two vowel groups
            cluster = low[j:k]
            m = len(cluster)
            onset = next((size for size in (3, 2) if size <= m and cluster[m - size:] in _ONSETS
                          and not (m == 2 and cluster in _S_ONSETS)), 1)
            cut = k - onset
            if cut > j and low[cut - 1:cut + 1] in _UNSPLIT:
                cut += 1
            if HYPHEN_HEAD <= cut <= n - HYPHEN_EDGE:
                points.append(cut)
        i = k
    return points


def _hyphenate(token: str, script: str, fits: Any) -> tuple[str, str] | None:
    """*token* (a word with its punctuation and emphasis markers) split at the last of its hyphenation points whose
    first part, with the hyphen, still *fits*: (that part, the rest); None when it has none that fits."""
    if script != "lgc":
        return None
    a = 0
    while a < len(token) and not token[a].isalpha():
        a += 1
    b = a
    while b < len(token) and token[b].isalpha():
        b += 1
    lead, word, trail = token[:a], token[a:b], token[b:]
    if any(c.isdigit() for c in lead + trail) or any(c.isalpha() for c in trail):
        return None
    for p in reversed(hyphen_points(word)):
        head = f"{lead}{word[:p]}-"
        if fits(head):
            return head, word[p:] + trail
    return None


def wrap_lines(text: str, font: FontT, max_width: int, script: str | None = None, keep_blank: bool = False,
               hyphenate: int = 0, stats: dict[str, int] | None = None) -> list[str]:
    """Wrap *text* to *max_width*; words wider than the box are split (`_split_word`; one too short to split stays
    whole, wider than the box). Each line break ends a line;
    an empty line is left out, or with *keep_blank* kept as an empty line. With *hyphenate*, a word wider than the
    box is first hyphenated at its syllable-like points (`hyphen_points`), and with *hyphenate* 2 a word that does
    not fit the rest of a line also gives the line its first part. *stats* counts the hyphens and the words split
    or left wider than the box ("breaks")."""
    script = script or script_of(text)
    lines: list[str] = []
    for para in text.replace("\r", "").split("\n"):
        if keep_blank and not para.strip():
            lines.append("")
            continue
        if script in NO_SPACE_SCRIPTS:
            lines.extend(_wrap_chars(para.strip(), font, max_width))
            continue
        words = para.split()
        if not words:
            continue
        cur = ""
        for word in words:
            cand = f"{cur} {word}".strip()
            if _display_width(font, cand, script) <= max_width:
                cur = cand
                continue
            if hyphenate >= 2 and cur:  # the line filled with the word's first part
                split = _hyphenate(word, script, lambda head: _display_width(font, f"{cur} {head}", script) <= max_width)
                if split is not None:
                    cur, word = f"{cur} {split[0]}", split[1]
                    _count(stats, "hyphens")
            if cur:
                lines.append(cur)
            while hyphenate and _display_width(font, word, script) > max_width:  # a word wider than the line
                split = _hyphenate(word, script, lambda head: _display_width(font, head, script) <= max_width)
                if split is None:
                    break
                lines.append(split[0])
                word = split[1]
                _count(stats, "hyphens")
            if _display_width(font, word, script) <= max_width:
                cur = word
            else:
                pieces = _break_word(word, font, max_width, script)
                lines.extend(pieces[:-1])
                cur = pieces[-1] if pieces else ""
                _count(stats, "breaks")
        if cur:
            lines.append(cur)
    return lines


def _count(stats: dict[str, int] | None, what: str) -> None:
    """A word hyphenated ("hyphens") or that fit nowhere ("breaks": split, or left too wide), counted when asked."""
    if stats is not None:
        stats[what] = stats.get(what, 0) + 1


def fit_text(text: str, font_path: str | Lettering | None, box_w: int, box_h: int, min_size: int = 9,
             max_size: int = 64, line_spacing: float = 1.12, bold_variation: bool = False,
             script: str | None = None) -> tuple[FontT, list[str], int]:
    """Largest font size whose wrapped text fits (box_w x box_h). Falls back to min_size."""
    box_w, box_h = max(4, box_w), max(4, box_h)
    script = script or script_of(text)
    hi = max(min_size, min(max_size, int(box_h / line_spacing)))
    words = text.split() if script not in NO_SPACE_SCRIPTS else []
    size = hi
    while size >= min_size:
        font = styled_font(font_path, size, bold_variation)
        # Prefer a smaller size over splitting a word across lines.
        if all(_display_width(font, w, script) <= box_w for w in words):
            lines = wrap_lines(text, font, box_w, script)
            line_h = size * line_spacing
            if lines and len(lines) * line_h <= box_h and all(_display_width(font, ln, script) <= box_w for ln in lines):
                return font, lines, size
        size -= 1 if size <= 24 else 2
    font = styled_font(font_path, min_size, bold_variation)
    return font, wrap_lines(text, font, box_w, script), min_size


def _fill_line(tokens: list[str], start: int, font: FontT, width: int, script: str, allow_break: bool,
               widths: dict[str, int], hyphenate: int = 0,
               stats: dict[str, int] | None = None) -> tuple[str, int] | None:
    """The longest run of *tokens* from *start* that fits *width* (words joined by spaces, characters as they are)
    and the index after it. None when the first token is wider than *width* and may not be broken; when it may,
    the line is its first part and the rest stays in *tokens* at *start*, or all of it, wider than *width*, when it
    is too short to split (`_split_word`). With *hyphenate*, a token too wide for
    the line on its own is hyphenated first (`hyphen_points`), and with *hyphenate* 2 one that does not fit the rest
    of the line also gives it its first part; the rest stays in *tokens*. *stats* counts the hyphens and the
    breaks."""
    chars = script in NO_SPACE_SCRIPTS
    cur = ""
    i = start

    def fits(cand: str) -> bool:
        wd = widths.get(cand)
        if wd is None:
            wd = widths[cand] = _display_width(font, cand, script)
        return wd <= width

    while i < len(tokens):
        cand = tokens[i] if not cur else (cur + tokens[i] if chars else f"{cur} {tokens[i]}")
        wd = widths.get(cand)
        if wd is None:
            wd = widths[cand] = _display_width(font, cand, script)
        if wd <= width or (chars and cur and tokens[i] in _NO_LINE_START):
            cur = cand
            i += 1
            continue
        if hyphenate and not chars and (not cur or hyphenate >= 2):
            split = _hyphenate(tokens[i], script, lambda head: fits(f"{cur} {head}" if cur else head))
            if split is not None:
                tokens[i : i + 1] = [split[1]]
                _count(stats, "hyphens")
                return (f"{cur} {split[0]}" if cur else split[0]), i
        if cur:
            return cur, i
        if not allow_break:
            return None
        _count(stats, "breaks")
        split = None if chars else _split_word(tokens[i], font, width, script)
        if split is None:  # a single character, or a word that stays whole: wider than the line
            return tokens[i], i + 1
        tokens[i : i + 1] = [split[1]]
        return split[0], i
    return cur, i


def _layout_at(paras: list[list[str]], font: FontT, script: str, size: int, line_spacing: float, top: int,
               left: np.ndarray, right: np.ndarray, allow_break: bool,
               widths: dict[str, int], hyphenate: int = 0, stats: dict[str, int] | None = None,
               ink: tuple[int, int] = (0, 0)) -> list[tuple[str, float, int]] | None:
    """The lines of *paras* set from *top* down, each as wide as the mask is at its rows: (text, x centre, y top).
    None when they do not fit (a line's rows leave the mask, or a word is wider than its line). An empty paragraph
    (an empty line kept) takes a line's height and sets nothing. *hyphenate* and *stats* as for `_fill_line`. *ink*
    is where a line's glyphs lie below its top (`_ink_rows`): each line must fit the mask over those rows."""
    h = left.shape[0]
    lh = size * line_spacing
    out: list[tuple[str, float, int]] = []
    line = 0
    for para in paras:
        tokens = list(para)
        if not tokens:
            y = int(round(top + line * lh))
            if y + ink[0] < 0 or y + ink[1] > h:
                return None
            out.append(("", out[-1][1] if out else left.shape[1] / 2.0, y))
            line += 1
            continue
        i = 0
        while i < len(tokens):
            y = int(round(top + line * lh))
            a, b = y + ink[0], max(y + ink[1], y + ink[0] + 1)
            if a < 0 or b > h:
                return None
            lo, hi = int(left[a:b].max()), int(right[a:b].min())
            if hi - lo < size:
                return None  # the band leaves the mask, or is narrower than a glyph
            filled = _fill_line(tokens, i, font, hi - lo, script, allow_break, widths, hyphenate, stats)
            if filled is None:
                return None
            text, i = filled
            out.append((text, (lo + hi) / 2.0, y))
            line += 1
    return out


def _span_closes(joined: str, starts: list[int]) -> list[int]:
    """For each token of a paragraph (*joined*, the tokens starting at *starts*) that begins inside a stressed span,
    the index of the token that closes the span; -1 for the others. A line from such a token must reach the closing
    one: a line wholly inside a span has no marker and would lose the stress (`lettering.split_runs`)."""
    closes = [-1] * len(starts)
    marks = [bisect_right(starts, m) - 1 for m in emphasis_marks(joined)]
    for opener, closer in zip(marks[::2], marks[1::2]):
        for t in range(opener + 1, closer + 1):
            closes[t] = closer
    return closes


def _lone(tokens: list[str], j: int, core: int, chars: bool, last: bool) -> bool:
    """Whether the line of tokens[j:core] (*core*: where what hangs past its end begins) is a lone short word: one word
    of ORPHAN_LETTERS or fewer at the end of a paragraph (an orphan), of ORPHAN_FIRST_LETTERS or fewer on another line
    ("I" or "Je" on the narrow top line of an oval), its punctuation counted. Never in a script wrapped by character:
    without spaces a line of one character is no lone word, and the way round it breaks inside one (我 / 一个人 would
    become 我一 / 个人把), which is worse than a short line."""
    if chars:
        return False
    return core - j == 1 and len(tokens[j]) <= (ORPHAN_LETTERS if last else ORPHAN_FIRST_LETTERS)


def _balanced_lines(tokens: list[str], rooms: list[int], font: FontT, script: str) -> list[str] | None:
    """*tokens* (words, or characters in a script wrapped by character) on exactly `len(rooms)` lines, line k no wider
    than rooms[k]: the way with the least total slack cubed, a last line free of penalty for the first LAST_LINE_FREE
    of its width, and a line of a lone short word (`_lone`) costing as much as an empty one (ORPHAN_SLACK). A line
    never starts with a character `_NO_LINE_START` forbids or a combining mark (Thai), and such characters at its end
    may run past the room, as in `_wrap_chars`; a stressed span's words may share out over two
    lines but no line lies wholly inside one. None when there is no such way."""
    chars = script in NO_SPACE_SCRIPTS
    glue = "" if chars else " "
    n, count = len(tokens), len(rooms)
    if n < count:
        return None
    starts, at = [], 0
    for token in tokens:
        starts.append(at)
        at += len(token) + len(glue)
    joined = glue.join(tokens)
    closes = _span_closes(joined, starts)
    no_start = [chars and (t in _NO_LINE_START or unicodedata.category(t) == "Mn") for t in tokens] + [False]
    known: dict[tuple[int, int], int] = {}

    def line(j: int, i: int) -> str:
        return joined[starts[j] : starts[i - 1] + len(tokens[i - 1])]

    def width(j: int, i: int) -> int:
        wd = known.get((j, i))
        if wd is None:
            wd = known[j, i] = _display_width(font, line(j, i), script)
        return wd

    inf = float("inf")
    cost = [inf] * (n + 1)
    cost[0] = 0.0
    back: list[list[int]] = []
    for k, room in enumerate(rooms):
        last = k == count - 1
        free = LAST_LINE_FREE * room if last else 0.0
        now = [inf] * (n + 1)
        came = [-1] * (n + 1)
        for j in range(k, n):
            if cost[j] == inf:
                continue
            for i in range(n if last else max(j + 1, closes[j] + 1), n - (count - k - 1) + 1):
                core = i
                while chars and core - 1 > j and no_start[core - 1]:
                    core -= 1  # what hangs past the room at the end of a line
                wd = width(j, core)
                if wd > room:
                    break
                if no_start[i]:
                    continue
                slack = max(0.0, room - wd - free)
                if count > 1 and _lone(tokens, j, core, chars, last):
                    slack = max(slack, ORPHAN_SLACK * room)
                total = cost[j] + slack**3
                if total < now[i]:
                    now[i], came[i] = total, j
        cost = now
        back.append(came)
    if cost[n] == inf:
        return None
    ends = [n]
    for came in reversed(back):
        ends.append(came[ends[-1]])
    ends.reverse()
    return [line(a, b) for a, b in zip(ends, ends[1:])]


def _line_rooms(fit: Fit) -> list[int] | None:
    """How wide each line of *fit* may be: the rectangle's width, or for a layout along the bubble's body each line's
    room as `_plan` measured it. None when it cannot be told (the last resort along the body)."""
    if fit.method == "rect" and fit.measure:
        return [fit.measure] * len(fit.lines)
    if fit.method == "shape" and fit.rooms:
        return list(fit.rooms)
    return None


def _balanced(fit: Fit, text: str, script: str) -> Fit:
    """*fit* with its words shared out over the same lines (`_balanced_lines`), paragraph by paragraph: every line stays
    where it is and as wide as it may be, the size and the number of lines do not change. A paragraph with a hyphen or
    a word split (its lines no longer are its tokens) and all after it stay as they are, and so does a paragraph
    without a valid way. A layout along the bubble's body is left as it is: `_plan_lines` shared its words out."""
    if not BALANCE_LINES or len(fit.lines) < 2 or fit.overflow or fit.method == "shape":
        return fit
    rooms = _line_rooms(fit)
    if rooms is None:
        return fit
    chars = script in NO_SPACE_SCRIPTS
    glue = "" if chars else " "
    lines = list(fit.lines)
    k = 0
    for para in text.replace("\r", "").split("\n"):
        tokens = list(para.replace(" ", "")) if chars else para.split()
        if not tokens:
            k += 1 if k < len(lines) and not lines[k][0] else 0  # a kept empty line
            continue
        whole = glue.join(tokens)
        held = ""
        end = k
        while len(held) < len(whole) and end < len(lines):
            held = glue.join(filter(None, (held, lines[end][0])))
            end += 1
        if held != whole:
            break
        if end - k > 1:
            better = _balanced_lines(tokens, rooms[k:end], fit.font, script)
            if better is not None:
                lines[k:end] = [(line, *lines[k + i][1:]) for i, line in enumerate(better)]
        k = end
    return replace(fit, lines=lines)


def page_caps(sized: Sequence[tuple[str, int, float]], least: int = 0) -> list[int]:
    """The largest size each lettering of a page may take, from the (kind, size it fits at, size of the original
    lettering, 0 when not measured) of all of them: `SIZE_CAP` times the median of its kind, so that a short line in a
    big bubble looks like its neighbours, and as much more as the original stood out from its neighbours' by
    `STANDS_OUT` or more (a cry lettered huge stays huge, reader's kind or not), never under *least*; 0 for no cap (kinds meant to be large,
    `UNCAPPED_KINDS`, and everything without a `SIZE_CAP`). An empty kind is plain speech. Depends on nothing but what
    is passed: the same page gives the same caps to whoever asks."""
    if not SIZE_CAP:
        return [0] * len(sized)
    sizes: dict[str, list[int]] = defaultdict(list)
    originals: dict[str, list[float]] = defaultdict(list)
    for kind, size, original in sized:
        sizes[kind or "speech"].append(size)
        if original > 0:
            originals[kind or "speech"].append(original)
    caps = []
    for kind, _size, original in sized:
        kind = kind or "speech"
        stands_out = original / median(originals[kind]) if original > 0 else 1.0
        scale = stands_out if stands_out >= STANDS_OUT else 1.0
        cap = max(least, int(round(SIZE_CAP * median(sizes[kind]) * scale)))
        caps.append(0 if kind in UNCAPPED_KINDS else cap - cap % 2 if cap > 24 else cap)  # above 24 sizes go by twos
    return caps


# --- the automatic layout: the lines along the bubble's body ------------------------------------------------------

MARGIN_EM = 0.3  # how far the lines' ink keeps off the bubble's outline, of the size ...
MARGIN_PX = 3  # ... and at least this many pixels
TAIL_OPEN = 0.14  # a tail is cut off by an opening this wide (of the mask's shorter side) before the body is measured
ROUND_FILL = 0.88  # a body that fills less of its bounding box than this is round
LOBE_CORES = (0.55, 0.7, 0.85)  # two bubbles joined at a neck: the parts of the body deeper than one of these (of its
LOBE_PEAK = 0.7  # deepest point, the first that parts it) apart, each as deep as this at its deepest, are each also
STRADDLE = 1.0  # tried as the room for the whole text; the whole body then counts this many defects (across the neck)
LONE_LETTERS = 5  # a line of one word of at most so many letters (its punctuation aside) is a lone short word ...
LONE_WORDS = 3  # ... in a paragraph of so many words or more (in "Hey, / you!" it has no way out), and not a sentence
# of its own ("Fine. / Whatever.")
COLUMN_WORDS = 2.0  # a block of fewer words a line than this is a column: a size is traded only for fewer hyphens
SIZE_TRADE = 0.2  # the largest share of the size a better block may cost ...
TRADE_PER_DEFECT = 0.1  # ... this share for each defect it has fewer of (`_defects`)
TRADE_TRIES = 4  # the smaller sizes tried for a better block
HOURGLASS = 0.85  # an inner line at most this share of the narrower of its neighbours makes an hourglass
EXTRA_LINES = 2  # the most lines a block is set on beyond the fewest it fits on (more make a tall, thin block)
# What a block costs (`_plan_lines`): each line the square of its distance from its target width (`_targets`, of the
# widest room), and on top of that:
COST_LONE = 0.12  # a line of a lone short word
COST_WEAK = 0.12  # a line ending on a word that leans on the next one (an article, a preposition, a conjunction)
COST_NAME = 0.06  # a break inside a name ("Captain / Velasquez", "Mirela / Hartwell")
COST_CLAUSE = 0.02  # a break inside a clause; after a comma, a colon or a dash COST_COMMA; after a sentence nothing
COST_COMMA = 0.006
COST_HYPHEN = 0.3  # a word hyphenated at its hyphenation point
COST_OWN_HYPHEN = 0.1  # a break after a word's own hyphen ("well- / known")
COST_OFF = 0.08  # the block moved off the centre, per line's height squared
COST_EVEN = 0.6  # the gap above and below the block against its lines' gap at the sides (of the widest room, squared)
COST_DEFECT = 0.1  # each of the block's defects (`_defects`), between the blocks of one size
# Words that lean on the next one, by language (a line should not end on them); other languages have none here
WEAK_WORDS = {"english": frozenset("""a an the my your his her its our their of to in on at by for with from into onto
    upon about over under after before between through during without within against toward towards across behind
    beyond near off per via and or but nor so yet as if than because although though while whereas unless until
    whether""".split())}
# Words that go with the name after them, by language (a break between them splits the name)
TITLES = {"english": frozenset("""mr mr. mrs mrs. ms ms. dr dr. st. prof. mister miss madam sir lady lord captain
    professor doctor uncle aunt auntie king queen prince princess general officer detective inspector sergeant
    lieutenant commander major colonel president chief master saint father sister brother""".split())}
NAME_LANGUAGES_NOT = ("german",)  # languages that capitalise every noun: a capital inside a sentence is no name there
_SENTENCE_END = set(".!?…。！？")
_SOFT_END = set(",;:、，；：")
_DASHES = ("—", "–", "--", "-")
_CLOSING = set(",.;:!?…)]}»”’、。，．！？")  # a token of these alone belongs to the line before it
_OPENING = set("([{«“‘¿¡\"'")  # a token of these alone belongs to the line after it
_NO_LINE_END = set("「『（【〈《〔［｛(")  # characters that must not end a line in CJK text
_TRAILERS = "\"'”’»)]}*"  # what may follow a word's last letter or its stop
_NOT_NAMES = frozenset({"I", "I'm", "I'll", "I've", "I'd", "OK", "Ok"})


@dataclass(frozen=True, eq=False)
class _Body:
    """A room for the lines: per pixel its distance to the outside (*depth*), the centre the block is set on (*cx*,
    *cy*, on pixel edges), whether it is round, its first and last rows (exclusive), the defects a block in it counts
    for lying across a neck (*straddle*: the whole of two bubbles joined, `_bodies`), and whether its lines share one
    centre axis (*axis*: in a bubble; text on the page follows the room it has, each line centred in its own run)."""

    depth: np.ndarray
    cx: float
    cy: float
    round: bool
    rows: tuple[int, int]
    straddle: float = 0.0
    axis: bool = True
    _extents: dict[float, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict, init=False, repr=False)

    def extent(self, margin: float) -> tuple[np.ndarray, np.ndarray]:
        """Per row, from where to where a line may reach with its ink more than *margin* px from the outside: the run
        of the row's pixels that deep through the centre column, on a shared axis as far to either side as its nearer
        end allows (nothing where the centre column itself is not that deep). Remembered: the sizes tried ask again."""
        known = self._extents.get(margin)
        if known is not None:
            return known
        ok = self.depth > margin
        w = ok.shape[1]
        c = min(w - 1, max(0, int(self.cx)))
        cols = np.arange(w)
        left = (np.where(~ok[:, : c + 1], cols[: c + 1], -1).max(axis=1) + 1).astype(np.float64)
        right = np.where(~ok[:, c:], cols[c:], w).min(axis=1).astype(np.float64)
        if self.axis:
            half = np.maximum(np.minimum(self.cx - left, right - self.cx), 0.0)
            left, right = self.cx - half, self.cx + half
        gone = ~ok[:, c]
        left[gone] = right[gone] = self.cx
        if len(self._extents) < 64:
            self._extents[margin] = (left, right)
        return left, right


def _depth(inside: np.ndarray) -> np.ndarray:
    """Each pixel's distance to the nearest pixel outside *inside* (or off the image)."""
    padded = np.pad(inside.astype(np.uint8), 1)
    return cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]


def _grown(core: np.ndarray, radius: float) -> np.ndarray:
    """The pixels within *radius* of *core*: a dilation by a disc, through a distance transform (fast at any radius)."""
    return cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 5) <= radius


def _room_of(part: np.ndarray, centre: tuple[float, float] | None = None,
             depth: np.ndarray | None = None) -> _Body | None:
    """*part* as a `_Body` (*depth*: its `_depth`, when known): a bubble's, centred on its centroid, or text on the
    page's around *centre*, each line in its own run (no shared axis, never round)."""
    ys, xs = np.nonzero(part)
    if xs.size == 0:
        return None
    bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    cx, cy = centre if centre is not None else (float(xs.mean()) + 0.5, float(ys.mean()) + 0.5)
    return _Body(_depth(part) if depth is None else depth, float(cx), float(cy),
                 centre is None and xs.size < ROUND_FILL * bw * bh, (int(ys.min()), int(ys.max()) + 1),
                 axis=centre is None)


def _bodies(mask: np.ndarray, centre: tuple[float, float] | None) -> list[_Body]:
    """The rooms the lines of a text may be set in inside *mask*. For text on the page (*centre*: its lettering's)
    the mask as it is, the block centred there. For a bubble its body: the tail cut off (an opening `TAIL_OPEN` of
    the mask's shorter side wide, the largest part kept), the block centred on the body's centroid; and where the body
    narrows to a neck between deep parts (`LOBE_CORES`, `LOBE_PEAK`: two bubbles joined), each of those parts on its
    own as well, so that one translation for both is set in one rather than along the neck (the whole body then
    counts `STRADDLE` defects against them)."""
    inside = mask > 0
    if centre is not None:
        found = _room_of(inside, centre)
        return [found] if found is not None else []
    ys, xs = np.nonzero(inside)
    if xs.size == 0:
        return []
    radius = TAIL_OPEN * min(int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)) / 2.0
    depth = _depth(inside)
    body = inside
    if radius >= 1.5:  # the opening: what a disc of that radius reaches, rolled round inside the mask
        opened = _grown(depth > radius, radius) & inside
        n, labels, stats, _ = cv2.connectedComponentsWithStats(opened.astype(np.uint8), connectivity=8)
        if n > 1:
            body = labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            if int(stats[1:, cv2.CC_STAT_AREA].max()) < int(inside.sum()):
                depth = _depth(body)  # the tail cut off: the body's own depth
    whole = _room_of(body, depth=depth)
    if whole is None:
        return []
    peak = float(whole.depth.max())
    if peak < 6:
        return [whole]
    for share in LOBE_CORES:
        n, labels, _stats, _ = cv2.connectedComponentsWithStats((whole.depth > share * peak).astype(np.uint8),
                                                                connectivity=8)
        cores = [labels == i for i in range(1, n)]
        cores = [core for core in cores if float(whole.depth[core].max()) >= LOBE_PEAK * peak]
        if len(cores) < 2:
            continue  # one core: no neck this deep
        lobes = [_room_of(_grown(core, share * peak) & body) for core in cores]
        return [replace(whole, straddle=STRADDLE), *(lobe for lobe in lobes if lobe is not None)]
    return [whole]


@dataclass
class _Pieces:
    """A text cut where its lines may break: the pieces (words, the parts of a word between its hyphenation points,
    or the characters of a script wrapped by character), what joins each to the one before (*glue*: 0 a line break of
    the text, 1 a space, 2 a hyphenation point, 3 a word's own hyphen, 4 nothing: between characters), the word each
    belongs to, per word whether it is a lone short word alone on a line, per piece where a line starting with it must
    reach at least (*need*: past the end of a stressed span it starts inside), and per position what a break there
    costs and whether one may be made; once measured (`_measure`) their widths."""

    text: list[str]
    glue: list[int]
    token: list[int]
    lone: list[bool]
    need: list[int]
    cost: list[float]
    breaks: list[bool]
    hang: list[bool] = field(default_factory=list)  # per piece: a character that may hang past the room at a line's end
    width: list[float] = field(default_factory=list)
    gap: list[float] = field(default_factory=list)  # per piece: the width of its glue when the line goes on
    cum: list[float] = field(default_factory=list)  # per position: the widths of the pieces before it, glue and all
    hyphen: float = 0.0  # the width of the hyphen a break at a hyphenation point adds
    back: list[int] = field(default_factory=list)  # per position: where the characters that may hang before it start
    # how wide what hangs may be past the room: a centred line hangs half of it out on each side, so a body's layout
    # keeps it within its margin (`_plan`); what is wider counts against the room
    allow: float = float("inf")

    def core(self, j: int, i: int) -> int:
        """Where the characters that may hang past the room at the end of the line j..i-1 start (i: none)."""
        return max(j + 1, self.back[i]) if self.back[i] < i else i

    def over(self, core: int, i: int) -> float:
        """How much of what hangs at the end of a line (pieces core..i-1) its room must hold: what is wider than
        *allow*."""
        return max(0.0, self.cum[i] - self.cum[core] - self.allow) if core < i else 0.0

    def span(self, j: int, i: int) -> float:
        """The width of the line of pieces j..i-1 as measured against its room: what hangs left out (but what is wider
        than *allow*), the hyphen of a break at a hyphenation point added."""
        core = self.core(j, i)
        return (self.cum[core] - self.cum[j] - self.gap[j] + self.over(core, i)
                + (self.hyphen if i < len(self.text) and self.glue[i] == 2 else 0.0))

    def line(self, j: int, i: int) -> str:
        parts = [self.text[j]]
        for q in range(j + 1, i):
            parts.append((" " if self.glue[q] == 1 else "") + self.text[q])
        if i < len(self.text) and self.glue[i] == 2:
            parts.append("-")
        return "".join(parts)

    def whole_word(self, j: int, i: int) -> bool:
        """Whether the line j..i-1 is one word, whole."""
        n = len(self.text)
        whole = (0, 1, 4)  # a paragraph's start, a space, a break between characters
        return self.token[j] == self.token[i - 1] and self.glue[j] in whole and (i == n or self.glue[i] in whole)


def _core(token: str) -> tuple[int, int]:
    """Where the letters and digits of *token* start and end (its punctuation and markers round them left out)."""
    a = 0
    while a < len(token) and not token[a].isalnum():
        a += 1
    b = len(token)
    while b > a and not token[b - 1].isalnum():
        b -= 1
    return a, b


def _words(text: str, script: str, keep_blank: bool) -> list[list[str]]:
    """The paragraphs of *text* (its line breaks) as words, or characters in a script wrapped by character; an empty
    one kept only with *keep_blank*, never at the start or the end."""
    paras = []
    for para in text.replace("\r", "").split("\n"):
        tokens = list(para.replace(" ", "")) if script in NO_SPACE_SCRIPTS else para.split()
        if tokens or keep_blank:
            paras.append(tokens)
    while paras and not paras[-1]:
        paras.pop()
    while paras and not paras[0]:
        paras.pop(0)
    return paras


def _language(language: str) -> str:
    return language.strip().lower().split()[0] if language.strip() else ""


def _cut(paras: list[list[str]], script: str, language: str, hyphenate: int, too_wide: Any) -> _Pieces:
    """*paras* cut into `_Pieces`. With *hyphenate* 2 every Latin word of eight letters or more may take a hyphen at
    its hyphenation points (`hyphen_points`), with 1 only one *too_wide* says fits on no line; never a name (a word
    with a capital inside a sentence, but in `NAME_LANGUAGES_NOT`). A word with a hyphen of its own may break after it.
    A break is free after a sentence, cheap after a comma, a colon or a dash, dearer inside a clause, dearer still where
    it leaves a word that leans on the next one at a line's end (`WEAK_WORDS` of *language*) or splits a name (two
    capitalised words inside a sentence, or a title of `TITLES` and a name); impossible before a token of closing
    punctuation alone or after one of opening punctuation alone, and in a script wrapped by character before a
    character `_NO_LINE_START` forbids or a combining mark and after one `_NO_LINE_END` forbids."""
    chars = script in NO_SPACE_SCRIPTS
    lgc = script == "lgc"
    lang = _language(language)
    weak = WEAK_WORDS.get(lang, frozenset())
    titles = TITLES.get(lang, frozenset())
    names = lgc and lang not in NAME_LANGUAGES_NOT
    out = _Pieces([], [], [], [], [], [], [])
    t = 0
    for para in paras:
        if not para:  # an empty line kept: a piece of its own
            out.text.append("")
            out.glue.append(0)
            out.token.append(t)
            out.lone.append(False)
            out.need.append(len(out.text))
            out.cost.append(0.0)
            out.breaks.append(True)
            out.hang.append(False)
            t += 1
            continue
        sep = "" if chars else " "
        joined = sep.join(para)
        marks = emphasis_marks(joined)
        spans = list(zip(marks[::2], marks[1::2]))
        first = len(out.text)
        starts: list[int] = []
        at = 0
        prev_name = False
        for n, tok in enumerate(para):
            a, b = _core(tok)
            core = tok[a:b]
            prev = para[n - 1] if n else ""
            stop = prev.rstrip(_TRAILERS)[-1:] if prev else ""
            prev_core = prev[slice(*_core(prev))] if prev else ""
            ends_sentence = stop in _SENTENCE_END and not (stop == "." and prev_core.lower() + "." in titles)
            capital = bool(core) and core[0].isupper() and core not in _NOT_NAMES
            name = names and capital and n > 0 and not ends_sentence
            sentence = (n == 0 or ends_sentence) and tok.rstrip(_TRAILERS)[-1:] in _SENTENCE_END  # "Fine." alone
            out.lone.append(not chars and not sentence and len(para) >= LONE_WORDS
                            and sum(ch.isalpha() for ch in tok) <= LONE_LETTERS)
            if n == 0:
                cost, ok = 0.0, True
            elif chars:
                cost = 0.0 if stop in _SENTENCE_END else COST_COMMA if stop in _SOFT_END else 0.0
                ok = not (tok in _NO_LINE_START or unicodedata.category(tok) == "Mn" or prev in _NO_LINE_END)
            else:
                soft = stop in _SOFT_END or prev in _DASHES or prev.endswith(("—", "–", "--"))
                cost = 0.0 if ends_sentence else COST_COMMA if soft else COST_CLAUSE
                if not soft and not ends_sentence:
                    if prev.strip(_TRAILERS).lower() in weak:
                        cost += COST_WEAK
                    if name and prev_name:
                        cost += COST_NAME
                ok = not all(ch in _CLOSING for ch in tok) and not all(ch in _OPENING for ch in prev)
            prev_name = name or (capital and n == 0 and core.lower() in titles)
            points: list[int] = []
            if lgc and hyphenate and not name and a < b and core.isalpha() and (hyphenate >= 2 or too_wide(tok)):
                points = hyphen_points(core)
            own = ([i for i in range(1, len(core) - 1) if core[i - 1] == "-" and core[i - 2:i - 1].isalpha()
                    and core[i].isalpha()] if lgc else [])
            cuts = sorted({a + p for p in points} | {a + p for p in own})
            for m, (s, e) in enumerate(zip([0, *cuts], [*cuts, len(tok)])):
                out.text.append(tok[s:e])
                out.token.append(t)
                out.hang.append(chars and (tok in _NO_LINE_START or unicodedata.category(tok) == "Mn"))
                starts.append(at + s)
                if m == 0:
                    out.glue.append(0 if n == 0 else 4 if chars else 1)
                    out.cost.append(cost)
                    out.breaks.append(ok)
                else:
                    after_own = s - a in own
                    out.glue.append(3 if after_own else 2)
                    out.cost.append(COST_OWN_HYPHEN if after_own else COST_HYPHEN)
                    out.breaks.append(True)
            at += len(tok) + len(sep)
            t += 1
        for q, s in enumerate(starts):  # a line starting inside a stressed span reaches past its end
            need = first + q + 1
            for opener, closer in spans:
                if opener < s <= closer:
                    need = first + max(k for k, start in enumerate(starts) if start <= closer) + 1
            out.need.append(need)
    out.cost.append(0.0)
    out.breaks.append(True)
    return out


def _measure(pieces: _Pieces, font: Any, script: str) -> None:
    """The widths of *pieces* in *font* (as drawn: right-to-left scripts turned round), their glue's and their sums."""
    styled = isinstance(font, StyledFont)
    scale = font.lettering.condense if styled else 1.0
    tracking = font.lettering.tracking * scale if styled else 0.0

    def wide(text: str) -> float:
        if not text:
            return 0.0
        shown = display_form(text, script)
        return font._natural(shown) * scale if styled else float(font.getlength(shown))

    space = wide(" ") + 2 * tracking
    pieces.width = [wide(t) for t in pieces.text]
    pieces.gap = [space if g == 1 else tracking if g in (2, 3, 4) else 0.0 for g in pieces.glue]
    pieces.hyphen = wide("-") + tracking
    cum = [0.0]
    for w, g in zip(pieces.width, pieces.gap):
        cum.append(cum[-1] + w + g)
    pieces.cum = cum
    back = list(range(len(pieces.text) + 1))
    if script in NO_SPACE_SCRIPTS:  # the characters that may not start a line hang at the end of the one before
        for i in range(2, len(pieces.text) + 1):
            if pieces.hang[i - 1]:
                back[i] = back[i - 1] if back[i - 1] < i - 1 else i - 1
    pieces.back = back


def _targets(rooms: list[float], total: float, floor: float) -> tuple[list[float], float]:
    """How wide each line of a block ought to be: its room less one gap shared by all the lines on both sides, so that
    the lines keep alike off the outline and follow it (an oval in an oval: short, long, short), all of them together
    as wide as the text (*total*); a line never aimed narrower than *floor*. Returns the targets and the gap."""
    n = len(rooms)
    fixed = [False] * n
    targets = list(rooms)
    gap = 0.0
    for _ in range(3):
        free = [k for k in range(n) if not fixed[k]]
        if not free:
            break
        rest = total - sum(targets[k] for k in range(n) if fixed[k])
        gap = max(0.0, (sum(rooms[k] for k in free) - rest) / (2.0 * len(free)))
        changed = False
        for k in free:
            targets[k] = rooms[k] - 2 * gap
            if targets[k] < floor:
                targets[k], fixed[k], changed = min(rooms[k], floor), True, True
        if not changed:
            break
    return targets, gap


def _plan_lines(pieces: _Pieces, rooms: list[float], targets: list[float], font: Any, script: str, widest: float,
                exact: dict[tuple[int, int], int], free_ends: bool = False) -> tuple[float, list[int]] | None:
    """The best way to set *pieces* on exactly `len(rooms)` lines, line k no wider than rooms[k]: a dynamic programme
    over the break positions, each line costing the square of its distance from targets[k] (of *widest*; with
    *free_ends* the last line of a paragraph only what it is wider), what the break at its end costs (`_cut`) and
    `COST_LONE` for a lone short word; no line wholly inside a stressed span, and in a script wrapped by
    character the characters that may not start a line hang past the room at the end of the one before, as in
    `_wrap_chars` (but what is wider than the pieces' *allow* counts against the room). A line near its room is
    measured exactly (*exact*: the widths measured so far, by (start, end)). Returns (the cost, the positions where the
    lines end, 0 first), or None when there is no way."""
    n, count = len(pieces.text), len(rooms)
    if n < count:
        return None
    glue, cum, gap, cost_at, may = pieces.glue, pieces.cum, pieces.gap, pieces.cost, pieces.breaks
    text, need, hyphen = pieces.text, pieces.need, pieces.hyphen
    limit = [n] * (n + 1)  # per start: the line break of the text after it, which no line passes
    nxt = n
    for p in range(n - 1, -1, -1):
        limit[p] = nxt
        if glue[p] == 0 and p > 0:
            nxt = p
    inf = float("inf")
    cost = [inf] * (n + 1)
    cost[0] = 0.0
    trail: list[list[int]] = []
    scale = 1.0 / max(1.0, widest) ** 2
    lone_line = [pieces.lone[pieces.token[q]] for q in range(n)]
    for k in range(count):
        room, target = rooms[k], targets[k]
        last = k == count - 1
        now = [inf] * (n + 1)
        came = [-1] * (n + 1)
        for j in range(k, n):
            base = cost[j]
            if base == inf:
                continue
            end = limit[j]
            top = min(end, n - (count - k - 1))
            first = max(j + 1, need[j]) if not last else n
            if not text[j]:  # an empty line kept: it holds itself alone
                if j + 1 <= top and (not last or j + 1 == n):
                    c = base + (cost_at[j + 1] if j + 1 < n else 0.0)
                    if c < now[j + 1]:
                        now[j + 1], came[j + 1] = c, j
                continue
            for i in range(first, top + 1):
                if i < n and i != end and not may[i]:
                    continue
                core = max(j + 1, pieces.back[i]) if pieces.back[i] < i else i
                hung = pieces.over(core, i)
                plain = cum[core] - cum[j] - gap[j] + hung
                if plain - 2 > room:
                    break
                w = plain + (hyphen if i < n and glue[i] == 2 else 0.0)
                if w + 2 > room:
                    key = (j, i)
                    if key not in exact:
                        exact[key] = _display_width(font, pieces.line(j, core) if core < i else pieces.line(j, i),
                                                    script)
                    if exact[key] + hung > room:
                        continue
                off = w - target if not free_ends or (i < n and glue[i] != 0) else max(0.0, w - target)
                c = base + off * off * scale
                if i < n:
                    c += cost_at[i]
                if count > 1 and lone_line[j] and pieces.whole_word(j, i):
                    c += COST_LONE
                if c < now[i]:
                    now[i], came[i] = c, j
        cost = now
        trail.append(came)
    if cost[n] == inf:
        return None
    ends = [n]
    for came in reversed(trail):
        ends.append(came[ends[-1]])
    ends.reverse()
    return cost[n], ends


def _greedy(pieces: _Pieces, rooms: list[float]) -> list[int] | None:
    """Where lines filled one after the other end (as much on each as its room takes; with fixed rooms nothing fits
    more), 0 first; None when the pieces do not all fit on `len(rooms)` lines."""
    n = len(pieces.text)
    glue, may = pieces.glue, pieces.breaks
    ends = [0]
    j = 0
    for room in rooms:
        if j >= n:
            break
        best = -1
        i = j + 1
        while i <= n:
            forced = i == n or glue[i] == 0
            if not pieces.text[j]:
                best = i
                break
            core = pieces.core(j, i)
            plain = pieces.cum[core] - pieces.cum[j] - pieces.gap[j] + pieces.over(core, i)
            if plain > room:
                break
            if (forced or may[i]) and pieces.span(j, i) <= room:
                best = i
            if forced:
                break
            i += 1
        if best < 0:
            return None
        ends.append(best)
        j = best
    return ends if j >= n else None


_BY_CHARACTER = frozenset({"lgc", "jp", "sc", "tc", "kr"})  # scripts whose glyphs keep their height beside any other


@functools.lru_cache(maxsize=1 << 16)
def _rows_of(font: Any, text: str) -> tuple[int, int]:
    """The rows *text*'s ink covers below a line's top in *font* (a loaded font: `fonts.load_font` keeps them)."""
    box = font.getbbox(text)
    return int(box[1]), int(box[3])


@functools.lru_cache(maxsize=4096)
def _ink_rows(font: Any, text: str, script: str = "") -> tuple[int, int]:
    """Where the ink of *text*'s lines lies below a line's top in *font*: from the highest glyph's top to the lowest
    one's foot over the whole text (a capital's, an accent's, a descender's), a synthetic bold's stroke included. In a
    script of `_BY_CHARACTER` without combining marks each character is measured once (and remembered), elsewhere the
    text as a whole: its marks stack and its letters join."""
    plain = strip_marks(text).replace("\n", " ").strip() or "H"
    if script in _BY_CHARACTER and not any(unicodedata.combining(ch) for ch in plain):
        parts: Any = set(plain) - {" "}
    else:
        parts = (plain,)
    faces = ([(face.font(font.size), face.stroke) for face in {font.base, font.emph}] if isinstance(font, StyledFont)
             else [(font, 0)])
    top, bottom = 10**6, -(10**6)
    for loaded, stroke in faces:
        for part in parts:
            a, b = _rows_of(loaded, part)
            if b > a:
                top, bottom = min(top, a - stroke), max(bottom, b + stroke)
    return (top, bottom) if bottom > top else _rows_of(faces[0][0], "H")


def _defects(pieces: _Pieces, ends: list[int], widths: list[int], round_room: bool) -> float:
    """What is wrong with a block, language aside, in the units a size is traded against (`TRADE_PER_DEFECT`): one for
    each lone short word on a line of its own, each hyphen and each hourglass (an inner line narrower than `HOURGLASS`
    of the narrower of its neighbours), and a half for a round block whose widest line is its first or its last."""
    found = float(sum(1 for i in ends[1:-1] if pieces.glue[i] == 2))
    if len(widths) > 1:
        found += sum(1 for j, i in zip(ends, ends[1:]) if pieces.text[j] and pieces.lone[pieces.token[j]]
                     and pieces.whole_word(j, i))
    if len(widths) >= 3:
        found += sum(1 for k in range(1, len(widths) - 1) if widths[k] < HOURGLASS * min(widths[k - 1], widths[k + 1]))
        if round_room and max(widths[0], widths[-1]) > max(widths[1:-1]):
            found += 0.5
    return found


@dataclass
class _Block:
    """A way to set a text at one size: the lines (text, x centre, y top), each line's room, what the way costs, the
    hyphens, what is wrong with it (`_defects`) and of that what a smaller size may be traded for (*traded*: in a
    column, fewer than `COLUMN_WORDS` words a line, the hyphens alone)."""

    lines: list[tuple[str, float, float]]
    rooms: tuple[int, ...]
    cost: float
    hyphens: int
    defects: float
    traded: float = 0.0


def _plan(body: _Body, paras: list[list[str]], text: str, font_path: str | Lettering | None, size: int,
          line_spacing: float, bold_variation: bool, script: str, valign: str, hyphenate: int, language: str,
          full: bool, cut: dict[Any, _Pieces] | None = None) -> _Block | bool | None:
    """*paras* at *size* in *body*. Without *full*, whether they fit at all (some number of lines, filled one after the
    other, at some place); with it the best block (`_Block`): over the numbers of lines that fit (up to `EXTRA_LINES`
    more than the fewest), the block centred on the body's centre (*valign* "middle"; a quarter or a half line's height
    off it where that fits, or has fewer defects, at `COST_OFF`), or as high or as low as it fits (*valign* "top",
    "bottom"), the lines shared out by `_plan_lines`, the block's gap above and below against its lines' at the sides
    (`COST_EVEN`); None when none fits. *cut* keeps the text's `_cut` from one size to the next."""
    font = styled_font(font_path, size, bold_variation)
    lh = size * line_spacing
    margin = max(float(MARGIN_PX), MARGIN_EM * size)
    left, right = body.extent(margin)
    rows = np.flatnonzero(right - left >= size)
    if rows.size == 0:
        return None if full else False
    ink_top, ink_bottom = _ink_rows(font, text, script)
    tall = max(1, ink_bottom - ink_top)
    widest = float((right - left).max())

    def too_wide(token: str) -> bool:
        return _display_width(font, token, script) > widest

    wide = frozenset(t for p in paras for t in p if too_wide(t)) if hyphenate == 1 and script == "lgc" else None
    key = (hyphenate, wide)
    pieces = cut.get(key) if cut is not None else None
    if pieces is None:
        pieces = _cut(paras, script, language, hyphenate, too_wide)
        if cut is not None:
            cut[key] = pieces
    _measure(pieces, font, script)
    pieces.allow = 2.0 * (margin - MARGIN_PX)  # what hangs reaches no nearer the outline than the smallest margin
    h = left.shape[0]
    y_lo, y_hi = int(rows[0]), int(rows[-1]) + 1
    space = pieces.gap[1] if len(pieces.gap) > 1 and pieces.glue[1] == 1 else 0.0
    total = pieces.cum[-1]
    fewest = max(len(paras), int(np.ceil(total / max(1.0, widest))))
    most = min(len(pieces.text), int((y_hi - y_lo - tall) / lh) + 1) if y_hi - y_lo >= tall else 0
    step = max(1, int(lh / 6))
    if h < tall:
        return None if full else False
    # per row: from where to where a line's ink from it may reach, its room and its centre
    starts = sliding_window_view(left, tall).max(axis=1)
    ends_at = sliding_window_view(right, tall).min(axis=1)
    narrowest = np.floor(np.maximum(ends_at - starts, 0.0))
    middles = body.cx if body.axis else (starts + ends_at) / 2.0

    def rooms_at(top: int, n: int) -> list[int] | None:
        at = [int(round(top + k * lh)) + ink_top for k in range(n)]
        if at[0] < 0 or at[-1] > h - tall:
            return None
        return at

    found: list[tuple[int, int, float, list[float], list[int]]] = []  # (lines, top, off the centre, rooms, rows)
    extra = EXTRA_LINES if len(paras) == 1 else 0
    for n in range(fewest, most + 1):
        if found and n > found[0][0] + extra:
            break
        block = (n - 1) * lh + tall
        mid = body.cy - block / 2.0 - ink_top
        if valign == "top":
            tops = list(range(y_lo - ink_top, int(y_hi - block - ink_top) + 1, step))
        elif valign == "bottom":
            tops = list(range(int(y_hi - block - ink_top), y_lo - ink_top - 1, -step))
        else:
            tops = [int(round(mid + d * lh)) for d in (0.0, 0.25, -0.25, 0.5, -0.5)]
        for top in tops:
            at = rooms_at(top, n)
            if at is None:
                continue
            rooms = narrowest[at].tolist()
            if min(rooms) < 1 or _greedy(pieces, rooms) is None:
                continue
            if not full:
                return True
            found.append((n, top, (top - mid) / lh if valign == "middle" else 0.0, rooms, at))
            if valign != "middle":
                break
    if not found:
        return None if full else False
    best: _Block | None = None
    exact: dict[tuple[int, int], int] = {}
    centred: dict[int, float] = {}  # per number of lines: the defects of its block nearest the centre
    found.sort(key=lambda f: (f[0], abs(f[2])))
    shared = len(paras) == 1  # one paragraph: its lines shaped as a block; several: each filled, its last line free
    for n, top, off, rooms, at in found:
        if n in centred and centred[n] == 0:
            continue  # the block nearest the centre has nothing wrong: no need to move it
        if BALANCE_LINES:
            targets, gap = (_targets(rooms, total - (n - len(paras)) * space, float(size)) if shared
                            else (rooms, 0.0))
            planned = _plan_lines(pieces, rooms, targets, font, script, widest, exact, not shared)
            if planned is None:
                continue
            cost, ends = planned
            if valign == "middle":
                cost += COST_OFF * off * off
                if shared:
                    block = (n - 1) * lh + tall
                    above, below = top + ink_top - y_lo, y_hi - (top + ink_top + block)
                    cost += COST_EVEN * ((max(0.0, (above + below) / 2.0) - gap) / widest) ** 2
        else:  # as the greedy fill leaves them
            ends = _greedy(pieces, rooms) or []
            if len(ends) - 1 != n:
                continue
            cost = abs(off)
        texts = [pieces.line(j, i) for j, i in zip(ends, ends[1:])]
        widths = [_display_width(font, t, script) for t in texts]
        defects = _defects(pieces, ends, widths, body.round)
        centred.setdefault(n, defects)
        cost += COST_DEFECT * defects
        if best is None or cost < best.cost:
            xs = [body.cx] * n if body.axis else [float(middles[r]) for r in at]
            hyphens = sum(1 for i in ends[1:-1] if pieces.glue[i] == 2)
            column = len(pieces.lone) < COLUMN_WORDS * n
            best = _Block([(t, x, top + k * lh) for k, (t, x) in enumerate(zip(texts, xs))],
                          tuple(int(r) for r in rooms), cost, hyphens, defects, float(hyphens) if column else defects)
    return best


def _sizes(lo: int, hi: int) -> list[int]:
    """The sizes tried from *hi* down to *lo*: by one up to 24, by two above (as `page_caps` gives its caps)."""
    out = []
    size = hi
    while size >= lo:
        out.append(size)
        size -= 1 if size <= 24 else 2
    return out


@dataclass
class _Shaped:
    """What `_shape_fit` found: the font, the lines (text, x centre, y top), the size, each line's room (none for a
    last resort), the hyphens, the words split as a last resort, what is wrong with the block (`_defects`), and the
    largest size the text fits at (*fits*: the size before a trade for a better block, what a rectangle competes
    with)."""

    font: Any
    lines: list[tuple[str, float, float]]
    size: int
    rooms: tuple[int, ...] = ()
    hyphens: int = 0
    breaks: int = 0
    defects: float = 0.0
    fits: int = 0


def _upper_bound(body: _Body, paras: list[list[str]], text: str, font_path: str | Lettering | None, top: int,
                 line_spacing: float, bold_variation: bool, script: str) -> int:
    """A size above which the text cannot fit in *body*: the area of its lines' ink at that size (their widths times the
    height of their ink, `_ink_rows`) against the room's, and (but in a script wrapped by character) its widest word
    against the widest line."""
    probe = styled_font(font_path, 100, bold_variation)
    glue = "" if script in NO_SPACE_SCRIPTS else " "
    area = sum(_display_width(probe, glue.join(p), script) for p in paras if p) / 100.0
    ink_top, ink_bottom = _ink_rows(probe, text, script)
    room = float((body.depth > MARGIN_PX).sum())
    bound = (room / max(1e-6, area * max(1, ink_bottom - ink_top) / 100.0)) ** 0.5 + 2
    if script not in NO_SPACE_SCRIPTS:
        longest = max((_display_width(probe, w, script) for p in paras for w in p), default=1) / 100.0
        left, right = body.extent(float(MARGIN_PX))
        bound = min(bound, float((right - left).max()) / max(1e-6, longest) + 2)
    return int(min(top, bound))


def _fit_body(body: _Body, paras: list[list[str]], text: str, font_path: str | Lettering | None, sizes: list[int],
              line_spacing: float, bold_variation: bool, script: str, valign: str, hyphenate: int,
              language: str, cut: dict[Any, _Pieces] | None = None) -> _Shaped | None:
    """`_shape_fit` in one room: the largest of *sizes* that fits, found from an upper bound (`_upper_bound`) in
    growing steps down, then one size at a time up again between the last that did not fit and the first that did (no
    size is taken to fit because a larger one does), its best block, or a smaller size's up to `SIZE_TRADE` below
    with fewer defects (`TRADE_PER_DEFECT` of the size each) - but for text that fits at the largest of *sizes*: held
    there by a cap (the page's, the lettering size's), it has room to spare and keeps the size the cap gives it. A
    column (`COLUMN_WORDS`) trades for fewer hyphens alone: its lone words and uneven lines are the way a narrow bubble
    is set, and a smaller size only leaves the bubble emptier."""
    ceiling = sizes[0]
    bound = _upper_bound(body, paras, text, font_path, sizes[0], line_spacing, bold_variation, script)
    sizes = [s for s in sizes if s <= bound] or sizes[-1:]
    known: dict[int, bool] = {}
    cut = {} if cut is None else cut  # the text cut once for all the sizes (`_plan`)

    def fits(i: int) -> bool:
        if sizes[i] not in known:
            known[sizes[i]] = bool(_plan(body, paras, text, font_path, sizes[i], line_spacing, bold_variation, script,
                                         valign, hyphenate, language, False, cut))
        return known[sizes[i]]

    found, bad, i, step = -1, -1, 0, 1
    while i < len(sizes):
        if fits(i):
            found = i
            break
        bad, i, step = i, i + step, step + 1
    if found < 0:
        if bad == len(sizes) - 1 or not fits(len(sizes) - 1):
            return None
        found = len(sizes) - 1
    for i in range(bad + 1, found):  # the sizes stepped over: the largest of them that fits
        if fits(i):
            found = i
            break
    block = None
    for i in range(found, len(sizes)):
        if i == found or fits(i):
            block = _plan(body, paras, text, font_path, sizes[i], line_spacing, bold_variation, script, valign,
                          hyphenate, language, True, cut)
            if isinstance(block, _Block):
                found = i
                break
    if not isinstance(block, _Block):
        return None
    size = sizes[found]
    chosen = (size, block)
    if block.traded > 0 and size < ceiling:
        score = block.traded
        least = size * (1.0 - SIZE_TRADE)
        for s in [s for s in sizes[found + 1:] if s >= least][:TRADE_TRIES]:
            other = _plan(body, paras, text, font_path, s, line_spacing, bold_variation, script, valign, hyphenate,
                          language, True, cut)
            if not isinstance(other, _Block):
                continue
            mine = other.traded + (1.0 - s / size) / TRADE_PER_DEFECT
            if mine < score - 1e-9:
                score, chosen = mine, (s, other)
            if other.traded == 0:
                break
    largest = size
    size, block = chosen
    return _Shaped(styled_font(font_path, size, bold_variation), block.lines, size, block.rooms, block.hyphens, 0,
                   block.defects, largest)


def _split_fallback(body: _Body, paras: list[list[str]], text: str, font_path: str | Lettering | None, size: int,
                    line_spacing: float, bold_variation: bool, script: str) -> _Shaped | None:
    """The last resort at the smallest size: the lines filled one after the other, a word too wide for every line split
    (`_split_word`), each line as wide as the body's row through its centre column is (`_layout_at`; not kept to one
    axis: in a bubble this cramped every pixel counts), the ink `MARGIN_PX` off the outline."""
    font = styled_font(font_path, size, bold_variation)
    ok = body.depth > MARGIN_PX
    h, w = ok.shape
    c = min(w - 1, max(0, int(body.cx)))
    cols = np.arange(w)
    left = np.where(~ok[:, : c + 1], cols[: c + 1], -1).max(axis=1) + 1
    right = np.where(~ok[:, c:], cols[c:], w).min(axis=1)
    left[~ok[:, c]], right[~ok[:, c]] = w, 0
    widest = np.zeros((2, h), int)  # per row its longest run, wherever it lies: what is left when the centre fails
    widest[0] = w
    for y in np.flatnonzero(ok.any(axis=1)):
        edges = np.flatnonzero(np.diff(np.concatenate(([0], ok[y].astype(np.int8), [0]))))
        k = int(np.argmax(edges[1::2] - edges[::2]))
        widest[:, y] = edges[2 * k], edges[2 * k + 1]
    lh = size * line_spacing
    widths: dict[str, int] = {}
    ink_top, ink_bottom = _ink_rows(font, text, script)
    for lo, hi in ((left, right), (widest[0], widest[1])):
        rows = np.flatnonzero(hi > lo)
        if rows.size == 0:
            continue
        for top in range(int(rows[0]) - ink_top, int(rows[-1]) + 1):
            tried: dict[str, int] = {}
            lines = _layout_at(paras, font, script, size, line_spacing, top, lo, hi, True, widths, 0, tried,
                               (ink_top, ink_bottom))
            if lines is not None:
                return _Shaped(font, lines, size, (), 0, tried.get("breaks", 0), 0.0, size)
    return None


def _shape_fit(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int, max_size: int,
               line_spacing: float, bold_variation: bool, script: str, centre: tuple[float, float] | None,
               valign: str = "middle", keep_blank: bool = False, break_at_min: bool = True, hyphenate: int = 0,
               bodies: list[_Body] | None = None, language: str = "", cut: dict[Any, _Pieces] | None = None
               ) -> _Shaped | None:
    """The largest size from *max_size* down to *min_size* at which *text* fits along the body of *mask* (`_bodies`; a
    smaller size in another of them wins where it has fewer defects, traded as in `_fit_body`), with its best block
    (`_fit_body`). At *min_size* (with *break_at_min*) a word too wide for every line is split as a last resort
    (`_split_fallback`). None when nothing fits."""
    bodies = bodies if bodies is not None else _bodies(mask, centre)
    paras = _words(text, script, keep_blank)
    if not bodies or not any(paras):
        return None
    sizes = _sizes(min_size, max(min_size, max_size))
    cut = {} if cut is None else cut
    found = [(shaped, body.straddle) for body in bodies
             if (shaped := _fit_body(body, paras, text, font_path, sizes, line_spacing, bold_variation, script, valign,
                                     hyphenate, language, cut)) is not None]
    if found:  # the largest size, or a smaller one in another room with fewer defects, traded as in `_fit_body`
        top = max(shaped.fits for shaped, _straddle in found)

        def score(item: tuple[_Shaped, float]) -> tuple[float, int]:
            shaped, straddle = item
            return shaped.defects + straddle + (1.0 - shaped.size / top) / TRADE_PER_DEFECT, -shaped.size

        best = min((item for item in found if item[0].size >= top * (1.0 - SIZE_TRADE)), key=score)[0]
        return replace(best, fits=top)
    if not break_at_min:
        return None
    for body in bodies:  # the last resort (a hyphen at a syllable instead is the rescue's, `_rescue`)
        shaped = _split_fallback(body, paras, text, font_path, min_size, line_spacing, bold_variation, script)
        if shaped is not None:
            return shaped
    return None


def shape_layout(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int = 9, max_size: int = 64,
                 line_spacing: float = 1.12, bold_variation: bool = False, script: str | None = None,
                 centre: tuple[float, float] | None = None, valign: str = "middle", keep_blank: bool = False,
                 break_at_min: bool = True, hyphenate: int = 0, stats: dict[str, int] | None = None,
                 room: list[_Body] | None = None, language: str = ""
                 ) -> tuple[FontT, list[tuple[str, float, int]], int] | None:
    """Largest font size at which *text* fits inside *mask* with every line as wide as the bubble is at its rows.

    A rectangle inside a round or oval bubble wastes the room at its widest part. Here the lines follow the body of the
    bubble (`_bodies`: its tail cut off; two bubbles joined at a neck each tried too), each as wide as the body is round
    one centre axis over the rows its ink covers, the ink `MARGIN_EM` of the size off the outline; the block sits on the
    body's centroid (for text on the page, on *centre*, its lettering's, each line as wide as the mask's run through
    it and centred in that run), with *valign* "top" / "bottom" as high / as
    low as it fits. The words are shared out over the lines by `_plan_lines` (an oval block in a round bubble, no lone
    short word, no line ending on a word that leans on the next one in *language*), and the size may give up a little
    for a better block (`_fit_body`). Words stay whole above *min_size* (and at it too without *break_at_min*); with
    *hyphenate* (1: a word too wide for every line, 2: any long Latin word) a long word may take a hyphen. Each line
    break ends a line; with *keep_blank* an empty line keeps its height. Returns the font, the lines as (text, x centre,
    y top, on whole pixels) in mask coordinates, and the size; None when the text does not fit even at *min_size*.
    *stats* gets the hyphens and the words split as a last resort. *room* is `_bodies` of the mask and *centre*, when
    the caller has it already.
    """
    script = script or script_of(text)
    shaped = _shape_fit(mask, text, font_path, min_size, max_size, line_spacing, bold_variation, script, centre,
                        valign, keep_blank, break_at_min, hyphenate, room, language)
    if shaped is None:
        return None
    if stats is not None:
        if shaped.hyphens:
            stats["hyphens"] = shaped.hyphens
        if shaped.breaks:
            stats["breaks"] = shaped.breaks
    return shaped.font, [(t, x, int(round(y))) for t, x, y in shaped.lines], shaped.size


@dataclass(frozen=True, eq=False)
class Fit:
    """Where and how large a text is set inside a mask (`layout_text`, `layout_formatted`): the font, the lines as
    (text, x, y top) in mask coordinates, where x is each line's left end, centre or right end as *anchor* says, the
    size, a line's height, how the layout was found (*method*: "shape" along the mask's shape, "rect" in a rectangle
    inside it, "box" in the mask's bounding box for a text that does not fit at its size), whether the text
    overflows its room (*overflow*: the caller cuts it at the mask), how many words took a hyphen and how much the
    text was condensed at the limit (`_rescue`), and whether it fits as it is (*clean*: not with a word split as a
    last resort, nor running out of its room at the smallest size); *measure* and *ink* tell `_balanced` how wide a
    line may be, and along the shape *rooms* says it for each line (its lines were shared out by `_plan_lines`
    already) and *defects* what is wrong with the block (`_defects`). It unpacks as (font, lines, size), the three
    things the layout functions gave before."""

    font: Any
    lines: list[tuple[str, float, float]]
    size: int
    line_height: float
    method: str = "shape"
    anchor: str = "center"
    overflow: bool = False
    hyphens: int = 0
    condense: float = 1.0
    clean: bool = True
    measure: int = 0  # a rectangle's layout: the width it wrapped to
    ink: bool = False  # along the shape: each line was kept inside the mask over all the rows of its glyphs
    rooms: tuple[int, ...] = ()  # along the body: how wide each line may be (`_plan`)
    defects: float = 0.0  # along the body: what is wrong with the block (`_defects`) ...
    fits: int = 0  # ... and the largest size the text fits at there (before a trade for a better block)
    body: tuple[float, float, int, int] | None = None  # a bubble's body (`_bodies`): its centroid, width and height

    @property
    def won(self) -> str:
        """Which layout won: "shape", "rect" or "box", with "+hyphens" when words took a hyphen and "+condensed"
        when the text was set narrower."""
        return self.method + ("+hyphens" if self.hyphens else "") + ("+condensed" if self.condense < 1.0 else "")

    def _parts(self) -> tuple[Any, list[tuple[str, float, float]], int]:
        return self.font, self.lines, self.size

    def __iter__(self):
        return iter(self._parts())

    def __getitem__(self, index: int) -> Any:
        return self._parts()[index]

    def __len__(self) -> int:
        return 3


def _text_centre(on_page: bool, anchor: Box | None) -> tuple[float, float] | None:
    """Where text set on the page is centred: on its original lettering (*anchor*); None for a bubble's text."""
    if on_page and anchor is not None:
        return ((anchor[0] + anchor[2]) / 2.0, (anchor[1] + anchor[3]) / 2.0)
    return None


def _candidate_rects(mask: np.ndarray, centre: tuple[float, float] | None, on_page: bool, anchor: Box | None) -> list[Box]:
    """The rectangles a text may be set in: the largest centred one, and for text on the page (whose drawing around
    it is not erased) the ones grown past it from the original lettering."""
    rects = [inner_rect(mask, center=centre)]
    if on_page and anchor is not None:  # the drawing around the text is not erased: also try growing past it
        grown = [r for r in (grown_rect(mask, anchor, bias=b) for b in (1.0, 2.0, 0.5)) if r is not None]
        if grown:
            x0, y0, x1, y1 = rects[0]
            inside = mask[max(0, y0) : max(0, y1), max(0, x0) : max(0, x1)]
            if inside.size == 0 or inside.min() == 0:
                rects = []  # no centred rectangle fits (inner_rect's fallback): it would lie on the drawing
            rects.extend(grown)
    return rects


LAYOUTS_KEPT = 1024  # layouts remembered (`layout_text`): a page's regions, measured and drawn, over many pages
_LAYOUTS: OrderedDict[tuple[Any, ...], "Fit"] = OrderedDict()
_LAYOUTS_LOCK = threading.Lock()


def _tunables() -> tuple[Any, ...]:
    """What a layout hangs on besides its arguments: this module's settings and layout functions as they are now
    (a test may change one)."""
    g = globals()
    return (tuple((k, v) for k, v in g.items() if k.isupper() and isinstance(v, (int, float, bool, tuple))),
            id(g["fit_text"]), id(g["shape_layout"]), id(g["_rescue"]), id(g["_balanced"]), id(g["_candidate_rects"]))


def layout_text(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int = 9, max_size: int = 64,
                line_spacing: float = 1.12, bold_variation: bool = False, script: str | None = None,
                on_page: bool = False, anchor: Box | None = None, hyphenate: bool = True,
                condense: bool = True, language: str = "") -> Fit:
    """`_layout_text`, remembered (in memory, the last `LAYOUTS_KEPT`): a layout is a function of its arguments - the
    mask's pixels among them - so a region measured for its page's sizes (`Pipeline.cap_sizes`) and then drawn, an early
    look and the finished page, or a page lettered again, is laid out once. The `Fit` handed out is shared: it is
    read, never changed."""
    m = np.ascontiguousarray(mask)
    try:
        key: tuple[Any, ...] | None = (m.shape, str(m.dtype), hashlib.blake2b(m.data, digest_size=16).digest(), text,
                                       font_path, min_size, max_size, line_spacing, bold_variation, script, on_page,
                                       tuple(anchor) if anchor is not None else None, hyphenate, condense,
                                       _language(language), _tunables())
        hash(key)
    except TypeError:  # a font argument that cannot be a key: laid out every time
        key = None
    if key is not None:
        with _LAYOUTS_LOCK:
            fit = _LAYOUTS.get(key)
            if fit is not None:
                _LAYOUTS.move_to_end(key)
                return fit
    fit = _layout_text(mask, text, font_path, min_size, max_size, line_spacing, bold_variation, script, on_page,
                       anchor, hyphenate, condense, language)
    if key is not None:
        with _LAYOUTS_LOCK:
            _LAYOUTS[key] = fit
            while len(_LAYOUTS) > LAYOUTS_KEPT:
                _LAYOUTS.popitem(last=False)
    return fit


def _layout_text(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int = 9, max_size: int = 64,
                 line_spacing: float = 1.12, bold_variation: bool = False, script: str | None = None,
                 on_page: bool = False, anchor: Box | None = None, hyphenate: bool = True,
                 condense: bool = True, language: str = "") -> Fit:
    """Where and how large *text* is set inside *mask*: the font, the lines as (text, x centre, y top) in mask
    coordinates, and the font size (a `Fit`, which unpacks as those three, and says which layout won).

    The lines are laid out along the bubble's body (shape_layout) or into the largest rectangle that fits, whichever
    allows the larger font. *anchor* is the box of the original lettering (mask coordinates); text on the page
    (*on_page*) stays where that lettering was and may also grow past the drawing around it, a bubble's text is
    centred in the bubble. At *min_size* the text is set even where it does not fit. At the limit (`_rescue`), when
    the size found is under `RESCUE_BELOW`, a larger size (or one that fits at *min_size*) may come from condensing the
    text (*condense*) or hyphenating a long word (*hyphenate*); elsewhere, and where neither helps, the layout is the
    one found without them. *language* (the target language's name) chooses the words a line should not end on
    (`WEAK_WORDS`) and whether a capital inside a sentence is a name (`NAME_LANGUAGES_NOT`).
    """
    script = script or script_of(text)
    centre = _text_centre(on_page, anchor)
    rects = _candidate_rects(mask, centre, on_page, anchor)
    best = None
    for rect in rects:
        fitted = fit_text(text, font_path, rect[2] - rect[0], rect[3] - rect[1], min_size, max_size, line_spacing,
                          bold_variation, script)
        if best is None or fitted[2] > best[0][2]:
            best = (fitted, rect)
    assert best is not None
    (font, lines, size), (rx0, ry0, rx1, ry1) = best
    room = _bodies(mask, centre)
    shaped = _shape_fit(mask, text, font_path, min_size, max_size, line_spacing, bold_variation, script, centre,
                        bodies=room, language=language)
    if shaped is not None and shaped.fits >= size:  # as large as the rectangle's, or traded for a better block
        fit = Fit(shaped.font, shaped.lines, shaped.size, shaped.size * line_spacing, "shape", clean=not shaped.breaks,
                  hyphens=shaped.hyphens, rooms=shaped.rooms, defects=shaped.defects, fits=shaped.fits)
    else:
        line_h = size * line_spacing
        top = (ry0 + ry1) / 2.0 - line_h * len(lines) / 2.0
        fit = Fit(font, [(ln, (rx0 + rx1) / 2.0, top + i * line_h) for i, ln in enumerate(lines)], size, line_h, "rect",
                  clean=size > min_size or _rect_holds(text, font, lines, line_h, rx1 - rx0, ry1 - ry0, script),
                  measure=rx1 - rx0)
    if hyphenate or condense:
        fit = _rescue(mask, text, font_path, fit, max_size, line_spacing, bold_variation, script, centre, rects,
                      TextFormat(), False, hyphenate, condense, room, language) or fit
    fit = _balanced(fit, text, script)
    if centre is None and room:  # a bubble: its body's centroid and size, for the checks (`lettering_flags`)
        cols = np.flatnonzero((room[0].depth > 0).any(axis=0))
        fit = replace(fit, body=(room[0].cx, room[0].cy, int(cols[-1] - cols[0] + 1) if cols.size else 1,
                                 room[0].rows[1] - room[0].rows[0]))
    return fit


def _rect_holds(text: str, font: FontT, lines: list[str], line_h: float, box_w: int, box_h: int, script: str) -> bool:
    """Whether fit_text's *lines* fit its box (box_w x box_h) with every word whole: what its smallest size need not."""
    box_w, box_h = max(4, box_w), max(4, box_h)
    words = text.split() if script not in NO_SPACE_SCRIPTS else []
    return (bool(lines) and len(lines) * line_h <= box_h and all(_display_width(font, w, script) <= box_w for w in words)
            and all(_display_width(font, ln, script) <= box_w for ln in lines))


def _rescue(mask: np.ndarray, text: str, font_path: str | Lettering | None, base: Fit, hi: int, line_spacing: float,
            bold_variation: bool, script: str, centre: tuple[float, float] | None, rects: list[Box], fmt: TextFormat,
            keep_blank: bool, hyphenate: bool, condense: bool, bodies: list[_Body] | None = None,
            language: str = "") -> Fit | None:
    """At the limit, for small lettering: the text where *base* (the layout found without these) would have dropped
    to its size, or does not fit cleanly at it - set at the sizes above *base*'s (from its own, when it is not clean),
    one at a time and up to *hi*, condensed by up to 8 % (*condense*: the mildest step of CONDENSE_STEPS that fits) or
    with long Latin words hyphenated (*hyphenate*: first only a word too wide for its line, then words that fill a
    line), or both; at each size the first of those that fits, fewest hyphens and mildest condensing first, and where
    the text fits whole at a smaller size, never with more than `HYPHENS_AVOIDABLE` hyphens (where it does not, never
    with more than the first size that fits needs, or than that). Returns the layout at the
    largest size reached (one that beats *base* by a point or more, or fits where it does not), None when none does.
    Only for a *base* under `RESCUE_BELOW` points: larger lettering reads well as it is and keeps its natural letter
    shapes (a region formatted to be condensed, *fmt.condense*, is as the reader asked at any size). *bodies* is
    `_bodies` of the mask, when the caller has it."""
    hyphenate = hyphenate and script == "lgc"
    if not (hyphenate or condense):
        return None
    reached = max(base.size, base.fits)  # a size traded for a better block is no size to rescue
    if RESCUE_BELOW is not None and reached >= RESCUE_BELOW and fmt.condense is not True:
        return None
    strongest = CONDENSE_STEPS[-1]
    room: Any = (bodies if bodies is not None else _bodies(mask, centre)) if fmt.align == "center" else False
    tried: dict[tuple[int, float, int], Fit | None] = {}
    cut: dict[Any, _Pieces] = {}
    # the most hyphens a layout may take: where the text fits whole, if smaller, `HYPHENS_AVOIDABLE`; where it does
    # not, as many as the first size that fits needs, or that many if more (none set until that size is found)
    limit: list[int | None] = [HYPHENS_AVOIDABLE if base.clean else None]

    def at(size: int, factor: float, mode: int) -> Fit | None:
        if (size, factor, mode) in tried:
            return tried[size, factor, mode]
        fit = _fit_at(mask, text, font_path, size, factor, mode, line_spacing, bold_variation, script, centre, rects,
                      fmt, keep_blank, room, language, cut)
        if fit is not None and limit[0] is not None and fit.hyphens > limit[0]:
            fit = None  # more hyphens than the text needs, for a larger size
        tried[size, factor, mode] = fit
        return fit

    def first(size: int) -> Fit | None:
        """The preferred layout at *size*: condensed as little as fits; else hyphenated (a word too wide for its
        line, then line-filling ones); else both. The most permissive try of each kind decides whether to look
        further, so a size where nothing fits costs a try or two."""
        if condense and at(size, strongest, 0) is not None:
            return next(f for f in (at(size, factor, 0) for factor in CONDENSE_STEPS) if f is not None)
        if hyphenate:
            fit = at(size, 1.0, 1) or at(size, 1.0, 2)
            if fit is not None:
                return fit
            if condense and at(size, strongest, 2) is not None:
                return next(f for f in (at(size, factor, mode) for mode in (1, 2) for factor in CONDENSE_STEPS)
                            if f is not None)
        return None

    found: Fit | None = None
    size = reached + 1 if base.clean else base.size
    while size <= hi and (RESCUE_STEPS is None or size - base.size <= RESCUE_STEPS):
        fit = first(size)
        if fit is None:
            break
        if limit[0] is None:
            limit[0] = max(HYPHENS_AVOIDABLE, fit.hyphens)
        found = fit
        size += 1
    return found


def _fit_at(mask: np.ndarray, text: str, font_path: str | Lettering | None, size: int, factor: float, hyphenate: int,
            line_spacing: float, bold_variation: bool, script: str, centre: tuple[float, float] | None,
            rects: list[Box], fmt: TextFormat, keep_blank: bool, room: Any = None, language: str = "",
            cut: dict[Any, _Pieces] | None = None) -> Fit | None:
    """One try of `_rescue`: the text at *size* condensed to *factor* and hyphenated as *hyphenate* says, along the
    bubble's body (centred text; *room*: its `_bodies`) or in one of *rects*; None when it does not fit with every
    word whole or hyphenated. *cut* keeps the text's `_cut` from one try to the next."""
    face = (font_path.formatted(condense=factor) if isinstance(font_path, Lettering)
            else Lettering(font_path, bold_variation, condense=factor))
    line_h = size * line_spacing
    if fmt.align == "center":
        shaped = _shape_fit(mask, text, face, size, size, line_spacing, bold_variation, script, centre, fmt.valign,
                            keep_blank, False, hyphenate, room if isinstance(room, list) else None, language, cut)
        if shaped is not None:
            return Fit(shaped.font, shaped.lines, size, line_h, "shape", hyphens=shaped.hyphens, condense=factor,
                       ink=True, rooms=shaped.rooms, defects=shaped.defects)
    for rect in rects:
        stats = {}
        fitted = _rect_fit(text, face, rect[2] - rect[0], rect[3] - rect[1], size, size, line_spacing, bold_variation,
                           script, keep_blank, hyphenate, stats, True)
        if fitted is not None:
            return Fit(fitted[0], _placed(fitted[1], line_h, rect, fmt), size, line_h, "rect", fmt.align,
                       hyphens=stats.get("hyphens", 0), condense=factor, measure=rect[2] - rect[0])
    return None


# --- the reader's formatting -------------------------------------------------------------------

NO_FIT = "no-fit"  # the text does not fit at its size: set past the inner rectangle, cut at the mask's edge
QUARTER_TURNS = {"down": -90.0, "up": 90.0}  # a text direction's turn, degrees counter-clockwise (as a slant)


@dataclass(frozen=True)
class TextFormat:
    """How the reader formatted a region's text in the region editor (`annotations.RegionStyle` but for the font
    and its faces, which make the lettering): the lines aligned "left", "center" or "right" and the block at the
    "top", "middle" or "bottom", a fixed *size* that is never shrunk (0: the largest that fits), the line spacing as
    a multiple of the size (0: the setting), and whether the text may be condensed at the limit (*condense*; None:
    when the size is the largest that fits, never at a fixed size)."""

    align: str = "center"
    valign: str = "middle"
    size: int = 0
    line_spacing: float = 0.0
    condense: bool | None = None


@dataclass(frozen=True)
class Lettered:
    """What lettering a region did: the font size used, what it could not do as formatted (`NO_FIT`) or what the
    checks of an automatic lettering found (`LETTER_CHECKS`), and which layout won (`Fit.won`)."""

    size: int
    flags: tuple[str, ...] = ()
    won: str = ""


def _rect_fit(text: str, font_path: str | Lettering | None, box_w: int, box_h: int, lo: int, hi: int,
              line_spacing: float, bold_variation: bool, script: str, keep_blank: bool = True, hyphenate: int = 0,
              stats: dict[str, int] | None = None, ink: bool = False) -> tuple[FontT, list[str], int] | None:
    """As fit_text (an empty line kept with *keep_blank*): the largest size from *hi* down to *lo* whose wrapped text
    fits (box_w x box_h) with every word whole, or hyphenated as *hyphenate* says (`wrap_lines`); None when none
    does. *stats* gets the hyphens of the lines returned. With *ink*, the last line's glyphs (ascent and descent)
    must fit too, not only its share of the block."""
    box_w, box_h = max(4, box_w), max(4, box_h)
    words = text.split() if script not in NO_SPACE_SCRIPTS else []
    size = max(lo, min(hi, int(box_h / line_spacing)))
    while size >= lo:
        font = styled_font(font_path, size, bold_variation)
        if hyphenate or all(_display_width(font, w, script) <= box_w for w in words):
            tried: dict[str, int] = {}
            lines = wrap_lines(text, font, box_w, script, keep_blank, hyphenate, tried)
            line_h = size * line_spacing
            tall = (len(lines) - 1) * line_h + max(line_h, sum(font.getmetrics())) if ink else len(lines) * line_h
            if (lines and not tried.get("breaks") and tall <= box_h
                    and all(_display_width(font, ln, script) <= box_w for ln in lines)):
                if stats is not None:
                    stats.update(tried)
                return font, lines, size
        size -= 1 if size <= 24 else 2
    return None


def _placed(lines: list[str], line_h: float, rect: Box, fmt: TextFormat) -> list[tuple[str, float, float]]:
    """*lines* in *rect* as *fmt* places them: each at the rectangle's left end, centre or right end, the block at
    its top, middle or bottom (a block taller than the rectangle runs past it at the other end)."""
    rx0, ry0, rx1, ry1 = rect
    block = line_h * len(lines)
    if fmt.valign == "top":
        top = float(ry0)
    elif fmt.valign == "bottom":
        top = ry1 - block
    else:
        top = (ry0 + ry1) / 2.0 - block / 2.0
    x = float(rx0) if fmt.align == "left" else float(rx1) if fmt.align == "right" else (rx0 + rx1) / 2.0
    return [(ln, x, top + i * line_h) for i, ln in enumerate(lines)]


def layout_formatted(mask: np.ndarray, text: str, font_path: str | Lettering | None, fmt: TextFormat,
                     min_size: int = 9, max_size: int = 64, line_spacing: float = 1.12, bold_variation: bool = False,
                     script: str | None = None, on_page: bool = False, anchor: Box | None = None,
                     language: str = "") -> Fit:
    """Where and how large *text* is set inside *mask* as the reader formatted it (*fmt*), as a `Fit`.

    Each line break ends a line and an empty line keeps its height; within a line the text wraps as usual. Centred
    text is laid out as layout_text lays it, along the bubble's body or in the inner rectangle, whichever allows the
    larger font (the block at the top, middle or bottom of the room it has); text aligned left or right is set in the
    inner rectangle. The size is the largest that fits between *min_size* and *max_size*, or *fmt.size*, which is
    never shrunk; at the limit (`_rescue`) a long word may take a hyphen, and the text may be condensed as
    *fmt.condense* says. Centred lines are shared out as layout_text's (`_plan_lines`, `_balanced`, between the line
    breaks), text aligned left or right wraps as in a word processor. A text that does not fit at its size even so (at
    *min_size*, or at the fixed size) is set at it in the mask's bounding box instead, aligned the same way, and marked
    as overflowing: the caller cuts it at the mask.
    """
    script = script or script_of(text)
    ls = fmt.line_spacing or line_spacing
    lo, hi = (fmt.size, fmt.size) if fmt.size else (min_size, max_size)
    centre = _text_centre(on_page, anchor)
    rects = _candidate_rects(mask, centre, on_page, anchor)
    best: tuple[tuple[FontT, list[str], int], Box] | None = None
    for rect in rects:
        fitted = _rect_fit(text, font_path, rect[2] - rect[0], rect[3] - rect[1], lo, hi, ls, bold_variation, script)
        if fitted is not None and (best is None or fitted[2] > best[0][2]):
            best = (fitted, rect)
    fit: Fit | None = None
    room: Any = None
    if fmt.align == "center":
        room = _bodies(mask, centre)
        shaped = _shape_fit(mask, text, font_path, lo, hi, ls, bold_variation, script, centre, fmt.valign, True,
                            not fmt.size, bodies=room, language=language)
        if shaped is not None and (best is None or shaped.fits > best[0][2]
                                   or shaped.fits == best[0][2] and fmt.valign == "middle"):
            fit = Fit(shaped.font, shaped.lines, shaped.size, shaped.size * ls, "shape", clean=not shaped.breaks,
                      hyphens=shaped.hyphens, rooms=shaped.rooms, defects=shaped.defects, fits=shaped.fits)
    if fit is None and best is not None:
        (font, lines, size), rect = best
        fit = Fit(font, _placed(lines, size * ls, rect, fmt), size, size * ls, "rect", fmt.align,
                  measure=rect[2] - rect[0])
    condense = fmt.condense if fmt.condense is not None else not fmt.size
    base = fit if fit is not None else Fit(None, [], lo, lo * ls, "box", fmt.align, overflow=True, clean=False)
    better = _rescue(mask, text, font_path, base, hi, ls, bold_variation, script, centre, rects, fmt, True, True,
                     condense, room if isinstance(room, list) else None, language)
    if better is not None or fit is not None:
        fit = better or fit
        return _balanced(fit, text, script) if fmt.align == "center" else fit
    ys, xs = np.nonzero(mask)
    box = ((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if xs.size
           else (0, 0, mask.shape[1], mask.shape[0]))
    font = styled_font(font_path, lo, bold_variation)
    lines = wrap_lines(text, font, box[2] - box[0], script, keep_blank=True)
    return Fit(font, _placed(lines, lo * ls, box, fmt), lo, lo * ls, "box", fmt.align, overflow=True)


def text_room(mask: np.ndarray, font_path: str | Lettering | None, size: int, line_spacing: float = 1.12,
              bold_variation: bool = False, centre: tuple[float, float] | None = None, probe: str = "words") -> int:
    """How many characters of ordinary text (five-letter words and spaces) fit inside *mask* at font *size*,
    laid out along its shape as `shape_layout` lays them, every word whole: whether they fit at all (`_plan` without
    *full*, in any of the mask's bodies), the block not planned and no last resort. What a translator is told a bubble
    has room for."""
    bodies = _bodies(mask, centre)

    def fits(n: int) -> bool:
        text = " ".join([probe] * n)
        paras = _words(text, "lgc", False)
        return any(_plan(body, paras, text, font_path, size, line_spacing, bold_variation, "lgc", "middle", 0, "",
                         False) for body in bodies)

    lo, hi = 0, 1
    while hi <= 512 and fits(hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid
    return lo * (len(probe) + 1)


BUSY_STD = 35.0  # grey-level spread under the lines beyond which the text sits on a drawing and gets an outline
INK_NAMED = {"black": (0, 0, 0), "white": (255, 255, 255)}  # the colours a style names (`annotations.INK_NAMES`)
Colour = tuple[int, int, int]


def ink_rgb(code: str) -> Colour | None:
    """The colour a style's code names ("black", "white" or "#rrggbb", `annotations.ink_code`); None for an automatic
    one ("") or a code that is none of these."""
    code = (code or "").strip().lower()
    if code in INK_NAMED:
        return INK_NAMED[code]
    if len(code) == 7 and code[0] == "#":
        try:
            return int(code[1:3], 16), int(code[3:5], 16), int(code[5:7], 16)
        except ValueError:
            return None
    return None


def _luminance(colour: Colour) -> float:
    return 0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2]


def ground_ink(background: Colour) -> Colour:
    """The automatic text colour on a ground of *background*: black on a light one, white on a dark one."""
    return (0, 0, 0) if _luminance(background) >= 128 else (255, 255, 255)


def opposite_ink(colour: Colour) -> Colour:
    """The automatic outline round letters of *colour*: white round dark letters, black round light ones (round
    black, white; round white, black)."""
    return (255, 255, 255) if _luminance(colour) < 128 else (0, 0, 0)


def _contour(color: Colour, outline_color: Colour | None, size: int, outline: bool | None) -> tuple[Colour, int] | None:
    """The outline the lines are drawn with: none unless *outline*, else in *outline_color* (None: `opposite_ink`),
    a twelfth of the size wide."""
    if not outline:
        return None
    return (outline_color if outline_color is not None else opposite_ink(color)), max(1, round(size / 12))


def busy_under(image: Image.Image, box: Box) -> bool:
    """True when the pixels of *image* inside *box* are a drawing or a tone rather than a flat ground."""
    x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(image.width, box[2]), min(image.height, box[3])
    if x1 - x0 < 2 or y1 - y0 < 2:
        return False
    gray = np.asarray(image.crop((x0, y0, x1, y1)).convert("L"), dtype=np.float32)
    return float(gray.std()) > BUSY_STD


# What the checks of an automatic lettering say is still wrong with it (`lettering_flags`; `Lettered.flags`, the
# review list's reasons for them in `ui.dialogs.review.FIT_REASONS`): nothing the layout could do better at its size
TIGHT = "tight"  # a glyph within TIGHT_PX of the bubble's edge, or past it
OFF_CENTRE = "off-centre"  # the block's middle off the bubble body's centroid by over OFF_SHARE of its width or height
HYPHENATED = "hyphenated"  # a word split with a hyphen (at a hyphenation point, or as a last resort)
LONE_WORD = "lone-word"  # a word of LONE_FLAG_LETTERS or fewer on a line of its own (`LONE_WORDS`; not in a column)
HOURGLASS_LINE = "hourglass"  # an inner line under `HOURGLASS` of the narrower of its neighbours (not in a column)
LOW_CONTRAST = "low-contrast"  # the letters' grey within CONTRAST_MIN of the ground's under them, and no outline
LETTER_CHECKS = (TIGHT, OFF_CENTRE, HYPHENATED, LONE_WORD, HOURGLASS_LINE, LOW_CONTRAST)
TIGHT_PX = 1.0
OFF_SHARE = 0.15  # (a translation set in one of two bubbles joined at a neck: the other may want part of it)
LONE_FLAG_LETTERS = 3  # ("I", "so", "you."; the layout avoids longer ones too, `LONE_LETTERS`, but "Where" may stand)
CONTRAST_MIN = 70.0


def lettering_flags(ground: np.ndarray, mask: np.ndarray, fit: Fit, lines: list[tuple[str, float, float]], script: str,
                    color: Colour, outline: bool, on_page: bool) -> tuple[str, ...]:
    """The checks of an automatic lettering (codes of `LETTER_CHECKS`): *fit* as `layout_text` made it, *lines* as
    drawn (the display form, x centre, y top in the region), *ground* the region's pixels before they were drawn
    (RGB), *mask* the region's; the letters in *color*, with an *outline* or not. Measured on each line's box (its
    width by the rows of the text's ink); a line whose box comes near the edge is drawn once more on a blank to tell
    whether its glyphs do. Off the centre is checked in a bubble only (text on the page sits where its lettering was);
    a lone word and an hourglass in a Latin-like script, but in a column (fewer than `COLUMN_WORDS` words a line: a
    narrow bubble is set so)."""
    h, w = ground.shape[:2]
    if mask.shape != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    font = fit.font
    ink_top, ink_bottom = _ink_rows(font, "".join(shown for shown, _x, _t in lines), script)
    boxes = []  # per line: x0, y0, x1, y1 of its ink, clipped to the region
    for shown, xc, top in lines:
        half = font.width(shown) / 2.0
        box = (max(0, int(xc - half)), max(0, int(top + ink_top)), min(w, int(np.ceil(xc + half))),
               min(h, int(np.ceil(top + ink_bottom))))
        boxes.append(box if box[2] > box[0] and box[3] > box[1] else None)
    if not any(boxes):
        return ()
    flags: list[str] = []
    depth = _depth(mask > 0)
    near = [k for k, b in enumerate(boxes)  # the lines whose box comes near the edge: their glyphs drawn to tell
            if b is not None and float(depth[b[1]:b[3], b[0]:b[2]].min()) <= TIGHT_PX + 1]
    if None in boxes:  # a line wholly off the region
        flags.append(TIGHT)
    elif near:
        blank = Image.new("RGB", (w, h), (0, 0, 0))
        for k in near:
            shown, xc, top = lines[k]
            font.draw(blank, xc - font.width(shown) / 2.0, top, shown, (255, 255, 255))
        if (np.asarray(blank)[:, :, 0] > 127)[depth <= TIGHT_PX].any():
            flags.append(TIGHT)
    found = [b for b in boxes if b is not None]
    if not on_page and fit.body is not None:
        cx, cy, bw, bh = fit.body
        mid_x = (min(b[0] for b in found) + max(b[2] for b in found)) / 2.0
        mid_y = (min(b[1] for b in found) + max(b[3] for b in found)) / 2.0
        if max(abs(mid_x - cx) / max(1, bw), abs(mid_y - cy) / max(1, bh)) > OFF_SHARE:
            flags.append(OFF_CENTRE)
    if fit.hyphens or not fit.clean:
        flags.append(HYPHENATED)
    texts = [t for t, _x, _y in fit.lines if t]
    words = sum(len(t.split()) for t in texts)
    if script not in NO_SPACE_SCRIPTS and len(texts) > 1 and words >= COLUMN_WORDS * len(texts):
        ended = True  # the line before ended a sentence
        for t in texts:
            mine = strip_marks(t).split()
            sentence = ended and t.rstrip(_TRAILERS)[-1:] in _SENTENCE_END
            if (len(mine) == 1 and words >= LONE_WORDS and not sentence
                    and sum(ch.isalpha() for ch in mine[0]) <= LONE_FLAG_LETTERS):
                flags.append(LONE_WORD)
                break
            ended = t.rstrip(_TRAILERS)[-1:] in _SENTENCE_END
        widths = [_display_width(font, t, script) for t in texts]
        if any(widths[k] < HOURGLASS * min(widths[k - 1], widths[k + 1]) for k in range(1, len(widths) - 1)):
            flags.append(HOURGLASS_LINE)
    if not outline:  # the ground's grey under the lines (a drawing gets an outline: `busy_under`)
        grey = np.concatenate([_luminance_of(ground[b[1]:b[3], b[0]:b[2]]).ravel() for b in found])
        if abs(float(np.median(grey)) - _luminance(color)) < CONTRAST_MIN:
            flags.append(LOW_CONTRAST)
    return tuple(flags)


def _luminance_of(pixels: np.ndarray) -> np.ndarray:
    """`_luminance` of each pixel of an RGB array."""
    return pixels[..., 0] * 0.299 + pixels[..., 1] * 0.587 + pixels[..., 2] * 0.114


def letter_text(image: Image.Image | None, region: TextRegion, text: str, font_path: str | Lettering | None,
                min_size: int = 9, max_size: int = 64, line_spacing: float = 1.12,
                uppercase: bool = False, background: tuple[int, int, int] = (255, 255, 255),
                bold_variation: bool = False, language: str = "", outline: bool | None = None,
                fmt: TextFormat | None = None, *, hyphenate: bool = True, condense: bool = True,
                direction: str = "", color: Colour | None = None, outline_color: Colour | None = None) -> Lettered:
    """Draw *text* inside the bubble (on no *image*: only find out how it would be set): as layout_text sets it (at the limit hyphenated or condensed when *hyphenate*,
    *condense* allow it), or with *fmt* as the reader formatted it (layout_formatted; a text that does not fit at its
    size is cut at the bubble's edge and said, `NO_FIT`). *font_path* may be a Lettering (italic, bold, the cuts for
    stressed words marked *like this*, letter spacing). The text is in *color* (None: black on a light *background*,
    white on a dark one, `ground_ink`). Text that lands on a drawing or a tone is given an outline in *outline_color*
    (None: the opposite of the text colour, `opposite_ink`; *outline* None: decided from the pixels under the lines;
    True or False: as said). The colours never move a line. Returns the font size used, what could not be done (and
    for the automatic lettering drawn, what its checks found still wrong with it, `lettering_flags`) and which layout
    won.

    *direction* is the region's text direction (`annotations.DIRECTIONS`): "" and "horizontal" set the lines across
    as always; "down" and "up" set them across in the region's frame turned a quarter (`QUARTER_TURNS`: its width
    and height swapped) and turn them onto the page, through `render.slant` as a slant is, the slant added; "stacked"
    sets them in columns (`render.vertical`), in the slanted frame when there is a slant."""
    text = text.strip()
    if not text:
        return Lettered(0)
    quarter = QUARTER_TURNS.get(direction, 0.0)
    angle = getattr(region, "angle", 0.0) + quarter
    if angle:  # slanted or turned lettering: set in the region's own frame, turned onto the page
        from .slant import letter_slanted

        turned = region
        if quarter:
            turned = copy.copy(region)
            turned.angle = angle
        inner = "stacked" if direction == "stacked" else ""
        return letter_slanted(image, turned, lambda im, upright: letter_text(
            im, upright, text, font_path, min_size, max_size, line_spacing, uppercase, background, bold_variation,
            language, outline, fmt, hyphenate=hyphenate, condense=condense, direction=inner, color=color,
            outline_color=outline_color))
    script = script_of(text, language)
    if uppercase and script == "lgc":  # a capital the font lacks is drawn as `fonts.drawable` draws it, as a small one was
        text = drawable(font_path.path if isinstance(font_path, Lettering) else font_path, text.upper())
    tx0, ty0, tx1, ty1 = region.letter_box or region.text_box
    anchor = (tx0 - region.x0, ty0 - region.y0, tx1 - region.x0, ty1 - region.y0)
    on_page = region.kind in ("text", "text-dark")
    color = ground_ink(background) if color is None else tuple(color)  # type: ignore[assignment]
    if direction == "stacked":  # vertical writing, column by column
        from . import vertical

        size, overflow = vertical.letter_stacked(
            image, region, text, font_path, min_size, (fmt.size if fmt is not None and fmt.size else max_size),
            (fmt.line_spacing if fmt is not None and fmt.line_spacing else line_spacing), color, bold_variation,
            outline, _text_centre(on_page, anchor), fmt.size if fmt is not None else 0,
            fmt.valign if fmt is not None else "middle", busy_under, outline_color)
        return Lettered(size, (NO_FIT,) if overflow and fmt is not None else (), "stacked")
    if fmt is not None:
        fit = layout_formatted(region.mask, text, font_path, fmt, min_size, max_size, line_spacing, bold_variation,
                               script, on_page, anchor, language)
        if image is None:
            return Lettered(fit.size, (NO_FIT,) if fit.overflow else (), fit.won)
        return _draw_fit(image, region, fit, script, color, outline, outline_color)
    fit = layout_text(region.mask, text, font_path, min_size, max_size, line_spacing, bold_variation, script,
                      on_page, anchor, hyphenate, condense, language)
    if image is None:
        return Lettered(fit.size, (), fit.won)
    font, placed, size = fit
    lines = [(display_form(ln, script), xc, top) for ln, xc, top in placed]
    if outline is None and lines:
        widths = [font.width(shown) for shown, _xc, _top in lines]
        box = (int(region.x0 + min(xc - w / 2.0 for (_s, xc, _t), w in zip(lines, widths))),
               int(region.y0 + min(top for _s, _xc, top in lines)),
               int(region.x0 + max(xc + w / 2.0 for (_s, xc, _t), w in zip(lines, widths))) + 1,
               int(region.y0 + max(top for _s, _xc, top in lines) + size * line_spacing) + 1)
        outline = busy_under(image, box)
    contour = _contour(color, outline_color, size, outline)
    ground = np.asarray(image.crop((region.x0, region.y0, region.x1, region.y1)).convert("RGB"))
    for shown, xc, top in lines:
        font.draw(image, region.x0 + xc - font.width(shown) / 2.0, region.y0 + top, shown, color, contour)
    return Lettered(size, lettering_flags(ground, region.mask, fit, lines, script, color, bool(outline), on_page),
                    fit.won)


def _draw_fit(image: Image.Image, region: TextRegion, fit: Fit, script: str, color: Colour,
              outline: bool | None, outline_color: Colour | None = None) -> Lettered:
    """Draw the lines of a formatted *fit* (each anchored at its left end, centre or right end) in *color*, with an
    outline in *outline_color* (None: the opposite colour) as *outline* says; an overflowing text is drawn on a copy
    of the region and only what lies inside its mask goes on the page."""
    font, size = fit.font, fit.size
    lines = []
    for ln, x, top in fit.lines:
        if not ln:
            continue  # an empty line: room only
        shown = display_form(ln, script)
        w = font.width(shown)
        left = x - w / 2.0 if fit.anchor == "center" else x if fit.anchor == "left" else x - w
        lines.append((shown, left, top, w))
    if outline is None and lines:
        box = (int(region.x0 + min(left for _s, left, _t, _w in lines)),
               int(region.y0 + min(top for _s, _l, top, _w in lines)),
               int(region.x0 + max(left + w for _s, left, _t, w in lines)) + 1,
               int(region.y0 + max(top for _s, _l, top, _w in lines) + fit.line_height) + 1)
        outline = busy_under(image, box)
    contour = _contour(color, outline_color, size, outline)
    if not fit.overflow:
        for shown, left, top, _w in lines:
            font.draw(image, region.x0 + left, region.y0 + top, shown, color, contour)
        return Lettered(size, (), fit.won)
    part = image.crop((region.x0, region.y0, region.x1, region.y1))  # the region alone, cut at its mask below
    for shown, left, top, _w in lines:
        font.draw(part, left, top, shown, color, contour)
    mask = region.mask
    if mask.shape != (part.height, part.width):
        mask = cv2.resize(mask, (part.width, part.height), interpolation=cv2.INTER_NEAREST)
    image.paste(part, (region.x0, region.y0), Image.fromarray(np.where(mask > 0, 255, 0).astype(np.uint8)))
    return Lettered(size, (NO_FIT,), fit.won)
