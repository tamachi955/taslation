"""The detection and OCR settings that suit one book, kept with its premises (`BookSettingsDialog`, opened by
Translator > Book settings...): three plain choices, the size of the book's lettering (`SIZE_ROWS`), and with
`settings.debug` the numbers too. Clear all asks first (Keep them has the focus) and can be taken back once with Undo
while the dialog is open. Below the choices, the areas ignored on all pages of the book (`annotations.BookArea`:
watermarks, page numbers, banners; added in translator mode, `ui.book_areas`), each named by the pages it applies to
and where it lies on them; Remove area (or Delete in the list) makes text be looked for there again, and the same Undo
puts it back."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ...annotations import BOOK_SETTING_BOUNDS, BOOK_SETTING_KEYS
from ...i18n import _
from ..layout import place_window
from ..tooltip import tip
from . import caches
from .caches import ERROR_COLOUR
from .help import explain_button
from .settings import percent, percent_of, text_scale_choices

CHOICES = {"detect_text_blocks": "Also translate text outside the bubbles",
           "detect_dark_bubbles": "Also translate bubbles on a dark background",
           "translate_sfx": "Translate sound effects"}  # what a reader chooses; a tick as the reader's own setting is no value
# Clear all: the question before it, what it says when there is nothing to clear, and once it has cleared
CLEAR_QUESTION = "Clear this book's {n} choice(s) of its own? Your own settings apply to it again. Undo in this window puts them back."
NOTHING_TO_CLEAR = "This book has no choices of its own: your own settings apply to it already."
CLEARED = "Cleared: your own settings apply to this book. Undo puts its choices back."
UNDONE = "This book's choices are back."
UNDO_TIP = "Put back the choices Clear all dropped (while this window is open)."
# the areas ignored on all pages of the book: the list's heading, a line per area, the pages it applies to, the line
# while there are none, Remove area, what it says once removed and once Undo put it back
AREAS_HEADING = "Areas ignored on all pages of this book (watermarks, page numbers, banners):"
AREA_ROW = "{pages}: {x0}-{x1} % across, {y0}-{y1} % down"
SIDE_WORDS = {"": "All pages", "right": "Right-hand pages", "left": "Left-hand pages"}
NO_AREAS = "None yet: in translator mode, Page > Ignore this area on all pages of this book adds one."
REMOVE_AREA = "Remove area"
REMOVE_AREA_TIP = "Look for text in the selected area again on every page of this book (Delete in the list)."
AREA_REMOVED = "Area removed: text is looked for there again. Undo puts it back."
AREA_BACK = "The area is ignored on all pages again."
AREA_UNDO_TIP = "Undo also puts back an area you removed."


def area_line(area: Any) -> str:
    """An area as the list names it: the pages it applies to, and where it lies on them in hundredths of the page."""
    x0, y0, x1, y1 = (max(0, min(100, round(float(v) * 100))) for v in area.box)
    return _(AREA_ROW).format(pages=_(SIDE_WORDS.get(area.side, SIDE_WORDS[""])), x0=x0, x1=x1, y0=y0, y1=y1)
SIZE_ROWS = ("text_scale", "max_font_size")  # the book's lettering size and largest size ("As in Settings", empty: none)


class BookSettingsDialog(tk.Toplevel):
    """Settings that suit this book, kept with its premises (`annotations.BOOK_SETTING_KEYS`): `CHOICES` as checkboxes,
    which start as this book has them or else as the reader's own setting; the lettering size and the largest size
    (`SIZE_ROWS`: "As in Settings" and an empty box are the reader's own, Tools > Settings...); only with
    `settings.debug` the other keys, as raw values (empty: the reader's own setting). Without it those stay as the
    book has them. Applied, the page on show is lettered again (`App._after_book_settings`). Clear all asks first,
    saying how many choices go (`CLEAR_QUESTION`, Keep them focused; with none it only says so), and leaves the dialog
    open with Undo, which puts back what it dropped. The areas ignored on all pages are listed under the choices
    (`area_line`; with annotations that keep areas); Remove area takes the selected one out of the book's annotations
    at once, and Undo, the last thing done in the dialog either way, puts it back."""

    def __init__(self, master: tk.Misc, pipeline: Any, on_change: Callable[[], None]):
        super().__init__(master)
        self.pipeline, self.on_change = pipeline, on_change
        self.title(_("Book settings"))
        self.transient(master)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        grid = ttk.Frame(frm)
        grid.pack(fill="x")
        current = pipeline.annotations.settings if pipeline.annotations is not None else {}
        base = pipeline._base_settings
        self.choices: dict[str, tk.BooleanVar] = {}
        self._cleared: dict[str, Any] | None = None  # what Clear all dropped, for Undo
        self._removed_area: Any = None  # the area Remove area took out, for Undo
        self.areas_list: tk.Listbox | None = None
        for i, (key, word) in enumerate(CHOICES.items()):
            var = tk.BooleanVar(self, value=bool(current.get(key, getattr(base, key))))
            self.choices[key] = var
            ttk.Checkbutton(grid, text=_(word), variable=var).grid(row=i, column=0, columnspan=3, sticky="w", pady=1)
        row = len(CHOICES)
        self.yours_scale = _("As in Settings ({value})").format(value=percent(base.text_scale))
        name = ttk.Label(grid, text=_("Lettering size:"))
        name.grid(row=row, column=0, sticky="w", pady=(6, 1))
        self.scale_var = tk.StringVar(self, value=percent(current["text_scale"]) if "text_scale" in current
                                      else self.yours_scale)
        shown_scales = [self.yours_scale, *text_scale_choices(current.get("text_scale", base.text_scale))]
        box = ttk.Combobox(grid, textvariable=self.scale_var, values=shown_scales, state="readonly",
                           width=max(len(s) for s in shown_scales) + 2)
        box.grid(row=row, column=1, columnspan=2, sticky="w", padx=(6, 10), pady=(6, 1))
        tip(_("This book's translations lettered smaller or larger by so much. As in Settings: the size in Tools > Settings..."), name, box)
        name = ttk.Label(grid, text=_("Largest size (pixels):"))
        name.grid(row=row + 1, column=0, sticky="w", pady=1)
        self.top_var = tk.StringVar(self, value=str(current["max_font_size"]) if "max_font_size" in current else "")
        box = ttk.Entry(grid, textvariable=self.top_var, width=6)
        box.grid(row=row + 1, column=1, sticky="w", padx=(6, 10), pady=1)
        ttk.Label(grid, text=_("(yours: {value})").format(value=base.max_font_size)).grid(row=row + 1, column=2, sticky="w")
        tip(_("No translation of this book is lettered larger than this. Empty: the largest size in Tools > Settings..."), name, box)
        self.vars: dict[str, tk.StringVar] = {}
        self.kept = {key: value for key, value in current.items() if key not in CHOICES and key not in SIZE_ROWS}
        shown = ([key for key in BOOK_SETTING_KEYS if key not in CHOICES and key not in SIZE_ROWS]
                 if getattr(base, "debug", False) else [])
        for i, key in enumerate(shown, start=row + 2):
            ttk.Label(grid, text=key).grid(row=i, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=str(current[key]) if key in current else "")
            self.vars[key] = var
            ttk.Entry(grid, textvariable=var, width=14).grid(row=i, column=1, sticky="w", padx=(6, 10), pady=1)
            ttk.Label(grid, text=_("(yours: {value})").format(value=getattr(base, key))).grid(row=i, column=2, sticky="w")
        self.problem = ttk.Label(frm, text="", foreground=ERROR_COLOUR, justify="left")
        self.problem.pack(anchor="w")
        if pipeline.annotations is not None and hasattr(pipeline.annotations, "areas"):
            self._build_areas(frm)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))
        button = ttk.Button(btns, text=_("Apply to this book"), command=self._apply)
        button.pack(side="left")
        tip(_("Use these choices for this book."), button)
        button = ttk.Button(btns, text=_("Clear all"), command=self._clear)
        button.pack(side="left", padx=(6, 0))
        tip(_("Drop this book's choices: your own settings apply again."), button)
        self.undo_btn = ttk.Button(btns, text=_("Undo"), command=self._undo, state="disabled")
        self.undo_btn.pack(side="left", padx=(6, 0))
        tip(_(UNDO_TIP) + (" " + _(AREA_UNDO_TIP) if self.areas_list is not None else ""), self.undo_btn)
        explain_button(btns, _("These choices apply to this book only. Clear all goes back to your own settings.")).pack(
            side="left", padx=(6, 0))
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")
        self.said_var = tk.StringVar(self, value="")  # what Clear all or Undo did
        ttk.Label(frm, textvariable=self.said_var, wraplength=420, justify="left").pack(anchor="w", pady=(6, 0))
        place_window(self, master)

    def _build_areas(self, frm: ttk.Frame) -> None:
        """The list of the areas ignored on all pages, with Remove area beside it and a line while there are none."""
        ttk.Label(frm, text=_(AREAS_HEADING), wraplength=420, justify="left").pack(anchor="w", pady=(10, 2))
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.areas_list = tk.Listbox(row, height=4, width=48, exportselection=False, activestyle="dotbox")
        self.areas_list.pack(side="left", fill="x", expand=True)
        self.areas_list.bind("<<ListboxSelect>>", lambda _e: self._sync_areas())
        self.areas_list.bind("<Delete>", lambda _e: self._remove_area())
        self.remove_area_btn = ttk.Button(row, text=_(REMOVE_AREA), command=self._remove_area)
        self.remove_area_btn.pack(side="left", padx=(6, 0), anchor="n")
        tip(_(REMOVE_AREA_TIP), self.remove_area_btn, self.areas_list)
        self.no_areas = ttk.Label(frm, text=_(NO_AREAS), wraplength=420, justify="left", foreground="#5a5a5a")
        self._shown_areas: list[Any] = []
        self._show_areas()

    def _show_areas(self) -> None:
        """The list as the book's annotations have the areas now (the first one selected), or the line that says
        there are none."""
        if self.areas_list is None:
            return
        self._shown_areas = list(getattr(self.pipeline.annotations, "areas", []))
        self.areas_list.delete(0, "end")
        for area in self._shown_areas:
            self.areas_list.insert("end", area_line(area))
        if self._shown_areas:
            self.areas_list.selection_set(0)
            self.areas_list.activate(0)
            self.no_areas.pack_forget()
        elif not self.no_areas.winfo_manager():
            self.no_areas.pack(anchor="w", pady=(2, 0), after=self.areas_list.master)
        self._sync_areas()

    def _sync_areas(self) -> None:
        if self.areas_list is not None:
            self.remove_area_btn.state(["!disabled"] if self.areas_list.curselection() else ["disabled"])

    def _remove_area(self) -> None:
        """Remove area (Delete in the list): the selected area is no longer ignored; Undo puts it back."""
        if self.areas_list is None or not self.areas_list.curselection():
            return
        area = self._shown_areas[self.areas_list.curselection()[0]]
        if not self.pipeline.annotations.remove_area(area):
            return
        self.pipeline.save_annotations()
        self._cleared, self._removed_area = None, area
        self.undo_btn.configure(state="normal")
        self.said_var.set(_(AREA_REMOVED))
        self._show_areas()
        self.on_change()

    def sizes(self) -> dict[str, Any]:
        """The book's lettering size and largest size as the two rows say them (none where they say the reader's
        own); ValueError, in the window's language, for a largest size that is no whole number from the smallest
        size (and the review size) to `BOOK_SETTING_BOUNDS`'s."""
        base = self.pipeline._base_settings
        out: dict[str, Any] = {}
        if self.scale_var.get() != self.yours_scale:
            out["text_scale"] = percent_of(self.scale_var.get())
        raw = self.top_var.get().strip()
        if raw:
            low, high = max(base.min_font_size, base.readable_font_size), BOOK_SETTING_BOUNDS["max_font_size"][1]
            if not raw.isdigit() or not low <= int(raw) <= high:
                raise ValueError(_("The largest size: a whole number from {low} to {high} pixels, or empty for yours.").format(
                    low=low, high=high))
            out["max_font_size"] = int(raw)
        return out

    def _apply(self) -> None:
        base = self.pipeline._base_settings
        try:
            sizes = self.sizes()
        except ValueError as e:
            self.problem.configure(text=str(e))
            return
        values: dict[str, Any] = {} if self.vars else dict(self.kept)
        values.update(sizes)
        for key, var in self.choices.items():
            if var.get() != bool(getattr(base, key)):
                values[key] = var.get()
        for key, var in self.vars.items():
            raw = var.get().strip()
            if not raw:
                continue
            low = raw.lower()
            if low in ("true", "false", "yes", "no", "on", "off"):
                values[key] = low in ("true", "yes", "on")
            else:
                try:
                    values[key] = int(raw) if raw.lstrip("-").isdigit() else float(raw)
                except ValueError:
                    values[key] = raw
        self.pipeline.set_book_settings(values)
        self.destroy()
        self.on_change()

    def _current(self) -> dict[str, Any]:
        annotations = self.pipeline.annotations
        return dict(annotations.settings) if annotations is not None else {}

    def _show(self, current: dict[str, Any]) -> None:
        """The fields as the book's choices *current* have them."""
        base = self.pipeline._base_settings
        for key, var in self.choices.items():
            var.set(bool(current.get(key, getattr(base, key))))
        self.scale_var.set(percent(current["text_scale"]) if "text_scale" in current else self.yours_scale)
        self.top_var.set(str(current["max_font_size"]) if "max_font_size" in current else "")
        self.problem.configure(text="")
        for key, var in self.vars.items():
            var.set(str(current[key]) if key in current else "")
        self.kept = {key: value for key, value in current.items() if key not in CHOICES and key not in SIZE_ROWS}

    def _clear(self) -> None:
        """Clear all: after the question, the book's choices go and the reader's own settings apply; the dialog
        stays, with Undo."""
        current = self._current()
        if not current:
            self.said_var.set(_(NOTHING_TO_CLEAR))
            return
        if not caches.ask(self, _(CLEAR_QUESTION).format(n=len(current)), _("Clear all"), _("Keep them"),
                          no_first=True):
            return
        self.pipeline.set_book_settings({})
        self._cleared, self._removed_area = current, None
        self._show({})
        self.undo_btn.configure(state="normal")
        self.said_var.set(_(CLEARED))
        self.on_change()

    def _undo(self) -> None:
        """Undo: the choices Clear all dropped are the book's again, or the area Remove area took out is ignored
        again - whichever was done last."""
        if self._removed_area is not None:
            area, self._removed_area = self._removed_area, None
            self.pipeline.annotations.add_area(area)
            self.pipeline.save_annotations()
            self._show_areas()
            self.undo_btn.configure(state="disabled")
            self.said_var.set(_(AREA_BACK))
            self.on_change()
            return
        if self._cleared is None:
            return
        back, self._cleared = self._cleared, None
        self.pipeline.set_book_settings(back)
        self._show(back)
        self.undo_btn.configure(state="disabled")
        self.said_var.set(_(UNDONE))
        self.on_change()
