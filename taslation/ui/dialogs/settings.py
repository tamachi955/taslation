"""The Settings dialog (Tools > Settings...): the settings a reader changes most, written into taslation.toml with the
file's notes and other lines kept (`config.write_settings`) and applied at once (`on_saved`, `App._settings_saved`);
an "Open settings file" button for all the others, which makes the file first where there is none (`config.
create_settings_file`, at the place the settings are read from: `config.settings_file`).

What it holds (`KEYS`): the lettering's smallest and largest size and the size under which a translation is listed
for review, the lettering size (`text_scale`, `TEXT_SCALES`; a book may have its own: `book_settings`), capitals,
slanted lettering; the window's text size (`ui_scale`, `ui.scaling`), always on top, how a book
starts (page by page or the whole book first, with what a store's terms make of that: `start.terms_note`); the two
optional page models (`detect_model`, `art_erase`), said for what they are: their licences as tagged, and that neither
says where its training images come from. The inpainting has three choices (`ERASE_CHOICES`: not used, only with a
GPU, always): "Only with a GPU" is the default, and where the rule (`artwork.runs_here`) finds no GPU on this computer
the row says it is not used here (`NO_GPU_TEXT`).

Three pages (a notebook): General, those settings; Shortcuts, the window's keys (`shortcuts_page.ShortcutsPage`
over `shortcuts.Keymap`, saved into the state folder with the same Save and applied at once by *on_keys*); System,
what each stage of a page runs on and the seconds a page there (`system_page.SystemPage`, looked at when first
shown).

Another part's setting is one line in `EXTRA_ROWS` (a `SettingRow`: a checkbox, or a list of choices), shown where
`Settings` has the key, written and applied like the others.

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

from ...config import LAMA_MODEL, LAYOUT_MODEL, ConfigError, Settings, create_settings_file, settings_file, write_settings
from ...i18n import _, load_ui_table, save_ui_entry
from ...render import artwork
from ..layout import place_window
from ..scaling import UI_SCALES, clamp_scale
from ..shortcuts import Keymap
from ..shortcuts import current as keys_in_force
from ..tooltip import tip
from .caches import ERROR_COLOUR, in_lines
from .shortcuts_page import ShortcutsPage
from .system_page import SystemPage
from .start import terms_note



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
    SettingRow("bubble_zoom", "Enlarge the bubble under the pointer",
               "In reading mode and the Reader role, a translated bubble the pointer rests on shows enlarged beside its original."),
    SettingRow("flash_when_done", "Flash the taskbar button when a whole-book run ends",
               "When a whole-book run finishes, or stops on a problem, while TASlation is not in front, its taskbar button flashes. TASlation does not take the focus."),
    SettingRow("sound_when_done", "Also play a sound when a whole-book run ends",
               "With the flash, the system's default sound plays once."),
)
FIELDS = frozenset(f.name for f in fields(Settings))


def shown_rows(rows: tuple[SettingRow, ...] = EXTRA_ROWS) -> tuple[SettingRow, ...]:
    """The rows of *rows* whose setting this version has (`Settings`' fields)."""
    return tuple(row for row in rows if row.key in FIELDS)


SHOWN_ROWS = shown_rows()
KEYS = ("min_font_size", "max_font_size", "readable_font_size", "text_scale", "uppercase", "slant_text", "ui_scale",
        "always_on_top", "scan_mode", "detect_model", "art_erase", *(row.key for row in SHOWN_ROWS))
SIZE_KEYS = ("min_font_size", "max_font_size", "readable_font_size")
# what changes the page: the page on show is lettered again (from the cache, nothing translated anew) once they are set
PAGE_SETTINGS = frozenset({*SIZE_KEYS, "text_scale", "uppercase", "slant_text", "detect_model", "art_erase",
                           *(row.key for row in SHOWN_ROWS if row.page)})
TEXT_SCALES = tuple(round(0.8 + 0.05 * i, 2) for i in range(11))  # the lettering sizes offered: 80 % to 130 %
SIZE_RANGE = (0, 200)  # what a size box steps through (the bounds are checked on Save: `size_problem`)
DETECT_CHOICES = (("off", "Not used"), ("auto", "Only with the inpainting"), ("on", "Always used"))
# art_erase's three values (`artwork.runs_here`): never; only where torch has a CUDA GPU (the default); always, the CPU too
ERASE_CHOICES = (("off", "Not used"), ("auto", "Only with a GPU"), ("lama", "Always, also on the CPU"))
TEXT_CHARS = 58  # the dialog's sentences are broken at so many "0" widths of its font: as many words at any scale
IGNORED_TABLE, IGNORED_ENTRY = "settings", "ignored"  # where ui.json keeps the unknown keys named last
PAGE_MODELS_TEXT = ("Two optional models: a layout model (comic-text-and-bubble-detector, tagged Apache-2.0) that "
                    "finds lettering on the drawing that the usual detection misses, and an inpainting model (LaMa, "
                    "MIT) that takes lettering out of the drawing. Neither says where its training images come from. "
                    "The inpainting is on by default where the computer has a GPU TASlation can use and its model is "
                    "installed; the layout model is off by default while it is measured on more books. TASlation "
                    "works without them.")
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


class SettingsDialog(tk.Toplevel):
    """The settings of `KEYS` for *settings* (the window's own object: what is saved is set on it by *on_saved*, the
    changed settings by name) on the General page, the window's keys over *keymap* (the one in force when None) on
    the Shortcuts page (saved, they go to *on_keys*), where the stages run on the System page (*pipeline* gives the
    window's pipeline, for its translator and its seconds a page), the file the settings are written to
    (`config.settings_file`) in a read-only line, Open settings file, Save and Close. ``message`` holds what the last Save or Open said. Not
    modal: the window goes on behind it."""

    def __init__(self, master: tk.Misc, settings: Settings, on_saved: Callable[[dict[str, Any]], None] | None = None,
                 keymap: Keymap | None = None, on_keys: Callable[[Keymap], None] | None = None,
                 pipeline: Callable[[], Any] | None = None):
        super().__init__(master)
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
        general = ttk.Frame(self.pages, padding=8)
        self.pages.add(general, text=_("General"))

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
        self.on_top = tk.BooleanVar(self, value=bool(settings.always_on_top))
        check = ttk.Checkbutton(window, text=_("Always on top"), variable=self.on_top)
        check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tip(_("Keep this window above the others."), check)
        name = ttk.Label(window, text=_("A book starts:"))
        name.grid(row=2, column=0, sticky="w", pady=(4, 0))
        modes = ttk.Frame(window)
        modes.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        self.mode = tk.StringVar(self, value="book" if settings.scan_mode == "book" else "page")
        for value, word in (("page", "Page by page"), ("book", "Whole book first")):
            ttk.Radiobutton(modes, text=_(word), value=value, variable=self.mode,
                            command=self._show_terms).pack(side="left", padx=(0, 8))
        tip(_("Page by page: each page is translated as you turn to it. Whole book first: TASlation reads the pages you turn, then translates the whole book."), name)
        self.terms_label = ttk.Label(window, justify="left")
        self.terms_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
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
            # (wide enough for the longest choice in the window's language: a box's width counts "0"s of its font)
            box = ttk.Combobox(models, textvariable=var, values=shown, state="readonly",
                               width=max(-(-tkfont.nametofont("TkDefaultFont").measure(s) // zero) for s in shown) + 2)
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

        self.keys = ShortcutsPage(self.pages, keymap if keymap is not None else keys_in_force(), self._say, self.text_width)
        self.pages.add(self.keys, text=_("Shortcuts"))
        self.system = SystemPage(self.pages, settings, self.text_width, pipeline=pipeline)
        self.pages.add(self.system, text=_("System"))
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
        self._show_terms()
        place_window(self, master)

    # ------------------------------------------------------------------ the fields
    def _page_shown(self, _event: Any = None) -> None:
        """A page came to the front: the System page looks the first time."""
        try:
            if self.pages.select() == str(self.system):
                self.system.shown()
        except tk.TclError:
            pass

    def _extra_rows(self, frame: ttk.LabelFrame, section: str, row: int) -> None:
        """The rows of `SHOWN_ROWS` in *section*, in *frame* from grid row *row* on (`self.extra`: their variables)."""
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
                                   width=max(len(s) for s in shown) + 2)
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

    def _show_terms(self) -> None:
        """Whole book first chosen: what a store's terms make of that mode, under the choice (as wherever it is
        chosen)."""
        text = in_lines(terms_note(), self.text_width) if self.mode.get() == "book" else ""
        self.terms_label.configure(text=text)
        if text:
            self.terms_label.grid()
        else:
            self.terms_label.grid_remove()

    def values(self) -> dict[str, Any]:
        """What the fields say, by setting; ValueError for a size that is no whole number."""
        out: dict[str, Any] = {key: int(var.get().strip()) for key, var in self.sizes.items()}
        out["text_scale"] = percent_of(self.text_scale.get())
        out["uppercase"] = bool(self.uppercase.get())
        out["slant_text"] = bool(self.slant.get())
        out["ui_scale"] = scale_of(self.scale.get())
        out["always_on_top"] = bool(self.on_top.get())
        out["scan_mode"] = self.mode.get()
        out["detect_model"] = self._value(DETECT_CHOICES, self.detect.get())
        out["art_erase"] = self._value(ERASE_CHOICES, self.erase.get())
        for spec in SHOWN_ROWS:
            var = self.extra[spec.key]
            out[spec.key] = self._value(spec.choices, var.get()) if spec.choices else bool(var.get())
        return out

    def changed(self) -> dict[str, Any]:
        """The fields that differ from the settings in force."""
        return {key: value for key, value in self.values().items() if getattr(self.settings, key) != value}

    def _say(self, text: str, error: bool = False) -> None:
        self.message_var.set(in_lines(text, self.text_width) if text else "")
        self.message_label.configure(foreground=ERROR_COLOUR if error else "")

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
            problem = size_problem(values["min_font_size"], values["max_font_size"], values["readable_font_size"])
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
