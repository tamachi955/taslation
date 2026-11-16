"""A new page the cache does not hold, started on its first changed frame (``early_start``, follow = "events": the live
view's `_early_start`): its job reads the page at once, but asks the model nothing and keeps nothing until the frame is
confirmed - unchanged for the viewer's confirmation time (`live.confirm_ms`, learnt from its turns, kept in its
profile); a frame that changes first drops the job, nothing of it lasts, and the page starts again on the new frame.
Pages the cache holds, blank and black frames and focus redraws go as without it. The viewer's frames are counted, its
window in front; the worker is a stand-in on the fake clock that reads a page in READ_S and asks the model for ASK_S
(tests/test_early_start_pipeline.py: the real pipeline's part)."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from test_follow import BROWSER, VIEWER, Clock, Window, _page

from taslation.capture import WindowInfo
from taslation.config import Settings
from taslation.pagekeys import SETTLE_SEEN, Profiles
from taslation import recovery
from taslation.pipeline import PageGate
from taslation.regions import PageResult
from taslation.ui import jobs, live
from taslation.ui.live import CONFIRM_FLOOR_MS, CONFIRM_MARGIN_MS, CONFIRM_WINDOW, confirm_ms

STEP_MS = 10  # the worker's stand-in looks at its job so often
READ_S, ASK_S, CANCEL_S = 0.3, 0.5, 0.03  # a page read (detection and OCR), the model's answer, a cancel taking hold
OTHER_VIEWER = WindowInfo(hwnd=9, title="Pagewell Reader", class_name="PagewellWindow", pid=9, rect=(0, 0, 960, 720))


class Worker:
    """The window's worker as it runs a page job (`_job_translate`), on the fake clock: it reads the page for READ_S;
    then, its gate confirmed (a job with no gate goes on at once), asks the model for ASK_S, stores the page and shows
    it. With *asks* False (every line reused) the page is stored and shown as soon as it is read, and kept once the
    gate is confirmed. A cancel - or a gate dropped - ends a job CANCEL_S later: what it did lasts only when its gate
    was confirmed first. ``jobs``: what each job did, when; ``kept``: the pages whose store lasted, in order."""

    def __init__(self, w, clock, name, asks=True):
        self.w, self.clock, self.name, self.asks = w, clock, name, asks
        self.jobs: list[SimpleNamespace] = []
        self.kept: list[str] = []

    def put(self, _job):
        w = self.w
        job = SimpleNamespace(frame=w._job_frame, name=self.name(w._job_frame), gate=w._page_gate,
                              cancel=w._page_cancel, start=self.clock.now, cancel_seen=None, asked=None, shown=None,
                              stored=None, ended=None, how=None, discarded=None, result=None)
        self.jobs.append(job)
        self._again(job)

    def of(self, name):
        return [j for j in self.jobs if j.name == name]

    def one(self, name):
        jobs = self.of(name)
        assert len(jobs) == 1, (name, [(j.name, j.start) for j in self.jobs])
        return jobs[0]

    def _again(self, job):
        self.clock.after(STEP_MS, lambda: self._tick(job))

    def _tick(self, job):
        now, gate = self.clock.now, job.gate
        confirmed = gate is None or gate.confirmed
        if job.shown is not None and confirmed:  # shown, and its frame confirmed: kept (`PageWork.settle`)
            self._keep(job)
            return self._end(job, "done")
        if job.cancel.is_set() or (gate is not None and gate.state == "dropped"):
            if job.cancel_seen is None:
                job.cancel_seen = now
            if now - job.cancel_seen + 1e-9 < CANCEL_S:
                return self._again(job)
            lasts = gate is None or gate.close()
            job.discarded = not lasts
            data = {"gate": gate, "discarded": job.discarded, "stored": []}
            if job.shown is not None:
                data["result"] = job.result
            self.w._handle_event("page_cancelled", data)
            return self._end(job, "cancelled")
        if now - job.start + 1e-9 < READ_S or job.shown is not None:
            return self._again(job)  # reading; or shown, and waiting for its frame
        if self.asks:
            if not confirmed:
                return self._again(job)  # read; it waits at the gate (`Pipeline._translate_regions`)
            if job.asked is None:
                job.asked = now
            if now - job.asked + 1e-9 < ASK_S:
                return self._again(job)
        job.shown = now
        job.result = PageResult(image=job.frame.copy(), original=job.frame.copy(), regions=[], cache_misses=1)
        self.w._handle_event("result", {"result": job.result, "gate": gate, "stored": [(job.name, 1.0)]})
        if confirmed:
            self._keep(job)
            return self._end(job, "done")
        return self._again(job)  # shown; it waits for its frame

    def _keep(self, job):
        job.stored = self.clock.now
        self.kept.append(job.name)

    def _end(self, job, how):
        job.ended, job.how = self.clock.now, how
        self.w._handle_event("translate_done", {})


@pytest.fixture
def follow(hidden_root, monkeypatch, tmp_path):
    """A window following the viewer by events, the viewer in front and its frames counted; the frames are the test's
    (`show`), each named; the gates record when they were confirmed and dropped."""
    return _environment(hidden_root, monkeypatch, tmp_path / "profiles.json")


def _environment(hidden_root, monkeypatch, path):
    """(`follow`) A clock, a viewer and their window of their own, the viewer's profile kept in *path*."""
    clock = Clock()
    first = _page(1)
    viewer = SimpleNamespace(frames=[(0.0, first)], captures=[])
    names: dict[int, str] = {id(first): "1"}

    class Gate(PageGate):
        def __init__(self):
            super().__init__()
            self.made, self.confirmed_at, self.dropped_at = clock.now, None, None

        def confirm(self):
            ok = super().confirm()
            if ok and self.confirmed_at is None:
                self.confirmed_at = clock.now
            return ok

        def drop(self):
            super().drop()
            if self.state == "dropped" and self.dropped_at is None:
                self.dropped_at = clock.now

    def frame_now():
        current = viewer.frames[0][1]
        for since, frame in viewer.frames:
            if clock.now >= since:
                current = frame
        return current

    def capture_window(hwnd, client_only=True, allow_screen_fallback=True):
        viewer.captures.append(clock.now)
        return frame_now()

    monkeypatch.setattr(live, "PageGate", Gate)
    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(jobs, "time", SimpleNamespace(monotonic=clock.monotonic))  # (the job watch's looks too)
    monkeypatch.setattr(live, "capture_window", capture_window)
    _viewer_in_front(monkeypatch, clock, lambda: viewer.frames)

    def make(early=True, asks=True, profiles=None, selected=VIEWER):
        w = Window(hidden_root, clock, owner="viewer")
        w.settings.early_start = early
        w.selected = selected
        w._starts_book = lambda image: False  # (the book is started: tests/test_start_flow.py)
        w._enlarge_asked = selected.hwnd  # (the window enlarged for this viewer already: tests/test_enlarge.py)
        w.profiles = profiles if profiles is not None else Profiles(path)
        w._jobs = worker = Worker(w, clock, lambda image: names.get(id(image), "?"), asks)
        w.start()
        clock.run(3)  # page 1 taken and done
        assert worker.kept == ["1"]
        return w, worker

    def show(*frames, run=3.0):
        """The viewer shows *frames* - (delay, name, picture) - from 0.3 s on; the clock run for *run* s. When the
        first of them came."""
        turned = clock.now + 0.3
        for delay, name, picture in frames:
            names[id(picture)] = name
            viewer.frames.append((turned + delay, picture))
        clock.run(run)
        return turned

    return SimpleNamespace(clock=clock, viewer=viewer, make=make, show=show, path=path, names=names)


def _viewer_in_front(monkeypatch, clock, frames):
    """The viewer's window in front, its frames counted (`capture.frame_count`: one more each time *frames*() - a list
    of (from time, picture) - has a new picture), the black watch on the same clock."""
    def count(hwnd):
        return 1 + sum(1 for since, _f in frames()[1:] if clock.now >= since)
    monkeypatch.setattr(live, "frame_count", count)
    monkeypatch.setattr(recovery, "frame_count", count)
    monkeypatch.setattr(recovery, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "client_rect_on_screen", lambda hwnd: (0, 0, 960, 720))
    monkeypatch.setattr(live, "foreground_owner", lambda hwnd, viewer_hwnd: "viewer")
    monkeypatch.setattr(live, "foreground_window", lambda: BROWSER)
    monkeypatch.setattr(live, "last_input", lambda: 1)
    monkeypatch.setattr(live, "window_at_pointer", lambda: 0)


def _after(seconds, wait):
    """Whether a confirmation came *seconds* after the frame: *wait* after it, give or take the frame's first look
    and the step after the wait (FRAME_STEP_MS each)."""
    return wait - 0.001 <= seconds <= wait + 0.035


def _learnt(follow, ms_each=0, turns=3):
    """The viewer's profile with *turns* turns of *ms_each* ms (its confirmation time learnt)."""
    Profiles(follow.path).set_settle_seen(VIEWER, [ms_each] * turns)


# ------------------------------------------------------------------ the time to the first request
@pytest.mark.parametrize("early", [False, True])
def test_a_sharp_page_starts_on_its_first_frame_and_asks_once_confirmed(follow, early):
    _learnt(follow)  # this viewer turns in one frame: confirmed after the floor
    w, worker = follow.make(early=early)
    page = _page(2)
    turned = follow.show((0.0, "2", page))
    job = worker.one("2")
    assert worker.kept == ["1", "2"] and job.how == "done"
    if not early:  # as before: started once settle_ms passed with no new frame
        assert job.gate is None and 0.4 <= job.start - turned <= 0.43
        assert job.asked - turned == pytest.approx(job.start - turned + READ_S, abs=0.011)
        return
    assert job.start - turned <= 0.016  # at its first frame (seen within FRAME_STEP_MS)
    gate = job.gate
    assert _after(gate.confirmed_at - turned, CONFIRM_FLOOR_MS / 1000)  # the learnt time
    assert job.asked >= gate.confirmed_at and job.asked - turned <= READ_S + 0.03  # the read alone before the request
    assert job.stored > gate.confirmed_at
    assert w.last_result is job.result


def test_the_settle_wait_is_gone_from_the_time_to_the_first_request(hidden_root, monkeypatch, tmp_path):
    asked, shown = {}, {}
    for early in (False, True):
        with monkeypatch.context() as patched:
            env = _environment(hidden_root, patched, tmp_path / f"profiles-{early}.json")
            _learnt(env)
            _w, worker = env.make(early=early)
            turned = env.show((0.0, "2", _page(2)))
            job = worker.one("2")
            asked[early], shown[early] = job.asked - turned, job.shown - turned
    assert asked[False] - asked[True] >= 0.38, asked  # the 400 ms settle_ms, all but a frame step ...
    assert shown[False] - shown[True] >= 0.38, shown  # ... from the first request and from the page lettered


def test_a_new_viewer_waits_settle_ms_for_its_confirmation_and_learns_its_turns(follow):
    w, worker = follow.make()  # no turn seen yet: 400 ms (`confirm_ms`)
    assert w._turns_seen(VIEWER.hwnd) == [0]  # (page 1: settled when it was seen)
    turned = follow.show((0.0, "2", _page(2)))
    job = worker.one("2")
    assert job.start - turned <= 0.016 and _after(job.gate.confirmed_at - turned, 0.4)
    assert job.asked == pytest.approx(job.gate.confirmed_at, abs=0.011)  # (the read was done by then)
    follow.show((0.0, "3", _page(3)))
    assert w._turns_seen(VIEWER.hwnd) == [0, 0, 0] and confirm_ms([0, 0, 0], 400) == CONFIRM_FLOOR_MS
    turned = follow.show((0.0, "4", _page(4)))
    assert _after(worker.one("4").gate.confirmed_at - turned, 0.15)  # learnt: the floor


def test_a_page_read_before_its_frame_is_confirmed_is_shown_and_kept_only_then(follow):
    w, worker = follow.make(asks=False)  # every line reused: no request; a new viewer, 400 ms
    turned = follow.show((0.0, "2", _page(2)))
    job = worker.one("2")
    assert job.shown - turned <= READ_S + 0.03 and job.shown < job.gate.confirmed_at  # shown before ...
    assert job.stored == pytest.approx(job.gate.confirmed_at, abs=0.011)  # ... kept once confirmed
    assert worker.kept == ["1", "2"] and w.last_result is job.result


# ------------------------------------------------------------------ frames that change before the confirmation
def test_a_soft_frame_then_the_sharp_one_drops_the_first_job_and_keeps_the_sharp_page(follow):
    w, worker = follow.make()
    soft, sharp = _page(4, soft=3), _page(4)
    seen_before = len(w._turns_seen(VIEWER.hwnd))
    turned = follow.show((0.0, "4 soft", soft), (0.25, "4", sharp))
    first, second = worker.one("4 soft"), worker.one("4")
    assert first.start - turned <= 0.016 and first.gate.state == "dropped" and first.gate.confirmed_at is None
    assert first.gate.dropped_at - (turned + 0.25) <= 0.016  # dropped at the sharp frame's first look ...
    assert first.ended - first.gate.dropped_at <= CANCEL_S + 0.011  # ... its job ended at once ...
    assert first.asked is None and first.stored is None and first.discarded  # ... nothing asked, nothing kept
    assert second.start - first.ended <= 0.016  # the sharp frame started as soon as the worker was free
    assert _after(second.gate.confirmed_at - (turned + 0.25), 0.4)
    assert second.asked is not None and second.how == "done"
    assert worker.kept == ["1", "4"] and w.pipeline.forgotten == []  # (the soft job stored nothing to forget)
    assert w.last_result is second.result and w.last_result.original.tobytes() == sharp.tobytes()
    seen = w._turns_seen(VIEWER.hwnd)
    assert len(seen) == seen_before + 1 and 240 <= seen[-1] <= 265  # one turn: first frame to the sharp one


def test_frames_of_an_animation_ask_nothing_and_keep_nothing(follow):
    w, worker = follow.make()
    final = _page(2)
    sliding = [Image.fromarray(np.roll(np.asarray(final), 40 * k, axis=1)) for k in (4, 3, 2, 1)]
    turned = follow.show(*[(0.05 * i, f"slide {i}", f) for i, f in enumerate(sliding)], (0.2, "2", final))
    for job in worker.jobs:
        if job.name.startswith("slide"):
            assert job.gate.confirmed_at is None and job.asked is None and job.stored is None, job
    assert worker.kept == ["1", "2"] and [j.name for j in worker.jobs if j.asked is not None] == ["1", "2"]
    assert _after(worker.one("2").gate.confirmed_at - (turned + 0.2), 0.4)
    assert w.pipeline.forgotten == []


@pytest.mark.parametrize("early", [False, True])
def test_pages_flipped_faster_than_the_floor_ask_nothing_and_keep_nothing(follow, early):
    _learnt(follow)  # the shortest confirmation: 150 ms
    w, worker = follow.make(early=early)
    pages = [(0.1 * i, f"p{i}", _page(20 + i)) for i in range(5)]  # each shown 100 ms, the last one stays
    turned = follow.show(*pages)
    asked = [j.name for j in worker.jobs if j.asked is not None]
    assert asked == ["1", "p4"] and worker.kept == ["1", "p4"]
    last = worker.one("p4")
    if early:
        assert _after(last.gate.confirmed_at - (turned + 0.4), 0.15)
        assert all(j.gate.state == "dropped" for j in worker.jobs if j.name.startswith("p") and j.name != "p4")
        assert all(j.ended is not None for j in worker.jobs)  # (every job ended: none left waiting)
    else:
        assert [j.name for j in worker.jobs] == ["1", "p4"]  # nothing started before p4 settled


def test_a_page_shown_past_the_floor_then_turned_has_its_job_cancelled_at_once(follow):
    _learnt(follow)  # 150 ms
    w, worker = follow.make()
    turned = follow.show((0.0, "2", _page(2)), (0.2, "3", _page(3)))  # page 2 confirmed, then page 3 at 200 ms
    two, three = worker.one("2"), worker.one("3")
    assert two.gate.confirmed_at is not None and two.asked is None  # confirmed, still reading when 3 came ...
    assert two.how == "cancelled" and two.ended - (turned + 0.2) <= CANCEL_S + 0.03  # ... cancelled at once
    assert three.start - two.ended <= 0.016 and three.how == "done" and worker.kept == ["1", "3"]
    seen = w._turns_seen(VIEWER.hwnd)
    assert 195 <= seen[-2] <= 215  # page 2's turn amended: another page came 200 ms after its first frame


# ------------------------------------------------------------------ a change after the confirmation
def test_a_sharper_frame_after_the_confirmation_replaces_the_page_kept_and_lengthens_the_wait(follow):
    _learnt(follow)  # 150 ms: the soft frame is confirmed before the sharp one comes
    w, worker = follow.make(asks=False)
    soft, sharp = _page(4, soft=3), _page(4)
    turned = follow.show((0.0, "4 soft", soft), (0.35, "4", sharp))
    first, second = worker.one("4 soft"), worker.one("4")
    assert _after(first.gate.confirmed_at - turned, 0.15)
    assert first.stored is not None and first.stored < turned + 0.35  # kept before the sharp frame came
    forgotten = w.pipeline.forgotten[-1]
    assert [(u.fingerprint, u.aspect) for u in forgotten.units] == [("4 soft", 1.0)]  # what it stored is dropped
    assert second.gate is None and second.start - (turned + 0.35) <= 0.016  # read again from the sharp frame
    assert worker.kept == ["1", "4 soft", "4"] and w.last_result is second.result
    seen = w._turns_seen(VIEWER.hwnd)
    assert 340 <= seen[-1] <= 365 and confirm_ms(seen, 400) == 400  # the turn took that long: the wait grows
    assert Profiles(follow.path).settle_seen_for(VIEWER) == seen  # (an amended turn is written at once)


# ------------------------------------------------------------------ the confirmation time learnt
def test_the_confirmation_time_is_the_longest_recent_turn_plus_a_margin_within_its_bounds():
    assert confirm_ms([], 400) == 400 and confirm_ms([0, 0], 400) == 400  # too few turns: settle_ms
    assert confirm_ms([0, 0, 0], 400) == CONFIRM_FLOOR_MS  # at least the floor
    assert confirm_ms([90, 120, 100], 400) == 120 + CONFIRM_MARGIN_MS
    assert confirm_ms([90, 900, 100], 400) == 400  # at most settle_ms
    assert confirm_ms([0, 0, 0], 100) == 100  # (a settle_ms under the floor is the ceiling still)
    outlier = [100] * 5 + [2000] + [100] * (CONFIRM_WINDOW - 1)
    assert confirm_ms(outlier, 400) == 400  # an outlier holds while it is among the last CONFIRM_WINDOW ...
    assert confirm_ms(outlier + [100], 400) == 180  # ... and is forgotten after


def test_the_turns_learnt_persist_per_viewer_and_bad_values_are_left_out(follow, tmp_path):
    w, _worker = follow.make()
    for ms in (120, 90, 100):
        w._note_turn(VIEWER.hwnd, ms / 1000)
    assert w._turns_seen(VIEWER.hwnd) == [0, 120, 90, 100]
    again = Profiles(follow.path)  # a new start: the store read anew
    assert again.settle_seen_for(VIEWER) == [0, 120, 90]  # written when the time changed (the third turn) ...
    assert confirm_ms([0, 120, 90], 400) == confirm_ms([0, 120, 90, 100], 400) == 200  # ... the same time: 120 + 80
    assert again.settle_seen_for(OTHER_VIEWER) == []  # per viewer
    fresh = Window(w.canvas.master, follow.clock, owner="viewer")
    fresh.settings.early_start, fresh.profiles = True, again
    assert confirm_ms(fresh._turns_seen(VIEWER.hwnd), 400) == 200
    fresh.selected = OTHER_VIEWER
    assert fresh._turns_seen(OTHER_VIEWER.hwnd) == []
    for turns in range(1, 12):  # written when the time changes, and every CONFIRM_SAVE_EVERY turns after
        fresh._note_turn(OTHER_VIEWER.hwnd, 0.3)
        written = Profiles(follow.path).settle_seen_for(OTHER_VIEWER)
        assert written == ([] if turns < 3 else [300] * 3 if turns < 11 else [300] * 11), turns
    assert Profiles(follow.path).settle_seen_for(VIEWER) == [0, 120, 90]  # (the other viewer's stays)

    bad = tmp_path / "bad.json"
    profiles = Profiles(bad)
    profiles.set_settle_seen(VIEWER, [100])
    data = profiles.data
    key = next(k for k, v in data.items() if isinstance(v, dict) and SETTLE_SEEN in v)
    data[key][SETTLE_SEEN] = [100, "x", -5, True, 70000, 2.5, None, 200]
    bad.write_text(__import__("json").dumps(data), encoding="utf-8")
    assert Profiles(bad).settle_seen_for(VIEWER) == [100, 2, 200]


def test_an_outlier_turn_is_forgotten_after_a_window_of_turns(follow):
    w, _worker = follow.make()
    w._note_turn(VIEWER.hwnd, 2.0)  # a viewer that once took 2 s
    for _i in range(3):
        w._note_turn(VIEWER.hwnd, 0.05)
    assert confirm_ms(w._turns_seen(VIEWER.hwnd), 400) == 400
    for _i in range(CONFIRM_WINDOW):
        w._note_turn(VIEWER.hwnd, 0.05)
    assert confirm_ms(w._turns_seen(VIEWER.hwnd), 400) == CONFIRM_FLOOR_MS
    assert len(Profiles(follow.path).settle_seen_for(VIEWER)) <= 16


# ------------------------------------------------------------------ what goes as without it
def _trace(hidden_root, monkeypatch, tmp_path, early: bool) -> list[tuple]:
    """Pages the cache holds, a focus redraw (a black frame, then the same page again), a blank frame, a page drawn
    again with the same pixels, a soft frame then the sharp one: what the window did, frame by frame - captures,
    jobs (with a gate or not), pages taken, what it showed and said."""
    from taslation import fingerprint as fp
    from taslation.cache import CachedBubble, CachedPage, CacheStore

    clock = Clock()
    a, b_soft, b, c, d = _page(31), _page(32, soft=3), _page(32), _page(33), _page(34)
    black, white = Image.new("RGB", a.size, "black"), Image.new("RGB", a.size, "white")
    t0 = clock.now
    frames = [(t0, a), (t0 + 3.0, black), (t0 + 3.06, a), (t0 + 5.0, b_soft), (t0 + 5.3, b), (t0 + 7.0, white),
              (t0 + 7.1, c), (t0 + 9.0, c), (t0 + 10.0, black), (t0 + 10.1, d)]
    names = {id(a): "a", id(b_soft): "b soft", id(b): "b", id(c): "c", id(d): "d", id(black): "black",
             id(white): "white"}
    labels: dict[int, str] = {}
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
        kept.append(copy)  # (alive, so that no later picture takes its id)
        labels[id(copy)] = names[id(source)]
        trace.append(("capture", round(clock.now - t0, 3), names[id(source)]))
        return copy

    def label(image):
        return None if image is None else labels.get(id(image), "?")

    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(jobs, "time", SimpleNamespace(monotonic=clock.monotonic))  # (the job watch's looks too)
    monkeypatch.setattr(live, "capture_window", capture_window)
    _viewer_in_front(monkeypatch, clock, lambda: frames)
    w = Window(hidden_root, clock, owner="viewer")
    w.settings.early_start = early
    w.settings.cache_enabled, w.settings.fingerprint_max_distance = True, 10
    w.settings.black_wait_s = Settings().black_wait_s
    w._enlarge_asked = VIEWER.hwnd
    w._starts_book = lambda image: False
    w.profiles = Profiles(tmp_path / f"profiles-{early}.json")
    w.store = CacheStore(tmp_path / f"cache-{early}")
    w._name_needed = lambda: False
    book = w.store.open("Book", "m", "English")
    for page in (a, b_soft, b, c, d):  # every page in the cache (the soft frame's units too)
        for unit in fp.analyze(np.asarray(page), (0, 0, 0, 0)):
            book.add(CachedPage(unit.fingerprint, unit.width / unit.height, [CachedBubble((0.1, 0.1, 0.3, 0.3), "Hi")]))
    book.save()
    w._jobs = SimpleNamespace(put=lambda job: trace.append(("job", round(clock.now - t0, 3), label(w._job_frame),
                                                            w._page_gate is not None)))
    w.start()
    shown = None
    while clock.now < t0 + 13:
        clock.run(0.05)
        if w.busy:  # the page job: drawn from the cache, done
            w.job_done(PageResult(image=w._job_frame.copy(), original=w._job_frame.copy(), regions=[],
                                  cache_hits=1))
        if label(w._live) != shown:
            shown = label(w._live)
            trace.append(("shown", round(clock.now - t0, 3), shown))
    trace += [("taken", round(t - t0, 3), label(p)) for t, p in w.new_pages]
    trace += [("said", line) for line in w.statuses]
    trace.append(("forgotten", len(w.pipeline.forgotten)))
    return trace


def test_cached_pages_blank_and_black_frames_and_redraws_go_as_without_it(hidden_root, monkeypatch, tmp_path):
    with monkeypatch.context() as patched:
        off = _trace(hidden_root, patched, tmp_path, early=False)
    on = _trace(hidden_root, monkeypatch, tmp_path, early=True)
    assert on == off
    jobs = [entry for entry in on if entry[0] == "job"]
    assert [j[2] for j in jobs] == ["a", "b soft", "b", "c", "d"] and not any(j[3] for j in jobs)  # (no gate)
    captured = {entry[2] for entry in on if entry[0] == "capture"}
    assert {"black", "white"} <= captured  # (the sequence did what it says: its black and blank frames were seen)
