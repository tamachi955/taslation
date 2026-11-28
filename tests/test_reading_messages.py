"""The viewer's messages: the line while the viewer cannot be read (a browser showing another tab, a browser window
minimised, a viewer's window hidden), the area set said in words, a viewer chosen said with its area and followed, and
the band breaking its lines in every script. Parts of the App are borrowed onto stand-ins on the shared hidden root
(never mapped)."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation import i18n
from taslation.capture import WindowInfo
from taslation.ui import app as app_mod
from taslation.ui import live
from taslation.ui.constants import BROWSER_MINIMISED
from taslation.ui.preview import ImageCanvas

CHROME = WindowInfo(hwnd=7, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7, rect=(0, 0, 960, 540))
VIEWER_APP = WindowInfo(hwnd=8, title="Yomizuq for PC", class_name="Qt5QWindowIcon", pid=8, rect=(0, 0, 960, 540))
WAITING = ("Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of its own.")


class Lines:
    """The status line of the window (`status`, `say`) on a stand-in."""

    status = app_mod.App.status
    say = app_mod.App.say

    def __init__(self, root):
        self.status_var = tk.StringVar(master=root)
        self._status_render = self._status_key = self._status_page = None


class Waiting(Lines):
    _say_waiting = app_mod.App._say_waiting

    def __init__(self, root, selected):
        super().__init__(root)
        self.selected = selected


def test_the_line_while_the_viewer_cannot_be_read_says_why(hidden_root, monkeypatch):
    minimised = [False]
    monkeypatch.setattr(live, "window_minimised", lambda hwnd: minimised[0])  # (no real window asked)
    w = Waiting(hidden_root, CHROME)
    w._say_waiting()  # the browser window shows another tab
    assert w.status_var.get() == WAITING
    i18n.set_language("ja")
    try:
        assert w._status_render().startswith("待機中: ブラウザが別のタブを表示しています。本のタブに戻すか")  # said again
    finally:
        i18n.set_language("en")
    minimised[0] = True  # the browser window minimised: its frames are blank
    w._say_waiting()
    assert w.status_var.get() == BROWSER_MINIMISED
    w = Waiting(hidden_root, VIEWER_APP)  # a viewer that is no browser: its window hidden or minimised
    w._say_waiting()
    assert w.status_var.get() == "Waiting: the viewer's window is hidden or minimised; bring it back."


class Area(Lines):
    """What the area set by hand uses."""

    _area_chosen = app_mod.App._area_chosen
    clear_area = app_mod.App.clear_area

    def __init__(self, root):
        super().__init__(root)
        self.selected = CHROME
        self.settings = SimpleNamespace(margins=(0, 0, 0, 0))
        self.kept: list = []
        self.profiles = SimpleNamespace(set_margins=lambda win, margins, large=False: self.kept.append(margins))
        self._manual_area, self._hand_area, self._auto_last = False, None, None
        self.looks = 0

    def _found_margins(self):
        return (0, 0, 0, 0)

    def _look_soon(self):
        self.looks += 1


def test_the_status_line_after_set_area_says_it_is_set(hidden_root):
    w = Area(hidden_root)
    w._area_chosen((295, 85, 665, 540), (960, 540))
    assert w.status_var.get() == "Area set. Only this part of the viewer is read."
    assert "margins" not in w.status_var.get() and "px" not in w.status_var.get()
    assert w._manual_area and tuple(w.settings.margins) == (295, 85, 295, 0) and w.kept == [(295, 85, 295, 0)]
    assert w.looks == 1  # read again with this area
    i18n.set_language("ja")
    try:
        assert w._status_render() == "範囲を設定しました。ビューアのこの部分だけを読みます。"
    finally:
        i18n.set_language("en")
    w._area_chosen((0, 0, 960, 540), (960, 540))  # the whole window: no area of the reader's
    assert not w._manual_area and w.kept[-1] is None and w.status_var.get().startswith("Area cleared:")


class Chooser(Lines):
    """What choosing a viewer in the list uses."""

    _on_window_selected = app_mod.App._on_window_selected
    _known_viewer = app_mod.App._known_viewer
    _learn_viewer = app_mod.App._learn_viewer
    _title_book = app_mod.App._title_book
    _enlarge_first = lambda self: True  # (the window looked at as it is: tests/test_see_hidden.py)
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    _warm_page_models = app_mod.App._warm_page_models

    def __init__(self, root, margins):
        super().__init__(root)
        self.windows = [CHROME]
        self.window_box = SimpleNamespace(current=lambda: 0)
        self.book_var = tk.StringVar(master=root)
        self._book_edited = True
        self.profiles = SimpleNamespace(margins_for=lambda title, large=False: margins)
        self.settings = SimpleNamespace(margins=(0, 0, 0, 0))
        self.followed = 0

    def _found_margins(self):
        return (0, 0, 0, 0)

    def _set_covered(self, covered):
        pass

    def _redisplay(self):
        pass

    def _follow_viewer(self):
        self.followed += 1


def test_choosing_a_viewer_says_its_area_in_words_and_follows_it(hidden_root):
    w = Chooser(hidden_root, (0, 85, 0, 0))
    w._on_window_selected()
    assert w.status_var.get() == "Viewer: Yomizuq - Google Chrome  (area set)" and w.followed == 1
    assert w._manual_area and tuple(w.settings.margins) == (0, 85, 0, 0)
    w = Chooser(hidden_root, None)
    w._on_window_selected()
    assert w.status_var.get() == "Viewer: Yomizuq - Google Chrome" and not w._manual_area


@pytest.mark.parametrize("code", ["ja", "de", "zh", "ko"])
def test_the_band_breaks_its_lines_in_every_script(hidden_root, code):
    """The band breaks its lines itself (CJK has no spaces for Tk to break at)."""
    i18n.set_language(code)
    try:
        canvas = ImageCanvas(hidden_root)
        canvas.winfo_width, canvas.winfo_height = (lambda: 800), (lambda: 600)
        canvas.set_image(Image.new("RGB", (800, 600), "white"))
        text = i18n.tr("The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or move it so that a strip of the viewer stays visible.")
        canvas.set_banner(text)
        x0, _y0, x1, _y1 = canvas.bbox("banner")
        assert x1 - x0 <= 640 + 2 * 12 + 12 and canvas.itemcget("banner-text", "text").count("\n") >= 1  # its box
        assert canvas.itemcget("banner-text", "text").replace("\n", "").replace(" ", "") == text.replace(" ", "")
        canvas.set_banner("")
        assert not canvas.find_withtag("banner")
    finally:
        i18n.set_language("en")
