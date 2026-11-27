"""A page job that is cancelled (a new page settled, or Stop) stops at the next stage boundary and inside the long
loops of a stage: between the detectors, before the other readers read a region, while the rooms of the translations
are measured, while they are reviewed, and between the regions of the render. Whatever it stops in leaves the cache
and the session's memos as they would be had it stopped a moment earlier: a page unit is stored whole or not at all,
an erase kept is a whole one, and nothing goes to the memo of the pages shown."""
from __future__ import annotations

import threading

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr

from taslation import pipeline as pipeline_mod
from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator


def _pipeline(settings, book="Stopped", ocr=None, translator=None):
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return Pipeline(settings, ocr=ocr or FakeOcr(), translator=translator or DictTranslator(EN_TEXTS), cache=cache)


def test_a_cancel_between_the_detectors_reads_nothing(sample_page, settings):
    assert settings.detect_dark_bubbles  # (a second detector to stop before)
    cancel = threading.Event()
    p = _pipeline(settings)
    real, ran = p.detector.detect, []

    def detect(rgb, inverted=False, scale=1.0):
        ran.append(inverted)
        cancel.set()  # the page changed while the first detector looked at it
        return real(rgb, inverted=inverted, scale=scale)

    p.detector.detect = detect
    events: list[str] = []
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel, events=lambda kind, data: events.append(kind))
    assert ran == [False]  # the dark bubbles were never looked for
    assert p.ocr.calls == 0 and p.translator.calls == []
    assert len(p.cache) == 0 and not p.cache.path.exists()
    assert "regions" not in events and "page" not in events


def test_a_cancel_before_the_other_readers_read_a_region(sample_page, settings):
    cancel = threading.Event()
    settled: list[int] = []
    p = _pipeline(settings)
    real_settle, real_verdict = p._settle, p._verdict

    def verdict(*args, **kwargs):
        cancel.set()  # Stop pressed while the first region's reading is judged
        return real_verdict(*args, **kwargs)

    def settle(*args, **kwargs):
        settled.append(1)
        return real_settle(*args, **kwargs)

    p._verdict, p._settle = verdict, settle
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel)
    assert settled == [] and p.translator.calls == []
    assert len(p.cache) == 0


def test_the_readers_are_asked_in_a_page_not_cancelled(sample_page, settings):
    """(the stop point above is on the path a page takes)"""
    p = _pipeline(settings)
    settled: list[int] = []
    real = p._settle
    p._settle = lambda *args, **kwargs: (settled.append(1), real(*args, **kwargs))[1]
    p.process(sample_page, use_cache=False)
    assert settled


def test_a_cancel_while_the_rooms_are_measured_asks_nothing(sample_page, settings, monkeypatch):
    cancel = threading.Event()
    real, measured = pipeline_mod.translation_room, []

    def room(*args, **kwargs):
        measured.append(1)
        cancel.set()
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline_mod, "translation_room", room)
    p = _pipeline(settings)
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel)
    assert measured == [1] and p.translator.calls == []
    assert len(p.cache) == 0 and not p.cache.path.exists()


def test_a_cancel_during_the_review_keeps_nothing_of_the_page(sample_page, settings):
    assert settings.readable_font_size  # (the review measures each translation)
    cancel = threading.Event()
    p = _pipeline(settings)
    real, measured = p.set_size, []

    def set_size(*args, **kwargs):
        measured.append(1)
        cancel.set()
        return real(*args, **kwargs)

    p.set_size = set_size
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
    assert len(p.translator.calls) == 1 and measured == [1]  # asked once, stopped at the second measure
    assert len(p.cache) == 0 and not p.cache.path.exists()  # not stored, so not saved
    assert len(p._context) == 0  # nor taken as context for the next page
    assert len(p.shown_pages) == 0


def test_a_cancel_in_the_render_keeps_the_page_stored_whole_and_whole_erases(sample_page, settings):
    """A cancel between two regions of the render: the page unit was stored and saved before (whole), the erase done
    is kept whole, the half-lettered page is shown nowhere and kept nowhere; shown again, the page comes out as a page
    from that cache comes out of a session that never stopped."""
    cancel = threading.Event()
    p = _pipeline(settings, book="Stopped")
    real = p._erase_kept

    def erase_then_stop(out, region, key):
        background = real(out, region, key)
        cancel.set()  # the page changed while the first region was erased
        return background

    p._erase_kept = erase_then_stop
    events: list[str] = []
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel, events=lambda kind, data: events.append(kind))
    assert "page" not in events
    assert len(p.erased_regions) == 1  # the one erase done, whole
    assert len(p.shown_pages) == 0
    assert len(p.cache) == 1 and p.cache.path.exists()  # stored, and saved, before the render began
    stopped_page = p.cache.pages[0]
    saved = CacheStore(settings.cache_dir).open("Stopped", "fake")
    assert [b.text for b in saved.pages[0].bubbles] == [b.text for b in stopped_page.bubbles]

    # the same page from a session that never stopped
    q = _pipeline(settings, book="Never stopped")
    q.process(sample_page)
    assert [b.text for b in q.cache.pages[0].bubbles] == [b.text for b in stopped_page.bubbles]
    assert [b.poly for b in q.cache.pages[0].bubbles] == [b.poly for b in stopped_page.bubbles]
    fresh = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS),
                     cache=CacheStore(settings.cache_dir).open("Never stopped", "fake"))
    expected = np.asarray(fresh.process(sample_page).image)

    p._erase_kept = real
    again = p.process(sample_page)  # from the cache, the first erase from the session's memo
    assert again.cache_hits == 1 and not again.error
    assert np.array_equal(np.asarray(again.image), expected)


def test_a_cancel_in_the_render_of_a_page_from_the_cache_changes_nothing(sample_page, settings):
    p = _pipeline(settings)
    p.process(sample_page)
    stamp = p.cache.path.stat().st_mtime_ns
    p.shown_pages.clear()
    p.erased_regions.clear()
    cancel = threading.Event()
    real = p._erase_kept

    def erase_then_stop(out, region, key):
        background = real(out, region, key)
        cancel.set()
        return background

    p._erase_kept = erase_then_stop
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel)
    assert len(p.shown_pages) == 0 and len(p.erased_regions) == 1
    assert len(p.cache) == 1 and p.cache.path.stat().st_mtime_ns == stamp
