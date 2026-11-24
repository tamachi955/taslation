"""Frames from Windows.Graphics.Capture (`capture.wgc`), the viewer raised for a look, a viewer's window a 1.0.1
session left enlarged put back with no key (`capture.restore_window`; the start's put-back:
`tests/test_enlarge_recovery.py`).

The package is a stand-in everywhere but in the gated test at the end, which opens nothing: it reads a window of the
Windows image viewer if one is open, and writes nothing."""

from __future__ import annotations

from contextlib import contextmanager

import builtins
import os
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

from taslation import cli
from taslation.capture import wgc, windows
from taslation.capture.windows import Raised
from taslation.config import Settings
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


def test_listeners_are_told_of_every_frame_and_a_peek_starts_nothing(api):
    capture = api(stand_in())
    assert wgc.peek(0x52) is None and capture.made == []  # (no session: none started)
    told = []

    def listener(hwnd, seq):
        told.append((hwnd, seq))

    def broken(hwnd, seq):
        raise RuntimeError("a listener's fault")

    wgc.add_listener(broken)
    wgc.add_listener(listener)
    try:
        wgc.latest(0x52)
        capture.made[0].send((4, 3), 9)
        assert told == [(0x52, 1), (0x52, 2)]  # (the broken one stopped nothing)
        assert wgc.peek(0x52).seq == 2 and wgc.peek(0x53) is None
    finally:
        wgc.remove_listener(listener)
        wgc.remove_listener(broken)


def test_a_new_update_interval_starts_the_session_over_with_it(api):
    capture = api(stand_in())
    try:
        wgc.latest(0x54)
        assert capture.made[0].options["minimum_update_interval"] == wgc.MIN_UPDATE_MS
        assert wgc.set_update_ms(wgc.FAST_UPDATE_MS) and wgc.update_ms() == wgc.FAST_UPDATE_MS
        wait_until(lambda: len(capture.made) == 2)
        assert capture.made[1].options["minimum_update_interval"] == wgc.FAST_UPDATE_MS
        assert not wgc.set_update_ms(wgc.FAST_UPDATE_MS)  # (as it is: nothing started over)
        assert wgc.latest(0x54).seq >= 2  # (the count goes on)
    finally:
        wgc.set_update_ms(wgc.MIN_UPDATE_MS)


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


@pytest.fixture
def window(monkeypatch):
    """A window whose bounds (and client area) the test sets; `restart`'s record of the size starts empty."""
    state = SimpleNamespace(bounds=(0, 0, 8, 6))
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsWindow=lambda h: True, IsIconic=lambda h: False))
    monkeypatch.setattr(windows, "_frame_bounds", lambda h: state.bounds)
    monkeypatch.setattr(windows, "_client_box", lambda h: (0, 0, state.bounds[2], state.bounds[3]))
    monkeypatch.setattr(wgc, "_restarted", None)
    return state


def test_a_resized_window_starts_the_session_over_and_its_count_goes_on(api, window):
    """The package drops a resized window's first frame of the new size, and a window that draws nothing more gives
    none: a new session's first frame is the window as it is."""
    sizes = [(8, 6)]  # what a session's start sends: the window as it is
    capture = api(stand_in(frames=sizes))
    assert windows._compositor_frame(1, True).size == (8, 6)
    capture.made[0].send((8, 6))
    assert wgc.count(1) == 2
    window.bounds, sizes[:] = (0, 0, 12, 9), [(12, 9)]  # resized: the session's frame is of the old size still
    started = time.monotonic()
    assert windows._compositor_frame(1, True).size == (12, 9) and time.monotonic() - started < 0.5
    assert len(capture.made) == 2 and wgc.count(1) == 3  # (a count never goes back: the window's looks go by it)
    wait_until(lambda: capture.made[0].stops == 1)
    assert windows._compositor_frame(1, True).size == (12, 9) and len(capture.made) == 2  # (no other start)


def test_a_frame_that_never_fits_starts_the_session_over_once_then_printwindow(api, window):
    capture = api(stand_in())  # frames of (4, 3), whatever the window's size
    started = time.monotonic()
    assert windows._compositor_frame(1, True) is None and len(capture.made) == 2
    assert windows._compositor_frame(1, True) is None and len(capture.made) == 2  # once for this size
    assert time.monotonic() - started < 0.5  # (no wait for a frame that does not come)
    window.bounds = (0, 0, 10, 7)  # another size: started over once more
    assert windows._compositor_frame(1, True) is None and len(capture.made) == 3


def test_a_minimised_window_is_left_to_the_old_route(api, monkeypatch):
    capture = api(stand_in())
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsIconic=lambda h: True))
    assert windows._compositor_frame(1, True) is None and capture.made == []


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


# ------------------------------------------------------------------ the window: raised for a look
class Live(BlackViewerMixin):
    _raise_viewer = App._raise_viewer
    _lower_viewer = App._lower_viewer
    _draws_covered = App._draws_covered
    _note_covered = App._note_covered
    _blank_behind = App._blank_behind
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


def test_a_browser_draws_covered_only_while_no_opaque_window_covers_it(live_desk, monkeypatch):
    """A browser follows the published rule: it goes on drawing under windows that let what lies under them show, and
    may stop under an opaque one. Nothing is kept for it; asking raises nothing."""
    covered = [False]
    from taslation.ui import live

    monkeypatch.setattr(live, "window_class", lambda _h: windows.BROWSER_CLASSES[0])
    monkeypatch.setattr(live, "covered_by_opaque", lambda _h: covered[0])
    w = Live()
    assert w._draws_covered(5) is True
    w._note_covered(5, False)  # (nothing is kept for a browser: the published rule decides)
    assert getattr(w, "_covered_seen", {}) == {} and w._draws_covered(5) is True
    covered[0] = True
    assert w._draws_covered(5) is False and live_desk.raised == []
    assert w.said == []


def test_another_viewer_that_draws_nothing_covered_is_kept_so_and_the_reader_is_told_once(live_desk, monkeypatch):
    from taslation.ui import live

    monkeypatch.setattr(live, "window_class", lambda _h: "ViewerClass")
    w = Live()
    assert w._draws_covered(5) is None  # (not known yet)
    w._note_covered(5, False)
    w._note_covered(5, False)
    assert w._draws_covered(5) is False and len(w.said) == 1
    w._note_covered(5, True)
    assert w._draws_covered(5) is True and live_desk.raised == []


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


# ------------------------------------------------------------------ a window 1.0.1 left enlarged, put back, no key
SMALL, WORK = (100, 100, 900, 700), (0, 0, 1920, 1032)


class Screen:
    """The window as `restore_window` sees it."""

    def __init__(self):
        self.rect, self.moved, self.zoomed = WORK, [], False

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
    monkeypatch.setattr(windows, "window_rect", lambda hwnd: s.rect)
    monkeypatch.setattr(windows, "move_window", s.move)
    return s


def test_a_window_left_enlarged_is_put_back_and_one_the_reader_resized_or_maximised_is_left_as_it_is(screen):
    enlarged = windows.Enlarged(5, SMALL, WORK)
    assert windows.restore_window(enlarged) and screen.rect == SMALL
    screen.rect = (0, 0, 800, 700)  # the reader's doing
    assert not windows.restore_window(enlarged) and screen.rect == (0, 0, 800, 700)
    screen.rect, screen.zoomed = WORK, True
    assert not windows.restore_window(enlarged) and screen.moved == [SMALL]


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
