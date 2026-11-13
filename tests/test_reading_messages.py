"""Reading mode and the viewer's messages: full screen on the window's own monitor, no note about the keys in the
reading window and the keys named as the reader knows them in the normal one, F11's refusal during a batch kept on
the page, Set area... offered first where a browser's tabs and address bar would be read, the area set said in
words, the line while the browser shows another tab. Parts of the App are borrowed onto stand-ins on the shared
hidden root (never mapped)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation import i18n
from taslation.capture import CaptureError, WindowInfo
from taslation.config import Settings
from taslation.ui import app as app_mod
from taslation.ui import reading, viewers
from taslation.ui.constants import READING_NOTE_MS, WINDOW_ALPHA
from taslation.ui.preview import ImageCanvas
from taslation.ui.reading import key_label
from taslation.ui.viewers import looks_like_browser

CHROME = WindowInfo(hwnd=7, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7, rect=(0, 0, 960, 540))
VIEWER_APP = WindowInfo(hwnd=8, title="Yomizuq for PC", class_name="Qt5QWindowIcon", pid=8, rect=(0, 0, 960, 540))
WAITING = ("Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of its own.")
REFUSED = "Reading mode waits for the whole-book run to finish (Stop ends it)."


def test_keys_are_named_as_the_reader_knows_them():
    assert [key_label(k) for k in ("Left", "Right", "Up", "Down")] == ["←", "→", "↑", "↓"]
    assert [key_label(k) for k in ("PageUp", "PageDown", "Home", "End", "Space")] == [
        "Page Up", "Page Down", "Home", "End", "Space"]
    assert key_label("F7") == "F7"  # a key of the batch's choosing: as it is
    i18n.set_language("de")
    try:
        assert [key_label(k) for k in ("Left", "PageDown", "Home", "Space")] == ["←", "Bild ab", "Pos1", "Leertaste"]
        i18n.set_language("ja")
        assert key_label("Space") == "スペース" and key_label("Right") == "→"
    finally:
        i18n.set_language("en")


class Keys:


    _raise_for_key = lambda self, hwnd: None  # (the viewer raised for a look: tests/test_wgc.py)
    _frame_count = lambda self: None  # (frames counted: tests/test_follow.py)
    _last_frame = lambda self, hwnd, seq: None
    """What `forward_key` uses."""

    forward_key = app_mod.App.forward_key
    _key_viewer = app_mod.App._key_viewer
    _hand_over = app_mod.App._hand_over
    _pass_on = app_mod.App._pass_on
    _key_for_viewer = app_mod.App._key_for_viewer
    _page_key_pair = app_mod.App._page_key_pair
    _say_waiting = app_mod.App._say_waiting
    status = app_mod.App.status
    say = app_mod.App.say

    def __init__(self, root):
        self.canvas = ImageCanvas(root)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        self.status_var = tk.StringVar(master=root)
        self.selected, self.batch, self.reading, self.in_front = CHROME, None, False, True
        self.followed: list[tuple[str, bool]] = []

    def _book_in_front(self):
        return self.in_front

    def _capture(self, hwnd):
        return Image.new("RGB", (64, 48), "white")

    def _set_covered(self, covered):
        pass

    def _follow_change(self, hwnd, reference, key, started, retried=False, seq=None):
        self.followed.append((key, retried))


def test_the_translator_role_names_the_key_and_a_reader_sees_the_page_turn(hidden_root, monkeypatch):
    sent = []
    monkeypatch.setattr(reading, "post_key", lambda hwnd, key: sent.append(key))
    monkeypatch.setattr(reading, "window_exists", lambda hwnd: True)
    w = Keys(hidden_root)
    w.role_var = tk.StringVar(hidden_root, value="reader")
    w.forward_key("Up")
    assert sent == ["Up"] and w.status_var.get() == "" and w.followed == [("Up", False)]
    sent.clear(), w.followed.clear()
    w.role_var.set("translator")
    w.forward_key("Left")
    assert sent == ["Left"] and w.status_var.get() == "Sent ← to the viewer..." and w.followed == [("Left", False)]
    i18n.set_language("ja")
    try:
        w.forward_key("Space")
        assert w.status_var.get() == "ビューアに スペース を送信..."
        assert w._status_render() == "ビューアに スペース を送信..."  # said again in the window's language after a switch
    finally:
        i18n.set_language("en")
    w.reading = True
    w.status_var.set("")
    w.forward_key("Right")
    assert sent[-1] == "Right" and w.status_var.get() == "" and not w.canvas.note  # no note in the reading window
    assert w.followed[-1] == ("Right", False)
    w.reading, w.in_front = False, False  # the browser window shows another tab: the key is not sent
    w.forward_key("Left")
    assert sent[-1] == "Right" and w.status_var.get() == WAITING
    i18n.set_language("ja")
    try:
        w.forward_key("Left")
        assert w.status_var.get().startswith("待機中: ブラウザが別のタブを表示しています。本のタブに戻すか")
    finally:
        i18n.set_language("en")


class Reading(tk.Toplevel):
    """Reading mode in and out on a withdrawn window of the hidden root (full screen and alpha are only recorded)."""

    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    enter_reading = app_mod.App.enter_reading
    leave_reading = app_mod.App.leave_reading
    status = app_mod.App.status
    say = app_mod.App.say
    _normal_status = app_mod.App._normal_status
    _restore_geometry = app_mod.App._restore_geometry
    _current_geometry = app_mod.App._current_geometry
    _window_monitor = app_mod.App._window_monitor
    _onto_monitor = app_mod.App._onto_monitor
    _area_offer_due = app_mod.App._area_offer_due
    _offer_area = app_mod.App._offer_area
    set_area = app_mod.App.set_area
    _area_chosen = app_mod.App._area_chosen
    clear_area = app_mod.App.clear_area
    _look_soon = app_mod.App._look_soon
    _follows_events = app_mod.App._follows_events
    _found_margins = app_mod.App._found_margins
    _set_covered = app_mod.App._set_covered
    _watch_top_edge = app_mod.App._watch_top_edge
    _top_edge_moved = app_mod.App._top_edge_moved
    _top_edge_left = app_mod.App._top_edge_left
    _show_close = app_mod.App._show_close
    _hide_close = app_mod.App._hide_close
    _close_clicked = app_mod.App._close_clicked
    _ask_name_after_reading = app_mod.App._ask_name_after_reading

    def __init__(self, root, hwnd=None):
        super().__init__(root)
        self.withdraw()
        self.hwnd = hwnd
        self.attrs = {"-alpha": 0.99, "-fullscreen": 0}
        self.calls: list[tuple] = []
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)
        self.bar = ttk.Frame(self)
        self.bar.pack(fill="x")
        self._bars = (self.bar,)
        self.canvas = ImageCanvas(self)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        self.status_bar = ttk.Frame(self)
        self.status_bar.pack(fill="x")
        self.notes_label = ttk.Label(self)
        self.status_var = tk.StringVar(self)
        self.original_var, self.auto_var, self.top_var = tk.BooleanVar(self), tk.BooleanVar(self), tk.BooleanVar(self)
        self.selected, self.last_result = CHROME, None
        self.reading = self._batching = self._viewer_hidden = self._scan_waits_told = self._restoring = False
        self._ordering = self._chosen_region = self._status_render = self._status_key = None
        self._normal_geometry = ""
        self.settings = Settings()
        self._manual_area, self._page_areas, self._covered = False, {}, False
        self.profiles = SimpleNamespace(set_margins=lambda title, margins, large=False: None)
        self.found = None  # the page panel the next capture finds
        self.frame = Image.new("RGB", (960, 540), "white")

    def attributes(self, *args):
        if len(args) == 1:
            return self.attrs.get(args[0], 0)
        self.attrs[args[0]] = args[1]
        self.calls.append(("attributes", args[0], args[1]))

    def after(self, ms, func=None):  # at once (the dialogs' and the area's follow-ups)
        if func is not None:
            func()

    def _own_hwnd(self):
        return self.hwnd

    def _apply_on_top(self):
        pass

    def _redisplay(self):
        pass

    def _show_notes(self):
        pass

    def _result_on_show(self):
        return False

    def _on_escape(self):
        pass

    def _current_window(self):
        return self.selected

    def _capture(self, hwnd):
        if self.frame is None:
            raise CaptureError("gone")
        key = app_mod.viewer_key_from_title(self.selected.title)
        self._page_areas[key] = (self.frame.size, self.found)  # what _find_page leaves
        return self.frame

    def _capture_failed(self, error):
        pass


def test_reading_mode_opens_full_screen_on_the_windows_own_monitor(hidden_root, monkeypatch):
    moved = []
    monkeypatch.setattr(reading, "monitor_rect", lambda hwnd: (1920, 0, 3840, 1080))
    monkeypatch.setattr(reading, "move_window", lambda hwnd, rect: moved.append((hwnd, rect)) or True)
    w = Reading(hidden_root, hwnd=4242)
    w._manual_area = True
    w.enter_reading()
    assert w.reading and w.attrs["-fullscreen"] is True and moved == [(4242, (1920, 0, 3840, 1080))]
    # unseen (alpha 0) from before full screen, which Tk puts on the primary monitor, until it is on its own
    assert [c for c in w.calls if c[1] in ("-alpha", "-fullscreen")] == [
        ("attributes", "-alpha", 0.0), ("attributes", "-fullscreen", True), ("attributes", "-alpha", WINDOW_ALPHA)]
    w.leave_reading()
    assert not w.reading and w.attrs["-fullscreen"] is False and w.attrs["-alpha"] == 0.99
    w = Reading(hidden_root, hwnd=None)  # no monitor to be had (not Windows): full screen as Tk makes it
    w._manual_area = True
    moved.clear()
    w.enter_reading()
    assert w.reading and not moved and [c[2] for c in w.calls if c[1] == "-alpha"] == [WINDOW_ALPHA]


def test_f11_during_a_batch_says_so_on_the_page_for_a_few_seconds(hidden_root):
    w = Reading(hidden_root)
    w._batching = True
    w.enter_reading()
    assert not w.reading and w.status_var.get() == REFUSED and w.canvas.note == REFUSED
    assert w.canvas._note_job is not None  # it goes by itself after READING_NOTE_MS
    w.say("Batch {phase}- {message}  ({pages} pages, {bubbles} bubbles, {hits} already cached)", phase="[scan] ",
          message="page 3", pages=3, bubbles=12, hits=0)  # the batch's next line, 0.3 s later
    assert w.canvas.note == REFUSED and w.status_var.get().startswith("Batch [scan]")
    assert READING_NOTE_MS >= 3000
    i18n.set_language("ja")
    try:
        w.enter_reading()
        assert w.canvas.note == i18n.tr(REFUSED) and w.canvas.note != REFUSED  # in the window's language
    finally:
        i18n.set_language("en")


def _buttons(box):
    found, stack = {}, [box]
    while stack:
        widget = stack.pop()
        if widget.winfo_class() == "TButton":
            found[str(widget.cget("text"))] = widget
        stack.extend(widget.winfo_children())
    return found


def test_set_area_is_offered_first_where_the_browsers_tabs_would_be_read(hidden_root, monkeypatch):
    w = Reading(hidden_root)
    assert looks_like_browser(CHROME) and not looks_like_browser(VIEWER_APP)
    w.enter_reading()  # a browser window, no area of the reader's, no page panel found: asked first
    assert not w.reading and w._area_offer.winfo_exists()
    box = w._area_offer
    label = next(c for c in box.winfo_children()[0].winfo_children() if c.winfo_class() == "TLabel")
    assert str(label.cget("text")).replace("\n", " ").startswith("The browser's tabs and address bar are part of the page")
    buttons = _buttons(box)
    assert set(buttons) == {"Set area...", "Read as it is"}
    buttons["Read as it is"].invoke()
    assert w.reading and not box.winfo_exists()  # read as it is
    w.leave_reading()
    w.enter_reading()  # asked once a session for each viewer
    assert w.reading
    w.leave_reading()

    w = Reading(hidden_root)
    chosen = []

    class Dialog:  # the area dialog: the reader draws a rectangle and presses Enter
        def __init__(self, master, image, callback, margins, inner=None, clear=None):
            chosen.append(margins)
            callback((295, 85, 665, 540), image.size)

    monkeypatch.setattr(viewers, "AreaDialog", Dialog)
    w.enter_reading()
    _buttons(w._area_offer)["Set area..."].invoke()
    assert chosen == [(0, 0, 0, 0)] and w._manual_area and tuple(w.settings.margins) == (295, 85, 295, 0)
    assert w.reading  # then the reading window, once the area is set
    w.leave_reading()
    w = Reading(hidden_root)
    w.enter_reading()
    w._area_offer.event_generate("<Escape>")  # Esc: nothing at all
    w._area_offer.destroy() if w._area_offer.winfo_exists() else None
    assert not w.reading

    for setup in ({"selected": VIEWER_APP}, {"_manual_area": True}, {"found": (150, 44, 810, 520)}, {"frame": None}):
        w = Reading(hidden_root)
        for name, value in setup.items():
            setattr(w, name, value)
        w.enter_reading()  # another viewer, an area of the reader's, a page panel found, no capture: straight in
        assert w.reading, setup
        w.leave_reading()


def test_the_status_line_after_set_area_says_it_is_set(hidden_root):
    w = Reading(hidden_root)
    w._area_chosen((295, 85, 665, 540), (960, 540))
    assert w.status_var.get() == "Area set. Only this part of the viewer is read."
    assert "margins" not in w.status_var.get() and "px" not in w.status_var.get()
    i18n.set_language("ja")
    try:
        assert w._status_render() == "範囲を設定しました。ビューアのこの部分だけを読みます。"
    finally:
        i18n.set_language("en")


class Chooser:
    """What choosing a viewer in the list uses."""

    _on_window_selected = app_mod.App._on_window_selected
    _learn_viewer = app_mod.App._learn_viewer
    _title_book = app_mod.App._title_book
    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    _warm_page_models = app_mod.App._warm_page_models
    status = app_mod.App.status
    say = app_mod.App.say

    def __init__(self, root, margins):
        self.windows = [CHROME]
        self.window_box = SimpleNamespace(current=lambda: 0)
        self.status_var = tk.StringVar(master=root)
        self.book_var = tk.StringVar(master=root)
        self._book_edited, self._reading_at_start, self.reading = True, False, False
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
def test_the_new_lines_fit_the_banner_and_the_offer_in_every_script(hidden_root, code):
    """The band and the offer break their lines themselves (CJK has no spaces for Tk to break at)."""
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


def test_the_band_about_the_viewer_covered_does_not_follow_into_reading_mode(hidden_root):
    w = Reading(hidden_root)
    w._manual_area = True
    w._set_covered(True)
    assert w.canvas.banner.startswith("The viewer stopped drawing")
    w.auto_var.set(True)  # (Auto on already: the plain first line)
    w.enter_reading()
    assert w.reading and w.canvas.banner == "" and not w._covered
    assert w.status_var.get() == "Reading mode: page keys turn the viewer's pages; F11 or Esc leaves it."
