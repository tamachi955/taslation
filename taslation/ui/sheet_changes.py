"""A rendering of the series sheet changed, and the lines already translated with the old one: which renderings changed
between two copies of a sheet (`renamed_pairs`: a term's or a character's, by the term or the name), and the text
edits that give every cached line the new spelling (`rename_edits`: whole words, as `BookCache.rename` takes them,
but as `TextEdit`s that `BookCache.put_texts` makes and a `history.BookStep` takes back). Only the sheet's own
renderings and the cache's translated text are looked at; nothing is written here, and no text of the book goes
anywhere but the reader's window."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..cache import BookCache, TextEdit

# a word's edge as `BookCache.rename` has it: no Latin letter (with the accented ones) right before or after
WORD_BEFORE, WORD_AFTER = r"(?<![A-Za-zÀ-ɏ])", r"(?![A-Za-zÀ-ɏ])"
PAIRS_SHOWN = 5  # the changes a question lists at most (then "...")


def _renderings(entries: Any, key: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in entries or []:
        if isinstance(entry, Mapping):
            name, rendering = str(entry.get(key, "") or "").strip(), str(entry.get("rendering", "") or "").strip()
            if name and rendering:
                out[name] = rendering
    return out


def renamed_pairs(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The renderings that changed from the sheet *before* to the sheet *after* (their `Glossary.to_json`), as (old,
    new): a term kept with another rendering, a character kept with another one. A term or a character added or
    removed changes no line; nor does a rendering given where there was none."""
    pairs: list[tuple[str, str]] = []
    for field, key in (("entries", "term"), ("characters", "name")):
        old, new = _renderings(before.get(field), key), _renderings(after.get(field), key)
        for name, rendering in old.items():
            changed = new.get(name)
            if changed and changed != rendering and (rendering, changed) not in pairs:
                pairs.append((rendering, changed))
    return pairs


def rename_edits(cache: BookCache, pairs: Sequence[tuple[str, str]]) -> list[TextEdit]:
    """The edits that put each pair's new rendering in place of the old one, as a whole word, in every translated line
    of *cache* (a line's pairs in one edit); nothing changes in the cache."""
    compiled = [(re.compile(WORD_BEFORE + re.escape(old) + WORD_AFTER), new)
                for old, new in pairs if old and new and old != new]
    edits: list[TextEdit] = []
    if not compiled:
        return edits
    for page in cache.pages:
        for bubble in page.bubbles:
            text = bubble.text
            for rx, new in compiled:
                text = rx.sub(lambda _m, new=new: new, text)
            if text != bubble.text:
                edits.append(TextEdit(page.fingerprint, tuple(bubble.box), bubble.text, text))
    return edits


def shown_pairs(pairs: Sequence[tuple[str, str]], most: int = PAIRS_SHOWN) -> str:
    """*pairs* as a question lists them, "old → new", the first *most* and then an ellipsis."""
    shown = ", ".join(f"{old} → {new}" for old, new in pairs[:most])
    return shown + (", ..." if len(pairs) > most else "")


__all__ = ["renamed_pairs", "rename_edits", "shown_pairs"]
