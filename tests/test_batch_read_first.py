"""The whole-book batch that reads first and translates all at once: no model request while the pages turn, what Stop
keeps in each pass, what a run left going on in the next one (in memory, in the same window), a page shown twice, and
the band's message after a Stop."""
from __future__ import annotations

import threading

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book, store_json, store_text
from test_batch import _fake_viewer

from taslation.batch import BatchReader, Readings
from taslation.cache import CacheStore
from taslation.message_texts import catalog
from taslation.messages import Message, render
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator, TranslationError

class Timeline(DictTranslator):
    """Every model request in the order it came, with what the viewer had been told by then."""

    def __init__(self, *args, viewer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewer = viewer
        self.requests: list[tuple[str, int]] = []

    def _at(self, kind):
        self.requests.append((kind, self.viewer.index if self.viewer is not None else 0))

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                       on_slow=None):
        self._at("translate")
        return super().translate_page(texts, context, notes, upcoming, meta, on_item, cancel, on_slow)


def _reader(settings, translator, cache, **kwargs):
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=translator, cache=cache)
    return BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, **kwargs)


def _stop_at(reader, code, page=None):
    """Stop pressed when the batch says *code* (of *page*)."""
    def told(p, _result):
        if p.message.code == code and (page is None or p.message.params.get("page") == page):
            reader.stop()

    reader.on_progress = told


def test_no_request_is_made_while_the_pages_turn(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = Timeline(EN_TEXTS, viewer=viewer)
    progress = read_book(_reader(settings, tr, CacheStore(settings.cache_dir).open("Order", "fake")))
    assert progress.pages == 3 and tr.requests
    turned = viewer.index
    assert turned >= 2 and all(at == turned for _kind, at in tr.requests)  # every request after the last key
    assert tr.requests == [("translate", turned)]  # the 18 lines: one run, and nothing else (no notes)


def test_a_new_line_has_one_request(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = Timeline(EN_TEXTS)
    read_book(_reader(settings, tr, CacheStore(settings.cache_dir).open("Once", "fake")))
    assert sum(len(c) for c in tr.calls) == 18 and len(tr.calls) == 1


def test_a_run_of_pages_stays_short_enough_for_the_replies_to_stay_on_their_lines():
    from taslation.config import Settings

    assert Settings().chunk_bubbles == 30  # (measured: at 100 lines the replies drift; docs/OFFLINE_VERIFICATION.md)


def test_stop_while_reading_leaves_nothing_translated_and_the_next_run_reads_those_pages_again(
        sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = Timeline(EN_TEXTS, viewer=viewer)
    cache = CacheStore(settings.cache_dir).open("Read stop", "fake")
    reader = _reader(settings, tr, cache)
    _stop_at(reader, "batch.read_page", 2)
    progress = read_book(reader)
    assert tr.requests == [] and len(cache) == 0 and progress.summary.code == "batch.stopped_reading"
    assert [s.code for s in progress.summary.sentences()] == ["batch.stopped_reading", "batch.read_again"]
    assert reader.left is not None and not reader.left.complete and len(reader.left.units) == 2  # (nobody keeps it)
    # a command line's next run: back to the start, all read again, all translated
    viewer.index = 0
    again = read_book(_reader(settings, tr, cache))
    assert again.pages == 3 and again.translated == 18 and len(cache) == 3


def test_a_window_goes_on_reading_from_the_page_on_show_with_what_it_kept(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = Timeline(EN_TEXTS, viewer=viewer)
    cache = CacheStore(settings.cache_dir).open("Kept reading", "fake")
    reader = _reader(settings, tr, cache, keep_readings=True)
    _stop_at(reader, "batch.read_page", 2)
    progress = read_book(reader)
    assert [s.code for s in progress.summary.sentences()] == ["batch.stopped_reading", "batch.readings_kept"]
    assert str(progress.summary).endswith("Read whole book... goes on from the page on show, until you close TASlation.")
    left = reader.left
    assert isinstance(left, Readings) and (left.pages, left.complete) == (2, False)
    viewer.index = 2  # the reader goes on from the third page
    second = _reader(settings, tr, cache, readings=left, keep_readings=True)
    done = read_book(second)
    assert done.pages == 3 and done.translated == done.found == 18 and len(cache) == 3
    assert second.left is None  # nothing is left in memory
    assert [c for c in tr.calls] and sum(len(c) for c in tr.calls) == 18


def test_a_page_read_twice_is_translated_once(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    tr = Timeline(EN_TEXTS, viewer=viewer)
    cache = CacheStore(settings.cache_dir).open("Twice", "fake")
    reader = _reader(settings, tr, cache, keep_readings=True)
    _stop_at(reader, "batch.read_page", 2)
    read_book(reader)
    viewer.index = 0  # the reader went back to the first page before starting again
    second = _reader(settings, tr, cache, readings=reader.left)
    done = read_book(second)
    assert sum(len(c) for c in tr.calls) == 18 and done.found == 18 and len(cache) == 3


def test_stop_during_the_translation_keeps_what_is_stored_and_a_window_goes_on_without_turning(
        sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 8  # a run a page
    tr = Timeline(EN_TEXTS, viewer=viewer)
    cache = CacheStore(settings.cache_dir).open("Mine 1巻", "fake")
    reader = _reader(settings, tr, cache, keep_readings=True, book="Mine 1巻")
    _stop_at(reader, "batch.translated_chunk")  # the first run of pages is stored
    progress = read_book(reader)
    summary = progress.summary
    assert summary.code == "batch.stopped_translating" and len(cache) == 1
    assert (summary.params["done"], summary.params["total"], summary.params["kept"]) == (6, 18, 1)
    assert [s.code for s in summary.sentences()] == ["batch.stopped_translating", "batch.continues_translating"]
    assert str(summary).startswith("Stopped: 6 of 18 lines are translated and stored, and stay.")
    assert render(summary, catalog("ja")).startswith("停止しました: 18 行中 6 行を翻訳して保存済みで")
    left = reader.left
    assert left.complete and len(left.units) == 2

    viewer.index = 0  # wherever the reader went: the run does not look
    tr2 = Timeline(EN_TEXTS, viewer=viewer)
    told = []
    second = _reader(settings, tr2, cache, readings=left, book="Mine 1巻",
                     on_progress=lambda p, _r: told.append(p.message.code))
    done = read_book(second)
    assert done.pages == 3
    assert sum(len(c) for c in tr2.calls) == 12  # the other two pages alone
    assert "batch.continuing" in told and "batch.scanning_page" not in told and "batch.pages_read" not in told
    assert done.reason in ("", None) or done.summary.code == "batch.finished"
    assert len(cache) == 3 and cache.bubble_count == 18 and second.left is None


def test_a_command_line_run_stopped_in_the_translation_says_it_reads_again(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 8
    tr = Timeline(EN_TEXTS, viewer=viewer)
    cache = CacheStore(settings.cache_dir).open("Line stop", "fake")
    reader = _reader(settings, tr, cache)
    _stop_at(reader, "batch.translated_chunk")
    summary = read_book(reader).summary
    assert [s.code for s in summary.sentences()] == ["batch.stopped_translating", "batch.stored_read_again"]
    assert "the pages translated are skipped" in str(summary)
    viewer.index = 0
    tr2 = Timeline(EN_TEXTS, viewer=viewer)
    done = read_book(_reader(settings, tr2, cache))
    assert sum(len(c) for c in tr2.calls) == 12 and done.cache_hits == 1 and len(cache) == 3


def test_a_page_translated_or_corrected_since_the_stop_is_not_translated_over(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 8
    tr = Timeline(EN_TEXTS, viewer=viewer)
    cache = CacheStore(settings.cache_dir).open("Read since", "fake")
    reader = _reader(settings, tr, cache, keep_readings=True)
    _stop_at(reader, "batch.translated_chunk")
    read_book(reader)
    # the reader reads the second page with Auto meanwhile, and corrects a line
    live = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    live.process(viewer.pages[1])
    page = next(p for p in cache.pages if p.fingerprint == reader.left.units[0].fingerprint)
    page.bubbles[0].text = "The reader's own line."
    cache.save()
    tr2 = Timeline(EN_TEXTS, viewer=viewer)
    done = read_book(_reader(settings, tr2, cache, readings=reader.left))
    assert sum(len(c) for c in tr2.calls) == 6 and done.found == 6  # the third page alone
    assert any(b.text == "The reader's own line." for p in cache.pages for b in p.bubbles)


def test_a_run_that_failed_for_good_leaves_its_readings_too(sample_page, sample_page2, settings, monkeypatch):
    down = Message("ollama.unreachable", url="http://127.0.0.1:11434")

    class Gone(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                           on_slow=None):
            raise TranslationError(down)

    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Gone", "fake")
    reader = _reader(settings, Gone(EN_TEXTS), cache, keep_readings=True)
    progress = read_book(reader)
    assert progress.reason == down and len(cache) == 0 and reader.left.complete and viewer.index >= 2
    done = read_book(_reader(settings, DictTranslator(EN_TEXTS), cache, readings=reader.left))
    assert done.translated == 18


def test_a_stopped_request_stores_nothing_of_it(sample_page, sample_page2, settings, monkeypatch):
    holder = {}

    class Blocking(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                           on_slow=None):
            holder["started"].set()
            assert cancel.wait(5)
            raise TranslationError(Message("ollama.cancelled"))

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Under way", "fake")
    holder["started"] = threading.Event()
    reader = _reader(settings, Blocking(EN_TEXTS), cache, keep_readings=True)
    thread = threading.Thread(target=read_book, args=(reader,))
    thread.start()
    assert holder["started"].wait(10)
    reader.stop()
    thread.join(10)
    assert not thread.is_alive() and len(cache) == 0
    assert reader.progress.summary.code == "batch.stopped_translating" and len(reader.left.units) == 3


def test_a_cache_file_with_first_drafts_of_an_earlier_version_loads_them_as_translations(sample_page, sample_page2,
                                                                                         settings, monkeypatch):
    """A cache an earlier version wrote marks some bubbles "draft": they load as the translations they are, a whole-book
    run asks for nothing of them, and the next save writes them without the mark."""
    import json

    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    store = CacheStore(settings.cache_dir)
    cache = store.open("Old drafts", "fake")
    read_book(_reader(settings, DictTranslator(EN_TEXTS), cache))
    data = store_json(cache.path)
    for page in data["pages"]:
        for b in page["bubbles"]:
            b["draft"] = True  # as a run of a version before 2026-11-06 left them
    cache.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    old = store.open("Old drafts", "fake")
    assert old.bubble_count == 18
    assert sorted(b.text for p in old.pages for b in p.bubbles) == sorted(
        b.text for p in cache.pages for b in p.bubbles)
    viewer.index = 0
    tr = Timeline(EN_TEXTS, viewer=viewer)
    done = read_book(_reader(settings, tr, old))
    assert tr.calls == [] and tr.requests == [] and done.translated == 0
    old.dirty = True
    old.save()
    assert '"draft"' not in store_text(old.path)


@pytest.mark.parametrize("complete", [True, False])
def test_readings_are_memory_only(sample_page, sample_page2, settings, monkeypatch, complete):
    """Nothing Japanese reaches the state folder: not at a Stop in any pass."""
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Private", "fake")
    reader = _reader(settings, DictTranslator(EN_TEXTS), cache, keep_readings=True)
    _stop_at(reader, "batch.pages_read" if complete else "batch.read_page")
    read_book(reader)
    assert reader.left is not None
    japanese = [r.source_text for u in reader.left.units for r in u.japanese()]
    assert japanese
    from pathlib import Path

    for path in Path(settings.state_dir).rglob("*"):
        if path.is_file():
            data = path.read_bytes().decode("utf-8", "replace")
            assert not any(line in data for line in japanese), path.name
