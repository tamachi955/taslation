"""The keys TASlation presses in the viewer: their names and the settings, the capture profiles that keep them per
viewer (with the defaults and the reader's presets beside), where a viewer's keys come from (profile > defaults >
settings), the command line (`taslation keys`), Page keys... (presets,
Test, validation, Apply) and the status line. What an older version kept of a first-page key is ignored. The window's
parts are borrowed onto stand-ins."""
from __future__ import annotations

import json
import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation import cli, i18n, netguard, pagekeys
from taslation.capture import WindowInfo
from taslation.config import ConfigError, Settings
from taslation.pagekeys import BUILTIN_PRESETS, DEFAULT_KEYS, KEY_PRESETS, PageKeys, Profiles, page_keys_for, valid_key
from taslation.ui import app as app_mod
from taslation.ui.dialogs.pagekeys import PRESET_LABELS, PageKeysDialog, check_keys
from taslation.ui.live import BlackViewerMixin
from test_follow import _page, setup  # noqa: F401 - setup is test_follow's fixture

A = app_mod.App
VIEWER = WindowInfo(hwnd=7, title="An Image Viewer", class_name="ImageViewer", pid=7, rect=(0, 0, 800, 600))
OTHER = WindowInfo(hwnd=8, title="Another Reader", class_name="Reader", pid=8, rect=(0, 0, 800, 600))


def _frame(x: int = 40) -> Image.Image:
    page = Image.new("RGB", (200, 150), "white")
    page.paste((20, 20, 20), (x, 30, x + 40, 70))
    return page


# ------------------------------------------------------------------ names, settings, profiles
def test_key_names_and_the_settings():
    assert all(valid_key(k) for k in ("Left", "right", "PageDown", "Home", "End", "Space", "Enter", "F11", "a", "7"))
    assert not valid_key("") and not valid_key("Hyper") and not valid_key("ä") and not valid_key("ab")
    s = Settings()
    assert (s.next_page_key, s.prev_page_key) == ("Left", "Right")
    s.validate()
    for bad, says in (({"prev_page_key": "left"}, "same key"), ({"next_page_key": "Hyper"}, "next_page_key"),
                      ({"next_page_key": ""}, "next_page_key")):
        with pytest.raises(ConfigError, match=says):
            Settings(**bad).validate()


def test_the_settings_file_takes_the_keys(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text('next_page_key = "Right"\nprev_page_key = "Left"\nfullscreen_key = ""\n', encoding="utf-8")
    s = Settings.load(path)
    s.validate()
    assert PageKeys.from_settings(s) == PageKeys("Right", "Left")  # (the full-screen key of old does nothing)


@pytest.mark.parametrize("value", ["Home", "", "Hyper"])
def test_a_settings_file_of_an_older_version_with_a_first_page_key_still_loads(tmp_path, value):
    path = tmp_path / "taslation.toml"
    path.write_text(f'next_page_key = "Right"\nprev_page_key = "Left"\nfirst_page_key = "{value}"\n', encoding="utf-8")
    s = Settings.load(path)
    s.validate()
    assert PageKeys.from_settings(s) == PageKeys("Right", "Left") and not hasattr(s, "first_page_key")


def test_what_an_older_version_kept_of_a_first_page_key_is_ignored_and_goes_with_the_next_change(tmp_path):
    path = tmp_path / "profiles.json"
    keys = {"next": "Right", "prev": "Left", "first": "Home", "fullscreen": "F10"}
    path.write_text(json.dumps({"An Image Viewer": {"keys": keys}, DEFAULT_KEYS: {"prev": "Up", "first": "End"},
                                KEY_PRESETS: {"Mine": {"next": "Down", "prev": "Up", "first": "Home"}}}), encoding="utf-8")
    p = Profiles(path)
    settings = Settings(state_dir=tmp_path)
    assert p.own_keys(VIEWER.title) == {"next": "Right", "prev": "Left"}
    assert page_keys_for(p, settings, VIEWER.title) == PageKeys("Right", "Left")
    assert p.default_keys(settings) == PageKeys("Left", "Up")
    assert p.user_presets() == {"Mine": PageKeys("Down", "Up")}
    p.set_keys(VIEWER.title, page_keys_for(p, settings, VIEWER.title))
    assert json.loads(path.read_text(encoding="utf-8"))["An Image Viewer"]["keys"] == {"next": "Right", "prev": "Left"}
    (tmp_path / "ui.json").write_text('{"language": "de", "first_page_key": "Home"}', encoding="utf-8")
    assert i18n.load_ui_language(tmp_path) == "de"


def test_a_profile_keeps_area_and_keys_across_a_reload(tmp_path):
    path = tmp_path / "profiles.json"
    p = Profiles(path)
    p.set_margins(VIEWER.title, (0, 85, 0, 0))
    p.set_keys(VIEWER.title, PageKeys("Right", "Left"))
    p.set_margins(VIEWER.title, (0, 90, 0, 0))  # a new area keeps the keys
    again = Profiles(path)
    assert again.margins_for(VIEWER.title) == (0, 90, 0, 0)
    assert again.own_keys(VIEWER.title) == {"next": "Right", "prev": "Left"}
    entry = json.loads(path.read_text(encoding="utf-8"))["An Image Viewer"]
    assert entry == {"margins": [0, 90, 0, 0], "keys": {"next": "Right", "prev": "Left"}}
    again.set_margins(VIEWER.title, None)  # no area of its own: the keys stay
    assert Profiles(path).margins_for(VIEWER.title) is None and Profiles(path).own_keys(VIEWER.title)
    again.set_keys(VIEWER.title, None)
    assert "An Image Viewer" not in json.loads(path.read_text(encoding="utf-8"))  # nothing left of it


def test_a_change_is_written_onto_the_file_as_it_is_then(tmp_path):
    """The window keeps its Profiles open while the command line (or an import) changes the file: neither undoes
    the other."""
    path = tmp_path / "profiles.json"
    window, command_line = Profiles(path), Profiles(path)
    window.set_margins(VIEWER.title, (0, 85, 0, 0))
    command_line.set_keys(OTHER.title, PageKeys("Down", "Up"))
    window.set_keys(VIEWER.title, PageKeys("Right", "Left"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["Another Reader"]["keys"]["next"] == "Down" and data["An Image Viewer"]["margins"] == [0, 85, 0, 0]


def test_a_viewers_keys_come_from_its_profile_then_the_defaults_then_the_settings(tmp_path):
    settings = Settings(state_dir=tmp_path, next_page_key="PageDown", prev_page_key="PageUp")
    p = Profiles(tmp_path / "profiles.json")
    assert page_keys_for(p, settings, OTHER.title) == PageKeys("PageDown", "PageUp")  # the settings'
    p.data[DEFAULT_KEYS] = {"next": "Space"}
    assert page_keys_for(p, settings, OTHER.title) == PageKeys("Space", "PageUp")  # key by key
    p.data[DEFAULT_KEYS] = {"next": "Space", "prev": "Backspace"}
    p.set_keys(VIEWER.title, {"next": "Right", "fullscreen": ""})  # (a full-screen key of old is dropped)
    assert page_keys_for(p, settings, VIEWER.title) == PageKeys("Right", "Backspace")
    assert page_keys_for(p, settings, OTHER.title).next == "Space"
    # anything with the data, as the window's stand-ins have it; none at all: the settings
    assert page_keys_for(SimpleNamespace(data={}), settings, VIEWER.title).next == "PageDown"
    assert page_keys_for(SimpleNamespace(), settings, VIEWER.title).next == "PageDown"
    assert page_keys_for(p, SimpleNamespace(), "") == PageKeys("Space", "Backspace")


def _own_preset(profiles: Profiles, name: str, keys: PageKeys) -> None:
    """A preset of the reader's own in the file, as an older version saved them."""
    profiles._change(lambda data: data.setdefault(KEY_PRESETS, {}).__setitem__(name, keys.as_dict()))


def test_presets_built_in_and_the_readers_own(tmp_path):
    p = Profiles(tmp_path / "profiles.json")
    assert p.presets() == BUILTIN_PRESETS and list(BUILTIN_PRESETS) == ["right-to-left", "left-to-right"]
    assert BUILTIN_PRESETS["right-to-left"] == PageKeys("Left", "Right")
    assert BUILTIN_PRESETS["left-to-right"] == PageKeys("Right", "Left")
    _own_preset(p, "Vertical scroll", PageKeys("Down", "Up"))
    _own_preset(p, "left-to-right", PageKeys("Up", "Down"))  # a built-in's name: the built-in stands
    assert list(Profiles(p.path).presets()) == ["right-to-left", "left-to-right", "Vertical scroll"]
    assert Profiles(p.path).presets()["left-to-right"] == BUILTIN_PRESETS["left-to-right"]


def test_apply_to_all_viewers_writes_every_profile_and_the_defaults(tmp_path):
    settings = Settings(state_dir=tmp_path)
    p = Profiles(tmp_path / "profiles.json")
    p.set_margins(VIEWER.title, (0, 85, 0, 0))
    p.set_keys(OTHER.title, PageKeys("Down", "Up"))
    _own_preset(p, "mine", PageKeys("Down", "Up"))
    assert p.apply_to_all(BUILTIN_PRESETS["left-to-right"]) == 2
    data = json.loads(p.path.read_text(encoding="utf-8"))
    assert data["An Image Viewer"] == {"margins": [0, 85, 0, 0], "keys": BUILTIN_PRESETS["left-to-right"].as_dict()}
    assert data["Another Reader"]["keys"]["next"] == "Right" and data[DEFAULT_KEYS]["next"] == "Right"
    assert data[KEY_PRESETS] == {"mine": PageKeys("Down", "Up").as_dict()}  # the presets are no viewer
    assert p.viewers() == ["An Image Viewer", "Another Reader"]
    assert page_keys_for(p, settings, "A viewer never seen") == BUILTIN_PRESETS["left-to-right"]
    assert settings.next_page_key == "Left"  # the settings are not rewritten


class Band(BlackViewerMixin, tk.Toplevel):
    """What the scan band uses, as `test_start_flow.Flow` borrows them."""

    _init_flow_state = A._init_flow_state
    _batch_done = A._batch_done
    _sync_stop = A._sync_stop
    _set_stop = A._set_stop
    stop_batch = A.stop_batch
    close_band = A.close_band
    _page_keys = A._page_keys
    open_batch_dialog = A.open_batch_dialog
    say = A.say
    status = A.status
    _build_strips = A._build_strips
    _place_strip = A._place_strip
    _band_view = A._band_view
    _show_band = A._show_band
    _show_banner = A._show_banner
    _fill = _job_frame = None
    _hide_busy = lambda self: None  # noqa: E731
    _set_busy = lambda self, busy: None  # noqa: E731
    _apply_found_margins = lambda self: None  # noqa: E731
    _run_queued = _offer_colophon = lambda self: None  # noqa: E731

    def __init__(self, root, tmp_path, profiles=None):
        super().__init__(root)
        self.withdraw()
        self._init_flow_state()
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.settle_ms = 0
        self.profiles = profiles if profiles is not None else Profiles(tmp_path / "state" / "profiles.json")
        self.status_var = tk.StringVar(self)
        self.auto_var = tk.BooleanVar(self, value=False)
        self.stop_btn, self.batch_btn, self.translate_btn = {}, {}, {}
        self.selected, self.batch, self.busy, self.reading, self.ready = VIEWER, None, False, False, True
        self._batching = self._resume_auto = False
        self._status_render = self._status_key = self._auto_last = None
        self._health, self._scan_held = [], False
        self.canvas = SimpleNamespace(set_note=lambda *a: None, set_busy=lambda *a: None)
        self.frames = [_frame()]
        self.later: list = []
        self._build_strips()

    def title(self, text=None):
        pass

    def after(self, ms, func=None, *args):
        self.later.append(func)
        return f"after#{len(self.later)}"

    def after_cancel(self, _id):
        pass

    def run_later(self, limit=200):
        for _ in range(limit):
            if not self.later:
                return
            self.later.pop(0)()
        raise AssertionError("still running")

    def _capture(self, hwnd):
        return self.frames[-1]

    def _book_in_front(self):
        return True

    def _current_window(self):
        return self.selected

    def _own_hwnd(self):
        return None

    def _hide_busy(self):
        pass

    def _name_needed(self):
        return False


# ------------------------------------------------------------------ the command line
@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)  # no taslation.toml of the checkout's
    yield tmp_path / "state"
    netguard.uninstall()


def test_taslation_keys_list_show_set_apply(state, capsys):
    assert cli.main(["keys", "list"]) == 0
    out = capsys.readouterr().out
    assert "right-to-left (built-in): next Left, previous Right\n" in out
    assert "viewers with keys of their own: none" in out
    assert cli.main(["keys", "apply", "left-to-right", "--viewer", VIEWER.title]) == 0
    assert cli.main(["keys", "show", "--viewer", VIEWER.title]) == 0
    out = capsys.readouterr().out
    assert "An Image Viewer: next Right, previous Left\n" in out
    with pytest.raises(SystemExit):  # TASlation presses no full-screen key: there is none to set
        cli.main(["keys", "set", "--viewer", VIEWER.title, "--fullscreen", ""])
    capsys.readouterr()
    assert cli.main(["keys", "set", "--all", "--next", "Down", "--prev", "Up"]) == 0
    data = json.loads((state / "profiles.json").read_text(encoding="utf-8"))
    assert data[DEFAULT_KEYS] == {"next": "Down", "prev": "Up"}
    assert data["An Image Viewer"]["keys"] == data[DEFAULT_KEYS]
    assert cli.main(["keys", "set", "--viewer", VIEWER.title, "--reset"]) == 0
    assert "keys" not in json.loads((state / "profiles.json").read_text(encoding="utf-8")).get("An Image Viewer", {})
    with pytest.raises(SystemExit, match="no preset"):
        cli.main(["keys", "apply", "upside-down", "--all"])
    with pytest.raises(SystemExit, match="--viewer TITLE or --all"):
        cli.main(["keys", "apply", "left-to-right"])
    with pytest.raises(SystemExit, match="same key"):
        cli.main(["keys", "set", "--all", "--next", "Up"])


# ------------------------------------------------------------------ Page keys...
def test_check_keys_says_what_is_wrong_in_the_windows_language():
    assert check_keys({"next": "right", "prev": "Left", "fullscreen": "home"}) == (PageKeys("right", "Left"), "")
    assert check_keys({"next": "q", "prev": "w"})[0] == PageKeys("Q", "W")
    assert check_keys({"next": "", "prev": "Left"}) == (None, "The next page and the previous page need a key each.")
    assert check_keys({"next": "Left", "prev": "left"})[1] == (
        "The next page and the previous page cannot have the same key.")
    i18n.set_language("ja")
    try:
        assert check_keys({"next": "Left", "prev": "Hyper"})[1] == (
            "不明なキー名です: Hyper。上に挙げた名前のどれかを使ってください。")
    finally:
        i18n.set_language("en")


def _dialog(root, tmp_path, saved=None):
    settings = Settings(state_dir=tmp_path / "state")
    profiles = Profiles(tmp_path / "state" / "profiles.json")
    dialog = PageKeysDialog(root, VIEWER.title, profiles, settings,
                            on_saved=(lambda: saved.append(1)) if saved is not None else None)
    dialog.withdraw()
    return dialog, profiles


def _radio_texts(dialog):
    return [w.cget("text") for w in dialog.preset_frame.winfo_children()]


def test_the_dialog_shows_the_viewer_the_presets_and_fills_the_fields(hidden_root, tmp_path):
    dialog, _profiles = _dialog(hidden_root, tmp_path)
    assert _radio_texts(dialog) == ["Right-to-left reading: Left arrow turns to the next page",
                                    "Left-to-right reading: Right arrow turns to the next page"]
    assert dialog.values() == {"next": "Left", "prev": "Right"}  # (no full-screen key: TASlation presses none)
    assert dialog.preset_var.get() == "right-to-left"  # the fields hold that preset's keys
    dialog.choose("left-to-right")
    assert dialog.values() == {"next": "Right", "prev": "Left"}
    dialog.vars["prev"].set("End")
    assert dialog.preset_var.get() == ""  # no preset holds these keys
    dialog.destroy()


def test_apply_to_this_viewer_keeps_keys_in_its_profile(hidden_root, tmp_path):
    saved = []
    dialog, profiles = _dialog(hidden_root, tmp_path, saved=saved)
    dialog.vars["next"].set("Left")
    dialog.vars["prev"].set("left")
    dialog.apply()
    assert dialog.error_var.get() == "The next page and the previous page cannot have the same key."
    assert dialog.winfo_exists() and not saved and not profiles.own_keys(VIEWER.title)
    dialog.choose("left-to-right")
    dialog.apply()
    assert saved == [1] and not dialog.winfo_exists()
    again = Profiles(profiles.path)
    assert again.own_keys(VIEWER.title) == BUILTIN_PRESETS["left-to-right"].as_dict()
    assert DEFAULT_KEYS not in again.data


def test_apply_to_all_viewers_and_reset_to_the_defaults(hidden_root, tmp_path):
    saved = []
    dialog, profiles = _dialog(hidden_root, tmp_path, saved=saved)
    profiles.set_margins(OTHER.title, (0, 10, 0, 0))
    dialog.choose("left-to-right")
    dialog.apply_all()
    again = Profiles(profiles.path)
    assert again.data[DEFAULT_KEYS] == BUILTIN_PRESETS["left-to-right"].as_dict()
    assert again.own_keys(OTHER.title) == BUILTIN_PRESETS["left-to-right"].as_dict()
    dialog, profiles = _dialog(hidden_root, tmp_path, saved=saved)
    dialog.vars["next"].set("Down")
    profiles.set_keys(VIEWER.title, PageKeys("Down", "Up"))
    dialog.reset()  # the viewer's own keys go; the defaults (now left-to-right) fill the fields; the dialog stays
    assert dialog.winfo_exists() and saved == [1, 1] and not Profiles(profiles.path).own_keys(VIEWER.title)
    assert dialog.values() == BUILTIN_PRESETS["left-to-right"].as_dict()
    assert dialog.source_label.cget("text") == ""
    dialog.destroy()


def test_the_dialog_offers_the_two_directions_and_no_presets_of_ones_own(hidden_root, tmp_path):
    dialog, profiles = _dialog(hidden_root, tmp_path)
    dialog.destroy()
    _own_preset(profiles, "Scrolling viewer", PageKeys("Down", "Up"))  # kept in the file, for `taslation keys`
    profiles.set_keys(VIEWER.title, PageKeys("Down", "Up"))
    dialog = PageKeysDialog(hidden_root, VIEWER.title, profiles, Settings(state_dir=tmp_path))
    dialog.withdraw()
    assert len(_radio_texts(dialog)) == 2 and dialog.preset_var.get() == ""
    assert dialog.source_label.cget("text") == "This viewer has keys of its own."
    assert not hasattr(dialog, "delete_btn") and not hasattr(dialog, "save_preset")
    dialog.destroy()


def test_the_dialogs_texts_in_japanese(hidden_root, tmp_path):
    i18n.set_language("ja")
    dialog, _profiles = _dialog(hidden_root, tmp_path)
    try:
        assert dialog.title() == "ページ送りのキー"
        assert _radio_texts(dialog) == ["右から左へ読む: ← キーで次のページ", "左から右へ読む: → キーで次のページ"]
        assert i18n.tr("Key names: {names}.") == "キー名: {names}。"
    finally:
        dialog.destroy()
        i18n.set_language("en")


def test_every_string_of_the_feature_is_in_every_language():
    from taslation.locales.features import page_keys as texts
    from taslation.ui.dialogs import pagekeys as dialog_mod

    used = {*PRESET_LABELS.values(), *dialog_mod.FIELD_LABELS.values()}
    assert used <= set(texts.TEXTS)
    for key in texts.TEXTS:
        for code in i18n.UI_LANGUAGES:
            if code != "en":
                assert i18n.CATALOGS[code][key].strip(), (code, key)


# ------------------------------------------------------------------ the window: the status line
class Viewer:
    """What the viewer's keys use in the window."""

    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    _viewer_left = lambda self: None
    _page_keys = A._page_keys
    _page_key_pair = A._page_key_pair
    _on_window_selected = A._on_window_selected
    _learn_viewer = A._learn_viewer
    _title_book = A._title_book
    _warm_page_models = A._warm_page_models
    status = A.status
    say = A.say

    def __init__(self, root, tmp_path):
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.settle_ms = 0
        self.profiles = Profiles(tmp_path / "state" / "profiles.json")
        self.selected = VIEWER
        self.windows = [VIEWER]
        self.window_box = SimpleNamespace(current=lambda: 0)
        self.status_var = tk.StringVar(master=root)
        self.book_var = tk.StringVar(master=root)
        self._book_edited, self._reading_at_start, self.reading = True, False, False
        self._status_render = self._status_key = self._auto_last = None
        self.frames = [_frame()]
        self.later: list = []

    def after(self, ms, func=None, *args):
        self.later.append(func)

    def run_later(self):
        while self.later:
            self.later.pop(0)()

    def _capture(self, hwnd):
        return self.frames[-1]

    def _current_window(self):
        return self.selected

    def _own_hwnd(self):
        return 99

    def _found_margins(self):
        return (0, 0, 0, 0)

    def _set_covered(self, covered):
        pass

    def _redisplay(self):
        pass

    def _follow_viewer(self):
        pass


def test_choosing_a_viewer_with_keys_of_its_own_says_them_once(hidden_root, tmp_path):
    w = Viewer(hidden_root, tmp_path)
    w._on_window_selected()
    assert w.status_var.get() == "Viewer: An Image Viewer"  # the defaults: nothing said of them
    w.profiles.set_keys(VIEWER.title, BUILTIN_PRESETS["left-to-right"])
    w._on_window_selected()
    assert w.status_var.get() == "Viewer: An Image Viewer  Page keys: → next page, ← previous page."
    w.profiles.set_margins(VIEWER.title, (0, 85, 0, 0))
    w._on_window_selected()
    assert w.status_var.get() == ("Viewer: An Image Viewer  (area set)  Page keys: "
                                  "→ next page, ← previous page.")
    i18n.set_language("ja")
    try:
        assert w._status_render().endswith("ページ送りのキー: 次のページ →、前のページ ←。")
    finally:
        i18n.set_language("en")


def test_the_page_menu_has_page_keys_and_no_full_screen_command():
    import inspect

    source = inspect.getsource(A._build_menus)
    assert source.index('_("Set area...")') < source.index('_("Page keys...")')
    assert "Viewer full screen" not in source and "fullscreen" not in source and not hasattr(A, "toggle_viewer_fullscreen")
    assert pagekeys.KEY_NAMES[:2] == ("Left", "Right")


# ------------------------------------------------------------------ the profile of a viewer whose title names a file
def test_a_title_that_names_the_file_shown_keeps_its_profile_under_the_text_after_the_last_dash():
    from taslation import viewerparts
    from taslation.cache import viewer_key_from_title
    from taslation.pagekeys import profile_key, profile_names

    assert profile_names("page01.png - An Image Viewer") == ("page01.png - An Image Viewer", "An Image Viewer")
    assert profile_names("a - b - An Image Viewer") == ("a - b - An Image Viewer", "An Image Viewer")
    assert profile_names("An Image Viewer") == ("An Image Viewer",)  # no " - ": the whole title, as before
    known = "My book 1 - Google Chrome"  # a browser the title ends with: its name, as before
    assert profile_names(known) == (viewer_key_from_title(known),) == ("Google Chrome",)
    viewerparts.change(lambda memory: memory.learn(["Yomizuq"]))  # an invented viewer, learned on this computer
    known = "My book 1 - Yomizuq"
    assert profile_names(known) == (viewer_key_from_title(known),) == ("Yomizuq",)
    assert profile_key({}, "page01.png - An Image Viewer") == "An Image Viewer"  # a new profile
    assert profile_key({"page01.png - An Image Viewer": {}}, "page01.png - An Image Viewer") == (
        "page01.png - An Image Viewer")  # one kept under the whole title is found first


def test_every_file_an_image_viewer_shows_finds_the_same_profile(tmp_path):
    settings = Settings(state_dir=tmp_path)
    p = Profiles(tmp_path / "profiles.json")
    p.set_keys("page01.png - An Image Viewer", BUILTIN_PRESETS["left-to-right"])
    p.set_margins("page01.png - An Image Viewer", (0, 40, 0, 0))
    again = Profiles(p.path)
    assert list(again.data) == ["An Image Viewer"]
    assert again.keys_for("page02.png - An Image Viewer", settings) == BUILTIN_PRESETS["left-to-right"]
    assert again.margins_for("cover.jpg - An Image Viewer") == (0, 40, 0, 0)
    assert again.key_of("page02.png - An Image Viewer") == "An Image Viewer"


def test_a_profile_kept_under_the_whole_title_goes_on_working(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"page01.png - An Image Viewer": {"margins": [0, 85, 0, 0]}}), encoding="utf-8")
    p = Profiles(path)
    assert p.margins_for("page01.png - An Image Viewer") == (0, 85, 0, 0)  # the old key, looked up first
    p.set_keys("page01.png - An Image Viewer", PageKeys("Right", "Left"))  # written where it was found
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data) == ["page01.png - An Image Viewer"]
    assert data["page01.png - An Image Viewer"]["keys"]["next"] == "Right"
    assert p.margins_for("page02.png - An Image Viewer") is None  # another file: the new key, which has none yet
    p.set_margins("page02.png - An Image Viewer", (0, 10, 0, 0))
    assert Profiles(path).margins_for("page03.png - An Image Viewer") == (0, 10, 0, 0)
    assert Profiles(path).margins_for("page01.png - An Image Viewer") == (0, 85, 0, 0)


# ------------------------------------------------------------------ how viewers take keys, by window
def test_what_was_seen_last_of_a_viewers_keys_counts_and_each_window_has_its_own():
    from taslation.pagekeys import KeyWays, key_ways

    ways = KeyWays()
    assert not ways.real(1) and not ways.posted(1)
    ways.learned(1, False, False)  # a click, or a key pressed at once: nothing new
    assert not ways.real(1) and not ways.posted(1)
    ways.learned(1, True, True)  # (the real press is what turned it)
    assert ways.real(1) and not ways.posted(1) and not ways.real(2)
    ways.learned(1, False, True)
    assert ways.posted(1) and not ways.real(1)
    ways.learned(2, True, False)
    assert ways.real(2) and ways.posted(1)
    window = SimpleNamespace()
    assert key_ways(window) is key_ways(window) and key_ways(SimpleNamespace()) is not key_ways(window)


# ------------------------------------------------------------------ the window's keys go on as the viewer's own
def test_the_windows_next_and_previous_keys_go_on_as_the_viewers_own_and_every_other_key_as_it_is():
    from taslation.pagekeys import passed_on

    window = PageKeys("Left", "Right")  # the defaults: what a person turns pages with everywhere
    viewer = PageKeys("PageDown", "PageUp")  # a viewer that turns with Page Down / Page Up
    assert [passed_on(k, viewer, window) for k in ("Left", "Right", "PageDown", "PageUp", "Home", "Space")] == [
        "PageDown", "PageUp", "PageDown", "PageUp", "Home", "Space"]
    letters = PageKeys("N", "Backspace")  # keys the window does not pass on by themselves
    assert passed_on("Left", letters, window) == "N" and passed_on("right", letters, window) == "Backspace"
    ltr = PageKeys("Right", "Left")  # an image viewer: its own keys as they are
    assert passed_on("Left", ltr, window) == "Left" and passed_on("Right", ltr, window) == "Right"
    assert passed_on("Left", window, window) == "Left"  # a viewer without keys of its own: as before


def test_the_key_back_is_named_as_it_is_pressed_in_the_window():
    from taslation.pagekeys import pressed_for
    from taslation.ui.constants import FORWARDED_KEYS

    window, forwarded = PageKeys("Left", "Right"), FORWARDED_KEYS.values()
    assert pressed_for("PageUp", PageKeys("PageDown", "PageUp"), window, forwarded) == "PageUp"
    assert pressed_for("P", PageKeys("N", "P"), window, forwarded) == "Right"  # P goes on from the window's Right
    assert pressed_for("X", PageKeys("N", "P"), window, forwarded) is None and pressed_for(None, window, window) is None


def test_the_status_line_says_which_key_of_the_window_goes_on_as_which(hidden_root):
    from taslation.ui.viewers import keys_words

    assert keys_words(PageKeys("PageDown", "PageUp"), PageKeys("Left", "Right")) == (
        "Page keys: Page Down next page, Page Up previous page.  ← here goes to the viewer as Page Down."
        "  → here goes to the viewer as Page Up.")
    assert keys_words(PageKeys("Right", "Left"), PageKeys("Left", "Right")) == (
        "Page keys: → next page, ← previous page.")  # its own keys: nothing goes on as another
    i18n.set_language("ja")
    try:
        assert "ここでの ← は、ビューアに N として渡します。" in keys_words(PageKeys("N", "P"), PageKeys("Left", "Right"))
    finally:
        i18n.set_language("en")


def test_a_key_pressed_in_the_window_goes_on_once_as_the_viewers_key(setup, monkeypatch, tmp_path):
    """One press of the window's next key, one press of the viewer's saved next key; a key of the viewer's own and
    any other key go on as they are."""
    from test_follow import VIEWER as BOOK
    from taslation.ui import live, reading

    turned = []
    monkeypatch.setattr(reading, "post_key", lambda hwnd, key: setup.viewer.keys.append((setup.clock.now, key)) or
                        turned.append(key) or setup.viewer.frames.append((setup.clock.now + 0.1, _page(30 + len(turned)))))
    monkeypatch.setattr(live, "press_briefly", lambda hwnd, key: pytest.fail("a posted key turned the page"))
    w = setup.make()
    w.profiles = Profiles(tmp_path / "profiles.json")
    w.profiles.set_keys(BOOK, PageKeys("PageDown", "PageUp"))
    w.settings.next_page_key, w.settings.prev_page_key = "Left", "Right"
    w.start()
    setup.clock.run(3)
    w.job_done()
    for key in ("Left", "Right", "PageUp", "Home"):
        w.forward_key(key)
        setup.clock.run(4)
        w.job_done()
    assert [key for _t, key in setup.viewer.keys] == ["PageDown", "PageUp", "PageUp", "Home"]
    w._say_two_turns("PageDown")  # the key back is the one to press here
    assert w.statuses[-1] == "The viewer turned two pages; press Page Up once to go back."
    w._say_two_turns("PageUp")
    assert w.statuses[-1] == "The viewer turned two pages; press Page Down once to go back."  # (the key itself first)
    w.profiles.set_keys(BOOK, PageKeys("N", "P"))
    w._say_two_turns("N")
    assert w.statuses[-1] == "The viewer turned two pages; press → once to go back."  # Right goes on as P
