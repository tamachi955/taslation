"""A page started early on a soft picture whose frame stayed long enough to be confirmed (twice settle_ms: the sharp
picture drawn late, or reaching the window late), then its sharp picture: the confirmation is taken back
(`PageGate.take_back`, the live view's `_retake`) and nothing of the job on the soft picture is in the book's cache
afterwards - neither its page nor the line it kept for reuse, in memory or on disk -, whatever the soft picture's time
and the lateness: put back while its job runs, and once it is done within TAKE_BACK_MS of the confirmation for a viewer
seen to draw a page soft first (`Provisional.keep`, `Pipeline.decide_kept`), before the job on the sharp picture
begins, which stores the page. A viewer never seen to draw soft first pays nothing: its page jobs are kept for good as
they end and saved at once, and a sharper picture after that drops the page as before. An ordinary turn to another
page after the confirmation keeps what was stored, its lines among it.

The window and its follow are the real ones on the test's clock (tests/test_early_start.py's); the worker is a stand-in
that runs each page job's stores through a real pipeline over a real book cache (`CacheWorker`). A sharp picture that
reaches the capture late is, for the window, one drawn that much later: the test shows it at the soft picture's time
plus the lateness."""
from __future__ import annotations

import hashlib
import time
from types import SimpleNamespace

import pytest
from test_early_start import ASK_S, CANCEL_S, KEEP_S, READ_S, STEP_MS, _environment
from test_follow import _page

from taslation import pipeline as pipeline_mod
from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.config import Settings
from taslation.fingerprint import FINGERPRINT_HEX_LEN
from taslation.messages import Cancelled
from taslation.pipeline import Pipeline
from taslation.regions import PageResult
from taslation.translate import DictTranslator
from taslation.ui.live import TAKE_BACK_MS

SCOPE = "test"  # the scope of the lines a job keeps for reuse (`linememo.LineMemo.put`)


def _fingerprint(name: str) -> str:
    return hashlib.sha512(name.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_LEN]  # (as long as a page unit's)


class CacheWorker:
    """The window's worker as it runs a page job (`JobsMixin._job_translate`), on the fake clock, through a real
    pipeline's stores (`Pipeline.page_on_show`, `PageWork`, `Provisional`) over a real book cache; before each job, and
    once its time is up while none comes, a page job kept for now is decided (`jobs.next_job`,
    `Pipeline.decide_kept`). A job reads its page for READ_S; with *asks*, asks the model once a look after it asked
    found its frame on show (`PageGate.seen_since`), for *ask_s*; then stores its page - a page of the cache and a line
    kept for reuse, both named by the frame -, reads on for *more_s* (the page's other half, say), shows the page and
    waits for its frame (`PageWork.settle`), and saves (`Pipeline.flush_saves`). A cancel, or its gate dropped, ends
    it CANCEL_S later (`PageWork.give_up`)."""

    def __init__(self, w, clock, name, pipeline, asks=True, ask_s=None, more_s=0.0):
        self.w, self.clock, self.name, self.p = w, clock, name, pipeline
        self.asks, self.ask_s, self.more_s = asks, ASK_S if ask_s is None else ask_s, more_s
        self.jobs: list[SimpleNamespace] = []
        self.stored: list[str] = []  # the names of the pages stored, in order

    @property
    def kept(self) -> list[str]:
        """The pages the cache holds, in the order they were stored."""
        held = {page.fingerprint for page in self.p.cache.pages}
        return [name for name in self.stored if _fingerprint(name) in held]

    def one(self, name):
        jobs = [j for j in self.jobs if j.name == name]
        assert len(jobs) == 1, (name, [(j.name, j.start) for j in self.jobs])
        return jobs[0]

    def put(self, _job):
        self.p.decide_kept()  # (the worker, before each job)
        w = self.w
        job = SimpleNamespace(frame=w._job_frame, name=self.name(w._job_frame), gate=w._page_gate,
                              cancel=w._page_cancel, start=self.clock.now, gate_at=None, asked=None, stored=None,
                              shown=None, cancel_seen=None, ended=None, how=None, result=None)
        job.ctx = self.p.page_on_show(job.gate)
        job.work = job.ctx.__enter__()
        self.jobs.append(job)
        self._again(job)

    def _again(self, job):
        self.clock.after(STEP_MS, lambda: self._tick(job))

    def _tick(self, job):
        now, gate, work = self.clock.now, job.gate, job.work
        if job.shown is not None:
            return self._settle(job)
        if job.cancel.is_set() or (gate is not None and gate.state == "dropped"):
            if job.cancel_seen is None:
                job.cancel_seen = now
            if now - job.cancel_seen + 1e-9 < CANCEL_S:
                return self._again(job)
            job.ctx.__exit__(Cancelled, Cancelled(), None)  # (`PageWork.give_up`, then the save `saves_held` makes)
            self.w._handle_event("page_cancelled", {"gate": gate, "discarded": work.kept is False,
                                                    "stored": list(work.stored)})
            return self._end(job, "cancelled")
        if now - job.start + 1e-9 < READ_S:
            return self._again(job)
        if self.asks and job.stored is None:
            if job.asked is None:
                if gate is not None and not gate.confirmed:
                    if job.gate_at is None:
                        job.gate_at = now
                    if not gate.seen_since(job.gate_at):
                        return self._again(job)
                job.asked = now
            if now - job.asked + 1e-9 < self.ask_s:
                return self._again(job)
        if job.stored is None:
            fingerprint = _fingerprint(job.name)
            cache = self.p.cache
            cache.add(CachedPage(fingerprint, 1.0, [CachedBubble((0.1, 0.1, 0.3, 0.3), job.name)]))
            cache.lines.put(SCOPE, job.name, job.name)
            work.stored.append((fingerprint, 1.0))
            self.p._save_store("cache", cache)  # (held back: `saves_held`)
            self.stored.append(job.name)
            job.stored = now
        if now - job.stored + 1e-9 < self.more_s:
            return self._again(job)
        job.ctx.__exit__(None, None, None)
        job.shown = now
        job.result = PageResult(image=job.frame.copy(), original=job.frame.copy(), regions=[], cache_misses=1)
        self.w._handle_event("result", {"result": job.result, "gate": gate, "stored": list(work.stored)})
        return self._settle(job)

    def _settle(self, job):
        gate, work = job.gate, job.work
        if work.waits and gate.state == "pending" and not job.cancel.is_set():
            return self._again(job)  # shown; it waits for its frame
        if work.waits and not work.settle(job.cancel):
            self.w._handle_event("page_cancelled", {"gate": gate, "discarded": True, "result": job.result,
                                                    "stored": []})
            return self._end(job, "cancelled")
        self.p.flush_saves()
        return self._end(job, "done")

    def _end(self, job, how):
        job.ended, job.how = self.clock.now, how
        self.w._handle_event("translate_done", {})
        held, left = self.p._kept_open, self.p.kept_open_left()
        if held is not None and left is not None:  # (the worker waits for its next job until then)
            self.clock.after(left * 1000, lambda: self._time_up(held))

    def _time_up(self, held):
        if self.p._kept_open is held:
            self.p.decide_kept()


@pytest.fixture
def cached(hidden_root, monkeypatch, tmp_path):
    """tests/test_early_start.py's window and viewer, the worker a `CacheWorker` over a real pipeline and book cache
    (the pipeline's clock the test's), and what the window forgets from that cache recorded."""
    env = _environment(hidden_root, monkeypatch, tmp_path / "profiles.json")
    monkeypatch.setattr(pipeline_mod, "time", SimpleNamespace(monotonic=env.clock.monotonic,
                                                              perf_counter=time.perf_counter))
    settings = Settings(state_dir=tmp_path / "state")
    settings.validate()
    store = CacheStore(settings.cache_dir)
    p = Pipeline(settings, ocr=None, translator=DictTranslator({}), cache=store.open("Book", "m", "English"))
    forgotten: list[list[tuple[str, float]]] = []
    real_forget = p.forget_page

    def forget(result, keep_edited=False):
        forgotten.append([(u.fingerprint, u.aspect) for u in result.units])
        return real_forget(result, keep_edited)

    p.forget_page = forget

    def make(asks=True, ask_s=None, more_s=0.0, soft_first=True):
        """The window, its worker, page 1 done; *soft_first*: the viewer has drawn a page soft first already."""
        def worker(w, clock, name, asks_, ask_s_):
            w.pipeline = p
            return CacheWorker(w, clock, name, p, asks_, ask_s_, more_s)

        w, work = env.make(asks=asks, ask_s=ask_s, worker=worker)
        if soft_first:
            w._drew_soft(_page(90, soft=3), _page(90))  # (as `_retake` and the settle learn it)
        assert w._draws_soft_first() is soft_first
        return w, work

    def on_disk():
        cache = CacheStore(settings.cache_dir).open("Book", "m", "English")
        return {page.fingerprint for page in cache.pages}, cache.lines

    return SimpleNamespace(env=env, p=p, make=make, forgotten=forgotten, on_disk=on_disk)


def _holds(pages, lines, name) -> tuple[bool, bool]:
    """Whether the cache's *pages* (fingerprints) hold the page *name*, and its *lines* the line it kept."""
    return _fingerprint(name) in pages, lines.find(SCOPE, name) is not None


JOBS = {"done before": dict(asks=False),  # every line reused: done before its frame is confirmed
        "about the confirmation": dict(ask_s=ASK_S),  # answered about when its frame is confirmed
        "running": dict(ask_s=ASK_S, more_s=1.5)}  # stored then, and read on for 1.5 s: running when the sharp comes


@pytest.mark.parametrize("job_kind", list(JOBS))
@pytest.mark.parametrize("late", [0.05, 0.15, 0.3])
@pytest.mark.parametrize("soft_s", [0.5, 0.7, 0.9, 1.5])
def test_nothing_of_a_soft_pictures_job_is_kept_once_its_sharp_picture_comes(cached, soft_s, late, job_kind):
    w, worker = cached.make(**JOBS[job_kind])
    p = cached.p
    soft, sharp = _page(4, soft=3), _page(4)
    turned = cached.env.show((0.0, "4 soft", soft), (soft_s + late, "4", sharp), run=8.0)
    first, second = worker.one("4 soft"), worker.one("4")
    if first.gate.confirmed_at is not None:  # the soft picture stayed long enough: confirmed, then taken back
        assert first.gate.confirmed_at < turned + soft_s + late and first.gate.state == "dropped"
    if soft_s + late > KEEP_S + 0.035:
        assert first.gate.confirmed_at is not None
    assert first.ended <= second.start  # (put back before the job on the sharp picture began)
    pages, lines = {page.fingerprint for page in p.cache.pages}, p.cache.lines
    assert _holds(pages, lines, "4 soft") == (False, False)  # nothing of the soft picture's job ...
    assert _holds(pages, lines, "4") == (True, True) and _holds(pages, lines, "1") == (True, True)
    assert cached.forgotten == []  # (nothing to drop: put back whole)
    assert p._kept_open is None and p._held_for is None  # (decided, once its time was up)
    pages, lines = cached.on_disk()
    assert _holds(pages, lines, "4 soft") == (False, False)  # ... in memory or on disk
    assert _holds(pages, lines, "4") == (True, True)
    assert w.last_result is second.result and w.last_result.original.tobytes() == sharp.tobytes()


@pytest.mark.parametrize("job_kind", list(JOBS))
def test_a_viewer_never_seen_to_draw_soft_first_pays_nothing(cached, job_kind):
    """Its page jobs are kept for good as they end - the gate sealed, the page saved at once, no snapshot held -; a
    sharper picture after that drops the page as before (the line it kept stays). One that comes while the job runs
    still takes its confirmation back: nothing of it is kept."""
    w, worker = cached.make(soft_first=False, **JOBS[job_kind])
    p = cached.p
    clock = cached.env.clock
    soft, sharp = _page(4, soft=3), _page(4)
    turned = cached.env.show((0.0, "4 soft", soft), run=0.0)
    while worker.jobs[-1].name != "4 soft" or worker.jobs[-1].ended is None:
        clock.run(0.01)
        if clock.now - turned > 2.0:
            break
    first = worker.one("4 soft")
    if first.ended is not None:  # done: kept for good at once
        assert first.how == "done" and first.gate.confirmed_at is not None
        assert p._kept_open is None and p._held_for is None and first.gate.state == "confirmed"
        assert _holds(*cached.on_disk(), "4 soft") == (True, True)  # saved as it ended
    cached.env.viewer.frames.append((max(clock.now, turned + 1.0) + 0.05, sharp))
    cached.env.names[id(sharp)] = "4"
    clock.run(8.0)
    second = worker.one("4")
    pages, lines = {page.fingerprint for page in p.cache.pages}, p.cache.lines
    if first.ended is not None and first.ended < turned + 1.0:  # done before the sharp picture came
        assert first.gate.state == "confirmed" and cached.forgotten == [[(_fingerprint("4 soft"), 1.0)]]
        assert _holds(pages, lines, "4 soft") == (False, True)  # its page dropped (`_stored_by`), its line kept
    else:  # running when it came
        assert first.gate.state == "dropped" and cached.forgotten == []
        assert _holds(pages, lines, "4 soft") == (False, False)
    assert _holds(pages, lines, "4") == (True, True) and second.how == "done"


@pytest.mark.parametrize("soft_first", [True, False])
@pytest.mark.parametrize("job_kind", list(JOBS))
def test_a_turn_to_another_page_after_the_confirmation_keeps_what_was_stored(cached, job_kind, soft_first):
    """The turn comes at 1.3 s: after the confirmation, the job done (or, "running", cancelled by the turn after it
    stored its page: what it stored lasts)."""
    w, worker = cached.make(soft_first=soft_first, **JOBS[job_kind])
    p = cached.p
    turned = cached.env.show((0.0, "2", _page(2)), (1.3, "3", _page(3)), run=8.0)
    two, three = worker.one("2"), worker.one("3")
    assert two.gate.confirmed_at is not None and two.gate.confirmed_at < turned + 1.3
    assert two.gate.state == "confirmed" and three.how == "done"
    assert two.how == ("cancelled" if job_kind == "running" else "done")
    pages, lines = {page.fingerprint for page in p.cache.pages}, p.cache.lines
    assert _holds(pages, lines, "2") == (True, True) and _holds(pages, lines, "3") == (True, True)
    pages, lines = cached.on_disk()
    assert _holds(pages, lines, "2") == (True, True) and _holds(pages, lines, "3") == (True, True)
    assert cached.forgotten == [] and p._kept_open is None


def test_a_page_kept_for_now_is_kept_for_good_and_saved_once_its_time_is_up(cached):
    w, worker = cached.make(asks=False)
    p, clock = cached.p, cached.env.clock
    cached.env.show((0.0, "2", _page(2)), run=0.0)
    while not worker.jobs or worker.jobs[-1].name != "2" or worker.jobs[-1].ended is None:
        clock.run(0.01)
    two = worker.one("2")
    confirmed = two.gate.confirmed_at
    assert two.how == "done" and p._kept_open is not None  # kept for now: held, ...
    assert _holds(*cached.on_disk(), "2") == (False, False) and not p.flush_saves()  # ... its save waiting
    clock.run(confirmed + TAKE_BACK_MS / 1000 - clock.now - 0.05)
    assert p._kept_open is not None
    clock.run(0.1)
    assert p._kept_open is None and p._held_for is None and two.gate.state == "confirmed"
    assert not two.gate.take_back()  # (sealed: kept for good)
    assert _holds(*cached.on_disk(), "2") == (True, True)
