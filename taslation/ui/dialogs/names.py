"""The names a whole-book run rendered in more than one way (`NamesDialog`, from the band at the end of the run or
Tools > Names rendered in more than one way...): each name as the Japanese writes it, its renderings and how many
lines hold each (`taslation.name_variants`). The reader picks one rendering, or types one, and Apply changes the
lines with another rendering to it (only lines whose Japanese has the name) and keeps it in the series sheet when
that box is ticked; Take back undoes both. Nothing is changed before Apply, and one name at a time.

The window is the reader's own: the names and renderings it shows go nowhere else (no log, no console)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from ...i18n import _
from ...name_variants import NameVariants
from ..layout import place_window

WRAP = 460  # px: the lines of explanation
LIST_ROWS = 10


def list_line(variants: NameVariants, chosen: str = "") -> str:
    """A name's line in the list: the name, its renderings with their counts, and the one chosen."""
    counts = ", ".join(f"{spelling} {n}" for spelling, n in variants.counts())
    return f"{variants.source}  ({counts})" + (f"  ✓ {chosen}" if chosen else "")


class NamesDialog(tk.Toplevel):
    """The names of *variants*, one chosen at a time in the list. *on_apply(variants, rendering, to_sheet)* changes the
    lines and the sheet (False when it cannot now: the window says why); *on_take_back(variants)* undoes the last
    change of that name. `applied` and `taken_back` tell the dialog once the change is made; `say` puts a line under
    the buttons. *chosen*: the renderings chosen before (the name as written -> the rendering)."""

    def __init__(self, master: tk.Misc, variants: Sequence[NameVariants],
                 on_apply: Callable[[NameVariants, str, bool], bool], on_take_back: Callable[[NameVariants], bool],
                 chosen: dict[str, str] | None = None):
        super().__init__(master)
        self.title(_("Names rendered in more than one way"))
        self.transient(master)
        self.variants = list(variants)
        self.on_apply, self.on_take_back = on_apply, on_take_back
        self.chosen: dict[str, str] = dict(chosen or {})
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=_("The translation gives these names more than one rendering. Choose the one to keep for each: the lines with another rendering are changed to it, and the series sheet keeps it for the translations to come. Only lines whose Japanese has the name are changed."),
                  wraplength=WRAP, justify="left").pack(anchor="w")
        body = ttk.Frame(frm)
        body.pack(fill="both", expand=True, pady=(10, 0))
        self.listbox = tk.Listbox(body, height=min(LIST_ROWS, max(3, len(self.variants))), exportselection=False,
                                  width=40, activestyle="dotbox")
        self.listbox.pack(side="left", fill="both", expand=True)
        for v in self.variants:
            self.listbox.insert("end", list_line(v, self.chosen.get(v.source, "")))
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._show(self._index()))
        self.detail = ttk.Frame(body, padding=(12, 0, 0, 0))
        self.detail.pack(side="left", fill="both", expand=True)
        self.header = ttk.Label(self.detail, justify="left")
        self.header.pack(anchor="w")
        self.choices = ttk.Frame(self.detail)
        self.choices.pack(anchor="w", fill="x", pady=(6, 0))
        self.choice = tk.StringVar(self)
        self.other = tk.StringVar(self)
        self.to_sheet = tk.BooleanVar(self, value=True)
        self.radios: list[ttk.Radiobutton] = []
        other_row = ttk.Frame(self.detail)
        other_row.pack(anchor="w", fill="x", pady=(2, 0))
        self.other_radio = ttk.Radiobutton(other_row, text=_("Other:"), value="\x00other", variable=self.choice,
                                           command=self._preview)
        self.other_radio.pack(side="left")
        self.other_entry = ttk.Entry(other_row, textvariable=self.other, width=22)
        self.other_entry.pack(side="left", padx=(4, 0))
        self.other_entry.bind("<FocusIn>", lambda _e: (self.choice.set("\x00other"), self._preview()))
        self.other.trace_add("write", lambda *_a: self._preview())
        ttk.Checkbutton(self.detail, text=_("Keep it in the series sheet"), variable=self.to_sheet).pack(
            anchor="w", pady=(8, 0))
        self.preview = ttk.Label(self.detail, justify="left", wraplength=WRAP // 2)
        self.preview.pack(anchor="w", pady=(8, 0))
        buttons = ttk.Frame(self.detail)
        buttons.pack(anchor="w", pady=(8, 0))
        self.apply_btn = ttk.Button(buttons, text=_("Apply"), default="active", command=self.apply)
        self.apply_btn.pack(side="left")
        self.back_btn = ttk.Button(buttons, text=_("Take back"), command=self.take_back)
        self.back_btn.pack(side="left", padx=(6, 0))
        self.line = ttk.Label(frm, justify="left", wraplength=WRAP)
        self.line.pack(anchor="w", pady=(10, 0))
        bottom = ttk.Frame(frm)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text=_("Close"), command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.apply() if self.focus_get() is not self.listbox else None)
        if self.variants:
            self.listbox.selection_set(0)
            self._show(0)
        place_window(self, master)

    # ------------------------------------------------------------------ what is shown
    def _index(self) -> int:
        picked = self.listbox.curselection()
        return int(picked[0]) if picked else 0

    def current(self) -> NameVariants | None:
        return self.variants[self._index()] if self.variants else None

    def _show(self, index: int) -> None:
        """The name at *index* with its renderings, the one chosen before (or the series sheet's, or the most
        frequent) picked."""
        v = self.variants[index]
        self.header.configure(text=_("{name}: on {n} line(s)").format(name=v.source, n=len(v.lines)))
        for radio in self.radios:
            radio.destroy()
        self.radios = []
        spellings = [spelling for spelling, _at in v.renderings]
        for spelling, n in v.counts():
            label = (_("{rendering} - {n} line(s) (series sheet)") if spelling == v.sheet
                     else _("{rendering} - {n} line(s)")).format(rendering=spelling, n=n)
            radio = ttk.Radiobutton(self.choices, text=label, value=spelling, variable=self.choice,
                                    command=self._preview)
            radio.pack(anchor="w")
            self.radios.append(radio)
        before = self.chosen.get(v.source, "")
        if before and before not in spellings:
            self.choice.set("\x00other")
            self.other.set(before)
        else:
            self.other.set("")
            self.choice.set(before or (v.sheet if v.sheet in spellings else spellings[0]))
        self._preview()
        self._sync()

    def picked(self) -> str:
        """The rendering chosen: a listed one, or the one typed ("" when none is typed)."""
        value = self.choice.get()
        return self.other.get().strip() if value == "\x00other" else value

    def _preview(self) -> None:
        v = self.current()
        if v is None:
            return
        chosen = self.picked()
        if not chosen:
            self.preview.configure(text=_("Choose a rendering, or type one."))
            return
        self.preview.configure(text=_("Changes {n} line(s).").format(n=v.to_change(chosen)))

    def _sync(self) -> None:
        v = self.current()
        self.back_btn.state(["!disabled"] if v is not None and v.source in self.chosen else ["disabled"])

    # ------------------------------------------------------------------ the change
    def apply(self) -> None:
        v = self.current()
        chosen = self.picked()
        if v is None:
            return
        if not chosen:
            self.say(_("Choose a rendering, or type one."))
            return
        self.on_apply(v, chosen, bool(self.to_sheet.get()))

    def take_back(self) -> None:
        v = self.current()
        if v is not None and v.source in self.chosen:
            self.on_take_back(v)

    def applied(self, v: NameVariants, chosen: str, line: str) -> None:
        """The change of *v* to *chosen* is made: the list says so, and *line* under the buttons."""
        self.chosen[v.source] = chosen
        self._relist(v)
        self.say(line)

    def taken_back(self, v: NameVariants, line: str) -> None:
        self.chosen.pop(v.source, None)
        self._relist(v)
        self.say(line)

    def _relist(self, v: NameVariants) -> None:
        try:
            index = self.variants.index(v)
        except ValueError:
            return
        self.listbox.delete(index)
        self.listbox.insert(index, list_line(v, self.chosen.get(v.source, "")))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self._show(index)

    def say(self, line: str) -> None:
        self.line.configure(text=line)

    def bring_up(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_set()


def labels(dialog: Any) -> list[str]:
    """The renderings offered for the name on show, as their buttons say them (for the tests)."""
    return [str(r.cget("text")) for r in dialog.radios]


__all__ = ["NamesDialog", "labels", "list_line"]
