"""Translations worth a second look, and renderings the reader changed by hand.

The flags need no judgement to set and no model, so they are set for every translation and stored with it: the
reader can go straight to the lines where the model was most likely wrong instead of reading everything. (The flag
"revised", for a line the model's own revision changed much, went with that revision on 2026-11-06; a cache that has
it still shows it, by its code.) A rendering the
reader replaced in a translation (a name spelt another way, a term in other words) is offered back as the
series sheet's new rendering, so one correction carries to the rest of the book.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any

from .annotations import Glossary
from .config import Settings
from .render.lettering import strip_marks
from .terms import contains_rendering, required_renderings, term_misses

REASONS = {
    "small": "set under the readable size",
    "rendering": "misses a rendering from the series sheet",
    "long": "far longer than the Japanese",
    "short": "far shorter than the Japanese",
    "ocr": "TASlation may have misread the Japanese",
    "spelling": "has a word the dictionary does not know",
}
# target languages with a word list in the optional pyspellchecker package (offline, MIT)
SPELL_LANGUAGES = {"english": "en", "spanish": "es", "french": "fr", "portuguese": "pt", "german": "de", "italian": "it",
                   "russian": "ru", "dutch": "nl"}
LONG_RATIO = 3.0  # characters of translation per Japanese character beyond which a line is suspect
LONG_EXTRA = 20  # characters of slack at every length (short Japanese lines take long English ones)
SHORT_RATIO = 0.4
OCR_UNSURE = 0.8  # the region's confidence under which a reading is suspect (gold set: mean CER 24 % under it, 6 % at most above); also where the readers split
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


def reason_label(code: str, language: str | None = None) -> str:
    """The reason *code* (a key of REASONS) as the window says it: in the window's language, or in
    *language* (a code of `i18n.UI_LANGUAGES`); the English of REASONS are the catalogs' keys
    (locales/features/review_reasons.py). A code it does not know is given as it is."""
    from .i18n import CATALOGS, current

    english = REASONS.get(code)
    if english is None:
        return code
    return CATALOGS.get(language or current(), {}).get(english, english)


@functools.lru_cache(maxsize=8)
def spell_checker(language: str) -> Any:
    """A dictionary for *language* from the optional `pyspellchecker` package (word lists on disk, nothing
    online), or None when the package or the language is not there."""
    first = language.strip().lower().split()[0] if language.strip() else ""
    code = SPELL_LANGUAGES.get(first)
    if not code:
        return None
    try:
        from spellchecker import SpellChecker  # type: ignore

        return SpellChecker(language=code)
    except Exception:  # noqa: BLE001 - not installed, or no list for the language
        return None


def known_words(sheet: Glossary | None) -> set[str]:
    """The words of the series sheet's renderings and names: never spelling mistakes."""
    words: set[str] = set()
    if sheet is None:
        return words
    renderings = [e.rendering for e in sheet.entries] + [c.rendering for c in sheet.characters]
    renderings += [form for c in sheet.characters for form in c.addresses.values()]
    for r in renderings:
        words.update(w.lower() for w in _WORD.findall(r))
    return words


def misspelt(text: str, checker: Any, known: Iterable[str] = ()) -> list[str]:
    """The words of *text* the dictionary does not know: plain alphabetic words, compared in lower case; words
    with digits or apostrophes, capitals in mixed-case text (acronyms) and the *known* words are left alone."""
    skip = {w.lower() for w in known}
    out: list[str] = []
    candidates: list[str] = []
    all_caps = text == text.upper()  # scanlation-style capitals: every word is compared in lower case
    for w in _WORD.findall(strip_marks(text)):
        if not w.isalpha() or (w.isupper() and not all_caps) or w.lower() in skip:
            continue  # an acronym in mixed-case text, a word with digits, or a word of the sheet
        candidates.append(w)
    if not candidates:
        return out
    unknown = {str(u).lower() for u in checker.unknown([w.lower() for w in candidates])}
    for w in candidates:
        if w.lower() in unknown and w not in out:
            out.append(w)
    return out


def flags_for(ja: str, text: str, size: int, settings: Settings, sheet: Glossary | None = None, speaker: str = "",
              confidence: float = 1.0, checker: Any = None) -> list[str]:
    """The reasons a translation deserves a look (keys of REASONS), or none. *checker* is a dictionary (an
    object with `unknown(words)`) to use instead of the language's own."""
    flags: list[str] = []
    if not text:
        return flags
    if settings.readable_font_size and 0 < size < settings.readable_font_size:
        flags.append("small")
    if sheet is not None and term_misses(sheet, ja, text, speaker):
        flags.append("rendering")
    n_ja, n = len(ja.replace(" ", "")), len(text)
    if n > LONG_RATIO * n_ja + LONG_EXTRA:  # set from the gold English of OpenMantra: flags 0.8 % of professional lines
        flags.append("long")
    if n_ja >= 8 and n < SHORT_RATIO * n_ja:
        flags.append("short")
    if confidence < OCR_UNSURE:
        flags.append("ocr")
    if getattr(settings, "spellcheck", True):
        checker = checker if checker is not None else spell_checker(settings.target_language)
        if checker is not None and misspelt(text, checker, known_words(sheet)):
            flags.append("spelling")
    return flags


def _norm(word: str) -> str:
    return re.sub(r"['’]s$", "", word.lower())


def rendering_changes(sheet: Glossary | None, ja: str, old: str, new: str, speaker: str = "") -> list[tuple[str, str]]:
    """(rendering the sheet asks for, what the reader wrote in its place): the renderings *old* had that *new*
    lacks, where the words that replaced them can be told; nothing otherwise."""
    if sheet is None or not old or not new:
        return []
    changes: list[tuple[str, str]] = []
    ow, nw = _WORD.findall(old), _WORD.findall(new)
    for r in required_renderings(sheet, ja, speaker):
        if not contains_rendering(old, r) or contains_rendering(new, r):
            continue
        rw = [_norm(w) for w in _WORD.findall(r)]
        pos = next((i for i in range(len(ow) - len(rw) + 1) if [_norm(w) for w in ow[i:i + len(rw)]] == rw), -1)
        if pos < 0:
            continue
        repl = ""
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, [_norm(w) for w in ow], [_norm(w) for w in nw], autojunk=False).get_opcodes():
            if tag == "replace" and i1 == pos and i2 == pos + len(rw):  # exactly the rendering was replaced
                repl = " ".join(nw[j1:j2])
                break
        if repl and _norm(repl) != _norm(r) and len(repl.split()) <= 4 and (r, repl) not in changes:
            changes.append((r, repl))
    return changes


def sheet_item_for(sheet: Glossary, rendering: str) -> tuple[str, str] | None:
    """("term", the Japanese term) or ("character", the Japanese name) the sheet renders as *rendering*."""
    for e in sheet.entries:
        if e.rendering == rendering:
            return "term", e.term
    for c in sheet.characters:
        if c.rendering == rendering:
            return "character", c.name
    return None
