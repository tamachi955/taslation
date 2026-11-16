"""A page read afresh and shown is lettered once more right after, as its next showing letters it from the cache, and
kept in memory (`Pipeline.keep_shown`): that showing comes from memory at once, the very page it would have lettered,
and the cache is what it would have been. A new page or Stop ends it with nothing kept."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import jobs


def _pipeline(settings, book):
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)


def _count_detection(pipeline, monkeypatch) -> list[int]:
    calls: list[int] = []
    real = pipeline._detect
    monkeypatch.setattr(pipeline, "_detect", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    return calls


def _kept(cache) -> list[tuple]:
    return [(p.fingerprint, p.seq, p.incomplete, [(b.box, b.text, b.poly, b.flags) for b in p.bubbles])
            for p in cache.pages]


def _as_shown(result) -> list[tuple]:
    return [(r.bbox, r.translated_text, r.status, r.font_size, tuple(r.letter_flags), r.order) for r in result.regions]


@pytest.mark.parametrize("which", ["sample_page", "sample_page2"])
def test_the_next_showing_is_from_memory_and_the_very_page_it_was(which, settings, monkeypatch, request):
    page = request.getfixturevalue(which)
    # as ever: read afresh, then shown again (from the cache, then kept)
    before = _pipeline(settings, "As ever")
    first_ever = before.process(page.copy())
    again_ever = before.process(page.copy())
    assert "shown before" not in again_ever.timings and again_ever.cache_hits == len(again_ever.units)

    # now: read afresh, kept ahead, then shown again
    p = _pipeline(settings, "Kept ahead")
    first = p.process(page.copy())
    assert np.array_equal(np.asarray(first.image), np.asarray(first_ever.image))
    times = len(p.stage_times)
    assert p.keep_shown(page.copy())
    assert len(p.stage_times) == times  # (not counted as a page lettered)
    detected = _count_detection(p, monkeypatch)
    again = p.process(Image.fromarray(np.asarray(page).copy()))
    assert detected == [] and "shown before" in again.timings
    assert np.array_equal(np.asarray(again.image), np.asarray(again_ever.image))
    assert _as_shown(again) == _as_shown(again_ever)
    assert _kept(p.cache) == _kept(before.cache)
    assert not p.keep_shown(page.copy())  # kept already: nothing done
    assert detected == []


def test_a_cancel_ends_it_with_nothing_kept(sample_page, settings, monkeypatch):
    p = _pipeline(settings, "Stopped ahead")
    p.process(sample_page.copy())
    cancel = threading.Event()
    cancel.set()
    detected = _count_detection(p, monkeypatch)
    assert not p.keep_shown(sample_page.copy(), cancel=cancel)
    assert detected == [] and len(p.shown_pages) == 0

    cancel = threading.Event()
    real = p.detector.detect

    def detect(rgb, inverted=False):
        cancel.set()  # the viewer turned the page meanwhile
        return real(rgb, inverted=inverted)

    p.detector.detect = detect
    assert not p.keep_shown(sample_page.copy(), cancel=cancel)
    assert len(p.shown_pages) == 0
    p.detector.detect = real
    shown = p.process(sample_page.copy())  # the next showing letters it as ever
    assert "shown before" not in shown.timings and len(p.shown_pages) == 1


def test_nothing_is_done_for_a_page_its_next_showing_letters_afresh(sample_page, settings, monkeypatch):
    p = _pipeline(settings, "Not kept")
    p.process(sample_page.copy(), use_cache=False)  # not in the cache
    detected = _count_detection(p, monkeypatch)
    assert not p.keep_shown(sample_page.copy())
    p.process(sample_page.copy())
    detected.clear()
    p.shown_pages.clear()
    assert not p.keep_shown(sample_page.copy(), complete=True)  # translator mode adds to its entry each time
    assert detected == [] and len(p.shown_pages) == 0
    assert not Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).keep_shown(sample_page)


class Window:
    """What `_job_translate` needs of the window; the worker's other jobs are dropped."""

    _job_translate = jobs.JobsMixin._job_translate
    _say_failed_save = jobs.JobsMixin._say_failed_save
    _use_model = jobs.JobsMixin._use_model

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.translator = SimpleNamespace(model="m")
        self.settings = Settings()
        self.posted: list[tuple[str, dict]] = []
        self._jobs = SimpleNamespace(put=lambda job: None)

    def _post(self, kind, **data):
        self.posted.append((kind, data))

    def _ensure_cache(self, *_a):
        return True

    def _look_for_colophon(self, *_a):
        pass

    def results(self):
        return [data["result"] for kind, data in self.posted if kind == "result"]


def test_the_page_job_keeps_the_page_after_its_result(sample_page, settings, monkeypatch):
    p = _pipeline(settings, "Job")
    w = Window(p)
    w._job_translate(sample_page.copy(), "Job", "m", "English", False, threading.Event())
    kinds = [kind for kind, _data in w.posted]
    assert kinds.index("result") < kinds.index("translate_done") and len(p.shown_pages) == 1
    detected = _count_detection(p, monkeypatch)
    w._job_translate(sample_page.copy(), "Job", "m", "English", False, threading.Event())
    assert detected == [] and "shown before" in w.results()[-1].timings

    # without a cancel of its own (no page on show to end it) nothing is lettered ahead
    q = _pipeline(settings, "Job without a cancel")
    Window(q)._job_translate(sample_page.copy(), "Job without a cancel", "m", "English")
    assert len(q.shown_pages) == 0
