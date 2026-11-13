"""The series sheet dialog: glossary terms, character sheets and the style guide. Remove selected asks first, naming
what goes; Undo takes back the last change made in the dialog (one step). The lettering font and the fonts per kind
are lists of the installed families (any family name may be typed) with the reader's starred and recently used ones
first and a star beside each (`font_memory`)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from ...annotations import (
    HONORIFIC_POLICIES,
    LETTERING_KINDS,
    CharacterSheet,
    GlossaryStore,
    LetteringStyle,
    StyleGuide,
)
from ...i18n import _
from ...render import resolve_font, split_face
from ...render.fonts import font_families
from ..banner import break_lines
from ..font_memory import FontMemory, StarButton, font_choices
from ..layout import fit_combobox, place_window
from ..sheet_changes import renamed_pairs
from ..tooltip import tip
from . import caches
from .help import explain_button
from .review import OUTLINE_WORDS, REGION_KIND_WORDS, InkChoice, outline_of, outline_words

FILE_WRAP = 560  # pixels: the line under the tabs that names the file
BRACKETS = "()（）"  # around a hint that once stood beside its field: gone as a tooltip
HONORIFIC_WORDS = {"": "(not set)", "keep": "Keep (-san, -chan)", "drop": "Drop (plain names)",
                   "adapt": "Adapt (natural equivalents)"}  # the policies as the list names them (the sheet keeps the codes)
FIELD_TIPS = {"pronoun": "The word this character says for \"I\".",
              "addresses": "How this character calls others: name=form, separated by semicolons."}
# Remove selected: the question, by what is removed; the names it lists at most (then "...")
REMOVE_QUESTIONS = {"terms": "Remove {n} term(s) from the series sheet: {names}? Undo puts them back.",
                    "characters": "Remove {n} character(s) from the series sheet: {names}? Undo puts them back."}
NAMES_SHOWN = 5
UNDO_TIP = "Take back the last change to the sheet made in this window (one step)."
# the lettering by kind: the ink's columns, and what each says (a region's own ink in the region editor comes first)
INK_HEADINGS = ((4, "Text colour"), (5, "Outline"), (6, "Outline colour"))
KIND_INK_TIPS = {"colour": "The colour of this kind's letters. Auto: black or white to suit the ground. A region's own "
                           "colour in the region editor comes first.",
                 "outline": "A rim round this kind's letters. Auto: only on a drawing or a tone. A region's own "
                            "setting in the region editor comes first.",
                 "outline_colour": "The colour of the rim. Auto: the opposite of the letters. A region's own setting "
                                   "in the region editor comes first."}


def shown_names(names: list[str], most: int = NAMES_SHOWN) -> str:
    """*names* as a question lists them: the first *most*, then an ellipsis for the others."""
    return ", ".join(names[:most]) + (", ..." if len(names) > most else "")


def same_style(a: StyleGuide, b: StyleGuide) -> bool:
    """Whether two style guides letter and tell the model the same: every kind's lettering as each gives it (one that
    names a kind's default lettering and one that leaves it out are the same)."""
    return ((a.honorifics, a.tone, list(a.rules), a.font) == (b.honorifics, b.tone, list(b.rules), b.font)
            and all(a.lettering_for(kind) == b.lettering_for(kind) for kind in LETTERING_KINDS))


def honorific_word(policy: str) -> str:
    return _(HONORIFIC_WORDS.get(policy, policy))


def honorific_policy(word: str) -> str:
    """The code of an entry of the Honorifics list; one it does not know is taken as a code."""
    return next((p for p in HONORIFIC_POLICIES if honorific_word(p) == word), word)


class GlossaryDialog(tk.Toplevel):
    """The series sheet: glossary terms, character sheets and the style guide; told to the model, shareable. Remove
    selected asks first (`REMOVE_QUESTIONS`, Keep them focused). Each change keeps a copy of the sheet before it, and
    Undo (in the foot) puts that back and saves it: one step, the last change. A saved change that gives a term or a
    character another rendering (Undo too) goes to *on_renamed* with the renderings changed (`renamed_pairs`), which
    offers them to the lines already translated (`TranslatorMixin._offer_sheet_renames`)."""

    def __init__(self, master: tk.Misc, store: GlossaryStore, series: str, language: str, on_change: Callable[[], None],
                 fonts_dir: Path | None = None,
                 on_renamed: Callable[[list[tuple[str, str]], tk.Misc], None] | None = None,
                 font_memory: FontMemory | None = None):
        super().__init__(master)
        self.store, self.series, self.language, self.on_change = store, series, language, on_change
        self.on_renamed = on_renamed  # renderings changed (old, new), once saved: the lines translated with the old one
        self.fonts_dir = fonts_dir
        self.font_memory = font_memory  # the reader's starred and recently used fonts (first in the font lists)
        self._families: list[str] | None = None  # the installed families, looked up when a font list first opens
        self.font_boxes: list[ttk.Combobox] = []
        self.glossary = store.open(series, language)
        self._undo: dict[str, Any] | None = None  # the sheet before the last change (`Glossary.to_json`), for Undo
        self.title(_("Series sheet - {series} [{language}]").format(series=series, language=language))
        self.geometry("860x560")
        self.transient(master)
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True, pady=(0, 6))
        self._build_terms(nb)
        self._build_characters(nb)
        self._build_style(nb)
        foot = ttk.Frame(outer)
        foot.pack(fill="x")
        file_line = ttk.Label(foot, justify="left")
        file_line.configure(text=break_lines(_("File: {path}").format(path=self.glossary.path), FILE_WRAP, file_line))
        file_line.pack(side="left")
        ttk.Button(foot, text=_("Close"), command=self._close).pack(side="right")
        self.undo_btn = ttk.Button(foot, text=_("Undo"), command=self.undo, state="disabled")
        self.undo_btn.pack(side="right", padx=(0, 6))
        tip(_(UNDO_TIP), self.undo_btn)
        explain_button(foot, _("Facts the model is told before translating: names and terms with their renderings, who the characters are and how they talk, and how the series should read. Never lines of the book.")).pack(
            side="right", padx=(0, 6))
        self._fill()
        self._style_kept = self._style_shown()  # what Close compares the style guide's fields with
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()  # as wide as the lettering rows with their ink need, in any language
        width = min(max(860, self.winfo_reqwidth()), self.winfo_screenwidth() - 40)
        self.geometry(f"{width}x560")
        place_window(self, master)

    # terms
    def _build_terms(self, nb: ttk.Notebook) -> None:
        frm = ttk.Frame(nb, padding=6)
        nb.add(frm, text=_("Terms"))
        self.tree = ttk.Treeview(frm, columns=("rendering", "note"), show="tree headings", height=9)
        self.tree.heading("#0", text=_("Term (as in the book)"))
        self.tree.heading("rendering", text=_("Rendering"))
        self.tree.heading("note", text=_("Note"))
        self.tree.column("#0", width=200)
        self.tree.column("rendering", width=200)
        self.tree.column("note", width=360)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._pick)
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(6, 0))
        self.term_var, self.rend_var, self.note_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var, width, what in ((_("Term"), self.term_var, 18, _("The word as it is written in the book.")),
                                        (_("Rendering"), self.rend_var, 18, ""),
                                        (_("Note"), self.note_var, 30, _("Anything that helps translate this word."))):
            name = ttk.Label(row, text=label + ":")
            name.pack(side="left")
            entry = ttk.Entry(row, textvariable=var, width=width)
            entry.pack(side="left", padx=(2, 8))
            if what:
                tip(what, name, entry)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text=_("Add / update"), command=self._set).pack(side="left")
        ttk.Button(btns, text=_("Remove selected"), command=self._remove).pack(side="left", padx=(6, 0))

    def _pick(self, _e: Any) -> None:
        for item in self.tree.selection():
            self.term_var.set(self.tree.item(item, "text"))
            rendering, note = self.tree.item(item, "values")
            self.rend_var.set(rendering)
            self.note_var.set(note)
            break

    def _set(self) -> None:
        term, rendering = self.term_var.get().strip(), self.rend_var.get().strip()
        if not term or not rendering:
            caches.tell(self, _("A term and its rendering are needed."), icon="info")
            return
        before = self.glossary.to_json()
        self.glossary.set(term, rendering, self.note_var.get().strip())
        self._save(before)

    def _remove(self) -> None:
        terms = [self.tree.item(item, "text") for item in self.tree.selection()]
        if not terms or not self._removal_asked("terms", terms):
            return
        before = self.glossary.to_json()
        for term in terms:
            self.glossary.remove(term)
        self._save(before)

    def _removal_asked(self, what: str, names: list[str]) -> bool:
        """Whether the reader chose to remove *names* (`REMOVE_QUESTIONS`; Keep them has the focus)."""
        question = _(REMOVE_QUESTIONS[what]).format(n=len(names), names=shown_names(names))
        return caches.ask(self, question, _("Remove selected"), _("Keep them"), no_first=True)

    # characters
    CHAR_FIELDS = (("name", "Name (as in the book)", 16), ("rendering", "Rendering", 14), ("gender", "Gender", 8),
                   ("age", "Age", 8), ("pronoun", "First person", 8), ("style", "Speech style", 24),
                   ("role", "Role / relationships", 24), ("addresses", "Calls others (name=form; ...)", 30))

    def _build_characters(self, nb: ttk.Notebook) -> None:
        frm = ttk.Frame(nb, padding=6)
        nb.add(frm, text=_("Characters"))
        cols = [k for k, _l, _w in self.CHAR_FIELDS if k != "name"]
        self.ctree = ttk.Treeview(frm, columns=cols, show="tree headings", height=8)
        self.ctree.heading("#0", text=_("Name"))
        self.ctree.column("#0", width=110)
        for key, label, width in self.CHAR_FIELDS:
            if key == "name":
                continue
            self.ctree.heading(key, text=_(label))
            self.ctree.column(key, width=max(60, width * 6))
        self.ctree.pack(fill="both", expand=True)
        self.ctree.bind("<<TreeviewSelect>>", self._pick_character)
        self.cvars: dict[str, tk.StringVar] = {}
        grid = ttk.Frame(frm)
        grid.pack(fill="x", pady=(6, 0))
        for i, (key, label, width) in enumerate(self.CHAR_FIELDS):
            r, c = divmod(i, 4)
            name = ttk.Label(grid, text=_(label) + ":")
            name.grid(row=r * 2, column=c, sticky="w", padx=(0, 6))
            var = tk.StringVar()
            self.cvars[key] = var
            entry = ttk.Entry(grid, textvariable=var, width=width + 4)
            entry.grid(row=r * 2 + 1, column=c, sticky="we", padx=(0, 10), pady=(0, 4))
            if key in FIELD_TIPS:
                tip(_(FIELD_TIPS[key]), name, entry)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text=_("Add / update character"), command=self._set_character).pack(side="left")
        ttk.Button(btns, text=_("Remove selected"), command=self._remove_character).pack(side="left", padx=(6, 0))

    def _pick_character(self, _e: Any) -> None:
        for item in self.ctree.selection():
            name = self.ctree.item(item, "text")
            c = next((x for x in self.glossary.characters if x.name == name), None)
            if c is None:
                return
            for key in self.cvars:
                if key == "addresses":
                    self.cvars[key].set("; ".join(f"{k}={v}" for k, v in c.addresses.items()))
                else:
                    self.cvars[key].set(getattr(c, key))
            break

    def _set_character(self) -> None:
        values = {k: v.get().strip() for k, v in self.cvars.items()}
        if not values["name"]:
            caches.tell(self, _("A character needs a name."), icon="info")
            return
        addresses: dict[str, str] = {}
        for part in values.pop("addresses").split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip() and v.strip():
                    addresses[k.strip()] = v.strip()
        before = self.glossary.to_json()
        self.glossary.set_character(CharacterSheet(addresses=addresses, **values))
        self._save(before)

    def _remove_character(self) -> None:
        names = [self.ctree.item(item, "text") for item in self.ctree.selection()]
        if not names or not self._removal_asked("characters", names):
            return
        before = self.glossary.to_json()
        for name in names:
            self.glossary.remove_character(name)
        self._save(before)

    # style
    def _build_style(self, nb: ttk.Notebook) -> None:
        frm = ttk.Frame(nb, padding=6)
        nb.add(frm, text=_("Style guide"))
        row = ttk.Frame(frm)
        row.pack(fill="x")
        label = ttk.Label(row, text=_("Honorifics:"))
        label.pack(side="left")
        self.hon_var = tk.StringVar(value=honorific_word(self.glossary.style.honorifics))
        words = [honorific_word(p) for p in HONORIFIC_POLICIES]
        honorifics = ttk.Combobox(row, textvariable=self.hon_var, values=words, state="readonly")
        fit_combobox(honorifics, words)
        honorifics.pack(side="left", padx=(4, 12))
        tip(_("How honorifics such as -san and -chan are carried over."), label, honorifics)
        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=(8, 0))
        label = ttk.Label(row2, text=_("Tone:"))
        label.pack(side="left")
        self.tone_var = tk.StringVar(value=self.glossary.style.tone)
        entry = ttk.Entry(row2, textvariable=self.tone_var, width=70)
        entry.pack(side="left", padx=(4, 0))
        tip(_("How the series should sound, in a few words."), label, entry)
        row3 = ttk.Frame(frm)
        row3.pack(fill="x", pady=(8, 0))
        label = ttk.Label(row3, text=_("Lettering font:"))
        label.pack(side="left")
        self.font_var = tk.StringVar(value=self.glossary.style.font)
        entry = self._font_box(row3, self.font_var, 28)
        entry.pack(side="left", padx=(4, 0))
        tip(_("(a font installed on this computer, by family name, e.g. Comic Neue; empty = automatic)").strip(BRACKETS), label, entry)
        self.font_star = self._star(row3, self.font_var)
        if self.font_star is not None:
            self.font_star.pack(side="left", padx=(2, 6))
        self.font_status = ttk.Label(frm, text="")
        self.font_status.pack(anchor="w", pady=(2, 0))
        self.font_var.trace_add("write", lambda *_a: self._check_font())
        self._check_font()
        ttk.Label(frm, text=_("Lettering by kind (text marked as thought, shout, narration, handwritten or sound effect; stressed words marked *like this* are set in bold italic):"),
                  wraplength=820, justify="left").pack(anchor="w", pady=(8, 0))
        grid = ttk.Frame(frm)
        grid.pack(fill="x")
        self.kind_vars: dict[str, tuple[tk.StringVar, tk.BooleanVar, tk.BooleanVar]] = {}
        self.kind_status: dict[str, ttk.Label] = {}
        self.kind_inks: dict[str, tuple[InkChoice, tk.StringVar, InkChoice]] = {}  # text colour, outline, its colour
        for column, word in INK_HEADINGS:
            ttk.Label(grid, text=_(word)).grid(row=0, column=column, sticky="w", padx=(0, 6))
        for i, kind in enumerate(LETTERING_KINDS, start=1):
            ls = self.glossary.style.lettering_for(kind)
            fv, iv, bv = tk.StringVar(value=ls.font), tk.BooleanVar(value=ls.italic), tk.BooleanVar(value=ls.bold)
            self.kind_vars[kind] = (fv, iv, bv)
            ttk.Label(grid, text=_(REGION_KIND_WORDS.get(kind, kind))).grid(row=i, column=0, sticky="w", pady=1)
            cell = ttk.Frame(grid)
            cell.grid(row=i, column=1, sticky="w", padx=(6, 6), pady=1)
            entry = self._font_box(cell, fv, 24)
            entry.pack(side="left")
            tip(_("(font family per kind; empty = the lettering font above)").strip(BRACKETS), entry)
            star = self._star(cell, fv)
            if star is not None:
                star.pack(side="left", padx=(2, 0))
            ttk.Checkbutton(grid, text=_("italic"), variable=iv).grid(row=i, column=2, sticky="w")
            ttk.Checkbutton(grid, text=_("bold"), variable=bv).grid(row=i, column=3, sticky="w", padx=(6, 6))
            self._build_kind_ink(grid, i, kind, ls)
            status = ttk.Label(grid, text="")
            status.grid(row=i, column=7, sticky="w")
            self.kind_status[kind] = status
            fv.trace_add("write", lambda *_a, k=kind: self._check_kind_font(k))
            self._check_kind_font(kind)
        ttk.Label(frm, text=_("House rules, one per line (short policies, never lines of the book):")).pack(anchor="w", pady=(8, 0))
        self.rules = tk.Text(frm, height=5, wrap="word", font="TkDefaultFont")
        self.rules.pack(fill="both", expand=True)
        self.rules.insert("1.0", "\n".join(self.glossary.style.rules))
        ttk.Button(frm, text=_("Save style guide"), command=self._set_style).pack(anchor="w", pady=(6, 0))

    def _font_box(self, parent: tk.Misc, var: tk.StringVar, width: int) -> ttk.Combobox:
        """A font field: any family name may be typed, and its list (`_fill_fonts`, as it opens) has the starred and
        recently used families first, then the installed ones."""
        box = ttk.Combobox(parent, textvariable=var, width=width, values=font_choices(self.font_memory))
        box.configure(postcommand=lambda b=box: self._fill_fonts(b))
        self.font_boxes.append(box)
        return box

    def _fill_fonts(self, box: ttk.Combobox) -> None:
        """A font list as it opens: the starred and recently used families, then the installed ones (looked up the
        first time a list opens: it takes a moment)."""
        if self._families is None:
            try:
                self._families = font_families(self.fonts_dir)
            except Exception:  # noqa: BLE001 - a typed name still works
                self._families = []
        box.configure(values=font_choices(self.font_memory, self._families))

    def _star(self, parent: tk.Misc, var: tk.StringVar) -> StarButton | None:
        """☆ / ★ beside a font field (with *font_memory*): the family it names starred, first in every font list."""
        if self.font_memory is None:
            return None
        return StarButton(parent, var, self.font_memory)

    def _build_kind_ink(self, grid: ttk.Frame, row: int, kind: str, ls: LetteringStyle) -> None:
        """A kind's ink in its row (columns 4 to 6, under `INK_HEADINGS`): the text colour, the outline (Auto, On,
        Off) and the outline's colour, which a region's own in the region editor overrides."""
        colour = InkChoice(grid, ls.colour)
        colour.frame.grid(row=row, column=4, sticky="w", padx=(0, 6))
        tip(_(KIND_INK_TIPS["colour"]), colour.box)
        words = outline_words()
        outline = tk.StringVar(grid, value=_(OUTLINE_WORDS[ls.outline]))
        box = ttk.Combobox(grid, textvariable=outline, values=words, state="readonly")
        fit_combobox(box, words, min_chars=5)
        box.grid(row=row, column=5, sticky="w", padx=(0, 6))
        tip(_(KIND_INK_TIPS["outline"]), box)
        rim = InkChoice(grid, ls.outline_colour)
        rim.frame.grid(row=row, column=6, sticky="w", padx=(0, 6))
        tip(_(KIND_INK_TIPS["outline_colour"]), rim.box)
        self.kind_inks[kind] = (colour, outline, rim)

    def _kind_ink(self, kind: str) -> dict[str, Any]:
        """A kind's ink as its row shows it, as `LetteringStyle`'s fields."""
        colour, outline, rim = self.kind_inks[kind]
        return {"colour": colour.get(), "outline": outline_of(outline.get()), "outline_colour": rim.get()}

    def _check_font(self) -> None:
        """Under the font entry: whether the font is installed on this computer (a warning when it is not)."""
        name = self.font_var.get().strip()
        if not name:
            self.font_status.configure(text="", foreground="")
            return
        spec = resolve_font(name, self.fonts_dir)
        if spec:
            self.font_status.configure(text=_("Installed here: {file}").format(file=Path(split_face(spec.path)[0]).name), foreground="")
        else:
            self.font_status.configure(text=_("Not installed on this computer: the automatic font is used instead."),
                                       foreground="#c03030")

    def _check_kind_font(self, kind: str) -> None:
        """Beside a kind's font entry: whether that font is installed on this computer."""
        name = self.kind_vars[kind][0].get().strip()
        label = self.kind_status[kind]
        if not name:
            label.configure(text="", foreground="")
            return
        spec = resolve_font(name, self.fonts_dir)
        if spec:
            label.configure(text=_("Installed here: {file}").format(file=Path(split_face(spec.path)[0]).name), foreground="")
        else:
            label.configure(text=_("Not installed on this computer: the automatic font is used instead."), foreground="#c03030")

    def _style_shown(self) -> StyleGuide:
        """The style guide as its fields show it."""
        rules = [line.strip() for line in self.rules.get("1.0", "end").splitlines() if line.strip()]
        lettering = {kind: LetteringStyle(font=fv.get().strip()[:60], italic=iv.get(), bold=bv.get(),
                                          **self._kind_ink(kind))
                     for kind, (fv, iv, bv) in self.kind_vars.items()}
        return StyleGuide(honorifics=honorific_policy(self.hon_var.get().strip()), tone=self.tone_var.get().strip(), rules=rules,
                          font=self.font_var.get().strip()[:60], lettering=lettering)

    def _set_style(self) -> None:
        shown = self._style_shown()
        # the fields name every kind's lettering, the sheet only those set: the same style is no change for Undo
        before = None if same_style(shown, self.glossary.style) else self.glossary.to_json()
        self.glossary.style = self._style_kept = shown
        if self.font_memory is not None:  # the fonts the sheet sets: the newest of those used last
            self.font_memory.used(*(ls.font for ls in shown.lettering.values()), shown.font)
        self._save(before)

    def _show_style(self) -> None:
        """The style guide's fields as the sheet has it (after Undo)."""
        style = self.glossary.style
        self.hon_var.set(honorific_word(style.honorifics))
        self.tone_var.set(style.tone)
        self.font_var.set(style.font)
        for kind, (fv, iv, bv) in self.kind_vars.items():
            ls = style.lettering_for(kind)
            fv.set(ls.font)
            iv.set(ls.italic)
            bv.set(ls.bold)
            colour, outline, rim = self.kind_inks[kind]
            colour.set(ls.colour)
            outline.set(_(OUTLINE_WORDS[ls.outline]))
            rim.set(ls.outline_colour)
        self.rules.delete("1.0", "end")
        self.rules.insert("1.0", "\n".join(style.rules))
        self._style_kept = self._style_shown()

    def undo(self) -> None:
        """Undo: the sheet as it was before the last change made in this window, saved; once (Undo is then disabled
        until the next change)."""
        if self._undo is None:
            return
        back, self._undo = self._undo, None
        was = self.glossary.to_json()
        self.glossary.entries, self.glossary.characters = [], []
        self.glossary.apply_json(back)
        self._show_style()
        self._save(was=was)
        self.undo_btn.configure(state="disabled")

    def _close(self) -> None:
        """Close, and the window's close button: a style guide changed in the fields is saved, as "Save style guide"
        does, not dropped."""
        if self._style_shown() != self._style_kept:
            self._set_style()
        self.destroy()

    # common
    def _fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for e in self.glossary.entries:
            self.tree.insert("", "end", text=e.term, values=(e.rendering, e.note))
        self.ctree.delete(*self.ctree.get_children())
        for c in self.glossary.characters:
            self.ctree.insert("", "end", text=c.name, values=(
                c.rendering, c.gender, c.age, c.pronoun, c.style, c.role, "; ".join(f"{k}={v}" for k, v in c.addresses.items())))

    def _save(self, before: dict[str, Any] | None = None, was: dict[str, Any] | None = None) -> None:
        """Write the sheet and show it; *before* (the sheet before the change) is what Undo puts back next. Once it is
        written, the renderings changed since *before* (or *was*, the sheet Undo replaced) go to *on_renamed*."""
        now = self.glossary.to_json()
        if before is not None and before != now:
            self._undo = before
            self.undo_btn.configure(state="normal")
        was = was if was is not None else before
        try:
            self.glossary.save()
        except OSError as e:
            caches.tell(self, _("Could not save the series sheet: {error}").format(error=e))
            was = None  # the lines stay as they are while the sheet is not written
        self._fill()
        self.on_change()
        pairs = renamed_pairs(was, now) if was is not None and self.on_renamed is not None else []
        if pairs:
            self.on_renamed(pairs, self)
