"""Fit the translated text into a bubble.

Approach (own implementation; the auto-sizing idea is the same one every
typesetting tool uses, including BallonsTranslator, GPL-3.0, studied for
design only): find the largest centered rectangle that fits inside the bubble
interior, then shrink the font until the wrapped text fits that rectangle.
Besides the rectangle, the lines are laid out along the bubble's shape, each
as wide as the bubble is at its rows (shape_layout), and the larger of the
two font sizes wins: a rectangle wastes the widest part of a round bubble.

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

Once the size is chosen the lines are balanced (`_balanced`): the same lines at
the same places, the words shared out over them by a dynamic programme (least
total slack cubed) instead of each line filled to the brim and the last one left
with a word. The size never moves. On a page, `page_caps` keeps a short line in
a big bubble from towering over its neighbours: `SIZE_CAP` times the page's
median size for its kind.

The reader may set a region's text direction (`RegionStyle.direction`), as a word processor's text box: turned a
quarter clockwise to read from the top down or a quarter the other way to read from the bottom up (the lines set as
always in the region's frame turned, its width and height swapped, then turned onto the page by `render.slant`
with the slant added: `QUARTER_TURNS`), or stacked in columns of upright glyphs (`render.vertical`). Auto and
horizontal letter the region as before, byte for byte.
"""

from __future__ import annotations

import copy
import hashlib
import re
import threading
import unicodedata
from bisect import bisect_right
from collections import OrderedDict, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from statistics import median
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..regions import Box, TextRegion
from .fonts import NO_SPACE_SCRIPTS, RTL_SCRIPTS, FontT, drawable, script_of
from .lettering import Lettering, StyledFont, emphasis_marks, styled_font

try:  # MIT; joins Arabic letters into their contextual forms
    import arabic_reshaper  # type: ignore
except Exception:  # pragma: no cover - optional
    arabic_reshaper = None

# Characters that must not start a line in CJK text.
_NO_LINE_START = set("、。，．・：；！？!?)）」』】〉》〕］}｝ー〜～…")
_LTR_RUN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.,:/%+-]*")
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
SHAPE_PAD = 0.05  # how far the shape layout keeps the lines off the mask's edge, of the mask's smaller side
# at the limit: how much narrower a text may be set, in the order tried, and where a long word may take a hyphen
CONDENSE_STEPS = (0.98, 0.96, 0.94, 0.92)
RESCUE_BELOW: int | None = 14  # the rescue steps in only for a plain fit under this size (None: at any size)
RESCUE_STEPS: int | None = None  # how many sizes above the plain layout's the rescue may climb (None: as far as fits)
HYPHEN_MIN_LETTERS = 8  # shorter words are never hyphenated
HYPHEN_EDGE = 3  # letters a hyphen leaves on each side
BREAK_MIN_LETTERS = 6  # a shorter word is never split, even where it fits nowhere: it stays whole
BALANCE_LINES = True  # share the words out over the lines once the size is chosen (False: as the greedy fill left them)
LAST_LINE_FREE = 0.1  # how much of its width a paragraph's last line may leave empty free of penalty
ORPHAN_LETTERS = 6  # a last line of one such word (with its punctuation) counts as an orphan
ORPHAN_SLACK = 1.0  # an orphan costs as much as a line this empty: only a worse way elsewhere keeps it
ORPHAN_FIRST_LETTERS = 3  # a first or inner line of one such word ("I", "Je", "Ich") is avoided the same way
ORPHAN_SHIFT = 0.75  # along the shape: how far (of a line's height) the block may leave its centre to avoid an orphan
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
    qu) and never leaving fewer than three letters on either side. None for a word of fewer than eight letters, for
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
            if HYPHEN_EDGE <= cut <= n - HYPHEN_EDGE:
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


def _row_runs(inside: np.ndarray, cx: int) -> tuple[np.ndarray, np.ndarray]:
    """Per row of *inside*, the run of true pixels through column *cx*: left edge and right edge (exclusive).
    Rows without one get left = width and right = 0, so that any band over them has no width."""
    h, w = inside.shape
    cx = min(max(0, cx), w - 1)
    outside = ~inside
    cols = np.arange(w)
    left = np.where(outside[:, :cx], cols[:cx], -1).max(axis=1) + 1 if cx > 0 else np.zeros(h, int)
    right = np.where(outside[:, cx + 1 :], cols[cx + 1 :], w).min(axis=1) if cx + 1 < w else np.full(h, w)
    gone = outside[:, cx]
    left[gone] = w
    right[gone] = 0
    return left, right


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
               ink: int = 0) -> list[tuple[str, float, int]] | None:
    """The lines of *paras* set from *top* down, each as wide as the mask is at its rows: (text, x centre, y top).
    None when they do not fit (a line's rows leave the mask, or a word is wider than its line). An empty paragraph
    (an empty line kept) takes a line's height and sets nothing. *hyphenate* and *stats* as for `_fill_line`. With
    *ink* (the height of a line's glyphs, ascent and descent, when it is more than a line), each line must fit the
    mask over all of the rows its glyphs reach, not only over its share of the block."""
    h = left.shape[0]
    lh = size * line_spacing
    out: list[tuple[str, float, int]] = []
    line = 0
    for para in paras:
        tokens = list(para)
        if not tokens:
            a, b = int(round(top + line * lh)), int(round(top + (line + 1) * lh))
            if a < 0 or b > h:
                return None
            out.append(("", out[-1][1] if out else left.shape[1] / 2.0, a))
            line += 1
            continue
        i = 0
        while i < len(tokens):
            a, b = int(round(top + line * lh)), int(round(top + (line + 1) * lh))
            b = max(b, a + ink)
            if a < 0 or b > h:
                return None
            lo, hi = int(left[a:b].max()), int(right[a:b].min())
            if hi - lo < size:
                return None  # the band leaves the mask, or is narrower than a glyph
            filled = _fill_line(tokens, i, font, hi - lo, script, allow_break, widths, hyphenate, stats)
            if filled is None:
                return None
            text, i = filled
            out.append((text, (lo + hi) / 2.0, a))
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


def _orphans(lines: list[tuple[str, float, int]], paras: list[list[str]], script: str, font: FontT, top: int,
             lh: float, glyphs: int, left: np.ndarray, right: np.ndarray) -> int:
    """How many lines of the block set from *top* (`_layout_at`'s *lines* of *paras*) are a lone short word (`_lone`)
    as `_balanced` will leave them: the balanced lines over the same rooms when there are any, else these. 0 for a
    single line, or text with a line break of the reader's (their lines are their own)."""
    if len(lines) < 2 or len(paras) != 1 or script in NO_SPACE_SCRIPTS:
        return 0  # (a script wrapped by character has no lone words: `_lone`)
    texts = [t for t, _x, _y in lines]
    if BALANCE_LINES and " ".join(texts) == " ".join(paras[0]):  # no hyphen, no word split
        rooms = []
        for k in range(len(lines)):
            a, b = int(round(top + k * lh)), int(round(top + (k + 1) * lh))
            b = max(b, a + glyphs)
            rooms.append(int(right[a:b].min()) - int(left[a:b].max()))
        texts = _balanced_lines(list(paras[0]), rooms, font, script) or texts
    found = 0
    for k, text in enumerate(texts):
        toks = text.split()
        found += _lone(toks, 0, len(toks), False, k == len(texts) - 1)
    return found


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


def _line_rooms(fit: Fit, room: Any) -> list[int] | None:
    """How wide each line of *fit* may be: the rectangle's width, or for a layout along the mask's shape the mask's run
    over the rows of that line, as `_layout_at` measured it. None when it cannot be told."""
    if fit.method == "rect" and fit.measure:
        return [fit.measure] * len(fit.lines)
    if fit.method != "shape" or room is None or room is False:
        return None
    left, right = room[0], room[1]
    glyphs = sum(fit.font.getmetrics()) if fit.ink else 0
    top, lh = fit.lines[0][2], fit.line_height
    rooms: list[int] = []
    for k in range(len(fit.lines)):
        a, b = int(round(top + k * lh)), int(round(top + (k + 1) * lh))
        b = max(b, a + glyphs)
        rooms.append(int(right[a:b].min()) - int(left[a:b].max()))
    return rooms


def _balanced(fit: Fit, text: str, script: str, room: Any = None) -> Fit:
    """*fit* with its words shared out over the same lines (`_balanced_lines`), paragraph by paragraph: every line stays
    where it is and as wide as it may be, the size and the number of lines do not change. A paragraph with a hyphen or
    a word split (its lines no longer are its tokens) and all after it stay as they are, and so does a paragraph
    without a valid way. *room* is `_shape_room`'s for a layout along the shape."""
    if not BALANCE_LINES or len(fit.lines) < 2 or fit.overflow:
        return fit
    rooms = _line_rooms(fit, room)
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


def _shape_room(mask: np.ndarray, pad_ratio: float, centre: tuple[float, float] | None) -> Any:
    """The room shape_layout lays lines out in: per row the run of the mask (kept *pad_ratio* of its size off its
    edge) through the centre column, the first and last rows with room, and the height the block is centred on, as
    (left, right, y_lo, y_hi, cy); False when there is none."""
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return False
    bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    margin = max(2, int(round(pad_ratio * min(bw, bh))))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin + 1, 2 * margin + 1))
    padded = np.pad((mask > 0).astype(np.uint8), margin)  # so the margin also holds at the mask's own edge
    inside = cv2.erode(padded, kernel)[margin:-margin, margin:-margin] > 0
    if not inside.any():
        return False
    cx, cy = centre if centre is not None else (float(xs.mean()), float(ys.mean()))
    left, right = _row_runs(inside, int(round(cx)))
    rows = np.flatnonzero(right > left)
    if rows.size == 0:
        return False
    return left, right, int(rows[0]), int(rows[-1]) + 1, cy


def shape_layout(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int = 9, max_size: int = 64,
                 line_spacing: float = 1.12, bold_variation: bool = False, script: str | None = None,
                 centre: tuple[float, float] | None = None, pad_ratio: float = 0.05, valign: str = "middle",
                 keep_blank: bool = False, break_at_min: bool = True, hyphenate: int = 0,
                 stats: dict[str, int] | None = None, room: Any = None, ink: bool = False
                 ) -> tuple[FontT, list[tuple[str, float, int]], int] | None:
    """Largest font size at which *text* fits inside *mask* with every line as wide as the mask is at its rows.

    A rectangle inside a round or oval bubble wastes the room at its widest part. Here each line takes the width
    of the mask's run through the centre column at the rows it covers, kept *pad_ratio* of the mask's size off
    the edge, and the block of lines sits as close to *centre* (default: the mask's centroid) as the fit allows
    (*valign* "top" / "bottom": as high / as low as it fits), or up to ORPHAN_SHIFT of a line's height further off
    it where that way fewer of its lines are a lone short word (`_orphans`). Words stay whole above *min_size*, as in
    fit_text (and at it too without *break_at_min*); with *hyphenate* (see `_fill_line`) a long word may take a hyphen.
    Each line break ends a line; with *keep_blank* an empty line keeps its height. Returns the font, the lines as (text,
    x centre, y top) in mask coordinates, and the size; None when the text does not fit even at *min_size*. *stats*
    gets the hyphens and the words split as a last resort of the layout returned. With *ink*, every line fits the mask
    over all the rows its glyphs reach (see `_layout_at`). *room* is `_shape_room` of the mask,
    *pad_ratio* and *centre*, when the caller has it already.
    """
    script = script or script_of(text)
    room = room if room is not None else _shape_room(mask, pad_ratio, centre)
    if room is False:
        return None
    left, right, y_lo, y_hi, cy = room
    paras: list[list[str]] = []
    for para in text.replace("\r", "").split("\n"):
        tokens = list(para.replace(" ", "")) if script in NO_SPACE_SCRIPTS else para.split()
        if tokens or keep_blank:
            paras.append(tokens)
    if not any(paras):
        return None
    size = max(min_size, min(max_size, int((y_hi - y_lo) / line_spacing)))
    while size >= min_size:
        font = styled_font(font_path, size, bold_variation)
        lh = size * line_spacing
        widths: dict[str, int] = {}
        best: tuple[float, list[tuple[str, float, int]]] | None = None
        best_stats: dict[str, int] | None = None
        glyphs = sum(font.getmetrics()) if ink else 0
        step = max(1, int(lh / 3))
        fitting: list[tuple[float, int, list[tuple[str, float, int]], dict[str, int] | None]] = []

        def try_at(top: int) -> tuple[list[tuple[str, float, int]] | None, dict[str, int] | None]:
            tried: dict[str, int] | None = {} if stats is not None else None
            return _layout_at(paras, font, script, size, line_spacing, top, left, right,
                              size == min_size and break_at_min, widths, hyphenate, tried, glyphs), tried

        last_top = max(y_lo, y_hi - int(lh))
        for top in range(y_lo, last_top + 1, step):
            lines, tried = try_at(top)
            if lines is None:
                continue
            if valign == "top":  # the first top that fits: as high as it goes
                best, best_stats = (0.0, lines), tried
                break
            if valign == "bottom":  # the last one: as low as it goes
                best, best_stats = (0.0, lines), tried
                continue
            fitting.append((abs(top + len(lines) * lh / 2.0 - cy), top, lines, tried))
        if fitting:
            # The block nearest the centre, unless a line of it is a lone short word ("I" alone on the narrow top
            # line of an oval) and a block a little off the centre has fewer: the lines move, the size stays. Such a
            # block may fit only between the tops tried (a line fewer, in a narrow window), so those are tried too,
            # the ones where a block of as many lines, one more or one fewer would lie within reach - only when the
            # nearest block has a lone word, so that most texts cost what they did.
            fitting.sort(key=lambda f: f[0])
            offset, top, lines, tried = fitting[0]
            fewest = _orphans(lines, paras, script, font, top, lh, glyphs, left, right)
            best, best_stats = (offset, lines), tried
            if fewest:
                reach, nearest = offset + ORPHAN_SHIFT * lh, top
                seen = {f[1] for f in fitting}
                fine = max(1, step // 3)
                near = {t for n in (len(lines) - 1, len(lines), len(lines) + 1)
                        for t in range(int(cy - n * lh / 2.0 - reach), int(cy - n * lh / 2.0 + reach) + 2, fine)
                        if y_lo <= t <= last_top and t not in seen}
                for t in sorted(near):
                    found, tried = try_at(t)
                    if found is not None:
                        fitting.append((abs(t + len(found) * lh / 2.0 - cy), t, found, tried))
                fitting.sort(key=lambda f: f[0])
                for offset, top, lines, tried in fitting:
                    if offset > reach:
                        break
                    if top == nearest:
                        continue
                    lone = _orphans(lines, paras, script, font, top, lh, glyphs, left, right)
                    if lone < fewest:
                        fewest, best, best_stats = lone, (offset, lines), tried
                    if not lone:
                        break
        if best is not None:
            if stats is not None and best_stats:
                stats.update(best_stats)
            return font, best[1], size
        size -= 1 if size <= 24 else 2
    return None


@dataclass(frozen=True, eq=False)
class Fit:
    """Where and how large a text is set inside a mask (`layout_text`, `layout_formatted`): the font, the lines as
    (text, x, y top) in mask coordinates, where x is each line's left end, centre or right end as *anchor* says, the
    size, a line's height, how the layout was found (*method*: "shape" along the mask's shape, "rect" in a rectangle
    inside it, "box" in the mask's bounding box for a text that does not fit at its size), whether the text
    overflows its room (*overflow*: the caller cuts it at the mask), how many words took a hyphen and how much the
    text was condensed at the limit (`_rescue`), and whether it fits as it is (*clean*: not with a word split as a
    last resort, nor running out of its room at the smallest size); *measure* and *ink* tell `_balanced` how wide a
    line may be. It unpacks as (font, lines, size), the three things the layout functions gave before."""

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
                condense: bool = True) -> Fit:
    """`_layout_text`, remembered (in memory, the last `LAYOUTS_KEPT`): a layout is a function of its arguments - the
    mask's pixels among them - so a region measured for its page's sizes (`Pipeline.cap_sizes`) and then drawn, an early
    look and the finished page, or a page lettered again, is laid out once. The `Fit` handed out is shared: it is
    read, never changed."""
    m = np.ascontiguousarray(mask)
    try:
        key: tuple[Any, ...] | None = (m.shape, str(m.dtype), hashlib.blake2b(m.data, digest_size=16).digest(), text,
                                       font_path, min_size, max_size, line_spacing, bold_variation, script, on_page,
                                       tuple(anchor) if anchor is not None else None, hyphenate, condense, _tunables())
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
                       anchor, hyphenate, condense)
    if key is not None:
        with _LAYOUTS_LOCK:
            _LAYOUTS[key] = fit
            while len(_LAYOUTS) > LAYOUTS_KEPT:
                _LAYOUTS.popitem(last=False)
    return fit


def _layout_text(mask: np.ndarray, text: str, font_path: str | Lettering | None, min_size: int = 9, max_size: int = 64,
                 line_spacing: float = 1.12, bold_variation: bool = False, script: str | None = None,
                 on_page: bool = False, anchor: Box | None = None, hyphenate: bool = True,
                 condense: bool = True) -> Fit:
    """Where and how large *text* is set inside *mask*: the font, the lines as (text, x centre, y top) in mask
    coordinates, and the font size (a `Fit`, which unpacks as those three, and says which layout won).

    The lines are laid out along the mask's shape (shape_layout) or into the largest rectangle that fits, whichever
    allows the larger font. *anchor* is the box of the original lettering (mask coordinates); text on the page
    (*on_page*) stays where that lettering was and may also grow past the drawing around it, a bubble's text is
    centred in the bubble. At *min_size* the text is set even where it does not fit. At the limit (`_rescue`), when
    the size found is under `RESCUE_BELOW`, a larger size (or one that fits at *min_size*) may come from condensing the
    text (*condense*) or hyphenating a long word (*hyphenate*); elsewhere, and where neither helps, the layout is the
    one found without them.
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
    stats: dict[str, int] = {}
    room = _shape_room(mask, SHAPE_PAD, centre)
    shaped = shape_layout(mask, text, font_path, min_size, max_size, line_spacing, bold_variation, script, centre,
                          SHAPE_PAD, stats=stats, room=room)
    if shaped is not None and (shaped[2] > size or shaped[2] == size == max_size):  # both at a cap: the wider lines
        fit = Fit(shaped[0], shaped[1], shaped[2], shaped[2] * line_spacing, "shape", clean=not stats.get("breaks"))
    else:
        line_h = size * line_spacing
        top = (ry0 + ry1) / 2.0 - line_h * len(lines) / 2.0
        fit = Fit(font, [(ln, (rx0 + rx1) / 2.0, top + i * line_h) for i, ln in enumerate(lines)], size, line_h, "rect",
                  clean=size > min_size or _rect_holds(text, font, lines, line_h, rx1 - rx0, ry1 - ry0, script),
                  measure=rx1 - rx0)
    if hyphenate or condense:
        fit = _rescue(mask, text, font_path, fit, max_size, line_spacing, bold_variation, script, centre, rects,
                      TextFormat(), False, hyphenate, condense) or fit
    return _balanced(fit, text, script, room)


def _rect_holds(text: str, font: FontT, lines: list[str], line_h: float, box_w: int, box_h: int, script: str) -> bool:
    """Whether fit_text's *lines* fit its box (box_w x box_h) with every word whole: what its smallest size need not."""
    box_w, box_h = max(4, box_w), max(4, box_h)
    words = text.split() if script not in NO_SPACE_SCRIPTS else []
    return (bool(lines) and len(lines) * line_h <= box_h and all(_display_width(font, w, script) <= box_w for w in words)
            and all(_display_width(font, ln, script) <= box_w for ln in lines))


def _rescue(mask: np.ndarray, text: str, font_path: str | Lettering | None, base: Fit, hi: int, line_spacing: float,
            bold_variation: bool, script: str, centre: tuple[float, float] | None, rects: list[Box], fmt: TextFormat,
            keep_blank: bool, hyphenate: bool, condense: bool) -> Fit | None:
    """At the limit, for small lettering: the text where *base* (the layout found without these) would have dropped
    to its size, or does not fit cleanly at it - set at the sizes above *base*'s (from its own, when it is not clean),
    one at a time and up to *hi*, condensed by up to 8 % (*condense*: the mildest step of CONDENSE_STEPS that fits) or
    with long Latin words hyphenated (*hyphenate*: first only a word too wide for its line, then words that fill a
    line), or both; at each size the first of those that fits, fewest hyphens and mildest condensing first. Returns
    the layout at the largest size reached (one that beats *base* by a point or more, or fits where it does not), None
    when none does. Only for a *base* under `RESCUE_BELOW` points: larger lettering reads well as it is and keeps
    its natural letter shapes (a region formatted to be condensed, *fmt.condense*, is as the reader asked at any
    size)."""
    hyphenate = hyphenate and script == "lgc"
    if not (hyphenate or condense):
        return None
    if RESCUE_BELOW is not None and base.size >= RESCUE_BELOW and fmt.condense is not True:
        return None
    strongest = CONDENSE_STEPS[-1]
    room = _shape_room(mask, SHAPE_PAD, centre) if fmt.align == "center" else False

    def at(size: int, factor: float, mode: int) -> Fit | None:
        return _fit_at(mask, text, font_path, size, factor, mode, line_spacing, bold_variation, script, centre, rects,
                       fmt, keep_blank, room)

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
    size = base.size + 1 if base.clean else base.size
    while size <= hi and (RESCUE_STEPS is None or size - base.size <= RESCUE_STEPS):
        fit = first(size)
        if fit is None:
            break
        found = fit
        size += 1
    return found


def _fit_at(mask: np.ndarray, text: str, font_path: str | Lettering | None, size: int, factor: float, hyphenate: int,
            line_spacing: float, bold_variation: bool, script: str, centre: tuple[float, float] | None,
            rects: list[Box], fmt: TextFormat, keep_blank: bool, room: Any = None) -> Fit | None:
    """One try of `_rescue`: the text at *size* condensed to *factor* and hyphenated as *hyphenate* says, along the
    mask's shape (centred text; *room*: its `_shape_room`) or in one of *rects*; None when it does not fit with every
    word whole or hyphenated."""
    face = (font_path.formatted(condense=factor) if isinstance(font_path, Lettering)
            else Lettering(font_path, bold_variation, condense=factor))
    line_h = size * line_spacing
    if fmt.align == "center":
        stats: dict[str, int] = {}
        shaped = shape_layout(mask, text, face, size, size, line_spacing, bold_variation, script, centre, SHAPE_PAD,
                              fmt.valign, keep_blank, False, hyphenate, stats, room, True)
        if shaped is not None:
            return Fit(shaped[0], shaped[1], size, line_h, "shape", hyphens=stats.get("hyphens", 0), condense=factor,
                       ink=True)
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
    """What lettering a region did: the font size used, what it could not do as formatted (`NO_FIT`), and which
    layout won (`Fit.won`)."""

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
                     script: str | None = None, on_page: bool = False, anchor: Box | None = None) -> Fit:
    """Where and how large *text* is set inside *mask* as the reader formatted it (*fmt*), as a `Fit`.

    Each line break ends a line and an empty line keeps its height; within a line the text wraps as usual. Centred
    text is laid out as layout_text lays it, along the mask's shape or in the inner rectangle, whichever allows the
    larger font (the block at the top, middle or bottom of the room it has); text aligned left or right is set in the
    inner rectangle. The size is the largest that fits between *min_size* and *max_size*, or *fmt.size*, which is
    never shrunk; at the limit (`_rescue`) a long word may take a hyphen, and the text may be condensed as
    *fmt.condense* says. Centred lines are balanced as layout_text's (`_balanced`, between the line breaks), text
    aligned left or right wraps as in a word processor. A text that does not fit at its size even so (at *min_size*, or at the fixed size) is set at
    it in the mask's bounding box instead, aligned the same way, and marked as overflowing: the caller cuts it at the
    mask.
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
        stats: dict[str, int] = {}
        room = _shape_room(mask, SHAPE_PAD, centre)
        shaped = shape_layout(mask, text, font_path, lo, hi, ls, bold_variation, script, centre, SHAPE_PAD, fmt.valign,
                              True, not fmt.size, stats=stats, room=room)
        if shaped is not None and (best is None or shaped[2] > best[0][2]):
            fit = Fit(shaped[0], shaped[1], shaped[2], shaped[2] * ls, "shape", clean=not stats.get("breaks"))
    if fit is None and best is not None:
        (font, lines, size), rect = best
        fit = Fit(font, _placed(lines, size * ls, rect, fmt), size, size * ls, "rect", fmt.align,
                  measure=rect[2] - rect[0])
    condense = fmt.condense if fmt.condense is not None else not fmt.size
    base = fit if fit is not None else Fit(None, [], lo, lo * ls, "box", fmt.align, overflow=True, clean=False)
    better = _rescue(mask, text, font_path, base, hi, ls, bold_variation, script, centre, rects, fmt, True, True,
                     condense)
    if better is not None or fit is not None:
        fit = better or fit
        return _balanced(fit, text, script, room) if fmt.align == "center" else fit
    ys, xs = np.nonzero(mask)
    box = ((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if xs.size
           else (0, 0, mask.shape[1], mask.shape[0]))
    font = styled_font(font_path, lo, bold_variation)
    lines = wrap_lines(text, font, box[2] - box[0], script, keep_blank=True)
    return Fit(font, _placed(lines, lo * ls, box, fmt), lo, lo * ls, "box", fmt.align, overflow=True)


def text_room(mask: np.ndarray, font_path: str | Lettering | None, size: int, line_spacing: float = 1.12,
              bold_variation: bool = False, centre: tuple[float, float] | None = None, probe: str = "words") -> int:
    """How many characters of ordinary text (five-letter words and spaces) fit inside *mask* at font *size*,
    laid out along its shape. What a translator is told a bubble has room for."""
    def fits(n: int) -> bool:
        return shape_layout(mask, " ".join([probe] * n), font_path, size, size, line_spacing, bold_variation,
                            "lgc", centre) is not None

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
    True or False: as said). The colours never move a line. Returns the font size used, what could not be done and
    which layout won.

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
                               script, on_page, anchor)
        if image is None:
            return Lettered(fit.size, (NO_FIT,) if fit.overflow else (), fit.won)
        return _draw_fit(image, region, fit, script, color, outline, outline_color)
    fit = layout_text(region.mask, text, font_path, min_size, max_size, line_spacing, bold_variation, script,
                      on_page, anchor, hyphenate, condense)
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
    for shown, xc, top in lines:
        font.draw(image, region.x0 + xc - font.width(shown) / 2.0, region.y0 + top, shown, color, contour)
    return Lettered(size, (), fit.won)


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
