"""The book's name as the window asks for it: two fields, Series and Volume (`BookFields`), wherever the name is
shown or asked - the toolbar's Book group, the start dialog, the colophon's offer - and the window's side of the one
name they make (`bookname`).

The two fields stand for one name, a StringVar (*name_var*: the toolbar's ``book_var``, which the window's stores go
by, or a dialog's own). What is typed in either field makes the name at once (`bookname.compose`: one spelling,
whatever was typed around the volume); a name set from elsewhere - a viewer's title, the colophon, a rename, the
start dialog's answer - is split into the fields (`bookname.split_name`), for the reader to correct. The Volume
field takes only a volume (`bookname.volume_of`): while what it holds is none yet ("第", "Vol."), the name stays the
last one it made; when the field is left (or Enter), it shows the volume as it is kept ("第三巻" becomes 3), or a
volume refused gives way to the one before and *on_refused* says why (`refused_line`: an edition belongs to the
series). Leaving one field for the other is not leaving the fields.

The window's side (`kept_name`, `fields_committed`, `offer_standard_name`): a name the fields or a dialog give is
the one spelling, or the spelling an older cache of the same book is kept under (`cache.CacheStore.kept_name`:
"Title 3巻" kept before the two fields, for "Title 3"), so that nothing kept under an older spelling is lost or kept
twice. Such a book is offered once per session to be renamed to the one spelling (`StandardNameOffer`, the
colophon's rename: `JobsMixin._plan_rename`, with the review where the sheets say otherwise); Not now leaves it
under its old name, where it is read and written as before."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from .. import bookname
from ..bookid import generic_book_name
from ..i18n import _
from ..notes import is_temporary_name

VOLUME_CHARS = 4  # the Volume field, in "0" widths: "10.5", "999", "前編"


def refused_line(text: str) -> str:
    """What is said of *text*, typed in the Volume field and refused (`bookname.volume_of`), in the window's
    language."""
    return _("{volume} is not a volume: the Volume field takes a number (3, 10.5) or 上, 中, 下, 前編, 後編. An edition such as 完全版 belongs to the series.").format(
        volume=" ".join(str(text).split()))


def parts_line(name: str) -> str:
    """The book's name *name* as its two fields, in a line (the rename's review)."""
    parts = bookname.split_name(name)
    if parts.volume:
        return _("Series {series}, volume {volume}").format(series=parts.series, volume=parts.volume)
    return _("Series {series}, no volume").format(series=parts.series)


class BookFields(ttk.Frame):
    """Series and Volume side by side (each after its label, with *labels*; the Volume field's shortened, *short*),
    bound both ways to *name_var* (see the module). *series_chars* and *volume_chars* are the fields' widths in "0"
    widths. With *matches* (whole names, best
    first) the Series field is a list of them, and picking one splits it into the two fields. *resolve(name)*, when
    the fields are left, gives the name to keep (the window's `kept_name`); *on_commit(name)* follows; *on_refused
    (text)* says that the Volume field's *text* is no volume (a bell without it)."""

    def __init__(self, parent: tk.Misc, name_var: tk.StringVar, *, series_chars: int, volume_chars: int = VOLUME_CHARS,
                 matches: Sequence[str] = (), labels: bool = True, short: bool = False,
                 resolve: Callable[[str], str] | None = None, on_commit: Callable[[str], None] | None = None,
                 on_refused: Callable[[str], None] | None = None):
        super().__init__(parent)
        self.name_var = name_var
        self.resolve, self.on_commit, self.on_refused = resolve, on_commit, on_refused
        self.series_var, self.volume_var = tk.StringVar(self), tk.StringVar(self)
        self._setting = False  # the fields or the name are being set from the other: the traces leave them
        self._accepted = ""  # the volume as last kept: what a refused one gives way to
        self.series_label = self.volume_label = None
        if labels:
            self.series_label = ttk.Label(self, text=_("Series:"))
            self.series_label.pack(side="left")
        if matches:
            self.series: ttk.Entry = ttk.Combobox(self, textvariable=self.series_var, values=list(matches),
                                                  width=series_chars)
            self.series.bind("<<ComboboxSelected>>", lambda _e: self._picked(), add="+")
        else:
            self.series = ttk.Entry(self, textvariable=self.series_var, width=series_chars)
        self.series.pack(side="left", fill="x", expand=True, padx=((2 if short else 4) if labels else 0, 0))
        if labels:  # (the toolbar's, *short*: its row has little room)
            self.volume_label = ttk.Label(self, text=_("Vol.:") if short else _("Volume:"))
            self.volume_label.pack(side="left", padx=(3 if short else 6, 0))
        self.volume = ttk.Entry(self, textvariable=self.volume_var, width=volume_chars)
        self.volume.pack(side="left", padx=(1 if short else 4, 0))
        for entry in (self.series, self.volume):
            entry.bind("<FocusOut>", lambda _e: self._focus_left(), add="+")
            for key in ("<Return>", "<KP_Enter>"):  # a volume refused: Enter goes no further (no dialog answers)
                entry.bind(key, lambda _e: None if self.commit() else "break", add="+")
        self._traces = [(self.name_var, self.name_var.trace_add("write", lambda *_a: self._from_name()))]
        for var in (self.series_var, self.volume_var):
            self._traces.append((var, var.trace_add("write", lambda *_a: self._from_fields())))
        self.bind("<Destroy>", self._destroyed, add="+")
        self._from_name()

    # ------------------------------------------------------------------ the two ways
    def _from_name(self) -> None:
        """The name was set from elsewhere: the fields show its two parts."""
        if self._setting:
            return
        parts = bookname.split_name(self.name_var.get())
        self._set_fields(parts.series, parts.volume)

    def _from_fields(self) -> None:
        """A field was typed in: the name they make, unless the Volume field holds no volume (yet)."""
        if self._setting:
            return
        volume = bookname.volume_of(self.volume_var.get())
        if volume is None:
            return
        self._set_name(bookname.compose(self.series_var.get(), volume))

    def _picked(self) -> None:
        """A whole name picked from the Series field's list: split into the two fields."""
        picked = self.series_var.get()
        self._set_name(" ".join(picked.split()))
        parts = bookname.split_name(picked)
        self._set_fields(parts.series, parts.volume)

    def _set_fields(self, series: str, volume: str) -> None:
        self._setting = True
        try:
            if self.series_var.get() != series:
                self.series_var.set(series)
            if self.volume_var.get() != volume:
                self.volume_var.set(volume)
            self._accepted = volume
        finally:
            self._setting = False

    def _set_name(self, name: str) -> None:
        if self.name_var.get() == name:
            return
        self._setting = True
        try:
            self.name_var.set(name)
        finally:
            self._setting = False

    # ------------------------------------------------------------------ leaving the fields
    def _focus_left(self) -> None:
        """A field lost the keys: once Tk knows where they went, the fields are left unless the other one has them."""
        self.after_idle(self._left)

    def _left(self) -> None:
        try:
            if not self.winfo_exists():
                return
            focus = self.focus_get()
        except (KeyError, tk.TclError):  # (a list's popdown, a window going)
            focus = None
        if focus is not None and focus in (self.series, self.volume):
            return
        self.commit()

    def commit(self) -> bool:
        """The fields as the reader leaves them: the volume as it is kept (or the one before, when this one is
        refused: *on_refused*, and False), the series cleaned of stray spaces, the name they make (the reader's split
        remembered where the parser's differs: `bookname.remember`) given to *resolve* and set, then *on_commit*."""
        typed = self.volume_var.get()
        volume = bookname.volume_of(typed)
        refused = volume is None
        if refused:
            volume = self._accepted
        series = bookname.clean_series(self.series_var.get())
        self._set_fields(series, volume or "")
        name = bookname.remember(series, volume) if series else ""
        if self.resolve is not None and name:
            name = self.resolve(name)
        self._set_name(name)
        if refused:
            if self.on_refused is not None:
                self.on_refused(typed)
            else:
                self.bell()
            return False
        if self.on_commit is not None:
            self.on_commit(name)
        return True

    def set_parts(self, series: str, volume: str) -> None:
        """The fields set to *series* and *volume* as they are (a colophon's: no split of the name they make guessed
        anew), and the name they make; a volume that is none (an edition) goes to the series."""
        kept = bookname.volume_of(volume)
        if kept is None:
            series, kept = f"{series} {volume}", ""
        series, volume = bookname.clean_series(series), kept
        self._set_fields(series, volume)
        self._set_name(bookname.compose(series, volume))

    def set_state(self, state: str) -> None:
        """Both fields "normal" or "disabled"."""
        for entry in (self.series, self.volume):
            entry.configure(state=state)

    def focus_series(self) -> None:
        self.series.focus_set()
        self.series.icursor("end")

    def _destroyed(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        for var, trace in self._traces:
            try:
                var.trace_remove("write", trace)
            except tk.TclError:
                pass
        self._traces = []


# ------------------------------------------------------------------ the window's side
def kept_name(window: Any, name: str) -> str:
    """The name *window* keeps the book *name* under: its one spelling (`bookname.split_name`: "Title 3" for "Title
    第3巻"), or the spelling a cache of the same book is kept under already (`cache.CacheStore.kept_name`). A name
    that names no book, or a temporary one, as it is."""
    name = " ".join(str(name or "").split())
    if not name or generic_book_name(name) or is_temporary_name(name):
        return name
    standard = bookname.split_name(name).name or name
    finder = getattr(getattr(window, "store", None), "kept_name", None)
    if finder is None:
        return standard
    try:
        return finder(standard)
    except Exception:  # noqa: BLE001 - the one spelling, as a new book has it
        return standard


def fields_committed(window: Any) -> None:
    """The toolbar's fields left by the reader: what the name says of the title (`ViewerMixin._book_typed`), and a
    book kept under an older spelling offered to be renamed (`offer_standard_name`)."""
    window._book_typed()
    offer_standard_name(window)


def offer_standard_name(window: Any) -> None:
    """The book in the toolbar, when its files are kept under a spelling other than the one its Series and Volume
    make (a cache from before the two fields: "Title 3巻"), offered once per session to be renamed to it
    (`StandardNameOffer`): Rename plans the rename as the colophon's does (`JobsMixin._plan_rename`, the review first
    where the sheets say otherwise), Not now leaves it under the old name, where it is read and written as before.
    It waits while the full screen, a dialog of the start or a run is on, or a page is being translated (the end of
    each page offers it again: "translate_done")."""
    if (getattr(window, "reading", False) or getattr(window, "_start_dialog", None) is not None
            or getattr(window, "_batching", False) or getattr(window, "batch", None) is not None
            or getattr(window, "busy", False) or getattr(window, "book_var", None) is None):
        return  # (a window part with no Book group, too)
    current = window.book_var.get().strip()
    if not current or generic_book_name(current) or is_temporary_name(current):
        return
    standard = bookname.split_name(current).name
    asked = getattr(window, "_standard_asked", None)
    if asked is None:
        asked = window._standard_asked = set()
    if not standard or standard == current or generic_book_name(standard) or current in asked:
        return
    asked.add(current)
    if not window._kept_under(current):
        return  # nothing to rename: the next name given is the one spelling
    from . import jobs

    model, language = window.model_var.get().strip(), window.lang_var.get().strip() or "English"

    def answer(rename: bool) -> None:
        window._start_dialog = None
        if rename and window.book_var.get().strip() == current:
            window._plan_rename(current, standard, model, language, None)
            return
        if not rename:
            window.say("{book} keeps its name for now; its translations are found under it as before.", book=current)
        window._resume_start()

    window._start_dialog = jobs.StandardNameOffer(window, current, standard, answer)


__all__ = ["BookFields", "VOLUME_CHARS", "fields_committed", "kept_name", "offer_standard_name", "parts_line",
           "refused_line"]
