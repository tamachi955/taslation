"""Encrypted export and import of what TASlation keeps of the reader's books: their own translations, page
information and series sheets, for their own backup or their other computer. Without the passphrase the file is
unreadable; the format is public and holds no secret, so its strength is the passphrase's alone.

The file is a first line ``TASLATION-CACHE-1`` and one JSON object::

    {"kdf": {"name": "scrypt", "n": 131072, "r": 8, "p": 1}, "salt": base64, "nonce": base64, "data": base64}

The key is scrypt over the passphrase (every space character an ordinary space, then Unicode NFC, in UTF-8: the
mapping of RFC 8265's OpaqueString, so the same words typed on another computer, or with the full-width space of a
Japanese input method, give the same key; control characters are refused) with a random 16-byte salt and those
parameters, 32 bytes long. ``data`` is AES-256-GCM, with a random 12-byte nonce, over the payload's JSON
compressed with zlib; the associated data is the first line and the
header (the object without ``data``, keys sorted, no spaces), so neither can be changed unnoticed. The books'
titles, models and languages are inside the encrypted JSON only. AES-GCM comes from the optional ``cryptography``
package (``pip install cryptography``); scrypt comes with Python.

The payload (what the passphrase opens) has a version of its own, its ``schema`` (`PAYLOAD_SCHEMA`). Version 1,
written until 2026-11-16, is one cache file's JSON as the cache store saves it (its ``schema``, the cache's, is 1):
one book in one language. Version 2 is a bundle of one book or several::

    {"schema": 2, "app": "taslation", "kind": "export", "note": ...,
     "books": [{"cache": <a cache's JSON>, "annotations": <index>, "sheet": <index>, "defaults": <index>}, ...],
     "annotations": [<a book's page information, as its store saves it>, ...],
     "sheets": [<a series sheet in one language, as its store saves it>, ...],
     "defaults": [<a series' defaults, as their store saves them>, ...]}

Each entry of ``books`` is one book's cache in one language, with the index of the book's page information
(`annotations.BookAnnotations`: regions added and ignored, the areas ignored on every page, the book's settings and
reading direction, the speakers and kinds of its regions and their formatting), of the series sheet in that
language (`annotations.Glossary`, the one the book reads: `notes.sheet_key`) and of its series' defaults
(`annotations.SeriesDefaults`: the settings, reading direction and areas a new volume of the series starts from, the
file of `series_id(series_of(book))`) when there are such files; several volumes of a series share one sheet and one
file of defaults, several languages of a book its page information. Each part is the plain JSON its store would save,
read through the store's own loader (so the protection of the file is undone, `protect.py`) and written on import by
the store's own save (so it is protected again); nothing is added to what those files hold. The version before reads
a bundle's ``schema`` 2 as a cache of a newer TASlation and refuses it with that sentence (`UnreadableExport`); this
version reads both, and refuses a later one the same way.

``defaults`` (the list, and the index in a book's entry) came to schema 2 after it was first written, on 2026-11-16,
before any release carried schema 2: both are optional, a bundle without them is read as one whose series have no
defaults, and a reader of schema 2 that does not know them leaves them alone (it reads only the keys it knows), so
the schema number stayed 2.

Reading a file trusts nothing in it before the tag is checked: a file larger than an export can be is refused
before it is read, a header with other fields or with scrypt parameters costing more than twice what this
version writes before any key is derived, and nothing is unpacked before the tag holds. What the passphrase
opens is checked too (it may come from someone else): per book at most MAX_PAGES pages (a cache is one book's, and a
volume has some 200; the file size cap alone would let in some 500,000) of at most MAX_BUBBLES_PER_PAGE bubbles
each, at most MAX_BOOKS books and MAX_TOTAL_PAGES pages in one file, page information, sheets and series' defaults
within the bounds their stores read, every page readable, no number that is not finite, the strings without control
characters, a book's series' defaults those of its own series, and each book's cache file must be that book's, never
another one whose name gives the same file. An export over those caps is
refused the same way, and so is one whose payload would unpack to more than MAX_PAYLOAD (some 200 volumes of 200
pages): a library larger than that goes in several files, a series or a few at a time.

The export is the one form of these files that moves to another computer or Windows user: the files themselves are
protected for the Windows user who saved them, on that computer (`protect.py`), and an export protected so would open
nowhere else. It is written with `write_atomic` as it is, its passphrase its only protection; an import is saved
through the stores, and so protected like every file of theirs.

An import (`open_export`, then `plan_import` to see what it would do, then `apply_import`) takes all of a file or the
books chosen of it. A book's pages join its cache here the way saves merge (the file's page in place of the same page
here, the others kept), but a translation a person wrote here (`CachedBubble.edited`) stays where the file's line for
that bubble (matched by box, as the pipeline matches) is none of a person's, unless the file is to be taken as it is;
with *replace* the file replaces the book's cache, header and all. The book's page information is added where it has
none here; where it has some, the reader's own stays unless they take the file's. The series sheet is added where the
series has none here in that language; otherwise the file's sheet joins it as a rename joins two sheets
(`annotations.compare_sheets`, `apply_review`): what it adds is taken over, and where the two say otherwise the sheet
here keeps its value unless the reader answered to take the file's. A series' defaults are added where the series has
none here (or empty ones); where it has others, the reader's stay unless they take the file's (its whole file: the
defaults are a few values that belong together). Every file an import changes is kept beside as it was,
``<file>.before-import.<date>.json``. Everything is read and checked before anything is written.

The short lines a cache keeps for reuse (`linememo`: keyed hashes of the lines, the book's secret for them, and
their translations; never the Japanese) are part of its JSON, so they travel in the export with the pages: an import
that merges adds them where the cache has nothing for the line (`LineMemo.join`), one that replaces takes them as
they are.

Every refusal is a BackupError with a sentence for the reader; a window tells the kinds apart by class:
WrongPassphrase, BrokenPassphrase, UnreadableExport (from a newer TASlation), TooLarge, LibraryMissing, and
plain BackupError for a damaged file. NameClash, an OSError, is the file of a book or a series that holds another.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from . import protect
from .atomic import write_atomic
from .locate_large import follow

if TYPE_CHECKING:
    from .annotations import (AnnotationStore, BookAnnotations, Conflict, Glossary, GlossaryStore, Review,
                              SeriesDefaults, SeriesDefaultsStore)
    from .cache import BookCache, CachedPage, CacheStore

MAGIC = b"TASLATION-CACHE-1"
OLD_MAGICS = (b"SELFTRANS-CACHE-1",)  # the same format under the project's former name: still read, never written
_MAGIC_ANY = re.compile(rb"TASLATION-CACHE-([0-9]{1,9})")  # the first line of any version's export
SUFFIX = ".stcache"  # what the window suggests for an export file
KDF: dict[str, Any] = {"name": "scrypt", "n": 2 ** 17, "r": 8, "p": 1}  # 128 MiB, about half a second
MIN_PASSPHRASE = 12
PASSPHRASE_ENV = "TASLATION_PASSPHRASE"  # the command line takes the passphrase from here when set (scripts)
SALT_BYTES, NONCE_BYTES, KEY_BYTES, TAG_BYTES = 16, 12, 32, 16
MAX_SALT = 64
# scrypt parameters a file may ask for: at most twice the memory and the work of KDF, each lane and block small
MAX_KDF_MEMORY = 2 * 128 * 8 * (2 ** 17 + 1 + 2)  # twice what KDF allocates, 128 * r * (n + p + 2) bytes
MAX_KDF_WORK = 2 * 2 ** 17 * 8 * 1  # twice KDF's n * r * p
MAX_KDF_R, MAX_KDF_P = 32, 16
MAX_PAYLOAD = 64 << 20  # the most a file unpacks to: some 200 times the cache of a 200-page volume
MAX_FILE = MAX_PAYLOAD // 2 * 3  # the largest file such a payload makes (base64 of it compressed, the tag, the header)
MAX_NAME = 1024  # characters in the book's name, the model's, the language's and the dates
MAX_PAGES = 5000  # pages one book's cache in an export may hold: a cache is one book's, and a volume has some 200
MAX_BUBBLES_PER_PAGE = 500  # bubbles one page may hold, far more than a page of a book has
MAX_BOOKS = 1000  # caches (a book in one language each) one export may hold; so many page informations and sheets too
MAX_TOTAL_PAGES = 100_000  # pages of all of them together: some 500 volumes of 200 pages, more than MAX_PAYLOAD lets in
PAYLOAD_SCHEMA = 2  # the payload's version this one writes (1: a cache's JSON alone, still read; see the docstring)
PAYLOAD_NOTE = ("The reader's own translations, page information, series sheets and series defaults of the books "
                "listed, for their own computers. No page images, no page text.")
MATCH_IOU = 0.4  # a bubble of the file is the one here whose box it overlaps so much (`config.Settings.match_min_iou`)
INSTALL_HINT = "the encrypted export needs the cryptography package: pip install cryptography"
_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")  # what a terminal would act on rather than show
_CONTROLS_BUT_LINES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")  # the same, tab and newline kept (translations)


class BackupError(ValueError):
    """What went wrong, in a sentence for the reader."""


class LibraryMissing(BackupError):
    """The cryptography package is not installed."""


class WrongPassphrase(BackupError):
    """The tag does not hold: not the passphrase the file was written with, or the file was changed since."""


class BrokenPassphrase(BackupError):
    """The passphrase holds half a character or a control character, so no key is made from it."""


class UnreadableExport(BackupError):
    """The passphrase opens the file, but it holds what this version cannot read (it likely comes from a newer
    TASlation); nothing is imported, so that nothing of it is lost."""


class TooLarge(BackupError):
    """More than TASlation writes or reads back: a cache over the cap, a file larger than any export, one that
    unpacks to more, or one with more pages (or bubbles on a page) than one book's cache has."""


class NameClash(FileExistsError):
    """No cache file for the imported book: both names its file can have hold other books (two names with one
    hash), or another process gave its file to another book meanwhile."""


def _aesgcm() -> Any:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise LibraryMissing(INSTALL_HINT) from e
    return AESGCM


def require() -> None:
    """Raise LibraryMissing, with the install hint, when the cryptography package is not installed."""
    _aesgcm()


def _normal(passphrase: str) -> str:
    """The passphrase as the key sees it (the mapping of RFC 8265's OpaqueString): a character outside the BMP whole
    again (getpass on Windows reads one as its two UTF-16 halves, the window gets it whole), every space character
    (Unicode Zs: the full-width space of a Japanese input method, a no-break space) the ordinary one, then NFC.
    BrokenPassphrase for half a character or a control character (Cc), without the passphrase in it or in its
    context."""
    try:
        joined: str | None = passphrase.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    except UnicodeError:
        joined = None
    if joined is None:
        raise BrokenPassphrase("the passphrase holds a broken character; type it again")
    if any(unicodedata.category(c) == "Cc" for c in joined):
        raise BrokenPassphrase("the passphrase holds a control character (a tab, a line break); type it again")
    spaced = "".join(" " if unicodedata.category(c) == "Zs" else c for c in joined)
    return unicodedata.normalize("NFC", spaced)


def passphrase_length(passphrase: str) -> int:
    """The characters of *passphrase* as the key sees them (`_normal`: a character outside the BMP is one, a letter
    with its accent typed apart is one after NFC), the count check_passphrase holds against MIN_PASSPHRASE; a window
    shows it as the reader types. BrokenPassphrase for a broken one."""
    return len(_normal(passphrase))


def check_passphrase(passphrase: str) -> None:
    """BackupError unless *passphrase* makes a key: at least MIN_PASSPHRASE characters as the key sees them
    (`passphrase_length`), BrokenPassphrase for a broken one."""
    if passphrase_length(passphrase) < MIN_PASSPHRASE:
        raise BackupError(f"the passphrase must be at least {MIN_PASSPHRASE} characters")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _kdf_memory(n: int, r: int, p: int) -> int:
    """The bytes scrypt allocates for these parameters (OpenSSL: the blocks of every lane and the table)."""
    return 128 * r * (n + p + 2)


def _kdf_ok(kdf: Any) -> bool:
    """True for scrypt parameters this version derives a key with: the same fields as KDF, whole numbers, n a power
    of two, and no more than MAX_KDF_MEMORY and MAX_KDF_WORK (a file's header could otherwise ask for gigabytes and
    minutes before its tag is even looked at)."""
    if not isinstance(kdf, dict) or set(kdf) != {"name", "n", "r", "p"} or kdf["name"] != "scrypt":
        return False
    n, r, p = kdf["n"], kdf["r"], kdf["p"]
    if not all(type(v) is int for v in (n, r, p)):
        return False
    return (n >= 2 and (n & (n - 1)) == 0 and 1 <= r <= MAX_KDF_R and 1 <= p <= MAX_KDF_P
            and n * r * p <= MAX_KDF_WORK and _kdf_memory(n, r, p) <= MAX_KDF_MEMORY)


def _key(passphrase: str, salt: bytes, kdf: dict[str, Any]) -> bytes:
    secret = _normal(passphrase).encode("utf-8")
    n, r, p = kdf["n"], kdf["r"], kdf["p"]
    return hashlib.scrypt(secret, salt=salt, n=n, r=r, p=p, maxmem=_kdf_memory(n, r, p) + (1 << 20), dklen=KEY_BYTES)


def _associated(header: dict[str, Any]) -> bytes:
    return MAGIC + b"\n" + json.dumps(header, sort_keys=True, separators=(",", ":")).encode("ascii")


def encrypt(payload: bytes, passphrase: str) -> bytes:
    """*payload* compressed and encrypted with *passphrase*: the bytes of an export file."""
    aesgcm = _aesgcm()
    check_passphrase(passphrase)
    if len(payload) > MAX_PAYLOAD:
        raise TooLarge("the cache is larger than TASlation reads back; it cannot be exported")
    kdf = dict(KDF)
    if not _kdf_ok(kdf):  # never write a file this version would refuse to read
        raise BackupError("the scrypt parameters are outside what TASlation reads back")
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    header = {"kdf": kdf, "salt": _b64(salt), "nonce": _b64(nonce)}
    sealed = aesgcm(_key(passphrase, salt, kdf)).encrypt(nonce, zlib.compress(payload, 9), _associated(header))
    return MAGIC + b"\n" + json.dumps({**header, "data": _b64(sealed)}).encode("ascii") + b"\n"


def _parse(blob: bytes) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    """The header, salt, nonce and sealed data of an export file: exactly the fields an export has, its scrypt
    parameters within bounds. UnreadableExport for the first line of a later version of the format."""
    newline = blob.find(b"\n")
    first = blob[:newline].strip() if newline >= 0 else b""
    if first != MAGIC and first not in OLD_MAGICS:
        version = _MAGIC_ANY.fullmatch(first)
        if version and int(version.group(1)) > int(MAGIC.rsplit(b"-", 1)[1]):
            raise UnreadableExport("the file comes from a newer version of TASlation, which this one cannot read")
        raise BackupError("not a TASlation cache export")
    try:
        obj = json.loads(blob[newline + 1:].decode("ascii"))
        if not isinstance(obj, dict) or set(obj) != {"kdf", "salt", "nonce", "data"} or not _kdf_ok(obj["kdf"]):
            raise ValueError("not the header of an export")
        salt, nonce, sealed = (base64.b64decode(obj[k], validate=True) for k in ("salt", "nonce", "data"))
    except (ValueError, KeyError, TypeError, AttributeError, binascii.Error, RecursionError, MemoryError):
        raise BackupError("damaged file") from None
    if not SALT_BYTES <= len(salt) <= MAX_SALT or len(nonce) != NONCE_BYTES or len(sealed) < TAG_BYTES:
        raise BackupError("damaged file")
    return {"kdf": obj["kdf"], "salt": obj["salt"], "nonce": obj["nonce"]}, salt, nonce, sealed


def _inflate(packed: bytes) -> bytes:
    """The payload: one zlib stream of at most MAX_PAYLOAD bytes, unpacked no further than that, nothing after it."""
    unpack = zlib.decompressobj()
    try:
        payload = unpack.decompress(packed, MAX_PAYLOAD + 1)
    except zlib.error:
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation unpacks") from None
    if len(payload) > MAX_PAYLOAD or unpack.unconsumed_tail:
        raise TooLarge("the file is larger than TASlation unpacks")
    if not unpack.eof or unpack.unused_data:
        raise BackupError("damaged file")
    return payload


def decrypt(blob: bytes, passphrase: str) -> bytes:
    """The payload of an export file. WrongPassphrase for a wrong passphrase (or a changed byte: the tag cannot
    tell them apart), BrokenPassphrase, UnreadableExport for a later format, TooLarge, BackupError for a damaged
    file, LibraryMissing without the cryptography package."""
    aesgcm = _aesgcm()
    from cryptography.exceptions import InvalidTag

    _normal(passphrase)  # a broken passphrase says so, not "damaged file"
    header, salt, nonce, sealed = _parse(blob)
    try:
        key = _key(passphrase, salt, header["kdf"])
    except (ValueError, MemoryError, OverflowError):  # parameters OpenSSL refuses, or memory there is not
        raise BackupError("damaged file") from None
    try:
        packed = aesgcm(key).decrypt(nonce, sealed, _associated(header))
    except InvalidTag:
        raise WrongPassphrase("wrong passphrase or damaged file") from None
    return _inflate(packed)


def cache_file(store: CacheStore, book: str, language: str = "English") -> Path:
    """The cache file of *book* in *language*; BackupError when there is none."""
    try:
        source: Path | None = store.path_for(book, language)
    except FileExistsError:  # both names its file can have hold other books: there is none of this one
        source = None
    if source is None or not source.is_file():
        others = sorted({b["language"] for b in store.list() if b["book"] == book})
        raise BackupError(f"no cache for {book!r} in {language}"
                          + (f"; it has one in {', '.join(others)}" if others else " (see `taslation cache list`)"))
    return source


def _parts(stores: Any) -> tuple["CacheStore", "AnnotationStore | None", "GlossaryStore | None"]:
    """The cache store, the store of page information and the store of series sheets of *stores* (`rename.Stores`),
    or a `cache.CacheStore` alone: then an export carries the caches alone, and an import takes nothing else."""
    if hasattr(stores, "cache_dir"):
        return stores, None, None
    return stores.cache, getattr(stores, "annotations", None), getattr(stores, "sheets", None)


def _defaults_store(marks_store: "AnnotationStore | None") -> "SeriesDefaultsStore | None":
    """Where the series' defaults are kept: the folder of them in the store of page information (`AnnotationStore.series`);
    None without one (a store that keeps none: an export carries none, an import takes none)."""
    return getattr(marks_store, "series", None) if marks_store is not None else None


class _LeftOut(Exception):
    """A file of page information or a series sheet that cannot be read here (another Windows user's or computer's,
    damaged, a newer TASlation's, held by another program now)."""


def _part(files: Any, path: Path, name: str, language: str | None, parse: Any) -> Any:
    """What the store file at *path*, the file of *name* (in *language*; None in a store without languages), holds as
    its store's loader reads it (*parse* of its JSON, `names.load_object`: opened when it is protected); None when there
    is no such file or it is another name's. _LeftOut when it cannot be read here. Nothing is written (a store's own
    `open` would set such a file aside)."""
    from .names import Unreadable, language_key, load_object, owns

    try:
        data = load_object(path)
        if data is None:
            return None
        if not owns(files.recorded(data), (name, "" if language is None else language_key(language))):
            return None
        files.check(data)
        return parse(data)
    except (Unreadable, OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError,
            RecursionError):
        raise _LeftOut from None


def _marks_here(store: "AnnotationStore", book: str) -> tuple[Path | None, "BookAnnotations | None"]:
    """Where the page information of *book* is in *store* (None: both its file names hold other books) and what it
    holds (None: none, or nothing at all: no page, setting, sequence, reading direction or area); _LeftOut when it cannot
    be read here."""
    from .annotations import ANNOTATION_FILES, BookAnnotations

    try:
        path = store.path_for(book)
    except FileExistsError:
        return None, None
    found = _part(ANNOTATION_FILES, path, book, None, lambda data: BookAnnotations.from_json(data, path))
    if found is not None:
        found.book = book
    return path, found


def _marks_empty(ann: "BookAnnotations") -> bool:
    return not (len(ann) or ann.settings or ann.sequence or ann.reading_direction or ann.areas)


def _sheet_here(store: "GlossaryStore", series: str, language: str) -> tuple[Path | None, "Glossary | None"]:
    """Where the sheet of *series* in *language* is in *store* (None: both its file names hold other series) and what
    it holds (None: none); _LeftOut when it cannot be read here. A sheet that records no language is the one asked for,
    as the store opens it."""
    from .annotations import SHEET_FILES, Glossary

    try:
        path = store.path_for(series, language)
    except FileExistsError:
        return None, None

    def parse(data: dict[str, Any]) -> "Glossary":
        sheet = Glossary.from_json(data, path)
        sheet.series = series
        if not isinstance(data.get("language"), str):
            sheet.language = language
        return sheet

    return path, _part(SHEET_FILES, path, series, language, parse)


def _defaults_here(store: "SeriesDefaultsStore", series: str) -> tuple[Path | None, "SeriesDefaults | None"]:
    """Where the defaults of *series* are in *store* (None: both their file names hold other series) and what they
    hold (None: none), as the store opens them (the series as written here, its key); _LeftOut when the file cannot be
    read here."""
    from .annotations import SERIES_DEFAULT_FILES, SeriesDefaults, series_id
    from .bookname import clean_series

    key = series_id(series)
    try:
        path = store.path_for(series)
    except FileExistsError:
        return None, None

    def parse(data: dict[str, Any]) -> "SeriesDefaults":
        defaults = SeriesDefaults.from_json(data, path)
        defaults.series, defaults.key = clean_series(series), key
        return defaults

    return path, _part(SERIES_DEFAULT_FILES, path, key, None, parse)


def _same_defaults(a: "SeriesDefaults", b: "SeriesDefaults") -> bool:
    """Whether two series' defaults hold the same values: settings, reading direction, and the same areas in any
    order (the series as written and the date aside)."""
    return (a.settings == b.settings and a.reading_direction == b.reading_direction
            and len(a.areas) == len(b.areas) and set(a.areas) == set(b.areas))


@dataclass
class Exported:
    """What an export wrote: the books (a cache in one language each) and their pages, the files of page information,
    the series sheets and the series' defaults that went with them, and how many such files could not be read here and
    were left out."""

    books: int = 0
    pages: int = 0
    annotations: int = 0
    sheets: int = 0
    left_out: int = 0
    defaults: int = 0


def _no_store_file(out: Path, folders: Iterable[tuple[Path, str]]) -> None:
    """BackupError when *out* would take the place of a file of one of the stores' *folders* (each with what its files
    are: "a cache in the cache folder")."""
    for folder, what in folders:
        if out.suffix.lower() == ".json" and out.resolve().parent == Path(folder).resolve():
            raise BackupError(f"{out} would take the place of {what}; write the export somewhere else")


def export_books(stores: Any, books: Sequence[tuple[str, str]], path: Path | str, passphrase: str) -> Exported:
    """Write the caches of *books* ((book, language) pairs; one given twice is written once) to *path*, encrypted with
    *passphrase*, in one file: with *stores* a `rename.Stores`, each with the book's page information, the series
    sheet the book reads in that language and its series' defaults, where it has such files (defaults that hold
    nothing are no file to carry); a `cache.CacheStore` alone carries the caches alone. The file appears whole or not
    at all (written beside it first, readable by its owner only where the system has such permissions). BackupError
    (TooLarge over the caps), and nothing written, when a book has no cache in its language or it cannot be read, or
    the books are more than one file takes; a file of page information, a sheet or a series' defaults that cannot be
    read here is left out of the file and counted (`Exported.left_out`)."""
    from .annotations import series_id, series_of
    from .cache import BookCache, language_key
    from .notes import sheet_key

    require()
    check_passphrase(passphrase)
    out = Path(path)
    if out.is_dir():
        raise BackupError(f"{out} is a folder; give the name of the file to write")
    cache_store, marks_store, sheet_store = _parts(stores)
    defaults_store = _defaults_store(marks_store)
    wanted: dict[tuple[str, str], tuple[str, str]] = {}
    for book, language in books:
        wanted.setdefault((book, language_key(language)), (book, language))
    if not wanted:
        raise BackupError("nothing to export")
    if len(wanted) > MAX_BOOKS:
        raise TooLarge(f"more than {MAX_BOOKS} books cannot go in one file; export fewer at a time")
    sources = [(book, language, cache_file(cache_store, book, language)) for book, language in wanted.values()]
    if any(out.resolve() == source.resolve() for _book, _language, source in sources):
        raise BackupError(f"{out} is the cache itself; write the export somewhere else")
    _no_store_file(out, [(cache_store.cache_dir, "a cache in the cache folder"),
                         *([(marks_store.annotations_dir, "a book's page information in its folder")] if marks_store
                           else []),
                         *([(sheet_store.glossary_dir, "a series sheet in its folder")] if sheet_store else [])])
    done = Exported()
    entries: list[dict[str, Any]] = []
    marks: list[dict[str, Any]] = []
    sheets: list[dict[str, Any]] = []
    defaults: list[dict[str, Any]] = []
    marks_at: dict[str, int | None] = {}  # book -> its page information's index (None: it has none)
    sheets_at: dict[tuple[str, str], int | None] = {}  # (series, language key) -> its sheet's index
    defaults_at: dict[str, int | None] = {}  # a series' key (`series_id`) -> the index of its defaults
    for book, _language, source in sources:
        try:
            cache = BookCache.load(source)
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as e:
            raise BackupError(f"the cache of {book!r} cannot be read: {e}") from None
        if len(cache.pages) > MAX_PAGES or any(len(page.bubbles) > MAX_BUBBLES_PER_PAGE for page in cache.pages):
            raise TooLarge(f"the cache of {book!r} holds more than TASlation imports (at most {MAX_PAGES} pages of at "
                           f"most {MAX_BUBBLES_PER_PAGE} bubbles); it cannot be exported")
        done.pages += len(cache)
        if done.pages > MAX_TOTAL_PAGES:
            raise TooLarge(f"more than {MAX_TOTAL_PAGES} pages cannot go in one file; export fewer books at a time")
        entry: dict[str, Any] = {"cache": cache.to_json()}
        if marks_store is not None:
            if book not in marks_at:
                marks_at[book] = None
                try:
                    _path, found = _marks_here(marks_store, book)
                except _LeftOut:
                    found, done.left_out = None, done.left_out + 1
                if found is not None and not _marks_empty(found):
                    marks_at[book] = len(marks)
                    marks.append(found.to_json())
            if marks_at[book] is not None:
                entry["annotations"] = marks_at[book]
        if sheet_store is not None:
            series = sheet_key(sheet_store, book)
            key = (series, language_key(cache.language))
            if key not in sheets_at:
                sheets_at[key] = None
                try:
                    _path, sheet = _sheet_here(sheet_store, series, cache.language)
                except _LeftOut:
                    sheet, done.left_out = None, done.left_out + 1
                if sheet is not None and not sheet.is_empty:
                    sheets_at[key] = len(sheets)
                    sheets.append(sheet.to_json())
            if sheets_at[key] is not None:
                entry["sheet"] = sheets_at[key]
        own_series = series_of(book) if defaults_store is not None else ""
        if own_series:  # (a book of one volume, or with a temporary name, has no series' defaults)
            defaults_key = series_id(own_series)
            if defaults_key not in defaults_at:
                defaults_at[defaults_key] = None
                try:
                    _path, found_defaults = _defaults_here(defaults_store, own_series)  # type: ignore[arg-type]
                except _LeftOut:
                    found_defaults, done.left_out = None, done.left_out + 1
                if found_defaults is not None and not found_defaults.is_empty:
                    defaults_at[defaults_key] = len(defaults)
                    defaults.append(found_defaults.to_json())
            if defaults_at[defaults_key] is not None:
                entry["defaults"] = defaults_at[defaults_key]
        entries.append(entry)
    payload = json.dumps({"schema": PAYLOAD_SCHEMA, "app": "taslation", "kind": "export", "note": PAYLOAD_NOTE,
                          "books": entries, "annotations": marks, "sheets": sheets, "defaults": defaults},
                         ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_PAYLOAD and len(entries) > 1:
        raise TooLarge("these books are larger than TASlation reads back from one file; export fewer at a time")
    blob = encrypt(payload, passphrase)
    write_atomic(out, blob)
    done.books, done.annotations, done.sheets, done.defaults = len(entries), len(marks), len(sheets), len(defaults)
    return done


def export_cache(stores: Any, book: str, path: Path | str, passphrase: str, language: str = "English") -> int:
    """Write the cache of *book* in *language* to *path*, encrypted with *passphrase* (`export_books`: with its page
    information and series sheet when *stores* has those stores); returns its page count."""
    return export_books(stores, [(book, language)], path, passphrase).pages


def _read_export(path: Path | str) -> bytes:
    """The bytes of a file to import, refused unread when it is larger than an export can be (reading never
    reserves more memory than the file needs)."""
    chunks: list[bytes] = []
    total = 0
    with open(path, "rb") as f:
        try:
            size = os.fstat(f.fileno()).st_size
        except OSError:
            size = 0
        while size <= MAX_FILE and total <= MAX_FILE:
            chunk = f.read(min(1 << 20, MAX_FILE + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    if size > MAX_FILE or total > MAX_FILE:
        raise TooLarge("not a TASlation cache export: larger than any export")
    return b"".join(chunks)


def _within_caps(data: Any) -> None:
    """TooLarge when the cache *data* (an export's JSON) has more than MAX_PAGES pages or a page with more than
    MAX_BUBBLES_PER_PAGE bubbles: more than one book's cache, read before any page is built. What is no cache at all
    is left for the checks after this one."""
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        return
    if len(pages) > MAX_PAGES:
        raise TooLarge(f"the file holds more pages than one book's cache (at most {MAX_PAGES}); nothing was imported")
    for page in pages:
        bubbles = page.get("bubbles") if isinstance(page, dict) else None
        if isinstance(bubbles, list) and len(bubbles) > MAX_BUBBLES_PER_PAGE:
            raise TooLarge(f"the file holds a page with more bubbles than TASlation reads (at most "
                           f"{MAX_BUBBLES_PER_PAGE}); nothing was imported")


def _incoming_cache(data: Any) -> "BookCache":
    """The cache a payload holds (*data*, its JSON), all of it: UnreadableExport when it is a later schema's or any page
    is one this version cannot read (a replace would lose it), TooLarge over the caps (`_within_caps`), BackupError
    when the names are not names; control characters dropped from every string, since the command line prints them."""
    from .cache import SCHEMA_VERSION, BookCache

    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] > SCHEMA_VERSION:
        raise UnreadableExport("the file holds the cache of a newer version of TASlation, which this one cannot "
                               "read; nothing was imported")
    _within_caps(data)
    try:
        if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
            raise ValueError("not a cache")
        for name in ("book", "model", "language", "created", "updated"):
            value = data.get(name, "")
            if not isinstance(value, str) or len(value) > MAX_NAME:
                raise ValueError(f"bad {name}")
        incoming = BookCache.from_json(data, Path())
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation reads") from None
    if len(incoming.pages) != len(data["pages"]):
        raise UnreadableExport("the file holds pages this version of TASlation cannot read (it likely comes from a "
                               "newer TASlation); nothing was imported")
    incoming.book, incoming.model, incoming.language, incoming.created, incoming.updated = (
        _CONTROLS.sub("", s) for s in (incoming.book, incoming.model, incoming.language, incoming.created,
                                       incoming.updated))
    if not incoming.book.strip():
        raise BackupError("damaged file")
    for page in incoming.pages:
        for b in page.bubbles:
            text = _CONTROLS_BUT_LINES.sub("", b.text)
            b.large = follow(b.text, text, b.large)  # (its part set larger moved with the text, or gone)
            b.text = text
            b.note = _CONTROLS_BUT_LINES.sub("", b.note)
            b.flags = [f for f in (_CONTROLS.sub("", f) for f in b.flags) if f]
    return incoming


def _clean_tree(value: Any) -> Any:
    """*value*, the JSON of a file of page information or of a sheet, with the control characters dropped from every
    string (and key); BackupError for a number that is not finite (a store would keep it, and a page drawn with it
    fail)."""
    if isinstance(value, str):
        return _CONTROLS.sub("", value)
    if isinstance(value, float) and not math.isfinite(value):
        raise BackupError("damaged file")
    if isinstance(value, list):
        return [_clean_tree(v) for v in value]
    if isinstance(value, dict):
        return {_CONTROLS.sub("", str(k)): _clean_tree(v) for k, v in value.items()}
    return value


def _head(raw: Any, kind: str, name_field: str, schema: int, what: str) -> None:
    """BackupError unless *raw* is the JSON of a store file of *kind* this version reads (UnreadableExport for a later
    schema's: *what*, "page information", says what it holds) with a name under *name_field* and a date that are
    names."""
    if not isinstance(raw, dict):
        raise BackupError("damaged file")
    found = raw.get("schema")
    if type(found) is int and found > schema:
        raise UnreadableExport(f"the file holds {what} of a newer version of TASlation, which this one cannot read; "
                               f"nothing was imported")
    if found != schema or raw.get("kind", kind) != kind:
        raise BackupError("damaged file")
    for name in (name_field, "updated", "language"):
        value = raw.get(name, "")
        if not isinstance(value, str) or len(value) > MAX_NAME:
            raise BackupError("damaged file")
    if not _CONTROLS.sub("", raw.get(name_field, "")).strip():
        raise BackupError("damaged file")


def _lists_within(raw: dict[str, Any], caps: Mapping[str, int], what: str) -> None:
    for name, cap in caps.items():
        items = raw.get(name) or []
        if not isinstance(items, list):
            raise BackupError("damaged file")
        if len(items) > cap:
            raise TooLarge(f"the file holds {what} larger than TASlation reads (at most {cap} {name}); nothing was "
                           f"imported")


def _incoming_marks(raw: Any) -> "BookAnnotations":
    """The page information of a book a bundle holds (*raw*, its JSON), read as its store reads a file: checked
    (`_head`, the store's caps), cleaned (`_clean_tree`)."""
    from .annotations import MAX_PAGES as MARKED_PAGES, SCHEMA_VERSION, BookAnnotations

    _head(raw, "annotations", "book", SCHEMA_VERSION, "page information")
    _lists_within(raw, {"pages": MARKED_PAGES, "sequence": MARKED_PAGES}, "page information")
    try:
        marks = BookAnnotations.from_json(_clean_tree(raw), Path())
    except BackupError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, RecursionError):
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation reads") from None
    return marks


def _incoming_sheet(raw: Any) -> "Glossary":
    """A series sheet a bundle holds (*raw*, its JSON), read as its store reads a file: checked (`_head`, the store's
    caps), cleaned (`_clean_tree`)."""
    from .annotations import MAX_CHARACTERS, MAX_TERMS, SCHEMA_VERSION, Glossary

    _head(raw, "glossary", "series", SCHEMA_VERSION, "a series sheet")
    _lists_within(raw, {"entries": MAX_TERMS, "characters": MAX_CHARACTERS}, "a series sheet")
    try:
        sheet = Glossary.from_json(_clean_tree(raw), Path())
    except BackupError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, RecursionError):
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation reads") from None
    if not sheet.language.strip():
        raise BackupError("damaged file")
    return sheet


def _incoming_defaults(raw: Any) -> "SeriesDefaults":
    """A series' defaults a bundle holds (*raw*, their JSON), read as their store reads a file: checked (`_head`, the
    series as written a name too, at most `annotations.MAX_AREAS` areas), cleaned (`_clean_tree`)."""
    from .annotations import MAX_AREAS, SCHEMA_VERSION, SeriesDefaults

    _head(raw, "series_defaults", "key", SCHEMA_VERSION, "a series' defaults")
    series = raw.get("series", "")
    if not isinstance(series, str) or len(series) > MAX_NAME:
        raise BackupError("damaged file")
    _lists_within(raw, {"areas": MAX_AREAS}, "a series' defaults")
    if raw.get("settings") is not None and not isinstance(raw.get("settings"), dict):
        raise BackupError("damaged file")
    try:
        defaults = SeriesDefaults.from_json(_clean_tree(raw), Path())
    except BackupError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, RecursionError):
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation reads") from None
    return defaults


@dataclass
class Held:
    """One book's translations in one language that an export file holds (`open_export`), as a list shows them: its
    place in the file, the book and the language, its pages and bubbles, how many of those a person wrote
    (`CachedBubble.edited`), whether the book's page information comes with it, the series whose sheet in that
    language does ("" for none) and the series whose defaults do ("" for none)."""

    index: int
    book: str
    language: str
    pages: int
    bubbles: int
    corrections: int
    annotations: bool
    sheet: str
    defaults: str = ""


@dataclass
class Opened:
    """An export file opened and checked, nothing written (`open_export`): the version of its payload
    (`PAYLOAD_SCHEMA`), what it holds (*held*, a `Held` per book in the file's order) and the parts themselves; per
    book, the index of its page information and of its sheet (*links*, None for none) and of its series' defaults
    (*defaults_links*, None for none)."""

    version: int
    held: list[Held]
    caches: list["BookCache"]
    annotations: list["BookAnnotations"] = field(default_factory=list)
    sheets: list["Glossary"] = field(default_factory=list)
    links: list[tuple[int | None, int | None]] = field(default_factory=list)
    defaults: list["SeriesDefaults"] = field(default_factory=list)
    defaults_links: list[int | None] = field(default_factory=list)

    def chosen(self, books: Iterable[int] | None = None) -> list[int]:
        """The indices of *books* (None: all) the file holds, in the file's order, each once."""
        if books is None:
            return list(range(len(self.held)))
        wanted = set(books)
        return [i for i in range(len(self.held)) if i in wanted]


def _held(index: int, cache: "BookCache", marks: bool, sheet: str, defaults: str = "") -> Held:
    return Held(index, cache.book, cache.language, len(cache.pages), cache.bubble_count,
                sum(1 for page in cache.pages for b in page.bubbles if b.edited), marks, sheet, defaults)


def _bundle(data: dict[str, Any]) -> Opened:
    """What a payload of version 2 holds (*data*), all of it read and checked (see the module's docstring)."""
    from .annotations import series_id, series_of
    from .cache import language_key

    books, marks, sheets = data.get("books"), data.get("annotations", []), data.get("sheets", [])
    defaults = data.get("defaults", [])  # (optional: see the module's docstring)
    if (not isinstance(books, list) or not isinstance(marks, list) or not isinstance(sheets, list)
            or not isinstance(defaults, list) or not books):
        raise BackupError("damaged file")
    if max(len(books), len(marks), len(sheets), len(defaults)) > MAX_BOOKS:
        raise TooLarge(f"the file holds more than {MAX_BOOKS} books; nothing was imported")
    total = sum(len(e["cache"]["pages"]) for e in books if isinstance(e, dict) and isinstance(e.get("cache"), dict)
                and isinstance(e["cache"].get("pages"), list))
    if total > MAX_TOTAL_PAGES:
        raise TooLarge(f"the file holds more pages than TASlation imports at once (at most {MAX_TOTAL_PAGES}); nothing "
                       f"was imported")
    read_marks = [_incoming_marks(raw) for raw in marks]
    read_sheets = [_incoming_sheet(raw) for raw in sheets]
    read_defaults = [_incoming_defaults(raw) for raw in defaults]
    opened = Opened(PAYLOAD_SCHEMA, [], [], read_marks, read_sheets, [], read_defaults, [])
    for entry in books:
        if not isinstance(entry, dict) or not isinstance(entry.get("cache"), dict):
            raise BackupError("damaged file")
        cache = _incoming_cache(entry["cache"])
        a, s, d = entry.get("annotations"), entry.get("sheet"), entry.get("defaults")
        for ref, count in ((a, len(read_marks)), (s, len(read_sheets)), (d, len(read_defaults))):
            if ref is not None and (type(ref) is not int or not 0 <= ref < count):
                raise BackupError("damaged file")
        if a is not None and read_marks[a].book != cache.book:
            raise BackupError("damaged file")
        if s is not None and language_key(read_sheets[s].language) != language_key(cache.language):
            raise BackupError("damaged file")
        if d is not None and (not series_of(cache.book) or read_defaults[d].key != series_id(series_of(cache.book))
                              or series_id(read_defaults[d].series) != read_defaults[d].key):
            raise BackupError("damaged file")  # the defaults of another series than the book's (or of none)
        opened.held.append(_held(len(opened.caches), cache, a is not None,
                                 read_sheets[s].series if s is not None else "",
                                 read_defaults[d].series if d is not None else ""))
        opened.caches.append(cache)
        opened.links.append((a, s))
        opened.defaults_links.append(d)
    if (len({c.owner for c in opened.caches}) != len(opened.caches)
            or len({m.book for m in read_marks}) != len(read_marks)
            or len({(g.series, language_key(g.language)) for g in read_sheets}) != len(read_sheets)
            or len({x.key for x in read_defaults}) != len(read_defaults)):
        raise BackupError("damaged file")  # a book, its page information, a sheet or defaults twice: which would win?
    return opened


def _opened(payload: bytes) -> Opened:
    """What the payload of an export file holds: a bundle (version 2) or a cache alone (version 1); UnreadableExport for
    a later version's."""
    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, RecursionError):
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation reads") from None
    schema = data.get("schema") if isinstance(data, dict) else None
    if type(schema) is int and schema > PAYLOAD_SCHEMA:
        raise UnreadableExport("the file comes from a newer version of TASlation, which this one cannot read; nothing "
                               "was imported")
    if schema == PAYLOAD_SCHEMA and type(schema) is int:
        return _bundle(data)
    cache = _incoming_cache(data)
    return Opened(1, [_held(0, cache, False, "")], [cache], links=[(None, None)])


def open_export(path: Path | str, passphrase: str) -> Opened:
    """The export file at *path* opened with *passphrase* and all it holds read and checked, nothing written: what a
    list of its books shows (`Opened.held`) and what `plan_import` and `apply_import` take. WrongPassphrase for a
    wrong passphrase, UnreadableExport for a newer TASlation's file, TooLarge, BackupError for a damaged file."""
    return _opened(decrypt(_read_export(path), passphrase))


# --- what an import would do, and doing it ---------------------------------------------------------------------

@dataclass
class BookPlan:
    """What an import does to one book's cache in one language (`plan_import`): its file here (*target*), whether there
    is a cache of it here (*exists*), the file's pages none of which is here (*added*), the pages here the file
    changes (*replaced*, keeping the reader's corrections; *replaced_as_is*, taking the file as it is) and the
    reader's corrections it keeps over the file's lines (*kept*: their text differs, or the file has no line there).
    *annotations*, *sheet* and *defaults*: the index in the file of the book's page information, of its sheet and of
    its series' defaults."""

    held: Held
    target: Path
    exists: bool = False
    added: int = 0
    replaced: int = 0
    replaced_as_is: int = 0
    kept: int = 0
    annotations: int | None = None
    sheet: int | None = None
    defaults: int | None = None


@dataclass
class MarksPlan:
    """What an import does to one book's page information: *state* "new" (none here: the file's is added), "same"
    (here as the file has it: nothing to do) or "differs" (the reader's own here: kept unless they take the
    file's)."""

    book: str
    index: int
    target: Path
    state: str


@dataclass
class DefaultsPlan:
    """What an import does to one series' defaults (the series as the book that brings them writes it): *state* "new"
    (none here, or none that hold anything, or a file this version cannot read, which the save sets aside: the file's
    are added), "same" (here with the same values: nothing to do) or "differs" (the reader's own here: kept unless
    they take the file's)."""

    series: str
    index: int
    target: Path
    state: str


@dataclass
class SheetPlan:
    """What an import does to one series sheet in one language: where the series has none here, the file's is added
    as it is (*review* None); else it joins the sheet here (*review*: `annotations.compare_sheets` with the sheet here
    "mine" and the file's "theirs": what it adds, where the two say otherwise), as a rename joins two sheets."""

    series: str
    language: str
    index: int
    target: Path
    review: "Review | None" = None
    here: "Glossary | None" = field(default=None, repr=False)  # the sheet here, which the join changes

    @property
    def state(self) -> str:
        """"new", "same" (the file's adds nothing and says nothing otherwise) or "join"."""
        if self.review is None:
            return "new"
        return "join" if self.review.terms or self.review.conflicts else "same"

    def key(self, c: "Conflict") -> tuple[str, ...]:
        """The key the answer for the conflict *c* goes under (`apply_import`'s *answers*): the series, then its
        `rename.conflict_key` with the sheet's language."""
        from .rename import conflict_key

        return (self.series, *conflict_key(c, self.language))


@dataclass
class ImportPlan:
    """What an import of the books chosen of a file would do (`plan_import`), nothing written: per book, per file of
    page information, per series sheet, per series' defaults."""

    books: list[BookPlan] = field(default_factory=list)
    annotations: list[MarksPlan] = field(default_factory=list)
    sheets: list[SheetPlan] = field(default_factory=list)
    defaults: list[DefaultsPlan] = field(default_factory=list)

    @property
    def pages(self) -> int:
        return sum(b.held.pages for b in self.books)

    @property
    def added(self) -> int:
        return sum(b.added for b in self.books)

    def replaced(self, keep_corrections: bool = True) -> int:
        return sum(b.replaced if keep_corrections else b.replaced_as_is for b in self.books)

    @property
    def kept(self) -> int:
        return sum(b.kept for b in self.books)

    @property
    def differing(self) -> list[MarksPlan]:
        """The books whose page information here is not the file's: kept, unless the reader takes the file's."""
        return [m for m in self.annotations if m.state == "differs"]

    @property
    def differing_defaults(self) -> list[DefaultsPlan]:
        """The series whose defaults here are not the file's: kept, unless the reader takes the file's."""
        return [d for d in self.defaults if d.state == "differs"]

    def keyed(self) -> list[tuple[tuple[str, ...], SheetPlan, "Conflict"]]:
        """Every conflict of the sheets that join, with the key its answer goes under (`SheetPlan.key`), sheet by
        sheet."""
        return [(sheet.key(c), sheet, c) for sheet in self.sheets if sheet.review is not None
                for c in sheet.review.conflicts]

    def only(self, books: Iterable[int]) -> "ImportPlan":
        """The plan for the books of *books* (indices in the file) alone, with their page information, sheets and
        series' defaults."""
        wanted = set(books)
        chosen = [b for b in self.books if b.held.index in wanted]
        marks = {b.annotations for b in chosen if b.annotations is not None}
        sheets = {b.sheet for b in chosen if b.sheet is not None}
        defaults = {b.defaults for b in chosen if b.defaults is not None}
        return ImportPlan(chosen, [m for m in self.annotations if m.index in marks],
                          [s for s in self.sheets if s.index in sheets],
                          [d for d in self.defaults if d.index in defaults])


def _cache_target(store: "CacheStore", incoming: "BookCache") -> Path:
    """The cache file the book of *incoming* has here; NameClash when both its file names hold other books, or the one
    found holds another book (another process wrote it meanwhile)."""
    from .cache import stored_book

    try:
        target = store.path_for(incoming.book, incoming.language)
    except FileExistsError as e:
        raise NameClash(str(e)) from None
    owner = stored_book(target)  # a safety net: path_for gives no file of another book, unless one came meanwhile
    if owner is not None and owner != incoming.owner:
        raise NameClash(f"{target} holds the cache of {owner[0]!r} in {owner[1]}, whose name gives the same file as "
                        f"{incoming.book!r} in {incoming.language}; move that file elsewhere first")
    return target


def _cache_here(target: Path, incoming: "BookCache") -> "BookCache | None":
    """The cache of *incoming*'s book in its file here, read without writing anything; None when there is none or this
    version cannot read it (the import sets it aside, as the store does). OSError when it cannot be opened now."""
    from .cache import BookCache

    try:
        here = BookCache.load(target)
    except FileNotFoundError:
        return None
    except ValueError:  # names.Unreadable
        return None
    return here if here.owner == incoming.owner else None


def _matcher(pages: Sequence["CachedPage"]) -> Any:
    """A function from a fingerprint to the page of *pages* the file's page of that fingerprint takes the place of, as
    `BookCache.add` finds it: the first within 6 bits; None for none."""
    values = [(int(p.fingerprint, 16), p) for p in pages]

    def match(fingerprint: str) -> "CachedPage | None":
        value = int(fingerprint, 16)
        return next((page for other, page in values if (value ^ other).bit_count() <= 6), None)

    return match


def _merged(mine: "CachedPage | None", theirs: "CachedPage", keep: bool) -> tuple["CachedPage", int]:
    """The page the file's page *theirs* becomes here, where the cache has *mine*: the file's, and with *keep* each
    translation a person wrote here (`CachedBubble.edited`) in place of the file's line for that bubble (the one its
    box overlaps most, `MATCH_IOU` at least, each taken once) unless that line is a person's too, or added where the
    file has none there. Returns the page and how many of those corrections it keeps with another text than the
    file's (or none there)."""
    from .cache import CachedPage
    from .regions import box_iou

    page = CachedPage(theirs.fingerprint, theirs.aspect, copy.deepcopy(theirs.bubbles), theirs.seq, theirs.incomplete)
    if mine is None or not keep:
        return page, 0
    kept, taken = 0, set()
    for local in (b for b in mine.bubbles if b.edited):
        best, best_iou = -1, 0.0
        for i, bubble in enumerate(page.bubbles):
            if i not in taken:
                iou = box_iou(local.box, bubble.box)  # type: ignore[arg-type]
                if iou > best_iou:
                    best, best_iou = i, iou
        if best >= 0 and best_iou >= MATCH_IOU:
            taken.add(best)
            if page.bubbles[best].edited:
                continue  # a person's on both computers: the file's, as the file's page wins
            kept += page.bubbles[best].text != local.text
            page.bubbles[best] = copy.deepcopy(local)
        else:
            page.bubbles.append(copy.deepcopy(local))
            kept += 1
    return page, kept


def _same(a: "CachedPage", b: "CachedPage") -> bool:
    return a.incomplete == b.incomplete and [x.to_json() for x in a.bubbles] == [y.to_json() for y in b.bubbles]


def _marks_body(marks: "BookAnnotations") -> dict[str, Any]:
    return {k: v for k, v in marks.to_json().items() if k != "updated"}


def plan_import(stores: Any, opened: Opened, books: Iterable[int] | None = None) -> ImportPlan:
    """What importing the books *books* (indices in the file; None: all) of *opened* into *stores* (`rename.Stores`, or
    a `CacheStore` alone, which takes the caches alone) would do, nothing written (see the module's docstring): the
    counts per book, the state of each book's page information here, each series sheet added or joined with its
    conflicts (each *take* False), the state of each series' defaults here. NameClash when a file the import would
    write holds another book or series (both its file names); OSError when a cache here cannot be opened now."""
    cache_store, marks_store, sheet_store = _parts(stores)
    plan = ImportPlan()
    for i in opened.chosen(books):
        incoming = opened.caches[i]
        target = _cache_target(cache_store, incoming)
        here = _cache_here(target, incoming)
        marks, sheet = opened.links[i] if i < len(opened.links) else (None, None)
        defaults = opened.defaults_links[i] if i < len(opened.defaults_links) else None
        book = BookPlan(opened.held[i], target, here is not None, annotations=marks, sheet=sheet, defaults=defaults)
        plan.books.append(book)
        if here is None:
            book.added = len(incoming.pages)
            continue
        match = _matcher(here.pages)
        for theirs in incoming.pages:
            mine = match(theirs.fingerprint)
            if mine is None:
                book.added += 1
                continue
            kept_page, kept = _merged(mine, theirs, True)
            book.kept += kept
            book.replaced += not _same(kept_page, mine)
            book.replaced_as_is += not _same(theirs, mine)
    if marks_store is not None:
        for index in dict.fromkeys(b.annotations for b in plan.books if b.annotations is not None):
            theirs = opened.annotations[index]
            try:
                target = marks_store.path_for(theirs.book)
            except FileExistsError as e:
                raise NameClash(str(e)) from None
            try:
                _path, mine_marks = _marks_here(marks_store, theirs.book)
            except _LeftOut:  # (the save sets the file aside first, as the store does)
                mine_marks = None
            state = ("new" if mine_marks is None or _marks_empty(mine_marks)
                     else "same" if _marks_body(mine_marks) == _marks_body(theirs) else "differs")
            plan.annotations.append(MarksPlan(theirs.book, index, target, state))
    if sheet_store is not None:
        from .annotations import compare_sheets

        for index in dict.fromkeys(b.sheet for b in plan.books if b.sheet is not None):
            theirs_sheet = opened.sheets[index]
            try:
                target = sheet_store.path_for(theirs_sheet.series, theirs_sheet.language)
            except FileExistsError as e:
                raise NameClash(str(e)) from None
            try:
                _path, mine_sheet = _sheet_here(sheet_store, theirs_sheet.series, theirs_sheet.language)
            except _LeftOut:
                mine_sheet = None
            review = None if mine_sheet is None else compare_sheets(mine_sheet, theirs_sheet)
            plan.sheets.append(SheetPlan(theirs_sheet.series, theirs_sheet.language, index, target, review,
                                         mine_sheet))
    defaults_store = _defaults_store(marks_store)
    if defaults_store is not None:
        from .annotations import series_of

        series_at: dict[int, str] = {}  # the defaults' index -> the series as the first book that brings them writes it
        for b in plan.books:
            if b.defaults is not None:
                series_at.setdefault(b.defaults, series_of(opened.caches[b.held.index].book))
        for index, series in series_at.items():
            try:
                target = defaults_store.path_for(series)
            except FileExistsError as e:
                raise NameClash(str(e)) from None
            try:
                _path, mine_defaults = _defaults_here(defaults_store, series)
            except _LeftOut:  # (the save sets the file aside first, as the store does)
                mine_defaults = None
            state = ("new" if mine_defaults is None or mine_defaults.is_empty
                     else "same" if _same_defaults(mine_defaults, opened.defaults[index]) else "differs")
            plan.defaults.append(DefaultsPlan(series, index, target, state))
    return plan


@dataclass
class ImportResult:
    """What an import did (`apply_import`): per book its `BookPlan` as it was done (*replaced* and *kept* as the
    reader chose: taking the file as it is keeps none), and the page information, series sheets and series' defaults:
    added where there were none, taken in place of the reader's own, kept as theirs; sheets joined, with what they
    added, the conflicts where the file's value was taken and those kept."""

    books: list[BookPlan] = field(default_factory=list)
    annotations_added: int = 0
    annotations_taken: int = 0
    annotations_kept: int = 0
    sheets_added: int = 0
    sheets_joined: int = 0
    sheet_terms: int = 0
    sheet_taken: int = 0
    sheet_kept: int = 0
    defaults_added: int = 0
    defaults_taken: int = 0
    defaults_kept: int = 0

    @property
    def pages(self) -> int:
        return sum(b.held.pages for b in self.books)

    @property
    def added(self) -> int:
        return sum(b.added for b in self.books)

    @property
    def replaced(self) -> int:
        return sum(b.replaced for b in self.books)

    @property
    def kept(self) -> int:
        return sum(b.kept for b in self.books)


def _keep_copy(path: Path) -> None:
    """A dated copy of the store file at *path* beside it, before an import changes it (never over an earlier
    copy); an import of the wrong or an older file can then be undone by hand. The copy is protected as the file is
    (`protect.protected`: the same bytes when the file is protected, sealed when it is an earlier version's plain
    file), whether or not this Windows user can open it here."""
    if path.is_file():
        copy_path = path.with_suffix(time.strftime(".before-import.%Y%m%d-%H%M%S.json"))
        if not copy_path.exists():
            write_atomic(copy_path, protect.protected(path.read_bytes()))


def apply_import(stores: Any, opened: Opened, books: Iterable[int] | None = None, *, replace: bool = False,
                 keep_corrections: bool = True, take_annotations: bool = False,
                 answers: Mapping[tuple[str, ...], bool] | None = None, take_defaults: bool = False) -> ImportResult:
    """Import the books *books* (indices in the file; None: all) of *opened* into *stores* (`rename.Stores`, or a
    `CacheStore` alone, which takes the caches alone), as `plan_import`, made again first, says (the files may have
    changed since the reader saw the plan): each book's pages join its cache (with *keep_corrections* the reader's
    corrections stay where the file's line is none of a person's; with *replace* the file's cache replaces the book's,
    header and all), its page information is added where it has none (*take_annotations*: also in place of the
    reader's own), its series sheet added or joined (*answers*: a conflict's key, `SheetPlan.key`, to True for "take
    the file's"; the sheet here keeps its value for any other), its series' defaults added where the series has none
    (*take_defaults*: also in place of the reader's own). What each file held is kept beside it first
    (``<file>.before-import.<date>.json``). NameClash, and nothing written, when a file the import would write holds
    another book or series; an OSError when a file cannot be written."""
    from .annotations import BookAnnotations, Glossary, SeriesDefaults, apply_review, series_id
    from .bookname import clean_series

    plan = plan_import(stores, opened, books)
    cache_store, marks_store, sheet_store = _parts(stores)
    result = ImportResult(plan.books)
    for book in plan.books:
        incoming = opened.caches[book.held.index]
        _keep_copy(book.target)
        if replace:
            fresh = copy.deepcopy(incoming)
            fresh.path = book.target
            fresh.save(merge=False)
            book.replaced, book.kept = book.replaced_as_is, 0
            continue
        cache = cache_store.open(incoming.book, incoming.model, incoming.language)
        match = _matcher(list(cache.pages))
        kept = 0
        for theirs in incoming.pages:
            page, count = _merged(match(theirs.fingerprint), theirs, keep_corrections)
            kept += count
            cache.add(page)
        cache.lines.join(incoming.lines)  # the short lines kept for reuse, where the cache has none of its own
        if not cache.details and incoming.details:  # the colophon's details, kept with the file's header
            cache.set_details(**incoming.details)
        cache.save()
        if not keep_corrections:
            book.replaced, kept = book.replaced_as_is, 0
        book.kept = kept
    if marks_store is not None:
        for marks in plan.annotations:
            if marks.state == "same":
                continue
            if marks.state == "differs" and not take_annotations:
                result.annotations_kept += 1
                continue
            written = BookAnnotations.from_json(opened.annotations[marks.index].to_json(), marks.target)
            written.book = marks.book
            if marks.state == "differs":
                _keep_copy(marks.target)
            written.save()  # (a file there this version cannot read is set aside first, as the store does)
            if marks.state == "new":
                result.annotations_added += 1
            else:
                result.annotations_taken += 1
    if sheet_store is not None:
        for sheet in plan.sheets:
            if sheet.state == "same":
                continue
            if sheet.review is None or sheet.here is None:
                written_sheet = Glossary.from_json(opened.sheets[sheet.index].to_json(), sheet.target)
                written_sheet.series, written_sheet.language = sheet.series, sheet.language
                written_sheet.save()
                result.sheets_added += 1
                continue
            for c in sheet.review.conflicts:
                c.take = bool((answers or {}).get(sheet.key(c), False))
            counts = apply_review(sheet.review, sheet.here)
            _keep_copy(sheet.target)
            sheet.here.path = sheet.target
            sheet.here.save()
            result.sheets_joined += 1
            result.sheet_terms += counts["terms"]
            result.sheet_taken += counts["taken"]
            result.sheet_kept += len(sheet.review.conflicts) - counts["taken"]
    for defaults in plan.defaults:  # (none without a store of them: `plan_import`)
        if defaults.state == "same":
            continue
        if defaults.state == "differs" and not take_defaults:
            result.defaults_kept += 1
            continue
        written_defaults = SeriesDefaults.from_json(opened.defaults[defaults.index].to_json(), defaults.target)
        written_defaults.series, written_defaults.key = clean_series(defaults.series), series_id(defaults.series)
        if defaults.state == "differs":
            _keep_copy(defaults.target)
        written_defaults.save()  # (a file there this version cannot read is set aside first, as the store does)
        if defaults.state == "new":
            result.defaults_added += 1
        else:
            result.defaults_taken += 1
    return result


def import_cache(stores: Any, path: Path | str, passphrase: str, replace: bool = False,
                 keep_corrections: bool = True) -> tuple[str, int]:
    """Read an export file into *stores* (`rename.Stores`, or a `CacheStore` alone: then its caches alone), all of it
    (`open_export`, `apply_import`: the reader's corrections, page information, sheet values and series' defaults kept
    where the file says otherwise, the corrections unless *keep_corrections* is False; with *replace* the file's caches
    replace the books'). Nothing is
    written for a wrong passphrase, a damaged file or one with what this version cannot read (BackupError and its
    kinds), nor when a file it would write holds another book (NameClash, an OSError: only for two names with the same
    hash, since a book whose name gives the file name of another's gets a file of its own); what was there is kept
    beside it as ``<file>.before-import.<date>.json``. Returns the first book and the number of pages read."""
    opened = open_export(path, passphrase)
    apply_import(stores, opened, replace=replace, keep_corrections=keep_corrections)
    return opened.held[0].book, sum(h.pages for h in opened.held)


__all__ = ["MAGIC", "SUFFIX", "KDF", "MIN_PASSPHRASE", "PASSPHRASE_ENV", "MAX_PAGES", "MAX_BUBBLES_PER_PAGE",
           "MAX_BOOKS", "MAX_TOTAL_PAGES", "PAYLOAD_SCHEMA", "BackupError", "LibraryMissing",
           "WrongPassphrase", "BrokenPassphrase", "UnreadableExport", "TooLarge", "NameClash", "require",
           "passphrase_length", "check_passphrase", "encrypt", "decrypt", "cache_file", "export_cache", "export_books",
           "Exported", "Held", "Opened", "open_export", "BookPlan", "MarksPlan", "DefaultsPlan", "SheetPlan", "ImportPlan",
           "plan_import", "ImportResult", "apply_import", "import_cache"]
