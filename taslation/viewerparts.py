"""What TASlation has learned of the viewers on this computer, and the book's name a viewer's window title gives.

TASlation comes with no list of e-book stores or viewers. A window's title carries the book's name with the name of
whatever shows it - a store's site after it ("<book> - <site>"), a viewer app's before it ("<app> - <book>"), or the
viewer's name alone, whatever book is open - and what of a title is the viewer's is learned here, on the reader's own
computer, from the reader's own choices. It is kept in the state folder's ``viewers.json`` and nowhere else: never in
a cache, an export or a log::

    {"version": 1,
     "parts": ["<viewer>"],              # title segments that are a viewer's, never a book's (`Memory.learn`)
     "books": ["<book>"],                # segments the reader said are a book's: never taken for a viewer's
     "titles": ["<book> - <viewer>"],    # the tab titles of the windows chosen as the viewer, the latest last
     "programs": ["<viewer>.exe"],       # the program files of the chosen windows that are no browser's
     "nameless": ["Google Chrome"],      # viewers (`cache.viewer_key_from_title`) whose one-segment titles named
                                         # no book
     "old_books": ["<book>"],            # the books kept when this version first ran in the folder (`migrate`)
     "migrated": true}

A title is cut into segments at " - ", " – ", " — ", " | " and "｜" (`spans`); the browser's own part ("- Google
Chrome", the profile before it) is never one of them (`capture.windows.browser_tab`). What is learned:

* A window chosen as the viewer (`chosen`) is remembered by its tab title, and a window that is no browser's by its
  program too; the next start chooses a window titled so, or of that program, by itself (`remembered`). Its title is
  set beside the titles chosen before: segments at the end of both that stay alike while what comes before them differs
  in more than its digits are the viewer's ("<book> - <site>", then "<another book> - <site>": `trailing_parts`).
  Only the end: by the custom of window titles a program or site names itself last, and the segments at the start that
  two titles share are as often the book's (its chapters, its volumes). A viewer that is no browser is followed through
  the changes of its own title the same way (`retitled`). A window chosen that gave no page before the reader chose
  another is not remembered, nor what choosing it taught (`corrected`).
* The reader's own naming (`named`): a name the reader gives the book that is its title with segments left out says
  that those are the viewer's (at either end); one that puts back a segment the title's name left out says that it is
  the book's; one that has nothing of a title of a single segment says that the title names no book there.
* The state folder of an earlier version (`migrate`, once): the viewers its capture profiles and last names were kept
  under name the segments that version's lists cut from the books' names, and the books then kept are found again
  under a title that carries one segment more (`book_for_title`).

What names no book on any computer (`PLACEHOLDERS`): nothing, "untitled", a new tab, a browser's name, a program's
name ("<name> for PC": `PROGRAM`). A title made of
nothing but the viewer's parts names no book either (`generic`), and nothing is kept under such a name (`bookid`). A
title of a single segment in a viewer whose such titles named no book before may be the viewer's name: it is held
back (`unconfirmed`, `hold`) until the reader says what the book is called, once.
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .atomic import write_atomic

STATE_FILE = "viewers.json"
VERSION = 1
PARTS_KEPT, BOOKS_KEPT, TITLES_KEPT, PROGRAMS_KEPT, NAMELESS_KEPT, OLD_BOOKS_KEPT = 200, 500, 24, 16, 32, 5000
MAX_PART = 80  # characters: a longer segment is no viewer's name
# what names no book on any computer: nothing, a new tab, the browsers (as `generic` compares them: `plain`)
PLACEHOLDERS = frozenset({
    "", "untitled", "new tab", "新しいタブ", "google chrome", "chrome", "microsoft edge", "edge", "firefox",
    "mozilla firefox", "brave", "vivaldi", "opera", "chromium",
})
# programs whose windows show anything, never one viewer: the browsers, the hosts of other programs' windows, the
# runtimes a program may run on (a window of one of them is never remembered by its program)
SHARED_PROGRAMS = frozenset({
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "vivaldi.exe", "opera.exe", "chromium.exe",
    "msedgewebview2.exe", "applicationframehost.exe", "explorer.exe", "dllhost.exe", "rundll32.exe", "python.exe",
    "pythonw.exe", "py.exe", "pyw.exe", "java.exe", "javaw.exe",
})
# a program's own name, as its window is titled while it shows no book ("<name> for PC"; `plain`)
PROGRAM = re.compile(r".*\S\s+for\s+(?:pc|windows)")
SEGMENT = re.compile(r"\s+[-–—|]\s+|\s*｜\s*")  # what parts a title into segments
PAGE_SEGMENT = re.compile(r"(?:(?:page|p\.?)\s*)?\d+(?:\s*/\s*\d+)?", re.IGNORECASE)  # "page 12", "12/200"
PAGE_ONLY = re.compile(r"(?:page|p\.?)\s*\d+(?:\s*/\s*\d+)?|\d+\s*/\s*\d+", re.IGNORECASE)  # never a volume
TRAILING_PAGE = re.compile(r"\s*[-–]\s*(?:page|p\.)\s*\d+\s*$", re.IGNORECASE)  # "<book> - page 12"
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏﻿"))
_LETTER = re.compile(r"[^\W\d_]")


def plain(text: Any) -> str:
    """*text* as titles are compared: NFKC (full-width letters and digits as plain ones), without zero-width
    characters, its spaces as single spaces, case folded."""
    t = unicodedata.normalize("NFKC", str(text or "")).translate(_INVISIBLE)
    return " ".join(t.casefold().split())


def spans(text: str) -> list[tuple[int, int]]:
    """Where the segments of *text* are (start, end), in order, each without the spaces around it; empty segments
    are left out."""
    out: list[tuple[int, int]] = []
    start = 0
    bounds = [(m.start(), m.end()) for m in SEGMENT.finditer(text)] + [(len(text), len(text))]
    for cut, after in bounds:
        piece = text[start:cut]
        if piece.strip(" -–—|｜"):
            lead = len(piece) - len(piece.lstrip(" -–—|｜"))
            trail = len(piece) - len(piece.rstrip(" -–—|｜"))
            out.append((start + lead, cut - trail))
        start = after
    return out


def segments(text: str) -> list[str]:
    """The segments of *text* (`spans`)."""
    return [text[a:b] for a, b in spans(text)]


def tab_of(title: str) -> str:
    """The part of a window's *title* the book and the viewer are in: without what a browser adds (its name, the
    profile, Edge's "and 2 more pages": `capture.windows.browser_tab`), its spaces as single spaces."""
    from .capture.windows import browser_tab

    return " ".join(browser_tab(str(title or "")).split())


def is_page_number(segment: str) -> bool:
    """Whether *segment* is a page's number ("12", "page 12", "12/200")."""
    return bool(PAGE_SEGMENT.fullmatch(plain(segment)))


def _browser_or_profile(segment: str) -> bool:
    from .capture.windows import PROFILE, _is_browser_name

    return _is_browser_name(segment) or bool(PROFILE.fullmatch(plain(segment)))


def learnable(segment: str) -> bool:
    """Whether *segment* can be a viewer's part: some letters, at most MAX_PART characters, no page number, no
    browser, no browser profile and none of `PLACEHOLDERS`."""
    p = plain(segment)
    return (bool(p) and len(p) <= MAX_PART and _LETTER.search(p) is not None and p not in PLACEHOLDERS
            and not is_page_number(p) and not _browser_or_profile(segment))


def _strings(value: Any, keep: int) -> list[str]:
    """The strings of a list read from the file, each once (by `plain`), the latest *keep*."""
    if not isinstance(value, list):
        return []
    out: dict[str, str] = {}
    for item in value:
        if isinstance(item, str) and item.strip():
            text = " ".join(item.split())
            out.pop(plain(text), None)
            out[plain(text)] = text
    return list(out.values())[-keep:] if keep else list(out.values())


class Memory:
    """What `viewers.json` holds (see the module); *path* None: kept in memory only (nothing is ever written)."""

    def __init__(self, path: Path | None = None, data: dict[str, Any] | None = None):
        self.path = path
        d = data if isinstance(data, dict) else {}
        self.parts = _strings(d.get("parts"), PARTS_KEPT)
        self.books = _strings(d.get("books"), BOOKS_KEPT)
        self.titles = _strings(d.get("titles"), TITLES_KEPT)
        self.programs = [p.lower() for p in _strings(d.get("programs"), PROGRAMS_KEPT)]
        self.nameless = _strings(d.get("nameless"), NAMELESS_KEPT)
        self.old_books = _strings(d.get("old_books"), OLD_BOOKS_KEPT)
        self.migrated = d.get("migrated") is True
        self._index()

    def _index(self) -> None:
        book_keys = {plain(b) for b in self.books}
        self.parts = [p for p in self.parts if plain(p) not in book_keys]
        self._parts = {plain(p) for p in self.parts}
        self._books = book_keys
        self._titles = {plain(t) for t in self.titles}
        self._nameless = {plain(n) for n in self.nameless}
        self._old = {plain(b): b for b in self.old_books}

    # ---------------------------------------------------------------- what is known
    def is_part(self, segment: str) -> bool:
        """Whether *segment* is a viewer's part."""
        return plain(segment) in self._parts

    def is_book(self, segment: str) -> bool:
        """Whether the reader said *segment* is a book's (never a viewer's)."""
        return plain(segment) in self._books

    def chose(self, title: str) -> bool:
        """Whether a window with the tab title *title* was chosen as the viewer before."""
        return plain(title) in self._titles

    def runs(self, program: str) -> bool:
        """Whether a window of the program *program* (its file name) was chosen as the viewer before."""
        return bool(program) and program.lower() in self.programs

    def is_nameless(self, viewer_key: str) -> bool:
        """Whether a title of a single segment named no book in the viewer *viewer_key* before."""
        return plain(viewer_key) in self._nameless

    def old_book(self, name: str) -> str:
        """The book kept when this version first ran that is called *name* (`plain`), as it is called; "" for none."""
        return self._old.get(plain(name), "")

    # ---------------------------------------------------------------- changes
    def learn(self, found: Iterable[str]) -> list[str]:
        """*found* are viewers' parts from now on (the ones that can be: `learnable`, not one the reader said is a
        book's); returns the ones that were not known."""
        added = []
        for segment in found:
            text = " ".join(str(segment).split())
            if learnable(text) and not self.is_book(text) and not self.is_part(text):
                self.parts.append(text)
                added.append(text)
        if added:
            self.parts = self.parts[-PARTS_KEPT:]
            self._index()
        return added

    def unlearn(self, found: Iterable[str]) -> bool:
        """*found* are no viewer's parts any more (they may be learned again); whether any was one."""
        gone = {plain(s) for s in found}
        kept = [p for p in self.parts if plain(p) not in gone]
        if len(kept) == len(self.parts):
            return False
        self.parts = kept
        self._index()
        return True

    def refuse(self, found: Iterable[str]) -> list[str]:
        """*found* are a book's, as the reader said: no viewer's part any more, and never learned as one again;
        returns the ones that were not known as a book's."""
        added = []
        for segment in found:
            text = " ".join(str(segment).split())
            if plain(text) and not self.is_book(text):
                self.books.append(text)
                added.append(text)
        if added:
            self.books = self.books[-BOOKS_KEPT:]
            self._index()
        return added

    def remember(self, title: str, program: str = "") -> bool:
        """The window with the tab title *title* (and the program *program*, unless it is one of `SHARED_PROGRAMS`)
        is the latest chosen as the viewer; whether anything changed."""
        changed = False
        title = " ".join(str(title or "").split())
        if title and (not self.titles or plain(self.titles[-1]) != plain(title)):
            self.titles = [t for t in self.titles if plain(t) != plain(title)] + [title]
            self.titles = self.titles[-TITLES_KEPT:]
            changed = True
        program = (program or "").lower()
        if program and program not in SHARED_PROGRAMS and (not self.programs or self.programs[-1] != program):
            self.programs = ([p for p in self.programs if p != program] + [program])[-PROGRAMS_KEPT:]
            changed = True
        if changed:
            self._index()
        return changed

    def forget(self, title: str, program: str = "") -> bool:
        """The window with the tab title *title* (and its program) is not remembered as the viewer any more."""
        before = (list(self.titles), list(self.programs))
        self.titles = [t for t in self.titles if plain(t) != plain(title)]
        self.programs = [p for p in self.programs if p != (program or "").lower()]
        self._index()
        return before != (self.titles, self.programs)

    def name_nameless(self, viewer_key: str) -> bool:
        """The viewer *viewer_key* has had a title of a single segment that named no book."""
        if not viewer_key or self.is_nameless(viewer_key):
            return False
        self.nameless = ([*self.nameless, " ".join(viewer_key.split())])[-NAMELESS_KEPT:]
        self._index()
        return True

    def to_json(self) -> dict[str, Any]:
        return {"version": VERSION, "parts": self.parts, "books": self.books, "titles": self.titles,
                "programs": self.programs, "nameless": self.nameless, "old_books": self.old_books,
                "migrated": self.migrated}

    def save(self) -> None:
        """Written all or nothing (none without a path; a folder that cannot be written keeps nothing)."""
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(self.path, json.dumps(self.to_json(), ensure_ascii=False, indent=1).encode("utf-8"))
        except OSError:
            pass


def memory_path(state_dir: Path | str) -> Path:
    """The file of what was learned in the state folder *state_dir*."""
    return Path(state_dir) / STATE_FILE


def _read(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _stamp(path: Path | None) -> tuple[int, int, int] | None:
    if path is None:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


_lock = threading.RLock()
_memory = Memory()
_memory_stamp: tuple[int, int, int] | None = None
_held: set[str] = set()  # the names held back this session until the reader says what the book is called


def use(state_dir: Path | str | None) -> Memory:
    """What was learned in the state folder *state_dir* is what this process goes by from now on (the window and the
    command line call it once their settings are read); the folder of an earlier version is looked through first,
    once (`migrate`). None: nothing learned, and nothing kept (what is learned meanwhile stays in memory)."""
    global _memory, _memory_stamp
    with _lock:
        _held.clear()
        if state_dir is None:
            _memory, _memory_stamp = Memory(), None
            return _memory
        path = memory_path(state_dir)
        _memory = Memory(path, _read(path))
        _memory_stamp = _stamp(path)
        if not _memory.migrated:
            migrate(Path(state_dir))
        return _memory


def current() -> Memory:
    """What this process goes by (`use`), read again once its file was changed by another process."""
    global _memory, _memory_stamp
    with _lock:
        path = _memory.path
        if path is not None:
            stamp = _stamp(path)
            if stamp != _memory_stamp:
                _memory = Memory(path, _read(path))
                _memory_stamp = stamp
        return _memory


def change(edit: Callable[[Memory], Any]) -> Any:
    """*edit* made on what the file holds now (a change another process made meanwhile is kept), and the file
    written when *edit* returns something true; returns what *edit* returned."""
    global _memory, _memory_stamp
    with _lock:
        mine = current()
        fresh = Memory(mine.path, _read(mine.path)) if mine.path is not None and mine.path.exists() else mine
        result = edit(fresh)
        if result:
            fresh.save()
        _memory, _memory_stamp = fresh, _stamp(fresh.path)
        return result


# ------------------------------------------------------------------ the names held back this session
def hold(name: str) -> None:
    """*name* names no book until the reader says what the book is called (`release`)."""
    with _lock:
        _held.add(plain(name))


def release(name: str) -> None:
    with _lock:
        _held.discard(plain(name))


def held(name: str) -> bool:
    """Whether *name* is held back (`hold`)."""
    with _lock:
        return bool(_held) and plain(name) in _held


# ------------------------------------------------------------------ names
def strip_parts(text: str, memory: Memory | None = None) -> tuple[str, list[str]]:
    """*text* without the viewer's parts at its start and its end (and a page number left at its end, "- page 12"),
    and the parts taken off, in the order they were found."""
    memory = memory if memory is not None else current()
    taken: list[str] = []
    t = text.strip()
    while t:
        found = spans(t)
        if not found:
            break
        a, b = found[0]
        if memory.is_part(t[a:b]):
            taken.append(t[a:b])
            t = t[found[1][0]:].strip() if len(found) > 1 else ""
            continue
        a, b = found[-1]
        if memory.is_part(t[a:b]):
            taken.append(t[a:b])
            t = t[:found[-2][1]].strip() if len(found) > 1 else ""
            continue
        shorter = TRAILING_PAGE.sub("", t).strip()
        if shorter == t or not shorter:
            break
        t = shorter
    return t, taken


def unpaged(title: str) -> list[str]:
    """The segments of a window's *title* (`tab_of`, `plain`) without the ones that number a page ("page 12", "p.
    12", "12/200"; a bare number may be a volume's): two titles alike but for them show one book, whatever was
    learned of the viewer ("<book> - page 12 | <site>", then "- page 13 |")."""
    return [plain(s) for s in segments(tab_of(title)) if not PAGE_ONLY.fullmatch(plain(s))]


def book_key_from_title(title: str, memory: Memory | None = None) -> str:
    """The book's name a viewer's window *title* gives: what a browser adds goes first (`tab_of`), then the viewer's
    parts at either end and a page number at the end (`strip_parts`). A title of nothing but the viewer's parts gives
    itself, which names no book (`generic`); an empty one "untitled"."""
    t = tab_of(title)
    book, _taken = strip_parts(t, memory)
    return book or t or "untitled"


def generic(name: str, memory: Memory | None = None) -> bool:
    """Whether *name* names no book: one of `PLACEHOLDERS`, a program's name ("<name> for PC": `PROGRAM`), or nothing
    but viewers' parts, `PLACEHOLDERS` and page numbers with a viewer's part among them (letter case, spaces and
    zero-width characters aside)."""
    p = plain(name)
    if p in PLACEHOLDERS or PROGRAM.fullmatch(p):
        return True
    memory = memory if memory is not None else current()
    found = segments(" ".join(str(name or "").split()))
    return bool(found) and all(memory.is_part(s) or plain(s) in PLACEHOLDERS or is_page_number(s)
                               for s in found) and any(memory.is_part(s) for s in found)


def trailing_parts(a: str, b: str) -> list[str]:
    """The segments at the end of the tab titles *a* and *b* that are alike in both while what comes before them is
    there in both and differs in more than its digits (another book, not another page): the viewer's, as *a* spells
    them. [] for anything else (the same title, nothing before the shared end, only a page number changed)."""
    sa, sb = segments(a), segments(b)
    pa, pb = [plain(s) for s in sa], [plain(s) for s in sb]
    k = 0
    while k < min(len(pa), len(pb)) and pa[-1 - k] == pb[-1 - k]:
        k += 1
    if not k:
        return []
    rest_a, rest_b = pa[:len(pa) - k], pb[:len(pb) - k]
    if not rest_a or not rest_b:
        return []
    if re.sub(r"\d+", "", " ".join(rest_a)) == re.sub(r"\d+", "", " ".join(rest_b)):
        return []
    return [s for s in sa[len(sa) - k:] if learnable(s)]


def remembered(window: Any, memory: Memory | None = None) -> bool:
    """Whether *window* (`capture.WindowInfo`, or a tab title) is the viewer by what was learned: a segment at the
    start or the end of its tab title is a viewer's part, a window so titled was chosen before, or (a window that is
    no browser's) its program was."""
    memory = memory if memory is not None else current()
    title = getattr(window, "tab_title", window if isinstance(window, str) else "")
    title = " ".join(str(title or "").split())
    if not title:
        return False
    found = segments(title)
    if found and (memory.is_part(found[0]) or memory.is_part(found[-1])):
        return True
    if memory.chose(title):
        return True
    return memory.runs(str(getattr(window, "program", "") or ""))


def shares_an_end(title: str, memory: Memory | None = None) -> bool:
    """Whether the tab title *title* ends as a window chosen before did, another book before it (`trailing_parts`):
    likely another book in the same viewer."""
    memory = memory if memory is not None else current()
    return any(trailing_parts(title, seen) for seen in reversed(memory.titles))


def kept_names(store: Any, name: str) -> bool:
    """Whether the cache folder of *store* (`cache.CacheStore`) keeps files of the book *name* (in any language)."""
    if store is None or not name:
        return False
    try:
        return bool(store.files_of(name))
    except OSError:
        return False


def book_for_title(title: str, store: Any = None, memory: Memory | None = None) -> str:
    """The book a viewer's window *title* is read as (`book_key_from_title`), found again where what TASlation keeps
    says so (*store*, a `cache.CacheStore`): a book kept under the fuller name the title gave before a viewer's part
    of it was learned; a book kept when this version first ran under the title's name with one segment fewer (the
    lists an earlier version had cut the viewer's name off; that segment is learned as the viewer's)."""
    memory = memory if memory is not None else current()
    book = book_key_from_title(title, memory)
    if store is None or generic(book, memory) or kept_names(store, book):
        return book
    tab = tab_of(title)
    if tab != book and kept_names(store, tab):
        return tab
    found = spans(tab)
    if len(found) < 2 or not memory.old_books:
        return book
    for drop, rest in ((found[-1], tab[:found[-2][1]]), (found[0], tab[found[1][0]:])):
        segment = tab[drop[0]:drop[1]]
        old = memory.old_book(rest.strip())
        if old and learnable(segment) and not memory.is_book(segment) and kept_names(store, old):
            change(lambda m: m.learn([segment]))
            return old
    return book


def unconfirmed(title: str, name: str, memory: Memory | None = None) -> bool:
    """Whether *name*, the book's name the window *title* gave, may be the viewer's own: the title is one segment, in
    a viewer whose one-segment titles named no book before (`Memory.is_nameless`), and the reader has not said it is
    a book's. Such a name is held back (`hold`) and asked about once."""
    from .cache import viewer_key_from_title

    memory = memory if memory is not None else current()
    tab = tab_of(title)
    if plain(name) != plain(tab) or len(spans(tab)) != 1 or generic(name, memory) or memory.is_book(name):
        return False
    return memory.is_nameless(viewer_key_from_title(title))


# ------------------------------------------------------------------ learning
def chosen(window: Any) -> list[str]:
    """*window* (`capture.WindowInfo`) was chosen as the viewer: its tab title set beside the ones chosen before
    (`trailing_parts`: what they end alike with is the viewer's), and the window remembered (`Memory.remember`).
    Returns the parts learned."""
    title = " ".join(str(getattr(window, "tab_title", "") or "").split())
    program = str(getattr(window, "program", "") or "")
    if not title:
        return []

    learned: list[str] = []

    def edit(memory: Memory) -> bool:
        found: list[str] = []
        for seen in reversed(memory.titles):
            found += trailing_parts(title, seen)
        learned[:] = memory.learn(found)
        return memory.remember(title, program) or bool(learned)

    change(edit)
    return learned


def corrected(window: Any, learned: Sequence[str] = ()) -> None:
    """The reader chose another window while *window*, chosen last, had given no page: it is not remembered, and
    *learned*, what choosing it taught (`chosen`), is no viewer's part any more."""
    title = " ".join(str(getattr(window, "tab_title", "") or "").split())

    def edit(memory: Memory) -> bool:
        return memory.forget(title, str(getattr(window, "program", "") or "")) | memory.unlearn(learned)

    change(edit)


def retitled(before: str, after: str) -> list[str]:
    """The window of a viewer that is no browser's went from the title *before* to *after*: what they end alike
    with, another book before it, is the viewer's (`trailing_parts`). Returns the parts learned."""
    found = trailing_parts(" ".join(str(after or "").split()), " ".join(str(before or "").split()))
    if not found:
        return []
    return change(lambda memory: memory.learn(found)) or []


def _related(a: str, b: str) -> bool:
    pa, pb = plain(a), plain(b)
    return bool(pa) and bool(pb) and (pa in pb or pb in pa)


def named(title: str, name: str) -> tuple[list[str], list[str]]:
    """The reader called the book *name* while the window *title* gave the Book box its name: what that says of the
    title (see the module). A name held back for the title's (`unconfirmed`) is released: the reader's answer stands.
    Returns (the parts learned, the segments the reader said are the book's)."""
    from .cache import viewer_key_from_title

    tab, name = tab_of(title), " ".join(str(name or "").split())
    before = book_key_from_title(title)
    was_held = held(before)
    release(before)
    if not tab or not name:
        return [], []
    found = spans(tab)
    texts = [tab[a:b] for a, b in found]
    if plain(name) == plain(before):
        if was_held:
            return [], change(lambda memory: memory.refuse([before])) or []
        return [], []
    for size in range(len(texts) - 1, 0, -1):  # the name is a run of the title's segments: the rest is the viewer's
        for start in range(0, len(texts) - size + 1):
            run = tab[found[start][0]:found[start + size - 1][1]]
            dropped = texts[:start] + texts[start + size:]
            if _related(name, run) and not any(_related(name, d) for d in dropped):
                return change(lambda memory: memory.learn(dropped)) or [], []
    cut = strip_parts(tab)[1]
    if plain(before) != plain(tab) and cut and _related(before, name):  # what was cut off put back: the book's
        taken = [t for t in cut if plain(t) in plain(name)]
        return [], (change(lambda memory: memory.refuse(taken)) or []) if taken else []
    if len(texts) == 1 and not _related(name, tab):  # nothing of a one-segment title: it names no book here
        key = viewer_key_from_title(title)
        learned: list[str] = []

        def edit(memory: Memory) -> bool:
            learned[:] = memory.learn([tab])
            return memory.name_nameless(key) or bool(learned)

        change(edit)
        return learned, []
    return [], []


# ------------------------------------------------------------------ an earlier version's state folder
def _viewer_keys(state_dir: Path) -> tuple[list[str], list[str]]:
    """The viewers an earlier version kept something under: the capture profiles' names (profiles.json) and the
    viewers of the names last given (ui.json's "last_book")."""
    profiles = _read(state_dir / "profiles.json")
    ui = _read(state_dir / "ui.json")
    last = ui.get("last_book")
    reserved = {"default_keys", "key_presets"}
    profile_keys = [k for k, v in profiles.items() if isinstance(k, str) and k not in reserved and isinstance(v, dict)]
    last_keys = [k for k in last if isinstance(k, str)] if isinstance(last, dict) else []
    return profile_keys, last_keys


def migrate(state_dir: Path | str) -> None:
    """Once per state folder, what an earlier version left in it: a viewer it kept a profile or a last name under is
    the window's title without the book's name, so the segments of such a name before a browser's are what its lists
    cut off a title as a viewer's (learned); a viewer whose last name was kept had titles that named no book
    (`Memory.is_nameless`); and the books kept now are the ones whose names those lists made (`book_for_title`)."""
    state_dir = Path(state_dir)
    profile_keys, last_keys = _viewer_keys(state_dir)
    found: list[str] = []
    for key in (*profile_keys, *last_keys):
        key = re.sub(r"\s+[-–—|](?:\s+[-–—|])+\s+", " - ", key)  # a name cut out of the middle: two separators
        tab = tab_of(key)
        if tab and plain(tab) != plain(key):  # a browser named after it: what is before it was cut off a book's name
            found += [s for s in segments(tab) if learnable(s)]
    books: list[str] = []
    cache_dir = state_dir / "cache"
    if cache_dir.is_dir():
        try:
            from .cache import CacheStore

            books = list(dict.fromkeys(entry.book for entry in CacheStore(cache_dir).identities()))
        except Exception:  # noqa: BLE001 - nothing to find again
            books = []

    def edit(memory: Memory) -> bool:
        memory.learn(found)
        for key in last_keys:
            memory.name_nameless(key)
        memory.old_books = _strings([*memory.old_books, *books], OLD_BOOKS_KEPT)
        memory.migrated = True
        memory._index()
        return True

    change(edit)


__all__ = [
    "MAX_PART", "Memory", "PAGE_ONLY", "PAGE_SEGMENT", "PLACEHOLDERS", "PROGRAM", "SEGMENT", "SHARED_PROGRAMS", "STATE_FILE",
    "VERSION", "book_for_title", "book_key_from_title", "change", "chosen", "corrected", "current", "generic", "held", "hold",
    "is_page_number", "kept_names", "learnable", "memory_path", "migrate", "named", "plain", "release", "remembered",
    "retitled", "segments", "shares_an_end", "spans", "strip_parts", "tab_of", "trailing_parts", "unconfirmed", "unpaged",
    "use",
]
