"""Ollama's model in GPU memory only while it is needed (`OllamaTranslator.ensure_loaded`, `release`, `gpu_share`): loaded
by the first request that wants it, never for a page in the cache, released at the end of a batch and at the window's
close, kept for good with ``keep_alive`` "-1"; a late load checked, and the pipeline's GPU models let go before it. A
fake Ollama keeps the model as the real one does."""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from fake_ollama import FakeOllama, free_port
from helpers import FakeOcr

from taslation import i18n, netguard
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.message_texts import catalog
from taslation.messages import Cancelled, Message
from taslation.pipeline import Pipeline
from taslation.translate import OllamaTranslator, TranslationError
from taslation.translate import ollama as ollama_module
from taslation.translate.ollama import never_unloads, partly_on_gpu, same_model, unloads_at_once
from taslation.ui import jobs
from taslation.ui.dialogs import caches
from taslation.ui.progress import progress_line, reads_page

MODEL = "qwen3.5:4b"


@pytest.fixture
def ollama():
    with FakeOllama() as fake:
        fake.tracks_loads = True
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            yield fake
        finally:
            netguard.uninstall()


def _english(items: list[dict], _request: dict) -> str | None:
    """A reply a page keeps: the fake's usual one holds the Japanese, a line left untranslated to the reply gates."""
    return json.dumps({"translations": [{"id": it["id"], "text": f"Line {it['id']} in English."} for it in items]}) \
        if items else None


def _translator(fake: FakeOllama, keep_alive="5m", **kw) -> tuple[OllamaTranslator, list]:
    said: list = []
    tr = OllamaTranslator(fake.url, MODEL, timeout=10.0, keep_alive=keep_alive, **kw)
    tr.on_status = said.append
    return tr, said


def _warm_ups(fake: FakeOllama) -> list[dict]:
    return [r for r in fake.requests if r["messages"] and r["messages"][-1]["content"] == "Hi"]


def _unloads(fake: FakeOllama) -> list[dict]:
    return [r for r in fake.requests if not r["messages"]]


def _codes(said: list) -> list[str]:
    return [m.code for m in said]


# ---------------------------------------------------------------------------- the settings' words
def test_which_keep_alive_is_which():
    for forever in ("-1", -1, "-1m", "-1h"):
        assert never_unloads(forever)
    for not_forever in ("5m", "0", 0, 600, "2h"):
        assert not never_unloads(not_forever)
    for at_once in ("0", 0, 0.0, "0s", "0m"):
        assert unloads_at_once(at_once)
    for not_at_once in ("5m", "-1", 600, "10s", "1h30m"):
        assert not unloads_at_once(not_at_once)


def test_a_model_s_name_may_leave_out_its_tag():
    assert same_model("qwen3.5:4b", "qwen3.5:4b") and same_model("foo:latest", "foo")
    assert not same_model("foo:7b", "foo") and not same_model("qwen3.5:9b", "qwen3.5:4b")


def test_a_model_is_split_when_part_of_it_is_on_the_gpu():
    assert partly_on_gpu(0.55) and partly_on_gpu(0.98)
    assert not partly_on_gpu(1.0) and not partly_on_gpu(None)
    assert not partly_on_gpu(0.0)  # a machine with no GPU for Ollama, as it was


# ---------------------------------------------------------------------------- the first line that needs it
def test_nothing_is_loaded_until_a_line_needs_translating_and_the_load_is_said(ollama):
    tr, said = _translator(ollama)
    assert ollama.loaded == set() and ollama.requests == []
    assert tr.translate_page(["はい"]) == ["T:はい"]
    assert ollama.loaded == {MODEL} and ollama.loads == 1
    assert _codes(said) == ["ollama.loading", "ollama.loaded"]
    assert said[0].params["model"] == MODEL
    assert ollama.requests[0]["options"]["num_predict"] == 1 and ollama.requests[0]["keep_alive"] == "5m"


def test_a_model_that_is_loaded_is_not_loaded_again_and_the_requests_keep_it(ollama):
    tr, said = _translator(ollama)
    for page in ("一", "二", "三"):
        tr.translate_page([page])
    assert ollama.loads == 1 and len(_warm_ups(ollama)) == 1 and len(said) == 2
    assert all(r["keep_alive"] == "5m" for r in ollama.requests)  # each one starts the idle time again


def test_after_the_idle_time_the_next_line_loads_it_again(ollama, monkeypatch):
    tr, said = _translator(ollama)
    tr.translate_page(["一"])
    ollama.loaded.clear()  # Ollama's keep_alive has run out ...
    # ... minutes after the request: long past the time a model that answered counts as loaded (`PS_RECHECK_S`)
    monkeypatch.setattr(ollama_module, "PS_RECHECK_S", 0.0)
    tr._answered(tr.model)
    tr.translate_page(["二"])
    assert ollama.loads == 2
    assert _codes(said) == ["ollama.loading", "ollama.loaded"] * 2


def test_a_page_in_the_cache_never_loads_it(ollama, sample_page, settings, monkeypatch):
    ollama.answer = _english
    cache = CacheStore(settings.cache_dir).open("Book", MODEL)
    translator, _said = _translator(ollama)
    first = Pipeline(settings, ocr=FakeOcr(), translator=translator, cache=cache)
    first.process(sample_page)
    assert ollama.loads == 1
    translator.release()
    ollama.requests.clear()
    result = first.process(sample_page)
    assert result.cache_hits > 0 and ollama.requests == [] and ollama.loaded == set()


def test_a_translator_set_to_unload_after_every_request_is_left_to_it(ollama):
    tr, said = _translator(ollama, keep_alive="0")
    tr.translate_page(["はい"])
    assert _warm_ups(ollama) == [] and said == []


def test_a_load_may_take_longer_than_a_request(ollama, monkeypatch):
    tr, said = _translator(ollama)
    tr.timeout = 0.3  # a reader's short request timeout
    ollama.before_first = 0.6  # the model comes up after that time
    cancel = threading.Event()
    seen: list[float] = []
    real = tr.warm_up

    def warm_up(model=None, keep_alive=None, timeout=None, cancel=None, on_slow=None):
        seen.append(timeout)
        ollama.before_first = 0.6
        out = real(model, keep_alive, timeout, cancel, on_slow)
        ollama.before_first = 0.0  # the request itself is quick
        return out

    monkeypatch.setattr(tr, "warm_up", warm_up)
    assert tr.translate_page(["はい"], cancel=cancel) == ["T:はい"]
    assert seen == [ollama_module.WARM_UP_TIMEOUT]
    assert _codes(said) == ["ollama.loading", "ollama.loaded"]


def test_stop_ends_a_load(ollama):
    tr, _said = _translator(ollama)
    ollama.before_first = 30.0
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    with pytest.raises(Cancelled):
        tr.translate_page(["はい"], cancel=cancel)
    assert ollama.gone.wait(3.0)


def test_a_slow_load_is_said_as_a_slow_request_is(ollama):
    tr, _said = _translator(ollama)
    tr.slow_after = 0.1
    ollama.before_first = 0.3
    slow: list[float] = []
    tr.translate_page(["はい"], on_slow=slow.append)
    assert slow


# ---------------------------------------------------------------------------- when Ollama fails
def test_the_model_missing_fails_with_the_same_message(ollama):
    tr, said = _translator(ollama)
    ollama.chat_error = (404, {"error": f"model '{MODEL}' not found"})
    with pytest.raises(TranslationError) as e:
        tr.translate_page(["はい"])
    assert e.value.message.code == "ollama.model_missing"
    assert _codes(said) == ["ollama.loading"]


def test_ollama_down_fails_with_the_same_message_and_is_revived_once(tmp_path):
    port = free_port()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        tr = OllamaTranslator(f"http://127.0.0.1:{port}", MODEL, timeout=5.0)
        asked: list = []
        tr.revive = lambda cancel: asked.append(cancel) or False
        with pytest.raises(TranslationError) as e:
            tr.translate_page(["はい"])
        assert e.value.message.code == "ollama.unreachable" and len(asked) == 1
    finally:
        netguard.uninstall()


def test_a_server_without_api_ps_translates_as_it_did(ollama):
    ollama.tracks_loads = False
    tr, said = _translator(ollama)
    assert tr.translate_page(["はい"]) == ["T:はい"]
    assert _warm_ups(ollama) == [] and said == []


def test_a_load_with_the_old_server_s_think_refusal(ollama):
    def refuse(_items, request):
        return (400, {"error": "think is not supported"}) if "think" in request else None

    ollama.answer = refuse
    tr, _said = _translator(ollama)
    assert tr.translate_page(["はい"]) == ["T:はい"]
    assert tr._supports_think is False


# ---------------------------------------------------------------------------- a late load is checked
def test_the_hook_runs_before_the_load_and_never_while_the_model_stays(ollama, settings):
    tr, _said = _translator(ollama)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    assert pipeline.gpu_releases == []  # empty until a GPU model registers
    order: list = []
    pipeline.gpu_releases.append(lambda: order.append(("detector", ollama.loads)))
    pipeline.gpu_releases.append(lambda: order.append(("inpainter", ollama.loads)))
    tr.translate_page(["一"])
    tr.translate_page(["二"])
    assert order == [("detector", 0), ("inpainter", 0)]


def test_a_release_that_fails_does_not_stop_the_others_or_the_page(ollama, settings):
    tr, _said = _translator(ollama)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    done: list = []

    def broken():
        raise RuntimeError("no")

    pipeline.gpu_releases.extend([broken, lambda: done.append(1)])
    assert tr.translate_page(["一"]) == ["T:一"] and done == [1]


def test_a_model_partly_on_the_cpu_gets_one_retry_after_a_release(ollama, settings):
    ollama.shares = [0.55, 1.0]
    tr, said = _translator(ollama)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    released: list = []
    pipeline.gpu_releases.append(lambda: released.append(ollama.loads))
    assert tr.translate_page(["一"]) == ["T:一"]
    assert ollama.loads == 2 and len(_unloads(ollama)) == 1 and released == [0, 1]
    assert _codes(said) == ["ollama.loading", "ollama.loaded"]  # all right in the end: nothing to worry the reader with


def test_a_model_that_stays_split_is_said_once_and_translates_all_the_same(ollama):
    ollama.shares = [0.55, 0.6, 0.6]
    tr, said = _translator(ollama)
    assert tr.translate_page(["一"]) == ["T:一"]
    assert ollama.loads == 2  # one retry, no more
    assert _codes(said) == ["ollama.loading", "ollama.loaded", "ollama.partly_on_gpu"]
    assert said[-1].params == {"model": MODEL, "percent": 60}
    tr.translate_page(["二"])
    assert ollama.loads == 2 and len(said) == 3  # it stays as it is


def test_a_machine_without_a_gpu_for_ollama_loads_once(ollama):
    ollama.shares = [0.0]
    tr, said = _translator(ollama)
    tr.translate_page(["一"])
    assert ollama.loads == 1 and _codes(said) == ["ollama.loading", "ollama.loaded"]


def test_gpu_share_reads_api_ps(ollama):
    ollama.shares = [0.5]
    tr, _said = _translator(ollama)
    assert tr.gpu_share() is None  # not loaded
    tr.warm_up()
    assert tr.gpu_share() == pytest.approx(0.5)
    ollama.tracks_loads = False
    assert tr.gpu_share() is None  # the server does not say


# ---------------------------------------------------------------------------- release
def test_release_unloads_what_this_translator_used_and_only_that(ollama):
    tr, _said = _translator(ollama)
    tr.release()
    assert ollama.requests == []  # nothing used: another program's model is left alone
    tr.translate_page(["一"])
    tr.release()
    assert ollama.loaded == set()
    (unload,) = _unloads(ollama)
    assert unload["model"] == MODEL and unload["keep_alive"] == 0 and unload["messages"] == []
    tr.release()
    assert len(_unloads(ollama)) == 1


def test_release_covers_the_model_the_box_changed_away_from(ollama):
    tr, _said = _translator(ollama)
    tr.translate_page(["一"])
    tr.model = "gemma3:4b"
    tr.translate_page(["二"])
    tr.release()
    assert ollama.loaded == set() and sorted(r["model"] for r in _unloads(ollama)) == ["gemma3:4b", MODEL]


def test_release_with_ollama_down_says_nothing_and_starts_nothing():
    port = free_port()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        tr = OllamaTranslator(f"http://127.0.0.1:{port}", MODEL, timeout=5.0)
        tr.revive = lambda cancel: pytest.fail("a release starts nothing")
        tr._used.add(MODEL)
        tr.release()
    finally:
        netguard.uninstall()


def test_never_unload_stays_as_it_was(ollama):
    tr, _said = _translator(ollama, keep_alive="-1")
    tr.warm_up()
    tr.translate_page(["一"])
    tr.release()
    assert ollama.loaded == {MODEL} and _unloads(ollama) == [] and ollama.requests[-1]["keep_alive"] == -1


def test_a_translator_without_a_model_has_nothing_to_release(settings):
    Pipeline(settings, ocr=FakeOcr(), translator=None).release_translator()
    Pipeline(settings, ocr=FakeOcr(), translator=SimpleNamespace()).release_translator()


# ---------------------------------------------------------------------------- a batch
# ---------------------------------------------------------------------------- the window
class Window:
    """The parts of the App that say a load and release the model."""

    _model_status = jobs.JobsMixin._model_status
    _release_model = jobs.JobsMixin._release_model
    _handle_event = jobs.JobsMixin._handle_event
    _warn_unasked = jobs.JobsMixin._warn_unasked
    reading = _over_on = False

    def __init__(self):
        self._progress: object = ""
        self._before_loading = None
        self._partial_said = False
        self._page_cancel = None
        self.pipeline = None
        self.events: list = []
        self.statuses: list = []

    def status(self, message):
        self.statuses.append(message)


@pytest.fixture
def window(monkeypatch):
    w = Window()
    w._handle_event = lambda kind, data: w.events.append((kind, data["text"]))  # the page's stage is its own test
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: w.events.append(("popup", text)))
    return w


def test_the_load_shows_as_the_page_s_stage_and_hands_back(window):
    translating = Message("pipeline.stage_translating", bubbles=3, translator="ollama")
    window._progress = translating
    window._model_status(Message("ollama.loading", model=MODEL))
    window._model_status(Message("ollama.loaded", model=MODEL, seconds=3.4))
    assert [e[1].code for e in window.events] == ["ollama.loading", "pipeline.stage_translating"]
    assert window.events[1][1] is translating and window._before_loading is None


def test_a_load_for_a_dialog_s_request_says_it_is_done(window):
    window._model_status(Message("ollama.loading", model=MODEL))
    done = Message("ollama.loaded", model=MODEL, seconds=3.4)
    window._model_status(done)
    assert window.statuses == [done] and window._progress == ""


def test_a_loading_message_shows_the_badge_and_reads_in_the_window_s_language():
    message = Message("ollama.loading", model=MODEL)
    assert reads_page(message)
    assert progress_line(message) == "Getting the translator ready..."
    try:
        i18n.set_language("ja")
        assert progress_line(message) == "翻訳の準備をしています..."
    finally:
        i18n.set_language("en")


def test_a_request_without_an_answer_is_said_in_the_status_line(window):
    translating = Message("pipeline.stage_translating", bubbles=3, translator="ollama")
    window._progress = translating
    window._model_status(Message("ollama.loading", model=MODEL))
    said = [Message("ollama.no_answer", seconds=30.0), Message("ollama.restarting")]
    for message in said:
        window._model_status(message)
    assert window.statuses == said and window._before_loading is translating  # (the load may still come)
    window._model_status(Message("ollama.not_answering"))
    assert window.statuses[-1].code == "ollama.not_answering" and window._before_loading is None
    assert [e[1].code for e in window.events] == ["ollama.loading"]  # (the page's stage is not touched)


def test_what_a_request_of_the_backlog_tells_is_said_in_the_status_line_only(window):
    """(a page turned past, read on behind the reader: ``behind``) Its load, the rule's sentences and its end go to the
    status line; the page on show's stage, the stage a load of the page's interrupted and its badge stay as they are."""
    translating = Message("pipeline.stage_translating", bubbles=3, translator="ollama")
    window._progress = translating
    said = [Message("ollama.loading", model=MODEL), Message("ollama.no_answer", seconds=30.0),
            Message("ollama.restarting"), Message("ollama.loading", model=MODEL),
            Message("ollama.loaded", model=MODEL, seconds=3.4), Message("ollama.not_answering")]
    for message in said:
        jobs.JobsMixin._handle_event(window, "model_status", {"message": message, "behind": True})
    assert window.statuses == said and window.events == []  # (no stage of the page's: `_handle_event` "progress")
    assert window._progress is translating and window._before_loading is None
    window._model_status(Message("ollama.loading", model=MODEL))  # (a load of the page's own shows as its stage)
    window._model_status(Message("ollama.no_answer", seconds=30.0), behind=True)
    assert window._before_loading is translating  # (and a sentence of the backlog's leaves what it interrupted)
    split = Message("ollama.partly_on_gpu", model=MODEL, percent=55)
    window._model_status(split, behind=True)
    window._model_status(split)
    assert [e[0] for e in window.events].count("popup") == 1  # (said in a popup once a session, whoever loaded)


def test_the_translator_tells_the_window_whether_its_request_is_the_backlogs(monkeypatch):
    from taslation import backlog

    posted: list = []
    w = SimpleNamespace(_post=lambda kind, **data: posted.append((kind, data)))
    loading = Message("ollama.loading", model=MODEL)
    jobs.JobsMixin._translator_status(w, loading)
    monkeypatch.setattr(backlog._STEP, "on", True, raising=False)  # (in a step of the backlog's, on its thread)
    jobs.JobsMixin._translator_status(w, loading)
    assert posted == [("model_status", {"message": loading, "behind": False}),
                      ("model_status", {"message": loading, "behind": True})]


def test_a_split_model_is_said_in_a_popup_once_a_session(window):
    message = Message("ollama.partly_on_gpu", model=MODEL, percent=55)
    window._model_status(message)
    window._model_status(message)
    assert len(window.statuses) == 2
    (popup,) = [e for e in window.events if e[0] == "popup"]
    assert "55%" in popup[1] and "graphics card" in popup[1]


def test_the_window_s_close_cancels_the_page_and_releases(ollama, settings, window):
    tr, _said = _translator(ollama)
    window.pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    window._page_cancel = threading.Event()
    tr.translate_page(["一"])
    window._release_model()
    assert window._page_cancel.is_set() and ollama.loaded == set()


def test_closing_a_window_that_never_finished_starting(window):
    window._release_model()  # no pipeline, no page: nothing to do


def test_nothing_in_the_window_re_arms_the_model():
    assert not hasattr(jobs.JobsMixin, "_start_keep_alive") and not hasattr(jobs.JobsMixin, "_keep_alive_tick")
    assert not hasattr(jobs, "KEEP_ALIVE_S")


def test_the_new_messages_are_in_every_language():
    from taslation.i18n import FEATURE_LANGUAGES

    assert FEATURE_LANGUAGES
    for lang in FEATURE_LANGUAGES:
        texts = catalog(lang)
        for code, fields in (("ollama.loading", ()), ("ollama.partly_on_gpu", ("{percent}",))):
            assert all(f in texts[code] for f in fields), (lang, code)
            assert texts[code] != catalog("en")[code], (lang, code)


@pytest.mark.parametrize("code", ["ollama.loading", "ollama.partly_on_gpu"])
def test_the_new_messages_are_plain_words(code):
    from test_plain_words import ALL, JARGON

    for lang in ALL:
        text = catalog(lang)[code].lower()
        assert not any(word in text for word in JARGON), (lang, code, text)


# ---------------------------------------------------------------------------- only Ollama
def test_a_load_and_a_release_go_nowhere_but_to_ollama_under_the_guard(ollama):
    with pytest.raises(TranslationError):
        OllamaTranslator("http://example.com:11434", MODEL)
    tr, _said = _translator(ollama)
    tr.translate_page(["一"])
    tr.release()
    state = netguard.state()
    assert state is not None and not state.blocked


def test_the_settings_default_is_the_translator_s():
    assert Settings().ollama_keep_alive == ollama_module.KEEP_ALIVE == "5m"
