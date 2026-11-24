"""The keys of TASlation's own dialogs in one table (`ui.shortcuts`): the region editor's Previous and Next and its
Copy format and Paste format. The table's keys bound as they always were, a key named as the keyboard does, what a key
may not be, the reader's keys an earlier version kept in the state folder (the keys of actions this version no longer
has left out), the keys bound on a dialog's widgets and named on its buttons. TASlation binds no key over the viewer:
there is nothing else here."""

from __future__ import annotations

import json
import tkinter as tk

import pytest

from taslation.i18n import FEATURE_LANGUAGES, set_language
from taslation.ui import shortcuts
from taslation.ui.shortcuts import ACTIONS, BY_NAME, Keymap, key_text, normal, sequences


@pytest.fixture(autouse=True)
def table_keys_in_force():
    shortcuts.set_current(Keymap())
    yield
    shortcuts.set_current(Keymap())


# ------------------------------------------------------------------ the table
def test_every_action_is_named_in_every_language():
    from taslation import i18n
    from taslation.locales.keys import KEYS

    assert [a.name for a in ACTIONS] == ["copy_format", "paste_format", "editor_previous", "editor_next"]
    for english in [a.label for a in ACTIONS]:
        homes = [found for found in i18n.FEATURES.values() if english in found]
        assert english in KEYS or (homes and sorted(homes[0][english]) == sorted(FEATURE_LANGUAGES)), english


def test_the_table_s_keys_are_bound_as_they_always_were():
    keymap = Keymap()
    bound = {a.name: [s for key in keymap.of(a.name) for s in sequences(key)] for a in ACTIONS}
    assert bound == {"copy_format": ["<Control-Key-C>", "<Control-Shift-Key-c>"],
                     "paste_format": ["<Control-Key-V>", "<Control-Shift-Key-v>"],
                     "editor_previous": ["<Alt-Up>"], "editor_next": ["<Alt-Down>"]}
    assert all(keymap.problem(a.name, key) is None for a in ACTIONS for key in a.keys)


def test_the_editor_s_keys_and_the_formats_keys_are_apart_and_each_refused_to_the_other():
    keymap = Keymap()
    assert keymap.owner("Alt-Down") == "editor_next" and keymap.owner("Control-Shift-c") == "copy_format"
    assert keymap.owner("Control-c") is None  # (the boxes' own Ctrl+C: no action's)
    assert "already the key of paste_format" in keymap.problem("editor_next", "Control-Shift-v")
    assert "already the key of editor_next" in keymap.with_key("editor_next", "Alt-n").problem("copy_format", "Alt-n")
    assert keymap.problem("editor_next", "Alt-n") is None and keymap.problem("editor_next", "F8") is None
    assert "plain key" in keymap.problem("editor_next", "Down")  # its text box would take it
    assert "plain key" in keymap.problem("copy_format", "c")
    assert "editing the text" in keymap.problem("editor_next", "Control-v")
    assert keymap.problem("editor_next", "F1") is None


def test_a_key_is_bound_in_both_cases_and_with_the_keypad_s_enter():
    assert sequences("1") == ["<Key-1>"] and sequences("t") == ["<Key-t>", "<Key-T>"]
    # Caps Lock turns the letter: Ctrl+Z and Ctrl+Shift+Z are told apart with it on too
    assert sequences("Control-z") == ["<Control-Key-z>", "<Control-Lock-Key-Z>"]
    assert sequences("Control-Shift-z") == ["<Control-Key-Z>", "<Control-Shift-Key-z>"]
    assert normal("Shift-Control-Z") == "Control-Shift-z" and sequences("Alt-F2") == ["<Alt-F2>"]
    assert normal("KP_Enter") == "Return" and sequences("Return") == ["<Return>", "<KP_Enter>"]
    assert normal("T") == "t" and normal("Shift-t") == "t"  # (Shift belongs to a letter only with Ctrl or Alt)


def test_a_key_is_named_as_the_keyboard_names_it_in_the_window_s_language():
    assert [key_text(k) for k in ("Control-Shift-z", "Return", "t", "Delete", "Prior", "Left", "Alt-F4")] == [
        "Ctrl+Shift+Z", "Enter", "T", "Del", "Page Up", "←", "Alt+F4"]
    assert shortcuts.keys_text(("F5", "Control-r")) == "F5, Ctrl+R" and shortcuts.keys_text(()) == ""
    set_language("de")
    try:
        assert key_text("Control-z") == "Strg+Z" and key_text("Delete") == "Entf"
    finally:
        set_language("en")


@pytest.mark.parametrize("name, key, why", [
    ("copy_format", "Escape", "Esc closes the dialogs"), ("copy_format", "Tab", "a key of Windows"),
    ("editor_next", "F10", "a key of Windows"), ("editor_next", "Alt-F4", "a key of Windows"),
    ("editor_next", "s", "plain key"), ("copy_format", "Control-c", "editing the text"),
    ("paste_format", "Control-x", "editing the text"), ("editor_next", "Alt-Up", "already the key of editor_previous")])
def test_what_a_key_may_not_be(name, key, why):
    assert why in Keymap().problem(name, key)


def test_an_editor_key_may_be_an_f_key_or_with_ctrl_or_alt():
    keymap = Keymap()
    assert keymap.problem("editor_next", "F4") is None and keymap.problem("editor_next", "Alt-s") is None
    assert keymap.problem("editor_previous", "Control-comma") is None
    assert keymap.problem("copy_format", "Control-Alt-c") is None  # (not the boxes' Ctrl+C)


# ------------------------------------------------------------------ the keymap and its file
def test_the_keymap_keeps_what_differs_from_the_table_and_its_file_holds_that_alone(tmp_path):
    keymap = Keymap().with_key("copy_format", "F6").with_key("editor_next", "Alt-n").with_key("paste_format", None)
    assert keymap.of("copy_format") == ("F6",) and keymap.of("paste_format") == () and keymap.customised
    assert keymap.shown("copy_format") == "F6" and keymap.shown("paste_format") == ""
    assert keymap.owner("Alt-n") == "editor_next"
    assert keymap.with_default("copy_format").of("copy_format") == ("Control-Shift-c",)
    assert Keymap().with_key("copy_format", "Control-Shift-C") == Keymap() and not Keymap.reset().customised
    path = keymap.save(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "keys": {"copy_format": ["F6"], "editor_next": ["Alt-n"], "paste_format": []}}
    assert Keymap.load(tmp_path) == keymap


def test_a_damaged_file_or_a_key_that_cannot_be_is_left_out(tmp_path):
    assert Keymap.load(tmp_path) == Keymap()  # no file
    (tmp_path / shortcuts.SHORTCUTS_FILE).write_text("{not json", encoding="utf-8")
    assert Keymap.load(tmp_path) == Keymap()
    (tmp_path / shortcuts.SHORTCUTS_FILE).write_text(json.dumps(["not", "a", "table"]), encoding="utf-8")
    assert Keymap.load(tmp_path) == Keymap()
    (tmp_path / shortcuts.SHORTCUTS_FILE).write_text(json.dumps({"keys": {
        "editor_next": ["Alt-Up"], "editor_previous": ["F6"], "copy_format": ["Left"], "gone": ["F7"],
        "paste_format": "x"}}), encoding="utf-8")
    keymap = Keymap.load(tmp_path)  # Alt+Up moved: the keys let go first
    assert keymap.of("editor_next") == ("Alt-Up",) and keymap.of("editor_previous") == ("F6",)
    assert keymap.of("copy_format") == () and keymap.of("paste_format") == ("Control-Shift-v",)


def test_the_keys_an_earlier_version_kept_for_actions_this_one_has_not_are_left_out(tmp_path):
    (tmp_path / shortcuts.SHORTCUTS_FILE).write_text(json.dumps({"keys": {
        "read_whole_book": ["Control-b"], "translate_now": ["F6"], "reading_mode": [], "copy_format": ["F6"]}}),
        encoding="utf-8")
    keymap = Keymap.load(tmp_path)
    assert not {"read_whole_book", "translate_now", "reading_mode"} & set(BY_NAME) and keymap.owner("Control-b") is None
    assert keymap == Keymap().with_key("copy_format", "F6") and keymap.of("copy_format") == ("F6",)


# ------------------------------------------------------------------ on a dialog
def test_a_dialog_binds_its_keys_on_its_widgets_and_its_buttons_name_them(hidden_root):
    window, text = tk.Frame(hidden_root), tk.Text(hidden_root)
    calls = []
    handlers = {"editor_previous": lambda e: calls.append("previous"), "editor_next": lambda e: calls.append("next")}
    shortcuts.bind_on((window, text), Keymap(), handlers)
    assert set(window.bind()) == set(text.bind()) == {"<Alt-Key-Up>", "<Alt-Key-Down>"}
    keymap = Keymap().with_key("editor_next", "F8").with_key("editor_previous", None)
    other = tk.Frame(hidden_root)
    shortcuts.bind_on((other,), keymap, handlers)
    assert set(other.bind()) == {"<Key-F8>"}
    assert shortcuts.with_keys("Previous", "editor_previous") == "Previous (Alt+↑)"
    assert shortcuts.with_keys("Next", "editor_next", keymap) == "Next (F8)"
    assert shortcuts.with_keys("Previous", "editor_previous", keymap) == "Previous"  # no key: the label alone
    shortcuts.set_current(keymap)  # the reader's keys, in force for the dialogs made from now on
    assert shortcuts.with_keys("Next", "editor_next") == "Next (F8)"


def test_the_buttons_name_the_keys_in_the_window_s_language():
    from taslation.i18n import _

    set_language("de")
    try:
        shown = key_text("Control-Shift-c")
        assert shown.startswith("Strg+") and shown.endswith("+C")
        assert shortcuts.with_keys("Copy format", "copy_format") == f"{_('Copy format')} ({shown})"
        assert _("Copy format") != "Copy format"
    finally:
        set_language("en")
