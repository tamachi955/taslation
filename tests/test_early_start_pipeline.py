"""A page job on a frame the window has not confirmed yet (`pipeline.PageGate`, `Pipeline.page_on_show`: the live
view's early start, tests/test_early_start.py): it reads the page, and asks the model - and loads its model - as soon
as the window has found the frame on show after the job asked (`PageGate.on_show`, `seen`), with no wait for the
confirmation; what it changes that lasts - the cache and its file, the lines kept for reuse, the book's sizes, where
the book was read last, the pairs held for the translator, the lines the translator counts as asked for, the line
tally, the stage times, the pages kept lettered - is held, kept once the frame is confirmed and put back whole when it
is dropped or the job is cancelled first, a request in flight among it. The memos keyed by the very pixels (the OCR's
readings) stay. The window's page job (`_job_translate`) shows the page first, then waits for the frame; what it stored
anew goes to the window with the page."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr

from taslation.cache import CacheStore
from taslation.config import Settings
from taslation import pipeline as pipeline_mod
from taslation.messages import Cancelled
from taslation.pipeline import LoadAhead, PageGate, Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import jobs


SHORT = {"えっ！": "Huh?!", "待って！": "Wait!", "ありがとう。": "Thanks.", "行くぞ！": "Let's go!", "そうだね。": "Yeah.",
         "知らない。": "No idea."}  # short whole lines: kept for reuse (`linememo`), the next reading asks for none


def _pipeline(settings, book, ocr=None):
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return Pipeline(settings, ocr=ocr or FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)


def _reused_page(settings, book, page) -> Pipeline:
    """A pipeline whose book's lines hold every line of *page* (read once with line reuse on) and whose cache does
    not hold the page: read again, the page asks the model nothing."""
    settings.reuse_lines = True
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    p = Pipeline(settings, ocr=FakeOcr(list(SHORT)), translator=DictTranslator(dict(SHORT)), cache=cache)
    first = p.process(page)
    assert sorted(t for call in p.translator.calls for t in call) == sorted(SHORT)
    for unit in first.units:
        p.cache.remove(unit.fingerprint)
    p.cache.save()
    return p


def _on_disk(settings, book) -> list[tuple]:
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return [(p.fingerprint, p.seq, [b.text for b in p.bubbles]) for p in cache.pages]


def _state(p: Pipeline) -> dict:
    """Everything of the pipeline a page job may change that lasts, as values."""
    cache = p.cache
    return {
        "pages": [(pg.fingerprint, pg.seq, pg.incomplete, [(b.text, tuple(b.box)) for b in pg.bubbles])
                  for pg in cache.pages],
        "touched": sorted(cache.touched), "removed": list(cache.removed), "dirty": cache.dirty, "stamp": cache.stamp,
        "lines": cache.lines.state(), "lines_touched": sorted(map(repr, cache.lines.touched)),
        "last_seq": p.last_seq, "sizes": list(p._book_sizes), "context": [list(page) for page in p._context],
        "names": p.book_names.held, "tally": (p.line_tally.reused, p.line_tally.asked),
        "shown": len(p.shown_pages), "stage_times": len(p.stage_times), "save_due": p._save_due is not None,
    }


class Job:
    """A page job on its own thread, as the window's worker runs it: `process` within `page_on_show(gate)`, then the
    frame waited for (`PageWork.settle`)."""

    def __init__(self, p: Pipeline, image, gate: PageGate | None, cancel: threading.Event | None = None, **kwargs):
        self.p, self.image, self.gate = p, image, gate
        self.cancel = cancel or threading.Event()
        self.result = self.error = self.kept = self.work = None
        self.processed = threading.Event()
        self.thread = threading.Thread(target=self._run, kwargs=kwargs, daemon=True)
        self.thread.start()

    def _run(self, **kwargs):
        try:
            with self.p.page_on_show(self.gate) as work:
                self.work = work
                self.result = self.p.process(self.image, cancel=self.cancel, **kwargs)
            self.processed.set()
            self.kept = work.settle(self.cancel)
        except BaseException as e:  # noqa: BLE001 - looked at by the test
            self.error = e
            self.processed.set()

    def join(self, seconds=20.0):
        self.thread.join(seconds)
        assert not self.thread.is_alive()


def _read_and_waiting(p: Pipeline, job: Job, seconds=20.0) -> None:
    """Until *job* has read its page and waits at the gate (the OCR read every line, nothing more comes)."""
    end = time.monotonic() + seconds
    calls = -1
    while time.monotonic() < end:
        if job.processed.is_set():
            return
        if p.ocr.calls and p.ocr.calls == calls:
            return
        calls = p.ocr.calls
        time.sleep(0.25)
    raise AssertionError("the job never came to the gate")


def _asked(p: Pipeline, seconds=20.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end and not p.translator.calls:
        time.sleep(0.01)
    return bool(p.translator.calls)


def test_the_model_is_asked_once_the_window_sees_the_frame_and_the_page_is_kept_once_it_is_confirmed(sample_page,
                                                                                                     settings):
    p = _pipeline(settings, "Confirmed")
    gate = PageGate()
    gate.seen(time.monotonic())  # (a look before the job asked says nothing of the frame now)
    job = Job(p, sample_page, gate)
    _read_and_waiting(p, job)
    assert p.ocr.calls and p.translator.calls == [] and job.thread.is_alive()  # read, and waiting at the gate
    gate.seen(time.monotonic())  # the window's next look: the frame is on show still
    assert _asked(p) and job.thread.is_alive()  # asked at once, not confirmed: the page waits for its frame ...
    time.sleep(0.2)
    assert len(p.cache) == 1 and not p.cache.dirty and not p.cache.path.exists()  # ... stored, and held
    assert gate.confirm()  # the window: the frame stayed
    job.join()
    assert job.error is None and job.kept is True and len(p.translator.calls) == 1
    assert len(p.cache) == 1 and p.cache.dirty and job.work.stored == [(u.fingerprint, u.aspect) for u in job.result.units]
    assert p.flush_saves() and len(_on_disk(settings, "Confirmed")) == 1

    # the same page with no gate (a frame that settled first, as ever): the very page
    q = _pipeline(settings, "As ever")
    with q.page_on_show():
        as_ever = q.process(sample_page, cancel=threading.Event())
    assert [(r.bbox, r.translated_text) for r in as_ever.regions] == [(r.bbox, r.translated_text)
                                                                      for r in job.result.regions]


def test_a_frame_dropped_while_its_page_waits_puts_back_everything_the_job_did(sample_page, sample_page2, settings,
                                                                               monkeypatch):
    monkeypatch.setattr(pipeline_mod, "size_sample", lambda reading: 21.0)  # (the fake reader's lines give a size)
    p = _pipeline(settings, "Dropped")
    p.process(sample_page2)  # a page before: the cache, the sizes, the pairs, the pages kept lettered
    assert len(p.cache) == 1 and p._context and len(p._book_sizes)
    stamp = p.cache.path.stat().st_mtime_ns
    before = _state(p)
    memo = len(p._ocr_memo)
    gate, cancel = PageGate(), threading.Event()
    job = Job(p, sample_page, gate, cancel)
    _read_and_waiting(p, job)
    assert list(p._book_sizes) != before["sizes"]  # (its reading added the page's sizes meanwhile)
    gate.drop()  # the frame changed: the window drops it and cancels the job
    cancel.set()
    job.join()
    assert isinstance(job.error, Cancelled) and job.work.kept is False and job.work.stored == []
    assert _state(p) == before  # all of it as it was
    assert p.cache.path.stat().st_mtime_ns == stamp and len(_on_disk(settings, "Dropped")) == 1  # nothing written
    assert len(p._ocr_memo) > memo  # the readings of these very pixels stay
    assert len(p.translator.calls) == 1  # the page before's request alone
    assert not gate.confirm()  # a confirmation that comes too late keeps nothing

    # the page read again (the frame came back): as a session that never saw the dropped one reads it
    again = p.process(sample_page)
    fresh = _pipeline(settings, "Never dropped")
    fresh.process(sample_page2)
    expected = fresh.process(sample_page)
    assert [(r.bbox, r.translated_text) for r in again.regions] == [(r.bbox, r.translated_text)
                                                                    for r in expected.regions]


class Slow(DictTranslator):
    """A translator whose request runs until it is cancelled (`translate_page`'s *cancel*), counting each line it was
    asked for as `PlamoTranslator` does (`draws`)."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.asked: dict[str, int] = {}
        self.running = threading.Event()

    def translate_page(self, texts, *args, cancel=None, **kwargs):
        for text in texts:
            self.asked[text] = self.asked.get(text, 0) + 1
        self.running.set()
        while cancel is not None and not cancel.wait(0.01):
            pass
        return super().translate_page(texts, *args, cancel=cancel, **kwargs)

    def draws(self):
        return dict(self.asked)

    def set_draws(self, draws):
        self.asked = dict(draws)


def test_a_frame_that_changes_while_its_request_runs_cancels_it_and_puts_back_everything(sample_page, sample_page2,
                                                                                         settings, monkeypatch):
    monkeypatch.setattr(pipeline_mod, "size_sample", lambda reading: 21.0)
    p = _pipeline(settings, "Changed in flight")
    p.process(sample_page2)  # a page before
    p.translator = translator = Slow(EN_TEXTS)
    translator.asked = {"before": 1}
    before, stamp = _state(p), p.cache.path.stat().st_mtime_ns
    gate, cancel = PageGate(), threading.Event()
    job = Job(p, sample_page, gate, cancel)
    _read_and_waiting(p, job)
    gate.seen(time.monotonic())
    assert translator.running.wait(20.0)  # the request on its way
    assert len(translator.asked) > 1
    gate.drop()  # the frame changed: the window drops it and cancels the job, its request with it
    cancel.set()
    job.join()
    assert isinstance(job.error, Cancelled) and job.work.kept is False and job.work.stored == []
    assert _state(p) == before and p.cache.path.stat().st_mtime_ns == stamp
    assert translator.asked == {"before": 1}  # (a line asked for on the frame that changed is drawn anew later)


def test_a_cancel_while_the_page_waits_for_its_frame_keeps_nothing(sample_page, settings):
    p = _pipeline(settings, "Stopped early")
    before = _state(p)
    gate, cancel = PageGate(), threading.Event()
    job = Job(p, sample_page, gate, cancel)
    _read_and_waiting(p, job)
    cancel.set()  # Stop, or a new page another look saw: the job gives the gate up itself
    job.join()
    assert isinstance(job.error, Cancelled) and gate.state == "dropped" and not gate.confirm()
    assert _state(p) == before and not p.cache.path.exists() and p.translator.calls == []


def test_a_page_done_before_its_frame_is_confirmed_is_held_then_kept_or_put_back(sample_page, settings):
    """Every line reused from the book's lines (no request, so no wait at the gate): the page is done, stored and
    shown before the frame is confirmed - held: not saved, not marked for the window's close to save, until then."""
    for keep in (False, True):
        book = f"Held {keep}"
        p = _reused_page(settings, book, sample_page)
        before, stamp = _state(p), p.cache.path.stat().st_mtime_ns
        asked = len(p.translator.calls)
        gate = PageGate()
        job = Job(p, sample_page, gate)
        assert job.processed.wait(20.0) and job.error is None, job.error
        assert len(p.translator.calls) == asked  # every line reused: the model was asked nothing
        assert len(p.cache) == 1 and job.result.translated  # stored and shown ...
        assert not p.cache.dirty and not p.flush_saves()  # ... and held: nothing saved, ...
        app_mod.last_save(p)  # ... not even by the window's close
        assert p.cache.path.stat().st_mtime_ns == stamp and _on_disk(settings, book) == []
        if keep:
            assert gate.confirm()
            job.join()
            assert job.kept is True and p.cache.dirty and p.flush_saves() and len(_on_disk(settings, book)) == 1
        else:
            gate.drop()
            job.join()
            assert job.kept is False and _state(p) == before and _on_disk(settings, book) == []


def test_a_cancel_after_the_confirmation_keeps_the_page_stored_as_ever(sample_page, settings):
    p = _pipeline(settings, "Confirmed then stopped")
    gate, cancel = PageGate(), threading.Event()
    assert gate.confirm()  # (confirmed before the job came to the gate)
    real = p._erase_kept
    p._erase_kept = lambda out, region, key: (real(out, region, key), cancel.set())[0]  # stopped in the render
    job = Job(p, sample_page, gate, cancel)
    job.join()
    assert isinstance(job.error, Cancelled) and job.work.kept is True
    assert len(_on_disk(settings, "Confirmed then stopped")) == 1  # stored whole, and saved, as ever


def test_the_model_loads_ahead_once_the_window_sees_the_frame(settings):
    loads: list[float] = []
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
    p.translator.ensure_loaded = lambda cancel=None: loads.append(time.monotonic())
    gate, cancel = PageGate(), threading.Event()
    ahead = LoadAhead(p, cancel, gate)
    ahead.start()
    time.sleep(0.3)
    assert loads == []  # waits for a look at the frame
    seen = time.monotonic()
    gate.seen(seen)
    ahead.thread.join(5.0)
    assert len(loads) == 1 and loads[0] >= seen and gate.state == "pending"  # loaded, nothing confirmed
    ahead.join()

    loads.clear()
    dropped = PageGate()
    ahead = LoadAhead(p, cancel, dropped)
    ahead.start()
    dropped.drop()  # the frame changed before a look found it
    ahead.thread.join(5.0)
    assert loads == [] and not ahead.thread.is_alive()
    ahead.join()

    loads.clear()
    pending = PageGate()
    ahead = LoadAhead(p, cancel, pending)
    ahead.start()
    started = time.monotonic()
    ahead.join()  # the page is done before its frame was confirmed: no load, no wait
    assert loads == [] and time.monotonic() - started < 1.0 and pending.state == "pending"


class Window:
    """What `_job_translate` needs of the window (as tests/test_save_after_showing.py's): what it posts is kept."""

    _job_translate = jobs.JobsMixin._job_translate
    _say_failed_save = jobs.JobsMixin._say_failed_save
    _use_model = jobs.JobsMixin._use_model

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.posted: list[tuple[str, dict]] = []
        self.colophons: list = []
        self.translator = SimpleNamespace(model="m")
        self.settings = Settings()
        self._jobs = SimpleNamespace(put=lambda job: None)

    def _post(self, kind, **data):
        self.posted.append((kind, data))

    def kinds(self):
        return [k for k, _d in self.posted if k in ("result", "page_cancelled", "translate_done")]

    def _ensure_cache(self, *_a):
        return True

    def _look_for_colophon(self, *args):
        self.colophons.append(args)


@pytest.mark.parametrize("confirmed", [True, False])
def test_the_page_job_shows_its_page_then_waits_for_the_frame(sample_page, settings, confirmed):
    p = _pipeline(settings, f"Job {confirmed}")
    w = Window(p)
    gate, cancel = PageGate(), threading.Event()
    thread = threading.Thread(target=w._job_translate, args=(sample_page, p.cache.book, "m", "English", False,
                                                             cancel), kwargs={"gate": gate}, daemon=True)
    thread.start()
    end = time.monotonic() + 20
    while time.monotonic() < end and "result" not in w.kinds():
        time.sleep(0.02)
        if p.ocr.calls and not p.translator.calls and not w.kinds():
            if not confirmed:
                break
            gate.seen(time.monotonic())  # (the frame on show: the model is asked; else it never is)
            gate.confirm()
    if confirmed:
        thread.join(20)
        assert w.kinds() == ["result", "translate_done"]
        result = dict(w.posted)["result"]
        assert result["gate"] is gate and result["stored"] == [(u.fingerprint, u.aspect) for u in result["result"].units]
        assert len(_on_disk(settings, p.cache.book)) == 1 and len(w.colophons) == 1  # saved, the colophon looked for
    else:
        time.sleep(0.5)
        assert p.translator.calls == [] and thread.is_alive()  # waits at the gate
        gate.drop()
        cancel.set()
        thread.join(20)
        assert w.kinds() == ["page_cancelled", "translate_done"]
        news = dict(w.posted)["page_cancelled"]
        assert news["discarded"] and news["gate"] is gate and news["stored"] == []
        assert not p.cache.path.exists() and len(p.cache) == 0 and w.colophons == []


def test_a_page_job_shown_before_its_frame_was_confirmed_and_then_dropped_says_so(sample_page, settings):
    p = _reused_page(settings, "Shown, dropped", sample_page)
    w = Window(p)
    gate, cancel = PageGate(), threading.Event()
    thread = threading.Thread(target=w._job_translate, args=(sample_page, p.cache.book, "m", "English", False,
                                                             cancel), kwargs={"gate": gate}, daemon=True)
    thread.start()
    end = time.monotonic() + 20
    while time.monotonic() < end and "result" not in w.kinds():
        time.sleep(0.02)
    assert w.kinds() == ["result"] and thread.is_alive()  # shown, waiting for the frame
    gate.drop()
    thread.join(20)
    assert w.kinds() == ["result", "page_cancelled", "translate_done"]
    news = dict(w.posted)["page_cancelled"]
    assert news["discarded"] and news["result"] is dict(w.posted)["result"]["result"]
    assert len(p.cache) == 0 and _on_disk(settings, "Shown, dropped") == [] and w.colophons == []
