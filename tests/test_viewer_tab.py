"""A browser window chosen for the book is read only while its tab is the one chosen: its title, the same book's
(`capture.still_the_book`), or one the rules learned on this computer take for the same viewer's (a viewer's part at
its start or its end, `viewerparts.shares_an_end`: another book in it, followed as the window chosen again). While
another tab shows nothing of it is captured for reading (`OtherTab`, before the capture and right after it), the
follow under way ends, the lettering hides and takes no mouse (`SeeThrough.set_away`), the right pane says so in one
line, nothing is learned; the book's tab back, it is looked at at once; the book's tab dragged out into a window of
its own is followed there. The viewer chooser says under its list to bring the book's tab to the front first. A
browser window the person picked is on trial until a frame under its tab is judged a page of a book
(`bookpage.judge`, stubbed here; tests/test_bookpage.py judges pages): nothing of it is read or learned before, a frame
judged no book's page has the right pane say so at once and how to choose the window again (one the layout cannot tell
of after a while), Translate reads the frame on show whatever it was judged and lettering read there ends the trial,
and a tab that looks like a viewer's is followed as the chosen one. A viewer known here - an area set by hand for it,
or a book read in it before by what viewers.json remembers - is never on trial. No window, no browser:
tools/standin_e2e.py's tab scenarios play it on the stand-in viewer."""
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
    _pick_wait = viewers.ViewerMixin._pick_wait
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


# ------------------------------------------------------------------ a browser window picked, on trial
NOTES = _as(BOOK, "Notes - Google Chrome")  # (the tab in front as the person picked the window)
SHELF = "Moon Road 2 | My Book Shelf - Google Chrome"  # (a reading word: no viewer's part learned)
BEFORE = "Star Road 1 - Reading Site - Google Chrome"  # (a title chosen before by itself)


class Pick(Tabs):
    """`Tabs` with the pick on trial: its frames judged, its page read, what is learned."""

    _pick_lets = viewers.ViewerMixin._pick_lets
    _pick_read = viewers.ViewerMixin._pick_read
    _pick_tab_kept = viewers.ViewerMixin._pick_tab_kept
    _learn_viewer = viewers.ViewerMixin._learn_viewer

    def _area_box(self, image):
        return 0, 0, image.width, image.height


@pytest.fixture
def pick(monkeypatch):
    known = viewerparts.Memory(None, {"parts": ["FOLIO☆QAT"], "titles": ["Star Road 1 - Reading Site"]})
    monkeypatch.setattr(viewerparts, "current", lambda: known)
    learned: list[tuple] = []
    monkeypatch.setattr(viewerparts, "chosen", lambda win: learned.append(("chosen", win.title)) or [])
    monkeypatch.setattr(viewerparts, "corrected", lambda win, parts=(): learned.append(("corrected", win.title)))
    titles = {NOTES.hwnd: NOTES.title}
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: hwnd in titles)
    monkeypatch.setattr(viewers, "window_title", lambda hwnd: titles[hwnd])
    monkeypatch.setattr(viewers, "time", SimpleNamespace(monotonic=lambda: clock.now))
    judged: list[int] = []

    def judge(rgb):  # (a frame's verdict by its grey level: 10 "not", 20 "unsure", 30 "book")
        judged.append(int(rgb[0, 0, 0]))
        return {10: "not", 20: "unsure", 30: "book"}[int(rgb[0, 0, 0])]

    monkeypatch.setattr(viewers.bookpage, "judge", judge)
    p = Pick(NOTES)
    p._pick_trial = {"since": clock.now}
    p.titles, p.clock, p.learned, p.judged = titles, clock, learned, judged
    return p


def frame(level: int) -> Image.Image:
    return Image.new("RGB", (64, 48), (level, level, level))


def right_lines(app) -> list[str]:
    state = {**vars(app), "selected": None, "status_var": SimpleNamespace(get=lambda: "")}
    return [r.text for r in ui.right_rows(SimpleNamespace(**state))[0]]


def test_on_trial_a_tab_that_looks_like_a_viewer_s_is_followed_as_the_chosen_one(pick):
    for title, kind in ((SHELF, "viewer"), (BEFORE, "viewer"), (NEXT_BOOK, "viewer"), (OTHER, "other")):
        pick.titles[NOTES.hwnd] = title
        assert pick._tab_of(title) == kind, title
    pick._pick_trial = None  # (once a page was read under the tab picked: the rule as ever)
    assert [pick._tab_of(t) for t in (SHELF, BEFORE, NEXT_BOOK)] == ["other", "other", "viewer"]
    pick._pick_trial = {"since": pick.clock.now}
    pick.titles[NOTES.hwnd] = SHELF
    assert pick._tab_now() == "viewer" and pick.calls[-1] == ("after", 0, "_follow_tab")
    assert pick.learned == []  # (nothing learned of either tab)


def test_on_trial_the_right_pane_says_no_page_was_found_after_a_while_with_nothing_read(pick):
    from taslation.ui.constants import PICK_AGAIN, PICK_NO_PAGE, PICK_NOTHING_S

    assert pick._tab_now() == "book" and not pick._pick_nothing
    pick.clock.now += PICK_NOTHING_S - 1
    pick._tab_now()
    assert not pick._pick_nothing and PICK_NO_PAGE not in right_lines(pick)
    pick.clock.now += 1
    pick._tab_now()
    assert pick._pick_nothing and PICK_NO_PAGE in right_lines(pick)
    pick.busy = True  # (a page job under way: the wait begins again)
    pick._tab_now()
    assert not pick._pick_nothing
    pick.busy = False
    pick.clock.now += PICK_NOTHING_S
    pick._tab_now()
    assert pick._pick_nothing
    pick.titles[NOTES.hwnd] = OTHER  # (another tab, not a viewer's: said, and how to have it read)
    assert pick._tab_now() == "other" and not pick._pick_nothing
    assert right_lines(pick) == [TAB_AWAY, PICK_AGAIN]
    pick._pick_trial = None
    assert right_lines(pick) == [TAB_AWAY]


def test_on_trial_a_frame_judged_no_book_s_page_is_not_read_and_said_at_once(pick):
    from taslation.ui.constants import PICK_NO_PAGE, PICK_NOTHING_S

    assert not pick._pick_lets(frame(10))  # (a page of text in the tab picked: nothing read)
    assert pick._pick_nothing and PICK_NO_PAGE in right_lines(pick) and pick.learned == []
    pick._tab_now()  # (the wait's own time not over: the verdict holds while that tab is in front)
    assert pick._pick_nothing and pick._pick_trial is not None
    assert not pick._pick_lets(frame(10)) and pick.judged == [10]  # (the same frame: judged once)
    pick.titles[NOTES.hwnd] = OTHER
    assert pick._tab_now() == "other" and not pick._pick_nothing  # (another tab: TAB_AWAY says it)
    pick.titles[NOTES.hwnd] = NOTES.title
    pick._tab_now()
    assert pick._pick_nothing  # (back, the same frame on show)
    assert not pick._pick_lets(frame(20)) and not pick._pick_nothing  # (a frame the layout cannot tell of: waits)
    pick.clock.now += PICK_NOTHING_S
    pick._tab_now()
    assert pick._pick_nothing and pick._pick_trial is not None and pick.learned == []


def test_on_trial_a_frame_judged_a_book_s_page_is_read_and_its_lettering_under_the_tab_chosen_ends_the_trial(pick):
    assert not pick._pick_lets(frame(20))
    assert pick._pick_lets(frame(30))  # (a page turned: judged in its turn, read)
    assert pick._pick_trial["asked"] and not pick._pick_nothing and pick.learned == []
    pick._pick_read(SimpleNamespace(regions=[object()]))  # (its lettering read, the tab chosen still in front)
    assert pick._pick_trial is None and pick.learned == [("chosen", NOTES.title)]
    assert pick._pick_lets(frame(10)) and pick.judged == [20, 30]  # (no trial: every frame read, none judged)


def test_on_trial_a_page_read_as_another_tab_came_teaches_nothing_and_a_frame_after_it_is_not_read(pick):
    # the book's tab brought to the front: its first frame captured before its title was seen (the title comes a
    # moment later), read, and its lettering read while that tab's title is in front - not the tab picked with
    assert pick._pick_lets(frame(30))
    pick.titles[NOTES.hwnd] = OTHER
    pick._pick_read(SimpleNamespace(regions=[object()]))
    assert pick._pick_trial is not None and pick.learned == [] and pick._pick_trial["since"] == pick.clock.now
    assert not pick._pick_lets(frame(30))  # (a frame asked for as that tab came: not read, nor judged again)
    assert pick.judged == [30]
    pick.titles[NOTES.hwnd] = NOTES.title  # (the tab picked with back: its page read, its lettering ends the trial)
    assert pick._pick_lets(frame(30))
    pick._pick_read(SimpleNamespace(regions=[object()]))
    assert pick._pick_trial is None and pick.learned == [("chosen", NOTES.title)]


def test_on_trial_translate_reads_the_frame_on_show_whatever_it_was_judged_and_lettering_read_so_ends_the_trial(
        pick):
    from taslation.ui.constants import PICK_NO_PAGE, PICK_NOTHING_S

    pick._pick_read(SimpleNamespace(regions=[object()]))  # (a page job of no frame asked for: nothing)
    assert pick._pick_trial is not None and pick.learned == []
    assert not pick._pick_lets(frame(10)) and pick._pick_nothing  # (judged no book's page: Auto reads nothing)
    assert pick._pick_lets(frame(10), asked=True) and pick._pick_trial["asked"]  # (Translate: read all the same)
    assert not pick._pick_nothing and PICK_NO_PAGE not in right_lines(pick) and pick.judged == [10]
    pick._pick_read(SimpleNamespace(regions=[]))  # (nothing to letter on it: the trial goes on)
    assert pick._pick_trial is not None and pick.learned == []
    pick.titles[NOTES.hwnd] = OTHER
    assert not pick._pick_lets(frame(30), asked=True)  # (a frame of another tab: never read, not even when asked)
    pick.titles[NOTES.hwnd] = NOTES.title
    assert pick._pick_lets(frame(20), asked=True) and pick._pick_trial["asked"]
    pick._pick_read(SimpleNamespace(regions=[]))  # (a page with nothing to letter: the wait begins again)
    assert pick.learned == [] and pick._pick_trial["since"] == pick.clock.now and not pick._pick_trial["asked"]
    pick.clock.now += PICK_NOTHING_S
    pick._tab_now()
    assert pick._pick_nothing
    assert pick._pick_lets(frame(20), asked=True)
    pick._pick_read(SimpleNamespace(regions=[object()]))
    assert pick._pick_trial is None and not pick._pick_nothing and pick.learned == [("chosen", NOTES.title)]
    pick._pick_read(SimpleNamespace(regions=[object()]))  # (no trial: nothing more)
    assert pick.learned == [("chosen", NOTES.title)]


def test_the_page_box_a_tab_with_no_page_gave_on_trial_is_forgotten_and_none_is_looked_for_meanwhile(monkeypatch):
    forgot = []
    app = SimpleNamespace(_pick_trial={"since": 0.0, "verdict": "not"}, _pick_nothing=False, busy=False,
                          _forget_page_area=lambda: forgot.append(1), _page_areas={})
    monkeypatch.setattr(viewers.time, "monotonic", lambda: 1.0)
    viewers.ViewerMixin._pick_wait(app, "book")
    assert app._pick_nothing and forgot == [1]  # (said: what the tab gave as its page box forgotten)
    viewers.ViewerMixin._pick_wait(app, "book")
    assert forgot == [1]  # (once, as it comes to say so)
    live.LiveViewMixin._find_page(app, Image.new("RGB", (40, 30)))  # (no window chosen in the fake: none needed)
    assert app._page_areas == {}
    app._pick_trial["verdict"] = "unsure"
    app._pick_nothing = False
    viewers.ViewerMixin._pick_wait(app, "book")  # (an "unsure" frame: said after PICK_NOTHING_S only)
    assert not app._pick_nothing and forgot == [1]


def test_a_viewer_known_here_is_never_on_trial(monkeypatch, tmp_path):
    from test_window_state import Chooser

    from taslation.pagekeys import Profiles

    titled = viewerparts.Memory(None, {"parts": ["FOLIO☆QAT"], "titles": ["Star Road 1 - Reading Site"]})
    monkeypatch.setattr(viewerparts, "current", lambda: titled)
    learned: list[str] = []
    monkeypatch.setattr(viewerparts, "chosen", lambda win: learned.append(win.title) or [])
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(viewers, "show_minimised", lambda app, win: False)
    picks = [(BOOK, "read"),  # (a viewer's part at its end: a book read in it before)
             (_as(BOOK, BEFORE), "read"),  # (its tab title chosen before: lettering read under it)
             (_as(BOOK, "Moon Road 2 - Reading Site - Google Chrome"), "read"),  # (another book of that viewer)
             (NOTES, "")]  # (nothing known of it)
    for win, known in picks:
        w = Chooser([win])
        w.window_box.index = 0
        w._on_window_selected(picked=True)
        assert w._viewer_known == known and (w._pick_trial is None) == bool(known), win.title
    assert learned == [BOOK.title, BEFORE, "Moon Road 2 - Reading Site - Google Chrome"]  # (remembered at once)
    profiles = Profiles(tmp_path / "profiles.json")
    profiles.set_margins(NOTES, (0, 85, 0, 0))  # (an area set by hand for it)
    w = Chooser([NOTES])
    w.profiles = profiles
    w.window_box.index = 0
    w._on_window_selected(picked=True)
    assert w._viewer_known == "area" and w._pick_trial is None


def test_an_area_set_in_the_window_on_trial_ends_the_trial(pick, tmp_path):
    from taslation.pagekeys import Profiles

    pick.profiles = Profiles(tmp_path / "profiles.json")
    pick.settings = SimpleNamespace(margins=(0, 0, 0, 0))
    pick.say = pick._look_soon = lambda *a, **k: None
    pick._area_chosen = viewers.ViewerMixin._area_chosen.__get__(pick)
    pick._area_chosen((0, 85, 1200, 900), (1200, 900))
    assert pick._pick_trial is None and pick._viewer_known == "area" and pick.learned == [("chosen", NOTES.title)]
    assert pick.profiles.margins_for(NOTES) == (0, 85, 0, 0)


def test_on_trial_a_frame_that_cannot_be_judged_is_read_and_lettering_ends_the_trial(pick, monkeypatch):
    def broken(rgb):
        raise RuntimeError("no judgement")

    monkeypatch.setattr(viewers.bookpage, "judge", broken)
    assert pick._pick_lets(frame(20)) and pick._pick_trial["asked"]
    pick._pick_read(SimpleNamespace(regions=[object()]))
    assert pick._pick_trial is None and pick.learned == [("chosen", NOTES.title)]


class NewPage:
    """What `live.LiveViewMixin._on_new_page` and `_early_allowed` use, the page job's start recorded."""

    _on_new_page = live.LiveViewMixin._on_new_page
    _early_allowed = live.LiveViewMixin._early_allowed
    _early_on = live.LiveViewMixin._early_on

    def __init__(self, lets: bool):
        self.lets, self.started, self._start_pending = lets, [], None
        self.ready, self.busy, self._early, self._auto_last = True, False, None, None
        self.auto_var = SimpleNamespace(get=lambda: True)
        self.settings = SimpleNamespace(early_start=True)
        self.selected = BOOK
        self._enlarge_asked = BOOK.hwnd

    def _pick_lets(self, image, asked=False):
        return self.lets

    def _follows_events(self):
        return True

    def _held_in_viewer(self):
        return False

    def _black_open(self):
        return False

    def _enlarge_first(self):
        pass

    def _starts_book(self, image):
        return False

    def _all_cached(self, image):
        return False

    def _start_translate(self, image, thumb=None, complete=None):
        self.started.append(image)


def test_a_page_job_starts_only_on_a_frame_the_pick_on_trial_lets_be_read():
    page = frame(30)
    held, let = NewPage(False), NewPage(True)
    held._on_new_page(page)
    let._on_new_page(page)
    assert held.started == [] and let.started == [page]
    assert not held._early_allowed(None, page, None) and let._early_allowed(None, page, None)


def test_a_browser_window_picked_is_on_trial_and_one_of_another_program_is_learned_at_once(monkeypatch, memory):
    from test_window_state import Chooser

    learned: list[str] = []
    monkeypatch.setattr(viewerparts, "chosen", lambda win: learned.append(win.title) or [])
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(viewers, "show_minimised", lambda app, win: False)
    shelf = _as(BOOK, SHELF)
    images = WindowInfo(hwnd=40, title="000.jpg", class_name="WinUIDesktopWin32WindowClass", pid=40, rect=(0, 0, 9, 9))
    w = Chooser([NOTES, images])
    w.window_box.index = 0
    w._on_window_selected(picked=True)
    assert w._pick_trial is not None and learned == [] and w.selected is NOTES
    w.windows = [shelf, images]  # (followed: the same window chosen again as it is now, its tab a viewer's)
    w._on_window_selected()
    assert w._pick_trial is not None and learned == [] and w.selected is shelf and w.book_var.get() != "Notes"
    w.window_box.index = 1
    w._on_window_selected(picked=True)  # (no browser's: no tab to doubt)
    assert w._pick_trial is None and learned == ["000.jpg"]


def test_the_chooser_says_to_bring_the_book_s_tab_to_the_front_first():
    from taslation.locales.features import viewer_tab
    from taslation.ui.constants import PICK_AGAIN, PICK_NO_PAGE

    assert CHOOSER_TAB in viewer_tab.TEXTS and TAB_AWAY in viewer_tab.TEXTS
    assert PICK_NO_PAGE in viewer_tab.TEXTS and PICK_AGAIN in viewer_tab.TEXTS
    see = __import__("taslation.locales.features.see_through", fromlist=["TEXTS"]).TEXTS
    for line in (PICK_NO_PAGE, PICK_AGAIN):  # (the Menu's entry named as it is in each language)
        for lang, text in viewer_tab.TEXTS[line].items():
            assert see["Viewer..."][lang] in text and see["Menu"][lang] in text, (lang, line)
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
