"""A viewer's window chosen while it is minimised: shown again as it was, with no activation, no key and no change of
the foreground, put directly behind TASlation's window; a browser window minimised later is waited for with a line of
its own and not restored again by itself. Windows' calls are on a fake."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from taslation import i18n
from taslation.capture import windows
from taslation.capture.windows import SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, unminimise_window
from taslation.ui import app as app_mod
from taslation.ui import live, viewers
from taslation.ui.constants import BROWSER_MINIMISED

OWN = 99  # TASlation's own top-level window
VIEWER = 7


class User32:
    """Only what showing a window again may call: anything that would activate a window, take the foreground or
    press a key (SetForegroundWindow, BringWindowToTop, SendInput, ...) is not here, and fails."""

    def __init__(self, iconic=True, exists=True, topmost_own=False, restores=True):
        self.iconic, self.exists, self.topmost_own, self.restores = iconic, exists, topmost_own, restores
        self.shown: list = []
        self.placed: list = []

    def IsWindow(self, hwnd):
        return self.exists or hwnd == OWN

    def IsIconic(self, hwnd):
        return self.iconic and hwnd == VIEWER

    def GetAncestor(self, hwnd, flag):
        return hwnd

    def GetWindowLongW(self, hwnd, index):
        return windows.WS_EX_TOPMOST if hwnd == OWN and self.topmost_own else 0

    def ShowWindow(self, hwnd, cmd):
        self.shown.append((hwnd, cmd))
        if self.restores:
            self.iconic = False
        return True

    def SetWindowPos(self, hwnd, after, x, y, cx, cy, flags):
        self.placed.append((hwnd, after, x, y, cx, cy, flags))
        return True


@pytest.fixture
def fake(monkeypatch):
    user32 = User32()
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", user32, raising=False)
    monkeypatch.setattr(windows, "GA_ROOT", 2, raising=False)
    monkeypatch.setattr(windows, "GWL_EXSTYLE", -20, raising=False)
    return user32


def test_a_minimised_window_is_shown_without_activation_and_put_behind_taslation(fake):
    assert unminimise_window(VIEWER, OWN)
    assert fake.shown == [(VIEWER, 4)]  # SW_SHOWNOACTIVATE: its last size, or maximised; not activated
    assert fake.placed == [(VIEWER, OWN, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)]


def test_a_window_not_minimised_or_gone_is_left_alone(fake):
    fake.iconic = False
    assert not unminimise_window(VIEWER, OWN) and fake.shown == [] and fake.placed == []
    fake.iconic, fake.exists = True, False
    assert not unminimise_window(VIEWER, OWN) and fake.shown == [] and fake.placed == []
    assert not unminimise_window(0, OWN) and fake.shown == []


def test_under_a_topmost_taslation_the_window_is_not_put_behind_it(fake):
    fake.topmost_own = True  # placed after a topmost window it would become topmost itself
    assert unminimise_window(VIEWER, OWN) and fake.shown == [(VIEWER, 4)] and fake.placed == []
    fake.topmost_own, fake.iconic = False, True
    assert unminimise_window(VIEWER, None) and fake.placed == []  # nothing to go behind


def test_a_window_that_stays_minimised_is_not_restored(fake):
    fake.restores = False
    assert not unminimise_window(VIEWER, OWN) and fake.placed == []


def test_nothing_outside_windows(fake, monkeypatch):
    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    assert not unminimise_window(VIEWER, OWN) and fake.shown == []


def test_show_minimised_passes_taslations_own_window(monkeypatch):
    calls = []
    monkeypatch.setattr(viewers, "IS_WINDOWS", True)
    monkeypatch.setattr(viewers, "unminimise_window", lambda hwnd, below=None: calls.append((hwnd, below)) or True)
    app = SimpleNamespace(_own_hwnd=lambda: OWN)
    assert viewers.show_minimised(app, SimpleNamespace(hwnd=VIEWER)) and calls == [(VIEWER, OWN)]
    monkeypatch.setattr(viewers, "IS_WINDOWS", False)
    assert not viewers.show_minimised(app, SimpleNamespace(hwnd=VIEWER)) and calls == [(VIEWER, OWN)]


# ------------------------------------------------------------------ minimised later: waited for, with a line
class Looker:
    """What the waiting line uses."""

    _viewer_shows_book = app_mod.App._viewer_shows_book
    _say_waiting = app_mod.App._say_waiting

    def __init__(self, class_name):
        self.selected = SimpleNamespace(hwnd=VIEWER, title="Book - Browser", class_name=class_name)
        self.auto_var = SimpleNamespace(get=lambda: True)
        self._waiting = False
        self.lines: list = []

    def _book_in_front(self):
        return True  # a browser's title is still the book's while it is minimised

    def say(self, text, **kw):
        self.lines.append(text.format(**kw) if kw else text)


def test_a_minimised_browser_is_waited_for_with_a_line_and_not_restored(monkeypatch):
    minimised = {VIEWER}
    monkeypatch.setattr(live, "window_minimised", lambda hwnd: hwnd in minimised)
    restored = []
    monkeypatch.setattr(viewers, "unminimise_window", lambda hwnd, below=None: restored.append(hwnd) or True)
    w = Looker("Chrome_WidgetWin_1")
    assert not w._viewer_shows_book(w.selected) and w.lines == [BROWSER_MINIMISED]
    assert not w._viewer_shows_book(w.selected) and w.lines == [BROWSER_MINIMISED]  # said once
    assert restored == []  # nothing shown again by itself
    minimised.clear()
    assert w._viewer_shows_book(w.selected) and w.lines[-1] == "Viewer: Book - Browser"
    assert i18n.CATALOGS["ja"][BROWSER_MINIMISED].startswith("待機中: 本を表示しているブラウザ")


def test_a_minimised_image_viewer_keeps_its_line(monkeypatch):
    monkeypatch.setattr(live, "window_minimised", lambda hwnd: True)
    w = Looker("ImageViewerClass")
    assert not w._viewer_shows_book(w.selected)
    assert w.lines == ["Waiting: the viewer's window is hidden or minimised; bring it back."]
