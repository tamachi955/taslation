"""Translator mode's "Lines to review": every line of the book of the Book field that is worth a look, page by page,
built from its cache alone (no page image, no Japanese): the lines flagged as they were translated (`CachedBubble.flags`,
the codes of `review.REASONS`) and those with a note for the reader, each with its reasons in the words of "Review
this page" (`review.reason_label`, `dialogs.review.FIT_REASONS`). The checks of a lettering (`TextRegion.letter_flags`:
letters touching the bubble's edge, a word split with a hyphen, ...) are worked out as a page is lettered and never
kept: they are added for the page on show only (`with_lettering`). The list can show one reason only (Show:) and be
sorted by page or by reason (a click on a column's heading).

Selecting a row says in a line which page it is on; nothing goes to the viewer, no key is pressed: turning to the page
is the person's, and "Review this page" there opens the region's editor. The second use of the window's list of lines
by page (`page_list.PageListDialog`); "My corrections" is the first. The window makes the list again after a page's
result and after a change of the translations (`TranslatorMixin._refresh_corrections`)."""

from __future__ import annotations

import tkinter as tk
from collections import Counter
from tkinter import ttk
from typing import Any, Iterable, NamedTuple

from ...i18n import _
from ...regions import ERASED, box_iou
from ...review import reason_label
from ..tooltip import tip
from .page_list import FAR, PageListDialog, one_line
from .review import FIT_REASONS

TITLE = "Lines to review"
EMPTY = ("No line of this book is flagged for a look yet. A line flagged as it is translated, or with a note for the "
         "reader, is listed here.")
COUNTED = "{n} line(s) worth a look."
FILTERED = "{shown} of {n} line(s) worth a look."
SHOW = "Show:"
ALL_REASONS = "All reasons"
SHOW_TIP = "Only the lines with this reason. A click on a column's heading sorts the list by it."
EXPLAIN = ("The lines of this book flagged for a look as they were translated, and those with a note for the reader, "
           "page by page, from the saved translations alone; for the page on show, what the checks of its lettering "
           "found too. Select one to see which page it is on, then turn to it in your viewer: Review... there opens "
           "its editor.")
NOTE = "note"  # a line with a note for the reader (no flag of its own: the cache keeps the note)
NOTE_WORDS = "note for the reader"  # (as "Review this page" says it)


class LineToReview(NamedTuple):
    """A line worth a look: its page's number (its sequence number from 1, as `taslation review` and "My corrections"
    number pages; 0 for a page with none), the page's fingerprint, the line's index on it, its translation, its box
    and its reasons (codes: of `review.REASONS`, of `dialogs.review.FIT_REASONS`, or `NOTE`)."""

    page: int
    fingerprint: str
    bubble: int
    text: str
    box: tuple[float, float, float, float]
    codes: tuple[str, ...]


def reason_words(code: str) -> str:
    """A reason as "Review this page" says it, in the window's language; a code it does not know as it is."""
    if code == NOTE:
        return _(NOTE_WORDS)
    if code in FIT_REASONS:
        return _(FIT_REASONS[code])
    return reason_label(code)


def worth_a_look(bubble: Any) -> tuple[str, ...]:
    """The reasons a cached line is worth a look: its flags, then a note for the reader (`NOTE`); none for most."""
    codes = [str(f) for f in getattr(bubble, "flags", ()) or () if f]
    if str(getattr(bubble, "note", "") or "").strip():
        codes.append(NOTE)
    return tuple(dict.fromkeys(codes))


def _order(page: Any) -> tuple[int, str]:
    return (page.seq if page.seq >= 0 else FAR, page.fingerprint)


def book_lines(cache: Any) -> list[LineToReview]:
    """Every line of *cache* worth a look (`worth_a_look`), page by page in the order the pages were first seen (a page
    with no sequence number last), each page's in the order it holds them. A copy of the list of pages is read (the
    worker may add to it meanwhile)."""
    rows: list[LineToReview] = []
    for page in sorted(list(cache.pages), key=_order):
        for i, bubble in enumerate(list(page.bubbles)):
            codes = worth_a_look(bubble)
            if codes:
                rows.append(LineToReview(page.seq + 1 if page.seq >= 0 else 0, page.fingerprint, i, bubble.text,
                                         tuple(bubble.box), codes))  # type: ignore[arg-type]
    return rows


def lines_on_page(page: Any) -> int:
    """How many lines of the cached *page* are worth a look."""
    return sum(1 for bubble in list(page.bubbles) if worth_a_look(bubble))


def _cached_line(cache: Any, result: Any, region: Any, settings: Any) -> tuple[Any, int] | None:
    """The cached page and the index of the line that holds *region*'s translation, as `replace.reletter` finds it:
    the page of the region's page unit, its bubble most over the region (at least `match_min_iou`)."""
    if region.unit >= len(result.units):
        return None
    unit = result.units[region.unit]
    hit = cache.lookup(unit.fingerprint, unit.aspect, settings.fingerprint_max_distance, None)
    if hit is None:
        return None
    page = hit[0]
    nbox = unit.normalize(region.bbox)
    bubbles = list(page.bubbles)
    if not bubbles:
        return None
    best = max(range(len(bubbles)), key=lambda i: box_iou(bubbles[i].box, nbox))
    if box_iou(bubbles[best].box, nbox) < settings.match_min_iou:
        return None
    return page, best


def with_lettering(rows: Iterable[LineToReview], cache: Any, result: Any, settings: Any) -> list[LineToReview]:
    """*rows* (`book_lines` of *cache*) with what the checks of the lettering found on the page on show (*result*:
    its regions' `letter_flags`), each region's added to the reasons of the cached line that holds its translation (a
    line of its own when it had none); *result* None: *rows* as they are. A region dropped or made "erase only" is
    never one, as in "Review this page"."""
    rows = list(rows)
    if result is None or cache is None:
        return rows
    at = {(row.fingerprint, row.bubble): i for i, row in enumerate(rows)}
    added = False
    for region in getattr(result, "regions", ()):
        found = [f for f in getattr(region, "letter_flags", ()) or () if f in FIT_REASONS]
        if not found or region.status in ("dropped", ERASED):
            continue
        line = _cached_line(cache, result, region, settings)
        if line is None:
            continue
        page, index = line
        key = (page.fingerprint, index)
        if key in at:
            row = rows[at[key]]
            rows[at[key]] = row._replace(codes=tuple(dict.fromkeys(row.codes + tuple(found))))
        else:
            bubble = page.bubbles[index]
            at[key] = len(rows)
            added = True
            rows.append(LineToReview(page.seq + 1 if page.seq >= 0 else 0, page.fingerprint, index, bubble.text,
                                     tuple(bubble.box), tuple(dict.fromkeys(found))))  # type: ignore[arg-type]
    if added:  # (in the book's order, as `book_lines` gives it)
        rows.sort(key=lambda r: (r.page or FAR, r.fingerprint, r.bubble))
    return rows


class LinesToReviewDialog(PageListDialog):
    """The list: Page, Why (the reasons in words) and Translation; over it, Show: the reason the list is narrowed to
    (All reasons, then each reason the rows have, with how many); under it, which page the selected row is on, else how
    many there are. A click on the heading of Page or Why sorts by it. *rows_of*() gives the rows (`book_lines`,
    `with_lettering`), or None while the Book field names no book."""

    TITLE, EMPTY, COUNTED, EXPLAIN = TITLE, EMPTY, COUNTED, EXPLAIN
    COLUMNS = (("why", "Why", 250), ("text", "Translation", 430))
    SIZE = "780x400"
    reason = ""  # the reason (code) the list is narrowed to; "" for all
    order = "page"  # "page" or "why"

    def _build_above(self, frame: ttk.Frame) -> None:
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 6))
        label = ttk.Label(row, text=_(SHOW))
        label.pack(side="left")
        self.reason_var = tk.StringVar(self, value=_(ALL_REASONS))
        self.reason_box = ttk.Combobox(row, textvariable=self.reason_var, values=[_(ALL_REASONS)], state="readonly",
                                       width=44)
        self.reason_box.pack(side="left", padx=(4, 0))
        self.reason_box.bind("<<ComboboxSelected>>", lambda _e: self.choose_reason(self.reason_box.current()))
        tip(_(SHOW_TIP), label, self.reason_box)
        self.reason_codes: list[str] = []  # the reasons of the box's entries after All reasons

    def _values(self, row: Any) -> tuple[str, ...]:
        return "; ".join(reason_words(c) for c in row.codes), one_line(row.text)

    def _listed(self, rows: list[Any]) -> list[Any]:
        if self.reason and not any(self.reason in r.codes for r in rows):
            self.reason = ""  # its last line was looked at: every reason again
        out = [r for r in rows if not self.reason or self.reason in r.codes]
        if self.order == "why":
            out.sort(key=lambda r: (self._values(r)[0].casefold(), r.page or FAR))
        return out

    def _filled(self) -> None:
        """The box's entries: All reasons, then each reason the rows have, by its words, with how many lines."""
        counts = Counter(code for row in self.rows for code in row.codes)
        self.reason_codes = sorted(counts, key=lambda c: reason_words(c).casefold())
        words = [_(ALL_REASONS)] + [f"{reason_words(c)} ({counts[c]})" for c in self.reason_codes]
        self.reason_box.configure(values=words)
        self.reason_var.set(words[self.reason_codes.index(self.reason) + 1] if self.reason in self.reason_codes
                            else words[0])

    def _counted(self) -> str:
        if not self.rows:
            return ""
        if len(self.shown) != len(self.rows):
            return _(FILTERED).format(shown=len(self.shown), n=len(self.rows))
        return _(COUNTED).format(n=len(self.rows))

    def choose_reason(self, entry: int) -> None:
        """The box's entry *entry* chosen (0: All reasons): the list shows the lines with that reason only."""
        self.reason = self.reason_codes[entry - 1] if 0 < entry <= len(self.reason_codes) else ""
        self.relist()

    def sort_by(self, order: str) -> None:
        """The list in another order: "page" (as the book goes) or "why" (by the reasons' words, then the page)."""
        self.order = order if order in ("page", "why") else "page"
        self.relist()

    def relist(self) -> None:
        if not getattr(self, "_headings_bound", False):  # (made once the tree is there)
            self._headings_bound = True
            self.tree.heading("#0", command=lambda: self.sort_by("page"))
            self.tree.heading("why", command=lambda: self.sort_by("why"))
        super().relist()


__all__ = ["LineToReview", "LinesToReviewDialog", "book_lines", "lines_on_page", "reason_words", "with_lettering",
           "worth_a_look"]
