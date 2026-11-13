"""Which book is on screen when the viewer's window title does not say.

A browser-based viewer's tab can be titled with the viewer's name whatever book it shows, and a browser's window
title can name nothing but the browser. `generic_book_name` is the one rule for the names that name no book: such a
name never becomes the name of a cache, a series sheet or the reader's annotations. Which names are a viewer's is
learned on the reader's computer (`viewerparts`); TASlation lists none.

Once the reader has given a book its name, the book is recognised by its pages the next time it is open under a
generic title (`recognise`): the page on screen is fingerprinted as the pipeline fingerprints a capture, and the
caches of every book are looked through for a page within the distance at which a cached page replaces another
(`cache.INDEXED_WITHIN`: 6 of the 320 bits, far closer than the pages of two different books come; the cache's own
lookup allows 36, for the same page at another window size). Only the book, the language, the header and the
fingerprints of each cache are read, never its pages (`CacheStore.identities`). What a book's colophon says of it
(`colophon.py`) is kept in its cache's header, and a book whose header has the ISBN on screen beats any fingerprint.

A page's fingerprint depends on the capture area it was read in: on a light reader frame the whole capture, an area
that cuts the browser's bars and the page panel inside it give fingerprints of 120 to 160 bits apart (on a dark
frame the paper is found alike in all three). So a frame is fingerprinted in every area the page may have been
translated in (`frame_areas`): the areas the caller gives (the capture area the window reads now, the reader's own),
the whole capture, and the page panel found in it (`detect.page_area.find_page_area`); the fingerprints of one page
on screen in all of them are one page to look for (`page_groups`). So is the page's unit as analyze found it before
2026-10-31 (``fingerprint.analyze(grow=False)``): since then the paper on a dark viewer grows through a page's black
panels, and the caches kept before hold such a page under another fingerprint (19 of the October volume's 198
pages more than 6 bits away, most of them 70 to 165).

After the viewer's window was resized, a page re-fitted into it lands a median 1 bit from its cached self, but its
unit can move by some pixels (the edges cut to the ink, the gutter of a spread) and the page with it farther than 6
bits (8 at the 95th percentile, 45 at the 99th); so a page within `AGREE_WITHIN` bits counts too when `AGREE_PAGES`
pages on screen match so, each another page of the same book - two different pages of a book stay over 20 bits
apart. The measurements are in
docs/OFFLINE_VERIFICATION.md ("Recognising a book after the window was resized").

When nothing is recognised, the name the reader last gave a book read in the same viewer under a title that named
none (`last_name`, kept in ui.json by `remember_name`) is the next best guess.

`isbn_key` and `clean_identity` are the ISBN and a book's identity as the caches compare and keep them.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Iterable, NamedTuple

import cv2
import numpy as np

from . import fingerprint as fp
from . import viewerparts
from .cache import DETAIL_FIELDS, INDEXED_WITHIN, CacheStore, clean_detail, language_key, viewer_key_from_title

# what a viewer's window title leaves for a book's name when it names no book on any computer: nothing, a new tab, a
# browser; the viewers' own names are learned on the reader's computer (`viewerparts`), never listed
GENERIC_NAMES = viewerparts.PLACEHOLDERS
IDENTITY_FIELDS = DETAIL_FIELDS  # a book's identity: the title, the volume, the author, the publisher, the ISBN
# what stands between the groups of an ISBN's digits, as printed or as the OCR reads it (in vertical text a hyphen
# is a vertical stroke, read as the long vowel mark or a bar; upright in a column, as the kanji one)
ISBN_DASHES = "-‐‑‒–—―−ーｰ一|｜丨.・･·"
_DASHES_RE = re.compile("[" + re.escape(ISBN_DASHES) + r"\s]")
_ISBN_PREFIX_RE = re.compile(r"^\s*ISBN(?:-1[03])?\s*[:：]?\s*", re.IGNORECASE)
Margins = tuple[int, int, int, int]  # left, top, right, bottom pixels of a capture left out: a capture area
WHOLE: Margins = (0, 0, 0, 0)  # the whole capture
LAST_NAMES = "last_book"  # ui.json: viewer (`cache.viewer_key_from_title`) -> the name last given to a book read in it
LAST_NAMES_KEPT = 32  # viewers whose last name is kept (the latest)
# recognising a book after its viewer's window was resized (`recognise`): a page within AGREE_WITHIN bits of a
# cached page counts when AGREE_PAGES pages on screen match so, each another page of the book (measured on the
# October volume re-fitted into viewports of 0.8 to 1.25 times the size: docs/OFFLINE_VERIFICATION.md)
AGREE_WITHIN = 16
AGREE_PAGES = 2


def generic_book_name(name: str) -> bool:
    """Whether *name* (the Book box, as a window's title gives it, or as typed) names no book: nothing, a new tab, a
    browser's name (`GENERIC_NAMES`), a viewer's name as learned on this computer (`viewerparts.generic`), or a
    title's name held back until the reader says what the book is called (`viewerparts.held`) - letter case, spaces
    and zero-width characters aside."""
    return viewerparts.generic(name) or viewerparts.held(name)


def same_book_name(a: str, b: str) -> bool:
    """Whether the names *a* and *b* name the book alike: the same once NFKC-normalised (full-width letters and
    digits), letter case and spaces aside ("見本の物語 3" and "見本の物語３")."""
    def key(name: str) -> str:
        return "".join(unicodedata.normalize("NFKC", str(name or "")).casefold().split())

    return key(a) == key(b)


# ------------------------------------------------------------------ the name last given in a viewer
def last_name(state_dir: Path | str, title: str) -> str:
    """The name the reader last gave a book read in the viewer whose window is titled *title*, under a title that
    named none (`remember_name`); the viewer is what the capture areas are kept by (`cache.viewer_key_from_title`:
    "<viewer> - Google Chrome" is Google Chrome's window). "" when there is none."""
    from .i18n import load_ui_table

    kept = load_ui_table(Path(state_dir), LAST_NAMES).get(viewer_key_from_title(str(title or "")), "")
    name = " ".join(kept.split())
    return "" if generic_book_name(name) else name


def remember_name(state_dir: Path | str, title: str, name: str) -> None:
    """*name*, given (typed or confirmed) to the book on screen in the viewer titled *title* while its title named
    none, kept in ui.json as that viewer's last name (`last_name`; the latest `LAST_NAMES_KEPT` viewers). A name that
    names no book is not kept. Book names only: nothing of a book's pages."""
    from .i18n import save_ui_entry

    name = " ".join(str(name or "").split())
    if generic_book_name(name):
        return
    save_ui_entry(Path(state_dir), LAST_NAMES, viewer_key_from_title(str(title or "")), name, keep=LAST_NAMES_KEPT)


# ------------------------------------------------------------------ ISBN
def _isbn10_ok(digits: str) -> bool:
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
    return total % 11 == 0


def _isbn13_check(first12: str) -> int:
    return (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12)) % 10) % 10


def isbn_key(text: Any) -> str:
    """The ISBN in *text* (``ISBN978-4-...``, the hyphens as printed or read, full-width digits) as its 13 digits (an
    ISBN-10 in its ISBN-13 form): what tells one book from another however the ISBN is written. "" when *text* is no
    valid ISBN, its check digit included."""
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    s = _DASHES_RE.sub("", _ISBN_PREFIX_RE.sub("", s)).upper()
    if re.fullmatch(r"\d{9}[\dX]", s) and _isbn10_ok(s):
        first12 = "978" + s[:9]
        return first12 + str(_isbn13_check(first12))
    if re.fullmatch(r"97[89]\d{10}", s) and _isbn13_check(s[:12]) == int(s[12]):
        return s
    return ""


def clean_identity(value: Any) -> dict[str, str]:
    """A book's identity (the details in a cache's header) as kept: only
    `IDENTITY_FIELDS`, each one line of text without controls or links within its bound (`cache.clean_detail`), the
    ISBN only when it is a valid one; {} for anything but an object."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for name in IDENTITY_FIELDS:
        text = clean_detail(name, value.get(name))
        if text and (name != "isbn" or isbn_key(text)):
            out[name] = text
    return out


# ------------------------------------------------------------------ recognising a book by a page
class Recognised(NamedTuple):
    """A book a page on screen belongs to, by the pages of its caches (`recognise`)."""

    book: str
    distance: int  # bits between a page on screen and the nearest of the book's pages (0 when only its ISBN matched)
    pages: int  # how many of the pages on screen match one of the book's pages


Probe = tuple[str, float]  # a page on screen: its fingerprint and its aspect ratio (0: not known)


def _is_margins(value: Any) -> bool:
    return isinstance(value, (tuple, list)) and len(value) == 4 and all(
        isinstance(v, (int, np.integer)) and not isinstance(v, bool) for v in value)


def _areas(margins: Margins | Sequence[Margins] | None) -> list[Margins]:
    """*margins* - one capture area (left, top, right, bottom) or several - as a list, each area once."""
    given = [margins] if _is_margins(margins) else list(margins or ())
    out: list[Margins] = []
    for m in given:
        if _is_margins(m):
            area = tuple(max(0, int(v)) for v in m)
            if area not in out:
                out.append(area)  # type: ignore[arg-type]
    return out


def _panel_area(image: np.ndarray) -> Margins | None:
    """The capture area of the page panel found in the capture *image* (an RGB or grey array:
    `detect.page_area.find_page_area`, as the window finds it while the reader has set no area); None when none is
    found."""
    try:
        from .detect.page_area import find_page_area, page_area_margins

        box = find_page_area(image)
    except Exception:  # noqa: BLE001 - a frame the finder cannot take: the other areas
        return None
    if box is None:
        return None
    h, w = image.shape[:2]
    return page_area_margins(box, (w, h))


def frame_areas(image: np.ndarray, margins: Margins | Sequence[Margins] = WHOLE, panel: bool = True) -> list[Margins]:
    """The capture areas a page of the capture *image* (an RGB or grey array) may have been fingerprinted in when it
    was translated: *margins* (one area or several: the capture area the window reads now, the reader's own), the
    whole capture, and with *panel* the page panel found in the capture (`_panel_area`); each once."""
    tried = _areas(margins)
    if WHOLE not in tried:
        tried.append(WHOLE)
    if panel:
        found = _panel_area(image)
        if found is not None and found not in tried:
            tried.append(found)
    return tried


def page_groups(source: Any, margins: Margins | Sequence[Margins] = WHOLE, panel: bool = True) -> list[list[Probe]]:
    """The pages to look for in *source*, each as the fingerprints it may have been kept under. A capture (a PIL image
    or an RGB array) gives its page units as the pipeline fingerprints them (`fingerprint.analyze`) in every area of
    `frame_areas`; the units of one place in the frame (the right or the left page of a spread) are one page.
    Fingerprints as they are (strings, `PageUnit`s, (fingerprint, aspect) pairs) are one page each; *source* may be a
    list of any of these (the current frame and one from before). Each fingerprint once, in the first page that has
    it."""
    groups: list[list[tuple[str, float]]] = []

    def take(item: Any) -> None:
        if item is None:
            return
        if hasattr(item, "convert") and hasattr(item, "size"):  # a PIL image
            item = np.asarray(item.convert("RGB"))
        if isinstance(item, np.ndarray):
            # grey once, as `fingerprint.analyze` makes it of an RGB capture: the same fingerprints in every area
            gray = cv2.cvtColor(np.ascontiguousarray(item[..., :3]), cv2.COLOR_RGB2GRAY) if item.ndim == 3 else item
            places: dict[int, list[tuple[str, float]]] = {}
            known: dict[tuple[int, int, int, int], str] = {}  # one box's fingerprint, in every area, computed once
            for area in frame_areas(gray, margins, panel):
                for grow in (True, False):  # the unit as analyze finds it, and as it found it before 2026-10-31
                    for unit in fp.analyze(gray, area, grow=grow, known=known):
                        places.setdefault(int(unit.index), []).append((unit.fingerprint, unit.aspect))
            groups.extend(places[k] for k in sorted(places))
        elif isinstance(item, str):
            groups.append([(item, 0.0)])
        elif hasattr(item, "fingerprint"):
            groups.append([(str(item.fingerprint), float(getattr(item, "aspect", 0.0) or 0.0))])
        elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) and \
                isinstance(item[1], (int, float)) and not isinstance(item[1], bool):
            groups.append([(item[0], float(item[1] or 0.0))])
        elif isinstance(item, Iterable):
            for part in item:
                take(part)

    take(source)
    seen: set[str] = set()
    out: list[list[Probe]] = []
    for group in groups:
        kept: list[Probe] = []
        for fingerprint, aspect in group:
            key = fingerprint.strip().lower()
            if len(key) == fp.FINGERPRINT_HEX_LEN and all(c in "0123456789abcdef" for c in key) and key not in seen:
                seen.add(key)
                kept.append((key, aspect))
        if kept:
            out.append(kept)
    return out


def page_probes(source: Any, margins: Margins | Sequence[Margins] = WHOLE, panel: bool = True) -> list[Probe]:
    """Every fingerprint to look for in *source* (`page_groups`, one list), each once."""
    return [probe for group in page_groups(source, margins, panel) for probe in group]


def _aspect_differs(a: float, b: float, tolerance: float) -> bool:
    return bool(a and b and abs(a - b) / max(a, b) > tolerance)


def identity_of(store: CacheStore, book: str, language: str | None = None) -> dict[str, str]:
    """What the colophon said of *book*, as its cache's header keeps it (`cache.DETAIL_FIELDS`): from its cache in
    *language* when that has it, else from one in another language; {} when none has."""
    best: dict[str, str] = {}
    for entry in store.identities():
        if entry.book != book or not entry.details:
            continue
        if language is not None and language_key(entry.language) == language_key(language):
            return dict(entry.details)
        best = best or dict(entry.details)
    return best


def _agreeing(near: dict[int, dict[Any, int]], pages: int) -> dict[int, int]:
    """The pages on screen of *near* (page on screen -> {cached page: distance}) that agree on a book: when at
    least *pages* of them match as many different cached pages (each one its own: two frames of one page match the
    same cached page and count once), each with its closest distance; {} otherwise."""
    near = {i: cached for i, cached in near.items() if cached}
    if len(near) < max(2, pages):
        return {}
    owner: dict[Any, int] = {}  # cached page -> the page on screen matched with it

    def assign(i: int, seen: set[Any]) -> bool:  # an augmenting path (Kuhn): a cached page for page i
        for cached in near[i]:
            if cached not in seen:
                seen.add(cached)
                if cached not in owner or assign(owner[cached], seen):
                    owner[cached] = i
                    return True
        return False

    if sum(assign(i, set()) for i in sorted(near)) < pages:
        return {}
    return {i: min(near[i].values()) for i in owner.values()}


def recognise(store: CacheStore, image_or_fingerprints: Any, language: str | None = None, *,
              margins: Margins | Sequence[Margins] = WHOLE, isbn: str = "", within: int = INDEXED_WITHIN,
              agree_within: int = AGREE_WITHIN, agree_pages: int = AGREE_PAGES, aspect_tolerance: float = 0.12,
              panel: bool = True) -> list[Recognised]:
    """The books whose caches hold a page on screen, best first. *image_or_fingerprints* is the capture (or
    captures: the current frame and one from before) or their fingerprints (`page_groups`: a capture is
    fingerprinted in the capture areas *margins*, in the whole capture and, with *panel*, in the page panel found in
    it, so that a page translated under another capture area is found as well; and as analyze found the page before
    2026-10-31, for the caches kept before then); a page matches a cached page within *within* bits whose aspect
    ratio is about the same (as `BookCache.lookup` matches one), in any of its areas. A page farther than that, but
    within *agree_within* bits, matches when *agree_pages* pages on screen do so, each another cached page of the
    book (`_agreeing`; the two pages of a spread after the viewer's window was resized: the page units then move by a
    few pixels and a page can land farther than 6 bits from its cached self, while two different pages of a book stay
    over 20 bits apart). The books are ranked by how many pages on screen they match, then by the closest distance,
    then the one with a cache in *language* (the target language read in; a book's caches in other languages count
    too: its name is the same in every language), then by name. A name that names no book (`generic_book_name`: the
    viewer's name of a cache kept before the name was asked for) is never one of them. With *isbn* (a colophon's),
    the books whose cache header has that ISBN are the answer whatever the fingerprints say: when there is one, only
    those are returned."""
    groups = page_groups(image_or_fingerprints, margins, panel)
    wanted = isbn_key(isbn)
    if not groups and not wanted:
        return []
    probe_values = [(i, int(key, 16), aspect) for i, group in enumerate(groups) for key, aspect in group]
    reach = max(within, agree_within if agree_pages >= 2 else within)
    found: dict[str, dict[str, Any]] = {}
    for n, entry in enumerate(store.identities()):
        if generic_book_name(entry.book):
            continue
        by_isbn = bool(wanted) and isbn_key(entry.details.get("isbn", "")) == wanted
        near: dict[int, dict[Any, int]] = {}  # page on screen -> {this cache's page: distance} within reach
        if probe_values:
            for k, (fingerprint, aspect) in enumerate(entry.pages):
                value = int(fingerprint, 16)
                for i, probe, probe_aspect in probe_values:
                    if _aspect_differs(probe_aspect, aspect, aspect_tolerance):
                        continue
                    distance = (value ^ probe).bit_count()
                    if distance <= reach:
                        pages = near.setdefault(i, {})
                        if distance < pages.get((n, k), reach + 1):
                            pages[(n, k)] = distance
        if not near and not by_isbn:
            continue
        book = found.setdefault(entry.book, {"near": {}, "isbn": False, "here": False})
        for i, pages in near.items():
            book["near"].setdefault(i, {}).update(pages)
        book["isbn"] = book["isbn"] or by_isbn
        if language is not None and language_key(entry.language) == language_key(language):
            book["here"] = True
    for book in found.values():
        close = {i: d for i, pages in book["near"].items() if (d := min(pages.values())) <= within}
        loose = _agreeing({i: {c: d for c, d in pages.items() if d <= agree_within}
                           for i, pages in book["near"].items()}, agree_pages) if agree_pages >= 2 else {}
        book["probes"] = {**loose, **close} if loose else close
    found = {name: book for name, book in found.items() if book["probes"] or book["isbn"]}
    if any(book["isbn"] for book in found.values()):
        found = {name: book for name, book in found.items() if book["isbn"]}
    ranked = sorted(found.items(), key=lambda item: (-len(item[1]["probes"]), min(item[1]["probes"].values(), default=0),
                                                     not item[1]["here"], item[0]))
    return [Recognised(name, min(book["probes"].values(), default=0), len(book["probes"])) for name, book in ranked]


__all__ = ["AGREE_PAGES", "AGREE_WITHIN", "GENERIC_NAMES", "IDENTITY_FIELDS", "ISBN_DASHES", "LAST_NAMES",
           "LAST_NAMES_KEPT", "Margins", "Probe", "Recognised", "WHOLE", "clean_identity", "frame_areas",
           "generic_book_name", "identity_of", "isbn_key", "last_name", "page_groups", "page_probes", "recognise",
           "remember_name", "same_book_name"]
