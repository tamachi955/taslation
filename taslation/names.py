"""The file a book's or a series' data goes to: one per exact name (and target language), even when two names give
the same file name.

What TASlation keeps per book or series is a JSON file named after it: the translation cache (`cache.py`), the
reader's annotations and the series sheet (`annotations.py`). Its plain name
is ``<slug>[.<language>].json`` (`slugify`; no language part for English, nor in a store without languages). Two
names can give one slug: punctuation ("Pebble:Harbor 1" and "Pebble Harbor 1"), letter case on Windows ("QUILLPOND 1" and
"Quillpond 1"), the 120-character cut, an all-symbol title ("!!!" and "???"). Every such file records the exact name
it belongs to, so the plain file stays with the first name saved under it, and each other name with that slug gets
``<slug>-<hash>[.<language>].json``, the hash being eight hex digits of SHA-256 over the exact name in NFC
(`file_names`, `pick`). No store renames a file: a file keeps its name while it exists, and the files written
before this scheme keep working where they are. Renaming a book (`rename.py`) writes its files under the new name,
each where `pick` puts it, and then deletes the old ones (`files_of`).

A file that records no name (one written by hand or by another tool) belongs to the first name that opens it under
its file name; the store records that name in it at its next save (`owns`, `StoreFiles.load`).

Every such file is protected at rest for the Windows user who saved it, on this computer (`protect.py`: Windows DPAPI),
under the same name: `load_object` opens a protected file and reads an earlier version's plain JSON as it is, and the
stores write through `protect.write`. A protected file this Windows user cannot open here - saved by another Windows
user or on another computer, or damaged - is a file the store cannot read (`NOT_HERE`).

A file a store cannot read is never written over: damaged (no JSON object, or not the shape the store writes), of
another kind, written by a newer TASlation (a schema number above the one this version reads), or protected for
another Windows user or computer. The store that opens it, or would save over it, first moves it to
``<stem>.unreadable-<YYYYmmdd-HHMMSS>.json`` beside it and says so in one line on stderr, without anything the file
holds, then starts afresh (`set_aside`, `StoreFiles.load`); a file moved for the last reason is also kept in a list the
window reads to say so (`take_set_aside`). Such a copy, like the ``<stem>.corrupt.json`` of earlier versions of the
cache, is no name's file whatever it holds (`is_copy`): no store lists or picks it, and `delete_files` takes it with
the files of its name.

Standard library only: `notice.py` and the start of the command line must not load the image libraries that
`cache.py` brings in.
"""

from __future__ import annotations

import errno
import glob
import hashlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

from . import protect

# Names Windows keeps for devices: a file called so (on Windows 10, with any extension) opens the device instead,
# and what is written to it is gone. Microsoft's list, COM0, LPT0 and the superscript digits included.
WINDOWS_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL",
                             *(f"{port}{digit}" for port in ("COM", "LPT") for digit in "0123456789¹²³")})

Owner = tuple[str | None, str | None]  # (exact name, language key) as a file records them; None: not recorded
OwnerOf = Callable[[Path], "Owner | None"]  # whose the file at a path is; None when there is none or it cannot be read
T = TypeVar("T")

# What a copy of a file a store could not read has after the file's stem (`set_aside`): the time it was set aside,
# with "-2", "-3" ... when two were set aside in the same second; ".corrupt" from earlier versions of the cache.
_COPY_PART = r"(?:unreadable-[0-9]{8}-[0-9]{6}(?:-[0-9]+)?|corrupt)"
_COPY_NAME = re.compile(r".+\." + _COPY_PART + r"\.json", re.IGNORECASE | re.DOTALL)
NEWER = "written by a newer TASlation"  # the reason a file with a schema number above this version's is set aside
DAMAGED = "damaged: wrong structure"  # the reason for a JSON object a store cannot take its data from
NOT_HERE = protect.NOT_HERE  # the reason for a protected file this Windows user cannot open on this computer
COPY_TRIES = 1000  # names tried for one copy (`set_aside`)
# what the line of `set_aside` adds for a file set aside as NOT_HERE: what to do
NOT_HERE_ADVICE = ("to bring a book's translations to this computer, export them where they were saved (Saved "
                   "translations..., or taslation cache export) and import the export here")
SET_ASIDE_KEPT = 50  # files set aside as NOT_HERE kept in the list the window reads (`take_set_aside`)


def slugify(text: str) -> str:
    """*text* as a file name: letters, digits, ``_`` and ``-`` only, at most 120 characters, ``untitled`` when
    nothing is left, and never a name Windows keeps for a device (``NUL`` gives ``_NUL``)."""
    slug = re.sub(r"[^\w\-]+", "_", text.strip(), flags=re.UNICODE).strip("_")
    slug = (slug or "untitled")[:120]
    if slug.split(".", 1)[0].upper() in WINDOWS_DEVICES:
        slug = "_" + slug
    return slug


def language_key(language: str) -> str:
    """What tells one target language from another (and its file): " English" and "english" are one."""
    return language.strip().lower()


def name_hash(name: str) -> str:
    """Eight hex digits of SHA-256 over the exact name in Unicode NFC (the same however the name was typed)."""
    exact = unicodedata.normalize("NFC", name).encode("utf-8", "surrogatepass")
    return hashlib.sha256(exact).hexdigest()[:8]


def _language_part(key: str) -> str:
    """The language part of a file name for the language *key*: never what a copy has there (`is_copy`), so that a
    copy is never the file of a name in some language."""
    part = slugify(key)
    return "_" + part if re.fullmatch(_COPY_PART, part, re.IGNORECASE) else part


def file_names(name: str, language: str | None = None) -> tuple[str, str]:
    """The two names the file of *name* in *language* can have: ``<slug>[.<language>].json``, and
    ``<slug>-<hash>[.<language>].json`` for when the first holds another name that gives the same one. No language
    part for English, nor for *language* None (a store without languages)."""
    key = None if language is None else language_key(language)
    suffix = "" if key is None or key == "english" else f".{_language_part(key)}"
    slug = slugify(name)
    return f"{slug}{suffix}.json", f"{slug}-{name_hash(name)}{suffix}.json"


def is_copy(path: Path) -> bool:
    """True when *path* is a copy of a file that a store could not read (`set_aside`), or a ``<stem>.corrupt.json``
    an earlier version of the cache made: never the file of a name, whatever it holds."""
    return _COPY_NAME.fullmatch(path.name) is not None


# --- reading a store file -------------------------------------------------------------------------------------

class Unreadable(ValueError):
    """A store file this version cannot read. *reason* says why in a few words, never anything the file holds."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_object(path: Path) -> dict[str, Any] | None:
    """The JSON object in the file at *path* (UTF-8, a byte order mark allowed), opened first when it is protected
    (`protect.readable`; an earlier version's plain file is read as it is); None when there is no such file.
    Unreadable when there is one but it holds no JSON object, or is protected and cannot be opened here (NOT_HERE:
    another Windows user's or computer's, or damaged; NEWER for a newer TASlation's); OSError when it cannot be opened
    now (another program holds it, or Windows' data protection did not answer)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    try:
        raw = protect.readable(raw)
    except protect.Newer:
        raise Unreadable(NEWER) from None
    except protect.CannotOpen:
        raise Unreadable(NOT_HERE) from None
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError):  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise Unreadable("damaged: not JSON") from None
    if not isinstance(data, dict):
        raise Unreadable("damaged: not a JSON object")
    return data


def read_object(path: Path) -> dict[str, Any] | None:
    """The JSON object in the file at *path*; None when there is no such file, it cannot be read or it holds no
    JSON object."""
    try:
        return load_object(path)
    except (OSError, Unreadable):
        return None


def check_schema(data: dict[str, Any], schema: int) -> None:
    """Unreadable unless the JSON *data* of a file has the schema number *schema*, the one this version reads:
    NEWER for a higher one."""
    found = data.get("schema")
    if isinstance(found, (int, float)) and not isinstance(found, bool) and found > schema:
        raise Unreadable(NEWER)
    if found != schema:
        raise Unreadable("damaged: unknown schema")


def _say(line: str) -> None:
    """*line* on stderr, where there is one (a window started without a console has none)."""
    stream = sys.stderr
    if stream is None:
        return
    try:
        try:
            print(line, file=stream, flush=True)
        except UnicodeEncodeError:  # a console that cannot show the name in the path
            encoding = getattr(stream, "encoding", None) or "ascii"
            print(line.encode(encoding, "backslashreplace").decode(encoding, "replace"), file=stream, flush=True)
    except (OSError, ValueError, LookupError):
        pass


def _move_new(source: Path, target: Path) -> None:
    """Move *source* to *target*, never over a file there (FileExistsError). Windows refuses that by itself; elsewhere
    a rename would replace it, so the file first gets the new name as a second link."""
    if os.name == "nt":
        os.rename(source, target)
        return
    try:
        os.link(source, target)
    except (FileExistsError, FileNotFoundError):
        raise
    except OSError:  # a file system without hard links
        if os.path.lexists(target):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target)) from None
        os.rename(source, target)
        return
    try:
        os.unlink(source)
    except FileNotFoundError:
        pass  # another process set it aside meanwhile: the copy is made all the same


class SetAside(NamedTuple):
    """A file a store set aside because this Windows user cannot open it here (`set_aside`, NOT_HERE): where it was,
    and the copy it is now."""

    path: Path
    copy: Path


_set_aside: list[SetAside] = []
_set_aside_lock = threading.Lock()


def take_set_aside() -> list[SetAside]:
    """The files set aside as NOT_HERE in this process since the last call (the latest `SET_ASIDE_KEPT`), oldest
    first, and the list emptied: what the window says once (`ui.jobs`)."""
    with _set_aside_lock:
        taken = list(_set_aside)
        _set_aside.clear()
    return taken


def set_aside(path: Path, reason: str) -> Path | None:
    """Move the file at *path*, which a store could not read for *reason* (a few words, never anything the file
    holds), out of the way before anything is written there: to ``<stem>.unreadable-<YYYYmmdd-HHMMSS>.json`` beside
    it, ``-2``, ``-3`` ... after the time when that is taken (never over an earlier copy), with one line on stderr
    that says so (for NOT_HERE, what to do: `NOT_HERE_ADVICE`; the file is also kept for `take_set_aside`). The copy is
    the very file, moved: nothing of it is read, changed or deleted. Returns the copy; None when the file is gone
    already (another process set it aside). OSError when it cannot be moved: then nothing may be written in its place
    either."""
    when = time.strftime("%Y%m%d-%H%M%S")
    for n in range(1, COPY_TRIES + 1):
        copy = path.with_name(f"{path.stem}.unreadable-{when}{'' if n == 1 else f'-{n}'}.json")
        try:
            _move_new(path, copy)
        except FileExistsError:
            continue
        except FileNotFoundError:
            return None
        advice = f"; {NOT_HERE_ADVICE}" if reason == NOT_HERE else ""
        _say(f"{path} could not be read ({reason}); kept as {copy}{advice}")
        if reason == NOT_HERE:
            with _set_aside_lock:
                _set_aside.append(SetAside(path, copy))
                del _set_aside[:-SET_ASIDE_KEPT]
        return copy
    raise FileExistsError(errno.EEXIST, f"no free name for a copy of {path.name} beside it", str(path))


# --- which file is a name's -----------------------------------------------------------------------------------

def _key(language: str | None) -> str:
    return "" if language is None else language_key(language)


def owns(stored: Owner, me: Owner) -> bool:
    """True when a file that records *stored* is the file of *me* (an exact name and a language key): the same name
    exactly and the same language key, where what the file does not record (None) matches anything."""
    return all(have is None or have == want for have, want in zip(stored, me))


def _who(owner: Owner) -> str:
    return repr(owner[0]) if owner[0] is not None else "a name it does not record"


def pick(folder: Path, name: str, language: str | None, owner_of: OwnerOf, what: str = "the data") -> Path:
    """The file of *name* in *language* (None in a store without languages) in *folder*: the plain name
    (`file_names`) when it holds this very name (the language by its key), else the hashed name when that one does;
    else the plain name when there is no such file, it records no name, or it is too damaged to tell whose it is;
    else the hashed name. FileExistsError when both hold other names (two names with the same hash). Reads two
    files at most; never renames one, and never gives a copy kept beside them (`is_copy`)."""
    plain_name, hashed_name = file_names(name, language)
    plain, hashed = folder / plain_name, folder / hashed_name
    me = (name, _key(language))
    there = owner_of(plain)
    if there == me:
        return plain
    other = owner_of(hashed)
    if other == me:
        return hashed
    if there is None or owns(there, me):  # no file, one too damaged to tell whose it is, or one that records no name
        return plain
    if other is None or owns(other, me):
        return hashed
    raise FileExistsError(f"{plain} holds {what} of {_who(there)} and {hashed} that of {_who(other)}, whose names "
                          f"give the same file names as {name!r}; move one of them out of {folder}")


def claim(path: Path, name: str, language: str | None, owner_of: OwnerOf, what: str = "the data") -> Path:
    """Where the file of *name*, opened at *path*, is saved: at *path*, unless that is one of the name's two file
    names and now holds another name (two names that give one file name, both opened while it was free, the other
    saved first); then where `pick` puts it. Any other path is the caller's choice and stays as it is."""
    plain, hashed = file_names(name, language)
    if os.path.normcase(path.name) not in (os.path.normcase(plain), os.path.normcase(hashed)):
        return path
    there = owner_of(path)
    if there is None or owns(there, (name, _key(language))):
        return path
    return pick(path.parent, name, language, owner_of, what)


def is_listed(path: Path, name: str, language: str | None, owner_of: OwnerOf) -> bool:
    """True when *path*, a file that records *name* in *language*, is the file `pick` gives that name: its plain
    file name, or its hashed one while the plain file is not that name's; not a copy kept beside them, nor a stale
    second file (on Windows whatever the letter case of the name on disk)."""
    plain, hashed = file_names(name, language)
    on_disk = os.path.normcase(path.name)
    if on_disk == os.path.normcase(plain):
        return True
    return on_disk == os.path.normcase(hashed) and owner_of(path.with_name(plain)) != (name, _key(language))


def files_of(folder: Path, name: str, owner_of: OwnerOf, any_language: bool = True) -> list[Path]:
    """What *folder* keeps of *name*, in every language: each file whose name starts with the name's slug and that
    records exactly this name (under either name `pick` gives, a copy kept beside them, a stale second file), in the
    order of their file names. A file that records no name, or cannot be read, counts only under one of the name's
    own two file names, or as a copy set aside from one of them (`set_aside`, `is_copy`): in any language with
    *any_language*, else only without a language part. Another name that starts the same ("Pennant" for "Pe") or
    gives the same file name ("Pebble:Harbor" for "Pebble Harbor") keeps its files. What `delete_files` deletes."""
    slug = slugify(name)
    language_part = r"(?:\.[\w-]+)?" if any_language else ""
    own = re.compile(re.escape(os.path.normcase(slug)) + f"(?:-{name_hash(name)})?" + language_part
                     + r"(?:\." + _COPY_PART + r")?\.json")
    found: list[Path] = []
    for path in sorted(folder.glob(glob.escape(slug) + "*.json")):
        there = owner_of(path)
        if there is None or there[0] is None:
            if not own.fullmatch(os.path.normcase(path.name)):
                continue
        elif there[0] != name:
            continue  # another name that starts the same, or gives the same file name
        found.append(path)
    return found


def leftovers(path: Path) -> list[Path]:
    """What a save of the file at *path* that stopped halfway may have left beside it: its temporary files (they hold
    the same data), as `atomic.write_atomic` names them, and the fixed ``<file>.tmp`` of earlier versions."""
    return [*path.parent.glob(glob.escape(path.name) + ".*.tmp"), path.with_name(path.name + ".tmp")]


def drop_leftovers(path: Path) -> None:
    """Delete `leftovers` of the file at *path*; one that a save of another process still has open stays."""
    for leftover in leftovers(path):
        try:
            leftover.unlink(missing_ok=True)
        except OSError:
            pass


def delete_files(folder: Path, name: str, owner_of: OwnerOf, any_language: bool = True) -> bool:
    """Delete what *folder* keeps of *name*, in every language (`files_of`: the files that record exactly this name,
    under either name `pick` gives, and the copies kept beside them), with what a save that stopped halfway left
    beside each (`leftovers`: its temporary files hold the same data). A file that records no name, or cannot be
    read, goes only under one of the name's own two file names, or as a copy set aside from one of them; another
    name that starts the same ("Pennant" for "Pe") or gives the same file name ("Pebble:Harbor" for "Pebble Harbor") keeps its
    files. Returns True when a file was deleted."""
    deleted = False
    for path in files_of(folder, name, owner_of, any_language):
        path.unlink()
        deleted = True
        drop_leftovers(path)
    return deleted


@dataclass(frozen=True)
class StoreFiles:
    """The files of a store whose JSON records whose each one is: the exact name under *name_field* and, in a store
    with target languages, the language under *language_field* (None in a store without languages). With *schema*,
    a file must have that schema number (`check_schema`); with *kind*, a file that says what kind it is must say
    that one."""

    what: str  # what a file holds, for messages: "the series sheet"
    name_field: str
    language_field: str | None = None
    schema: int | None = None  # the schema number this version reads; a higher one is a newer TASlation's
    kind: str | None = None  # what the "kind" field of a file of this store says, where there is one

    def recorded(self, data: dict[str, Any]) -> Owner:
        """Whose the file with JSON *data* is: its exact name and language key, None for what it does not record (a
        field that is missing or not a string); the language key is "" in a store without languages."""
        name = data.get(self.name_field)
        exact = name if isinstance(name, str) else None
        if self.language_field is None:
            return exact, ""
        language = data.get(self.language_field)
        return exact, language_key(language) if isinstance(language, str) else None

    def owner_of(self, path: Path) -> Owner | None:
        """Whose the file at *path* is (`recorded`); None when there is no such file or it cannot be read."""
        data = read_object(path)
        return None if data is None else self.recorded(data)

    def check(self, data: dict[str, Any]) -> None:
        """Unreadable when a file with JSON *data* is not one this version reads as this store's: another schema
        number (NEWER for a higher one, `check_schema`), or another kind."""
        if self.schema is not None:
            check_schema(data, self.schema)
        if self.kind is not None and "kind" in data and data["kind"] != self.kind:
            raise Unreadable("another kind of file")

    def pick(self, folder: Path, name: str, language: str | None = None) -> Path:
        """The file of *name* in *language* (`pick`)."""
        return pick(folder, name, language, self.owner_of, self.what)

    def claim(self, path: Path, name: str, language: str | None = None) -> Path:
        """Where the file of *name*, opened at *path*, is saved (`claim`). A file there that this version cannot
        read (one written since it was opened: no JSON object, another kind, a newer TASlation's) is set aside first
        (`set_aside`), never written over. OSError when that file cannot be opened or moved."""
        target = claim(path, name, language, self.owner_of, self.what)
        try:
            data = load_object(target)
            if data is not None:
                self.check(data)
        except Unreadable as e:
            set_aside(target, e.reason)
        return target

    def load(self, path: Path, name: str, language: str | None,
             parse: Callable[[dict[str, Any]], T]) -> tuple[T, Owner] | None:
        """What the file at *path* (where `pick` put *name*) holds, as *parse* takes it from the file's JSON object,
        and whose the file says it is. None when there is no such file, or when there is one this version cannot
        read: no JSON object, another schema number (`NEWER` for a higher one) or kind (`check`), or one *parse*
        refuses (ValueError, TypeError, KeyError and the like). Such a file is set aside first (`set_aside`), so that
        nothing is ever written over it, and the caller starts afresh. FileExistsError when the file holds another
        name (another process saved one there since `pick` looked): it is never read as this name's, nor moved. A
        file that records no name (or no language) is this name's; the caller gives it the name to save. OSError
        when the file cannot be opened or set aside."""
        try:
            data = load_object(path)
            if data is None:
                return None
            owner = self.recorded(data)
            if not owns(owner, (name, _key(language))):
                raise FileExistsError(f"{path} holds {self.what} of {_who(owner)}, not that of {name!r}")
            self.check(data)
            try:
                return parse(data), owner
            except Unreadable:
                raise
            except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, RecursionError):
                raise Unreadable(DAMAGED) from None
        except Unreadable as e:
            set_aside(path, e.reason)
            return None

    def listed(self, path: Path, data: dict[str, Any]) -> bool:
        """True when *path*, holding *data*, is the file `pick` gives the name it records (`is_listed`), or records
        no name (it is listed as it is); a copy kept beside a file is not, nor one set aside (`is_copy`)."""
        if is_copy(path):
            return False
        name, language = self.recorded(data)
        if name is None or language is None:
            return True
        return is_listed(path, name, None if self.language_field is None else language, self.owner_of)

    def delete(self, folder: Path, name: str) -> bool:
        """Delete the files of *name* in every language, with the copies set aside from them (`delete_files`)."""
        return delete_files(folder, name, self.owner_of, any_language=self.language_field is not None)


__all__ = [
    "DAMAGED", "NEWER", "NOT_HERE", "WINDOWS_DEVICES", "Owner", "OwnerOf", "SetAside", "StoreFiles", "Unreadable",
    "check_schema", "claim", "delete_files", "drop_leftovers", "file_names", "files_of", "is_copy", "is_listed",
    "language_key", "leftovers", "load_object", "name_hash", "owns", "pick", "read_object", "set_aside", "slugify",
    "take_set_aside",
]
