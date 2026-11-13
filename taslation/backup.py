"""Encrypted export and import of a translation cache: the reader's own translations, for their own backup or
their other computer. Without the passphrase the file is unreadable; the format is public and holds no secret,
so its strength is the passphrase's alone.

The file is a first line ``TASLATION-CACHE-1`` and one JSON object::

    {"kdf": {"name": "scrypt", "n": 131072, "r": 8, "p": 1}, "salt": base64, "nonce": base64, "data": base64}

The key is scrypt over the passphrase (every space character an ordinary space, then Unicode NFC, in UTF-8: the
mapping of RFC 8265's OpaqueString, so the same words typed on another computer, or with the full-width space of a
Japanese input method, give the same key; control characters are refused) with a random 16-byte salt and those
parameters, 32 bytes long. ``data`` is AES-256-GCM, with a random 12-byte nonce, over the cache file's JSON
compressed with zlib; the associated data is the first line and the
header (the object without ``data``, keys sorted, no spaces), so neither can be changed unnoticed. The book's
title, model and language are inside the encrypted JSON only. AES-GCM comes from the optional ``cryptography``
package (``pip install cryptography``); scrypt comes with Python.

Reading a file trusts nothing in it before the tag is checked: a file larger than an export can be is refused
before it is read, a header with other fields or with scrypt parameters costing more than twice what this
version writes before any key is derived, and nothing is unpacked before the tag holds. What the passphrase
opens is checked too (it may come from someone else): at most MAX_PAGES pages (a cache is one book's, and a
volume has some 200; the file size cap alone would let in some 500,000) of at most MAX_BUBBLES_PER_PAGE bubbles
each, every page readable, the strings without control characters, and the book's cache file must be that book's,
never another one whose name gives the same file. An export of a cache over those caps is refused the same way.

The export is the one form of a cache that moves to another computer or Windows user: the cache files themselves are
protected for the Windows user who saved them, on that computer (`protect.py`), and an export protected so would open
nowhere else. It is read from the cache through the store (`BookCache.load`, which opens the protected file) and
written with `write_atomic` as it is, its passphrase its only protection; an import is saved through the store, and so
protected like every cache. The format is the same as before the caches were protected (2026-11-14), so an export of
an earlier version imports.

Every refusal is a BackupError with a sentence for the reader; a window tells the kinds apart by class:
WrongPassphrase, BrokenPassphrase, UnreadableExport (from a newer TASlation), TooLarge, LibraryMissing, and
plain BackupError for a damaged file. NameClash, an OSError, is the cache file that holds another book.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import time
import unicodedata
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import protect
from .atomic import write_atomic

if TYPE_CHECKING:
    from .cache import BookCache, CacheStore

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
MAX_PAGES = 5000  # pages one export may hold: a cache is one book's, and a volume has some 200
MAX_BUBBLES_PER_PAGE = 500  # bubbles one page may hold, far more than a page of a book has
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


def export_cache(store: CacheStore, book: str, path: Path | str, passphrase: str, language: str = "English") -> int:
    """Write the cache of *book* in *language* to *path*, encrypted with *passphrase*; returns its page count.
    The file appears whole or not at all (written beside it first, readable by its owner only where the system
    has such permissions)."""
    from .cache import BookCache

    require()
    check_passphrase(passphrase)
    out = Path(path)
    if out.is_dir():
        raise BackupError(f"{out} is a folder; give the name of the file to write")
    source = cache_file(store, book, language)
    if out.resolve() == source.resolve():
        raise BackupError(f"{out} is the cache itself; write the export somewhere else")
    if out.suffix.lower() == ".json" and out.resolve().parent == store.cache_dir.resolve():
        raise BackupError(f"{out} would take the place of a cache in the cache folder; write the export somewhere else")
    try:
        cache = BookCache.load(source)
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as e:
        raise BackupError(f"the cache of {book!r} cannot be read: {e}") from None
    if len(cache.pages) > MAX_PAGES or any(len(page.bubbles) > MAX_BUBBLES_PER_PAGE for page in cache.pages):
        raise TooLarge(f"the cache holds more than TASlation imports (at most {MAX_PAGES} pages of at most "
                       f"{MAX_BUBBLES_PER_PAGE} bubbles); it cannot be exported")
    blob = encrypt(json.dumps(cache.to_json(), ensure_ascii=False).encode("utf-8"), passphrase)
    write_atomic(out, blob)
    return len(cache)


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


def _incoming(payload: bytes) -> BookCache:
    """The cache an export file holds, all of it: UnreadableExport when it is a later schema's or any page is one
    this version cannot read (a replace would lose it), TooLarge over the caps (`_within_caps`), BackupError when
    the names are not names; control characters dropped from every string, since the command line prints them."""
    from .cache import SCHEMA_VERSION, BookCache

    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, RecursionError):
        raise BackupError("damaged file") from None
    except MemoryError:
        raise TooLarge("the file is larger than TASlation reads") from None
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
            b.text = _CONTROLS_BUT_LINES.sub("", b.text)
            b.note = _CONTROLS_BUT_LINES.sub("", b.note)
            b.flags = [f for f in (_CONTROLS.sub("", f) for f in b.flags) if f]
    return incoming


def _keep_copy(path: Path) -> None:
    """A dated copy of the cache file at *path* beside it, before an import changes it (never over an earlier
    copy); an import of the wrong or an older file can then be undone by hand. The copy is protected as the cache is
    (`protect.protected`: the same bytes when the file is protected, sealed when it is an earlier version's plain
    file), whether or not this Windows user can open it here."""
    if path.is_file():
        copy = path.with_suffix(time.strftime(".before-import.%Y%m%d-%H%M%S.json"))
        if not copy.exists():
            write_atomic(copy, protect.protected(path.read_bytes()))


def import_cache(store: CacheStore, path: Path | str, passphrase: str, replace: bool = False) -> tuple[str, int]:
    """Read an export file into the store: its pages replace the same pages in that book's cache and join the
    others there, the way saves merge, and the details its header has (what the colophon says of the book: title,
    volume, author, publisher, ISBN) go into the cache's header when that has none; with *replace* the file
    replaces the book's cache, header and all. Nothing is written for a wrong passphrase, a damaged file or one with
    pages this version cannot read (BackupError and its kinds), nor when both files the book's cache can have hold
    other books (NameClash, an OSError: only for two names with the same hash, since a book whose name gives the
    file name of another's gets a file of its own); what was there is kept beside it as
    ``<file>.before-import.<date>.json``. Returns the book and the number of pages read."""
    from .cache import language_key, stored_book

    incoming = _incoming(decrypt(_read_export(path), passphrase))
    try:
        target = store.path_for(incoming.book, incoming.language)
    except FileExistsError as e:
        raise NameClash(str(e)) from None
    owner = stored_book(target)  # a safety net: path_for gives no file of another book, unless one came meanwhile
    if owner is not None and owner != (incoming.book, language_key(incoming.language)):
        raise NameClash(f"{target} holds the cache of {owner[0]!r} in {owner[1]}, whose name gives the same file as "
                        f"{incoming.book!r} in {incoming.language}; move that file elsewhere first")
    _keep_copy(target)
    if replace:
        incoming.path = target
        incoming.save(merge=False)
    else:
        cache = store.open(incoming.book, incoming.model, incoming.language)
        for page in incoming.pages:
            cache.add(page)
        if not cache.details and incoming.details:  # the colophon's details, kept with the file's header
            cache.set_details(**incoming.details)
        cache.save()
    return incoming.book, len(incoming.pages)


__all__ = ["MAGIC", "SUFFIX", "KDF", "MIN_PASSPHRASE", "PASSPHRASE_ENV", "MAX_PAGES", "MAX_BUBBLES_PER_PAGE",
           "BackupError", "LibraryMissing",
           "WrongPassphrase", "BrokenPassphrase", "UnreadableExport", "TooLarge", "NameClash", "require",
           "passphrase_length", "check_passphrase", "encrypt", "decrypt", "cache_file", "export_cache", "import_cache"]
