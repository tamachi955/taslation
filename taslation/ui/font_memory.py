"""The fonts the reader stars and the ones they used last, first in every font list: the region editor's Font (its
formatting bar) and the series sheet's lettering font and fonts per kind. Kept in ui.json by family name only
(`i18n.load_ui_table`, tables "fonts_starred" and "fonts_recent"; the last `MAX_RECENT` used, at most `MAX_STARRED`
starred), on this computer: no font file, no page, nothing of the book. A star (`StarButton`, ☆ or ★) beside each
font field stars or unstars the family the field names; it is a button like any other, reached with Tab and pressed
with Space."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Iterable

from ..i18n import _, load_ui_table, save_ui_entry
from .tooltip import tip

RECENT_TABLE = "fonts_recent"
STARRED_TABLE = "fonts_starred"
MAX_RECENT = 10
MAX_STARRED = 40
MAX_NAME = 60  # characters of a family name, as the annotations and the series sheet keep one
STARRED, NOT_STARRED = "★", "☆"  # ★, ☆
STAR_TIP = ("Star this font: starred fonts, then the ones used last, come first in the font lists. Press again to "
            "unstar it.")


def family_name(value: str) -> str:
    """*value* as a family name worth keeping ("" for none): one line, trimmed, at most `MAX_NAME` characters."""
    name = " ".join(str(value or "").split())
    return name[:MAX_NAME] if name and name.isprintable() else ""


class FontMemory:
    """The starred and recently used font families of the reader in the state folder *state_dir* (ui.json)."""

    def __init__(self, state_dir: Path | str):
        self.state_dir = Path(state_dir)

    def starred(self) -> list[str]:
        """The starred families, in alphabetical order."""
        return sorted(load_ui_table(self.state_dir, STARRED_TABLE), key=str.casefold)

    def recent(self) -> list[str]:
        """The families used last, the newest first."""
        return list(reversed(load_ui_table(self.state_dir, RECENT_TABLE)))

    def is_starred(self, name: str) -> bool:
        name = family_name(name)
        return bool(name) and name in load_ui_table(self.state_dir, STARRED_TABLE)

    def toggle(self, name: str) -> bool:
        """Star *name*, or unstar it when it is starred; whether it is starred now (False for no name)."""
        name = family_name(name)
        if not name:
            return False
        on = not self.is_starred(name)
        save_ui_entry(self.state_dir, STARRED_TABLE, name, "1" if on else None, keep=MAX_STARRED)
        return on

    def used(self, *names: str) -> None:
        """*names* set in a region or the series sheet: the newest of the families used last (the last one given
        the newest of all)."""
        for value in names:
            name = family_name(value)
            if name:
                save_ui_entry(self.state_dir, RECENT_TABLE, name, "1", keep=MAX_RECENT)

    def first(self) -> list[str]:
        """What a font list shows first: the starred families, then those used last that are not starred."""
        starred = self.starred()
        return starred + [n for n in self.recent() if n not in starred]


def font_choices(memory: FontMemory | None, installed: Iterable[str] = (), head: Iterable[str] = ()) -> list[str]:
    """A font list's entries: *head* (the automatic font, the name the field holds), then the starred and recent
    families (`FontMemory.first`), then *installed*; each once, where it comes first."""
    out: list[str] = []
    for name in (*head, *(memory.first() if memory is not None else ()), *installed):
        if name and name not in out:
            out.append(name)
    return out


class StarButton:
    """☆ or ★ beside a font field (its *var*): stars or unstars the family the field names in *memory*, and shows
    whether it is starred as the field changes; disabled while the field names none (empty, or one of *blank*: the
    automatic font). *on_toggle* is told after each press."""

    def __init__(self, parent: tk.Misc, var: tk.StringVar, memory: FontMemory, blank: Iterable[str] = (),
                 on_toggle: Callable[[], None] | None = None):
        self.var, self.memory, self.blank = var, memory, tuple(blank)
        self.on_toggle = on_toggle
        self.button = ttk.Button(parent, text=NOT_STARRED, width=2, command=self.press, takefocus=True)
        tip(_(STAR_TIP), self.button)
        self._trace = var.trace_add("write", lambda *_a: self.show())
        self.button.bind("<Destroy>", lambda _e: self._untrace(), add="+")
        self.show()

    def name(self) -> str:
        value = self.var.get().strip()
        return "" if value in self.blank else family_name(value)

    def show(self) -> None:
        """The star as the field's family is: ★ starred, ☆ not; disabled with no family."""
        try:
            name = self.name()
            self.button.configure(text=STARRED if name and self.memory.is_starred(name) else NOT_STARRED)
            self.button.state(["!disabled"] if name else ["disabled"])
        except tk.TclError:  # the dialog is gone
            pass

    def press(self) -> None:
        name = self.name()
        if not name:
            return
        self.memory.toggle(name)
        self.show()
        if self.on_toggle is not None:
            self.on_toggle()

    def _untrace(self) -> None:
        try:
            self.var.trace_remove("write", self._trace)
        except (tk.TclError, ValueError):
            pass

    def pack(self, **kw: object) -> None:
        self.button.pack(**kw)

    def grid(self, **kw: object) -> None:
        self.button.grid(**kw)


__all__ = ["FontMemory", "MAX_RECENT", "MAX_STARRED", "NOT_STARRED", "STARRED", "STAR_TIP", "StarButton",
           "family_name", "font_choices"]
