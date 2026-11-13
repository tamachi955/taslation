"""What a batch says, and that it is right: the bubbles found while scanning, failures in the summary, Stop that
ends a request at once and is reported as a stop, the screens turned, the pre-flight check in the first message."""
from __future__ import annotations

import threading
import time

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image
from test_batch import _fake_viewer

from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.message_texts import catalog
from taslation.messages import Cancelled, Message, render
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator, TranslationError


class Recorder:
    """Every (phase, bubbles shown, message) the batch reports."""

    def __init__(self, on_message=None):
        self.seen: list[tuple[str, int, Message]] = []
        self.on_message = on_message

    def __call__(self, p, _result):
        self.seen.append((p.phase, p.bubbles, p.message))
        if self.on_message is not None:
            self.on_message(p.message)

    def codes(self):
        return [m.code for _phase, _b, m in self.seen]

    def of(self, code):
        return [(b, m) for _phase, b, m in self.seen if m.code == code]


def _reader(settings, translator, cache, recorder=None, **kwargs):
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=translator, cache=cache)
    return BatchReader(pipeline, hwnd=1, settings=settings, on_progress=recorder, **kwargs)


def test_the_scan_counts_the_bubbles_it_finds(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Counted", "fake")
    rec = Recorder()
    progress = read_book(_reader(settings, DictTranslator(EN_TEXTS), cache, rec, context_mode=True))
    assert all(isinstance(m, Message) for _p, _b, m in rec.seen)
    first, last = rec.seen[0][2], rec.seen[-1][2]
    assert first.code == "batch.started" and first.params["problems"] == 0
    scanned = rec.of("batch.read_page")
    assert len(scanned) == 3
    totals = [m.params["bubbles"] for _b, m in scanned]
    assert totals[0] >= 6 and totals == sorted(totals) and totals[-1] == progress.found
    assert all(shown == m.params["bubbles"] for shown, m in scanned)  # "pages, bubbles" while turning: the found ones
    assert [m.params["page"] for _b, m in scanned] == [1, 2, 3] and all(m.params["lines"] == 6 for _b, m in scanned)
    assert rec.codes().index("batch.pages_read") < rec.codes().index("batch.translating_chunk")
    assert not any(code.startswith("batch.notes") for code in rec.codes())  # no notes pass
    assert progress.translated == progress.bubbles == progress.found == progress.checked  # all read, all translated
    assert last is progress.summary and last.code == "batch.finished"
    params = last.params
    assert (params["pages"], params["bubbles"], params["failed"]) == (3, progress.translated, 0)
    assert params["reason"].code == "batch.finished_reading" and params["error"] == ""
    assert str(last).startswith("Whole-book scan done: 3 pages, ") and str(last).endswith(" - you finished reading.")
    assert [s.code for s in last.sentences()] == ["batch.finished"]


def test_failed_requests_reach_the_summary(sample_page, sample_page2, settings, monkeypatch):
    class Flaky(DictTranslator):
        """The first request times out; every other one is answered."""

        failed = False

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            if not self.failed:
                self.failed = True
                raise TranslationError(Message("ollama.timeout", seconds=900.0))
            return super().translate_page(texts, context, notes, upcoming)

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 100
    tr = Flaky(EN_TEXTS)
    progress = read_book(_reader(settings, tr, CacheStore(settings.cache_dir).open("Flaky2", "fake"), context_mode=True))
    summary = progress.summary
    assert summary.code == "batch.finished" and progress.translated == 18
    assert summary.params["failed"] == progress.errors == 1
    assert summary.params["error"].code == "ollama.timeout" and progress.first_error.code == "ollama.timeout"
    assert [s.code for s in summary.sentences()] == ["batch.finished", "batch.failures"]
    assert "1 part(s) could not be translated." in summary
    assert any(n.code == "batch.note_retry_failed" for n in progress.notes) and progress.checked == 18  # in two halves


def test_when_every_request_fails_nothing_is_called_done(sample_page, sample_page2, settings, monkeypatch):
    class Failing(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            self.calls.append(list(texts))
            raise TranslationError(Message("ollama.timeout", seconds=900.0))

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = Failing(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Failing", "fake")
    progress = read_book(_reader(settings, tr, cache, context_mode=True))
    assert len(tr.calls) > 1  # a timeout may pass: retried in halves
    summary = progress.summary
    assert summary.code == "batch.failed_requests" and progress.translated == 0 and len(cache) == 0
    assert summary.params["failed"] == progress.errors == len(tr.calls)
    assert summary.params["reason"].code == "ollama.timeout"
    assert str(summary).startswith("Nothing could be translated: ")


def test_ollama_gone_ends_the_translation_at_the_first_failure(sample_page, sample_page2, settings, monkeypatch):
    down = Message("ollama.unreachable", url="http://127.0.0.1:11434")

    class Down(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            self.calls.append(list(texts))
            raise TranslationError(down)

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 8  # several chunks: none after the first is tried
    tr = Down(EN_TEXTS)
    progress = read_book(_reader(settings, tr, CacheStore(settings.cache_dir).open("Down", "fake"), context_mode=True))
    assert len(tr.calls) == 1  # no retry in halves, no other run tried: nothing would be translated
    assert progress.summary.code == "batch.failed_requests" and progress.summary.params["reason"] == down
    assert progress.reason.code == "ollama.unreachable" and progress.pages == 3  # the pages turn with no model at work


def test_stop_is_reported_as_a_stop(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = DictTranslator(EN_TEXTS)
    holder: dict[str, BatchReader] = {}

    def stop_at_page_two(message):
        if message.code == "batch.read_page" and message.params["page"] == 2:
            holder["reader"].stop()

    rec = Recorder(stop_at_page_two)
    cache = CacheStore(settings.cache_dir).open("Stopped", "fake")
    holder["reader"] = reader = _reader(settings, tr, cache, rec, context_mode=True)
    progress = read_book(reader)
    summary = progress.summary
    assert summary.code == "batch.stopped_reading" and rec.seen[-1][2] is summary
    assert dict(summary.params) | {"seconds": 0} == {"pages": 2, "seconds": 0, "kept": 0, "again": 1}
    assert str(summary) == ("Stopped after reading 2 pages. Nothing is translated yet: the translation comes after "
                            "Finished reading. - Those pages are read again next time: go back 2 pages in the viewer, then run "
                            "Read whole book... again.")
    assert "batch.pages_read" not in rec.codes()
    assert tr.calls == []  # no request at all
    assert len(cache) == 0  # nothing read is stored
    assert progress.reason.code == "batch.user_stop"


def test_stop_ends_a_request_in_progress_at_once(sample_page, sample_page2, settings, monkeypatch):
    holder: dict[str, BatchReader] = {}

    class Slow(DictTranslator):
        """A model that takes its time: answers only after 10 s, unless the request is cancelled."""

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                           on_slow=None):
            self.calls.append(list(texts))
            self.asked = time.monotonic()
            assert cancel is holder["reader"]._stop  # the batch's Stop is the request's cancel
            on_slow(20.0)
            threading.Timer(0.3, holder["reader"].stop).start()  # Stop pressed while the model writes
            if cancel.wait(10):
                raise Cancelled()
            return super().translate_page(texts, context, notes, upcoming)

    for context_mode in (True, False):
        _fake_viewer(sample_page, sample_page2, settings, monkeypatch).index = 0
        tr = Slow(EN_TEXTS)
        cache = CacheStore(settings.cache_dir).open(f"Slow {context_mode}", "fake")
        rec = Recorder()
        holder["reader"] = reader = _reader(settings, tr, cache, rec, context_mode=context_mode)
        progress = read_book(reader)
        assert time.monotonic() - tr.asked < 5.0  # not the 10 s the request would have taken
        assert len(tr.calls) == 1 and len(cache) == 0  # nothing of the cancelled request was cached
        assert progress.summary.code == ("batch.stopped_translating" if context_mode else "batch.stopped")
        assert progress.errors == 0  # a stop, not a failure
        assert "ollama.slow" in rec.codes()  # the slow answer was told


def test_the_pre_flight_result_is_the_first_message(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    down = Message("health.ollama_down", url="http://127.0.0.1:11434")
    rec = Recorder()
    progress = read_book(_reader(settings, DictTranslator(EN_TEXTS), CacheStore(settings.cache_dir).open("Pre", "fake"), rec,
                       context_mode=True, preflight=[down]))
    first = rec.seen[0][2]
    assert first.code == "batch.started" and dict(first.params) == {"problems": 1, "problem": down}
    assert progress.preflight == [down]
    assert str(first) == "Whole-book run started - before the start 1 problem was found: " + str(down)
    assert progress.summary.code == "batch.finished"  # the batch ran regardless: the caller decides


def test_without_a_pre_flight_result_the_batch_looks_at_its_own_pipeline(sample_page, sample_page2, settings,
                                                                        monkeypatch, tmp_path):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.models_dir = tmp_path / "no-models"
    rec = Recorder()
    progress = read_book(BatchReader(Pipeline(settings, ocr=None, translator=None), hwnd=1, settings=settings, on_progress=rec,
                           context_mode=True))
    first = rec.seen[0][2]
    assert first.code == "batch.started" and first.params["problems"] == 2
    assert [m.code for m in progress.preflight] == ["health.ocr_missing", "pipeline.no_translator"]
    assert first.params["problem"] is progress.preflight[0]


def test_page_by_page_says_the_same_things(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    rec = Recorder()
    progress = read_book(_reader(settings, DictTranslator(EN_TEXTS), CacheStore(settings.cache_dir).open("Pages", "fake"), rec,
                       context_mode=False))
    pages = rec.of("batch.translated_page")
    assert [m.params["page"] for _b, m in pages] == [1, 2, 3] and all(m.params["error"] == "" for _b, m in pages)
    assert progress.summary.code == "batch.finished"
    assert progress.summary.params["bubbles"] == progress.translated >= 18


@pytest.mark.parametrize("context_mode", [True, False])
def test_a_viewer_that_never_drew_reads_nothing(sample_page, sample_page2, settings, monkeypatch, context_mode):
    """No frame had a page unit: nothing was read, and that is what the summary says."""
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    viewer.pages = [Image.new("RGB", sample_page.size, (255, 255, 255))]
    tr = DictTranslator(EN_TEXTS)
    rec = Recorder()
    progress = read_book(_reader(settings, tr, CacheStore(settings.cache_dir).open("Undrawn", "fake"), rec,
                       context_mode=context_mode))
    assert progress.finished and (progress.pages, progress.seen) == (0, [])
    assert progress.reason == Message("batch.no_page_seen") and not tr.calls
    assert progress.summary.code == "batch.not_started" and progress.summary.params["reason"] == progress.reason
    assert str(progress.summary) == ("Whole-book run not started: no page of the book could be seen in the viewer; check that "
                                     "the book is on show, then start again")
    assert "batch.pages_read" not in rec.codes() and rec.seen[-1][2] is progress.summary
    assert render(progress.reason, catalog("ja")) == ("ビューアに本のページが見えません。本が表示されているか確認して"
                                                      "から、もう一度始めてください")


def test_a_book_of_one_screen_with_content_ends_with_the_reader(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    viewer.pages = [sample_page]
    cache = CacheStore(settings.cache_dir).open("One screen", "fake")
    first = read_book(_reader(settings, DictTranslator(EN_TEXTS), cache, context_mode=True))
    assert first.pages == 1 and first.reason == Message("batch.finished_reading") and first.summary.code == "batch.finished"
    again = read_book(_reader(settings, DictTranslator(EN_TEXTS), cache, context_mode=True))  # all of it in the cache now
    assert again.pages == 1 and again.summary.code == "batch.finished"
    assert again.reason == Message("batch.nothing_new", reason=Message("batch.finished_reading"))


def test_a_viewer_that_stops_showing_pages_after_one_was_read_ends_nothing(sample_page, sample_page2, settings,
                                                                          monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    viewer.pages = [sample_page, Image.new("RGB", sample_page.size, (255, 255, 255))]
    progress = read_book(_reader(settings, DictTranslator(EN_TEXTS), CacheStore(settings.cache_dir).open("Left", "fake"),
                       context_mode=False))
    assert progress.pages == 1 and progress.reason == Message("batch.finished_reading")
    assert progress.summary.code == "batch.finished"


class TimingOut(DictTranslator):
    """A translator whose every request times out (a failure the lines are not asked for again after)."""

    def translate_page(self, *_args, **_kwargs):
        raise TranslationError(Message("ollama.timeout", seconds=900.0))


def test_a_failed_page_unit_says_it_is_translated_when_its_page_is_read(settings):
    """When a unit cannot be translated, the note says what happens: the page is translated when it is read."""
    from collections import deque

    from taslation.message_texts import catalog
    from taslation.messages import render
    from taslation.pipeline import ScannedRegion, ScannedUnit

    regions = [ScannedRegion((0, 0, 10, 10), (0, 0, 10, 10), [], f"文{i}", "untranslated") for i in range(2)]
    reader = _reader(settings, TimingOut({}), CacheStore(settings.cache_dir).open("Failing", "fake"))
    reader._translate_units([ScannedUnit(0, (0, 0, 100, 100), "b" * 80, 0.7, regions)], deque(), "", [], "English")
    notes = reader.progress.notes
    assert [n.code for n in notes] == ["batch.note_unit_failed"]
    assert str(notes[0]) == ("page unit bbbbbbbb: The translation took too long. Press F5 to try again.; it is translated "
                             "when its page is read")
    assert "live mode" not in str(notes[0])
    assert render(notes[0], catalog("ja")).endswith("。読むときに翻訳します")
