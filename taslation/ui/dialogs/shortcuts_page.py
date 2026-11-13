"""The Shortcuts page of Tools > Settings... (`ShortcutsPage`): every action of `shortcuts.ACTIONS` with its key, the
keys it cannot change below them in grey (Esc, and the page keys passed on to the viewer, which Page > Page keys...
sets), and Change key... (the next key pressed, checked by `Keymap.problem`), No key, Default and Reset all. What
it changes is kept in `keymap` until the dialog's Save (`SettingsDialog.save`: `Keymap.save` and the window's
`on_keys`)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ...i18n import _
from ..shortcuts import ACTIONS, BY_NAME, Keymap, fixed_rows, key_of_event
from ..tooltip import tip
from .caches import in_lines

FIXED_COLOUR = "#6b6b6b"  # the rows of the keys this page does not change
ROWS_SHOWN = 12  # lines of the list
NO_MESSAGE = ""  # what the message line says once a key is set


class ShortcutsPage(ttk.Frame):
    """The list of the actions and their keys over *keymap*; *say* (text, error) puts what happened in the dialog's
    message line, broken at *width* pixels. ``keymap`` is what the page shows (`changed` when it is not what was
    saved last: ``saved``)."""

    def __init__(self, master: tk.Misc, keymap: Keymap, say: Callable[..., None], width: int):
        super().__init__(master, padding=8)
        self.keymap = self.saved = keymap
        self.say = say
        self.capturing: str | None = None
        zero = max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("key",), show="tree headings", height=ROWS_SHOWN, selectmode="browse")
        self.tree.heading("#0", text=_("Action"), anchor="w")
        self.tree.heading("key", text=_("Key"), anchor="w")
        self.tree.column("#0", width=34 * zero, stretch=True)
        self.tree.column("key", width=16 * zero, stretch=True)
        self.tree.tag_configure("fixed", foreground=FIXED_COLOUR)
        bar = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for action in ACTIONS:
            self.tree.insert("", "end", iid=action.name, text=_(action.label), values=("",))
        for i, (what, keys) in enumerate(fixed_rows()):
            self.tree.insert("", "end", iid=f"fixed-{i}", text=what, values=(keys,), tags=("fixed",))
        self.tree.bind("<Double-Button-1>", lambda _e: self.change())
        self.tree.bind("<Return>", lambda _e: self.change())

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 0))
        for text, command, hint in (
                (_("Change key..."), self.change, _("Choose an action in the list, then press its new key.")),
                (_("No key"), self.clear, _("The chosen action has no key.")),
                (_("Default"), self.default, _("The chosen action's key as it was at first.")),
                (_("Reset all"), self.reset, _("Every key as it was at first."))):
            button = ttk.Button(row, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            tip(hint, button)
        self.capture_var = tk.StringVar(self, value="")
        self.capture = ttk.Entry(self, textvariable=self.capture_var, state="readonly", width=40)
        self.capture.pack(fill="x", pady=(6, 0))
        self.capture.bind("<KeyPress>", self._take)
        self.capture.bind("<FocusOut>", lambda _e: self._stop())
        note = _("Over the full-screen viewer, F5, F11 and Esc keep their keys. The keys apply once you press Save.")
        ttk.Label(self, text=in_lines(note, width), justify="left", foreground=FIXED_COLOUR).pack(
            anchor="w", pady=(6, 0))
        self.show()

    # ------------------------------------------------------------------ what it shows
    @property
    def changed(self) -> bool:
        return self.keymap != self.saved

    def show(self) -> None:
        """Every action's row with its keys as ``keymap`` has them."""
        for action in ACTIONS:
            self.tree.set(action.name, "key", self.keymap.shown(action.name))

    def chosen(self) -> str | None:
        """The action of the chosen row (None: none, or a fixed key's)."""
        picked = self.tree.selection()
        return picked[0] if picked and picked[0] in BY_NAME else None

    def _set(self, keymap: Keymap) -> None:
        self.keymap = keymap
        self.show()

    # ------------------------------------------------------------------ the buttons
    def change(self) -> None:
        """Change key...: the next key pressed becomes the chosen action's (Esc: cancel)."""
        name = self.chosen()
        if name is None:
            self.say(_("Choose an action in the list first."), error=True)
            return
        self.capturing = name
        self.capture.configure(state="normal")
        self.capture_var.set(_("Press the new key for {action} (Esc: cancel).").format(action=_(BY_NAME[name].label)))
        self.capture.configure(state="readonly")
        self.capture.focus_set()
        self.say(NO_MESSAGE)

    def press(self, key: str | None) -> bool:
        """*key* pressed while a key is awaited: the chosen action's key when it can be (said in the message line
        when not), "Escape" cancels, None (a modifier alone) waits on. Whether the wait ended."""
        name = self.capturing
        if name is None or key is None:
            return False
        if key == "Escape":
            self._stop()
            self.say(NO_MESSAGE)  # a key refused before it goes with the wait
            return True
        problem = self.keymap.problem(name, key)
        if problem:
            self.say(problem, error=True)
            return False
        self._set(self.keymap.with_key(name, key))
        self.say(NO_MESSAGE)
        self._stop()
        return True

    def _take(self, event: Any) -> str:
        if self.capturing is not None:
            self.press(key_of_event(event))
        return "break"  # (Esc and Enter stay this box's: the dialog is not closed nor saved)

    def _stop(self) -> None:
        self.capturing = None
        self.capture.configure(state="normal")
        self.capture_var.set("")
        self.capture.configure(state="readonly")

    def clear(self) -> None:
        name = self.chosen()
        if name is not None:
            self._set(self.keymap.with_key(name, None))

    def default(self) -> None:
        """Default: the chosen action on its keys of the table, unless another action has one of them now."""
        name = self.chosen()
        if name is None:
            return
        for key in BY_NAME[name].keys:
            problem = self.keymap.problem(name, key)
            if problem:
                self.say(problem, error=True)
                return
        self._set(self.keymap.with_default(name))

    def reset(self) -> None:
        self._set(Keymap.reset())

    def saved_now(self) -> None:
        """Save wrote ``keymap``: it is what was saved last."""
        self.saved = self.keymap
