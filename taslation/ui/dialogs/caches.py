"""The Caches dialog (the library: list, sort, rename and delete the translation caches; export one or more of them,
with their page information and series sheets, to an encrypted file, import one), the warning it shows before an
export or an import, the passphrase it asks for, the new name it asks for (`RenameBookDialog`), and what it says
when an import fails. Also TASlation's own message box (`WarningBox`) and the two ways the whole window
uses it in place of Windows' message boxes, whose buttons speak Windows' language and which come up behind a
full-screen viewer: `ask` (a question, two buttons named for what they do) and `tell` (one OK)."""

from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable, Sequence

from ... import backup
from ...bookname import split_name
from ...capture import foreground_window, give_foreground
from ...cache import CacheStore
from ...i18n import _
from ...recycle import to_recycle_bin
from .. import theme
from ..book_fields import BookFields, refused_line
from ..layout import fit_columns, place_window, wrap_label
from ..tooltip import tip
from ..wrap import wrap_line
from .help import explain_button
from .import_review import ImportChoice, ImportReviewDialog

ERROR_COLOUR = theme.LIGHT["error"]  # a line that says what went wrong, in the light mode (`theme.colour("error")`)
WARNING_ICON = "::tk::icons::warning"  # the stock icon of Tk's own message boxes (Tk makes it as it starts)
ICONS = {"warning": (WARNING_ICON, "warning"), "info": ("::tk::icons::information", "info"),
         "question": ("::tk::icons::question", "questhead")}  # a box's icon: Tk's stock image, the bitmap without it
WARNING_CHARS = 62  # the warning box's lines are broken at so many "0" widths of its font: as many words at any DPI


# Delete in the list: what it asks (the row's book in the row's language alone, to the Recycle Bin), what it says when
# the Recycle Bin did not take the file, and what it says once it did
DELETE_QUESTION = "Move the saved translations of {book} in {language} to the Recycle Bin? Its saved translations in other languages stay. You can restore the file from the Recycle Bin."
NOT_DELETED = "Nothing was deleted: the saved translations of {book} in {language} could not go to the Recycle Bin. Open folder shows the file; delete it there if you want it gone."
IN_THE_BIN = "The saved translations of {book} in {language} are in the Recycle Bin; restore them from there to have them back."
# the same for several rows chosen at once: one question, naming how many and which (`NAMES_SHOWN` of them at most)
DELETE_MANY_QUESTION = "Move these {n} saved translations to the Recycle Bin: {names}? Each is one book in one language; the books' translations in other languages stay. You can restore the files from the Recycle Bin."
NOT_ALL_DELETED = "{n} of them could not go to the Recycle Bin and were not deleted: {names}. Open folder shows the files; delete them there if you want them gone."
IN_THE_BIN_MANY = "{n} saved translations are in the Recycle Bin; restore them from there to have them back."
NAMES_SHOWN = 5
COLUMNS = ("volume", "pages", "bubbles", "size", "language", "updated")  # the list's, after the Series (its own text)
ARROWS = (" ▲", " ▼")  # after the heading the list is sorted by, once the reader chose it: up, down
RENAME_POLL_MS = 300  # how often the list looks whether the window's rename is done


def in_lines(text: str, width: int, font: str = "TkDefaultFont") -> str:
    """*text* broken into lines of at most *width* pixels in *font*, between words or CJK characters and never inside
    a run of Latin letters such as "TASlation" (`wrap.wrap_line`), for a label of a dialog of one size: Tk breaks
    only at spaces, which leaves a short line before "TASlation" in a Japanese sentence."""
    measure = tkfont.nametofont(font).measure
    return "\n".join(line.rstrip(" ") for paragraph in text.split("\n") for line in wrap_line(paragraph, width, measure))


def box_chars(texts: Sequence[str], font: str = "TkDefaultFont") -> int:
    """The width of a box of choices (Tk counts it in "0"s of *font*) that shows the longest of *texts* whole, in
    any language: a count of characters is too narrow for Chinese, Japanese, Korean or Thai."""
    measure = tkfont.nametofont(font).measure
    zero = max(1, measure("0"))
    return max((-(-measure(text) // zero) for text in texts), default=1) + 2


def shown_time(stamp: Any) -> str:
    """A time as the lists show it: local time, YYYY-MM-DD HH:MM. TASlation writes its times in local time without a
    zone (``2026-10-30T14:05:09``), so those are only cut short; one with a zone is turned into this computer's. What
    is no time at all is shown as it is."""
    text = str(stamp)
    try:
        when = datetime.fromisoformat(text.strip())
        if when.tzinfo is not None:
            when = when.astimezone()
        return when.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OverflowError, OSError):
        return text


def shown_size(size: int) -> str:
    """A file's size as the list shows it: kilobytes (rounded up) below a megabyte, else megabytes to one decimal."""
    if size < 1024 * 1024:
        return _("{n} KB").format(n=-(-max(0, size) // 1024))
    return _("{n} MB").format(n=f"{size / (1024 * 1024):.1f}")


def names_line(entries: Sequence[dict[str, Any]]) -> str:
    """The books of *entries* (rows of the list), each with its language, `NAMES_SHOWN` at most and an ellipsis."""
    names = [f"{e.get('book', '')} ({e.get('language', '')})" for e in entries]
    return ", ".join(names[:NAMES_SHOWN]) + (", …" if len(names) > NAMES_SHOWN else "")


def _volume_key(volume: str) -> tuple[int, float, str]:
    """A volume as the list sorts it: none first, then by number (3 before 10), then the others (上, 下) by text."""
    if not volume:
        return (0, 0.0, "")
    try:
        return (1, float(volume), "")
    except ValueError:
        return (2, 0.0, volume)


def sort_key(column: str | None, entry: dict[str, Any]) -> tuple[Any, ...]:
    """Where the row of *entry* (with its "series", "volume" and "size") goes when the list is sorted by *column*
    (None: by series, then volume, then language); the series and the volume break ties."""
    series = (str(entry.get("series", "")).casefold(), _volume_key(str(entry.get("volume", ""))),
              str(entry.get("language", "")).casefold())
    if column in ("pages", "bubbles", "size"):
        return (int(entry.get(column, 0) or 0), *series)
    if column == "volume":
        return (series[1], series[0], series[2])
    if column == "language":
        return (series[2], series[0], series[1])
    if column == "updated":
        return (str(entry.get("updated", "")), *series)
    return series


def _backup_error(name: str) -> type | None:
    """An error class of taslation.backup by name, None when this version of it does not have that one."""
    found = getattr(backup, name, None)
    return found if isinstance(found, type) and issubclass(found, BaseException) else None


def import_error_text(error: BaseException) -> str:
    """What the window says when an import of an encrypted cache fails, by why it failed."""
    for name, text in (("WrongPassphrase", _("Wrong passphrase or damaged file.")),
                       ("BrokenPassphrase", _("The passphrase holds a broken or control character; type it again.")),
                       ("UnreadableExport", _("This file was written by a newer version of TASlation; update TASlation to import it.")),
                       ("TooLarge", _("The file is larger than TASlation reads; nothing was imported.")),
                       ("NameClash", _("Not imported: the file for this book already holds another book's translations (their names give the same file name). Move that file out of its folder, then import again."))):
        cls = _backup_error(name)
        if cls is not None and isinstance(error, cls):
            return text
    if _backup_error("WrongPassphrase") is None:  # a backup module that names no causes: this is the likeliest
        return _("Wrong passphrase or damaged file.")
    return _("Could not import: the file is damaged or is not a TASlation backup.")


class WarningBox(tk.Toplevel):
    """A warning that waits for an answer, as `messagebox.askokcancel` with its warning icon does, but with buttons
    in the window's language: the icon, *text* broken into lines (`in_lines`), Continue and Cancel - or the words
    *go* and *stay* say instead (what each button does). Modal over *master* and centred over it (`place_window`).
    ``answer`` turns True on Continue (also Return while Continue has the focus, as it has from the start, unless
    *stay_first*: then Cancel has it); Cancel, Escape and closing the box leave it False. *alone*: Continue only
    (*go*, OK by default), a box that tells; *icon*: "warning", "info" or "question" (`ICONS`). *choice*: a box to
    tick under the text, unticked at first; ``chosen`` turns True on Continue with it ticked."""

    def __init__(self, master: tk.Misc, title: str, text: str, go: str | None = None, stay: str | None = None,
                 stay_first: bool = False, alone: bool = False, icon: str = "warning", choice: str | None = None):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.answer = self.chosen = False
        self.message_text = text
        self.stay_first = stay_first
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        image, bitmap = ICONS.get(icon, ICONS["warning"])
        try:
            self.icon: tk.Widget = ttk.Label(frm, image=image)
        except tk.TclError:  # a Tk without its stock icons: its built-in bitmap
            self.icon = tk.Label(frm, bitmap=bitmap)
        self.icon.grid(row=0, column=0, sticky="n", padx=(0, 12))
        self.text_width = WARNING_CHARS * max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.message = ttk.Label(frm, text=in_lines(text, self.text_width), justify="left")
        self.message.grid(row=0, column=1, sticky="nw")
        self.choice_var = tk.BooleanVar(self, value=False)
        self.choice_box: ttk.Checkbutton | None = None
        if choice:
            self.choice_box = ttk.Checkbutton(frm, text=choice, variable=self.choice_var)
            self.choice_box.grid(row=1, column=1, sticky="w", pady=(10, 0))
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self.cancel_btn = ttk.Button(btns, text=stay or _("Cancel"), command=self._cancel,
                                     default="active" if stay_first else "normal")
        if alone:
            stay_first = self.stay_first = False
        else:
            self.cancel_btn.pack(side="right")
        self.continue_btn = ttk.Button(btns, text=go or (_("OK") if alone else _("Continue")),
                                       default="normal" if stay_first else "active", command=self._continue)
        self.continue_btn.pack(side="right", padx=(0, 6))
        self.bind("<Return>", self._on_return)
        self.bind("<Escape>", self._cancel)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        (self.cancel_btn if stay_first else self.continue_btn).focus_set()
        place_window(self, master)
        try:
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    def _continue(self) -> None:
        self.answer = True
        self.chosen = bool(self.choice_var.get()) if self.choice_box is not None else False
        self.destroy()

    def _cancel(self, _event: tk.Event | None = None) -> None:
        """Cancel, Escape or the box's close button: ``answer`` stays False."""
        self.answer = False
        self.destroy()

    def _on_return(self, _event: tk.Event | None = None) -> None:
        """Return presses the button that has the focus, the one that had it first unless the reader moved it."""
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        first = self.cancel_btn if self.stay_first else self.continue_btn
        (focused if focused in (self.cancel_btn, self.continue_btn) else first).invoke()


def _box(parent: tk.Misc, text: str, wait: bool, **kwargs: Any) -> WarningBox:
    """TASlation's own box over *parent* (`WarningBox`), in front and above everything - a full-screen viewer too -
    with the keys. When the viewer chosen had the foreground (a box nobody asked for, the reader in the book), the
    viewer gets it back once the box is closed. *wait*: until then (else at once, the box left to the reader)."""
    app = parent._root()
    win = getattr(app, "selected", None)
    viewer = getattr(win, "hwnd", 0) or 0
    try:
        had_viewer = bool(viewer) and foreground_window() == viewer
    except Exception:  # noqa: BLE001 - not Windows: nothing to give back
        had_viewer = False
    box = WarningBox(parent, kwargs.pop("title", "TASlation"), text, **kwargs)
    if had_viewer:
        def back(event: tk.Event) -> None:
            if event.widget is box:
                try:
                    give_foreground(viewer)
                except Exception:  # noqa: BLE001 - the viewer gone meanwhile
                    pass
        box.bind("<Destroy>", back, add="+")
    try:
        box.attributes("-topmost", True)
        box.lift()
        if had_viewer:
            box.update_idletasks()
            give_foreground(int(box.wm_frame(), 16))
    except (tk.TclError, ValueError, OSError, RuntimeError):  # (a box closed already)
        pass
    if wait and box.winfo_exists():
        parent.wait_window(box)
    return box


def ask(parent: tk.Misc, text: str, yes: str | None = None, no: str | None = None, *, title: str = "TASlation",
        no_first: bool = False, icon: str = "question") -> bool:
    """A question in TASlation's own box (in place of `messagebox.askyesno`): *yes* and *no* name what each button
    does (Continue and Cancel by default), *no_first* gives *no* the focus. Whether the reader chose *yes*."""
    return _box(parent, text, True, title=title, go=yes, stay=no, stay_first=no_first, icon=icon).answer


def ask_choice(parent: tk.Misc, text: str, choice: str, yes: str | None = None, no: str | None = None, *,
               title: str = "TASlation", no_first: bool = False, icon: str = "question") -> tuple[bool, bool]:
    """`ask` with a box to tick under the text (*choice*, unticked at first): whether the reader chose *yes*, and
    whether they ticked the box as they did."""
    box = _box(parent, text, True, title=title, go=yes, stay=no, stay_first=no_first, icon=icon, choice=choice)
    return box.answer, box.answer and box.chosen


def tell(parent: tk.Misc, text: str, *, title: str = "TASlation", icon: str = "warning", wait: bool = True) -> None:
    """What the reader should know, in TASlation's own box with one OK (in place of `messagebox.showwarning` and
    `showinfo`). *wait*: False for a box nobody asked for, so that the window goes on meanwhile."""
    _box(parent, text, wait, title=title, alone=True, icon=icon)


class PassphraseDialog(tk.Toplevel):
    """The passphrase of an encrypted cache file, typed twice for an export, below a line that says what it is: for
    an export, that without it nobody can open the file, TASlation included; for an import, the one the file was
    made with. OK waits until backup.check_passphrase takes it (long enough, no broken or control character) and
    both match; the line under the fields says, as the reader types, what it waits for (too short, counted as
    backup.passphrase_length counts; a broken or control character; the two differ, once the repeat is no longer
    the start of the first), nothing once all is well. Show unmasks both fields. ``passphrase`` stays None when the
    reader cancels."""

    def __init__(self, master: tk.Misc, confirm: bool):
        super().__init__(master)
        self.title("TASlation")
        self.transient(master)
        self.resizable(False, False)
        self.passphrase: str | None = None
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        if confirm:
            self.intro_text = _("Choose a passphrase for this backup ({min} characters or more). Without it nobody can open the file, not even TASlation – keep it safe.").format(
                min=backup.MIN_PASSPHRASE)
        else:
            self.intro_text = _("Type the passphrase this backup was made with.")
        self.intro = ttk.Label(frm, justify="left")  # its text once the fields' width is known
        self.intro.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.vars = [tk.StringVar(self) for _i in range(2 if confirm else 1)]
        self.entries: list[ttk.Entry] = []
        labels: list[ttk.Label] = []
        for i, (var, label) in enumerate(zip(self.vars, (_("Passphrase:"), _("Repeat the passphrase:")))):
            labels.append(ttk.Label(frm, text=label))
            labels[-1].grid(row=1 + i, column=0, sticky="w", pady=2)
            entry = ttk.Entry(frm, textvariable=var, show="*", width=34)
            entry.grid(row=1 + i, column=1, sticky="we", padx=(6, 0), pady=2)
            self.entries.append(entry)
            var.trace_add("write", lambda *_args: self._sync())
        row = 1 + len(self.vars)
        self.show_var = tk.BooleanVar(self, value=False)
        self.show_box = ttk.Checkbutton(frm, text=_("Show"), variable=self.show_var, command=self._show)
        self.show_box.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=(2, 0))
        self.hint_var = tk.StringVar(self, value="")
        self.hint = ttk.Label(frm, textvariable=self.hint_var, justify="left", foreground=theme.colour("error"))
        self.hint.grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        field = self.entries[0].winfo_reqwidth()
        self.intro_width = max(label.winfo_reqwidth() for label in labels) + 6 + field  # as wide as labels and fields
        self.intro.configure(text=in_lines(self.intro_text, self.intro_width))
        self.hint.configure(wraplength=self.intro_width)  # a hint of any language on one line, mostly
        self._problem: Exception | None = None
        btns = ttk.Frame(frm)
        btns.grid(row=row + 2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text=_("Cancel"), command=self.destroy).pack(side="right")
        self.ok_btn = ttk.Button(btns, text=_("OK"), command=self._ok, state="disabled")
        self.ok_btn.pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.entries[0].focus_set()
        place_window(self, master)
        self.grab_set()

    def valid(self) -> bool:
        """Whether backup.check_passphrase takes the passphrase (its reason kept when not) and both entries match."""
        first = self.vars[0].get()
        try:
            backup.check_passphrase(first)
        except backup.BackupError as e:
            self._problem = e
            return False
        self._problem = None
        return all(v.get() == first for v in self.vars)

    def broken(self) -> bool:
        """Whether the passphrase was refused for a broken or control character (not for its length)."""
        cls = _backup_error("BrokenPassphrase")
        if cls is not None:
            return isinstance(self._problem, cls)
        return self._problem is not None and len(self.vars[0].get()) >= backup.MIN_PASSPHRASE

    @staticmethod
    def length(passphrase: str) -> int:
        """The passphrase's length as the key counts it (`backup.passphrase_length`), as typed when it cannot be
        counted (a broken character, or a backup module without the helper)."""
        count = getattr(backup, "passphrase_length", None)
        try:
            return int(count(passphrase)) if count is not None else len(passphrase)
        except backup.BackupError:
            return len(passphrase)

    def hint_text(self, force: bool = False) -> str:
        """What the line under the fields says: what keeps OK disabled, or nothing: also while nothing is typed, and
        while the repeat is still being typed and so far the same, unless *force* (OK was pressed)."""
        self.valid()
        first = self.vars[0].get()
        if self.broken():
            return _("The passphrase holds a broken or control character; type it again.")
        if not force and not any(v.get() for v in self.vars):
            return ""
        length = self.length(first)
        if self._problem is not None and length < backup.MIN_PASSPHRASE:
            return _("Too short ({n} of {min})").format(n=length, min=backup.MIN_PASSPHRASE)
        if len(self.vars) > 1:
            second = self.vars[1].get()
            typing = bool(second) and len(second) < len(first) and first.startswith(second)
            if second != first and (force or (second and not typing)):
                return _("The two passphrases differ")
        return ""

    def _show(self) -> None:
        """Show: both fields unmasked, or masked again."""
        for entry in self.entries:
            entry.configure(show="" if self.show_var.get() else "*")

    def _sync(self) -> None:
        self.ok_btn.configure(state="normal" if self.valid() else "disabled")
        self.hint_var.set(self.hint_text())

    def _ok(self) -> None:
        if self.valid():
            self.passphrase = self.vars[0].get()
            self.destroy()
        else:
            self.hint_var.set(self.hint_text(force=True))


class RenameBookDialog(tk.Toplevel):
    """The new name of *book*, in the Series and Volume fields the toolbar has (`book_fields.BookFields`), over the
    Saved translations dialog: Rename (or Enter) gives it to *on_rename* when it is another name than *book* (the
    window's rename then plans it, asks where the sheets say otherwise, and moves the files); Cancel, Esc and closing
    it give nothing. A Volume field that holds no volume says why under the fields (`book_fields.refused_line`)."""

    def __init__(self, master: tk.Misc, book: str, on_rename: Callable[[str], None]):
        super().__init__(master)
        self.book, self.on_rename = book, on_rename
        self.title(_("Rename {book}").format(book=book))
        self.transient(master)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        self.text_width = WARNING_CHARS * max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        ttk.Label(frm, text=in_lines(_("The new name of {book}:").format(book=book), self.text_width),
                  justify="left").pack(anchor="w", pady=(0, 6))
        self.name_var = tk.StringVar(self, value=book)
        self.hint_var = tk.StringVar(self, value="")
        self.fields = BookFields(frm, self.name_var, series_chars=34,
                                 on_refused=lambda text: self.hint_var.set(refused_line(text)))
        self.fields.pack(fill="x")
        ttk.Label(frm, textvariable=self.hint_var, foreground=theme.colour("error"), wraplength=self.text_width,
                  justify="left").pack(anchor="w", pady=(4, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text=_("Cancel"), command=self.destroy).pack(side="right")
        self.rename_btn = ttk.Button(btns, text=_("Rename"), command=self.apply, default="active")
        self.rename_btn.pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda _e: self.apply())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.fields.focus_series()
        place_window(self, master)
        try:
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    def apply(self) -> None:
        """Rename: the fields as they are left (a refused volume keeps the dialog open), then *on_rename* with the
        name they make, unless it is none or the book's own."""
        if not self.winfo_exists() or not self.fields.commit():
            return
        new = " ".join(self.name_var.get().split())
        self.destroy()
        if new and new != self.book:
            self.on_rename(new)


class CachesDialog(tk.Toplevel):
    """The library of saved translations (text-only files, one per book and language): a row each, with its Series
    and Volume (`bookname.split_name`, a name kept under an older spelling too), pages, bubbles, the file's size,
    language and last change (in local time, `shown_time`), and under the list how many files, pages and bytes in all.
    A click on a heading sorts the list by it (again: the other way round); at first it goes by series, volume and
    language. Ctrl+click and Shift+click choose several rows, Ctrl+A all of them.

    Delete moves the files of the rows chosen, each book in its row's language alone, to the Recycle Bin
    (`recycle.to_recycle_bin`), after one question that says so (one book: which; several: how many and which; Keep
    them has the focus); when the bin does not take a file nothing of it is deleted and the dialog says so. Rename...
    gives the one book chosen a new name in its Series and Volume fields (`RenameBookDialog`) and hands it to the
    window's rename (*rename*, by default the window's `_plan_rename`: the rename's review where the sheets say
    otherwise, then its files moved), and the list follows once the window is done. Open folder shows where the files
    are.

    Export writes the rows chosen to one file encrypted with a passphrase, each book with its page information, the
    series sheet it reads and its series' defaults (`backup.export_books`; the stores are the window's, *annotations*
    and *sheets*, else the caches alone); Import reads one back (`backup.open_export`, `backup.plan_import`), after a
    review (`import_review.ImportReviewDialog`) when the file holds several books or meets corrections, page
    information, series' defaults or sheet values of the reader's own, and imports what the reader chose
    (`backup.apply_import`). A line above Export and
    Import says what such a file is for and that it holds the translated text; each of them first shows a warning
    (`WarningBox`) before it asks for a file: an export's file holds the book's translated text and is for the reader
    alone, an import is only of a file the reader made; Cancel there does nothing else. The line below them says what
    the last export or import did (the file's name and the pages; the list is filled again, the books selected), or,
    from the start, that both need the optional cryptography package when it is not installed (both disabled then).
    The dialog takes the size of what it shows in the window's language: the columns as wide as their headings and
    cells, the explanations wrapped to the dialog's width."""

    def __init__(self, master: tk.Misc, store: CacheStore,
                 on_changed: Callable[[str], None] | None = None, on_status: Callable[[str], None] | None = None,
                 *, annotations: Any = None, sheets: Any = None,
                 rename: Callable[[str, str, str, str, Any], None] | None = None):
        super().__init__(master)
        self.store = store
        annotations = annotations if annotations is not None else getattr(master, "annotation_store", None)
        sheets = sheets if sheets is not None else getattr(master, "glossary_store", None)
        if annotations is not None and sheets is not None:
            from ...rename import Stores

            self.stores: Any = Stores(store, annotations, sheets)
        else:
            self.stores = store  # the caches alone (`backup` takes a CacheStore so)
        self.rename_flow = rename if rename is not None else getattr(master, "_plan_rename", None)
        self.on_changed = on_changed  # a book's cache was deleted or imported into
        self.on_status = on_status or (lambda _text: None)
        self._entries: dict[str, dict[str, Any]] = {}  # tree item -> the cache it lists
        self._sort: tuple[str, bool] | None = None  # the heading the reader sorted by, and whether the other way round
        self.recycle = to_recycle_bin  # where Delete puts a cache's files (tests put them elsewhere)
        self._explanations: list[ttk.Label] = []
        self._backup_ready = self.crypto_available()  # export and import need the cryptography package
        self.title(_("Saved translations"))
        self.transient(master)
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        self._frame = frm
        # the book's name as its Series (the tree's own text) and Volume (`bookname.split_name`)
        self.tree = ttk.Treeview(frm, columns=COLUMNS, show="tree headings", height=7, selectmode="extended")
        self.tree.pack(fill="both", expand=True, pady=(0, 2))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_buttons())
        for key in ("<Control-a>", "<Control-A>"):
            self.tree.bind(key, self._select_all)
        for column in ("#0", *COLUMNS):
            self.tree.heading(column, command=lambda c=column: self._sort_by(c))
        self.empty_var = tk.StringVar(self, value="")  # how much is kept, or that nothing is: an empty list looks broken
        ttk.Label(frm, textvariable=self.empty_var).pack(anchor="w")
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        button = ttk.Button(btns, text=_("Delete selected translations"), command=self._delete)
        button.pack(side="left")
        tip(_("Delete the chosen book's translations from this computer."), button)
        self.rename_btn = ttk.Button(btns, text=_("Rename..."), command=self._rename, state="disabled")
        self.rename_btn.pack(side="left", padx=(6, 0))
        tip(_("Give the chosen book another name: its translations, page information and series sheet move along."),
            self.rename_btn, disabled=_("Choose a book in the list first."))
        button = ttk.Button(btns, text=_("Open folder"), command=self._open_folder)
        button.pack(side="left", padx=(6, 0))
        tip(_("Open the folder that holds these files."), button)
        explain_button(btns, _("Each file holds translated text and bubble positions, matched to each page by a short code made from its picture; no picture is kept, and no original text.")).pack(
            side="left", padx=(6, 0))
        ttk.Button(btns, text=_("Close"), command=self.destroy).pack(side="right")
        self._explain(frm, _("Export makes an encrypted backup of the selected book's translations, for yourself or your other computer. It contains the translated text: never give it to anyone."),
                      pady=(10, 0))
        backups = ttk.Frame(frm)  # a row of its own: with the row above it would not fit every language
        backups.pack(fill="x", pady=(4, 0))
        self.export_btn = ttk.Button(backups, text=_("Export (encrypted)..."), command=self._export, state="disabled")
        self.export_btn.pack(side="left")
        tip(_("Make an encrypted backup of the chosen book."), self.export_btn, disabled=_("Choose a book in the list first."))
        self.import_btn = ttk.Button(backups, text=_("Import..."), command=self._import,
                                     state="normal" if self._backup_ready else "disabled")
        self.import_btn.pack(side="left", padx=(6, 0))
        self.backup_var = tk.StringVar(self, value="")  # what the last export or import did
        self.backup_line = ttk.Label(frm, textvariable=self.backup_var, justify="left", wraplength=600)
        self.backup_line.pack(anchor="w", fill="x", pady=(4, 0))
        self._explanations.append(self.backup_line)
        if not self._backup_ready:
            self._say(_("Export and import are not installed. Double-click install.cmd in the TASlation folder."), error=True)

        frm.bind("<Configure>", lambda e: self._wrap_explanations(e.width - 16))
        self._fill()
        place_window(self, master)
        self.minsize(min(self.winfo_reqwidth(), 900), min(self.winfo_reqheight(), 700))

    @staticmethod
    def crypto_available() -> bool:
        """Whether the optional cryptography package, which export and import need, is installed (`backup.require`)."""
        try:
            backup.require()
        except backup.LibraryMissing:
            return False
        return True

    def _explain(self, parent: tk.Misc, text: str, pady: tuple[int, int] = (0, 0)) -> None:
        """An explanation above a list or a row of buttons, wrapped to the dialog's width."""
        label = ttk.Label(parent, text=text, justify="left", wraplength=600)
        label.pack(anchor="w", fill="x", pady=pady)
        self._explanations.append(label)

    def _wrap_explanations(self, width: int) -> None:
        for label in self._explanations:
            wrap_label(label, width)

    def _say(self, text: str, error: bool = False) -> None:
        """The line under Export and Import: what the last export or import did, a failure in red."""
        self.backup_var.set(text)
        self.backup_line.configure(foreground=theme.colour("error") if error else "")

    # ------------------------------------------------------------------ the list
    def _fill(self, select: str | Sequence[str] | None = None, book: str | None = None) -> None:
        """The list from the files as they are now, sorted as the reader chose (`sort_key`); afterwards the cache
        files *select* (one, or several) are selected, or the cache of *book* saved last (an import's)."""
        self.tree.delete(*self.tree.get_children())
        self._entries = {}
        found = []
        for b in self.store.list():
            parts = split_name(b["book"])
            try:
                size = os.stat(b["file"]).st_size
            except OSError:
                size = 0
            found.append({**b, "series": parts.series or b["book"], "volume": parts.volume, "size": size})
        column, backwards = self._sort if self._sort is not None else (None, False)
        found.sort(key=lambda entry: sort_key(column, entry), reverse=backwards)
        rows = []
        for entry in found:
            values = (entry["volume"], entry["pages"], entry["bubbles"], shown_size(entry["size"]),
                      entry.get("language", ""), shown_time(entry["updated"]))
            item = self.tree.insert("", "end", text=entry["series"], values=values)
            self._entries[item] = entry
            rows.append((entry["series"], *values))
        arrow = {self._sort[0]: ARROWS[self._sort[1]]} if self._sort is not None else {}
        width = fit_columns(self.tree, (
            ("#0", _("Series") + arrow.get("#0", ""), ["A book title of some length"], 300),
            ("volume", _("Volume") + arrow.get("volume", ""), ["10.5"], 100),
            ("pages", _("Pages") + arrow.get("pages", ""), ["9999"], 120),
            ("bubbles", _("Bubbles") + arrow.get("bubbles", ""), ["99999"], 140),
            ("size", _("Size") + arrow.get("size", ""), [shown_size(10 * 1024 * 1024)], 120),
            ("language", _("Language") + arrow.get("language", ""), ["Portuguese (Brazil)"], 200),
            ("updated", _("Updated") + arrow.get("updated", ""), ["2026-12-31 23:59"], 200)), rows)
        if found:
            self.empty_var.set(_("In all: {files} translation file(s), {pages} page(s), {size}.").format(
                files=len(found), pages=sum(int(e["pages"]) for e in found),
                size=shown_size(sum(e["size"] for e in found))))
        else:
            self.empty_var.set(_("Nothing is kept yet."))
        self._wrap_explanations(width)  # no wider than the lists until the dialog is on the screen
        wanted = {str(select)} if isinstance(select, (str, Path)) else {str(s) for s in select or ()}
        targets = [item for item, b in self._entries.items() if b["file"] in wanted]
        if not targets and book is not None:
            saved = [(str(b.get("updated", "")), item) for item, b in self._entries.items() if b["book"] == book]
            targets = [max(saved)[1]] if saved else []
        if targets:
            self.tree.selection_set(targets)
            self.tree.see(targets[0])
        self._sync_buttons()

    def _sort_by(self, column: str) -> None:
        """A click on *column*'s heading: the list sorted by it, the other way round when it was already; the rows
        chosen stay chosen."""
        backwards = self._sort is not None and self._sort[0] == column and not self._sort[1]
        self._sort = (column, backwards)
        self._fill(select=[e["file"] for e in self._chosen()])

    def _select_all(self, _event: Any = None) -> str:
        """Ctrl+A in the list: every row chosen."""
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def _chosen(self) -> list[dict[str, Any]]:
        """The caches selected, in the list's order."""
        chosen = set(self.tree.selection())
        return [entry for item, entry in self._entries.items() if item in chosen]

    def _selected(self) -> dict[str, Any] | None:
        """The one cache selected (None for none or several)."""
        items = self.tree.selection()
        return self._entries.get(items[0]) if len(items) == 1 else None

    def _sync_buttons(self) -> None:
        self.export_btn.configure(state="normal" if self._chosen() and self._backup_ready else "disabled")
        one = self._selected() is not None and self.rename_flow is not None
        self.rename_btn.configure(state="normal" if one else "disabled")

    # ------------------------------------------------------------------ delete, rename
    def _delete(self) -> None:
        entries = self._chosen()
        if not entries:
            self._say(_("Select one in the list first."))
            return
        if len(entries) == 1:
            book, language = str(entries[0].get("book", "")), str(entries[0].get("language", "") or "English")
            question = _(DELETE_QUESTION).format(book=book, language=language)
        else:
            question = _(DELETE_MANY_QUESTION).format(n=len(entries), names=names_line(entries))
        if not ask(self, question, _("Delete"), _("Keep them"), no_first=True):
            return  # the list and its selection stay
        gone, failed = 0, []
        for entry in entries:
            book, language = str(entry.get("book", "")), str(entry.get("language", "") or "English")
            try:
                gone += bool(self.store.delete(book, language, recycle=self.recycle))
            except OSError:  # no Recycle Bin for the file, or the shell refused: nothing is deleted for good
                failed.append(entry)
                continue
            if self.on_changed:
                self.on_changed(book)
        self._fill()
        if len(entries) == 1:
            book, language = str(entries[0].get("book", "")), str(entries[0].get("language", "") or "English")
            if failed:
                self._warn(_(NOT_DELETED).format(book=book, language=language))
            elif gone:
                self._say(_(IN_THE_BIN).format(book=book, language=language))
        elif failed:
            self._warn(_(NOT_ALL_DELETED).format(n=len(failed), names=names_line(failed)))
        elif gone:
            self._say(_(IN_THE_BIN_MANY).format(n=gone))

    def _rename(self) -> None:
        """Rename...: the one book chosen gets the name the reader gives (`RenameBookDialog`), by the window's rename
        - never while the window waits for an answer to a question of its own."""
        entry = self._selected()
        if entry is None or self.rename_flow is None:
            return
        book = str(entry["book"])
        if getattr(self.master, "_start_dialog", None) is not None:
            self._say(_("Answer the question in the TASlation window first."), error=True)
            return
        self._ask_name(book, lambda new: self._renaming(entry, new))

    def _ask_name(self, book: str, then: Callable[[str], None]) -> None:
        """The new name of *book*, asked for (`RenameBookDialog`); *then* takes it."""
        RenameBookDialog(self, book, then)

    def _renaming(self, entry: dict[str, Any], new: str) -> None:
        old = str(entry["book"])
        assert self.rename_flow is not None
        try:
            self.rename_flow(old, new, str(entry.get("model", "")), str(entry.get("language", "") or "English"), None)
        except Exception:  # noqa: BLE001 - the window says nothing then: the dialog does
            self._say(_("{book} keeps its name; the status line in the right pane says why.").format(book=old), error=True)
            return
        self._watch_rename(old, new)

    def _watch_rename(self, old: str, new: str) -> None:
        """Once the window is done with the rename (no longer busy, its review answered), the list as the files are
        and a line that says whether the book now has its new name."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        master = self.master
        if getattr(master, "busy", False) or getattr(master, "_start_dialog", None) is not None:
            self.after(RENAME_POLL_MS, lambda: self._watch_rename(old, new))
            return
        names = {b["book"] for b in self.store.list()}
        if new in names and old not in names:
            self._fill(book=new)
            self._say(_("Renamed {book} to {name}.").format(book=old, name=new))
        else:
            self._fill(book=old)
            self._say(_("{book} keeps its name; the status line in the right pane says why.").format(book=old))

    # ------------------------------------------------------------------ export, import
    def _before(self, title: str, text: str) -> bool:
        """The warning before an export or an import (`WarningBox`): whether the reader chose Continue."""
        box = WarningBox(self, title, text)
        self.wait_window(box)
        return box.answer

    def _passphrase(self, confirm: bool) -> str | None:
        dialog = PassphraseDialog(self, confirm)
        self.wait_window(dialog)
        return dialog.passphrase

    def _review(self, opened: Any, plan: Any, file: str) -> ImportChoice | None:
        """What to import of *opened*, asked (`ImportReviewDialog`); None when the reader cancels."""
        dialog = ImportReviewDialog(self, opened, plan, file)
        self.wait_window(dialog)
        return dialog.choice

    def _busy(self, work: Callable[[], Any]) -> Any:
        """*work* under the busy cursor (deriving the key from the passphrase takes a moment)."""
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            return work()
        finally:
            self.configure(cursor="")

    def _warn(self, text: str) -> None:
        self._say(text, error=True)
        self.on_status(text)
        tell(self, text)

    def _missing(self) -> None:
        """The cryptography package is gone since the dialog opened: Export and Import off, and the line says so."""
        self._backup_ready = False
        self.import_btn.configure(state="disabled")
        self._sync_buttons()
        self._warn(_("Export and import are not installed. Double-click install.cmd in the TASlation folder."))

    def _export(self) -> None:
        """The caches chosen to one file encrypted with a passphrase, each with its page information and series sheet,
        once the reader has read what the file is and chosen Continue; the file name is the reader's (the suggested
        one names no book)."""
        entries = self._chosen()
        if not entries or not self._backup_ready:
            return
        if not self._before(_("Before exporting"), _("This file will contain the translated text of the book. Keep it for yourself: never give it to anyone, post it, or share it. Handing a translation to someone else infringes the author's rights even when the book is yours.")):
            return  # Cancel: no file is asked for, nothing changes
        path = filedialog.asksaveasfilename(parent=self, defaultextension=backup.SUFFIX,
                                            initialfile="taslation-cache" + backup.SUFFIX,
                                            filetypes=[("TASlation", "*" + backup.SUFFIX), (_("All files"), "*.*")])
        if not path:
            return
        passphrase = self._passphrase(confirm=True)
        if passphrase is None:
            return
        books = [(str(e["book"]), str(e.get("language", "") or "English")) for e in entries]
        try:
            done = self._busy(lambda: backup.export_books(self.stores, books, path, passphrase))
        except backup.LibraryMissing:
            self._missing()
        except backup.TooLarge:
            self._warn(_("This book's translations are larger than TASlation can export.") if len(entries) == 1
                       else _("These books are larger than TASlation can export in one file; export fewer at a time."))
        except backup.BackupError:  # (its own text is English: for the command line)
            self._warn(_("Could not export: choose another file name or folder."))
        except OSError as e:
            self._warn(_("Could not write the file: {error}").format(error=e))
        else:
            self._fill(select=[e["file"] for e in entries])
            if len(entries) == 1:
                line = _("Exported {pages} page(s) of {book} to {file}.").format(pages=done.pages, book=entries[0]["book"],
                                                                                 file=Path(path).name)
                status = _("Exported {book} to {path}").format(book=entries[0]["book"], path=path)
            else:
                line = _("Exported {books} books, {pages} page(s), to {file}.").format(
                    books=done.books, pages=done.pages, file=Path(path).name)
                status = _("Exported {books} books, {pages} page(s), to {file}.").format(
                    books=done.books, pages=done.pages, file=path)
            more = []
            if done.annotations or done.sheets:
                more.append(_("With them: the page information of {marks} book(s) and {sheets} series sheet(s).").format(
                    marks=done.annotations, sheets=done.sheets))
            if getattr(done, "defaults", 0):
                more.append(_("Also with them: the defaults of {n} series.").format(n=done.defaults))
            if done.left_out:
                more.append(_("{n} file(s) that cannot be opened on this computer were left out.").format(n=done.left_out))
            self._say(" ".join([line, *more]))
            self.on_status(status)

    def _import_failed(self, error: BaseException) -> None:
        clash = _backup_error("NameClash")
        if isinstance(error, backup.BackupError) or (clash is not None and isinstance(error, clash)):
            self._warn(import_error_text(error))  # what went wrong, in the window's language
        else:
            self._warn(_("Could not import: {error}").format(error=error))

    def _import(self) -> None:
        """A file made by an export, once the reader has read that it must be one of their own and chosen Continue:
        what it holds is read and checked, and what an import would do counted (nothing written); the review asks
        what to import when the file holds several books or meets corrections, page information, series' defaults or
        sheet values of the reader's own (Cancel there: nothing is imported); then its pages replace the same pages of
        each book's
        cache here and join the others, the reader's corrections kept unless they took the file as it is."""
        if not self._backup_ready:
            return
        if not self._before(_("Before importing"), _("Import only a file you made yourself on this or another of your computers. Importing someone else's translation is receiving a copy made without permission, and TASlation is built not to pass translations between people.")):
            return  # Cancel: no file is asked for, nothing changes
        path = filedialog.askopenfilename(parent=self, filetypes=[("TASlation", "*" + backup.SUFFIX),
                                                                  (_("All files"), "*.*")])
        if not path:
            return
        passphrase = self._passphrase(confirm=False)
        if passphrase is None:
            return
        try:
            opened, plan = self._busy(lambda: self._opened(path, passphrase))
        except backup.LibraryMissing:
            self._missing()
            return
        except (backup.BackupError, OSError) as e:
            self._import_failed(e)
            return
        choice = ImportChoice(list(range(len(opened.held))))
        if len(opened.held) > 1 or plan.kept or plan.differing or plan.differing_defaults or plan.keyed():
            choice = self._review(opened, plan, Path(path).name)
            if choice is None or not choice.books:
                return  # Cancel: nothing is imported
        books = list(dict.fromkeys(opened.held[i].book for i in opened.chosen(choice.books)))
        try:
            result = self._busy(lambda: backup.apply_import(
                self.stores, opened, choice.books, keep_corrections=choice.keep_corrections,
                take_annotations=choice.take_annotations, answers=choice.answers, take_defaults=choice.take_defaults))
        except backup.LibraryMissing:
            self._missing()
            return
        except (backup.BackupError, OSError) as e:
            self._import_failed(e)
            return
        self._fill(select=[str(b.target) for b in result.books], book=books[0] if books else None)
        if self.on_changed:
            for book in books:
                self.on_changed(book)
        if (result.annotations_added or result.annotations_taken or result.sheets_added or result.sheets_joined
                or getattr(result, "defaults_added", 0) or getattr(result, "defaults_taken", 0)):
            self._premises_changed()
        if len(result.books) == 1:
            book = result.books[0].held.book
            line = _("Imported {pages} page(s) of {book} from {file}.").format(pages=result.pages, book=book,
                                                                             file=Path(path).name)
            status = _("Imported {pages} page(s) into {book}").format(pages=result.pages, book=book)
        else:
            line = _("Imported {books} books, {pages} page(s), from {file}.").format(
                books=len(result.books), pages=result.pages, file=Path(path).name)
            status = _("Imported {books} books, {pages} page(s), from {file}.").format(
                books=len(result.books), pages=result.pages, file=path)
        self._say(" ".join([line, *self._import_details(result)]))
        self.on_status(status)

    def _opened(self, path: str, passphrase: str) -> tuple[Any, Any]:
        """The file at *path* opened and checked, and what importing all of it would do (nothing written)."""
        opened = backup.open_export(path, passphrase)
        return opened, backup.plan_import(self.stores, opened)

    @staticmethod
    def _import_details(result: Any) -> list[str]:
        """What an import did beyond its pages, a sentence each, where there is something to say."""
        said = []
        if result.replaced or result.kept:
            said.append(_("{added} page(s) added, {replaced} replaced, {kept} of your corrections kept.").format(
                added=result.added, replaced=result.replaced, kept=result.kept))
        if result.annotations_added or result.annotations_taken or result.annotations_kept:
            said.append(_("Page information: {added} added, {taken} taken from the file, {kept} kept as yours.").format(
                added=result.annotations_added, taken=result.annotations_taken, kept=result.annotations_kept))
        if result.sheets_added or result.sheets_joined:
            said.append(_("Series sheets: {added} added, {joined} joined with yours ({taken} value(s) taken from the file, {kept} kept as yours).").format(
                added=result.sheets_added, joined=result.sheets_joined, taken=result.sheet_taken, kept=result.sheet_kept))
        added, taken, kept = (getattr(result, name, 0) for name in ("defaults_added", "defaults_taken", "defaults_kept"))
        if added or taken or kept:
            said.append(_("Series defaults: {added} added, {taken} taken from the file, {kept} kept as yours.").format(
                added=added, taken=taken, kept=kept))
        return said

    def _premises_changed(self) -> None:
        """Page information or a series sheet was written: the window's book takes them anew (its sheet may be one an
        import joined, of another volume of its series), where the dialog is the window's."""
        refresh = getattr(self.master, "_premises_changed", None)
        book_var, lang_var = getattr(self.master, "book_var", None), getattr(self.master, "lang_var", None)
        if refresh is None or book_var is None:
            return
        try:
            refresh(book_var.get().strip(), (lang_var.get().strip() if lang_var is not None else "") or "English")
        except Exception:  # noqa: BLE001 - the next page takes the book's stores anew
            pass

    def _open_folder(self) -> None:
        self.store.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(self.store.cache_dir))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            tell(self, str(self.store.cache_dir), icon="info")
