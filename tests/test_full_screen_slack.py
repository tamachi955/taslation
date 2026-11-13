"""A browser's full screen stops one row short of the monitor, and is full screen all the same."""

import pytest

from taslation.capture import windows as W

MONITOR = (0, 0, 1920, 1080)


@pytest.mark.parametrize("rect, full", [
    ((0, 0, 1920, 1080), True),
    ((0, 0, 1920, 1079), True),  # a browser's full screen, measured
    ((-8, -8, 1928, 1040), False),  # maximised over a taskbar
    ((0, 0, 1920, 1032), False),  # the work area
    ((104, 104, 1544, 857), False),
])
def test_a_window_fills_its_monitor(monkeypatch, rect, full):
    monkeypatch.setattr(W, "IS_WINDOWS", True)
    monkeypatch.setattr(W, "monitor_rect", lambda hwnd: MONITOR)
    monkeypatch.setattr(W, "window_rect", lambda hwnd: rect)
    assert W.is_fullscreen(1) is full
