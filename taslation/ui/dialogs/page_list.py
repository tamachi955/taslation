"""A list of lines of the book of the Book field, page by page, built from its cache alone (`PageListDialog`): the
window's "My corrections" (`dialogs.corrections`) and "Lines to review" (`dialogs.review_list`) are two uses of it. No
page image, no Japanese: a row is a page's number (its sequence number from 1, as `taslation review` numbers pages; 0
for a page with none, shown as "?"), the line's translation and what the use adds. Selecting a row says in a line
which page it is on; nothing goes to the viewer, no key is pressed (turning to the page is the person's)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from ...i18n import _
from ..layout import place_window
from .help import explain_button

ON_PAGE = "On page {page}. Turn to it in your viewer: nothing is sent to it from here."
PLACE_UNKNOWN = "This page's place in the book is not known."
FAR = 10**9  # a page with no place in the book: after the others


def one_line(text: str) -> str:
    """A translation on one line of the list (its line breaks as spaces)."""
    return " ".join(str(text or "").split())


def row_key(row: Any) -> tuple[str, int]:
    """What tells a row from the others while the cache holds it: its page's fingerprint and the line's index."""
    return row.fingerprint, row.bubble


class PageListDialog(tk.Toplevel):
    """The list: Page, the columns of `COLUMNS` (the translation's is "text"), a line under it (which page the selected
    row is on, else how many there are: `_counted`), an explanation and Close. *rows_of*() gives the rows (each with
    ``page``, ``fingerprint``, ``bubble`` and ``text``), or None while the Book field names no book; the window makes
    the list again (`fill`) when it is asked for again, once the book's cache is open and after each change of the
    translations. A use names its strings (`TITLE`, `EMPTY`, `NO_BOOK`, `COUNTED`, `EXPLAIN`: English keys of the
    catalogs) and may add a row of its own over the list (`_build_above`), the values of its columns (`_values`) and
    which rows are listed, in which order (`_listed`)."""

    TITLE = ""
    EMPTY = ""
    NO_BOOK = "Give the book a name first (its series in the Series field, and its volume beside it if it has one)."  # (the window's own line: `locales.keys`)
    COUNTED = ""
    EXPLAIN = ""
    COLUMNS: tuple[tuple[str, str, int], ...] = (("text", "Translation", 590),)  # (id, heading key, width)
    SIZE = "700x380"

    def __init__(self, master: tk.Misc, rows_of: Callable[[], Sequence[Any] | None]):
        super().__init__(master)
        self.title(_(self.TITLE))
        self.transient(master)
        self.geometry(self.SIZE)
        self.rows_of = rows_of
        self.rows: list[Any] = []  # what the cache gives
        self.shown: list[Any] = []  # what the list shows of them (`_listed`), row by row
        self.given: Sequence[Any] | None = None  # what *rows_of* gave last (None: no book)
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        self._build_above(frm)
        self.body = ttk.Frame(frm)  # the list, or the line that says there is nothing in it
        self.body.pack(fill="both", expand=True, pady=(0, 6))
        self.tree = ttk.Treeview(self.body, columns=tuple(c for c, _h, _w in self.COLUMNS), show="tree headings",
                                 height=12, selectmode="browse")
        self.tree.heading("#0", text=_("Page"))
        self.tree.column("#0", width=70, stretch=False)
        for column, heading, width in self.COLUMNS:
            self.tree.heading(column, text=_(heading))
            self.tree.column(column, width=width)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._said())
        self.empty = ttk.Label(self.body, text="", anchor="center", justify="center", wraplength=600)
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        explain_button(btns, _(self.EXPLAIN)).pack(side="left")
        self.line_var = tk.StringVar(self, value="")
        ttk.Label(btns, textvariable=self.line_var).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.fill()
        place_window(self, master)

    # ---------------------------------------------------------------- what a use adds
    def _build_above(self, frame: ttk.Frame) -> None:
        """A row of the use's own over the list (none here)."""

    def _values(self, row: Any) -> tuple[str, ...]:
        """The row's values in the columns of `COLUMNS`."""
        return (one_line(row.text),)

    def _listed(self, rows: list[Any]) -> list[Any]:
        """The rows the list shows, in its order (all of them, as the cache gives them, here)."""
        return list(rows)

    def _filled(self) -> None:
        """The rows are listed anew (`rows`, `shown`): what the use shows besides follows them."""

    def _counted(self) -> str:
        """The line under the list while no row is selected."""
        return _(self.COUNTED).format(n=len(self.rows)) if self.rows else ""

    # ---------------------------------------------------------------- the list
    def fill(self) -> None:
        """The rows as the cache holds them now, the row selected before selected again while it is still there."""
        try:
            rows = self.rows_of()
        except Exception:  # noqa: BLE001 - the cache read meanwhile: the list as it was
            return
        self.given = rows
        self.rows = list(rows or [])
        self.relist()

    def relist(self) -> None:
        """The rows listed again as the use lists them now (`_listed`: another reason chosen, another order)."""
        chosen = self._chosen()
        key = row_key(chosen) if chosen is not None else None
        self.shown = self._listed(self.rows)
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.shown):
            self.tree.insert("", "end", iid=str(i), text=str(row.page) if row.page else "?", values=self._values(row))
        again = next((i for i, row in enumerate(self.shown) if row_key(row) == key), None)
        if again is not None:
            self.tree.selection_set(str(again))
            self.tree.see(str(again))
        self._filled()
        self.empty.configure(text=_(self.NO_BOOK) if self.given is None else _(self.EMPTY))
        shown, hidden = (self.tree, self.empty) if self.shown else (self.empty, self.tree)
        hidden.pack_forget()
        if not shown.winfo_manager():
            shown.pack(fill="both", expand=True)
        self._said()

    def _chosen(self) -> Any:
        sel = self.tree.selection()
        if not sel:
            return None
        at = int(sel[0])
        return self.shown[at] if 0 <= at < len(self.shown) else None

    def _said(self) -> None:
        """The line under the list: the selected row's page, else how many rows there are."""
        row = self._chosen()
        if row is not None:
            self.line_var.set(_(ON_PAGE).format(page=row.page) if row.page else _(PLACE_UNKNOWN))
        else:
            self.line_var.set(self._counted())


__all__ = ["FAR", "ON_PAGE", "PLACE_UNKNOWN", "PageListDialog", "one_line", "row_key"]
