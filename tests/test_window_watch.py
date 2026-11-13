"""A viewer opened after TASlation: the list rescans as it opens, and a watch picks the viewer until one is chosen -
one remembered on this computer, or one whose title has a reading word; a viewer used for the first time is left to
the reader. Every store and viewer named below is invented (test data)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from taslation import viewerparts
from taslation.capture import WindowInfo
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
    """The parts of the App that the list and the watch use."""

    _rescan_windows = app_mod.App._rescan_windows
    _watch_windows = app_mod.App._watch_windows

    def __init__(self, windows=(), selected=None, grab="", query=""):
        self.windows = list(windows)
        self.window_box = Box()
        self.window_box["values"] = [w.label() for w in self.windows]
        self.selected = selected
        self.window_query = query
        self.tk = SimpleNamespace(call=lambda *args: grab)
        self.refreshed: list[str | None] = []
        self.scheduled = 0
        self._tied_said: tuple[int, ...] = ()

    def refresh_windows(self, select=None):  # as the App's: the named window, else the one viewer (several: said)
        self.refreshed.append(select)
        self.selected, tied = viewers.choose_viewer(viewers.list_windows(), select or "")
        if tied:
            self._tied_said = tuple(w.hwnd for w in tied)

    def _on_window_selected(self, picked=False, named=False):  # as the App's: the window the list shows becomes the viewer
        self.selected = self.windows[self.window_box.current()]

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
    assert w.window_box.current() == 1 and w.selected is NOTEPAD and not w.refreshed
    values = w.window_box["values"]
    w._rescan_windows()  # nothing changed: nothing replaced
    assert w.window_box["values"] is values
    monkeypatch.setattr(viewers, "list_windows", _fail)
    w._rescan_windows()
    assert w.windows == [YOMIZUQ, NOTEPAD]


def test_the_watch_picks_a_viewer_opened_later_then_stops(screen):
    _learned()
    screen[:] = [NOTEPAD]
    w = Window([NOTEPAD])
    w._watch_windows()
    assert not w.refreshed and w.selected is None and w.scheduled == 1  # no viewer yet: look again
    screen[:] = [YOMIZUQ, NOTEPAD]
    w._watch_windows()
    assert w.refreshed == [""] and w.selected == YOMIZUQ and w.scheduled == 1  # chosen: no more looking
    w._watch_windows()
    assert w.refreshed == [""] and w.scheduled == 1


def test_with_nothing_remembered_the_watch_leaves_a_new_viewer_to_the_reader_but_takes_a_reading_word(screen):
    screen[:] = [YOMIZUQ, NOTEPAD]  # a viewer used for the first time on this computer
    w = Window([YOMIZUQ, NOTEPAD])
    w._watch_windows()
    assert not w.refreshed and w.selected is None and w.scheduled == 1  # the reader picks it in the Viewer list
    shelf = WindowInfo(hwnd=11, title="見本の物語 1 - Zumo Books - Google Chrome", class_name="Chrome_WidgetWin_1",
                       pid=11, rect=(0, 0, 1000, 800))
    screen[:] = [YOMIZUQ, NOTEPAD, shelf]
    w._watch_windows()
    assert w.refreshed == [""] and w.selected == shelf  # "Books": a reading word


def test_the_watch_looks_for_the_named_window_too(screen):
    screen[:] = [READER, NOTEPAD]
    w = Window(query="my reader")
    w._watch_windows()
    assert w.refreshed == ["my reader"] and w.selected == READER and w.scheduled == 0


def test_the_watch_waits_while_the_list_is_open_and_outlives_errors(screen, monkeypatch):
    screen[:] = [YOMIZUQ]
    w = Window(grab=".!combobox.popdown")
    w._watch_windows()
    assert not w.refreshed and w.selected is None and w.scheduled == 1
    monkeypatch.setattr(viewers, "list_windows", _fail)
    w = Window()
    w._watch_windows()
    assert w.selected is None and w.scheduled == 1


def test_no_watch_without_window_capture(monkeypatch):
    monkeypatch.setattr(viewers, "IS_WINDOWS", False)
    w = Window()
    w._watch_windows()
    w._rescan_windows()
    assert w.scheduled == 0 and not w.refreshed


def test_a_viewer_closed_and_opened_again_is_chosen_again_as_the_list_opens(screen, monkeypatch):
    reopened = WindowInfo(hwnd=7, title=YOMIZUQ.title, class_name=YOMIZUQ.class_name, pid=9, rect=YOMIZUQ.rect)
    closed = {YOMIZUQ.hwnd}
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: hwnd not in closed)
    w = Window([YOMIZUQ, NOTEPAD], selected=YOMIZUQ)
    w.window_box.index = 0
    screen[:] = [NOTEPAD]  # closed: nothing showing the book yet, the choice stays as it was
    w._rescan_windows()
    assert w.selected is YOMIZUQ and w.window_box["values"] == [NOTEPAD.label()]
    screen[:] = [NOTEPAD, reopened]
    w._rescan_windows()
    assert w.selected is reopened and w.window_box.current() == 1
    hidden = WindowInfo(hwnd=8, title="My Reader", class_name="Reader", pid=3, rect=(0, 0, 10, 10))
    w = Window([hidden], selected=hidden)  # not listed (on another desktop) but still there: left alone
    screen[:] = [READER]
    w._rescan_windows()
    assert w.selected is hidden


CHAT = WindowInfo(hwnd=4, title="Yomizuq画面翻訳アプリ - Claude - Google Chrome", class_name="Chrome_WidgetWin_1", pid=4,
                  rect=(0, 0, 1600, 1000))
STORE = WindowInfo(hwnd=5, title="見本の物語 1 - FOLIO☆QAT - Google Chrome", class_name="Chrome_WidgetWin_1", pid=5,
                    rect=(0, 0, 1000, 800))
BOOKISH = WindowInfo(hwnd=6, title="Book club notes - Google Chrome", class_name="Chrome_WidgetWin_1", pid=6,
                     rect=(0, 0, 900, 700))


LEARNED = ("Yomizuq - Google Chrome", "Yomizuq for PC", "FOLIO☆QAT", "BookZumo!Reader", "ebookqat - Microsoft Edge",
           "Yomizuq", "見本の物語 1 - FOLIO☆QAT", "ズモリカ", "Yomizuq: 見本の物語 1", "【Yomizuq】 本")
NEVER = ("Facebook - Google Chrome", "Book1 - Excel", "Bookmarks - Google Chrome", "Notebook - OneNote",
         "notes.txt - Notepad", "Booking.com - Microsoft Edge", "Yomizuq画面翻訳アプリ - Claude - Google Chrome",
         "Yomizuq画面翻訳アプリ", "ebookqatese study notes", "My e-book sale - Google Chrome")


def test_what_looks_like_a_viewer():
    assert app_mod.looks_like_viewer("Zumo Books") and app_mod.looks_like_viewer("見本の物語 1 - 電子書籍")
    for title in (*LEARNED, *NEVER):  # nothing learned: a viewer's own name is a word like any other
        assert not app_mod.looks_like_viewer(title), title
    _learned()
    for title in (*LEARNED, "Zumo Books"):
        assert app_mod.looks_like_viewer(title), title
    for title in NEVER:
        assert not app_mod.looks_like_viewer(title), title
    assert not app_mod.looks_like_viewer(CHAT)
    assert app_mod.looks_like_viewer(YOMIZUQ) and app_mod.looks_like_viewer(STORE)


class Choosing(Window):
    """The App's own choice of the viewer, over the stand-in's list, its status line recorded."""

    refresh_windows = app_mod.App.refresh_windows

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.said: list[str] = []

    def say(self, key, **_values):
        self.said.append(key)


def test_the_window_chooses_the_readers_tab_not_a_chat_page_about_the_viewer(screen):
    _learned()
    screen[:] = [CHAT, NOTEPAD, YOMIZUQ]  # the chat page is the largest window, as in the incident
    w = Choosing()
    w.refresh_windows()
    assert w.selected == YOMIZUQ and w.window_box.current() == 2 and not w.said
    screen[:] = [CHAT, NOTEPAD]  # no reader: the chat page is not taken for one
    w = Choosing()
    w.refresh_windows()
    assert w.selected is None and not w.said


def test_a_named_window_is_chosen_by_its_tab_title(screen):
    screen[:] = [CHAT, YOMIZUQ]  # (nothing learned: a name given needs nothing learned)
    w = Choosing(query="Yomizuq")
    w.refresh_windows(select="Yomizuq")
    assert w.selected == YOMIZUQ
    w = Choosing(query="Yomizuq画面")
    w.refresh_windows(select="Yomizuq画面")
    assert w.selected == CHAT


def test_a_surer_viewer_wins_and_equals_are_left_to_the_reader_said_once(screen):
    _learned()
    screen[:] = [BOOKISH, YOMIZUQ]  # the viewer learned before a page with "Book" in its title
    w = Choosing()
    w.refresh_windows()
    assert w.selected == YOMIZUQ
    screen[:] = [YOMIZUQ, STORE, NOTEPAD]  # two readers: TASlation does not guess
    w = Choosing()
    w.refresh_windows()
    assert w.selected is None and w.window_box.current() == -1
    assert w.said == ["Several windows look like a viewer: pick the right one in the Viewer list."]
    assert w._tied_said == (YOMIZUQ.hwnd, STORE.hwnd)
    w._watch_windows()  # the same two: not said again, the watch goes on
    assert len(w.said) == 1 and w.selected is None and w.scheduled == 1
    screen[:] = [YOMIZUQ, NOTEPAD]  # one of them closed: the other is chosen
    w._watch_windows()
    assert w.selected == YOMIZUQ and w._tied_said == ()


def test_a_name_that_fits_several_windows_takes_the_viewer_among_them(screen):
    _learned()
    other = WindowInfo(hwnd=9, title="Yomizuqメモ.txt - Notepad", class_name="Notepad", pid=9, rect=(0, 0, 500, 400))
    screen[:] = [other, YOMIZUQ]
    w = Choosing()
    w.refresh_windows(select="yomiz")  # starts both titles: the one that looks like a viewer
    assert w.selected == YOMIZUQ
