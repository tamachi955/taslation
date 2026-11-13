from __future__ import annotations

import numpy as np
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image

from taslation import batch as batch_mod
from taslation.batch import BatchReader, frames_differ, thumbnail
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator, TranslationError


def test_frames_differ(sample_page, sample_page2):
    a, b = thumbnail(sample_page), thumbnail(sample_page2)
    assert not frames_differ(a, a)
    assert frames_differ(a, b)
    assert frames_differ(None, a)


class FakeViewer:
    """A book: the person at the viewer moves `index` (`helpers.read_book`)."""

    def __init__(self, pages: list[Image.Image]):
        self.pages = pages
        self.index = 0

    def capture(self, hwnd):
        return self.pages[self.index]


def _fake_viewer(sample_page, sample_page2, settings, monkeypatch):
    viewer = FakeViewer([sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT)])
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    settings.settle_ms = 10
    settings.page_turn_wait_ms = 300
    return viewer


def test_pagewise_batch_reads_until_the_end_and_fills_cache(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    seen = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, on_progress=lambda p, r: seen.append((p.pages, r)), context_mode=False)
    progress = read_book(reader)
    assert progress.finished
    assert progress.pages == 3, progress
    assert progress.reason.code == "batch.finished_reading"
    assert len(cache) == 3 and cache.bubble_count >= 12
    assert any(r is not None for _, r in seen)


def test_whole_book_reads_every_page_then_translates_with_the_series_sheet(sample_page, sample_page2, settings,
                                                                           monkeypatch):
    from pathlib import Path

    from taslation.annotations import Glossary

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 8  # 3 pages x 6 bubbles -> several chunks, units never split
    tr = DictTranslator(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("My Story 2巻", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache)
    sheet = Glossary(Path("sheet.json"), "My Story", "English")
    sheet.set("天気", "Tenki")
    pipeline.glossary, pipeline.glossary_text = sheet, sheet.format()
    phases, while_reading = [], []

    def on_progress(p, _result):
        phases.append(p.phase)
        if p.message.code == "batch.read_page":  # nothing is asked of the model or stored while the pages turn
            while_reading.append((len(cache), len(tr.calls)))

    reader = BatchReader(pipeline, hwnd=1, settings=settings, on_progress=on_progress, book="My Story 2巻")
    progress = read_book(reader)
    assert progress.finished and progress.pages == 3, progress
    assert progress.reason.code == "batch.finished_reading"
    assert while_reading == [(0, 0)] * 3
    assert {"read", "translate"} <= set(phases) and "notes" not in phases
    assert phases.index("read") < phases.index("translate")
    # one translation request a chunk (here a page), with the series sheet, the pairs before and what comes next
    assert len(tr.calls) == 3 and all(len(c) == 6 for c in tr.calls)
    first = tr.kwargs[0]
    assert "Tenki" in first["notes"] and getattr(first["notes"], "sheet", None) is sheet
    assert first["upcoming"]  # the next chunk's bubbles were shown for context
    assert not first["context"] and tr.kwargs[-1]["context"]  # the pairs before carried along
    assert len(cache) == 3 and cache.bubble_count == 18
    assert progress.checked == progress.translated == 18


def test_failed_chunk_is_retried_in_halves(sample_page, sample_page2, settings, monkeypatch):
    class FlakyTranslator(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            if len(texts) > 7:
                self.calls.append(list(texts))
                raise TranslationError("Ollama timed out after 900s")
            return super().translate_page(texts, context, notes, upcoming)

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 100  # everything in one chunk: 18 bubbles -> fails -> halves -> ...
    tr = FlakyTranslator(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Flaky", "fake")
    reader = BatchReader(Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache), hwnd=1, settings=settings, context_mode=True)
    progress = read_book(reader)
    assert progress.finished and progress.pages == 3
    assert progress.errors >= 2  # the chunk, then a half
    assert "timed out" not in progress.reason  # the batch went on
    assert len(cache) == 3 and cache.bubble_count >= 12
    assert any("retrying in two halves" in n for n in progress.notes)
    assert progress.checked == progress.translated == cache.bubble_count


def test_output_budget_scales_with_input():
    from taslation.translate.ollama import OllamaTranslator

    assert OllamaTranslator.output_budget(["x"]) == 512
    assert OllamaTranslator.output_budget(["あ" * 15] * 60) == 12 * 60 + 2 * 900


def test_incomplete_reply_is_followed_by_a_request_for_the_unfinished_pages(sample_page, sample_page2, settings, monkeypatch):
    class CutOffTranslator(DictTranslator):
        """Answers big requests only partly (as a reply cut off by the output cap would)."""

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            out = super().translate_page(texts, context, notes, upcoming)
            if len(texts) > 8:
                out = out[:7] + [""] * (len(texts) - 7)
            return out

    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 100
    tr = CutOffTranslator(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Cut", "fake")
    reader = BatchReader(Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache), hwnd=1, settings=settings, context_mode=True)
    progress = read_book(reader)
    assert progress.finished and progress.pages == 3
    assert len(cache) == 3 and cache.bubble_count >= 12
    assert any("came back incomplete; asking again" in n for n in progress.notes)
    assert not any(n.code == "batch.note_unit_incomplete" for n in progress.notes)
    assert len(tr.calls) >= 2


def test_chunk_units_never_splits_a_page():
    from taslation.batch import chunk_units
    from taslation.pipeline import ScannedRegion, ScannedUnit

    def unit(n, idx):
        regions = [ScannedRegion((0, 0, 10, 10), (0, 0, 10, 10), [], f"文{i}", "untranslated") for i in range(n)]
        return ScannedUnit(idx, (0, 0, 100, 100), "f" * 80, 0.7, regions)

    units = [unit(5, 0), unit(5, 1), unit(5, 2), unit(2, 3)]
    chunks = chunk_units(units, 8)
    assert [len(c) for c in chunks] == [1, 1, 2]
    assert chunk_units([], 8) == []


def test_batch_stop(sample_page, settings, monkeypatch):
    viewer = FakeViewer([sample_page])
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    settings.settle_ms = 10
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
    reader = BatchReader(pipeline, hwnd=1, settings=settings)
    reader.stop()
    progress = read_book(reader)
    assert progress.finished and progress.pages <= 1
