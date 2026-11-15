"""The detection and OCR settings that suit one book, kept with its premises (`BookSettingsDialog`, opened by
Translator > Book settings...): three plain choices, the size of the book's lettering (`SIZE_ROWS`), the book's
reading direction (`DIRECTIONS`), and with `settings.debug` the numbers too. Clear all asks first (Keep them has the
focus) and can be taken back once with Undo while the dialog is open. Below the choices, the areas ignored on all pages
of the book (`annotations.BookArea`: watermarks, page numbers, banners; added in translator mode, `ui.book_areas`),
each named by the pages it applies to and where it lies on them; Remove area (or Delete in the list) makes text be
looked for there again, and the same Undo puts it back.

A book of a series (one whose name has a volume, `annotations.series_of`) can keep its values as the series' defaults,
which a new volume of the series starts from (`annotations.SeriesDefaults`): Save as the series' default (`SHARE`:
the choices, sizes and reading direction, applied to this book as well) and, beside the areas, Use these areas for
the series (`book_areas.use_areas_for_series`). In a book that follows its series (`BookAnnotations.follows_series`),
a value it has none of its own for is the series' default, and the dialog says so beside it (`FROM_SERIES`,
`AS_SERIES`, `SERIES_VALUE`, `AREAS_FROM_SERIES`); a choice as the series' default is no value of the book's own, as a
choice as the reader's own setting is none without one, and Clear all goes back to the series' defaults."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ...annotations import BOOK_SETTING_BOUNDS, BOOK_SETTING_KEYS
from ...i18n import _
from ..book_areas import USE_FOR_SERIES, USE_FOR_SERIES_TIP, use_areas_for_series
from ..layout import fit_combobox, place_window
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
# a series' defaults (`annotations.SeriesDefaults`): the button that keeps this book's values as them, its tip, what it
# says once saved or when it could not save; the line that names the series; beside a value that comes from them: a
# choice, the first choice of the lettering size and of the reading direction, a box left empty; the line over areas
# that are the series'; Clear all in a book that follows defaults of its series
SHARE = "Save as the series' default"
SHARE_TIP = ("Use these choices, sizes and reading direction for this book, and start every new volume of {series} "
             "from them. The areas ignored on all pages have a button of their own.")
SHARED = "Saved as the defaults of {series}: a new volume of it starts from these choices, sizes and reading direction."
SHARE_FAILED = "Could not save the series' defaults: {error}"
SERIES_LINE = "A new volume of {series} starts from the series' defaults."
FOLLOWS_LINE = "Values marked as the series' default come from the defaults of {series}; this book's own values win."
FROM_SERIES = "(the series' default)"
AS_SERIES = "As the series' default ({value})"
SERIES_VALUE = "(series' default: {value})"
AREAS_FROM_SERIES = ("These are the areas of {series}. Removing one here, or adding one in translator mode, gives "
                     "this book a list of its own.")
CLEAR_QUESTION_SERIES = ("Clear this book's {n} choice(s) of its own? The series' defaults apply to it again, and your "
                         "own settings where the series has none. Undo in this window puts them back.")
NOTHING_TO_CLEAR_SERIES = ("This book has no choices of its own: the series' defaults and your own settings apply to it "
                           "already.")
CLEARED_SERIES = ("Cleared: the series' defaults apply to this book again, and your own settings where the series has "
                  "none. Undo puts its choices back.")
HINT_COLOUR = "#5a5a5a"


def area_line(area: Any) -> str:
    """An area as the list names it: the pages it applies to, and where it lies on them in hundredths of the page."""
    x0, y0, x1, y1 = (max(0, min(100, round(float(v) * 100))) for v in area.box)
    return _(AREA_ROW).format(pages=_(SIDE_WORDS.get(area.side, SIDE_WORDS[""])), x0=x0, x1=x1, y0=y0, y1=y1)
SIZE_ROWS = ("text_scale", "max_font_size")  # the book's lettering size and largest size ("As in Settings", empty: none)
# the book's reading direction (`BookAnnotations.reading_direction`; "" is read right to left): the row's label, its
# two choices, and its tip. It is no setting of the reader's own, so Clear all leaves it as it is.
DIRECTION_LABEL = "Reading direction:"
DIRECTIONS = {"rtl": "Right to left (Japanese books)", "ltr": "Left to right"}
DIRECTION_TIP = ("Which page of a two-page spread is read first, and the order of the bubbles on a page. Pages "
                 "translated before keep their translations and take the new order when shown again. Clear all "
                 "leaves it as it is.")


class BookSettingsDialog(tk.Toplevel):
    """Settings that suit this book, kept with its premises (`annotations.BOOK_SETTING_KEYS`): `CHOICES` as checkboxes,
    which start as this book has them or else as the reader's own setting; the lettering size and the largest size
    (`SIZE_ROWS`: "As in Settings" and an empty box are the reader's own, Tools > Settings...); the book's reading
    direction (`DIRECTIONS`, with annotations that keep one: `Pipeline.set_reading_direction`, which Clear all leaves
    alone); only with `settings.debug` the other keys, as raw values (empty: the reader's own setting). Without it
    those stay as the book has them. Applied, the page on show is lettered again (`App._after_book_settings`), its
    spread and its bubbles in the book's direction. Clear all asks first,
    saying how many choices go (`CLEAR_QUESTION`, Keep them focused; with none it only says so), and leaves the dialog
    open with Undo, which puts back what it dropped. The areas ignored on all pages are listed under the choices
    (`area_line`; with annotations that keep areas); Remove area takes the selected one out of the book's annotations
    at once, and Undo, the last thing done in the dialog either way, puts it back.

    In a book that follows its series' defaults (`series_values`), what the book has no value of its own for is the
    series' default instead of the reader's own setting (`_fallback`): a checkbox starts as it and says so, "As the
    series' default" is the lettering size's and the reading direction's first choice, an empty box says the
    series' value. Save as the series' default (with annotations that know their series: `can_share`) applies the
    values to this book and keeps them as the series' defaults; the dialog stays."""

    def __init__(self, master: tk.Misc, pipeline: Any, on_change: Callable[[], None]):
        super().__init__(master)
        self.pipeline, self.on_change = pipeline, on_change
        self.title(_("Book settings"))
        self.transient(master)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        grid = ttk.Frame(frm)
        grid.pack(fill="x")
        current = self._current()
        self.series_values = self._inherited()  # the series' default settings this book follows ({}: none)
        base = pipeline._base_settings
        self.choices: dict[str, tk.BooleanVar] = {}
        self.hints: dict[str, ttk.Label] = {}  # beside a choice: it is the series' default
        self._cleared: dict[str, Any] | None = None  # what Clear all dropped, for Undo
        self._removed_area: Any = None  # the area Remove area took out, for Undo
        self.areas_list: tk.Listbox | None = None
        self.share_areas_btn: ttk.Button | None = None
        for i, (key, word) in enumerate(CHOICES.items()):
            var = tk.BooleanVar(self, value=bool(current.get(key, self._fallback(key))))
            self.choices[key] = var
            ttk.Checkbutton(grid, text=_(word), variable=var).grid(row=i, column=0, columnspan=3, sticky="w", pady=1)
            self.hints[key] = ttk.Label(grid, text=_(FROM_SERIES), foreground=HINT_COLOUR)
            self.hints[key].grid(row=i, column=3, sticky="w", padx=(6, 0))
            var.trace_add("write", lambda *_args, k=key: self._sync_hint(k))
        row = len(CHOICES)
        name = ttk.Label(grid, text=_("Lettering size:"))
        name.grid(row=row, column=0, sticky="w", pady=(6, 1))
        self.yours_scale = self._unset_scale()
        self.scale_var = tk.StringVar(self, value=percent(current["text_scale"]) if "text_scale" in current
                                      else self.yours_scale)
        shown_scales = self._scales(current)
        self.scale_box = ttk.Combobox(grid, textvariable=self.scale_var, values=shown_scales, state="readonly",
                                      width=max(len(s) for s in shown_scales) + 2)
        self.scale_box.grid(row=row, column=1, columnspan=2, sticky="w", padx=(6, 10), pady=(6, 1))
        tip(_("This book's translations lettered smaller or larger by so much. As in Settings: the size in Tools > Settings..."), name, self.scale_box)
        name = ttk.Label(grid, text=_("Largest size (pixels):"))
        name.grid(row=row + 1, column=0, sticky="w", pady=1)
        self.top_var = tk.StringVar(self, value=str(current["max_font_size"]) if "max_font_size" in current else "")
        box = ttk.Entry(grid, textvariable=self.top_var, width=6)
        box.grid(row=row + 1, column=1, sticky="w", padx=(6, 10), pady=1)
        self.sides: dict[str, ttk.Label] = {}  # beside a box: the value it gives when left empty
        self.sides["max_font_size"] = ttk.Label(grid, text=self._side_text("max_font_size"))
        self.sides["max_font_size"].grid(row=row + 1, column=2, sticky="w")
        tip(_("No translation of this book is lettered larger than this. Empty: the largest size in Tools > Settings..."), name, box)
        self.direction_var: tk.StringVar | None = None  # (annotations that keep no direction: no row)
        self.direction_box: ttk.Combobox | None = None
        self.series_direction_word: str | None = None  # the direction row's "As the series' default" (None: none)
        if pipeline.annotations is not None and hasattr(pipeline.annotations, "reading_direction"):
            self._build_direction(grid, row + 2)
        self.vars: dict[str, tk.StringVar] = {}
        self.kept = {key: value for key, value in current.items() if key not in CHOICES and key not in SIZE_ROWS}
        shown = ([key for key in BOOK_SETTING_KEYS if key not in CHOICES and key not in SIZE_ROWS]
                 if getattr(base, "debug", False) else [])
        for i, key in enumerate(shown, start=row + 3):
            ttk.Label(grid, text=key).grid(row=i, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=str(current[key]) if key in current else "")
            self.vars[key] = var
            ttk.Entry(grid, textvariable=var, width=14).grid(row=i, column=1, sticky="w", padx=(6, 10), pady=1)
            self.sides[key] = ttk.Label(grid, text=self._side_text(key))
            self.sides[key].grid(row=i, column=2, sticky="w")
        self._sync_hints()
        self.problem = ttk.Label(frm, text="", foreground=ERROR_COLOUR, justify="left")
        self.problem.pack(anchor="w")
        self.series_var = tk.StringVar(self, value="")  # the line that names the series (`_series_line`)
        if pipeline.annotations is not None and hasattr(pipeline.annotations, "areas"):
            self._build_areas(frm)
        if self._can_share():
            self._build_series(frm)
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

    # ------------------------------------------------------------------ the book's own values and its series'
    def _current(self) -> dict[str, Any]:
        """The book's own settings (not what it takes from its series' defaults)."""
        annotations = self.pipeline.annotations
        if annotations is None:
            return {}
        own = getattr(annotations, "own_settings", None)
        return dict(own if own is not None else annotations.settings)

    def _inherited(self) -> dict[str, Any]:
        """The series' default settings the book follows ({} for a book that follows none)."""
        inherited = getattr(self.pipeline.annotations, "inherited_settings", None)
        return dict(inherited()) if callable(inherited) else {}

    def _fallback(self, key: str) -> Any:
        """What *key* is for the book without a value of its own: its series' default, else the reader's setting."""
        if key in self.series_values:
            return self.series_values[key]
        return getattr(self.pipeline._base_settings, key)

    def _can_share(self) -> bool:
        return bool(getattr(self.pipeline.annotations, "can_share", False))

    def _series_name(self) -> str:
        return str(getattr(self.pipeline.annotations, "series_name", ""))

    def _unset_scale(self) -> str:
        """The lettering size's first choice, no value of the book's own: as the series' default, else as in
        Settings."""
        if "text_scale" in self.series_values:
            return _(AS_SERIES).format(value=percent(self.series_values["text_scale"]))
        return _("As in Settings ({value})").format(value=percent(self.pipeline._base_settings.text_scale))

    def _scales(self, current: dict[str, Any]) -> list[str]:
        return [self.yours_scale, *text_scale_choices(current.get("text_scale", self._fallback("text_scale")))]

    def _side_text(self, key: str) -> str:
        """Beside the box of *key*: what an empty box gives (the series' default, else the reader's own)."""
        if key in self.series_values:
            return _(SERIES_VALUE).format(value=self.series_values[key])
        return _("(yours: {value})").format(value=getattr(self.pipeline._base_settings, key))

    def _sync_hint(self, key: str) -> None:
        """The hint beside the choice *key*, shown while it is the series' default (no value of the book's own)."""
        hint = self.hints.get(key)
        if hint is None:
            return
        if key in self.series_values and self.choices[key].get() == bool(self.series_values[key]):
            hint.grid()
        else:
            hint.grid_remove()

    def _sync_hints(self) -> None:
        for key in self.hints:
            self._sync_hint(key)

    def _refresh_series(self) -> None:
        """What the dialog says of the series' defaults, as the book follows them now (after a save of them): the
        hints, the first choices, the boxes' side labels, the line that names the series."""
        self.series_values = self._inherited()
        unset = self._unset_scale()
        if self.scale_var.get() == self.yours_scale:
            self.scale_var.set(unset)
        self.yours_scale = unset
        values = [unset, *list(self.scale_box.cget("values"))[1:]]
        self.scale_box.configure(values=values, width=max(len(s) for s in values) + 2)
        for key, side in self.sides.items():
            side.configure(text=self._side_text(key))
        self._sync_hints()
        if self.direction_var is not None and self.direction_box is not None:
            self.series_direction_word = self._series_word()
            words = self._direction_words()
            self.direction_box.configure(values=words)
            fit_combobox(self.direction_box, words)
            self.direction_var.set(self._direction_shown())
        self.series_var.set(self._series_line())

    # ------------------------------------------------------------------ the reading direction
    def _build_direction(self, grid: ttk.Frame, row: int) -> None:
        """The row of the book's reading direction: right to left (also for a book whose direction was never set) or
        left to right; first, in a book that follows a series' default direction, that one."""
        name = ttk.Label(grid, text=_(DIRECTION_LABEL))
        name.grid(row=row, column=0, sticky="w", pady=(6, 1))
        self.series_direction_word = self._series_word()
        words = self._direction_words()
        self.direction_var = tk.StringVar(self, value=self._direction_shown())
        self.direction_box = ttk.Combobox(grid, textvariable=self.direction_var, values=words, state="readonly")
        fit_combobox(self.direction_box, words)
        self.direction_box.grid(row=row, column=1, columnspan=2, sticky="w", padx=(6, 10), pady=(6, 1))
        tip(_(DIRECTION_TIP), name, self.direction_box)

    def _series_direction(self) -> str:
        """The series' default direction the book follows ("rtl" or "ltr"; "" for none)."""
        direction = getattr(self.pipeline.annotations, "inherited_direction", "")
        return direction if direction in DIRECTIONS else ""

    def _series_word(self) -> str | None:
        series = self._series_direction()
        return _(AS_SERIES).format(value=_(DIRECTIONS[series])) if series else None

    def _direction_words(self) -> list[str]:
        words = [_(w) for w in DIRECTIONS.values()]
        return [self.series_direction_word, *words] if self.series_direction_word is not None else words

    def _direction_now(self) -> str:
        """The book's reading direction as the row offers it: "ltr", else "rtl"."""
        return "ltr" if getattr(self.pipeline.annotations, "reading_direction", "") == "ltr" else "rtl"

    def _direction_shown(self) -> str:
        """The row's choice for the book as it is: "As the series' default" while it has no direction of its own and
        follows one of its series, else the direction in force."""
        if self.series_direction_word is not None and not getattr(self.pipeline.annotations, "own_direction", ""):
            return self.series_direction_word
        return _(DIRECTIONS[self._direction_now()])

    def _follows_direction(self) -> bool:
        """Whether the row says the series' default direction (no direction of the book's own)."""
        return (self.direction_var is not None and self.series_direction_word is not None
                and self.direction_var.get() == self.series_direction_word)

    def direction(self) -> str:
        """The reading direction the row says ("rtl" or "ltr"; the series' default for "As the series' default");
        the book's own without the row."""
        if self.direction_var is None:
            return self._direction_now()
        if self._follows_direction():
            return self._series_direction()
        said = self.direction_var.get()
        return next((key for key, word in DIRECTIONS.items() if said in (word, _(word))), self._direction_now())

    def _apply_direction(self) -> None:
        """The direction the row says as the book's: "As the series' default" drops the book's own (saved when it
        had one); a direction is set through the pipeline (`Pipeline.set_reading_direction`: saved when it changed;
        the one in force is left as it was, "" too)."""
        if self.direction_var is None:
            return
        annotations = self.pipeline.annotations
        if self._follows_direction():
            if getattr(annotations, "own_direction", ""):
                annotations.reading_direction = ""
                save = getattr(self.pipeline, "save_annotations", None)
                if save is not None:
                    save()
            return
        set_direction = getattr(self.pipeline, "set_reading_direction", None)
        if set_direction is not None:
            set_direction(self.direction())

    # ------------------------------------------------------------------ the areas ignored on all pages
    def _build_areas(self, frm: ttk.Frame) -> None:
        """The list of the areas ignored on all pages, with Remove area beside it (and, in a book of a series, Use
        these areas for the series), a line while there are none, and one while they are the series'."""
        ttk.Label(frm, text=_(AREAS_HEADING), wraplength=420, justify="left").pack(anchor="w", pady=(10, 2))
        row = ttk.Frame(frm)
        row.pack(fill="x")
        self.areas_list = tk.Listbox(row, height=4, width=48, exportselection=False, activestyle="dotbox")
        self.areas_list.pack(side="left", fill="x", expand=True)
        self.areas_list.bind("<<ListboxSelect>>", lambda _e: self._sync_areas())
        self.areas_list.bind("<Delete>", lambda _e: self._remove_area())
        side = ttk.Frame(row)
        side.pack(side="left", padx=(6, 0), anchor="n")
        self.remove_area_btn = ttk.Button(side, text=_(REMOVE_AREA), command=self._remove_area)
        self.remove_area_btn.pack(fill="x")
        tip(_(REMOVE_AREA_TIP), self.remove_area_btn, self.areas_list)
        if self._can_share():
            self.share_areas_btn = ttk.Button(side, text=_(USE_FOR_SERIES), command=self._share_areas)
            self.share_areas_btn.pack(fill="x", pady=(4, 0))
            tip(_(USE_FOR_SERIES_TIP).format(series=self._series_name()), self.share_areas_btn)
        self.no_areas = ttk.Label(frm, text=_(NO_AREAS), wraplength=420, justify="left", foreground=HINT_COLOUR)
        self.areas_hint = ttk.Label(frm, text="", wraplength=420, justify="left", foreground=HINT_COLOUR)
        self._shown_areas: list[Any] = []
        self._show_areas()

    def _show_areas(self) -> None:
        """The list as the book's annotations have the areas now (the first one selected), or the line that says
        there are none; the line that says they are the series', while they are."""
        if self.areas_list is None:
            return
        annotations = self.pipeline.annotations
        self._shown_areas = list(getattr(annotations, "areas", []))
        self.areas_list.delete(0, "end")
        for area in self._shown_areas:
            self.areas_list.insert("end", area_line(area))
        if self._shown_areas:
            self.areas_list.selection_set(0)
            self.areas_list.activate(0)
            self.no_areas.pack_forget()
        elif not self.no_areas.winfo_manager():
            self.no_areas.pack(anchor="w", pady=(2, 0), after=self.areas_list.master)
        if getattr(annotations, "areas_from_series", False):
            self.areas_hint.configure(text=_(AREAS_FROM_SERIES).format(series=self._series_name()))
            if not self.areas_hint.winfo_manager():
                self.areas_hint.pack(anchor="w", pady=(2, 0), after=self.areas_list.master)
        else:
            self.areas_hint.pack_forget()
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

    def _share_areas(self) -> None:
        """Use these areas for the series: the areas listed kept as the series' (`book_areas.use_areas_for_series`);
        nothing changes on this book's pages."""
        try:
            key, values = use_areas_for_series(self.pipeline)
        except OSError as e:
            self.problem.configure(text=_(SHARE_FAILED).format(error=e))
            return
        self.problem.configure(text="")
        self.said_var.set(_(key).format(**values))
        self._show_areas()
        self.series_var.set(self._series_line())

    # ------------------------------------------------------------------ the series' defaults
    def _build_series(self, frm: ttk.Frame) -> None:
        """Save as the series' default, and the line that names the series."""
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(10, 0))
        button = ttk.Button(row, text=_(SHARE), command=self._share)
        button.pack(side="left")
        tip(_(SHARE_TIP).format(series=self._series_name()), button)
        self.series_var.set(self._series_line())
        ttk.Label(row, textvariable=self.series_var, wraplength=300, justify="left", foreground=HINT_COLOUR).pack(
            side="left", padx=(8, 0))

    def _series_line(self) -> str:
        """The line beside Save as the series' default: which values are the series' in a book that follows them,
        else what a new volume starts from."""
        annotations = self.pipeline.annotations
        follows = bool(self.series_values) or bool(self._series_direction()) or bool(
            getattr(annotations, "areas_from_series", False))
        return _(FOLLOWS_LINE if follows else SERIES_LINE).format(series=self._series_name())

    def _share(self) -> None:
        """Save as the series' default: the values the dialog says are this book's (as Apply makes them) and its
        series' defaults, which a new volume of it starts from (`BookAnnotations.share_settings`: the choices, the
        sizes, the other settings and the reading direction; the areas have a button of their own). The dialog
        stays; Undo has nothing to take back after it."""
        try:
            values = self._values()
        except ValueError as e:
            self.problem.configure(text=str(e))
            return
        annotations = self.pipeline.annotations
        self.pipeline.set_book_settings(values)
        self._apply_direction()
        try:
            annotations.share_settings()
        except OSError as e:  # (FileExistsError among them)
            self.problem.configure(text=_(SHARE_FAILED).format(error=e))
            self.on_change()
            return
        self.problem.configure(text="")
        self._cleared, self._removed_area = None, None
        self.undo_btn.configure(state="disabled")
        self._refresh_series()
        self._show(self._current())
        self.said_var.set(_(SHARED).format(series=self._series_name()))
        self.on_change()

    # ------------------------------------------------------------------ the choices and sizes
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

    def _values(self) -> dict[str, Any]:
        """The book's own values as the dialog says them: a choice as it is without one (the series' default, else
        the reader's own setting) is none, nor a size left so; the settings the dialog does not show stay as the book
        has them. ValueError for a largest size that does not fit (`sizes`)."""
        sizes = self.sizes()
        values: dict[str, Any] = {} if self.vars else dict(self.kept)
        values.update(sizes)
        for key, var in self.choices.items():
            if var.get() != bool(self._fallback(key)):
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
        return values

    def _apply(self) -> None:
        try:
            values = self._values()
        except ValueError as e:
            self.problem.configure(text=str(e))
            return
        self.pipeline.set_book_settings(values)
        self._apply_direction()
        self.destroy()
        self.on_change()

    def _show(self, current: dict[str, Any]) -> None:
        """The fields as the book's own choices *current* have them (the series' default, else the reader's own,
        where it has none)."""
        for key, var in self.choices.items():
            var.set(bool(current.get(key, self._fallback(key))))
        self.scale_var.set(percent(current["text_scale"]) if "text_scale" in current else self.yours_scale)
        self.top_var.set(str(current["max_font_size"]) if "max_font_size" in current else "")
        self.problem.configure(text="")
        for key, var in self.vars.items():
            var.set(str(current[key]) if key in current else "")
        self.kept = {key: value for key, value in current.items() if key not in CHOICES and key not in SIZE_ROWS}
        self._sync_hints()

    def _clear(self) -> None:
        """Clear all: after the question, the book's choices go and the series' defaults, else the reader's own
        settings, apply; the dialog stays, with Undo."""
        current = self._current()
        series = bool(self.series_values)
        if not current:
            self.said_var.set(_(NOTHING_TO_CLEAR_SERIES if series else NOTHING_TO_CLEAR))
            return
        question = CLEAR_QUESTION_SERIES if series else CLEAR_QUESTION
        if not caches.ask(self, _(question).format(n=len(current)), _("Clear all"), _("Keep them"), no_first=True):
            return
        self.pipeline.set_book_settings({})
        self._cleared, self._removed_area = current, None
        self._show({})
        self.undo_btn.configure(state="normal")
        self.said_var.set(_(CLEARED_SERIES if series else CLEARED))
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
