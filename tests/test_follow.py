"""Following the viewer by events (Settings.follow = "events"): no capture while TASlation is in front and nothing
happens, polling while the viewer itself is, nothing while neither is, one look when a window comes back to the front,
when the viewer's window stops moving or is renamed; an operation of TASlation's followed until the frame changes and
settles, the page started at once and looked at once more a second later (a soft picture first, then the sharp one).
Also the pure parts: the decision, the fine detail of a frame, who is in front, Windows' notes. Parts of the App are
borrowed onto a stand-in on the shared hidden root; time is a fake clock."""
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

from taslation import batch, capture, i18n
from taslation.batch import DETAIL_GRID, detail, frames_differ, sharper, thumbnail
from taslation.capture import WindowInfo, windows
from taslation.config import ConfigError, Settings
from taslation.pagekeys import key_ways
from taslation.regions import PageResult
from taslation.ui import app as app_mod
from taslation.ui import jobs, live, reading, status, translator
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
    assert live.detail is batch.detail and live.sharper is batch.sharper  # one test of sharpness: the live view's ...
    # ... and the whole-book scan's (`batch.PageWatch`)
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
    assert capture.front_owner(own, (5, 5, 5), own, viewer=7) == "own"  # the window, the reading window, a dialog
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
    """The App's live view, reading mode's keys, the status line and the requests, borrowed; the viewer, the
    clock and Windows' notes are the test's."""

    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
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
    _queue = app_mod.App._queue
    _run_queued = app_mod.App._run_queued
    _start_translate = app_mod.App._start_translate
    _editing = app_mod.App._editing
    forward_key = app_mod.App.forward_key
    _key_viewer = app_mod.App._key_viewer
    _hand_over = app_mod.App._hand_over
    _pass_on = app_mod.App._pass_on
    _key_for_viewer = app_mod.App._key_for_viewer
    _page_key_pair = app_mod.App._page_key_pair
    _forward_click = translator.TranslatorMixin._forward_click
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
        self.busy = self.reading = self._viewer_hidden = self._busy_shown = self._waiting = False
        self.ready, self.batch, self._batching, self._bar_shown = True, None, False, False
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
    viewer = SimpleNamespace(frames=[(0.0, _page(1))], captures=[], keys=[], pressed=[], input=[1], pointer=[0])
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

    def post_key(hwnd, key):
        viewer.keys.append((clock.now, key))

    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(live, "capture_window", capture_window)
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "client_rect_on_screen", lambda hwnd: (0, 0, 960, 720))
    monkeypatch.setattr(live, "foreground_owner", lambda hwnd, viewer_hwnd: owners.get(hwnd, "other"))
    monkeypatch.setattr(live, "foreground_window", lambda: OWN)
    monkeypatch.setattr(live, "last_input", lambda: viewer.input[0])  # the session's last input, as Windows ticks
    monkeypatch.setattr(live, "window_at_pointer", lambda: viewer.pointer[0])
    monkeypatch.setattr(reading, "post_key", post_key)
    monkeypatch.setattr(reading, "press_briefly", lambda hwnd, key: viewer.pressed.append((clock.now, key)) or True)

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


def test_over_the_book_a_click_on_the_window_leaves_the_viewer_in_front_and_its_turns_followed(setup, monkeypatch):
    """Over a full-screen viewer the window never takes the foreground, but a click on it (Finished reading, the page
    strip) gives Windows' note that it came to the front, and no note follows: who is in front is what Windows says
    now, and the pages turned in the viewer are followed - in reading mode too."""
    v = setup.viewer
    monkeypatch.setattr(live, "foreground_window", lambda: BROWSER)  # the viewer keeps the foreground throughout
    for reading_mode in (False, True):
        w = setup.make(owner="viewer")
        w._over_on, w.reading = True, reading_mode
        w.start()
        setup.clock.run(3)
        w.job_done()
        pages = len(w.new_pages)
        w.events.notes.append(("front", OWN))  # Finished reading clicked
        setup.clock.run(0.15)
        assert w._following.owner == "viewer"
        v.frames.append((setup.clock.now + 0.3, _page(10 + reading_mode)))  # the reader turns the page in the viewer
        setup.clock.run(3)
        assert len(w.new_pages) == pages + 1 and w.new_pages[-1][1] is v.frames[-1][1]
        w.job_done()
    w = setup.make(owner="viewer")  # not over the book: a note that TASlation came to the front is taken as it is
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


def _turn(setup, w, *frames):
    """Press Left in the window: the viewer shows *frames* (delay, frame) after the key."""
    now = setup.clock.now
    setup.viewer.frames += [(now + delay, frame) for delay, frame in frames]
    w.forward_key("Left")
    return now


def test_a_key_is_followed_until_the_page_settles_and_the_page_starts_at_once(setup):
    v = setup.viewer
    w = setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    assert len(w.new_pages) == 1
    setup.clock.run(60)
    v.captures.clear()
    page2 = _page(2)
    pressed = _turn(setup, w, (0.15, page2))
    assert v.keys[-1] == (pressed, "Left") and "Sent ← to the viewer..." not in w.statuses  # a reader sees the page turn
    setup.clock.run(5)
    assert [p for _t, p in w.new_pages][1:] == [page2]
    delay = w.new_pages[1][0] - pressed
    assert 0.5 <= delay <= 0.75  # the change seen at the next 100 ms step, then settle_ms: not two polls
    assert len(v.captures) == 1 + 2 + 1 + 1  # before the key, until the change, the settle, a second later
    setup.clock.run(60)
    assert len(v.captures) == 5  # nothing after that
    w.job_done()
    w.reading = True  # reading mode: no note about the key
    lines = len(w.statuses)
    _turn(setup, w, (0.1, _page(3)))
    assert len(w.statuses) == lines
    setup.clock.run(3)
    assert len(w.new_pages) == 3


def test_a_soft_picture_first_is_read_again_from_the_sharp_one(setup):
    v = setup.viewer
    w = setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    soft, sharp = _page(4, soft=3), _page(4)
    pressed = _turn(setup, w, (0.15, soft), (1.0, sharp))  # a browser-based viewer: a soft picture, the sharp one later
    setup.clock.run(0.8)
    assert [p for _t, p in w.new_pages][1:] == [soft] and w.busy  # taken at once, as it settled
    setup.clock.run(1.2)  # a second later: sharper, while the job on the soft one runs: it waits for the job
    assert w._queued == ("auto", ()) and w._following.retake is not None and len(w.new_pages) == 2
    result = PageResult(image=soft.copy(), original=soft.copy(), regions=[], cache_misses=1)  # read anew
    w.job_done(result)
    assert [p for _t, p in w.new_pages][2:] == [sharp]  # read again, from the sharp frame ...
    assert w.pipeline.forgotten == [result]  # ... what the soft one put in the cache dropped first
    assert w.new_pages[2][0] - pressed < 2.5

    w.job_done()
    soft, sharp = _page(5, soft=3), _page(5)
    _turn(setup, w, (0.15, soft), (1.0, sharp))
    setup.clock.run(0.8)
    w.job_done(PageResult(image=soft.copy(), original=soft.copy(), regions=[], cache_hits=1))  # came from the cache
    setup.clock.run(1.2)
    assert [p for _t, p in w.new_pages][-1] is sharp and len(w.pipeline.forgotten) == 1  # drawn again, nothing dropped
    w.job_done()

    sharp = _page(6)
    _turn(setup, w, (0.15, sharp))  # a sharp page at once: one take, one look a second later
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


def test_a_page_that_settles_while_a_job_runs_is_taken_after_it(setup):
    v = setup.viewer
    w = setup.make()
    w.start()
    setup.clock.run(3)
    assert w.busy  # the first page is being translated
    page2 = _page(2)
    _turn(setup, w, (0.15, page2))
    setup.clock.run(2)
    assert len(w.new_pages) == 1 and w._queued == ("auto", ())  # waits for the job
    w.job_done()
    assert [p for _t, p in w.new_pages] == [v.frames[0][1], page2]  # taken at once after it
    w.job_done()
    w.ready = False  # the models still load: the page waits for them, the badge says so
    _turn(setup, w, (0.15, _page(3)))
    setup.clock.run(2)
    assert len(w.new_pages) == 2 and w._queued == ("auto", ()) and w.canvas.find_withtag("busy")
    w._handle_event("ready", {"ocr": True})
    assert len(w.new_pages) == 3


def test_nothing_is_captured_while_the_batch_drives_the_viewer(setup):
    v = setup.viewer
    w = setup.make()
    w._batching = True
    w.start()
    setup.clock.run(30)
    assert v.captures == []
    w._batching = False  # done: looked at again
    setup.clock.run(1)
    assert len(v.captures) >= 1


def test_a_key_the_viewer_ignores_is_pressed_for_real(setup, monkeypatch):
    v = setup.viewer
    pressed = []
    monkeypatch.setattr(live, "press_briefly", lambda hwnd, key: pressed.append(hwnd) or
                        v.frames.append((setup.clock.now + 0.1, _page(9))) or True)
    w = setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    w.forward_key("Left")  # posted, and nothing happens: not pressed again before page_turn_wait_ms
    setup.clock.run(2.85)
    assert not pressed
    setup.clock.run(0.3)
    assert pressed == [VIEWER.hwnd]
    setup.clock.run(2)
    assert len(w.new_pages) == 2 and not any("two pages" in line for line in w.statuses)  # one turn: nothing said
    w.job_done()
    w.forward_key("Left")  # the end of the book: nothing changes, even pressed for real
    setup.clock.run(0.05)  # (the keys gathered for one handover: reading.KEY_QUIET_MS)
    assert len(v.pressed) == 1 and len(v.keys) == 1  # pressed at once: this viewer took no posted key
    v.frames = [(0.0, v.frames[-1][1])]
    monkeypatch.setattr(live, "press_briefly", lambda hwnd, key: True)
    setup.clock.run(2.5)
    assert w.statuses[-1] != "The viewer did not change (end of book, or the key means nothing there)."
    setup.clock.run(1)  # page_turn_wait_ms after the press
    assert w.statuses[-1] == "The viewer did not change (end of book, or the key means nothing there)."
    assert len(pressed) == 1  # and no second press of that key


def test_a_click_passed_on_is_followed_as_a_key_is_also_before_any_page_was_taken(setup, monkeypatch):
    v = setup.viewer
    clicks = []
    monkeypatch.setattr(translator, "post_click", lambda hwnd, x, y: clicks.append((hwnd, x, y)))
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(2)
    assert w._auto_last is None and len(v.captures) == 1 and w._live_thumb is not None
    assert not hasattr(w, "_watch_page_clicks") and not hasattr(w, "_page_released")  # no watchers of their own
    w.canvas.set_image(w._live)
    w.canvas._shown = (0, 0, 400, 300)  # where the page is on the canvas
    now = setup.clock.now
    v.frames.append((now + 0.2, _page(7)))  # the click opens the viewer's toolbar
    w._forward_click(SimpleNamespace(x=50, y=60))  # reader mode: the click goes on to the viewer
    assert clicks and clicks[0][0] == VIEWER.hwnd and w._following.op is not None  # followed from the frame on show
    assert w._following.op.reference is w._live_thumb and w._following.op.key == ""
    setup.clock.run(2)
    assert w._live is v.frames[-1][1] and len(v.captures) >= 4  # followed: shown, and translated (Auto off)
    assert w._auto_last is not None and w.busy
    w.job_done()

    taken = w._auto_last  # once a page was taken: followed from that one, as a key is
    v.frames.append((setup.clock.now + 0.2, _page(8)))
    w.role_var.set("translator")  # (a page not translated on show: the Translator's click goes on too, and is said)
    w._forward_click(SimpleNamespace(x=50, y=60))
    assert w._following.op.reference is taken and w.statuses[-1] == "Sent a click to the viewer..."
    w.role_var.set("reader")
    setup.clock.run(2)
    assert w._live is v.frames[-1][1]
    w.job_done()
    count = len(v.captures)
    w._forward_click(SimpleNamespace(x=500, y=60))  # beside the page: nothing goes on, nothing is followed
    setup.clock.run(5)
    assert len(clicks) == 2 and len(v.captures) == count


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


def test_while_taslation_covers_the_viewer_it_is_looked_at_until_it_draws_again(setup):
    v = setup.viewer
    w = setup.make(auto=False)
    w.start()
    setup.clock.run(2)
    good = v.frames[0][1]
    w.own = [(0, 0, 1920, 1040)]  # maximised over the viewer, which stops drawing
    now = setup.clock.now
    v.frames.append((now, Image.new("RGB", (960, 720), "white")))
    w.events.notes.append(("front", OTHER))
    w.events.notes.append(("front", OWN))  # back to TASlation: one look, which finds the viewer covered
    setup.clock.run(0.2)
    covered = ("The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or move it "
               "so that a strip of the viewer stays visible.")
    assert w._covered and w.canvas.banner == covered and w.statuses[-1] == covered and w._live is good
    count = len(v.captures)
    setup.clock.run(7)
    assert len(v.captures) - count in (9, 10)  # looked at every auto_interval_ms while it lasts
    v.frames.append((setup.clock.now, good.copy()))  # un-maximised: the viewer draws again
    setup.clock.run(1)
    assert not w._covered and w.canvas.banner == "" and w.statuses[-1] == "Viewer: Yomizuq - Google Chrome"
    count = len(v.captures)
    setup.clock.run(30)
    assert len(v.captures) == count  # and no more looks


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


def test_a_page_job_the_window_can_cancel_gives_way_to_the_sharp_frame_and_to_a_new_page(setup):
    """Where a page job carries its own cancel event (the window's `_page_cancel`, as Stop cancels it), the job on
    a soft picture is cancelled as soon as the sharp one is there - nothing of it reaches the cache, so nothing is
    dropped - and so is the job on a page the reader has turned away from."""
    v = setup.viewer
    w = setup.make()
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
    _turn(setup, w, (0.15, soft), (1.0, sharp))
    setup.clock.run(0.8)
    cancel = w._page_cancel
    assert [p for _t, p in w.new_pages][-1] is soft and w.busy and not cancel.is_set()
    setup.clock.run(1.2)  # the sharp picture: the job on the soft one is cancelled at once
    assert cancel.is_set() and w._cancel_why == "page" and w._queued == ("auto", ())
    cancelled_job_ends()
    assert [p for _t, p in w.new_pages][-1] is sharp and not w.pipeline.forgotten  # nothing of the soft job to drop
    cancel = w._page_cancel  # the job on the sharp page runs ...
    page5 = _page(5)
    _turn(setup, w, (0.15, page5))  # ... and the reader turns on: it gives way to the new page
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
    for _step in range(5):  # more input while the cancelled job ends: nothing more is captured for it
        v.input[0] += 100
        setup.clock.run(0.1)
    setup.clock.run(2)
    assert len(v.captures) == before + 2 and len(w.new_pages) == 1
    w._handle_event("page_cancelled", {})  # what the worker says of a cancelled page: no result, then done
    w._handle_event("translate_done", {})
    assert [p for _t, p in w.new_pages][1:] == [page2] and len(v.captures) == before + 3  # taken at once: settled
    assert w.busy and w._page_cancel is not cancel
    assert not any("Stopped" in line for line in w.statuses)  # a page given way is not "stopped"


def _pressing(setup, monkeypatch):
    """Keys pressed for real (`capture.press_briefly`), kept as the times they came."""
    pressed: list[float] = []
    monkeypatch.setattr(live, "press_briefly", lambda hwnd, key: pressed.append(setup.clock.now) or True)
    return pressed


def test_a_slow_viewer_is_waited_for_and_the_key_is_sent_once(setup, monkeypatch):
    """The browser-based viewer showed the next page only 2.5 s after the posted key: no second press before
    page_turn_wait_ms without any change at all, so no page is skipped."""
    v = setup.viewer
    pressed = _pressing(setup, monkeypatch)
    w = setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    page2 = _page(2)
    sent = _turn(setup, w, (2.5, page2))
    setup.clock.run(6)
    assert [key for _t, key in v.keys] == ["Left"] and pressed == []  # exactly one key
    assert [p for _t, p in w.new_pages][1:] == [page2] and 2.5 < w.new_pages[1][0] - sent < 3.2


def test_a_loading_indicator_says_the_viewer_took_the_key(setup, monkeypatch):
    """Any change of the frame at all after the key - a loading indicator, a partial repaint - says the viewer took
    it: never pressed again, and the page is waited for beyond page_turn_wait_ms."""
    v = setup.viewer
    pressed = _pressing(setup, monkeypatch)
    w = setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    loading = v.frames[0][1].copy()
    ImageDraw.Draw(loading).rectangle((470, 350, 480, 360), fill=(120, 120, 120))  # a spinner over the page
    assert not frames_differ(thumbnail(v.frames[0][1]), thumbnail(loading))  # no page turn to Auto's look ...
    page2 = _page(2)
    sent = _turn(setup, w, (0.5, loading), (4.2, page2))  # ... but a change all the same
    setup.clock.run(8)
    assert [key for _t, key in v.keys] == ["Left"] and pressed == []
    assert [p for _t, p in w.new_pages][1:] == [page2] and w.new_pages[1][0] - sent > 4.2
    assert "The viewer did not change (end of book, or the key means nothing there)." not in w.statuses


def test_a_key_pressed_for_real_that_turns_two_pages_is_said(setup, monkeypatch):
    """The posted key changed nothing for page_turn_wait_ms and was pressed for real; then the page turned twice
    within a second (the posted key had arrived after all): the status line says so, with the key back one page."""
    v = setup.viewer
    w = setup.make()
    pages = [_page(2), _page(3)]

    def press(hwnd, key):  # the posted key arrives late, together with the real press: two turns
        v.frames.extend([(setup.clock.now + 0.1, pages[0]), (setup.clock.now + 0.75, pages[1])])
        return True

    monkeypatch.setattr(live, "press_briefly", press)
    w.start()
    setup.clock.run(3)
    w.job_done()
    w.forward_key("Left")
    setup.clock.run(6)
    line = "The viewer turned two pages; press → once to go back."
    assert line in w.statuses and w.canvas.note == line  # on the page for a while too
    assert [p for _t, p in w.new_pages][-1] is pages[1] and w.statuses.count(line) == 1
    w.job_done()
    w._say_two_turns("Space")  # a key without one that turns back: the turns alone
    assert w.statuses[-1] == "The viewer turned two pages."
    i18n.set_language("ja")
    try:
        w._say_two_turns("PageUp")  # in the window's language, the key back named as the reader knows it
        assert w.statuses[-1] == "ビューアが 2 ページめくりました。PageDown を 1 回押すと 1 ページ戻ります。"
    finally:
        i18n.set_language("en")


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


def _learned_real(setup, monkeypatch, w):
    """The first key of *w*'s viewer: posted, ignored, and taken pressed for real."""
    v = setup.viewer
    monkeypatch.setattr(live, "press_briefly",
                        lambda hwnd, key: v.frames.append((setup.clock.now + 0.1, _page(9))) or True)
    w.start()
    setup.clock.run(3)
    w.job_done()
    w.forward_key("Left")
    setup.clock.run(6)
    w.job_done()


@pytest.mark.parametrize("follow", ["events", "poll"])
def test_a_viewer_of_real_keys_gets_them_at_once_for_the_session(setup, monkeypatch, follow):
    """No wait for a posted key that does nothing: the page turns within a second, not after page_turn_wait_ms."""
    v = setup.viewer
    monkeypatch.setattr(reading, "time", live.time)  # (the test's clock)
    w = setup.make(follow=follow, auto=False) if follow == "poll" else setup.make()
    _learned_real(setup, monkeypatch, w)
    assert len(v.keys) == 1 and key_ways(w).real(VIEWER.hwnd) and not key_ways(w).posted(VIEWER.hwnd)
    turned = []
    monkeypatch.setattr(reading, "press_briefly",
                        lambda hwnd, key: turned.append(key) or v.frames.append((setup.clock.now + 0.1, _page(10))) or True)
    before = len(w.statuses)
    w.role_var.set("translator")
    w.forward_key("Left")
    setup.clock.run(0.05)  # (the keys gathered for one handover: reading.KEY_QUIET_MS)
    assert turned == ["Left"] and len(v.keys) == 1  # nothing posted
    assert w.statuses[before:] == ["Sent ← to the viewer..."]  # the status line as for a posted key
    setup.clock.run(1.2)
    assert w._live is v.frames[-1][1]


def _real_keys(setup, monkeypatch):
    """A window whose viewer has been seen to take only keys pressed for real; every handover recorded as the list
    of its keys (a viewer that turns one page a key)."""
    v = setup.viewer
    monkeypatch.setattr(reading, "time", live.time)  # (the test's clock)
    w = setup.make()
    _learned_real(setup, monkeypatch, w)
    handovers = []

    def press(hwnd, keys):
        keys = [keys] if isinstance(keys, str) else list(keys)
        handovers.append(keys)
        for _ in keys:
            v.frames.append((setup.clock.now + 0.1, _page(20 + sum(map(len, handovers)))))
        return True

    monkeypatch.setattr(reading, "press_briefly", press)
    return w, handovers


def test_keys_pressed_while_the_window_was_busy_go_in_one_handover(setup, monkeypatch):
    """Keys that came while the window was busy come out of its queue a few ms apart: one handover for all of them,
    in order, none dropped, none twice, and the page followed once from the frame before them."""
    w, handovers = _real_keys(setup, monkeypatch)
    followed = []
    monkeypatch.setattr(w, "_follow_change", lambda hwnd, reference, key, started, retried=False, seq=None:
                        followed.append((key, retried)), raising=False)
    for key in ("Left", "Left", "Right"):
        w.forward_key(key)
    setup.clock.run(reading.KEY_QUIET_MS / 1000 + 0.001)
    assert handovers == []  # (not yet: two came after the first, more may come)
    setup.clock.run(reading.KEY_QUIET_MS / 1000)
    assert handovers == [["Left", "Left", "Right"]] and followed == [("Right", True)]
    setup.clock.run(1)
    assert handovers == [["Left", "Left", "Right"]]  # sent once


def test_a_key_within_the_quiet_time_joins_the_handover_and_each_later_key_gets_its_own(setup, monkeypatch):
    w, handovers = _real_keys(setup, monkeypatch)
    quiet = reading.KEY_QUIET_MS / 1000
    w.forward_key("Left")
    setup.clock.run(quiet * 0.75)
    w.forward_key("Left")  # the wait starts again
    setup.clock.run(quiet * 0.75)
    assert handovers == []
    setup.clock.run(quiet)
    assert handovers == [["Left", "Left"]]
    for _ in range(3):  # a person's keys, 0.5 s apart: one handover each, at once
        w.forward_key("Left")
        setup.clock.run(0.5)
    assert handovers == [["Left", "Left"], ["Left"], ["Left"], ["Left"]]


def test_keys_that_keep_coming_are_held_back_only_briefly(setup, monkeypatch):
    w, handovers = _real_keys(setup, monkeypatch)
    quiet = reading.KEY_QUIET_MS / 1000
    sent_at = None
    for n in range(40):  # a key every 3/4 of the quiet time: the wait would never end
        w.forward_key("Left")
        setup.clock.run(quiet * 0.75)
        if handovers and sent_at is None:
            sent_at = n
    assert sent_at is not None and sent_at * quiet * 0.75 <= (reading.KEY_GATHERS + 1) * quiet
    assert sum(map(len, handovers)) <= 40 and all(handovers)
    setup.clock.run(1)
    assert sum(map(len, handovers)) == 40  # every key went, once


def test_a_key_for_a_viewer_no_longer_chosen_is_dropped(setup, monkeypatch):
    w, handovers = _real_keys(setup, monkeypatch)
    w.forward_key("Left")
    w.selected = SimpleNamespace(hwnd=VIEWER.hwnd + 1, title=VIEWER.title)
    setup.clock.run(0.1)
    assert handovers == []


@pytest.mark.parametrize("follow", ["events", "poll"])
def test_a_viewer_that_takes_posted_keys_keeps_getting_them(setup, monkeypatch, follow):
    v = setup.viewer
    monkeypatch.setattr(reading, "time", live.time)  # (the test's clock)
    w = setup.make(follow=follow, auto=False) if follow == "poll" else setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    for page in (2, 3):
        w.forward_key("Left")
        v.frames.append((setup.clock.now + 0.1, _page(page)))
        setup.clock.run(2)
        w.job_done()
    assert len(v.keys) == 2 and v.pressed == [] and key_ways(w).posted(VIEWER.hwnd)
    assert not key_ways(w).real(VIEWER.hwnd)


def test_a_real_key_that_cannot_be_pressed_is_posted_and_followed_as_ever(setup, monkeypatch):
    v = setup.viewer
    w = setup.make()
    _learned_real(setup, monkeypatch, w)
    monkeypatch.setattr(reading, "press_briefly", lambda hwnd, key: False)
    pressed = []
    monkeypatch.setattr(live, "press_briefly", lambda hwnd, key: pressed.append(hwnd) or
                        v.frames.append((setup.clock.now + 0.1, _page(10))) or True)
    w.forward_key("Left")
    setup.clock.run(0.05)  # (the keys gathered for one handover: reading.KEY_QUIET_MS)
    assert len(v.keys) == 2
    setup.clock.run(3.2)
    assert pressed == [VIEWER.hwnd]


def test_a_key_a_browser_did_not_take_is_never_posted(setup, monkeypatch):
    """Measured: a key posted to a browser that is not in front reaches nothing (0 of 9, Chrome and Edge 156). When
    the foreground did not come for a real press, nothing is posted and the reader is told to turn the page there."""
    from taslation.capture import windows as W

    v = setup.viewer
    for module in (reading, live, W):
        monkeypatch.setattr(module, "window_class", lambda hwnd: W.BROWSER_CLASSES[0])
    w = setup.make()
    w.start()
    setup.clock.run(3)
    w.job_done()
    monkeypatch.setattr(reading, "press_briefly", lambda hwnd, key: False)
    w.forward_key("Left")
    setup.clock.run(0.05)  # (the keys gathered for one handover: reading.KEY_QUIET_MS)
    assert v.keys == [] and w.statuses[-1] == "The browser did not take the key: click the book and turn the page there."


def test_each_window_handle_learns_for_itself(setup, monkeypatch):
    w = setup.make()
    _learned_real(setup, monkeypatch, w)
    assert key_ways(w).real(VIEWER.hwnd) and not key_ways(w).real(VIEWER.hwnd + 1)
