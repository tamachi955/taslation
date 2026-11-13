"""Before a book is read: its name and, in whole-book mode, whether to read the whole book first (`StartDialog`); the
names a window's title gives that name no book (`generic_book_name`, from `bookid`: a browser-based viewer's tab
can be titled with the viewer's name, so every book read there would share one cache, one series sheet and one notes
file; which names are a viewer's is learned on the reader's computer, `viewerparts`); the name
the book's colophon gives, offered once (`ColophonOffer`). Wherever whole-book mode is chosen, what a store's terms
make of it is said too (`terms_note`)."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from ... import viewerparts
from ...bookid import GENERIC_NAMES, generic_book_name
from ...i18n import _
from ...notes import TEMPORARY_STAMP
from ..banner import break_lines
from ..layout import dialog_keys, place_by_book

WRAP = 470  # pixels: the dialog's text is broken into lines this wide
HINTS = ("recognised", "several", "colophon", "last")  # what the start dialog says of the names it offers


def terms_note() -> str:
    """What a store's terms make of whole-book mode, in the window's language: said wherever that mode is chosen (the
    start dialog's question, the whole-book dialog). It says what TASlation does and promises nothing of the terms."""
    return _("A store's terms of use are a contract between you and the store. In a whole-book run TASlation turns no page: it reads only the pages you turn yourself. That does not settle what your store's terms allow, so check them and use this mode knowing that.")


class StartDialog(tk.Toplevel):
    """The start of a book, centred over the window and modal: its name (*name*, prefilled; empty and required when
    the window's title gives a generic one, *generic*) and, with *ask*, the question whether to read the whole book
    first, with what a store's terms make of it (`terms_note`), [Start] [Page by page instead]; without *ask* the name
    alone, with [OK]. The buttons wait for a name, and never take one that names no book (`generic_book_name`).
    *on_answer(answer, name)* gets "start", "page" or "ok" and the name - or None when the dialog is closed without an
    answer (Esc, the window's close button). Enter gives *default*: "page" (the lighter choice: nothing runs that the
    reader did not choose), or "start" when the reader chose to read this book whole before (`JobsMixin._ask_book`).

    With a generic title, *matches* are the names the book may have, best first (`bookid.recognise`: books whose
    pages look like the one on screen; or the name its colophon gives; or the name last given in this viewer), and
    *hint* says where they come from (unless the colophon gave the name, a tick takes the title from the colophon
    instead: the name field rests, and a temporary name holds the book's files until `ColophonOffer` renames them):
    one name is filled in ("recognised": from a page already translated;
    "colophon": from the colophon; "last": the book read last time with this viewer, `bookid.last_name`), several
    are offered in the name field's list with an empty field ("several")."""

    def __init__(self, master: tk.Misc, name: str, generic: bool, ask: bool,
                 on_answer: Callable[[str | None, str], None], matches: Sequence[str] = (), hint: str = "",
                 default: str = "page"):
        super().__init__(master)
        self.title("TASlation")
        self.transient(master)
        self.resizable(False, False)
        self.on_answer = on_answer
        self.answered = False
        self.ask = ask
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        offered = [m for m in dict.fromkeys(" ".join(str(m).split()) for m in matches) if m and not generic_book_name(m)]
        self.matches = offered if generic else []
        single = generic and len(self.matches) == 1
        self.name_var = tk.StringVar(self, value=self.matches[0] if single else "" if generic else " ".join(str(name).split()))
        self.hint_label: ttk.Label | None = None
        # ticked: no name to type; a temporary one holds the book's files until the colophon's name is offered
        self.from_colophon = tk.BooleanVar(self, value=False)
        self.temporary = f'{_("Untitled book")} {time.strftime(TEMPORARY_STAMP)}'
        if generic:
            label = ttk.Label(frm, justify="left")
            label.configure(text=break_lines(_("What is this book called? TASlation keeps this book's translations under this name."), WRAP, label))
            label.pack(anchor="w")
            if len(self.matches) > 1:  # several books look like this one: the list offers them, the field stays empty
                self.entry = ttk.Combobox(frm, textvariable=self.name_var, values=self.matches, width=50)
            else:
                self.entry = ttk.Entry(frm, textvariable=self.name_var, width=52)
            self.entry.pack(fill="x", pady=(6, 0))
            said = ""
            if single and hint == "colophon":
                said = _("The last page of the book says this is {book}; change it if that is wrong.").format(book=self.matches[0])
            elif single and hint == "last":
                said = _("Last time with this viewer: {book} - change it if that is wrong.").format(book=self.matches[0])
            elif single:
                said = _("Recognised as {book} from a page already translated; change it if that is wrong.").format(book=self.matches[0])
            elif len(self.matches) > 1:
                said = _("Pages already translated in several books look like this one: pick the book in the list, or type its name.")
            if said:
                self.hint_label = ttk.Label(frm, justify="left")
                self.hint_label.configure(text=break_lines(said, WRAP, self.hint_label))
                self.hint_label.pack(anchor="w", pady=(4, 0))
            if hint != "colophon":
                ttk.Checkbutton(frm, text=_("Take the title from the last page of the book"),
                                variable=self.from_colophon, command=self._sync).pack(anchor="w", pady=(6, 0))
        else:
            row = ttk.Frame(frm)
            row.pack(fill="x")
            ttk.Label(row, text=_("Book:")).pack(side="left")
            self.entry = ttk.Entry(row, textvariable=self.name_var, width=46)
            self.entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        if ask:
            question = ttk.Label(frm, justify="left")
            question.configure(text=break_lines(_("Read the whole book first? Turn the pages at your own pace, in the viewer or with the page keys in this window: TASlation reads each page you turn, and never turns one itself. When you reach the end, press Finished reading, and it translates the whole book with the whole story in view (about an hour for a 190-page volume on a mid-range GPU). Stop ends the run at any time."), WRAP, question))
            question.pack(anchor="w", pady=(14, 0))
            self.terms_label = ttk.Label(frm, justify="left")
            self.terms_label.configure(text=break_lines(terms_note(), WRAP, self.terms_label))
            self.terms_label.pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(14, 0))
        if ask:
            self.default = "start" if default == "start" else "page"
            page = ttk.Button(row, text=_("Page by page instead"), command=lambda: self._answer("page"),
                              default="active" if self.default == "page" else "normal")
            start = ttk.Button(row, text=_("Start"), command=lambda: self._answer("start"),
                               default="active" if self.default == "start" else "normal")
            page.pack(side="right")
            start.pack(side="right", padx=(0, 6))
            self.buttons = [start, page]
        else:
            self.default = "ok"
            ok = ttk.Button(row, text=_("OK"), default="active", command=lambda: self._answer("ok"))
            ok.pack(side="right")
            self.buttons = [ok]
        self.name_var.trace_add("write", lambda *_args: self._sync())
        self._sync()
        self.bind("<Return>", lambda _e: self._answer(self.default))
        self.bind("<KP_Enter>", lambda _e: self._answer(self.default))
        self.bind("<Escape>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Map>", self._on_map, add="+")
        self._keys_given = False
        place_by_book(self, master)  # where the reader looks: over a book full screen on another monitor too
        self.entry.focus_set()
        self.entry.icursor("end")

    def name(self) -> str:
        return self.temporary if self.from_colophon.get() else " ".join(self.name_var.get().split())

    def _usable(self) -> bool:
        """A name that names a book (none of `GENERIC_NAMES`, no viewer's name: nothing is kept under those); the
        title's name held back until the reader says what the book is called (`viewerparts.held`) is one: taking it
        says that the title is the book's."""
        name = self.name()
        return not generic_book_name(name) or viewerparts.held(name)

    def _sync(self) -> None:
        """The buttons wait for a name that names a book; the name field rests while the colophon is to give it."""
        self.entry.configure(state="disabled" if self.from_colophon.get() else "normal")
        state = "normal" if self._usable() else "disabled"
        for button in self.buttons:
            button.configure(state=state)

    def _on_map(self, event: tk.Event) -> None:
        """On the screen: modal over the window; the keys only when TASlation had them (Auto may find the page while
        the reader is in the book: then the dialog waits in sight above it for a click, `dialog_keys`)."""
        if event.widget is not self:
            return
        try:
            self.grab_set()
        except tk.TclError:
            pass
        if not self._keys_given:
            self._keys_given = True
            dialog_keys(self, self.master, self.entry)

    def _answer(self, answer: str) -> None:
        if self.answered:
            return
        name = self.name()
        if not self._usable():
            self.bell()
            self.entry.focus_set()
            return
        self.answered = True
        self.destroy()
        self.on_answer(answer, name)

    def _close(self) -> None:
        if self.answered:
            return
        self.answered = True
        name = self.name()
        self.destroy()
        self.on_answer(None, name)


class ColophonOffer(tk.Toplevel):
    """The name the book's colophon gives (*title*, *volume*), offered once over the window, modal: [Use] [Keep].
    *on_answer(True)* for Use, *on_answer(False)* for Keep and when the dialog is closed (it was offered)."""

    def __init__(self, master: tk.Misc, title: str, volume: str, on_answer: Callable[[bool], None]):
        super().__init__(master)
        self.title(_("Book"))
        self.transient(master)
        self.resizable(False, False)
        self.on_answer = on_answer
        self.answered = False
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        if volume:
            text = _("The last page of the book says this is {title} ({volume}). Use this name?").format(title=title, volume=volume)
        else:
            text = _("The last page of the book says this is {title}. Use this name?").format(title=title)
        self.label = ttk.Label(frm, justify="left")
        self.label.configure(text=break_lines(text, WRAP, self.label))
        self.label.pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(14, 0))
        keep = ttk.Button(row, text=_("Keep"), command=lambda: self._answer(False))
        use = ttk.Button(row, text=_("Use"), default="active", command=lambda: self._answer(True))
        keep.pack(side="right")
        use.pack(side="right", padx=(0, 6))
        self.buttons = [use, keep]
        self.bind("<Return>", lambda _e: self._answer(True))
        self.bind("<KP_Enter>", lambda _e: self._answer(True))
        self.bind("<Escape>", lambda _e: self._answer(False))
        self.protocol("WM_DELETE_WINDOW", lambda: self._answer(False))
        self.bind("<Map>", self._on_map, add="+")
        self._keys_given = False
        place_by_book(self, master)

    def _on_map(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        try:
            self.grab_set()
        except tk.TclError:
            pass
        if not self._keys_given:  # offered by itself after a run: the keys only when TASlation had them
            self._keys_given = True
            dialog_keys(self, self.master)

    def _answer(self, use: bool) -> None:
        if self.answered:
            return
        self.answered = True
        self.destroy()
        self.on_answer(use)


__all__ = ["ColophonOffer", "GENERIC_NAMES", "HINTS", "StartDialog", "WRAP", "generic_book_name",
           "terms_note"]
