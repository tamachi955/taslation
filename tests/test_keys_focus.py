"""The keys can be found and the page keeps them: Help > Keys... opens the help at its Keys topic, which lists every
key of the shortcuts table as the keymap has it in the window's language, the Help menu shows F1 and Shift+F1, Tab and
Shift+Tab go through the regions in reading order, Alt with an arrow nudges the selected region (one move for Ctrl+Z),
Esc in a text box gives the keys back to the page, and the strip's hint names the keys in force."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest
from test_translator_mode import Window, window  # noqa: F401 - the fixture, with its pipeline

from taslation.i18n import CATALOGS, _, set_language
from taslation.ui import app as app_mod
from taslation.ui import shortcuts, translator
from taslation.ui.dialogs import help as help_mod


# ------------------------------------------------------------------ Help > Keys...
def test_the_keys_topic_lists_every_key_in_the_windows_language():
    keys_topic = dict(help_mod.TOPICS)[help_mod.KEYS_TOPIC]
    lines = help_mod.topic_lines(help_mod.KEYS_TOPIC, keys_topic)  # the shortcuts table's keys, Esc, the mouse's ways
    keyed = [a for a in shortcuts.ACTIONS if a.keys]
    assert len(lines) == len(keyed) + 1 + len(shortcuts.FIXED_GESTURES) + 1 and len(keyed) >= 15
    assert {"Ctrl+Z: Undo", "Ctrl+Y: Redo", "Tab: Select the next region", "Shift+Tab: Select the previous region",
            "Alt+←: Move the selected regions left by 1 pixel (with Shift, by 10)",
            "Alt+↓: Region editor: save and go to the next region", "Shift while rotating: Rotate in steps of 15°.",
            "T: Text direction", "F5: Translate the page on show", "Shift+F1: Keys..."} <= set(lines)
    set_language("de")
    try:
        lines = help_mod.topic_lines(help_mod.KEYS_TOPIC, keys_topic)
        assert f"Strg+Z: {_('Undo')}" in lines and any(line.startswith("Entf: ") for line in lines)
        assert any(line.startswith("F5: ") for line in lines) and _(help_mod.KEYS_TOPIC) == "Tasten"
    finally:
        set_language("en")


def test_help_keys_opens_the_help_at_its_keys_topic(hidden_root):
    shown = []
    w = SimpleNamespace(open_help=lambda: shown.append("help"), _help=SimpleNamespace(show_topic=shown.append))
    app_mod.App.open_keys(w)
    assert shown == ["help", "Keys"]
    help_window = help_mod.HelpWindow(hidden_root)
    help_window.geometry("500x300")
    help_window.update_idletasks()
    help_window.show_topic("Keys")
    help_window.update_idletasks()
    assert help_window.text.index("@0,0") == help_window.topics["Keys"] != "1.0"
    assert help_window.text.get(help_window.topics["Keys"], f"{help_window.topics['Keys']} lineend") == "Keys"
    help_window.destroy()


# ------------------------------------------------------------------ Esc in a text box
class Escaping(tk.Toplevel):
    _escape_key = app_mod.App._escape_key

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.calls: list[str] = []
        self.entry, self.combo, self.text = ttk.Entry(self), ttk.Combobox(self), tk.Text(self)
        self.button = ttk.Button(self)

    def _focus_page(self):
        self.calls.append("page")

    def _on_escape(self):
        self.calls.append("escape")


def test_esc_in_a_text_box_gives_the_keys_back_to_the_page_and_does_nothing_else(hidden_root):
    w = Escaping(hidden_root)
    for box in (w.entry, w.combo, w.text):
        w._escape_key(SimpleNamespace(widget=box))
    assert w.calls == ["page"] * 3  # never the run's Stop, nor a deselection
    w.calls.clear()
    w._escape_key(SimpleNamespace(widget=w.button))
    w._escape_key(SimpleNamespace(widget=w))
    assert w.calls == ["escape", "escape"]
    w.destroy()


# ------------------------------------------------------------------ Tab and Alt+arrows on the page
class Keys(Window):
    _editing = app_mod.App._editing
    _tab_region = app_mod.App._tab_region
    _nudge_key = app_mod.App._nudge_key
    _nudge_done = app_mod.App._nudge_done

    def __init__(self, pipeline, result):
        super().__init__(pipeline, result)
        self._grip_box = None
        self.timers: dict[int, object] = {}
        self.forwarded: list[str] = []
        self.drawn = 0

    def _draw_frame(self):
        self.drawn += 1

    def after(self, _ms, job):
        key = len(self.timers) + 1
        self.timers[key] = job
        return key

    def after_cancel(self, key):
        self.timers.pop(key, None)

    def fire(self):
        jobs, self.timers = list(self.timers.values()), {}
        for job in jobs:
            job()

    def forward_key(self, key):
        self.forwarded.append(key)


@pytest.fixture
def keys(window):  # noqa: F811 - the fixture of test_translator_mode
    return Keys(window.pipeline, window.last_result)


def test_tab_goes_through_the_regions_in_reading_order_and_round(keys):
    w = keys
    regions = w._page_regions()
    assert len(regions) >= 3
    assert w._tab_region(1) == "break" and w._chosen_region is regions[0]
    assert w.said[-1] == translator.REGION_OF
    w._tab_region(1)
    assert w._chosen_region is regions[1]
    w._tab_region(-1)
    w._tab_region(-1)
    assert w._chosen_region is regions[-1]  # round from the first to the last
    w._chosen_region = None
    w._tab_region(-1)
    assert w._chosen_region is regions[-1]
    w.role_var.set("reader")
    assert w._tab_region(1) is None  # the Reader role: Tab moves the focus as always


def test_alt_arrows_nudge_the_selected_region_as_one_move(keys):
    w = keys
    target = w.region("Hello there!")
    w._choose(target)
    start, box = w.state(), target.bbox
    shift = SimpleNamespace(state=0x0001)
    for _ in range(3):
        assert w._nudge_key(SimpleNamespace(state=0), "Right") == "break"
    w._nudge_key(shift, "Down")
    assert w._grip_box == (box[0] + 3, box[1] + 10, box[2] + 3, box[3] + 10) and len(w.timers) == 1
    assert target.bbox == box  # nothing stored before the presses stop
    w.fire()
    moved = w.region("Hello there!")
    assert moved.bbox == (box[0] + 3, box[1] + 10, box[2] + 3, box[3] + 10)
    assert [s.kind for s in w.history.done] == ["move"]
    w.undo_edit()
    assert w.said[-1] == "Move taken back." and w.state() == start


def test_alt_arrows_without_a_region_or_off_translator_mode(keys):
    w = keys
    w._chosen_region = None
    w._nudge_key(SimpleNamespace(state=0), "Left")
    assert w.said[-1] == "Select a region first (click it)." and not w.timers
    w.role_var.set("reader")
    w._nudge_key(SimpleNamespace(state=0, keysym="Left"), "Left")
    assert w.forwarded == ["Left"]  # the arrow goes to the viewer as it did
    w._nudge_key(SimpleNamespace(state=0, keysym="h"), "Left")  # a nudge the reader put on Alt+H: not an arrow
    assert w.forwarded == ["Left"]


def test_a_nudge_back_where_it_began_stores_nothing(keys):
    w = keys
    w._choose(w.region("Hello there!"))
    w._nudge_key(SimpleNamespace(state=0), "Left")
    w._nudge_key(SimpleNamespace(state=0), "Right")
    w.fire()
    assert not w.history.done and w._grip_box is None


# ------------------------------------------------------------------ the words
def test_the_strips_hint_names_redo_tab_and_the_nudge():
    hint = translator.hint_text(shortcuts.Keymap())
    assert "Ctrl+Y: redo" in hint and "Tab: next region" in hint and "Alt+arrow keys: move by 1 px" in hint
    assert "Del: drop" in hint and "T: text direction" in hint and "{" not in hint
    keymap = shortcuts.Keymap().with_key("remove_box", None).with_key("redo", "Control-Shift-z")
    hint = translator.hint_text(keymap.with_key("nudge_left", "Alt-h"))  # the reader's keys; a part with none goes
    assert "Ctrl+Shift+Z: redo" in hint and ": drop" not in hint and "Alt+H/Alt+→/Alt+↑/Alt+↓: move by 1 px" in hint
    set_language("ja")
    try:
        assert "{" not in translator.hint_text(keymap) and "Ctrl+Shift+Z" in translator.hint_text(keymap)
    finally:
        set_language("en")


def test_every_line_of_the_keys_is_in_every_language():
    keys = [translator.HINT, translator.NUDGE_WORDS, translator.REGION_OF, "Keys...",
            "Every key TASlation knows, in one list.", "Tools > Settings... > Shortcuts changes these keys.",
            *(a.label for a in shortcuts.ACTIONS), *(text for row in shortcuts.FIXED_GESTURES for text in row)]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
            parts = catalog[translator.HINT]  # the hint's placeholders kept, so each part can go with its key
            assert sorted(re.findall(r"{(\w+)}", parts)) == sorted(re.findall(r"{(\w+)}", translator.HINT)), code
    assert _("Keys") == "Keys"
