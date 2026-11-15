"""A book's series: the name its volumes share (`series_key`), which the series sheet is kept under, and the
temporary name an untitled book gets (`is_temporary_name`).

The series is the book's Series field (`bookname`): a book named by its two fields is kept under "<series>
<volume>" (`bookname.compose`), and its series key is the Series field itself, also where the parser would read the
name otherwise (`bookname.remember`). A name that arrives as one string is split by the parser
(`bookname.split_name`): "Title 3巻", "Title 第三巻", "Title (3)", "Title Vol. 3" are the series "Title". Until
2026-11-15 the series was a guess at the volume markers of the name alone (`legacy_series_key`): kanji numerals were
not understood ("Title 第一巻" was a series of its own), an edition was taken off ("Title 完全版" was "Title"), and
several markers in a row were all taken off. A sheet kept under such a key is still found (`sheet_key`), and renaming
the book moves it (`rename.py`).

Until 2026-11-06 the translation model also wrote translator's notes per series here (who is who, renderings, a
synopsis, under ``~/.taslation/series``). They were removed: what the model is told of a book is the series sheet the
reader keeps (`annotations.GlossaryStore`). Notes files an earlier version wrote are left where they are, unread.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .bookname import is_temporary, split_name

# the stamp at the end of a temporary name (`dialogs.start`: the localised word for an untitled book, then this)
TEMPORARY_STAMP = "%Y-%m-%d %H%M"

# --- the series as the parser before 2026-11-15 gave it (`legacy_series_key`): for the sheets kept under it ---
_SEPARATORS = r"[\s\-–:：,、・]"  # what may stand between a title and its volume ("Title, Vol. 3")
_COUNTERS = r"(?:巻|卷|集|話|章|冊|册|권)"  # a volume's counter: ja, zh (卷, 册), ko (권)
_VOLUME_PATTERNS = [
    _SEPARATORS + r"*[（(\[【]\s*(?:第|제)?\s*\d+\s*" + _COUNTERS + r"?\s*[)）\]】]\s*$",
    _SEPARATORS + r"*(?:第|제)?\s*\d+\s*" + _COUNTERS + r"\s*$",
    _SEPARATORS + r"*(?:vol(?:ume)?|v|#|no)\.?\s*\d+\s*$",
    r"[\s\-–:：]+\d+\s*$",
    r"\s+(?:上|中|下|前編|後編|完全版)\s*$",
]
_IMPRINT = re.compile(r"\s*[（(][^()（）]*[)）]\s*$")


def _strip_volumes(t: str) -> str:
    changed = True
    while changed and t:
        changed = False
        for pat in _VOLUME_PATTERNS:
            new = re.sub(pat, "", t, flags=re.I)
            if new != t and new.strip():
                t, changed = new.strip(), True
    return t


def is_temporary_name(book: str) -> bool:
    """Whether *book* is a temporary name: a word (any language's) and the time it was given, `TEMPORARY_STAMP`."""
    return is_temporary(book)


def series_key(book: str) -> str:
    """The series of the book named *book*: its Series field (`bookname.split_name`: the reader's own split where the
    two fields made the name, else the parser's) - 'Some Title 3巻' / 'Some Title (3)' / 'Some Title Vol. 3' /
    'Some Title 第三巻' -> 'Some Title', a typed name as a window title: "Title, Vol. 3", "제3권" and "第3卷" too, and an
    imprint after the volume ("Title 3 (Some Comics)": a title that ends in brackets with no volume before them keeps
    them). A temporary name is a series of its own (`is_temporary_name`): its stamp is no volume, and two untitled
    books share nothing."""
    t = unicodedata.normalize("NFKC", book).strip()
    if is_temporary_name(t):
        return t
    return split_name(book).series or book.strip() or "untitled"


def legacy_series_key(book: str) -> str:
    """The series key the parser before 2026-11-15 gave *book* (volume markers in digits stripped, as many as stood at
    the end, an edition such as 完全版 with them; no kanji numerals): where a sheet made then is kept."""
    t = unicodedata.normalize("NFKC", book).strip()
    if is_temporary_name(t):
        return t
    imprint = _IMPRINT.search(t)
    if imprint is not None and imprint.start() > 0:
        before = t[: imprint.start()].strip()
        stripped = _strip_volumes(before)
        if stripped != before:  # a volume stood before the brackets: they were the imprint
            return stripped
    t = _strip_volumes(t)
    return t or book.strip() or "untitled"


def sheet_key(sheets: Any, book: str) -> str:
    """The series *book*'s series sheet is kept under in *sheets* (an `annotations.GlossaryStore`): its series
    (`series_key`), unless a sheet is kept under the key the parser before 2026-11-15 gave the name
    (`legacy_series_key`) and either that key still carries the book's volume (a kanji numeral it did not know: "Title
    第一巻" had a sheet of its own, which this book keeps reading until it is renamed) or the series has no sheet of
    its own ("Title 完全版 3" read the sheet of "Title"). A store that cannot say which sheets it keeps, or cannot be
    read now, gives the series."""
    new = series_key(book)
    old = legacy_series_key(book)
    has = getattr(sheets, "has", None)
    if old == new or has is None:
        return new
    try:
        if has(old) and (series_key(old) != old or not has(new)):
            return old
    except OSError:
        pass
    return new


__all__ = ["TEMPORARY_STAMP", "is_temporary_name", "legacy_series_key", "series_key", "sheet_key"]
