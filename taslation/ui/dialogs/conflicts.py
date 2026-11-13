"""The rows of a review where two series sheets say otherwise (`ConflictRows`; the review of a rename whose book's
sheet joins the new series' sheet shows them: `rename_review`): what each conflict is, the two values, and a choice of
two per row. The values are shown as the sheets keep them - renderings, names, policies, the readers' own notes,
never a line of the book -, one longer than `CUT` characters cut with an ellipsis (`conflict_texts`)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Sequence

from ...annotations import Conflict, LetteringStyle
from ...i18n import _
from .review import REGION_KIND_WORDS, ink_word

CUT = 80  # a value longer than this many characters is cut, with an ellipsis
LIST_HEIGHT = 300  # pixels of rows on show before the list scrolls
CELL = 230  # a value's column wraps at this many pixels
WIDTH = 720  # the dialog's lines wrap at this many pixels
FACT_WORDS = {"rendering": "Rendering", "gender": "Gender", "age": "Age", "pronoun": "First person",
              "style": "Speech style", "role": "Role / relationships"}  # a character's facts, as the series sheet names them
POLICY_WORDS = {"honorifics": "Honorifics", "tone": "Tone", "font": "Lettering font"}


def cut(value: Any, limit: int = CUT) -> str:
    """*value* as one line of at most *limit* characters: a longer one cut, with an ellipsis."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _term(value: Any) -> str:
    rendering, note = value
    return cut(rendering) + (f" ({cut(note)})" if note else "")


def _lettering(style: LetteringStyle) -> str:
    parts = [cut(style.font, 60)] if style.font else []
    parts += [_("italic")] if style.italic else []
    parts += [_("bold")] if style.bold else []
    if style.colour:  # the kind's ink, where the sheet sets it
        parts.append(_("text colour {colour}").format(colour=ink_word(style.colour) if style.colour in ("black", "white")
                                                     else style.colour))
    if style.outline is not None:
        parts.append(_("with outline") if style.outline else _("without outline"))
    if style.outline_colour:
        parts.append(_("outline colour {colour}").format(
            colour=ink_word(style.outline_colour) if style.outline_colour in ("black", "white") else style.outline_colour))
    return ", ".join(parts) if parts else _("plain")


def conflict_texts(c: Conflict) -> tuple[str, str, str]:
    """A conflict's row in the window's language: what it is, the one sheet's value, the other's."""
    if c.area == "term":
        return _("Term: {term}").format(term=cut(c.key)), _term(c.mine), _term(c.theirs)
    if c.area == "character":
        if c.field == "addresses":
            what = _("Character {name}: how they call {other}").format(name=cut(c.key, 40), other=cut(c.sub, 40))
        else:
            what = _("Character {name}: {fact}").format(name=cut(c.key, 40), fact=_(FACT_WORDS.get(c.field, c.field)))
        return what, cut(c.mine), cut(c.theirs)
    if c.area == "style":
        if c.key == "lettering":
            kind = _(REGION_KIND_WORDS.get(c.sub, c.sub))
            return _("Style guide: lettering of {kind}").format(kind=kind), _lettering(c.mine), _lettering(c.theirs)
        return _("Style guide: {policy}").format(policy=_(POLICY_WORDS.get(c.key, c.key))), cut(c.mine), cut(c.theirs)
    return c.area, cut(c.mine), cut(c.theirs)


class ConflictRows:
    """A review's conflicts, a row each under three *headings*: what it is and the two values (*rows*, as
    `conflict_texts` gives them) and a choice of two (*words*: keep, take; each row's variable in `choices` holds
    "mine" or "theirs", from *takes* at first), in a list that scrolls once it is taller than `LIST_HEIGHT` - also
    with the mouse wheel anywhere over *dialog*. Packed into *parent*. The review of a rename (`rename_review`) shows
    its conflicts so."""

    def __init__(self, dialog: tk.Toplevel, parent: tk.Misc, rows: Sequence[tuple[str, str, str]],
                 takes: Sequence[bool], headings: Sequence[str], words: Sequence[str]):
        self.rows = list(rows)  # what each row shows
        self.choices: list[tk.StringVar] = []
        outer = ttk.Frame(parent)
        outer.pack(fill="both", expand=True)
        background = ttk.Style(dialog).lookup("TFrame", "background") or dialog.cget("background")
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, background=background)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        self.bold = tkfont.nametofont("TkDefaultFont").copy()  # the headings' face, kept while the list lives
        self.bold.configure(weight="bold")
        for column, heading in enumerate(headings):
            ttk.Label(inner, text=heading, font=self.bold).grid(row=0, column=column, sticky="w", padx=(0, 12),
                                                                pady=(0, 4))
        keep, take = words
        for i, (texts, taken) in enumerate(zip(self.rows, takes), start=1):
            var = tk.StringVar(master=dialog, value="theirs" if taken else "mine")
            for column, text in enumerate(texts):
                ttk.Label(inner, text=text, wraplength=CELL if column else CELL - 20, justify="left").grid(
                    row=i, column=column, sticky="nw", padx=(0, 12), pady=2)
            ttk.Radiobutton(inner, text=keep, value="mine", variable=var).grid(row=i, column=3, sticky="nw", pady=2)
            ttk.Radiobutton(inner, text=take, value="theirs", variable=var).grid(row=i, column=4, sticky="nw",
                                                                                padx=(8, 0), pady=2)
            self.choices.append(var)
        inner.update_idletasks()
        width, height = inner.winfo_reqwidth(), inner.winfo_reqheight()
        canvas.configure(width=width, height=min(height, LIST_HEIGHT), scrollregion=(0, 0, width, height))
        canvas.pack(side="left", fill="both", expand=True)
        if height > LIST_HEIGHT:
            bar.pack(side="right", fill="y")
        self.canvas = canvas
        dialog.bind("<MouseWheel>", self._wheel, add="+")

    def _wheel(self, event: tk.Event) -> None:
        if event.delta:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")


__all__ = ["CELL", "CUT", "ConflictRows", "LIST_HEIGHT", "WIDTH", "conflict_texts", "cut"]
