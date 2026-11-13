"""Lines a reply left without a usable translation are asked for again, a few consecutive ones at a time with their
neighbours as context, then each on its own (`taslation.translate.base.ask_for_missing`); a reply that is almost JSON is
repaired rather than thrown away (`taslation.translate.ollama.parse_translations`); a line of punctuation
alone is its own translation. Through the fake Ollama for the live page and the whole-book batch: every failure
kind a reply can have, a line the model never translates, a Stop while a line is asked for again."""
from __future__ import annotations

import json
import threading
import time

import pytest
from fake_ollama import FakeOllama
from helpers import EN_TEXTS, JA_TEXTS, FakeOcr, read_book
from test_batch import _fake_viewer

from taslation import netguard
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.messages import Cancelled, Message
from taslation.pipeline import Pipeline, is_real_translation
from taslation.translate import OllamaTranslator, TranslationError
from taslation.translate.base import ask_for_missing, reask_groups, worth_asking_again
from taslation.translate.ollama import drop_trailing_commas, parse_translations


# ------------------------------------------------------------------------------------------- ask_for_missing itself
class Scripted:
    """A translator whose answers a function gives: answer(texts, call number) -> translations."""

    name = "scripted"

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[dict] = []

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
        self.calls.append({"texts": list(texts), "context": list(context), "notes": notes,
                           "upcoming": list(upcoming), "meta": meta})
        return self.answer(list(texts), len(self.calls))


SOURCES = [f"行{i}です" for i in range(12)]


def english(t: str) -> str:
    return "Line " + t[1:-2]


def usable_for(texts):
    return lambda i, text: bool(text) and is_real_translation(texts[i], text)


def test_groups_are_runs_of_consecutive_lines_cut_to_size():
    assert reask_groups([1, 2, 3, 4, 5, 9, 11, 12], 4) == [[1, 2, 3, 4], [5], [9], [11, 12]]
    assert reask_groups([0, 2, 4], 4) == [[0], [2], [4]]
    assert reask_groups([3, 4, 5], 1) == [[3], [4], [5]]
    assert reask_groups([], 4) == []


def test_only_the_missing_lines_are_asked_for_with_their_neighbours():
    outputs = [english(t) for t in SOURCES]
    for i in (1, 2, 3, 4, 5, 9):
        outputs[i] = ""
    outputs[7] = SOURCES[7]  # the Japanese copied: not usable either
    tr = Scripted(lambda texts, _n: [english(t) for t in texts])
    got = ask_for_missing(tr, SOURCES, outputs, usable_for(SOURCES), context=[("前", "Before")], notes="NOTES",
                    upcoming=["次"], meta=[{"speaker": "Saku"} if i == 9 else {} for i in range(12)], before=3, after=2)
    assert got.texts == [english(t) for t in SOURCES]
    assert [c["texts"] for c in tr.calls] == [SOURCES[1:5], [SOURCES[5]], [SOURCES[7]], [SOURCES[9]]]
    assert (got.requests, got.asked, got.filled, got.failed, got.stopped) == (4, 7, 7, 0, False)
    first, last = tr.calls[0], tr.calls[-1]
    assert first["context"] == [("前", "Before"), (SOURCES[0], english(SOURCES[0]))]  # what came before: all there is
    assert first["upcoming"] == SOURCES[5:7] and first["notes"] == "NOTES" and first["meta"] is None
    # the translated lines just before (those filled a moment ago included), the lines after, then what follows
    assert last["context"] == [(SOURCES[j], english(SOURCES[j])) for j in (6, 7, 8)]
    assert last["upcoming"] == [SOURCES[10], SOURCES[11]] and last["meta"] == [{"speaker": "Saku"}]
    assert ask_for_missing(tr, SOURCES, got.texts, usable_for(SOURCES)).requests == 0  # nothing missing: nothing asked


def test_a_line_still_missing_after_its_group_is_asked_alone_and_then_left():
    outputs = [english(t) for t in SOURCES]
    outputs[2] = outputs[3] = outputs[8] = ""

    def answer(texts, _n):
        # line 3 is never answered; line 8 only when it is asked alone
        return ["" if t == SOURCES[3] or (t == SOURCES[8] and len(texts) > 1) else english(t) for t in texts]

    tr = Scripted(answer)
    got = ask_for_missing(tr, SOURCES, outputs, usable_for(SOURCES))
    assert [c["texts"] for c in tr.calls] == [SOURCES[2:4], [SOURCES[8]], [SOURCES[3]]]
    assert got.texts[2] == english(SOURCES[2]) and got.texts[8] == english(SOURCES[8]) and got.texts[3] == ""
    assert got.filled == 2 and got.requests == 3  # line 3 asked twice (in its group, then alone), line 8 once


def test_failures_are_handed_over_and_can_stop_the_asking():
    outputs = [english(t) for t in SOURCES]
    for i in (0, 4, 8):
        outputs[i] = ""
    seen: list[TranslationError] = []

    def boom(texts, n):
        if n == 1:
            raise TranslationError(Message("ollama.http_error", status=500, path="/api/chat", detail="runner died"))
        return [english(t) for t in texts]

    got = ask_for_missing(Scripted(boom), SOURCES, outputs, usable_for(SOURCES),
                          on_error=lambda e: seen.append(e) or True)
    assert len(seen) == 1 and got.failed == 1 and not got.stopped
    assert all(got.texts)  # line 0 failed in round one and was asked again alone in round two
    stopped = ask_for_missing(Scripted(boom), SOURCES, outputs, usable_for(SOURCES), on_error=lambda e: False)
    assert stopped.stopped and stopped.requests == 1 and stopped.texts == outputs
    alone = ask_for_missing(Scripted(boom), SOURCES, outputs, usable_for(SOURCES))
    assert alone.stopped  # no handler: the first failure stops it


def test_a_reply_with_nothing_usable_is_an_answer_not_a_failure():
    outputs = [english(t) for t in SOURCES]
    outputs[2] = outputs[3] = outputs[9] = ""

    def nothing(texts, _n):
        if SOURCES[3] in texts or SOURCES[9] in texts:  # every line left empty: the client calls that a bad answer
            raise TranslationError(Message("ollama.bad_answer", chars=40))
        return [english(t) for t in texts]

    tr = Scripted(nothing)
    got = ask_for_missing(tr, SOURCES, outputs, usable_for(SOURCES), on_error=lambda e: pytest.fail("not a failure"))
    assert got.failed == 0 and not got.stopped and got.texts[2] == english(SOURCES[2])
    assert got.texts[3] == got.texts[9] == ""
    # lines 2-3 together, line 9 alone (answered: not asked again), then 2 and 3 each alone (3 answers nothing)
    assert [c["texts"] for c in tr.calls] == [SOURCES[2:4], [SOURCES[9]], [SOURCES[2]], [SOURCES[3]]]


def test_a_cancel_stops_before_the_next_request():
    outputs = [""] * len(SOURCES)
    cancel = threading.Event()

    def answer(texts, _n):
        cancel.set()  # Stop pressed while the first group was asked for
        return [english(t) for t in texts]

    tr = Scripted(answer)
    with pytest.raises(Cancelled):
        ask_for_missing(tr, SOURCES, outputs, usable_for(SOURCES), cancel=cancel)
    assert len(tr.calls) == 1


def test_items_handed_over_while_written_go_to_their_lines():
    outputs = [english(t) for t in SOURCES]
    outputs[6] = outputs[7] = ""

    class Streaming(Scripted):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None):
            out = super().translate_page(texts, context, notes, upcoming, meta)
            for k, t in enumerate(out):
                on_item(k, t)
            return out

    seen: list[tuple[int, str]] = []
    ask_for_missing(Streaming(lambda texts, _n: [english(t) for t in texts]), SOURCES, outputs, usable_for(SOURCES),
              on_item=lambda i, t: seen.append((i, t)))
    assert seen == [(6, english(SOURCES[6])), (7, english(SOURCES[7]))]


def test_which_failures_are_worth_asking_again_after():
    assert worth_asking_again(Message("ollama.bad_answer", chars=10))
    assert worth_asking_again(TranslationError(Message("ollama.http_error", status=500, path="/api/chat", detail="x")))
    assert not worth_asking_again(Message("ollama.timeout", seconds=900.0))
    assert not worth_asking_again(Message("ollama.unreachable", url="http://127.0.0.1:11434"))
    assert not worth_asking_again(TranslationError("cannot reach Ollama (test)"))


# ------------------------------------------------------------------------------- the copy check, the replies
def test_a_line_of_punctuation_alone_is_its_own_translation():
    assert is_real_translation("……", "……") and is_real_translation("！？", "！？")
    assert is_real_translation("!?", "!?")
    assert is_real_translation("……", "...") and is_real_translation("OK", "OK")
    assert not is_real_translation("こんにちは", "こんにちは") and not is_real_translation("東京", "東京")
    assert is_real_translation("・・・", "・・・") and is_real_translation("こんにちは", "・・・")  # dots, no kana
    assert is_real_translation("ーー", "ーー") and is_real_translation("こんにちは", "ｰ") and is_real_translation("あ", "…･")
    assert not is_real_translation("コーヒー", "コーヒー") and not is_real_translation("こんにちは", "コーヒー")
    assert not is_real_translation("", "")


@pytest.mark.parametrize("content", [
    '{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"},]}',  # trailing comma
    '{"translations": [{"id": 1, "text": "Hello",}, {"id": 2, "text": "Bye"}]}',
    '{"result": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]}',  # the list under another name
    '{"data": {"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]}}',  # one level down
    '{"translations": {"1": "Hello", "2": "Bye"}}',  # numbered keys under "translations"
    '{"translations": [{"1": "Hello"}, {"2": "Bye"}]}',  # an object per number
    '{"1": {"text": "Hello"}, "2": {"text": "Bye"}}',
    '{"translations": [{"id": 0, "text": "Hello"}, {"id": 1, "text": "Bye"}]}',  # numbered from 0
    '{"translations": [{"id": 41, "text": "Hello"}, {"id": 42, "text": "Bye"}]}',  # numbered on from the context
    'Here is {the} JSON: {"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]} (and {more})',
    '{"id": 1, "text": "Hello"}\n{"id": 2, "text": "Bye"}',  # one object per line
    '{"translations": [{"id": 1, "english": "Hello"}, {"id": 2, "line": "Bye"}]}',  # the text under another key
    '{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]',  # the closing brace missing
    '```json\n{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"},]}\n```',
])
def test_near_miss_replies_are_repaired(content):
    assert parse_translations(content, 2) == ["Hello", "Bye"]


def test_ids_that_do_not_fit_leave_the_line_to_be_asked_again():
    dup = '{"translations": [{"id": 1, "text": "A"}, {"id": 2, "text": "B"}, {"id": 2, "text": "C"}]}'
    assert parse_translations(dup, 3) == ["A", "B", ""]  # the first of a repeated id has it; line 3 is missing
    gap = '{"translations": [{"id": 1, "text": "A"}, {"id": 3, "text": "C"}, {"id": 9, "text": "X"}]}'
    assert parse_translations(gap, 3) == ["A", "", "C"]
    assert parse_translations('{"translations": [{"id": 1, "ja": "x"}, {"id": 2, "jp": "y"}]}', 2) == ["", ""]


def test_a_reply_cut_off_keeps_every_item_before_the_cut():
    cut = ('{"translations": [{"id": 1, "text": "Hello", "note": "a pun"}, {"id": 2, "text": "She said \\"go\\""}, '
           '{"id": 3, "text": "No way, no w')
    assert parse_translations(cut, 3) == ["Hello", 'She said "go"', ""]


def test_commas_are_dropped_only_outside_strings():
    assert drop_trailing_commas('[1, 2,]') == "[1, 2]" and drop_trailing_commas('{"a": "x,]",}') == '{"a": "x,]"}'


# ------------------------------------------------------------------------------------ through the fake Ollama
@pytest.fixture
def server():
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)  # nothing but the fake may be reached
        try:
            yield fake
        finally:
            netguard.uninstall()


def _english(items):
    return [{"id": it["id"], "text": EN_TEXTS.get(it["ja"], "Line " + str(it["id"]))} for it in items]


def _reply(rows) -> str:
    return json.dumps({"translations": rows})


def _translations(payload) -> bool:
    """Whether a request to the fake is one for translations (not a warm-up)."""
    return "Bubbles to translate:" in payload["messages"][-1]["content"]


def _defective(kind: str, items):
    """The first reply for a page of six lines, with the defect *kind*."""
    rows = _english(items)
    if kind == "missing_id":
        return _reply(rows[:2] + rows[3:])
    if kind == "wrong_count":
        return _reply(rows[:4])
    if kind == "duplicate_id":
        return _reply(rows[:3] + [{**rows[3], "id": 3}] + rows[4:])
    if kind == "zero_based":
        return _reply([{**r, "id": r["id"] - 1} for r in rows])
    if kind == "empty_text":
        return _reply([{**r, "text": ""} if r["id"] == 2 else r for r in rows])
    if kind == "copied":
        return _reply([{**r, "text": items[1]["ja"]} if r["id"] == 2 else r for r in rows])
    if kind == "kana":
        return _reply([{**r, "text": r["text"] + " (" + items[1]["ja"] + ")"} if r["id"] == 2 else r for r in rows])
    if kind == "not_json":
        return "I am sorry, here is my best attempt at the lines you sent."
    if kind == "cut_off":
        return _reply(rows)[: _reply(rows).index('{"id": 4')] + '{"id": 4, "text": "It\'s fi'
    if kind == "prefix_trailing_comma":
        return "Sure! " + _reply(rows)[:-2] + ",]}"
    if kind == "http_500":
        return (500, {"error": "llama runner process has terminated"})
    raise AssertionError(kind)


# kind -> translation requests for the page: the first one, then the lines asked for again
KINDS = {"missing_id": 2, "wrong_count": 2, "duplicate_id": 2, "zero_based": 1, "empty_text": 2, "copied": 2,
         "kana": 2, "not_json": 3, "cut_off": 2, "prefix_trailing_comma": 1, "http_500": 3}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_a_live_page_is_complete_whatever_the_first_reply_got_wrong(server, sample_page, settings, kind):
    first: list[bool] = []

    def answer(items, payload):
        if not _translations(payload):
            return None
        if not first:
            first.append(True)
            if kind == "cut_off":
                server.done_reason = "length"
            return _defective(kind, items)
        server.done_reason = "stop"
        return _reply(_english(items))

    server.answer = answer
    cache = CacheStore(settings.cache_dir).open(f"Defect {kind}", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=OllamaTranslator(server.url, timeout=10), cache=cache)
    result = pipeline.process(sample_page, cancel=threading.Event())
    translated = [r for r in result.regions if r.status == "translated"]
    assert len(translated) == 6 and {r.translated_text for r in translated} == set(EN_TEXTS.values())
    assert not result.error and len(cache) == 1 and cache.bubble_count == 6  # complete, so cached
    assert sum(1 for p in server.requests if _translations(p)) == KINDS[kind]


def test_a_line_the_model_never_translates_is_asked_alone_once_then_left(server, sample_page, settings):
    never = JA_TEXTS[3]

    def answer(items, payload):
        if not _translations(payload):
            return None
        return _reply([{"id": it["id"], "text": it["ja"]} if it["ja"] == never else r
                       for it, r in zip(items, _english(items))])

    server.answer = answer
    cache = CacheStore(settings.cache_dir).open("Never", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=OllamaTranslator(server.url, timeout=10), cache=cache)
    result = pipeline.process(sample_page)
    assert sum(1 for r in result.regions if r.status == "translated") == 5
    assert [r.status for r in result.regions if r.source_text == never] == ["untranslated"]
    assert len(cache) == 1 and cache.pages[0].incomplete and cache.bubble_count == 5  # the line is asked for next time
    asked = [p for p in server.requests if _translations(p) and never in p["messages"][-1]["content"].splitlines()[-1]]
    assert len(asked) == 2  # the page, then the line on its own


def test_punctuation_copied_is_kept_without_asking_again(server, settings):
    """A line of punctuation alone (the OCR's judgement leaves those as drawn; a gold transcription hands them
    over) comes back as it is: that is its translation, not a copy to ask again for."""
    import numpy as np

    from taslation.regions import TextRegion

    def answer(items, payload):
        if not _translations(payload):
            return None
        return _reply([{"id": it["id"], "text": EN_TEXTS.get(it["ja"], it["ja"])} for it in items])

    server.answer = answer
    regions = [TextRegion(x0=0, y0=40 * i, x1=200, y1=40 * i + 36, mask=np.full((36, 200), 255, np.uint8),
                          text_box=(10, 40 * i + 4, 190, 40 * i + 32), source_text=t, status="untranslated")
               for i, t in enumerate(JA_TEXTS[:3] + ["……！？"])]
    pipeline = Pipeline(settings, ocr=None, translator=OllamaTranslator(server.url, timeout=10))
    assert pipeline._translate_regions(regions, lambda _m: None) == ""
    assert [r.status for r in regions] == ["translated"] * 4 and regions[3].translated_text == "……！？"
    assert sum(1 for p in server.requests if _translations(p)) == 1


def test_a_cancel_while_a_line_is_asked_again_ends_at_once_and_caches_nothing(server, sample_page, settings):
    def answer(items, payload):
        if not _translations(payload):
            return None
        if len(items) == 6:
            return _reply(_english(items)[:5])  # the last line missing
        server.between, server.endless = 0.05, True  # the line asked again: the model never stops writing
        return None

    server.answer = answer
    cache = CacheStore(settings.cache_dir).open("Cancelled again", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=OllamaTranslator(server.url, timeout=30), cache=cache)
    events: list[str] = []
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        pipeline.process(sample_page, cancel=cancel, events=lambda kind, data: events.append(kind))
    assert time.monotonic() - started < 1.0 + 1.5
    assert server.gone.wait(2.0) and sum(1 for p in server.requests if _translations(p)) == 2
    assert len(cache) == 0 and not cache.path.exists() and "page" not in events


def _batch(server, settings, monkeypatch, sample_page, sample_page2, book):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 100  # the three pages in one request
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=OllamaTranslator(server.url, timeout=10), cache=cache)
    return BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True), cache


def test_the_batch_asks_again_only_for_the_lines_a_reply_left_out(server, settings, monkeypatch, sample_page,
                                                                   sample_page2):
    asked: list[int] = []

    def answer(items, payload):
        if not _translations(payload):
            return None
        asked.append(len(items))
        rows = _english(items)
        if len(asked) == 1:  # the run: one id left out early, a line copied, the last line empty
            rows = [{**r, "text": items[3]["ja"]} if r["id"] == 4 else {**r, "text": ""} if r["id"] == 6 else r
                    for r in rows if r["id"] != 2]
        return _reply(rows)

    server.answer = answer
    reader, cache = _batch(server, settings, monkeypatch, sample_page, sample_page2, "Gaps")
    progress = read_book(reader)
    assert progress.finished and progress.pages == 3 and progress.errors == 0
    # the run of three pages, then each line left out (no page asked again whole)
    assert asked == [18, 1, 1, 1]
    assert len(cache) == 3 and cache.bubble_count == 18  # every page complete
    assert any(n.code == "batch.note_incomplete" for n in progress.notes)
    assert not any(n.code in ("batch.note_unit_incomplete", "batch.note_retry_unusable") for n in progress.notes)


def test_a_batch_unit_the_model_gives_nothing_for_is_translated_when_read(server, settings, monkeypatch, sample_page,
                                                                        sample_page2):
    never = JA_TEXTS[4]
    requests: list[list[str]] = []

    def answer(items, payload):
        if not _translations(payload):
            return None
        requests.append([it["ja"] for it in items])
        return _reply([{"id": it["id"], "text": ""} if it["ja"] == never else r
                       for it, r in zip(items, _english(items))])

    server.answer = answer
    reader, cache = _batch(server, settings, monkeypatch, sample_page, sample_page2, "Nothing")
    progress = read_book(reader)
    codes = [n.code for n in progress.notes]
    assert codes.count("batch.note_unit_incomplete") == 3
    assert progress.finished and len(cache) == progress.pages == 3 and cache.bubble_count == 15
    assert all(page.incomplete for page in cache.pages) and progress.translated == 15  # read live, the line comes
    # every run, then the line left out, asked for alone, once
    whole = [r for r in requests if len(r) > 1]
    assert len(whole) == 1 and sum(r.count(never) for r in whole) == 3
    assert [r for r in requests if len(r) == 1] == [[never]] * 3
    assert progress.errors == 0


def test_stop_while_a_batch_asks_again_ends_the_request_and_keeps_the_pages_done(server, settings, monkeypatch,
                                                                               sample_page, sample_page2):
    holder: dict[str, BatchReader] = {}
    asked: list[int] = []

    def answer(items, payload):
        if not _translations(payload):
            return None
        asked.append(len(items))
        if len(asked) == 1:
            return _reply(_english(items)[1:])  # the first line left out
        threading.Timer(0.3, holder["reader"].stop).start()  # Stop pressed while the line is asked for again
        server.between, server.endless = 0.05, True
        return None

    server.answer = answer
    reader, cache = _batch(server, settings, monkeypatch, sample_page, sample_page2, "Stopped again")
    holder["reader"] = reader
    started = time.monotonic()
    progress = read_book(reader)
    assert time.monotonic() - started < 10.0 and asked[1:] == [1]
    assert progress.summary.code == "batch.stopped_translating" and progress.errors == 0 and server.gone.wait(2.0)
    # the first run lacked a line: what came is stored, and the Stop came before the page was done
    assert len(cache) == 3 and sum(page.incomplete for page in cache.pages) == 1 and progress.pages == 3


def test_a_live_request_that_timed_out_is_not_asked_again(server, sample_page, settings):
    server.before_headers = 2.0  # nothing comes within the client's timeout
    cache = CacheStore(settings.cache_dir).open("Timed out", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=OllamaTranslator(server.url, timeout=0.5), cache=cache)
    result = pipeline.process(sample_page)
    assert result.error.code == "ollama.timeout" and len(cache) == 0
    assert len(server.requests) == 1  # a timeout is not fanned out into more requests that would wait as long


def test_a_batch_page_whose_reply_could_not_be_read_is_asked_for_a_few_lines_at_a_time(server, settings, monkeypatch,
                                                                                     sample_page, sample_page2):
    sizes: list[int] = []

    def answer(items, payload):
        if not _translations(payload):
            return None
        sizes.append(len(items))
        if len(sizes) == 1:
            return "Here is the translation you asked for."  # nothing that reads: a bad answer
        return _reply(_english(items))

    server.answer = answer
    reader, cache = _batch(server, settings, monkeypatch, sample_page, sample_page2, "One page a request")
    reader.settings.chunk_bubbles = 1  # every page on its own: the one that fails is a single page unit
    progress = read_book(reader)
    assert progress.finished and len(cache) == 3 and progress.errors == 1  # the failed request, counted
    first = sizes[0]
    assert first > 4 and sizes[1:3] == [4, first - 4]  # the page's lines, four and the rest
    assert len(sizes) == 3 + 2  # the first page's three requests, then one for each of the other two
    assert progress.first_error.code == "ollama.bad_answer"
