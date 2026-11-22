"""The Settings dialog (Tools > Settings...): the settings a reader changes most, written into taslation.toml with the
file's notes and other lines kept (`config.write_settings`) and applied at once (`on_saved`, `App._settings_saved`);
an "Open settings file" button for all the others, which makes the file first where there is none (`config.
create_settings_file`, at the place the settings are read from: `config.settings_file`).

What it holds (`KEYS`): the lettering's smallest and largest size and the size under which a translation is listed
for review, the lettering size (`text_scale`, `TEXT_SCALES`, 80-200 %; a book may have its own: `book_settings`), capitals,
slanted lettering; the window's text size (`ui_scale`, `ui.scaling`), its colours (`theme`, `ui.theme`: as Windows
is set, light or dark, said to wait while Windows' high contrast is on), always on top; the two optional page models
(`detect_model`, `art_erase`), said for what they are: their licences as tagged, and that neither says where its
training images come from. The inpainting has three choices (`ERASE_CHOICES`: not used, only with a
GPU, always): "Only with a GPU" is the default, and where the rule (`artwork.runs_here`) finds no GPU on this computer
the row says it is not used here (`NO_GPU_TEXT`). The layout model has three too (`DETECT_CHOICES`: not used, only
with the inpainting, always): "Only with the inpainting" is the default, so it goes where the inpainting goes. Save
writes only what was changed, so a choice never made is never written and a later default applies to it.

Three pages (a notebook): General, those settings; Shortcuts, the window's keys (`shortcuts_page.ShortcutsPage`
over `shortcuts.Keymap`, saved into the state folder with the same Save and applied at once by *on_keys*); System,
what each stage of a page runs on and the seconds a page there (`system_page.SystemPage`, looked at when first
shown), how many of the translation model's layers Ollama puts on the GPU (``ollama_num_gpu``), whether the window
loads that model at its start (``load_model_at_start``), where the OCR readers run (``ocr_runs_on``), the window
cache of the Ollama TASlation starts (``ollama_window_cache``) and whether the window looks for a new version at its
start (``update_check``), saved with the others. Each page scrolls where the whole dialog would be taller than the
screen leaves room for (`ScrolledPage`), so that Save and Close stay on the screen.

Another part's setting is one line in `EXTRA_ROWS` (a `SettingRow`: a checkbox, or a list of choices), shown where
`Settings` has the key, written and applied like the others. A whole number is one line in `NUMBER_ROWS` (a
`NumberRow`: a box with arrows, checked on Save): the panel's text size and the delay under the pointer
(``panel_font_size``, ``hover_delay_ms``), under the hover rows of the window section.

`warn_ignored`: the keys of the file this version does not know, named once in a box of the window's own (the names
only; the same names are not named again: ``ui.json``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, fields, replace
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from ...config import (
    HOVER_DELAY_RANGE,
    LAMA_MODEL,
    LAYOUT_MODEL,
    PANEL_FONT_RANGE,
    ConfigError,
    Settings,
    create_settings_file,
    settings_file,
    write_settings,
)
from ...i18n import _, load_ui_table, save_ui_entry
from ...render import artwork
from .. import theme
from ..layout import frame_extents, place_window, work_area
from ..scaling import UI_SCALES, clamp_scale
from ..shortcuts import Keymap
from ..shortcuts import current as keys_in_force
from ..tooltip import tip
from .caches import box_chars, in_lines
from .shortcuts_page import ShortcutsPage
from .system_page import SystemPage



@dataclass(frozen=True)
class SettingRow:
    """One more setting in the dialog (`EXTRA_ROWS`): the `Settings` field *key*; *label* and *tip* in English, keys
    of the window's catalogs (the 16 languages in a ``locales/features`` module, as every string of the window); in
    the *section* "lettering" or "window", under the rows there; a checkbox, or with *choices* ((value, label), ...)
    a list to choose from; *page*: a change letters the page on show again (`PAGE_SETTINGS`)."""

    key: str
    label: str
    tip: str = ""
    section: str = "window"
    choices: tuple[tuple[str, str], ...] = ()
    page: bool = False


# ---------------------------------------------------------------- other parts' settings: one line each
# A part's setting is added here in one line; nothing else in this file changes. It shows only where `Settings` has
# the key (a part not merged yet shows nothing), Save writes it into taslation.toml with the others and sets it on the
# window's settings at once (`App._settings_saved`), and the part reads ``settings.<key>`` whenever it acts. Its label
# and tip need the 16 languages (`locales/features/settings_dialog.py`; `tests/test_settings_rows.py` checks them).
EXTRA_ROWS: tuple[SettingRow, ...] = (
    SettingRow("hover_shows", "On the page:",
               "In the Reader role: the page translated, a bubble under the pointer showing its original; or the page as the viewer shows it, a bubble under the pointer showing its translation. Also in the View menu.",
               choices=(("original", "The translation (the original under the pointer)"),
                        ("translation", "The original (the translation under the pointer)"))),
    SettingRow("hover_reveal", "Under the pointer:",
               "How a bubble under the pointer shows the other side: in a panel beside it, both in sight at once; or in the bubble itself, with the original lettering, or what was read as text, erased and set. Also in the View menu.",
               choices=(("panel", "A panel beside the bubble"), ("in_place", "The bubble itself"))),
    SettingRow("bubble_zoom", "Enlarge the bubble under the pointer",
               "With the translation on the page (always so in the Translator role), a translated bubble the pointer rests on shows its original: enlarged beside it, or in its place (Under the pointer)."),
    SettingRow("side_indicator", "Pages turned past:",
               "Beside the page, on the side it turns to: the pages you turned past and how far TASlation is with each. A column of small thumbnails where the margin has room for it, and a narrow bar elsewhere; the narrow bar only; or nothing. A page whose words changed since you saw it gets a diamond, and when you turn back to it, its changed bubbles get corner brackets for a moment.",
               choices=(("column", "Thumbnails where there is room"), ("rail", "A narrow bar"), ("off", "Not shown"))),
    SettingRow("reuse_lines", "Reuse the translation of a short line seen before",
               "A short line already translated in this book or its series (a cry, a reply) gets the same translation again without asking the model: faster, and alike each time. A correction of yours comes first. The book's cache keeps a keyed hash of the line, never the Japanese."),
    SettingRow("size_emphasis", "Set larger what the original sets larger",
               "Where the original letters part of a bubble larger than the rest, that part is looked for in the translation (one or two short requests beside the page's; the words never change) and lettered larger too, where the bubble holds both sizes. Off: every translation at one size.",
               section="lettering", page=True),
)
FIELDS = frozenset(f.name for f in fields(Settings))


def shown_rows(rows: tuple[SettingRow, ...] = EXTRA_ROWS) -> tuple[SettingRow, ...]:
    """The rows of *rows* whose setting this version has (`Settings`' fields)."""
    return tuple(row for row in rows if row.key in FIELDS)


@dataclass(frozen=True)
class NumberRow:
    """A setting the dialog asks for as a whole number in a box (`NUMBER_ROWS`): the `Settings` field *key*; *label*
    and *tip* in English (the 16 languages in `locales/features/panel_size.py`); *bounds* (lowest, highest) and, with
    *zero*, 0 besides (automatic), checked on Save (`number_problem`, which *problem* says them in); *step*: the box's
    arrows; in *section*, right under the row of the setting *after* (at the section's end where that row is not
    shown)."""

    key: str
    label: str
    tip: str
    bounds: tuple[int, int]
    problem: str
    zero: bool = False
    step: int = 1
    section: str = "window"
    after: str = "bubble_zoom"

    def fits(self, value: Any) -> bool:
        """Whether *value* is a whole number this row takes."""
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        return (self.zero and value == 0) or self.bounds[0] <= value <= self.bounds[1]


# the panel beside a bubble under the pointer (`ui.zoom`), under the rows of how a bubble shows its other side
NUMBER_ROWS: tuple[NumberRow, ...] = (
    NumberRow("panel_font_size", "Panel text size (points, 0: automatic):",
              "The size of the text in the panel beside a bubble under the pointer, in points. It grows with the window's text size and the monitor's scaling, and the panel always stays on the screen. 0: automatic (about twice the review size).",
              PANEL_FONT_RANGE, "The panel text size: 0 (automatic) or a whole number from {low} to {high} points.",
              zero=True),
    NumberRow("hover_delay_ms", "Delay under the pointer (milliseconds):",
              "How long the pointer rests on a bubble before its other side shows: this long on a bubble that is hard to read and on every bubble while the original is on the page, about 2.7 times as long on the others. 450: 0.45 and 1.2 seconds. 0: at once.",
              HOVER_DELAY_RANGE, "The delay under the pointer: a whole number from {low} to {high} milliseconds.",
              step=50),
)


def number_problem(row: NumberRow, value: Any) -> str | None:
    """What is wrong with *value* for the number row *row* (in the window's language), None when nothing is."""
    return None if row.fits(value) else _(row.problem).format(low=row.bounds[0], high=row.bounds[1])


def whole_number(text: str) -> int | str:
    """A number box's text as a whole number; the text itself when it is none (`number_problem` says so on Save)."""
    try:
        return int(str(text).strip())
    except ValueError:
        return str(text).strip()


SHOWN_ROWS = shown_rows()
SHOWN_NUMBERS = tuple(row for row in NUMBER_ROWS if row.key in FIELDS)
# (ollama_num_gpu, load_model_at_start, ocr_runs_on, ollama_window_cache and update_check: on the System page,
# `system_page.SystemPage.num_gpu`, `load_at_start`, `ocr_runs_on`, `window_cache` and `update_check`)
KEYS = ("min_font_size", "max_font_size", "readable_font_size", "text_scale", "uppercase", "slant_text", "ui_scale",
        "theme", "always_on_top", "detect_model", "art_erase", *(row.key for row in SHOWN_ROWS),
        *(row.key for row in SHOWN_NUMBERS), "ollama_num_gpu", "load_model_at_start", "ocr_runs_on",
        "ollama_window_cache", "update_check")
SIZE_KEYS = ("min_font_size", "max_font_size", "readable_font_size")
# what changes the page: the page on show is lettered again (from the cache, nothing translated anew) once they are set
PAGE_SETTINGS = frozenset({*SIZE_KEYS, "text_scale", "uppercase", "slant_text", "detect_model", "art_erase",
                           *(row.key for row in SHOWN_ROWS if row.page)})
# the lettering sizes offered: 80 % to 130 % by 5, then on to 200 % by 10 (`config.TEXT_SCALE_RANGE`)
TEXT_SCALES = (*(round(0.8 + 0.05 * i, 2) for i in range(11)), *(round(1.4 + 0.1 * i, 2) for i in range(7)))
SIZE_RANGE = (0, 200)  # what a size box steps through (the bounds are checked on Save: `size_problem`)
DETECT_CHOICES = (("off", "Not used"), ("auto", "Only with the inpainting"), ("on", "Always used"))
# art_erase's three values (`artwork.runs_here`): never; only where torch has a CUDA GPU (the default); always, the CPU too
ERASE_CHOICES = (("off", "Not used"), ("auto", "Only with a GPU"), ("lama", "Always, also on the CPU"))
# the window's colours (`theme`: applied at once by `App._settings_saved`); the words: `locales/features/window_theme.py`
THEME_CHOICES = (("system", "As Windows is set"), ("light", "Light"), ("dark", "Dark"))
THEME_TIP = ("The window's colours: light, dark, or as Windows has them for apps (the app mode in Windows' colour "
             "settings). The page keeps its own. While Windows' high contrast is on, the window takes Windows' colours.")
CONTRAST_TEXT = "Windows' high contrast is on: the window takes Windows' colours."
TEXT_CHARS = 58  # the dialog's sentences are broken at so many "0" widths of its font: as many words at any scale
PAGE_LEAST = 160  # the least height a page keeps on a screen too low for the rest of the dialog (pixels)
IGNORED_TABLE, IGNORED_ENTRY = "settings", "ignored"  # where ui.json keeps the unknown keys named last
PAGE_MODELS_TEXT = ("Two optional models: a layout model (comic-text-and-bubble-detector, tagged Apache-2.0) that "
                    "finds lettering on the drawing that the usual detection misses, and an inpainting model (LaMa, "
                    "MIT) that takes lettering out of the drawing. Neither says where its training images come from. "
                    "Both are on by default where the computer has a GPU TASlation can use and they are installed; "
                    "the layout model is used only together with the inpainting. TASlation works without them.")
NO_GPU_TEXT = "Not used on this computer: it has no GPU that TASlation can use (NVIDIA, with CUDA)."


def scale_label(scale: float) -> str:
    """A UI scale as the Text size box shows it: "125 %"."""
    return f"{round(clamp_scale(scale) * 100)} %"


def scale_of(label: str) -> float:
    """The UI scale a Text size entry stands for ("125 %" -> 1.25); ValueError for what is none."""
    return clamp_scale(float(label.replace("%", "").strip()) / 100.0)


def text_scale_choices(current: float) -> list[str]:
    """The lettering sizes a box offers (`TEXT_SCALES`), with *current* among them where the file has another."""
    shown = [percent(s) for s in TEXT_SCALES]
    if percent(current) not in shown:
        shown = sorted(set(shown) | {percent(current)}, key=percent_of)
    return shown


def percent(scale: float) -> str:
    """A lettering size as its box shows it: "90 %"."""
    return f"{round(float(scale) * 100)} %"


def percent_of(label: str) -> float:
    """The lettering size a box entry stands for ("90 %" -> 0.9); ValueError for what is none."""
    return round(float(label.replace("%", "").strip()) / 100.0, 4)


def size_problem(low: int, high: int, readable: int) -> str | None:
    """What is wrong with the three lettering sizes (in the window's language), None when nothing is: as
    `Settings.validate` checks them."""
    if low < 4 or high < low or (readable and not low <= readable <= high) or readable < 0:
        return _("The sizes do not fit together: the smallest at least 4, the largest at least the smallest, and the review size 0 or between the two.")
    return None


def page_models_installed(models_dir: Path | str) -> bool:
    """Whether both optional page models are in the models folder (nothing is imported for it)."""
    return not LAYOUT_MODEL.missing(Path(models_dir)) and not LAMA_MODEL.missing(Path(models_dir))


def open_in_editor(path: Path) -> None:
    """*path* opened with the program Windows has for it, else with Notepad (a .toml file often has none)."""
    if sys.platform == "win32":
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        except OSError:
            pass
        subprocess.Popen(["notepad.exe", str(path)])
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])


class ScrolledPage(ttk.Frame):
    """A page of the dialog's notebook: its content (`hold`, made with ``canvas`` as its master so that the canvas
    cuts it off) as tall as it is, or as tall as ``limit`` with a bar at the side for the rest (`fit`, again whenever
    the content's size changes). `SettingsDialog._fit` sets the limit from the screen's height."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        background = ttk.Style(self).lookup("TFrame", "background") or self.winfo_toplevel().cget("background")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=background,
                                yscrollincrement=tkfont.nametofont("TkDefaultFont").metrics("linespace"))
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.limit: int | None = None
        self.content: tk.Misc | None = None

    def hold(self, content: tk.Misc) -> None:
        self.content = content
        self.canvas.create_window(0, 0, window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: self.fit(), add="+")
        self.fit()

    def scrolls(self) -> bool:
        """Whether part of the content is out of sight (the bar shows)."""
        return bool(self.bar.winfo_manager())

    def fit(self) -> None:
        if self.content is None:
            return
        try:
            width, height = self.content.winfo_reqwidth(), self.content.winfo_reqheight()
            shown = height if self.limit is None else min(height, self.limit)
            self.canvas.configure(width=width, height=shown, scrollregion=(0, 0, width, height))
            if shown < height:
                if not self.scrolls():
                    self.bar.pack(side="right", fill="y")
            elif self.scrolls():
                self.bar.pack_forget()
                self.canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def show(self, widget: tk.Misc) -> None:
        """*widget* (in the content, on the screen) scrolled into sight with a line of room around it, as when the
        keyboard goes to it."""
        if self.content is None or not self.scrolls():
            return
        try:
            room = int(self.canvas.winfo_fpixels(self.canvas.cget("yscrollincrement")))
            top = widget.winfo_rooty() - self.content.winfo_rooty() - room
            bottom = top + widget.winfo_height() + 2 * room
            seen, height = int(self.canvas.canvasy(0)), max(1, self.content.winfo_reqheight())
            if top < seen:
                self.canvas.yview_moveto(max(0, top) / height)
            elif bottom > seen + self.canvas.winfo_height():
                self.canvas.yview_moveto((bottom - self.canvas.winfo_height()) / height)
        except tk.TclError:
            pass


class SettingsDialog(tk.Toplevel):
    """The settings of `KEYS` for *settings* (the window's own object: what is saved is set on it by *on_saved*, the
    changed settings by name) on the General page, the window's keys over *keymap* (the one in force when None) on
    the Shortcuts page (saved, they go to *on_keys*), where the stages run on the System page (*pipeline* gives the
    window's pipeline, for its translator and its seconds a page), the file the settings are written to
    (`config.settings_file`) in a read-only line, Open settings file, Save and Close. ``message`` holds what the last Save or Open said. Not
    modal: the window goes on behind it. Where the whole dialog would be taller than the screen's work area under
    the window, the pages scroll (`ScrolledPage`, `_fit`), so that the buttons stay on the screen."""

    def __init__(self, master: tk.Misc, settings: Settings, on_saved: Callable[[dict[str, Any]], None] | None = None,
                 keymap: Keymap | None = None, on_keys: Callable[[Keymap], None] | None = None,
                 pipeline: Callable[[], Any] | None = None):
        super().__init__(master)
        self.withdraw()  # measured and placed before it first shows
        self._room = self._others = 0  # (`_fit`)
        self.settings = settings
        self.on_saved = on_saved
        self.on_keys = on_keys
        self.path = settings_file(settings)
        self.title(_("Settings"))
        self.transient(master)
        self.resizable(False, False)
        zero = max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.text_width = TEXT_CHARS * zero
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        self.pages = ttk.Notebook(frm)
        self.pages.pack(fill="both", expand=True)
        self.general_tab, self.keys_tab, self.system_tab = (ScrolledPage(self.pages) for _i in range(3))
        general = ttk.Frame(self.general_tab.canvas, padding=8)
        self.pages.add(self.general_tab, text=_("General"))

        letters = ttk.LabelFrame(general, text=_("Lettering"), padding=8)
        letters.pack(fill="x")
        self.sizes: dict[str, tk.StringVar] = {}
        for row, (key, label, hint) in enumerate((
                ("min_font_size", "Smallest size (pixels):", "The translation is lettered as large as its bubble allows, between these two sizes."),
                ("max_font_size", "Largest size (pixels):", "The translation is lettered as large as its bubble allows, between these two sizes."),
                ("readable_font_size", "List for review below (pixels, 0: never):", "A translation lettered smaller than this is listed for a second look (Review)."))):
            name = ttk.Label(letters, text=_(label))
            name.grid(row=row, column=0, sticky="w", pady=1)
            var = tk.StringVar(self, value=str(getattr(settings, key)))
            box = ttk.Spinbox(letters, from_=SIZE_RANGE[0], to=SIZE_RANGE[1], textvariable=var, width=5)
            box.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=1)
            tip(_(hint), name, box)
            self.sizes[key] = var
        name = ttk.Label(letters, text=_("Lettering size:"))
        name.grid(row=3, column=0, sticky="w", pady=1)
        self.text_scale = tk.StringVar(self, value=percent(settings.text_scale))
        box = ttk.Combobox(letters, textvariable=self.text_scale, values=text_scale_choices(settings.text_scale),
                           state="readonly", width=7)
        box.grid(row=3, column=1, sticky="w", padx=(8, 0), pady=1)
        tip(_("Every translation lettered smaller or larger by so much (100 %: as large as its bubble allows), never past its bubble or the largest size. A book can have its own: Book settings... in translator mode."), name, box)
        self.uppercase = tk.BooleanVar(self, value=bool(settings.uppercase))
        check = ttk.Checkbutton(letters, text=_("Capital letters"), variable=self.uppercase)
        check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tip(_("Letter the translations in capitals, as many comics in English are."), check)
        self.slant = tk.BooleanVar(self, value=bool(settings.slant_text))
        check = ttk.Checkbutton(letters, text=_("Slanted lettering: read upright and lettered at its slant"),
                                variable=self.slant)
        check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 0))
        tip(_("Lettering set at a slant is turned upright to be read, and the translation is lettered at the same slant. Off: everything upright."), check)
        self.extra: dict[str, tk.Variable] = {}
        self.numbers: dict[str, tk.StringVar] = {}  # (the boxes of `SHOWN_NUMBERS`)
        self._extra_rows(letters, "lettering", 6)

        window = ttk.LabelFrame(general, text=_("The window"), padding=8)
        window.pack(fill="x", pady=(10, 0))
        name = ttk.Label(window, text=_("Text size:"))
        name.grid(row=0, column=0, sticky="w")
        scales = [scale_label(s) for s in UI_SCALES]
        current = scale_label(settings.ui_scale)
        if current not in scales:
            scales = sorted(set(scales) | {current}, key=scale_of)
        self.scale = tk.StringVar(self, value=current)
        box = ttk.Combobox(window, textvariable=self.scale, values=scales, state="readonly", width=7)
        box.grid(row=0, column=1, sticky="w", padx=(8, 0))
        tip(_("The size of this window's text, times what Windows sets for the monitor (100 %: as Windows has it)."), name, box)
        name = ttk.Label(window, text=_("Colours:"))
        name.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.colours_var = tk.StringVar(self, value=self._shown(THEME_CHOICES, getattr(settings, "theme", "system")))
        shown = [_(label) for _value, label in THEME_CHOICES]
        box = ttk.Combobox(window, textvariable=self.colours_var, values=shown, state="readonly",
                           width=box_chars(shown))
        box.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        tip(_(THEME_TIP), name, box)
        if theme.high_contrast():  # the choice waits while Windows' high contrast is on (`theme.effective`)
            ttk.Label(window, text=in_lines(_(CONTRAST_TEXT), self.text_width), justify="left").grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.on_top = tk.BooleanVar(self, value=bool(settings.always_on_top))
        check = ttk.Checkbutton(window, text=_("Always on top"), variable=self.on_top)
        check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tip(_("Keep this window above the others."), check)
        self._extra_rows(window, "window", 4)

        models = ttk.LabelFrame(general, text=_("Optional page models"), padding=8)
        models.pack(fill="x", pady=(10, 0))
        ttk.Label(models, text=in_lines(_(PAGE_MODELS_TEXT), self.text_width), justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.detect = tk.StringVar(self, value=self._shown(DETECT_CHOICES, settings.detect_model))
        self.erase = tk.StringVar(self, value=self._shown(ERASE_CHOICES, settings.art_erase))
        for row, (word, var, choices) in enumerate((("Layout model:", self.detect, DETECT_CHOICES),
                                                    ("Inpainting:", self.erase, ERASE_CHOICES)), start=1):
            ttk.Label(models, text=_(word)).grid(row=row, column=0, sticky="w", pady=(4, 0))
            shown = [_(label) for _value, label in choices]
            box = ttk.Combobox(models, textvariable=var, values=shown, state="readonly", width=box_chars(shown))
            box.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        self.gpu_label = ttk.Label(models, text=in_lines(_(NO_GPU_TEXT), self.text_width), justify="left")
        self.gpu_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.erase.trace_add("write", lambda *_a: self._show_gpu_line())
        self._show_gpu_line()
        installed = page_models_installed(settings.models_dir)
        self.models_line = (_("Installed on this computer.") if installed else
                            _("Not installed on this computer: run install.cmd again and agree to them."))
        ttk.Label(models, text=in_lines(self.models_line, self.text_width), justify="left").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.general_tab.hold(general)
        self.keys = ShortcutsPage(self.keys_tab.canvas, keymap if keymap is not None else keys_in_force(), self._say,
                                  self.text_width)
        self.keys_tab.hold(self.keys)
        self.pages.add(self.keys_tab, text=_("Shortcuts"))
        self.system = SystemPage(self.system_tab.canvas, settings, self.text_width, pipeline=pipeline)
        self.system_tab.hold(self.system)
        self.pages.add(self.system_tab, text=_("System"))
        self.pages.bind("<<NotebookTabChanged>>", self._page_shown)

        where = ttk.Frame(frm)
        where.pack(fill="x", pady=(10, 0))
        ttk.Label(where, text=_("Settings file:")).pack(anchor="w")
        self.path_field = ttk.Entry(where, width=TEXT_CHARS)
        self.path_field.insert(0, str(self.path))
        self.path_field.configure(state="readonly")
        self.path_field.pack(fill="x", pady=(2, 0))

        self.message_var = tk.StringVar(self, value="")
        self.message_label = ttk.Label(frm, textvariable=self.message_var, justify="left")
        self.message_label.pack(anchor="w", fill="x", pady=(8, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        self.open_btn = ttk.Button(btns, text=_("Open settings file"), command=self.open_file)
        self.open_btn.pack(side="left")
        tip(_("Open the file with every setting in your text editor (it is made first when there is none). Changes made there apply at the next start."), self.open_btn)
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")
        self.save_btn = ttk.Button(btns, text=_("Save"), command=self.save, default="active")
        self.save_btn.pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<MouseWheel>", self._wheel, add="+")
        self.bind("<FocusIn>", self._focus_shown, add="+")
        self._fit(master)
        place_window(self, master)
        if master.winfo_viewable():  # (a window not on the screen, as the tests' root: it stays out of sight)
            self.deiconify()

    # ------------------------------------------------------------------ the pages' height
    def _fit(self, master: tk.Misc) -> None:
        """How tall the pages may be (`ScrolledPage.limit`): what the work area of the monitor under *master* (where
        `place_window` puts the dialog, or the primary one) leaves once the title bar, the border and the rest of the
        dialog are counted. The message line is counted as it is (`_limit_pages`, again whenever it changes)."""
        try:
            self.update_idletasks()
            if master.winfo_viewable():
                _left, top, _right, bottom = work_area(self, master.winfo_rootx() + master.winfo_width() // 2,
                                                       master.winfo_rooty() + master.winfo_height() // 2)
            else:
                _left, top, _right, bottom = work_area(self)
            border, caption = frame_extents()
            self._room = bottom - top - caption - border
            tallest = max(page.canvas.winfo_reqheight() for page in self.scrolled_pages())
            self._others = self.winfo_reqheight() - tallest - self.message_label.winfo_reqheight()
        except tk.TclError:
            return
        self._limit_pages()

    def _limit_pages(self) -> None:
        if not self._room:
            return
        limit = max(PAGE_LEAST, self._room - self._others - self.message_label.winfo_reqheight())
        for page in self.scrolled_pages():
            page.limit = limit
            page.fit()

    def scrolled_pages(self) -> tuple[ScrolledPage, ...]:
        return self.general_tab, self.keys_tab, self.system_tab

    def _wheel(self, event: tk.Event) -> None:
        """The mouse wheel anywhere over the dialog scrolls the page in front where it scrolls; not over a box, a list
        or a bar, which take the wheel themselves."""
        widget = event.widget
        try:
            if isinstance(widget, tk.Misc) and widget.bind_class(widget.winfo_class(), "<MouseWheel>"):
                return
            page = self.nametowidget(self.pages.select())
        except (tk.TclError, KeyError):
            return
        if isinstance(page, ScrolledPage) and page.scrolls() and event.delta:
            steps = max(1, abs(int(event.delta)) // 40)  # (three lines a notch, as Windows has it)
            page.canvas.yview_scroll(-steps if event.delta > 0 else steps, "units")

    def _focus_shown(self, event: tk.Event) -> None:
        """A field the keyboard goes to on a page that scrolls is scrolled into sight."""
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return
        for page in self.scrolled_pages():
            if page.content is not None and str(widget).startswith(str(page.content) + "."):
                page.show(widget)

    # ------------------------------------------------------------------ the fields
    def _page_shown(self, _event: Any = None) -> None:
        """A page came to the front: the System page looks the first time."""
        try:
            if self.pages.select() == str(self.system_tab):
                self.system.shown()
        except tk.TclError:
            pass

    def _extra_rows(self, frame: ttk.LabelFrame, section: str, row: int) -> None:
        """The rows of `SHOWN_ROWS` in *section*, in *frame* from grid row *row* on (`self.extra`: their variables),
        each number row of the section (`SHOWN_NUMBERS`) under the row it goes after, else at the end."""
        numbers = [spec for spec in SHOWN_NUMBERS if spec.section == section]
        for spec in SHOWN_ROWS:
            if spec.section != section:
                continue
            value = getattr(self.settings, spec.key)
            var: tk.Variable
            if spec.choices:
                name = ttk.Label(frame, text=_(spec.label))
                name.grid(row=row, column=0, sticky="w", pady=(4, 0))
                var = tk.StringVar(self, value=self._shown(spec.choices, value))
                shown = [_(label) for _value, label in spec.choices]
                box = ttk.Combobox(frame, textvariable=var, values=shown, state="readonly",
                                   width=box_chars(shown))
                box.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
                widgets: tuple[tk.Misc, ...] = (name, box)
            else:
                var = tk.BooleanVar(self, value=bool(value))
                check = ttk.Checkbutton(frame, text=_(spec.label), variable=var)
                check.grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
                widgets = (check,)
            if spec.tip:
                tip(_(spec.tip), *widgets)
            self.extra[spec.key] = var
            row += 1
            for number in [n for n in numbers if n.after == spec.key]:
                numbers.remove(number)
                self._number_row(frame, number, row)
                row += 1
        for number in numbers:
            self._number_row(frame, number, row)
            row += 1

    def _number_row(self, frame: ttk.LabelFrame, spec: NumberRow, row: int) -> None:
        """The number row *spec* in *frame* at grid row *row*: its label and a box with arrows (`self.numbers`)."""
        name = ttk.Label(frame, text=_(spec.label))
        name.grid(row=row, column=0, sticky="w", pady=(4, 0))
        var = tk.StringVar(self, value=str(getattr(self.settings, spec.key)))
        low, high = spec.bounds
        if spec.zero:  # (0 and then the bounds: the arrows skip what Save would refuse)
            box = ttk.Spinbox(frame, values=(0, *range(low, high + 1, spec.step)), textvariable=var, width=6)
        else:
            box = ttk.Spinbox(frame, from_=low, to=high, increment=spec.step, textvariable=var, width=6)
        var.set(str(getattr(self.settings, spec.key)))  # (as the file has it, also where the arrows do not stop)
        box.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        tip(_(spec.tip), name, box)
        self.numbers[spec.key] = var

    @staticmethod
    def _shown(choices: tuple[tuple[str, str], ...], value: str) -> str:
        return next((_(label) for v, label in choices if v == value), _(choices[0][1]))

    @staticmethod
    def _value(choices: tuple[tuple[str, str], ...], shown: str) -> str:
        return next((v for v, label in choices if _(label) == shown), choices[0][0])

    def gpu_line_shown(self) -> bool:
        """Whether the Inpainting row says that it is not used on this computer: "Only with a GPU" is chosen and the
        rule (`artwork.runs_here`) finds no GPU here, as the System page counts one (torch asked once, and only now)."""
        return self._value(ERASE_CHOICES, self.erase.get()) == "auto" and not artwork.runs_here("auto")

    def _show_gpu_line(self) -> None:
        if self.gpu_line_shown():
            self.gpu_label.grid()
        else:
            self.gpu_label.grid_remove()

    def values(self) -> dict[str, Any]:
        """What the fields say, by setting; ValueError for a size that is no whole number."""
        out: dict[str, Any] = {key: int(var.get().strip()) for key, var in self.sizes.items()}
        out["text_scale"] = percent_of(self.text_scale.get())
        out["uppercase"] = bool(self.uppercase.get())
        out["slant_text"] = bool(self.slant.get())
        out["ui_scale"] = scale_of(self.scale.get())
        out["theme"] = self._value(THEME_CHOICES, self.colours_var.get())
        out["always_on_top"] = bool(self.on_top.get())
        out["detect_model"] = self._value(DETECT_CHOICES, self.detect.get())
        out["art_erase"] = self._value(ERASE_CHOICES, self.erase.get())
        for spec in SHOWN_ROWS:
            var = self.extra[spec.key]
            out[spec.key] = self._value(spec.choices, var.get()) if spec.choices else bool(var.get())
        for spec in SHOWN_NUMBERS:  # (as typed when it is no whole number: `number_problem` says so on Save)
            out[spec.key] = whole_number(self.numbers[spec.key].get())
        out["ollama_num_gpu"] = self.system.num_gpu_value()  # (the System page's box, as typed when it is none)
        out["load_model_at_start"] = bool(self.system.load_at_start.get())
        out["ocr_runs_on"] = self.system.ocr_runs_on_value()
        out["ollama_window_cache"] = self.system.window_cache_value()
        out["update_check"] = self.system.update_check_value()
        return out

    def number_problem(self, values: dict[str, Any]) -> str | None:
        """What is wrong with the number boxes' *values* (`number_problem`), the first one; None when nothing is."""
        return next((p for p in (number_problem(spec, values.get(spec.key)) for spec in SHOWN_NUMBERS) if p), None)

    def changed(self) -> dict[str, Any]:
        """The fields that differ from the settings in force."""
        return {key: value for key, value in self.values().items() if getattr(self.settings, key) != value}

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(in_lines(text, self.text_width) if text else "")
        self.message_label.configure(foreground=theme.colour("error") if error else "")
        self._limit_pages()  # (a longer message: the pages give it room, so that the buttons stay on the screen)

    # ------------------------------------------------------------------ Save and Open
    def save(self) -> bool:
        """The changed fields written into the settings file and handed to *on_saved*; what happened in the message
        line. Whether they were saved (nothing to save counts)."""
        problem = None
        try:
            values = self.values()
        except ValueError:
            problem = size_problem(-1, -1, -1)
        else:
            problem = (size_problem(values["min_font_size"], values["max_font_size"], values["readable_font_size"])
                       or self.number_problem(values) or self.system.num_gpu_problem())
        if problem:
            self._say(problem, error=True)
            return False
        changed = {key: value for key, value in values.items() if getattr(self.settings, key) != value}
        if not changed and not self.keys.changed:
            self._say(_("Nothing changed."))
            return True
        try:
            if changed:
                replace(self.settings, **changed).validate()
                write_settings(self.path, changed)
            if self.keys.changed:
                self.keys.keymap.save(self.settings.state_dir)
        except (ConfigError, OSError) as e:
            why = getattr(e, "strerror", None) or str(e)
            self._say(_("Not saved: {error}").format(error=why), error=True)
            return False
        if changed and self.on_saved is not None:
            self.on_saved(dict(changed))
        if self.keys.changed:
            self.keys.saved_now()
            if self.on_keys is not None:
                self.on_keys(self.keys.keymap)
        text = _("Saved. The changes apply now.")
        if "ui_scale" in changed:
            text += " " + _("The new text size shows in full after a restart.")
        self._say(text)
        return True

    def open_file(self) -> Path | None:
        """The settings file in the reader's editor, made from the example first when there is none; the file, None
        when it could not be made or opened (said in the message line)."""
        try:
            made = create_settings_file(self.path)
            open_in_editor(self.path)
        except OSError as e:
            self._say(_("Could not open the file: {error}").format(error=e.strerror or type(e).__name__), error=True)
            return None
        self._say(_("The file was made: every setting in it is a note until you delete its \"#\".") if made
                  else _("Changes made in the file apply at the next start."))
        return self.path


def ignored_note(settings: Settings) -> str | None:
    """What the window says of the keys in the settings file this version does not know (by name only), or None."""
    names = tuple(getattr(settings, "ignored_keys", ()) or ())
    if not names:
        return None
    return _("TASlation does not know these settings in taslation.toml and leaves them out: {names}. Tools > Settings... opens the file.").format(
        names=", ".join(names))


def warn_ignored(master: tk.Misc, settings: Settings, tell: Callable[..., Any]) -> bool:
    """The unknown keys of the settings file named once (`ignored_note`) with *tell* (`caches.tell`, not waited for);
    the same names are not named again on later starts (``ui.json``). Whether it was said."""
    note = ignored_note(settings)
    if note is None:
        return False
    state = Path(settings.state_dir)
    names = ",".join(settings.ignored_keys)
    if load_ui_table(state, IGNORED_TABLE).get(IGNORED_ENTRY) == names:
        return False
    tell(master, note, icon="info", wait=False)
    save_ui_entry(state, IGNORED_TABLE, IGNORED_ENTRY, names)
    return True
