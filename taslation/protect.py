"""The saved files that hold text of a book, protected at rest for this Windows user on this computer.

Which files (`STORE_FOLDERS` of the state folder): the translation caches (``cache``: per book and language the
translations, the bubbles' positions and outlines, the page fingerprints, the book's name and the colophon's details),
the reader's annotations (``annotations``: notes, texts typed by the reader, rectangles, areas, the book's name), the
series sheets (``glossary``: terms with their renderings, characters, the style guide), with the copies the stores
keep beside them (``.before-import``, ``.before-apply``, ``.unreadable-<date>``, ``.corrupt``) and the temporary files
a save that stopped halfway left; and the translator's notes an old version left in ``series``, which nothing reads
any more. The window's own settings (``ui.json``, ``viewers.json``, ``profiles.json`` and the like) are not among
them: they hold no text of a book, though ``ui.json`` and ``viewers.json`` hold the names of books as their windows
were titled (`bookid.remember_name`, `viewerparts`), and the installer reads ``ui.json``.

How: Windows' data protection (DPAPI: ``CryptProtectData`` and ``CryptUnprotectData`` of crypt32, through ctypes; no
package, no passphrase), in the scope of the Windows user, not of the computer, with a fixed entropy of TASlation's
(`ENTROPY`), so that another program's plain DPAPI call does not open these files by accident, and never with a
prompt (CRYPTPROTECT_UI_FORBIDDEN). Windows derives the key from the user's login secrets: a protected file copied to
another computer, or opened by another Windows user, cannot be opened (`CannotOpen`). That is what it is for: a file
copied out of the folder - by hand, by a sync or backup tool, by someone who gets hold of the disk or the file - holds
no readable translation. It is not a protection against the owner of the computer: any program that runs as the same
Windows user can open the files as TASlation does. The key goes with the Windows profile: an administrator who resets
the user's password (without the user's own password change), a new Windows profile or a reinstalled system loses it,
and with it every protected file; the passphrase-encrypted export (`backup.py`) is the copy that survives that, and the
one way to move a book's translations to another computer, since it does not depend on this computer.

The format, version 1: two lines of ASCII, then the DPAPI blob::

    TASLATION-PROTECTED-1
    Protected by TASlation with Windows DPAPI: ... Not JSON.
    <CryptProtectData of the file's bytes compressed with zlib>

The first line is the magic and the version (`HEADER`): a file that begins with ``TASLATION-PROTECTED-`` is a protected
one, and one with a higher version comes from a newer TASlation (`Newer`). The second line (`NOTE`) says in plain words
what the file is, for whoever opens it in an editor; it is read up to its end and not compared. The bytes inside are
the store's file as it was before (its JSON in UTF-8), compressed first: DPAPI moves some 18 MB a second through the
Windows security service (measured on the development machine: 65 ms for a 1.1 MB cache, 1.5 ms once compressed),
and a cache's JSON shrinks five to fifty times. DPAPI checks the blob's integrity: a changed byte cannot be opened.

Why the name stays: a protected file keeps its file name, ``.json`` and all, though it is no JSON. Every rule that
names, finds and keeps a store's files (`names.py`: one file per exact name with the hash for two names that give one
file name, the copies set aside, the leftovers of a save; `rename.py`, `recycle.py`, the delete of the Saved
translations dialog) works as it is, for the old plain files and the protected ones alike, which share one name per
book. The conversion of a plain file (`migrate`) replaces it by its protected form in one step (`atomic.write_atomic`:
``os.replace``), so there is never a moment with both on disk or with neither, and a stop halfway leaves the one or the
other. An older TASlation that finds a protected file reads no JSON object in it and sets it aside as unreadable
(`names.set_aside`), never writing over it. A new extension would have needed every one of those rules twice and a
second step - the plain file deleted after the protected one was written - that a stop could leave undone.

Reading accepts both forms (`readable`, `read`: a plain file is given as it is), so files of an earlier version keep
working; every write writes the protected form (`write`: sealed before anything reaches the disk, so the temporary
file beside it never holds plain text either). `migrate` protects the plain files of the folder at the start of the
window and of the command line, each in its own atomic step, passing over a file that fails (it stays as it was and
is tried again at the next start); `survey` counts what the folder holds without changing anything (`taslation audit`,
`taslation cache protect`).

Where crypt32 is missing (not Windows; the application is for Windows), nothing is protected and nothing is written
in plain text instead: `seal` raises `Unavailable` (an OSError, which a save reports as a failed save and keeps in
memory), and a protected file cannot be opened. Standard library only, like `names.py` and `atomic.py`, which use it.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .atomic import write_atomic

LOG = logging.getLogger("taslation.protect")

MAGIC = b"TASLATION-PROTECTED-"  # what a protected file begins with
VERSION = 1
HEADER = MAGIC + str(VERSION).encode("ascii") + b"\n"
NOTE = (b"Protected by TASlation with Windows DPAPI: only the Windows user who saved it can open it, on the computer "
        b"it was saved on. Not JSON; TASlation reads it. To move it to another computer, use TASlation's encrypted "
        b"export.\n")
_FIRST_LINE = re.compile(rb"TASLATION-PROTECTED-([0-9]{1,9})")
MAX_LINE = 4096  # the most the note line may be (a file whose second line does not end before is damaged)
# TASlation's own entropy: a DPAPI call of another program with none (or another) does not open these files
ENTROPY = b"TASlation saved files, protected for this Windows user (format 1)"
CRYPTPROTECT_UI_FORBIDDEN = 0x1  # never a prompt: a call that would need one fails
LEVEL = 6  # zlib's level: a 1.1 MB cache in about 5 ms
MAX_PLAIN = 256 << 20  # the most a protected file opens to: far above any store's file (an export is capped at 64 MB)
# what CryptUnprotectData answers for a blob this user cannot open here, or one that is damaged: another user's or
# another computer's key (NTE_BAD_KEY_STATE), a changed byte or another entropy (ERROR_INVALID_DATA, NTE_BAD_DATA),
# no blob at all (ERROR_INVALID_PARAMETER). Any other failure (the security service busy, out of memory) is no answer
# about the file: an OSError, and the file is left alone as one that cannot be opened now.
NOT_HERE_ERRORS = frozenset({0x8009000B, 0x0000000D, 0x80090005, 0x00000057})
NTE_BAD_KEY_STATE = 0x8009000B
# why a protected file does not open, as the stores say it (`names.Unreadable`, the line of `names.set_aside`)
NOT_HERE = ("cannot be opened by this Windows user on this computer: saved by another Windows user or on another "
            "computer, or damaged")

STORE_FOLDERS = ("cache", "annotations", "glossary", "series")  # the state folder's folders with text of a book
LEFTOVER_AGE_S = 600.0  # a save's temporary file younger than this may be one being written now: left alone


class CannotOpen(ValueError):
    """A protected file this Windows user cannot open on this computer: protected by another Windows user, on another
    computer, or with a key this profile no longer has (*elsewhere*), or damaged; *reason* in a few words, never
    anything the file holds; *code* the Windows error, 0 when there was none."""

    def __init__(self, reason: str, code: int = 0, elsewhere: bool = False) -> None:
        super().__init__(reason)
        self.reason, self.code, self.elsewhere = reason, code, elsewhere


class Newer(CannotOpen):
    """A protected file of a later format than this version reads: it comes from a newer TASlation."""


class Unavailable(OSError):
    """Windows data protection did not work: there is none on this system, or Windows refused for a reason that says
    nothing about the file (*code*, the Windows error; 0 when there is none). Nothing is written, and nothing in plain
    text instead; a file that could not be opened so may open later."""

    def __init__(self, text: str, code: int = 0) -> None:
        super().__init__(0, text)
        self.code = code

    def __str__(self) -> str:
        return str(self.strerror)


# ------------------------------------------------------------------ Windows DPAPI
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


class _Api:
    """crypt32's two calls and kernel32's LocalFree, typed for ctypes."""

    def __init__(self) -> None:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        blob = ctypes.POINTER(_Blob)
        self.protect = crypt32.CryptProtectData
        self.protect.argtypes = [blob, ctypes.c_wchar_p, blob, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, blob]
        self.protect.restype = ctypes.c_int
        self.unprotect = crypt32.CryptUnprotectData
        self.unprotect.argtypes = [blob, ctypes.c_void_p, blob, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                   blob]
        self.unprotect.restype = ctypes.c_int
        self.free = kernel32.LocalFree
        self.free.argtypes = [ctypes.c_void_p]
        self.free.restype = ctypes.c_void_p


_api: _Api | None | bool = None  # None: not looked for yet; False: there is none


def _crypt() -> _Api | None:
    """The DPAPI calls of this system, None where there are none (not Windows)."""
    global _api
    if _api is None:
        try:
            _api = _Api() if sys.platform == "win32" else False
        except (OSError, AttributeError):
            _api = False
    return _api or None


def available() -> bool:
    """Whether this system can protect and open files (Windows DPAPI)."""
    return _crypt() is not None


def _buffer(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(api: _Api, call: Any, data: bytes) -> bytes:
    """*call* (CryptProtectData or CryptUnprotectData of *api*) over *data* with TASlation's entropy, no prompt; the
    bytes it gives. Unavailable, with the Windows error as *code*, when it fails."""
    source, _source_buf = _buffer(data)  # (the buffers stay alive until the call is done)
    entropy, _entropy_buf = _buffer(ENTROPY)
    out = _Blob()
    if not call(ctypes.byref(source), None, ctypes.byref(entropy), None, None, CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out)):
        code = ctypes.get_last_error() & 0xFFFFFFFF  # type: ignore[attr-defined]
        raise Unavailable(f"Windows data protection failed (error {code:#010x})", code)
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        api.free(ctypes.cast(out.pbData, ctypes.c_void_p))


# ------------------------------------------------------------------ the format
def is_protected(data: bytes) -> bool:
    """Whether *data* (a file's bytes, or their beginning) is a protected file, of any version."""
    return bytes(data[: len(MAGIC)]) == MAGIC


def seal(data: bytes) -> bytes:
    """*data* protected for this Windows user on this computer: `HEADER`, `NOTE`, then the DPAPI blob of *data*
    compressed. `Unavailable` (an OSError) where there is no DPAPI, or when Windows refuses."""
    api = _crypt()
    if api is None:
        raise Unavailable("this system cannot protect saved files (Windows data protection is missing); nothing was "
                          "written")
    try:
        blob = _dpapi(api, api.protect, zlib.compress(bytes(data), LEVEL))
    except Unavailable as e:
        raise Unavailable(f"Windows did not protect the file ({e}); nothing was written", e.code) from None
    return HEADER + NOTE + blob


def _body(data: bytes) -> bytes:
    """The DPAPI blob of the protected file *data*. Newer for a later version, CannotOpen for a damaged header."""
    end = data.find(b"\n", 0, len(MAGIC) + 12)
    first = _FIRST_LINE.fullmatch(data[:end]) if end >= 0 else None
    if first is None:
        raise CannotOpen("damaged: no protected file's first line")
    version = int(first.group(1))
    if version > VERSION:
        raise Newer("written by a newer TASlation")
    if version != VERSION:
        raise CannotOpen("damaged: an unknown version")
    note_end = data.find(b"\n", end + 1, end + 1 + MAX_LINE)
    if note_end < 0:
        raise CannotOpen("damaged: no end to the second line")
    return data[note_end + 1:]


def _inflate(packed: bytes) -> bytes:
    """The bytes the compressed *packed* holds: one zlib stream, at most MAX_PLAIN bytes, nothing after it."""
    unpack = zlib.decompressobj()
    try:
        plain = unpack.decompress(packed, MAX_PLAIN + 1)
    except zlib.error:
        raise CannotOpen("damaged: what it holds is broken") from None
    if len(plain) > MAX_PLAIN or unpack.unconsumed_tail or not unpack.eof or unpack.unused_data:
        raise CannotOpen("damaged: what it holds is broken")
    return plain


def open_(data: bytes) -> bytes:
    """The bytes the protected file *data* holds (what `seal` was given). CannotOpen when this Windows user cannot
    open it on this computer (*elsewhere*: another user's or another computer's key) or it is damaged, Newer for a
    file of a newer TASlation, CannotOpen for *data* that is no protected file at all; `Unavailable` (an OSError) when
    Windows refused for a reason that says nothing about the file (it may open later)."""
    if not is_protected(data):
        raise CannotOpen("not a protected file")
    blob = _body(bytes(data))
    api = _crypt()
    if api is None:
        raise CannotOpen("this system cannot open protected files (Windows data protection is missing)")
    try:
        packed = _dpapi(api, api.unprotect, blob)
    except Unavailable as e:
        if e.code in NOT_HERE_ERRORS:
            raise CannotOpen(NOT_HERE, e.code, elsewhere=e.code == NTE_BAD_KEY_STATE) from None
        raise
    return _inflate(packed)


def readable(data: bytes) -> bytes:
    """A store file's bytes as the store reads them: a protected file opened (`open_`, and its errors), a plain one
    (an earlier version's) as it is."""
    return open_(data) if is_protected(data) else bytes(data)


def read(path: Path | str) -> bytes:
    """The bytes of the store file at *path*, opened when it is protected (`readable`). FileNotFoundError when there
    is none, another OSError when it cannot be read now, CannotOpen (a ValueError) as `open_`."""
    with open(path, "rb") as f:
        return readable(f.read())


def protected(data: bytes) -> bytes:
    """*data* (a store file's bytes) in the protected form: sealed (`seal`), or as it is when it is a protected file
    already (a copy of one, whoever's it is). What every write of a store file writes, sealed before anything reaches
    the disk, so the temporary file `atomic.write_atomic` writes beside the file holds the protected form too.
    `Unavailable` (an OSError) where there is no DPAPI."""
    data = bytes(data)
    return data if is_protected(data) else seal(data)


def write(path: Path | str, data: bytes) -> None:
    """*data* (a store file's bytes) as the file at *path*, protected (`protected`), all or nothing
    (`atomic.write_atomic`). `Unavailable` (an OSError) where there is no DPAPI: nothing is written, plain or
    otherwise."""
    write_atomic(path, protected(data))


# ------------------------------------------------------------------ the folder
@dataclass
class Tally:
    """What `migrate` or `survey` found in the state folder's `STORE_FOLDERS`; counts only, never a name."""

    protected: int = 0  # plain files protected now (`migrate`)
    plain: int = 0  # plain files still there: could not be protected now (`migrate`), or found (`survey`)
    sealed: int = 0  # protected files found (not those protected now)
    opened: int = 0  # of the protected files, those this Windows user opened here (when they were checked)
    not_here: int = 0  # ... those it cannot open here: another user's or computer's, or damaged
    newer: int = 0  # ... those a newer TASlation wrote
    busy: int = 0  # ... those that could not be opened now for a reason that says nothing about them
    unreadable: int = 0  # files that could not be read now (another program holds them): neither of the above
    checked: bool = False  # the protected files were opened to see whether they open here
    errors: list[str] = field(default_factory=list)  # why files failed, in a few words each (no names)

    @property
    def files(self) -> int:
        """Every file found (the leftovers of a save among them)."""
        return self.protected + self.plain + self.sealed + self.unreadable

    def lines(self) -> list[str]:
        """The tally in plain English, a line each, counts only: what the command line prints."""
        out = [f"{self.files} saved file(s) with text of a book: {self.protected + self.sealed} protected for this "
               f"Windows user on this computer, {self.plain} plain"
               + (f", {self.unreadable} could not be read now" if self.unreadable else "")]
        if self.protected:
            out.append(f"protected now: {self.protected} file(s), each replaced by its protected form")
        if self.checked and self.sealed:
            out.append(f"opened here: {self.opened} of {self.sealed} protected file(s)"
                       + (f"; {self.newer} written by a newer TASlation" if self.newer else "")
                       + (f"; {self.busy} could not be opened now (try again)" if self.busy else ""))
        if self.not_here:
            out.append(f"cannot be opened here: {self.not_here} file(s), saved by another Windows user or on another "
                       "computer, or damaged; TASlation never writes over them")
        if self.plain or self.unreadable:
            out.append(f"not protected yet: {self.plain + self.unreadable} file(s); `taslation cache protect` protects "
                       "them (TASlation does at its start) once nothing else holds them (another TASlation, a backup "
                       "tool)")
        return out


def store_files(state_dir: Path | str) -> list[Path]:
    """Every file of the state folder's `STORE_FOLDERS` that may hold text of a book: the ``*.json`` files (a store's
    files and the copies kept beside them) and the ``*.tmp`` files (what a save that stopped halfway left), in the
    order of their folders and names. Not recursive: the stores keep no folders."""
    found: list[Path] = []
    for name in STORE_FOLDERS:
        folder = Path(state_dir) / name
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            lower = entry.name.lower()
            try:
                if lower.endswith((".json", ".tmp")) and entry.is_file(follow_symlinks=False):
                    found.append(Path(entry.path))
            except OSError:
                continue
    return found


def _head(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read(len(MAGIC))


def _stamp(path: Path) -> tuple[int, int, int]:
    st = os.stat(path)
    return st.st_ino, st.st_mtime_ns, st.st_size


def _check(path: Path, tally: Tally) -> None:
    """Whether the protected file at *path* opens here, counted in *tally*."""
    try:
        open_(Path(path).read_bytes())
    except Newer:
        tally.newer += 1
        return
    except CannotOpen:
        tally.not_here += 1
        return
    except OSError as e:
        tally.busy += 1
        tally.errors.append(str(e.strerror or type(e).__name__))
        return
    tally.opened += 1


def survey(state_dir: Path | str, check: bool = True) -> Tally:
    """What the state folder's store files are, nothing changed: plain, protected and (with *check*: each is opened,
    a few milliseconds for a cache of 200 pages) whether this Windows user can open them here."""
    tally = Tally(checked=check)
    for path in store_files(state_dir):
        try:
            protected = is_protected(_head(path))
        except OSError as e:
            tally.unreadable += 1
            tally.errors.append(str(e.strerror or type(e).__name__))
            continue
        if not protected:
            tally.plain += 1
            continue
        tally.sealed += 1
        if check:
            _check(path, tally)
    return tally


def _protect_one(path: Path, now: float) -> bool | None:
    """The plain file at *path* replaced by its protected form, the same bytes inside: True when it was, None when it
    was left for now (a save's temporary file that may be being written, or a file that changed while it was read).
    The protected form is opened again and compared before it takes the file's place. OSError (`Unavailable` among
    them) when it could not be: the file stays as it was."""
    before = _stamp(path)
    if path.name.lower().endswith(".tmp") and now - before[1] / 1e9 < LEFTOVER_AGE_S:
        return None
    with open(path, "rb") as f:
        raw = f.read()
    if is_protected(raw):
        return False
    sealed = seal(raw)
    try:
        same = open_(sealed) == raw
    except CannotOpen:
        same = False
    if not same:
        raise Unavailable("Windows data protection gave back other bytes; the file was left as it was")
    if _stamp(path) != before:
        return None  # saved again meanwhile: the next start protects what is there then
    write_atomic(path, sealed)
    return True


def migrate(state_dir: Path | str) -> Tally:
    """Protect every plain store file of the state folder (`store_files`), each in its own atomic step: the file is
    replaced by its protected form (`write_atomic`), so a stop halfway leaves either. A file that fails (another
    program holds it, the disk is full) stays as it was, counted in ``plain``, and the next start tries it again; a
    save's temporary file younger than `LEFTOVER_AGE_S` is left for its save. Protected files are not opened here
    (`survey` does that). Counts only, also in the log (`LOG`): no file's name."""
    tally = Tally()
    now = time.time()
    for path in store_files(state_dir):
        try:
            if is_protected(_head(path)):
                tally.sealed += 1
                continue
        except OSError as e:
            tally.unreadable += 1
            tally.errors.append(str(e.strerror or type(e).__name__))
            continue
        try:
            done = _protect_one(path, now)
        except FileNotFoundError:
            continue  # gone meanwhile (a save's leftover deleted, a book deleted)
        except OSError as e:
            tally.plain += 1
            tally.errors.append(str(e.strerror or type(e).__name__))
            continue
        if done is None:
            tally.plain += 1
        elif done:
            tally.protected += 1
        else:
            tally.sealed += 1
    if tally.protected or tally.plain or tally.unreadable:
        LOG.info("saved files: %d protected now, %d already protected, %d left plain (tried again at the next "
                 "start), %d could not be read%s", tally.protected, tally.sealed, tally.plain, tally.unreadable,
                 f" ({'; '.join(sorted(set(tally.errors)))})" if tally.errors else "")
    return tally


__all__ = ["CannotOpen", "ENTROPY", "HEADER", "LEFTOVER_AGE_S", "MAGIC", "NOT_HERE", "NOTE", "Newer", "STORE_FOLDERS",
           "Tally", "Unavailable", "VERSION", "available", "is_protected", "migrate", "open_", "protected", "read",
           "readable", "seal", "store_files", "survey", "write"]
