"""Before a book is read: its name (`StartDialog`); the names a window's title gives that name no book
(`generic_book_name`, from `bookid`: a browser-based viewer's tab can be titled with the viewer's name, so every book
read there would share one cache, one series sheet and one notes file; which names are a viewer's is learned on the
reader's computer, `viewerparts`); the name the book's colophon gives, offered once (`ColophonOffer`); the one spelling
of a book's name, offered for a book kept under an older one (`StandardNameOffer`). The name is asked and shown as
Series and Volume (`book_fields`)."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from ... import viewerparts
from ...bookid import GENERIC_NAMES, generic_book_name
from ...i18n import _
from ...notes import TEMPORARY_STAMP
from .. import theme
from ..banner import break_lines
from ..book_fields import BookFields, refused_line
from ..layout import dialog_keys, place_by_book

WRAP = 470  # pixels: the dialog's text is broken into lines this wide
HINTS = ("recognised", "several", "colophon", "last")  # what the start dialog says of the names it offers


class StartDialog(tk.Toplevel):
    """The start of a book, centred over the window and modal: its name (*name*, prefilled; empty and required when
    the window's title gives a generic one, *generic*), with [OK], which Enter presses. The button waits for a name,
    and never takes one that names no book (`generic_book_name`). *on_answer(answer, name)* gets "ok" and the name -
    or None when the dialog is closed without an answer (Esc, the window's close button).

    With a generic title, *matches* are the names the book may have, best first (`bookid.recognise`: books whose
    pages look like the one on screen; or the name its colophon gives; or the name last given in this viewer), and
    *hint* says where they come from (unless the colophon gave the name, a tick takes the title from the colophon
    instead: the name field rests, and a temporary name holds the book's files until `ColophonOffer` renames them):
    one name is filled in ("recognised": from a page already translated;
    "colophon": from the colophon; "last": the book read last time with this viewer, `bookid.last_name`), several
    are offered in the name field's list with an empty field ("several").

    The name is asked as two fields, Series and Volume (`book_fields.BookFields`, bound to ``name_var``, the name they
    make; ``entry`` is the Series field, a list of whole names with several *matches*): a name given is split into
    them, and a volume that is none keeps the dialog from answering, with a line that says why."""

    def __init__(self, master: tk.Misc, name: str, generic: bool, on_answer: Callable[[str | None, str], None],
                 matches: Sequence[str] = (), hint: str = ""):
        super().__init__(master)
        self.title("TASlation")
        self.transient(master)
        self.resizable(False, False)
        self.on_answer = on_answer
        self.answered = False
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
            # several books look like this one: the Series field's list offers them, the fields stay empty
            self.fields = BookFields(frm, self.name_var, series_chars=40, on_refused=self._refused,
                                     matches=self.matches if len(self.matches) > 1 else ())
            self.fields.pack(fill="x", pady=(6, 0))
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
            self.fields = BookFields(frm, self.name_var, series_chars=36, on_refused=self._refused)
            self.fields.pack(fill="x")
        self.entry = self.fields.series
        self.refused_label = ttk.Label(frm, justify="left", foreground=theme.colour("error"))  # shown when a volume is refused
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(14, 0))
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
        """The buttons wait for a name that names a book; the name fields rest while the colophon is to give it."""
        self.fields.set_state("disabled" if self.from_colophon.get() else "normal")
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

    def _refused(self, text: str) -> None:
        """The Volume field held no volume: said under the fields, which wait for one."""
        self.bell()
        self.refused_label.configure(text=break_lines(refused_line(text), WRAP, self.refused_label))
        if not self.refused_label.winfo_manager():
            self.refused_label.pack(anchor="w", pady=(4, 0), after=self.fields)
        self.fields.volume.focus_set()

    def _answer(self, answer: str) -> None:
        if self.answered:
            return
        if not self.from_colophon.get() and not self.fields.commit():
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
    """The name the book's colophon gives (*title*, *volume*), offered once over the window, modal, in the Series and
    Volume fields for the reader to correct (`book_fields.BookFields`): [Use] [Keep]. *on_answer(True, name)* for Use
    with the name the fields make, *on_answer(False, None)* for Keep and when the dialog is closed (it was offered).
    Use waits while the Volume field holds no volume, with a line that says why."""

    def __init__(self, master: tk.Misc, title: str, volume: str, on_answer: Callable[[bool, str | None], None]):
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
        self.name_var = tk.StringVar(self)
        self.fields = BookFields(frm, self.name_var, series_chars=36, on_refused=self._refused)
        self.fields.set_parts(title, volume)
        self.fields.pack(fill="x", pady=(10, 0))
        self.refused_label = ttk.Label(frm, justify="left", foreground=theme.colour("error"))
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
        if not self._keys_given:  # offered by itself after a page: the keys only when TASlation had them
            self._keys_given = True
            dialog_keys(self, self.master)

    def _refused(self, text: str) -> None:
        """The Volume field held no volume: said under the fields, which wait for one."""
        self.bell()
        self.refused_label.configure(text=break_lines(refused_line(text), WRAP, self.refused_label))
        if not self.refused_label.winfo_manager():
            self.refused_label.pack(anchor="w", pady=(4, 0), after=self.fields)
        self.fields.volume.focus_set()

    def name(self) -> str:
        """The name the Series and Volume fields make."""
        return " ".join(self.name_var.get().split())

    def _answer(self, use: bool) -> None:
        if self.answered:
            return
        if use and (not self.fields.commit() or not self.name() or generic_book_name(self.name())):
            return
        self.answered = True
        name = self.name() if use else None
        self.destroy()
        self.on_answer(use, name)


class StandardNameOffer(tk.Toplevel):
    """A book whose files are kept under an older spelling of its name (*old*: "Title 3巻", from before the Series and
    Volume fields), offered once a session over the window, modal, to be renamed to the one spelling its fields make
    (*new*: "Title 3"): [Rename] [Not now]. *on_answer(True)* for Rename, *on_answer(False)* for Not now and when the
    dialog is closed. Until it is renamed the book is read and written under its old name."""

    def __init__(self, master: tk.Misc, old: str, new: str, on_answer: Callable[[bool], None]):
        super().__init__(master)
        self.title(_("Book"))
        self.transient(master)
        self.resizable(False, False)
        self.on_answer = on_answer
        self.answered = False
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        text = _("This book's files are kept under {old}, a spelling from before the Series and Volume fields. Rename the book to {new}? Its translations, notes and sheet move along; until then everything is found under the old name.").format(old=old, new=new)
        self.label = ttk.Label(frm, justify="left")
        self.label.configure(text=break_lines(text, WRAP, self.label))
        self.label.pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(14, 0))
        later = ttk.Button(row, text=_("Not now"), command=lambda: self._answer(False))
        rename = ttk.Button(row, text=_("Rename"), default="active", command=lambda: self._answer(True))
        later.pack(side="right")
        rename.pack(side="right", padx=(0, 6))
        self.buttons = [rename, later]
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
        if not self._keys_given:  # offered by itself after a page: the keys only when TASlation had them
            self._keys_given = True
            dialog_keys(self, self.master)

    def _answer(self, rename: bool) -> None:
        if self.answered:
            return
        self.answered = True
        self.destroy()
        self.on_answer(rename)


__all__ = ["ColophonOffer", "GENERIC_NAMES", "HINTS", "StandardNameOffer", "StartDialog", "WRAP",
           "generic_book_name"]
