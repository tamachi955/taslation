"""A book's series: the name its volumes share (`series_key`), which the series sheet is kept under, and the
temporary name an untitled book gets (`is_temporary_name`).

Until 2026-11-06 the translation model also wrote translator's notes per series here (who is who, renderings, a
synopsis, under ``~/.taslation/series``). They were removed: what the model is told of a book is the series sheet the
reader keeps (`annotations.GlossaryStore`). Notes files an earlier version wrote are left where they are, unread.
"""

from __future__ import annotations

import re
import unicodedata

_SEPARATORS = r"[\s\-–:：,、・]"  # what may stand between a title and its volume ("Title, Vol. 3")
_COUNTERS = r"(?:巻|卷|集|話|章|冊|册|권)"  # a volume's counter: ja, zh (卷, 册), ko (권)
_VOLUME_PATTERNS = [
    _SEPARATORS + r"*[（(\[【]\s*(?:第|제)?\s*\d+\s*" + _COUNTERS + r"?\s*[)）\]】]\s*$",
    _SEPARATORS + r"*(?:第|제)?\s*\d+\s*" + _COUNTERS + r"\s*$",
    _SEPARATORS + r"*(?:vol(?:ume)?|v|#|no)\.?\s*\d+\s*$",
    r"[\s\-–:：]+\d+\s*$",
    r"\s+(?:上|中|下|前編|後編|完全版)\s*$",
]
# the stamp at the end of a temporary name (`dialogs.start`: the localised word for an untitled book, then this)
TEMPORARY_STAMP = "%Y-%m-%d %H%M"
_TEMPORARY = re.compile(r"\s(?:19|20)\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\s(?:[01]\d|2[0-3])[0-5]\d$")
# an imprint after the volume, as a shop's title has it: "Title 3 (Some Comics DIGITAL)"
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
    return _TEMPORARY.search(unicodedata.normalize("NFKC", book).strip()) is not None


def series_key(book: str) -> str:
    """Strip volume markers: 'Some Title 3巻' / 'Some Title (3)' / 'Some Title Vol. 3' -> 'Some Title', a typed name
    as a window title: "Title, Vol. 3", "제3권" and "第3卷" too, and an imprint after the volume ("Title 3 (Some
    Comics)": a title that ends in brackets with no volume before them keeps them). A temporary name is a series of
    its own (`is_temporary_name`): its stamp is no volume, and two untitled books share nothing."""
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
