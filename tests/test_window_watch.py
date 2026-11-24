"""The windows TASlation may follow: the list rescans as it opens; TASlation chooses no viewer by itself - not one
remembered on this computer, not one whose title has a reading word: the person chooses in the viewer chooser
(tests/test_viewer_chooser.py), where those come first and one is preselected. Only a window named with --window is
chosen, and watched for until it is there (again after it was closed). Every store and viewer named below is invented
(test data)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from taslation import viewerparts
from taslation.capture import WindowInfo, looks_like_viewer
from taslation.ui import app as app_mod
from taslation.ui import viewers

NOTEPAD = WindowInfo(hwnd=1, title="notes.txt - Notepad", class_name="Notepad", pid=1, rect=(0, 0, 800, 600))
YOMIZUQ = WindowInfo(hwnd=2, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=2, rect=(0, 0, 1200, 900))
READER = WindowInfo(hwnd=3, title="My Reader", class_name="Reader", pid=3, rect=(0, 0, 1000, 800))
VIEWERS = ("Yomizuq", "FOLIO☆QAT", "BookZumo!Reader", "ebookqat", "ズモリカ")


def _learned(*parts: str) -> None:
    """*parts* are viewers' parts, as choosing their windows teaches (tests/test_viewer_parts.py)."""
    viewerparts.change(lambda memory: memory.learn(parts or VIEWERS))


class Box(dict):
    """Stands in for the viewer list (a ttk.Combobox): its values, and the current index."""

    def __init__(self):
        super().__init__(values=[])
        self.index = -1

    def current(self, index=None):
        if index is None:
            return self.index
        self.index = index


class Window:
    """The parts of the App that the list and the watch use: the App's own list, its stand-ins recorded."""

    _rescan_windows = app_mod.App._rescan_windows
    _watch_windows = app_mod.App._watch_windows
    refresh_windows = app_mod.App.refresh_windows

    def __init__(self, windows=(), selected=None, grab="", query=""):
        self.windows = list(windows)
        self.window_box = Box()
        self.window_box["values"] = [w.label() for w in self.windows]
        self.selected = selected
        self.window_query = query
        self.tk = SimpleNamespace(call=lambda *args: grab)
        self.chosen: list[tuple[WindowInfo, bool]] = []
        self.scheduled = 0
        self.said: list[str] = []

    def _on_window_selected(self, picked=False, named=False):  # as the App's: the window the list shows becomes the viewer
        self.selected = self.windows[self.window_box.current()]
        self.chosen.append((self.selected, named))

    def say(self, key, **_values):
        self.said.append(key)

    def after(self, ms, func):
        assert ms == app_mod.WINDOW_WATCH_MS and func == self._watch_windows
        self.scheduled += 1


@pytest.fixture
def screen(monkeypatch):
    shown: list = []
    monkeypatch.setattr(viewers, "IS_WINDOWS", True)
    monkeypatch.setattr(viewers, "list_windows", lambda: list(shown))
    return shown


def _fail():
    raise OSError("EnumWindows failed")


def test_the_list_rescans_as_it_opens_and_keeps_the_choice(screen, monkeypatch):
    w = Window([NOTEPAD], selected=NOTEPAD)
    w.window_box.index = 0
    screen[:] = [YOMIZUQ, NOTEPAD]
    w._rescan_windows()
    assert w.windows == [YOMIZUQ, NOTEPAD] and w.window_box["values"] == [YOMIZUQ.label(), NOTEPAD.label()]
    assert w.window_box.current() == 1 and w.selected is NOTEPAD and not w.chosen
    values = w.window_box["values"]
    w._rescan_windows()  # nothing changed: nothing replaced
    assert w.window_box["values"] is values
    monkeypatch.setattr(viewers, "list_windows", _fail)
    w._rescan_windows()
    assert w.windows == [YOMIZUQ, NOTEPAD]


def test_without_a_name_nothing_is_chosen_nor_watched_for_remembered_or_with_a_reading_word(screen):
    _learned()
    shelf = WindowInfo(hwnd=11, title="見本の物語 1 - Zumo Books - Google Chrome", class_name="Chrome_WidgetWin_1",
                       pid=11, rect=(0, 0, 1000, 800))
    screen[:] = [YOMIZUQ, NOTEPAD, shelf]  # a remembered viewer and a reading word: both only offered first
    w = Window()
    w.refresh_windows()
    assert w.selected is None and not w.chosen and not w.said and w.windows == [YOMIZUQ, NOTEPAD, shelf]
    w._watch_windows()
    assert w.selected is None and w.scheduled == 0  # (no watch: the viewer chooser is on the screen)
    assert viewers.offered(w.windows) == ([YOMIZUQ, shelf, NOTEPAD], YOMIZUQ)


def test_the_watch_looks_for_the_named_window_until_it_is_there_then_stops(screen):
    screen[:] = [NOTEPAD]
    w = Window(query="my reader")
    w._watch_windows()
    assert w.selected is None and w.scheduled == 1  # not there yet: looked for again
    screen[:] = [READER, NOTEPAD]
    w._watch_windows()
    assert w.selected == READER and w.chosen == [(READER, True)] and w.scheduled == 1  # chosen, named: no more looking
    w._watch_windows()
    assert w.scheduled == 1


def test_a_name_that_names_nothing_falls_back_on_no_viewer(screen):
    _learned()
    screen[:] = [YOMIZUQ, NOTEPAD]  # a remembered viewer, but not the one named
    w = Window(query="my reader")
    w.refresh_windows(select="my reader")
    w._watch_windows()
    assert w.selected is None and not w.chosen and w.scheduled == 1


def test_the_watch_waits_while_the_list_is_open_and_outlives_errors(screen, monkeypatch):
    screen[:] = [READER]
    w = Window(grab=".!combobox.popdown", query="my reader")
    w._watch_windows()
    assert w.selected is None and w.scheduled == 1
    monkeypatch.setattr(viewers, "list_windows", _fail)
    w = Window(query="my reader")
    w._watch_windows()
    assert w.selected is None and w.scheduled == 1


def test_no_watch_without_window_capture(monkeypatch):
    monkeypatch.setattr(viewers, "IS_WINDOWS", False)
    w = Window(query="my reader")
    w._watch_windows()
    w._rescan_windows()
    assert w.scheduled == 0 and not w.chosen


def test_a_viewer_closed_and_opened_again_is_chosen_again_only_when_it_was_named(screen, monkeypatch):
    reopened = WindowInfo(hwnd=7, title=YOMIZUQ.title, class_name=YOMIZUQ.class_name, pid=9, rect=YOMIZUQ.rect)
    closed = {YOMIZUQ.hwnd}
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: hwnd not in closed)
    for query, again in (("Yomizuq", True), ("", False)):
        w = Window([YOMIZUQ, NOTEPAD], selected=YOMIZUQ, query=query)
        w.window_box.index = 0
        screen[:] = [NOTEPAD]  # closed: nothing showing the book yet, the choice stays as it was
        w._rescan_windows()
        assert w.selected is YOMIZUQ and w.window_box["values"] == [NOTEPAD.label()]
        screen[:] = [NOTEPAD, reopened]
        w._rescan_windows()
        assert (w.selected is reopened) == again, query  # (not named: the chooser preselects it, the person chooses)
    hidden = WindowInfo(hwnd=8, title="My Reader", class_name="Reader", pid=3, rect=(0, 0, 10, 10))
    w = Window([hidden], selected=hidden, query="My Reader")  # not listed (on another desktop) but still there: left
    screen[:] = [READER]
    w._rescan_windows()
    assert w.selected is hidden


CHAT = WindowInfo(hwnd=4, title="Yomizuq画面翻訳アプリ - Chat - Google Chrome", class_name="Chrome_WidgetWin_1", pid=4,
                  rect=(0, 0, 1600, 1000))
STORE = WindowInfo(hwnd=5, title="見本の物語 1 - FOLIO☆QAT - Google Chrome", class_name="Chrome_WidgetWin_1", pid=5,
                    rect=(0, 0, 1000, 800))
BOOKISH = WindowInfo(hwnd=6, title="Book club notes - Google Chrome", class_name="Chrome_WidgetWin_1", pid=6,
                     rect=(0, 0, 900, 700))


LEARNED = ("Yomizuq - Google Chrome", "Yomizuq for PC", "FOLIO☆QAT", "BookZumo!Reader", "ebookqat - Microsoft Edge",
           "Yomizuq", "見本の物語 1 - FOLIO☆QAT", "ズモリカ", "Yomizuq: 見本の物語 1", "【Yomizuq】 本")
NEVER = ("Facebook - Google Chrome", "Book1 - Excel", "Bookmarks - Google Chrome", "Notebook - OneNote",
         "notes.txt - Notepad", "Booking.com - Microsoft Edge", "Yomizuq画面翻訳アプリ - Chat - Google Chrome",
         "Yomizuq画面翻訳アプリ", "ebookqatese study notes", "My e-book sale - Google Chrome")


def test_what_looks_like_a_viewer():
    assert looks_like_viewer("Zumo Books") and looks_like_viewer("見本の物語 1 - 電子書籍")
    for title in (*LEARNED, *NEVER):  # nothing learned: a viewer's own name is a word like any other
        assert not looks_like_viewer(title), title
    _learned()
    for title in (*LEARNED, "Zumo Books"):
        assert looks_like_viewer(title), title
    for title in NEVER:
        assert not looks_like_viewer(title), title
    assert not looks_like_viewer(CHAT)
    assert looks_like_viewer(YOMIZUQ) and looks_like_viewer(STORE)


def test_the_readers_tab_comes_first_not_a_chat_page_about_the_viewer(screen):
    _learned()
    assert viewers.offered([CHAT, NOTEPAD, YOMIZUQ]) == ([YOMIZUQ, CHAT, NOTEPAD], YOMIZUQ)  # (the chat page is larger)
    assert viewers.offered([CHAT, NOTEPAD]) == ([CHAT, NOTEPAD], None)  # no reader: the chat page is not taken for one
    assert viewers.offered([BOOKISH, YOMIZUQ])[1] == YOMIZUQ  # the viewer learned before a page with "Book" in it
    assert viewers.offered([YOMIZUQ, STORE, NOTEPAD])[1] == YOMIZUQ  # two readers: the first, for the person to confirm


def test_a_named_window_is_chosen_by_its_tab_title(screen):
    screen[:] = [CHAT, YOMIZUQ]  # (nothing learned: a name given needs nothing learned)
    w = Window(query="Yomizuq")
    w.refresh_windows(select="Yomizuq")
    assert w.selected == YOMIZUQ and w.chosen == [(YOMIZUQ, True)]
    w = Window(query="Yomizuq画面")
    w.refresh_windows()  # (no viewer followed: the name the window was started with)
    assert w.selected == CHAT


def test_a_name_that_fits_several_windows_takes_the_viewer_among_them(screen):
    _learned()
    other = WindowInfo(hwnd=9, title="Yomizuqメモ.txt - Notepad", class_name="Notepad", pid=9, rect=(0, 0, 500, 400))
    screen[:] = [other, YOMIZUQ]
    w = Window()
    w.refresh_windows(select="yomiz")  # starts both titles: the one that looks like a viewer
    assert w.selected == YOMIZUQ
