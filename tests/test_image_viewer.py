"""A viewer that is no browser - an image viewer showing a folder of page images, its window titled with the file it
shows ("000.jpg", then "001.jpg") - stays the book while its window is there and shown, whatever its title; only a
browser window (whose title is its active tab's) goes by the title. Its profile (the area) is kept by the window's
class, so what was set for "000.jpg" is found for "001.jpg"; and while it is hidden or minimised the waiting line says
so without a word about tabs."""
from __future__ import annotations

import json
from types import SimpleNamespace

from taslation import i18n
from taslation.cache import viewer_key_from_title
from taslation.capture import WindowInfo, still_the_book
from taslation.pagekeys import Profiles, names_a_file, profile_names, viewer_key, viewer_title
from taslation.ui import live, viewers
from taslation.ui.live import BROWSER_MINIMISED

PHOTOS = "WinUIDesktopWin32WindowClass"  # the class of the image viewer of the incident
IMAGES = WindowInfo(hwnd=11, title="000.jpg", class_name=PHOTOS, pid=11, rect=(0, 0, 1200, 900))
CHROME = WindowInfo(hwnd=12, title="Star Road 1 - FOLIO☆QAT - Google Chrome", class_name="Chrome_WidgetWin_1",
                    pid=12, rect=(0, 0, 1200, 900))
HIDDEN = "Waiting: the viewer's window is hidden or minimised; bring it back."
HIDDEN_JA = "待機中: ビューアのウィンドウが非表示か最小化されています。元に戻してください。"
WAITING = "Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of its own."


def _as(win: WindowInfo, title: str) -> WindowInfo:
    return WindowInfo(win.hwnd, title, win.class_name, win.pid, win.rect)


# ------------------------------------------------------------------ the rule
def test_a_window_that_is_no_browser_stays_the_book_whatever_its_title():
    assert still_the_book(IMAGES, "001.jpg")  # the incident: the first page turn renamed the window
    assert still_the_book(IMAGES, "page 12 of 200")
    assert still_the_book(IMAGES, "")  # (a title that is gone for a moment)
    assert not still_the_book(IMAGES, "000.jpg", shown=False)  # hidden or minimised: not the book until it is back


def test_a_browser_window_goes_by_its_title_as_before():
    assert still_the_book(CHROME, CHROME.title)
    assert still_the_book(CHROME, "Star Road 1 - page 2 | FOLIO☆QAT - Google Chrome")  # the same book's page
    assert not still_the_book(CHROME, "ホーム / X - Google Chrome")  # another tab
    assert not still_the_book(CHROME, "001.jpg - Google Chrome")
    assert still_the_book(CHROME, CHROME.title, shown=False)  # (its visibility was never asked: as before)
    unknown = WindowInfo(hwnd=13, title="Book - Browser", class_name="", pid=13, rect=(0, 0, 10, 10))
    assert not still_the_book(unknown, "Other tab - Browser")  # a class not known: the title rule, as before


class Front:
    """What `_book_in_front` uses."""

    _book_in_front = viewers.ViewerMixin._book_in_front
    _viewer_retitled = viewers.ViewerMixin._viewer_retitled

    def __init__(self, selected):
        self.selected, self.window_query = selected, ""


def test_the_chosen_image_viewer_is_in_front_while_its_title_changes(monkeypatch):
    titles = {IMAGES.hwnd: "001.jpg", CHROME.hwnd: "ホーム / X - Google Chrome"}
    shown = {IMAGES.hwnd: True, CHROME.hwnd: True}
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: hwnd in titles)
    monkeypatch.setattr(viewers, "window_title", lambda hwnd: titles[hwnd])
    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: shown[hwnd])
    assert Front(IMAGES)._book_in_front()
    titles[IMAGES.hwnd] = "002.jpg"
    assert Front(IMAGES)._book_in_front()
    shown[IMAGES.hwnd] = False  # minimised
    assert not Front(IMAGES)._book_in_front()
    assert not Front(CHROME)._book_in_front()  # the browser shows another tab: waiting, as before
    titles[CHROME.hwnd] = CHROME.title
    assert Front(CHROME)._book_in_front()
    del titles[IMAGES.hwnd]  # closed
    assert not Front(IMAGES)._book_in_front()


# ------------------------------------------------------------------ the profile: the area by the window's class
def test_a_file_name_title_keys_the_profile_on_the_window_class():
    assert names_a_file("000.jpg") and names_a_file("Scan_0012.PNG") and names_a_file("cover.webp")
    assert names_a_file("12") and names_a_file("12 / 200")
    assert not names_a_file("Yomizuq") and not names_a_file("notes.txt") and not names_a_file("")
    assert profile_names(IMAGES) == ("000.jpg", PHOTOS)  # the old whole-title entry first, then the class
    assert profile_names(_as(IMAGES, "001.jpg")) == ("001.jpg", PHOTOS)
    assert profile_names("000.jpg") == ("000.jpg",)  # a title alone, as before
    assert profile_names(_as(IMAGES, "page01.png - Photos")) == ("page01.png - Photos", "Photos")  # as before
    assert profile_names(_as(IMAGES, "My Reader")) == ("My Reader",)  # a viewer's own name: as before
    assert profile_names(CHROME) == profile_names(CHROME.title)  # a browser: as before
    assert profile_names(_as(CHROME, "001.jpg")) == ("001.jpg",)  # (a browser's tab: never its class)
    assert viewer_key(IMAGES) == viewer_key(_as(IMAGES, "001.jpg")) == PHOTOS  # the in-memory tables, the same
    assert viewer_key(CHROME) == viewer_key_from_title(CHROME.title)


def test_the_area_set_for_000_is_found_for_001(tmp_path):
    p = Profiles(tmp_path / "profiles.json")
    p.set_margins(IMAGES, (0, 40, 0, 0))
    p.set_covered(IMAGES, False)
    again = Profiles(p.path)
    assert list(again.data) == [PHOTOS]
    for name in ("001.jpg", "002.jpg", "123.JPEG"):
        assert again.margins_for(_as(IMAGES, name)) == (0, 40, 0, 0)
        assert again.covered_for(_as(IMAGES, name)) is False
    # a title that knows its window's class finds the class's profile; a title alone has no class
    title = viewer_title(_as(IMAGES, "005.jpg"))
    assert title == "005.jpg" and again.key_of(title) == PHOTOS and again.margins_for(title) == (0, 40, 0, 0)
    assert again.margins_for("001.jpg") is None  # as before


def test_a_profile_kept_under_the_file_name_before_is_found_first(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"000.jpg": {"margins": [0, 85, 0, 0]}}), encoding="utf-8")
    p = Profiles(path)
    assert p.margins_for(IMAGES) == (0, 85, 0, 0)  # the old entry, looked up first
    assert p.margins_for(_as(IMAGES, "001.jpg")) is None  # another file: the class, which has none yet
    p.set_margins(_as(IMAGES, "001.jpg"), (0, 40, 0, 0))
    assert sorted(json.loads(path.read_text(encoding="utf-8"))) == sorted(["000.jpg", PHOTOS])


def test_what_versions_up_to_1_0_1_kept_in_a_profile_stays_in_the_file_and_is_ignored(tmp_path):
    """The page keys passed on, the presets, the area set on a window TASlation had enlarged, how a viewer took a key,
    full screen with reading mode: left as they are, never read; a change writes the area alone."""
    path = tmp_path / "profiles.json"
    old = {"An Image Viewer": {"fullscreen_reading": True, "margins": [0, 85, 0, 0], "margins_large": [0, 90, 0, 0],
                               "key_way": "posted", "keys": {"next": "Right", "prev": "Left", "fullscreen": "F10"}},
           "default_keys": {"fullscreen": ""}, "key_presets": {"Mine": {"next": "Down", "prev": "Up"}}}
    path.write_text(json.dumps(old), encoding="utf-8")
    p = Profiles(path)
    title = "Book - An Image Viewer"
    assert p.margins_for(title) == (0, 85, 0, 0) and p.covered_for(title) is None
    assert p.viewers() == ["An Image Viewer"]  # (the presets and the default keys are no viewer)
    p.set_margins(title, (0, 40, 0, 0))
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert kept["An Image Viewer"] == {**old["An Image Viewer"], "margins": [0, 40, 0, 0]}
    assert kept["default_keys"] == old["default_keys"] and kept["key_presets"] == old["key_presets"]
    p.set_margins(title, None)  # the area cleared: what this version does not use stays
    assert "margins" not in json.loads(path.read_text(encoding="utf-8"))["An Image Viewer"]
    assert json.loads(path.read_text(encoding="utf-8"))["An Image Viewer"]["keys"] == old["An Image Viewer"]["keys"]


# ------------------------------------------------------------------ the waiting line
class Waiting:
    """What the waiting line uses: what it says, in the window's language."""

    _say_waiting = live.LiveViewMixin._say_waiting

    def __init__(self, selected):
        self.selected, self.lines = selected, []

    def say(self, text, **params):
        self.lines.append(i18n._(text).format(**params))


def test_the_waiting_line_for_an_image_viewer_says_nothing_of_tabs(monkeypatch):
    minimised = {IMAGES.hwnd: True, CHROME.hwnd: False}
    monkeypatch.setattr(live, "window_minimised", lambda hwnd: minimised[hwnd])
    w = Waiting(IMAGES)
    w._say_waiting()  # minimised
    i18n.set_language("ja")
    try:
        w._say_waiting()
    finally:
        i18n.set_language("en")
    minimised[IMAGES.hwnd] = False  # hidden by the viewer itself: the same line
    w._say_waiting()
    assert w.lines == [HIDDEN, HIDDEN_JA, HIDDEN]
    w.selected = CHROME  # a browser window keeps its line about the tab
    w._say_waiting()
    minimised[CHROME.hwnd] = True
    w._say_waiting()
    assert w.lines[3:] == [WAITING, BROWSER_MINIMISED]


# ------------------------------------------------------------------ chosen again on another file
class Chooser:
    """What choosing a viewer uses, down to the area it reads and its line."""

    _on_window_selected = viewers.ViewerMixin._on_window_selected
    _learn_viewer = lambda self, win, by_person: None  # (the viewers learned: tests/test_viewer_parts.py)
    _title_book = lambda self, win: win.title
    _found_margins = lambda self: (0, 0, 0, 0)

    def __init__(self, profiles, windows):
        self.profiles, self.windows = profiles, list(windows)
        self.window_box = SimpleNamespace(current=lambda: 0)
        self.selected, self.busy, self.window_query = None, False, ""
        self._book_given = self._book_edited = False
        self.book_var = SimpleNamespace(set=lambda value: None)
        self.settings = SimpleNamespace(margins=(0, 0, 0, 0))
        self.lines, self.looked = [], []

    def status(self, line):
        self.lines.append(line() if callable(line) else line)

    def say(self, text, **params):
        self.lines.append(text.format(**params))

    def _enlarge_first(self):
        self.looked.append(self.selected.hwnd)  # looked at once as it is (never moved nor resized)
        return True

    def _nothing(self, *_a):
        return None

    _set_covered = _redisplay = _warm_page_models = _learn_covered_soon = _follow_viewer = _viewer_left = _nothing


def test_choosing_the_image_viewer_on_another_file_finds_its_area(tmp_path, monkeypatch):
    monkeypatch.setattr(viewers, "show_minimised", lambda app, win: False)
    profiles = Profiles(tmp_path / "profiles.json")
    profiles.set_margins(IMAGES, (0, 85, 0, 0))  # set while it showed 000.jpg
    w = Chooser(profiles, [_as(IMAGES, "001.jpg")])  # chosen again on the next file
    w._on_window_selected()
    assert w.selected.title == "001.jpg" and w.settings.margins == (0, 85, 0, 0) and w._manual_area
    assert w.lines == ["Viewer: 001.jpg  (area set)"] and w.looked == [IMAGES.hwnd]
