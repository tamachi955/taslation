"""Find and replace across the book (`FindReplaceDialog`), from Translator > Find and replace... and the button of the
translator strip: a window that blocks nothing, whose list of matches (page and the line around each) follows what is
typed. Nothing is written until a Replace button is pressed. The search and the change are the window's (`ui.replace`).

Ctrl+Z and Ctrl+Y work here as in the window: a dialog's keys do not reach it by themselves."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ...i18n import _
from ..layout import place_window
from ..replace import Hit, Query, around
from ..tooltip import tip

REFRESH_MS = 120  # after the last key: a word typed fast is searched once
MAX_ROWS = 500  # rows in the list: a single letter can match thousands of times (the count and Replace all take every one)
LINE_WRAP = 660  # pixels


class FindReplaceDialog(tk.Toplevel):
    """*search* gives for a `Query` the matches and a line to show when there is nowhere to look; *on_replace* takes
    the query, the replacement and the keys of the matches picked (None: all) and says whether it went ahead; *on_undo*
    and *on_redo* are the window's Ctrl+Z and Ctrl+Y. *kept*: what `kept` gave, from the window before a language
    switch."""

    def __init__(self, master: tk.Misc, search: Callable[[Query], tuple[list[Hit], str]],
                 on_replace: Callable[[Query, str, set[Any] | None], bool], on_undo: Callable[[], None],
                 on_redo: Callable[[], None], kept: dict[str, Any] | None = None):
        super().__init__(master)
        self.search, self.on_replace = search, on_replace
        kept = kept or {}
        self.title(_("Find and replace"))
        self.transient(master)
        self.geometry("720x460")
        self.minsize(460, 300)
        self.hits: list[Hit] = []
        self.rows: list[tuple[Any, str, str]] = []  # what the list shows: each match's key, page and line
        self._due: str | None = None  # the look that waits for the last key
        self.find_var = tk.StringVar(self, kept.get("find", ""))
        self.replace_var = tk.StringVar(self, kept.get("replace", ""))
        self.case_var = tk.BooleanVar(self, kept.get("case", False))
        self.word_var = tk.BooleanVar(self, kept.get("word", False))
        self.count_var = tk.StringVar(self, "")
        self.said_var = tk.StringVar(self, "")

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(4, weight=1)
        label = ttk.Label(frm, text=_("Find:"))
        label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.find_entry = ttk.Entry(frm, textvariable=self.find_var)
        self.find_entry.grid(row=0, column=1, sticky="ew")
        tip(_("The words to look for in this book's translations, in the language chosen."), label, self.find_entry)
        label = ttk.Label(frm, text=_("Replace with:"))
        label.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
        self.replace_entry = ttk.Entry(frm, textvariable=self.replace_var)
        self.replace_entry.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        tip(_("What goes in their place. Nothing changes until you press a Replace button."), label, self.replace_entry)
        boxes = ttk.Frame(frm)
        boxes.grid(row=2, column=1, sticky="w", pady=(4, 0))
        case = ttk.Checkbutton(boxes, text=_("Match case"), variable=self.case_var)
        case.pack(side="left")
        tip(_("Tell capitals from small letters."), case)
        word = ttk.Checkbutton(boxes, text=_("Whole word"), variable=self.word_var)
        word.pack(side="left", padx=(10, 0))
        tip(_("Only where it stands as a word of its own, not inside a longer one."), word)
        ttk.Label(frm, textvariable=self.count_var, anchor="w", justify="left", wraplength=LINE_WRAP).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        listed = ttk.Frame(frm)
        listed.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.tree = ttk.Treeview(listed, columns=("page", "line"), show="headings", height=12, selectmode="extended")
        self.tree.heading("page", text=_("Page"))
        tip(_("Page numbers follow the order in which the pages were first read, not the numbers printed in the book."), self.tree)
        self.tree.heading("line", text=_("Translation"), anchor="w")
        self.tree.column("page", width=70, stretch=False, anchor="e")
        self.tree.column("line", width=600)
        bar = ttk.Scrollbar(listed, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_buttons())
        ttk.Label(frm, textvariable=self.said_var, anchor="w", justify="left", wraplength=LINE_WRAP).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.selected_btn = ttk.Button(btns, text=_("Replace selected"), command=self.replace_selected)
        self.selected_btn.pack(side="left")
        tip(_("Replace the lines selected in the list."), self.selected_btn)
        self.all_btn = ttk.Button(btns, text=_("Replace all"), command=self.replace_all)
        self.all_btn.pack(side="left", padx=(6, 0))
        tip(_("Replace every match in the book. Ctrl+Z takes it all back."), self.all_btn)
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")

        for var in (self.find_var, self.case_var, self.word_var):
            var.trace_add("write", self._typed)
        self.bind("<FocusIn>", lambda _e: self.refresh())  # the cache, the book or the language may have changed
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-z>", lambda _e: on_undo())
        self.bind("<Control-y>", lambda _e: on_redo())
        self.update_list()
        place_window(self, master)
        if kept.get("place"):
            self.geometry(kept["place"])
        self.find_entry.focus_set()

    def query(self) -> Query:
        return Query(self.find_var.get(), self.case_var.get(), self.word_var.get())

    def kept(self) -> dict[str, Any]:
        """What the window shows, for the window a language switch builds anew."""
        return {"find": self.find_var.get(), "replace": self.replace_var.get(), "case": self.case_var.get(),
                "word": self.word_var.get(), "place": self.geometry()}

    def bring_up(self) -> None:
        self.lift()
        self.find_entry.focus_set()
        self.refresh()

    def say(self, line: str) -> None:
        """The line under the list: what the last replacement did."""
        self.said_var.set(line)

    def _typed(self, *_args: object) -> None:
        self.said_var.set("")
        self.refresh()

    def refresh(self) -> None:
        """Look again in a moment, once for all that comes until then."""
        if self._due is not None:
            self.after_cancel(self._due)
        self._due = self.after(REFRESH_MS, self.update_list)

    def update_list(self) -> None:
        """Look now. The rows are built anew only when they differ, so that what is selected stays selected, also when
        the lines moved."""
        if self._due is not None:
            self.after_cancel(self._due)
            self._due = None
        self.hits, note = self.search(self.query())
        rows = [(h.key, str(h.page), around(h)) for h in self.hits[:MAX_ROWS]]
        if rows != self.rows:
            chosen = self.picked()
            self.rows = rows
            self.tree.delete(*self.tree.get_children())
            for i, (_key, page, line) in enumerate(rows):
                self.tree.insert("", "end", iid=str(i), values=(page, line))
            again = [str(i) for i, row in enumerate(rows) if row[0] in chosen]
            if again:
                self.tree.selection_set(again)
        self.count_var.set(note or self._counted())
        self._sync_buttons()

    def _counted(self) -> str:
        if not self.find_var.get():
            return ""
        if not self.hits:
            return _("No match.")
        line = _("{n} match(es) on {pages} page(s).").format(n=len(self.hits), pages=len({h.page for h in self.hits}))
        if len(self.hits) > len(self.rows):
            line += " " + _("The first {shown} are listed; Replace all takes every one.").format(shown=len(self.rows))
        return line

    def _sync_buttons(self) -> None:
        self.selected_btn["state"] = "normal" if self.tree.selection() else "disabled"
        self.all_btn["state"] = "normal" if self.hits else "disabled"

    def picked(self) -> set[Any]:
        """The keys of the matches selected in the list."""
        return {self.rows[int(iid)][0] for iid in self.tree.selection()}

    def replace_selected(self) -> None:
        self.update_list()  # the rows as the cache holds them now
        picked = self.picked()
        if picked:
            self.on_replace(self.query(), self.replace_var.get(), picked)

    def replace_all(self) -> None:
        self.update_list()
        if self.hits:
            self.on_replace(self.query(), self.replace_var.get(), None)

    def destroy(self) -> None:
        if self._due is not None:
            try:
                self.after_cancel(self._due)
            except tk.TclError:
                pass
            self._due = None
        super().destroy()


__all__ = ["FindReplaceDialog", "MAX_ROWS"]
