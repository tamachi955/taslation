"""Names a book's translation renders in more than one way ("Ryuji" on one page, "Ryūji" or "Ryuuji" on another),
found without a model and without guessing (`find_variants`), and put right on the lines that hold them
(`unify_text`).

A name is found where the Japanese marks it as one: a katakana word, or two to four kanji, right before an honorific
(さん, ちゃん, くん, 君, さま, 様, 先輩, 先生, as the term check knows them: `terms.HONORIFICS`), on at least
`NAME_MIN_HONORIFIC` lines; the OCR's kana are folded as the term check folds them (`terms.fold_kana`). Every line whose
Japanese holds the name is then looked at in its translation: a capitalised word that comes mostly on those lines
(`ALONE_SHARE` of its lines), on two or more of them, is the name's rendering; another capitalised word that takes its
place - never on a line with it - is another rendering of the same name when it spells it nearly alike
(`ALIKE_RATIO`, or the same once long vowels are written one way: "Ryūji", "Ryuuji", "Ryuji") or comes on two or more
of the name's lines and on hardly any other (`OTHER_SHARE`). A word the translations also use in lower case is no
name ("Time", "Hide"); a name in kanji is rendered in romaji (`romaji_like`): "Queen" or "Boss" for a title before
an honorific is never taken for it; kinship words and titles before an honorific (ママ, 女王, 社長...) are no names
(`NOT_NAMES`); nor is a word that is the rendering of another name found. Scripts without capitals (Chinese,
Korean, Thai) give nothing. A wrong suggestion is worse than a missed one, so every gate leans to saying nothing.

Nothing here keeps or writes any text: the lines are the run's, in memory; the result holds the name as the Japanese
writes it (to show the reader in the window), its renderings and where each comes - never printed nor logged.
Standard library only."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, NamedTuple, Sequence

from .terms import FOLD_MIN_CHARS, HONORIFICS, fold_kana

NAME_MIN_HONORIFIC = 2  # lines with the name before an honorific: one is no pattern
NAME_MIN_LINES = 3  # lines with the name in all: fewer show no habit of the translation
RENDERING_MIN_LINES = 2  # the main rendering comes on at least this many of the name's lines
# of a rendering's lines, at least this share holds the name in the Japanese (a translation also names a character
# where the Japanese has "you" or no word at all: 0.7 for one name in the app's translation of OpenMantra)
ALONE_SHARE = 0.6
OTHER_SHARE = 0.9  # ... for another rendering that does not spell the main one alike
ALIKE_RATIO = 0.75  # difflib's ratio of two renderings, folded, that spell one name
MAIN_SHARE = 0.4  # the main rendering comes on at least this share of the name's lines that have any
CAPITALS_SHARE = 0.8  # letters in capitals from this share on: lettering set in capitals (every word looks a name)
KANJI_RUN = (2, 4)  # a name in kanji: this many characters before the honorific
_KATAKANA = "ァ-ヺー・"
_KANJI = "一-鿿々〆"
_TAIL_KATAKANA = re.compile(f"[{_KATAKANA}]+$")
_TAIL_KANJI = re.compile(f"[{_KANJI}]+$")
_WORD = re.compile(r"[^\W\d_]+")
# before an honorific, but no one's name: kinship, titles, forms of address
NOT_NAMES = frozenset({
    "ママ", "パパ", "マスター", "シスター", "ブラザー", "ボス", "ドクター", "ミスター", "ミセス", "ミス", "マダム",
    "レディ", "レディー", "ベイビー", "ベビー", "リーダー", "キャプテン", "コーチ", "オーナー", "ダーリン", "ハニー",
    "オジサン", "オバサン", "オジ", "オバ", "ジジイ", "ババア", "ニイ", "ネエ", "アニキ", "アネキ", "センセイ", "センパイ",
    "女王", "王女", "王子", "王妃", "皇子", "皇女", "魔王", "勇者", "聖女", "旦那", "主人", "社長", "部長", "課長",
    "店長", "会長", "校長", "隊長", "団長", "船長", "艦長", "院長", "所長", "局長", "署長", "組長", "総長", "番長",
    "師匠", "先輩", "後輩", "先生", "兄貴", "姉貴", "親父", "父上", "母上", "兄上", "姉上", "神父", "博士", "教授",
    "監督", "刑事", "警部", "主任", "大将", "殿下", "陛下", "閣下", "坊主", "坊や", "お嬢", "嬢ちゃん", "運転手",
    "看護師", "医者", "弁護士", "委員長", "生徒会長", "管理人", "大家", "店主", "女将", "女神", "天使", "悪魔",
})
# the honorifics' own words, and the titles a translation puts before a name: no rendering of the name
HONORIFIC_WORDS = frozenset(en for _ja, en in HONORIFICS)
TITLE_WORDS = frozenset({
    "mr", "mrs", "ms", "miss", "mister", "madam", "madame", "lady", "lord", "sir", "dame", "master", "mistress",
    "dr", "doctor", "professor", "prof", "teacher", "boss", "chief", "captain", "señor", "señora", "señorita", "don",
    "doña", "sra", "sr", "srta", "herr", "frau", "fräulein", "monsieur", "mademoiselle", "mme", "mlle", "signor",
    "signora", "signorina", "pan", "pani", "bay", "bayan", "hanım", "bey", "bapak", "ibu", "kak", "anh", "chị",
    "em", "ông", "bà", "senhor", "senhora", "meneer", "mevrouw", "господин", "госпожа",
})
NOT_RENDERINGS = HONORIFIC_WORDS | TITLE_WORDS


class RunLine(NamedTuple):
    """A line of a run: its Japanese (*source*, in memory only), its translation as stored (*text*) and where it is
    stored (*where*: the page's fingerprint and the bubble's box, for `cache.TextEdit`)."""

    source: str
    text: str
    where: Any = None


@dataclass
class NameVariants:
    """A name the translation renders in more than one way: as the Japanese writes it (*source*), each rendering with
    the lines that hold it (the main one first: the most lines), and the lines whose Japanese holds the name
    (indices into the lines looked at)."""

    source: str
    renderings: list[tuple[str, list[int]]] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)
    sheet: str = ""  # the series sheet's rendering of the name, when it has one

    def counts(self) -> list[tuple[str, int]]:
        return [(spelling, len(at)) for spelling, at in self.renderings]

    def to_change(self, chosen: str) -> int:
        """How many lines a choice of *chosen* changes: those holding another rendering."""
        key = _key(chosen)
        return len({i for spelling, at in self.renderings if _key(spelling) != key for i in at})


def _key(word: str) -> str:
    return unicodedata.normalize("NFC", word).casefold()


def _plain(word: str) -> str:
    """*word* folded: no accents, lower case, long vowels written once ("Ryūji", "Ryuuji", "Ryuji", "Ryouji" -> ryuji)."""
    text = "".join(ch for ch in unicodedata.normalize("NFKD", word) if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"([aiueo])\1+", r"\1", text)
    return re.sub(r"ou", "o", re.sub(r"(?<=o)h(?![aiueo])", "", text))


def romaji_like(word: str) -> bool:
    """Whether *word* can be a Japanese name in romaji (Hepburn, with or without long vowels marked): "Nando",
    "Ryūji", "Shiruma", "Gen'ichi"; not "Queen", "Boss", "Majesty"."""
    text = "".join(ch for ch in unicodedata.normalize("NFKD", word) if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"['’\-]", "", text)
    if not text:
        return False
    i, n = 0, len(text)
    syllable = re.compile(r"(?:ky|gy|sh|ch|ny|hy|by|py|my|ry|ts|dz|j|[kgsztdnhbpmyrwfv])?[aiueo]")
    while i < n:
        ch = text[i]
        if ch == "n" and (i + 1 == n or text[i + 1] not in "aiueoy"):
            i += 1
            continue
        if i + 1 < n and ch == text[i + 1] and ch in "kstpgdbzjmrc":
            i += 1  # a doubled consonant (small tsu)
            continue
        if ch == "t" and text.startswith("ch", i + 1):
            i += 1
            continue
        if ch == "h" and i > 0 and text[i - 1] in "aiueo" and (i + 1 == n or text[i + 1] not in "aiueoy"):
            i += 1  # "oh" for a long o
            continue
        m = syllable.match(text, i)
        if m is None:
            return False
        i = m.end()
    return True


def _words(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in _WORD.finditer(text)]


def _capitalised(word: str) -> bool:
    return len(word) >= 2 and word[0].isupper() and (word[1:].islower() or word.isupper())


def _honorific_names(source: str) -> list[str]:
    """The names *source* puts right before an honorific (as it writes them)."""
    if not source:
        return []
    folded = fold_kana(source)
    names: list[str] = []
    for ja, _en in HONORIFICS:
        short = len(ja) < FOLD_MIN_CHARS
        for m in re.finditer(re.escape(ja if short else fold_kana(ja)), source if short else folded):
            head = source[:m.start()]
            kata = _TAIL_KATAKANA.search(head)
            kanji = _TAIL_KANJI.search(head)
            if kata is not None and len(kata.group().strip("・ー")) >= 2:
                name = kata.group().strip("・")
            elif kanji is not None and KANJI_RUN[0] <= len(kanji.group()) <= KANJI_RUN[1]:
                name = kanji.group()
            else:
                continue
            if name in NOT_NAMES or fold_kana(name) in {fold_kana(w) for w in NOT_NAMES}:
                continue
            names.append(name)
    return names


def _anchored(text: str, word_key: str) -> bool:
    """Whether *text* has the word *word_key* (a key: `_key`) with an honorific after a hyphen ("Nando-san") or a
    title before it ("Mr. Nando", "Señora Nando"): the translation of a name before an honorific."""
    for m in _WORD.finditer(text):
        if _key(m.group()) != word_key:
            continue
        after = text[m.end():m.end() + 12]
        hon = re.match(r"[-‐‑]([^\W\d_]+)", after)
        if hon is not None and _key(hon.group(1)) in HONORIFIC_WORDS:
            return True
        before = re.search(r"([^\W\d_]+)\.?\s+$", text[max(0, m.start() - 16):m.start()])
        if before is not None and _key(before.group(1)) in TITLE_WORDS:
            return True
    return False


def find_variants(lines: Sequence[RunLine], sheet: Any = None) -> list[NameVariants]:
    """The names *lines* render in more than one way (see the module's docstring), the ones on most lines first.
    *sheet*: the series sheet (`annotations.Glossary`), whose rendering of a name is named with it."""
    if not lines:
        return []
    folded = [fold_kana(line.source or "") for line in lines]
    words = [_words(line.text or "") for line in lines]
    letters = "".join(w for ws in words for w, _s, _e in ws)
    capitals = bool(letters) and sum(ch.isupper() for ch in letters) >= CAPITALS_SHARE * len(letters)
    lower: set[str] = set()  # words the translations use in lower case: no names
    for ws in words:
        lower.update(_key(w) for w, _s, _e in ws if w.islower())
    capital: list[dict[str, str]] = []  # per line: word key -> the spelling it has there
    for ws in words:
        capital.append({_key(w): w for w, _s, _e in ws if _capitalised(w)})
    lines_with: dict[str, set[int]] = defaultdict(set)
    for i, cap in enumerate(capital):
        for k in cap:
            lines_with[k].add(i)

    # the names, by their honorifics
    honorific_lines: dict[str, set[int]] = defaultdict(set)
    written: dict[str, Counter[str]] = defaultdict(Counter)
    for i, line in enumerate(lines):
        for name in _honorific_names(line.source or ""):
            key = fold_kana(name)
            honorific_lines[key].add(i)
            written[key][name] += 1
    keys = [k for k, at in honorific_lines.items() if len(at) >= NAME_MIN_HONORIFIC]
    # a name inside a longer one found too (樫戸 in 樫戸大和) keeps the lines of its own
    name_lines: dict[str, list[int]] = {}
    for key in keys:
        longer = [o for o in keys if o != key and key in o]
        at = [i for i, f in enumerate(folded) if key in f and not any(o in f for o in longer)]
        if len(at) >= NAME_MIN_LINES:
            name_lines[key] = at

    def candidates(key: str) -> tuple[dict[str, list[int]], set[str]]:
        """Words that render the name *key* on its lines that name no other (a line with two names says nothing
        of which word is whose): capitalised, no common word, no title, on its lines almost alone; and those of them
        the translation puts with an honorific or a title where the Japanese has the name with its honorific."""
        romaji = capitals or _TAIL_KANJI.fullmatch(key) is not None
        others = [o for o in name_lines if o != key and o not in key]
        evidence = [i for i in name_lines[key] if not any(o in folded[i] for o in others)]
        mine: dict[str, list[int]] = defaultdict(list)
        for i in evidence:
            for k in capital[i]:
                mine[k].append(i)
        out: dict[str, list[int]] = {}
        anchored: set[str] = set()
        for k, where in mine.items():
            if k in lower or k in NOT_RENDERINGS or len(k) < 2:
                continue
            if romaji and not romaji_like(k):
                continue
            if len(where) / max(1, len(lines_with[k])) < ALONE_SHARE:
                continue
            out[k] = where
            if any(i in honorific_lines[key] and _anchored(lines[i].text, k) for i in where):
                anchored.add(k)
        return out, anchored

    found: dict[str, tuple[str, dict[str, list[int]], set[str]]] = {}
    for key in name_lines:
        words_of, anchored = candidates(key)
        evidence = len({i for where in words_of.values() for i in where}) or 1
        fit = [k for k, where in words_of.items() if len(where) >= RENDERING_MIN_LINES]
        if anchored & set(fit):
            fit = [k for k in fit if k in anchored]  # the translation names it so with its honorific
        main = max(fit, key=lambda k: (len(words_of[k]), k), default=None)
        if main is not None and len(words_of[main]) >= MAIN_SHARE * evidence:
            found[key] = (main, words_of, anchored)
    mains = Counter(main for main, _w, _a in found.values())

    out: list[NameVariants] = []
    for key, (main, words_of, anchored) in found.items():
        if mains[main] > 1:
            continue  # one word the rendering of two names: neither can be told
        main_lines = set(words_of[main])
        others: list[str] = []
        for k, where in words_of.items():
            if k == main or k in mains or main_lines & set(where):
                continue  # the main one, another name's, or a word beside it (a second name, a place)
            pm, pk = _plain(main), _plain(k)
            if pk != pm and (pm.startswith(pk) or pk.startswith(pm)):
                continue  # a part of the name, or more than it: not the same rendering
            alike = pk == pm or SequenceMatcher(None, pk, pm, autojunk=False).ratio() >= ALIKE_RATIO
            alone = len(where) >= RENDERING_MIN_LINES and len(where) / max(1, len(lines_with[k])) >= OTHER_SHARE
            if alike or alone or k in anchored:
                others.append(k)
        if not others:
            continue

        def spelling(k: str) -> str:
            return Counter(capital[i][k] for i in lines_with[k]).most_common(1)[0][0]

        at_name = set(name_lines[key])
        renderings = sorted([(spelling(k), sorted(lines_with[k] & at_name)) for k in [main, *others]],
                            key=lambda r: (-len(r[1]), r[0]))
        source = written[key].most_common(1)[0][0]
        out.append(NameVariants(source=source, renderings=renderings, lines=list(name_lines[key]),
                                sheet=_sheet_rendering(sheet, source)))
    out.sort(key=lambda v: (-len(v.lines), v.source))
    return out


def _sheet_rendering(sheet: Any, source: str) -> str:
    if sheet is None:
        return ""
    try:
        character = sheet.get_character(source)
    except Exception:  # noqa: BLE001 - a sheet of another shape: nothing to name
        return ""
    return str(getattr(character, "rendering", "") or "").strip() if character is not None else ""


def unify_text(text: str, olds: Sequence[str], new: str) -> str:
    """*text* with each whole word of *olds* (any case: "RYUJI" in lettering set in capitals stays in capitals) put as
    *new*; a word with an honorific after a hyphen ("Ryuji-san") or a possessive ("Ryuji's") is one too."""
    new = new.strip()
    if not new:
        return text
    for old in olds:
        if not old or _key(old) == _key(new):
            continue

        def put(m: re.Match[str]) -> str:
            found = m.group()
            return new.upper() if found.isupper() and len(found) > 1 else new

        text = re.sub(r"(?<![^\W\d_])" + re.escape(old) + r"(?![^\W\d_])", put, text, flags=re.IGNORECASE)
    return text


def changes(variants: NameVariants, lines: Sequence[RunLine], chosen: str) -> list[tuple[RunLine, str]]:
    """(the line, its new text) for each line of the name's that a choice of *chosen* changes."""
    olds = [spelling for spelling, _at in variants.renderings if _key(spelling) != _key(chosen)]
    out: list[tuple[RunLine, str]] = []
    for i in sorted({i for spelling, at in variants.renderings if _key(spelling) != _key(chosen) for i in at}):
        line = lines[i]
        new = unify_text(line.text, olds, chosen)
        if new != line.text:
            out.append((line, new))
    return out


__all__ = ["NameVariants", "RunLine", "changes", "find_variants", "romaji_like", "unify_text"]
