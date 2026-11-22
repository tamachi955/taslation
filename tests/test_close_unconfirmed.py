"""The window's close while a page job's frame is not confirmed yet (`pipeline.PageGate`, the live view's early start:
tests/test_early_start_pipeline.py) - the job waiting for a look at its frame, its request running, or its page done
and waiting for the confirmation. Nothing of that job reaches the disk - neither the cache file nor the stage times
kept at the close - and what it changed in memory goes back: every gate is dropped and the job's cancel set before
anything is saved (`ui.app.end_page_job`; a request in flight is cancelled), what the job changed is put back
(`Pipeline.drop_unconfirmed`), and the close writes the stores as they were before the job while its worker may still
change them (`Pipeline.to_save`). The pages an earlier save left unsaved are still written; a page whose frame was
confirmed before the close is kept and saved as ever; a worker held on the job past the close's wait changes nothing
that lasts."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr
from test_early_start_pipeline import Slow

from taslation import cache as cachemod
from taslation import devices
from taslation import pipeline as pipeline_mod
from taslation.cache import CacheStore
from taslation.pipeline import PageGate, Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import jobs

A = app_mod.App
SHORT = {"えっ！": "Huh?!", "待って！": "Wait!", "ありがとう。": "Thanks.", "行くぞ！": "Let's go!", "そうだね。": "Yeah.",
         "知らない。": "No idea."}  # short whole lines: kept for reuse (`linememo`), the next reading asks for none


@pytest.fixture(autouse=True)
def scratch_state(settings, monkeypatch):
    """Every store of these tests in the test's own folder (the settings' state folder is the test's already)."""
    monkeypatch.setenv("TASLATION_STATE_DIR", str(settings.state_dir))


@pytest.fixture
def gate_waits(monkeypatch) -> threading.Event:
    """Set once the page job waits at its gate with *close* - the job's own waits, not the model's load ahead: before
    the model is asked, for a look at its frame (`PageGate.on_show`), or after the page was shown (`PageGate.wait`)."""
    waiting = threading.Event()
    real_wait, real_on_show = PageGate.wait, PageGate.on_show

    def wait(self, cancel=None, limit=pipeline_mod.GATE_LIMIT_S, close=True):
        if close:
            waiting.set()
        return real_wait(self, cancel, limit, close)

    def on_show(self, cancel=None, limit=pipeline_mod.GATE_LIMIT_S, close=True):
        if close:
            waiting.set()
        return real_on_show(self, cancel, limit, close)

    monkeypatch.setattr(PageGate, "wait", wait)
    monkeypatch.setattr(PageGate, "on_show", on_show)
    return waiting


@pytest.fixture
def held_settle(monkeypatch) -> threading.Event:
    """The page job, its page shown, waits for this before it waits for its frame (`PageWork.settle`): what the close
    finds while the job is shown and not decided."""
    go = threading.Event()
    real = pipeline_mod.PageWork.settle

    def settle(self, cancel=None):
        assert go.wait(20.0)
        return real(self, cancel)

    monkeypatch.setattr(pipeline_mod.PageWork, "settle", settle)
    return go


def _pipeline(settings, book) -> Pipeline:
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)


def _reused_page(settings, book, page) -> Pipeline:
    """A pipeline whose book's lines hold every line of *page* (read once with line reuse on) and whose cache does
    not hold the page: read again, the page asks the model nothing, and is stored before its frame is confirmed."""
    settings.reuse_lines = True
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    p = Pipeline(settings, ocr=FakeOcr(list(SHORT)), translator=DictTranslator(dict(SHORT)), cache=cache)
    first = p.process(page)
    for unit in first.units:
        p.cache.remove(unit.fingerprint)
    p.cache.save()
    return p


def _unsaved_page(p: Pipeline, page, monkeypatch) -> None:
    """*page* read and stored, its save failed (a full disk): it waits in memory for the next save that works."""
    real = cachemod.write_atomic
    monkeypatch.setattr(cachemod, "write_atomic", lambda *_a, **_k: (_ for _ in ()).throw(OSError(28, "No space")))
    p.process(page)
    monkeypatch.setattr(cachemod, "write_atomic", real)
    assert p.cache.dirty and p.save_error


def _on_disk(settings, book) -> list[tuple]:
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return [(pg.fingerprint, pg.seq, [b.text for b in pg.bubbles]) for pg in cache.pages]


def _file(p: Pipeline) -> bytes | None:
    return p.cache.path.read_bytes() if p.cache.path.exists() else None


def _times_kept(settings) -> int | None:
    """How many pages' seconds the close kept (`devices.save_times`), None when it kept none."""
    path = settings.state_dir / devices.TIMINGS_FILE
    return len(json.loads(path.read_text(encoding="utf-8"))["pages"]) if path.exists() else None


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


class Window:
    """The window's page job (`_job_translate`, on a thread of its own as on the worker) and its close (`_on_close`,
    on the test's thread as on Tk's), with what they need; what the job posts is kept."""

    _job_translate = jobs.JobsMixin._job_translate
    _say_failed_save = jobs.JobsMixin._say_failed_save
    _use_model = jobs.JobsMixin._use_model
    _on_close = A._on_close
    _release_model = lambda self: None  # noqa: E731 - Ollama's model is not this test's (`end_page_job` cancels)
    _target_chosen = _restore_enlarged = _lower_viewer = _over_close = lambda self: None  # noqa: E731

    def __init__(self, pipeline, settings):
        self.pipeline, self.settings = pipeline, settings
        self.translator = SimpleNamespace(model="m")
        self._jobs = SimpleNamespace(put=lambda job: None)
        self.posted: list[tuple[str, dict]] = []
        self.closed = False
        self._early = self._early_gate = self._page_gate = self._page_cancel = None
        self.thread: threading.Thread | None = None

    def start(self, image, gate: PageGate) -> threading.Event:
        """A page started early on its frame (`ui.live._early_start`): the window holds its gate and its cancel."""
        cancel = threading.Event()
        self._early, self._page_gate, self._page_cancel = SimpleNamespace(gate=gate), gate, cancel
        self.thread = threading.Thread(target=self._job_translate, args=(image, self.pipeline.cache.book, "m",
                                                                         "English", False, cancel),
                                       kwargs={"gate": gate}, daemon=True)
        self.thread.start()
        return cancel

    def join(self) -> None:
        assert self.thread is not None
        self.thread.join(20.0)
        assert not self.thread.is_alive()

    def _post(self, kind, **data):
        self.posted.append((kind, data))

    def kinds(self) -> list[str]:
        return [k for k, _d in self.posted if k in ("result", "page_cancelled", "translate_done")]

    def shown(self, seconds=20.0) -> None:
        """Until the job has shown its page ("result")."""
        end = time.monotonic() + seconds
        while "result" not in self.kinds():
            assert time.monotonic() < end, "the page was never shown"
            time.sleep(0.01)

    def _ensure_cache(self, *_a):
        return True

    def _look_for_colophon(self, *_a):
        pass

    def destroy(self):
        self.closed = True


def test_closing_while_the_job_waits_for_a_look_at_its_frame_writes_nothing_of_the_page(sample_page, sample_page2,
                                                                                       settings, gate_waits):
    p = _pipeline(settings, "Closed waiting")
    p.process(sample_page2)  # a page before: saved, its seconds counted
    before, stamp, file = _state(p), p.cache.path.stat().st_mtime_ns, _file(p)
    w = Window(p, settings)
    gate = PageGate()
    cancel = w.start(sample_page, gate)
    assert gate_waits.wait(20.0)  # read, and waiting for a look at its frame before the model is asked
    w._on_close()
    assert w.closed and gate.state == "dropped" and cancel.is_set() and w._early is None
    assert _file(p) == file and p.cache.path.stat().st_mtime_ns == stamp  # the file as it was
    assert _times_kept(settings) == 1  # the page before's seconds alone
    w.join()
    assert w.kinds() == ["page_cancelled", "translate_done"] and dict(w.posted)["page_cancelled"]["discarded"]
    assert _state(p) == before and len(p.translator.calls) == 1  # the page before's request alone
    assert _file(p) == file and len(_on_disk(settings, "Closed waiting")) == 1
    assert not gate.confirm()  # a confirmation that comes after the close keeps nothing


def test_closing_while_the_request_runs_cancels_it_and_writes_nothing_of_the_page(sample_page, sample_page2, settings):
    p = _pipeline(settings, "Closed asking")
    p.process(sample_page2)  # a page before: saved, its seconds counted
    p.translator = translator = Slow(EN_TEXTS)  # (its request runs until it is cancelled)
    before, stamp, file = _state(p), p.cache.path.stat().st_mtime_ns, _file(p)
    w = Window(p, settings)
    gate = PageGate()
    cancel = w.start(sample_page, gate)
    end = time.monotonic() + 20
    while not translator.running.is_set():  # the window's looks: the frame is on show still
        assert time.monotonic() < end, "the model was never asked"
        gate.seen(time.monotonic())
        time.sleep(0.01)
    w._on_close()  # while the request runs
    assert w.closed and gate.state == "dropped" and cancel.is_set() and w._early is None
    assert _file(p) == file and p.cache.path.stat().st_mtime_ns == stamp  # the file as it was
    assert _times_kept(settings) == 1  # the page before's seconds alone
    w.join()  # (the request ended with the cancel)
    assert w.kinds() == ["page_cancelled", "translate_done"] and dict(w.posted)["page_cancelled"]["discarded"]
    assert _state(p) == before and _file(p) == file and len(_on_disk(settings, "Closed asking")) == 1


def test_closing_while_a_page_done_waits_for_its_frame_writes_nothing_of_it(sample_page, settings, held_settle):
    """Every line reused (no request, no wait before the model): the page is stored, and shown, before its frame is
    confirmed - and the close comes then."""
    p = _reused_page(settings, "Closed shown", sample_page)
    before, file = _state(p), _file(p)
    w = Window(p, settings)
    gate = PageGate()
    w.start(sample_page, gate)
    w.shown()
    assert len(p.cache) == 1 and len(p.stage_times) == before["stage_times"] + 1  # stored and timed, held
    held_settle.set()  # (the job goes on to wait for its frame: the close's drop reaches it there)
    w._on_close()
    assert w.closed and gate.state == "dropped"
    assert _file(p) == file and _on_disk(settings, "Closed shown") == []  # nothing of the page written
    assert _times_kept(settings) == before["stage_times"]  # nor its seconds
    w.join()
    assert w.kinds() == ["result", "page_cancelled", "translate_done"]
    assert _state(p) == before and _file(p) == file


@pytest.mark.parametrize("worker_first", [True, False])
def test_pages_an_earlier_save_left_are_saved_at_the_close_the_page_not_confirmed_is_not(sample_page, sample_page2,
                                                                                         settings, held_settle,
                                                                                         monkeypatch, worker_first):
    """*worker_first*: the job waits for its frame as the close comes, and puts itself back within the close's wait;
    else it is held before that wait past the close's (`CLOSE_WAIT_S`), and the close puts it back itself."""
    book = f"Earlier unsaved {worker_first}"
    p = _reused_page(settings, book, sample_page)
    _unsaved_page(p, sample_page2, monkeypatch)  # stored, its save failed: dirty before the job
    earlier = [(pg.fingerprint, pg.seq, [b.text for b in pg.bubbles]) for pg in p.cache.pages]
    assert len(earlier) == 1 and _on_disk(settings, book) == []
    before = _state(p)
    w = Window(p, settings)
    gate = PageGate()
    w.start(sample_page, gate)
    w.shown()
    assert len(p.cache) == 2 and p.cache.dirty  # the unconfirmed page in the cache, which was dirty before it
    if worker_first:
        held_settle.set()
    else:
        monkeypatch.setattr(pipeline_mod, "CLOSE_WAIT_S", 0.05)
    w._on_close()
    assert _on_disk(settings, book) == earlier  # the earlier page saved, the unconfirmed one not
    assert _times_kept(settings) == before["stage_times"]  # nor its seconds
    held_settle.set()
    w.join()
    assert w.kinds() == ["result", "page_cancelled", "translate_done"]
    assert _on_disk(settings, book) == earlier
    after = _state(p)
    if worker_first:  # (the close saved the cache the job had put back: nothing of it waits any more)
        after = {**after, "dirty": True, "stamp": before["stamp"], "touched": before["touched"],
                 "lines_touched": before["lines_touched"]}
    assert after == before


def test_a_page_confirmed_before_the_close_is_kept_and_saved(sample_page, settings, held_settle):
    p = _reused_page(settings, "Confirmed, closed", sample_page)
    before = _state(p)
    w = Window(p, settings)
    gate = PageGate()
    w.start(sample_page, gate)
    w.shown()
    assert gate.confirm()  # the window: the frame stayed, before the close
    assert not p.cache.dirty and _on_disk(settings, "Confirmed, closed") == []  # (the job has not kept it yet)
    w._on_close()
    assert gate.state == "confirmed"  # the close's drop changes nothing of it
    assert len(_on_disk(settings, "Confirmed, closed")) == 1  # kept, and saved at the close
    assert _times_kept(settings) == before["stage_times"] + 1  # its seconds too
    held_settle.set()
    w.join()
    assert w.kinds() == ["result", "translate_done"]
    assert len(p.cache) == 1 and len(_on_disk(settings, "Confirmed, closed")) == 1


def test_a_worker_held_on_the_job_past_the_close_changes_nothing_that_lasts(sample_page, sample_page2, settings,
                                                                           held_settle, monkeypatch):
    """The worker is held (a model's load, say) before it stores the page, past the close's wait: the close puts the
    job back from its own thread; the worker stores the page and counts its seconds after that, in memory - a save
    then writes none of it - and puts the job back itself when it decides it."""
    monkeypatch.setattr(pipeline_mod, "CLOSE_WAIT_S", 0.05)
    p = _reused_page(settings, "Held worker", sample_page)
    _unsaved_page(p, sample_page2, monkeypatch)
    earlier = [(pg.fingerprint, pg.seq, [b.text for b in pg.bubbles]) for pg in p.cache.pages]
    before = _state(p)
    entered, release = threading.Event(), threading.Event()
    real_store = p._store_regions

    def late_store(unit, regions):
        entered.set()
        assert release.wait(20.0)
        real_store(unit, regions)

    p._store_regions = late_store
    # (the worker past its last look at the cancel: it goes on to the page's end, whatever the close did meanwhile)
    monkeypatch.setattr(pipeline_mod, "check_cancel", lambda cancel: None)
    p._render = lambda out, regions, cancel=None, **_k: None
    w = Window(p, settings)
    gate = PageGate()
    w.start(sample_page, gate)
    assert entered.wait(20.0)
    started = time.monotonic()
    w._on_close()
    assert time.monotonic() - started < 5.0  # (a bounded wait)
    assert p._held_for is None and _state(p) == before  # put back by the close
    assert _on_disk(settings, "Held worker") == earlier and _times_kept(settings) == before["stage_times"]

    release.set()  # the worker goes on: the page stored, and its seconds counted, after the close put the job back
    w.shown()
    assert len(p.cache) == 2 and len(p.stage_times) == before["stage_times"] + 1 and p.cache.dirty
    app_mod.last_save(p)  # a save at this moment writes nothing of it ...
    devices.save_times(p, settings.state_dir)
    assert _on_disk(settings, "Held worker") == earlier and _times_kept(settings) == before["stage_times"]
    assert not p.flush_saves()  # ... nor does a save of what waits, until the worker has decided the job
    assert _on_disk(settings, "Held worker") == earlier

    held_settle.set()  # the worker decides the job: dropped, all of it put back again
    w.join()
    assert w.kinds() == ["result", "page_cancelled", "translate_done"]
    assert _state(p) == before
    assert _on_disk(settings, "Held worker") == earlier and _times_kept(settings) == before["stage_times"]


def test_the_close_drops_the_gates_and_cancels_the_page_job_before_anything_is_saved():
    pending, confirmed, cancel = PageGate(), PageGate(), threading.Event()
    assert confirmed.confirm()
    w = SimpleNamespace(_early=SimpleNamespace(gate=pending), _early_gate=None, _page_gate=confirmed,
                        _page_cancel=cancel)
    app_mod.end_page_job(w)
    assert pending.state == "dropped" and confirmed.state == "confirmed" and cancel.is_set() and w._early is None
    assert not pending.confirm()  # a confirmation at the same moment comes too late
    app_mod.end_page_job(SimpleNamespace())  # (a window with no page job: nothing)


def test_with_no_page_waiting_the_close_saves_as_ever(sample_page, settings):
    p = _pipeline(settings, "As ever")
    with p.saves_held():
        p.process(sample_page)  # a page read, its save waiting (the window closes before the job saved it)
    started = time.monotonic()
    assert not p.drop_unconfirmed()
    assert time.monotonic() - started < pipeline_mod.CLOSE_WAIT_S / 2  # nothing waited for
    assert p.to_save(p.cache) is p.cache and p.to_save(p.stage_times) is p.stage_times
    app_mod.last_save(p)
    devices.save_times(p, settings.state_dir)
    assert len(_on_disk(settings, "As ever")) == 1 and _times_kept(settings) == 1
