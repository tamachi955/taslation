"""A browser window chosen for the book is read only while its tab is the one chosen: its title, the same book's
(`capture.still_the_book`), or one the rules learned on this computer take for the same viewer's (a viewer's part at
its start or its end, `viewerparts.shares_an_end`: another book in it, followed as the window chosen again). While
another tab shows nothing of it is captured for reading (`OtherTab`, before the capture and right after it), the
follow under way ends, the lettering hides and takes no mouse (`SeeThrough.set_away`), the right pane says so in one
line, nothing is learned; the book's tab back, it is looked at at once; the book's tab dragged out into a window of
its own is followed there. The viewer chooser says under its list to bring the book's tab to the front first. No
window, no browser: tools/standin_e2e.py's tab scenarios play it on the stand-in viewer."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from taslation import viewerparts
from taslation.capture import OtherTab, WindowInfo
from taslation.capture import seethrough as window
from taslation.ui import app as app_mod
from taslation.ui import live, viewers
from taslation.ui import seethrough as ui
from taslation.ui.constants import CHOOSER_TAB, TAB_AWAY, TAB_FOLLOW_MS, TAB_WAITING, TAB_WATCH_MS

CHROME = "Chrome_WidgetWin_1"
BOOK = WindowInfo(hwnd=12, title="Star Road 1 - FOLIO☆QAT - Google Chrome", class_name=CHROME, pid=12,
                  rect=(0, 0, 1200, 900), program="chrome.exe")
OTHER = "週末の予定メモ - Google Chrome"
NEXT_BOOK = "Moon Road 2 - FOLIO☆QAT - Google Chrome"


def _as(win: WindowInfo, title: str, hwnd: int | None = None, program: str | None = None) -> WindowInfo:
    return WindowInfo(win.hwnd if hwnd is None else hwnd, title, win.class_name, win.pid, win.rect,
                      win.program if program is None else program)


@pytest.fixture
def memory(monkeypatch):
    """What this computer learned of the viewer: its part at the end of its titles (memory only, nothing written)."""
    known = viewerparts.Memory(None, {"parts": ["FOLIO☆QAT"]})
    monkeypatch.setattr(viewerparts, "current", lambda: known)
    return known


# ------------------------------------------------------------------ which tab is the book's
def test_a_tab_is_the_viewer_s_by_a_part_at_its_start_or_end_or_an_end_a_chosen_window_had():
    parts = viewerparts.Memory(None, {"parts": ["FOLIO☆QAT"]})
    assert viewerparts.viewer_tab(NEXT_BOOK, parts)  # (its end)
    assert viewerparts.viewer_tab("FOLIO☆QAT - Moon Road 2 - Google Chrome", parts)  # (its start)
    assert not viewerparts.viewer_tab(OTHER, parts) and not viewerparts.viewer_tab("Notes - Google Chrome", parts)
    assert not viewerparts.viewer_tab("", parts)
    chosen = viewerparts.Memory(None, {"titles": ["Star Road 1 - Reading Site"]})
    assert viewerparts.viewer_tab("Moon Road 2 - Reading Site - Google Chrome", chosen)  # (`shares_an_end`)
    assert not viewerparts.viewer_tab("Star Road 1 - Reading Site", chosen)  # (a title chosen before by itself: a book's)
    assert not viewerparts.viewer_tab("Moon Road 2 - Other Site", chosen)


class Tabs:
    """What the tab rule of `viewers.ViewerMixin` uses, the rest of the window recorded."""

    _book_in_front = viewers.ViewerMixin._book_in_front
    _tab_of = viewers.ViewerMixin._tab_of
    _tab_now = viewers.ViewerMixin._tab_now
    _tab_seen = viewers.ViewerMixin._tab_seen
    _follow_tab = viewers.ViewerMixin._follow_tab
    _tab_moved_out = viewers.ViewerMixin._tab_moved_out
    _choose_listed = viewers.ViewerMixin._choose_listed
    _viewer_retitled = viewers.ViewerMixin._viewer_retitled

    def __init__(self, selected: WindowInfo):
        self.selected, self.window_query, self.busy = selected, "", False
        self.calls: list[tuple] = []
        self.windows: list[WindowInfo] = []
        self.window_box = _Box()

    def _end_follow(self):
        self.calls.append(("end_follow",))

    def _look_soon(self):
        self.calls.append(("look_soon",))

    def after(self, ms, fn):
        self.calls.append(("after", ms, getattr(fn, "__name__", "")))

    def _on_window_selected(self, picked=False, named=False, same_book=False):
        self.calls.append(("selected", self.windows[self.window_box.index].hwnd, same_book))


class _Box(dict):
    """The Viewer list's combobox: its values, its current entry."""

    def __init__(self):
        super().__init__()
        self.index = -1

    def current(self, index):
        self.index = index


@pytest.fixture
def tabs(monkeypatch, memory):
    titles = {BOOK.hwnd: BOOK.title}
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: hwnd in titles)
    monkeypatch.setattr(viewers, "window_title", lambda hwnd: titles[hwnd])
    monkeypatch.setattr(viewers, "time", SimpleNamespace(monotonic=lambda: clock.now))
    t = Tabs(BOOK)
    t.titles, t.clock = titles, clock
    return t


def test_the_chosen_tab_is_the_book_another_tab_is_not_and_another_book_of_the_viewer_is_followed(tabs):
    assert tabs._tab_now() == "book" and tabs._book_in_front() and tabs.calls == []
    tabs.titles[BOOK.hwnd] = "Star Road 1 - page 2 | FOLIO☆QAT - Google Chrome"  # (the same book's page: as before)
    assert tabs._tab_now() == "book"
    tabs.titles[BOOK.hwnd] = OTHER
    assert tabs._tab_now() == "other" and not tabs._book_in_front() and tabs._tab_away
    assert tabs.calls == [("end_follow",)]  # (once, as it came: a page started early on its frame dropped)
    tabs.titles[BOOK.hwnd] = BOOK.title
    assert tabs._tab_now() == "book" and not tabs._tab_away and tabs.calls[-1] == ("look_soon",)
    tabs.calls.clear()
    tabs.titles[BOOK.hwnd] = NEXT_BOOK  # another book in the same viewer: not read as this one, followed
    assert tabs._tab_now() == "viewer" and not tabs._book_in_front() and not tabs._tab_away
    assert tabs.calls == [("end_follow",), ("after", 0, "_follow_tab")]  # (asked once, not at each look)


def test_a_window_that_is_no_browser_s_has_no_tab(tabs):
    images = WindowInfo(hwnd=11, title="000.jpg", class_name="WinUIDesktopWin32WindowClass", pid=11,
                        rect=(0, 0, 10, 10))
    tabs.selected = images
    tabs.titles[11] = "001.jpg"
    assert tabs._tab_now() == "book" and tabs.calls == []
    tabs.selected = None
    assert tabs._tab_now() == "book"


def test_another_book_of_the_viewer_is_chosen_again_once_no_page_job_runs(tabs, monkeypatch):
    listed = [_as(BOOK, NEXT_BOOK)]
    monkeypatch.setattr(viewers, "list_windows", lambda: listed)
    tabs.titles[BOOK.hwnd] = NEXT_BOOK
    tabs.busy = True
    tabs._follow_tab()
    assert tabs.calls == [("after", TAB_FOLLOW_MS, "_follow_tab")]  # (the job of the book before ends first)
    tabs.busy = False
    tabs._follow_tab()
    assert tabs.calls[-1] == ("selected", BOOK.hwnd, False)  # (chosen again as it is: the book its title names)
    tabs.calls.clear()
    tabs.titles[BOOK.hwnd] = OTHER  # (gone meanwhile: nothing)
    tabs._follow_tab()
    assert tabs.calls == []


def test_the_book_s_tab_dragged_out_is_followed_into_its_own_window(tabs, monkeypatch):
    own = _as(BOOK, BOOK.title, hwnd=30)
    elsewhere = _as(BOOK, BOOK.title, hwnd=31, program="other.exe")  # (another program's window of that title)
    listed = [elsewhere, _as(BOOK, OTHER), own]
    monkeypatch.setattr(viewers, "list_windows", lambda: listed)
    tabs.titles[BOOK.hwnd] = OTHER
    assert tabs._tab_now() == "other"
    assert ("after", 0, "_tab_moved_out") not in tabs.calls  # (not at once: the window dragged out comes after)
    tabs.clock.now += TAB_FOLLOW_MS / 1000
    tabs._tab_now()
    assert tabs.calls[-1] == ("after", 0, "_tab_moved_out")
    tabs._tab_now()
    assert tabs.calls.count(("after", 0, "_tab_moved_out")) == 1  # (then every TAB_WATCH_MS)
    tabs.clock.now += TAB_WATCH_MS / 1000
    tabs._tab_now()
    assert tabs.calls.count(("after", 0, "_tab_moved_out")) == 2
    tabs.busy = True
    tabs._tab_moved_out()
    assert not any(c[0] == "selected" for c in tabs.calls)  # (a page job runs: looked for again later)
    tabs.busy = False
    tabs._tab_moved_out()
    assert tabs.calls[-1] == ("selected", 30, True)  # (the book's name stays: the same book)


def test_the_chooser_says_to_bring_the_book_s_tab_to_the_front_first():
    from taslation.locales.features import viewer_tab

    assert CHOOSER_TAB in viewer_tab.TEXTS and TAB_AWAY in viewer_tab.TEXTS
    for text in viewer_tab.TEXTS.values():
        assert len(text) == 16 and all(v.strip() for v in text.values())
    from taslation.locales.features import viewer_choice

    again = viewer_choice.TEXTS["List again"]
    for lang, line in viewer_tab.TEXTS[CHOOSER_TAB].items():
        assert again[lang] in line  # (the button named as it is in that language)


# ------------------------------------------------------------------ nothing of another tab captured
class Capture:
    _capture = app_mod.App._capture
    _capture_frame = app_mod.App._capture_frame
    _shows_other_tab = app_mod.App._shows_other_tab
    _capture_failed = app_mod.App._capture_failed

    def __init__(self, kinds):
        self.selected = BOOK
        self.kinds, self.said = list(kinds), []

    def _tab_now(self):
        return self.kinds.pop(0) if len(self.kinds) > 1 else self.kinds[0]

    def _covers_viewer(self, hwnd):
        return False

    def say(self, *args, **kwargs):
        self.said.append(args)


def test_nothing_of_another_tab_is_captured_before_or_noted_after(monkeypatch):
    taken, noted = [], []
    monkeypatch.setattr(live, "frame_count", lambda hwnd: 3)
    monkeypatch.setattr(live, "capture_window", lambda hwnd, **kw: taken.append(hwnd) or Image.new("RGB", (8, 8)))
    monkeypatch.setattr(live, "_captured_facts", lambda *a: noted.append(a))
    w = Capture(["other"])
    with pytest.raises(OtherTab):
        w._capture(BOOK.hwnd)
    assert taken == [] and noted == []  # (not captured at all)
    w = Capture(["book", "other"])  # (the tab switched while the frame was taken)
    with pytest.raises(OtherTab):
        w._capture(BOOK.hwnd)
    assert taken == [BOOK.hwnd] and noted == []  # (taken, dropped before anything looked at it)
    w._capture_failed(OtherTab())
    assert w.said == []  # (nothing said at each look: the right pane says it once)


# ------------------------------------------------------------------ the see-through window and the right pane
def test_the_lettering_hides_and_takes_no_mouse_while_another_tab_shows(monkeypatch):
    monkeypatch.setattr(window, "_user32", SimpleNamespace(IsWindow=lambda hwnd: 0, ShowWindow=lambda h, c: 1))
    over = window.SeeThrough()
    seen = []
    over._key_tick = lambda viewer: seen.append(("key", viewer))
    over._edit_take = lambda wanted, sets: seen.append(("mouse", wanted))
    over.follow(5)
    over.set_ground(True)  # (editing: the whole page takes the mouse)
    over._step()
    assert seen == [("key", 5), ("mouse", True)]
    changed = over._changed
    over.set_away(True)
    over.set_away(True)
    assert over._away and over._changed == changed + 1  # (the same again: nothing)
    seen.clear()
    over._step()
    assert seen == [("key", 0), ("mouse", False)]  # (the Insert key let go of, the mouse the viewer's)
    over.set_away(False)
    seen.clear()
    over._step()
    assert seen == [("key", 5), ("mouse", True)]
    assert [n["on"] for n in over.notes if n["ev"] == "away"] == [1, 0]


def test_the_right_pane_says_in_one_line_that_another_tab_shows():
    def rows(**state):
        status = state.pop("status", "")
        app = SimpleNamespace(status_var=SimpleNamespace(get=lambda: status), selected=None, **state)
        return [r.text for r in ui.right_rows(app)[0]]

    assert TAB_AWAY not in rows()
    said = rows(_tab_away=True, status=TAB_WAITING, _status_key=TAB_WAITING)
    assert said == [TAB_AWAY]  # (the waiting line, which says it at more length, left out)
    assert rows(_tab_away=True, status="Looking at the page...") == [TAB_AWAY, "Looking at the page..."]
    assert rows(status=TAB_WAITING, _status_key=TAB_WAITING) == [TAB_WAITING]


def test_the_chooser_has_the_line_under_its_list(hidden_root, monkeypatch):
    from test_viewer_chooser import CHAT, NOTEPAD, FakeApp, _texts

    from taslation.ui import layout
    from taslation.ui import see_menu as sm

    monkeypatch.setattr(layout, "dialog_keys", lambda win, parent, focus=None: None)
    dialog = sm.open_viewer(FakeApp(hidden_root, [CHAT, NOTEPAD]))
    texts = _texts(dialog)
    assert CHOOSER_TAB in texts and texts.index(CHOOSER_TAB) == len(texts) - 1  # (under the list, the last line)
    dialog.destroy()
