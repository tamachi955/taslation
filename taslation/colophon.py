"""A book's colophon (奥付) read off its page: the title, the volume, the author, the publisher, the date, the ISBN.

Near the end of a Japanese book the colophon names it: printed text on a sparse page (or on half of one, beside
artwork or an advertisement), a column for the title, then 発行 with the date, 著者, 発行者, 発行所, 印刷所, ©, the
ISBN. The pipeline's detector cuts such columns into pieces, but each column read whole reads well, so this module
finds the columns itself. In the page panel (the paper on a dark viewer background, else the capture area) it looks
for a sparse part - the whole panel, else its right or its left half - with ink (darker than `INK`) on under
`SPARSE` of it and a few columns or lines of text (`precheck`: a few milliseconds, which keeps ordinary pages away
from the OCR). The text is cut into columns by the column-wise projection of the ink (runs at least `MIN_RUN`
pixels wide; long rules and frames taken out first), or into lines by the row-wise one for a colophon set
horizontally (Japanese is set on a grid, so both projections have gaps; the text runs the way whose gaps, between
the columns or lines, are the wider); each one is cropped to its ink with `PAD` pixels around it, read whole
(`read_with_confidence`) and NFKC-normalised, right to left (top to bottom). An ISBN set sideways in a column is
read once more on its side when the column read upright gives none.

The page is a colophon only when at least two of them carry one of its labels (`LABELS`). The title is the first
(rightmost, topmost) one without a label, at least 4 characters long, with no date in it; its volume comes off its
end ("3巻", "第3巻", "(3)", "vol. 3", a circled number), half-width. The ISBN is an ISBN-10 or ISBN-13 whose check
digit holds, the hyphens as printed or as the OCR reads them (`bookid.ISBN_DASHES`: in vertical text a hyphen is a
vertical stroke, read as the long vowel mark), full-width digits made half-width. Nothing of the page is kept but
the `Colophon` itself.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np
from PIL import Image

from . import fingerprint as fp
from .bookid import ISBN_DASHES, isbn_key

INK = 128  # a pixel darker than this is ink
SPARSE = 0.03  # a part of the page with ink on less than this share of it may hold a colophon ...
MIN_INK = 0.0008  # ... and more than this (a blank page, a page number alone, holds none)
MIN_RUN = 8  # pixels: a column (or a line) of text is at least this wide
PAD = 6  # pixels around a column's ink in its crop
MIN_COLUMNS, MAX_COLUMNS = 3, 30  # a colophon has a title and two labels at least; a page of prose has more
MAX_PARTS = 2  # parts of one page read in full at most (the whole panel, its halves)
MAX_READS = 6  # pages of one book read in full at most (a whole-book scan, the window's pages)
# a column that carries one of these is a label of the colophon (the more specific first)
LABELS = ("発行日", "発行者", "発行所", "発行", "著者", "印刷所", "印刷", "ISBN", "©", "(C)")
AUTHOR_LABELS = ("著者", "作者", "原作", "作画", "漫画")
PUBLISHER_LABELS = ("発行所",)
_DATE_RE = re.compile(r"(?:\d{4}|(?:令和|平成|昭和)\s*(?:\d{1,2}|元))\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
# the volume at the end of the title column, also in the brackets the OCR may read for the space before it
_OPEN, _CLOSE = r"[(\[「『【〈《]?", r"[)\]」』】〉》]?"
_VOLUME_RES = (
    re.compile(r"[\s\-–:・,、]*" + _OPEN + r"\s*第\s*(\d{1,4})\s*巻\s*" + _CLOSE + r"\s*$"),
    re.compile(r"[\s\-–:・,、]*" + _OPEN + r"\s*(\d{1,4})\s*巻\s*" + _CLOSE + r"\s*$"),
    re.compile(r"[\s\-–:・,、]*[(\[【〈《]\s*(\d{1,4})\s*[)\]】〉》]\s*$"),
    re.compile(r"[\s\-–:・,、]*" + _OPEN + r"\s*vol\.?\s*(\d{1,4})\s*" + _CLOSE + r"\s*$", re.IGNORECASE),
)
# what the OCR may read around a value (the space after a label read as a bracket or a comma)
_VALUE_EDGES = " :：・/　,，、.。「」『』()[]【】〈〉《》\"'"
_CIRCLED = {chr(0x2460 + i): i + 1 for i in range(20)}  # ①..⑳
_ISBN_RUN_RE = re.compile(r"ISBN\s*[:：]?\s*([0-9Xx" + re.escape(ISBN_DASHES) + r"\s]{10,24})", re.IGNORECASE)
_BARE_ISBN_RE = re.compile(r"(97[89][0-9" + re.escape(ISBN_DASHES) + r"\s]{10,24})")
_DASH_TO_HYPHEN = str.maketrans({c: "-" for c in ISBN_DASHES})
_PUBLISHER_END_RE = re.compile(r"〒|電話|TEL|Tel|℡|\d{3,}")

Box = tuple[int, int, int, int]
Read = tuple[str, float]  # what a column says (NFKC) and how sure the OCR is of it


@dataclass
class Colophon:
    """What a colophon says of its book ("" for what it does not say, or what could not be read)."""

    title: str
    volume: str = ""  # half-width digits
    author: str = ""
    publisher: str = ""
    date: str = ""  # as printed (NFKC): "2020年8月18日", "令和2年8月18日"
    isbn: str = ""  # with hyphens as printed: "978-4-09-850221-3"
    confidence: float = 0.0  # the OCR's confidence in the title column

    @property
    def name(self) -> str:
        """The book's name from it: the title and the volume ("見本の物語 3")."""
        return f"{self.title} {self.volume}".strip()

    def details(self) -> dict[str, str]:
        """The fields a cache's header keeps (`cache.DETAIL_FIELDS`)."""
        return {name: value for name, value in (("title", self.title), ("volume", self.volume),
                                                 ("author", self.author), ("publisher", self.publisher),
                                                 ("isbn", self.isbn)) if value}


# ------------------------------------------------------------------ where the text is
def _gray(image: Any) -> tuple[np.ndarray, np.ndarray]:
    """(RGB, gray) arrays of a PIL image or an array."""
    if hasattr(image, "convert"):
        rgb = np.asarray(image if image.mode == "RGB" else image.convert("RGB"))
    else:
        rgb = np.asarray(image)
    if rgb.ndim == 2:
        return np.dstack([rgb] * 3), rgb
    return rgb, cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _panel(gray: np.ndarray, margins: tuple[int, int, int, int]) -> Box:
    """The page panel: the paper on a dark viewer background (`fingerprint.paper_box`, looked for at half the
    size: the same box, at a quarter of the cost), else the capture area."""
    h, w = gray.shape
    small = cv2.resize(gray, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    paper = fp.paper_box(small, tuple(max(0, int(m)) // 2 for m in margins))  # type: ignore[arg-type]
    if paper is not None:
        return min(w - 1, 2 * paper[0]), min(h - 1, 2 * paper[1]), min(w, 2 * paper[2]), min(h, 2 * paper[3])
    left, top, right, bottom = (max(0, int(m)) for m in margins)
    x0, y0 = min(left, w - 1), min(top, h - 1)
    return x0, y0, max(x0 + 1, w - right), max(y0 + 1, h - bottom)


def _all_runs(profile: np.ndarray) -> list[tuple[int, int]]:
    """The runs of nonzero values in *profile*, as (start, end)."""
    on = np.concatenate([[0], (profile > 0).astype(np.int8), [0]])
    edges = np.diff(on)
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    return [(int(s), int(e)) for s, e in zip(starts, ends)]


def _gap(runs: list[tuple[int, int]]) -> float:
    """The median gap between consecutive runs (0 for fewer than two)."""
    gaps = [b[0] - a[1] for a, b in zip(runs, runs[1:])]
    return float(np.median(gaps)) if gaps else 0.0


def _without_rules(dark: np.ndarray) -> np.ndarray:
    """*dark* without long straight lines (rules, a frame round the colophon): they would join every column."""
    h, w = dark.shape
    ink = dark.astype(np.uint8)
    across = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(40, w // 4)), np.uint8))
    down = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(40, h // 4), 1), np.uint8))
    return dark & ~(across.astype(bool) | down.astype(bool))


@dataclass
class _Part:
    box: Box  # in capture coordinates
    vertical: bool  # columns (else lines)
    runs: list[tuple[int, int]]  # columns (x) or lines (y), within the part
    dark: np.ndarray  # the part's ink, rules taken out


def _parts(gray: np.ndarray, panel: Box) -> list[_Part]:
    """The sparse parts of the panel that may hold a colophon (the whole, else its right and left halves), each cut
    into the columns or lines of its text; the ones with too few or too many of them are left out."""
    x0, y0, x1, y1 = panel
    mid = (x0 + x1) // 2
    found: list[_Part] = []
    for box in ((x0, y0, x1, y1), (mid, y0, x1, y1), (x0, y0, mid, y1)):
        bx0, by0, bx1, by1 = box
        if bx1 - bx0 < 4 * MIN_RUN or by1 - by0 < 4 * MIN_RUN:
            continue
        share = float((gray[by0:by1:2, bx0:bx1:2] < INK).mean())  # every other pixel tells the share as well
        if not MIN_INK <= share < SPARSE:
            continue
        dark = _without_rules(gray[by0:by1, bx0:bx1] < INK)
        columns, lines = _all_runs(dark.sum(axis=0)), _all_runs(dark.sum(axis=1))
        # Japanese is set on a grid, so both projections have gaps: between the columns (or lines) they are wide,
        # between the characters of one narrow - the text runs the way whose gaps are the wider
        vertical = _gap(columns) >= _gap(lines)
        runs = [run for run in (columns if vertical else lines) if run[1] - run[0] >= MIN_RUN]
        if MIN_COLUMNS <= len(runs) <= MAX_COLUMNS:
            found.append(_Part(box, vertical, runs, dark))
        if box == panel and found:
            break  # the whole panel is sparse: its halves are part of it
    return found


def precheck(image: Any, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> bool:
    """Whether the page may be a colophon (the cheap test, no OCR): a sparse part with a few columns or lines."""
    _rgb, gray = _gray(image)
    return bool(_parts(gray, _panel(gray, margins)))


def _crops(rgb: np.ndarray, part: _Part) -> list[Image.Image]:
    """The part's columns (right to left) or lines (top to bottom), each cropped to its ink with PAD around it."""
    bx0, by0, bx1, by1 = part.box
    h, w = part.dark.shape
    crops: list[Image.Image] = []
    runs = sorted(part.runs, reverse=True) if part.vertical else sorted(part.runs)
    for start, end in runs:
        strip = part.dark[:, start:end] if part.vertical else part.dark[start:end, :]
        extent = np.flatnonzero(strip.any(axis=1) if part.vertical else strip.any(axis=0))
        if extent.size == 0:
            continue
        lo, hi = int(extent[0]), int(extent[-1]) + 1
        if part.vertical:
            cx0, cx1, cy0, cy1 = start - PAD, end + PAD, lo - PAD, hi + PAD
        else:
            cx0, cx1, cy0, cy1 = lo - PAD, hi + PAD, start - PAD, end + PAD
        cx0, cy0, cx1, cy1 = max(0, cx0), max(0, cy0), min(w, cx1), min(h, cy1)
        crops.append(Image.fromarray(np.ascontiguousarray(rgb[by0 + cy0:by0 + cy1, bx0 + cx0:bx0 + cx1])))
    return crops


def _reader(ocr: Any) -> Callable[[Image.Image], Read]:
    """How one crop is read: `read_with_confidence` where the engine has it, else `read` (confidence 1)."""
    if hasattr(ocr, "read_with_confidence"):
        return lambda crop: ocr.read_with_confidence(crop)
    return lambda crop: (ocr.read(crop), 1.0)


# ------------------------------------------------------------------ what the text says
def _label(text: str, raw: str) -> str:
    upper = text.upper()
    for label in LABELS:
        if label in (upper if label.isascii() else text):
            return label
    return "©" if "Ⓒ" in raw else ""


def _volume(raw: str, text: str) -> tuple[str, str]:
    """(title, volume) of the title column: its volume marker taken off its end."""
    stripped = raw.rstrip().rstrip(")]」』】〉》）］").rstrip()
    if stripped and stripped[-1] in _CIRCLED:
        title = unicodedata.normalize("NFKC", stripped[:-1]).strip().rstrip(_VALUE_EDGES).strip()
        return title, str(_CIRCLED[stripped[-1]])
    for pattern in _VOLUME_RES:
        match = pattern.search(text)
        if match and match.start() > 0:
            return text[: match.start()].strip().rstrip(_VALUE_EDGES).strip(), str(int(match.group(1)))
    return text.strip(), ""


def _after(text: str, labels: tuple[str, ...]) -> str | None:
    """What *text* says after the first of *labels* in it ("" when nothing; None when it has none of them)."""
    for label in labels:
        at = text.find(label)
        if at >= 0:
            return text[at + len(label):].strip(_VALUE_EDGES)
    return None


def _field(texts: list[str], labels: tuple[str, ...], end: re.Pattern[str] | None = None) -> str:
    """The value of the first column with one of *labels*: what follows it there, else the next column's text."""
    for i, text in enumerate(texts):
        value = _after(text, labels)
        if value is None:
            continue
        if not value and i + 1 < len(texts) and not _label(texts[i + 1], texts[i + 1]):
            value = texts[i + 1]
        if end is not None:
            cut = end.search(value)
            value = value[: cut.start()] if cut else value
        return value.strip(_VALUE_EDGES)
    return ""


def find_isbn(text: str) -> str:
    """The ISBN in *text* (NFKC), hyphenated as printed ("978-4-09-850221-3"); "" when none is valid. An ISBN
    is 13 digits when its run starts with 978 or 979 and has as many, else 10: never the first 10 digits of a
    13-digit run whose check digit does not hold (one in eleven would pass for an ISBN-10)."""
    for pattern in (_ISBN_RUN_RE, _BARE_ISBN_RE):
        for match in pattern.finditer(text):
            run = re.sub(r"\s+", "-", match.group(1).strip()).translate(_DASH_TO_HYPHEN).upper().strip("-")
            digits = re.sub(r"[^0-9X]", "", run)
            want = 13 if digits[:3] in ("978", "979") and len(digits) >= 13 else 10
            seen, end = 0, 0
            for i, c in enumerate(run):
                if c.isdigit() or c == "X":
                    seen += 1
                    if seen == want:
                        end = i + 1
                        break
            candidate = re.sub("-{2,}", "-", run[:end].strip("-")) if end else ""
            if candidate and isbn_key(candidate):
                return candidate
    return ""


def parse(reads: list[Read], raws: list[str] | None = None) -> Colophon | None:
    """The colophon that the columns' *reads* (NFKC, in reading order) say; None unless two of them carry a label
    (`LABELS`) and one is a title. *raws* are the texts as read, before NFKC (a circled volume number)."""
    texts = [text.strip() for text, _conf in reads]
    raws = raws if raws is not None and len(raws) == len(texts) else texts
    labels = [_label(text, raw) for text, raw in zip(texts, raws)]
    if sum(1 for label in labels if label) < 2:
        return None
    title_at = next((i for i, (text, label) in enumerate(zip(texts, labels))
                     if not label and len(text) >= 4 and not _DATE_RE.search(text)), None)
    if title_at is None:
        return None
    title, volume = _volume(raws[title_at], texts[title_at])
    if len(title) < 2:
        return None
    dated = [text for text, label in zip(texts, labels) if label.startswith("発行")] + texts
    date = next((m.group(0) for text in dated if (m := _DATE_RE.search(text))), "")
    date = re.sub(r"\s+", "", date)
    return Colophon(title=title, volume=volume, author=_field(texts, AUTHOR_LABELS),
                    publisher=_field(texts, PUBLISHER_LABELS, _PUBLISHER_END_RE), date=date,
                    isbn=next((isbn for text in texts if (isbn := find_isbn(text))), ""),
                    confidence=float(reads[title_at][1]))


def _isbn_columns(reads: list[Read], title: str) -> list[int]:
    """The columns worth reading again on their side for the ISBN (in vertical text an ISBN is set sideways): the
    ones the OCR read "ISBN" in, else the ones read as mostly Latin letters and digits, else the last one."""
    texts = [text for text, _conf in reads]
    named = [i for i, text in enumerate(texts) if re.search(r"ISB|SBN", text.upper())]
    if named:
        return named[:2]
    latin = [i for i, text in enumerate(texts)
             if len(alnum := [c for c in text if c.isascii() and c.isalnum()]) >= 8 and len(alnum) * 2 >= len(text)]
    if latin:
        return latin[:2]
    return [len(texts) - 1] if texts and texts[-1] != title else []


def find_colophon(image: Any, ocr: Any, margins: tuple[int, int, int, int] = (0, 0, 0, 0),
                  read: Callable[[Image.Image], Read] | None = None) -> Colophon | None:
    """The colophon on the page *image* (a capture: PIL image or RGB array; *margins* as the pipeline's), read with
    the OCR engine *ocr* or with *read*, how one crop is
    read; None when the page is none (`precheck` fails, or fewer than two labels are read). Costs nothing but the
    pre-check on an ordinary page; a page that passes it costs an OCR read per column, and up to four more for an
    ISBN set sideways."""
    rgb, gray = _gray(image)
    reader = read or _reader(ocr)
    for part in _parts(gray, _panel(gray, margins))[:MAX_PARTS]:
        crops = _crops(rgb, part)
        pairs = [reader(crop) for crop in crops]
        raws: list[str] = []
        reads: list[Read] = []
        for text, confidence in pairs:
            raws.append(str(text or ""))
            reads.append((unicodedata.normalize("NFKC", raws[-1]).strip(), float(confidence)))
        found = parse(reads, raws)
        if found is None:
            continue
        if not found.isbn and part.vertical:
            for i in _isbn_columns(reads, found.title):
                for turn in (Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_270):
                    text, _confidence = reader(crops[i].transpose(turn))
                    found.isbn = find_isbn(unicodedata.normalize("NFKC", str(text or "")))
                    if found.isbn:
                        break
                if found.isbn:
                    break
        return found
    return None


__all__ = ["AUTHOR_LABELS", "Colophon", "INK", "LABELS", "MAX_COLUMNS", "MIN_COLUMNS", "MIN_INK", "MIN_RUN", "PAD",
           "SPARSE", "find_colophon", "find_isbn", "parse", "precheck"]
