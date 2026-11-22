"""Line reuse: a short line already translated in this book or its series is given the same translation again,
without asking the model (``reuse_lines``, on by default).

Why: the same exclamation, reply or name called out comes back page after page. Asked again, the model takes the
time of a request and may answer otherwise ("Huh?", "What?", "Eh?"). The page cache cannot help: it is keyed by the
page's fingerprint, so a new page is a new request for every line on it.

What is reused (`material`): a line of at most `MAX_CHARS` characters once normalised (`normalise`: Unicode NFKC,
no whitespace, runs of dots made one ellipsis, runs of the long-vowel mark, dashes and tildes made one long-vowel
mark, runs of ! and ? made one "!", "?" or "!?", a symbol written twice made one, a trailing full stop or comma
left out: only merges that change no reading; small kana, hiragana and katakana, and ! against ? stay apart). Never
a line whose sentence goes on in the next bubble or comes from the one before (the facts' ``continues``,
`translate.continuation`: a piece of a sentence is no line of its own), nor one with the reader's hint for the
model (a remark that holds for that bubble alone). The speaker and the kind the reader gave a line are part of its
key: a line said by someone else, or marked a thought, is another line. The rule was chosen on OpenMantra
(docs/OFFLINE_VERIFICATION.md, "Line reuse"): the repeats within a book are short lines; the professional translators
rendered a repeated line alike only half the time, but our model's fresh translation of one came no closer to theirs
than its first translation, a whole book at once or page by page, for any length or kind within `MAX_CHARS`. What reuse
risks is a first translation that misses coming back with the line, until a person corrects it once.

Where it is kept: in the book's cache file (`cache.BookCache.lines`, the ``lines`` field before its pages), sealed
with it (`protect.py`), so that everything a cache goes through - ``taslation cache list`` and ``delete``, the Saved
translations dialog, the encrypted export and import (`backup.py`), a rename of the book, uninstall - takes it too.
A line is found by its keyed hash alone: HMAC-SHA-256 of the key material (`KEY_VERSION`, the normalised line, the
speaker, the kind) with a random secret of the book's own (`SECRET_BYTES`, made with its first entry, kept in the same
file), cut to `DIGEST_BYTES`; per translator, model and target language (`scope`: another model or language never
reuses), the translation and whether a person wrote it. The Japanese is never written: the hash is all the file
holds of it. What that reveals, to whoever can open the file (its Windows user, or anyone with an export and its
passphrase): the translations (the cache holds them all already), how many short lines were kept, and - since the
secret is in the file - whether a line they guess was among them; a short exclamation is easy to guess, so the file
says which short lines the book has to someone who tries them. Without the secret (another book's file, another
book's secret) two hashes of one line cannot be told to be the same line.

The series: a book reuses its own lines first, then those of the other volumes of its series in the same language
(`series_lines`: the caches whose book's series sheet is the book's own, `notes.sheet_key` - the Series field, "Some
Title" for "Some Title 3" and for "Some Title 3巻" kept before the two fields, or the older key a sheet is still kept
under - letter case and spaces aside; read but never written); never another series'. A line a person corrected in
translator mode wins over the model's, in the book and across the series (`Entry.edited`, `SeriesLines.find`): the
editor's Save stores it (`remember_edit`), and later identical lines get it. A model's answer never replaces a
person's (`LineMemo.put`); "Translate again" asks the model for every line (`Plan`
with *serve* False) and replace the model's entries with the new answers; the editor's Ask again asks the model, and
its answer saved is a person's choice. Ctrl+Z on a change of translator mode takes back the lines it kept with the
rest of it (`LineMemo.state`, `LineMemo.carry`, with `ui.history`).

What is kept is the model's answer as the page got it: spelt as the series sheet spells (`terms.spelt_right`, which
both ways of translating apply to a fresh answer before it is set and kept). Before a kept translation is reused it
is held to the sheet as it is now (`held_to`): a near spelling of a rendering the line names is put right by the same
`terms.spelt_right`, and a translation that still misses a rendering the sheet asks for is not reused (the model is
asked, with the sheet's glossary): a sheet changed since never brings an old spelling back. A reused line goes
through the checks of any translation (`Pipeline.real_translation`, then the review's flags where it is set).

Within a request, a line that repeats an earlier one of the same request is not sent twice: it takes the first one's
answer (`Plan.copies`). The lines asked go out as one request without the reused ones, so a translator that carries
the request's own lines as history (PLaMo) does not see the reused pairs: measured page by page on OpenMantra, the
lines asked beside a reused one came out as without reuse. Nothing here talks to a model or prints a line; the
Japanese is held in memory only while a request is planned.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

KEY_VERSION = 1  # in every key: a change of `normalise` or of the key's parts is a new version, and nothing old matches
SECRET_BYTES = 32  # the book's random HMAC key
DIGEST_BYTES = 16  # the hash kept per line: 128 bits (two lines of one book never meet by chance)
# The longest line reused, in characters once normalised. On OpenMantra (docs/OFFLINE_VERIFICATION.md, "Line reuse")
# the repeats within a book were lines of up to 6 characters but one of 7-10, none longer; within 10, the model's
# fresh translation of a repeat came no closer to the professional one than its first (pooled -0.4 chrF, interval
# -3.3 to +2.5), and 3.5 % of the lines were reused
MAX_CHARS = 10
MAX_TEXT = 500  # a kept translation is at most this long (a longer one is no short line's)
MAX_SCOPE = 200  # characters of a scope's name
MAX_ENTRIES = 20000  # per memo: beyond it the oldest of the model's entries make room (a volume has some 2,000 lines)
MAX_RINGS = 8  # secrets a memo holds (its own, and those merged in by an import or a save of another process)
_HEX = re.compile(r"[0-9a-f]+")
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")  # tab and newline kept: a person's line breaks
_WORD = re.compile(r"[0-9A-Za-z぀-ヿ㐀-䶿一-鿿々]")
_DOTS = re.compile(r"(?:…|‥|\.{2,}|・{2,}|。{2,})+")  # (after NFKC: "…" is "...", "‥" is "..")
_PROLONG = re.compile(r"[ー―─—〜~]+")  # (after NFKC: "～" is "~")
_MARKS = re.compile(r"[!?]+")
_TWICE = re.compile(r"([♡♥♪☆★])\1+")
_TRAILING = "。、,."


def normalise(line: str) -> str:
    """*line* as it is keyed (see the module's docstring): NFKC, no whitespace, a run of dots one "…", a run of
    long-vowel marks, dashes and tildes one "ー", a run of ! and ? one "!", "?" or "!?", a symbol written twice once,
    no full stop or comma at the end."""
    t = "".join(unicodedata.normalize("NFKC", str(line or "")).split())
    t = _DOTS.sub("…", t)
    t = _PROLONG.sub("ー", t)
    t = _MARKS.sub(lambda m: "!?" if "!" in m.group(0) and "?" in m.group(0) else m.group(0)[0], t)
    t = _TWICE.sub(r"\1", t)
    return t.rstrip(_TRAILING)


def material(line: str, facts: dict[str, Any] | None = None, after_open: bool = False) -> str | None:
    """What a line is keyed by, or None when it is not reused: *line* `normalise`d, at most `MAX_CHARS` characters
    with a letter, kana or kanji in it, with the speaker and the kind of its *facts* (`regions.region_meta`, as the
    translator gets them); None for a line that ``continues`` in the next bubble, one that goes on from the bubble
    before (*after_open*: that one's facts say it continues), and one with a hint for the model (``note``)."""
    facts = facts or {}
    if after_open or facts.get("continues") or str(facts.get("note", "") or "").strip():
        return None
    norm = normalise(line)
    if not norm or len(norm) > MAX_CHARS or not _WORD.search(norm):
        return None
    speaker = " ".join(unicodedata.normalize("NFKC", str(facts.get("speaker", "") or "")).split())
    kind = str(facts.get("kind", "") or "").strip()
    return "\x1f".join((str(KEY_VERSION), norm, speaker, kind))


def materials(texts: Sequence[str], meta: Sequence[dict[str, Any] | None] | None) -> list[str | None]:
    """`material` of each of *texts* (in reading order) with its facts in *meta*; a line after one that continues is
    not reused."""
    facts = [dict((meta[i] or {}) if meta and i < len(meta) else {}) for i in range(len(texts))]
    return [material(t, facts[i], i > 0 and bool(facts[i - 1].get("continues"))) for i, t in enumerate(texts)]


def scope(translator: Any, language: str) -> str:
    """The translations a line may be reused from: those of the same translator (its kind, PLaMo or Ollama's chat)
    and model, into the same target language."""
    parts = (str(getattr(translator, "name", "") or ""), str(getattr(translator, "model", "") or ""),
             str(language or "").strip().lower())
    return "|".join(parts)[:MAX_SCOPE]


@dataclass
class Entry:
    """A kept translation: its text and whether a person wrote it (translator mode's editor), which wins."""

    text: str
    edited: bool = False

    def to_json(self) -> list[Any]:
        return [self.text, 1] if self.edited else [self.text]


def _entry(value: Any) -> Entry | None:
    """The entry a file holds as *value* ([text] or [text, 1]); None for anything else."""
    if not isinstance(value, list) or not value or not isinstance(value[0], str):
        return None
    text = _CONTROLS.sub("", value[0]).strip()[:MAX_TEXT]
    if not text:
        return None
    return Entry(text, len(value) > 1 and value[1] == 1)


@dataclass
class Ring:
    """One secret and the entries hashed with it: scope -> digest (hex) -> entry, oldest first."""

    secret: bytes
    scopes: dict[str, dict[str, Entry]] = field(default_factory=dict)

    def digest(self, key: str) -> str:
        mac = hmac.new(self.secret, key.encode("utf-8", "surrogatepass"), hashlib.sha256)
        return mac.hexdigest()[:2 * DIGEST_BYTES]

    def __len__(self) -> int:
        return sum(len(entries) for entries in self.scopes.values())


class LineMemo:
    """The kept lines of one book (`cache.BookCache.lines`): rings of entries (`Ring`), new entries in the first.
    *on_change* is called whenever an entry changes (the cache is then saved with its next save)."""

    def __init__(self, on_change: Callable[[], None] | None = None):
        self.rings: list[Ring] = []
        # what this process changed since its last save: (secret, scope, digest) -> the entry (None: taken out); a
        # merging save applies it on top of what the file holds (`take`)
        self.touched: dict[tuple[bytes, str, str], Entry | None] = {}
        self.on_change = on_change

    def __len__(self) -> int:
        return sum(len(ring) for ring in self.rings)

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def find(self, scope: str, key: str) -> Entry | None:
        """The entry of *key* (`material`) in *scope*: a person's first, from whichever ring holds it."""
        found: Entry | None = None
        for ring in self.rings:
            entry = ring.scopes.get(scope, {}).get(ring.digest(key))
            if entry is not None:
                if entry.edited:
                    return entry
                found = found or entry
        return found

    def put(self, scope: str, key: str, text: str, edited: bool = False) -> bool:
        """Keep *text* as the translation of *key* in *scope* (*edited*: a person's). A model's (not *edited*) never
        replaces a person's. Returns True when that changed anything."""
        text = _CONTROLS.sub("", str(text or "")).strip()[:MAX_TEXT]
        scope = scope[:MAX_SCOPE]
        if not text:
            return False
        held = self.find(scope, key)
        if held is not None and ((held.edited and not edited) or (held.text == text and held.edited == edited)):
            return False
        if not self.rings:
            self.rings.append(Ring(secrets.token_bytes(SECRET_BYTES)))
        for ring in self.rings[1:]:  # an older ring's entry of the line gives way to the new one
            digest = ring.digest(key)
            if ring.scopes.get(scope, {}).pop(digest, None) is not None:
                self.touched[(ring.secret, scope, digest)] = None
        ring = self.rings[0]
        entries = ring.scopes.setdefault(scope, {})
        digest = ring.digest(key)
        entries.pop(digest, None)  # (put last: the newest)
        entries[digest] = entry = Entry(text, edited)
        self.touched[(ring.secret, scope, digest)] = entry
        self._make_room(ring, scope)
        self._changed()
        return True

    def _make_room(self, ring: Ring, scope: str) -> None:
        """At most `MAX_ENTRIES` entries: the oldest of the model's go first."""
        excess = len(self) - MAX_ENTRIES
        entries = ring.scopes[scope]
        for digest in [d for d, e in entries.items() if not e.edited][:max(0, excess)]:
            del entries[digest]
            self.touched[(ring.secret, scope, digest)] = None

    def retext(self, change: Callable[[str], str]) -> int:
        """Every entry's text through *change* (the cache's renames and edits of its translations: `BookCache.rename`,
        `BookCache.put_texts`); returns how many changed."""
        changed = 0
        for ring in self.rings:
            for scope_name, entries in ring.scopes.items():
                for digest, entry in entries.items():
                    new = _CONTROLS.sub("", str(change(entry.text) or "")).strip()[:MAX_TEXT]
                    if new and new != entry.text:
                        entry.text = new
                        self.touched[(ring.secret, scope_name, digest)] = entry
                        changed += 1
        if changed:
            self._changed()
        return changed

    # --- translator mode's Undo ----------------------------------------------------------------------------------
    def state(self) -> dict[tuple[bytes, str, str], tuple[str, bool]]:
        """Every entry as it is now, (secret, scope, digest) -> (text, edited): a copy, kept with a change of
        translator mode (`ui.history.unit_states`) so that taking the change back takes back the line it kept."""
        return {(ring.secret, name, digest): (entry.text, entry.edited)
                for ring in self.rings for name, entries in ring.scopes.items() for digest, entry in entries.items()}

    def carry(self, frm: dict[tuple[bytes, str, str], tuple[str, bool]],
              to: dict[tuple[bytes, str, str], tuple[str, bool]]) -> bool:
        """The change from the state *frm* to the state *to* (`state`'s) made here, only for the entries that differ
        between the two (what came in meanwhile stays): Ctrl+Z takes back the line an edit kept, Ctrl+Y keeps it
        again. True when anything changed."""
        changed = False
        for key in set(frm) | set(to):
            value = to.get(key)
            if frm.get(key) == value:
                continue
            secret, name, digest = key
            ring = next((r for r in self.rings if r.secret == secret), None)
            if value is None:
                if ring is not None and ring.scopes.get(name, {}).pop(digest, None) is not None:
                    self.touched[key] = None
                    changed = True
                continue
            if ring is None:
                ring = Ring(secret)
                self.rings.append(ring)
            ring.scopes.setdefault(name, {})[digest] = entry = Entry(*value)
            self.touched[key] = entry
            changed = True
        if changed:
            self._changed()
        return changed

    # --- the file ------------------------------------------------------------------------------------------------
    def to_json(self) -> dict[str, Any] | None:
        """What the cache file keeps (None when there is nothing: the field is left out)."""
        rings = [{"key": ring.secret.hex(),
                  "scopes": {name: {d: e.to_json() for d, e in entries.items()}
                             for name, entries in ring.scopes.items() if entries}}
                 for ring in self.rings if len(ring)]
        return {"v": KEY_VERSION, "rings": rings} if rings else None

    @classmethod
    def from_json(cls, data: Any, on_change: Callable[[], None] | None = None) -> "LineMemo":
        """The memo a file's ``lines`` field holds; whatever is not one (another version's, damaged, written by hand) is
        left out, never fatal. At most `MAX_RINGS` rings and `MAX_ENTRIES` entries are read."""
        memo = cls(on_change)
        if not isinstance(data, dict) or data.get("v") != KEY_VERSION or not isinstance(data.get("rings"), list):
            return memo
        count = 0
        for raw in data["rings"][:MAX_RINGS]:
            if (not isinstance(raw, dict) or not isinstance(raw.get("key"), str)
                    or not isinstance(raw.get("scopes"), dict)):
                continue
            key = raw["key"].lower()
            if len(key) != 2 * SECRET_BYTES or not _HEX.fullmatch(key):
                continue
            ring = Ring(bytes.fromhex(key))
            for name, entries in raw["scopes"].items():
                if not isinstance(name, str) or len(name) > MAX_SCOPE or not isinstance(entries, dict):
                    continue
                kept: dict[str, Entry] = {}
                for digest, value in entries.items():
                    entry = _entry(value)
                    if (entry is not None and isinstance(digest, str) and len(digest) == 2 * DIGEST_BYTES
                            and _HEX.fullmatch(digest) and count < MAX_ENTRIES):
                        kept[digest] = entry
                        count += 1
                if kept:
                    ring.scopes[_CONTROLS.sub("", name)] = kept
            if len(ring) and all(r.secret != ring.secret for r in memo.rings):
                memo.rings.append(ring)
        return memo

    def take(self, fresh: "LineMemo") -> None:
        """Take what the file holds now (*fresh*: another process saved it meanwhile), with this process's changes since
        its last save on top (`touched`): a change to a ring the file no longer has comes back as a ring of its own,
        so that nothing this process kept is lost. In place: the memo stays the object the pipeline holds."""
        rings = [Ring(r.secret, {name: dict(entries) for name, entries in r.scopes.items()}) for r in fresh.rings]
        for (secret, scope_name, digest), entry in self.touched.items():
            ring = next((r for r in rings if r.secret == secret), None)
            if ring is None:
                if entry is None:
                    continue
                ring = Ring(secret)
                rings.append(ring)
            if entry is None:
                ring.scopes.get(scope_name, {}).pop(digest, None)
            else:
                ring.scopes.setdefault(scope_name, {})[digest] = entry
        mine = self.rings[0].secret if self.rings else None
        rings.sort(key=lambda r: r.secret != mine)  # this process's first ring stays first (new entries go there)
        self.rings = [r for r in rings if len(r)][:MAX_RINGS]

    def saved(self) -> None:
        """The file has what this memo holds: nothing is waiting any more."""
        self.touched.clear()

    def join(self, other: "LineMemo") -> int:
        """Add what *other* holds (an imported export's memo) where this one has nothing for the line: a ring with
        the same secret entry by entry, another secret as a ring of its own (at most `MAX_RINGS`). Returns how many
        entries came in."""
        added = 0
        for theirs in other.rings:
            ring = next((r for r in self.rings if r.secret == theirs.secret), None)
            if ring is None:
                if len(self.rings) >= MAX_RINGS:
                    continue
                ring = Ring(theirs.secret)
                self.rings.append(ring)
            for name, entries in theirs.scopes.items():
                mine = ring.scopes.setdefault(name, {})
                for digest, entry in entries.items():
                    if digest not in mine:
                        mine[digest] = Entry(entry.text, entry.edited)
                        self.touched[(ring.secret, name, digest)] = mine[digest]
                        added += 1
        if added:
            self._changed()
        return added


class SeriesLines:
    """What a book reuses: its own memo (*own*, written) and those of the other volumes of its series (*others*, read
    only, the most recently saved first). A person's translation wins wherever it is; then the book's own."""

    def __init__(self, own: LineMemo, others: Sequence[LineMemo] = ()):
        self.own = own
        self.others = list(others)

    def find(self, scope_name: str, key: str) -> Entry | None:
        mine = self.own.find(scope_name, key)
        if mine is not None and mine.edited:
            return mine
        theirs = [hit for hit in (memo.find(scope_name, key) for memo in self.others) if hit is not None]
        edited = next((hit for hit in theirs if hit.edited), None)
        return edited or mine or (theirs[0] if theirs else None)

    def put(self, scope_name: str, key: str, text: str, edited: bool = False) -> bool:
        return self.own.put(scope_name, key, text, edited)


@dataclass
class Tally:
    """This session's lines: how many were reused (from the book or its series, or from a line before them in the
    same request) and how many the model translated with reuse on. Counts only, in memory (Settings > System)."""

    reused: int = 0
    asked: int = 0


class Plan:
    """One request's lines (*texts*, with their facts *meta*, in reading order) split into those reused and those the
    model is asked for. With *lines* None or *serve* False every line is asked; with *lines* and *learn*, what the
    model answers is kept (`learn`). *sheet*: the series sheet a reused translation is held to; *usable*(Japanese,
    translation): whether a translation is one (`Pipeline.real_translation`). *regions*: the lines' regions, which
    get the translation reused in ``reused_text`` ("" for the others); *tally* counts.

    The caller sends what `ask` sends, then takes `fill` of the answer (also of no answer, after a failed request):
    the whole request's translations, the reused ones in their places."""

    def __init__(self, lines: SeriesLines | None, scope_name: str, texts: Sequence[str],
                 meta: Sequence[dict[str, Any] | None] | None = None, *, regions: Sequence[Any] = (),
                 sheet: Any = None, usable: Callable[[str, str], bool] | None = None, serve: bool = True,
                 learn: bool = True, tally: Tally | None = None):
        self.lines, self.scope, self.texts = lines, scope_name, [str(t) for t in texts]
        self.meta = [dict((meta[i] or {}) if meta and i < len(meta) else {}) for i in range(len(self.texts))]
        self.regions = list(regions)
        self.learns = learn and lines is not None
        self.tally = tally
        self.keys: list[str | None] = (materials(self.texts, self.meta) if lines is not None
                                       else [None] * len(self.texts))
        self.served: dict[int, str] = {}  # line -> the translation reused
        self.copies: dict[int, int] = {}  # line -> the earlier line of this request it repeats (its answer is taken)
        first: dict[str, int] = {}
        for i, key in enumerate(self.keys):
            if key is None or not serve:
                continue
            assert lines is not None
            entry = lines.find(scope_name, key)
            speaker = str(self.meta[i].get("speaker", "") or "")
            text = held_to(entry.text, self.texts[i], sheet, speaker) if entry else ""
            if text and (usable is None or usable(self.texts[i], text)):
                self.served[i] = text
            elif key in first:
                self.copies[i] = first[key]
            else:
                first[key] = i
        self.asked = [i for i in range(len(self.texts)) if i not in self.served and i not in self.copies]
        for i, region in enumerate(self.regions):
            try:
                region.reused_text = self.served.get(i, "")
            except AttributeError:
                pass

    @property
    def reuses(self) -> bool:
        """Whether any line of the request is not sent to the model."""
        return len(self.asked) < len(self.texts)

    def ask(self, translate: Callable[..., Sequence[str]], *args: Any, meta: Any = None, **kwargs: Any) -> list[str]:
        """``translate(texts, *args, meta=..., **kwargs)`` (a translator's ``translate_page``) for the lines not reused:
        their answers, in their order; nothing is asked when every line is reused ([]). An ``on_item`` among *kwargs*
        is told the reused lines first, then each answer in the request's own numbering (and for each line that takes
        it)."""
        on_item = kwargs.pop("on_item", None)
        if on_item is not None:
            for i in sorted(self.served):
                on_item(i, self.served[i])
        if not self.reuses:
            if on_item is not None:
                kwargs["on_item"] = on_item
            return list(translate(self.texts, *args, meta=meta, **kwargs))
        if not self.asked:
            return []
        asked = self.asked
        if on_item is not None:
            def told(k: int, text: str) -> None:
                if 0 <= k < len(asked):
                    on_item(asked[k], text)
                    for i, j in self.copies.items():
                        if j == asked[k]:
                            on_item(i, text)

            kwargs["on_item"] = told
        sub_meta = [meta[i] for i in asked] if meta else None
        return list(translate([self.texts[i] for i in asked], *args, meta=sub_meta, **kwargs))

    def fill(self, answers: Sequence[Any]) -> list[str]:
        """The translation of every line of the request from *answers* (`ask`'s, maybe fewer, or [] after a failed
        request): the answers in the places of the lines asked, the reused translations in theirs, a repeat with the
        answer of the line it repeats; "" where there is none."""
        answers = [str(a or "").strip() for a in answers]
        if not self.reuses:
            return answers[:len(self.texts)] + [""] * max(0, len(self.texts) - len(answers))
        out = [""] * len(self.texts)
        for k, i in enumerate(self.asked):
            out[i] = answers[k] if k < len(answers) else ""
        for i, text in self.served.items():
            out[i] = text
        self._copy(out)
        return out

    def _copy(self, out: list[str]) -> None:
        """Each repeat of *out* with the translation of the line it repeats (its region told it was reused)."""
        for i, j in self.copies.items():
            out[i] = out[j]
            if i < len(self.regions) and out[j]:
                try:
                    self.regions[i].reused_text = out[j]
                except AttributeError:
                    pass

    def unserved(self, outputs: Sequence[str]) -> list[str]:
        """*outputs* (`fill`'s) with "" for the lines reused and the repeats: what a later pass that asks the model
        again looks at (`ask_again_romanised`); a reused line was looked at when it was first answered, and a repeat
        follows its line (`served_back`)."""
        return ["" if i in self.served or i in self.copies else str(o or "") for i, o in enumerate(outputs)]

    def served_back(self, outputs: Sequence[str]) -> list[str]:
        """*outputs* (`unserved`'s, after such a pass) with the reused lines and the repeats in their places again."""
        out = [str(o or "") for o in outputs]
        for i, text in self.served.items():
            if i < len(out):
                out[i] = text
        if all(i < len(out) and j < len(out) for i, j in self.copies.items()):
            self._copy(out)
        return out

    def learn(self, finals: dict[int, str] | Sequence[str]) -> int:
        """Keep the final translation of each line asked (*finals*: by line, "" or missing where there is none; as set
        on the page, after the checks), and count. A reused line, or a repeat, that kept its reused translation is
        counted as reused and kept as it was; one that ended with another (asked again after all) is kept anew.
        Returns how many entries changed."""
        if isinstance(finals, dict):
            final = finals
        else:
            final = {i: t for i, t in enumerate(finals)}
        changed = 0
        for i, key in enumerate(self.keys):
            text = str(final.get(i, "") or "").strip()
            if not text:
                continue
            reused = ((i in self.served and text == self.served[i])
                      or (i in self.copies and text == final.get(self.copies[i])))
            if self.tally is not None:
                if reused:
                    self.tally.reused += 1
                elif self.learns:
                    self.tally.asked += 1
            if reused or key is None or not self.learns:
                continue
            assert self.lines is not None
            changed += self.lines.put(self.scope, key, text)
        return changed

    def learn_regions(self, regions: Sequence[Any]) -> int:
        """`learn` of the regions of the request (in its order): the translation of each one translated."""
        return self.learn({i: r.translated_text for i, r in enumerate(regions)
                           if getattr(r, "status", "") == "translated" and getattr(r, "translated_text", "")})


def held_to(text: str, source: str, sheet: Any, speaker: str = "") -> str:
    """*text*, a kept translation of *source*, as the series sheet *sheet* has it now: spelt as the sheet spells
    (`terms.spelt_right`, the correction a fresh answer gets: a sheet changed since the line was kept never brings an
    old spelling back); "" when it still misses a rendering the sheet asks for (`terms.term_misses`: the line is asked
    for instead)."""
    if not text or sheet is None:
        return text
    from .terms import spelt_right, term_misses

    text = spelt_right(sheet, source, text, speaker)
    return "" if term_misses(sheet, source, text, speaker) else text


# --- the pipeline's side --------------------------------------------------------------------------------------------
def held_lines(pipeline: Any) -> SeriesLines | None:
    """The lines *pipeline*'s book reuses: those of its cache (`BookCache.lines`) and, when the window or the command
    line read them for that very cache (``series_lines``, `series_lines`), its series' other volumes; None without a
    cache, or with ``reuse_lines`` off."""
    cache = getattr(pipeline, "cache", None)
    if cache is None or not getattr(pipeline.settings, "reuse_lines", True):
        return None
    own = getattr(cache, "lines", None)
    if own is None:
        return None
    held = getattr(pipeline, "series_lines", None)
    if held is None or held.own is not own:
        held = SeriesLines(own)
        pipeline.series_lines = held
    return held


def plan_for(pipeline: Any, texts: Sequence[str], meta: Sequence[dict[str, Any] | None] | None,
             regions: Sequence[Any] = (), serve: bool = True, learn: bool = True) -> Plan:
    """The `Plan` of a request of *pipeline* (`Pipeline._translate_regions`, the backlog's
    `translate.sequence.translate_units`): its book's lines (`held_lines`), its translator and target language, its
    series sheet; *serve* False ("Translate again") asks every line and keeps the new answers; *learn*
    False keeps nothing either (a page read without the cache: `Pipeline.process` with ``use_cache`` False)."""
    lines = held_lines(pipeline) if serve or learn else None
    return Plan(lines, scope(pipeline.translator, pipeline.settings.target_language), texts, meta,
                regions=regions, sheet=pipeline.check_sheet(), usable=pipeline.real_translation, serve=serve,
                learn=learn, tally=getattr(pipeline, "line_tally", None))


def remember_edit(pipeline: Any, result: Any, region: Any, text: str) -> bool:
    """Translator mode's Save of *text* as the translation of *region* on the page *result*: kept as a person's
    translation of its line, which later identical lines of the book and its series get. The region's Japanese is
    read again from the capture first when the page came from the cache (`Pipeline.read_source`, in memory). Not for
    a line that is not reused (`material`; one the region before it on the page goes on into, by its Japanese).
    Returns True when it was kept."""
    lines = held_lines(pipeline)
    if lines is None or not text.strip():
        return False
    source = getattr(region, "source_text", "")
    if not source and getattr(pipeline, "ocr", None) is not None:
        try:
            source = pipeline.read_source(result, region)
        except Exception:  # noqa: BLE001 - nothing read: the edit stays the page's alone
            source = ""
    if not source:
        return False
    from .regions import region_meta

    key = material(source, region_meta(region), after_open=_goes_on_into(result, region))
    if key is None:
        return False
    return lines.put(scope(pipeline.translator, pipeline.settings.target_language), key, text, edited=True)


def _goes_on_into(result: Any, region: Any) -> bool:
    """Whether the region before *region* on the page *result* (its reading order) goes on into it: the reader's mark,
    or by its Japanese and its place (`translate.continuation.continues`), when this session read it."""
    from .translate.continuation import continues

    regions = [r for r in getattr(result, "regions", []) if getattr(r, "status", "") in ("translated", "untranslated")]
    at = next((k for k, r in enumerate(regions) if r is region), -1)
    if at <= 0:
        return False
    before = regions[at - 1]
    if getattr(before, "continues", False):
        return True
    units = getattr(result, "units", []) or []
    unit = units[region.unit].box if 0 <= getattr(region, "unit", 0) < len(units) else None
    return bool(before.source_text) and continues(before.source_text, before.bbox, region.bbox, unit,
                                                  getattr(before, "unit", 0) == getattr(region, "unit", 0))


def same_series(a: str, b: str) -> bool:
    """Whether the series keys *a* and *b* name one series: alike but for letter case and spaces, as the two fields
    compare a series (`bookname.same_book`)."""
    from .bookname import clean_series

    def compact(key: str) -> str:
        return "".join(clean_series(key).casefold().split())

    return bool(compact(a)) and compact(a) == compact(b)


def series_lines(store: Any, cache: Any, series: str | None = None, sheets: Any = None) -> SeriesLines:
    """The lines the book of *cache* reuses: its own, then those of the other books of its series whose caches in
    *store* are in the same target language, the most recently saved first (read from the files' headers,
    `CacheStore.line_memos`). A book's series is the key its series sheet is kept under in *sheets* (an
    `annotations.GlossaryStore`; `notes.sheet_key`: the Series field, or the older key a sheet is still kept under;
    without *sheets*, `notes.series_key`), and *series*, when given, is the book's (``--series``); two keys alike
    but for letter case and spaces are one series (`same_series`). A cache that cannot be read is passed over."""
    from .notes import sheet_key

    def series_of(name: str) -> str:
        try:
            return sheet_key(sheets, name)
        except (OSError, ValueError):
            return sheet_key(None, name)  # (the series alone: the store cannot say which sheets it keeps now)

    book = str(getattr(cache, "book", "") or "")
    wanted = series if series is not None else series_of(book)
    look = getattr(store, "line_memos", None)
    try:
        others = (look(wanted, getattr(cache, "language", ""), but=book, series_of=series_of)
                  if look is not None and wanted else [])
    except (OSError, ValueError):
        others = []
    return SeriesLines(cache.lines, others)


def count(memos: Iterable[LineMemo]) -> int:
    """How many lines *memos* keep in all."""
    return sum(len(memo) for memo in memos)


__all__ = ["DIGEST_BYTES", "Entry", "KEY_VERSION", "LineMemo", "MAX_CHARS", "Plan", "Ring", "SECRET_BYTES",
           "SeriesLines", "Tally", "count", "held_lines", "held_to", "material", "materials", "normalise", "plan_for",
           "remember_edit", "same_series", "scope", "series_lines"]
