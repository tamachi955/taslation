"""The series sheet's renderings checked against each translation.

A small model follows the sheet most of the time but not always: a term comes back in other words or
capitalised as a title, a full name as a first name only, an honorific the sheet keeps as "Mr.". The sheet says
exactly what a Japanese term or name must become, so the check is plain string matching (uppercase lettering
passes, and a lowercase rendering may take a capital at the start of a sentence): a translation that misses a
rendering gets the review flag "rendering" (`term_misses`, `review.flags_for`); nothing is asked of the model again
(removed 2026-11-06). A translation that spells a rendering another way ("Ryuji" where the sheet says "Ryūji") is put
right without the model (`rendering_variants`, `rename_text`). Which entries a line names (`_sheet_hits`) is also the
PLaMo translator's glossary. Nothing here is printed.

A term of two or more characters is also found through a kana fold (`fold_kana`: small kana to large, katakana to
hiragana, on both sides, one character for one), because the OCR reads ピョ as ピヨ; there is no edit distance, which
would hit short names falsely, and the source is only ever compared, never changed. `cut_entries` gives what the
stable block of premises left out of a request's lines: the block has its limits and stays a stable prompt prefix,
so an entry late in a long sheet comes after the bubbles of the requests that need it.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import NamedTuple, Sequence

from .annotations import Glossary

HONORIFICS = (("さん", "san"), ("ちゃん", "chan"), ("くん", "kun"), ("君", "kun"), ("さま", "sama"), ("様", "sama"),
              ("先輩", "senpai"), ("せんぱい", "senpai"), ("先生", "sensei"), ("せんせい", "sensei"))
_SENTENCE_END = '.!?…。！？"“([\n'
FOLD_MIN_CHARS = 2  # a shorter term is matched exactly: one kana folded would hit everywhere
REQUEST_TERMS_CHARS = 900  # the most a request's lines add after its bubbles (`cut_entries`)
REQUEST_TERM_CHARS = 160  # an entry longer than this comes as its bare rendering
_KANA_FOLD = {code: code - 0x60 for code in range(0x30A1, 0x30F7)}  # katakana to hiragana (ァ..ヶ to ぁ..ゖ)
_KANA_FOLD |= {ord(small): ord(large) for small, large in zip("ぁぃぅぇぉっゃゅょゎゕゖ", "あいうえおつやゆよわかけ")}
_KANA_FOLD |= {ord(small): _KANA_FOLD[ord(large)] for small, large in zip("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")}


def fold_kana(text: str) -> str:
    """*text* with small kana made large and katakana made hiragana. One character stays one: positions hold."""
    return text.translate(_KANA_FOLD)


def find_term(term: str, source: str) -> int:
    """Where *term* stands in *source*, -1 when it does not: as written, or, from `FOLD_MIN_CHARS` characters on,
    through the kana fold."""
    if not term:
        return -1
    at = source.find(term)
    if at < 0 and len(term) >= FOLD_MIN_CHARS:
        at = fold_kana(source).find(fold_kana(term))
    return at


def occurs(term: str, source: str) -> bool:
    """*term* stands in *source* (`find_term`)."""
    return find_term(term, source) >= 0


def _usable(rendering: str) -> bool:
    r = rendering.strip()
    return len(r) >= 2 and "/" not in r  # "A / B" lists alternatives: guidance, not a rendering to insist on


def contains_rendering(text: str, rendering: str) -> bool:
    """*text* contains *rendering* as the sheet writes it. Uppercase lettering counts, and a lowercase rendering
    may start with a capital at the start of a sentence; "Magical Girls" in mid-sentence does not pass."""
    r = rendering.strip()
    if not r:
        return True
    if r in text:
        return True
    if text == text.upper() and r.upper() in text:
        return True
    if r[0].islower():
        cap = r[0].upper() + r[1:]
        start = 0
        while (i := text.find(cap, start)) >= 0:
            before = text[:i].rstrip()
            if not before or before[-1] in _SENTENCE_END:
                return True
            start = i + 1
    return False


def _strip_honorific(form: str) -> str:
    low = form.lower()
    for _ja, en in HONORIFICS:
        if low.endswith("-" + en):
            return form[: -(len(en) + 1)]
    return form


def name_words(glossary: Glossary) -> tuple[dict[str, str], bool]:
    """Japanese names and name parts -> the words that render them, as far as the sheet shows: full names, the
    forms characters use for each other (without their honorific), and the half of a full name whose other half
    the sheet knows. Keys the sheets disagree on are left out. Also whether the family name comes first in the
    renderings (assumed, unless a known part shows otherwise)."""
    words: dict[str, str] = {}
    disputed: set[str] = set()

    def put(ja: str, w: str) -> None:
        w = w.strip()
        if not ja or not w:
            return
        if ja in words and words[ja] != w:
            disputed.add(ja)
        words.setdefault(ja, w)

    for c in glossary.characters:
        put(c.name, c.rendering)
    names = {c.name for c in glossary.characters if c.rendering}
    for c in glossary.characters:
        for ja, form in c.addresses.items():
            if ja not in names:  # a full name keeps its own rendering; a speaker's form for it is their business
                put(ja, _strip_honorific(form))
    for ja in disputed:
        words.pop(ja, None)
    votes = 0
    pinned: list[tuple[str, str, str, bool]] = []  # (full name, known part, its word, the part is a suffix)
    for c in glossary.characters:
        ws = c.rendering.split()
        if len(ws) != 2 or c.name not in words:
            continue
        for ja, w in words.items():
            if ja == c.name or len(ja) >= len(c.name) or w not in ws:
                continue
            if c.name.endswith(ja):
                pinned.append((c.name, ja, w, True))
                votes += 1 if w == ws[-1] else -1
            elif c.name.startswith(ja):
                pinned.append((c.name, ja, w, False))
                votes += 1 if w == ws[0] else -1
    for name, part, w, suffix in pinned:
        other = name[: -len(part)] if suffix else name[len(part):]
        other_words = [x for x in words[name].split() if x != w]
        if other and len(other_words) == 1:
            put(other, other_words[0])
    return {ja: w for ja, w in words.items() if ja not in disputed}, votes >= 0


class _Hit(NamedTuple):
    """What the sheet says about a place in a line: *ja* (as the sheet writes it, never as the line does) stands
    from *at* to *end* and is rendered *rendering*; *name* is the pair (Japanese, rendering) a line of the premises
    must hold for the model to know this already; *entry* is the sheet's whole entry for it, or ""."""

    at: int
    end: int
    ja: str
    rendering: str
    name: tuple[str, str]
    entry: str = ""


def _ends_with(head: str, folded: str, name: str) -> bool:
    return head.endswith(name) or (len(name) >= FOLD_MIN_CHARS and folded.endswith(fold_kana(name)))


def _honorific_hits(glossary: Glossary, source: str, known: tuple[dict[str, str], bool] | None = None) -> list[_Hit]:
    """The names with an honorific in *source*, when the sheet keeps honorifics ("Kashido-san" for 樫戸さん: a name
    or part the sheet knows, or two or more characters from the start or the end of a full name with a two-word
    rendering, family name first unless the sheet shows otherwise). *known*:
    `name_words` of the sheet, when the caller has it."""
    if getattr(glossary.style, "honorifics", "") != "keep" or not source:
        return []
    folded = fold_kana(source)
    words, family_first = known if known is not None else name_words(glossary)
    by_length = sorted(words.items(), key=lambda kv: -len(kv[0]))
    hits: list[_Hit] = []
    for ja_hon, en_hon in HONORIFICS:
        short = len(ja_hon) < FOLD_MIN_CHARS  # 君, 様: no kana to fold
        for m in re.finditer(re.escape(ja_hon if short else fold_kana(ja_hon)), source if short else folded):
            head, fold_head = source[: m.start()], folded[: m.start()]
            part, word = next(((ja, w) for ja, w in by_length if _ends_with(head, fold_head, ja)), ("", ""))
            if not word:
                for c in glossary.characters:
                    ws = c.rendering.split()
                    if len(ws) != 2 or len(c.name) < 3:
                        continue
                    for k in range(2, len(c.name)):
                        if _ends_with(head, fold_head, c.name[:k]):
                            part, word = c.name[:k], ws[0] if family_first else ws[-1]
                        elif len(c.name) - k >= 2 and _ends_with(head, fold_head, c.name[k:]):
                            part, word = c.name[k:], ws[-1] if family_first else ws[0]
                    if word:
                        break
            if word:
                hits.append(_Hit(m.start() - len(part), m.end(), part + ja_hon, f"{word}-{en_hon}", (part, word)))
    return hits


def _sheet_hits(glossary: Glossary, source: str, speaker: str = "",
                known: tuple[dict[str, str], bool] | None = None) -> list[_Hit]:
    """What the sheet says about *source*, in the order of `required_renderings`: glossary terms; the forms the
    speaker uses (or, without a speaker, a form every character sheet agrees on); full names no such form covers;
    names with an honorific."""
    hits: list[_Hit] = []

    def hit(at: int, ja: str, rendering: str, entry: str = "") -> None:
        hits.append(_Hit(at, at + len(ja), ja, rendering, (ja, rendering), entry))

    for e in glossary.entries:
        at = find_term(e.term, source)
        if at >= 0 and e.rendering.strip():
            hit(at, e.term, e.rendering, f"- {e.term} = {e.rendering}" + (f" ({e.note})" if e.note else ""))
    speaker_sheet = glossary.get_character(speaker) if speaker else None
    sheets = [speaker_sheet] if speaker_sheet is not None else list(glossary.characters)
    forms: dict[str, set[str]] = {}
    for c in sheets:
        for ja, form in c.addresses.items():
            if occurs(ja, source):
                forms.setdefault(ja, set()).add(form)
    addressed = [ja for ja, fs in forms.items() if len(fs) == 1]
    for ja in addressed:
        hit(find_term(ja, source), ja, next(iter(forms[ja])))
    for c in glossary.characters:
        if c.name and c.rendering and c.name not in addressed:
            at = find_term(c.name, source)
            if at >= 0:
                hit(at, c.name, c.rendering, c.format())
    hits.extend(_honorific_hits(glossary, source, known))
    written = {(h.at, h.end) for h in hits if source[h.at:h.end] == h.ja}  # ヒャ as written is not ヒヤ folded
    return [h for h in hits if source[h.at:h.end] == h.ja or (h.at, h.end) not in written]


def required_renderings(glossary: Glossary | None, source: str, speaker: str = "") -> list[str]:
    """Renderings a translation of *source* must contain, by the sheet.

    Glossary terms written in the source; the form the speaker uses for someone they address (or, without a
    speaker, a form every character sheet agrees on); the full rendering of a character whose full name is
    written in the source and whom the speaker has no form for; and, when the sheet keeps honorifics, the name
    with its honorific. "Written in the source" tolerates the OCR's kana (`find_term`).
    """
    if glossary is None or not source:
        return []
    required: list[str] = []
    for hit in _sheet_hits(glossary, source, speaker):
        r = hit.rendering.strip()
        if _usable(r) and r not in required:
            required.append(r)
    return required


def cut_entries(glossary: Glossary | None, block: str, lines: Sequence[str], speakers: Sequence[str] = (),
                limit_chars: int = REQUEST_TERMS_CHARS) -> list[str]:
    """Lines for a request: what the sheet says about its Japanese *lines* (found as `required_renderings` finds
    it, and name parts the sheet knows) that the premises *block* does not, by first appearance, at most
    *limit_chars* in all. An entry is left out of *block* when no line of it holds both the Japanese and the
    rendering. Everything comes from the sheet, nothing from the lines."""
    if glossary is None or not any(lines):
        return []
    known = name_words(glossary)
    shown = block.splitlines()
    found: list[tuple[int, int, _Hit]] = []
    for i, source in enumerate(lines):
        if not source:
            continue
        hits = _sheet_hits(glossary, source, speakers[i] if i < len(speakers) else "", known)
        for ja, word in known[0].items():
            at = find_term(ja, source) if len(ja) >= FOLD_MIN_CHARS else -1
            end = at + len(ja)
            if at >= 0 and not any(o.at <= at and end <= o.end for o in hits):
                hits.append(_Hit(at, end, ja, word, (ja, word)))
        found.extend((i, h.at, h) for h in hits  # 樫戸 within 樫戸さん says nothing more
                     if not any(o.at <= h.at and h.end <= o.end and o.end - o.at > h.end - h.at for o in hits))
    out: list[str] = []
    seen: set[tuple[str, str]] = set()
    used = 0
    for _i, _at, h in sorted(found, key=lambda row: row[:2]):
        if (h.ja, h.rendering) in seen:
            continue
        seen.add((h.ja, h.rendering))
        if any(h.name[0] in line and h.name[1] in line for line in shown):
            continue
        bare = f"- {h.ja} = {h.rendering}"
        text = h.entry if h.entry and len(h.entry) <= REQUEST_TERM_CHARS and used + len(h.entry) < limit_chars else bare
        if used + len(text) + 1 > limit_chars:
            continue
        out.append(text)
        used += len(text) + 1
    return out


def term_misses(glossary: Glossary | None, source: str, text: str, speaker: str = "") -> list[str]:
    """The required renderings that *text* does not contain."""
    return [r for r in required_renderings(glossary, source, speaker) if not contains_rendering(text, r)]


VARIANT_RATIO = 0.8  # how alike (difflib's ratio, folded) a spelling must be to a rendering to be taken for it
_WORD_SPAN = re.compile(r"[^\W_][\w'’\-]*")
_POSSESSIVE = re.compile(r"['’]s$", re.I)


def _fold(text: str) -> str:
    """*text* compared loosely: accents off, case folded, no hyphens, apostrophes, dots or spaces."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return re.sub(r"[\s\-'’.]", "", plain.casefold())


def near_spelling(text: str, rendering: str, taken: Sequence[str] = ()) -> str:
    """The words of *text* that spell *rendering* another way ("Ryuji" for "Ryūji", "Tanka" for "Tanaka", "magic
    girl" for "magical girl"): as many words as the rendering has, alike to `VARIANT_RATIO` once folded (`_fold`),
    capitalised when it is, a possessive's "'s" left out, and none of the spellings *taken* (the sheet's other
    renderings: "Haruki" is not "Haruka" misspelt when both are characters). The rendering with an ending
    ("magical girls") or an honorific, or a part of it, is no other spelling. "" when there is none."""
    want = rendering.split()
    if not want or not text:
        return ""
    target, others = _fold(rendering), {_fold(t) for t in taken if t and t != rendering}
    spans = list(_WORD_SPAN.finditer(text))
    best, score = "", 0.0
    for i in range(len(spans) - len(want) + 1):
        span = _POSSESSIVE.sub("", text[spans[i].start():spans[i + len(want) - 1].end()])
        folded = _fold(span)
        if not folded or span == rendering or folded in others:
            continue
        if folded != target and (folded.startswith(target) or target.startswith(folded)):
            continue  # the rendering with an ending or an honorific, or a part of it: the model's to say
        if rendering[:1].isupper() and not span[:1].isupper():
            continue
        ratio = SequenceMatcher(None, folded, target, autojunk=False).ratio()
        if ratio >= VARIANT_RATIO and ratio > score:
            best, score = span, ratio
    return best


def rendering_variants(glossary: Glossary | None, source: str, text: str, speaker: str = "") -> list[tuple[str, str]]:
    """(the spelling in *text*, the rendering the sheet asks for) for each rendering *text* misses (`term_misses`)
    where it has a near spelling of it (`near_spelling`): what can be put right without asking the model."""
    misses = term_misses(glossary, source, text, speaker)
    if not misses or glossary is None:
        return []
    taken = [e.rendering for e in glossary.entries] + [c.rendering for c in glossary.characters]
    taken += [form for c in glossary.characters for form in c.addresses.values()]
    out: list[tuple[str, str]] = []
    for rendering in misses:
        spelt = near_spelling(text, rendering, taken)
        if spelt and (spelt, rendering) not in out:
            out.append((spelt, rendering))
    return out


def rename_text(text: str, pairs: Sequence[tuple[str, str]]) -> str:
    """*text* with each whole-word *old* of *pairs* replaced by its *new* (as `cache.BookCache.rename` does in every
    cached translation), an old spelling followed by a hyphen and a word left alone ("Tanaka-san" is not "Tanaka")."""
    for old, new in pairs:
        if old and new and old != new:
            text = re.sub(r"(?<![\wÀ-ɏ])" + re.escape(old) + r"(?![\wÀ-ɏ])(?!-\w)", new, text)
    return text
