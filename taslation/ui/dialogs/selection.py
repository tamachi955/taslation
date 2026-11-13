"""The small questions translator mode's Page menu asks about the selected regions, one or several (`ui.selection`):
the kind of text they hold (`KindDialog`, the region editor's Kind list), a fixed text size or the size that fits
(`SizeDialog`, the editor's Size), and their place in the page's reading order (`PlaceDialog`). Each is modal over
the window and centred on it, with OK (also Return) and Cancel (also Esc and the close box); ``answer`` stays None
unless OK took a value."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ...annotations import STYLE_SIZES
from ...i18n import _
from ..layout import fit_combobox, place_window
from ..tooltip import tip
from .review import AUTO, REGION_KIND_WORDS, kind_of, kind_words

# what each question says, {n}: how many regions are selected
KIND_LINE = "The kind of text of the {n} selected region(s):"
SIZE_LINE = "The text size of the {n} selected region(s):"
PLACE_LINE = "Put the {n} selected region(s) at this place in the page's reading order:"
PLACE_OF = "of {total}"
SIZE_START = 24  # the size the box shows while the size is automatic (the region editor's too)
WRAP = 380  # pixels: the question's line is broken this wide


def whole(text: str) -> int | None:
    """*text* as a whole number (a decimal one rounded), None when it is none."""
    try:
        return int(round(float(text.strip().replace(",", "."))))
    except (TypeError, ValueError):
        return None


class ValueDialog(tk.Toplevel):
    """A small modal question over *master*: *text*, one field (`_field`), OK and Cancel. OK takes the field's value
    (`value`; None: not one, and the box rings) as ``answer``."""

    def __init__(self, master: tk.Misc, text: str):
        super().__init__(master)
        self.title("TASlation")
        self.transient(master)
        self.resizable(False, False)
        self.answer: Any = None
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        self.line = ttk.Label(frm, text=text, justify="left", wraplength=WRAP)
        self.line.grid(row=0, column=0, sticky="w")
        field = ttk.Frame(frm)
        field.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._field(field)
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, sticky="e", pady=(12, 0))
        self.cancel_btn = ttk.Button(btns, text=_("Cancel"), command=self.destroy)
        self.cancel_btn.pack(side="right")
        self.ok_btn = ttk.Button(btns, text=_("OK"), command=self._ok, default="active")
        self.ok_btn.pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<KP_Enter>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        place_window(self, master)
        try:
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    def _field(self, parent: ttk.Frame) -> None:
        raise NotImplementedError

    def value(self) -> Any:
        raise NotImplementedError

    def _ok(self) -> None:
        value = self.value()
        if value is None:
            self.bell()
            return
        self.answer = value
        self.destroy()


class KindDialog(ValueDialog):
    """The kind of text of *count* selected regions, from the region editor's list (`review.kind_words`), *kind*
    shown first; ``answer`` is its code (`REGION_KINDS`)."""

    def __init__(self, master: tk.Misc, count: int, kind: str = ""):
        self._start = kind
        super().__init__(master, _(KIND_LINE).format(n=count))

    def _field(self, parent: ttk.Frame) -> None:
        words = kind_words()
        self.kind_var = tk.StringVar(self, value=_(REGION_KIND_WORDS.get(self._start, self._start)))
        self.kind_box = ttk.Combobox(parent, textvariable=self.kind_var, values=words, state="readonly")
        fit_combobox(self.kind_box, words)
        self.kind_box.pack(side="left")
        self.kind_box.focus_set()

    def value(self) -> str:
        return kind_of(self.kind_var.get().strip())


class SizeDialog(ValueDialog):
    """A text size for *count* selected regions: a fixed one within `STYLE_SIZES`, or Auto (0, the largest that
    fits, as the region editor's Size); *size* shown first (0: Auto)."""

    def __init__(self, master: tk.Misc, count: int, size: int = 0):
        self._start = int(size or 0)
        super().__init__(master, _(SIZE_LINE).format(n=count))

    def _field(self, parent: ttk.Frame) -> None:
        self.size_var = tk.StringVar(self, value=str(self._start or SIZE_START))
        self.size_spin = ttk.Spinbox(parent, from_=STYLE_SIZES[0], to=STYLE_SIZES[1], increment=1, width=5,
                                     textvariable=self.size_var)
        self.size_spin.pack(side="left", padx=(0, 6))
        self.auto_var = tk.BooleanVar(self, value=not self._start)
        check = ttk.Checkbutton(parent, text=_(AUTO), variable=self.auto_var, command=self._sync)
        check.pack(side="left")
        tip(_("The size that fits the bubble."), check)
        self._sync()
        self.size_spin.focus_set()

    def _sync(self) -> None:
        self.size_spin.configure(state="disabled" if self.auto_var.get() else "normal")

    def value(self) -> int | None:
        if self.auto_var.get():
            return 0
        size = whole(self.size_var.get())
        return None if size is None else max(STYLE_SIZES[0], min(STYLE_SIZES[1], size))


class PlaceDialog(ValueDialog):
    """The place, 1 to *total*, the *count* selected regions are put at in the page's reading order (*place* shown
    first)."""

    def __init__(self, master: tk.Misc, count: int, total: int, place: int = 1):
        self._total, self._start = max(1, int(total)), max(1, min(int(total), int(place)))
        super().__init__(master, _(PLACE_LINE).format(n=count))

    def _field(self, parent: ttk.Frame) -> None:
        self.place_var = tk.StringVar(self, value=str(self._start))
        self.place_spin = ttk.Spinbox(parent, from_=1, to=self._total, increment=1, width=5,
                                      textvariable=self.place_var)
        self.place_spin.pack(side="left", padx=(0, 6))
        ttk.Label(parent, text=_(PLACE_OF).format(total=self._total)).pack(side="left")
        self.place_spin.focus_set()

    def value(self) -> int | None:
        place = whole(self.place_var.get())
        return None if place is None else max(1, min(self._total, place))


__all__ = ["KIND_LINE", "KindDialog", "PLACE_LINE", "PLACE_OF", "PlaceDialog", "SIZE_LINE", "SizeDialog",
           "ValueDialog", "whole"]
