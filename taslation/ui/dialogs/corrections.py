"""Translator mode's "My corrections": the translations a person wrote in the book of the Book field
(`cache.BookCache.corrections`: those marked `CachedBubble.edited` - the region editor's Save, Find and replace), page
by page, built from the cache alone: no page image, no Japanese. Selecting a row says in a line which page it is on;
nothing goes to the viewer, no key is pressed (turning to the page is the person's). One use of the window's list of
lines by page (`page_list.PageListDialog`); "Lines to review" is the other (`review_list`)."""

from __future__ import annotations

from .page_list import ON_PAGE, PLACE_UNKNOWN, PageListDialog, one_line

TITLE = "My corrections"
EMPTY = "You have corrected no translation in this book yet. A translation you change in the region editor or with Find and replace is listed here."
NO_BOOK = "Give the book a name first (its series in the Series field, and its volume beside it if it has one)."  # (the window's own line: `locales.keys`)
COUNTED = "{n} translation(s) you corrected."
EXPLAIN = ("The translations you wrote yourself: \"Translate again\" and a whole-book run that translates again keep "
           "them unless you ask for them to be replaced. Select one to see which page it is on.")


class CorrectionsDialog(PageListDialog):
    """The list: Page and Translation, a line under it (which page the selected row is on, else how many there are),
    Close. *rows_of*() gives the rows (`BookCache.corrections`), or None while the Book field names no book; the
    window makes the list again (`fill`) when it is asked for again, once the book's cache is open and after each
    change of the translations."""

    TITLE, EMPTY, NO_BOOK, COUNTED, EXPLAIN = TITLE, EMPTY, NO_BOOK, COUNTED, EXPLAIN


__all__ = ["CorrectionsDialog", "ON_PAGE", "PLACE_UNKNOWN", "one_line"]
