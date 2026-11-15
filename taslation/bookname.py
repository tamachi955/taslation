"""A book's name in two parts - its series (text) and its volume (a number) - and the one name they make.

The window and the command line ask for a book's name as two fields: the **series**, what its volumes share ("Some
Title", "見本の物語", an edition such as 完全版 included), and the **volume**, a number, empty for a book of one volume.
A name typed as one string had a spelling per reader: "Some Title 3", "Some Title 3巻", "Some Title　３", "Some Title
第三巻", "Some Title (3)" were five books to the cache, though one series. With two fields there is one spelling:

* the volume is normalised, never kept as typed (`volume_of`): half-width digits without leading zeros ("03" is 3,
  "10.5" stays a decimal), from full-width digits, circled numbers (①, ❸, ⓷) and kanji numerals (一 to 九百九十九,
  "一〇" digit by digit as well), with what the reader may type around it taken off: 第...巻, 巻, 集, 冊, 卷, 册, 권,
  Vol., Volume, v, No., #, brackets. The few volumes that are no number are kept as they are, from one fixed list
  (`VOLUME_WORDS`: 上, 中, 下, 前編, 後編; 上巻 and 前篇 are spellings of two of them). Anything else is refused (None):
  an edition belongs to the series;
* the book's name, which its files are kept under, is made of the two in exactly one way (`compose`): the series
  (NFKC, trimmed, every run of whitespace one space, invisible characters left out: `clean_series`), one space, the
  volume; the series alone when there is no volume.

A name that arrives as one string - a viewer's window title, a cache kept before, ``--book`` - is split into the two
fields by one parser (`split_name`), and the window lets the reader correct what it found. The parser takes one
volume marker off the end ("Title 3巻", "Title 第三巻", "Title (3)", "Title【第3巻】", "Title Vol. 3", "Title, v3",
"Title #3", "Title - 3", "Title 三", "Title 上", "Title①", an imprint after the volume: "Title 3 (Some Comics)"), and
keeps what is part of a title: a number with no separator before it ("Title13", "見本の物語３": the rule that a title
ending in a digit keeps it), brackets with no volume before them ("Title (Remastered)"), a bare number of four digits
("Summer 2049"). A temporary name of an untitled book (`notes.is_temporary_name`) is a series of its own with no
volume: two untitled books share nothing.

The parser guesses; the two fields do not. Where the reader's fields make a name the parser would split otherwise
("Gate 51" with no volume: the parser reads volume 51), the reader's split is remembered (`remember`, kept in
ui.json under `SPLITS_TABLE`, the latest `SPLITS_KEPT`) and is what `split_name` gives for that name from then on,
so that the series a sheet is kept under (`notes.series_key`) is the Series field itself. `use` reads what is
remembered in a state folder (the command line calls it as it starts, with the viewers' memory).

Two names name one book when they split into the same series (letter case and spaces aside) and the same volume, or
when they are the same but for letter case and spaces as before (`same_book`: "Title 3" and "Title 3巻" and "Title
第三巻"); that is how files kept under an older spelling are found again (`cache.CacheStore.kept_name`).

Standard library only (the start of the command line imports it).
"""

from __future__ import annotations

import re
import threading
import unicodedata
from pathlib import Path
from typing import Mapping, NamedTuple

# the volumes that are no number, as they are kept; the spellings that mean one of them
VOLUME_WORDS = ("上", "中", "下", "前編", "後編")
WORD_SPELLINGS = {"上巻": "上", "中巻": "中", "下巻": "下", "前篇": "前編", "後篇": "後編"}
MAX_KANJI = 999  # kanji numerals are read up to 九百九十九
MAX_DIGITS = 4  # a volume typed in digits has at most this many before its decimal point
BARE_DIGITS = 3  # a number after a separator at the end of a name, with no counter or mark, is a volume up to 999
# ui.json: a book's name -> the series the reader's fields gave it, where the parser splits the name otherwise
SPLITS_TABLE = "book_series"
SPLITS_KEPT = 500

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏⁠﻿"))
# circled numbers NFKC leaves as they are (①..⑳ and ㉑..㊿ it makes digits): ❶..❿, ➀..➉, ➊..➓, ⓵..⓾, ⓫..⓴
_CIRCLED = {**{chr(0x2776 + i): str(i + 1) for i in range(10)}, **{chr(0x2780 + i): str(i + 1) for i in range(10)},
            **{chr(0x278A + i): str(i + 1) for i in range(10)}, **{chr(0x24F5 + i): str(i + 1) for i in range(10)},
            **{chr(0x24EB + i): str(i + 11) for i in range(10)}}
_CIRCLED_CHARS = "①-⑳㉑-㉟㊱-㊿" + "".join(_CIRCLED)
_CIRCLED_END = re.compile(f"\\s*([{_CIRCLED_CHARS}])(\\s*(?:[（(][^()（）]*[)）]\\s*)?)$")
_KANJI_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_UNITS = {"十": 10, "百": 100}
_KANJI = "[〇零一二三四五六七八九十百]{1,6}"

_SEP = r"[\s\-–:,、・]"  # what may stand between a title and its volume ("Title, Vol. 3"; NFKC made "：" a colon)
_OPEN, _CLOSE = r"[(\[【〈《「『]", r"[)\]】〉》」』]"
_COUNTERS = r"(?:巻|卷|集|話|章|冊|册|권)"  # a volume's counter: ja, zh (卷, 册), ko (권)
_FIRST = r"(?:第|제)"  # the ordinal before it (ja, zh; ko)
_WORD = r"(?:上|中|下|前編|後編|前篇|後篇)"
_NUM = rf"(?:\d{{1,{MAX_DIGITS}}}(?:\.\d{{1,3}})?|{_KANJI})"
_BARE = rf"(?:\d{{1,{BARE_DIGITS}}}(?:\.\d{{1,3}})?|{_KANJI})"
# a volume at the end of a name, in the order they are tried: the first that leaves a series wins
_VOLUME_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    rf"{_SEP}*{_OPEN}\s*{_FIRST}?\s*(?P<v>{_NUM}|{_WORD})\s*{_COUNTERS}?\s*{_CLOSE}\s*$",  # (3) 【第3巻】 （上）
    rf"{_SEP}*{_FIRST}?\s*(?P<v>{_NUM})\s*{_COUNTERS}\s*$",  # 第3巻 3巻 三巻 제3권: the counter says it, no separator
    rf"{_SEP}*(?P<v>上|中|下)\s*巻\s*$",  # 上巻 下巻
    rf"{_SEP}*(?:(?<![^\W\d_])(?:vol(?:ume)?|v|no)\.?|#)\s*(?P<v>\d{{1,{MAX_DIGITS}}}(?:\.\d{{1,3}})?)\s*$",  # Vol. 3
    rf"[\s\-–:]+(?P<v>{_BARE})\s*$",  # "Title 3", "Title - 3", "Title 三": never a digit the title ends in
    rf"\s+(?P<v>{_WORD})\s*$",  # "Title 上", "Title 後編"
))
_TRAILING_SEP = " -–:,、・"
# an imprint after the volume, as a shop's title has it: "Title 3 (Some Comics DIGITAL)"
_IMPRINT = re.compile(r"\s*[（(][^()（）]*[)）]\s*$")
# a temporary name of an untitled book: a word (any language's) and the time it was given (`notes.TEMPORARY_STAMP`)
_TEMPORARY = re.compile(r"\s(?:19|20)\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\s(?:[01]\d|2[0-3])[0-5]\d$")


class BookName(NamedTuple):
    """A book's name in its two fields: *series* (`clean_series`) and *volume* (`volume_of`; "" for none)."""

    series: str
    volume: str = ""

    @property
    def name(self) -> str:
        """The one name the two make (`compose`)."""
        return compose(self.series, self.volume)


# ------------------------------------------------------------------ the two fields
def clean_series(text: object) -> str:
    """*text* as a series (or a name) is kept: NFKC (full-width letters and digits half-width), invisible characters
    left out, every run of whitespace one space, trimmed."""
    t = unicodedata.normalize("NFKC", str(text or "").translate(_INVISIBLE))
    return " ".join(t.split())


def kanji_number(text: str) -> int | None:
    """The number the kanji numerals *text* write: 一 to 九百九十九 ("二十", "十一", "百五", "三百五十五"), or digit
    by digit when there is no 十 or 百 ("一〇" is 10, "二〇五" 205); None for anything else or above `MAX_KANJI`."""
    if not text or any(c not in _KANJI_DIGITS and c not in _KANJI_UNITS for c in text):
        return None
    if not any(c in _KANJI_UNITS for c in text):  # digit by digit
        if len(text) > 3:
            return None
        value = int("".join(str(_KANJI_DIGITS[c]) for c in text))
        return value if value <= MAX_KANJI else None
    total, digit, last_unit = 0, None, MAX_KANJI + 1
    for c in text:
        if c in _KANJI_DIGITS:
            if digit is not None:
                return None  # two digits in a row beside a unit ("二三十")
            digit = _KANJI_DIGITS[c]
        else:
            unit = _KANJI_UNITS[c]
            if unit >= last_unit or digit == 0:
                return None  # "十百", "十十", "〇十"
            total += (1 if digit is None else digit) * unit
            digit, last_unit = None, unit
    total += digit or 0
    return total if 0 < total <= MAX_KANJI else None


def _number(whole: str, fraction: str | None) -> str:
    """Digits as a volume is kept: no leading zeros, a decimal without trailing zeros ("010" is 10, "2.50" 2.5)."""
    fraction = (fraction or "").rstrip("0")
    return str(int(whole)) + (f".{fraction}" if fraction else "")


def volume_of(text: object) -> str | None:
    """The Volume field *text* as a volume is kept: "" when it is empty; half-width digits without leading zeros, a
    decimal allowed (from full-width digits, circled numbers and kanji numerals as well); one of `VOLUME_WORDS` (上巻
    and 前篇 are spellings of two of them); with 第...巻 and the other counters, Vol., Volume, v, No., # and brackets
    taken off. None for anything else (an edition, a word): it is refused."""
    t = clean_series(str(text or "").translate(str.maketrans(_CIRCLED)))
    if not t:
        return ""
    for _ in range(2):
        if len(t) > 2 and re.fullmatch(_OPEN, t[0]) and re.fullmatch(_CLOSE, t[-1]):
            t = t[1:-1].strip()
    t = re.sub(rf"^{_FIRST}\s*", "", t)
    t = re.sub(r"^(?:(?:vol(?:ume)?|v|no)\.?|#)\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(rf"\s*{_COUNTERS}$", "", t)
    t = WORD_SPELLINGS.get(t, t)
    if t in VOLUME_WORDS:
        return t
    match = re.fullmatch(rf"(\d{{1,{MAX_DIGITS}}})(?:\.(\d{{1,3}}))?", t)
    if match:
        return _number(match.group(1), match.group(2))
    value = kanji_number(t)
    return None if value is None else str(value)


def compose(series: object, volume: object = "") -> str:
    """The book's name the two fields make, in exactly one way: the series (`clean_series`), one space, the volume
    (`volume_of`); the series alone when there is no volume; "" when there is no series. ValueError for a volume
    `volume_of` refuses."""
    s = clean_series(series)
    v = volume_of(volume)
    if v is None:
        raise ValueError(f"not a volume: {volume!r}")
    if not s:
        return ""
    return f"{s} {v}" if v else s


# ------------------------------------------------------------------ a name as one string
def is_temporary(name: str) -> bool:
    """Whether *name* is a temporary name of an untitled book (`notes.is_temporary_name`)."""
    return _TEMPORARY.search(clean_series(name)) is not None


def _take_volume(text: str) -> BookName | None:
    """*text* with one volume marker off its end (`_VOLUME_PATTERNS`, the first that leaves a series); None when it
    ends in none."""
    for pattern in _VOLUME_PATTERNS:
        match = pattern.search(text)
        if match is None or match.start() == 0:
            continue
        series = text[: match.start()].strip().rstrip(_TRAILING_SEP).strip()
        volume = volume_of(match.group("v"))
        if series and volume:
            return BookName(series, volume)
    return None


def parse_name(name: object) -> BookName:
    """What the parser makes of *name* as one string (see the module's docstring), without what the reader's fields
    said of it (`split_name`)."""
    raw = str(name or "").translate(_INVISIBLE)
    circled = _CIRCLED_END.search(raw)  # "Title①": a circled number at the end is a volume, with no separator too
    if circled is not None and circled.start() > 0:
        number = clean_series(circled.group(1).translate(str.maketrans(_CIRCLED)))
        raw = raw[: circled.start()] + " " + number + circled.group(2)
    t = clean_series(raw)
    if not t or _TEMPORARY.search(t):
        return BookName(t, "")
    imprint = _IMPRINT.search(t)
    if imprint is not None and imprint.start() > 0:
        found = _take_volume(t[: imprint.start()].strip())
        if found is not None:  # a volume stood before the brackets: they were the imprint
            return found
    return _take_volume(t) or BookName(t, "")


def split_name(name: object) -> BookName:
    """*name*, a name that arrives as one string (a window's title, an old cache's, ``--book``), as the two fields:
    the split the reader's fields gave it when they made it (`remember`), else the parser's (`parse_name`)."""
    t = clean_series(name)
    if not t:
        return BookName("", "")
    with _lock:
        series = _splits.get(t)
    if series is not None and (t == series or t.startswith(series + " ")):
        volume = t[len(series):].strip()
        if volume_of(volume) == volume:
            return BookName(series, volume)
    return parse_name(name)  # (as it came: NFKC would make a circled volume "Title①" a digit the title ends in)


def book_key(name: object) -> tuple[str, str]:
    """What tells one book from another: its series (`split_name`) with letter case and spaces aside, and its
    volume."""
    parts = split_name(name)
    return "".join(parts.series.casefold().split()), parts.volume


def _compact(name: object) -> str:
    return "".join(clean_series(name).casefold().split())


def same_book(a: object, b: object) -> bool:
    """Whether the names *a* and *b* name one book: the same series (letter case and spaces aside) and the same
    volume ("Title 3", "Title 3巻", "Title 第三巻", "Title (3)"), or the same name but for letter case and spaces
    ("見本の物語 3" and "見本の物語３", as before the two fields)."""
    return book_key(a) == book_key(b) or _compact(a) == _compact(b)


def entry_for(table: Mapping[str, str], name: object, default: str = "") -> str:
    """What *table* (a ui.json table by book name: the start dialog's answer, the role chosen) keeps for the book
    *name*: under that name, else under another spelling of the same book (`same_book`: kept before the book was
    renamed to the one spelling its Series and Volume make); *default* when neither is there."""
    key = str(name or "")
    if key in table:
        return table[key]
    if not key.strip():
        return default
    for other, value in table.items():
        if same_book(other, key):
            return value
    return default


# ------------------------------------------------------------------ the reader's own splits
_lock = threading.Lock()
_splits: dict[str, str] = {}  # a book's name -> its series, where the reader's fields split it unlike the parser
_state_dir: Path | None = None


def use(state_dir: Path | str | None) -> None:
    """What the reader's fields split unlike the parser, as kept in the state folder *state_dir* (ui.json,
    `SPLITS_TABLE`), is what `split_name` goes by from now on in this process; None: nothing, and what is
    remembered meanwhile stays in memory."""
    global _state_dir
    table: dict[str, str] = {}
    if state_dir is not None:
        from .i18n import load_ui_table

        table = load_ui_table(Path(state_dir), SPLITS_TABLE)
    with _lock:
        _state_dir = None if state_dir is None else Path(state_dir)
        _splits.clear()
        _splits.update({clean_series(k): clean_series(v) for k, v in table.items() if clean_series(k)})


def remember(series: object, volume: object = "") -> str:
    """The reader's fields *series* and *volume* made a book's name (`compose`, returned): where the parser would
    split that name otherwise ("Gate 51" with no volume), the reader's split is kept for it, in memory and in the
    state folder of `use`; where it splits it alike, what was kept for the name goes. ValueError for a volume
    `volume_of` refuses."""
    name = compose(series, volume)
    if not name:
        return name
    parts = BookName(clean_series(series), volume_of(volume) or "")
    differs = parse_name(name) != parts
    with _lock:
        kept = _splits.get(name)
        if (kept == parts.series) if differs else kept is None:
            return name  # kept as it should be already
        if differs:
            _splits.pop(name, None)
            _splits[name] = parts.series
            while len(_splits) > SPLITS_KEPT:
                _splits.pop(next(iter(_splits)))
        else:
            _splits.pop(name, None)
        state_dir = _state_dir
    if state_dir is not None:
        from .i18n import save_ui_entry

        save_ui_entry(state_dir, SPLITS_TABLE, name, parts.series if differs else None, keep=SPLITS_KEPT)
    return name


__all__ = ["BARE_DIGITS", "BookName", "MAX_DIGITS", "MAX_KANJI", "SPLITS_KEPT", "SPLITS_TABLE", "VOLUME_WORDS",
           "WORD_SPELLINGS", "book_key", "clean_series", "compose", "entry_for", "is_temporary", "kanji_number",
           "parse_name",
           "remember", "same_book", "split_name", "use", "volume_of"]
