"""The window's keys in one table (`ui.shortcuts`): the table's keys bound as they always were, a key made from a key
press and named as the keyboard does, what a key may not be, the reader's keys kept in the state folder, the bindings
moved when a key changes, translator mode's tools only in that role, the menus, the toolbar and Help's Keys naming
the keys in force, and the Shortcuts page of Tools > Settings...."""

from __future__ import annotations

import json
import tkinter as tk
from types import SimpleNamespace

import pytest

from taslation.config import Settings
from taslation.i18n import FEATURE_LANGUAGES, set_language
from taslation.locales.features import settings_dialog as texts
from taslation.ui import app as app_mod
from taslation.ui import shortcuts
from taslation.ui.dialogs import help as help_mod
from taslation.ui.dialogs import settings as dlg
from taslation.ui.shortcuts import ACTIONS, BY_NAME, Keymap, key_of_event, key_text, normal, sequences

ALT = shortcuts.ALT_MASK


@pytest.fixture(autouse=True)
def table_keys_in_force():
    shortcuts.set_current(Keymap())
    yield
    shortcuts.set_current(Keymap())


# ------------------------------------------------------------------ the table
def test_every_action_and_fixed_key_is_named_in_every_language():
    from taslation import i18n
    from taslation.locales.keys import KEYS

    assert len({a.name for a in ACTIONS}) == len(ACTIONS) and all(a.scope in shortcuts.SCOPES for a in ACTIONS)
    for english in [a.label for a in ACTIONS] + [shortcuts.FIXED_ESCAPE, shortcuts.FIXED_PAGE_KEYS]:
        homes = [found for found in i18n.FEATURES.values() if english in found]
        assert english in KEYS or (homes and sorted(homes[0][english]) == sorted(FEATURE_LANGUAGES)), english
    assert all(sorted(texts.TEXTS[english]) == sorted(FEATURE_LANGUAGES)
               for english in (shortcuts.FIXED_ESCAPE, shortcuts.FIXED_PAGE_KEYS))


def test_the_table_s_keys_are_bound_as_they_always_were():
    keymap = Keymap()
    bound = {a.name: [s for key in keymap.of(a.name) for s in sequences(key)] for a in ACTIONS if keymap.of(a.name)}
    assert bound == {"translate_now": ["<F5>"], "reading_mode": ["<F11>"],
                     "undo": ["<Control-Key-z>", "<Control-Lock-Key-Z>"], "redo": ["<Control-Key-y>", "<Control-Lock-Key-Y>"],
                     "how_to_use": ["<F1>"], "keys_help": ["<Shift-F1>"],
                     "edit_box": ["<Return>", "<KP_Enter>"], "remove_box": ["<Delete>"],
                     "text_direction": ["<Key-t>", "<Key-T>"],
                     # translator mode's keys of the region editing branch, in the table since its merge
                     "next_region": ["<Tab>"], "previous_region": ["<Shift-Tab>"], "nudge_left": ["<Alt-Left>"],
                     "nudge_right": ["<Alt-Right>"], "nudge_up": ["<Alt-Up>"], "nudge_down": ["<Alt-Down>"],
                     "copy_format": ["<Control-Key-C>", "<Control-Shift-Key-c>"],
                     "paste_format": ["<Control-Key-V>", "<Control-Shift-Key-v>"],
                     "copy_region": ["<Control-Key-c>", "<Control-Lock-Key-C>"],
                     "paste_region": ["<Control-Key-v>", "<Control-Lock-Key-V>"],
                     "editor_previous": ["<Alt-Up>"], "editor_next": ["<Alt-Down>"]}
    assert all(keymap.problem(a.name, key) is None for a in ACTIONS for key in a.keys)


def test_the_table_s_own_tab_arrows_and_ctrl_c_pass_for_their_action_alone():
    keymap = Keymap()
    assert "a key of Windows" in keymap.problem("review", "Tab")  # Tab moves the focus: never another action's
    assert "a key of Windows" in keymap.with_key("next_region", None).problem("previous_region", "Tab")
    assert keymap.with_key("next_region", None).problem("next_region", "Tab") is None  # put back as it was
    assert "turns the viewer's pages" in keymap.problem("nudge_left", "Control-Left")
    assert keymap.problem("nudge_left", "Alt-h") is None and keymap.problem("nudge_left", "h") is None  # the page's
    assert "editing the text" in keymap.problem("settings", "Control-c")  # in the window Ctrl+C stays the boxes'
    assert "already the key of Copy region" in keymap.problem("review", "Control-c")


def test_a_key_works_where_its_action_does_so_the_page_and_the_editor_may_share_one():
    keymap = Keymap()
    assert keymap.of("nudge_down") == keymap.of("editor_next") == ("Alt-Down",)  # the page, the editor: apart
    assert keymap.owner("Alt-Down", near="editor_next") == "editor_next"
    assert keymap.owner("Alt-Down", near="nudge_down") == "nudge_down"
    assert "already the key of Paste format" in keymap.problem("editor_next", "Control-Shift-v")  # also the editor's
    assert "already the key of Region editor" in keymap.with_key("editor_next", "Alt-n").problem("copy_format", "Alt-n")
    assert keymap.problem("editor_next", "Alt-n") is None and keymap.problem("editor_next", "F8") is None
    assert "works in the region editor needs Ctrl or Alt" in keymap.problem("editor_next", "Down")  # its text box
    assert "works in the region editor needs Ctrl or Alt" in keymap.problem("copy_format", "c")  # the editor's too
    assert "editing the text" in keymap.problem("editor_next", "Control-v")
    assert keymap.problem("translate_now", "F1") is not None and keymap.problem("editor_next", "F1") is None


def test_a_key_press_makes_a_key_and_a_modifier_alone_none():
    press = lambda keysym, state=0: key_of_event(SimpleNamespace(keysym=keysym, state=state))  # noqa: E731
    assert press("F6") == "F6" and press("F6", 1) == "Shift-F6" and press("z", 4) == "Control-z"
    assert press("Z", 5) == "Control-Shift-z" and press("T", 1) == "t" and press("r", ALT | 4) == "Control-Alt-r"
    assert press("KP_Enter") == "Return" and press("Control_L", 4) is None and press("Shift_R", 1) is None
    assert press("1") == "1" and sequences("1") == ["<Key-1>"]
    # Caps Lock turns the letter: Ctrl+Z and Ctrl+Shift+Z are told apart with it on too
    assert sequences("Control-z") == ["<Control-Key-z>", "<Control-Lock-Key-Z>"]
    assert sequences("Control-Shift-z") == ["<Control-Key-Z>", "<Control-Shift-Key-z>"]
    assert normal("Shift-Control-Z") == "Control-Shift-z" and sequences("Alt-F2") == ["<Alt-F2>"]


def test_a_key_is_named_as_the_keyboard_names_it_in_the_window_s_language():
    assert [key_text(k) for k in ("Control-Shift-z", "Return", "t", "Delete", "Prior", "Left", "Alt-F4")] == [
        "Ctrl+Shift+Z", "Enter", "T", "Del", "Page Up", "←", "Alt+F4"]
    set_language("de")
    try:
        assert key_text("Control-z") == "Strg+Z" and key_text("Delete") == "Entf"
    finally:
        set_language("en")


@pytest.mark.parametrize("name, key, why", [
    ("review", "Left", "turns the viewer's pages"), ("settings", "Control-Next", "turns the viewer's pages"),
    ("review", "Escape", "Esc is fixed"), ("review", "Tab", "a key of Windows"), ("settings", "F10", "a key of Windows"),
    ("settings", "Alt-F4", "a key of Windows"), ("settings", "s", "needs Ctrl or Alt"),
    ("settings", "Control-c", "editing the text"), ("review", "t", "already the key of Text direction"),
    ("settings", "F5", "already the key of Translate the page on show")])
def test_what_a_key_may_not_be(name, key, why):
    assert why in Keymap().problem(name, key)


def test_a_page_key_may_be_plain_and_a_window_key_an_f_key_or_with_ctrl_or_alt():
    keymap = Keymap()
    assert keymap.problem("review", "r") is None and keymap.problem("review", "Control-r") is None
    assert keymap.problem("settings", "F2") is None and keymap.problem("settings", "Alt-s") is None
    assert keymap.problem("settings", "Control-comma") is None


# ------------------------------------------------------------------ the keymap and its file
def test_the_keymap_keeps_what_differs_from_the_table_and_its_file_holds_that_alone(tmp_path):
    keymap = Keymap().with_key("translate_now", "F6").with_key("review", "r").with_key("redo", None)
    assert keymap.of("translate_now") == ("F6",) and keymap.of("redo") == () and keymap.customised
    assert keymap.shown("translate_now") == "F6" and keymap.shown("redo") == "" and keymap.owner("r") == "review"
    assert keymap.with_default("translate_now").of("translate_now") == ("F5",)
    assert Keymap().with_key("translate_now", "F5") == Keymap() and not Keymap.reset().customised
    path = keymap.save(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "keys": {"redo": [], "review": ["r"], "translate_now": ["F6"]}}
    assert Keymap.load(tmp_path) == keymap


def test_a_damaged_file_or_a_key_that_cannot_be_is_left_out(tmp_path):
    assert Keymap.load(tmp_path) == Keymap()  # no file
    (tmp_path / shortcuts.SHORTCUTS_FILE).write_text("{not json", encoding="utf-8")
    assert Keymap.load(tmp_path) == Keymap()
    (tmp_path / shortcuts.SHORTCUTS_FILE).write_text(json.dumps({"keys": {
        "settings": ["F5"], "translate_now": ["F6"], "review": ["Left"], "gone": ["F7"], "undo": "x"}}), encoding="utf-8")
    keymap = Keymap.load(tmp_path)  # F5 moved: the keys let go first
    assert keymap.of("settings") == ("F5",) and keymap.of("translate_now") == ("F6",)
    assert keymap.of("review") == () and keymap.of("undo") == ("Control-z",)


# ------------------------------------------------------------------ the bindings
def test_the_bindings_move_with_the_keys_and_what_the_parts_bound_is_let_go(hidden_root):
    window, page = tk.Frame(hidden_root), tk.Canvas(hidden_root)
    window.bind("<Control-y>", lambda e: "the part's own")  # as the translator strip binds Ctrl+Y
    calls = []
    handlers = {a.name: (lambda e, n=a.name: calls.append(n)) for a in ACTIONS}
    bound = shortcuts.bind_keys({"window": window, "page": page}, Keymap(), handlers)
    assert set(window.bind()) == {"<Key-F5>", "<Key-F11>", "<Key-F1>", "<Shift-Key-F1>", "<Control-Key-z>",
                                  "<Control-Lock-Key-Z>", "<Control-Key-y>", "<Control-Lock-Key-Y>"}
    assert set(page.bind()) == {"<Key-Return>", "<Key-KP_Enter>", "<Key-Delete>", "t", "T",  # (as Tk lists them)
                                "<Key-Tab>", "<Shift-Key-Tab>", "<Alt-Key-Left>", "<Alt-Key-Right>", "<Alt-Key-Up>",
                                "<Alt-Key-Down>", "<Control-Key-C>", "<Control-Shift-Key-c>", "<Control-Key-V>",
                                "<Control-Shift-Key-v>", "<Control-Key-c>", "<Control-Lock-Key-C>", "<Control-Key-v>",
                                "<Control-Lock-Key-V>"}
    keymap = Keymap().with_key("redo", "Control-Shift-z").with_key("text_direction", "d").with_key("review", "r")
    bound = shortcuts.bind_keys({"window": window, "page": page}, keymap, handlers, bound)
    assert "<Control-Key-y>" not in window.bind() and "<Control-Key-Z>" in window.bind()
    assert {"d", "D", "r", "R"} <= set(page.bind()) and "t" not in page.bind()
    shortcuts.bind_keys({"window": window, "page": page}, Keymap(), handlers, bound)
    assert "r" not in page.bind() and "t" in page.bind() and "<Control-Key-y>" in window.bind()


def _fake_window(hidden_root, role="reader"):
    done = []
    record = lambda name: (lambda *a, **k: done.append(name))  # noqa: E731
    w = SimpleNamespace(role_var=tk.StringVar(hidden_root, value=role),
                        original_var=tk.BooleanVar(hidden_root, value=False),
                        top_var=tk.BooleanVar(hidden_root, value=False), over_var=tk.BooleanVar(hidden_root, value=True),
                        order_numbers_var=tk.BooleanVar(hidden_root, value=False),
                        _edit_key=lambda e, step: step(), _nudge_key=lambda e, d: done.append(f"nudge {d}"),
                        _tab_region=lambda step: done.append(f"tab {step}"))
    for name in ("translate_now", "toggle_reading", "undo_edit", "redo_edit", "_redisplay", "_apply_on_top", "toggle_over",
                 "open_batch_dialog", "set_area", "open_page_keys", "open_caches", "review_names", "open_settings", "open_help",
                 "open_keys", "toggle_order_numbers", "_edit_chosen", "_drop_chosen", "_turn_direction", "toggle_order",
                 "toggle_skip", "retranslate_page", "open_book_settings", "open_glossary", "open_review", "open_find_replace",
                 "copy_format", "paste_format", "copy_region", "paste_region", "ignore_area_everywhere",
                 "paste_format_on_kind", "set_kind_of_selection", "set_size_of_selection", "place_in_order"):
        setattr(w, name, record(name))
    return w, done


def test_every_action_has_its_step_and_translator_mode_s_tools_wait_for_that_role(hidden_root):
    w, done = _fake_window(hidden_root)
    handlers = app_mod.App._shortcut_handlers(w)
    assert set(handlers) == {a.name for a in ACTIONS if a.scope != "editor"}  # the editor's: `ReviewDialog`
    for name in ("review", "find_replace", "skip_page", "next_region", "copy_region", "paste_format", "set_kind"):
        handlers[name](None)
    assert done == []  # the Reader role: their buttons are not there (and Tab goes on to move the focus)
    handlers["nudge_left"](None)  # Alt+arrows: `_nudge_key` sends them on to the viewer outside translator mode
    handlers["keys_help"](None)
    handlers["order_numbers"](None)
    assert done == ["nudge Left", "open_keys", "toggle_order_numbers"] and w.order_numbers_var.get() is True
    done.clear()
    w.role_var.set("translator")
    handlers["review"](None)
    handlers["translate_now"](None)
    handlers["show_original"](None)
    handlers["over_viewer"](None)
    handlers["previous_region"](None)
    handlers["copy_format"](None)
    handlers["ignore_area"](None)
    assert done == ["open_review", "translate_now", "_redisplay", "toggle_over", "tab -1", "copy_format",
                    "ignore_area_everywhere"]
    assert w.original_var.get() is True and w.over_var.get() is False  # flipped as the View menu's tick does


def test_the_menus_and_the_toolbar_name_the_keys_in_force(hidden_root):
    menu = tk.Menu(hidden_root, tearoff=0)
    menu.add_command(label="Settings...")
    menu.add_checkbutton(label="Show original")
    w = SimpleNamespace(keymap=Keymap(), _menu_keys=[(menu, 0, "settings"), (menu, 1, "show_original")],
                        translate_btn=tk.Button(hidden_root), reading_btn=tk.Button(hidden_root))
    app_mod.App._show_keys(w)
    assert menu.entrycget(0, "accelerator") == "" and w.translate_btn.cget("text") == "Translate (F5)"
    assert w.reading_btn.cget("text") == "Reading mode (F11)"
    w.keymap = Keymap().with_key("settings", "Control-comma").with_key("translate_now", "F6").with_key("reading_mode", None)
    app_mod.App._show_keys(w)
    assert menu.entrycget(0, "accelerator") == "Ctrl+," and w.translate_btn.cget("text") == "Translate (F6)"
    assert w.reading_btn.cget("text") == "Reading mode"


def test_saved_keys_are_bound_at_once_and_help_says_them(hidden_root):
    rendered, bound = [], []
    w = SimpleNamespace(keymap=Keymap(), _bind_shortcuts=lambda: bound.append(True),
                        _help=SimpleNamespace(winfo_exists=lambda: True, wrapped_at=400,
                                              render=lambda width, again=False: rendered.append((width, again))))
    keymap = Keymap().with_key("translate_now", "F6")
    app_mod.App._shortcuts_saved(w, keymap)
    assert w.keymap is keymap and shortcuts.current() is keymap and bound == [True] and rendered == [(400, True)]


def test_help_s_keys_follow_the_keymap_in_force():
    topic = dict(help_mod.TOPICS)["Keys"]
    lines = help_mod.topic_lines("Keys", topic)  # the table's keys, Esc and the mouse's ways (the one Keys list)
    assert lines == [*shortcuts.help_lines(Keymap()), "Tools > Settings... > Shortcuts changes these keys."]
    assert "F5: Translate the page on show" in lines and "Tab: Select the next region" in lines
    assert "Ctrl+Shift+C: Copy format" in lines and "Several selected: " + shortcuts.FIXED_GESTURES[-1][0] in lines
    shortcuts.set_current(Keymap().with_key("translate_now", "F6").with_key("review", "r").with_key("next_region", None))
    lines = help_mod.topic_lines("Keys", topic)
    assert "F6: Translate the page on show" in lines and "R: Review..." in lines
    assert not any(line.startswith(("F5", "Tab")) for line in lines)
    assert "Esc: Leave reading mode, or let go of the chosen box" in lines
    assert help_mod.topic_lines("Page keys", ("Page > Page keys... sets the keys that turn pages in your viewer. A right-to-left book often turns with the left arrow.",))[0].startswith("Page >")


def test_the_menus_name_the_entries_they_hold_whatever_else_a_menu_has(hidden_root, monkeypatch):
    from taslation.ui import app as app_mod

    monkeypatch.setattr(app_mod, "tip_menu", lambda *a, **k: None)
    w = tk.Toplevel(hidden_root)
    w.withdraw()
    for name in ("set_area", "open_page_keys", "open_caches", "review_names", "open_settings", "_redisplay", "_apply_on_top",
                 "toggle_over", "_on_ui_language", "open_help", "open_keys", "open_notice", "open_about"):
        setattr(w, name, lambda *a: None)
    w.original_var, w.top_var, w.over_var, w.order_numbers_var = (tk.BooleanVar(w) for _ in range(4))
    w.ui_lang_var = tk.StringVar(w)
    shortcuts.set_current(Keymap().with_key("copy_region", "Alt-c"))
    app_mod.App._build_menus(w)
    labels = {"set_area": "Set area...", "page_keys": "Page keys...", "saved_translations": "Saved translations...",
              "settings": "Settings...", "show_original": "Show original", "always_on_top": "Always on top",
              "over_viewer": "Over the full-screen viewer", "how_to_use": "How to use...", "keys_help": "Keys...",
              "ignore_area": "Ignore this area on all pages of this book", "copy_format": "Copy format",
              "paste_format": "Paste format", "paste_format_on_kind": "Paste format on every region of this kind...",
              "copy_region": "Copy region", "paste_region": "Paste region", "set_kind": "Set kind...",
              "set_text_size": "Set text size...", "place_in_order": "Place in reading order...",
              "order_numbers": "Reading-order numbers"}
    assert sorted(name for _m, _i, name in w._menu_keys) == sorted(labels)
    for menu, index, name in w._menu_keys:  # the keys in force from the start, before `_show_keys`
        assert menu.entrycget(index, "label") == labels[name]
        assert menu.entrycget(index, "accelerator") == shortcuts.current().shown(name)
    accelerators = {name: menu.entrycget(index, "accelerator") for menu, index, name in w._menu_keys}
    assert accelerators["copy_region"] == "Alt+C" and accelerators["copy_format"] == "Ctrl+Shift+C"
    assert accelerators["how_to_use"] == "F1" and accelerators["keys_help"] == "Shift+F1" and accelerators["set_kind"] == ""

# ------------------------------------------------------------------ the Shortcuts page
@pytest.fixture
def dialog(hidden_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    got = []
    d = dlg.SettingsDialog(hidden_root, settings, on_saved=got.append, keymap=Keymap(), on_keys=got.append)
    return d, got, settings


def _press(page, keysym, state=0):
    return page._take(SimpleNamespace(keysym=keysym, state=state))


def test_the_page_lists_every_action_and_the_fixed_keys_in_grey(dialog):
    d, _got, _s = dialog
    page = d.keys
    assert [d.pages.tab(i, "text") for i in range(d.pages.index("end"))][:2] == ["General", "Shortcuts"]
    assert list(page.tree.get_children())[:len(ACTIONS)] == [a.name for a in ACTIONS]
    assert page.tree.set("translate_now", "key") == "F5" and page.tree.set("review", "key") == ""
    fixed = [iid for iid in page.tree.get_children() if "fixed" in page.tree.item(iid, "tags")]
    keys = [page.tree.set(iid, "key") for iid in fixed]  # Esc, the page keys, then the mouse's ways
    assert keys[0] == "Esc" and len(fixed) == 2 + len(shortcuts.FIXED_GESTURES) and keys[2:] == [
        shortcuts._(how) for _what, how in shortcuts.FIXED_GESTURES]


def test_a_key_is_changed_checked_and_saved_with_the_dialog(dialog):
    d, got, settings = dialog
    page = d.keys
    page.change()
    assert d.message_var.get() == "Choose an action in the list first." and page.capturing is None
    page.tree.selection_set("review")
    page.change()
    assert page.capturing == "review" and "Review..." in page.capture_var.get()
    assert _press(page, "Control_L", 4) == "break" and page.capturing == "review"  # a modifier alone: waits on
    _press(page, "t")
    assert "already the key of Text direction" in d.message_var.get() and page.capturing == "review"
    _press(page, "r")
    assert page.capturing is None and page.tree.set("review", "key") == "R" and page.changed
    assert d.save() is True and got == [page.keymap] and d.message_var.get() == "Saved. The changes apply now."
    assert Keymap.load(settings.state_dir).of("review") == ("r",) and not page.changed
    assert d.save() is True and d.message_var.get() == "Nothing changed."


def test_esc_cancels_and_no_key_default_and_reset_all(dialog):
    d, got, _s = dialog
    page = d.keys
    page.tree.selection_set("translate_now")
    page.change()
    _press(page, "F11")  # refused: said in the message line, the wait goes on
    assert "Reading mode" in d.message_var.get() and page.capturing == "translate_now"
    _press(page, "Escape")
    assert page.capturing is None and page.keymap == Keymap() and d.winfo_exists()
    assert d.message_var.get() == ""  # the refusal goes with the wait
    page.clear()
    assert page.tree.set("translate_now", "key") == ""
    page.tree.selection_set("settings")
    page.change()
    _press(page, "F5")
    assert page.keymap.of("settings") == ("F5",)
    page.tree.selection_set("translate_now")
    page.default()  # F5 is the settings' now
    assert "already the key of Settings..." in d.message_var.get() and page.keymap.of("translate_now") == ()
    page.reset()
    assert page.keymap == Keymap() and page.tree.set("settings", "key") == "" and not page.changed


def test_the_dialog_in_japanese_names_the_keys_page(hidden_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    set_language("ja")
    d = dlg.SettingsDialog(hidden_root, Settings(state_dir=tmp_path, config_path=tmp_path / "t.toml"))
    assert d.pages.tab(1, "text") == "ショートカット" and d.keys.tree.item("undo", "text") == "元に戻す"
