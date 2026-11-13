"""A key waits for a browser reader that draws itself anew when it gets the foreground (`capture.press_briefly`)."""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from taslation.capture import windows

BLACK = Image.new("RGB", (64, 64), (0, 0, 0))
PAGE = Image.effect_noise((64, 64), 80).convert("RGB")


def frames(monkeypatch, shown, browser=True):
    """The window's frames one after the other, the last one for good; the looks are counted."""
    looks = []

    def capture(_hwnd, allow_screen_fallback=True):
        looks.append(1)
        return shown[min(len(looks) - 1, len(shown) - 1)]

    monkeypatch.setattr(windows, "capture_window", capture)
    monkeypatch.setattr(windows, "window_class", lambda _h: "Chrome_WidgetWin_1" if browser else "Other")
    monkeypatch.setattr(windows, "REDRAW_STEP_S", 0.001)
    return looks


def test_a_browser_that_goes_black_is_waited_for(monkeypatch):
    looks = frames(monkeypatch, [PAGE, BLACK, BLACK, PAGE])
    windows._redrawn_after_focus(5)
    assert len(looks) == 4


def test_a_browser_that_shows_no_black_holds_the_key_only_briefly(monkeypatch):
    monkeypatch.setattr(windows, "REDRAW_STARTS_S", 0.01)
    looks = frames(monkeypatch, [PAGE])
    windows._redrawn_after_focus(5)
    assert looks


def test_a_black_page_ends_the_wait_at_its_limit(monkeypatch):
    monkeypatch.setattr(windows, "REDRAW_WAIT_S", 0.01)
    assert frames(monkeypatch, [BLACK]) == []
    windows._redrawn_after_focus(5)


def test_another_window_is_not_looked_at(monkeypatch):
    looks = frames(monkeypatch, [BLACK], browser=False)
    windows._redrawn_after_focus(5)
    assert looks == []


def test_a_window_gone_ends_the_wait(monkeypatch):
    frames(monkeypatch, [PAGE])

    def gone(*_a, **_k):
        raise windows.CaptureError("gone")

    monkeypatch.setattr(windows, "capture_window", gone)
    windows._redrawn_after_focus(5)


def _press(monkeypatch, front, covered, browser=True):
    """press_briefly for window 5 with window *front* in front: whether it waited for a redraw."""
    waited = []
    monkeypatch.setattr(windows, "_redrawn_after_focus", waited.append)
    monkeypatch.setattr(windows, "_reach_foreground", lambda _h: True)
    monkeypatch.setattr(windows, "press_key", lambda _h, _k: True)
    monkeypatch.setattr(windows, "give_foreground", lambda _h: True)
    monkeypatch.setattr(windows, "KEY_SETTLE_S", 0)
    monkeypatch.setattr(windows, "window_class", lambda _h: "Chrome_WidgetWin_1" if browser else "Other")
    monkeypatch.setattr(windows, "covered_by_opaque", lambda _h: covered)
    monkeypatch.setattr(windows.user32, "GetForegroundWindow", lambda: front, raising=False)
    assert windows.press_briefly(5, "Left")
    return waited == [5]


def test_the_press_waits_only_when_the_foreground_moved_to_a_browser_opaque_windows_covered(monkeypatch):
    assert _press(monkeypatch, front=9, covered=True)
    assert not _press(monkeypatch, front=5, covered=True)  # it had the foreground: nothing to draw anew
    assert not _press(monkeypatch, front=9, covered=True, browser=False)


def test_a_browser_under_see_through_windows_only_gets_the_key_at_once(monkeypatch):
    """Under TASlation's own window at WINDOW_ALPHA a browser never stops drawing (Chromium counts no layered window
    with an alpha below 255 as covering it): the redraw wait made every key take 1.1-1.5 s, and the keys pressed
    meanwhile went to the browser behind TASlation's back (measured 2026-11-06: half of them at 1 key a second)."""
    assert not _press(monkeypatch, front=9, covered=False)


class Win:
    """A top-level window as `fully_opaque` asks Windows about it."""

    def __init__(self, ex=0, layered=None, cls="Chrome_WidgetWin_1", visible=True, iconic=False, cloaked=False):
        self.ex, self.layered, self.cls = ex, layered, cls
        self.visible, self.iconic, self.cloaked = visible, iconic, cloaked


def _windows(monkeypatch, wins):
    def layered(h, key, alpha, flags):
        got = wins[h].layered
        if got is None:
            return 0
        alpha._obj.value, flags._obj.value = got
        return 1

    fake = SimpleNamespace(IsWindow=lambda h: h in wins, IsWindowVisible=lambda h: wins[h].visible,
                           IsIconic=lambda h: wins[h].iconic, GetWindowLongW=lambda h, _i: wins[h].ex,
                           GetLayeredWindowAttributes=layered)
    monkeypatch.setattr(windows, "user32", fake)
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "_is_cloaked", lambda h: wins[h].cloaked)
    monkeypatch.setattr(windows, "window_class", lambda h: wins[h].cls)


def test_which_windows_hide_what_lies_under_them(monkeypatch):
    L, T, TOOL = windows.WS_EX_LAYERED, windows.WS_EX_TRANSPARENT, windows.WS_EX_TOOLWINDOW
    wins = {1: Win(), 2: Win(L, (252, windows.LWA_ALPHA)), 3: Win(L, (255, windows.LWA_ALPHA)),
            4: Win(L, (255, windows.LWA_COLORKEY)), 5: Win(L, None), 6: Win(T), 7: Win(TOOL),
            8: Win(TOOL, cls=windows.TASKBAR_CLASS), 9: Win(visible=False), 10: Win(iconic=True), 11: Win(cloaked=True)}
    _windows(monkeypatch, wins)
    opaque = {h for h in wins if windows.fully_opaque(h)}
    assert opaque == {1, 3, 8}  # plain, layered at 255 (Tk's -alpha 0.999), the taskbar


def test_only_a_window_that_hides_what_lies_under_it_counts_as_covering_the_browser(monkeypatch):
    L = windows.WS_EX_LAYERED
    taslation, other, aside = Win(L, (252, windows.LWA_ALPHA)), Win(), Win()
    wins = {5: Win(), 20: taslation, 21: other, 22: aside}
    rects = {20: (0, 0, 1920, 1040), 21: (100, 100, 400, 400), 22: (2000, 0, 2400, 400)}
    above = {5: 22, 22: 20, 20: 0}
    _windows(monkeypatch, wins)
    windows.user32.GetAncestor = lambda h, _f: h
    windows.user32.GetWindow = lambda h, _w: above.get(h, 0)
    monkeypatch.setattr(windows, "client_rect_on_screen", lambda _h: (0, 0, 1900, 1000))
    monkeypatch.setattr(windows, "_window_rect", lambda h: rects[h])
    assert not windows.covered_by_opaque(5)  # TASlation's own at WINDOW_ALPHA over it, an opaque one beside it
    above.update({20: 21, 21: 0})
    assert windows.covered_by_opaque(5)  # an opaque window over part of it
