"""Work behind the reader (`taslation.backlog`): a page the reader turned past once its frame was confirmed goes on
being read and translated from that capture, in memory, while nothing of the page on show runs; what is caught and
what not, what is kept, the order of the work, a step stopped by the next page with what it answered kept, the drops
and pauses, the events, the history (the order of work), and the six guarantees of the design (each a test of its own).
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
from taslation.translate.base import GrowingContext


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
        with p.page_on_show(gate) as work:  # (no gate: a page the window took as settled, as the window's job has it)
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


# ------------------------------------------------------------------ never left at work with nothing at work on it
def _last(posted, seq=1) -> dict[str, str]:
    """The last state told of each stage of screen *seq*."""
    return dict(_stages(posted, seq))


class CancelWhileReading(FakeOcr):
    """Reads one region, then the job is cancelled: the reader turned away (*turned*), or Stop."""

    def __init__(self, cancel_of, turned=True):
        super().__init__()
        self.cancel_of, self.turned = cancel_of, turned

    def read(self, image):
        text = super().read(image)
        if self.calls == 1:
            cancel = self.cancel_of()
            turn_away(cancel) if self.turned else cancel.set()
        return text


def _job_cancelled_reading(settings, b, sample_page, gate, turned, book):
    """A page job (`_job`) cancelled while it reads: turned past (*turned*) or stopped."""
    holder: dict = {}
    p = _pipeline(settings, DictTranslator(EN_TEXTS), book, ocr=CancelWhileReading(lambda: holder["cancel"], turned))
    tracking = Tracking(b, p, sample_page, gate, 7)
    holder["cancel"] = cancel = threading.Event()
    try:
        with pytest.raises(Cancelled):
            with p.page_on_show(gate) as work:
                tracking.attach(work)
                p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
        tracking.cancelled(keeps_answered(cancel), work)
    finally:
        tracking.over()
    return tracking


@pytest.mark.parametrize("turned", [True, False])
def test_a_page_job_without_a_gate_cancelled_while_it_reads_is_never_left_at_work(settings, sample_page, turned):
    # (a page job with no gate - F5, a page taken as settled, a sharper frame read again: `backlog`'s docstring -,
    # told "read working" at once: turned past or stopped, it waits to be read when shown again. Before, its bar
    # stayed "working" for good, nothing at work on it; then, turned past, it was told "missed" as a page gone by)
    posted, post = _events()
    b = Backlog(post)
    _job_cancelled_reading(settings, b, sample_page, None, turned, f"Gateless {turned}")
    assert _stages(posted)[0] == ("read", "working")
    assert "working" not in _last(posted).values()
    assert _last(posted)["read"] == "waiting" and not b.screens[0].missed
    assert not b.entries and not b.pending and b.not_caught == (1 if turned else 0)


def test_a_page_job_without_a_gate_turned_past_while_it_asks_waits_for_its_next_showing(settings, sample_page):
    # (it is never caught - nothing from a frame never confirmed is kept behind the reader -, and it is no page that
    # went by too fast: before, it was told "missed" and the totals counted it among the pages gone by)
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, None)
    assert ("translate", "working") in _stages(posted)
    assert _last(posted) == {"read": "done", "translate": "waiting"} and b.not_caught == 1
    assert not b.entries and not b.pending and not b.screens[0].missed
    assert all(d["dropped"] == 0 for k, d in posted if k == "backlog")  # (not counted as gone by)
    # (one whose gate was sealed but is not caught - soft, not settled, over the caps - is told "missed" as ever:
    # test_a_soft_frame_is_never_caught and those after it)


@pytest.mark.parametrize("turned", [True, False])
def test_a_confirmation_taken_back_while_its_job_reads_leaves_nothing_at_work(settings, sample_page, turned):
    # (a sharper picture of the page came: the window takes the confirmation back and cancels the job - the sharper
    # frame's own job tells the page from then on; until it does, the page waits)
    posted, post = _events()
    b = Backlog(post)
    gate = _confirmed(open_for=30.0)
    real_set = threading.Event.set

    class Taken(threading.Event):
        def set(self):
            gate.take_back()
            real_set(self)

    holder: dict = {}
    p = _pipeline(settings, DictTranslator(EN_TEXTS), f"Taken back {turned}",
                  ocr=CancelWhileReading(lambda: holder["cancel"], turned))
    tracking = Tracking(b, p, sample_page, gate, 7)
    holder["cancel"] = cancel = Taken()
    with pytest.raises(Cancelled):
        with p.page_on_show(gate) as work:
            tracking.attach(work)
            p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
    tracking.cancelled(keeps_answered(cancel), work)
    tracking.over()
    assert gate.state == "dropped" and _stages(posted)[0] == ("read", "working")
    assert _last(posted) == {"read": "waiting"} and not b.entries and not b.pending


def test_a_page_job_that_fails_leaves_nothing_at_work(settings, sample_page):
    class Failing(FakeOcr):
        def read(self, image):
            raise RuntimeError("a reader that fails")

    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, DictTranslator(EN_TEXTS), "Fails", ocr=Failing())
    gate = _confirmed()
    tracking = Tracking(b, p, sample_page, gate, 7)
    try:
        with pytest.raises(RuntimeError):
            with p.page_on_show(gate) as work:
                tracking.attach(work)
                p.process(sample_page, cancel=threading.Event(), events=lambda kind, data: None)
    finally:
        tracking.over()  # (`ui.jobs._job_translate`'s finally: neither finished nor cancelled)
    assert _stages(posted)[0] == ("read", "working") and _last(posted) == {"read": "failed"}


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


@pytest.mark.parametrize("while_it", ["asks", "reads"])
def test_a_page_kept_for_now_whose_confirmation_is_taken_back_is_told_as_not_caught(settings, sample_page, while_it):
    # (turned away from within the hold, then its confirmation taken back: nothing holds the page any more. Before, it
    # was only let go of - translate left "waiting", read "working" when it was turned away from as it read)
    posted, post = _events()
    b = Backlog(post)
    gate = _confirmed(open_for=30.0)
    if while_it == "asks":
        p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Taken back, asked")
        _job(p, b, sample_page, gate)
    else:
        holder: dict = {}
        p = _pipeline(settings, DictTranslator(EN_TEXTS), "Taken back, read",
                      ocr=TurnWhileReading(lambda: holder["cancel"]))
        tracking = Tracking(b, p, sample_page, gate, 7)
        holder["cancel"] = cancel = threading.Event()
        with pytest.raises(Cancelled):
            with p.page_on_show(gate) as work:
                tracking.attach(work)
                p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
        tracking.cancelled(keeps_answered(cancel), work)
    read = "done" if while_it == "asks" else "working"
    assert len(b.pending) == 1 and _last(posted) == {"read": read, "translate": "waiting"}  # (kept for now)
    assert gate.take_back()
    p.decide_kept()
    b.settle_pending()
    assert not b.entries and not b.pending and b.not_caught == 1
    assert _last(posted) == {"read": "done" if while_it == "asks" else "missed", "translate": "missed"}
    assert posted[-1][0] == "backlog" and posted[-1][1]["dropped"] == 1


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


def _done_with(b: Backlog, what: str, e: Entry) -> None:
    """*e* as the step *what* leaves it: read (or made) - its units to translate -, or translated - gone."""
    if what in ("read", "make"):
        e.frame = e.raw = e.regions = None
        e.units = []
    else:
        b.entries.remove(e)


def test_the_page_nearest_the_reader_ahead_of_it_comes_first_with_all_it_needs_before_the_next():
    b = Backlog(lambda kind, **data: None)
    for sight, kind in ((1, "units"), (2, "frame"), (5, "frame"), (6, "regions"), (8, "units")):
        _entry(b, sight, kind)
    b.screens = [e.screen for e in b.entries]
    here = Screen(4, "f" * 80, 0.7, seq=4)  # (the page on show: none of the backlog's entries)
    b.screens.append(here)
    b.show(here)
    order = []
    while b.entries:
        what, e = b._next()
        order.append((what, e.screen.sight))
        _done_with(b, what, e)
    # (ahead of the reader first, each page read then translated before the next; then from the smallest of all)
    assert order == [("read", 5), ("translate", 5), ("make", 6), ("translate", 6), ("translate", 8),
                     ("translate", 1), ("read", 2), ("translate", 2)]


def test_in_a_page_jobs_hold_the_next_step_is_the_nearest_read_its_translations_wait():
    """(`Backlog._next` with *reads_only*: a page kept for now, `Pipeline.behind_reads_allowed`)"""
    b = Backlog(lambda kind, **data: None)
    for sight, kind in ((1, "units"), (2, "frame"), (3, "regions"), (4, "units")):
        _entry(b, sight, kind)
    assert [b._next()[0], b._next()[1].screen.sight] == ["translate", 1]
    order = []
    while (nxt := b._next(reads_only=True)) is not None:
        order.append((nxt[0], nxt[1].screen.sight))
        _done_with(b, nxt[0], nxt[1])
    assert order == [("read", 2), ("make", 3)] and len(b.entries) == 4  # (all four left to translate, nearest first)
    assert [b._next()[0], b._next()[1].screen.sight] == ["translate", 1]


def test_the_choice_is_made_again_at_every_step_where_the_reader_is_now():
    b = Backlog(lambda kind, **data: None)
    entries = {sight: _entry(b, sight, "frame") for sight in (2, 3, 7, 8)}
    b.screens = [e.screen for e in b.entries]
    on_show = {sight: Screen(sight, f"{sight:080x}", 0.7) for sight in (1, 6)}
    b.screens.extend(on_show.values())
    b.show(on_show[1])
    what, e = b._next()
    assert (what, e.screen.sight) == ("read", 2)
    _done_with(b, what, e)
    b.show(on_show[6])  # (the reader turned to page 6 meanwhile: page 7 is the likeliest next)
    assert b._next()[1] is entries[7]
    b.show(None)  # (none of the book's on show: where the reader was last)
    assert b._next()[1] is entries[7]
    for e in (entries[7], entries[8]):
        b.entries.remove(e)
    assert b._next()[1] is entries[2]  # (nothing past the reader: the smallest of all)


def test_a_frame_read_by_the_backlog_says_how_long_it_was_held(settings, sample_page):
    b = Backlog(lambda kind, **data: None)
    p = _reading_job(settings, b, sample_page, "Waited")
    _packed(b)
    assert _drain(p, b) == ["read", "translate"]
    assert len(b.frame_waits) == 1 and 0 < b.frame_waits[0] < 30 and b.last_frame_wait == b.frame_waits[0]
    assert b.bytes_held == 0


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
    assert not getattr(window._jobs.queue[0], "in_hold", False)
    backlog_tick(window)
    assert window._jobs.qsize() == 1  # (one at a time)


def test_in_a_page_jobs_hold_the_window_queues_a_read_only_and_the_worker_leaves_the_page_undecided_for_it(settings):
    """(a page kept for now: `Pipeline.behind_reads_allowed` without `behind_allowed`; `ui.jobs.next_job`)"""
    import queue

    from taslation.ui import jobs

    b = Backlog(lambda kind, **data: None)
    b.hwnd = 7
    _entry(b, 1, "units")
    decided: list[str] = []
    left = [1.5]
    pipeline = SimpleNamespace(behind_allowed=lambda: False, behind_reads_allowed=lambda: True,
                               translator=object(), behind_paused=False, kept_open_left=lambda: left[0],
                               decide_kept=lambda: decided.append("decided"), stop_warm=lambda: None)
    window = SimpleNamespace(auto_var=SimpleNamespace(get=lambda: True), selected=SimpleNamespace(hwnd=7),
                             pipeline=pipeline, ready=True, busy=False, batch=None, _batching=False, _queued=None,
                             _jobs=queue.Queue(), _backlog=b)
    backlog_tick(window)
    assert window._jobs.empty()  # (only a translation to do: it waits for the decision)
    _entry(b, 2, "frame")
    backlog_tick(window)
    assert window._jobs.qsize() == 1 and window._jobs.queue[0].in_hold
    job = jobs.next_job(window)
    assert job.in_hold and decided == []  # (the page kept for now stays undecided while the read runs)
    window._jobs.put(job)
    left[0] = 0.0  # (its time up by the time the worker takes it: decided first, as before any job)
    assert jobs.next_job(window) is job and decided == ["decided"]
    pipeline.behind_reads_allowed = lambda: False  # (a page job's changes held for its frame: nothing at all)
    b.step_queued = False
    backlog_tick(window)
    assert window._jobs.empty()


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


def test_a_step_stopped_mid_page_gives_the_pairs_answered_by_then_to_the_pages_pairs(settings, sample_page):
    # (a translator that does not grow its context - `_Recording` -: before, the pairs answered before the stop never
    # reached `Pipeline._context`, so the next request did not have them; one that grows it has them grown as it goes)
    b = Backlog(_events()[1])
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Stopped, not growing")
    _job(p, b, sample_page, _confirmed())
    assert b.step(p) == "made"
    p.translator = Blocking(EN_TEXTS)  # (answers one line, then holds the request until it is stopped)
    assert not getattr(p.translator, "grows_context", False) and p._context.maxlen
    p._context.clear()
    out: list[str] = []
    thread = threading.Thread(target=lambda: out.append(b.step(p)), daemon=True)
    thread.start()
    assert p.translator.waiting.wait(10)
    p.stop_warm()
    thread.join(5)
    assert out == ["stopped"]
    pairs = [pair for page in p._context for pair in page]
    asked = p.translator.calls[0][0]
    assert pairs == [(asked, EN_TEXTS[asked])]  # (the one line answered before the stop)
    p.translator = DictTranslator(EN_TEXTS)
    assert b.step(p) == "translate" and len(p._context) == 2  # (the rest of the page: its pairs once more, as ever)


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


def _held_with_a_frame_behind(settings, b, sample_page, sample_page2, book, open_for=30.0):
    """A page turned past while it was read (its frame to read, `_reading_job`), then a page job on another page kept
    for now (`Provisional.keep`: its confirmation open for *open_for* s)."""
    p = _reading_job(settings, b, sample_page, book)
    _packed(b)
    assert len(b.entries) == 1 and b.entries[0].frame is not None
    gate = _confirmed(open_for=open_for)
    _job(p, b, sample_page2, gate)
    assert p._kept_open is not None and p._provisional is None and not gate.sealed
    return p, gate


@pytest.mark.parametrize("taken_back", [False, True])
def test_while_a_page_is_kept_for_now_the_backlog_reads_and_its_translation_waits(settings, sample_page, sample_page2,
                                                                                  taken_back):
    b = Backlog(lambda kind, **data: None)
    p, gate = _held_with_a_frame_behind(settings, b, sample_page, sample_page2, f"Hold {taken_back}")
    held = p._kept_open
    pages_before = len(p.cache.pages)
    assert not p.behind_allowed() and p.behind_reads_allowed()
    assert b.step(p) == "read"  # (in the hold: the frame of the page turned past read)
    assert b.entries[0].frame is None and b.entries[0].units
    assert b.step(p) == ""  # (its translation waits: a take-back would put back what it stored)
    assert p._kept_open is held and not gate.sealed and len(p.cache.pages) == pages_before
    if taken_back:
        assert gate.take_back()
    assert p.decide_kept() is (not taken_back)
    assert b.step(p) == "translate" and not b.entries
    assert len(p.cache.pages) == (1 if taken_back else 2) and not any(pg.incomplete for pg in p.cache.pages)


def test_a_read_in_the_hold_stops_as_its_time_is_up_and_the_next_read_takes_it_up(settings, sample_page,
                                                                                    sample_page2):
    b = Backlog(lambda kind, **data: None)
    p, _gate = _held_with_a_frame_behind(settings, b, sample_page, sample_page2, "Hold up")
    left = [30.0]
    p.kept_open_left = lambda: left[0]  # (the hold's time, as the step looks at it)

    class TimeUp(FakeOcr):
        """(the same reader read before and after: what a read depends on unchanged, `Pipeline.read_signature`)"""

        def __init__(self):
            super().__init__()
            self.up = False

        def read(self, image):
            if not self.up:
                self.up, left[0] = True, 0.0  # (the time is up while the first region is read)
            return super().read(image)

    ocr = p.ocr = TimeUp()
    assert b.step(p) == "stopped" and b.waits == [] and b.last_wait is None  # (no turn stopped it: no wait counted)
    assert b.entries[0].found is not None and b.in_hold == {"time up": 1, "stopped": 1}  # (what it read kept)
    calls = ocr.calls
    del p.kept_open_left
    assert p.decide_kept() is True
    assert b.step(p) == "read" and b.resumes.get("resumed") == 1
    assert ocr.calls > calls and b.in_hold == {"time up": 1, "stopped": 1}  # (the rest read, outside the hold)
    assert b.step(p) == "translate" and not b.entries


def test_the_windows_close_decides_a_page_kept_for_now_once_the_read_in_its_hold_is_over(settings, sample_page,
                                                                                          sample_page2):
    """(the close decides it on its own thread, `Pipeline.drop_unconfirmed`: never under the backlog's read)"""
    b = Backlog(lambda kind, **data: None)
    p, gate = _held_with_a_frame_behind(settings, b, sample_page, sample_page2, "Hold close")
    entered, release = threading.Event(), threading.Event()

    class Held(FakeOcr):
        def read(self, image):
            entered.set()
            assert release.wait(10)
            return super().read(image)

    p.ocr = Held()
    stepped: list[str] = []
    step = threading.Thread(target=lambda: stepped.append(b.step(p)), daemon=True)
    step.start()
    assert entered.wait(10)
    decided: list = []
    close = threading.Thread(target=lambda: decided.append(p.decide_kept()), daemon=True)
    close.start()
    close.join(0.3)
    assert close.is_alive() and p._kept_open is not None and not gate.sealed  # (it waits for the read)
    release.set()
    step.join(10)
    close.join(10)
    assert stepped == ["read"] and decided == [True] and gate.sealed and p._kept_open is None


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


class Silent(DictTranslator):
    """A translator whose server does not answer, as `translate.ollama`'s rule leaves it: each request ends with
    ``ollama.not_answering`` (asked again and, for the server TASlation started, the server started again, before),
    ``silent`` the incident and ``endings`` counted, until *answers* is set: then it answers again."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.silent = self.endings = 0
        self.answers = False

    def translate_page(self, texts, *args, **kwargs):
        from taslation.messages import Message
        from taslation.translate import TranslationError

        if self.answers:
            self.silent = 0  # (`OllamaTranslator._answered`)
            return super().translate_page(texts, *args, **kwargs)
        self.calls.append(list(texts))
        self.silent, self.endings = 1, self.endings + 1
        raise TranslationError(Message("ollama.not_answering"))


def _paused_told(posted) -> list[bool]:
    return [d["paused"] for k, d in posted if k == "backlog"]


def test_a_request_of_its_own_without_an_answer_pauses_it_says_so_and_an_answer_lets_it_go_on(settings, sample_page):
    from taslation.messages import Message

    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "NoAnswer")
    _job(p, b, sample_page, _confirmed())
    assert b.step(p) == "made"
    p.translator = silent = Silent(EN_TEXTS)
    assert b.step(p) == "failed" and len(silent.calls) == 1
    assert "no_answer" in b.paused and b.fatal is None and b.entries  # (never waits for a page job as a fatal one)
    # (the backlog's end is said, as the backlog's: in the status line, no page on show's)
    assert ("model_status", {"message": Message("ollama.not_answering"), "behind": True}) in posted
    assert _paused_told(posted)[-1] is True and _stages(posted)[-1] == ("translate", "waiting")
    window = _window(b, p)
    for _ in range(3):  # (nothing goes on, nothing asks: the reader is told, once)
        backlog_tick(window)
    assert window._jobs.empty() and b.step(p) == "" and len(silent.calls) == 1
    silent.answers = True
    p.translator.translate_page(["x"])  # (a request of any job answered: the page on show's, say)
    backlog_tick(window)
    assert not b.paused and _paused_told(posted)[-1] is False and window._jobs.qsize() == 1  # (on by itself)
    assert window._jobs.get()() is None and not b.entries and not p.cache.pages[0].incomplete


def test_another_job_s_request_without_an_answer_pauses_it_until_f5_or_auto_on(settings, sample_page):
    from taslation.ui import jobs

    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "NoAnswer2")
    _job(p, b, sample_page, _confirmed())
    assert b.step(p) == "made"
    p.translator = silent = Silent(EN_TEXTS)
    silent.silent, silent.endings = 1, 1  # (the page on show's request ended so)
    window = _window(b, p)
    backlog_tick(window)
    assert b.paused == {"no_answer"} and window._jobs.empty() and _paused_told(posted)[-1] is True
    queued: list[str] = []
    f5 = SimpleNamespace(ready=False, busy=False, _backlog=b, pipeline=p, _queue=queued.append)
    jobs.JobsMixin.translate_now(f5)  # (F5)
    assert not b.paused and queued == ["translate"]
    backlog_tick(window)
    assert not b.paused and window._jobs.qsize() == 1  # (asked once more)
    window._jobs.get()()
    assert "no_answer" in b.paused and silent.endings == 2  # (its own request ended so too: paused again)
    window.auto_var = SimpleNamespace(get=lambda: False)
    backlog_tick(window)
    assert b.paused == {"auto", "no_answer"}
    window.auto_var = SimpleNamespace(get=lambda: True)  # (Auto on)
    backlog_tick(window)
    assert not b.paused and window._jobs.qsize() == 1
    window._jobs.get()()
    assert b.paused == {"no_answer"}
    p.translator = Silent(EN_TEXTS)  # (another translator: the language switched; nothing ended without an answer)
    backlog_tick(window)
    assert not b.paused


class Telling(DictTranslator):
    """Notes, in each request, whether its thread runs a step of the backlog's (`backlog.in_step`) - and whether
    another thread is taken for one meanwhile -, and waits on its cancel as the translator's restart does
    (`ollama_start._wait_answer`: ``cancel.wait``)."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.seen: list[tuple[bool, bool, bool]] = []

    def translate_page(self, texts, *args, cancel=None, **kwargs):
        other: list[bool] = []
        thread = threading.Thread(target=lambda: other.append(backlog_mod.in_step()))
        thread.start()
        thread.join()
        waited = cancel.wait(0.01) if cancel is not None else False
        self.seen.append((backlog_mod.in_step(), other[0], waited))
        return super().translate_page(texts, *args, cancel=cancel, **kwargs)


def test_what_a_request_of_the_backlogs_tells_is_the_backlogs_and_its_cancel_waits_as_an_event(settings, sample_page):
    """(the rule for a request without an answer, `translate.ollama`) A request of the backlog's is known for one in
    its thread while its step runs (the window says what it tells in the status line only: `ui.jobs._model_status`),
    never in another thread nor after the step; its cancel (`Preempt`) is waited on where the restart waits on a
    request's cancel - it had no ``wait``, and the restart of a server for a request of the backlog's failed."""
    b = Backlog(lambda kind, **data: None)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Behind-told")
    _job(p, b, sample_page, _confirmed())
    assert not backlog_mod.in_step() and b.step(p) == "made"
    p.translator = telling = Telling(EN_TEXTS)
    assert b.step(p) == "translate" and telling.seen and not b.entries
    assert all(seen == (True, False, False) for seen in telling.seen), telling.seen
    assert not backlog_mod.in_step()  # (the step is over)
    telling.translate_page(["x"], cancel=threading.Event())  # (a request of the page on show's)
    assert telling.seen[-1][0] is False


def test_the_backlogs_cancel_is_waited_on_as_a_threading_event_and_a_restart_waits_on_it(monkeypatch):
    from taslation import health, ollama_start

    stop = Preempt()
    began = time.monotonic()
    assert stop.wait(0.06) is False and time.monotonic() - began >= 0.05
    waiting = [False]
    turned = Preempt(lambda: waiting[0])
    threading.Timer(0.05, lambda: waiting.__setitem__(0, True)).start()  # (a page job comes to wait for the worker)
    began = time.monotonic()
    assert turned.wait(5.0) is True and time.monotonic() - began < 2.0 and turned.set_at is not None
    stop.set()
    assert stop.wait() is True and stop.wait(0) is True
    # (the restart's wait for a server started again: `_wait_answer` with a step's cancel)
    monkeypatch.setattr(health, "ollama_running", lambda url: False)
    monkeypatch.setattr(ollama_start, "START_WAIT_S", 0.2)
    monkeypatch.setattr(ollama_start, "POLL_S", 0.02)
    assert ollama_start._wait_answer("http://127.0.0.1:1", Preempt()).code == "health.ollama_no_answer"
    assert ollama_start._wait_answer("http://127.0.0.1:1", Preempt(lambda: True)).code == "health.ollama_down"


def test_a_drop_tells_the_window_at_once_and_the_numbering_starts_at_1_again(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    assert b.screens[0].seq == 1 and b.entries
    told = len(posted)
    b.drop("another book")
    after = posted[told:]
    assert after[0] == ("backlog", {"pages": 0, "lines": 0, "paused": False, "dropped": True, "reading": True})
    assert after[-1] == ("backlog", {"pages": 0, "lines": 0, "paused": False, "dropped": 0, "reading": True})
    assert ("page_on_show", {"seq": None, "reading": True}) in after  # (between the two)
    assert sum(1 for k, d in after if k == "backlog" and d["dropped"] is True) == 1
    told = len(posted)
    b.drop("again")  # (nothing there: nothing told)
    assert posted[told:] == []
    _job(p, b, sample_page, _confirmed())
    assert b.screens[0].seq == 1 and _stages(posted[told:])[0] == ("read", "working")


def test_nothing_is_told_of_a_screen_dropped_and_none_is_caught(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    old = b.entries[0]
    b.drop("another book")
    told = len(posted)
    b.tell(old.screen, "translate", "done")  # (a step of the backlog that ended after the drop)
    b._finish(old, "translate", "done")
    b.show(old.screen)
    b.totals()
    assert posted[told:] == []
    assert not b.catch(old.screen, sample_page, None, p, 7) and not b.entries


def test_a_step_under_way_at_a_drop_tells_nothing_of_its_page(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())
    assert b.step(p) == "made"
    p.translator = Blocking(EN_TEXTS)
    out: list[str] = []
    thread = threading.Thread(target=lambda: out.append(b.step(p)), daemon=True)
    thread.start()
    assert p.translator.waiting.wait(10)
    b.drop("another book")
    told = len(posted)
    p.stop_warm()
    thread.join(5)
    assert out == ["stopped"] and not [d for k, d in posted[told:] if k == "page_stage"]


class Stopped(DictTranslator):
    """Answers the first line, then Stop (or the window's close): the page's cancel set, no turn."""

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                       on_slow=None):
        self.calls.append(list(texts))
        if on_item is not None and texts:
            on_item(0, self.mapping.get(texts[0], ""))
        cancel.set()
        raise Cancelled()


def test_a_page_job_stopped_without_a_turn_leaves_its_page_waiting_never_skipped(settings, sample_page):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Stopped(EN_TEXTS))
    _job(p, b, sample_page, _confirmed())
    stages = _stages(posted)
    assert stages[-1] == ("translate", "waiting") and ("translate", "skipped") not in stages
    assert not b.entries  # (not caught: Stop ends the page where it is; it is read or asked when shown again)


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


# ------------------------------------------------------------------ what was read behind the reader, taken again
def _watch_detect(p: Pipeline, monkeypatch) -> list:
    detected: list = []
    real = p._detect
    monkeypatch.setattr(p, "_detect", lambda rgb: (detected.append(1), real(rgb))[1])
    return detected


def _job_events(p: Pipeline, b: Backlog, image, gate):
    """`_job`, with the page's fill events kept (kind, data) in the order they came."""
    seen: list = []
    real = p.process

    def process(image, **k):
        k["events"] = lambda kind, data: seen.append((kind, data))
        return real(image, **k)

    p.process = process
    try:
        return (*_job(p, b, image, gate), seen)
    finally:
        del p.process


def test_a_page_shown_again_takes_what_its_job_had_read_and_reads_nothing(settings, sample_page, monkeypatch):
    posted, post = _events()
    b = Backlog(post)
    ocr = FakeOcr()
    p = _pipeline(settings, Turning(EN_TEXTS, answer=2), "Lent", ocr=ocr)
    _job(p, b, sample_page, _confirmed())
    entry = b.entries[0]
    assert entry.read and entry.size == sample_page.size and entry.sig and entry.kept_bytes > 0
    assert all(r.status != "translated" for _u, rs in entry.read.values() for r in rs)  # (as read: copies)
    stored = {cb.text for cb in p.cache.pages[0].bubbles}
    calls, detected = ocr.calls, _watch_detect(p, monkeypatch)
    p.translator = DictTranslator(EN_TEXTS)
    tracking, work, result, fill = _job_events(p, b, sample_page, _confirmed())
    assert tracking.reuse == "reused" and not detected and ocr.calls == calls  # (nothing found or read on the frame)
    page = p.cache.pages[0]
    asked = [t for call in p.translator.calls for t in call]
    assert not page.incomplete and len(asked) == len(page.bubbles) - len(stored)  # (only the rest asked)
    lettered = [d["text"] for k, d in fill if k == "translated" and d.get("text")]
    assert stored <= set(lettered)  # (the lines stored lettered at once, before what is asked)
    first_asked = next(i for i, (k, d) in enumerate(fill) if k == "translated" and d.get("text") not in stored)
    assert all(k != "regions" for k, _d in fill[first_asked:])
    assert result.translated and not result.error and result.image.size == sample_page.size
    assert not b.entries and b.bytes_held == 0 and b.lends == {"none": 1, "reused": 1}  # (the first: nothing held)


@pytest.mark.parametrize("from_frame", [False, True])
def test_a_page_the_backlog_finished_shown_again_is_read_nowhere_and_told_done_throughout(settings, sample_page,
                                                                                           monkeypatch, from_frame):
    # (turned back to a page the backlog read - from what its job had read, or from its frame - and translated: it is
    # lettered from the cache with the regions as the backlog had them, nothing found or read on the frame, and its
    # bar stays done. Before, the read was let go with the page done: the page job found and read it again - 3.4 s on
    # the processor -, its bar "reading" over a page shown translated)
    posted, post = _events()
    b = Backlog(post)
    if from_frame:
        p = _reading_job(settings, b, sample_page, "Done frame")
        _packed(b)
        p.translator = DictTranslator(EN_TEXTS)
    else:
        p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Done read")
        _job(p, b, sample_page, _confirmed())
        p.translator = DictTranslator(EN_TEXTS)
    _drain(p, b)
    assert not b.entries and _last(posted) == {"read": "done", "translate": "done"}
    assert not p.cache.pages[0].incomplete
    told = len(posted)
    calls, detected = p.ocr.calls, _watch_detect(p, monkeypatch)
    asked = len(p.translator.calls)
    tracking, work, result = _job(p, b, sample_page, _confirmed())
    assert tracking.reuse == "reused" and not detected and p.ocr.calls == calls and len(p.translator.calls) == asked
    assert not [d for k, d in posted[told:] if k == "page_stage" and d["state"] != "done"]
    assert result.translated and not result.error and b.bytes_held == 0
    tracking, work, result = _job(p, b, sample_page, _confirmed())  # (and every time it is shown)
    assert tracking.reuse == "reused" and not detected


def test_a_page_the_backlog_read_from_its_frame_is_not_read_again_when_shown(settings, sample_page, monkeypatch):
    posted, post = _events()
    b = Backlog(post)
    p = _reading_job(settings, b, sample_page, "LentFrame")
    _packed(b)
    assert b.step(p) == "read"  # (its read; its translation not yet)
    entry = b.entries[0]
    assert entry.read and entry.units and entry.frame is None and entry.found is None and b.frame_bytes == 0
    calls, detected = p.ocr.calls, _watch_detect(p, monkeypatch)
    tracking, work, result = _job(p, b, sample_page, _confirmed())
    assert tracking.reuse == "reused" and not detected and p.ocr.calls == calls
    assert not p.cache.pages[0].incomplete and result.translated and not b.entries


def test_a_page_turned_to_while_the_backlog_translates_it_shows_what_was_answered_and_asks_the_rest(
        settings, sample_page, monkeypatch):
    posted, post = _events()
    b = Backlog(post)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Turned to")
    _job(p, b, sample_page, _confirmed())
    assert b.step(p) == "made"
    p.translator = Blocking(EN_TEXTS)
    out: list[str] = []
    thread = threading.Thread(target=lambda: out.append(b.step(p)), daemon=True)
    thread.start()
    assert p.translator.waiting.wait(10)
    p.stop_warm()  # (the page turned to: its job comes)
    thread.join(5)
    assert out == ["stopped"]
    stored = {cb.text for cb in p.cache.pages[0].bubbles}
    detected = _watch_detect(p, monkeypatch)
    p.translator = DictTranslator(EN_TEXTS)
    tracking, work, result = _job(p, b, sample_page, _confirmed())
    asked = [t for call in p.translator.calls for t in call]
    assert tracking.reuse == "reused" and not detected
    assert len(asked) == len(p.cache.pages[0].bubbles) - len(stored) and not p.cache.pages[0].incomplete


class StopAt(FakeOcr):
    """Reads *n* regions, then the backlog's step is stopped (a page to read: `Pipeline.stop_warm`)."""

    def __init__(self, pipeline_of, n=1):
        super().__init__()
        self.pipeline_of, self.n, self.armed = pipeline_of, n, False

    def read(self, image):
        text = super().read(image)
        if self.armed and self.calls >= self.n:
            self.armed = False
            self.pipeline_of().stop_warm()
        return text


def test_a_read_stopped_by_a_turn_to_its_page_leaves_its_detection_to_the_page_job(settings, sample_page,
                                                                                   monkeypatch):
    posted, post = _events()
    b = Backlog(post)
    holder: dict = {}
    p = _reading_job(settings, b, sample_page, "Half read")
    ocr = StopAt(lambda: holder["p"], n=p.ocr.calls + 1)
    p.ocr = ocr
    holder["p"] = p
    _packed(b)
    ocr.calls = p.ocr.calls = 0
    ocr.n, ocr.armed = 1, True
    assert b.step(p) == "stopped"
    entry = b.entries[0]
    assert entry.found and entry.frame is not None and entry.read == {} and b.wait_stats()["n"] == 1
    detected = _watch_detect(p, monkeypatch)
    tracking, work, result = _job(p, b, sample_page, _confirmed())
    assert tracking.reuse == "partial" and not detected  # (its detection taken, the rest read)
    assert result.translated and not p.cache.pages[0].incomplete and not b.entries and b.bytes_held == 0


def test_a_page_shown_again_is_read_as_ever_at_another_size_or_once_a_setting_changed(settings, sample_page,
                                                                                      monkeypatch):
    for change, why in (("size", "size"), ("setting", "settings"), ("units", "units")):
        b = Backlog(_events()[1])
        p = _pipeline(settings, Turning(EN_TEXTS, answer=1), f"Again {change}")
        _job(p, b, sample_page, _confirmed())
        image = sample_page
        if change == "size":
            w, h = sample_page.size
            image = sample_page.crop((0, 0, w, h - 2))  # (the page, two pixel rows fewer: another capture size)
            b.entries[0].size = (w, h)
        elif change == "setting":
            p._base_settings.white_threshold -= 1
        else:
            b.entries[0].page_units[0].box = (1, 1, 2, 2)
        detected = _watch_detect(p, monkeypatch)
        p.translator = DictTranslator(EN_TEXTS)
        tracking, _work, result = _job(p, b, image, _confirmed())
        assert tracking.reuse == why and detected, change  # (read as ever)
    b = Backlog(_events()[1])
    p = _reading_job(settings, b, sample_page, "Still a frame")
    tracking, _work, _result = _job(p, b, sample_page, _confirmed())
    assert tracking.reuse == "frame"
    detected = _watch_detect(p, monkeypatch)
    tracking, _work, _result = _job(p, b, sample_page, _confirmed())
    assert tracking.reuse == "reused" and not detected  # (done on show: its read kept for this showing, `keep_done`)


def test_the_regions_kept_count_against_the_cap(settings, sample_page, monkeypatch):
    b = Backlog(_events()[1])
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), "Kept capped")
    monkeypatch.setattr(backlog_mod, "FRAME_CAP_MB", 1e-6)
    _job(p, b, sample_page, _confirmed())
    assert not b.entries  # (its regions as read would pass the cap: not caught, as a frame over it is not)


# ------------------------------------------------------------------ the backlog's own read, stopped, taken up
class ByCrop(FakeOcr):
    """Reads each region by what its crop holds (the same line for the same crop, in whatever order the regions are
    read), and stops the backlog's step at the next region read once *armed* (a turn: `Pipeline.stop_warm`)."""

    def __init__(self, pipeline_of=None):
        super().__init__()
        self.pipeline_of, self.armed = pipeline_of, False

    def read(self, image):
        self.calls += 1
        if self.armed:
            self.armed = False
            self.pipeline_of().stop_warm()
        digest = sum(np.asarray(image.convert("L"), dtype=np.int64).ravel()[::7]) + image.width * 31 + image.height
        return self.texts[int(digest) % len(self.texts)]


def _spread(right, left):
    from PIL import Image

    w, h = right.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(left, (0, 20))
    spread.paste(right, (w + 60, 20))
    return spread


def _as_read(units) -> list:
    """What a read gave of each page unit, as the backlog keeps it to translate: every region's place, text, state,
    order, room and the boxes it stands for."""
    return [(su.index, [(r.bbox, r.source_text, r.status, r.order, r.room, r.aliases) for r in su.regions])
            for su in units]


def _stopped_read(settings, b, image, book, after_unit=False, monkeypatch=None):
    """A page turned past while its job read it (caught as its frame), and the backlog's read of that frame stopped:
    at its first region (*after_unit*: at the first region after its first page unit was read)."""
    p = _reading_job(settings, b, image, book)
    _packed(b)
    ocr = ByCrop(lambda: p)
    p.ocr = ocr
    p._ocr_memo.clear()  # (the page job's readings, in its reader's order: read by the crop from now on)
    p._unanimous_memo.clear()
    if after_unit:
        real = p.share_rooms

        def share(regions, size):  # (`scan`: a page unit read, ordered and given its rooms)
            real(regions, size)
            ocr.armed = True

        monkeypatch.setattr(p, "share_rooms", share)
    else:
        ocr.armed = True
    assert b.step(p) == "stopped"
    if after_unit:
        monkeypatch.setattr(p, "share_rooms", real)
    return p, ocr


def _whole_read(settings, image, book) -> tuple[list, int]:
    """The same frame read once without a stop, by a pipeline of its own (the reference), and its regions read."""
    ocr = ByCrop()
    p = _pipeline(settings, DictTranslator(EN_TEXTS), book, ocr=ocr)
    scan = p.scan(image, skip_cached=True, cancel=threading.Event(), behind=True,
                  keep=SimpleNamespace(units=None, found=None, read={}, aliases={}))
    return _as_read(scan.units), ocr.calls


def test_a_read_of_the_backlogs_stopped_is_taken_up_where_it_stopped_not_begun_again(settings, sample_page,
                                                                                      monkeypatch):
    b = Backlog(_events()[1])
    p, ocr = _stopped_read(settings, b, sample_page, "Taken up")
    entry = b.entries[0]
    assert entry.found and entry.read == {} and entry.frame is not None and entry.kept_bytes > 0
    assert b.bytes_held == entry.held_bytes + entry.kept_bytes  # (counted against the cap with the frame)
    detected = _watch_detect(p, monkeypatch)
    assert b.step(p) == "read"
    assert not detected and b.resumes == {"resumed": 1}  # (its detection taken: nothing found again)
    assert entry.frame is None and entry.found is None and entry.aliases is None
    assert _as_read(entry.units) == _whole_read(settings, sample_page, "Taken up, the reference")[0]
    p.translator = DictTranslator(EN_TEXTS)
    assert _drain(p, b) == ["translate"] and not b.entries and b.bytes_held == 0
    assert entry.read is None and entry.found is None and entry.aliases is None  # (let go with the entry)


def test_a_spread_stopped_after_its_first_page_reads_only_the_second_and_a_second_stop_keeps_the_first(
        settings, sample_page, sample_page2, monkeypatch):
    spread = _spread(sample_page, sample_page2)
    b = Backlog(_events()[1])
    p, ocr = _stopped_read(settings, b, spread, "Spread taken up", after_unit=True, monkeypatch=monkeypatch)
    entry = b.entries[0]
    assert len(entry.page_units) == 2 and set(entry.read) == {0} and entry.found and set(entry.aliases) == {0}
    first = len(entry.read[0][1])
    ocr.armed = True  # (stopped again, at the first region of the resumed read: the second page's)
    assert b.step(p) == "stopped"
    assert set(entry.read) == {0} and len(entry.read[0][1]) == first and b.resumes == {"resumed": 1}
    detected = _watch_detect(p, monkeypatch)
    calls = ocr.calls
    assert b.step(p) == "read"
    reference, whole_calls = _whole_read(settings, spread, "Spread taken up, the reference")
    assert not detected and b.resumes == {"resumed": 2}
    assert 0 < ocr.calls - calls < whole_calls  # (the first page not read again)
    assert _as_read(entry.units) == reference


def test_a_stopped_read_is_begun_again_at_another_size_with_other_units_once_a_setting_changed_or_over_the_cap(
        settings, sample_page, monkeypatch):
    for change in ("size", "units", "settings", "cap"):
        b = Backlog(_events()[1])
        if change == "cap":  # (the frame caught; its read's regions would pass the cap with it: not kept)
            p = _reading_job(settings, b, sample_page, f"Begun again, {change}")
            _packed(b)
            ocr = ByCrop(lambda: p)
            p.ocr, ocr.armed = ocr, True
            with monkeypatch.context() as m:
                m.setattr(backlog_mod, "FRAME_CAP_MB", (b.bytes_held + 1) / backlog_mod.MB)
                assert b.step(p) == "stopped"
        else:
            p, ocr = _stopped_read(settings, b, sample_page, f"Begun again, {change}")
        entry = b.entries[0]
        if change == "size":
            w, h = entry.size
            entry.size = (w, h + 1)
        elif change == "units":
            entry.page_units[0].box = (1, 1, 2, 2)
        elif change == "settings":
            p._base_settings.white_threshold -= 1
        else:
            assert entry.found is None and entry.kept_bytes == 0
        detected = _watch_detect(p, monkeypatch)
        assert b.step(p) == "read" and detected, change  # (read from the start)
        assert b.resumes == ({} if change == "cap" else {change: 1}), change


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


# ------------------------------------------------------------------ the history
def test_the_history_is_the_order_of_work_the_pairs_of_one_growing_context(settings, sample_page):
    # (a history in story order was measured and taken out: docs/OFFLINE_VERIFICATION.md)
    b = Backlog(_events()[1])
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1), book="Behind, in the order of work")
    assert type(p._grown) is GrowingContext and not hasattr(backlog_mod, "HISTORY")
    _job(p, b, sample_page, _confirmed())
    p.translator = DictTranslator(EN_TEXTS)
    assert _drain(p, b) == ["made", "translate"]


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
