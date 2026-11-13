"""The Caches dialog (list and delete the translation caches; export a cache to an
encrypted file, import one), the warning it shows before an export or an import, the passphrase it asks for, and
what it says when an import fails. Also TASlation's own message box (`WarningBox`) and the two ways the whole window
uses it in place of Windows' message boxes, whose buttons speak Windows' language and which come up behind a
full-screen viewer: `ask` (a question, two buttons named for what they do) and `tell` (one OK)."""

from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

from ... import backup
from ...capture import foreground_window, give_foreground
from ...cache import CacheStore
from ...i18n import _
from ...recycle import to_recycle_bin
from ..layout import fit_columns, place_window, wrap_label
from ..tooltip import tip
from ..wrap import wrap_line
from .help import explain_button

ERROR_COLOUR = "#b3261e"  # a line that says what went wrong, as the window's other warnings
WARNING_ICON = "::tk::icons::warning"  # the stock icon of Tk's own message boxes (Tk makes it as it starts)
ICONS = {"warning": (WARNING_ICON, "warning"), "info": ("::tk::icons::information", "info"),
         "question": ("::tk::icons::question", "questhead")}  # a box's icon: Tk's stock image, the bitmap without it
WARNING_CHARS = 62  # the warning box's lines are broken at so many "0" widths of its font: as many words at any DPI


# Delete in the list: what it asks (the row's book in the row's language alone, to the Recycle Bin), what it says when
# the Recycle Bin did not take the file, and what it says once it did
DELETE_QUESTION = "Move the saved translations of {book} in {language} to the Recycle Bin? Its saved translations in other languages stay. You can restore the file from the Recycle Bin."
NOT_DELETED = "Nothing was deleted: the saved translations of {book} in {language} could not go to the Recycle Bin. Open folder shows the file; delete it there if you want it gone."
IN_THE_BIN = "The saved translations of {book} in {language} are in the Recycle Bin; restore them from there to have them back."


def in_lines(text: str, width: int, font: str = "TkDefaultFont") -> str:
    """*text* broken into lines of at most *width* pixels in *font*, between words or CJK characters and never inside
    a run of Latin letters such as "TASlation" (`wrap.wrap_line`), for a label of a dialog of one size: Tk breaks
    only at spaces, which leaves a short line before "TASlation" in a Japanese sentence."""
    measure = tkfont.nametofont(font).measure
    return "\n".join(line.rstrip(" ") for paragraph in text.split("\n") for line in wrap_line(paragraph, width, measure))


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
    (*go*, OK by default), a box that tells; *icon*: "warning", "info" or "question" (`ICONS`)."""

    def __init__(self, master: tk.Misc, title: str, text: str, go: str | None = None, stay: str | None = None,
                 stay_first: bool = False, alone: bool = False, icon: str = "warning"):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.answer = False
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
        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=2, sticky="e", pady=(14, 0))
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
    """TASlation's own box over *parent* (`WarningBox`), in front and above everything - a full-screen viewer too: a
    box of the window's own over the full-screen viewer is raised there by `overbook` as well - with the keys. When
    the viewer chosen in the window had the foreground (a box nobody asked for, the reader in the book), the viewer
    gets it back once the box is closed. *wait*: until then (else at once, the box left to the reader)."""
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
        self.hint = ttk.Label(frm, textvariable=self.hint_var, justify="left", foreground=ERROR_COLOUR)
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


class CachesDialog(tk.Toplevel):
    """List and delete translation caches (text-only JSON files); export a cache to a file
    encrypted with a passphrase, or import one, for the reader's own backup or other computer. A line above Export
    and Import says what such a file is for and that it holds the translated text; each of them first shows a
    warning (`WarningBox`) before it asks for a file: an export's file holds the book's translated text and is for
    the reader alone, an import is only of a file the reader made; Cancel there does nothing else. The line below
    them says what the last export or import did (the file's name and the pages; the list is filled again, the
    book's cache selected), or, from the start, that both need the optional cryptography package when it is not
    installed (both disabled then). The dialog takes the size of what it shows in the window's language: the
    columns as wide as their headings and cells, the times in local time (`shown_time`), the explanations wrapped
    to the dialog's width. Open folder shows where the files are. Delete takes the selected row's book in the row's
    language alone, after a question that says so (Keep them has the focus), and moves its files to the Recycle Bin
    (`recycle.to_recycle_bin`), where they can be restored; when the bin does not take them nothing is deleted and
    the dialog says so."""

    def __init__(self, master: tk.Misc, store: CacheStore,
                 on_changed: Callable[[str], None] | None = None, on_status: Callable[[str], None] | None = None,
                 in_use: Callable[[str], bool] | None = None):
        super().__init__(master)
        self.store = store
        self.in_use = in_use or (lambda _book: False)  # a run reads this book: its next save would bring the file back
        self.on_changed = on_changed  # a book's cache was deleted or imported into
        self.on_status = on_status or (lambda _text: None)
        self._entries: dict[str, dict[str, Any]] = {}  # tree item -> the cache it lists
        self.recycle = to_recycle_bin  # where Delete puts a cache's files (tests put them elsewhere)
        self._explanations: list[ttk.Label] = []
        self._backup_ready = self.crypto_available()  # export and import need the cryptography package
        self.title(_("Saved translations"))
        self.transient(master)
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        self._frame = frm
        self.tree = ttk.Treeview(frm, columns=("pages", "bubbles", "language", "updated"),
                                 show="tree headings", height=7)
        self.tree.pack(fill="both", expand=True, pady=(0, 2))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_buttons())
        self.empty_var = tk.StringVar(self, value="")  # says so while nothing is kept: an empty list looks broken
        ttk.Label(frm, textvariable=self.empty_var).pack(anchor="w")
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        button = ttk.Button(btns, text=_("Delete selected translations"), command=self._delete)
        button.pack(side="left")
        tip(_("Delete the chosen book's translations from this computer."), button)
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
        self.backup_line.configure(foreground=ERROR_COLOUR if error else "")

    def _fill(self, select: str | None = None, book: str | None = None) -> None:
        """The list from the files as they are now; afterwards the cache file *select* is selected, or the cache of
        *book* saved last (an import's)."""
        self.tree.delete(*self.tree.get_children())
        self._entries = {}
        rows = []
        for b in self.store.list():
            values = (b["pages"], b["bubbles"], b.get("language", ""), shown_time(b["updated"]))
            item = self.tree.insert("", "end", text=b["book"], values=values)
            self._entries[item] = b
            rows.append((b["book"], *values))
        width = fit_columns(self.tree, (
            ("#0", _("Book"), ["A book title of some length"], 300),
            ("pages", _("Pages"), ["9999"], 120), ("bubbles", _("Bubbles"), ["99999"], 140),
            ("language", _("Language"), ["Portuguese (Brazil)"], 200),
            ("updated", _("Updated"), ["2026-12-31 23:59"], 200)), rows)
        self.empty_var.set("" if rows else _("Nothing is kept yet."))
        self._wrap_explanations(width)  # no wider than the lists until the dialog is on the screen
        target = next((item for item, b in self._entries.items() if select is not None and b["file"] == str(select)), None)
        if target is None and book is not None:
            saved = [(str(b.get("updated", "")), item) for item, b in self._entries.items() if b["book"] == book]
            target = max(saved)[1] if saved else None
        if target is not None:
            self.tree.selection_set(target)
            self.tree.see(target)
        self._sync_buttons()

    def _selected(self) -> dict[str, Any] | None:
        """The one cache selected (an export is one file per cache)."""
        items = self.tree.selection()
        return self._entries.get(items[0]) if len(items) == 1 else None

    def _sync_buttons(self) -> None:
        self.export_btn.configure(state="normal" if self._selected() is not None and self._backup_ready else "disabled")

    def _delete(self) -> None:
        items = self.tree.selection()
        if not items:
            self._say(_("Select one in the list first."))
            return
        for item in items:
            book = self.tree.item(item, "text")
            language = str(self._entries.get(item, {}).get("language", "") or "English")
            if self.in_use(book):  # the list and its selection stay
                self._say(_("{book} is being read by a run: press Stop first.").format(book=book), error=True)
                return
            if not ask(self, _(DELETE_QUESTION).format(book=book, language=language), _("Delete"), _("Keep them"),
                       no_first=True):
                return  # the list and its selection stay
            try:
                gone = self.store.delete(book, language, recycle=self.recycle)
            except OSError:  # no Recycle Bin for the file, or the shell refused: nothing is deleted for good
                self._fill()
                self._warn(_(NOT_DELETED).format(book=book, language=language))
                return
            if gone:
                self._say(_(IN_THE_BIN).format(book=book, language=language))
            if self.on_changed:
                self.on_changed(book)
        self._fill()

    def _before(self, title: str, text: str) -> bool:
        """The warning before an export or an import (`WarningBox`): whether the reader chose Continue."""
        box = WarningBox(self, title, text)
        self.wait_window(box)
        return box.answer

    def _passphrase(self, confirm: bool) -> str | None:
        dialog = PassphraseDialog(self, confirm)
        self.wait_window(dialog)
        return dialog.passphrase

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
        """The selected cache to a file encrypted with a passphrase, once the reader has read what the file is and
        chosen Continue; the file name is the reader's (the suggested one names no book)."""
        entry = self._selected()
        if entry is None or not self._backup_ready:
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
        try:
            pages = self._busy(lambda: backup.export_cache(self.store, entry["book"], path, passphrase, entry["language"]))
        except backup.LibraryMissing:
            self._missing()
        except backup.TooLarge:
            self._warn(_("This book's translations are larger than TASlation can export."))
        except backup.BackupError:  # (its own text is English: for the command line)
            self._warn(_("Could not export: choose another file name or folder."))
        except OSError as e:
            self._warn(_("Could not write the file: {error}").format(error=e))
        else:
            self._fill(select=entry["file"])
            self._say(_("Exported {pages} page(s) of {book} to {file}.").format(pages=pages, book=entry["book"],
                                                                               file=Path(path).name))
            self.on_status(_("Exported {book} to {path}").format(book=entry["book"], path=path))

    def _import(self) -> None:
        """A file made by an export, once the reader has read that it must be one of their own and chosen Continue:
        its pages replace the same pages of the book's cache here and join the others."""
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
        clash = _backup_error("NameClash")
        try:
            book, pages = self._busy(lambda: backup.import_cache(self.store, path, passphrase))
        except backup.LibraryMissing:
            self._missing()
            return
        except (backup.BackupError, OSError) as e:
            if isinstance(e, backup.BackupError) or (clash is not None and isinstance(e, clash)):
                self._warn(import_error_text(e))  # what went wrong, in the window's language
            else:
                self._warn(_("Could not import: {error}").format(error=e))
            return
        self._fill(book=book)
        if self.on_changed:
            self.on_changed(book)
        self._say(_("Imported {pages} page(s) of {book} from {file}.").format(pages=pages, book=book, file=Path(path).name))
        self.on_status(_("Imported {pages} page(s) into {book}").format(pages=pages, book=book))

    def _open_folder(self) -> None:
        self.store.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(self.store.cache_dir))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            tell(self, str(self.store.cache_dir), icon="info")
