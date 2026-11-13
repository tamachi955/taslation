"""Renaming a book: everything TASlation keeps under one name moved to another.

A book's name is the name of its files (`names.py`): its translation cache in every target language (`cache.py`), the
reader's annotations (`annotations.py`) and, for its series (`notes.series_key` of the name), the series sheet in every
language. `rename_book` moves them from *old* to *new*: each file is read, given the new name (a cache's header
``book``, an annotations file's ``book``, a sheet's ``series``), written where its store puts the new name's file
(`names.pick`; `atomic.write_atomic`), and then the old name's files are deleted with the copies kept beside them
(`names.files_of`). The series sheet moves only when the new name gives another series ("Star Road 3" and "Star Road
4" are one series): then the whole sheet goes, as it is the series'. Otherwise it stays where it is. (Translator's
notes of the model's own were kept per series until 2026-11-06; files of them an earlier version left are not moved.)

When the new series has a sheet of its own in a language already (its volume 1 was renamed to the full title
before, or an old cache kept under the viewer's name is renamed), the book's sheet in that language joins it instead of
moving: what the book's sheet has and the series' lacks - terms, characters, facts, policies - is taken over
(`Glossary.merge`), and where the two say otherwise (a `Conflict`: a term's rendering or note, a character's fact or
how they call someone, a policy of the style guide, the lettering of a kind) the series' value stays unless the
reader answered to take the book's (*answers*, by `conflict_key`). The joined sheet is written in place of the
series' file, header and all (its series, its ``updated`` now), and the book's old file deleted as a moved one is.
Each language on its own: a sheet with nothing of the new series' in its language moves as it is. `plan_rename`
makes every check and says what would join - the conflicts to answer, what would be added - without
writing anything; `rename_book` makes the plan again when it renames (the files may have changed meanwhile) and
carries the answers over by `conflict_key`.

Nothing is ever written over. Everything is checked first, and the rename is refused (`RenameRefused`, naming the file)
with nothing changed when a target file exists already (the new name's own cache or annotations, a file of another name
in the way, one that cannot be read - also the new series' own sheet when this version cannot read it), when
a file of the old name cannot be read (damaged, or written by a newer TASlation: it is never deleted unread), when the
new name names no book (`bookid.generic_book_name`) or is the old name itself. The series' own sheet is
joined, not written over: all it holds stays, but for the values the reader answered to take from the book. A write
that fails halfway takes back what was written: a new file deleted, a file written in place or joined given its old
bytes again. An old file that cannot be deleted afterwards (another program has it open) stays where it is, and the
result names it.

A moved cache keeps the details its header had (`cache.DETAIL_FIELDS`); a colophon's *details* go into the header of
every cache moved, and of the book's cache in the language it is read in (made when the book has none there, as the
window keeps a colophon's details).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple

from .annotations import (
    ANNOTATION_FILES, SHEET_FILES, AnnotationStore, Conflict, Glossary, GlossaryStore, Review, apply_review,
    compare_sheets,
)
from .atomic import write_atomic
from .bookid import generic_book_name
from .cache import DETAIL_FIELDS, CacheStore, clean_detail, language_key, stored_book
from .cache import SCHEMA_VERSION as CACHE_SCHEMA
from .messages import Message
from .names import (
    DAMAGED, Owner, OwnerOf, Unreadable, check_schema, drop_leftovers, file_names, files_of, is_copy, load_object,
    pick,
)
from .notes import series_key

Answers = Mapping[tuple[str, ...], bool]  # a conflict's key (`conflict_key`) -> take this book's value
_PARSE_ERRORS = (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, RecursionError)


class Stores(NamedTuple):
    """Where a book's files are kept: the caches, the reader's annotations and the series sheets (the window's own
    stores, or those of the settings: `of`)."""

    cache: CacheStore
    annotations: AnnotationStore
    sheets: GlossaryStore

    @classmethod
    def of(cls, settings: Any) -> "Stores":
        """The stores in the folders of *settings* (`config.Settings`)."""
        return cls(CacheStore(settings.cache_dir), AnnotationStore(settings.annotations_dir),
                   GlossaryStore(settings.glossary_dir))


class RenameRefused(ValueError):
    """Why a book cannot be renamed, in a sentence that names the file in the way; nothing was changed. ``str()`` is
    that sentence in English, for the command line and the log; ``.message`` says what to do, for a window to show in
    its language."""

    def __init__(self, text: str, message: Message):
        super().__init__(text)
        self.message = message


def conflict_key(c: Conflict, language: str | None = None) -> tuple[str, ...]:
    """A conflict's identity, under which its answer is carried from the plan the window showed to the rename made
    after it (`rename_book`'s *answers*; the files may have changed meanwhile): its area, key, field and sub - the
    term; the character and their fact, or whom they call; the style guide's policy, or the kind of lettering. With
    *language*, its sheet's language key first: an answer for the sheet in that language alone (where the sheets of
    several languages join, `RenamePlan.keyed`)."""
    identity = (c.area, c.key, c.field, c.sub)
    return identity if language is None else (language_key(language), *identity)


@dataclass
class SheetJoin:
    """The book's series sheet in one language joining the sheet the new series has in it already (`plan_rename`):
    how many terms, characters, facts and policies it adds that the series' sheet lacks (*added*), and where the two
    say otherwise (*conflicts*: `annotations.Conflict`s of the areas "term", "character" and "style", *mine* the
    series' value and *theirs* the book's; *take* False keeps the series')."""

    language: str
    added: int = 0
    conflicts: list[Conflict] = field(default_factory=list)


@dataclass
class RenamePlan:
    """What renaming *old* to *new* would do where the book's files meet the new series' (`plan_rename`), nothing
    written: per language, the series sheet that joins the sheet the new series has already (`SheetJoin`). Empty
    while the series stays, or while the new series has no sheet in the languages of the book's (they move as they
    are)."""

    old: str
    new: str
    old_series: str
    new_series: str
    sheets: list[SheetJoin] = field(default_factory=list)

    @property
    def series_moved(self) -> bool:
        """Whether the new name gives another series (the sheet goes with the book)."""
        return self.old_series != self.new_series

    @property
    def conflicts(self) -> list[Conflict]:
        """Every conflict to answer, sheet by sheet."""
        return [c for sheet in self.sheets for c in sheet.conflicts]

    @property
    def added(self) -> int:
        """What the book's sheets add to the series' sheets: terms, characters, facts, policies."""
        return sum(sheet.added for sheet in self.sheets)

    def keyed(self) -> list[tuple[tuple[str, ...], str, Conflict]]:
        """Every conflict with the key its answer goes under (`conflict_key`: with its sheet's language when the
        conflicts are in the sheets of more than one language) and that language, sheet by sheet."""
        several = len({language_key(sheet.language) for sheet in self.sheets if sheet.conflicts}) > 1
        return [(conflict_key(c, sheet.language if several else None), sheet.language, c)
                for sheet in self.sheets for c in sheet.conflicts]


@dataclass
class RenameResult:
    """What a rename moved, per store, and what joined the new series' sheet."""

    old: str
    new: str
    old_series: str
    new_series: str
    caches: int = 0  # cache files moved: one per target language
    annotations: int = 0  # the reader's annotations moved (one file per book)
    sheets: int = 0  # series sheet files moved or joined, one per language (none while the series stays the same)
    sheets_merged: int = 0  # of the sheets, those that joined the sheet the new series had in their language
    added: int = 0  # what they added: terms, characters, facts and policies the series' sheet lacked
    taken: int = 0  # conflicts where the book's value was taken
    kept: int = 0  # conflicts kept as the series' sheet had them
    left: list[str] = field(default_factory=list)  # old files that could not be deleted: they are still there

    @property
    def series_moved(self) -> bool:
        """Whether the new name gives another series (the sheet went with the book)."""
        return self.old_series != self.new_series

    @property
    def files(self) -> int:
        """How many files moved (or joined)."""
        return self.caches + self.annotations + self.sheets


@dataclass(frozen=True)
class _Kind:
    """One store, as a rename sees it."""

    what: str  # what its files hold, for messages: "the cache"
    folder: Path
    owner_of: OwnerOf  # whose a file is (`names.StoreFiles.owner_of`, `cache.stored_book`)
    languages: bool  # a file per target language
    check: Callable[[dict[str, Any]], None]  # names.Unreadable for a file this version cannot read
    default_language: str | None = None  # the language of a file that records none ("English" in the cache)


@dataclass
class _Source:
    path: Path
    data: dict[str, Any]
    language: str | None  # as the file records it (None in a store without languages)


@dataclass
class _Move:
    what: str  # "the cache of 'X' in English"
    source: Path
    target: Path
    data: dict[str, Any]  # what the target is to hold: the source's JSON with the new name (or joined)
    original: bytes | None = None  # what the target held before it was written (in place, or joined): to take it back


@dataclass
class _Join:
    """A sheet of the book's joining the new series' sheet: the move that writes the joined sheet (its data made once
    the answers are known: `_answer`), the series' file's JSON, its sheet (the book's joined into it, in memory) and
    what the book's sheet adds and says otherwise (`annotations.compare_sheets`)."""

    view: SheetJoin
    move: _Move
    there: dict[str, Any]
    own: Glossary
    review: Review


@dataclass
class _Plan:
    """A rename checked and laid out (`_plan`): what is written where, and what is then deleted."""

    view: RenamePlan
    result: RenameResult
    kinds: tuple[_Kind, _Kind, _Kind]
    details: dict[str, str]
    moves: list[_Move] = field(default_factory=list)
    joins: list[_Join] = field(default_factory=list)
    languages: set[str] = field(default_factory=set)  # the keys of the languages whose caches move


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _check_cache(data: dict[str, Any]) -> None:
    check_schema(data, CACHE_SCHEMA)
    if not isinstance(data.get("pages", []), list):
        raise Unreadable("damaged: no list of pages")


def _kinds(stores: Stores) -> tuple[_Kind, _Kind, _Kind]:
    """The caches, the annotations, the series sheets."""
    return (_Kind("the cache", Path(stores.cache.cache_dir), stored_book, True, _check_cache, "English"),
            _Kind("the annotations", Path(stores.annotations.annotations_dir), ANNOTATION_FILES.owner_of, False,
                  ANNOTATION_FILES.check),
            _Kind("the series sheet", Path(stores.sheets.glossary_dir), SHEET_FILES.owner_of, True, SHEET_FILES.check))


def _unreadable(path: Path, folder: Path) -> Message:
    return Message("rename.unreadable", path=str(path), folder=str(folder))


def _busy(path: Path) -> Message:
    return Message("rename.busy", path=str(path))


def _in_way(path: Path, folder: Path) -> Message:
    return Message("rename.in_way", path=str(path), folder=str(folder))


def _read(check: Callable[[dict[str, Any]], None], path: Path) -> dict[str, Any] | None:
    """The JSON object in *path*, a file of the old name (*check*: its store's, `_Kind.check`); None when it is gone
    meanwhile. RenameRefused when this version cannot read it (it is never deleted unread) or it cannot be opened
    now."""
    try:
        data = load_object(path)
        if data is not None:
            check(data)
    except Unreadable as e:
        raise RenameRefused(f"{path} cannot be read ({e.reason}); move it out of {path.parent} first, or the rename "
                            f"would lose it", _unreadable(path, path.parent)) from None
    except OSError as e:
        raise RenameRefused(f"{path} cannot be opened now ({e.strerror or e}); close what holds it, then try "
                            f"again", _busy(path)) from None
    return data


def _damaged(path: Path) -> RenameRefused:
    """The refusal for the file at *path*, whose JSON a join cannot take its data from."""
    return RenameRefused(f"{path} cannot be read ({DAMAGED}); move it out of {path.parent} first",
                         _unreadable(path, path.parent))


def _language_of(kind: _Kind, name: str, path: Path, data: dict[str, Any]) -> str | None:
    """The language of *name*'s file at *path* as its store opens it (None in a store without languages): the one it
    records; for a sheet that records none, English when it has one of the English file names, else
    RenameRefused (where it would go cannot be told)."""
    if not kind.languages:
        return None
    if kind.default_language is not None:
        return str(data.get("language", kind.default_language))
    language = data.get("language")
    if isinstance(language, str):
        return language
    if os.path.normcase(path.name) in {os.path.normcase(n) for n in file_names(name, "English")}:
        return "English"
    raise RenameRefused(f"{path} does not record which language it is for; move it out of {path.parent} first",
                        _unreadable(path, path.parent))


def _sources(kind: _Kind, name: str, strict: bool = True) -> list[_Source]:
    """The files of *name* in the store to move: per language the one its store opens (`names.pick`), read. Every
    other file of the name (a copy kept beside them, a stale second file) goes with the old files afterwards; one
    that cannot be read refuses the rename (`_read`) - unless not *strict* (files that are changed in place, never
    deleted: it is left as it is)."""
    read: dict[str, dict[str, Any]] = {}
    languages: dict[str, str | None] = {}  # the language's key -> the language as a file records it
    for path in files_of(kind.folder, name, kind.owner_of, kind.languages):
        if is_copy(path):
            continue
        try:
            data = _read(kind.check, path)
            language = _language_of(kind, name, path, data) if data is not None else None
        except RenameRefused:
            if strict:
                raise
            continue
        if data is None:
            continue
        read[_key(path)] = data
        languages.setdefault("" if language is None else language_key(language), language)
    sources: list[_Source] = []
    for language in languages.values():
        try:
            path = pick(kind.folder, name, language, kind.owner_of, kind.what)
        except FileExistsError:
            continue  # both its file names hold other names: there is no file of it in this language
        data = read.get(_key(path))
        if data is not None:
            sources.append(_Source(path, data, language))
    return sources


def _place(kind: _Kind, name: str, language: str | None, free: set[str], what: str) -> Path:
    """Where *what*, the file of *name* in *language*, goes: where its store puts it (`names.pick`), the old name's
    files counted free (they go). RenameRefused when both file names *name* can have hold other names."""

    def owner(path: Path) -> Owner | None:
        return None if _key(path) in free else kind.owner_of(path)

    try:
        return pick(kind.folder, name, language, owner, kind.what)
    except FileExistsError as e:
        raise RenameRefused(f"there is no file for {what}: {e}", _in_way(Path(kind.folder), Path(kind.folder))) from None


def _target(kind: _Kind, name: str, language: str | None, free: set[str], what: str) -> Path:
    """Where *what*, the file of *name* in *language*, goes (`_place`). RenameRefused when a file is there already."""
    target = _place(kind, name, language, free, what)
    if _key(target) not in free and os.path.lexists(target):
        there = kind.owner_of(target)
        if there is not None and there[0] == name:
            raise RenameRefused(f"{what} exists already ({target})", _in_way(target, target.parent))
        raise RenameRefused(f"{target} is in the way of {what}; move it out of {kind.folder} first",
                            _in_way(target, target.parent))
    return target


def _meeting(kind: _Kind, name: str, language: str | None, free: set[str],
             what: str) -> tuple[Path, dict[str, Any] | None]:
    """Where *what*, the series sheet of the series *name* in *language*, goes (`_place`), and the JSON
    of the file *name* has there already, read and checked: the file it joins; None when there is none (it moves).
    RenameRefused when a file that is not *name*'s is in the way (another name's, one that records none, one too
    damaged to tell whose it is), or when *name*'s own cannot be read or opened now (it is never written over
    unread)."""
    target = _place(kind, name, language, free, what)
    if _key(target) in free or not os.path.lexists(target):
        return target, None
    there = kind.owner_of(target)
    if there is None or there[0] != name:
        raise RenameRefused(f"{target} is in the way of {what}; move it out of {kind.folder} first",
                            _in_way(target, target.parent))
    try:
        data = load_object(target)
        if data is not None:
            kind.check(data)
    except Unreadable as e:
        raise RenameRefused(f"{what} exists already ({target}) and cannot be read ({e.reason}); move it out of "
                            f"{kind.folder} first", _unreadable(target, target.parent)) from None
    except OSError as e:
        raise RenameRefused(f"{target} cannot be opened now ({e.strerror or e}); close what holds it, then try "
                            f"again", _busy(target)) from None
    return target, data


def _details(details: Mapping[str, Any] | None) -> dict[str, str]:
    """The colophon's *details* as a cache's header keeps them (`cache.clean_detail`), the empty ones left out."""
    known: dict[str, str] = {}
    for name in DETAIL_FIELDS:
        value = clean_detail(name, (details or {}).get(name))
        if value:
            known[name] = value
    return known


def _moved_cache(data: dict[str, Any], new: str, details: dict[str, str]) -> dict[str, Any]:
    """A cache file's JSON under the name *new*, with the colophon's *details* in its header; its pages stay last,
    where `CacheStore.identities` expects them."""
    head = {key: value for key, value in data.items() if key != "pages"}
    head["book"] = new
    head.update(details)
    head["pages"] = data.get("pages", [])
    return head


def _sheet(data: dict[str, Any], path: Path) -> Glossary:
    """The series sheet whose JSON *data* the file at *path* holds, to join; RenameRefused when it cannot be taken."""
    try:
        return Glossary.from_json(data, path)
    except _PARSE_ERRORS:
        raise _damaged(path) from None


def _sheet_join(source: _Source, target: Path, there: dict[str, Any], what: str) -> _Join:
    """The book's sheet *source* joining the series' sheet at *target* (its JSON *there*): compared (`compare_sheets`:
    the series' sheet is "mine", the book's "theirs"), the joined sheet's data still to be made (`_answer`)."""
    own = _sheet(there, target)
    review = compare_sheets(own, _sheet(source.data, source.path))
    view = SheetJoin(str(source.language), review.terms, list(review.conflicts))
    return _Join(view, _Move(what, source.path, target, {}), there, own, review)


def _taken(answers: Answers | None, c: Conflict, language: str) -> bool:
    """The reader's answer for *c* in the sheet in *language*: under its key with the language, else under its key
    (`conflict_key`); keep the series' value when there is none."""
    for key in (conflict_key(c, language), conflict_key(c)):
        if answers and key in answers:
            return bool(answers[key])
    return False


def _answer(join: _Join, answers: Answers | None, series: str) -> tuple[int, int, int]:
    """The joined sheet as the reader answered (`annotations.apply_review`): what the book's sheet adds, its values
    where the answer says take the book's, the series' everywhere else; its JSON made the move's data - the series'
    file with the joined terms, characters and style, *series*, ``updated`` now. Returns how much was added, how many
    conflicts were taken and how many kept."""
    for c in join.review.conflicts:
        c.take = _taken(answers, c, join.view.language)
    counts = apply_review(join.review, join.own)
    body = join.own.to_json()
    data = {**join.there, "series": series, "updated": _now(),
            **{name: body[name] for name in ("entries", "characters", "style")}}
    if not isinstance(join.there.get("language"), str):
        data["language"] = join.view.language
    join.move.data = data
    return counts["terms"], counts["taken"], len(join.review.conflicts) - counts["taken"]


def _encode(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def _write(moves: list[_Move]) -> None:
    """Every move's target written; when one cannot be, the ones written before are taken back (a new file deleted,
    a file written over - in place, or joined - given its old bytes again) and the OSError raised."""
    done: list[_Move] = []
    try:
        for move in moves:
            try:
                move.original = move.target.read_bytes()
            except FileNotFoundError:
                move.original = None  # a new file
            move.target.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(move.target, _encode(move.data))
            done.append(move)
    except OSError:
        for move in reversed(done):
            try:
                if move.original is not None:
                    write_atomic(move.target, move.original)
                else:
                    move.target.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _delete(kind: _Kind, name: str, written: set[str], left: list[str]) -> None:
    """The old name's files in the store deleted (`names.files_of`: with the copies kept beside them and what a save
    that stopped halfway left), never one just written; one that cannot be deleted is named in *left*."""
    for path in files_of(kind.folder, name, kind.owner_of, kind.languages):
        if _key(path) in written:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            left.append(str(path))
            continue
        drop_leftovers(path)


def _plan(stores: Stores, old: str, new: str, details: Mapping[str, Any] | None = None) -> _Plan:
    """Every check of a rename of *old* to *new* made and every file read, nothing written: what goes where (the
    joined sheets' data still to be made from the answers: `_answer`). RenameRefused for what stands in the way."""
    if not old.strip():
        raise RenameRefused("there is no book to rename", Message("rename.no_name"))
    if generic_book_name(new):
        raise RenameRefused(f"{new!r} names no book; give the book its own name", Message("rename.no_name"))
    if new == old:
        raise RenameRefused(f"the book is called {old!r} already", Message("rename.same_name", book=old))
    old_series, new_series = series_key(old), series_key(new)
    caches, annotations, sheets = kinds = _kinds(stores)
    plan = _Plan(RenamePlan(old, new, old_series, new_series), RenameResult(old, new, old_series, new_series), kinds,
                 _details(details))
    result, moves = plan.result, plan.moves

    sources = _sources(caches, old)
    free = {_key(s.path) for s in sources}
    for s in sources:
        what = f"the cache of {new!r} in {s.language}"
        moves.append(_Move(what, s.path, _target(caches, new, s.language, free, what),
                           _moved_cache(s.data, new, plan.details)))
        plan.languages.add(language_key(str(s.language)))
    result.caches = len(sources)

    marks = _sources(annotations, old)
    free = {_key(s.path) for s in marks}
    for s in marks:
        what = f"the annotations of {new!r}"
        target = _target(annotations, new, None, free, what)
        moves.append(_Move(what, s.path, target, {**s.data, "book": new}))
    result.annotations = len(marks)

    if result.series_moved:  # the whole sheet goes with the book, or joins the new series'
        sources = _sources(sheets, old_series)
        free = {_key(s.path) for s in sources}
        for s in sources:
            what = f"the series sheet of {new_series!r} in {s.language}"
            target, there = _meeting(sheets, new_series, s.language, free, what)
            if there is None:
                moves.append(_Move(what, s.path, target, {**s.data, "series": new_series}))
                continue
            join = _sheet_join(s, target, there, what)
            plan.joins.append(join)
            plan.view.sheets.append(join.view)
            moves.append(join.move)
        result.sheets = len(sources)
    return plan


def plan_rename(stores: Stores, old: str, new: str) -> RenamePlan:
    """What renaming the book *old* to *new* would do where its files meet the new series' (`RenamePlan`: per
    language the sheet that joins the new series' sheet - what it adds, the conflicts to answer, each *take* False),
    every check of `rename_book` made and nothing written. RenameRefused, as `rename_book` would refuse. It reads the
    book's files and the new series' sheet, nothing more."""
    return _plan(stores, old, new).view


def rename_book(stores: Stores, old: str, new: str, language: str | None = None,
                details: Mapping[str, Any] | None = None, answers: Answers | None = None) -> RenameResult:
    """Move everything kept under the book name *old* to *new* (see the module's docstring): the cache in every
    language, the reader's annotations and, when the series of *new* (`notes.series_key`) is another than *old*'s, the
    series sheet in every language. Where the new series has a sheet in a language already, the book's joins it;
    *answers* (a conflict's key, `conflict_key`, to True for "take this book's value": what the review answered on
    `plan_rename`'s plan) decide the conflicts of the plan
    made again now, each one without an answer keeping the series' value. *details* (a colophon's: title, volume,
    author, publisher, isbn) go into the header of every cache moved, and with *language* (the target language the
    book is read in) of its cache in that language, made when there is none. Returns what moved and what joined.
    RenameRefused, with nothing changed, when anything stands in the way; an OSError when a file cannot be written
    (what was written before is taken back)."""
    plan = _plan(stores, old, new, details)
    result = plan.result
    for join in plan.joins:
        added, taken, kept = _answer(join, answers, result.new_series)
        result.sheets_merged += 1
        result.added += added
        result.taken += taken
        result.kept += kept

    _write(plan.moves)  # everything checked: now written, all or nothing
    written = {_key(m.target) for m in plan.moves}
    caches, annotations, sheets = plan.kinds
    _delete(caches, old, written, result.left)
    _delete(annotations, old, written, result.left)
    if result.series_moved:
        _delete(sheets, result.old_series, written, result.left)

    known = plan.details
    if known and language is not None and language_key(language) not in plan.languages:
        try:  # the colophon's details where the window looks for them first: the cache in the language read in
            cache = stores.cache.open(new, "", language)
            if cache.set_details(**known):
                cache.save()
        except OSError:
            pass  # the window keeps them the next time it reads the colophon
    return result


__all__ = ["Answers", "RenamePlan", "RenameRefused", "RenameResult", "SheetJoin", "Stores",
           "conflict_key", "plan_rename", "rename_book"]
