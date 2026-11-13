"""A browser window always gets real key presses; other windows get posted keys until they refuse."""

from taslation import pagekeys
from taslation.capture import windows as W


def test_a_browser_always_gets_real_presses(monkeypatch):
    """A key posted to a browser that is not in front reaches nothing (measured 0 of 9): what looked like one taken
    never makes a browser get posted keys."""
    monkeypatch.setattr(W, "window_class", lambda hwnd: W.BROWSER_CLASSES[0])
    ways = pagekeys.KeyWays()
    assert ways.real(5)
    ways.learned(5, False, True)  # seen to take a posted key, it seemed
    assert ways.real(5)


def test_another_window_starts_with_posted_keys(monkeypatch):
    monkeypatch.setattr(W, "window_class", lambda hwnd: "SomeViewer")
    ways = pagekeys.KeyWays()
    assert not ways.real(5)
    ways.learned(5, True, False)
    assert ways.real(5)


def test_an_image_viewer_turns_with_the_right_arrow_whichever_file_it_opened_at():
    from types import SimpleNamespace

    from taslation.capture import WindowInfo

    win = WindowInfo(hwnd=5, title="005.jpg", class_name="SomeImageViewer", pid=5, rect=(0, 0, 800, 600))
    settings = SimpleNamespace(next_page_key="Left", prev_page_key="Right", fullscreen_key="F11")
    keys = pagekeys.page_keys_for(SimpleNamespace(data={}), settings, win)
    assert (keys.next, keys.prev) == ("Right", "Left")
