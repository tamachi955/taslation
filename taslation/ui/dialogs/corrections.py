"""Translator mode's "My corrections": the translations a person wrote in the book of the Book field
(`cache.BookCache.corrections`: those marked `CachedBubble.edited` - the region editor's Save, Find and replace), page
by page, built from the cache alone: no page image, no Japanese. Selecting a row says in a line which page it is on;
nothing goes to the viewer, no key is pressed (turning to the page is the person's)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from ...i18n import _
from ..layout import place_window
from .help import explain_button

TITLE = "My corrections"
EMPTY = "You have corrected no translation in this book yet. A translation you change in the region editor or with Find and replace is listed here."
NO_BOOK = "Give the book a name first (the Book field)."  # (the window's own line: `locales.keys`)
ON_PAGE = "On page {page}. Turn to it in your viewer: nothing is sent to it from here."
PLACE_UNKNOWN = "This page's place in the book is not known."
COUNTED = "{n} translation(s) you corrected."
EXPLAIN = ("The translations you wrote yourself: \"Translate again\" and a whole-book run that translates again keep "
           "them unless you ask for them to be replaced. Select one to see which page it is on.")


def one_line(text: str) -> str:
    """A translation on one line of the list (its line breaks as spaces)."""
    return " ".join(str(text or "").split())


class CorrectionsDialog(tk.Toplevel):
    """The list: Page and Translation, a line under it (which page the selected row is on, else how many there are),
    Close. *rows_of*() gives the rows (`BookCache.corrections`), or None while the Book field names no book; the
    window makes the list again (`fill`) when it is asked for again, once the book's cache is open and after each
    change of the translations."""

    def __init__(self, master: tk.Misc, rows_of: Callable[[], Sequence[Any] | None]):
        super().__init__(master)
        self.title(_(TITLE))
        self.transient(master)
        self.geometry("700x380")
        self.rows_of = rows_of
        self.rows: list[Any] = []
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        self.body = ttk.Frame(frm)  # the list, or the line that says there is nothing in it
        self.body.pack(fill="both", expand=True, pady=(0, 6))
        self.tree = ttk.Treeview(self.body, columns=("text",), show="tree headings", height=12, selectmode="browse")
        self.tree.heading("#0", text=_("Page"))
        self.tree.heading("text", text=_("Translation"))
        self.tree.column("#0", width=70, stretch=False)
        self.tree.column("text", width=590)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._said())
        self.empty = ttk.Label(self.body, text="", anchor="center", justify="center", wraplength=600)
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        explain_button(btns, _(EXPLAIN)).pack(side="left")
        self.line_var = tk.StringVar(self, value="")
        ttk.Label(btns, textvariable=self.line_var).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.fill()
        place_window(self, master)

    def fill(self) -> None:
        """The rows as the cache holds them now, the row selected before selected again while it is still there."""
        try:
            rows = self.rows_of()
        except Exception:  # noqa: BLE001 - the cache read meanwhile: the list as it was
            return
        chosen = self._chosen()
        key = (chosen.fingerprint, chosen.bubble) if chosen is not None else None
        self.rows = list(rows or [])
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), text=str(row.page) if row.page else "?",
                             values=(one_line(row.text),))
        again = next((i for i, row in enumerate(self.rows) if (row.fingerprint, row.bubble) == key), None)
        if again is not None:
            self.tree.selection_set(str(again))
            self.tree.see(str(again))
        self.empty.configure(text=_(NO_BOOK) if rows is None else _(EMPTY))
        shown, hidden = (self.tree, self.empty) if self.rows else (self.empty, self.tree)
        hidden.pack_forget()
        if not shown.winfo_manager():
            shown.pack(fill="both", expand=True)
        self._said()

    def _chosen(self) -> Any:
        sel = self.tree.selection()
        if not sel:
            return None
        at = int(sel[0])
        return self.rows[at] if 0 <= at < len(self.rows) else None

    def _said(self) -> None:
        """The line under the list: the selected row's page, else how many rows there are."""
        row = self._chosen()
        if row is not None:
            self.line_var.set(_(ON_PAGE).format(page=row.page) if row.page else _(PLACE_UNKNOWN))
        else:
            self.line_var.set(_(COUNTED).format(n=len(self.rows)) if self.rows else "")


__all__ = ["CorrectionsDialog", "one_line"]
