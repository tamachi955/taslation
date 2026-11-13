"""Frames from Windows.Graphics.Capture (`capture.wgc`), the viewer raised for a look, the viewer's window
enlarged and put back with no key.

The package is a stand-in everywhere but in the gated test at the end, which opens nothing: it reads a window of the
Windows image viewer if one is open, and writes nothing."""

from __future__ import annotations

from contextlib import contextmanager

import builtins
import os
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import batch as batch_mod
from taslation import capture as capture_mod
from taslation import cli
from taslation.batch import BatchReader
from taslation.cli import enlarge_viewer
from taslation.capture import wgc, windows
from taslation.capture.windows import Raised
from taslation.config import Settings
from taslation.pagekeys import PageKeys
from taslation.ui import viewers
from taslation.ui.app import App
from taslation.ui.live import BlackViewerMixin


class Control:
    """The package's control object: calls from another thread than the session's are mistakes."""

    def __init__(self, capture):
        self.capture = capture

    def is_finished(self):
        return self.capture.finished

    def wait(self):
        if self.capture.failure:
            raise RuntimeError(self.capture.failure)

    def stop(self):
        self.capture.finished = True
        self.capture.stops += 1


def stand_in(refuse=lambda options: False, frames=((4, 3),)):
    """A stand-in of `windows_capture.WindowsCapture`; *refuse*: which options its start does not take."""

    class Capture:
        made: list = []

        def __init__(self, **options):
            self.options, self.handlers = options, {}
            self.finished, self.failure, self.stops = False, "", 0
            Capture.made.append(self)

        def event(self, handler):
            self.handlers[handler.__name__] = handler

        def start_free_threaded(self):
            if refuse(self.options):
                raise Exception("not on this system")
            for size in frames:
                self.send(size)
            return Control(self)

        def send(self, size, value=7):
            width, height = size
            buffer = np.full((height, width, 4), value, np.uint8)
            self.handlers["on_frame_arrived"](SimpleNamespace(frame_buffer=buffer), None)

    return Capture


@pytest.fixture
def api(monkeypatch):
    wgc.close(wait=True)
    monkeypatch.setattr(wgc, "_api", None)
    monkeypatch.setattr(wgc, "_why", "")

    def use(capture):
        monkeypatch.setattr(wgc, "_load", lambda: capture)
        return capture

    yield use
    wgc.close(wait=True)


def wait_until(test, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not test() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert test()


# ------------------------------------------------------------------ the session
def test_the_session_takes_the_window_by_handle_and_keeps_the_newest_frame(api):
    capture = api(stand_in())
    frame = wgc.latest(0x51)
    assert frame.size == (4, 3)
    made = capture.made[0]
    assert made.options["window_hwnd"] == 0x51 and "window_name" not in made.options
    assert made.options["cursor_capture"] is False and made.options["draw_border"] is False
    made.send((4, 3), 200)
    newest = wgc.latest(0x51)
    assert newest.seq == 2 and newest.bgra.max() == 200 and len(capture.made) == 1  # (no second session)


def test_a_frame_is_a_copy_of_its_own(api):
    capture = api(stand_in())
    wgc.latest(1)
    buffer = np.full((3, 4, 4), 9, np.uint8)
    capture.made[0].handlers["on_frame_arrived"](SimpleNamespace(frame_buffer=buffer), None)
    buffer[:] = 0
    assert wgc.latest(1).bgra.min() == 9


def test_no_frame_yet_is_waited_for_at_the_start_only(api):
    capture = api(stand_in(frames=()))
    started = time.monotonic()
    assert wgc.latest(2, timeout=0.05) is None
    assert time.monotonic() - started >= 0.04
    time.sleep(0.06)
    started = time.monotonic()
    assert wgc.latest(2, timeout=0.05) is None
    assert time.monotonic() - started < 0.04  # an unchanged window is not waited for at every look
    capture.made[0].send((4, 3))
    assert wgc.latest(2).size == (4, 3)


def test_a_title_that_changes_touches_nothing(api):
    """(The session is by handle: nothing here even asks for the title.)"""
    capture = api(stand_in())
    for _ in range(3):
        assert wgc.latest(3) is not None
    assert len(capture.made) == 1


def test_another_viewer_closes_the_session(api):
    capture = api(stand_in())
    wgc.latest(4)
    first = capture.made[0]
    wgc.latest(5)
    wait_until(lambda: first.stops == 1)
    assert [c.options["window_hwnd"] for c in capture.made] == [4, 5]
    assert wgc.live(5) and not wgc.live(4)
    wgc.close(5)
    wait_until(lambda: capture.made[1].stops == 1)
    assert not wgc.live(5)


def test_a_session_that_ended_comes_back_after_a_while(api, monkeypatch):
    capture = api(stand_in())
    monkeypatch.setattr(wgc, "CHECK_S", 0.01)
    assert wgc.latest(6) is not None
    capture.made[0].handlers["on_closed"]()
    capture.made[0].finished = True
    wait_until(lambda: not wgc.live(6))
    assert wgc.latest(6) is None  # (not at every look)
    assert len(capture.made) == 1
    monkeypatch.setattr(wgc, "RETRY_S", 0.0)
    assert wgc.latest(6) is not None and len(capture.made) == 2


def test_the_system_refusing_the_border_keeps_the_capture_going(api):
    capture = api(stand_in(refuse=lambda options: "draw_border" in options))
    assert wgc.latest(7) is not None
    assert "draw_border" not in capture.made[-1].options and len(capture.made) == 3


def test_a_window_that_cannot_be_captured_gives_no_frame(api):
    api(stand_in(refuse=lambda options: True))
    assert wgc.latest(8) is None and not wgc.live(8)


def test_a_missing_package_is_said_and_gives_no_frame(monkeypatch):
    wgc.close(wait=True)
    monkeypatch.setattr(wgc, "_session", None)
    monkeypatch.setattr(wgc, "_api", None)
    monkeypatch.setattr(wgc, "_why", "")
    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "windows_capture":
            raise ImportError("No module", name="windows_capture")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    monkeypatch.setitem(sys.modules, "windows_capture", None)
    assert wgc.latest(9) is None
    assert wgc.route() == "PrintWindow (the windows-capture package is not installed)"


def test_a_package_that_will_not_load_is_said(monkeypatch):
    monkeypatch.setattr(wgc, "_api", None)
    monkeypatch.setattr(wgc, "_why", "")
    real = builtins.__import__

    def broken(name, *args, **kwargs):
        if name == "windows_capture":
            raise OSError("a DLL is missing")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    monkeypatch.delitem(sys.modules, "windows_capture", raising=False)
    assert "does not load: a DLL is missing" in wgc.route()


def test_the_doctor_says_the_route(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wgc, "route", lambda: "PrintWindow (why)")
    import taslation.capture as capture

    monkeypatch.setattr(capture, "capture_route", wgc.route)
    settings = Settings(state_dir=tmp_path, models_dir=tmp_path)
    cli.cmd_doctor(SimpleNamespace(config=None), settings)
    assert "Capture: PrintWindow (why)" in capsys.readouterr().out


# ------------------------------------------------------------------ the client area
def test_the_client_area_of_the_measured_window():
    """The numbers of the Windows image viewer: its frame is the extended frame bounds, 1 pixel wider than its client
    area on either side; the 48 rows of its own title bar lie inside the client area (`caption_rows`)."""
    bounds, client = (111, 104, 1537, 850), (112, 104, 1424, 745)
    assert wgc.crop_box((1426, 746), bounds, client) == (1, 0, 1425, 745)
    assert wgc.crop_box((1426, 746), bounds, (112, 152, 1424, 697)) == (1, 48, 1425, 745)
    assert windows.title_band((112, 104, 1536, 152), client) == 48


def test_a_classic_title_bar_lies_outside_the_client_area():
    assert wgc.crop_box((1000, 700), (100, 100, 1100, 800), (108, 131, 984, 661)) == (8, 31, 992, 692)


def test_a_maximised_window_takes_what_is_inside_the_bounds():
    assert wgc.crop_box((1920, 1032), (0, 0, 1920, 1032), (-8, -8, 1936, 1048)) == (0, 0, 1920, 1032)


def test_a_frame_of_another_size_is_a_resize_on_its_way():
    assert wgc.crop_box((1426, 746), (0, 0, 1906, 1025), (1, 0, 1904, 1024)) is None
    assert wgc.crop_box((1906, 1024), (0, 0, 1906, 1025), None) == (0, 0, 1906, 1024)  # (rounding)


def test_a_child_that_is_no_title_bar_is_not_cut():
    client = (0, 0, 1000, 800)
    assert windows.title_band((0, 40, 1000, 90), client) == 0  # not along the top
    assert windows.title_band((0, 0, 200, 40), client) == 0  # narrow
    assert windows.title_band((0, 0, 1000, 400), client) == 0  # high


def test_the_image_has_the_box_and_the_right_colours():
    bgra = np.zeros((4, 5, 4), np.uint8)
    bgra[..., 0], bgra[..., 1], bgra[..., 2] = 10, 20, 30
    image = wgc.Frame(bgra, 1).image((1, 1, 4, 3))
    assert image.size == (3, 2) and image.mode == "RGB" and image.getpixel((0, 0)) == (30, 20, 10)


def test_a_resize_is_waited_for(api, monkeypatch):
    capture = api(stand_in(frames=((4, 3),)))
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsWindow=lambda h: True, IsIconic=lambda h: False))
    monkeypatch.setattr(windows, "_frame_bounds", lambda h: (0, 0, 8, 6))
    monkeypatch.setattr(windows, "_client_box", lambda h: (0, 0, 8, 6))
    threading.Timer(0.05, lambda: capture.made[0].send((8, 6))).start()
    assert windows._compositor_frame(1, True).size == (8, 6)


def test_a_frame_that_never_fits_is_waited_for_once_then_printwindow(api, monkeypatch):
    api(stand_in())
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsWindow=lambda h: True, IsIconic=lambda h: False))
    monkeypatch.setattr(windows, "_frame_bounds", lambda h: (0, 0, 8, 6))
    monkeypatch.setattr(windows, "_client_box", lambda h: (0, 0, 8, 6))
    monkeypatch.setattr(windows, "RESIZE_WAIT_S", 0.05)
    started = time.monotonic()
    assert windows._compositor_frame(1, True) is None
    assert time.monotonic() - started >= 0.04
    started = time.monotonic()
    assert windows._compositor_frame(1, True) is None
    assert time.monotonic() - started < 0.04


def test_a_minimised_window_is_left_to_the_old_route(api, monkeypatch):
    capture = api(stand_in())
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsIconic=lambda h: True))
    assert windows._compositor_frame(1, True) is None and capture.made == []


# ------------------------------------------------------------------ one key, one window
@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_a_browser_keeps_its_target_and_a_viewer_with_children_gets_its_largest_child(monkeypatch):
    rects = {1: (0, 0, 100, 40), 2: (0, 0, 800, 600), 3: (0, 0, 0, 0), 4: (0, 0, 800, 600)}
    shown = {1, 2, 3, 4}
    monkeypatch.setattr(windows, "input_target", lambda h: h)
    classes = {}
    monkeypatch.setattr(windows, "_class_name", lambda h: classes.get(h, "SomeViewer"))
    monkeypatch.setattr(windows, "_window_rect", lambda h: rects[h])

    def enumerate_children(parent, callback, _lparam):
        for child in (1, 2, 3, 4):
            if not callback(child, 0):
                break

    monkeypatch.setattr(windows, "user32", SimpleNamespace(
        EnumChildWindows=enumerate_children, IsWindowVisible=lambda h: h in shown, IsWindowEnabled=lambda h: True))
    monkeypatch.setattr(windows, "WNDENUMPROC", lambda f: f)
    assert windows.key_target(99) == 4  # the deepest of the largest
    classes[3] = windows.KEY_CHILD_CLASS
    assert windows.key_target(99) == 3  # WinUI's input site, though it is not shown and has no size
    classes.clear()
    shown.discard(4)
    assert windows.key_target(99) == 2
    shown.clear()
    assert windows.key_target(99) == 99
    classes[99] = "Chrome_WidgetWin_1"
    shown.update(rects)
    assert windows.key_target(99) == 99  # a browser's window without a render widget is its own target
    monkeypatch.setattr(windows, "input_target", lambda h: 5)
    assert windows.key_target(99) == 5


# ------------------------------------------------------------------ raised for a moment
class Desk:
    """user32 as `raise_window` uses it."""

    def __init__(self, above=70, topmost=()):
        self.above, self.topmost, self.calls = above, set(topmost), []

    IsWindow = staticmethod(lambda h: True)
    IsIconic = staticmethod(lambda h: False)
    GetAncestor = staticmethod(lambda h, how: h)

    def GetWindowLongW(self, h, index):
        return windows.WS_EX_TOPMOST if h in self.topmost else 0

    IsWindowVisible = staticmethod(lambda h: h not in (60,))

    def GetWindow(self, h, how):
        if how == windows.GW_OWNER:
            return 5 if h == 61 else 0
        return {5: self.above, 60: 61, 61: 70}.get(h, 0)

    def SetWindowPos(self, h, after, x, y, w, h2, flags):
        self.calls.append((h, after, flags))
        return True


@pytest.fixture
def desk(monkeypatch):
    desk = Desk()
    monkeypatch.setattr(windows, "user32", desk)
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "_raised", {})
    return desk


@contextmanager
def raised_window(hwnd):
    raised = windows.raise_window(hwnd)
    try:
        yield raised
    finally:
        if raised is not None:
            windows.lower_window(raised)


def test_raising_touches_the_order_of_the_windows_alone_and_puts_the_window_back(desk):
    with raised_window(5) as raised:
        assert raised == Raised(5, 70)
        assert desk.calls == [(5, windows.HWND_TOPMOST, windows.SWP_STAY)]
        assert windows.SWP_STAY & windows.SWP_NOACTIVATE
    assert desk.calls[1:] == [(5, windows.HWND_NOTOPMOST, windows.SWP_STAY), (5, 70, windows.SWP_STAY)]
    assert windows._raised == {}


def test_the_window_goes_back_whatever_happens_meanwhile(desk):
    with pytest.raises(RuntimeError):
        with raised_window(5):
            raise RuntimeError("no")
    assert desk.calls[-2][1] == windows.HWND_NOTOPMOST


def test_nothing_stays_topmost_at_exit(desk):
    windows.raise_window(5)
    windows._lower_all()
    assert (5, windows.HWND_NOTOPMOST, windows.SWP_STAY) in desk.calls and windows._raised == {}


def test_a_window_under_a_topmost_one_is_not_put_under_it(desk):
    desk.topmost.add(70)  # (under a topmost window it would become topmost itself)
    with raised_window(5):
        pass
    assert [c[1] for c in desk.calls] == [windows.HWND_TOPMOST, windows.HWND_NOTOPMOST]


def test_the_window_goes_back_under_the_nearest_window_that_is_not_its_own(desk):
    desk.above = 60  # a hidden window, then one it owns (they move up with it)
    with raised_window(5) as raised:
        assert raised.above == 70


def test_a_window_topmost_of_its_own_is_left_alone(desk):
    desk.topmost.add(5)
    with raised_window(5) as raised:
        assert raised is None
    assert desk.calls == []


def _reader(monkeypatch, tmp_path, frames_come=False):
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "behind_others", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "frames_come", lambda hwnd: frames_come)
    return BatchReader(SimpleNamespace(), 1, Settings(state_dir=tmp_path, settle_ms=1))


def test_a_blank_page_of_a_viewer_whose_frames_come_is_a_page(monkeypatch, tmp_path):
    r = _reader(monkeypatch, tmp_path, frames_come=True)
    blank = Image.new("RGB", (400, 600), "white")
    monkeypatch.setattr(batch_mod, "capture_window", lambda hwnd, **_: blank)
    assert r._capture_once() is blank


def test_a_blank_frame_with_no_frames_coming_is_no_page_and_the_viewer_is_never_raised(monkeypatch, tmp_path):
    r = _reader(monkeypatch, tmp_path)
    blank = Image.new("RGB", (400, 600), "white")
    monkeypatch.setattr(batch_mod, "capture_window", lambda hwnd, **_: blank)
    monkeypatch.setattr(windows, "raise_window", lambda hwnd: pytest.fail("the batch raises no window"))
    assert r._capture_once() is None


# ------------------------------------------------------------------ the window: raised for a look
class Live(BlackViewerMixin):
    _raise_viewer = App._raise_viewer
    _lower_viewer = App._lower_viewer
    _raise_helped = App._raise_helped
    _raise_for_key = App._raise_for_key
    _draws_covered = App._draws_covered
    _note_covered = App._note_covered
    _blank_behind = App._blank_behind
    _resizing = App._resizing
    _window_size = App._window_size
    _blank_lasted = App._blank_lasted

    def __init__(self):
        self.settings = Settings(page_turn_wait_ms=100, settle_ms=10)
        self.jobs, self.said = [], []

    def after(self, ms, job):
        self.jobs.append((ms, job))
        return "job"

    def after_cancel(self, job):
        self.jobs.clear()

    def say(self, text, **params):
        self.said.append(text)


@pytest.fixture
def live_desk(monkeypatch):
    from taslation.ui import live

    state = SimpleNamespace(behind=True, raised=[], lowered=[], come=False, rect=(0, 0, 800, 600))
    monkeypatch.setattr(live, "behind_others", lambda hwnd: state.behind)
    monkeypatch.setattr(live, "raise_window", lambda hwnd: state.raised.append(hwnd) or Raised(hwnd, 0))
    monkeypatch.setattr(live, "lower_window", state.lowered.append)
    monkeypatch.setattr(live, "frames_come", lambda hwnd: state.come)
    monkeypatch.setattr(live, "window_rect", lambda hwnd: state.rect)
    return state


def test_the_window_raises_the_viewer_once_and_a_timer_lowers_it(live_desk):
    w = Live()
    assert w._raise_viewer(5) and not w._raise_viewer(5)
    assert live_desk.raised == [5]
    ms, job = w.jobs[0]
    assert ms == 110
    job()
    assert live_desk.lowered == [Raised(5, 0)] and w._raised is None


def test_a_viewer_in_front_is_not_raised(live_desk):
    live_desk.behind = False
    assert not Live()._raise_viewer(5) and live_desk.raised == []


def test_once_it_helped_every_key_raises_first_and_it_is_said_once(live_desk):
    w = Live()
    w._raise_for_key(5)
    assert live_desk.raised == []
    w._raise_helped(5)
    w._raise_helped(5)
    assert len(w.said) == 1
    w._raise_for_key(5)
    assert live_desk.raised == [5]


def test_a_browser_is_raised_before_a_key_only_while_an_opaque_window_covers_it(live_desk, monkeypatch):
    """Under TASlation's own window at WINDOW_ALPHA a browser goes on drawing: raised at every key it came over the
    page for page_turn_wait_ms + settle_ms for nothing. Behind an opaque window it may have stopped drawing."""
    covered = [False]
    from taslation.ui import live

    monkeypatch.setattr(live, "window_class", lambda _h: windows.BROWSER_CLASSES[0])
    monkeypatch.setattr(live, "covered_by_opaque", lambda _h: covered[0])
    w = Live()
    w._raise_for_key(5)
    assert live_desk.raised == [] and w._draws_covered(5) is True
    w._note_covered(5, False)  # (nothing is kept for a browser: the published rule decides)
    assert getattr(w, "_covered_seen", {}) == {} and w._draws_covered(5) is True
    covered[0] = True
    w._raise_for_key(5)
    assert live_desk.raised == [5]


def test_a_blank_frame_of_the_window_is_looked_at_raised_once_a_spell(live_desk):
    w = Live()
    w.settings.page_turn_wait_ms = 0
    assert w._blank_behind(5) and live_desk.raised == []  # (no picture yet; it has only just gone blank)
    assert w._blank_behind(5) and live_desk.raised == [5]  # it has stayed so
    w._lower_viewer()
    assert w._blank_behind(5)  # nothing comes: a viewer that does not draw
    live_desk.come = True
    assert not w._blank_behind(5)  # a blank page
    assert live_desk.raised == [5]


# ------------------------------------------------------------------ the viewer's window enlarged, no key
SMALL, MONITOR, WORK = (100, 100, 900, 700), (0, 0, 1920, 1080), (0, 0, 1920, 1032)


class Screen:
    """The window as `enlarge_window` and `restore_window` see it, and every key that would go to it (none may)."""

    def __init__(self):
        self.rect, self.pressed, self.moved, self.zoomed = SMALL, [], [], False

    def press(self, hwnd, key, *_a, **_k):
        self.pressed.append(key)
        return True

    def move(self, hwnd, rect):
        self.moved.append(rect)
        self.rect = rect
        return True


@pytest.fixture
def screen(monkeypatch):
    s = Screen()
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsZoomed=lambda hwnd: s.zoomed))
    monkeypatch.setattr(windows, "window_shown", lambda hwnd: True)
    monkeypatch.setattr(windows, "monitor_rect", lambda hwnd: MONITOR)
    monkeypatch.setattr(windows, "work_area", lambda hwnd: WORK)
    monkeypatch.setattr(windows, "window_rect", lambda hwnd: s.rect)
    monkeypatch.setattr(windows, "move_window", s.move)
    for name in ("press_briefly", "press_key", "post_key"):
        monkeypatch.setattr(windows, name, s.press)
    return s


def test_the_window_is_enlarged_to_the_work_area_and_put_back_with_no_key(screen):
    enlarged = windows.enlarge_window(5)
    assert enlarged.before == SMALL and enlarged.given == WORK and screen.rect == WORK
    assert windows.enlarge_window(5) is None  # as large already
    assert windows.restore_window(enlarged) and screen.rect == SMALL
    assert screen.pressed == []


def test_a_window_the_reader_resized_or_maximised_is_left_as_it_is(screen):
    enlarged = windows.enlarge_window(5)
    screen.rect = (0, 0, 800, 700)  # the reader's doing
    assert not windows.restore_window(enlarged) and screen.rect == (0, 0, 800, 700)
    screen.rect, screen.zoomed = SMALL, True
    assert windows.enlarge_window(5) is None and screen.moved == [WORK]
    assert screen.pressed == []


class Choosing:
    """The parts of the App that enlarge the viewer's window before the first read and put it back."""

    _enlarge_first = App._enlarge_first
    _enlarge_wait = App._enlarge_wait
    _enlarge_done = App._enlarge_done
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    _restore_enlarged = App._restore_enlarged
    _keep_enlarged = App._keep_enlarged  # (kept for the next start: tests/test_enlarge_recovery.py)
    _viewer_left = App._viewer_left

    def __init__(self):
        self.settings = Settings(settle_ms=1)
        self.selected = SimpleNamespace(hwnd=5)
        self.jobs, self.said, self.then = [], [], []
        self.reading = True
        self.canvas = SimpleNamespace(set_note=lambda *a: None)
        self._enlarging = self._enlarge_asked = self._enlarged = None

    _capture = lambda self, hwnd: Image.new("RGB", (9, 9))
    _page_keys = lambda self, win=None: PageKeys()
    _sync_area = lambda self: None
    _resize_begins = lambda self: None
    _forget_page_area = lambda self: None
    _apply_found_margins = lambda self: None
    _look_afresh = lambda self, frame=None, thumb=None: None
    _lower_viewer = lambda self: None
    focus_get = lambda self: None

    def after(self, ms, job):
        self.jobs.append(job)

    def say(self, text, **params):
        self.said.append(text.format(**params))

    def run(self, steps=40):
        while self.jobs and steps:
            self.jobs.pop(0)()
            steps -= 1


@pytest.fixture
def choosing(screen, monkeypatch):
    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: True)
    monkeypatch.setattr(viewers, "window_rect", lambda hwnd: screen.rect)
    monkeypatch.setattr(viewers, "enlarge_window", windows.enlarge_window)
    monkeypatch.setattr(viewers, "restore_window", windows.restore_window)
    monkeypatch.setattr(viewers, "stop_capture", lambda: None)
    return screen


def test_once_per_selection_before_the_first_read_and_no_key(choosing):
    w = Choosing()
    assert w._enlarge_first(lambda: w.then.append(1)) is False
    w.run()
    assert w.then == [1] and w._enlarged.given == WORK and w.said == [viewers.ENLARGED]
    assert w._enlarge_first() is True and choosing.moved == [WORK]
    assert choosing.pressed == []


def test_at_a_change_of_viewer_the_window_goes_back_with_no_key(choosing):
    w = Choosing()
    w._enlarge_first()
    w.run()
    w._viewer_left()
    assert choosing.rect == SMALL and w._enlarged is None and choosing.pressed == []


def test_a_window_the_reader_made_smaller_stays_so_at_the_end(choosing):
    w = Choosing()
    w._enlarge_first()
    w.run()
    choosing.rect = (0, 0, 700, 600)
    w._restore_enlarged()
    assert choosing.rect == (0, 0, 700, 600) and choosing.pressed == []


def test_a_maximised_viewer_is_read_as_it_is(choosing):
    choosing.zoomed = True
    w = Choosing()
    assert w._enlarge_first() is True and w._enlarged is None and w.said == [] and choosing.pressed == []


def test_the_command_line_enlarges_and_presses_nothing(screen, monkeypatch):
    monkeypatch.setattr(capture_mod, "enlarge_window", windows.enlarge_window)
    monkeypatch.setattr(capture_mod, "capture_window", lambda hwnd, **_: Image.new("RGB", (9, 9)))
    monkeypatch.setattr(capture_mod, "window_rect", lambda hwnd: screen.rect)
    enlarged = enlarge_viewer(5, SimpleNamespace(settle_ms=0))
    assert enlarged.given == WORK and screen.pressed == []
    screen.zoomed, screen.rect = True, SMALL
    assert enlarge_viewer(5, SimpleNamespace(settle_ms=0)) is None and screen.pressed == []


class Foreground:
    """Who has the foreground, as Windows says: *refusing*, so many requests for it go unanswered."""

    def __init__(self, monkeypatch, refusing=0):
        self.front, self.refusing, self.calls = 9, refusing, []
        monkeypatch.setattr(windows, "user32", SimpleNamespace(GetForegroundWindow=lambda: self.front))
        monkeypatch.setattr(windows, "give_foreground", self.give)
        monkeypatch.setattr(windows, "press_key", self.press)
        monkeypatch.setattr(windows, "_redrawn_after_focus", lambda _hwnd: None)
        monkeypatch.setattr(windows, "FOREGROUND_STEP_S", 0.0)
        monkeypatch.setattr(windows, "window_class", lambda _hwnd: "Other")

    def give(self, hwnd):
        self.calls.append(("give", hwnd))
        if self.refusing and hwnd == 5:
            self.refusing -= 1
            return False
        self.front = hwnd
        return True

    def press(self, hwnd, key):
        assert self.front == hwnd  # never a key for a window that has not got the foreground
        self.calls.append(("press", key))
        return True


def test_the_hand_back_is_no_alt_tap(monkeypatch):
    f = Foreground(monkeypatch)
    assert windows.press_briefly(5, "F11")
    assert f.calls == [("give", 5), ("press", "F11"), ("give", 9)]


def test_a_foreground_refused_once_is_asked_for_again_and_the_key_waits_for_it(monkeypatch):
    f = Foreground(monkeypatch, refusing=1)
    assert windows.press_briefly(5, "F11")
    assert f.calls == [("give", 5), ("give", 5), ("press", "F11"), ("give", 9)]


def test_a_foreground_that_never_comes_presses_nothing_and_says_so(monkeypatch):
    f = Foreground(monkeypatch, refusing=10 ** 9)
    monkeypatch.setattr(windows, "FOREGROUND_WAIT_S", 0.01)
    assert not windows.press_briefly(5, "F11")
    assert ("press", "F11") not in f.calls and f.calls[0] == ("give", 5) and f.calls[-1] == ("give", 9)


def test_the_hand_back_follows_a_refused_press(monkeypatch):
    f = Foreground(monkeypatch)
    monkeypatch.setattr(windows, "press_key", lambda hwnd, key: False)
    assert not windows.press_briefly(5, "F11")
    assert f.calls == [("give", 5), ("give", 9)]


def test_keys_gathered_go_in_one_handover_in_order(monkeypatch):
    f = Foreground(monkeypatch)
    monkeypatch.setattr(windows, "KEY_SETTLE_S", 0.0)
    assert windows.press_briefly(5, ["Left", "Left", "Right"])
    assert f.calls == [("give", 5), ("press", "Left"), ("press", "Left"), ("press", "Right"), ("give", 9)]


def test_a_key_refused_in_a_handover_ends_it(monkeypatch):
    f = Foreground(monkeypatch)
    monkeypatch.setattr(windows, "KEY_SETTLE_S", 0.0)
    keys = iter([True, False, True])
    monkeypatch.setattr(windows, "press_key", lambda hwnd, key: f.calls.append(("press", key)) or next(keys))
    assert windows.press_briefly(5, ["Left", "Right", "Up"])  # the first was delivered
    assert f.calls == [("give", 5), ("press", "Left"), ("press", "Right"), ("give", 9)]
    assert not windows.press_briefly(5, [])  # no key: nothing at all


def test_a_window_with_the_foreground_keeps_it(monkeypatch):
    f = Foreground(monkeypatch)
    f.front = 5
    assert windows.press_briefly(5, "F11")
    assert f.calls == [("give", 5), ("press", "F11")]


# ------------------------------------------------------------------ the real thing
@pytest.mark.skipif(os.environ.get("TASLATION_REALDATA") != "1" or sys.platform != "win32",
                    reason="needs TASLATION_REALDATA=1 and a window of the Windows image viewer")
def test_a_real_window_of_the_image_viewer():
    from taslation.capture import capture_window, enable_dpi_awareness, list_windows

    enable_dpi_awareness()
    found = [w for w in list_windows() if w.class_name == "WinUIDesktopWin32WindowClass"]
    if not found:
        pytest.skip("no window of the image viewer is open")
    hwnd = found[0].hwnd
    wgc.close(wait=True)
    try:
        image = capture_window(hwnd)
        if wgc.route() != wgc.ROUTE:
            pytest.skip("the package is not installed")
        assert wgc.live(hwnd)
        x, y, width, height = windows.client_rect_on_screen(hwnd)
        rows = windows.caption_rows(hwnd)
        assert image.size == (width, height - rows) and rows > 0
    finally:
        wgc.close(wait=True)

