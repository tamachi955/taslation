"""A page read in the window is shown first and saved right after, on the same worker thread (`Pipeline.saves_held`,
`flush_saves`): one save for all its units, the very file a save at the storing writes. A page stopped after its
storing, one that fails after it, a cache taken away and the window's close all save it; one save at a time."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation import cache as cachemod
from taslation.cache import BookCache, CacheStore
from taslation.config import Settings
from taslation.messages import Cancelled
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import jobs


def _spread(right: Image.Image, left: Image.Image) -> Image.Image:
    """Two pages side by side on a dark viewer: two page units, each stored on its own."""
    w, h = right.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(left, (0, 20))
    spread.paste(right, (w + 60, 20))
    return spread


def _pipeline(settings, book):
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)


def _on_disk(settings, book) -> list[tuple]:
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    return [(p.fingerprint, p.aspect, p.seq, p.incomplete, [(b.box, b.text, b.poly, b.flags) for b in p.bubbles])
            for p in cache.pages]


@pytest.fixture
def saves(monkeypatch) -> list[str]:
    """The books of the cache saves made, in order."""
    made: list[str] = []
    real = BookCache.save

    def save(self, merge=True):
        made.append(self.book)
        return real(self, merge)

    monkeypatch.setattr(BookCache, "save", save)
    return made


def test_a_held_save_writes_the_very_file_once_for_a_spread(sample_page, sample_page2, settings, saves):
    spread = _spread(sample_page, sample_page2)
    _pipeline(settings, "At once").process(spread)
    assert saves == ["At once", "At once"]  # as ever: a save per unit stored
    saves.clear()

    p = _pipeline(settings, "Held")
    with p.saves_held():
        result = p.process(spread)
    assert result.cache_misses == 2 and not result.error
    assert saves == [] and not p.cache.path.exists() and p.cache.dirty  # stored, not saved yet
    assert p.flush_saves() and saves == ["Held"]  # one save for the two units
    assert not p.cache.dirty and not p.flush_saves()  # nothing waits any more
    assert _on_disk(settings, "Held") == _on_disk(settings, "At once")


def test_a_page_stopped_after_its_storing_is_saved_before_the_stop_goes_on(sample_page, settings, saves):
    p = _pipeline(settings, "Stopped")
    cancel = threading.Event()
    real = p._erase_kept

    def erase_then_stop(out, region, key):
        background = real(out, region, key)
        cancel.set()  # stopped in the render: the page was stored
        return background

    p._erase_kept = erase_then_stop
    with pytest.raises(Cancelled):
        with p.saves_held():
            p.process(sample_page, cancel=cancel)
    assert saves == ["Stopped"] and not p.cache.dirty and len(_on_disk(settings, "Stopped")) == 1


def test_a_page_that_fails_after_its_storing_is_saved(sample_page, settings, saves):
    p = _pipeline(settings, "Failed")

    def broken(*_a, **_k):
        raise RuntimeError("the render failed (test)")

    p._render = broken
    with pytest.raises(RuntimeError):
        with p.saves_held():
            p.process(sample_page)
    assert saves == ["Failed"] and len(_on_disk(settings, "Failed")) == 1


def test_a_cache_taken_away_and_the_window_close_save_what_waits(sample_page, sample_page2, settings, saves):
    p = _pipeline(settings, "Taken away")
    with p.saves_held():
        p.process(sample_page)
    p.set_cache(None)  # (another book, or none)
    assert saves == ["Taken away"] and len(_on_disk(settings, "Taken away")) == 1

    q = _pipeline(settings, "Closed")
    with q.saves_held():
        q.process(sample_page2)
    assert saves == ["Taken away"]
    app_mod.last_save(q)  # the window closes before the job saved it
    assert saves == ["Taken away", "Closed"] and len(_on_disk(settings, "Closed")) == 1
    assert not q.flush_saves()  # saved: the job's own save has nothing left to do


def test_saves_outside_a_page_are_made_at_once(sample_page, settings, saves):
    p = _pipeline(settings, "Edits")
    result = p.process(sample_page)
    saves.clear()
    assert p.set_translation(result, result.translated[0], "A line the reader typed.")
    assert saves == ["Edits"]  # an edit is no page being read: saved as ever


def test_one_save_at_a_time(sample_page, settings):
    p = _pipeline(settings, "One at a time")
    p.process(sample_page)
    cache = p.cache
    cache.dirty = True
    done = threading.Event()
    with cache._save_lock:  # a save on the worker, as the window closes
        other = threading.Thread(target=lambda: (cache.save(), done.set()), daemon=True)
        other.start()
        time.sleep(0.2)
        assert not done.is_set()  # the close's save waits for it
    assert done.wait(5.0) and not cache.dirty


class Window:
    """What `_job_translate` needs of the window; the worker's other jobs are dropped."""

    _job_translate = jobs.JobsMixin._job_translate
    _say_failed_save = jobs.JobsMixin._say_failed_save
    _use_model = jobs.JobsMixin._use_model

    def __init__(self, pipeline, record):
        self.pipeline, self.record = pipeline, record
        self.translator = SimpleNamespace(model="m")
        self.settings = Settings()
        self._jobs = SimpleNamespace(put=lambda job: None)

    def _post(self, kind, **data):
        self.record.append(kind)

    def _ensure_cache(self, *_a):
        return True

    def _look_for_colophon(self, *_a):
        pass


def test_the_page_job_shows_the_page_then_saves_it(sample_page, settings, monkeypatch):
    order: list[str] = []
    real = BookCache.save
    monkeypatch.setattr(BookCache, "save", lambda self, merge=True: (order.append("saved"), real(self, merge))[1])
    p = _pipeline(settings, "Job")
    Window(p, order)._job_translate(sample_page, "Job", "m", "English", False, threading.Event())
    assert order.index("result") < order.index("saved") < order.index("translate_done")
    assert order.count("saved") == 1 and not p.cache.dirty and len(_on_disk(settings, "Job")) == 1

    # a full disk: said after the page, as ever
    order.clear()
    monkeypatch.setattr(cachemod, "write_atomic", lambda *_a, **_k: (_ for _ in ()).throw(OSError(28, "No space")))
    q = _pipeline(settings, "Full")
    Window(q, order)._job_translate(sample_page, "Full", "m", "English", False, threading.Event())
    assert [k for k in order if k in ("result", "saved", "status", "translate_done")] == \
        ["result", "saved", "status", "translate_done"]
    assert q.save_error and q.cache.dirty


def test_a_stopped_page_job_saves_what_it_stored(sample_page, settings, saves):
    p = _pipeline(settings, "Stopped job")
    cancel = threading.Event()
    real = p._erase_kept
    p._erase_kept = lambda out, region, key: (real(out, region, key), cancel.set())[0]
    order: list[str] = []
    Window(p, order)._job_translate(sample_page, "Stopped job", "m", "English", False, cancel)
    assert "page_cancelled" in order and "result" not in order
    assert saves == ["Stopped job"] and len(_on_disk(settings, "Stopped job")) == 1
