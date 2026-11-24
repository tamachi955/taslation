"""Add area in the one mode (`ui.see_edit`'s adding, `capture.seethrough.SeeThrough`'s Insert key): the key held as
the lettering's window's hot key only while it is wanted and the viewer is in front (`_key_tick`, `viewer_in_front`),
let go otherwise, a registration that fails counted and logged once; a press of it handed to the Tk thread
(``WM_HOTKEY``, `take_keys`), which starts or gives up adding; a right click while adding gives it up; adding with
Edit off (marks of no box, the rectangle stored and read); the left pane's Add area row; the two Settings rows (Insert
adds a text area, Start with Edit on). A fake user32 only: no key is taken from this machine and nothing is sent to
another program."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import panes as pn
from taslation import seethrough as st
from taslation.config import Settings
from taslation.i18n import CATALOGS, FEATURE_LANGUAGES
from taslation.capture import seethrough as window
from taslation.locales.features import see_edit as edit_texts
from taslation.locales.features import settings_dialog as settings_texts
from taslation.ui import see_edit
from taslation.ui import seethrough as ui
from taslation.ui.dialogs import settings as dlg

VIEWER = 77
SIZE = (900, 800)


# ------------------------------------------------------------------ the key (the see-through window's side)
@pytest.fixture
def keyed(monkeypatch):
    """A see-through window with a fake user32 that records the hot key's registrations; *front* says whether the
    viewer is in front, *takes* whether a registration succeeds."""
    calls = []
    state = SimpleNamespace(front=True, takes=True, calls=calls)

    def register(hwnd, ident, mods, vk):
        calls.append(("register", hwnd, ident, mods, vk))
        return 1 if state.takes else 0

    monkeypatch.setattr(window, "IS_WINDOWS", True)
    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        RegisterHotKey=register,
        UnregisterHotKey=lambda hwnd, ident: calls.append(("unregister", hwnd, ident)) or 1,
        PostMessageW=lambda hwnd, message, w, l: 1,
        GetCapture=lambda: 0,
        ReleaseCapture=lambda: 1))
    monkeypatch.setattr(window, "viewer_in_front", lambda viewer: state.front and viewer == VIEWER)
    monkeypatch.setattr(window.ctypes, "get_last_error", lambda: 1409)  # (ERROR_HOTKEY_ALREADY_REGISTERED)
    see = window.SeeThrough()
    see.hwnd = 9
    state.see = see
    return state


def test_the_key_is_held_only_while_wanted_and_the_viewer_in_front_and_let_go_otherwise(keyed):
    see = keyed.see
    see._key_tick(VIEWER)
    assert keyed.calls == [] and not see.key_held()  # (not wanted yet: Settings' row off, or the window shown)
    see.set_add_key(True)
    see._key_tick(VIEWER)
    assert keyed.calls == [("register", 9, window.HOTKEY_ID, window.MOD_NOREPEAT, window.VK_INSERT)]
    assert see.key_held() and see.counts["key_registered"] == 1
    see._key_tick(VIEWER)
    assert len(keyed.calls) == 1  # (held: not registered again at every look)
    keyed.front = False  # (another program or a dialog of ours in front, or the viewer minimised)
    see._key_tick(VIEWER)
    assert keyed.calls[-1] == ("unregister", 9, window.HOTKEY_ID) and not see.key_held()
    assert see.counts["key_released"] == 1
    see._key_tick(VIEWER)
    assert len(keyed.calls) == 2  # (let go of once)
    keyed.front = True
    see._key_tick(VIEWER)
    assert see.key_held() and see.counts["key_registered"] == 2
    see._key_tick(0)  # (no viewer chosen, or it has gone)
    assert not see.key_held() and see.counts["key_released"] == 2
    see._key_tick(VIEWER)
    see.set_add_key(False)  # (Settings' row unticked: let go of at the next look)
    assert see.key_held()
    see._key_tick(VIEWER)
    assert not see.key_held() and see.counts["key_released"] == 3
    assert [n["on"] for n in see.notes if n["ev"] == "key_held"] == [1, 0, 1, 0, 1, 0]


def test_a_registration_that_fails_is_counted_logged_once_and_tried_again_only_after_a_let_go(keyed, caplog):
    see = keyed.see
    keyed.takes = False  # (another program holds Insert)
    see.set_add_key(True)
    with caplog.at_level(logging.INFO, logger=window.__name__):
        see._key_tick(VIEWER)
        see._key_tick(VIEWER)
        assert not see.key_held() and see.counts["key_failed"] == 1 and len(keyed.calls) == 1  # (not at every look)
        keyed.front = False
        see._key_tick(VIEWER)
        assert ("unregister", 9, window.HOTKEY_ID) not in keyed.calls  # (none held: none let go of)
        keyed.front = True
        see._key_tick(VIEWER)
        assert see.counts["key_failed"] == 2 and len(keyed.calls) == 2
    lines = [r for r in caplog.records if "Insert key could not be taken" in r.getMessage()]
    assert len(lines) == 1 and "1409" in lines[0].getMessage()
    assert [n["error"] for n in see.notes if n["ev"] == "key_failed"] == [1409, 1409]
    keyed.takes = True
    keyed.front = False
    see._key_tick(VIEWER)
    keyed.front = True
    see._key_tick(VIEWER)
    assert see.key_held()  # (free again: taken)


def test_a_press_of_the_key_is_handed_to_the_tk_thread_and_another_hot_key_is_not(keyed):
    see = keyed.see
    window._key_hooks[see.hwnd] = see._hot_key
    try:
        assert window._proc(see.hwnd, window.WM_HOTKEY, window.HOTKEY_ID, 0) == 0
        assert window._proc(see.hwnd, window.WM_HOTKEY, 12, 0) == 0  # (another id: nothing)
        assert window._proc(1234, window.WM_HOTKEY, window.HOTKEY_ID, 0) == 0  # (another window: nothing)
    finally:
        window._key_hooks.pop(see.hwnd, None)
    taken = see.take_keys()
    assert len(taken) == 1 and see.counts["keys"] == 1 and see.take_keys() == []


def test_the_key_or_a_right_click_while_a_rectangle_is_drawn_gives_the_adding_up(keyed):
    see = keyed.see
    marks = st.Marks(key=5, boxes=(), adding=True, serial=1)
    see._marks_live = marks
    see._last_look = (None, (), [], 1, 0.0, (0, 0), SIZE, True)
    see._edit_redraw = lambda: None
    see._edit_takes = True  # (marks handed: the window takes the mouse)
    see._press = {"adding": True, "start": (10, 10), "now": (40, 40), "moved": True, "marks": marks}
    see._hot_key(window.HOTKEY_ID)
    assert see._press is None and see.take_edits() == [] and len(see.take_keys()) == 1  # (the Tk side gives it up)
    see._press = {"adding": True, "start": (10, 10), "now": (40, 40), "moved": True, "marks": marks}
    see._edit_message(window.WM_RBUTTONDOWN, 0, 0)
    (event,) = see.take_edits()
    assert see._press is None and event["kind"] == "add" and event["box"] is None and event["marks"] == 1
    see._marks_live = st.Marks(key=5, boxes=((1, 1, 30, 30),), serial=2)  # (Edit, nothing to add: a right click
    see._edit_message(window.WM_RBUTTONDOWN, 0, 0)  # only gives up a drag)
    assert see.take_edits() == []


def test_viewer_in_front_is_the_viewer_or_a_window_of_its_own_and_not_minimised(monkeypatch):
    from taslation.capture import windows

    monkeypatch.undo()  # (the suite's stand-in for it gone, `conftest.no_real_hot_key`: the real one, on fakes)
    real = window.viewer_in_front
    monkeypatch.setattr(window, "IS_WINDOWS", True)
    shown = SimpleNamespace(front=500, iconic=False, alive=True)
    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        IsWindow=lambda hwnd: shown.alive, IsIconic=lambda hwnd: shown.iconic,
        GetForegroundWindow=lambda: shown.front))
    owners = {500: "viewer", 600: "own", 700: "other"}
    monkeypatch.setattr(windows, "foreground_owner", lambda front, viewer: owners[front])
    assert real(VIEWER) is True
    for front in (600, 700, 0):
        shown.front = front
        assert real(VIEWER) is False, front
    shown.front, shown.iconic = 500, True
    assert real(VIEWER) is False
    shown.iconic, shown.alive = False, False
    assert real(VIEWER) is False
    assert real(0) is False


def test_the_tick_wants_the_key_only_with_the_window_hidden_and_the_setting_on(tmp_path, monkeypatch):
    wanted = []
    over = SimpleNamespace(follow=lambda hwnd: None, set_hover_delay=lambda ms: None, set_add_key=wanted.append)
    for name in ("present", "panes_tick", "keep_hidden", "front_tick"):
        monkeypatch.setattr(ui, name, lambda app: None)
    monkeypatch.setattr(see_edit, "tick", lambda app, over: None)
    from taslation.ui import see_menu

    monkeypatch.setattr(see_menu, "chooser_tick", lambda app: None)
    monkeypatch.setattr(window, "viewer_dpi", lambda hwnd: 96)
    settings = Settings(state_dir=tmp_path / "state", config_path=tmp_path / "taslation.toml")
    app = SimpleNamespace(_see_through=over, selected=None, settings=settings, _see_hidden=False)
    ui.tick(app)
    app._see_hidden = True
    ui.tick(app)
    settings.add_area_key = False
    ui.tick(app)
    assert wanted == [False, True, False]


# ------------------------------------------------------------------ the Tk side
class Over:
    def __init__(self, on=True):
        self.on, self.edits, self.marks, self.keys = on, [], [], []

    def take_edits(self):
        out, self.edits = self.edits, []
        return out

    def take_keys(self):
        out, self.keys = self.keys, []
        return out

    def set_edit(self, marks):
        self.marks.append(marks)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def add_app(role="reader", tmp_path=None):
    result = SimpleNamespace(original=Image.new("RGB", SIZE), regions=[], image=None)
    calls, said = [], []
    app = SimpleNamespace(_see_hidden=True, _see_through=Over(), role_var=Var(role), last_result=result, busy=False,
                          _ordering=None, _chosen_region=None, _also_chosen=[], _see_dpi=96, calls=calls, said=said,
                          pipeline=SimpleNamespace(annotations=object()), settings=SimpleNamespace(add_area_key=True))
    app._editing = lambda: role == "translator"
    app._result_on_show = lambda: True
    app._page_regions = lambda: list(result.regions)
    app.say = lambda text, **k: said.append(text)
    app._add_region = lambda box: (calls.append(("add", box)), setattr(app, "busy", True))
    return app


def test_the_key_starts_adding_with_edit_off_and_a_rectangle_is_stored_and_read():
    app = add_app()
    over = app._see_through
    see_edit.tick(app, over)
    assert over.marks[-1] is None  # (Edit off, nothing to add: no marks, every click the viewer's)
    over.keys.append(1.0)  # (Insert pressed with the viewer in front)
    see_edit.tick(app, over)
    marks = over.marks[-1]
    assert see_edit.adding(app) and app.said == [see_edit.ADDING]
    assert marks is not None and marks.adding and marks.boxes == () and marks.key == id(app.last_result.original)
    over.edits.append({"press": 1, "marks": marks.serial, "key": marks.key, "kind": "add", "box": (10, 20, 90, 70)})
    see_edit.tick(app, over)
    assert app.calls == [("add", (10, 20, 90, 70))] and not see_edit.adding(app)
    app.busy = False
    see_edit.tick(app, over)
    assert over.marks[-1] is None  # (stored: back to reading, the page the viewer's again)


def test_the_key_again_a_right_click_or_another_page_gives_the_adding_up():
    app = add_app()
    over = app._see_through
    see_edit.toggle_adding(app)
    over.keys.append(1.0)
    see_edit.tick(app, over)
    assert not see_edit.adding(app) and app.said[-1] == see_edit.ADD_GIVEN_UP and over.marks[-1] is None
    see_edit.toggle_adding(app)
    marks = over.marks[-1]
    over.edits.append({"press": 1, "marks": marks.serial, "key": marks.key, "kind": "add", "box": None})
    see_edit.tick(app, over)  # (a right click, or a click without a drag)
    assert not see_edit.adding(app) and app.said[-1] == see_edit.ADD_GIVEN_UP and app.calls == []
    see_edit.toggle_adding(app)
    app._result_on_show = lambda: False  # (the viewer turned to a page not translated yet)
    see_edit.tick(app, over)
    assert not see_edit.adding(app) and over.marks[-1] is None


def test_with_edit_on_the_marks_keep_the_regions_while_adding():
    app = add_app(role="translator")
    app.last_result.regions = [SimpleNamespace(bbox=(100, 100, 200, 160), status="translated", kind="speech",
                                               flags=None, x0=100, y0=100)]
    see_edit.toggle_adding(app)
    marks = app._see_through.marks[-1]
    assert marks.adding and marks.boxes == ((100, 100, 200, 160),)


@pytest.mark.parametrize("change, said", [
    (lambda app: setattr(app, "_see_hidden", False), see_edit.ADD_NOT_NOW),
    (lambda app: setattr(app._see_through, "on", False), see_edit.ADD_NO_LETTERING),
    (lambda app: setattr(app, "busy", True), see_edit.ADD_NOT_NOW),
    (lambda app: setattr(app, "_result_on_show", lambda: False), see_edit.ADD_NOT_NOW),
    (lambda app: setattr(app, "last_result", None), see_edit.ADD_NOT_NOW),
    (lambda app: setattr(app.pipeline, "annotations", None), see_edit.ADD_NO_BOOK),
])
def test_where_no_area_can_be_added_the_status_says_why_and_nothing_begins(change, said):
    app = add_app()
    change(app)
    assert see_edit.start_adding(app) is False
    assert app.said == [said] and not see_edit.adding(app) and app._see_through.marks == []


def test_the_menu_entry_begins_adding_and_never_gives_it_up():
    app = add_app(role="translator")
    see_edit.add_region(app)
    see_edit.add_region(app)
    assert see_edit.adding(app) and app.said == [see_edit.ADDING]


# ------------------------------------------------------------------ the left pane's row
def test_the_left_pane_has_add_area_after_edit_while_hidden_and_it_shows_pressed_while_adding(tmp_path):
    from test_see_panes import fake_app

    app = fake_app(tmp_path, role_var=Var("reader"))
    assert "add_area" not in [r.name for r in ui.left_rows(app)]  # (the window shown: not the one mode)
    app._see_hidden = True
    names = [r.name for r in ui.left_rows(app)]
    assert names.index("add_area") == names.index("edit") + 1
    row = {r.name: r for r in ui.left_rows(app)}["add_area"]
    assert row.text == "Add area" and row.kind == "button" and row.on is False  # (the key named elsewhere only)
    app._see_adding = True
    assert {r.name: r for r in ui.left_rows(app)}["add_area"].on is True
    assert ui.PANE_ACTIONS["add_area"] is ui._add_area


@pytest.mark.parametrize("dpi", [96, 144])
def test_the_add_area_row_makes_the_left_pane_no_wider_in_any_language(tmp_path, dpi):
    from test_see_panes import fake_app

    from taslation.i18n import set_language

    try:
        for code in ("en", *FEATURE_LANGUAGES):
            set_language(code)
            rows = ui.left_rows(fake_app(tmp_path, role_var=Var("reader"), _see_hidden=True))
            assert "add_area" in [r.name for r in rows]
            without = [r for r in rows if r.name != "add_area"]
            assert pn.width_for(rows, code, dpi) == pn.width_for(without, code, dpi), code
    finally:
        set_language("en")


def test_a_pressed_button_is_drawn_on_the_accent_plate():
    rows = [pn.Row("add_area", "Add area"), pn.Row("add_area", "Add area", on=True)]
    picture = pn.render(rows, 160, "en", 96, pn.DARK)
    (_n, plain), (_m, pressed) = picture.hits
    colour = []
    for box in (plain, pressed):
        x, y = box[2] - 4, (box[1] + box[3]) // 2  # (the plate's right end: no words there)
        colour.append(tuple(int(v) for v in picture.bgra[y, x, :3][::-1]))  # (premultiplied RGB)
    alpha = pn.ALPHA / 255
    for got, wanted in zip(colour, (pn.DARK.plate, pn.DARK.accent)):
        assert all(abs(g - w * alpha) <= 2 for g, w in zip(got, wanted)), (got, wanted)


# ------------------------------------------------------------------ the words
def test_the_new_words_are_in_every_language_and_name_the_controls_as_the_window_does():
    new = (see_edit.ADD_AREA, see_edit.ADDING, see_edit.ADD_NOT_NOW, see_edit.ADD_NO_LETTERING)
    for english in new:
        assert sorted(edit_texts.TEXTS[english]) == sorted(FEATURE_LANGUAGES), english
    assert "Add area (Insert)" not in edit_texts.TEXTS  # (the row names no key: the pane keeps its width)
    for code in FEATURE_LANGUAGES:
        catalog = CATALOGS[code]
        area = catalog[see_edit.ADD_AREA]
        assert area.lower() in catalog[see_edit.ADDING].lower(), code
        assert catalog["Lettering"].lower() in catalog[see_edit.ADD_NO_LETTERING].lower(), code
    for english in ("Insert adds a text area", dlg.ADD_KEY_TIP, "Start with Edit on", dlg.START_EDIT_TIP):
        assert sorted(settings_texts.TEXTS[english]) == sorted(FEATURE_LANGUAGES), english
    for code in FEATURE_LANGUAGES:
        catalog = CATALOGS[code]
        assert catalog["Edit"].lower() in catalog["Start with Edit on"].lower(), code
        assert catalog[see_edit.ADD_AREA].lower() in catalog[dlg.ADD_KEY_TIP].lower(), code  # (the row as it reads)


# ------------------------------------------------------------------ Settings
@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def test_insert_adds_a_text_area_is_ticked_by_default_and_saved_off(hidden_root, in_force):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.extra["add_area_key"].get() is True and d.values()["add_area_key"] is True
    d.extra["add_area_key"].set(False)
    assert d.save() is True and got == [{"add_area_key": False}]
    assert Settings.from_toml(in_force.config_path).add_area_key is False


def test_start_with_edit_on_is_the_translator_role(hidden_root, in_force):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert in_force.role == "reader" and d.extra["role"].get() is False and d.values()["role"] == "reader"
    d.extra["role"].set(True)
    assert d.save() is True and got == [{"role": "translator"}]
    assert Settings.from_toml(in_force.config_path).role == "translator"
    in_force.role = "translator"
    d.destroy()
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.extra["role"].get() is True
    d.extra["role"].set(False)
    assert d.save() is True and got[-1] == {"role": "reader"}
    row = next(row for row in dlg.EXTRA_ROWS if row.key == "role")
    assert row.ticked("translator") and not row.ticked("reader") and row.value_of(True) == "translator"


def test_the_two_rows_leave_the_page_alone():
    rows = {row.key: row for row in dlg.SHOWN_ROWS}
    assert {"add_area_key", "role"} <= set(rows) and not rows["add_area_key"].page and not rows["role"].page
    assert not {"add_area_key", "role"} & dlg.PAGE_SETTINGS
