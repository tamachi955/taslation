"""A new page the cache does not hold, started on its first changed frame (``early_start``, follow = "events": the live
view's `_early_start`): its job reads the page at once and asks the model as soon as it has read it and a look after it
asked has found its frame on show still (`PageGate.on_show`, the window's `_frame_seen`) - no wait for a confirmation -;
what it stores lasts once the frame has stayed as it is for twice settle_ms (`live.KEEP_SETTLES`, the same for every
viewer and every turn: nothing learnt, nothing in the profile). A frame that changes first drops the job - its request
cancelled when it runs -, nothing of it lasts, and the page starts again on the new frame. Pages the cache holds, blank
and black frames and focus redraws go as without it. The viewer's frames are counted, its window in front (one test
without the counts); the worker is a stand-in on the fake clock that reads a page in READ_S and asks the model for
ASK_S (tests/test_early_start_pipeline.py: the real pipeline's part)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from test_follow import BROWSER, VIEWER, Clock, Window, _page

from taslation.config import Settings
from taslation.pagekeys import Profiles
from taslation import recovery
from taslation.pipeline import PageGate
from taslation.regions import PageResult
from taslation.ui import jobs, live
from taslation.ui.constants import FOLLOW_STEP_MS, FRAME_STEP_MS
from taslation.ui.live import KEEP_SETTLES, LEFT_PAGE_MS

KEEP_S = KEEP_SETTLES * 0.4  # what a page started early stores lasts once its frame stayed this long (settle_ms 400)

STEP_MS = 10  # the worker's stand-in looks at its job so often
READ_S, ASK_S, CANCEL_S = 0.3, 0.5, 0.03  # a page read (detection and OCR), the model's answer, a cancel taking hold


class Worker:
    """The window's worker as it runs a page job (`_job_translate`), on the fake clock: it reads the page for READ_S;
    then - a job with a gate not confirmed yet once a look of the window's after it asked has found its frame on show
    (`PageGate.on_show`: ``gate_at`` when it asked), a job with no gate or a confirmed one at once - asks the model for
    *ask_s*, stores the page and shows it; what it stored is kept once its gate is confirmed. With *asks* False (every
    line reused) the page is stored and shown as soon as it is read, and kept once the gate is confirmed. A cancel - or
    a gate dropped - ends a job CANCEL_S later, its request with it: what it did lasts only when its gate was confirmed
    first. ``jobs``: what each job did, when; ``kept``: the pages whose store lasted, in order."""

    def __init__(self, w, clock, name, asks=True, ask_s=None):
        self.w, self.clock, self.name, self.asks = w, clock, name, asks
        self.ask_s = ask_s
        self.jobs: list[SimpleNamespace] = []
        self.kept: list[str] = []

    def put(self, _job):
        w = self.w
        job = SimpleNamespace(frame=w._job_frame, name=self.name(w._job_frame), gate=w._page_gate,
                              cancel=w._page_cancel, start=self.clock.now, cancel_seen=None, gate_at=None, asked=None,
                              shown=None, stored=None, ended=None, how=None, discarded=None, result=None)
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
            if job.asked is None:
                if gate is not None and not confirmed:
                    if job.gate_at is None:
                        job.gate_at = now  # read: is its frame on show still? (`Pipeline._translate_regions`)
                    if not gate.seen_since(job.gate_at):
                        return self._again(job)  # waits for the window's next look
                job.asked = now
            if now - job.asked + 1e-9 < (ASK_S if self.ask_s is None else self.ask_s):
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


def _environment(hidden_root, monkeypatch, path, counted=True):
    """(`follow`) A clock, a viewer and their window of their own, the viewer's profile kept in *path*; *counted*
    False: the viewer's frames not counted (`capture.frame_count` None)."""
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
    if not counted:
        monkeypatch.setattr(live, "frame_count", lambda hwnd: None)

    def make(early=True, asks=True, profiles=None, selected=VIEWER, ask_s=None):
        w = Window(hidden_root, clock, owner="viewer")
        w.settings.early_start = early
        w.selected = selected
        w._starts_book = lambda image: False  # (the book is started: tests/test_start_flow.py)
        w._enlarge_asked = selected.hwnd  # (the window enlarged for this viewer already: tests/test_enlarge.py)
        w.profiles = profiles if profiles is not None else Profiles(path)
        w._jobs = worker = Worker(w, clock, lambda image: names.get(id(image), "?"), asks, ask_s)
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


# ------------------------------------------------------------------ the time to the first request
@pytest.mark.parametrize("early", [False, True])
def test_a_sharp_page_starts_on_its_first_frame_and_asks_as_soon_as_it_is_read(follow, early):
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
    assert job.gate_at - job.start == pytest.approx(READ_S, abs=0.011)  # read: is the frame on show still? ...
    assert job.asked - job.gate_at <= FRAME_STEP_MS / 1000 + 0.011  # ... the window's next look said so
    assert job.asked < gate.confirmed_at  # no wait for the confirmation, ...
    assert _after(gate.confirmed_at - turned, KEEP_S)  # ... which comes once the frame stayed twice settle_ms
    assert job.stored >= gate.confirmed_at  # what it stored kept only then
    assert w.last_result is job.result


def test_the_settle_wait_is_gone_from_the_time_to_the_first_request(hidden_root, monkeypatch, tmp_path):
    asked, shown = {}, {}
    for early in (False, True):
        with monkeypatch.context() as patched:
            env = _environment(hidden_root, patched, tmp_path / f"profiles-{early}.json")
            _w, worker = env.make(early=early)
            turned = env.show((0.0, "2", _page(2)))
            job = worker.one("2")
            asked[early], shown[early] = job.asked - turned, job.shown - turned
    # the 400 ms settle_ms, all but a frame step to the first frame and one to the look that let the request go
    assert asked[False] - asked[True] >= 0.36, asked
    assert shown[False] - shown[True] >= 0.36, shown  # ... from the first request and from the page lettered


def test_what_a_page_started_early_stores_lasts_after_the_same_fixed_time_on_every_turn(follow):
    w, worker = follow.make()
    for k in range(4):
        turned = follow.show((0.0, f"p{k}", _page(2 + k)))
        job = worker.one(f"p{k}")
        assert _after(job.gate.confirmed_at - turned, KEEP_S) and job.how == "done", k  # nothing learnt
    assert worker.kept == ["1", "p0", "p1", "p2", "p3"]
    data = json.loads(follow.path.read_text(encoding="utf-8")) if follow.path.exists() else {}
    assert not any("settle_seen" in v for v in data.values() if isinstance(v, dict))  # nothing in the profile


def test_without_frame_counts_the_frame_is_looked_at_every_step_while_its_job_is_unconfirmed(hidden_root, monkeypatch,
                                                                                           tmp_path):
    env = _environment(hidden_root, monkeypatch, tmp_path / "profiles.json", counted=False)
    w, worker = env.make()
    turned = env.show((0.0, "2", _page(2)), run=0.0)
    env.clock.run(3.0)
    job = worker.one("2")
    assert job.how == "done" and worker.kept == ["1", "2"] and job.gate is not None
    looks = [t for t in env.viewer.captures if job.start <= t <= job.gate.confirmed_at]
    gaps = np.diff(looks)
    assert len(looks) >= 8 and gaps.max() <= FOLLOW_STEP_MS / 1000 + 1e-6, gaps  # every FOLLOW_STEP_MS, not settle_ms
    assert job.asked - job.gate_at <= FOLLOW_STEP_MS / 1000 + 0.011  # the request waits for the next look alone
    assert KEEP_S <= job.gate.confirmed_at - job.start <= KEEP_S + FOLLOW_STEP_MS / 1000 + 0.011
    assert job.start - turned <= w.settings.auto_interval_ms / 1000 + 0.016  # (seen at the next poll)


def test_a_page_read_before_its_frame_is_confirmed_is_shown_and_kept_only_then(follow):
    w, worker = follow.make(asks=False)  # every line reused: no request
    turned = follow.show((0.0, "2", _page(2)))
    job = worker.one("2")
    assert job.shown - turned <= READ_S + 0.03 and job.shown < job.gate.confirmed_at  # shown before ...
    assert job.stored == pytest.approx(job.gate.confirmed_at, abs=0.011)  # ... kept once confirmed
    assert worker.kept == ["1", "2"] and w.last_result is job.result


def test_a_page_done_before_its_fixed_time_keeps_nothing_when_its_frame_changes(follow):
    w, worker = follow.make(asks=False)
    turned = follow.show((0.0, "2", _page(2)), (0.5, "3", _page(3)))
    two, three = worker.one("2"), worker.one("3")
    assert two.shown is not None and two.shown < turned + 0.5  # done before page 3 came ...
    assert two.gate.state == "dropped" and two.gate.confirmed_at is None  # ... never confirmed ...
    assert two.discarded and two.stored is None and two.how == "cancelled"  # ... and kept nothing
    assert three.how == "done" and worker.kept == ["1", "3"] and w.last_result is three.result


# ------------------------------------------------------------------ frames that change before the confirmation
def test_a_soft_frame_then_the_sharp_one_before_the_request_drops_the_first_job_and_keeps_the_sharp_page(follow):
    w, worker = follow.make()
    soft, sharp = _page(4, soft=3), _page(4)
    turned = follow.show((0.0, "4 soft", soft), (0.25, "4", sharp))
    first, second = worker.one("4 soft"), worker.one("4")
    assert first.start - turned <= 0.016 and first.gate.state == "dropped" and first.gate.confirmed_at is None
    assert first.gate.dropped_at - (turned + 0.25) <= 0.016  # dropped at the sharp frame's first look ...
    assert first.ended - first.gate.dropped_at <= CANCEL_S + 0.011  # ... its job ended at once ...
    assert first.asked is None and first.stored is None and first.discarded  # ... nothing asked, nothing kept
    assert second.start - first.ended <= 0.016  # the sharp frame started as soon as the worker was free
    assert _after(second.gate.confirmed_at - (turned + 0.25), KEEP_S)
    assert second.asked is not None and second.how == "done"
    assert worker.kept == ["1", "4"] and w.pipeline.forgotten == []  # (the soft job stored nothing to forget)
    assert w.last_result is second.result and w.last_result.original.tobytes() == sharp.tobytes()


def test_a_sharp_frame_that_comes_while_the_soft_frames_request_runs_cancels_it_and_keeps_the_sharp_page(follow):
    w, worker = follow.make()
    soft, sharp = _page(4, soft=3), _page(4)
    turned = follow.show((0.0, "4 soft", soft), (0.42, "4", sharp))
    first, second = worker.one("4 soft"), worker.one("4")
    assert first.asked is not None and first.asked < turned + 0.42  # its request went out on the soft frame ...
    assert first.gate.dropped_at - (turned + 0.42) <= 0.016  # ... and the sharp frame's first look dropped it:
    assert first.cancel_seen - first.gate.dropped_at <= STEP_MS / 1000 + 1e-6  # the request cancelled at once ...
    assert first.how == "cancelled" and first.shown is None and first.stored is None and first.discarded  # nothing
    assert second.start - first.ended <= 0.016 and second.how == "done" and worker.kept == ["1", "4"]
    assert _after(second.gate.confirmed_at - (turned + 0.42), KEEP_S)
    assert w.last_result is second.result and w.last_result.original.tobytes() == sharp.tobytes()


def test_soft_pictures_drawn_longer_than_settle_ms_are_never_kept(follow):
    """The browser-type stand-in viewer draws its soft picture up to 400-420 ms on the screen: settle_ms itself
    confirmed some of those soft frames; twice settle_ms confirms none. Their requests go out and are cancelled."""
    w, worker = follow.make()
    for k in range(4):
        follow.show((0.0, f"p{k} soft", _page(70 + k, soft=3)), (0.42, f"p{k}", _page(70 + k)))
    soft = [j for j in worker.jobs if j.name.endswith("soft")]
    assert len(soft) == 4 and all(j.gate.confirmed_at is None and j.stored is None and j.discarded for j in soft)
    assert all(j.asked is not None and j.how == "cancelled" for j in soft)  # (asked, and cancelled)
    assert worker.kept == ["1", "p0", "p1", "p2", "p3"]


def test_frames_of_an_animation_ask_nothing_and_keep_nothing(follow):
    w, worker = follow.make()
    final = _page(2)
    sliding = [Image.fromarray(np.roll(np.asarray(final), 40 * k, axis=1)) for k in (4, 3, 2, 1)]
    turned = follow.show(*[(0.05 * i, f"slide {i}", f) for i, f in enumerate(sliding)], (0.2, "2", final))
    for job in worker.jobs:
        if job.name.startswith("slide"):
            assert job.gate.confirmed_at is None and job.asked is None and job.stored is None, job
    assert worker.kept == ["1", "2"] and [j.name for j in worker.jobs if j.asked is not None] == ["1", "2"]
    assert _after(worker.one("2").gate.confirmed_at - (turned + 0.2), KEEP_S)
    assert w.pipeline.forgotten == []


@pytest.mark.parametrize("early", [False, True])
def test_pages_flipped_faster_than_a_page_is_read_ask_nothing_and_keep_nothing(follow, early):
    w, worker = follow.make(early=early)
    pages = [(0.1 * i, f"p{i}", _page(20 + i)) for i in range(5)]  # each shown 100 ms, the last one stays
    turned = follow.show(*pages)
    asked = [j.name for j in worker.jobs if j.asked is not None]
    assert asked == ["1", "p4"] and worker.kept == ["1", "p4"]
    last = worker.one("p4")
    if early:
        assert _after(last.gate.confirmed_at - (turned + 0.4), KEEP_S)
        assert all(j.gate.state == "dropped" for j in worker.jobs if j.name.startswith("p") and j.name != "p4")
        assert all(j.ended is not None for j in worker.jobs)  # (every job ended: none left waiting)
    else:
        assert [j.name for j in worker.jobs] == ["1", "p4"]  # nothing started before p4 settled


def test_pages_flipped_through_each_soft_first_keep_the_last_page_alone(follow):
    w, worker = follow.make()
    frames = []
    for k in range(5):  # five pages flipped 120 ms apart, each soft first and sharp 60 ms later; the last one stays
        frames += [(0.12 * k, f"p{k} soft", _page(40 + k, soft=3)), (0.12 * k + 0.06, f"p{k}", _page(40 + k))]
    follow.show(*frames)
    assert worker.kept == ["1", "p4"]


def test_a_flash_within_a_turn_keeps_the_sharp_page(follow):
    w, worker = follow.make()
    w.settings.black_wait_s = Settings().black_wait_s
    soft, sharp = _page(2, soft=3), _page(2)
    black = Image.new("RGB", soft.size, "black")
    follow.show((0.0, "2 soft", soft), (0.1, "black", black), (0.8, "2", sharp))  # a focus flash of 700 ms
    assert worker.kept == ["1", "2"]


def test_a_frame_of_another_size_is_taken_as_ever(follow):
    """The viewer's window narrowed, its page laid out anew."""
    w, worker = follow.make()
    follow.show((0.0, "2 narrow", _page(2).resize((480, 720))))
    assert worker.kept == ["1", "2 narrow"]


def test_the_time_spent_on_a_frame_is_not_added_to_the_wait(follow):
    """The fixed time is counted from the look that saw the frame (`Look.at`), not from after the window had worked
    it out (its thumbnail drawn, its page units read for the cache: 30-170 ms on the stand-in)."""
    w, worker = follow.make()
    clock = follow.clock
    cached = w._all_cached

    def slow(image):  # reading the frame's page units takes 120 ms of the Tk thread
        clock.now += 0.12
        return cached(image)

    w._all_cached = slow
    turned = follow.show((0.0, "3 soft", _page(3, soft=3)), (0.3, "3", _page(3)))
    assert KEEP_S - 0.001 <= worker.one("3").gate.confirmed_at - (turned + 0.3) <= KEEP_S + 0.12, (
        worker.one("3").gate.confirmed_at - (turned + 0.3))


def test_a_page_seen_again_while_the_models_load_waits_for_them(follow):
    w, worker = follow.make()
    w.ready = False  # the models load: a page that settles waits for them, and is followed again at each poll
    follow.show((0.0, "2", _page(2)), run=3.0)
    assert [j.name for j in worker.jobs] == ["1"] and w._queued is not None


def test_a_turn_not_seen_as_it_came_is_taken_as_ever(follow):
    w, worker = follow.make()
    w._following.owner = "other"  # neither window in front: the window does not look ...
    follow.show((0.0, "2 soft", _page(2, soft=3)), (0.25, "2", _page(2)), run=1.0)  # ... while the page turns
    assert [j.name for j in worker.jobs] == ["1"]
    w._following.owner, w._following.look_at = "viewer", follow.clock.now  # the viewer in front again: one look
    follow.clock.run(2.0)
    assert worker.one("2").how == "done"


# ------------------------------------------------------------------ a change after the confirmation
def test_a_page_turned_while_its_confirmed_job_runs_cancels_it_once_the_new_frame_stayed_briefly(follow):
    w, worker = follow.make(ask_s=1.5)  # the model answers for 1.5 s: page 2's job runs past its confirmation
    three = _page(3)
    turned = follow.show((0.0, "2", _page(2)), (1.0, "3", three), run=0.3 + 1.02)
    two = worker.one("2")
    assert two.gate.confirmed_at is not None and two.asked is not None and two.shown is None  # confirmed, asking ...
    assert w._live is three and not two.cancel.is_set()  # ... page 3 on show at once, the job going on ...
    follow.clock.run(3)
    # ... until page 3 has stayed LEFT_PAGE_MS (`_look_over_job`'s rule), then cancelled
    lag = two.cancel_seen - (turned + 1.0)
    assert two.how == "cancelled" and LEFT_PAGE_MS / 1000 <= lag <= LEFT_PAGE_MS / 1000 + 3 * FRAME_STEP_MS / 1000, lag
    assert two.ended - two.cancel_seen <= CANCEL_S + 0.011
    three_job = worker.one("3")
    assert three_job.start - two.ended <= 0.016 and three_job.how == "done" and worker.kept == ["1", "3"]
    # page 3 started early - a gate of its own -, kept once its frame stayed twice settle_ms from the look that saw it
    assert three_job.gate is not None and _after(three_job.gate.confirmed_at - (turned + 1.0), KEEP_S)


def test_a_sharper_frame_after_the_confirmation_replaces_the_page_kept(follow):
    w, worker = follow.make(asks=False)
    soft, sharp = _page(4, soft=3), _page(4)
    turned = follow.show((0.0, "4 soft", soft), (0.95, "4", sharp))  # the soft frame confirmed before the sharp came
    first, second = worker.one("4 soft"), worker.one("4")
    assert _after(first.gate.confirmed_at - turned, KEEP_S)
    assert first.stored is not None and first.stored < turned + 0.95  # kept before the sharp frame came
    forgotten = w.pipeline.forgotten[-1]
    assert [(u.fingerprint, u.aspect) for u in forgotten.units] == [("4 soft", 1.0)]  # what it stored is dropped
    assert second.gate is None and second.start - (turned + 0.95) <= 0.016  # read again from the sharp frame
    assert worker.kept == ["1", "4 soft", "4"] and w.last_result is second.result


# ------------------------------------------------------------------ the profile
def test_an_old_profile_with_turn_times_loads_and_they_are_never_written(follow, tmp_path):
    """Older versions kept the viewer's page turns timed in its profile ("settle_seen"): such a profile loads - its
    area and keys as ever -, the times are ignored, and nothing writes them."""
    path = follow.path
    Profiles(path).set_key_way(VIEWER, "posted")
    data = json.loads(path.read_text(encoding="utf-8"))
    key = next(k for k, v in data.items() if isinstance(v, dict) and v.get("key_way") == "posted")
    data[key]["settle_seen"] = [120, 90, 100]
    data[key]["margins"] = [0, 85, 0, 0]
    path.write_text(json.dumps(data), encoding="utf-8")
    profiles = Profiles(path)
    assert profiles.key_way_for(VIEWER) == "posted"
    w, worker = follow.make(profiles=profiles)
    for k in range(3):
        turned = follow.show((0.0, f"p{k}", _page(2 + k)))
        assert _after(worker.one(f"p{k}").gate.confirmed_at - turned, KEEP_S)  # the fixed time, whatever it says
    profiles.set_covered(VIEWER, True)  # (a write of the profile's own: the old entry stays as it was found)
    after = json.loads(path.read_text(encoding="utf-8"))[key]
    assert after["settle_seen"] == [120, 90, 100] and after["margins"] == [0, 85, 0, 0]
    assert after["while_covered"] == "draws"


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
