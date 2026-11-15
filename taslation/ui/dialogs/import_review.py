"""What an import of an export file would do, shown before anything is written (`ImportReviewDialog`, opened by the
Saved translations dialog's Import when there is something to choose: `caches.CachesDialog`): the books the file
holds, each with its series, volume, language and pages, and whether it is new here or joins the cache here - all of
them chosen at first, the reader picks some or all -; a line of counts for the books chosen (pages added, pages
replaced, the reader's own corrections kept); where the reader corrected translations here that the file has
otherwise, "Keep my corrections" (the default) or "Take the file as it is"; where the page information here differs
from the file's, "Keep mine" (the default) or "Take the file's"; and where the series sheets here say otherwise than
the file's, a row each (`conflicts.ConflictRows`: the values as the sheets keep them, never a line of the book),
"Keep yours" at first. Import gives the reader's choice (`ImportChoice`), Cancel (Esc, closing it) none."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ...bookname import split_name
from ...i18n import _
from ..layout import fit_columns, place_window
from .conflicts import WIDTH, ConflictRows, conflict_texts

if TYPE_CHECKING:
    from ...backup import ImportPlan, Opened

LIST_ROWS = 8  # books on show before the list scrolls


@dataclass
class ImportChoice:
    """What the reader chose to import (`ImportReviewDialog`): the books (indices in the file), whether their
    corrections here stay, whether the file's page information takes the place of theirs, and per conflict of the
    sheets (`backup.SheetPlan.key`) True for "take the file's"."""

    books: list[int]
    keep_corrections: bool = True
    take_annotations: bool = False
    answers: dict[tuple[str, ...], bool] = field(default_factory=dict)


def counts_line(plan: "ImportPlan", keep_corrections: bool) -> str:
    """The counts of *plan* (the books chosen) as the review shows them."""
    return _("{pages} page(s) of {books} book(s): {added} new, {replaced} replacing yours, {kept} of your corrections kept.").format(
        pages=plan.pages, books=len(plan.books), added=plan.added, replaced=plan.replaced(keep_corrections),
        kept=plan.kept if keep_corrections else 0)


class ImportReviewDialog(tk.Toplevel):
    """The review of importing *opened* (`backup.Opened`) as *plan* (`backup.plan_import` for all its books) says
    (see the module), over *master* and modal. ``choice`` is the reader's `ImportChoice` once Import is pressed,
    None otherwise."""

    def __init__(self, master: tk.Misc, opened: "Opened", plan: "ImportPlan", file: str):
        super().__init__(master)
        self.opened, self.plan = opened, plan
        self.choice: ImportChoice | None = None
        self.title(_("Import from {file}").format(file=file))
        self.transient(master)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        self._frame = frm
        ttk.Label(frm, text=_("The file holds these books. Choose the ones to import:"), wraplength=WIDTH,
                  justify="left").pack(anchor="w", pady=(0, 4))
        self.tree = ttk.Treeview(frm, columns=("volume", "language", "pages", "here"), show="tree headings",
                                 height=min(LIST_ROWS, max(2, len(plan.books))))
        self.tree.pack(fill="both", expand=True)
        self._items: dict[str, int] = {}  # tree item -> the book's index in the file
        rows = []
        for book in plan.books:
            held = book.held
            parts = split_name(held.book)
            values = (parts.volume, held.language, held.pages, _("Joins yours") if book.exists else _("New here"))
            item = self.tree.insert("", "end", text=parts.series or held.book, values=values)
            self._items[item] = held.index
            rows.append((parts.series or held.book, *values))
        fit_columns(self.tree, (("#0", _("Series"), ["A book title of some length"], 300),
                                ("volume", _("Volume"), ["10.5"], 100), ("language", _("Language"), ["English"], 200),
                                ("pages", _("Pages"), ["9999"], 120), ("here", "", [_("Joins yours")], 200)), rows)
        self.tree.selection_set(tuple(self._items))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync(), add="+")
        self.tree.bind("<Control-a>", self._select_all, add="+")
        self.counts_var = tk.StringVar(self, value="")
        ttk.Label(frm, textvariable=self.counts_var, wraplength=WIDTH, justify="left").pack(anchor="w", pady=(6, 0))

        self.corrections_var = tk.StringVar(self, value="keep")
        self.corrections_box: ttk.Frame | None = None
        if plan.kept:
            self.corrections_box = self._pair(frm, _("You corrected translations here that the file has otherwise:"),
                                              self.corrections_var, ("keep", _("Keep my corrections")),
                                              ("take", _("Take the file as it is")))
        self.marks_var = tk.StringVar(self, value="keep")
        self.marks_box: ttk.Frame | None = None
        if plan.differing:
            self.marks_box = self._pair(frm, _("The page information you have here for {n} book(s) differs from the file's:").format(
                n=len(plan.differing)), self.marks_var, ("keep", _("Keep mine")), ("take", _("Take the file's")))
        keyed = plan.keyed()
        self.choices: list[tuple[tuple[str, ...], tk.StringVar]] = []
        self.rows: list[tuple[str, str, str]] = []
        if keyed:
            ttk.Label(frm, text=_("Your series sheets say otherwise than the file's here; choose for each one:"),
                      wraplength=WIDTH, justify="left").pack(anchor="w", pady=(10, 4))
            rows3 = []
            several = len({(s.series, s.language) for _k, s, _c in keyed}) > 1  # whose sheet a row is, then
            for key, sheet, c in keyed:
                what, mine, theirs = conflict_texts(c)
                rows3.append((f"{what} ({sheet.series}, {sheet.language})" if several else what, mine, theirs))
            listed = ConflictRows(self, frm, rows3, [False] * len(keyed), (_("What"), _("Yours here"), _("The file's")),
                                  (_("Keep yours"), _("Take the file's")))
            self.rows = listed.rows
            self.choices = [(key, var) for (key, _sheet, _c), var in zip(keyed, listed.choices)]
        for var in (self.corrections_var, self.marks_var):
            var.trace_add("write", lambda *_a: self._sync())
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        self.import_btn = ttk.Button(btns, text=_("Import"), command=self.apply, default="active")
        self.import_btn.pack(side="right")
        self.cancel_btn = ttk.Button(btns, text=_("Cancel"), command=self.cancel)
        self.cancel_btn.pack(side="right", padx=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self._sync()
        self.import_btn.focus_set()
        place_window(self, master)
        try:
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    @staticmethod
    def _pair(parent: tk.Misc, text: str, var: tk.StringVar, first: tuple[str, str], second: tuple[str, str]) -> ttk.Frame:
        box = ttk.Frame(parent)
        box.pack(fill="x", pady=(10, 0))
        ttk.Label(box, text=text, wraplength=WIDTH, justify="left").pack(anchor="w")
        for value, label in (first, second):
            ttk.Radiobutton(box, text=label, value=value, variable=var).pack(anchor="w", padx=(12, 0))
        return box

    def _select_all(self, _event: Any = None) -> str:
        self.tree.selection_set(tuple(self._items))
        return "break"

    def chosen_books(self) -> list[int]:
        """The books selected in the list (indices in the file), in the file's order."""
        return sorted(self._items[item] for item in self.tree.selection() if item in self._items)

    def _sync(self) -> None:
        books = self.chosen_books()
        self.counts_var.set(counts_line(self.plan.only(books), self.corrections_var.get() == "keep") if books else "")
        self.import_btn.configure(state="normal" if books else "disabled")

    def answers(self) -> dict[tuple[str, ...], bool]:
        """Each conflict's key to the row's choice: True where it says take the file's."""
        return {key: var.get() == "theirs" for key, var in self.choices}

    def apply(self) -> None:
        """Import: the reader's choice, the dialog closed."""
        books = self.chosen_books()
        if not books:
            return
        self.choice = ImportChoice(books, self.corrections_var.get() == "keep", self.marks_var.get() == "take",
                                   self.answers())
        self.destroy()

    def cancel(self) -> None:
        """Cancel: nothing is imported."""
        self.choice = None
        self.destroy()


__all__ = ["ImportChoice", "ImportReviewDialog", "counts_line"]
