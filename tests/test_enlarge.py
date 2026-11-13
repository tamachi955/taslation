"""The viewer's window enlarged to its monitor's work area as it is chosen, in the background, and read once it has
settled (a minimised one shown again first): no key, no change of the foreground, once per viewer chosen, put back when it goes; its own hand-set area
so that the foreground stays too. The window's parts are borrowed onto stand-ins, Windows' calls on a fake."""
from __future__ import annotations

import json
import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from taslation import batch as batch_mod
from taslation import capture as capture_mod
from taslation import cli, i18n
from taslation.batch import BatchReader
from taslation.cli import enlarge_viewer
from taslation.capture import windows
from taslation.capture.windows import Enlarged, behind_others, enlarge_window, restore_window, smaller_than
from taslation.config import ConfigError, Settings
from taslation.messages import Message
from taslation.pagekeys import PageKeys, Profiles, own_keys, page_keys_for
from taslation.ui import app as app_mod
from taslation.ui import viewers

A = app_mod.App
WORK = (0, 0, 1920, 1040)
SMALL = (100, 100, 900, 756)
TITLE = "Book - An Image Viewer"


def _win(hwnd=7, title=TITLE):
    return SimpleNamespace(hwnd=hwnd, title=title, class_name="Viewer", label=lambda: title)


def _frame(x=40):
    image = Image.new("RGB", (320, 240), "white")
    ImageDraw.Draw(image).rectangle((x, 40, x + 60, 120), fill="black")
    return image


# ------------------------------------------------------------------ Windows' side, on a fake
class User32:
    """Only what enlarging may call: any call that would touch the foreground, the order of the windows or a key
    is not here, and fails."""

    def __init__(self, zoomed=False):
        self.zoomed = zoomed
        self.moved = []

    def IsZoomed(self, hwnd):
        return self.zoomed


@pytest.fixture
def fake(monkeypatch):
    user32 = User32()
    place = {"rect": SMALL}

    def move(hwnd, rect):
        user32.moved.append(rect)
        place["rect"] = rect
        return True

    monkeypatch.setattr(windows, "user32", user32, raising=False)
    monkeypatch.setattr(windows, "window_shown", lambda hwnd: True)
    monkeypatch.setattr(windows, "work_area", lambda hwnd: WORK)
    monkeypatch.setattr(windows, "window_rect", lambda hwnd: place["rect"])
    monkeypatch.setattr(windows, "move_window", move)
    return SimpleNamespace(user32=user32, place=place)


def test_smaller_than_the_work_area():
    assert smaller_than(SMALL, WORK) and smaller_than((0, 0, 1920, 900), WORK) and smaller_than((0, 0, 1000, 1040), WORK)
    assert not smaller_than(WORK, WORK) and not smaller_than((-8, -8, 1928, 1048), WORK)


def test_the_window_is_put_on_the_work_area_and_nothing_else_is_called(fake):
    enlarged = enlarge_window(7)  # (the fake has no SetForegroundWindow, no SendInput: a call to them would fail)
    assert enlarged == Enlarged(7, SMALL, WORK) and fake.user32.moved == [WORK] and enlarged.changed


def test_a_maximised_large_minimised_or_hidden_window_is_left_alone(fake, monkeypatch):
    fake.user32.zoomed = True
    assert enlarge_window(7) is None
    fake.user32.zoomed = False
    fake.place["rect"] = WORK
    assert enlarge_window(7) is None
    fake.place["rect"] = SMALL
    monkeypatch.setattr(windows, "window_shown", lambda hwnd: False)
    assert enlarge_window(7) is None and fake.user32.moved == []


def test_only_a_window_of_the_size_taslation_gave_it_is_put_back(fake, monkeypatch):
    enlarged = enlarge_window(7)
    assert restore_window(enlarged) and fake.place["rect"] == SMALL  # back
    enlarged = enlarge_window(7)
    fake.place["rect"] = (0, 0, 1200, 800)  # the reader made it smaller
    assert not restore_window(enlarged) and fake.place["rect"] == (0, 0, 1200, 800)
    enlarged = Enlarged(7, SMALL, WORK)
    fake.place["rect"] = (300, 0, 2220, 1040)  # moved, same size: put back
    assert restore_window(enlarged) and fake.place["rect"] == SMALL
    fake.place["rect"] = WORK
    fake.user32.zoomed = True  # the reader maximised it
    assert not restore_window(enlarged)
    fake.user32.zoomed = False
    monkeypatch.setattr(windows, "window_shown", lambda hwnd: False)  # closed or minimised
    assert not restore_window(enlarged)


def test_a_size_the_window_clamps_is_the_size_it_keeps():
    enlarged = Enlarged(7, SMALL, WORK)
    enlarged.given = (0, 0, 800, 656)
    assert not enlarged.changed  # the same size: a window of a fixed size
    enlarged.given = (0, 0, 1920, 1000)
    assert enlarged.changed and enlarged.has_its_size((5, 5, 1925, 1005))


def test_another_window_over_the_viewer_is_seen_but_no_overlay_or_hidden_one(monkeypatch):
    above = {1: 2, 2: 3, 3: 4, 4: 0}
    state = {2: (False, False, 0, (0, 0, 2000, 2000)), 3: (True, True, 0, (0, 0, 2000, 2000)),
             4: (True, False, 0x20, (0, 0, 2000, 2000))}  # hidden, minimised, click-through
    fake = SimpleNamespace(IsWindow=lambda h: True, GetAncestor=lambda h, f: h, GetWindow=lambda h, f: above[h],
                           IsWindowVisible=lambda h: state[h][0], IsIconic=lambda h: state[h][1],
                           GetWindowLongW=lambda h, i: state[h][2])
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", fake, raising=False)
    monkeypatch.setattr(windows, "GWL_EXSTYLE", -20, raising=False)
    monkeypatch.setattr(windows, "client_rect_on_screen", lambda hwnd: (100, 100, 800, 600))
    monkeypatch.setattr(windows, "_is_cloaked", lambda hwnd: False)
    monkeypatch.setattr(windows, "_window_rect", lambda hwnd: state[hwnd][3])
    assert not behind_others(1)
    state[3] = (True, False, 0, (950, 0, 1000, 50))  # on the screen, beside the viewer
    assert not behind_others(1)
    state[3] = (True, False, 0, (850, 0, 1000, 150))  # over a corner of it
    assert behind_others(1)


# ------------------------------------------------------------------ the window: the gate
class Win(tk.Toplevel):
    _release_model = lambda self: None  # noqa: E731 - Ollama's model is not this test's
    _page_keys = lambda self, win=None: PageKeys(fullscreen="")  # (the viewer's own full screen: tests/test_wgc.py)
    _lower_viewer = lambda self: None
    _over_close = lambda self: None

    """The window's part that enlarges the viewer; `after` keeps its callbacks, Windows' calls are the test's."""

    _enlarge_first = A._enlarge_first
    _enlarge_wait = A._enlarge_wait
    _enlarge_done = A._enlarge_done
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    _restore_enlarged = A._restore_enlarged
    _keep_enlarged = A._keep_enlarged  # (kept for the next start: tests/test_enlarge_recovery.py)
    _viewer_left = A._viewer_left
    _window_enlarged = A._window_enlarged
    _sync_area = A._sync_area
    _resize_begins = A._resize_begins
    _forget_page_area = A._forget_page_area
    _on_window_selected = A._on_window_selected
    _learn_viewer = A._learn_viewer
    _title_book = A._title_book
    _warm_page_models = A._warm_page_models
    _area_chosen = A._area_chosen
    clear_area = A.clear_area
    _find_page = A._find_page
    _found_margins = A._found_margins
    _inner_margins = A._inner_margins
    _hand_set = A._hand_set
    _apply_found_margins = A._apply_found_margins
    _area_hint_due = A._area_hint_due
    _on_close = A._on_close
    _close_allowed = A._close_allowed
    _target_chosen = lambda self: None  # (the "To:" box kept: tests/test_window_state.py)
    _on_new_page = A._on_new_page
    translate_now = A.translate_now
    status = A.status
    say = A.say

    def __init__(self, root, tmp_path):
        super().__init__(root)
        self.withdraw()
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.settle_ms = 0
        self.settings.margins = (0, 0, 0, 0)
        self.profiles = Profiles(tmp_path / "state" / "profiles.json")
        self.selected = _win()
        self.windows = [self.selected]
        self.index = 0
        self.window_box = SimpleNamespace(current=lambda: self.index)
        self.status_var = tk.StringVar(master=root)
        self.book_var = tk.StringVar(master=root, value="Book")
        self.canvas = SimpleNamespace(note="", set_note=lambda text, ms=0: setattr(self, "note", text))
        self.note = ""
        self.reading = self.busy = self._batching = self._manual_area = self._area_hinted = False
        self.ready = True
        self._book_edited, self._reading_at_start = True, False
        self._status_render = self._status_key = self._auto_last = self._auto_candidate = self._hand_area = None
        self._page_areas: dict = {}
        self._enlarged = self._enlarging = self._enlarge_asked = None
        self._area_large = False
        self._start_pending = None
        self._book_scanned, self._scanned_book = True, "Book"
        self._ordering = None
        self.batch = None
        self.frames = [_frame()]
        self.later: list = []
        self.read: list = []

    def after(self, ms, func=None, *args):
        self.later.append(func)

    def run_later(self):
        while self.later:
            self.later.pop(0)()

    def destroy(self):
        self.closed = True

    def _capture(self, hwnd):
        image = self.frames[-1]
        self._find_page(image)
        return image

    def _book_in_front(self):
        return True

    def _current_window(self):
        return self.selected

    def scan_mode(self):
        return "page"

    def _name_needed(self):
        return False

    def _look_soon(self):
        self.looked = True

    _look_afresh = lambda self, frame=None, thumb=None: self._look_soon()

    def _set_covered(self, covered):
        pass

    def _redisplay(self):
        pass

    def _follow_viewer(self):
        self.followed = getattr(self, "followed", 0) + 1

    def _own_hwnd(self):
        return 99  # TASlation's own top-level window

    def _show_live(self, image, thumb=None):
        pass

    def _start_translate(self, image, complete=None, thumb=None):
        self.read.append(image)


@pytest.fixture
def desk(monkeypatch):
    """The screen: the viewer's windows and what was done to them. Any key or click for a viewer fails."""

    def never(*_a, **_k):
        raise AssertionError("a key or a click went to the viewer")

    from taslation.capture import windows as windows_mod

    for name in ("press_key", "press_briefly", "post_key", "post_click", "click_screen", "bring_to_front"):
        monkeypatch.setattr(windows_mod, name, never)
    d = SimpleNamespace(rect={7: SMALL, 8: (0, 0, 500, 500)}, shown={7: True, 8: True}, enlarged=[], restored=[],
                        large_after={})

    def enlarge(hwnd):
        if d.rect[hwnd] == WORK:
            return None
        before = d.rect[hwnd]
        d.rect[hwnd] = d.large_after.get(hwnd, WORK)
        d.enlarged.append(hwnd)
        return Enlarged(hwnd, before, WORK)

    def restore(e):
        if e.has_its_size(d.rect[e.hwnd]):
            d.rect[e.hwnd] = e.before
            d.restored.append(e.hwnd)
            return True
        return False

    monkeypatch.setattr(viewers, "enlarge_window", enlarge)
    monkeypatch.setattr(viewers, "restore_window", restore)
    monkeypatch.setattr(viewers, "window_rect", lambda hwnd: d.rect[hwnd])
    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: d.shown[hwnd])
    return d


def test_the_first_read_waits_for_the_enlarged_window_once(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    ran = []
    assert not w._enlarge_first(lambda: ran.append(1)) and desk.enlarged == [7]
    assert not ran and w.later  # the Tk thread is not held: it goes on with `after`
    assert not w._enlarge_first()  # Auto meanwhile: what waits stays
    w.run_later()
    assert ran == [1] and w._enlarged.given == WORK and w._enlarging is None and w.looked
    assert w._enlarge_first() and desk.enlarged == [7]  # a page turn enlarges nothing


def test_a_frame_that_keeps_changing_is_waited_for_a_while_only(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    capture = iter(range(1000))
    w._capture = lambda hwnd: _frame(10 + next(capture) * 5 % 200)
    ran = []
    w._enlarge_first(lambda: ran.append(1))
    w.run_later()
    assert ran == [1] and w._enlarging is None


def test_f5_and_auto_read_only_after_the_window_is_enlarged(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    w.translate_now()  # F5
    assert desk.enlarged == [7] and w.read == []
    w.run_later()
    assert len(w.read) == 1
    w = Win(hidden_root, tmp_path)
    desk.rect[7] = SMALL
    w._auto_last = "thumb"
    w._on_new_page(_frame(), "thumb")  # Auto: this frame goes, the next one is read
    assert w.read == [] and w._auto_last is None
    w.run_later()
    assert w._auto_last is None and w.looked
    w._on_new_page(_frame(), "thumb")
    assert len(w.read) == 1


def test_a_window_that_is_large_already_is_read_at_once(hidden_root, tmp_path, desk):
    desk.rect[7] = WORK
    w = Win(hidden_root, tmp_path)
    assert w._enlarge_first() and desk.enlarged == [] and w._enlarged is None


def test_a_minimised_window_is_looked_at_again_at_the_next_read(hidden_root, tmp_path, desk):
    desk.shown[7] = False
    w = Win(hidden_root, tmp_path)
    assert w._enlarge_first() and desk.enlarged == [] and w._enlarge_asked is None
    desk.shown[7] = True
    assert not w._enlarge_first() and desk.enlarged == [7]


def test_a_window_the_reader_makes_smaller_stays_so_and_nothing_is_said(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    w._enlarge_first()
    w.run_later()
    desk.rect[7] = (0, 0, 1000, 700)
    w.status_var.set("before")
    assert w._enlarge_first() and desk.enlarged == [7] and w.status_var.get() == "before"
    w._restore_enlarged()
    assert desk.rect[7] == (0, 0, 1000, 700) and desk.restored == []


def test_a_window_of_a_fixed_size_is_read_as_it_is_with_one_line(hidden_root, tmp_path, desk):
    desk.large_after[7] = SMALL
    w = Win(hidden_root, tmp_path)
    ran = []
    w._enlarge_first(lambda: ran.append(1))
    w.run_later()
    line = "This viewer's window keeps its size, so it is read as it is."
    assert ran == [1] and w.status_var.get() == line and w.note == line and w._enlarged is None
    w.status_var.set("after")
    assert w._enlarge_first() and w.status_var.get() == "after" and desk.enlarged == [7]  # said once
    w._restore_enlarged()
    assert desk.restored == []
    assert i18n.CATALOGS["ja"][line] == "このビューアのウィンドウは大きさが変わらないので、そのままの大きさで読み取ります。"


def test_the_window_goes_back_on_another_viewer_and_on_close_not_on_the_same_one_chosen_again(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    w._enlarge_first()
    w.run_later()
    w._on_window_selected()  # the same window, as the list's rescan chooses it again
    assert desk.restored == [] and w._enlarged is not None and w._enlarge_first()
    w.windows = [w.selected, _win(8, "Other - An Image Viewer")]
    w.index = 1
    w._on_window_selected()
    assert desk.restored == [7] and desk.rect[7] == SMALL
    assert w._enlarge_asked == 8 and desk.enlarged == [7, 8]  # the new viewer is enlarged at once, as it is chosen
    assert not w._enlarge_first() and desk.enlarged == [7, 8]  # a read waits for it to settle; not enlarged twice
    w.run_later()
    assert w._enlarge_first() and desk.enlarged == [7, 8]
    w._on_close()
    assert desk.restored == [7, 8] and w.closed


def test_choosing_another_viewer_while_the_window_settles_lets_what_waited_go_on(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    ran = []
    w._enlarge_first(lambda: ran.append(1))
    w.windows = [w.selected, _win(8, "Other - An Image Viewer")]
    w.index = 1
    w._on_window_selected()
    assert ran == [1] and desk.restored == [7]
    assert w._enlarging is not None and w._enlarging["enlarged"].hwnd == 8  # the new viewer's own wait
    w.run_later()  # the old timer finds nothing of its own to do; the new one settles
    assert ran == [1] and w._enlarging is None


# ------------------------------------------------------------------ chosen: shown again when minimised, enlarged at once
@pytest.fixture
def unminimise(monkeypatch, desk):
    """The viewers' windows minimised or not (`desk.minimised`); what was shown again, and behind which window."""
    desk.minimised, desk.unminimised = set(), []

    def show(hwnd, below=None):
        if hwnd not in desk.minimised:
            return False
        desk.minimised.discard(hwnd)
        desk.unminimised.append((hwnd, below))
        return True

    monkeypatch.setattr(viewers, "unminimise_window", show)
    return desk


def test_a_viewer_chosen_is_enlarged_at_once_and_read_once_it_has_settled(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    w.windows = [w.selected, _win(8, "Other - An Image Viewer")]
    w.index = 1
    w._on_window_selected(picked=True)
    assert desk.enlarged == [8] and w._enlarge_asked == 8 and w._enlarging is not None  # before any read
    assert w.followed == 1
    assert not w._enlarge_first(w.translate_now) and desk.enlarged == [8]  # F5 meanwhile waits for the settle
    w.run_later()
    assert w._enlarging is None and w.read and desk.enlarged == [8]  # read once settled, enlarged once


def test_a_minimised_viewer_chosen_is_shown_again_behind_taslation_then_enlarged(hidden_root, tmp_path, unminimise):
    w = Win(hidden_root, tmp_path)
    w.windows = [w.selected, _win(8, "Other - An Image Viewer")]
    unminimise.minimised.add(8)
    w.index = 1
    w._on_window_selected(picked=True)
    assert unminimise.unminimised == [(8, 99)] and unminimise.enlarged == [8]
    assert w.status_var.get() == "Viewer: Other - An Image Viewer  (restored from the taskbar)"
    w.run_later()
    unminimise.minimised.add(8)  # minimised again afterwards: the rescan choosing it again restores nothing
    w._on_window_selected()
    assert unminimise.unminimised == [(8, 99)] and 8 in unminimise.minimised
    w._on_window_selected(picked=True)  # the person picks it in the list again: that is a choice of theirs
    assert unminimise.unminimised == [(8, 99), (8, 99)]
    assert i18n.CATALOGS["ja"]["Viewer: {title}  (restored from the taskbar)"] == "ビューア: {title}（タスクバーから元に戻しました）"


def test_a_viewer_chosen_that_is_not_minimised_is_left_as_it_is(hidden_root, tmp_path, unminimise):
    w = Win(hidden_root, tmp_path)
    w.windows = [w.selected, _win(8, "Other - An Image Viewer")]
    w.index = 1
    w._on_window_selected(picked=True)
    assert unminimise.unminimised == [] and w.status_var.get() == "Viewer: Other - An Image Viewer"


# ------------------------------------------------------------------ the area of the enlarged window
def test_the_enlarged_window_has_an_area_of_its_own(hidden_root, tmp_path, desk):
    w = Win(hidden_root, tmp_path)
    w.profiles.set_margins(w.selected, (0, 85, 0, 0))
    w._on_window_selected()
    assert w.settings.margins == (0, 85, 0, 0) and w._manual_area
    w._enlarge_first()
    w.run_later()
    assert w._area_large and not w._manual_area and w._hand_area is None  # the old area says nothing of this frame
    assert w.profiles.margins_for(w.selected) == (0, 85, 0, 0) and w.profiles.margins_for(w.selected, large=True) is None
    assert w.settings.margins != (0, 85, 0, 0)
    w._area_chosen((0, 24, 320, 240), (320, 240))  # Set area on this frame
    assert w.profiles.margins_for(w.selected, large=True) == (0, 24, 0, 0)
    assert w.profiles.margins_for(w.selected) == (0, 85, 0, 0)
    desk.rect[7] = (0, 0, 1000, 700)  # the reader makes it smaller: the area of the window as it was, at the next frame
    w._capture(7)
    assert not w._area_large and w._hand_area == (0, 85, 0, 0) and w.settings.margins == (0, 85, 0, 0)
    desk.rect[7] = WORK  # and back
    w._capture(7)
    assert w._area_large and w._hand_area == (0, 24, 0, 0) and w.settings.margins == (0, 24, 0, 0)
    w.clear_area()
    assert w.profiles.margins_for(w.selected, large=True) is None and w.profiles.margins_for(w.selected) == (0, 85, 0, 0)


def test_the_area_set_on_a_window_not_enlarged_stays_in_margins(hidden_root, tmp_path, desk):
    desk.rect[7] = WORK  # maximised by the reader, say: nothing was enlarged
    w = Win(hidden_root, tmp_path)
    w._enlarge_first()
    w._area_chosen((0, 24, 320, 240), (320, 240))
    assert w.profiles.margins_for(w.selected) == (0, 24, 0, 0) and w.profiles.margins_for(w.selected, large=True) is None


class Batch(Win):
    _start_batch = A._start_batch
    _run_area = A._run_area
    _pace = A._pace

    def _go_busy(self):
        self.busy = True

    def _show_band(self):
        pass

    def _sync_stop(self):
        pass


def _batch_window(hidden_root, tmp_path):
    w = Batch(hidden_root, tmp_path)
    w.auto_var, w.model_var, w.lang_var = tk.BooleanVar(master=hidden_root), tk.StringVar(master=hidden_root), tk.StringVar(master=hidden_root)
    w._jobs = SimpleNamespace(put=lambda job: w.jobs.append(job))
    w.jobs = []
    w._own_hwnd = lambda: 99
    w.margins = []
    w._apply_found_margins = lambda starting=False: w.margins.append(starting)
    return w


def test_a_batch_in_the_window_leaves_the_viewer_as_the_reader_has_set_it(hidden_root, tmp_path, desk):
    w = _batch_window(hidden_root, tmp_path)
    w._start_batch(w.selected, 0, True)
    assert desk.enlarged == [] and len(w.jobs) == 1 and w.busy and True in w.margins  # no key, no new size: it starts


def test_a_batch_waits_for_a_window_being_enlarged_for_the_page_on_show(hidden_root, tmp_path, desk):
    w = _batch_window(hidden_root, tmp_path)
    w._enlarge_first()
    w._start_batch(w.selected, 0, True)
    assert w.jobs == [] and w.busy  # nothing can start meanwhile
    w.run_later()
    assert len(w.jobs) == 1


def test_start_shows_a_viewer_minimised_since_it_was_chosen_behind_taslation(hidden_root, tmp_path, unminimise):
    w = _batch_window(hidden_root, tmp_path)
    unminimise.minimised.add(7)
    w._start_batch(w.selected, 0, True)
    assert unminimise.unminimised == [(7, 99)] and len(w.jobs) == 1 and unminimise.enlarged == []


# ------------------------------------------------------------------ the profile and the settings of older versions
def test_what_older_versions_kept_about_full_screen_with_reading_mode_is_ignored(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"An Image Viewer": {"fullscreen_reading": True, "margins": [0, 85, 0, 0], "keys": {
        "next": "Right", "prev": "Left", "first": "Home", "fullscreen": "F10"}}, "default_keys": {"fullscreen": ""},
        "key_presets": {"Mine": {"next": "Down", "prev": "Up", "fullscreen": "F"}}}), encoding="utf-8")
    p = Profiles(path)
    settings = Settings(state_dir=tmp_path)
    assert own_keys(p, TITLE) == {"next": "Right", "prev": "Left"}  # (the full-screen key of old: no key goes)
    assert page_keys_for(p, settings, TITLE) == PageKeys("Right", "Left")
    assert p.user_presets() == {"Mine": PageKeys("Down", "Up")}
    assert p.margins_for(TITLE) == (0, 85, 0, 0) and p.margins_for(TITLE, large=True) is None
    assert not hasattr(p, "fullscreen_reading")


def test_the_full_screen_key_of_old_still_loads_and_what_is_unknown_is_left_out_by_name(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text('fullscreen_key = "F11"\nnext_page_key = "Right"\nprev_page_key = "Left"\n', encoding="utf-8")
    settings = Settings.load(path)
    assert settings.next_page_key == "Right" and not hasattr(settings, "fullscreen_key")
    assert settings.ignored_keys == ()  # a setting of old that was dropped is not named
    path.write_text('no_such_setting = 1\nnext_page_key = "Down"\n', encoding="utf-8")
    settings = Settings.load(path)
    assert settings.ignored_keys == ("no_such_setting",) and settings.next_page_key == "Down"
    path.write_text('next_page_key = \n', encoding="utf-8")  # a file that is no TOML still stops
    with pytest.raises(ConfigError):
        Settings.load(path)


# ------------------------------------------------------------------ the command line
def test_the_command_line_waits_for_the_enlarged_window_and_finds_the_size_it_took(tmp_path, monkeypatch):
    settings = Settings(state_dir=tmp_path)
    settings.settle_ms = 0
    frames = iter([_frame(10), _frame(100), _frame(100)])
    monkeypatch.setattr(capture_mod, "enlarge_window", lambda hwnd: Enlarged(hwnd, SMALL, WORK))
    monkeypatch.setattr(capture_mod, "capture_window", lambda hwnd, allow_screen_fallback=True: next(frames))
    monkeypatch.setattr(capture_mod, "window_rect", lambda hwnd: (0, 0, 1920, 1000))
    enlarged = enlarge_viewer(7, settings)
    assert enlarged.given == (0, 0, 1920, 1000) and next(frames, "all taken") == "all taken"
    monkeypatch.setattr(capture_mod, "enlarge_window", lambda hwnd: None)
    assert enlarge_viewer(7, settings) is None


def test_the_cli_says_a_fixed_window_once_and_restores_only_a_changed_one(tmp_path, monkeypatch, capsys):
    from taslation import capture

    settings = Settings(state_dir=tmp_path)
    monkeypatch.setattr(cli, "enlarge_viewer", lambda hwnd, s: Enlarged(hwnd, SMALL, SMALL))
    assert cli._enlarged(7, settings) is None
    assert capsys.readouterr().out == "the viewer's window keeps its size: it is read as it is\n"
    monkeypatch.setattr(cli, "enlarge_viewer", lambda hwnd, s: Enlarged(hwnd, SMALL, WORK))
    assert cli._enlarged(7, settings) == Enlarged(7, SMALL, WORK)

    restored, order = [], []
    monkeypatch.setattr(capture, "restore_window", lambda e: restored.append(e.hwnd) or order.append("restored"))
    monkeypatch.setattr(capture, "enable_dpi_awareness", lambda: None)
    monkeypatch.setattr(capture, "capture_window", lambda hwnd: order.append("captured") or _frame())
    monkeypatch.setattr(cli, "_notice_once", lambda s: None)
    monkeypatch.setattr(cli, "_pick_window", lambda window, wait=0.0: _win())
    monkeypatch.setattr(cli, "_print_result", lambda result, as_json: None)
    monkeypatch.setattr(cli, "build_pipeline", lambda *a, **k: SimpleNamespace(
        process=lambda image, progress=None: SimpleNamespace(image=image, error=""),
        release_translator=lambda: None, cache=None))
    import taslation.ui.preview as preview

    monkeypatch.setattr(preview, "show_preview", lambda image, title: None)
    args = SimpleNamespace(window="x", book=None, translator=None, json=False)
    assert cli.cmd_read(args, settings) == 0
    assert order == ["captured", "restored"] and restored == [7]  # read first, then put back

    ran = []

    class Reader:
        progress = SimpleNamespace(notes=[], proposals=[])

        def __init__(self, *a, **k):
            pass

        def finish(self):
            ran.append("finish")

        def run(self):
            ran.append("run")
            raise KeyboardInterrupt

        def stop(self):
            ran.append("stop")

    monkeypatch.setattr(batch_mod, "BatchReader", Reader)
    monkeypatch.setattr(cli, "_finish_at_enter", lambda reader: None)
    args = SimpleNamespace(window="x", wait=0, no_notes=False, book="B", series="S", translator=None, no_context=False,
                           max_pages=None, retranslate=False)
    assert cli.cmd_batch(args, settings) == 0
    assert ran == ["run", "stop"] and restored == [7]  # a batch touches no window of the viewer's


# ------------------------------------------------------------------ the batch and a covered viewer
def test_a_viewer_that_draws_nothing_behind_another_window_is_waited_for(tmp_path, monkeypatch):
    settings = Settings(state_dir=tmp_path)
    said = []
    reader = BatchReader(SimpleNamespace(), 1, settings, lambda p, result: said.append(p.message))
    blank = Image.new("RGB", (320, 240), "white")
    page = _frame(100)
    frames = iter([blank, blank, page])
    reader.wait_poll_s = 0
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "capture_window", lambda hwnd: next(frames))
    monkeypatch.setattr(batch_mod, "behind_others", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "frames_come", lambda hwnd: False)
    assert reader._capture() is page
    assert said == [Message("batch.waiting_behind"), Message("batch.viewer_draws_again")]
    monkeypatch.setattr(batch_mod, "capture_window", lambda hwnd: blank)
    monkeypatch.setattr(batch_mod, "behind_others", lambda hwnd: False)
    assert reader._capture() is blank  # a white page of a viewer nothing lies over is a page
