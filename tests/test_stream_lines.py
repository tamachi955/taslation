"""A page unit's lines sent to the translator as soon as they are read (`taslation.streaming.LineStream`), in the
window's page job: the requests that stand are those the request made after the reading would have made - the same
prompts (history, joined runs, the Japanese after a line, glossary and names) and draws -, and the page, its cache,
the pairs that only grow and the names are what that request leaves; the runs asked too soon are taken back (their
requests aside, nothing of them lasts and nothing of their lettering stays on show); nothing is asked before the frame
was seen on show; a page stopped while it is read puts back what its lines changed. A stand-in for PLaMo's server
that answers from the prompt; invented lines only."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from test_early_start_pipeline import _state

from taslation import pipeline as pipeline_mod
from taslation import streaming
from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.pipeline import PageGate, Pipeline
from taslation.regions import TextRegion
from taslation.translate.plamo import PlamoTranslator

NAME_LINE = "芦藤（あしふじ）が来た。"  # (a name with its reading: the book's names learn it from any answer)
TEXTS = [NAME_LINE, "芦藤さんはどこ？", "今日はいい天気だね", "ありがとう", "どこへ行くの", "大丈夫だよ", "まだ終わってない"]


class SlowOcr(FakeOcr):
    """`FakeOcr` that takes a while per crop, so that the first answers come while the unit is still read."""

    def __init__(self, texts=None, delay: float = 0.03):
        super().__init__(texts)
        self.delay = delay

    def read(self, image):
        time.sleep(self.delay)
        return super().read(image)


def english(source: str) -> str:
    return EN_TEXTS.get(source, f"Some words, {len(source)} of them.")


class Recorded(PlamoTranslator):
    """PLaMo with the server's answer made here: each request's prompt and draw kept (with the run of the stream it
    belongs to), an answer per bubble after *delay* seconds, cancelled as a request is."""

    def __init__(self, delay: float = 0.02):
        super().__init__(url="http://127.0.0.1:9", seed=None)
        self.delay = delay
        self.asked: list[tuple[str, int, int | None, float]] = []
        self.ensure_loaded = lambda cancel=None, on_slow=None: None  # type: ignore[method-assign]

    def _generate(self, prompt, max_tokens, offset=0, cancel=None, on_slow=None):
        token = streaming.current_token()
        end = time.monotonic() + self.delay
        while time.monotonic() < end:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            time.sleep(0.002)
        self.asked.append((prompt, offset, token, time.monotonic()))
        source = prompt.rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0]
        return "\n".join(english(part) for part in source.split("\n"))


def _pipeline(settings, book: str, texts=TEXTS, delay: float = 0.02) -> Pipeline:
    cache = CacheStore(settings.cache_dir).open(book, "plamo")
    return Pipeline(settings, ocr=SlowOcr(texts), translator=Recorded(delay), cache=cache)


def _read(p: Pipeline, page, streamed: bool, monkeypatch, gate=None, cancel=None):
    """*page* read as the window's page job reads it, its lines streamed or not: the events and the result."""
    monkeypatch.setattr(streaming, "STREAM_LINES", streamed)
    events: list[tuple[str, dict]] = []
    cancel = cancel or threading.Event()
    with p.page_on_show(gate):
        result = p.process(page.copy(), events=lambda kind, data: events.append((kind, dict(data))), cancel=cancel)
    return events, result


def _kept_requests(p: Pipeline) -> list[tuple[str, int]]:
    """The requests that count: those of runs not taken back."""
    gone = {t for log in p.stream_log for t in log["tokens_taken_back"]}
    return [(prompt, offset) for prompt, offset, token, _t in p.translator.asked if token not in gone]


def _page(result):
    from judge_order_check import fingerprint

    return fingerprint(result.regions), np.asarray(result.image).tobytes()


def _shown_early_at_end(events) -> list[int]:
    """The regions whose last lettering before the finished page came from the drafts layer."""
    last: dict[int, bool] = {}
    for kind, data in events:
        if kind == "translated":
            last[data["index"]] = bool(data.get("early")) and not data.get("early_end")
        elif kind == "page":
            break
    return [i for i, early in last.items() if early]


@pytest.fixture(autouse=True)
def _tools_path():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    yield


def test_streamed_lines_make_the_same_requests_and_leave_the_same_page(settings, sample_page, monkeypatch):
    a = _pipeline(settings, "Alone")
    events_a, result_a = _read(a, sample_page, False, monkeypatch)
    b = _pipeline(settings, "Streamed")
    events_b, result_b = _read(b, sample_page, True, monkeypatch)
    log = b.stream_log[-1]
    assert log["lines_sent_early"] > 0 and log["early_lettered"] > 0  # (the lines did leave before the unit was read)
    assert [x[:2] for x in a.translator.asked] == _kept_requests(b)
    assert _page(result_a) == _page(result_b)
    sa, sb = _state(a), _state(b)
    assert sa == sb and a.translator.draws() == b.translator.draws() and a.book_names.state() == b.book_names.state()
    assert NAME_LINE.split("（")[0] in b.book_names.held  # (a name was learnt: the glossary is in the prompts)
    assert _shown_early_at_end(events_b) == [] and log["early_left"] == 0
    assert log["final_from_taken_back"] == 0
    first_a = next(i for i, (k, _d) in enumerate(events_a) if k == "translated")
    first_b = next(i for i, (k, _d) in enumerate(events_b) if k == "translated")
    reads_before = lambda events, n: sum(1 for k, _d in events[:n] if k == "read")  # noqa: E731
    assert reads_before(events_b, first_b) < reads_before(events_a, first_a)  # (lettered before the reading ended)


def _reversed_order(self, rgb, unit_box, regions):
    """The final reading order unlike the order before the reading: the lines read as text the other way round."""
    text = [r for r in regions if r.status == "untranslated" and r.source_text]
    rest = [r for r in regions if not (r.status == "untranslated" and r.source_text)]
    regions[:] = text[::-1] + rest
    for i, r in enumerate(regions):
        r.order = i


def test_runs_asked_too_soon_are_taken_back_and_nothing_of_them_lasts(settings, sample_page, monkeypatch):
    monkeypatch.setattr(Pipeline, "_order_read", _reversed_order)
    a = _pipeline(settings, "Alone")
    _events_a, result_a = _read(a, sample_page, False, monkeypatch)
    b = _pipeline(settings, "Streamed")
    events_b, result_b = _read(b, sample_page, True, monkeypatch)
    log = b.stream_log[-1]
    assert log["runs_taken_back"] > 0 and log["first_taken_back"]
    # the requests that count are the request's own: history, glossary (the name learnt from a line taken back is
    # not in the prompts of the lines before it now) and draws put back
    assert [x[:2] for x in a.translator.asked] == _kept_requests(b)
    assert _page(result_a) == _page(result_b)
    assert _state(a) == _state(b) and a.translator.draws() == b.translator.draws()
    assert a.book_names.state() == b.book_names.state()
    # nothing of a line taken back on show once the page is finished, nor in what the page keeps
    assert _shown_early_at_end(events_b) == [] and log["early_left"] == 0 and log["final_from_taken_back"] == 0
    withdrawn = [d for k, d in events_b if k == "translated" and d.get("withdrawn")]
    assert withdrawn and all(d["text"] == "" or not d.get("early") or d.get("early_end") for d in withdrawn)


def test_a_line_the_book_already_translates_is_lettered_while_the_page_is_read(settings, sample_page, monkeypatch):
    # (read once: the book's lines learn the page's; read again, out of the cache, with two lines new)
    again = TEXTS[:3] + ["新しい台詞だ", "もう一つの台詞"] + TEXTS[5:]

    def twice(p: Pipeline, streamed: bool):
        _read(p, sample_page, streamed, monkeypatch)
        for page in list(p.cache.pages):
            p.cache.remove(page.fingerprint)
        p.shown_pages.clear()
        p.ocr = SlowOcr(again)
        p.translator.asked.clear()
        return _read(p, sample_page, streamed, monkeypatch)

    settings.reuse_lines = True  # (the default; the tests' settings turn it off)
    a = _pipeline(settings, "Served alone")
    events_a, result_a = twice(a, False)
    b = _pipeline(settings, "Served streamed")
    events_b, result_b = twice(b, True)
    served = {r.translated_text for r in result_b.regions if getattr(r, "reused_text", "")}
    assert served and 0 < len(a.translator.asked)  # (some lines reused, the new ones asked)
    assert [x[:2] for x in a.translator.asked] == _kept_requests(b)
    assert _page(result_a) == _page(result_b)
    early = {d["text"] for k, d in events_b if k == "translated" and d.get("early") and not d.get("early_end")}
    assert served and served <= early  # (the reused ones lettered on the drafts layer, asked nothing)
    log = b.stream_log[-1]
    assert log["early_withdrawn"] == 0 and log["early_left"] == 0 and _shown_early_at_end(events_b) == []


def test_a_page_stopped_while_it_is_read_puts_back_what_its_lines_changed(settings, sample_page, monkeypatch):
    p = _pipeline(settings, "Stopped", delay=0.01)

    def lasting():
        state = _state(p)
        return ([state[k] for k in ("pages", "lines", "context", "grown", "names")], p.translator.draws(),
                p.book_names.state())

    before = lasting()
    cancel = threading.Event()
    real = p._ocr_regions

    def stopped_late(*a, **k):  # (the stop comes as the reading ends: lines have been answered by then)
        out = real(*a, **k)
        time.sleep(0.2)
        cancel.set()
        return out

    monkeypatch.setattr(p, "_ocr_regions", stopped_late)
    with pytest.raises(Cancelled):
        _read(p, sample_page, True, monkeypatch, cancel=cancel)
    assert p.translator.asked  # (lines were asked while the page was read)
    assert lasting() == before
    assert p.stream_log[-1]["outcome"] == "stopped" and p.stream_log[-1]["why_taken_back"] == "stopped"


def test_nothing_is_asked_before_the_frame_was_seen_on_show(settings, sample_page, monkeypatch):
    p = _pipeline(settings, "Gate")
    gate = PageGate()
    out: dict = {}

    def job():
        try:
            out["result"] = _read(p, sample_page, True, monkeypatch, gate=gate)
        except BaseException as e:  # noqa: BLE001
            out["error"] = e

    thread = threading.Thread(target=job)
    thread.start()
    time.sleep(1.0)  # (read by now, its lines known)
    assert p.translator.asked == []
    seen = time.monotonic()
    gate.seen(seen)
    thread.join(30.0)
    assert "error" not in out and p.translator.asked and min(t for *_x, t in p.translator.asked) >= seen

    dropped = _pipeline(settings, "Dropped")
    gate = PageGate()
    out.clear()

    def job_dropped():
        try:
            _read(dropped, sample_page, True, monkeypatch, gate=gate)
        except BaseException as e:  # noqa: BLE001
            out["error"] = e

    thread = threading.Thread(target=job_dropped)
    thread.start()
    time.sleep(0.3)
    gate.drop()  # (the frame changed before a look found it on show)
    thread.join(30.0)
    assert isinstance(out.get("error"), Cancelled) and dropped.translator.asked == []


# --- which runs may leave (`LineStream._runs_known`), told region by region ---------------------------------------
def _region(text: str, row: int, col: int = 0) -> TextRegion:
    y0, x0 = 120 * row, 400 * col
    return TextRegion(x0, y0, x0 + 300, y0 + 100, np.full((100, 300), 255, np.uint8), (x0 + 50, y0 + 20, x0 + 250, y0 + 80),
                      status="untranslated", source_text=text)


class _Unit:
    index, box = 0, (0, 0, 800, 1200)


def _stream(settings, regions) -> streaming.LineStream:
    p = Pipeline(settings, ocr=None, translator=Recorded())
    stream = streaming.LineStream(p, _Unit(), regions, None, threading.Event(), None, True, None)
    stream._start = lambda: None  # (no sender: only what may leave is looked at)
    return stream


def _wanted(stream) -> list[tuple[str, ...]]:
    return [spec.lines for spec, _regions in stream.wanted]


def test_a_line_leaves_once_judged_and_an_open_line_waits_for_its_next_one(settings):
    regions = [_region("今日はいい天気だね", 0), _region("どこへ行く時は電車で", 1), _region("駅まで行くんだ", 2)]
    stream = _stream(settings, regions)
    stream.judged(regions[0])
    assert _wanted(stream) == [("今日はいい天気だね",)]
    stream.judged(regions[1])  # (ends open: whether it goes on depends on the next line)
    assert _wanted(stream) == [("今日はいい天気だね",)]
    stream.judged(regions[2])  # (near it: the two are one sentence, one request)
    assert _wanted(stream) == [("今日はいい天気だね",), ("どこへ行く時は電車で", "駅まで行くんだ")]


def test_a_model_candidate_not_judged_yet_holds_the_lines_after_it(settings):
    regions = [_region("ありがとう", 0), _region("大丈夫だよ", 1), _region("まだ終わってない", 2)]
    regions[1].from_model = True
    stream = _stream(settings, regions)
    stream.judged(regions[0])
    stream.judged(regions[2])
    assert _wanted(stream) == [("ありがとう",)]
    stream.judged(regions[1])
    assert _wanted(stream) == [("ありがとう",), ("大丈夫だよ",), ("まだ終わってない",)]


def test_a_full_joined_run_waits_for_the_line_after_it(settings):
    texts = ["それで", "あの時に", "駅で会った人が", "いい人だった"]  # (three that go on, then the fourth)
    regions = [_region(t, k) for k, t in enumerate(texts)]
    stream = _stream(settings, regions)
    for r in regions[:3]:
        stream.judged(r)
    assert _wanted(stream) == []  # (three joined, the third goes on: the line after it is their request's too)
    stream.judged(regions[3])
    wanted = stream.wanted
    assert [spec.lines for spec, _r in wanted][0] == tuple(texts[:3]) and wanted[0][0].follow == (texts[3],)


def test_a_request_under_way_is_cancelled_when_its_run_is_taken_back(settings):
    first, second = _region("ありがとう", 0), _region("大丈夫だよ", 1)
    p = Pipeline(settings, ocr=None, translator=Recorded(delay=1.0))
    stream = streaming.LineStream(p, _Unit(), [first, second], None, threading.Event(), None, True, None)
    try:
        stream.judged(second)  # (the classical candidate before it not read yet: no text so far)
        deadline = time.monotonic() + 2.0
        while stream.flight is None and time.monotonic() < deadline:
            time.sleep(0.005)
        gone = stream.flight
        assert gone is not None and gone.spec.lines == ("大丈夫だよ",)  # under way
        took_back = time.monotonic()
        stream.judged(first)  # (text after all, before it: the run sent no longer begins the lines)
        while not (gone.redo.is_set() and stream.flight is not gone) and time.monotonic() < deadline:
            time.sleep(0.002)
        assert stream.flight is not gone and time.monotonic() - took_back < 0.2  # (cancelled, not answered)
        while len(p.translator.asked) < 2 and time.monotonic() < took_back + 5.0:
            time.sleep(0.01)
    finally:
        stream.read_done()
        log = stream.close()
    assert not gone.done and gone in stream.taken_back and gone.token in log["tokens_taken_back"]
    assert all(token != gone.token for _p, _o, token, _t in p.translator.asked)  # (no answer of it came)
    # what was asked after the take-back: the lines in their order, the first from the session as it was at the start
    asked = [prompt.rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0] for prompt, *_x in p.translator.asked]
    assert asked[:2] == ["ありがとう", "大丈夫だよ"]
    assert p.translator.asked[0][0].count("<|plamo:msg|>") == p.translator.asked[1][0].count("<|plamo:msg|>") - 2


def test_a_line_read_later_before_the_ones_sent_takes_them_back(settings):
    regions = [_region("ありがとう", 0), _region("大丈夫だよ", 1), _region("まだ終わってない", 2)]
    stream = _stream(settings, regions)
    stream.judged(regions[0])
    stream.judged(regions[2])
    sent = [streaming._Sent(spec, rs, stream.session.mark(), False) for spec, rs in stream.wanted]
    stream.sent.extend(sent)
    stream.judged(regions[1])  # (a classical candidate before the second one sent: text after all)
    assert stream.back_to == 1 and sent[1].redo.is_set() and not sent[0].redo.is_set()
    with stream.lock:
        stream._apply_back()
    assert stream.sent == sent[:1] and stream.taken_back == sent[1:]


def test_a_unit_that_asks_nothing_after_all_takes_back_every_run_sent_and_says_why(settings):
    regions = [_region("ありがとう", 0), _region("大丈夫だよ", 1)]
    stream = _stream(settings, regions)
    for r in regions:
        stream.judged(r)
    sent = [streaming._Sent(spec, rs, stream.session.mark(), False) for spec, rs in stream.wanted]
    stream.sent.extend(sent)
    stream.discard("every line reused")
    log = stream.close()
    assert stream.sent == [] and stream.taken_back == sent and log["outcome"] == "discarded"
    assert log["runs_taken_back"] == 2 and log["first_taken_back"]
    assert log["why_taken_back"] == "nothing asked: every line reused"
