"""Following the viewer by events (Settings.follow = "events"): no capture while TASlation is in front and nothing
happens, polling while the viewer itself is (and a look at each new frame it draws), nothing while neither is, one
look when a window comes back to the front, when the viewer's window stops moving or is renamed; a page turned in the
viewer followed until its frame settles, the page started at once and looked at again (a soft picture first, then the
sharp one). Also the pure parts: the decision, the fine detail of a frame, who is in front, Windows' notes. Parts of
the App are borrowed onto a stand-in on the shared hidden root; time is a fake clock."""
from __future__ import annotations

import heapq
import os
import queue
import random
import threading
import tkinter as tk
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import windows_only
from PIL import Image, ImageDraw

from taslation import capture, frames
from taslation.frames import DETAIL_GRID, detail, frames_differ, sharper, thumbnail
from taslation.capture import WindowInfo, windows
from taslation.config import ConfigError, Settings
from taslation.regions import PageResult
from taslation.ui import app as app_mod
from taslation.ui import jobs, live, status
from taslation.ui.live import Following, follow_decision
from taslation.ui.preview import ImageCanvas
from taslation.ui.live import BlackViewerMixin

VIEWER = WindowInfo(hwnd=7, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7, rect=(0, 0, 960, 720))
OWN, BROWSER, OTHER = 101, 7, 303  # windows in front: one of TASlation's, the viewer's, someone else's


def _page(seed: int, soft: int = 1, size=(960, 720)) -> Image.Image:
    """A capture of the viewer showing page *seed*: white paper with strokes of ink; *soft*: drawn from a picture that
    many times smaller first, as a viewer that loads the sharp page later does."""
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    rnd = random.Random(seed)
    for _i in range(900):
        x, y = rnd.randint(4, size[0] - 30), rnd.randint(4, size[1] - 12)
        d.rectangle((x, y, x + rnd.randint(1, 3), y + rnd.randint(4, 10)), fill=(20, 20, 20))
    for _i in range(3):
        x, y = rnd.randint(0, size[0] - 200), rnd.randint(0, size[1] - 150)
        d.rectangle((x, y, x + 180, y + 130), fill=(90, 90, 90))
    if soft > 1:
        img = img.resize((size[0] // soft, size[1] // soft), Image.BILINEAR).resize(size, Image.BILINEAR)
    return img


# ------------------------------------------------------------------ the pure parts
def test_the_decision_from_who_is_in_front_and_the_last_operation():
    d = follow_decision
    assert d("poll", "own", following=False, look_due=False, poll_due=True) == "poll"  # as before, whoever is in front
    assert d("poll", "other", following=True, look_due=True, poll_due=False) == "idle"
    assert d("events", "own", following=False, look_due=False, poll_due=True) == "idle"  # TASlation in front: no polling
    assert d("events", "own", following=True, look_due=True, poll_due=True) == "follow"  # an operation's own captures
    assert d("events", "other", following=True, look_due=False, poll_due=True) == "follow"  # ... to its end
    assert d("events", "own", following=False, look_due=True, poll_due=False) == "look"  # back in front, moved, renamed
    assert d("events", "viewer", following=False, look_due=False, poll_due=True) == "poll"  # pages turned in the viewer
    assert d("events", "viewer", following=False, look_due=False, poll_due=False) == "idle"
    assert d("events", "viewer", following=False, look_due=True, poll_due=True) == "look"
    for look in (False, True):  # neither in front: nothing at all
        assert d("events", "other", following=False, look_due=look, poll_due=True) == "idle"
    # a viewer just chosen, no frame of it on the page yet: a due look is taken whoever is in front
    assert d("events", "other", following=False, look_due=True, poll_due=False, unseen=True) == "look"
    assert d("events", "other", following=False, look_due=False, poll_due=True, unseen=True) == "idle"
    assert d("events", "own", following=True, look_due=True, poll_due=True, unseen=True) == "follow"


def test_a_soft_picture_is_told_from_the_sharp_one_though_their_thumbnails_are_alike():
    assert live.detail is frames.detail and live.sharper is frames.sharper  # one test of sharpness, `frames`'
    for seed in (1, 2):
        sharp, soft = _page(seed), _page(seed, soft=3)
        assert not frames_differ(thumbnail(sharp), thumbnail(soft))  # the same page to every look Auto had
        d_sharp, d_soft = detail(sharp), detail(soft)
        assert d_sharp.shape == (DETAIL_GRID, DETAIL_GRID) and d_sharp.mean() > 1.5 * d_soft.mean()
        assert sharper(d_soft, d_sharp) and not sharper(d_sharp, d_soft) and not sharper(d_sharp, detail(sharp.copy()))
        overlay = sharp.copy()  # the viewer's toolbar over the top of the page: not sharper
        ImageDraw.Draw(overlay).rectangle((0, 0, 960, 50), fill=(40, 40, 40))
        ImageDraw.Draw(overlay).text((6, 6), "Aa  1 / 120", fill=(230, 230, 230))
        assert not sharper(d_sharp, detail(overlay))
        noisy = Image.fromarray(np.clip(np.asarray(sharp, np.int16) + np.random.default_rng(seed).integers(
            -2, 3, (720, 960, 3)), 0, 255).astype(np.uint8))
        assert not sharper(d_sharp, detail(noisy))
    box = (0, 50, 960, 720)  # the capture area only
    assert detail(_page(1), box).shape == (4, 4) and not np.array_equal(detail(_page(1), box), detail(_page(1)))
    blank = Image.new("RGB", (960, 720), "white")
    assert not detail(blank).any() and not sharper(detail(blank), detail(blank)) and not sharper(None, detail(blank))
    assert not detail(Image.new("RGB", (10, 10), "white")).any()  # too small to look at


def test_who_is_in_front():
    own = os.getpid()
    assert capture.front_owner(own, (5, 5, 5), own, viewer=7) == "own"  # the window, a pane, a dialog
    assert capture.front_owner(99, (7, 7, 7), own, viewer=7) == "viewer"
    assert capture.front_owner(99, (8, 8, 7), own, viewer=7) == "viewer"  # a popup the viewer's window owns
    assert capture.front_owner(99, (9, 9, 9), own, viewer=7) == "other"  # another window of the same browser too
    assert capture.front_owner(0, (0, 0, 0), own, viewer=7) == "other"  # nothing in front
    assert capture.front_owner(99, (7, 7, 7), own, viewer=0) == "other"  # no viewer chosen
    assert capture.foreground_owner(0, 7) == "other"


def test_the_callback_only_takes_notes():
    events = windows.WindowEvents()  # no hooks set: the callback alone
    events.viewer = 7
    events._note(None, windows.EVENT_SYSTEM_FOREGROUND, 101, 0, 0, 1, 1)
    events._note(None, windows.EVENT_SYSTEM_FOREGROUND, 101, 0, 0, 1, 1)  # the same window again: one note
    for _step in range(5):  # the viewer's window dragged: one note for the run
        events._note(None, windows.EVENT_OBJECT_LOCATIONCHANGE, 7, windows.OBJID_WINDOW, 0, 1, 1)
    events._note(None, windows.EVENT_OBJECT_LOCATIONCHANGE, None, -9, 0, 1, 1)  # the pointer moving: nothing
    events._note(None, windows.EVENT_OBJECT_NAMECHANGE, 7, -4, 3, 1, 1)  # a part of the page renamed: nothing
    events._note(None, windows.EVENT_OBJECT_NAMECHANGE, 8, 0, 0, 1, 1)  # another window of the browser: nothing
    events._note(None, windows.EVENT_OBJECT_NAMECHANGE, 7, 0, 0, 1, 1)
    events._note(None, windows.EVENT_OBJECT_DESTROY, 7, 0, 0, 1, 1)
    events._note(None, "not an event", object(), None, None, 1, 1)  # never raises
    assert events.front == 101
    assert events.take() == [("front", 101), ("moved", 7), ("renamed", 7), ("closed", 7)] and events.take() == []
    for i in range(windows.MAX_NOTES + 40):  # never taken for long: the newest are kept
        events._add("front", i)
    notes = events.take()
    assert len(notes) == windows.MAX_NOTES and notes[-1] == ("front", windows.MAX_NOTES + 39)


@windows_only
def test_windows_notes_come_through_tks_own_event_loop(tk_root):
    events = capture.WindowEvents.start()
    assert events is not None and events.active
    top = tk.Toplevel(tk_root)
    try:
        top.attributes("-alpha", 0.0)  # on the screen for the events, never seen
        top.geometry("200x120+40+40")
        top.update()
        hwnd = int(windows.user32.GetAncestor(top.winfo_id(), 2))
        assert events.watch(hwnd) and events.viewer == hwnd
        events.take()

        def pump(seconds=0.4):
            import time
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                top.update()
                time.sleep(0.02)

        top.title("renamed by the test")
        pump()
        top.geometry("220x130+60+50")
        pump()
        kinds = [kind for kind, h in events.take() if h == hwnd]
        assert "renamed" in kinds and "moved" in kinds
        events.close()  # unhooked: nothing comes in any more
        top.title("again")
        pump()
        assert not events.take() and not events.active and events.viewer == 0
        assert not events.watch(hwnd)  # no hook on the window in front any more: the viewer cannot be watched
    finally:
        events.close()
        top.destroy()


def test_the_setting(tmp_path):
    assert Settings().follow == "events"
    for value in ("events", "poll"):
        Settings(follow=value).validate()
    with pytest.raises(ConfigError, match="follow"):
        Settings(follow="sometimes").validate()
    path = tmp_path / "taslation.toml"
    path.write_text('follow = "poll"\n', encoding="utf-8")
    assert Settings.from_toml(path).follow == "poll"


# ------------------------------------------------------------------ the live view, following by events
class Clock:
    """Monotonic time that moves only when told, and Tk's after() on it."""

    def __init__(self):
        self.now = 1000.0
        self.jobs: list = []
        self.seq = 0
        self.cancelled: set[str] = set()

    def monotonic(self):
        return self.now

    def after(self, ms, func):
        self.seq += 1
        heapq.heappush(self.jobs, (self.now + ms / 1000, self.seq, func))
        return f"after#{self.seq}"

    def cancel(self, job):
        self.cancelled.add(job)

    def run(self, seconds):
        end = self.now + seconds
        while self.jobs and self.jobs[0][0] <= end:
            due, seq, func = heapq.heappop(self.jobs)
            self.now = max(self.now, due)
            if f"after#{seq}" not in self.cancelled:
                func()
        self.now = end


class Bar:
    shown = False

    def start(self, _ms=50):
        pass

    def stop(self):
        pass

    def pack(self, **_kw):
        self.shown = True

    def pack_forget(self):
        self.shown = False


class FakeEvents:
    """Windows' notes, given by the test."""

    def __init__(self, viewer=VIEWER.hwnd):
        self.viewer, self.notes, self.front, self.closed, self.watched = viewer, [], OWN, False, [viewer]

    def take(self):
        notes, self.notes = self.notes, []
        return notes

    def watch(self, hwnd):
        self.watched.append(hwnd)
        self.viewer = hwnd or 0
        return True

    def close(self):
        self.closed = True


BORROWED = {name: value for name, value in vars(live.LiveViewMixin).items()
            if callable(value) and not name.startswith("__") and name not in ("destroy", "_on_new_page")}
# the worker's events, the requests and the status line as the window has them, whatever their parts are now
WINDOW_PARTS = {name: value for part in (jobs.JobsMixin, status.StatusMixin) for name, value in vars(part).items()
                if callable(value) and not name.startswith("__")}


class Window(BlackViewerMixin):
    """The App's live view, the status line and the requests, borrowed; the viewer, the clock and Windows' notes are
    the test's."""

    _enlarge_first = lambda self, then=None: True  # (the viewer looked at as it is chosen: tests/test_early_start.py)
    _viewer_gone = lambda self: None  # (a viewer closed: tests/test_window_state.py)
    locals().update(WINDOW_PARTS)
    locals().update(BORROWED)
    _handle_event = app_mod.App._handle_event
    _on_page_event = app_mod.App._on_page_event
    _flush_fill = app_mod.App._flush_fill
    _go_busy = app_mod.App._go_busy
    _set_busy = app_mod.App._set_busy
    _show_progress = app_mod.App._show_progress
    _busy_text = app_mod.App._busy_text
    _hide_busy = app_mod.App._hide_busy
    _summary = staticmethod(app_mod.App._summary)
    _page_line = app_mod.App._page_line
    _normal_status = app_mod.App._normal_status
    _page_status = app_mod.App._page_status
    _job_line = app_mod.App._job_line
    _queue = app_mod.App._queue
    _run_queued = app_mod.App._run_queued
    _start_translate = app_mod.App._start_translate
    _editing = app_mod.App._editing
    say = app_mod.App.say

    def __init__(self, root, clock, owner="own", auto=True, follow="events"):
        if hasattr(self, "_init_flow_state"):
            self._init_flow_state()
        self.stop_btn = {}
        self.clock = clock
        self.canvas = ImageCanvas(root)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        self.translate_btn, self.batch_btn = {}, {}
        self.progress_bar = Bar()
        self.statuses: list[str] = []
        self.status_var = tk.StringVar(master=root)
        self.role_var = tk.StringVar(master=root, value="reader")
        self.original_var = tk.BooleanVar(master=root, value=False)
        self.auto_var = tk.BooleanVar(master=root, value=auto)
        self.book_var = tk.StringVar(master=root, value="Book")
        self.model_var = tk.StringVar(master=root, value="m")
        self.lang_var = tk.StringVar(master=root, value="English")
        self.settings = SimpleNamespace(margins=(0, 0, 0, 0), auto_interval_ms=700, settle_ms=400,
                                        page_turn_wait_ms=3000, follow=follow)
        self.selected = VIEWER
        self.busy = self._viewer_hidden = self._busy_shown = self._waiting = False
        self.ready, self._bar_shown = True, False
        self._progress, self._busy_since = "", 0.0
        self._chosen_region = self._grip_box = self._review = self.last_result = self._ordering = None
        self._live = self._live_thumb = self._job_frame = self._job_thumb = self._fill = self._queued = None
        self._fill_dirty = self._covered = False
        self._thumbs, self._lettered_memo, self._mask_memo = [], None, None
        self._auto_last = self._auto_candidate = None
        self._manual_area, self._page_areas, self._area_hinted = True, {}, False
        self._status_key = None
        self._jobs: queue.Queue = queue.Queue()
        self.pipeline = SimpleNamespace(forgotten=[], forget_page=lambda result: self.pipeline.forgotten.append(result))
        self.new_pages: list[tuple[float, Image.Image]] = []
        self.in_front = True  # the viewer's window shows the book
        self.own: list[tuple[int, int, int, int]] = []  # where TASlation's windows are on the screen
        self.events = FakeEvents()
        self.events_ok = True
        if follow == "events":
            self._following = Following(mode="events", events=self.events, owner=owner, look_at=0.0)

    # what Tk and the rest of the App would do
    def after(self, ms, func):
        return self.clock.after(ms, func)

    def after_cancel(self, job):
        self.clock.cancel(job)

    def title(self, _text):
        pass

    def status(self, text):
        self.statuses.append(text() if callable(text) else text)

    def _own_rects(self):
        return list(self.own)

    def _own_hwnd(self):
        return None

    def _book_in_front(self):
        return self.in_front

    def _find_page(self, image):
        pass

    def _on_new_page(self, image, thumb=None, complete=None):  # as the App's in page-by-page mode
        self.new_pages.append((self.clock.now, image))
        self._start_translate(image, thumb=thumb, complete=complete)

    def _font_note(self):
        return ""

    def _show_notes(self):
        pass

    def start(self):
        """The window's start: the first heartbeat after auto_interval_ms, then by itself."""
        self.clock.after(self.settings.auto_interval_ms, self._auto_tick)

    def job_done(self, result=None):
        """The running job's page came (or none), and the job ended."""
        if result is not None:
            self._handle_event("result", {"result": result})
        self._handle_event("translate_done", {})


@pytest.fixture
def setup(hidden_root, monkeypatch):
    """A window following a viewer whose frame the test sets (a frame, or a list of (from time, frame)); every capture
    is counted. Windows' answer to who is in front: the test's table."""
    clock = Clock()
    viewer = SimpleNamespace(frames=[(0.0, _page(1))], captures=[], input=[1], pointer=[0])
    owners = {OWN: "own", BROWSER: "viewer", OTHER: "other"}

    def frame_now():
        current = viewer.frames[0][1]
        for since, frame in viewer.frames:
            if clock.now >= since:
                current = frame
        return current

    def capture_window(hwnd, client_only=True, allow_screen_fallback=True):
        viewer.captures.append(clock.now)
        return frame_now()

    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(live, "capture_window", capture_window)
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "client_rect_on_screen", lambda hwnd: (0, 0, 960, 720))
    monkeypatch.setattr(live, "foreground_owner", lambda hwnd, viewer_hwnd: owners.get(hwnd, "other"))
    monkeypatch.setattr(live, "foreground_window", lambda: OWN)
    monkeypatch.setattr(live, "last_input", lambda: viewer.input[0])  # the session's last input, as Windows ticks
    monkeypatch.setattr(live, "window_at_pointer", lambda: viewer.pointer[0])

    def make(**kwargs):
        return Window(hidden_root, clock, **kwargs)

    return SimpleNamespace(clock=clock, viewer=viewer, make=make)


def _per_minute(captures, start, end):
    return sum(1 for t in captures if start <= t < end) * 60 / (end - start)


def test_no_capture_while_taslation_is_in_front_and_nothing_happens(setup):
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(60)
    assert len(setup.viewer.captures) == 1 and w._live is setup.viewer.frames[0][1]  # one look at the start, no more
    poll = setup.make(auto=False, follow="poll")  # as before: every auto_interval_ms
    setup.viewer.captures.clear()
    poll.start()
    setup.clock.run(60)
    assert 84 <= len(setup.viewer.captures) <= 86


def test_the_viewer_in_front_is_polled_and_its_pages_followed(setup):
    v = setup.viewer
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    assert [p for _t, p in w.new_pages] == [v.frames[0][1]]  # the page in front, taken once
    w.job_done()
    start = setup.clock.now
    setup.clock.run(30)
    assert 84 <= _per_minute(v.captures, start, start + 30) <= 87  # every auto_interval_ms, as before
    turned = setup.clock.now + 0.3
    v.frames.append((turned, _page(2)))  # the reader turns the page in the viewer
    setup.clock.run(3)
    assert [p for _t, p in w.new_pages][1:] == [v.frames[1][1]]
    assert 0.4 <= w.new_pages[1][0] - turned <= 1.1  # seen at the next poll, then followed: alike settle_ms later


def test_nothing_while_neither_is_in_front_and_one_look_when_one_comes_back(setup):
    v = setup.viewer
    w = setup.make(owner="other", auto=False)
    w.start()
    setup.clock.run(30)
    assert len(v.captures) == 1  # the viewer just chosen, once (its first frame on the page); neither in front: no more
    w.events.notes.append(("front", OWN))  # TASlation comes back to the front
    setup.clock.run(0.15)
    assert len(v.captures) == 2
    setup.clock.run(30)
    assert len(v.captures) == 2
    w.events.notes += [("front", OTHER), ("front", BROWSER)]  # away, then the viewer comes to the front
    setup.clock.run(0.15)
    assert len(v.captures) == 3  # looked at at once ...
    setup.clock.run(7)
    assert 12 <= len(v.captures) <= 13  # ... and polled while it is in front
    w.events.notes.append(("front", OTHER))
    before = len(v.captures)
    setup.clock.run(30)
    assert len(v.captures) == before


def test_over_the_viewer_a_click_on_a_pane_leaves_the_viewer_in_front_and_its_turns_followed(setup, monkeypatch):
    """Over the viewer (see-through) TASlation's panes never take the foreground, but a click on one gives Windows'
    note that TASlation came to the front, and no note follows: who is in front is what Windows says now
    (`_front_as_it_is`), and the pages turned in the viewer are followed."""
    v = setup.viewer
    monkeypatch.setattr(live, "foreground_window", lambda: BROWSER)  # the viewer keeps the foreground throughout
    w = setup.make(owner="viewer")
    w._see_hidden = True
    w.start()
    setup.clock.run(3)
    w.job_done()
    pages = len(w.new_pages)
    w.events.notes.append(("front", OWN))  # a button of a pane clicked
    setup.clock.run(0.15)
    assert w._following.owner == "viewer"
    v.frames.append((setup.clock.now + 0.3, _page(10)))  # the reader turns the page in the viewer
    setup.clock.run(3)
    assert len(w.new_pages) == pages + 1 and w.new_pages[-1][1] is v.frames[-1][1]
    w.job_done()
    w = setup.make(owner="viewer")  # not over the viewer: a note that TASlation came to the front is taken as it is
    w.start()
    setup.clock.run(3)
    w.job_done()
    w.events.notes.append(("front", OWN))
    setup.clock.run(0.15)
    assert w._following.owner == "own"


def test_the_viewer_moved_is_looked_at_once_it_stops_and_renamed_at_once(setup):
    v = setup.viewer
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(2)
    assert len(v.captures) == 1
    for _step in range(10):  # dragged for a second
        w.events.notes.append(("moved", VIEWER.hwnd))
        setup.clock.run(0.1)
    assert len(v.captures) == 1  # not while it moves
    setup.clock.run(0.6)
    assert len(v.captures) == 2  # once it stopped (settle_ms after the last move)
    w.in_front = False  # a tab switch: the browser window shows another tab
    w.auto_var.set(True)
    w.events.notes.append(("renamed", VIEWER.hwnd))
    setup.clock.run(0.15)
    assert len(v.captures) == 2 and w.statuses[-1].startswith("Waiting: the browser shows another tab.")
    setup.clock.run(20)
    assert len(v.captures) == 2  # waiting costs no capture
    w.in_front = True  # the book's tab is back
    w.events.notes.append(("renamed", VIEWER.hwnd))
    setup.clock.run(0.15)
    assert len(v.captures) == 3 and "Viewer: Yomizuq - Google Chrome" in w.statuses[-2:]
    w.events.notes.append(("closed", VIEWER.hwnd))  # closed: nothing more is looked at
    setup.clock.run(10)
    assert len(v.captures) <= 5  # the page taken, settled and looked at again; nothing after


def test_the_viewer_given_another_size_is_looked_at_at_once_and_again_once_it_stops(setup, monkeypatch):
    """A window given another size may draw no frame of it by itself (the capture's first frame of the new size can be
    all that comes): it is looked at at the first note, and once it stops; a drag in between is not looked at."""
    v = setup.viewer
    rect = [(0, 0, 960, 760)]
    monkeypatch.setattr(live, "window_rect", lambda hwnd: rect[0])
    w = setup.make(auto=False)
    w._following.size = (960, 760)  # (as the window watching it found it: `_follower`)
    w.start()
    setup.clock.run(2)
    w.events.notes.append(("moved", VIEWER.hwnd))  # moved, its size as it was: once it stops only
    setup.clock.run(0.15)
    assert len(v.captures) == 1
    setup.clock.run(0.6)
    assert len(v.captures) == 2
    rect[0] = (0, 0, 860, 1000)  # given another size in one step
    w.events.notes += [("moved", VIEWER.hwnd), ("moved", VIEWER.hwnd)]
    setup.clock.run(0.15)
    assert len(v.captures) == 3  # at once
    setup.clock.run(1)
    assert len(v.captures) == 4  # and once it stopped (settle_ms after the last note)
    for step in range(10):  # dragged to other sizes for a second
        rect[0] = (0, 0, 870 + 10 * step, 1000)
        w.events.notes.append(("moved", VIEWER.hwnd))
        setup.clock.run(0.1)
    assert len(v.captures) == 5  # at its first note alone
    setup.clock.run(0.6)
    assert len(v.captures) == 6


def _turn(setup, *frames):
    """The reader turns the page in the viewer: it shows *frames* (delay, frame) from now on."""
    now = setup.clock.now
    setup.viewer.frames += [(now + delay, frame) for delay, frame in frames]
    return now


def test_a_soft_picture_first_is_read_again_from_the_sharp_one(setup, monkeypatch):
    _count_frames(setup, monkeypatch)
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    w.job_done()
    soft, sharp = _page(4, soft=3), _page(4)
    turned = _turn(setup, (0.15, soft), (1.0, sharp))  # a browser-based viewer: a soft picture, the sharp one later
    setup.clock.run(0.8)
    assert [p for _t, p in w.new_pages][1:] == [soft] and w.busy  # taken at once, as it settled
    setup.clock.run(1.2)  # a second later: sharper, while the job on the soft one runs: it waits for the job
    assert w._queued == ("auto", ()) and w._following.retake is not None and len(w.new_pages) == 2
    result = PageResult(image=soft.copy(), original=soft.copy(), regions=[], cache_misses=1)  # read anew
    w.job_done(result)
    assert [p for _t, p in w.new_pages][2:] == [sharp]  # read again, from the sharp frame ...
    assert w.pipeline.forgotten == [result]  # ... what the soft one put in the cache dropped first
    assert w.new_pages[2][0] - turned < 2.5

    w.job_done()
    soft, sharp = _page(5, soft=3), _page(5)
    _turn(setup, (0.15, soft), (1.0, sharp))
    setup.clock.run(0.8)
    w.job_done(PageResult(image=soft.copy(), original=soft.copy(), regions=[], cache_hits=1))  # came from the cache
    setup.clock.run(1.2)
    assert [p for _t, p in w.new_pages][-1] is sharp and len(w.pipeline.forgotten) == 1  # drawn again, nothing dropped
    w.job_done()

    sharp = _page(6)
    _turn(setup, (0.15, sharp))  # a sharp page at once: one take
    setup.clock.run(5)
    assert [p for _t, p in w.new_pages][-1] is sharp and sum(1 for _t, p in w.new_pages if p is sharp) == 1


def _count_frames(setup, monkeypatch):
    """The capture's frame events (`capture.frame_count`): one more frame each time the viewer's picture changes."""
    def count(hwnd):
        return 1 + sum(1 for since, _frame in setup.viewer.frames[1:] if setup.clock.now >= since)
    monkeypatch.setattr(live, "frame_count", count)


def test_a_page_turned_in_the_viewer_is_followed_at_its_first_frame(setup, monkeypatch):
    """The viewer in front, its frames counted: a page turned there is seen as its frame comes (no 700 ms poll) and
    taken once no new frame came for settle_ms; a page the cache holds whole is taken on its first frame, soft or
    not, and the sharp frame that follows takes its place at once - nothing dropped from the cache, for the soft
    job read nothing."""
    _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    w.job_done()
    setup.clock.run(5)
    turned = setup.clock.now + 0.3
    v.frames.append((turned, _page(2)))  # not in the cache: settles first
    setup.clock.run(2)
    assert [p for _t, p in w.new_pages][1:] == [v.frames[-1][1]]
    assert 0.4 <= w.new_pages[1][0] - turned <= 0.45  # seen within FRAME_STEP_MS, then settle_ms without a new frame
    w.job_done()
    setup.clock.run(2)

    w._all_cached = lambda image: True  # the book's cache holds every page from here on
    soft, sharp = _page(7, soft=3), _page(7)
    turned = setup.clock.now + 0.3
    v.frames += [(turned, soft), (turned + 0.25, sharp)]  # a browser-based viewer: soft first, sharp 250 ms later
    setup.clock.run(0.1 + 0.3)
    assert w.new_pages[-1][1] is soft and w.new_pages[-1][0] - turned <= 0.03  # taken on its first frame
    setup.clock.run(0.3)  # the sharp frame comes while the job on the soft one runs: that job gives way to it
    assert w._following.retake is not None and w._following.retake.thumb is not None and w._queued == ("auto", ())
    assert w._page_cancel.is_set()  # (cancelled: nothing of it is kept)
    w.job_done(PageResult(image=soft.copy(), original=soft.copy(), regions=[], cache_hits=1))
    assert w.new_pages[-1][1] is sharp and w.new_pages[-1][0] == setup.clock.now  # at once when the job is gone
    assert w.pipeline.forgotten == []  # (all of it came from the cache)
    w.job_done()
    captures = len(v.captures)
    setup.clock.run(30)
    assert len(v.captures) <= captures + 1 + 30 // 0.7  # no new frame: polled every auto_interval_ms, as before


def test_a_page_dragged_with_the_button_held_is_taken_only_once_let_go(setup, monkeypatch):
    """A viewer that slides its page along with the pointer while the button is held, and turns it once it is let go
    at the screen's edge: no frame of the drag is taken - not one the cache holds whole either, which is otherwise
    taken on its first frame -, and the frame the release leaves is taken once it settled. The button held while
    another program is in front holds nothing."""
    _count_frames(setup, monkeypatch)
    v = setup.viewer
    held = [False]
    monkeypatch.setattr(live.overlay, "button_down", lambda: held[0])
    monkeypatch.setattr(live, "foreground_window", lambda: BROWSER)
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    w.job_done()
    setup.clock.run(2)
    pages = len(w.new_pages)
    assert w._held_in_viewer() is False
    held[0] = True
    assert w._held_in_viewer() is True
    for cached in (False, True):
        w._all_cached = lambda image, cached=cached: cached
        now = setup.clock.now
        v.frames += [(now + 0.1 * k, _page(20 + k + 10 * cached)) for k in range(1, 4)]  # the page following the pointer
        setup.clock.run(3)  # (held there for well over settle_ms)
        assert len(w.new_pages) == pages, cached
    held[0] = False  # let go at the edge: the next page
    turned = setup.clock.now + 0.05
    v.frames.append((turned, _page(40)))
    setup.clock.run(2)
    assert [p for _t, p in w.new_pages][pages:] == [v.frames[-1][1]]
    w.job_done()
    setup.clock.run(2)
    monkeypatch.setattr(live, "foreground_window", lambda: OTHER)
    held[0] = True  # held in another program: not the viewer's press
    assert w._held_in_viewer() is False


def test_a_turn_stops_the_backlog_s_step_before_the_turned_page_is_drawn(setup, monkeypatch):
    """A step of the backlog's under way (``pipeline.behind_stop``) stops at the window's first capture of a turned
    page, before that page is drawn - not only once the page's job is queued (on a runner's 4 cores the server's work
    for the step kept the window from drawing the captured page for 2.6 s) -, and no step begins while the window
    follows that page (`backlog.follows_viewer`). A frame of the page on show drawn again stops nothing."""
    from taslation import backlog

    _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    w.job_done()
    setup.clock.run(3)
    assert not backlog.follows_viewer(w)
    stop = backlog.Preempt()
    w.pipeline.behind_stop = stop
    drawn: list = []
    show = w._show_live
    w._show_live = lambda image, thumb=None: (drawn.append((image, stop.is_set())), show(image, thumb))[1]
    v.frames.append((setup.clock.now + 0.1, v.frames[0][1].copy()))  # the page on show drawn again
    setup.clock.run(0.3)
    assert drawn and not stop.is_set() and not backlog.follows_viewer(w)
    page2 = _page(2)
    v.frames.append((setup.clock.now + 0.1, page2))  # the reader turns the page in the viewer
    setup.clock.run(0.15)
    assert drawn[-1] == (page2, True)  # stopped before it was drawn
    assert backlog.follows_viewer(w) and w._following.op.phase == "settle" and not w.new_pages[1:]
    setup.clock.run(2)
    assert [p for _t, p in w.new_pages][1:] == [page2]


def test_once_the_viewer_drew_a_page_soft_first_a_page_the_cache_holds_is_taken_on_its_sharp_frame(setup, monkeypatch):
    """The viewer in front, its frames counted, the book's cache holding every page: the first page drawn soft first
    is taken on its soft frame, as nothing says yet that this viewer draws so, and read again from its sharp one -
    what the window learns the viewer's soft and sharp pictures by (`frames.crispness`). From then on a soft frame of a
    page the cache holds is not lettered: the page is taken on its sharp frame as that comes, which the window learns
    by as well; a page drawn sharp at once is taken at once, as ever. Another viewer chosen has learnt nothing."""
    _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    w.job_done()
    setup.clock.run(2)
    w._all_cached = lambda image: True
    f = w._following
    soft, sharp = _page(7, soft=3), _page(7)
    turned = setup.clock.now + 0.3
    v.frames += [(turned, soft), (turned + 0.25, sharp)]
    setup.clock.run(0.4)
    assert w.new_pages[-1][1] is soft and not w._looks_soft(soft)  # taken on its first frame: nothing learnt yet
    setup.clock.run(0.3)
    assert f.soft_of == VIEWER.hwnd and len(f.soft) == len(f.sharp) == 1  # come sharper: this viewer draws soft first
    w.job_done(PageResult(image=soft.copy(), original=soft.copy(), regions=[], cache_hits=1))
    assert w.new_pages[-1][1] is sharp
    w.job_done()
    setup.clock.run(2)

    pages = len(w.new_pages)
    soft, sharp = _page(8, soft=3), _page(8)
    turned = setup.clock.now + 0.3
    v.frames += [(turned, soft), (turned + 0.25, sharp)]
    setup.clock.run(0.5)
    assert len(w.new_pages) == pages and w._live is soft and w._looks_soft(soft)  # on the page as it is, unlettered
    setup.clock.run(0.1)
    assert [p for _t, p in w.new_pages[pages:]] == [sharp] and w.new_pages[-1][0] - (turned + 0.25) <= 0.03
    assert len(f.soft) == len(f.sharp) == 2  # (learnt from as it settled)
    w.job_done()
    setup.clock.run(2)

    page = _page(9)
    turned = setup.clock.now + 0.3
    v.frames.append((turned, page))  # drawn sharp at once: taken on its first frame
    setup.clock.run(0.4)
    assert w.new_pages[-1][1] is page and w.new_pages[-1][0] - turned <= 0.03 and not w._looks_soft(page)
    w.job_done()
    w.selected = WindowInfo(hwnd=8, title="Another - Google Chrome", class_name="Chrome_WidgetWin_1", pid=8,
                            rect=(0, 0, 960, 720))
    assert not w._looks_soft(_page(10, soft=3))  # another viewer: judged by nothing it has not drawn


def test_a_page_the_window_saw_sharp_is_judged_by_its_own_sharp_picture(setup):
    """The soft picture of a page with much fine detail, part of it drawn sharp already, is as crisp as the viewer's
    sharp pictures of other pages: by those alone it would be taken for sharp, and what the cache holds of it
    lettered on it. Once the window has seen that page's own sharp picture (`frames.SharpSeen`, kept as the page came
    sharper) such a frame of it is soft, the sharp one is not; a page not seen sharp is judged as before."""
    w = setup.make(owner="viewer")
    w._drew_soft(_page(7, soft=3), _page(7))  # the viewer draws soft first (as `_retake` and the settle learn it)
    size = (540, 720)  # (single pages: the soft picture's page unit is the sharp one's)
    sharp = _page(8, size=size)
    part = _page(8, soft=3, size=size)
    part.paste(sharp.crop((0, 0, size[0], 216)), (0, 0))  # its top drawn sharp already
    assert not w._looks_soft(part)  # by the viewer's pictures of the other pages: sharp
    w._drew_soft(_page(8, soft=3, size=size), sharp)  # the page seen soft, then sharp
    assert w._looks_soft(part) and not w._looks_soft(sharp)
    assert not w._looks_soft(_page(9, size=size)) and w._looks_soft(_page(9, soft=3, size=size))  # not seen: as before
    assert not w._looks_soft(_page(8, size=(600, 720)))  # another size: as before


def test_the_pages_own_picture_only_adds_soft_frames(setup):
    """A page's own sharp picture as the window kept it may pass a frame the viewer's pictures of all pages call soft
    (the picture kept may itself be little crisper than the soft one, and what the cache held of the page would then
    be lettered on its soft picture): such a frame stays soft. The page's own picture only finds soft frames the
    viewer's pictures pass."""
    w = setup.make(owner="viewer")
    for seed in range(1, 6):  # the viewer draws soft first, its pictures of these pages what all are judged by
        w._drew_soft(_page(seed, soft=3), _page(seed))
    size = (540, 720)
    frame = _page(8, soft=3, size=size)
    w._drew_soft(_page(8, soft=4, size=size), _page(8, soft=3, size=size))  # its "sharp" picture: as soft
    f = w._following
    crisp = live._crisp(w, frame, w._area_box(frame))
    units = live._units(w, frame, w._margins_of(frame))
    assert f.sharp_pages.judge(units[0].fingerprint, frame.size, crisp, 36) is True  # its own page passes it
    assert not frames.looks_sharp(crisp, f.soft, f.sharp)  # the viewer's pictures do not
    assert w._looks_soft(frame)
    assert not w._looks_soft(_page(8, size=size))  # its sharp picture: sharp by both


def test_a_frames_thumbnail_from_its_pixels_is_the_one_frames_gives():
    """The live view takes a frame's pixels out of the picture once (`live.FrameFacts`) and makes its thumbnail from
    them (`live.thumbnail_of`): the very values `frames.thumbnail` gives, which the pages seen are compared with."""
    pictures = [_page(1), _page(2, soft=3), _page(3, size=(333, 517)), Image.new("RGB", (7, 5), (3, 200, 9))]
    for picture in pictures:
        assert np.array_equal(live.thumbnail_of(picture, np.asarray(picture)), thumbnail(picture))
        assert np.array_equal(live.thumbnail_of(picture, np.asarray(picture), 32), thumbnail(picture, 32))
    for other in (_page(4).convert("RGBA"), _page(5).convert("L")):  # not RGB: `frames`' own, as it is
        assert np.array_equal(live.thumbnail_of(other, np.asarray(other)), thumbnail(other))


def _follow_recorded(hidden_root, monkeypatch, tmp_path, worked_out_once: bool):
    """A recorded sequence of the viewer's frames followed by events, the viewer in front and its frames counted:
    page 1, the same picture captured again and again, page 2 sliding in (frames that keep changing), settling; a
    page the cache holds whole, drawn soft first and sharp after; each capture a new picture, as the real capture
    gives (the same bytes for a picture the viewer did not draw anew). What the window did, frame by frame: the
    captures, the pages taken, what was on the page, what it said. With *worked_out_once* False every check works
    its value out anew from the picture, as before `live.FrameFacts` (and nothing is shared with the page job)."""
    from taslation import fingerprint as fp
    from taslation.cache import CachedBubble, CachedPage, CacheStore

    if not worked_out_once:
        monkeypatch.setattr(live, "_facts", lambda window, image: live.FrameFacts(image))
        monkeypatch.setattr(live, "_captured_facts", lambda window, hwnd, seq, image: live.FrameFacts(image))
        monkeypatch.setattr(live, "thumbnail_of", lambda image, pixels=None, size=64: thumbnail(image, size))
        monkeypatch.setattr(fp, "SHARED_KEEP", 0)
    clock = Clock()
    first = _page(1)
    sliding = [Image.fromarray(np.roll(np.asarray(_page(2)), 40 * k, axis=1)) for k in (4, 3, 2, 1)]
    soft, sharp = _page(8, soft=3), _page(8)
    t0 = clock.now
    frames = [(t0, first), *[(t0 + 5.0 + 0.05 * i, f) for i, f in enumerate(sliding)], (t0 + 5.2, _page(2)),
              (t0 + 9.0, soft), (t0 + 9.3, sharp)]
    labels: dict[int, str] = {}
    names = {id(first): "1", id(soft): "8 soft", id(sharp): "8", id(frames[5][1]): "2"}
    names.update({id(f): f"2 sliding {i}" for i, f in enumerate(sliding)})
    kept: list[Image.Image] = []
    trace: list[tuple] = []

    def frame_now():
        current = frames[0][1]
        for since, frame in frames:
            if clock.now >= since:
                current = frame
        return current

    def capture_window(hwnd, client_only=True, allow_screen_fallback=True):
        source = frame_now()
        copy = source.copy()  # a new picture every time, as the real capture gives
        kept.append(copy)
        labels[id(copy)] = names[id(source)]
        trace.append(("capture", round(clock.now - t0, 3), names[id(source)]))
        return copy

    def label(image):
        return None if image is None else labels.get(id(image), names.get(id(image), "?"))

    worked: dict[str, int] = {}  # how often each check was worked out

    def counted(name, check):
        def count(*args, **kwargs):
            worked[name] = worked.get(name, 0) + 1
            return check(*args, **kwargs)
        return count

    for name in ("is_blank", "is_black", "detail"):
        monkeypatch.setattr(live, name, counted(name, getattr(live, name)))
    monkeypatch.setattr(fp, "_analyze", counted("analyze", fp._analyze))
    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(live, "capture_window", capture_window)
    monkeypatch.setattr(live, "frame_count", lambda hwnd: 1 + sum(1 for since, _f in frames[1:] if clock.now >= since))
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "client_rect_on_screen", lambda hwnd: (0, 0, 960, 720))
    monkeypatch.setattr(live, "foreground_owner", lambda hwnd, viewer_hwnd: "viewer")
    monkeypatch.setattr(live, "foreground_window", lambda: BROWSER)
    monkeypatch.setattr(live, "last_input", lambda: 1)
    monkeypatch.setattr(live, "window_at_pointer", lambda: 0)
    w = Window(hidden_root, clock, owner="viewer")
    w.settings.cache_enabled, w.settings.fingerprint_max_distance = True, 10
    w.store = CacheStore(tmp_path / f"cache-{worked_out_once}")
    w._name_needed = lambda: False
    book = w.store.open("Book", "m", "English")
    for unit in fp.analyze(np.asarray(sharp), (0, 0, 0, 0)):  # page 8 is in the cache, page 1 and 2 are not
        book.add(CachedPage(unit.fingerprint, unit.width / unit.height, [CachedBubble((0.1, 0.1, 0.3, 0.3), "Hi")]))
    book.save()
    w.start()
    shown = None
    while clock.now < t0 + 12:
        clock.run(0.05)
        if w.busy:  # the page job: its frame read as `Pipeline.process` reads it (`units_of`), then done
            read = np.asarray(w._job_frame.convert("RGB"))
            trace.append(("job read", [u.fingerprint for u in fp.analyze(read, w.settings.margins)]))
            w.job_done(PageResult(image=w._job_frame.copy(), original=w._job_frame.copy(), regions=[],
                                  cache_hits=1))
        if label(w._live) != shown:
            shown = label(w._live)
            trace.append(("shown", round(clock.now - t0, 3), shown))
    trace += [("taken", round(t - t0, 3), label(p)) for t, p in w.new_pages]
    trace += [("said", line) for line in w.statuses]
    trace.append(("forgotten", len(w.pipeline.forgotten)))
    return trace, worked


def test_a_recorded_sequence_of_frames_leads_to_the_same_decisions_with_every_check_worked_out_once(
        hidden_root, monkeypatch, tmp_path):
    with monkeypatch.context() as patched:
        before, worked_before = _follow_recorded(hidden_root, patched, tmp_path, worked_out_once=False)
    now, worked = _follow_recorded(hidden_root, monkeypatch, tmp_path, worked_out_once=True)
    assert now == before
    assert all(worked[name] < worked_before[name] for name in worked_before), (worked, worked_before)
    taken = [entry[2] for entry in now if entry[0] == "taken"]
    assert taken == ["1", "2", "8"]  # (the sequence did what it says: page 8 taken at its first sharp frame, cached)
    assert ("taken", 9.315, "8") in now and ("shown", 9.05, "8 soft") in now
    assert sum(1 for entry in now if entry[0] == "capture" and entry[2] == "1") > 5  # page 1 captured again and again


def test_a_page_that_settles_while_a_job_runs_is_taken_after_it(setup, monkeypatch):
    _count_frames(setup, monkeypatch)
    v = setup.viewer
    w = setup.make(owner="viewer")
    w.start()
    setup.clock.run(3)
    assert w.busy  # the first page is being translated
    page2 = _page(2)
    _turn(setup, (0.15, page2))
    setup.clock.run(2)
    assert len(w.new_pages) == 1 and w._queued == ("auto", ())  # waits for the job
    w.job_done()
    assert [p for _t, p in w.new_pages] == [v.frames[0][1], page2]  # taken at once after it
    w.job_done()
    w.ready = False  # the models still load: the page waits for them, the badge says so
    _turn(setup, (0.15, _page(3)))
    setup.clock.run(2)
    assert len(w.new_pages) == 2 and w._queued == ("auto", ()) and w.canvas.find_withtag("busy")
    w._handle_event("ready", {"ocr": True})
    assert len(w.new_pages) == 3


def test_without_the_hooks_the_viewer_is_polled_as_before(hidden_root, monkeypatch):
    monkeypatch.setattr(live.WindowEvents, "start", classmethod(lambda cls: None))
    w = SimpleNamespace(settings=SimpleNamespace(follow="events"), selected=VIEWER)
    assert live.LiveViewMixin._follower(w).mode == "poll"  # not Windows, or the hook could not be set
    failing = FakeEvents()
    failing.watch = lambda hwnd: False
    closed = []
    failing.close = lambda: closed.append(True)
    monkeypatch.setattr(live.WindowEvents, "start", classmethod(lambda cls: failing))
    w = SimpleNamespace(settings=SimpleNamespace(follow="events"), selected=VIEWER)
    assert live.LiveViewMixin._follower(w).mode == "poll" and closed == [True]
    w = SimpleNamespace(settings=SimpleNamespace(follow="poll"), selected=VIEWER)
    assert live.LiveViewMixin._follower(w).mode == "poll"


def test_a_viewer_chosen_is_watched_and_the_hooks_go_with_the_window(setup):
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(2)
    other = WindowInfo(hwnd=8, title="Yomizuq 2 - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7,
                       rect=(0, 0, 960, 720))
    w.selected = other
    w._follow_viewer()
    assert w.events.watched[-1] == 8 and w._following.look_at == 0.0
    w.events.watch = lambda hwnd: False  # the hooks cannot be set on it: polled as before
    w._follow_viewer()
    assert w._following.mode == "poll" and w.events.closed

    class Base:
        def destroy(self):
            self.destroyed = True

    class Closing(live.LiveViewMixin, Base):
        pass

    c = Closing()
    c._following = Following(mode="events", events=FakeEvents())
    events = c._following.events
    c.destroy()
    assert events.closed and c.destroyed and c._following.mode == "poll"


def test_input_over_the_viewer_while_taslation_is_in_front_is_looked_at_once_it_stops(setup):
    v = setup.viewer
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(2)
    assert len(v.captures) == 1
    v.pointer[0] = OTHER  # typing in TASlation, the pointer elsewhere: nothing
    for _step in range(10):
        v.input[0] += 100
        setup.clock.run(0.1)
    setup.clock.run(5)
    assert len(v.captures) == 1
    v.pointer[0] = VIEWER.hwnd  # the wheel over the viewer, which is not in front (Windows scrolls it all the same)
    v.frames.append((setup.clock.now + 0.2, _page(8)))
    for _step in range(8):
        v.input[0] += 100
        setup.clock.run(0.1)
    assert len(v.captures) == 1  # not while it goes on
    setup.clock.run(0.6)
    assert len(v.captures) == 2 and w._live is v.frames[-1][1]  # once it stopped
    setup.clock.run(20)  # the pointer resting there, no input: nothing more
    assert len(v.captures) == 2


def test_taslation_moved_or_resized_is_followed_by_one_look_once_it_stops(setup):
    v = setup.viewer
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(2)
    assert len(v.captures) == 1
    for _step in range(5):  # maximised, or dragged: Tk's <Configure> of the window itself
        w._own_moved(SimpleNamespace(widget=w))
        setup.clock.run(0.1)
    assert len(v.captures) == 1
    setup.clock.run(0.6)
    assert len(v.captures) == 2  # one look once it stopped (it may cover the viewer now, or no more)
    w._own_moved(SimpleNamespace(widget=w.canvas))  # a widget inside it resized: nothing
    setup.clock.run(2)
    assert len(v.captures) == 2


def test_a_page_job_the_window_can_cancel_gives_way_to_the_sharp_frame_and_to_a_new_page(setup, monkeypatch):
    """Where a page job carries its own cancel event (the window's `_page_cancel`, as Stop cancels it), the job on
    a soft picture is cancelled as soon as the sharp one is there - nothing of it reaches the cache, so nothing is
    dropped - and so is the job on a page the reader has turned away from."""
    _count_frames(setup, monkeypatch)
    w = setup.make(owner="viewer")
    real_start = w._start_translate

    def start(image, complete=None, thumb=None):
        before = getattr(w, "_page_cancel", None)
        real_start(image, complete=complete, thumb=thumb)
        if getattr(w, "_page_cancel", None) is before:  # a window whose jobs make none: one for every page here
            w._page_cancel = threading.Event()

    w._start_translate = start

    def cancelled_job_ends():  # what the worker says of a cancelled page: no result, then done
        w._handle_event("page_cancelled", {})
        w._handle_event("translate_done", {})

    w.start()
    setup.clock.run(3)
    w.job_done()
    soft, sharp = _page(4, soft=3), _page(4)
    _turn(setup, (0.15, soft), (1.0, sharp))
    setup.clock.run(0.8)
    cancel = w._page_cancel
    assert [p for _t, p in w.new_pages][-1] is soft and w.busy and not cancel.is_set()
    setup.clock.run(1.2)  # the sharp picture: the job on the soft one is cancelled at once
    assert cancel.is_set() and w._cancel_why == "page" and w._queued == ("auto", ())
    cancelled_job_ends()
    assert [p for _t, p in w.new_pages][-1] is sharp and not w.pipeline.forgotten  # nothing of the soft job to drop
    cancel = w._page_cancel  # the job on the sharp page runs ...
    page5 = _page(5)
    _turn(setup, (0.15, page5))  # ... and the reader turns on: it gives way to the new page
    setup.clock.run(1)
    assert cancel.is_set() and w._queued == ("auto", ())
    cancelled_job_ends()
    assert [p for _t, p in w.new_pages][-1] is page5
    w.job_done()
    lines = len(w.statuses)
    assert not any("Stopped" in line for line in w.statuses[:lines])  # a page given way is not "stopped"


def test_a_page_turned_by_the_wheel_while_a_job_runs_does_not_wait_for_the_job(setup):
    """TASlation in front, a page being translated, the wheel over the viewer: the look once the input stops finds
    the page being translated - nothing is cancelled and nothing more is looked at - or a new page, looked at once
    more settle_ms later; alike there (as `_watch_page` judges it while the viewer is in front), the job gives way to
    it (`_cancel_page`) and the new page starts as soon as the job is gone."""
    v = setup.viewer
    w = setup.make()
    w.start()
    setup.clock.run(3)
    cancel = w._page_cancel
    assert w.busy and len(w.new_pages) == 1 and cancel is not None and not cancel.is_set()
    v.pointer[0] = VIEWER.hwnd  # the wheel over the viewer, which is not in front: the page stays as it is
    before = len(v.captures)
    for _step in range(3):
        v.input[0] += 100
        setup.clock.run(0.1)
    setup.clock.run(10)
    assert len(v.captures) == before + 1 and not cancel.is_set() and w._queued == ("auto", ())  # one look, as before
    page2 = _page(2)
    v.frames.append((setup.clock.now + 0.2, page2))  # now the wheel turns the page
    before = len(v.captures)
    for _step in range(8):
        v.input[0] += 100
        setup.clock.run(0.1)
    assert len(v.captures) == before  # not while the input goes on
    setup.clock.run(0.6)
    assert len(v.captures) == before + 1 and not cancel.is_set()  # a new page on one look: it may still be turning
    setup.clock.run(0.6)
    assert len(v.captures) == before + 2 and cancel.is_set() and w._cancel_why == "page" and w._queued == ("auto", ())
    for _step in range(5):  # more input while the cancelled job ends: the look once it stops shows the viewer's
        v.input[0] += 100  # frame (`_look_over_job`), and nothing more is done
        setup.clock.run(0.1)
    setup.clock.run(2)
    assert len(v.captures) == before + 3 and len(w.new_pages) == 1 and w._live is page2
    w._handle_event("page_cancelled", {})  # what the worker says of a cancelled page: no result, then done
    w._handle_event("translate_done", {})
    assert [p for _t, p in w.new_pages][1:] == [page2] and len(v.captures) == before + 4  # taken at once: settled
    assert w.busy and w._page_cancel is not cancel
    assert not any("Stopped" in line for line in w.statuses)  # a page given way is not "stopped"


def test_a_viewer_chosen_while_another_window_is_in_front_gets_its_first_frame_on_the_page(setup, monkeypatch):
    """After a restart with a terminal in front: the viewer chosen is looked at at once whoever is in front, and
    while no frame of it could be shown yet (it drew nothing) again every auto_interval_ms; once one is on the page,
    the usual rules - nothing while neither window is in front. A viewer chosen later is looked at at once too."""
    v = setup.viewer
    page = _page(1)
    v.frames = [(0.0, Image.new("RGB", (960, 720), "white")), (setup.clock.now + 3.0, page)]  # drawn 3 s later
    w = setup.make(owner="other", auto=False)
    w.start()
    setup.clock.run(2)
    assert len(v.captures) == 2 and w._live is None  # blank: looked at again every auto_interval_ms
    setup.clock.run(2)
    assert w._live is page  # on the page, though neither TASlation nor the viewer is in front
    count = len(v.captures)
    setup.clock.run(30)
    assert len(v.captures) == count  # then the usual rules: nothing while neither is in front
    monkeypatch.setattr(live, "foreground_window", lambda: OTHER)
    w.selected = WindowInfo(hwnd=8, title="Yomizuq 2 - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7,
                            rect=(0, 0, 960, 720))
    w._follow_viewer()  # another viewer chosen from the list
    setup.clock.run(0.15)
    assert len(v.captures) == count + 1 and w._following.owner == "other" and not w._following.unseen
    setup.clock.run(30)
    assert len(v.captures) == count + 1
