"""Where a line may break, by language: between Thai words, at a word's hyphenation points, and not after a word that
leans on the next one.

Thai is written without spaces between its words (a space ends a phrase or a sentence), so a line may break only
where a word ends (`thai_cuts`, `thai_words`). The line-break iterator Windows itself has finds those places with its
Thai dictionary: ICU's, in ``icu.dll`` (Windows 10 version 1903 and later; ``icuuc.dll`` before), called through
ctypes. Where it is missing (another system, an older Windows) rules of this module's own stand in: never inside a
cluster of letters (`cluster_cuts`), that is never before a vowel sign, a tone mark or a vowel written after its
consonant, never after a vowel written before its consonant, never before the consonant that closes a syllable after
mai han-akat or mai taikhu, nor before a letter made silent; and never where the syllable surely goes on
(`_syllable_cuts`: a vowel's own อ or ย, a leading ห or อ, an initial cluster, a final consonant). Without the
dictionary a line may still break inside a word, but only between its syllables.

Hyphenation (`hyphen_points`) follows Liang's algorithm (F. M. Liang, "Word Hy-phen-a-tion by Com-put-er", Stanford,
1983; written here from that description) with the patterns of the hyph-utf8 project (`PATTERNS`) for the languages
whose patterns are under a permissive licence; the files in ``hyphenation/`` are kept as published, their headers
with them (the licences and sources in docs/THIRD_PARTY.md). Elsewhere rules of this module's own: any Cyrillic word
(Russian, Ukrainian: the Russian patterns are under the LPPL only) by its vowels, Turkish and Indonesian (their
patterns are under the LPPL and the GPL) by their syllables, which both languages divide by plain rules; Vietnamese
not at all, its words being single syllables. English, and a language without a rule here, is left to the
typesetter's own rule (`typeset.hyphen_points`).

`WEAK_WORDS` and `TITLES` list, per language, the short words that lean on the next one (articles, prepositions,
conjunctions: a line should not end on them) and the titles that go with a name after them; written for this project.
"""

from __future__ import annotations

import ctypes
import functools
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent / "hyphenation"

# --- languages ----------------------------------------------------------------------------------------------------

# Other names a target language may be given by (its first word in lower case, as `typeset._language` takes it)
ALIASES = {
    "en": "english", "de": "german", "deutsch": "german", "fr": "french", "français": "french", "francais": "french",
    "es": "spanish", "español": "spanish", "espanol": "spanish", "it": "italian", "italiano": "italian",
    "pt": "portuguese", "pt-br": "portuguese", "português": "portuguese", "portugues": "portuguese",
    "brazilian": "portuguese", "pl": "polish", "polski": "polish", "nl": "dutch", "nederlands": "dutch",
    "ru": "russian", "русский": "russian", "uk": "ukrainian", "українська": "ukrainian", "tr": "turkish",
    "türkçe": "turkish", "turkce": "turkish", "id": "indonesian", "bahasa": "indonesian", "vi": "vietnamese",
    "tiếng": "vietnamese", "th": "thai",
}


def language_key(language: str) -> str:
    """The name this module knows *language* by: its first word in lower case ("Portuguese (Brazil)": "portuguese"),
    or what that is another name for (`ALIASES`: "de", "Deutsch": "german"); "" for none."""
    words = language.strip().lower().split()
    first = words[0] if words else ""
    return ALIASES.get(first, first)


# --- hyphenation ----------------------------------------------------------------------------------------------------

# language -> (its file in hyphenation/, the fewest letters before a hyphen and after it, as the file asks)
PATTERNS: dict[str, tuple[str, int, int]] = {
    "german": ("hyph-de-1996.tex", 2, 2),  # MIT
    "french": ("hyph-fr.tex", 2, 2),  # MIT
    "spanish": ("hyph-es.tex", 2, 2),  # MIT
    "italian": ("hyph-it.tex", 2, 2),  # MIT (or the LPPL)
    "portuguese": ("hyph-pt.tex", 2, 3),  # BSD-3-Clause
    "polish": ("hyph-pl.tex", 2, 2),  # MIT (or a public-domain notice)
    "dutch": ("hyph-nl.tex", 2, 2),  # MIT
}
NO_HYPHENS = frozenset({"vietnamese"})  # languages whose words never take a hyphen
_TEX_GROUP = r"\\{}\s*\{{([^}}]*)\}}"


@functools.lru_cache(maxsize=None)
def _patterns(language: str) -> tuple[dict[str, bytes], int, dict[str, tuple[int, ...]]]:
    """*language*'s patterns: per string of letters (``.`` for a word's edge) the values between them, the longest
    string's length, and the exceptions (a word in lower case: where it takes a hyphen). Read once, on first use."""
    name = PATTERNS[language][0]
    text = (HERE / name).read_text(encoding="utf-8")
    body = "\n".join(line.split("%", 1)[0] for line in text.splitlines())  # the comments left out
    table: dict[str, bytes] = {}
    for group in re.finditer(_TEX_GROUP.format("patterns"), body):
        for item in group.group(1).split():
            letters = "".join(ch for ch in item if not ch.isdigit())
            if not letters or not all(ch.isalpha() or ch in ".'" for ch in letters):
                continue
            values = bytearray(len(letters) + 1)
            k = 0
            for ch in item:
                if ch.isdigit():
                    values[k] = int(ch)
                else:
                    k += 1
            table[letters] = bytes(values)
    exceptions: dict[str, tuple[int, ...]] = {}
    for group in re.finditer(_TEX_GROUP.format("hyphenation"), body):
        for item in group.group(1).split():
            parts = item.lower().split("-")
            if all(p.isalpha() for p in parts):
                at = 0
                points = []
                for part in parts[:-1]:
                    at += len(part)
                    points.append(at)
                exceptions["".join(parts)] = tuple(points)
    return table, max((len(k) for k in table), default=0), exceptions


def _lower(word: str) -> str:
    """*word* in lower case letter by letter, as long as it is (a capital that lowers to two characters kept)."""
    return "".join(low if len(low := ch.lower()) == 1 else ch for ch in word)


def _liang(word: str, language: str, head: int, edge: int) -> list[int]:
    """The points Liang's algorithm finds in *word* with *language*'s patterns: every pattern that matches a stretch
    of the word (its edges marked by dots) lays its values between the letters, the highest value wins, and an odd one
    is a point; none nearer the word's start than *head* letters (or the file's own least), nor its end than *edge*."""
    table, longest, exceptions = _patterns(language)
    _name, left, right = PATTERNS[language]
    low = _lower(word)
    n = len(low)
    first, last = max(head, left), n - max(edge, right)
    if low in exceptions:
        return [p for p in exceptions[low] if first <= p <= last]
    marked = f".{low}."
    size = len(marked)
    score = bytearray(size + 1)
    for i in range(size):
        for j in range(i + 1, min(size, i + longest) + 1):
            values = table.get(marked[i:j])
            if values is not None:
                for k, v in enumerate(values):
                    if v > score[i + k]:
                        score[i + k] = v
    return [p for p in range(first, last + 1) if score[p + 1] % 2]


_CYR_VOWELS = frozenset("аеёиоуыэюяіїєАЕЁИОУЫЭЮЯІЇЄ")
_CYR_SIGNS = frozenset("ьъЬЪ")  # the soft and the hard sign: they stay with the consonant before them


def _cyrillic(word: str, head: int, edge: int) -> list[int]:
    """Where a Cyrillic word (Russian, Ukrainian) may take a hyphen, by a rule of its vowels: once between each two
    vowel groups, before a lone consonant (ма-ма), after the first of several (сес-тра, чув-ство, пред-ставление), so
    that each side has a vowel and no consonant leaves the vowel after it but at a sign or й; never before ь, ъ or й
    (толь-ко, вой-на, объ-езд, май-ор), and never nearer the word's start than *head* letters nor its end than
    *edge*."""
    low = _lower(word)
    n = len(low)
    vowel = [c in _CYR_VOWELS for c in low]
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
        if j < k < n:  # consonants (and signs) between two vowel groups
            consonants = [q for q in range(j, k) if low[q] not in _CYR_SIGNS]
            if len(consonants) >= 2:
                cut = consonants[0] + 1
                while cut < k and low[cut] in _CYR_SIGNS:
                    cut += 1
            elif consonants and low[consonants[0]] != "й" and k - j == 1:
                cut = j  # one consonant: it goes with the vowel after it
            else:
                cut = k  # й, or a consonant with its sign, stays with the vowel before
            if head <= cut <= n - edge and low[cut] not in "ьъй":
                points.append(cut)
        i = k
    return points


_TR_VOWELS = frozenset("aeıioöuüâîûAEIİOÖUÜÂÎÛ")


def _turkish(word: str, head: int, edge: int) -> list[int]:
    """Where a Turkish word may take a hyphen: each syllable has one vowel and the consonant just before a vowel
    begins its syllable (ki-tap-lık, İs-tan-bul, Türk-çe, sa-at), never nearer the word's start than *head* letters nor
    its end than *edge*."""
    vowels = [i for i, c in enumerate(word) if c in _TR_VOWELS]
    points = []
    for a, b in zip(vowels, vowels[1:]):
        cut = b - 1 if b - a > 1 else b
        if head <= cut <= len(word) - edge:
            points.append(cut)
    return points


_ID_VOWELS = frozenset("aeiou")
_ID_DIGRAPHS = ("ng", "ny", "sy", "kh")  # one consonant each: never parted
_ID_DIPHTHONGS = ("ai", "au", "ei", "oi")  # one vowel each: never parted


def _indonesian(word: str, head: int, edge: int) -> list[int]:
    """Where an Indonesian word may take a hyphen, by its syllables: two vowels side by side part but for a
    diphthong (ai, au, ei, oi), a lone consonant goes with the vowel after it, of two or more the first stays (ng, ny,
    sy, kh count as one): ber-sa-ma, me-nga-pa, sang-gup, in-stru-men, pe-nge-ta-hu-an; never nearer the word's start
    than *head* letters nor its end than *edge*."""
    low = _lower(word)
    n = len(low)
    units: list[tuple[int, bool]] = []  # (where it starts, a vowel)
    i = 0
    while i < n:
        pair = low[i:i + 2]
        if low[i] in _ID_VOWELS:
            units.append((i, True))
            i += 2 if pair in _ID_DIPHTHONGS else 1
        else:
            units.append((i, False))
            i += 2 if pair in _ID_DIGRAPHS else 1
    points = []
    vowels = [u for u, (_at, v) in enumerate(units) if v]
    for a, b in zip(vowels, vowels[1:]):
        between = b - a - 1
        cut = units[b][0] if between == 0 else units[a + 1][0] if between == 1 else units[a + 2][0]
        if head <= cut <= n - edge:
            points.append(cut)
    return points


def _script(word: str) -> str:
    """"latin" or "cyrillic" when every letter of *word* is of that script, else ""."""
    names = {unicodedata.name(ch, "").split(" ", 1)[0] for ch in word}
    if names == {"LATIN"}:
        return "latin"
    if names == {"CYRILLIC"}:
        return "cyrillic"
    return ""


@functools.lru_cache(maxsize=8192)
def hyphen_points(word: str, language: str, head: int = 2, edge: int = 3) -> tuple[int, ...] | None:
    """Where *word* (its letters only) may take a hyphen in *language* (a `language_key`), as offsets into it: by
    *language*'s patterns (`PATTERNS`, `_liang`), a rule of the language (Turkish, Indonesian; none in Vietnamese), or,
    for a Cyrillic word in any language, `_cyrillic`; never nearer the word's start than *head* letters nor its end
    than *edge*. None where there is no rule here for it (an English word, a Latin word in a language with no rule
    here, another script): the typesetter's own rule decides."""
    script = _script(word)
    if script == "cyrillic":
        return tuple(_cyrillic(word, head, edge))
    if script != "latin":
        return None
    if language in NO_HYPHENS:
        return ()
    if language in PATTERNS:
        return tuple(_liang(word, language, head, edge))
    if language == "turkish":
        return tuple(_turkish(word, head, edge))
    if language == "indonesian":
        return tuple(_indonesian(word, head, edge))
    return None


# --- Thai -----------------------------------------------------------------------------------------------------------

USE_NATIVE = True  # Thai words found by Windows' own break iterator where it has one (False: `_syllable_cuts` always)
_UBRK_LINE = 2
_ICU: Any = None  # the break iterator's library once looked for (False: there is none)


def _icu() -> Any:
    """Windows' ICU library with the line-break iterator's functions declared, from the system folder only; None
    where there is none (another system, a Windows before 10 version 1703)."""
    global _ICU
    if _ICU is None:
        _ICU = False
        if sys.platform == "win32":
            system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
            for name in ("icu.dll", "icuuc.dll"):
                try:
                    lib = ctypes.WinDLL(str(system / name))
                    lib.ubrk_open.restype = ctypes.c_void_p
                    lib.ubrk_open.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int32,
                                              ctypes.POINTER(ctypes.c_int)]
                    lib.ubrk_first.restype = ctypes.c_int32
                    lib.ubrk_first.argtypes = [ctypes.c_void_p]
                    lib.ubrk_next.restype = ctypes.c_int32
                    lib.ubrk_next.argtypes = [ctypes.c_void_p]
                    lib.ubrk_close.restype = None
                    lib.ubrk_close.argtypes = [ctypes.c_void_p]
                except (OSError, AttributeError):
                    continue
                _ICU = lib
                break
    return _ICU or None


def native_available() -> bool:
    """Whether Windows' own break iterator is there to find Thai words (`thai_cuts`)."""
    return _icu() is not None


def _icu_cuts(text: str) -> list[int] | None:
    """Where ICU's line-break iterator, with its Thai dictionary, lets a line of *text* break (offsets into it, the
    end left out); None when it cannot be asked."""
    lib = _icu()
    if lib is None or not text:
        return None
    data = text.encode("utf-16-le")
    units = len(data) // 2
    buffer = ctypes.create_string_buffer(data, len(data) + 2)  # kept alive while the iterator reads it
    status = ctypes.c_int(0)
    try:
        it = lib.ubrk_open(_UBRK_LINE, b"th", buffer, units, ctypes.byref(status))
    except OSError:
        return None
    if not it or status.value > 0:  # (a value under 0 is a warning: the root locale's rules, which hold the Thai)
        return None
    cuts: list[int] = []
    try:
        lib.ubrk_first(it)
        while True:
            at = lib.ubrk_next(it)
            if at <= 0 or at >= units:
                break
            cuts.append(at)
    finally:
        lib.ubrk_close(it)
    if units != len(text):  # a character beyond the Basic Multilingual Plane takes two UTF-16 units
        index: dict[int, int] = {}
        unit = 0
        for i, ch in enumerate(text):
            index[unit] = i
            unit += 2 if ord(ch) > 0xFFFF else 1
        cuts = [index[c] for c in cuts if c in index]
    return cuts


_LEADING = frozenset("\u0e40\u0e41\u0e42\u0e43\u0e44")  # เ แ โ ใ ไ: written before the consonant they follow
_TRAILING = frozenset("\u0e30\u0e32\u0e33\u0e45\u0e2f\u0e46")  # ะ า ำ ๅ ฯ ๆ: written after it; never a line's start
_CLOSES_AFTER = frozenset("\u0e31\u0e47")  # ั ็: the consonant after them closes the syllable
_TONES = frozenset("\u0e48\u0e49\u0e4a\u0e4b")  # ่ ้ ๊ ๋
_SILENT = "\u0e4c"  # ์: the letter under it is silent, the end of the syllable before
_CLOSING = frozenset(",.;:!?…)]}»”’\"'%")
_OPENING = frozenset("([{«“‘")


def _thai(ch: str) -> bool:
    return "\u0e00" <= ch <= "\u0e7f"


def cluster_cuts(text: str) -> list[int]:
    """Where a line of Thai *text* may break without a dictionary: after a space, and between two clusters of letters
    (see the module's notes), never inside a run of other letters or digits, before closing punctuation or after
    opening punctuation."""
    cuts = []
    n = len(text)
    for p in range(1, n):
        a, b = text[p - 1], text[p]
        if b == " ":
            continue
        if a == " ":
            cuts.append(p)
            continue
        if unicodedata.category(b) == "Mn" or b in _TRAILING or a in _LEADING:
            continue
        if b in _CLOSING or a in _OPENING or not (_thai(a) or _thai(b)) or (a.isdigit() and b.isdigit()):
            continue
        q = p - 1
        while q > 0 and text[q] in _TONES:
            q -= 1
        if text[q] in _CLOSES_AFTER:
            continue
        r = p + 1
        if r < n and unicodedata.category(text[r]) == "Mn" and text[r] != _SILENT:
            r += 1
        if r < n and text[r] == _SILENT:
            continue
        cuts.append(p)
    return cuts


_VOWELS_BEFORE_FINAL = frozenset("าิีึืุู")  # า ิ ี ึ ื ุ ู: a final may follow
_INITIAL_MARKS = frozenset("ะาำๅัิีึืุู็"
                           "่้๊๋")  # a consonant with one of these after it begins a syllable
_LED_BY_H = frozenset("งญนมยรลว")  # low consonants a silent ห leads (หมา, หรือ, ไหน)
_CLUSTER_FIRST = frozenset("กขคตปพผบดจทศส")  # with ร ล ว after them, an initial cluster (กร, ปล, คว, จริง, ทราบ)


def _consonant(ch: str) -> bool:
    return "ก" <= ch <= "ฮ"


def _syllable_cuts(text: str) -> list[int]:
    """`cluster_cuts` less the places that are surely inside a syllable: before the อ or ย that belongs to a vowel
    (มือ, เธอ, เรียน), between a leading ห or อ and the consonant it leads (หมาย, อย่าง), inside an initial cluster
    (ประตู), and before a consonant that closes the syllable before it (หมาย, ทุกคน: one with no vowel of its own after
    it, after a vowel that takes a final, or ending a word). What stands in for the dictionary where Windows' is missing;
    between two syllables it still cannot tell whether they make one word."""
    n = len(text)
    out = []
    for p in cluster_cuts(text):
        a, b = text[p - 1], text[p]
        nxt = text[p + 1] if p + 1 < n else ""
        if not _consonant(b):
            out.append(p)
            continue
        q = p - 1
        while q > 0 and text[q] in _TONES:
            q -= 1
        before = text[q]
        led = q >= 1 and text[q - 1] == "เ" or q >= 2 and text[q - 2] == "เ" and before in "รลว"
        if b == "อ" and (before == "ื" or _consonant(before) and led):
            continue  # -ือ, เ-อ (เธอ, เพลอ)
        if b == "ย" and before == "ี" and "เ" in text[max(0, q - 3):q]:
            continue  # เ-ีย
        if (a == "ห" and b in _LED_BY_H) or (a == "อ" and b == "ย"):
            continue
        if b == "อ" and _consonant(before) and nxt not in _INITIAL_MARKS:
            continue  # the vowel อ after a bare consonant (ลอง, ห้อง)
        initial = nxt in _INITIAL_MARKS or (b in _CLUSTER_FIRST and nxt in "รลว" and p + 2 < n
                                            and text[p + 2] in _INITIAL_MARKS)
        if a in _CLUSTER_FIRST and b in "รลว" and initial:
            continue
        r = q - 1
        while r > 0 and text[r] in _TONES:
            r -= 1
        vowel_before = (before in _VOWELS_BEFORE_FINAL or before == "อ" and r >= 0 and _consonant(text[r])
                        or q >= 1 and text[q - 1] in _LEADING
                        or q >= 2 and text[q - 2] in _LEADING and before in "รลว")
        after = text[p + 2] if p + 2 < n else ""
        next_begins = (not nxt or nxt == " " or not _thai(nxt) or nxt in _LEADING
                       or _consonant(nxt) and (not after or after == " " or after in _INITIAL_MARKS))
        # a consonant that closes a syllable itself (โรง) leaves none to close
        closing = r >= 0 and (text[r] in _VOWELS_BEFORE_FINAL or text[r] in _CLOSES_AFTER
                              or r >= 1 and text[r - 1] in _LEADING and _consonant(text[r]))
        if not initial and (vowel_before or _consonant(a) and not closing and next_begins):
            continue  # a final consonant: after a vowel that takes one, or after a bare consonant before a syllable
        out.append(p)
    return out


@functools.lru_cache(maxsize=4096)
def _cuts(text: str, native: bool) -> tuple[int, ...]:
    found = _icu_cuts(text) if native else None
    return tuple(found if found is not None else _syllable_cuts(text))


def thai_cuts(text: str) -> tuple[int, ...]:
    """Where a line of Thai *text* may break (offsets into it, neither 0 nor its end): between its words, as Windows'
    break iterator finds them (`_icu_cuts`), or where it is missing (or `USE_NATIVE` is off) between syllables as a
    rule tells them (`_syllable_cuts`). A space stays with what is before it."""
    return _cuts(text, USE_NATIVE)


def thai_words(text: str) -> list[str]:
    """A Thai paragraph as the words a line may break between (`thai_cuts`): joined they give the paragraph, its runs
    of spaces folded into one and none at its ends; a space is kept at the start of the word after it (" แต่"), which
    a line starting there leaves out."""
    text = re.sub(" +", " ", text).strip(" ")  # (spaces only: a no-break space stays inside its word)
    cuts = thai_cuts(text)
    words: list[str] = []
    spaced = False
    for a, b in zip((0, *cuts), (*cuts, len(text))):
        part = text[a:b]
        core = part.strip(" ")
        if core:
            words.append((" " if spaced and words else "") + core)
            spaced = part.endswith(" ")
        else:
            spaced = True
    return words


# --- words that lean on the next one, titles --------------------------------------------------------------------------

def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


WEAK_WORDS: dict[str, frozenset[str]] = {
    "german": _words("""der die das den dem des ein eine einen einem einer eines an auf aus bei bis durch für gegen
        hinter im ins mit nach neben ohne seit über um unter von vom vor zu zum zur zwischen und oder aber dass weil
        wenn ob"""),
    "french": _words("""le la les un une des du au aux de à en dans sur sous par pour avec sans chez vers entre et ou
        mais car donc ni que si mon ma mes ton ta tes son sa ses notre votre leur leurs ce cet cette ces"""),
    "spanish": _words("""el la los las un una unos unas del al de a en con por para sin sobre entre hacia desde hasta
        y e o u ni pero que si mi mis tu tus su sus"""),
    "italian": _words("""il lo la i gli le un uno una di a da in con su per tra fra del dello della dei degli delle al
        allo alla ai agli alle dal dalla dai nel nello nella nei negli nelle sul sulla sui e ed o ma che se mio mia
        tuo tua suo sua"""),
    "portuguese": _words("""o a os as um uma uns umas de do da dos das em no na num numa por pelo pela pelos pelas
        para com sem sobre entre ao aos à às e ou mas que se meu minha teu tua seu sua"""),
    "polish": _words("""w we z ze na do od o u za po przy przez dla bez nad pod przed i a ale lub albo czy że oraz
        bo"""),
    "dutch": _words("""de het een van in op aan met voor naar bij uit om tot door over onder tussen zonder en of
        maar dat mijn jouw ons onze hun"""),
    "russian": _words("""в во на с со к ко у о об от до по за из без для при про над под перед через между и а но да
        или что чтобы если как не ни"""),
    "ukrainian": _words("""в у з із зі на до від по за о об при про над під перед через між без для і й та а але чи
        що щоб якщо як не ні"""),
    "turkish": _words("ve veya ile ama fakat ancak çünkü eğer ki bir bu şu her"),
    "indonesian": _words("""di ke dari pada dalam untuk dengan oleh tentang kepada bagi yang dan atau tetapi tapi
        karena jika kalau bahwa si sang para sebuah seorang"""),
    "vietnamese": _words("của và với các những mọi một cho ở từ để khi nếu vì nhưng hoặc rằng trong trên dưới"),
}
TITLES: dict[str, frozenset[str]] = {
    "german": _words("herr frau dr. prof. doktor professor onkel tante könig königin prinz prinzessin kapitän"),
    "french": _words("""m. mme mme. mlle mlle. monsieur madame mademoiselle docteur professeur capitaine oncle tante
        roi reine prince princesse"""),
    "spanish": _words("""sr. sra. srta. señor señora señorita don doña doctor doctora profesor profesora capitán tío
        tía rey reina príncipe princesa"""),
    "italian": _words("""sig. sig.ra signor signore signora signorina dottor dottore dottoressa professor professore
        capitano zio zia re regina principe principessa"""),
    "portuguese": _words("""sr. sra. senhor senhora dona doutor doutora professor professora capitão tio tia rei
        rainha príncipe princesa"""),
    "polish": _words("pan pani panna dr. prof. doktor profesor kapitan wujek ciocia król królowa książę"),
    "dutch": _words("meneer mevrouw dhr. mevr. dr. prof. dokter professor kapitein oom tante koning koningin prins"),
    "russian": _words("господин госпожа доктор профессор капитан дядя тётя король королева принц принцесса"),
    "ukrainian": _words("пан пані доктор професор капітан дядько тітка король королева принц принцеса"),
    "indonesian": _words("pak bu bapak ibu tuan nyonya nona dokter profesor kapten paman bibi raja ratu pangeran"),
}
