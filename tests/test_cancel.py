"""Stop ends a request to the model at once: the streamed request looks at its cancel event between pieces and
while it waits for one, closes the connection (Ollama stops writing) and raises Cancelled; the pipeline stops
between regions and around the request; nothing of a cancelled page is cached. A request that says nothing for a
while calls on_slow once."""
from __future__ import annotations

import threading
import time

import pytest
from fake_ollama import FakeOllama
from helpers import EN_TEXTS, FakeOcr

from taslation import netguard
from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator, OllamaTranslator


@pytest.fixture
def server():
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)  # nothing but the fake may be reached
        try:
            yield fake
        finally:
            netguard.uninstall()


def _cancel_after(seconds: float) -> threading.Event:
    event = threading.Event()
    threading.Timer(seconds, event.set).start()
    return event


@pytest.mark.parametrize("chunked", [True, False])
def test_a_cancel_mid_stream_ends_the_request_within_a_second(server, chunked):
    server.chunked = chunked
    server.between, server.endless = 0.05, True  # the model keeps writing until the client goes away
    tr = OllamaTranslator(server.url, timeout=30)
    cancel = _cancel_after(0.4)
    started = time.monotonic()
    with pytest.raises(Cancelled):
        tr.translate_page(["こんにちは", "急いで"], cancel=cancel)
    assert time.monotonic() - started < 0.4 + 1.0
    assert server.gone.wait(2.0)  # the connection was closed: Ollama stops generating
    assert server.requests[-1]["stream"] is True


def test_a_cancel_while_the_model_loads_ends_the_wait(server):
    server.before_headers = 10.0  # nothing at all comes: the model is still loading
    tr = OllamaTranslator(server.url, timeout=30)
    cancel = _cancel_after(0.3)
    started = time.monotonic()
    with pytest.raises(Cancelled):
        tr.translate_page(["こんにちは"], cancel=cancel)
    assert time.monotonic() - started < 0.3 + 1.0
    assert server.gone.wait(2.0)


def test_a_cancel_set_before_the_request_sends_nothing(server):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        OllamaTranslator(server.url).translate_page(["こんにちは"], cancel=cancel)
    assert server.requests == []


def test_without_a_cancel_the_answer_comes_as_before(server):
    tr = OllamaTranslator(server.url)
    assert tr.translate_page(["こんにちは"], cancel=threading.Event()) == ["T:こんにちは"]  # streamed, not cancelled
    assert server.requests[-1]["stream"] is True
    assert tr.translate_page(["急いで"]) == ["T:急いで"] and server.requests[-1]["stream"] is False


@pytest.mark.parametrize("where", ["before_headers", "before_first"])
def test_on_slow_fires_once_when_nothing_comes(server, where):
    setattr(server, where, 0.8)
    tr = OllamaTranslator(server.url, slow_after=0.25)
    told: list[float] = []
    assert tr.translate_page(["こんにちは", "急いで"], on_slow=told.append) == ["T:こんにちは", "T:急いで"]
    assert len(told) == 1 and 0.25 <= told[0] < 0.8  # once, while it waited; the answer came all the same
    told.clear()
    server.before_headers = server.before_first = 0.0
    tr.translate_page(["本当に"], on_slow=told.append)
    assert told == []  # an answer that comes at once is not slow


def test_a_cancelled_page_is_not_cached(server, sample_page, settings):
    server.between, server.endless = 0.05, True
    cache = CacheStore(settings.cache_dir).open("Cancelled Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=OllamaTranslator(server.url, timeout=30), cache=cache)
    events: list[str] = []
    started = time.monotonic()
    with pytest.raises(Cancelled):
        pipeline.process(sample_page, cancel=_cancel_after(0.5), events=lambda kind, data: events.append(kind))
    assert time.monotonic() - started < 0.5 + 1.5
    assert len(cache) == 0 and not cache.path.exists()  # nothing of the page reached the cache
    assert "page" not in events  # no finished page: the window shows the viewer's picture again


def test_the_pipeline_stops_between_regions_while_reading(sample_page, settings):
    cancel = threading.Event()

    class StoppingOcr(FakeOcr):
        def read(self, image):
            if self.calls == 2:
                cancel.set()  # Stop pressed while the third region is read
            return super().read(image)

    ocr, tr = StoppingOcr(), DictTranslator(EN_TEXTS)
    with pytest.raises(Cancelled):
        Pipeline(settings, ocr=ocr, translator=tr).process(sample_page, use_cache=False, cancel=cancel)
    assert ocr.calls == 3 and tr.calls == []  # no further region read, the model never asked


def test_a_translator_that_takes_no_cancel_still_stops_the_page(sample_page, settings):
    cancel = threading.Event()

    class Old:  # an older translator: no cancel argument; the pipeline stops after its answer
        name = "old"

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            cancel.set()
            return [EN_TEXTS.get(t, "") for t in texts]

    cache = CacheStore(settings.cache_dir).open("Old", "fake")
    with pytest.raises(Cancelled):
        Pipeline(settings, ocr=FakeOcr(), translator=Old(), cache=cache).process(sample_page, cancel=cancel)
    assert len(cache) == 0


def test_a_cancel_reaches_the_simple_translators():
    from taslation.translate import EchoTranslator, NullTranslator

    cancel = threading.Event()
    cancel.set()
    for tr in (DictTranslator(EN_TEXTS), EchoTranslator(), NullTranslator()):
        with pytest.raises(Cancelled):
            tr.translate_page(["こんにちは"], cancel=cancel)
