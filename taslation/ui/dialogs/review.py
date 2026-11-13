"""Translator mode's dialogs on the page's regions: the list of those worth a look (`ReviewDialog`, `review_rows`)
and the region editor (`EditBubbleDialog`), whose formatting bar sets a region's lettering as a word processor's text
box does: bold and italic, the font family and size, the alignment, the line and letter spacing, the slant, the text
direction, the text colour and the outline (`InkChoice`); the page behind it
shows each change a moment later. The editor shows the region as the page has it (a crop of the frame in memory,
never written anywhere), reads its Japanese again on demand where the page came from the cache (which keeps none),
goes to the region before or after it in reading order, and asks before it drops what was typed."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, ttk
from typing import Any, Callable

from PIL import Image, ImageTk

from ...annotations import (ALIGNS, DIRECTIONS, ERASE_ONLY, INK_NAMES, LETTER_SPACINGS, REGION_KINDS, SLANTS,
                             STYLE_SIZES, VALIGNS, RegionStyle, ink_code)
from ...i18n import _
from ...regions import ERASED
from ...review import reason_label
from .. import shortcuts
from ..layout import FlowBar, fit_combobox, place_window, wrap_label
from ..font_memory import StarButton, font_choices
from ..progress import status_word
from ..tooltip import tip
from . import caches
from .help import explain_button

# The kinds of text a region holds, as the editor's Kind list names them (the annotations keep the codes).
REGION_KIND_WORDS = {"": "(not set)", "speech": "Speech", "thought": "Thought", "shout": "Shout",
                     "narration": "Narration", "sfx": "Sound effect", "handwritten": "Handwritten",
                     ERASE_ONLY: "Erase only"}  # (erase only: the lettering is erased and nothing is set there)
ERASE_ONLY_TIP = ("Erase only: the lettering is erased and nothing is set in its place; the region is not translated "
                  "and not counted as untranslated.")
ASKING = {"again": "Asking the model for a new translation..."}
FLASH = "#fff4bf"  # the translation box, for a moment, when the model's new translation is put in it
FLASH_MS = 1200
# the formatting bar
PREVIEW_MS = 300  # after the last change in the editor, this long until the page behind it shows the region again
FACE_TIPS = {"bold": "Set this text in bold.", "italic": "Set this text in italic."}
SLANT_TIP = ("How far the lines are turned, in degrees counter-clockwise. Auto keeps the slant of the original lettering; "
             "0 sets them straight.")
AUTO = "Auto"  # B and I as the series sheet says, the size that fits, the line spacing of the settings
# the text direction, in a word processor's words ("": Auto, across)
DIRECTION_WORDS = {"": AUTO, "horizontal": "Horizontal", "down": "Rotate all text 90°", "up": "Rotate all text 270°",
                   "stacked": "Stacked"}
DIRECTION_TIP = ("Which way the lines run. Horizontal: across. Rotate all text 90°: turned to read from the top down, "
                 "as an English book's spine. Rotate all text 270°: turned to read from the bottom up. Stacked: "
                 "vertical writing, the letters one below the other in columns from right to left. Auto: across.")
AUTOMATIC_FONT = "(automatic)"  # the font list's first entry: the lettering the series sheet gives the region's kind
# the ink: the text colour and the outline's, each Auto, black, white or a colour of the reader's (`InkChoice`), and
# the outline Auto, on or off; the region's own Auto is its kind's in the series sheet, else the automatic one
INK_WORDS = {"": AUTO, "black": "Black", "white": "White"}
CUSTOM_INK = "Custom..."
CHOOSE_INK = "Choose a colour"
OUTLINE_WORDS = {None: AUTO, True: "With outline", False: "No outline"}
INK_TIPS = {"colour": "The colour of the letters. Auto: as the series sheet says for this kind of text, else black or "
                      "white to suit the ground.",
            "outline": "A rim round the letters. Auto: as the series sheet says for this kind of text, else only on a "
                       "drawing or a tone.",
            "outline_colour": "The colour of the rim. Auto: as the series sheet says for this kind of text, else the "
                              "opposite of the letters."}
# the formatting copied (Ctrl+Shift+C) and pasted (Ctrl+Shift+V) as a word processor's, shared with the window's
# Page menu (`formats.FormatClip`)
FORMAT_TIPS = {"copy": "Copy the formatting on this bar (Ctrl+Shift+C), to paste it on another region.",
               "paste": "Put the formatting copied last on this bar (Ctrl+Shift+V); Save keeps it."}
ALIGN_WORDS = {"left": "Left", "center": "Centre", "right": "Right"}
VALIGN_WORDS = {"top": "Top", "middle": "Middle", "bottom": "Bottom"}
LINE_SPACING_STEPS = ("0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.75", "2.0", "2.5", "3.0")
# what the lettering could not do as formatted: the line under the bar ({font}: the family asked for) ...
FIT_LINES = {"no-fit": "The text does not fit at this size: it runs to the edge of the bubble and is cut off there.",
             "font-missing": "The font \"{font}\" is not installed on this computer: the automatic font is used instead.",
             "font-glyphs": "The font \"{font}\" has no letters for this text: the automatic font is used instead."}
# ... and the review list's reasons
FIT_REASONS = {"no-fit": "text does not fit", "font-missing": "font not installed", "font-glyphs": "font lacks these letters"}
FIT_COLOUR = "#c03030"
# the region as the page has it, at the top of the editor: at most this many pixels across and down, enlarged at most so
CROP_ROOM, CROP_ENLARGE = (460, 200), 2.0
READING = "Reading the Japanese..."
NOT_READ = {"none": "No Japanese was read in this region.",
            "no-ocr": "The reading model is not loaded yet. Try again in a moment."}
# the editor's way to the region before (-1) or after (+1) it in reading order, and its key
STEP_WORDS = {-1: "Previous", 1: "Next"}  # named with their keys (`shortcuts.with_keys`: "Previous (Alt+↑)")
STEP_ACTIONS = {-1: "editor_previous", 1: "editor_next"}
STEP_TIPS = {-1: "Go to the region before this one in reading order. What you changed here is saved first.",
             1: "Go to the region after this one in reading order. What you changed here is saved first."}
DISCARD = "Discard your changes to this region?"


def kind_words() -> list[str]:
    """The Kind list's entries in the window's language, in the order of `REGION_KINDS`."""
    return [_(REGION_KIND_WORDS.get(k, k)) for k in REGION_KINDS]


def kind_of(word: str) -> str:
    """The code (`REGION_KINDS`) of a Kind list entry; an entry it does not know is taken as a code."""
    return next((k for k in REGION_KINDS if _(REGION_KIND_WORDS.get(k, k)) == word), word)


def review_rows(regions: list[Any]) -> list[tuple[Any, str, str]]:
    """The regions worth a look on a page, in reading order: (region, why, its translation), *why* in the window's
    language (`review.reason_label`; the regions keep the codes). A region made "erase only" is never one."""
    rows: list[tuple[Any, str, str]] = []
    for r in regions:
        if r.status in ("dropped", ERASED):
            continue
        why = [reason_label(f) for f in getattr(r, "flags", [])]
        if r.status not in ("translated", "not-japanese", "ocr-empty"):
            why.append(_("untranslated"))
        if getattr(r, "reader_note", ""):
            why.append(_("note for the reader"))
        why.extend(_(FIT_REASONS[f]) for f in getattr(r, "letter_flags", ()) if f in FIT_REASONS)
        if why:
            rows.append((r, "; ".join(why), r.translated_text))
    return rows


def fit_line(flags: Any, font: str = "") -> str:
    """The editor's line on what the lettering could not do as formatted (*font*: the family asked for); "" for
    nothing."""
    return " ".join(_(FIT_LINES[f]).format(font=font) for f in flags if f in FIT_LINES)


def fitted_crop(crop: Image.Image, room: tuple[int, int] = CROP_ROOM, enlarge: float = CROP_ENLARGE) -> Image.Image:
    """*crop* (the region as the page has it) at the size the editor shows it: within *room*, a small one enlarged at
    most *enlarge* times. In memory only."""
    w, h = max(1, crop.width), max(1, crop.height)
    scale = min(room[0] / w, room[1] / h, enlarge)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return crop if size == crop.size else crop.resize(size, Image.LANCZOS)


class SelectableLine(tk.Text):
    """A line of text that looks like a label (no border, the dialog's ground, wrapping at *wraplength* pixels, as
    many lines high as its text takes) but can be selected with the mouse and copied with Ctrl+C (Tk's own Text
    bindings); it cannot be edited (disabled: typing, pasting and deleting change nothing) and Tab passes it by. Its
    text is *variable*'s, kept in memory only."""

    def __init__(self, master: tk.Misc, variable: tk.StringVar, wraplength: int = 480):
        font = tkfont.nametofont("TkDefaultFont")
        ground = ttk.Style(master).lookup("TFrame", "background") or str(master.winfo_toplevel().cget("background"))
        super().__init__(master, width=max(10, wraplength // max(1, font.measure("0"))), height=1, wrap="char",
                         font=font, relief="flat", borderwidth=0, highlightthickness=0, padx=0, pady=0,
                         background=ground, takefocus=0, cursor="xterm", exportselection=True)
        self.configure(inactiveselectbackground=self.cget("selectbackground"))
        self.variable = variable
        self._trace = variable.trace_add("write", lambda *_a: self._show())
        self.bind("<Configure>", lambda _e: self._fit())
        self._show()

    def _show(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("1.0", self.variable.get())
        self.configure(state="disabled")
        self._fit()

    def _fit(self) -> None:
        """As many lines high as the text takes at the width it has."""
        try:
            counted = self.count("1.0", "end-1c", "displaylines")
        except tk.TclError:
            return
        if isinstance(counted, tuple):
            counted = counted[0]
        lines = max(1, int(counted or 0) + 1)
        if int(self.cget("height")) != lines:
            self.configure(height=lines)

    def text(self) -> str:
        return self.get("1.0", "end-1c")

    def destroy(self) -> None:
        try:
            self.variable.trace_remove("write", self._trace)
        except (tk.TclError, ValueError):
            pass
        super().destroy()


def _number(text: str) -> float | None:
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        return None


def choose_colour(parent: tk.Misc, initial: str = "") -> str:
    """The colour the reader picks in the system's colour chooser (`tkinter.colorchooser`: nothing online), as
    "#rrggbb"; "" when they cancel."""
    try:
        _rgb, chosen = colorchooser.askcolor(color=initial or "#000000", parent=parent, title=_(CHOOSE_INK))
    except tk.TclError:
        return ""
    return ink_code(chosen) if isinstance(chosen, str) and chosen.startswith("#") else ""


def ink_word(code: str) -> str:
    """A colour code as its list names it: Auto, Black, White, or Custom... for a colour of the reader's."""
    return _(INK_WORDS[code]) if code in INK_WORDS else _(CUSTOM_INK)


def outline_words() -> list[str]:
    return [_(OUTLINE_WORDS[v]) for v in (None, True, False)]


def outline_of(word: str) -> bool | None:
    """The outline a word of the Outline list sets (Auto: None)."""
    return next((v for v in (True, False) if _(OUTLINE_WORDS[v]) == word), None)


class InkChoice:
    """A colour as a word processor's colour button gives it: a list (Auto, Black, White, Custom...) and, for a
    colour of the reader's, a swatch with its code that opens the colour chooser again (`choose_colour`). Choosing
    Custom... opens it; cancelled, the list shows what it showed before. *on_change* is called for each change the
    reader makes (not for `set`). In memory only."""

    def __init__(self, parent: tk.Misc, code: str = "", on_change: Callable[[], None] | None = None,
                 chooser: Callable[[tk.Misc, str], str] | None = None):
        self.frame = ttk.Frame(parent)
        self.code = ink_code(code)
        self.on_change = on_change
        self.chooser = chooser or choose_colour
        words = [_(INK_WORDS[c]) for c in INK_NAMES] + [_(CUSTOM_INK)]
        self.var = tk.StringVar(self.frame, value=ink_word(self.code))
        self.box = ttk.Combobox(self.frame, textvariable=self.var, values=words, state="readonly")
        fit_combobox(self.box, words, min_chars=6)
        self.box.pack(side="left")
        self.box.bind("<<ComboboxSelected>>", lambda _e: self._picked())
        self.swatch = tk.Label(self.frame, width=8, relief="solid", borderwidth=1, cursor="hand2")
        self.swatch.bind("<Button-1>", lambda _e: self.choose())
        self._show()

    def get(self) -> str:
        """The colour code shown ("", "black", "white" or "#rrggbb")."""
        return self.code

    def set(self, code: str) -> None:
        self.code = ink_code(code)
        self._show()

    def _show(self) -> None:
        self.var.set(ink_word(self.code))
        if self.code.startswith("#"):
            light = sum(int(self.code[i:i + 2], 16) * w for i, w in ((1, 0.299), (3, 0.587), (5, 0.114))) >= 128
            self.swatch.configure(text=self.code, background=self.code, foreground="#000000" if light else "#ffffff")
            if not self.swatch.winfo_manager():
                self.swatch.pack(side="left", padx=(4, 0))
        elif self.swatch.winfo_manager():
            self.swatch.pack_forget()

    def _picked(self) -> None:
        word = self.var.get()
        if word == _(CUSTOM_INK):
            self.choose()
            return
        code = next((c for c in INK_NAMES if _(INK_WORDS[c]) == word), "")
        if code != self.code:
            self.code = code
            self._show()
            self._changed()
        self.box.selection_clear()

    def choose(self) -> None:
        """The colour chooser, from the colour shown (black for none of the reader's); the editor keeps its grab."""
        top = self.frame.winfo_toplevel()
        try:
            grabbed = top.grab_current() is top
        except (tk.TclError, KeyError):
            grabbed = False
        chosen = ink_code(self.chooser(top, self.code if self.code.startswith("#") else ""))
        try:
            if grabbed and top.winfo_exists():
                top.grab_set()
        except tk.TclError:
            pass
        if chosen and chosen != self.code:
            self.code = chosen
            self._show()
            self._changed()
        else:
            self._show()  # cancelled: the list shows what it showed

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


class ReviewDialog(tk.Toplevel):
    """Translator mode: the page's regions worth a look; a double-click opens the editor on one. A page with none
    says so in the list's place."""

    def __init__(self, master: tk.Misc, rows: list[tuple[Any, str, str]], on_edit: Callable[[Any], None]):
        super().__init__(master)
        self.title(_("Review this page"))
        self.transient(master)
        self.geometry("780x380")
        self.on_edit = on_edit
        self.rows: list[tuple[Any, str, str]] = []
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        self.body = ttk.Frame(frm)  # the list, or the line that says there is nothing to look at
        self.body.pack(fill="both", expand=True, pady=(0, 6))
        self.tree = ttk.Treeview(self.body, columns=("why", "text"), show="tree headings", height=12)
        self.tree.heading("#0", text=_("Region"))
        self.tree.heading("why", text=_("Why"))
        self.tree.heading("text", text=_("Translation"))
        self.tree.column("#0", width=70)
        self.tree.column("why", width=250)
        self.tree.column("text", width=430)
        self.tree.bind("<Double-1>", lambda _e: self._edit())
        self.empty = ttk.Label(self.body, text=_("Nothing on this page needs a look."), anchor="center", justify="center")
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        self.edit_btn = ttk.Button(btns, text=_("Edit..."), command=self._edit)
        self.edit_btn.pack(side="left")
        explain_button(btns, _("Regions flagged for a look, untranslated, or with a note for the reader. Double-click one to edit it.")).pack(
            side="left", padx=(6, 0))
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")
        self.hint_var = tk.StringVar(self, value="")  # Edit... with nothing selected says what to do
        ttk.Label(btns, textvariable=self.hint_var).pack(side="left", padx=(8, 0))
        self.fill(rows)
        place_window(self, master)

    def fill(self, rows: list[tuple[Any, str, str]]) -> None:
        self.rows = list(rows)
        self.tree.delete(*self.tree.get_children())
        for i, (r, why, text) in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), text=str(r.order + 1), values=(why, text))
        shown, hidden = (self.tree, self.empty) if self.rows else (self.empty, self.tree)
        hidden.pack_forget()
        if not shown.winfo_manager():
            shown.pack(fill="both", expand=True)
        self.edit_btn["state"] = "normal" if self.rows else "disabled"

    def _edit(self) -> None:
        sel = self.tree.selection()
        self.hint_var.set("" if sel else _("Select one in the list first."))
        if sel:
            self.on_edit(self.rows[int(sel[0])][0])


class EditBubbleDialog(tk.Toplevel):
    """Translator mode: who says it, what kind of text it is, whether it continues, a remark, the translation and
    how it is lettered; the model can be asked for one more translation, or for others to pick from. The header names
    the bubble by its place on the page (*place*: its number and how many there are) and its state. While the model
    is asked, a line says so and the buttons wait (Cancel closes all the same); the line says when the answer came.

    The formatting bar above the translation (`style`, `set_style`), folded away behind one button unless the region
    has a formatting of its own: bold and italic, each forced on or off or as the
    series sheet says ("Auto"; *faces*: whether the region's automatic lettering is bold, italic), the font family
    (*families*: the installed ones, asked for when the list is first opened; any family name may be typed; with
    *font_memory*, `font_memory.FontMemory`, the starred and recently used families come first, a star beside the
    list stars the one it names, and the family a Save or a step sets is the newest of those used), the
    size (Auto: the largest that fits) and whether the text may be condensed to fit (as the size goes until it is
    clicked: with an automatic size only), the alignment left, centre or right and top, middle or bottom, the line
    spacing (Auto: the setting) and the room between characters, the slant the lines are set at (Auto: the one
    measured on the original lettering), the text direction (Auto: across; `DIRECTION_WORDS`), the text colour, the
    outline and its colour (`InkChoice`, the system's colour chooser for a colour of the reader's; Auto: as the series
    sheet says for the region's kind, else the automatic ink), Reset formatting, and Copy format and Paste format
    (Ctrl+Shift+C, Ctrl+Shift+V; *clip*: what the window copied, `formats.FormatClip`). Enter in the translation
    starts a new line, which the lettering keeps; Ctrl+Enter saves. A moment (`PREVIEW_MS`) after the last change of
    the text or of the formatting, *on_preview*(text, style) is called: the window letters the region again on the
    page behind the editor, and says what could not be done as formatted (`show_fit`). Closing the editor any other
    way than Save (Cancel, Esc, the window's close button, Drop) calls *on_cancel*: the page as it was; Esc and the
    close button ask first when something was changed (`changed`, `close_asked`).

    At the top, *crop* (the region as the page has it, a picture in memory) and the Japanese read there ("Read as:",
    text that can be selected and copied but not edited: `SelectableLine`);
    where there is none (a page shown from the cache, which keeps no Japanese), "Read the Japanese" asks *on_read*
    (called with `show_reading`, which it calls once the reading is done; False: it cannot read now) and Ask again reads
    it first. Previous and Next (Alt+Up, Alt+Down, or the keys the reader gave `shortcuts`' editor_previous and
    editor_next, bound with Copy format and Paste format's: `shortcuts.bind_on`; the first and the last region of
    *place* have no way on) hand *on_step*(-1 or 1, what is to be saved or None when nothing changed, the editor's
    place on the screen) the way to
    the region before or after this one; the editor closes without *on_cancel* (the window ends its preview). *at*:
    where the editor opens on the screen (the place the one before it had), else over *master*. *note*: a line the
    window has to say once (the spellcheck that cannot run), under the header."""

    def __init__(self, master: tk.Misc, region: Any, speakers: list[str], on_save: Callable[[dict[str, Any]], None],
                 on_drop: Callable[[], None], on_ask: Callable[[str, dict[str, str]], bool] | None = None,
                 place: tuple[int, int] | None = None,
                 on_preview: Callable[[str, RegionStyle], None] | None = None,
                 on_cancel: Callable[[], None] | None = None,
                 families: Callable[[], list[str]] | None = None, faces: tuple[bool, bool] = (False, False),
                 crop: Image.Image | None = None,
                 on_read: Callable[[Callable[[str, str], None]], bool] | None = None,
                 on_step: Callable[[int, dict[str, Any] | None, tuple[int, int]], None] | None = None,
                 at: tuple[int, int] | None = None, note: str = "", clip: Any = None, font_memory: Any = None):
        super().__init__(master)
        self.title(_("Edit region"))
        self.transient(master)
        self.region = region
        self.clip = clip  # what the window copied (`formats.FormatClip`: its `style`); None: no Copy and Paste format
        self.on_ask, self.on_save, self.on_preview, self.on_cancel = on_ask, on_save, on_preview, on_cancel
        self.on_read, self.on_step = on_read, on_step
        self.families = families
        self.font_memory = font_memory  # the starred and recent families (`font_memory.FontMemory`), or None
        self._family_names: list[str] = []  # the installed families, once looked up
        self.answer: dict[str, str] = {}  # what went wrong while the model was asked ("error"), filled by the worker
        self._flash_job: str | None = None
        self._preview_job: str | None = None
        self._saved = self._closed = False
        self._handed = False  # gone to the region before or after it: the window ends the preview
        self._ready = False  # the controls are set: their changes are the reader's
        self._reading = False  # the Japanese is being read
        self._ask_after: str | None = None  # Ask again pressed with no Japanese yet: asked once it is read
        self._auto_size = int(getattr(region, "font_size", 0) or 0)  # the size the automatic lettering has now
        self._auto_slant = float(getattr(region, "angle", 0.0) or 0.0)  # the slant measured on its lettering
        number, total = place if place is not None else (region.order + 1, region.order + 1)
        self._place = (number, total)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=_("Bubble {n} of {total} · {state}").format(
            n=number, total=total, state=status_word(region.status))).pack(anchor="w")
        self.note_label: ttk.Label | None = None
        if note:
            self.note_label = ttk.Label(frm, text=note, foreground="#5a5a5a", justify="left", wraplength=480)
            self.note_label.pack(anchor="w", fill="x", pady=(2, 0))
            self.note_label.bind("<Configure>", lambda e: wrap_label(self.note_label, e.width))
        self._build_original(frm, crop)
        grid = ttk.Frame(frm)
        grid.pack(fill="x", pady=(8, 0))
        label = ttk.Label(grid, text=_("Speaker:"))
        label.grid(row=0, column=0, sticky="w")
        self.speaker_var = tk.StringVar(value=region.speaker)
        speaker_box = ttk.Combobox(grid, textvariable=self.speaker_var, values=speakers)
        fit_combobox(speaker_box, [*speakers, region.speaker], min_chars=24, max_chars=40)
        speaker_box.grid(row=0, column=1, sticky="w", padx=(4, 12))
        tip(_("Who says this line. It helps the translation keep their way of speaking."), label, speaker_box)
        label = ttk.Label(grid, text=_("Kind:"))
        label.grid(row=0, column=2, sticky="w")
        words = kind_words()
        self.kind_var = tk.StringVar(value=_(REGION_KIND_WORDS.get(region.tag, region.tag)))
        self.kind_box = ttk.Combobox(grid, textvariable=self.kind_var, values=words, state="readonly")
        fit_combobox(self.kind_box, words, min_chars=8)
        self.kind_box.grid(row=0, column=3, sticky="w", padx=(4, 0))
        tip(_("What sort of text this is; the lettering follows it.") + " " + _(ERASE_ONLY_TIP), label, self.kind_box)
        self.kind_box.bind("<<ComboboxSelected>>", lambda _e: self._changed())  # (erase only: the page shows it)
        self.cont_var = tk.BooleanVar(value=bool(region.continues))
        ttk.Checkbutton(grid, text=_("Sentence continues in the next bubble"), variable=self.cont_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(grid, text=_("Hint for the model (a pun, who is addressed):")).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.note_var = tk.StringVar(value=region.remark)
        ttk.Entry(grid, textvariable=self.note_var, width=64).grid(row=3, column=0, columnspan=4, sticky="we")
        ttk.Label(grid, text=_("Note to the reader (a pun, a reference the translation cannot carry):")).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.reader_var = tk.StringVar(value=getattr(region, "reader_note", ""))
        ttk.Entry(grid, textvariable=self.reader_var, width=64).grid(row=5, column=0, columnspan=4, sticky="we")
        ttk.Label(frm, text=_("Translation (what is drawn in the region):")).pack(anchor="w", pady=(8, 0))
        style = getattr(region, "style", None) or RegionStyle()
        self._build_bar(frm, style, faces)
        self.fit_var = tk.StringVar(value="")  # what the lettering could not do as formatted
        self.fit_label = ttk.Label(frm, textvariable=self.fit_var, foreground=FIT_COLOUR, justify="left", wraplength=480)
        self.fit_label.pack(anchor="w", fill="x")
        self.fit_label.bind("<Configure>", lambda e: wrap_label(self.fit_label, e.width))
        self.show_fit(getattr(region, "letter_flags", ()))
        self.text = tk.Text(frm, width=62, height=5, wrap="word", font="TkDefaultFont", undo=True)
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", region.translated_text)
        self.text.edit_reset()  # Ctrl+Z in the box takes back typing, not the text it opened with
        self.text.edit_modified(False)
        self.text.bind("<<Modified>>", self._text_changed)
        self.text.bind("<Control-Return>", lambda _e: (self._save(), "break")[1])
        self._text_bg = str(self.text.cget("background"))
        ttk.Label(frm, text=_("Enter starts a new line; Ctrl+Enter saves."), foreground="#5a5a5a").pack(anchor="w")
        line = ttk.Frame(frm)  # while the model is asked: a running bar and a line; then what came
        line.pack(fill="x", pady=(6, 0))
        self.busy_bar = ttk.Progressbar(line, mode="indeterminate", length=80)
        self.busy_var = tk.StringVar(value="")
        self.busy_label = ttk.Label(line, textvariable=self.busy_var, wraplength=240, justify="left")
        self.busy_label.pack(side="left", fill="x", expand=True)
        # the line wraps at the width the editor has, never widening it
        self.busy_label.bind("<Configure>", lambda e: wrap_label(self.busy_label, e.width))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        self.drop_btn = ttk.Button(btns, text=_("Drop this region"), command=lambda: (self.destroy(), on_drop()))
        self.drop_btn.pack(side="left")
        tip(_("Take this box off the page: the book shows as it is here. Ctrl+Z brings it back."), self.drop_btn)
        self.ask_btns: list[ttk.Button] = []
        if on_ask is not None and (region.source_text or on_read is not None):  # (with no Japanese: read first)
            for text, mode, explanation in ((_("Ask again"), "again", _("Ask the model for this line once more.")),):
                button = ttk.Button(btns, text=text, command=lambda m=mode: self._ask(m))
                button.pack(side="left", padx=(6, 0))
                tip(explanation, button)
                self.ask_btns.append(button)
        ttk.Button(btns, text=_("Cancel"), command=self.destroy).pack(side="right")
        self.save_btn = ttk.Button(btns, text=_("Save"), command=self._save)
        self.save_btn.pack(side="right", padx=(0, 6))
        self.step_btns: dict[int, ttk.Button] = {}
        if on_step is not None:  # the region before and after this one, in reading order
            steps = ttk.Frame(frm)
            steps.pack(fill="x", pady=(6, 0))
            for delta in (-1, 1):
                button = ttk.Button(steps, text=shortcuts.with_keys(STEP_WORDS[delta], STEP_ACTIONS[delta]),
                                    command=lambda d=delta: self.step(d))
                button.pack(side="left", padx=(6 if delta > 0 else 0, 0))
                tip(_(STEP_TIPS[delta]), button)
                self.step_btns[delta] = button
            self._sync_steps()
        self.bind("<Escape>", lambda _e: self.close_asked())
        self.protocol("WM_DELETE_WINDOW", self.close_asked)
        self.bind("<Control-Return>", lambda _e: self._save())
        # Previous and Next, and Copy format and Paste format on the page's keys, as the keymap has them (`shortcuts`;
        # the steps on the translation's box too, ahead of its own arrow keys)
        keymap = shortcuts.current()
        steps = {"editor_previous": lambda e: self._step_key(e, -1), "editor_next": lambda e: self._step_key(e, 1)}
        shortcuts.bind_on((self, self.text), keymap, steps)
        if clip is not None:
            shortcuts.bind_on((self,), keymap, {"copy_format": lambda _e: self.copy_format(),
                                                "paste_format": lambda _e: self.paste_format()})
        self._ready = True
        self._initial = self._data()  # what `changed` compares with
        self.text.focus_set()
        self.update_idletasks()
        self.bar.relayout(max(self.bar.winfo_width(), frm.winfo_reqwidth() - 20))
        if at is not None:
            self.geometry(f"+{int(at[0])}+{int(at[1])}")
        else:
            place_window(self, master)
        self.grab_set()

    # ------------------------------------------------------------------ the region as the page has it
    def _build_original(self, parent: tk.Misc, crop: Image.Image | None) -> None:
        """The region's picture (*crop*, fitted: `fitted_crop`), the Japanese read there ("Read as:") and, while there
        is none and it can be read, "Read the Japanese"."""
        box = ttk.Frame(parent)
        box.pack(anchor="w", fill="x", pady=(4, 0))
        self._crop_photo: ImageTk.PhotoImage | None = None
        self.crop_label: ttk.Label | None = None
        if crop is not None and crop.width > 1 and crop.height > 1:
            shown = fitted_crop(crop.convert("RGB"))
            self._crop_photo = ImageTk.PhotoImage(shown, master=self)
            self.crop_label = ttk.Label(box, image=self._crop_photo, relief="solid", borderwidth=1)
            self.crop_label.pack(anchor="w")
            tip(_("The region as it is on the page."), self.crop_label)
        self.source_var = tk.StringVar(self, value="")
        # selectable and copied with Ctrl+C, never edited (`SelectableLine`); in memory only
        self.source_label = SelectableLine(box, self.source_var, wraplength=480)
        self.read_btn = ttk.Button(box, text=_("Read the Japanese"), command=self.read)
        tip(_("Read the Japanese of this region from the page again, to see it here and to ask the model again. Nothing of it is kept."),
            self.read_btn)
        self._show_source()

    def _source(self) -> str:
        return str(getattr(self.region, "source_text", "") or "")

    def _show_source(self) -> None:
        """"Read as:" with the region's Japanese, or "Read the Japanese" while it has none (when it can be read)."""
        text = self._source()
        self.source_var.set(_("Read as: ") + text if text else "")
        if text:
            self.read_btn.pack_forget()
            if not self.source_label.winfo_manager():
                self.source_label.pack(anchor="w", fill="x", pady=(4, 0))
        else:
            self.source_label.pack_forget()
            if self.on_read is not None and not self.read_btn.winfo_manager():
                self.read_btn.pack(anchor="w", pady=(4, 0))

    def read(self) -> None:
        """Read the Japanese (the button, and Ask again with none yet): the window reads it in its worker and hands
        it back (`show_reading`); the buttons wait meanwhile."""
        if self._closed or self._reading or self.on_read is None:
            return
        self._reading = True
        self.busy_var.set(_(READING))
        if not self.busy_bar.winfo_manager():
            self.busy_bar.pack(side="left", padx=(0, 8), before=self.busy_label)
        self.busy_bar.start(15)
        self._set_buttons("disabled")
        if self.on_read(self.show_reading) is False:  # it cannot be read now
            self.show_reading("", "no-ocr")

    def show_reading(self, text: str, error: str = "") -> None:
        """The Japanese read (*text*; the window has given it to the region too), or nothing and why (*error*: a key
        of `NOT_READ`, or the error's own words): "Read as:" shows it, and an Ask again that waited for it asks now."""
        if self._closed:
            return
        self._reading = False
        self.busy_bar.stop()
        self.busy_bar.pack_forget()
        self._set_buttons("normal")
        mode, self._ask_after = self._ask_after, None
        if text and not self._source():
            self.region.source_text = text
        self._show_source()
        if not self._source():
            self.busy_var.set(_(NOT_READ[error]) if error in NOT_READ else (error or _(NOT_READ["none"])))
            return
        self.busy_var.set("")
        if mode is not None:
            self._ask(mode)

    # ------------------------------------------------------------------ the region before or after, and closing
    def _sync_steps(self) -> None:
        """Previous and Next: no way on before the first region or after the last; neither while the buttons wait."""
        number, total = self._place
        for delta, button in self.step_btns.items():
            last = number <= 1 if delta < 0 else number >= total
            busy = str(self.save_btn.cget("state")) == "disabled"
            button["state"] = "disabled" if last or busy else "normal"

    def changed(self) -> bool:
        """Whether anything the editor shows differs from what it opened with (the text, a field, the formatting)."""
        return self._data() != getattr(self, "_initial", None)

    def step(self, delta: int) -> None:
        """Previous (-1) or Next (+1), or Alt+Up and Alt+Down: what was changed is handed on to be saved (as Save
        would), and the window opens the editor on the region before or after this one."""
        button = self.step_btns.get(delta)
        if self._closed or button is None or str(button.cget("state")) == "disabled":
            return
        data = self._data() if self.changed() else None
        if data is not None:
            self._remember_font()
        at = self.place_on_screen()
        self._handed = True
        self.destroy()
        if self.on_step is not None:
            self.on_step(delta, data, at)

    def _step_key(self, event: tk.Event, delta: int) -> str | None:
        """Alt+Up, Alt+Down: Previous, Next - but in a list, whose own Alt+Down opens it."""
        if isinstance(getattr(event, "widget", None), (ttk.Combobox, ttk.Spinbox)):
            return None
        self.step(delta)
        return "break"

    def place_on_screen(self) -> tuple[int, int]:
        """Where the editor is on the screen, as its geometry sets it (the next one opens there)."""
        try:
            x, y = self.geometry().split("+", 1)[1].split("+")[:2]
            return int(x), int(y)
        except (tk.TclError, ValueError, IndexError):
            return (0, 0)

    def close_asked(self) -> None:
        """Esc and the window's close button: with something changed, the reader is asked before it is dropped;
        "Keep editing" (the button that has the focus) leaves the editor as it is."""
        if self._closed:
            return
        if self.changed() and not caches.ask(self, _(DISCARD), _("Discard"), _("Keep editing"), no_first=True):
            try:
                if self.winfo_exists():
                    self.grab_set()  # the question's box took the grab with it
                    self.text.focus_set()
            except tk.TclError:
                pass
            return
        self.destroy()

    # ------------------------------------------------------------------ the formatting bar
    def _build_bar(self, parent: tk.Misc, style: RegionStyle, faces: tuple[bool, bool]) -> None:
        """Bold, italic and their Auto; the font; the size and its Auto; the alignment; the line and letter spacing;
        the slant; the text direction; the ink (`_build_ink`); Reset formatting: groups that flow into as many rows as
        the editor's width needs."""
        self._faces_auto = {"bold": faces[0], "italic": faces[1]}
        self._faces: dict[str, bool | None] = {"bold": style.bold, "italic": style.italic}
        base = tkfont.nametofont("TkDefaultFont")
        self._bold_font = base.copy()
        self._bold_font.configure(weight="bold")
        self._italic_font = base.copy()
        self._italic_font.configure(slant="italic")
        look = ttk.Style(self)
        look.configure("FormatBold.TCheckbutton", font=self._bold_font)
        look.configure("FormatItalic.TCheckbutton", font=self._italic_font)
        self.format_btn = ttk.Button(parent, style="Toolbutton", command=self._toggle_bar)
        self.format_btn.pack(anchor="w")
        self.bar = bar = FlowBar(parent, padding=(0, 4), gap=(12, 4))
        self._show_bar(style != RegionStyle())
        g = bar.group()
        self.face_vars: dict[str, tk.BooleanVar] = {}
        self.face_boxes: dict[str, ttk.Checkbutton] = {}
        for name, word, look_name in (("bold", "Bold", "FormatBold.TCheckbutton"),
                                      ("italic", "Italic", "FormatItalic.TCheckbutton")):
            forced = self._faces[name]
            var = tk.BooleanVar(value=self._faces_auto[name] if forced is None else forced)
            box = ttk.Checkbutton(g, text=_(word), variable=var, style=look_name, command=lambda n=name: self._face(n))
            box.pack(side="left", padx=(0, 6))
            if forced is None:
                box.state(["alternate"])
            self.face_vars[name], self.face_boxes[name] = var, box
            tip(_(FACE_TIPS[name]), box)
        self.faces_auto_btn = ttk.Button(g, text=_(AUTO), width=6, command=self._faces_to_auto)
        self.faces_auto_btn.pack(side="left")
        tip(_("Bold and italic as the series sheet says."), self.faces_auto_btn)
        g = bar.group()
        ttk.Label(g, text=_("Font:")).pack(side="left")
        self.font_var = tk.StringVar(value=style.font or _(AUTOMATIC_FONT))
        self.font_box = ttk.Combobox(g, textvariable=self.font_var, width=24, postcommand=self._fill_families,
                                     values=font_choices(self.font_memory, (),
                                                         [_(AUTOMATIC_FONT), *([style.font] if style.font else [])]))
        self.font_box.pack(side="left", padx=(4, 0))
        self.font_star: StarButton | None = None
        if self.font_memory is not None:  # ☆ / ★: the family the list names starred, first in every font list
            self.font_star = StarButton(g, self.font_var, self.font_memory, blank=(_(AUTOMATIC_FONT),),
                                        on_toggle=self._fill_families)
            self.font_star.pack(side="left", padx=(2, 0))
        self._families_shown = False
        g = bar.group()
        ttk.Label(g, text=_("Size:")).pack(side="left")
        self.size_var = tk.StringVar(value=str(style.size or self._auto_size or 24))
        self.size_spin = ttk.Spinbox(g, from_=STYLE_SIZES[0], to=STYLE_SIZES[1], increment=1, width=5,
                                     textvariable=self.size_var)
        self.size_spin.pack(side="left", padx=(4, 4))
        self.size_auto = tk.BooleanVar(value=not style.size)
        check = ttk.Checkbutton(g, text=_(AUTO), variable=self.size_auto, command=self._size_mode)
        check.pack(side="left")
        tip(_("The size that fits the bubble."), check)
        self._condense: bool | None = style.condense  # None: as the size goes (an automatic size may be condensed)
        self.condense_var = tk.BooleanVar(value=self._condense_shown())
        self.condense_box = ttk.Checkbutton(g, text=_("Condense to fit"), variable=self.condense_var,
                                            command=self._condense_clicked)
        self.condense_box.pack(side="left", padx=(8, 0))
        tip(_("Squeeze the letters a little so that the text fits."), self.condense_box)
        if self._condense is None:
            self.condense_box.state(["alternate"])
        g = bar.group()
        self.align_var = tk.StringVar(value=style.align)
        self.align_btns = []
        for code in ALIGNS:
            button = ttk.Radiobutton(g, text=_(ALIGN_WORDS[code]), value=code, variable=self.align_var, style="Toolbutton")
            button.pack(side="left")
            self.align_btns.append(button)
        g = bar.group()
        self.valign_var = tk.StringVar(value=style.valign)
        self.valign_btns = []
        for code in VALIGNS:
            button = ttk.Radiobutton(g, text=_(VALIGN_WORDS[code]), value=code, variable=self.valign_var, style="Toolbutton")
            button.pack(side="left")
            self.valign_btns.append(button)
        g = bar.group()
        label = ttk.Label(g, text=_("Line spacing:"))
        label.pack(side="left")
        self.line_var = tk.StringVar(value=self._spacing_word(style.line_spacing))
        self.line_spin = ttk.Spinbox(g, values=(_(AUTO), *LINE_SPACING_STEPS), width=6, textvariable=self.line_var,
                                     wrap=False)
        self.line_spin.pack(side="left", padx=(4, 0))
        tip(_("The space between the lines. Auto keeps your setting."), label, self.line_spin)
        g = bar.group()
        label = ttk.Label(g, text=_("Letter spacing:"))
        label.pack(side="left")
        self.letter_var = tk.StringVar(value=str(style.letter_spacing))
        self.letter_spin = ttk.Spinbox(g, from_=LETTER_SPACINGS[0], to=LETTER_SPACINGS[1], increment=1, width=5,
                                       textvariable=self.letter_var)
        self.letter_spin.pack(side="left", padx=(4, 0))
        tip(_("Pixels added between the letters."), label, self.letter_spin)
        g = bar.group()
        label = ttk.Label(g, text=_("Slant:"))
        label.pack(side="left")
        self.slant_var = tk.StringVar(value=self._slant_word(style.slant))
        self.slant_spin = ttk.Spinbox(g, from_=SLANTS[0], to=SLANTS[1], increment=1, width=5, textvariable=self.slant_var)
        self.slant_spin.pack(side="left", padx=(4, 4))
        self.slant_auto = tk.BooleanVar(value=style.slant is None)
        check = ttk.Checkbutton(g, text=_(AUTO), variable=self.slant_auto, command=self._slant_mode)
        check.pack(side="left")
        tip(_(SLANT_TIP), label, self.slant_spin, check)
        g = bar.group()
        label = ttk.Label(g, text=_("Text direction:"))
        label.pack(side="left")
        words = [_(DIRECTION_WORDS[code]) for code in DIRECTIONS]
        self.direction_var = tk.StringVar(value=_(DIRECTION_WORDS.get(style.direction, AUTO)))
        self.direction_box = ttk.Combobox(g, textvariable=self.direction_var, values=words, state="readonly")
        fit_combobox(self.direction_box, words, min_chars=8)
        self.direction_box.pack(side="left", padx=(4, 0))
        tip(_(DIRECTION_TIP), label, self.direction_box)
        self._build_ink(bar, style)
        g = bar.group()
        self.reset_btn = ttk.Button(g, text=_("Reset formatting"), command=lambda: self.set_style(RegionStyle()))
        self.reset_btn.pack(side="left")
        if self.clip is not None:
            self.copy_btn = ttk.Button(g, text=_("Copy format"), command=self.copy_format)
            self.paste_btn = ttk.Button(g, text=_("Paste format"), command=self.paste_format)
            for button, which in ((self.copy_btn, "copy"), (self.paste_btn, "paste")):
                button.pack(side="left", padx=(6, 0))
                tip(_(FORMAT_TIPS[which]), button)
            self._sync_paste()
        self._size_mode(quiet=True)
        self._slant_mode(quiet=True)
        for var in (self.font_var, self.size_var, self.align_var, self.valign_var, self.line_var, self.letter_var,
                    self.slant_var, self.direction_var, self.outline_var):
            var.trace_add("write", lambda *_a: self._changed())

    def _build_ink(self, bar: FlowBar, style: RegionStyle) -> None:
        """The bar's ink: the text colour, the outline (Auto, On, Off) and the outline's colour (`InkChoice`); Auto
        is what the series sheet says for the region's kind, else the automatic lettering."""
        g = bar.group()
        label = ttk.Label(g, text=_("Text colour:"))
        label.pack(side="left")
        self.colour_choice = InkChoice(g, style.colour, self._changed)
        self.colour_choice.frame.pack(side="left", padx=(4, 0))
        tip(_(INK_TIPS["colour"]), label, self.colour_choice.box)
        g = bar.group()
        label = ttk.Label(g, text=_("Outline:"))
        label.pack(side="left")
        words = outline_words()
        self.outline_var = tk.StringVar(self, value=_(OUTLINE_WORDS[style.outline]))
        self.outline_box = ttk.Combobox(g, textvariable=self.outline_var, values=words, state="readonly")
        fit_combobox(self.outline_box, words, min_chars=5)
        self.outline_box.pack(side="left", padx=(4, 0))
        tip(_(INK_TIPS["outline"]), label, self.outline_box)
        g = bar.group()
        label = ttk.Label(g, text=_("Outline colour:"))
        label.pack(side="left")
        self.outline_choice = InkChoice(g, style.outline_colour, self._changed)
        self.outline_choice.frame.pack(side="left", padx=(4, 0))
        tip(_(INK_TIPS["outline_colour"]), label, self.outline_choice.box)

    def copy_format(self) -> None:
        """Copy format (Ctrl+Shift+C): the formatting on the bar kept in the window's clip, for Paste format here, in
        another editor or on the page."""
        if self.clip is not None:
            self.clip.style = self.style()
            self._sync_paste()

    def paste_format(self) -> None:
        """Paste format (Ctrl+Shift+V): the formatting copied last on the bar, unfolded; the page follows a moment
        later and Save keeps it. With nothing copied, nothing happens."""
        style = getattr(self.clip, "style", None)
        if style is None:
            return
        self._show_bar(True)
        self.set_style(style)

    def _sync_paste(self) -> None:
        if hasattr(self, "paste_btn"):
            self.paste_btn.state(["!disabled"] if getattr(self.clip, "style", None) is not None else ["disabled"])

    def _show_bar(self, shown: bool) -> None:
        """The formatting bar on the editor or folded away; the button says which, and opens or folds it."""
        if shown and not self.bar.winfo_manager():
            self.bar.pack(fill="x", pady=(2, 0), after=self.format_btn)
        elif not shown and self.bar.winfo_manager():
            self.bar.pack_forget()
        self.format_btn.configure(text=("▾ " if shown else "▸ ") + _("Formatting"))

    def _toggle_bar(self) -> None:
        self._show_bar(not self.bar.winfo_manager())
        self.update_idletasks()
        self.bar.relayout(max(self.bar.winfo_width(), self.format_btn.master.winfo_width() - 20))

    @staticmethod
    def _spacing_word(value: float) -> str:
        """The line spacing as its box shows it: Auto, a step of its list, or the number."""
        if not value:
            return _(AUTO)
        return next((step for step in LINE_SPACING_STEPS if float(step) == value), f"{value:g}")

    def _fill_families(self) -> None:
        """The font list as it opens: the automatic font, the name typed, the starred and recently used families
        (*font_memory*), then the installed ones (looked up the first time the list opens: it takes a moment)."""
        if self.families is None and self.font_memory is None:
            return
        if not self._families_shown and self.families is not None:
            self._families_shown = True
            try:
                self._family_names = list(self.families())
            except Exception:  # noqa: BLE001 - a typed name still works
                self._family_names = []
        names = self._family_names
        current = self.font_var.get().strip()
        extra = [current] if current and current != _(AUTOMATIC_FONT) and current not in names else []
        self.font_box.configure(values=font_choices(self.font_memory, names, [_(AUTOMATIC_FONT), *extra]))

    def _remember_font(self) -> None:
        """The family the bar sets (none: automatic) is the newest of the fonts used last (*font_memory*)."""
        if self.font_memory is not None:
            self.font_memory.used(self.style().font)

    def _face(self, name: str) -> None:
        """B or I clicked: forced on or off from now on, no longer as the series sheet says."""
        self._faces[name] = bool(self.face_vars[name].get())
        self.face_boxes[name].state(["!alternate"])
        self._changed()

    def _faces_to_auto(self) -> None:
        """Auto beside B and I: both as the series sheet says for the region's kind again."""
        for name in ("bold", "italic"):
            self._faces[name] = None
            self.face_vars[name].set(self._faces_auto[name])
            self.face_boxes[name].state(["alternate"])
        self._changed()

    def _size_mode(self, quiet: bool = False) -> None:
        """The size's Auto: the box shows the size the lettering has and waits; unticked, it is the size to keep.
        Condense to fit, while it is automatic, follows: on with an automatic size, off at a fixed one."""
        self.size_spin.configure(state="disabled" if self.size_auto.get() else "normal")
        if self._condense is None:
            self.condense_var.set(self._condense_shown())
            self.condense_box.state(["alternate"])  # setting the box's variable clears it
        if not quiet:
            self._changed()

    def _slant_word(self, slant: float | None) -> str:
        """The slant as its box shows it: the reader's, or the measured one while it is automatic."""
        value = self._auto_slant if slant is None else slant
        return f"{value:g}"

    def _slant_mode(self, quiet: bool = False) -> None:
        """The slant's Auto: the box shows the slant measured on the lettering and waits; unticked, it is the slant
        to set the lines at."""
        if self.slant_auto.get():
            ready, self._ready = self._ready, False
            try:
                self.slant_var.set(self._slant_word(None))
            finally:
                self._ready = ready
        self.slant_spin.configure(state="disabled" if self.slant_auto.get() else "normal")
        if not quiet:
            self._changed()

    def _direction(self) -> str:
        """The text direction the box shows, as its code (`annotations.DIRECTIONS`)."""
        shown = self.direction_var.get()
        return next((code for code in DIRECTIONS if _(DIRECTION_WORDS[code]) == shown), "")

    def _condense_shown(self) -> bool:
        return self._condense if self._condense is not None else bool(self.size_auto.get())

    def _condense_clicked(self) -> None:
        """Condense to fit clicked: allowed or not from now on, whatever the size."""
        self._condense = bool(self.condense_var.get())
        self.condense_box.state(["!alternate"])
        self._changed()

    def style(self) -> RegionStyle:
        """The formatting the bar shows, checked as a file's is (`RegionStyle.make`)."""
        font = self.font_var.get().strip()
        size = _number(self.size_var.get()) if not self.size_auto.get() else 0
        line = _number(self.line_var.get())
        letter = _number(self.letter_var.get())
        slant = None if self.slant_auto.get() else _number(self.slant_var.get())
        return RegionStyle.make(align=self.align_var.get(), valign=self.valign_var.get(),
                                font="" if font == _(AUTOMATIC_FONT) else font, size=size or 0,
                                bold=self._faces["bold"], italic=self._faces["italic"], line_spacing=line or 0,
                                letter_spacing=letter or 0, condense=self._condense,
                                slant=0.0 if slant is None and not self.slant_auto.get() else slant,
                                direction=self._direction(), colour=self.colour_choice.get(),
                                outline=outline_of(self.outline_var.get()), outline_colour=self.outline_choice.get())

    def set_style(self, style: RegionStyle) -> None:
        """Show *style* on the bar (Reset formatting: the automatic one); the page follows a moment later."""
        self._ready = False
        try:
            self._faces = {"bold": style.bold, "italic": style.italic}
            for name in ("bold", "italic"):
                forced = self._faces[name]
                self.face_vars[name].set(self._faces_auto[name] if forced is None else forced)
                self.face_boxes[name].state(["alternate" if forced is None else "!alternate"])
            self.font_var.set(style.font or _(AUTOMATIC_FONT))
            self.size_auto.set(not style.size)
            self.size_var.set(str(style.size or self._auto_size or 24))
            self._condense = style.condense
            self.condense_var.set(self._condense_shown())
            self.condense_box.state(["alternate" if style.condense is None else "!alternate"])
            self._size_mode(quiet=True)
            self.align_var.set(style.align)
            self.valign_var.set(style.valign)
            self.line_var.set(self._spacing_word(style.line_spacing))
            self.letter_var.set(str(style.letter_spacing))
            self.slant_auto.set(style.slant is None)
            self.slant_var.set(self._slant_word(style.slant))
            self._slant_mode(quiet=True)
            self.direction_var.set(_(DIRECTION_WORDS.get(style.direction, AUTO)))
            self.colour_choice.set(style.colour)
            self.outline_var.set(_(OUTLINE_WORDS[style.outline]))
            self.outline_choice.set(style.outline_colour)
        finally:
            self._ready = True
        self._changed()

    def show_fit(self, flags: Any, size: int | None = None) -> None:
        """What the lettering could not do as formatted, under the bar (nothing: an empty line); *size* is the size
        the lettering came to, which the size box shows while it is automatic."""
        self.fit_var.set(fit_line(flags, self.style().font))
        if size and self.size_auto.get():
            self._auto_size = int(size)
            ready, self._ready = self._ready, False
            try:
                self.size_var.set(str(size))
            finally:
                self._ready = ready

    # ------------------------------------------------------------------ the page behind the editor
    def _text_changed(self, _event: Any = None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._changed()

    def _changed(self) -> None:
        """A change of the text or of the formatting: the page shows it once the reader pauses."""
        if not self._ready or self._closed or self.on_preview is None:
            return
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(PREVIEW_MS, self._preview)

    def _preview(self) -> None:
        if self._preview_job is not None:  # called before its time: the waiting one goes
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
        self._preview_job = None
        if self.on_preview is not None and not self._closed:
            erase_only = kind_of(self.kind_var.get().strip()) == ERASE_ONLY  # erased, nothing set
            self.on_preview("" if erase_only else self.text.get("1.0", "end").strip(), self.style())

    def _save(self) -> None:
        """Save (the button, Ctrl+Enter): what the editor shows is kept; not while the model is asked."""
        if self._closed or str(self.save_btn.cget("state")) == "disabled":
            return
        self._saved = True
        self._remember_font()
        self.on_save(self._data())
        self.destroy()

    # ------------------------------------------------------------------ the model asked
    def _ask(self, mode: str) -> None:
        """Ask again: the model asked for the line; a region with no Japanese yet has it read first (`read`)."""
        if self.on_ask is None or self._closed:
            return
        if not self._source():
            if self.on_read is not None:
                self._ask_after = mode
                self.read()
            return
        self.answer = {}
        self.set_asking(mode)
        if self.on_ask(mode, self.answer) is False:  # the model cannot be asked now
            self.show_answers(mode, [])

    def set_asking(self, mode: str) -> None:
        """The model is asked: a running bar and a line say so, and the buttons wait (Cancel still closes)."""
        self.busy_var.set(_(ASKING.get(mode, ASKING["again"])))
        if not self.busy_bar.winfo_manager():
            self.busy_bar.pack(side="left", padx=(0, 8), before=self.busy_label)
        self.busy_bar.start(15)
        self._set_buttons("disabled")

    def show_answers(self, mode: str, texts: list[str]) -> None:
        """What the model gave: one more translation replaces the text (the box lights up for a moment); the line
        says so, or that nothing came, and why."""
        if self._closed:
            return
        self.busy_bar.stop()
        self.busy_bar.pack_forget()
        self._set_buttons("normal")
        self._show_source()  # (read for the question when there was none)
        error = self.answer.get("error", "")
        if not texts:
            self.busy_var.set(_("No answer from the model: {error}").format(error=error) if error
                              else _("The model gave no other translation."))
            return
        self._use(texts[0])
        self._flash()
        self.busy_var.set(_("The model's new translation is in the box: Save keeps it, Cancel keeps the old one."))

    def _set_buttons(self, state: str) -> None:
        for button in (self.drop_btn, self.save_btn, *self.ask_btns, self.read_btn):
            try:
                button["state"] = state
            except tk.TclError:
                pass
        if getattr(self, "step_btns", None):
            self._sync_steps()

    def _flash(self) -> None:
        if self._flash_job is not None:
            self.after_cancel(self._flash_job)
        self.text.configure(background=FLASH)

        def back() -> None:
            self._flash_job = None
            try:
                self.text.configure(background=self._text_bg)
            except tk.TclError:  # the editor is gone
                pass

        self._flash_job = self.after(FLASH_MS, back)

    def destroy(self) -> None:
        """The editor closes: without Save (or a step to the region before or after it, whose preview the window
        ends), the page shows the region as it was (*on_cancel*)."""
        for job in ("_flash_job", "_preview_job"):
            if getattr(self, job, None) is not None:
                try:
                    self.after_cancel(getattr(self, job))
                except tk.TclError:
                    pass
                setattr(self, job, None)
        closed, self._closed = getattr(self, "_closed", True), True
        if not closed and not self._saved and not getattr(self, "_handed", False) and self.on_cancel is not None:
            try:
                self.on_cancel()
            except tk.TclError:  # the window is going too
                pass
        super().destroy()

    def _use(self, text: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)

    def _data(self) -> dict[str, Any]:
        return {"text": self.text.get("1.0", "end").strip(), "speaker": self.speaker_var.get().strip(),
                "kind": kind_of(self.kind_var.get().strip()), "continues": bool(self.cont_var.get()),
                "note": self.note_var.get().strip(), "reader_note": self.reader_var.get().strip(),
                "style": self.style()}
