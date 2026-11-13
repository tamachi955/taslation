"""Names held fixed through a book: the rendering a name got once is the one it keeps.

A small model renders a name from scratch on every line it meets it on, and not always alike: "Ryūji" here, "Ryuji"
there, a reading of the kanji on one page and another on the next. The series sheet settles this where the reader
wrote the name down (`terms._sheet_hits`, the PLaMo translator's glossary). For the names the sheet does not have,
the book's own lines say which words are names and the translations say how each was rendered, and from then on every
line that names one carries that rendering in its glossary (PLaMo's ``glossary`` field; for the chat translator the
lines after the bubbles that the sheet's cut entries use).

What counts as a name is never the model's guess. A word is a name when the book shows it:

* right before an honorific, as the name helper finds one (`name_variants._honorific_names`, the app's one test of a
  name: a katakana word, or two to four kanji, before an honorific of `terms.HONORIFICS`, no kinship word or title),
  and rendered with that honorific in the translation ("Yuzuha-san" for 柚葉さん): the word before the hyphen is the
  rendering. A name in kanji the line renders two ways with its honorific goes unrecorded (which is whose is not
  known); a name in katakana is then the form that reads as its kana;
* with its reading in brackets (芦藤（あしふじ）): the reading romanised ("Ashifuji").

The first rendering a name gets is the one held (a reading in brackets outranks it); the sheet's entries outrank
both. Nothing here is written to the series sheet: the reader adds a name to the sheet through the window (the
names a run rendered two ways, `name_variants.find_variants`; the sheet's own dialog; a rendering offered after an
edit, `ui.translator._propose_renderings`). Nothing here is printed or logged.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from typing import Any, Iterable, Sequence

from ..annotations import Glossary, Premises
from ..terms import FOLD_MIN_CHARS, HONORIFICS, find_term, fold_kana

KEPT_NAMES = 2000  # the most names a book keeps (then it keeps what it has)
_BRACKETED = re.compile(r"([一-鿿][一-鿿々]{0,5})[（(]([ぁ-ゖァ-ヺー]{1,12})[）)]")
_WORD = r"[A-ZÀ-ÖØ-Þ][\w'’]*"
_KATAKANA = re.compile(r"[ァ-ヺー・]+")


def romaji(kana: str) -> str:
    """Hepburn romaji of *kana* as a name is written in English: no long-vowel mark, a small tsu doubling the next
    consonant (at the end: nothing), lowercase."""
    import jaconv

    latin = jaconv.kana2alphabet(jaconv.kata2hira(kana.replace("・", "")))
    return latin.replace("xtsu", "").replace("-", "").lower()


def fold_latin(text: str) -> str:
    """A rendering compared loosely: accents off, letters only, lowercase, no letter twice in a row, no h after a
    consonant or at the end (Shiruma / Siruma, Ryūji / Ryuji, Sakyōmaru / Sakyoumaru stay apart only by their letters)."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text.lower()) if "a" <= ch <= "z")
    plain = re.sub(r"(?<=[^aeiou])h|h$", "", plain)
    plain = re.sub(r"ou", "o", plain)
    return re.sub(r"(.)\1+", r"\1", plain)


def reads_as(kana: str, rendering: str) -> bool:
    """Whether *rendering* is a romanisation of *kana* (`fold_latin` on both sides)."""
    r = romaji(kana)
    return bool(r) and fold_latin(r) == fold_latin(rendering)


def _honorific_forms(translation: str, honorific: str) -> list[str]:
    """The capitalised words the translation writes with the honorific *honorific* after a hyphen: "Tsubana" for
    "Tsubana-san"."""
    return re.findall(rf"(?<![\w'’-])({_WORD})-{re.escape(honorific)}\b", translation)


def honorific_names(source: str, translation: str) -> list[tuple[str, str]]:
    """(the name as *source* writes it, its rendering in *translation*) for each name *source* puts before an
    honorific (`name_variants._honorific_names`) that the translation renders with the same honorific (see the
    module's docstring)."""
    from ..name_variants import _honorific_names  # the name helper's test of a name (it imports terms, as this does)

    out: list[tuple[str, str]] = []
    folded = fold_kana(source)
    for name in dict.fromkeys(_honorific_names(source)):
        forms: list[str] = []
        for ja_hon, en_hon in HONORIFICS:
            if name + ja_hon in source or (len(ja_hon) >= FOLD_MIN_CHARS and fold_kana(name + ja_hon) in folded):
                forms += [f for f in dict.fromkeys(_honorific_forms(translation, en_hon)) if f not in forms]
        if len(forms) == 1:
            picked = forms[0]
        elif _KATAKANA.fullmatch(name):
            picked = next((f for f in forms if reads_as(name, f)), "")
        else:
            picked = ""
        if picked and (name, picked) not in out:
            out.append((name, picked))
    return out


def bracketed_readings(source: str) -> list[tuple[str, str]]:
    """(kanji, the rendering of its reading) for each word with its reading in brackets: 芦藤（あしふじ） -> ("芦藤",
    "Ashifuji")."""
    out = []
    for m in _BRACKETED.finditer(source):
        latin = romaji(m.group(2))
        if latin:
            out.append((m.group(1), latin[0].upper() + latin[1:]))
    return out


class BookNames:
    """The names of the book being translated, as its lines show them, each with the rendering it keeps: the first
    one its translations gave (`learn`), a reading in brackets before any. Memory only; the pipeline makes one per
    book (`Pipeline.reset_context`). Safe to share between threads."""

    def __init__(self) -> None:
        self._held: dict[str, str] = {}  # name -> the rendering it keeps
        self._from_reading: set[str] = set()  # the names whose rendering is their reading in brackets
        self._learnt: set[tuple[str, str]] = set()  # (source, translation) pairs learnt from already
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._held)

    def __bool__(self) -> bool:
        return True  # an empty memory is a memory still

    @property
    def held(self) -> dict[str, str]:
        """A copy of what is held: name -> rendering."""
        with self._lock:
            return dict(self._held)

    def clear(self) -> None:
        with self._lock:
            self._held.clear()
            self._from_reading.clear()
            self._learnt.clear()

    def learn(self, source: str, translation: str) -> None:
        """What the line *source* and its *translation* show: the names given a reading in brackets, and the names
        with an honorific rendered with it; a name already held keeps its rendering."""
        source, translation = str(source or ""), str(translation or "")
        if not source or not translation:
            return
        with self._lock:
            if (source, translation) in self._learnt or len(self._held) >= KEPT_NAMES:
                return
            self._learnt.add((source, translation))
            for name, rendering in bracketed_readings(source):
                if name not in self._from_reading:
                    self._held[name] = rendering
                    self._from_reading.add(name)
            for name, rendering in honorific_names(source, translation):
                self._held.setdefault(name, rendering)

    def glossary(self, source: str, skip: Sequence[str] = ()) -> list[tuple[str, str]]:
        """(name as *source* writes it, the rendering it keeps) for every name held that *source* names, the longer
        names first, none inside another one found or inside one of *skip* (what the series sheet gives already)."""
        with self._lock:
            held = sorted(self._held.items(), key=lambda kv: -len(kv[0]))
        out: list[tuple[str, str]] = []
        spans: list[tuple[int, int]] = [(at, at + len(s)) for s in skip if s for at in [find_term(s, source)] if at >= 0]
        for name, rendering in held:
            at = find_term(name, source)
            if at < 0 or any(a <= at and at + len(name) <= b for a, b in spans):
                continue
            spans.append((at, at + len(name)))
            out.append((source[at:at + len(name)] or name, rendering))
        return out


class NamedPremises(Premises):
    """The premises (`annotations.Premises`: the sheet's text and the sheet) with the book's names held so far
    (`BookNames`), which the translators add to each line's glossary and learn from."""

    names: BookNames | None

    def __new__(cls, text: str, sheet: Glossary | None = None, names: BookNames | None = None) -> "NamedPremises":
        self = super().__new__(cls, text, sheet)
        self.names = names
        return self


def names_of(notes: Any) -> BookNames | None:
    """The book's names the premises *notes* carry (`NamedPremises`), or None."""
    return getattr(notes, "names", None)


def learn(notes: Any, pairs: Iterable[tuple[str, str]]) -> None:
    """The book's names (when *notes* carry them) learn from the (source, translation) *pairs*."""
    names = names_of(notes)
    if names is not None:
        for source, translation in pairs:
            names.learn(source, translation)
