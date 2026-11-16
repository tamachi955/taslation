"""A page on show in the window that has a line to translate loads the translator's model while the rest of it is read
(`pipeline.LoadAhead`, within `Pipeline.page_on_show`): one load (`OllamaTranslator.ensure_loaded` takes turns), the
GPU models let go once before it and warmed again only after it, the page's cancel ends it, and the page never lets go
of the worker with its load under way. A page from the cache, one with nothing to translate, a translator set to
unload at once and a page outside the window (a whole-book run, a command) load nothing ahead. A fake Ollama keeps the
model as the real one does; the translations are what they are without it."""
from __future__ import annotations

import json
import threading
import time

import numpy as np
import pytest
from fake_ollama import FakeOllama, free_port
from helpers import FakeOcr

from taslation import netguard
from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.pipeline import Pipeline
from taslation.translate import OllamaTranslator

MODEL = "qwen3.5:4b"
LOAD_S = 0.6  # how long the fake takes to load the model


@pytest.fixture
def ollama():
    with FakeOllama() as fake:
        fake.tracks_loads = True
        fake.warmed: list[float] = []  # when each load request came, and (below) when it was answered
        fake.answered: list[float] = []

        def answer(items, request):
            if request["messages"][-1]["content"] == "Hi":  # a warm-up: the load
                fake.warmed.append(time.monotonic())
                time.sleep(LOAD_S)
                fake.answered.append(time.monotonic())
                return None
            return json.dumps({"translations": [{"id": it["id"], "text": f"Line {it['id']} in English."}
                                                for it in items]}) if items else None

        fake.answer = answer
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            yield fake
        finally:
            netguard.uninstall()


class SlowOcr(FakeOcr):
    """Reads as the OCR does, a moment per line, and the other readers settle each line to translate after that
    (`Readers.settle`, most of a line's time); keeps when each read ended."""

    def __init__(self, texts=None, seconds=0.05):
        super().__init__(texts)
        self.seconds, self.ends = seconds, []

    def read(self, image):
        time.sleep(self.seconds / 5)
        text = super().read(image)
        self.ends.append(time.monotonic())
        return text

    def settle(self, crop, reading):
        time.sleep(self.seconds)
        self.ends.append(time.monotonic())
        return reading


def _pipeline(settings, url, book="Ahead", keep_alive="5m", ocr=None):
    tr = OllamaTranslator(url, MODEL, timeout=10.0, keep_alive=keep_alive)
    said: list = []
    tr.on_status = said.append
    cache = CacheStore(settings.cache_dir).open(book, MODEL)
    p = Pipeline(settings, ocr=ocr or SlowOcr(), translator=tr, cache=cache)
    released: list[float] = []
    real = p.release_gpu_models
    p.release_gpu_models = lambda: (released.append(time.monotonic()), real())[1]
    tr.before_load = p.release_gpu_models
    warmed: list[float] = []
    p.warm_page_models = lambda: warmed.append(time.monotonic())
    return p, said, released, warmed


def _no_load_thread() -> bool:
    return not any(t.name == "taslation-load-ahead" and t.is_alive() for t in threading.enumerate())


def test_the_model_loads_while_the_page_is_read(ollama, settings, sample_page):
    p, said, released, warmed = _pipeline(settings, ollama.url)
    with p.page_on_show():
        result = p.process(sample_page, cancel=threading.Event())
    assert not result.error and result.translated
    assert ollama.loads == 1 and len(ollama.warmed) == 1 and len(released) == 1
    assert ollama.warmed[0] < p.ocr.ends[-1]  # the load began while the page was read
    assert [m.code for m in said] == ["ollama.loading", "ollama.loaded"]
    assert len(warmed) == 1 and warmed[0] >= ollama.answered[0]  # the page models after the load, never during it
    assert _no_load_thread()

    # the same page, the model loaded the usual way (by the request): the very translations and page
    ollama.loaded.clear()
    q, _said, _released, _warmed = _pipeline(settings, ollama.url, book="As ever")
    as_ever = q.process(sample_page, cancel=threading.Event())
    assert [(r.bbox, r.translated_text, r.status) for r in as_ever.regions] == \
        [(r.bbox, r.translated_text, r.status) for r in result.regions]
    assert np.array_equal(np.asarray(as_ever.image), np.asarray(result.image))
    assert ollama.warmed[1] > q.ocr.ends[-1]  # (as ever: once the page was read)


def test_a_model_loaded_already_is_only_looked_at(ollama, settings, sample_page):
    p, said, released, warmed = _pipeline(settings, ollama.url)
    ollama.loaded.add(MODEL)
    with p.page_on_show():
        p.process(sample_page, cancel=threading.Event())
    assert ollama.warmed == [] and released == [] and warmed == [] and said == []


def test_a_cancel_ends_the_load_and_the_page(ollama, settings, sample_page):
    p, _said, _released, warmed = _pipeline(settings, ollama.url, ocr=SlowOcr(seconds=0.15))
    cancel = threading.Event()
    threading.Timer(0.6, cancel.set).start()  # the reader turns the page while the model loads
    started = time.monotonic()
    with pytest.raises(Cancelled):
        with p.page_on_show():
            p.process(sample_page, cancel=cancel)
    assert time.monotonic() - started < 0.6 + 1.5
    assert _no_load_thread() and warmed == [] and len(p.cache) == 0


def test_nothing_loads_ahead_for_a_page_from_the_cache_or_with_nothing_to_translate(ollama, settings, sample_page):
    p, _said, _released, _warmed = _pipeline(settings, ollama.url)
    p.process(sample_page, cancel=threading.Event())
    ollama.loaded.clear()
    ollama.warmed.clear()
    with p.page_on_show():
        cached = p.process(sample_page, cancel=threading.Event())
    assert cached.cache_hits and ollama.warmed == []

    blank, _s, _r, _w = _pipeline(settings, ollama.url, book="Blank", ocr=SlowOcr(texts=[""]))
    with blank.page_on_show():
        blank.process(sample_page, cancel=threading.Event())
    assert ollama.warmed == []  # no line to translate: no load


def test_outside_the_window_and_with_keep_alive_0_nothing_loads_ahead(ollama, settings, sample_page):
    p, _said, _released, _warmed = _pipeline(settings, ollama.url)
    loaders: list[str] = []
    real = p.translator.ensure_loaded
    p.translator.ensure_loaded = lambda *a, **k: (loaders.append(threading.current_thread().name), real(*a, **k))[1]
    p.process(sample_page, cancel=threading.Event())  # (a whole-book run, a command)
    assert loaders and "taslation-load-ahead" not in loaders

    q, said, released, _w = _pipeline(settings, ollama.url, book="At once", keep_alive="0")
    ollama.warmed.clear()
    with q.page_on_show():
        q.process(sample_page, cancel=threading.Event())
    assert ollama.warmed == [] and released == [] and said == []


def test_two_loads_at_once_are_one(ollama):
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0, keep_alive="5m")
    freed: list[int] = []
    tr.before_load = lambda: freed.append(1)
    threads = [threading.Thread(target=tr.ensure_loaded) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5.0)
    assert ollama.loads == 1 and len(ollama.warmed) == 1 and freed == [1]


def test_a_wait_for_another_load_ends_with_stop(ollama):
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0, keep_alive="5m")
    first = threading.Thread(target=tr.ensure_loaded)
    first.start()
    time.sleep(0.1)
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        tr.ensure_loaded(cancel)
    assert time.monotonic() - started < LOAD_S
    first.join(5.0)


def test_an_ollama_that_is_not_there_is_never_started_ahead(settings, sample_page):
    port = free_port()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        p, said, released, _w = _pipeline(settings, f"http://127.0.0.1:{port}")
        with p.page_on_show():
            result = p.process(sample_page, cancel=threading.Event())
    finally:
        netguard.uninstall()
    assert result.error and released == [] and said == [] and _no_load_thread()
