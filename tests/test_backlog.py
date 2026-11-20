"""Work behind the reader (`taslation.backlog`): a page the reader turned past once its frame was confirmed goes on
being read and translated from that capture, in memory, while nothing of the page on show runs; what is caught and
what not, what is kept, the order of the work, a step stopped by the next page with what it answered kept, the drops
and pauses, the events, the history in story order, and the six guarantees of the design (each a test of its own).
Invented lines only (`helpers`)."""
from __future__ import annotations

import builtins
import inspect
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, JA_TEXTS

from taslation import backlog as backlog_mod
from taslation.backlog import Backlog, Entry, Preempt, Screen, Tracking, drop_backlog, pause_backlog, reading_event
from taslation.backlog import tick as backlog_tick
from taslation.backlog import tracking_for
from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.pageimages import Packed, unpack
from taslation.pipeline import PageGate, Pipeline, keeps_answered, turn_away
from taslation.translate import DictTranslator
from taslation.translate.base import GrowingContext, StoryContext


class Turning(DictTranslator):
    """Answers the first *answer* lines of a request (handed over one by one), then the reader turns away (or, with
    *drop*, the window drops the frame: it changed before its confirmation; with *moment*, a frame on show only a
    moment). It says what its prompts computed, as PLaMo's does: the lines answered before a turn are kept."""

    grows_context = True

    def __init__(self, mapping, answer=1, drop=None, moment=False):
        super().__init__(mapping)
        self.answer, self.drop, self.moment = answer, drop, moment

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                       on_slow=None, computed=None):
        self.calls.append(list(texts))
        for i, text in enumerate(texts[:self.answer]):
            if on_item is not None:
                on_item(i, self.mapping.get(text, ""))
        if self.drop is not None:
            if self.moment:
                self.drop.shown_since = time.monotonic()
            self.drop.drop()
            cancel.set()
        else:
            turn_away(cancel)
        raise Cancelled()


class Blocking(DictTranslator):
    """Answers the first line, then holds the request until it is cancelled (a long line on a slow server)."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.waiting = threading.Event()

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                       on_slow=None):
        self.calls.append(list(texts))
        if on_item is not None and texts:
            on_item(0, self.mapping.get(texts[0], ""))
        self.waiting.set()
        while not cancel.is_set():
            time.sleep(0.01)
        raise Cancelled()


def _pipeline(settings, translator, book="Behind", ocr=None) -> Pipeline:
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return Pipeline(settings, ocr=ocr or FakeOcr(), translator=translator, cache=cache)


def _events():
    posted: list[tuple[str, dict]] = []
    return posted, (lambda kind, **data: posted.append((kind, data)))


def _confirmed(open_for=0.0, soft=False) -> PageGate:
    gate = PageGate(open_for, soft=soft)
    gate.seen(time.monotonic())
    assert gate.confirm()
    return gate


def _job(p: Pipeline, backlog: Backlog, image, gate, hwnd=7):
    """A page job of normal reading as the window's worker runs it (`ui.jobs._job_translate`): `process` within
    `page_on_show(gate)`, tracked; turned away from, or done."""
    cancel = threading.Event()
    tracking = Tracking(backlog, p, image, gate, hwnd)
    work = None
    looking = threading.Event()

    def look() -> None:  # (the window's looks at the viewer while the frame is pending: it is on show still)
        while not looking.is_set() and gate.state == "pending":
            gate.seen(time.monotonic())
            time.sleep(0.02)

    looker = threading.Thread(target=look, daemon=True) if gate is not None else None
    if looker is not None:
        looker.start()
    try:
        with (p.page_on_show(gate) if gate is not None else p.saves_held()) as work:
            tracking.attach(work)
            result = p.process(image, cancel=cancel, events=lambda kind, data: None)  # (a page fill: lines handed over)
    except Cancelled:
        tracking.cancelled(keeps_answered(cancel), work)
        return tracking, work, None
    finally:
        looking.set()
        if looker is not None:
            looker.join()
    if work is not None and work.waits:
        work.settle(cancel)
    tracking.finished(result)
    return tracking, work, result


def _stages(posted, seq=1):
    return [(d["stage"], d["state"]) for k, d in posted if k == "page_stage" and d.get("seq") == seq]


def _drain(p: Pipeline, backlog: Backlog, limit=20) -> list[str]:
    done = []
    for _ in range(limit):
        what = backlog.step(p)
        if not what:
            break
        done.append(what)
    return done


# ------------------------------------------------------------------ what is caught
def test_a_page_turned_past_once_confirmed_is_caught_with_its_reading_and_no_frame(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=2))
    _job(p, b, sample_page, _confirmed())
    assert len(b.entries) == 1
    entry = b.entries[0]
    assert entry.regions and entry.raw is None and entry.frame is None and b.frame_bytes == 0
    assert _stages(posted) == [("read", "working"), ("read", "done"), ("translate", "working"),
                               ("translate", "waiting")]
    first = next(d for k, d in posted if k == "page_stage")
    assert first["thumb"].height <= 96 and first["reading"] is True and first["fingerprint"]
    assert ("page_on_show", {"seq": 1, "reading": True}) in posted
    assert posted[-1][0] == "backlog" and posted[-1][1]["pages"] == 1


def test_the_backlog_translates_what_is_left_and_the_page_is_complete(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=2))
    _job(p, b, sample_page, _confirmed())
    kept = sum(len(page.bubbles) for page in p.cache.pages)
    p.translator = DictTranslator(EN_TEXTS)
    assert _drain(p, b) == ["made", "translate"]
    page = p.cache.pages[0]
    assert not page.incomplete and len(page.bubbles) > kept
    asked = [t for call in p.translator.calls for t in call]
    assert len(asked) == len(page.bubbles) - kept  # (only the lines not answered before the turn)
    assert _stages(posted)[-2:] == [("translate", "working"), ("translate", "done")]
    assert not b.entries and posted[-1][1]["pages"] == 0


def test_a_frame_that_changed_before_its_confirmation_is_told_as_gone_by_and_kept_nowhere(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    gate = PageGate()
    gate.seen(time.monotonic())
    gate.shown_since -= 0.5  # (on show half a second)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1, drop=gate))
    _job(p, b, sample_page, gate)
    assert not b.entries and not b.pending
    assert _stages(posted) == [("read", "missed")]
    missed = next(d for k, d in posted if k == "page_stage")
    assert "thumb" not in missed
    assert posted[-1] == ("backlog", {"pages": 0, "lines": 0, "paused": False, "dropped": 1, "reading": True})
    assert not p.cache.pages or all(not page.bubbles for page in p.cache.pages)  # (`Provisional`: put back)


def test_a_frame_on_show_only_a_moment_is_told_nothing(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    gate = PageGate()
    gate.seen(time.monotonic())
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1, drop=gate, moment=True))
    _job(p, b, sample_page, gate)  # (dropped within milliseconds of its start: a frame on its way)
    assert not b.entries and not [k for k, _d in posted if k == "page_stage"]


def test_a_soft_frame_is_never_caught(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed(soft=True))
    assert not b.entries and not b.pending
    assert ("translate", "missed") in _stages(posted)


def test_a_frame_confirmed_while_the_frames_still_changed_is_never_caught(settings, sample_page):
    # (pages flipped through without a stop: the window confirms the frame there is after SETTLE_TRIES looks, and the
    # frame did not stay - its page goes on being read nowhere, as it was before there was a backlog)
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    gate = _confirmed()
    gate.settled = False
    _job(p, b, sample_page, gate)
    assert not b.entries and not b.pending and b.frame_bytes == 0
    assert ("translate", "missed") in _stages(posted)
    gate = _confirmed(open_for=30.0)  # (on a viewer that draws soft first: not even kept for now)
    gate.settled = False
    _job(p, b, sample_page, gate)
    assert not b.entries and not b.pending
    gate = _confirmed()  # ... but one a look still found on show the fixed time after (`ui.live._mark_stayed`) is
    gate.settled_by, gate.settled = time.monotonic(), True
    _job(p, b, sample_page, gate)
    assert len(b.entries) == 1


def test_the_window_says_whether_the_frame_it_confirms_had_stayed():
    # (tests/test_early_start.py has the window's side: frames that keep changing, then one that stays or not)
    source = inspect.getsource(__import__("taslation.ui.live", fromlist=["x"]))
    at = source.index("early.gate.settled = not moving")
    assert at < source.index("if self._early_confirm(op, now):", at)
    assert source.count("self._mark_stayed(now") == 2


def test_a_page_job_without_a_gate_is_not_caught(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, None)
    assert not b.entries and not b.pending


def test_a_confirmation_kept_for_now_is_caught_once_sealed(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    gate = _confirmed(open_for=30.0)
    _job(p, b, sample_page, gate)
    assert not b.entries and len(b.pending) == 1 and not gate.sealed
    b.settle_pending()
    assert not b.entries  # (still open: a sharper picture may take it back)
    assert p.decide_kept() is True and gate.sealed  # (the worker, before its next job)
    b.settle_pending()
    assert len(b.entries) == 1 and not b.pending


def test_a_confirmation_taken_back_is_dropped_without_a_word(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    gate = _confirmed(open_for=30.0)
    _job(p, b, sample_page, gate)
    told = len(posted)
    assert gate.take_back() and p.decide_kept() is False
    b.settle_pending()
    assert not b.entries and not b.pending
    assert not [d for k, d in posted[told:] if k == "page_stage"]


class TurnWhileReading(FakeOcr):
    """Reads one region, then the reader turns away (the page's reading not over)."""

    def __init__(self, cancel_of):
        super().__init__()
        self.cancel_of = cancel_of

    def read(self, image):
        text = super().read(image)
        if self.calls == 1:
            turn_away(self.cancel_of())
        return text


def _reading_job(settings, b, sample_page, ocr_book="Frames"):
    holder: dict = {}
    ocr = TurnWhileReading(lambda: holder["cancel"])
    p = _pipeline(settings, DictTranslator(EN_TEXTS), ocr_book, ocr=ocr)
    gate = _confirmed()
    tracking = Tracking(b, p, sample_page, gate, 7)
    holder["cancel"] = cancel = threading.Event()
    with pytest.raises(Cancelled):
        with p.page_on_show(gate) as work:
            tracking.attach(work)
            p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
    tracking.cancelled(keeps_answered(cancel), work)
    return p


def _packed(b: Backlog, seconds=10.0) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end and any(e.raw is not None for e in b.entries):
        time.sleep(0.02)


def test_a_page_not_read_in_full_keeps_its_frame_packed_until_read_then_drops_it(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _reading_job(settings, b, sample_page)
    assert len(b.entries) == 1 and b.entries[0].regions is None
    _packed(b)
    entry = b.entries[0]
    assert isinstance(entry.frame, Packed) and entry.raw is None and 0 < b.frame_bytes == len(entry.frame.data)
    assert np.array_equal(np.asarray(unpack(entry.frame)), np.asarray(sample_page))  # (the job's own capture)
    assert ("read", "waiting") in _stages(posted)
    assert _drain(p, b) == ["read", "translate"]
    assert b.frame_bytes == 0 and not b.entries and b.peak_bytes > 0
    page = p.cache.pages[0]
    assert not page.incomplete and page.bubbles


def test_over_the_caps_a_page_is_not_caught(settings, sample_page, monkeypatch):
    posted, post = _events()
    b = Backlog(post)
    monkeypatch.setattr(backlog_mod, "FRAME_CAP_MB", 0.01)
    _reading_job(settings, b, sample_page, "Capped")
    assert not b.entries and ("translate", "missed") in _stages(posted)
    posted2, post2 = _events()
    b2 = Backlog(post2)
    monkeypatch.setattr(backlog_mod, "UNIT_CAP", 0)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Capped2")
    _job(p, b2, sample_page, _confirmed())
    assert not b2.entries


# ------------------------------------------------------------------ the order of work
def _entry(b: Backlog, sight: int, kind: str) -> Entry:
    screen = Screen(sight, f"{sight:080x}", 0.7)
    e = Entry(screen, 7)
    if kind == "frame":
        e.frame = Packed("RGB", (1, 1), b"x")
    elif kind == "regions":
        e.regions = []
    else:
        e.units = []
    b.entries.append(e)
    return e


def test_reads_come_first_in_the_order_of_first_sight_then_translations_in_story_order():
    b = Backlog(lambda kind, **data: None)
    t3, t1 = _entry(b, 3, "units"), _entry(b, 1, "units")
    r5, r2 = _entry(b, 5, "frame"), _entry(b, 2, "frame")
    m4 = _entry(b, 4, "regions")
    order = []
    for _ in range(5):
        what, e = b._next()
        order.append((what, e.screen.sight))
        b.entries.remove(e)
    assert order == [("read", 2), ("read", 5), ("make", 4), ("translate", 1), ("translate", 3)]
    assert {id(x) for x in (t3, t1, r5, r2, m4)}


def test_the_window_queues_a_step_only_when_it_is_idle_and_nothing_is_held(settings):
    b = Backlog(lambda kind, **data: None)
    _entry(b, 1, "units")
    import queue

    pipeline = SimpleNamespace(behind_allowed=lambda: True, translator=object(), behind_paused=False)
    window = SimpleNamespace(auto_var=SimpleNamespace(get=lambda: True), selected=SimpleNamespace(hwnd=7),
                             pipeline=pipeline, ready=True, busy=False, batch=None, _batching=False, _queued=None,
                             _jobs=queue.Queue(), _backlog=b)
    b.hwnd = 7
    for attr, value in (("busy", True), ("ready", False), ("batch", object()), ("_batching", True)):
        before = getattr(window, attr)
        setattr(window, attr, value)
        backlog_tick(window)
        assert window._jobs.empty(), attr
        setattr(window, attr, before)
    pipeline.behind_allowed = lambda: False  # (a page job's changes held for its frame)
    backlog_tick(window)
    assert window._jobs.empty()
    pipeline.behind_allowed = lambda: True
    backlog_tick(window)
    assert window._jobs.qsize() == 1 and b.step_queued
    backlog_tick(window)
    assert window._jobs.qsize() == 1  # (one at a time)


# ------------------------------------------------------------------ pre-emption
def test_the_next_page_stops_a_step_at_once_and_what_was_answered_is_stored(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    assert b.step(p) == "made"
    before = len(p.cache.pages[0].bubbles)
    p.translator = Blocking(EN_TEXTS)
    out: list[str] = []
    thread = threading.Thread(target=lambda: out.append(b.step(p)), daemon=True)
    thread.start()
    assert p.translator.waiting.wait(10)
    t0 = time.monotonic()
    p.stop_warm()  # (`ui.jobs._start_translate`: a page to read)
    thread.join(5)
    assert not thread.is_alive() and out == ["stopped"] and time.monotonic() - t0 < 0.5
    page = p.cache.pages[0]
    assert len(page.bubbles) == before + 1 and page.incomplete  # (the line answered kept, the page marked)
    assert len(b.entries) == 1 and b.wait_stats()["n"] == 1
    assert _stages(posted)[-2:] == [("translate", "working"), ("translate", "waiting")]
    p.translator = DictTranslator(EN_TEXTS)
    assert b.step(p) == "translate" and not p.cache.pages[0].incomplete


def test_a_job_waiting_for_the_worker_stops_a_step_too():
    waiting = [False]
    stop = Preempt(lambda: waiting[0])
    assert not stop.is_set()
    waiting[0] = True
    assert stop.is_set() and stop.set_at is not None


def test_no_step_runs_while_a_page_jobs_changes_are_held(settings, sample_page):
    b = Backlog(lambda kind, **data: None)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed(open_for=30.0))
    b.settle_pending()
    p.decide_kept()
    b.settle_pending()
    assert b.entries
    p._held_for = object()  # (a page job on a frame not confirmed yet)
    assert b.step(p) == ""
    p._held_for = None
    assert b.step(p) == "made"


# ------------------------------------------------------------------ drops and pauses
def _window(b: Backlog, p) -> SimpleNamespace:
    import queue

    return SimpleNamespace(auto_var=SimpleNamespace(get=lambda: True), selected=SimpleNamespace(hwnd=7), pipeline=p,
                           ready=True, busy=False, batch=None, _batching=False, _queued=None, _jobs=queue.Queue(),
                           _backlog=b, _post=lambda kind, **data: None)


def test_another_book_a_run_and_another_viewer_window_drop_it_stop_auto_and_a_release_pause_it(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    window = _window(b, p)
    assert b.entries
    pause_backlog(window, "stop")
    assert b.step(p) == "" and b.paused == {"stop"} and posted[-1][1]["paused"] is True
    tracking_for(window, sample_page, None)  # (the next page job: the reader reads on)
    assert not b.paused
    window.auto_var = SimpleNamespace(get=lambda: False)
    backlog_tick(window)
    assert "auto" in b.paused and window._jobs.empty() and b.entries  # (paused, not dropped)
    window.auto_var = SimpleNamespace(get=lambda: True)
    p.stop_warm(wait=True)  # (Tools > Release the model now)
    backlog_tick(window)
    assert b.paused == {"release"} and b.entries
    tracking_for(window, sample_page, None)
    assert not b.paused and not p.behind_paused
    window.selected = SimpleNamespace(hwnd=8)
    backlog_tick(window)
    assert not b.entries and not b.screens and ("page_on_show", {"seq": None, "reading": True}) in posted
    _job(p, b, sample_page, _confirmed())
    assert b.entries
    drop_backlog(window, "another book")
    assert not b.entries and p.cache.pages  # (what is stored stays)


def test_a_whole_book_run_and_another_book_drop_it_in_the_window():
    source = inspect.getsource(__import__("taslation.ui.jobs", fromlist=["x"]))
    assert 'drop_backlog(self, "a whole-book run")' in source and 'drop_backlog(self, "another book")' in source
    assert 'pause_backlog(self, "stop")' in source and "tracking.over()" in source


def test_no_tracking_in_a_whole_book_run_nor_for_translate_again(settings, sample_page):
    p = _pipeline(settings, DictTranslator(EN_TEXTS))
    b = Backlog(lambda kind, **data: None)
    window = _window(b, p)
    window.batch = object()
    assert tracking_for(window, sample_page, None) is None
    window.batch = None
    assert tracking_for(window, sample_page, None, again=object()) is None
    assert tracking_for(window, sample_page, None) is not None


# ------------------------------------------------------------------ the events and the window
def test_reading_events_go_to_the_reading_handlers_and_never_to_the_runs_page_strip():
    from taslation.ui.jobs import JobsMixin

    got: list = []
    fake = SimpleNamespace(_on_page_stage=lambda data: (_ for _ in ()).throw(AssertionError("the run's strip")),
                           _on_reading_page_stage=lambda data: got.append(("stage", data)),
                           _on_reading_page_on_show=lambda data: got.append(("show", data)),
                           _on_reading_backlog=lambda data: got.append(("backlog", data)))
    JobsMixin._handle_event(fake, "page_stage", {"seq": 1, "stage": "read", "state": "done", "reading": True})
    JobsMixin._handle_event(fake, "page_on_show", {"seq": 1, "reading": True})
    JobsMixin._handle_event(fake, "backlog", {"pages": 0, "reading": True})
    assert [k for k, _d in got] == ["stage", "show", "backlog"]
    reading_event(SimpleNamespace(), "backlog", {})  # (no handler yet: nothing)


def test_a_page_seen_again_keeps_its_number_and_a_page_that_went_by_merges_into_it(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, DictTranslator(EN_TEXTS))
    _job(p, b, sample_page, _confirmed())
    _job(p, b, sample_page, _confirmed())
    assert len(b.screens) == 1 and {d["seq"] for k, d in posted if k == "page_stage"} == {1}
    gone = Screen(9, b.screens[0].fingerprint, b.screens[0].aspect, seq=2, missed=True)
    b.screens.append(gone)
    backlog_mod.merge_missed(b, b.screens[0], 36)
    assert posted[-1] == ("page_stage", {"seq": 2, "fingerprint": gone.fingerprint, "stage": "read",
                                         "state": "merged", "into": 1, "reading": True})


# ------------------------------------------------------------------ the history in story order
def test_story_context_is_growing_context_while_pages_come_in_order():
    import random

    rnd = random.Random(5)
    for trial in range(60):
        g, s = GrowingContext(), StoryContext()
        fits = (lambda pairs: sum(len(a) + len(b) for a, b in pairs) < 900) if trial % 2 else None
        for page in range(30):
            assert g.take(fits) == s.take(fits) and g.peek(fits) == s.peek(fits)
            pairs = [(f"j{page}_{i}" * rnd.randint(1, 4), f"t{i}") for i in range(rnd.randint(0, 9))]
            s.place(page if trial % 3 == 0 else None)
            g.extend(pairs)
            s.extend(pairs)
            assert list(g) == list(s)
        assert g.cuts == s.cuts


def test_a_request_behind_the_reader_gets_the_pages_before_it_in_the_story():
    s = StoryContext()
    for page in (1, 2, 5, 6):  # (the reader: pages 1 and 2, then 5 and 6 - pages 3 and 4 turned past)
        s.place(page)
        s.extend([(f"ja{page}", f"en{page}")])
    s.place(3)
    assert s.take() == [("ja1", "en1"), ("ja2", "en2")]
    s.extend([("ja3", "en3")])
    s.place(4)
    assert s.take() == [("ja1", "en1"), ("ja2", "en2"), ("ja3", "en3")]  # (extends the request before it)
    s.place(7)
    assert [p[0] for p in s.take()] == ["ja1", "ja2", "ja3", "ja5", "ja6"]


def test_a_cut_behind_the_reader_keeps_the_pages_after_it():
    s = StoryContext(grows_to=5, cut_to=2)
    for page in range(1, 7):
        s.place(page)
        s.extend([(f"ja{page}", "x")])
    s.place(3)
    s.extend([("ja3b", "x"), ("ja3c", "x"), ("ja3d", "x")])
    assert [p[0] for p in s.take()] == ["ja3c", "ja3d"] and s.cuts == 1  # (6 up to it: cut to the newest 2)
    s.place(None)
    assert [p[0] for p in s.peek()] == ["ja3c", "ja3d", "ja4", "ja5", "ja6"]  # (the pages after it kept)


def test_a_request_that_parts_from_the_last_gets_the_common_beginning_and_little_more():
    s = StoryContext()
    s.place(1)
    s.extend([(f"a{i}", "x") for i in range(3)])
    s.place(9)
    s.extend([(f"r{i}", "x") for i in range(20)])
    s.take()  # (the reader's request: a0..a2, r0..r19)
    s.place(2)
    s.switch_to = 2
    assert s.switches()  # (behind the reader: the server's pairs of the reader's page are left)
    assert [p[0] for p in s.peek()] == ["a0", "a1", "a2"]  # (a beginning of the last: nothing left out)
    s.extend([(f"b{i}", "x") for i in range(10)])
    s.place(1.5)
    s.extend([("c", "x")])
    s.place(2)
    assert s.switches()
    got = [p[0] for p in s.take()]
    assert got == ["a0", "a1", "a2", "b8", "b9"]  # (the common beginning and the newest 2 of the rest)
    s.extend([("b10", "x")])
    assert not s.switches()  # (the next request behind the reader grows the one before it)
    assert [p[0] for p in s.take()] == ["a0", "a1", "a2", "b8", "b9", "b10"]
    s.switch_to = None
    s.place(9)
    assert len(s.take()) == 3 + 1 + 11 + 20  # (the reader's own request: every pair before its page, in order)


def test_a_page_jobs_snapshot_of_the_story_is_not_changed_by_what_comes_after():
    from taslation.pipeline import _held_state, _put_back

    s = StoryContext()
    s.place(1)
    s.extend([("a", "x")])
    held = _held_state(s)
    s.extend([("b", "x")])
    s.place(4)
    _put_back(s, held)
    assert list(s) == [("a", "x")] and s.at == 1


# ------------------------------------------------------------------ the six guarantees (design, section 2)
def test_guarantee_1_only_the_capture_the_job_read_is_ever_read_and_nothing_is_captured(settings, sample_page,
                                                                                        monkeypatch):
    import taslation.capture as capture

    for name in ("capture_window", "frame_count", "frame_wait"):
        monkeypatch.setattr(capture, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("a capture")))
    posted, post = _events()
    b = Backlog(post)
    read: list = []
    p = _reading_job(settings, b, sample_page, "OnlyThat")
    real_scan = p.scan
    monkeypatch.setattr(p, "scan", lambda image, **k: (read.append(np.asarray(image).copy()), real_scan(image, **k))[1])
    _packed(b)
    assert _drain(p, b) == ["read", "translate"]
    assert len(read) == 1 and np.array_equal(read[0], np.asarray(sample_page))


def test_guarantee_2_nothing_from_a_soft_or_unconfirmed_frame_is_kept_or_queued(settings, sample_page):
    b = Backlog(lambda kind, **data: None)
    pending = PageGate()
    pending.seen(time.monotonic())
    for gate in (_confirmed(soft=True), pending, None):
        p = _pipeline(settings, Turning(EN_TEXTS, answer=1), f"G2{id(gate)}")
        _job(p, b, sample_page, gate)
        b.settle_pending()
        assert not b.entries and not b.pending


def test_guarantee_3_the_backlog_draws_nothing_and_shows_no_page(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    p.translator = DictTranslator(EN_TEXTS)
    _drain(p, b)
    assert {k for k, _d in posted} <= {"page_stage", "page_on_show", "backlog"}
    for _k, d in posted:
        for v in d.values():
            assert not hasattr(v, "size") or v.size[1] <= 96  # (a thumbnail at most; never a page)


def test_guarantee_4_a_turn_waits_for_one_step_at_most(settings, sample_page):
    test_the_next_page_stops_a_step_at_once_and_what_was_answered_is_stored(settings, sample_page)


def test_guarantee_5_the_backlog_writes_no_page_image_and_no_japanese_text(settings, sample_page, monkeypatch):
    b = Backlog(lambda kind, **data: None)
    p = _reading_job(settings, b, sample_page, "NoDisk")
    _packed(b)
    written: list[str] = []
    real_open = builtins.open

    def watched(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            written.append(str(file))
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", watched)
    from PIL import Image

    monkeypatch.setattr(Image.Image, "save", lambda *a, **k: (_ for _ in ()).throw(AssertionError("an image saved")))
    _drain(p, b)
    cache_dir = str(settings.cache_dir)
    assert all(path.startswith(cache_dir) for path in written)  # (the protected cache alone, as a page job saves it)
    for path in written:
        try:
            text = real_open(path, "rb").read().decode("utf-8", "ignore")
        except OSError:
            continue
        assert not any(ja in text for ja in JA_TEXTS)


def test_guarantee_6_the_backlog_sends_no_key_and_turns_no_page():
    source = inspect.getsource(backlog_mod)
    for name in ("SendInput", "keybd_event", "PostMessage", "SendMessage", "send_key", "press_key", "turn_page",
                 "capture_window", "SetForegroundWindow", "mouse_event"):
        assert name not in source
    tree = __import__("ast").parse(source)
    imported = {n.module for n in __import__("ast").walk(tree) if type(n).__name__ == "ImportFrom" and n.module}
    assert not imported & {"capture", "viewers", "ui.live", "live"}


def test_a_page_job_that_ends_otherwise_gives_back_what_the_backlog_held_for_its_page(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    screen = b.entries[0].screen
    b.hold(screen)  # (the page on show again, its job at work ...)
    assert not b.entries and b.held_entry(screen) is not None
    tracking = Tracking(b, p, sample_page, _confirmed(), 7)
    tracking.screen = screen
    tracking.over()  # (... and failed: `ui.jobs._job_translate`'s finally)
    assert [e.screen for e in b.entries] == [screen] and b.held_entry(screen) is None
