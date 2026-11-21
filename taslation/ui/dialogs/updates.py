"""Help > Check for updates...: asks GitHub for the newest version when it opens (`updates.Check`: check_update.py in a
process of its own; TASlation's own process asks nothing), then says one of: this is the newest version (with its
version and date), GitHub could not be asked (one plain sentence: `reason_text`), or a newer version is out - both
versions with their dates, the changes since this one in a scrolling plain-text box, Update now and Later. In a git
clone nothing is asked: git updates it. Opened again within a minute of an answer that was no failure, it shows that
answer again and asks nothing (`updates.recent`). Under it, the box that turns the start's look on and off (``update_check``,
kept in taslation.toml as the Settings dialog keeps it), with one sentence on what is asked of whom.

The dialog is centred over the window and kept on the work area of the monitor there (`layout.place_window`); each
time what it says changes, it is placed again as a dialog of its new size would be (`layout.place_again`), without
taking the focus, and where it is when its size stayed the same. Where it would be taller than the work area, the
changes box gets fewer lines (`_fit`)."""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ... import config
from ...i18n import _
from .. import layout, updates
from .caches import in_lines

TEXT_CHARS = 60  # the dialog's sentences are broken at this many "0" widths of its font
CHANGES_SIZE = (72, 12)  # the changes box: characters wide, lines high (it scrolls)
CHANGES_MIN_LINES = 4  # ... and never fewer lines than this, however low the screen


def reason_text(reason: str) -> str:
    """check_update.py's sentence of why GitHub could not be asked, in the window's language (one the window does
    not know: that GitHub could not be asked just now)."""
    reason = (reason or "").strip()
    code = re.fullmatch(r"GitHub answered with HTTP ([0-9]{3})\.", reason)
    if code:
        return _("GitHub answered with HTTP {code}.").format(code=code.group(1))
    if reason.startswith("GitHub sent the request on"):
        return _("GitHub sent the request on to another address, which is not asked.")
    if reason.startswith("GitHub's answer is larger than expected"):
        return _("GitHub's answer is larger than expected.")
    if reason.startswith("The installed version could not be read"):
        return _("The installed version could not be read from pyproject.toml.")
    if reason.startswith("check_update.py could not be started"):
        return _("check_update.py could not be started.")
    known = {
        "GitHub did not answer in time.": _("GitHub did not answer in time."),
        "GitHub could not be reached: is this computer online?": _("GitHub could not be reached: is this computer online?"),
        "GitHub could not be reached.": _("GitHub could not be reached."),
        "The secure connection to GitHub could not be made.": _("The secure connection to GitHub could not be made."),
        "The connection to GitHub broke off.": _("The connection to GitHub broke off."),
        "The newest version could not be read from GitHub's answer.": _("The newest version could not be read from GitHub's answer."),
        "check_update.py is not in the TASlation folder.": _("{file} is not in the TASlation folder.").format(file="check_update.py"),
    }
    return known.get(reason, _("GitHub could not be asked just now."))


def dated(version: str, date: str) -> str:
    return _("{version}, of {date}").format(version=version, date=date) if date else version


class UpdateDialog(tk.Toplevel):
    """Check for updates, modal over the window and centred over it. ``shown`` is "asking", "clone", "up to date",
    "could not ask" or "newer"; ``lines`` the sentences on show, ``answer`` the asking program's answer. Update now
    closes the dialog and calls *on_update* with the new version (`updates.update_now`)."""

    def __init__(self, master: tk.Misc, window: Any, on_update: Callable[[str], Any] | None = None,
                 root: Any = None):
        super().__init__(master)
        self.window = window
        self.on_update = on_update
        self.root_dir = updates.program_root(root)
        self.title(_("Check for updates"))
        self.transient(master)
        self.resizable(False, False)
        self.shown = "asking"
        self.answer: dict[str, Any] | None = None
        self.lines: list[str] = []
        self.check: updates.Check | None = None
        self.changes: tk.Text | None = None
        self.update_btn: ttk.Button | None = None
        zero = max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.text_width = TEXT_CHARS * zero
        self._bold = tkfont.Font(self, font=tkfont.nametofont("TkDefaultFont"))
        self._bold.configure(weight="bold")
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        self.body = ttk.Frame(frm)
        self.body.pack(fill="both", expand=True)
        self.choice_var = tk.BooleanVar(self, value=getattr(window.settings, "update_check", "off") == "daily")
        self.choice_box: ttk.Checkbutton | None = None
        self.choice_note = ttk.Label(frm, justify="left")
        if not updates.is_clone(self.root_dir):  # (a clone has no look at the start: git updates it)
            ttk.Separator(frm).pack(fill="x", pady=(12, 8))
            self.choice_box = ttk.Checkbutton(frm, text=_("Look for a new version once a day when TASlation starts"),
                                              variable=self.choice_var, command=self._keep_choice)
            self.choice_box.pack(anchor="w")
            self.choice_note.configure(text=in_lines(_("It asks GitHub for one small file, the list of changes, at most once a day and never while a page is read; nothing about you or your books is sent."), self.text_width))
            self.choice_note.pack(anchor="w", pady=(2, 0))
        self.btns = ttk.Frame(frm)
        self.btns.pack(fill="x", pady=(14, 0))
        self.close_btn = ttk.Button(self.btns, text=_("Close"), command=self.close)
        self.close_btn.pack(side="right")
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        kept = None if updates.is_clone(self.root_dir) else updates.recent(window)
        if updates.is_clone(self.root_dir):
            self._show("clone")
        elif kept is not None:  # chosen again within a minute of an answer: that answer, nothing asked
            self.answer = kept
            self._show(kept["result"], kept)
        else:
            self._show("asking")
            self.check = updates.Check(self.root_dir)
            updates.watch(window, self.check, self._answered)
        self.close_btn.focus_set()
        layout.place_window(self, master, fit=self._fit)
        try:
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    # ------------------------------------------------------------------ what it says
    def _sentence(self, text: str, bold: bool = False, pady: tuple[int, int] = (0, 0)) -> None:
        label = ttk.Label(self.body, text=in_lines(text, self.text_width), justify="left",
                          font=self._bold if bold else None)
        label.pack(anchor="w", fill="x", pady=pady)
        self.lines.append(text)

    def _row(self, grid: ttk.Frame, row: int, name: str, value: str) -> None:
        ttk.Label(grid, text=name).grid(row=row, column=0, sticky="w", padx=(0, 10))
        ttk.Label(grid, text=value).grid(row=row, column=1, sticky="w")
        self.lines.append(f"{name} {value}")

    def _show(self, state: str, answer: dict[str, Any] | None = None) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.lines, self.changes, self.shown = [], None, state
        if self.update_btn is not None:
            self.update_btn.destroy()
            self.update_btn = None
        self.close_btn.configure(text=_("Close"))
        if state == "asking":
            self._sentence(_("Asking GitHub for the newest version ..."))
        elif state == "clone":
            self._sentence(_("This TASlation is a git clone: update it with git (git pull). Nothing was asked of GitHub."))
        elif state == "could not ask":
            self._sentence(reason_text((answer or {}).get("reason", "")))
        elif state == "up to date":
            assert answer is not None
            self._sentence(_("This TASlation is the newest version."), bold=True)
            grid = ttk.Frame(self.body)
            grid.pack(anchor="w", pady=(6, 0))
            self._row(grid, 0, _("This one:"), dated(answer["installed"], answer.get("installed_date", "")))
        else:  # newer
            assert answer is not None
            self._sentence(_("A newer version of TASlation is available."), bold=True)
            grid = ttk.Frame(self.body)
            grid.pack(anchor="w", pady=(6, 0))
            self._row(grid, 0, _("This one:"), dated(answer["installed"], answer.get("installed_date", "")))
            self._row(grid, 1, _("The new one:"), dated(answer["newest"], answer.get("date", "")))
            self._sentence(_("What changed since this one:"), pady=(10, 2))
            box = ttk.Frame(self.body)
            box.pack(fill="both", expand=True)
            self.changes = tk.Text(box, width=CHANGES_SIZE[0], height=CHANGES_SIZE[1], wrap="word",
                                   font="TkDefaultFont", padx=8, pady=6)
            scroll = ttk.Scrollbar(box, orient="vertical", command=self.changes.yview)
            self.changes.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            self.changes.pack(side="left", fill="both", expand=True)
            self.changes.insert("1.0", answer.get("changes", ""))  # plain text: shown, never run or opened
            self.changes.configure(state="disabled")
            self._sentence(_("Update now closes TASlation, downloads the new version from GitHub, updates the program files and starts TASlation again. The files it replaces are kept: update.cmd -Back goes back to this version."),
                           pady=(10, 0))
            self.close_btn.configure(text=_("Later"))
            self.update_btn = ttk.Button(self.btns, text=_("Update now"), default="active",
                                         command=lambda: self._update(answer["newest"]))
            self.update_btn.pack(side="right", padx=(0, 6))
            self.update_btn.focus_set()

    def _answered(self, answer: dict[str, Any]) -> None:
        """(Tk) The asking program answered: noted (`updates.noted`) and kept for a minute (`updates.remember`), then
        shown."""
        self.check = None
        updates.noted(self.window, answer)
        updates.remember(self.window, answer)
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.answer = answer
        self._changed(lambda: self._show(answer["result"], answer))

    def _changed(self, change: Callable[[], None]) -> None:
        """(Tk) *change* to what the dialog says, then the dialog lowered for the work area as needed (`_fit`) and
        placed again at its new size (`layout.place_again`): until then it keeps its size and place
        (`layout.hold_size`), so that it is never seen grown where it stood."""
        before = layout.hold_size(self)
        try:
            change()
            self._fit()
        finally:
            layout.place_again(self, self.master, before)

    def _fit(self) -> None:
        """The changes box with fewer lines (it scrolls; at least `CHANGES_MIN_LINES`) while the dialog would be
        taller than the work area of the monitor it is placed on (`layout.dialog_area`, as `place_window` finds it)."""
        if self.changes is None:
            return
        area, _centre = layout.dialog_area(self, self.master)
        border, caption = layout.frame_extents()
        over = layout.asked_size(self)[1] - (area[3] - area[1] - caption - border)
        if over <= 0:
            return
        line = max(1, tkfont.Font(self, font=self.changes.cget("font")).metrics("linespace"))
        lines = int(self.changes.cget("height"))
        fewer = max(CHANGES_MIN_LINES, lines - -(-over // line))
        if fewer < lines:
            self.changes.configure(height=fewer)

    # ------------------------------------------------------------------ what it does
    def _keep_choice(self) -> None:
        """The box under the text: ``update_check`` kept in taslation.toml as the Settings dialog keeps a setting
        (from the next start); when it cannot be, the box goes back and says why."""
        value = "daily" if self.choice_var.get() else "off"
        try:
            config.write_settings(config.settings_file(self.window.settings), {"update_check": value})
        except (config.ConfigError, OSError) as e:
            self.choice_var.set(not self.choice_var.get())
            reason = getattr(e, "strerror", None) or str(e)
            note = in_lines(_("Not kept: {reason}").format(reason=reason), self.text_width)
            self._changed(lambda: self.choice_note.configure(text=note))
            return
        self.window.settings.update_check = value

    def _update(self, version: str) -> None:
        self.close()
        if self.on_update is not None:
            self.on_update(version)

    def close(self) -> None:
        if self.check is not None:
            self.check.cancel()
            self.check = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
