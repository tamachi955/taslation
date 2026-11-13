"""The About dialog (Help > About TASlation): the version, the licence, that TASlation runs offline, where its data
is kept and where to read more, given by path: nothing here opens a browser."""

from __future__ import annotations

import importlib.metadata
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from ..constants import APP_EXPANSION, APP_NAME
from ... import __version__, errorlog
from ...config import REPO_DIR
from ...i18n import _
from ...translator_install import CREDIT
from ..copy_details import details_button
from ..layout import ICON_PNG, place_window
from .caches import in_lines

DOCUMENTS = (Path("README.md"), Path("docs") / "THIRD_PARTY.md")  # where to read more, in the source
TEXT_CHARS = 60  # the narrowest the dialog's lines are broken at, in "0" widths of its font (as many words at any
# scale); wider when a path asks for more
PATH_CHARS = (40, 100)  # a path's line: at least, at most so many "0" widths (a longer path scrolls in it)


def version() -> str:
    """The version of TASlation as installed (`importlib.metadata`), else the package's own."""
    try:
        return importlib.metadata.version("taslation")
    except importlib.metadata.PackageNotFoundError:
        return __version__


def documents(root: Path = REPO_DIR) -> list[Path]:
    """README.md and docs/THIRD_PARTY.md by their full paths, those that are on this computer (a checkout of the
    source has them, an installed package does not: the line above them names them anyway)."""
    return [Path(root) / rel for rel in DOCUMENTS if (Path(root) / rel).is_file()]


class AboutDialog(tk.Toplevel):
    """About TASlation, modal over the window and centred over it: the icon, the name, the version (`version`) and the
    date of its program files (``date_text``, as install.cmd and update.cmd print it);
    free software under the MIT licence; runs offline, talking only to Ollama on this computer, with the offline
    guard's state (*guard*, a line); the folder where its data is kept, then the README and docs/THIRD_PARTY.md, each path in a read-only line that can be selected and
    copied; Copy details (``details_btn``: the version, the system and the last error for a report, nothing of the
    books) and Close. ``paths`` holds the paths shown, ``lines`` the sentences."""

    def __init__(self, master: tk.Misc, state_dir: Path | str, port: int = 11434, root: Path = REPO_DIR, guard: str = ""):
        super().__init__(master)
        self.title(_("About TASlation"))
        self.transient(master)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        head = ttk.Frame(frm)
        head.pack(fill="x")
        try:
            self._icon: tk.PhotoImage | None = tk.PhotoImage(master=self, file=str(ICON_PNG)).subsample(4)  # 64 px
        except tk.TclError:  # no icon file: the name alone
            self._icon = None
        if self._icon is not None:
            ttk.Label(head, image=self._icon).pack(side="left", padx=(0, 12))
        names = ttk.Frame(head)
        names.pack(side="left", anchor="w")
        base = tkfont.nametofont("TkDefaultFont")
        size = int(base.actual("size"))
        self._name_font = tkfont.Font(self, font=base)
        self._name_font.configure(weight="bold", size=size + 6 if size > 0 else size - 8)
        ttk.Label(names, text=APP_NAME, font=self._name_font).pack(anchor="w")
        ttk.Label(names, text=APP_EXPANSION).pack(anchor="w")
        self.version_text = _("Version {version}").format(version=version())
        ttk.Label(names, text=self.version_text).pack(anchor="w")
        # the date install.cmd and update.cmd show beside the version: the newest program file (`errorlog.release_date`)
        released = errorlog.release_date()
        self.date_text = _("Program files dated {date}").format(date=released) if released else ""
        if self.date_text:
            ttk.Label(names, text=self.date_text).pack(anchor="w")

        self.lines: list[str] = []
        self._labels: list[ttk.Label] = []
        self.paths: list[str] = []
        self._fields: list[ttk.Entry] = []
        self._line(frm, _("Free software under the MIT licence"), pady=(12, 0))
        self._line(frm, CREDIT, pady=(2, 0))  # PLaMo's licence, article 4: these words as they are
        self._line(frm, _("Runs offline: it talks only to Ollama on this computer (localhost:{port})").format(port=port),
                   pady=(2, 0))
        if guard:
            self._line(frm, guard, pady=(2, 0))
        self._line(frm, _("Your translations, notes and settings are kept in this folder:"), pady=(12, 2))
        self._path(frm, str(Path(state_dir)))
        self._line(frm, _("More in the README and in docs/THIRD_PARTY.md (the projects TASlation uses and their licences):"),
                   pady=(12, 2))
        for document in documents(root):
            self._path(frm, str(document))
        zero = max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.text_width = max([TEXT_CHARS * zero] + [field.winfo_reqwidth() for field in self._fields])
        for label, text in zip(self._labels, self.lines):
            label.configure(text=in_lines(text, self.text_width))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        self.details_btn = details_button(btns, self)  # what a report needs, nothing of the books (`copy_details`)
        self.details_btn.pack(side="left")
        self.close_btn = ttk.Button(btns, text=_("Close"), command=self.destroy)
        self.close_btn.pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.destroy())
        self.close_btn.focus_set()
        place_window(self, master)
        try:
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    def _line(self, parent: tk.Misc, text: str, pady: tuple[int, int]) -> None:
        """A sentence, broken into lines at the dialog's width once that is known (`in_lines`)."""
        label = ttk.Label(parent, justify="left")
        label.pack(anchor="w", fill="x", pady=pady)
        self.lines.append(text)
        self._labels.append(label)

    def _path(self, parent: tk.Misc, path: str) -> None:
        """A path in a read-only line as wide as the path (within PATH_CHARS): it can be selected and copied, never
        edited, and nothing opens it."""
        font = tkfont.nametofont("TkTextFont")  # an entry's
        chars = -(-font.measure(path) // max(1, font.measure("0"))) + 2
        field = ttk.Entry(parent, width=max(PATH_CHARS[0], min(PATH_CHARS[1], chars)))
        field.insert(0, path)
        field.configure(state="readonly")
        field.pack(anchor="w", fill="x", pady=(0, 2))
        self.paths.append(path)
        self._fields.append(field)
