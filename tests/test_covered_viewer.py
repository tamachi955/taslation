"""Whether a viewer draws while other windows hide it wholly, found out without a key and kept per viewer, and the
page turn that this spares: a browser follows the published rule (Chromium and Firefox stop drawing only under windows
that hide what lies under them), any other viewer is asked to paint itself anew as it is chosen (`capture.ask_repaint`)
and raised for a look only when nothing comes; what was seen goes in its profile ("while_covered", "key_way"), so that a
later session neither raises it nor waits for a posted key at its first key. Also the frames counted while a key's turn
is awaited, and translator mode drawing a cached page at its first frame and completing it once the frame has settled.
Windows' calls are fakes; the follows run on test_follow's stand-in and fake clock."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_follow import VIEWER, _count_frames, _page, setup  # noqa: F401 - setup is test_follow's fixture

from taslation.capture import Raised, WindowInfo, windows
from taslation.pagekeys import KeyWays, Profiles, key_ways
from taslation.regions import PageResult
from taslation.ui import app as app_mod
from taslation.ui import live, reading
from taslation.ui.constants import FRAME_STEP_MS
from taslation.ui.live import BlackViewerMixin

A = app_mod.App
HWND = 7
TK_VIEWER = WindowInfo(hwnd=HWND, title="Book 3 - A Desktop Viewer", class_name="TkTopLevel", pid=7, rect=(0, 0, 960, 720))
BROWSER = WindowInfo(hwnd=HWND, title="Book 3 - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7,
                     rect=(0, 0, 960, 720))
HELPED = "This viewer draws nothing while it is covered: from now on it comes to the front for a moment at each page."


# ------------------------------------------------------------------ Windows' side, on a fake
def _desk(monkeypatch, above_rects, viewer=(100, 100, 900, 700), screen=(0, 0, 1920, 1080), shown=True):
    """A fake user32: the viewer (1) and the windows above it, nearest first (2, 3, ...) with their rectangles."""
    order = {1: 2 if above_rects else 0}
    for n in range(len(above_rects)):
        order[n + 2] = n + 3 if n + 1 < len(above_rects) else 0
    rects = {n + 2: r for n, r in enumerate(above_rects)}
    metrics = {76: screen[0], 77: screen[1], 78: screen[2] - screen[0], 79: screen[3] - screen[1]}
    fake = SimpleNamespace(IsWindow=lambda h: True, GetAncestor=lambda h, f: h, GetWindow=lambda h, f: order[h],
                           IsWindowVisible=lambda h: shown if h == 1 else True, IsIconic=lambda h: False,
                           GetWindowLongW=lambda h, i: 0, GetSystemMetrics=lambda i: metrics[i])
    x0, y0, x1, y1 = viewer
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", fake, raising=False)
    monkeypatch.setattr(windows, "GWL_EXSTYLE", -20, raising=False)
    monkeypatch.setattr(windows, "client_rect_on_screen", lambda hwnd: (x0, y0, x1 - x0, y1 - y0))
    monkeypatch.setattr(windows, "_is_cloaked", lambda hwnd: False)
    monkeypatch.setattr(windows, "_window_rect", lambda hwnd: rects[hwnd])
    return fake


def test_a_viewer_is_hidden_wholly_only_when_the_windows_above_take_in_all_of_it_on_the_screens(monkeypatch):
    _desk(monkeypatch, [(0, 0, 1920, 1080)])  # TASlation full screen over it
    assert windows.fully_covered(1)
    _desk(monkeypatch, [(0, 0, 600, 1080), (600, 0, 1920, 1080)])  # two windows side by side, between them all of it
    assert windows.fully_covered(1)
    _desk(monkeypatch, [(0, 0, 1200, 650)])  # a strip of it stays in sight: it draws as a window in front does
    assert not windows.fully_covered(1)
    _desk(monkeypatch, [(0, 0, 1920, 1080)], viewer=(-400, 100, 900, 700))  # partly off the screens, the rest hidden
    assert windows.fully_covered(1)
    _desk(monkeypatch, [(0, 0, 1920, 1080)], shown=False)  # a window not shown is no covered one
    assert not windows.fully_covered(1)
    _desk(monkeypatch, [])
    assert not windows.fully_covered(1)


def test_a_repaint_is_asked_of_the_top_level_window_with_no_key_no_focus_and_no_change_of_order(monkeypatch):
    asked = []
    fake = SimpleNamespace(IsWindow=lambda h: True, GetAncestor=lambda h, f: 40,
                           RedrawWindow=lambda *a: asked.append(a) or True)  # (nothing else: any other call fails)
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", fake, raising=False)
    assert windows.ask_repaint(41) and asked == [(40, None, None, windows.RDW_INVALIDATE | windows.RDW_ALLCHILDREN)]


def test_a_fresh_frame_is_a_newer_one_of_the_windows_present_size(monkeypatch):
    frame = SimpleNamespace(seq=5, size=(800, 600))
    fits = [True]
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", SimpleNamespace(IsWindow=lambda h: True), raising=False)
    monkeypatch.setattr(windows.wgc, "latest", lambda hwnd, timeout: frame)
    monkeypatch.setattr(windows.wgc, "crop_box", lambda size, bounds: (0, 0, 800, 600) if fits[0] else None)
    monkeypatch.setattr(windows, "_frame_bounds", lambda hwnd: None)
    assert windows.fresh_frame(1, 4) and not windows.fresh_frame(1, 5)
    fits[0] = False  # a frame of the size before
    assert not windows.fresh_frame(1, 4)


# ------------------------------------------------------------------ the profile
def test_what_was_seen_of_a_viewer_is_kept_in_its_profile_and_written_only_when_it_changes(tmp_path, monkeypatch):
    path = tmp_path / "profiles.json"
    profiles = Profiles(path)
    profiles.set_margins(TK_VIEWER, (0, 10, 0, 0))
    assert profiles.covered_for(TK_VIEWER) is None and profiles.key_way_for(TK_VIEWER) == ""
    profiles.set_covered(TK_VIEWER, True)
    profiles.set_key_way(TK_VIEWER, "real")
    entry = next(iter(json.loads(path.read_text(encoding="utf-8")).values()))
    assert entry["while_covered"] == "draws" and entry["key_way"] == "real" and entry["margins"] == [0, 10, 0, 0]
    writes = []
    monkeypatch.setattr(profiles, "_change", lambda change: writes.append(change))
    profiles.set_covered(TK_VIEWER, True)
    profiles.set_key_way(TK_VIEWER, "real")
    profiles.set_key_way(TK_VIEWER, "sometimes")  # (not a way: nothing kept)
    assert writes == []
    again = Profiles(path)  # a later session
    assert again.covered_for(TK_VIEWER) is True and again.key_way_for(TK_VIEWER) == "real"
    again.set_covered(TK_VIEWER, False)
    assert Profiles(path).covered_for(TK_VIEWER) is False


def test_a_session_takes_up_how_the_viewer_took_keys_unless_it_has_seen_it_itself():
    ways = KeyWays()
    ways.seed(1, "real")
    ways.seed(2, "posted")
    ways.seed(3, "")
    assert ways.real(1) and ways.posted(2) and not ways.real(3) and not ways.posted(3)
    ways.learned(4, False, True)
    ways.seed(4, "real")  # seen in this session: that counts
    assert ways.posted(4) and not ways.real(4)


def test_a_viewer_chosen_takes_up_its_key_way_from_a_session_before(hidden_root, tmp_path):
    from test_page_keys import Viewer

    w = Viewer(hidden_root, tmp_path)
    w.profiles.set_key_way(w.selected, "real")
    w._on_window_selected()
    assert key_ways(w).real(w.selected.hwnd)


# ------------------------------------------------------------------ the window: what it concludes
class Looks(BlackViewerMixin):
    """The window's part that raises the viewer and keeps what it saw; `after` keeps its callbacks."""

    _raise_viewer = A._raise_viewer
    _lower_viewer = A._lower_viewer
    _raise_helped = A._raise_helped
    _raise_for_key = A._raise_for_key
    _draws_covered = A._draws_covered
    _note_covered = A._note_covered
    _learned = A._learned
    _look_raised = A._look_raised
    _seen_turn = A._seen_turn
    _learn_covered = A._learn_covered
    _probe_covered = A._probe_covered
    _resizing = A._resizing
    _window_size = A._window_size

    def __init__(self, tmp_path, selected=TK_VIEWER):
        self.settings = SimpleNamespace(page_turn_wait_ms=3000, settle_ms=400)
        self.profiles = Profiles(tmp_path / "profiles.json")
        self.selected = selected
        self.jobs, self.said = [], []
        self.seq = 10
        self.batch, self._batching = None, False

    def after(self, ms, job):
        self.jobs.append(job)
        return job

    def after_cancel(self, job):
        if job in self.jobs:
            self.jobs.remove(job)

    def run(self):
        while self.jobs:
            self.jobs.pop(0)()

    def say(self, text, **params):
        self.said.append(text)

    def _frame_count(self):
        return self.seq

    def _capture(self, hwnd):
        return None


@pytest.fixture
def desk(monkeypatch):
    """The viewer's window as the window sees it: its class, hidden wholly or not, raised and lowered, repaints asked
    for and the frames that come of them (`drawn`: a repaint covered brings one, `raised_draws`: one comes once it is
    raised)."""
    d = SimpleNamespace(cls="TkTopLevel", hidden=True, opaque=False, raised=[], lowered=[], asked=[], drawn=True,
                        raised_draws=True, fresh=False)

    def ask(hwnd):
        d.asked.append(hwnd)
        d.fresh = d.drawn or (bool(d.raised) and len(d.lowered) < len(d.raised) and d.raised_draws)
        return True

    monkeypatch.setattr(live, "IS_WINDOWS", True)
    monkeypatch.setattr(live, "window_class", lambda hwnd: d.cls)
    monkeypatch.setattr(live, "covered_by_opaque", lambda hwnd: d.opaque)
    monkeypatch.setattr(live, "fully_covered", lambda hwnd: d.hidden)
    monkeypatch.setattr(live, "behind_others", lambda hwnd: True)
    monkeypatch.setattr(live, "raise_window", lambda hwnd: d.raised.append(hwnd) or Raised(hwnd, 0))
    monkeypatch.setattr(live, "lower_window", d.lowered.append)
    monkeypatch.setattr(live, "window_rect", lambda hwnd: (0, 0, 960, 720))
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "ask_repaint", ask)
    monkeypatch.setattr(live, "fresh_frame", lambda hwnd, seq: d.fresh)
    return d


def test_a_browser_follows_the_published_rule_and_nothing_is_kept_for_it(tmp_path, desk):
    desk.cls = "Chrome_WidgetWin_1"
    w = Looks(tmp_path, BROWSER)
    assert w._draws_covered(HWND) is True  # under TASlation's own window at WINDOW_ALPHA it draws on
    desk.opaque = True
    assert w._draws_covered(HWND) is False
    w._note_covered(HWND, True)
    w._learned(HWND, True, False)
    assert w.profiles.data == {} and w.said == []
    w._learn_covered(HWND)
    assert desk.asked == [] and desk.raised == []  # no repaint asked of it: the rule tells


def test_what_was_seen_comes_from_this_session_else_from_a_session_before(tmp_path, desk):
    w = Looks(tmp_path)
    assert w._draws_covered(HWND) is None
    w._note_covered(HWND, True)
    assert w._draws_covered(HWND) is True and w.said == []
    later = Looks(tmp_path)  # a later session: the profile tells
    assert later._draws_covered(HWND) is True
    later._raise_for_key(HWND)
    assert desk.raised == []
    later._note_covered(HWND, False)
    later._note_covered(HWND, False)
    assert later.said == [HELPED] and Looks(tmp_path)._draws_covered(HWND) is False  # said once, kept
    later._raise_for_key(HWND)
    assert desk.raised == [HWND]


def test_a_turn_tells_how_the_viewer_draws_only_when_nothing_else_explains_it(tmp_path, desk):
    w = Looks(tmp_path)
    w._seen_turn(HWND, raised=True, pressed=True)  # raised for a look, then pressed: the press turned it
    assert w._draws_covered(HWND) is None and w.said == []
    desk.hidden = False
    w._seen_turn(HWND, raised=False, pressed=False)  # partly in sight: it draws as one in front does
    assert w._draws_covered(HWND) is None
    desk.hidden = True
    w._seen_turn(HWND, raised=False, pressed=True)  # hidden wholly, not raised, and the page came
    assert w._draws_covered(HWND) is True and w.profiles.covered_for(TK_VIEWER) is True
    other = Looks(tmp_path / "other")
    other._seen_turn(HWND, raised=True, pressed=False)  # the posted key turned it, drawn only once raised
    assert other._draws_covered(HWND) is False and other.said == [HELPED]


def test_how_a_viewer_took_a_key_is_kept_for_the_next_session(tmp_path, desk):
    w = Looks(tmp_path)
    w._learned(HWND, False, False)  # a click: nothing new
    assert w.profiles.key_way_for(TK_VIEWER) == ""
    w._learned(HWND, True, False)
    assert w.profiles.key_way_for(TK_VIEWER) == "real" and key_ways(w).real(HWND)
    w._learned(HWND, False, True)
    assert w.profiles.key_way_for(TK_VIEWER) == "posted"


def test_a_viewer_hidden_wholly_that_draws_on_a_repaint_is_known_to_draw_with_no_raise(tmp_path, desk):
    w = Looks(tmp_path)
    done = []
    w._learn_covered(HWND, lambda: done.append(1))
    w.run()
    assert desk.asked == [HWND] and desk.raised == [] and done == [1]
    assert w._draws_covered(HWND) is True and w.profiles.covered_for(TK_VIEWER) is True and w.said == []


def test_a_viewer_that_draws_only_raised_is_raised_once_for_a_look_and_put_back(tmp_path, desk):
    desk.drawn = False
    w = Looks(tmp_path)
    w._learn_covered(HWND)
    w.run()
    assert desk.raised == [HWND] and desk.lowered == [Raised(HWND, 0)] and len(desk.asked) == 2
    assert w._draws_covered(HWND) is False and w.said == [HELPED]


def test_a_viewer_that_draws_neither_way_says_nothing(tmp_path, desk):
    desk.drawn = desk.raised_draws = False
    w = Looks(tmp_path)
    w._learn_covered(HWND)
    w.run()
    assert desk.raised == [HWND] and desk.lowered == [Raised(HWND, 0)]
    assert w._draws_covered(HWND) is None and w.said == []


def test_nothing_is_asked_of_a_viewer_in_sight_known_already_or_no_longer_chosen(tmp_path, desk):
    desk.hidden = False
    w = Looks(tmp_path)
    w._learn_covered(HWND)
    desk.hidden = True
    w._learn_covered(HWND + 1)  # another viewer is chosen by now
    w._note_covered(HWND, True)
    w._learn_covered(HWND)
    w.run()
    assert desk.asked == [] and desk.raised == []


# ------------------------------------------------------------------ the follow: a key's turn
def _ignored_posted_keys(setup, monkeypatch, pressed):
    """A viewer that ignores posted keys: the page turns 0.1 s after a key pressed for real."""
    v = setup.viewer
    monkeypatch.setattr(live, "press_briefly", lambda hwnd, key: pressed.append(setup.clock.now) or
                        v.frames.append((setup.clock.now + 0.1, _page(20 + len(pressed)))) or True)
    monkeypatch.setattr(reading, "press_briefly", lambda hwnd, key: pressed.append(setup.clock.now) or
                        v.frames.append((setup.clock.now + 0.1, _page(20 + len(pressed)))) or True)
    monkeypatch.setattr(reading, "time", live.time)


def _hidden(monkeypatch, hidden=True):
    raised = []
    monkeypatch.setattr(live, "window_class", lambda hwnd: "TkTopLevel")
    monkeypatch.setattr(live, "fully_covered", lambda hwnd: hidden)
    monkeypatch.setattr(live, "behind_others", lambda hwnd: True)
    monkeypatch.setattr(live, "raise_window", lambda hwnd: raised.append(hwnd) or Raised(hwnd, 0))
    monkeypatch.setattr(live, "lower_window", lambda r: None)
    monkeypatch.setattr(live, "window_rect", lambda hwnd: (0, 0, 960, 720))
    return raised


def _started(setup, w):
    w.selected = TK_VIEWER
    w.start()
    setup.clock.run(3)
    w.job_done()


def test_raised_for_a_look_and_then_pressed_for_real_the_viewer_is_not_said_to_draw_nothing(setup, monkeypatch):
    """The first key of a viewer that ignores posted keys and is hidden wholly: raised for a look, then pressed for
    real; the press turned the page, so nothing is concluded of how it draws - no line, and no raise at the next
    keys, which are pressed at once."""
    pressed = []
    _ignored_posted_keys(setup, monkeypatch, pressed)
    raised = _hidden(monkeypatch)
    w = setup.make()
    _started(setup, w)
    sent = setup.clock.now
    w.forward_key("Left")
    setup.clock.run(8)
    assert raised == [HWND] and len(pressed) == 1 and 5.9 <= pressed[0] - sent <= 6.4
    assert HELPED not in w.statuses and w._draws_covered(HWND) is None
    w.job_done()
    sent = setup.clock.now
    w.forward_key("Right")
    setup.clock.run(2)
    assert raised == [HWND] and len(pressed) == 2 and pressed[1] - sent < 0.1


@pytest.mark.parametrize("why", ["known", "in sight"])
def test_a_viewer_known_to_draw_or_partly_in_sight_is_pressed_after_one_wait_with_no_raise(setup, monkeypatch, why):
    pressed = []
    _ignored_posted_keys(setup, monkeypatch, pressed)
    raised = _hidden(monkeypatch, hidden=why == "known")
    w = setup.make()
    _started(setup, w)
    if why == "known":
        w._note_covered(HWND, True)  # (seen as it was chosen, or in a session before)
    sent = setup.clock.now
    w.forward_key("Left")
    setup.clock.run(5)
    assert raised == [] and len(pressed) == 1 and 2.9 <= pressed[0] - sent <= 3.2
    assert [p for _t, p in w.new_pages][-1] is setup.viewer.frames[-1][1]


def test_with_its_frames_counted_a_turn_is_seen_as_its_frame_comes(setup, monkeypatch):
    """The viewer's frames counted (`capture.frame_count`): the turned page is captured within FRAME_STEP_MS of its
    frame, not at the next FOLLOW_STEP_MS, and no more often than the frames and FOLLOW_STEP_MS ask for."""
    _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make()
    _started(setup, w)
    w._all_cached = lambda image: True  # taken on its first frame
    setup.clock.run(5)
    v.captures.clear()
    turned = setup.clock.now + 0.25
    v.frames.append((turned, _page(2)))
    w.forward_key("Left")
    setup.clock.run(0.5)
    assert w.new_pages[-1][1] is v.frames[-1][1]
    assert w.new_pages[-1][0] - turned <= 2 * FRAME_STEP_MS / 1000
    assert len(v.captures) <= 1 + 4  # the frame before the key, a look at the start and every 100 ms, the turn


def test_a_frame_not_changed_since_the_last_capture_is_the_one_before_the_key(setup, monkeypatch):
    _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make()
    _started(setup, w)
    setup.clock.run(5)
    w._capture(HWND)  # (a look: nothing drawn since)
    v.captures.clear()
    v.frames.append((setup.clock.now + 0.25, _page(2)))
    w.forward_key("Left")
    setup.clock.run(0.01)
    assert v.captures == []  # nothing captured for the frame before the key


@pytest.mark.parametrize("counted", [True, False])
def test_in_translator_mode_a_cached_page_is_drawn_at_once_and_completed_once_it_settled(setup, monkeypatch, counted):
    """A page the cache holds whole: drawn from the cache at its first frame (nothing read from it), then completed
    from what it reads once the frame has settled - no new frame for settle_ms, or two frames settle_ms apart
    alike -, once the job drawing it is done."""
    if counted:
        _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make()
    _started(setup, w)
    w.role_var.set("translator")
    w._all_cached = lambda image: True
    jobs = []
    real_start = w._start_translate
    monkeypatch.setattr(w, "_start_translate", lambda image, complete=None, thumb=None, again=None:
                        jobs.append((setup.clock.now, complete)) or real_start(image, complete, thumb, again))
    setup.clock.run(5)
    turned = setup.clock.now + 0.2
    v.frames.append((turned, _page(2)))
    w.forward_key("Left")
    setup.clock.run(0.35)
    assert [c for _t, c in jobs] == [False] and jobs[0][0] - turned <= 0.15  # drawn from the cache at once
    w.job_done(PageResult(image=_page(2), original=_page(2), regions=[], cache_hits=1))
    setup.clock.run(1.5)
    assert [c for _t, c in jobs] == [False, True]  # then completed, once settled
    assert 0.4 <= jobs[1][0] - turned <= 1.0
    w.job_done()
    setup.clock.run(5)
    assert len(jobs) == 2
