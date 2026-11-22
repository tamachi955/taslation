"""The beginning of the next page's first request computed while the reader reads (`PlamoTranslator.warm_prefix`,
`Pipeline.warm_soon`, the window's `_warm_when_idle`): only when the server does not hold it in any of the prompts it
may hold (the last ones, a cancelled one's too; none after a load), in steps that each
extend the one before and end where a prompt's element ends, the very options a request sends and one token asked
for, nothing drawn and nothing kept, so that the next request is what it is without it and begins with the last step;
nothing for a model not wholly on the GPU or not loaded; ended between two steps by the next page, by any request, by
a release (which waits for the step under way); never while a page job's changes are held, a job or a run runs, or a
request waits. Against a stand-in Ollama; invented lines only."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from helpers import FakeOcr
from test_plamo import generates, stub  # noqa: F401 - the stand-in Ollama and its fixture

from taslation.messages import Cancelled
from taslation.pipeline import Pipeline
from taslation.translate.base import CONTEXT_CUT_TO, GrowingContext, SentPair
from taslation.translate.plamo import (HELD_KEPT, NUM_CTX, STOPS, WARM_LEAST, WARM_STEP, PlamoTranslator,
                                       common_length, pfml_ends, pfml_prompt, tokens_about, warm_steps)
from taslation.ui import jobs

PAIRS = [(f"これは{i}番目の台詞です。", f"This is line number {i}.") for i in range(40)]


# ------------------------------------------------------------------ the beginning and its steps
def test_the_ends_are_the_prompts_beginning_element_by_element():
    ends = pfml_ends("en", "premises", PAIRS)
    assert len(ends) == len(PAIRS) + 1
    assert all(b.startswith(a) and len(b) > len(a) for a, b in zip(ends, ends[1:]))
    for source in ("一", "二\n三"):
        assert pfml_prompt(source, "en", "premises", PAIRS, [("魔導書", "grimoire")]).startswith(ends[-1])
    assert pfml_ends("en", "", [])[0] == pfml_prompt("一", "en").split("<|plamo:tag|>input")[0]
    assert common_length("abcdef", "abcxyz") == 3 and common_length("", "a") == 0 and common_length("ab", "ab") == 2


@pytest.mark.parametrize("held", [0, 1, 700, -1])
def test_the_steps_extend_each_other_and_end_on_an_element(held):
    ends = pfml_ends("en", "premises", PAIRS)
    held = len(ends[-1]) if held == -1 else held
    steps = warm_steps(ends, held)
    if held >= len(ends[-1]):
        assert steps == []
        return
    assert steps[-1] == ends[-1] and all(s in ends for s in steps)
    at = held
    for step in steps:
        assert len(step) > at
        single = next(e for e in ends if len(e) > at)  # (an element longer than a step goes whole)
        assert tokens_about(step[at:]) <= WARM_STEP or step == single
        at = len(step)


# ------------------------------------------------------------------ the pairs it starts from
def test_peek_is_what_take_gives_and_changes_nothing():
    grown = GrowingContext()
    grown.extend(PAIRS[:30])
    assert grown.peek() == list(PAIRS[:30]) and len(grown) == 30
    grown.extend(PAIRS + PAIRS[:5])  # past 60: the next take cuts them back
    assert len(grown) == 75
    peeked = grown.peek()
    assert len(peeked) == CONTEXT_CUT_TO and len(grown) == 75 and grown.cuts == 0
    assert grown.take() == peeked and len(grown) == CONTEXT_CUT_TO and grown.cuts == 1
    fits = lambda pairs: len(pairs) <= 8  # noqa: E731 - (a request that would not fit after more)
    assert grown.peek(fits) == list(grown)[-5:] and grown.cuts == 1


# ------------------------------------------------------------------ the translator
def _loaded(server, url, **kw):
    tr = PlamoTranslator(url, **kw)
    tr.translate_page(["一"])  # (the model loaded, a request made)
    tr.gpu_share = lambda model=None: 1.0 if server.loaded else None  # (/api/ps as Ollama says it: wholly on the GPU)
    server.requests.clear()
    return tr


def test_a_warming_computes_the_next_requests_beginning_in_steps(stub):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url, seed=7)
    facts = tr.warm_prefix("premises", PAIRS)
    steps = generates(server)
    assert facts["why"] == "" and facts["steps"] == len(steps) > 1 and facts["left"] >= WARM_LEAST
    head = pfml_ends("en", "premises", PAIRS)[-1]
    assert steps[-1]["prompt"] == head
    for a, b in zip(steps, steps[1:]):
        assert b["prompt"].startswith(a["prompt"])
    for s in steps:  # a request's options, one token asked for, raw and in one piece
        assert s["raw"] is True and s["stream"] is False and s["keep_alive"] == "5m"
        assert s["options"]["num_predict"] == 1 and s["options"]["num_ctx"] == NUM_CTX
        assert s["options"]["stop"] == list(STOPS) and s["options"]["seed"] == 7
    assert [r for r in server.requests if not r.get("prompt")] == []  # (nothing loaded for it)
    tr.translate_page(["二"], PAIRS, notes="premises")
    request = generates(server)[-1]
    assert request["prompt"].startswith(head)
    # ... and the very request a translator that never warmed sends
    other = _loaded(server, url, seed=7)
    other.translate_page(["二"], PAIRS, notes="premises")
    alone = generates(server)[-1]
    assert alone["prompt"] == request["prompt"] and alone["options"] == request["options"]


def test_a_warming_sends_nothing_while_the_server_holds_the_beginning(stub):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)
    computed: list = []
    tr.translate_page(["二"], PAIRS, computed=computed)
    server.requests.clear()
    facts = tr.warm_prefix("", [*PAIRS, *computed])  # (the next page starts from what the last request computed)
    assert facts["why"] == "held" and facts["left"] < WARM_LEAST and server.requests == []
    facts = tr.warm_prefix("", [*PAIRS[-CONTEXT_CUT_TO:], *computed])  # cut back: its beginning is new
    assert facts["why"] == "" and facts["steps"] >= 1


@pytest.mark.parametrize("loaded, share, why", [(False, None, "not loaded"), (True, 0.5, "not on the GPU")])
def test_nothing_is_warmed_for_a_model_not_wholly_on_the_gpu(stub, monkeypatch, loaded, share, why):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)
    server.loaded = loaded
    monkeypatch.setattr(tr, "gpu_share", lambda model=None: share)
    assert tr.warm_prefix("", PAIRS)["why"] == why and generates(server) == []


def test_a_keep_alive_that_unloads_at_once_warms_nothing(stub):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url, keep_alive="0")
    assert tr.warm_prefix("", PAIRS)["why"] == "keep_alive" and server.requests == []


def test_stop_and_any_request_end_the_warming_between_steps(stub):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)
    stop = threading.Event()
    stop.set()
    assert tr.warm_prefix("", PAIRS, stop)["why"] == "stopped" and generates(server) == []
    step = tr._warm_step
    stop = threading.Event()

    def one(prompt):
        out = step(prompt)
        stop.set()  # (the next page came while this step was under way)
        return out

    tr._warm_step = one
    facts = tr.warm_prefix("", PAIRS, stop)
    assert facts["why"] == "stopped" and facts["steps"] == 1 and len(generates(server)) == 1
    del tr._warm_step
    halt = tr._warm_halt = threading.Event()
    tr.translate_page(["三"])  # a request of the translator's ends any warming
    assert halt.is_set()


def test_a_step_that_fails_ends_the_warming_and_forgets_what_the_server_holds(stub, monkeypatch):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)
    assert tr._holds
    monkeypatch.setattr(tr, "_request_once", lambda *a, **k: (_ for _ in ()).throw(OSError("gone"))
                        if a and a[0] == "/api/generate" else {"models": [{"name": tr.model, "size": 1, "size_vram": 1}]})
    facts = tr.warm_prefix("", PAIRS)
    assert facts["why"].startswith("failed") and tr._holds == []


def test_what_the_server_may_hold_is_the_last_prompts_each_grown_in_place(stub):  # noqa: F811
    server, url = stub
    tr = PlamoTranslator(url)
    tr._held_now("ab|x", "ab")
    tr._held_now("ab|xcd|y", "ab|xcd")  # (it extends the last one: the server's prompt grew)
    assert tr._holds == [("ab|xcd", "ab|xcd|y")]
    tr._held_now("zz|w", "zz")  # (another beginning: beside it)
    assert [p for p, _s in tr._holds] == ["ab|xcd", "zz"]
    assert tr.held_of("ab|xcd|y and more") == len("ab|xcd|y") and tr.held_of("zz|") == 3 and tr.held_of("q") == 0
    for k in range(HELD_KEPT + 3):
        tr._held_now(f"{k}-", f"{k}-")
    assert len(tr._holds) == HELD_KEPT and tr.held_of("ab|xcd") == 0  # (the oldest went first)
    tr._held_now(None)
    assert tr._holds == []


def test_a_beginning_the_server_holds_before_a_request_of_another_history_is_not_warmed(stub):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)
    computed: list = []
    tr.translate_page(["二"], PAIRS, computed=computed)
    tr.translate_aside("三", PAIRS[:3])  # (a request with a history of its own came after it)
    server.requests.clear()
    facts = tr.warm_prefix("", [*PAIRS, *computed])
    assert facts["why"] == "held" and server.requests == []


def test_a_cancelled_requests_prompt_counts_as_held_and_a_load_holds_nothing(stub, monkeypatch):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)

    def cancelled(*a, **k):
        raise Cancelled()

    monkeypatch.setattr(tr, "_stream", cancelled)  # (the reader turned while the line was asked)
    with pytest.raises(Cancelled):
        tr.translate_page(["二"], PAIRS, cancel=threading.Event())
    monkeypatch.undo()
    server.requests.clear()
    assert tr.warm_prefix("", PAIRS)["why"] == "held" and server.requests == []  # (the server computed that prompt)
    tr.warm_up()  # a load: nothing of the translator's is held
    server.requests.clear()
    tr.gpu_share = lambda model=None: 1.0
    facts = tr.warm_prefix("", PAIRS)
    assert facts["why"] == "" and facts["steps"] >= 1


def test_the_draws_and_the_pairs_stay_as_they_were(stub):  # noqa: F811
    server, url = stub
    tr = _loaded(server, url)
    draws = tr.draws()
    tr.warm_prefix("", PAIRS)
    assert tr.draws() == draws


# ------------------------------------------------------------------ the pipeline
class Warming:
    """A translator that grows its pairs and warms (records what it is given; *hold* keeps a step under way)."""

    name = "plamo"
    grows_context = True

    def __init__(self, hold: threading.Event | None = None):
        self.calls: list[tuple[str, list, threading.Event]] = []
        self.hold = hold

    def context_fits(self, pairs, notes=""):
        return True

    def warm_prefix(self, notes, pairs, stop=None):
        self.calls.append((notes, list(pairs), stop))
        if self.hold is not None:
            self.hold.wait(5)
        return {"why": "", "steps": 1}

    def translate_page(self, texts, context=(), notes="", **kw):
        return [f"EN {t}" for t in texts]


def _joined(pipeline: Pipeline) -> None:
    thread = pipeline._warm_thread
    if thread is not None:
        thread.join(5)


def test_the_pipeline_warms_the_pairs_the_next_page_takes(settings):
    tr = Warming()
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    pipeline._grown.extend([SentPair(a, b) for a, b in PAIRS + PAIRS[:25]])  # (past 60: the next page cuts them back)
    assert pipeline.warm_soon()
    _joined(pipeline)
    (notes, pairs, stop), = tr.calls
    assert notes == str(pipeline.premises()) and pairs == pipeline._grown.peek() and len(pairs) == CONTEXT_CUT_TO
    assert len(pipeline._grown) == 65 and pipeline._grown.cuts == 0  # (nothing changed: the page cuts them itself)
    assert pipeline.warm_facts == {"why": "", "steps": 1} and not stop.is_set()
    assert pipeline.context_pairs() == pairs


def test_one_warming_at_a_time_and_none_while_a_page_is_held(settings):
    hold = threading.Event()
    tr = Warming(hold)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    assert pipeline.warm_soon() and not pipeline.warm_soon()  # (one under way)
    hold.set()
    _joined(pipeline)
    pipeline._provisional = object()  # a page job's changes held (`Provisional`)
    assert not pipeline.warm_soon()
    pipeline._provisional = None
    pipeline._kept_open = object()
    assert not pipeline.warm_soon()
    pipeline._kept_open = None
    assert Pipeline(settings, ocr=FakeOcr(), translator=SimpleNamespace(name="x")).warm_soon() is False


def test_a_page_and_a_release_stop_the_warming_and_the_release_waits_for_its_step(settings, monkeypatch):
    hold = threading.Event()
    tr = Warming(hold)
    released: list[bool] = []
    tr.release = lambda: released.append(pipeline._warm_thread.is_alive())
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    pipeline.warm_soon()
    stop = tr.calls[0][2] if tr.calls else None
    for _ in range(100):
        if tr.calls:
            break
        time.sleep(0.01)
    stop = tr.calls[0][2]
    from PIL import Image

    pipeline.process(Image.new("RGB", (40, 30), "white"), use_cache=False, translate=False)
    assert stop.is_set()  # a page: no more steps
    threading.Timer(0.2, hold.set).start()
    pipeline.release_translator()
    assert released == [False]  # (its step answered before the model went)


# ------------------------------------------------------------------ the window
class Idle:
    _warm_when_idle = jobs.JobsMixin._warm_when_idle

    def __init__(self):
        import queue

        self.ready, self.busy, self._queued = True, False, None
        self._jobs = queue.Queue()
        self.warmed = 0
        self.pipeline = SimpleNamespace(warm_soon=self.warm, stop_warm=self.stop)
        self.stops = 0

    def warm(self):
        self.warmed += 1
        return True

    def stop(self, wait=False):
        self.stops += 1


@pytest.mark.parametrize("busy", ["", "busy", "_queued", "job", "not ready", "no pipeline"])
def test_the_window_warms_only_while_nothing_of_it_runs(busy):
    w = Idle()
    if busy == "busy":
        w.busy = True
    elif busy == "_queued":
        w._queued = ("auto",)
    elif busy == "job":
        w._jobs.put(lambda: None)
    elif busy == "not ready":
        w.ready = False
    elif busy == "no pipeline":
        w.pipeline = None
    w._warm_when_idle()
    assert w.warmed == (1 if busy == "" else 0)


def test_the_worker_stops_the_warming_before_any_job():
    w = Idle()
    w.pipeline.kept_open_left = lambda: None
    w.pipeline.decide_kept = lambda: None
    w._jobs.put(lambda: None)
    assert callable(jobs.next_job(w)) and w.stops == 1
