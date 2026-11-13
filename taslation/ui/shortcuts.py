"""The window's keys in one table (`ACTIONS`), which the bindings (`bind_keys`), the menus' and the toolbar's key
names (`Keymap.shown`) and Help > How to use's Keys (`help_lines`) all read, with the reader's own keys over it
(`Keymap`: Tools > Settings... > Shortcuts, kept in ``<state dir>/shortcuts.json``: only the keys that differ from the
table's). `current` is the keymap in force, for the parts that have no window at hand (`set_current` makes it so).

A key is written as Tk names it, the modifiers first in the order Control, Alt, Shift: ``F5``, ``Control-z``,
``Alt-Shift-F2``, ``t``. A letter is lowercase; Shift belongs to a letter only with Ctrl or Alt (a plain letter is
bound in both cases, as T always was), and Enter (``Return``) is bound with the keypad's Enter too (`normal`,
`sequences`). `key_of_event` makes one from a key press, `key_text` names it as the keyboard does, in the window's
language ("Ctrl+Z", "Strg+Z").

Where a key works (`Action.scope`): a "window" key anywhere in the window (bound on it), so it has Ctrl or Alt or is
an F key, else it would be taken from the boxes one types in; a "page" key while the page has the keys (bound on it;
plain keys too); an "editor" key in the region editor (`dialogs.review.EditBubbleDialog` binds it, `bind_on`), with
Ctrl or Alt or an F key as in the window. Copy format and Paste format work on the page and in the editor alike
(`Action.editor`). Translator mode's tools (`Action.translator`) do nothing in the Reader role, where their buttons are
not there. Never a key of another action that works in the same place (`meet`), a key passed on to the viewer
(`constants.FORWARDED_KEYS`, with any modifier) for the window or the page, Esc (`FIXED`: it leaves reading mode, lets
go of the chosen box, stops a run and closes the dialogs), Tab, F10 or Alt+F4 (Windows' own), nor in the window or
the editor Ctrl+A, C, V or X (the boxes' editing): `Keymap.problem`. The table's own keys of an action pass those
rules for it: Tab and Shift+Tab going through the regions and Alt with an arrow nudging them hold the keys on the page
themselves ("break"), and Ctrl+C and Ctrl+V copy and paste a region on the page, which has no text to edit.

The viewer's page keys are Page > Page keys...'s (`dialogs.pagekeys`): shown read-only (`FIXED`), as are translator
mode's mouse gestures (`FIXED_GESTURES`: a click and a drag, Shift while rotating, a drag on empty space, Shift+click,
a Shift+drag band, and what acts on several selected). Over the full-screen viewer, F5, F11 and Esc are hot keys of
their own (`overbook.OVER_HOTKEYS`) and keep those keys."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..atomic import write_atomic
from ..i18n import _
from .constants import FORWARDED_KEYS, KEY_ARROWS

SHORTCUTS_FILE = "shortcuts.json"  # in the state folder
SCOPES = ("window", "page", "editor")
MODIFIERS = ("Control", "Alt", "Shift")  # in this order in a key
SHIFT_MASK, CONTROL_MASK = 0x1, 0x4
ALT_MASK = 0x20000 if sys.platform == "win32" else 0x8  # (on Windows, Tk's Mod1 is Num Lock)
MODIFIER_KEYSYMS = frozenset({"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock",
                              "Num_Lock", "Scroll_Lock", "Win_L", "Win_R", "Meta_L", "Meta_R", "Super_L", "Super_R",
                              "App", "ISO_Level3_Shift"})
WINDOWS_KEYS = frozenset({"Tab", "ISO_Left_Tab", "F10"})  # Windows' own (with Alt+F4)
EDITING_LETTERS = frozenset("acvx")  # Ctrl with them edits the text of a box
ALIASES = {"KP_Enter": "Return"}


@dataclass(frozen=True)
class Action:
    """One thing the window does on a key: its *name* (in the keymap's file), *label* (English, a key of the window's
    catalogs), its *keys* at first, the *scope* it works in, whether it is translator mode's (*translator*) and whether
    the region editor does it too, on the same keys (*editor*)."""

    name: str
    label: str
    keys: tuple[str, ...] = ()
    scope: str = "window"
    translator: bool = False
    editor: bool = False


ACTIONS: tuple[Action, ...] = (
    Action("translate_now", "Translate the page on show", ("F5",)),
    Action("reading_mode", "Reading mode", ("F11",)),
    Action("undo", "Undo", ("Control-z",)),
    Action("redo", "Redo", ("Control-y",)),
    Action("show_original", "Show original"),
    Action("always_on_top", "Always on top"),
    Action("over_viewer", "Over the full-screen viewer"),
    Action("order_numbers", "Reading-order numbers"),
    Action("read_whole_book", "Read whole book..."),
    Action("set_area", "Set area..."),
    Action("page_keys", "Page keys..."),
    Action("saved_translations", "Saved translations..."),
    Action("settings", "Settings..."),
    Action("how_to_use", "How to use...", ("F1",)),
    Action("keys_help", "Keys...", ("Shift-F1",)),
    Action("edit_box", "Edit the chosen box", ("Return",), "page"),
    Action("remove_box", "Remove the chosen box", ("Delete",), "page"),
    Action("text_direction", "Text direction", ("t",), "page"),
    Action("next_region", "Select the next region", ("Tab",), "page", True),
    Action("previous_region", "Select the previous region", ("Shift-Tab",), "page", True),
    Action("nudge_left", "Move the selected regions left by 1 pixel (with Shift, by 10)", ("Alt-Left",), "page", True),
    Action("nudge_right", "Move the selected regions right by 1 pixel (with Shift, by 10)", ("Alt-Right",), "page",
           True),
    Action("nudge_up", "Move the selected regions up by 1 pixel (with Shift, by 10)", ("Alt-Up",), "page", True),
    Action("nudge_down", "Move the selected regions down by 1 pixel (with Shift, by 10)", ("Alt-Down",), "page", True),
    Action("copy_format", "Copy format", ("Control-Shift-c",), "page", True, editor=True),
    Action("paste_format", "Paste format", ("Control-Shift-v",), "page", True, editor=True),
    Action("copy_region", "Copy region", ("Control-c",), "page", True),
    Action("paste_region", "Paste region", ("Control-v",), "page", True),
    Action("reading_order", "Reading order", (), "page", True),
    Action("skip_page", "Skip page", (), "page", True),
    Action("translate_again", "Translate again", (), "page", True),
    Action("book_settings", "Book settings...", (), "page", True),
    Action("series_sheet", "Series sheet...", (), "page", True),
    Action("review", "Review...", (), "page", True),
    Action("find_replace", "Find and replace...", (), "page", True),
    Action("ignore_area", "Ignore this area on all pages of this book", (), "page", True),
    Action("paste_format_on_kind", "Paste format on every region of this kind...", (), "page", True),
    Action("set_kind", "Set kind...", (), "page", True),
    Action("set_text_size", "Set text size...", (), "page", True),
    Action("place_in_order", "Place in reading order...", (), "page", True),
    Action("editor_previous", "Region editor: save and go to the previous region", ("Alt-Up",), "editor"),
    Action("editor_next", "Region editor: save and go to the next region", ("Alt-Down",), "editor"),
)
BY_NAME = {action.name: action for action in ACTIONS}
FIXED_ESCAPE = "Leave reading mode, or let go of the chosen box"
FIXED_PAGE_KEYS = "Passed on to the viewer, which turns its pages with the keys of Page > Page keys..."
# translator mode's mouse gestures, read-only like Esc: (what it does, the gesture), keys of the window's catalogs
FIXED_GESTURES = (
    ("Select a region and move it; its handles resize it, its round handle rotates it.", "Click, drag"),
    ("Rotate in steps of 15°.", "Shift while rotating"),
    ("Add a region.", "Drag on empty space"),
    ("Add a region to the selection, or take it out of it.", "Shift+click"),
    ("Add every region inside the rectangle you draw to the selection.", "Shift+drag"),
    ("Removing, the text direction, moving (with the keys or a drag) and pasting a format act on all of them, as one "
     "change.", "Several selected"),
)


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


def key_of_event(event: Any) -> str | None:
    """The key a key press stands for, None for a modifier pressed alone."""
    keysym = str(getattr(event, "keysym", "") or "")
    if not keysym or keysym in MODIFIER_KEYSYMS or keysym == "??":
        return None
    try:
        state = int(getattr(event, "state", 0) or 0)
    except (TypeError, ValueError):
        state = 0
    mods = [name for name, mask in (("Control", CONTROL_MASK), ("Alt", ALT_MASK), ("Shift", SHIFT_MASK))
            if state & mask]
    return normal("-".join((*mods, keysym)))


def key_names() -> dict[str, str]:
    """The names of the keys that have one, in the window's language."""
    return {"Control": _("Ctrl"), "Alt": _("Alt"), "Shift": _("Shift"), "Return": _("Enter"), "Escape": _("Esc"),
            "Delete": _("Del"), "BackSpace": _("Backspace"), "Insert": _("Insert"), "Tab": _("Tab"),
            "Prior": _("Page Up"), "Next": _("Page Down"), "Home": _("Home"), "End": _("End"), "space": _("Space"),
            "plus": "+", "minus": "-", "comma": ",", "period": ".", "slash": "/", "backslash": "\\",
            "semicolon": ";", "apostrophe": "'", "bracketleft": "[", "bracketright": "]", "grave": "`",
            "equal": "=", **KEY_ARROWS}


def key_text(key: str) -> str:
    """*key* as the keyboard names it, in the window's language: "Ctrl+Shift+Z", "F5", "T", "Enter"."""
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
        """The keys of the action *name* as the menus and buttons name them ("" for none)."""
        return keys_text(self.of(name))

    def owner(self, key: str, near: str | None = None) -> str | None:
        """The action *key* is the key of, if any; with *near* (an action's name) only among the actions that work
        where that one does (`meet`), itself among them."""
        key = normal(key)
        return next((action.name for action in ACTIONS if key in self.of(action.name)
                     and (near is None or meet(BY_NAME[near], action))), None)

    def problem(self, name: str, key: str) -> str | None:
        """Why *key* cannot be the key of the action *name* (in the window's language), None when it can. A key the
        table gives the action itself is refused only while another action has it."""
        action = BY_NAME[name]
        key = normal(key)
        mods, base = split(key)
        shown = key_text(key)
        own = key in {normal(k) for k in action.keys}
        if base in FORWARDED_KEYS and action.scope != "editor" and not own:
            return _("{key} turns the viewer's pages (Page > Page keys...).").format(key=shown)
        if base == "Escape":
            return _("Esc is fixed: it leaves reading mode, lets go of the chosen box and closes the dialogs.")
        if (base in WINDOWS_KEYS or (base == "F4" and "Alt" in mods)) and not own:
            return _("{key} is a key of Windows.").format(key=shown)
        if (action.scope in ("window", "editor") or action.editor) and not own:  # (the editor has boxes to type in)
            if not ("Control" in mods or "Alt" in mods) and not _is_function_key(base):
                if action.scope == "window":
                    return _("A key for the whole window needs Ctrl or Alt, or is an F key: a plain key would be taken from the boxes you type in.")
                return _("A key that works in the region editor needs Ctrl or Alt, or is an F key: a plain key would be taken from its text box.")
            if mods == ("Control",) and base in EDITING_LETTERS:
                return _("{key} is for editing the text in a box.").format(key=shown)
        other = self.owner(key, near=name)
        if other is not None and other != name:
            return _("{key} is already the key of {action}.").format(key=shown, action=_(BY_NAME[other].label))
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


def places(action: Action) -> set[str]:
    """Where *action*'s keys work: its scope, the editor too for Copy format and Paste format, and for a window key
    the page as well (the window's bindings run for the page)."""
    out = {action.scope, *(("editor",) if action.editor else ())}
    return out | {"page"} if "window" in out else out


def meet(one: Action, other: Action) -> bool:
    """Whether two actions work in a place in common, so that they cannot share a key (Alt+Down nudges the regions on
    the page and goes to the next region in the editor)."""
    return bool(places(one) & places(other))


_CURRENT: list[Keymap] = [Keymap()]


def current() -> Keymap:
    """The keymap in force (the table's until the window has set the reader's: `set_current`)."""
    return _CURRENT[0]


def set_current(keymap: Keymap) -> None:
    _CURRENT[0] = keymap


# ------------------------------------------------------------------ the bindings and the words
def bind_keys(widgets: Mapping[str, Any], keymap: Keymap, handlers: Mapping[str, Callable[[Any], Any]],
              bound: Iterable[tuple[str, str]] = ()) -> list[tuple[str, str]]:
    """The keys of *keymap* bound on *widgets* (scope -> widget) to *handlers* (action name -> what a key press
    does; an action without one is left unbound). What was bound before goes first: *bound* (as this returned it
    last time) and the table's own keys (as the parts may have bound them themselves). The (scope, sequence) bound."""
    unbind = set(bound)
    for action in ACTIONS:
        unbind.update((action.scope, seq) for key in action.keys for seq in sequences(key))
    for scope, seq in sorted(unbind):
        widget = widgets.get(scope)
        if widget is not None:
            widget.unbind(seq)
    out: list[tuple[str, str]] = []
    for action in ACTIONS:
        handler = handlers.get(action.name)
        widget = widgets.get(action.scope)
        if handler is None or widget is None:
            continue
        for key in keymap.of(action.name):
            for seq in sequences(key):
                widget.bind(seq, handler)
                out.append((action.scope, seq))
    return out


def bind_on(widgets: Iterable[Any], keymap: Keymap, handlers: Mapping[str, Callable[[Any], Any]]) -> None:
    """The keys of the actions in *handlers* (action name -> what a key press does) bound on each of *widgets*,
    whatever their scope: a dialog made anew each time binds its own keys so (the region editor's Previous and Next,
    and Copy format and Paste format on the page's keys)."""
    for name, handler in handlers.items():
        for key in keymap.of(name):
            for seq in sequences(key):
                for widget in widgets:
                    widget.bind(seq, handler)


def with_keys(label: str, name: str, keymap: Keymap | None = None) -> str:
    """*label* (English, a key of the window's catalogs) in the window's language with the keys of the action *name*
    in brackets, as a button names them ("Undo (Ctrl+Z)"); the label alone for an action with no key."""
    shown = (keymap or current()).shown(name)
    return _(label) + (f" ({shown})" if shown else "")


def fixed_rows() -> list[tuple[str, str]]:
    """The keys this table does not change, as the Shortcuts page lists them: (what, keys), in the window's language:
    Esc, the page keys passed on to the viewer, then translator mode's mouse gestures (`FIXED_GESTURES`)."""
    page_keys = ", ".join(key_text(k) for k in FORWARDED_KEYS)
    return [(_(FIXED_ESCAPE), key_text("Escape")), (_(FIXED_PAGE_KEYS), page_keys),
            *((_(what), _(gesture)) for what, gesture in FIXED_GESTURES)]


def help_lines(keymap: Keymap | None = None) -> list[str]:
    """Help's Keys as the keymap has them: "F5: Translate the page on show", one line per action with a key, then
    Esc and the mouse gestures (the page keys have a topic of their own), in the window's language."""
    keymap = keymap or current()
    lines = [_("{keys}: {action}").format(keys=keymap.shown(a.name), action=_(a.label))
             for a in ACTIONS if keymap.of(a.name)]
    fixed = fixed_rows()
    lines += [_("{keys}: {action}").format(keys=keys, action=what) for what, keys in fixed[:1] + fixed[2:]]
    return lines
