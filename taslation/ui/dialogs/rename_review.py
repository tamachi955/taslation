"""The review of a rename whose book's series sheet joins the sheet the new series has already (`RenameReviewDialog`,
opened by the colophon's Use when the plan has conflicts: `rename.plan_rename`, `ui/jobs.py`): where the two sheets
say otherwise, a row each - what it is, the series' value, this book's, Keep the series' / Take this book's (All
series', All this book's) -. Rename renames
the book with the answers, Cancel (Esc, closing it) keeps its name. The rows are `conflicts.ConflictRows` (with
`conflicts.conflict_texts`): the values as the sheets keep them, never a line of the book; a row's language follows
what it is when the sheets of several languages join."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

from ...i18n import _
from ..layout import place_window
from .conflicts import WIDTH, ConflictRows, conflict_texts

if TYPE_CHECKING:
    from ...rename import RenamePlan


class RenameReviewDialog(tk.Toplevel):
    """The review of renaming *plan*'s book (`rename.RenamePlan`: the conflicts of its sheets with the new series'),
    over the window and modal. Rename calls *on_apply* with the answers - each conflict's key (`plan.keyed`) to True
    for "take this book's" -, Cancel (and Esc, and closing it) calls *on_cancel*; one answer only."""

    def __init__(self, master: tk.Misc, plan: "RenamePlan", on_apply: Callable[[dict[tuple[str, ...], bool]], None],
                 on_cancel: Callable[[], None] | None = None):
        super().__init__(master)
        self.plan, self.on_apply, self.on_cancel = plan, on_apply, on_cancel
        self.answered = False
        self.title(_("Renaming {book} to {name}").format(book=plan.old, name=plan.new))
        self.transient(master)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        keyed = plan.keyed()
        self.rows: list[tuple[str, str, str]] = []  # what each row shows
        self.choices: list[tuple[tuple[str, ...], tk.StringVar]] = []  # each conflict's key and choice
        if keyed:
            self.intro = ttk.Label(frm, text=_("The series sheet of {series} exists already; this book's sheet joins it. Where the two say otherwise, choose for each one:").format(
                series=plan.new_series), wraplength=WIDTH, justify="left")
            self.intro.pack(anchor="w", pady=(0, 4))
            rows = []
            for key, language, c in keyed:
                what, mine, theirs = conflict_texts(c)
                rows.append((f"{what} ({language})" if len(key) > 4 else what, mine, theirs))
            listed = ConflictRows(self, frm, rows, [c.take for _key, _language, c in keyed],
                                  (_("What"), _("Series sheet"), _("This book's sheet")),
                                  (_("Keep the series'"), _("Take this book's")))
            self.rows, self.list_canvas = listed.rows, listed.canvas
            self.choices = [(key, var) for (key, _language, _c), var in zip(keyed, listed.choices)]
            both = ttk.Frame(frm)
            both.pack(fill="x", pady=(6, 0))
            ttk.Button(both, text=_("All series'"), command=lambda: self.set_all(False)).pack(side="left")
            ttk.Button(both, text=_("All this book's"), command=lambda: self.set_all(True)).pack(side="left",
                                                                                                 padx=(6, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        self.apply_btn = ttk.Button(btns, text=_("Rename"), command=self.apply)
        self.apply_btn.pack(side="right")
        self.cancel_btn = ttk.Button(btns, text=_("Cancel"), command=self.cancel)
        self.cancel_btn.pack(side="right", padx=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self.bind("<Map>", self._on_map, add="+")
        place_window(self, master)

    def _on_map(self, event: tk.Event) -> None:
        """On the screen: modal over the window, and in front (as the colophon's offer it follows)."""
        if event.widget is not self:
            return
        try:
            self.grab_set()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def answers(self) -> dict[tuple[str, ...], bool]:
        """Each conflict's key to the row's choice: True where it says take this book's."""
        return {key: var.get() == "theirs" for key, var in self.choices}

    def set_all(self, take: bool) -> None:
        """All series' / All this book's: every row's choice alike."""
        for _key, var in self.choices:
            var.set("theirs" if take else "mine")

    def apply(self) -> None:
        """Rename: the book renamed with the answers as chosen (*on_apply*)."""
        if self.answered:
            return
        self.answered = True
        answers = self.answers()
        self.destroy()
        self.on_apply(answers)

    def cancel(self) -> None:
        """Cancel: the book keeps its name."""
        if self.answered:
            return
        self.answered = True
        self.destroy()
        if self.on_cancel is not None:
            self.on_cancel()


__all__ = ["RenameReviewDialog"]
