"""The keys of TASlation's own dialogs in one table (`ACTIONS`): the region editor's Previous and Next and its Copy
format and Paste format (`dialogs.review.EditBubbleDialog` binds them, `bind_on`; its buttons name them, `with_keys`).
Every other key goes to the viewer: TASlation binds none over it. A reader's own keys for these, kept in
``<state dir>/shortcuts.json`` by an earlier version (only the keys that differ from the table's), still apply
(`Keymap.load`); the keys of actions this version no longer has are left out of it. `current` is the keymap in force,
for the parts that have no window at hand (`set_current` makes it so).

A key is written as Tk names it, the modifiers first in the order Control, Alt, Shift: ``F5``, ``Control-z``,
``Alt-Shift-F2``. A letter is lowercase; Shift belongs to a letter only with Ctrl or Alt, and Enter (``Return``) is
bound with the keypad's Enter too (`normal`, `sequences`). `key_text` names a key as the keyboard does, in the window's
language ("Ctrl+Z", "Strg+Z").

A key of the editor has Ctrl or Alt or is an F key (a plain key would be taken from its text box), and is never Esc
(it closes the dialogs), Tab, F10 or Alt+F4 (Windows' own), Ctrl+A, C, V or X (the boxes' editing), nor the key of
another action: `Keymap.problem`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..atomic import write_atomic
from ..i18n import _
from .constants import KEY_ARROWS

SHORTCUTS_FILE = "shortcuts.json"  # in the state folder
MODIFIERS = ("Control", "Alt", "Shift")  # in this order in a key
WINDOWS_KEYS = frozenset({"Tab", "ISO_Left_Tab", "F10"})  # Windows' own (with Alt+F4)
EDITING_LETTERS = frozenset("acvx")  # Ctrl with them edits the text of a box
ALIASES = {"KP_Enter": "Return"}


@dataclass(frozen=True)
class Action:
    """One thing a dialog does on a key: its *name* (in the keymap's file), *label* (English, a key of the window's
    catalogs) and its *keys* at first."""

    name: str
    label: str
    keys: tuple[str, ...] = ()


ACTIONS: tuple[Action, ...] = (
    Action("copy_format", "Copy format", ("Control-Shift-c",)),
    Action("paste_format", "Paste format", ("Control-Shift-v",)),
    Action("editor_previous", "Region editor: save and go to the previous region", ("Alt-Up",)),
    Action("editor_next", "Region editor: save and go to the next region", ("Alt-Down",)),
)
BY_NAME = {action.name: action for action in ACTIONS}


def split(key: str) -> tuple[tuple[str, ...], str]:
    """The modifiers of *key* (in `MODIFIERS` order) and its key."""
    parts = key.split("-")
    mods = {p for p in parts[:-1] if p in MODIFIERS}
    return tuple(m for m in MODIFIERS if m in mods), parts[-1]


def normal(key: str) -> str:
    """*key* as the keymap writes it: the modifiers in order, a letter lowercase (Shift dropped from a plain one),
    the keypad's Enter as Enter."""
    mods, base = split(key)
    base = ALIASES.get(base, base)
    if len(base) == 1 and base.isalpha():
        if base.isupper() and ("Control" in mods or "Alt" in mods):
            mods = tuple(m for m in MODIFIERS if m in mods or m == "Shift")
        base = base.lower()
        if not ("Control" in mods or "Alt" in mods):
            mods = ()
    return "-".join((*mods, base))


def sequences(key: str) -> list[str]:
    """The Tk event sequences *key* is bound as: a plain letter in both cases, Enter with the keypad's Enter. A letter
    with Ctrl or Alt also as Caps Lock makes it: alone the capital (with Lock, ahead of the capital that Shift makes),
    with Shift the small letter (with Shift, ahead of the small one alone)."""
    mods, base = split(normal(key))
    if len(base) == 1 and base.isalpha():
        if not mods:
            return [f"<Key-{base}>", f"<Key-{base.upper()}>"]
        held = "".join(f"{m}-" for m in mods if m != "Shift")
        if "Shift" in mods:  # Shift is in the letter's case
            return [f"<{held}Key-{base.upper()}>", f"<{held}Shift-Key-{base}>"]
        return [f"<{held}Key-{base}>", f"<{held}Lock-Key-{base.upper()}>"]
    prefix = "".join(f"{m}-" for m in mods)
    if len(base) == 1:
        return [f"<{prefix}Key-{base}>"]
    out = [f"<{prefix}{base}>"]
    if base == "Return":
        out.append(f"<{prefix}KP_Enter>")
    return out


def key_names() -> dict[str, str]:
    """The names of the keys that have one, in the window's language."""
    return {"Control": _("Ctrl"), "Alt": _("Alt"), "Shift": _("Shift"), "Return": _("Enter"), "Escape": _("Esc"),
            "Delete": _("Del"), "BackSpace": _("Backspace"), "Insert": _("Insert"), "Tab": _("Tab"),
            "Prior": _("Page Up"), "Next": _("Page Down"), "Home": _("Home"), "End": _("End"), "space": _("Space"),
            "plus": "+", "minus": "-", "comma": ",", "period": ".", "slash": "/", "backslash": "\\",
            "semicolon": ";", "apostrophe": "'", "bracketleft": "[", "bracketright": "]", "grave": "`",
            "equal": "=", **KEY_ARROWS}


def key_text(key: str) -> str:
    """*key* as the keyboard names it, in the window's language: "Ctrl+Shift+Z", "F5", "Alt+↑", "Enter"."""
    mods, base = split(normal(key))
    names = key_names()
    shown = names.get(base, base.upper() if len(base) == 1 else base)
    return "+".join((*(names[m] for m in mods), shown))


def keys_text(keys: Iterable[str]) -> str:
    """Keys named one after the other ("F5, Ctrl+R"); "" for none."""
    return ", ".join(key_text(key) for key in keys)


class Keymap:
    """The keys of `ACTIONS` as the reader has them: the table's, with the reader's own over them (*own*: action
    name -> its keys, () for none). Never changed in place: `with_key`, `with_default` and `reset` give another."""

    def __init__(self, own: Mapping[str, Iterable[str]] | None = None):
        self.own: dict[str, tuple[str, ...]] = {}
        for name, keys in (own or {}).items():
            if name in BY_NAME:
                keys = tuple(normal(key) for key in keys)
                if keys != tuple(normal(key) for key in BY_NAME[name].keys):
                    self.own[name] = keys

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Keymap) and self.own == other.own

    def __repr__(self) -> str:
        return f"Keymap({self.own!r})"

    @property
    def customised(self) -> bool:
        return bool(self.own)

    def of(self, name: str) -> tuple[str, ...]:
        """The keys of the action *name*."""
        if name in self.own:
            return self.own[name]
        return tuple(normal(key) for key in BY_NAME[name].keys)

    def shown(self, name: str) -> str:
        """The keys of the action *name* as the buttons name them ("" for none)."""
        return keys_text(self.of(name))

    def owner(self, key: str) -> str | None:
        """The action *key* is the key of, if any."""
        key = normal(key)
        return next((action.name for action in ACTIONS if key in self.of(action.name)), None)

    def problem(self, name: str, key: str) -> str | None:
        """Why *key* cannot be the key of the action *name* (in English, for the log: no dialog sets keys any more),
        None when it can. A key the table gives the action itself is refused only while another action has it."""
        action = BY_NAME[name]
        key = normal(key)
        mods, base = split(key)
        own = key in {normal(k) for k in action.keys}
        if base == "Escape":
            return "Esc closes the dialogs"
        if (base in WINDOWS_KEYS or (base == "F4" and "Alt" in mods)) and not own:
            return "a key of Windows"
        if not own:  # (the editor has boxes to type in)
            if not ("Control" in mods or "Alt" in mods) and not _is_function_key(base):
                return "a plain key would be taken from the editor's text box"
            if mods == ("Control",) and base in EDITING_LETTERS:
                return "a key for editing the text in a box"
        other = self.owner(key)
        if other is not None and other != name:
            return f"already the key of {other}"
        return None

    def with_key(self, name: str, key: str | None) -> "Keymap":
        """This keymap with *key* the one key of the action *name* (None: no key)."""
        own = dict(self.own)
        own[name] = (normal(key),) if key else ()
        return Keymap(own)

    def with_default(self, name: str) -> "Keymap":
        """This keymap with the action *name* on its keys of the table."""
        return Keymap({k: v for k, v in self.own.items() if k != name})

    @staticmethod
    def reset() -> "Keymap":
        return Keymap()

    # ------------------------------------------------------------------ the file
    @classmethod
    def load(cls, state_dir: Path | str) -> "Keymap":
        """The reader's keys from the state folder (the table's where the file is missing, damaged or names what
        this version does not have); a key that cannot be the action's (`problem`) is left out."""
        try:
            data = json.loads((Path(state_dir) / SHORTCUTS_FILE).read_text(encoding="utf-8"))
            given = data.get("keys", {}) if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return cls()
        if not isinstance(given, dict):
            return cls()
        given = {name: keys for name, keys in given.items() if name in BY_NAME and isinstance(keys, list)
                 and all(isinstance(k, str) and k for k in keys)}
        keymap = cls({name: () for name in given})  # the keys they had let go first: a key may have moved
        for name, keys in given.items():
            for key in keys[:1]:
                if keymap.problem(name, key) is None:
                    keymap = keymap.with_key(name, key)
        return keymap

    def save(self, state_dir: Path | str) -> Path:
        """The reader's own keys into the state folder (only those that differ from the table's)."""
        path = Path(state_dir) / SHORTCUTS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"keys": {name: list(keys) for name, keys in sorted(self.own.items())}}, indent=1)
        write_atomic(path, (text + "\n").encode("utf-8"))
        return path


def _is_function_key(base: str) -> bool:
    return base[:1] == "F" and base[1:].isdigit() and 1 <= int(base[1:]) <= 24


_CURRENT: list[Keymap] = [Keymap()]


def current() -> Keymap:
    """The keymap in force (the table's until the window has set the reader's: `set_current`)."""
    return _CURRENT[0]


def set_current(keymap: Keymap) -> None:
    _CURRENT[0] = keymap


# ------------------------------------------------------------------ the bindings and the words
def bind_on(widgets: Iterable[Any], keymap: Keymap, handlers: Mapping[str, Callable[[Any], Any]]) -> None:
    """The keys of the actions in *handlers* (action name -> what a key press does) bound on each of *widgets*: a
    dialog made anew each time binds its own keys so (the region editor's Previous and Next, and Copy format and Paste
    format)."""
    for name, handler in handlers.items():
        for key in keymap.of(name):
            for seq in sequences(key):
                for widget in widgets:
                    widget.bind(seq, handler)


def with_keys(label: str, name: str, keymap: Keymap | None = None) -> str:
    """*label* (English, a key of the window's catalogs) in the window's language with the keys of the action *name*
    in brackets, as a button names them ("Previous (Alt+↑)"); the label alone for an action with no key."""
    shown = (keymap or current()).shown(name)
    return _(label) + (f" ({shown})" if shown else "")
