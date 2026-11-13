"""What a run says, said as it is: one unit (lines) in every count of the run and its stages, a page from the cache
named as translated before (not "0 lines read"), not "Translating..." while a page is only looked at, the page read
counted as it is said (the band, the strip and the status line say the same number), and the whole-book dialog
saying what TASlation does to the viewer's window."""
from __future__ import annotations

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from test_batch import _fake_viewer
from test_start_flow import VIEWER, Flow, _frame

from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.i18n import set_language
from taslation.message_texts import catalog
from taslation.messages import PARAMS, Message, render
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import progress
from taslation.ui.dialogs.batch import BatchDialog

LANGUAGES = ("ja", "es", "pt", "fr", "de", "it", "nl", "pl", "ru", "tr", "id", "vi", "zh", "zh-tw", "ko", "th")
# the counts of a run, each with the word of a bubble it no longer uses
COUNTS = ("batch.translated_page", "batch.pages_read", "batch.translating_chunk", "batch.translated_chunk",
          "batch.finished", "batch.note_retry_failed", "batch.note_retry_unusable", "batch.note_pruned",
          "batch.page_cached")
BUBBLE_WORDS = {"en": "bubble", "ja": "吹き出し", "es": "bocadillo", "pt": "balã", "fr": "bulle", "de": "Sprechblase",
                "it": "nuvolett", "nl": "tekstballon", "pl": "dymk", "ru": "пузыр", "tr": "balon", "id": "balon",
                "vi": "bong bóng", "zh": "气泡", "zh-tw": "氣泡", "ko": "말풍선", "th": "บอลลูน"}


def _params(code):
    values = {"page": 3, "pages": 4, "bubbles": 12, "lines": 12, "seconds": 9.0, "minutes": 2, "chunk": 1, "chunks": 2,
              "error": "", "failed": 0, "reason": Message("batch.finished_reading"), "cached": 0, "dropped": 0}
    return {name: values[name] for name in PARAMS[code]}


@pytest.mark.parametrize("language", ("en",) + LANGUAGES)
def test_every_count_of_a_run_is_of_lines(language):
    templates = catalog(language) if language != "en" else None
    for code in COUNTS:
        text = render(Message(code, **_params(code)), templates)
        assert BUBBLE_WORDS[language] not in text, (language, code, text)
    if language == "en":
        assert str(Message("batch.pages_read", pages=4, bubbles=52)).startswith("Every page is read: 4 screens, 52 lines.")


def test_the_stages_count_lines_and_looking_for_the_text_is_not_translating():
    assert progress.stage_of(Message("pipeline.stage_reading", done=1, total=3)) == "reading 3 line(s)"
    assert progress.stage_of(Message("pipeline.stage_translating", bubbles=5, translator="m"), 2) == "2 of 5 line(s) done"
    finding = Message("pipeline.stage_finding")
    assert progress.progress_line(finding) == "Looking at the page... finding the bubbles"  # a cached page, too
    assert progress.progress_line(Message("pipeline.stage_reading", done=1, total=3)) == "Translating... reading 3 line(s)"
    set_language("ja")
    try:
        assert progress.progress_line(finding) == "ページを確認中... 吹き出しを検出中"
        assert progress.stage_of(Message("pipeline.stage_reading", done=1, total=3)) == "3 行を読み取り中"
    finally:
        set_language("en")


def test_a_page_starts_as_looked_at(hidden_root, tmp_path):
    flow = Flow(hidden_root, tmp_path)
    flow._start_translate(_frame())
    assert flow.status_var.get() == "Looking at the page..."


# ------------------------------------------------------------------ the run's own words
class Said:
    """(pages counted, message) as the batch says each, as the window gets them."""

    def __init__(self):
        self.seen = []

    def __call__(self, p, _result):
        self.seen.append((p.pages, p.message))

    def of(self, code):
        return [(pages, m) for pages, m in self.seen if m.code == code]


def _reader(settings, cache, said, **kwargs):
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    return BatchReader(pipeline, hwnd=1, settings=settings, on_progress=said, **kwargs)


def test_a_page_is_counted_as_it_is_said_and_a_cached_one_says_its_lines(sample_page, sample_page2, settings,
                                                                          monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Said", "fake")
    said = Said()
    read_book(_reader(settings, cache, said, context_mode=True))
    reads = said.of("batch.read_page")
    assert [m.params["page"] for _p, m in reads] == [1, 2, 3]
    assert all(pages == m.params["page"] for pages, m in reads)  # "Read: 3" on the band as "Page 3: ..." is said
    assert not said.of("batch.page_cached")
    scanning = said.of("batch.scanning_page")
    assert all(pages == m.params["page"] - 1 for pages, m in scanning)  # being read: not counted yet
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    again = Said()
    read_book(_reader(settings, cache, again, context_mode=True))  # the same book again: every page from the cache
    cached = again.of("batch.page_cached")
    assert [m.params["page"] for _p, m in cached] == [1, 2, 3] and not again.of("batch.read_page")
    assert all(m.params["lines"] == 6 for _p, m in cached)  # its lines, translated before - not "0 lines read"
    assert all(pages == m.params["page"] for pages, m in cached)
    assert str(cached[0][1]).startswith("Page 1: 6 lines translated before")


def test_a_page_translated_page_by_page_is_counted_as_it_is_said(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    said = Said()
    read_book(_reader(settings, CacheStore(settings.cache_dir).open("Pagewise", "fake"), said, context_mode=False))
    done = said.of("batch.translated_page")
    assert [m.params["page"] for _p, m in done] == [1, 2, 3]
    assert all(pages == m.params["page"] for pages, m in done)
    assert str(done[0][1]).startswith("Page 1: 6 lines")


def test_the_whole_book_dialog_says_what_is_done_to_the_viewer(hidden_root, tmp_path):
    d = BatchDialog(hidden_root, VIEWER, Settings(state_dir=tmp_path), on_start=lambda *a: None)
    d.withdraw()
    text = " ".join(str(d.size_line.cget("text")).split())
    assert "leaves the viewer as you have set it" not in text
    assert "as large as the screen once" in text and "gives it its size back when TASlation closes" in text
    assert "Start shows it again if it is minimised" in text
