"""Which windows hide what lies under them (`capture.fully_opaque`), and so whether a browser may have stopped
drawing behind them (`capture.covered_by_opaque`): TASlation's see-through windows never count."""

from __future__ import annotations

from types import SimpleNamespace

from taslation.capture import windows

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
    assert not windows.covered_by_opaque(5)  # TASlation's see-through window over it, an opaque one beside it
    above.update({20: 21, 21: 0})
    assert windows.covered_by_opaque(5)  # an opaque window over part of it
