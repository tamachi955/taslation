"""Text-only translation cache.

What is stored, per page unit: the page fingerprint, its aspect ratio, and for
each bubble its normalised position, a coarse outline of the bubble interior
and the translated text. What is *never* stored: page images, crops, or the
original Japanese text. The cache lets a page you already translated be
composited again instantly when it is on screen, and is useless without the
real page in your viewer.

Files are JSON under ``~/.taslation/cache``, protected at rest so that only the
Windows user who saved them can open them, on this computer (`protect.py`:
Windows DPAPI; a file of an earlier version, plain JSON, is read as it is and
protected at the next start or save). Copied to another computer or opened by
another Windows user they cannot be read; the passphrase-encrypted export
(`backup.py`) is what moves a book's translations. A book's file is
``<name>[.<language>].json``; when that file
already holds another book whose name gives the same file name (letter case on
Windows, punctuation, the 120-character cut), it is ``<name>-<hash>[.<language>].json``
instead, the hash being of the exact name (see `CacheStore.path_for`; every
store names its files so, `names.py`). A file this version cannot read (damaged,
written by a newer TASlation, or protected for another Windows user or computer)
is kept beside as ``<file stem>.unreadable-<date>.json`` before a fresh cache
takes its place, never written over (`names.set_aside`).

The file's header may also say what the book is as its colophon names it (`DETAIL_FIELDS`: the title, the volume,
the author, the publisher, the ISBN; each optional, cleaned and bounded, never text from a page's bubbles), and
`CacheStore.identities` reads the book, the language, those details and the page fingerprints of every cache
without building its pages, which is what recognising a book by a page needs (`bookid.recognise`).
"""

from __future__ import annotations

import bisect
import errno
import json
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

from . import protect
from .atomic import write_atomic
from .fingerprint import FINGERPRINT_BITS, FINGERPRINT_HEX_LEN, hamming
from .names import (
    DAMAGED, WINDOWS_DEVICES, Unreadable, check_schema, delete_files, drop_leftovers, file_names, files_of, is_copy,
    is_listed, language_key, load_object, pick, read_object, set_aside, slugify,
)
from .textclean import clean_text

SCHEMA_VERSION = 1
NBox = tuple[float, float, float, float]
MAX_COORD = 1e5  # a normalised coordinate beyond this is no bubble (a page is 1 wide; a capture some thousand pixels)
INDEXED_WITHIN = 6  # the distance in bits within which a page replaces another that the index serves (`_PageIndex`)
SAME_BOX = 1e-3  # two normalised boxes this close are the same box (a saved file keeps four decimals)
# optional header fields: the book as its colophon names it (written only when known), with their length bounds
DETAIL_FIELDS = ("title", "volume", "author", "publisher", "isbn")
DETAIL_LIMITS = {"title": 120, "volume": 16, "author": 120, "publisher": 120, "isbn": 20}


def clean_detail(name: str, value: Any) -> str:
    """The header field *name* (one of `DETAIL_FIELDS`) as kept: a string of one line, without controls or links, at
    most `DETAIL_LIMITS` characters; "" for anything else (a number, a list, a field of another name)."""
    if name not in DETAIL_LIMITS or not isinstance(value, str):
        return ""
    return clean_text(value, DETAIL_LIMITS[name])


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not a finite number")
    return number


def _coord(value: Any) -> float:
    number = _finite(value)
    if abs(number) > MAX_COORD:
        raise ValueError("not a position on the page")
    return number


@dataclass
class CachedBubble:
    box: NBox  # normalised to the page unit's content box
    text: str
    poly: list[tuple[float, float]] = field(default_factory=list)  # normalised interior outline
    flags: list[str] = field(default_factory=list)  # why the translation deserves a look (cleared when the reader edits it)
    note: str = ""  # a note for the reader (a pun, a reference the translation cannot carry)
    angle: float = 0.0  # degrees its lettering is turned counter-clockwise (`TextRegion.angle`; written when not 0)

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"box": [round(v, 4) for v in self.box], "text": self.text}
        if self.poly:
            d["poly"] = [[round(x, 4), round(y, 4)] for x, y in self.poly]
        if self.flags:
            d["flags"] = list(self.flags)
        if self.note:
            d["note"] = self.note
        if self.angle:
            d["angle"] = round(self.angle, 2)
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "CachedBubble":
        """The bubble *d* describes; ValueError (or TypeError, KeyError) for one no pipeline wrote, such as a
        position that is not a finite number on the page (drawing it would fail). The "draft" mark an earlier version
        wrote on a first draft is left out: the bubble is a translation like any other."""
        box = tuple(_coord(v) for v in d["box"])
        if len(box) != 4:
            raise ValueError("bad box")
        poly = [(_coord(p[0]), _coord(p[1])) for p in d.get("poly", [])]
        flags = [str(f) for f in d.get("flags", []) if f]
        angle = _finite(d.get("angle", 0.0))
        return cls(box=box, text=str(d.get("text", "")), poly=poly, flags=flags,  # type: ignore[arg-type]
                   note=str(d.get("note", "") or ""), angle=angle if abs(angle) < 90 else 0.0)


@dataclass
class CachedPage:
    fingerprint: str
    aspect: float
    bubbles: list[CachedBubble]
    seq: int = 0  # order in which the page was first seen
    # the page has text the model gave nothing usable for: what it did give is kept here, and reading the page
    # translates what is missing (`Pipeline.process`), as a whole-book run does (`Pipeline.scan`)
    incomplete: bool = False

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "fp": self.fingerprint,
            "aspect": round(self.aspect, 4),
            "seq": self.seq,
            "bubbles": [b.to_json() for b in self.bubbles],
        }
        if self.incomplete:
            d["incomplete"] = True
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "CachedPage":
        fp = str(d["fp"]).lower()
        if len(fp) != FINGERPRINT_HEX_LEN or any(c not in "0123456789abcdef" for c in fp):
            raise ValueError("bad fingerprint")
        return cls(
            fingerprint=fp,
            aspect=_finite(d.get("aspect", 0.0)),
            seq=int(d.get("seq", 0)),  # OverflowError for an infinite one
            bubbles=[CachedBubble.from_json(b) for b in d.get("bubbles", [])],
            incomplete=d.get("incomplete") is True,
        )


Stamp = tuple[int, int, int]
NO_FILE: Stamp = (0, 0, 0)


def _stamp(path: Path) -> Stamp:
    """Which version of the file is on disk. Every save writes a new file in place of the old one, so its file id
    changes even when two saves fall in the same tick of the file clock (a millisecond or more on Windows)."""
    try:
        st = os.stat(path)
    except OSError:
        return NO_FILE
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def cache_names(book: str, language: str = "English") -> tuple[str, str]:
    """The two names the cache file of *book* in *language* can have: ``<name>[.<language>].json``, and
    ``<name>-<hash>[.<language>].json`` for when the first holds another book whose name gives the same one
    (`names.file_names`; `slugify`, `language_key` and `WINDOWS_DEVICES` come from there too)."""
    return file_names(book, language)


def _recorded(data: dict[str, Any]) -> tuple[str, str]:
    """The book and the language, as written, that a cache file's JSON *data* records (as `BookCache.from_json` takes
    them)."""
    return str(data.get("book", "untitled")), str(data.get("language", "English"))


def stored_book(path: Path) -> tuple[str, str] | None:
    """The book and the language key (`language_key`) of the cache file at *path*, as `BookCache.load` would give
    them but without building its pages; None when there is no such file or it holds no JSON object."""
    data = read_object(path)
    if data is None:
        return None
    book, language = _recorded(data)
    return book, language_key(language)


def book_key_from_title(title: str) -> str:
    """Derive a stable book name from a viewer window title: what a browser adds, its name and the profile before it,
    goes first (`capture.windows.browser_tab`), which would else pass for the book; then the viewer's parts at either
    end, as learned on this computer (`viewerparts.book_key_from_title`: no store or viewer is named in TASlation),
    and a page number at the end. A title of nothing but the viewer's parts gives itself, which names no book."""
    from .viewerparts import book_key_from_title as learned

    return learned(title)


def viewer_key_from_title(title: str) -> str:
    """Name of the viewer application in a window title (what is left once the book name is removed).

    "Some Book - <a viewer's part learned> - Google Chrome" -> "<that part> - Google Chrome"; a title of nothing but
    a viewer's part, "<viewer> - Google Chrome" -> "Google Chrome"; "<viewer>" -> "<viewer>". Used to remember the
    capture area per viewer rather than per book.
    """
    t = " ".join(title.split())
    book = book_key_from_title(t)
    if book and book != "untitled" and book in t and book != t:
        rest = t.replace(book, "", 1).strip(" -–|")
        return rest or t
    return t or "untitled"


# --- the fingerprint index ---------------------------------------------------------------------------------------

_CHUNKS = INDEXED_WITHIN + 1
# chunk c of a fingerprint: every bit whose position is c modulo _CHUNKS, so that each chunk samples the whole page
# (the 16 rows of the difference hash and the average hash) rather than one band of it that many pages may share
_CHUNK_MASKS = tuple(sum(1 << bit for bit in range(chunk, FINGERPRINT_BITS, _CHUNKS)) for chunk in range(_CHUNKS))
_HEX_FINGERPRINT = re.compile(f"[0-9a-fA-F]{{{FINGERPRINT_HEX_LEN}}}")
_SCAN = object()  # what `_PageIndex.find` gives for a fingerprint it cannot look up: compare every page


def _chunk_keys(fingerprint: Any) -> tuple[int, ...] | None:
    """The chunks of *fingerprint* (each its bits in place, the others cleared); None for one that is not
    FINGERPRINT_HEX_LEN hex digits, which no pipeline makes and the index leaves to a comparison every time."""
    if not isinstance(fingerprint, str) or _HEX_FINGERPRINT.fullmatch(fingerprint) is None:
        return None
    value = int(fingerprint, 16)
    return tuple(value & mask for mask in _CHUNK_MASKS)


class _PageIndex:
    """Where the pages of a cache's list are by fingerprint, so that `BookCache._place` finds the first page within
    INDEXED_WITHIN bits of a fingerprint without comparing it with every page (a merge of N pages into N compared up
    to N times N fingerprints: 5,000 into 5,000 took 13 to 23 seconds, and takes under a tenth of one).

    Pigeonhole: the fingerprint is split into INDEXED_WITHIN + 1 chunks of its bits (`_CHUNK_MASKS`), and two
    fingerprints that differ in at most INDEXED_WITHIN bits differ in at most that many chunks, so they agree exactly
    on one at least. A dict per chunk, from its value to the positions of the pages that have it, gives every page
    that can be so near; the exact distance is then checked as before, in the order of the list. A fingerprint that
    is not FINGERPRINT_HEX_LEN hex digits is compared every time. The index also counts the sequence numbers in use
    and knows the highest, so that a page placed after the others gets its number without a scan either.

    It stands for one list as it was when it last changed it: `BookCache` indexes its list anew when that is another
    list (a reload, a removal) or has another length, and changes the pages of the list only through `_place`
    otherwise, which keeps the index in step (`rename` and `put_texts` change texts only)."""

    def __init__(self, pages: list[CachedPage]) -> None:
        self.pages = pages  # the list the index stands for
        self.chunks: list[dict[int, list[int]]] = [{} for _ in _CHUNK_MASKS]  # per chunk: value -> positions
        self.keys: list[tuple[int, ...] | None] = []  # per position: the chunks of its page; None: not indexed
        self.ids: list[int] = []  # per position: id() of the page there
        self.odd: list[int] = []  # the positions whose fingerprint is not indexed, ascending: compared every time
        self.members: dict[int, int] = {}  # id() of a page in the list -> at how many positions it is
        self.seqs: dict[Any, int] = {}  # sequence number -> how many pages have it
        self.top: Any = None  # the highest sequence number; None while there is no page
        for page in pages:
            self.append(page)

    def current(self, pages: list[CachedPage]) -> bool:
        """True when the index stands for *pages*: the same list, as long as when the index last changed it."""
        return self.pages is pages and len(self.keys) == len(pages)

    def holds(self, page: CachedPage) -> bool:
        """True when *page* itself (not one like it) is in the list."""
        return id(page) in self.members

    @property
    def next_seq(self) -> int:
        """`BookCache.next_seq` of the list."""
        return (-1 if self.top is None else self.top) + 1

    def find(self, fingerprint: str, within: int) -> Any:
        """The position of the first page in the list whose fingerprint is within *within* bits of *fingerprint*
        (at most INDEXED_WITHIN), None when there is none; _SCAN for a fingerprint the index cannot look up."""
        keys = _chunk_keys(fingerprint)
        if keys is None:
            return _SCAN
        near = set(self.odd)
        for chunk, key in zip(self.chunks, keys):
            positions = chunk.get(key)
            if positions:
                near.update(positions)
        for position in sorted(near):
            if hamming(self.pages[position].fingerprint, fingerprint) <= within:
                return position
        return None

    def append(self, page: CachedPage) -> None:
        """Take in *page*, which goes after the others in the list."""
        self._enter(len(self.keys), page)
        self.seqs[page.seq] = self.seqs.get(page.seq, 0) + 1
        if self.top is None or page.seq > self.top:
            self.top = page.seq

    def replace(self, position: int, page: CachedPage) -> None:
        """Take in *page*, which takes the place and the sequence number of the page at *position* in the list."""
        self._leave(position)
        self._enter(position, page)

    def _enter(self, position: int, page: CachedPage) -> None:
        keys = _chunk_keys(page.fingerprint)
        if keys is None:
            bisect.insort(self.odd, position)
        else:
            for chunk, key in zip(self.chunks, keys):
                positions = chunk.get(key)
                if positions is None:
                    chunk[key] = [position]
                else:
                    positions.append(position)
        if position == len(self.keys):
            self.keys.append(keys)
            self.ids.append(id(page))
        else:
            self.keys[position], self.ids[position] = keys, id(page)
        self.members[id(page)] = self.members.get(id(page), 0) + 1

    def _leave(self, position: int) -> None:
        keys = self.keys[position]
        if keys is None:
            self.odd.remove(position)
        else:
            for chunk, key in zip(self.chunks, keys):
                positions = chunk[key]
                positions.remove(position)
                if not positions:
                    del chunk[key]
        member = self.ids[position]
        if self.members[member] > 1:
            self.members[member] -= 1
        else:
            del self.members[member]


class TextEdit(NamedTuple):
    """A bubble's text changed from *old* to *new* (`BookCache.put_texts`): the bubble is the one of the page
    *fingerprint* at *box* that holds *old*."""

    fingerprint: str
    box: NBox
    old: str
    new: str

    def undone(self) -> "TextEdit":
        """The same edit the other way round."""
        return self._replace(old=self.new, new=self.old)


class BookCache:
    """All translated pages of one book (one JSON file)."""

    def __init__(self, path: Path, book: str, model: str, language: str = "English"):
        self.path = Path(path)
        self.book = book
        self.model = model
        self.language = language
        self.pages: list[CachedPage] = []
        self.created = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.updated = self.created
        self.dirty = False
        self.stamp = NO_FILE  # the version of the file this copy reflects (`_stamp`); NO_FILE = not loaded from one
        self.touched: dict[str, CachedPage] = {}  # pages this process changed since its last save, by fingerprint
        self.removed: list[str] = []  # fingerprints of pages this process removed since its last save
        self._index: _PageIndex | None = None  # where the pages are by fingerprint, made when a page is placed
        self.details: dict[str, str] = {}  # the header's `DETAIL_FIELDS` that are known (the colophon's)
        self._details_set = False  # this process set them since its last save: they win over the file's

    def set_details(self, **details: Any) -> bool:
        """Keep what the colophon says of the book in the header (`DETAIL_FIELDS`: title, volume, author, publisher,
        isbn); a field given as "" is forgotten, one not given stays. Returns True when that changed anything (the
        cache is then saved with the next save)."""
        new = dict(self.details)
        for name, value in details.items():
            if name not in DETAIL_LIMITS:
                raise TypeError(f"no header field {name!r}")
            cleaned = clean_detail(name, value)
            if cleaned:
                new[name] = cleaned
            else:
                new.pop(name, None)
        if new == self.details:
            return False
        self.details = {name: new[name] for name in DETAIL_FIELDS if name in new}
        self._details_set = self.dirty = True
        return True

    # --- persistence --------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "BookCache":
        """The cache in the file at *path*. FileNotFoundError when there is none, another OSError when it cannot be
        opened, `names.Unreadable` (a ValueError) when this version cannot read it: no JSON object, no list of pages,
        another schema (`names.NEWER`: a newer TASlation's)."""
        data = load_object(path)
        if data is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(path))
        return cls._from_file(data, path)

    @classmethod
    def _from_file(cls, data: dict[str, Any], path: Path) -> "BookCache":
        """The cache that the JSON object *data* just read from the file at *path* holds; Unreadable when this
        version cannot read it."""
        check_schema(data, SCHEMA_VERSION)
        if not isinstance(data.get("pages", []), list):
            raise Unreadable("damaged: no list of pages")
        try:
            cache = cls.from_json(data, path)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise Unreadable(DAMAGED) from None
        cache.stamp = _stamp(path)
        return cache

    @classmethod
    def from_json(cls, data: dict[str, Any], path: Path) -> "BookCache":
        """The cache that ``to_json`` gave *data* for (a file's, or an imported backup's), kept at *path*."""
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unsupported cache schema in {path}")
        pages = data.get("pages", [])
        if not isinstance(pages, list):
            raise ValueError(f"no list of pages in {path}")
        cache = cls(path, str(data.get("book", "untitled")), str(data.get("model", "?")), str(data.get("language", "English")))
        cache.created = str(data.get("created", cache.created))
        cache.updated = str(data.get("updated", cache.updated))
        cache.details = {name: value for name in DETAIL_FIELDS if (value := clean_detail(name, data.get(name)))}
        for raw in pages:
            try:
                cache.pages.append(CachedPage.from_json(raw))
            except (ValueError, TypeError, KeyError, OverflowError):
                continue  # a hand-edited or damaged page entry is skipped, not fatal
        return cache

    def refresh(self) -> bool:
        """Pick up what another process saved meanwhile (a batch run while the app is open, or the reverse).

        When the file is another version than this copy's, it is reloaded and the
        pages this process changed since its last save are applied on top. Returns
        True when something was reloaded.
        """
        if _stamp(self.path) == self.stamp:
            return False
        try:
            fresh = BookCache.load(self.path)
        except (ValueError, OSError):  # gone, cannot be opened now, or this version cannot read it (Unreadable)
            return False
        if fresh.owner != self.owner:
            return False  # another book took the file meanwhile: its pages are never this book's (`save` moves on)
        self._take(fresh)
        return True

    def _take(self, fresh: "BookCache") -> None:
        """Take the pages of *fresh*, this book's cache as just read from its file, with the changes this process
        made since its last save on top."""
        self.pages, self.created, self.updated, self.stamp = fresh.pages, fresh.created, fresh.updated, fresh.stamp
        if not self._details_set:  # the header's details as the file has them, unless this process set its own
            self.details = dict(fresh.details)
        self._index = None
        for fp in self.removed:
            self.pages = [p for p in self.pages if hamming(p.fingerprint, fp) > 6]
        for page in list(self.touched.values()):
            self._place(page)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "app": "taslation",
            "note": "Translated text and bubble geometry keyed by page fingerprints. "
                    "Contains no page images and no original text; useless without the book open in your viewer.",
            "book": self.book,
            "model": self.model,
            "language": self.language,
            "created": self.created,
            "updated": self.updated,
            **{name: self.details[name] for name in DETAIL_FIELDS if self.details.get(name)},
            "pages": [p.to_json() for p in sorted(self.pages, key=lambda p: p.seq)],  # last: `CacheStore.identities`
        }

    @property
    def owner(self) -> tuple[str, str]:
        """The book and the language key: what `stored_book` reads from this cache's file."""
        return self.book, language_key(self.language)

    def save(self, merge: bool = True) -> None:
        """Write the file, merging in what other processes saved since this copy was loaded (never clobbering it);
        with ``merge=False`` this copy replaces what the file holds. When another process gave the file to another
        book meanwhile (one whose name gives the same file name, opened before either was saved), this cache moves
        to its book's other file name instead (`cache_names`). A file there that this version cannot read (written
        meanwhile: damaged, by a newer TASlation, or protected for another Windows user or computer) is set aside
        first, never written over (`names.set_aside`); an OSError, and nothing written, when the file cannot be opened
        now or this system cannot protect it (`protect.Unavailable`). The file is written protected, sealed before
        anything reaches the disk (`protect.protected`), all or nothing (`write_atomic`)."""
        if merge:
            self._take_in()
        self.updated = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_json(), ensure_ascii=False, indent=1).encode("utf-8")
        write_atomic(self.path, protect.protected(payload))
        self.stamp = _stamp(self.path)
        self.touched.clear()
        self.removed.clear()
        self.dirty = self._details_set = False

    def _take_in(self) -> None:
        """Before a merging save: take in what another process saved in the file since this copy was loaded, move
        to this book's other file name when the file holds another book's cache (`_step_aside`), and set aside a
        file this version cannot read. OSError when the file cannot be opened now."""
        while _stamp(self.path) != self.stamp:
            try:
                data = load_object(self.path)
                if data is None:
                    return  # deleted meanwhile: this copy is written anew
                book, language = _recorded(data)
                if (book, language_key(language)) != self.owner:
                    self._step_aside(book)
                    continue
                fresh = BookCache._from_file(data, self.path)
            except Unreadable as e:
                set_aside(self.path, e.reason)
                return
            self._take(fresh)
            return

    def _step_aside(self, there: str) -> None:
        """The file holds the cache of the book *there*: move to this book's hashed file name (and take in what that
        file holds of this book, `_take_in`); FileExistsError when there is no such name to move to or it holds
        another book too."""
        plain, hashed = cache_names(self.book, self.language)
        target = self.path.with_name(hashed)
        if os.path.normcase(self.path.name) != os.path.normcase(plain) or stored_book(target) not in (None, self.owner):
            raise FileExistsError(f"{self.path} now holds the cache of {there!r}, whose name gives the same file as "
                                  f"{self.book!r}; the cache of {self.book!r} was not saved")
        self.path, self.stamp = target, NO_FILE

    # --- queries ------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.pages)

    @property
    def bubble_count(self) -> int:
        return sum(len(p.bubbles) for p in self.pages)

    @property
    def next_seq(self) -> int:
        return max((p.seq for p in self.pages), default=-1) + 1

    def lookup(self, fingerprint: str, aspect: float, max_distance: int, hint_seq: int | None = None,
               aspect_tolerance: float = 0.12) -> tuple[CachedPage, int] | None:
        """Best matching page within *max_distance* bits; ties go to the page after *hint_seq*."""
        best: tuple[int, int, CachedPage] | None = None  # (distance, seq penalty, page)
        for page in self.pages:
            if aspect and page.aspect and abs(page.aspect - aspect) / max(page.aspect, aspect) > aspect_tolerance:
                continue
            d = hamming(fingerprint, page.fingerprint)
            if d > max_distance:
                continue
            penalty = 0 if hint_seq is None else abs(page.seq - (hint_seq + 1))
            key = (d, penalty, page)
            if best is None or (key[0], key[1]) < (best[0], best[1]):
                best = key
        if best is None:
            return None
        return best[2], best[0]

    def add(self, page: CachedPage, replace_within: int = 6) -> CachedPage:
        """Insert a page; a near-identical fingerprint already present is replaced (its sequence number is kept)."""
        self._place(page, replace_within)
        self.touched[page.fingerprint] = page
        self.dirty = True
        return page

    def put_back(self, page: CachedPage) -> CachedPage:
        """`add` for a page `remove` took away a moment ago: a merging save no longer takes it out of the file."""
        self.removed = [fp for fp in self.removed if hamming(fp, page.fingerprint) > 6]
        return self.add(page)

    def rename(self, pairs: list[tuple[str, str]]) -> int:
        """Replace whole-word renderings in every cached translation (old -> new); returns how many bubbles changed.

        This is the editor's consistency pass: when the series sheet settles on
        a name, the pages translated before it get the same spelling.
        """
        compiled = [(re.compile(r"(?<![A-Za-z\u00C0-\u024F])" + re.escape(old) + r"(?![A-Za-z\u00C0-\u024F])"), new)
                    for old, new in pairs if old and new and old != new]
        if not compiled:
            return 0
        changed = 0
        for page in self.pages:
            touched = False
            for b in page.bubbles:
                text = b.text
                for rx, new in compiled:
                    text = rx.sub(new, text)
                if text != b.text:
                    b.text = text
                    touched = True
                    changed += 1
            if touched:
                self.touched[page.fingerprint] = page
                self.dirty = True
        return changed

    def put_texts(self, edits: Iterable[TextEdit]) -> list[TextEdit]:
        """Make *edits*, each only where its bubble still holds its old text: the text is all that changes (flags,
        note, the page's mark and every position stay, as in `rename`). Returns the edits that were made; a save writes
        them, and a merging save keeps them as it keeps a page added."""
        pages = {page.fingerprint: page for page in self.pages}
        made: list[TextEdit] = []
        for edit in edits:
            page = pages.get(edit.fingerprint)
            if page is None:
                continue
            for bubble in page.bubbles:
                if bubble.text == edit.old and all(abs(a - b) <= SAME_BOX for a, b in zip(bubble.box, edit.box)):
                    made.append(edit)
                    bubble.text = edit.new
                    self.touched[page.fingerprint] = page
                    self.dirty = True
                    break
        return made

    def remove(self, fingerprint: str, replace_within: int = 6) -> int:
        """Forget the page with (nearly) this fingerprint; returns how many entries went."""
        before = len(self.pages)
        self.pages = [p for p in self.pages if hamming(p.fingerprint, fingerprint) > replace_within]
        self._index = None  # another list: indexed anew when a page is placed
        gone = before - len(self.pages)
        if gone:
            self.removed.append(fingerprint)
            self.touched.pop(fingerprint, None)
            self.dirty = True
        return gone

    def _indexed(self) -> _PageIndex:
        """The index of the list of pages, made anew when it stands for another list (`_PageIndex.current`)."""
        if self._index is None or not self._index.current(self.pages):
            self._index = _PageIndex(self.pages)
        return self._index

    def _place(self, page: CachedPage, replace_within: int = 6) -> None:
        """Put *page* in place of the first page in the list whose fingerprint is within *replace_within* bits of its
        own, with that page's sequence number; else after the others, with a sequence number of its own (the next one
        when it has none or another page has it). The page is found through the index (`_PageIndex`) when
        *replace_within* is the distance it serves, else by comparing every page in turn: the same page either way."""
        index: _PageIndex | None = self._indexed()
        if index.holds(page):  # the page itself is in the list: taking another page's number would change a number
            self._index = index = None  # the index counts, so this once without it (it is made anew next time)
        found: Any = _SCAN
        if index is not None and replace_within == INDEXED_WITHIN:
            found = index.find(page.fingerprint, replace_within)
        if found is _SCAN:
            found = next((i for i, existing in enumerate(self.pages)
                          if hamming(existing.fingerprint, page.fingerprint) <= replace_within), None)
        if found is not None:
            page.seq = self.pages[found].seq
            if index is not None:
                index.replace(found, page)
            self.pages[found] = page
            return
        if index is None:
            if page.seq < 0 or any(p.seq == page.seq for p in self.pages):
                page.seq = self.next_seq
        elif page.seq < 0 or page.seq in index.seqs:
            page.seq = index.next_seq
        if index is not None:
            index.append(page)
        self.pages.append(page)


class CacheIdentity(NamedTuple):
    """What recognising a book by one of its pages needs of a cache file (`CacheStore.identities`)."""

    file: str
    book: str
    language: str  # as the file records it
    pages: tuple[tuple[str, float], ...]  # (fingerprint, aspect) of every page, in the file's order
    details: dict[str, str]  # the header's `DETAIL_FIELDS` that are known (the colophon's)


_PAGES_KEY = re.compile(r'"pages"\s*:\s*\[')
_PAGE_FP = re.compile(r'"fp"\s*:\s*"([0-9A-Fa-f]{%d})"(?:\s*,\s*"aspect"\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?))?'
                      % FINGERPRINT_HEX_LEN)
_Read = tuple[dict[str, Any], tuple[tuple[str, float], ...]]  # a cache file's header and its pages' fingerprints


def _aspect(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) and number > 0 else 0.0


def _read_identity(path: Path) -> _Read | None:
    """The header (every field but the pages) and the pages' (fingerprint, aspect) of the cache file at *path*, read
    without building its pages: the header from the text before the list of pages (which a save writes last), the
    fingerprints by their pattern in the rest, which in a file `json.dumps` wrote can only be the pages' own (a quote
    inside a string is escaped). A file of another shape (written by hand) is parsed whole instead. A protected file
    is opened first (`protect.read`), a plain one of an earlier version read as it is. None when there is no such
    file, it cannot be read or opened here, or `BookCache.load` would refuse it for what this can tell (no complete
    JSON object, another schema, no list of pages)."""
    try:
        text = protect.read(path).decode("utf-8-sig")
    except (OSError, ValueError):  # protect.CannotOpen and UnicodeDecodeError are ValueErrors
        return None
    if not text.rstrip().endswith("}"):
        return None  # cut short, or no object: no JSON object to read
    head: dict[str, Any] | None = None
    match = _PAGES_KEY.search(text)
    if match is not None:
        before = text[: match.start()].rstrip()
        try:
            parsed = json.loads((before[:-1] if before.endswith(",") else before) + "}")
        except (ValueError, RecursionError):
            parsed = None
        if isinstance(parsed, dict) and "schema" in parsed and "pages" not in parsed:
            head = parsed
    if head is not None and match is not None:
        if head.get("schema") != SCHEMA_VERSION:
            return None
        pages = tuple((m.group(1).lower(), _aspect(m.group(2))) for m in _PAGE_FP.finditer(text, match.end()))
        return head, pages
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION or not isinstance(data.get("pages", []), list):
        return None
    found: list[tuple[str, float]] = []
    for raw in data.get("pages", []):
        fp = str(raw.get("fp", "")).lower() if isinstance(raw, dict) else ""
        if len(fp) == FINGERPRINT_HEX_LEN and all(c in "0123456789abcdef" for c in fp):
            found.append((fp, _aspect(raw.get("aspect"))))
    return {k: v for k, v in data.items() if k != "pages"}, tuple(found)


class CacheStore:
    """The cache directory: one JSON file per book."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self._read: dict[str, tuple[Stamp, _Read | None]] = {}  # `identities`: what each file held, by its stamp
        self._read_lock = threading.Lock()  # the window reads them on its thread, its worker at the start

    def _identity_of(self, path: Path) -> _Read | None:
        """`_read_identity` of the file at *path*, read again only once the file has changed (`_stamp`)."""
        key, stamp = os.path.normcase(str(path)), _stamp(path)
        with self._read_lock:
            known = self._read.get(key)
        if known is not None and known[0] == stamp and stamp != NO_FILE:
            return known[1]
        read = _read_identity(path)
        with self._read_lock:
            self._read[key] = (stamp, read)
        return read

    def _owner_of(self, path: Path) -> tuple[str, str] | None:
        """`stored_book` of the file at *path*, from what `_identity_of` read of it."""
        read = self._identity_of(path)
        if read is None:
            return None
        book, language = _recorded(read[0])
        return book, language_key(language)

    def identities(self) -> list[CacheIdentity]:
        """The book, the language, the header's details and the page fingerprints of every cache `list` gives (each
        book's file in every language, not the copies kept beside them), without building their pages; what
        recognising a book by a page needs (`bookid.recognise`). A file read before is read again only once it has
        changed: 30 protected caches of 200 pages take some 140 ms the first time (each opened, `protect.read`; 23 ms
        as the plain files of before), 1.4 ms after that (measured 2026-11-14).
        A page whose bubbles a load would refuse still counts here by its fingerprint."""
        out: list[CacheIdentity] = []
        if not self.cache_dir.is_dir():
            return out
        present: set[str] = set()
        for path in sorted(self.cache_dir.glob("*.json")):
            if is_copy(path):
                continue  # set aside, never read (`names.set_aside`)
            present.add(os.path.normcase(str(path)))
            read = self._identity_of(path)
            if read is None:
                continue
            head, pages = read
            book, language = _recorded(head)
            if not is_listed(path, book, language, self._owner_of):
                continue  # a backup or a copy of a book's cache, not the cache itself
            details = {name: value for name in DETAIL_FIELDS if (value := clean_detail(name, head.get(name)))}
            out.append(CacheIdentity(str(path), book, language, pages, details))
        with self._read_lock:
            for key in [k for k in self._read if k not in present]:
                del self._read[key]  # a file gone (deleted, renamed by hand) is forgotten
        return out

    def path_for(self, book: str, language: str = "English") -> Path:
        """The cache file of *book* in *language*: one per book and target language, so switching languages never
        mixes translations. It is ``<name>[.<language>].json`` (`cache_names`) when there is no such file or it
        holds this very book (the exact name; the language by its key). When it holds another book whose name gives
        the same file name ("Pebble:Harbor 1" and "Pebble Harbor 1"; "QUILLPOND 1" and "Quillpond 1" on Windows), the book's file is
        ``<name>-<hash>[.<language>].json``; FileExistsError when that one holds another book too (two names with
        the same hash). Reads the stored names of two files at most; never renames one. A file too damaged to tell
        whose it is counts as free (`open` sets it aside)."""
        return pick(self.cache_dir, book, language, stored_book, "the cache")

    def page_count(self, book: str, language: str = "English") -> int | None:
        """How many translated pages the cache of *book* in *language* holds, from its file's page list alone (as
        `identities` reads it, without building the pages): 0 when there is no file; None when that cannot be told
        (the file cannot be read, or holds another book)."""
        try:
            path = self.path_for(book, language)
        except OSError:
            return None
        if not path.is_file():
            return 0
        read = self._identity_of(path)
        if read is None:
            return None
        there, there_language = _recorded(read[0])
        if (there, language_key(there_language)) != (book, language_key(language)):
            return None
        return len(read[1])

    def open(self, book: str, model: str, language: str = "English") -> BookCache:
        """The cache of *book* in *language*, from its file (`path_for`), or a new one a save will put there. A file
        this version cannot read (damaged, or written by a newer TASlation) is first set aside as ``<file
        stem>.unreadable-<date>.json``, never written over (`names.set_aside`); a file of another book is never read
        as this one's, nor moved (FileExistsError); OSError when the file cannot be opened."""
        path = self.path_for(book, language)
        try:
            data = load_object(path)
            if data is None:
                return BookCache(path, book, model, language)
            there, there_language = _recorded(data)
            if (there, language_key(there_language)) != (book, language_key(language)):  # written since path_for
                raise FileExistsError(f"{path} holds the cache of {there!r} in {there_language}, not that of {book!r}")
            cache = BookCache._from_file(data, path)
        except Unreadable as e:
            set_aside(path, e.reason)
            return BookCache(path, book, model, language)
        cache.model = cache.model or model
        return cache

    def _is_cache_file(self, path: Path, cache: BookCache) -> bool:
        """True when *path* is the file `path_for` gives the book of *cache* (loaded from it), not a copy kept beside
        it; on Windows whatever the letter case of the name on disk."""
        return is_listed(path, cache.book, cache.language, stored_book)

    def list(self) -> list[dict[str, Any]]:
        """The cache of every book in every language: the files `path_for` gives, not the copies kept beside them
        (``.before-import.*``, ``.before-apply.*``, ``.unreadable-*``, ``.corrupt``)."""
        out: list[dict[str, Any]] = []
        if not self.cache_dir.is_dir():
            return out
        for path in sorted(self.cache_dir.glob("*.json")):
            if is_copy(path):
                continue  # set aside, never read (`names.set_aside`)
            try:
                cache = BookCache.load(path)
            except Exception:
                continue
            if not self._is_cache_file(path, cache):
                continue  # a backup or a copy of a book's cache, not the cache itself
            out.append({
                "file": str(path),
                "book": cache.book,
                "model": cache.model,
                "language": cache.language,
                "pages": len(cache),
                "bubbles": cache.bubble_count,
                "updated": cache.updated,
            })
        return out

    def delete(self, book: str, language: str | None = None,
               recycle: Callable[[list[Path]], Any] | None = None) -> bool:
        """Delete the book's cache in every language (*language* None) or in *language* alone, under either name
        `path_for` gives it, with the copies kept beside it and what a save that stopped halfway left (its temporary
        files hold the same text). A file that cannot be read goes only when it has one of the book's own file names
        (of that language, or of any with *language* None, as in the other stores), or is a copy set aside from one of
        them (``.unreadable-<date>``, ``.corrupt``). With *recycle* (`recycle.to_recycle_bin`), the files go to it in
        one go instead of being deleted, and its error (OSError) leaves them where they are; the leftovers of a save
        are deleted all the same. Returns True when a file went."""
        if language is None and recycle is None:
            return delete_files(self.cache_dir, book, stored_book)
        files = self.files_of(book, language)
        if not files:
            return False
        if recycle is not None:
            recycle(files)
        else:
            for path in files:
                path.unlink()
        for path in files:
            drop_leftovers(path)
        return True

    def files_of(self, book: str, language: str | None = None) -> list[Path]:
        """The files `delete` takes for *book* (in *language* alone, or in every language with None): the book's own
        files (`names.files_of`) whose language is *language*, a file of no known book only under one of the two file
        names of the book in that language, or a copy set aside from one of them."""
        found = files_of(self.cache_dir, book, stored_book)
        if language is None:
            return found
        key = language_key(language)
        own = {os.path.normcase(name[:-len(".json")]) for name in cache_names(book, language)}
        out: list[Path] = []
        for path in found:
            there = stored_book(path)
            if there is not None and there[0] == book:
                if there[1] == key:
                    out.append(path)
                continue
            stem = os.path.normcase(path.name[:-len(".json")])
            if is_copy(path):
                stem = stem.rsplit(".", 1)[0]  # what it was set aside from
            if stem in own:
                out.append(path)
        return out


__all__ = [
    "DETAIL_FIELDS", "DETAIL_LIMITS", "FINGERPRINT_BITS", "BookCache", "CacheIdentity", "CacheStore", "CachedBubble",
    "CachedPage", "TextEdit", "WINDOWS_DEVICES", "book_key_from_title", "cache_names", "clean_detail", "language_key", "slugify",
    "stored_book", "viewer_key_from_title", "write_atomic",
]
