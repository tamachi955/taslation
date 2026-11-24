"""In which order the models load, and how long Ollama's model stays (``keep_alive`` on every request, `warm_up`): nothing
at the start unless the settings keep the model for good, which loads it before the OCR model on the command line
(``batch``, ``audit``) and while the OCR model loads in a thread of its own in the window (`_job_init`). Fakes stand in
for the OCR engine and Ollama. The load on demand itself: test_model_on_demand.py."""
from __future__ import annotations

import argparse
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_ollama import FakeOllama, free_port

from taslation import health, i18n, netguard
from taslation.config import ConfigError, Settings
from taslation.messages import Message
from taslation.ocr import charspot
from taslation.translate import OllamaTranslator, TranslationError
from taslation.translate.ollama import keep_alive_value, loaded_message
from taslation.ui import jobs

@pytest.fixture
def ollama():
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            yield fake
        finally:
            netguard.uninstall()


def _chats(fake: FakeOllama) -> list[dict]:
    return [r for r in fake.requests if "messages" in r]


def test_keep_alive_in_ollama_s_own_format():
    assert keep_alive_value("30m") == "30m" and keep_alive_value(" 1h30m ") == "1h30m" and keep_alive_value("-1m") == "-1m"
    assert keep_alive_value("-1") == -1 and keep_alive_value("0") == 0 and keep_alive_value("600") == 600
    assert keep_alive_value("1.5") == 1.5 and keep_alive_value(-1) == -1 and keep_alive_value(90.0) == 90.0
    for bad in ("30 minutes", "", "forever", "5x", True, None):
        with pytest.raises(ValueError):
            keep_alive_value(bad)


def test_every_request_carries_keep_alive(ollama):
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    assert tr.keep_alive == "5m"  # the default, as the settings'
    tr.translate_page(["こんにちは", "さようなら"])
    tr.translate_page(["こんにちは"], on_item=lambda i, t: None)  # streamed
    tr.warm_up()
    chats = _chats(ollama)
    assert len(chats) == 3 and all(r["keep_alive"] == "5m" for r in chats)
    for setting, sent in (("-1", -1), ("0", 0), ("2h", "2h"), (600, 600)):
        OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0, keep_alive=setting).translate_page(["はい"])
        assert ollama.requests[-1]["keep_alive"] == sent  # "-1" as the number Ollama reads as "never unload"


def test_warm_up_is_a_one_token_request_and_returns_how_long_it_took(ollama):
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0, num_ctx=16384, keep_alive="45m")
    ollama.before_headers = 0.3  # the model loading
    seconds = tr.warm_up()
    assert 0.3 <= seconds < 5.0
    (req,) = _chats(ollama)
    assert req["model"] == "qwen3.5:4b" and req["stream"] is False and req["keep_alive"] == "45m"
    assert req["options"]["num_predict"] == 1 and req["options"]["num_ctx"] == 16384  # the size every request asks for
    assert [m["role"] for m in req["messages"]] == ["user"] and req["think"] is False and "format" not in req
    ollama.before_headers = 0.0
    tr.last_stats = {"eval_count": 5}
    tr.warm_up("gemma3:4b", "-1")
    assert ollama.requests[-1]["model"] == "gemma3:4b" and ollama.requests[-1]["keep_alive"] == -1
    assert tr.last_stats == {"eval_count": 5}  # a page's statistics are not a warm-up's
    assert tr.model == "qwen3.5:4b"
    tr0 = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0, num_ctx=0)
    tr0.warm_up()
    assert "num_ctx" not in ollama.requests[-1]["options"]  # the server's own, as for every request


def test_warm_up_fails_as_every_request_does(ollama):
    tr = OllamaTranslator(ollama.url, "missing:1b", timeout=10.0)
    ollama.chat_error = (404, {"error": "model 'missing:1b' not found"})
    with pytest.raises(TranslationError) as info:
        tr.warm_up()
    assert info.value.message.code == "health.chosen_model_missing"
    port = free_port()
    netguard.install(allowed_ports={port}, audit_hook=False)
    down = OllamaTranslator(f"http://127.0.0.1:{port}", "qwen3.5:4b", timeout=10.0)
    with pytest.raises(TranslationError) as info:
        down.warm_up()
    assert info.value.message.code == "ollama.unreachable"


def test_the_loaded_line():
    m = loaded_message("qwen3.5:4b", 3.4449)
    assert m.code == "ollama.loaded" and dict(m.params) == {"model": "qwen3.5:4b", "seconds": 3.4}
    assert str(m) == "Translator ready."


# ------------------------------------------------------------------------------------------ the settings
def test_the_settings_keep_the_model_loaded_for_thirty_minutes(tmp_path):
    s = Settings()
    assert s.ollama_keep_alive == "5m"
    s.validate()
    example = Settings.from_toml(Path(__file__).resolve().parent.parent / "taslation.toml.example")
    assert example.ollama_keep_alive == "5m"
    for good in ("-1", "0", "2h", "90s", "1h30m"):
        Settings(ollama_keep_alive=good).validate()
    with pytest.raises(ConfigError):
        Settings(ollama_keep_alive="half an hour").validate()
    path = tmp_path / "taslation.toml"
    path.write_text("ollama_keep_alive = -1\n", encoding="utf-8")
    s = Settings.from_toml(path)
    assert s.ollama_keep_alive == "-1" and keep_alive_value(s.ollama_keep_alive) == -1
    s.validate()


def test_settings_of_the_old_ocr_are_dropped_quietly(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text('ocr_device = "cuda"\nocr_batch = 4\nocr_precision = "fp16"\nocr_reader = "auto"\n'
                    'ocr_reread_below = 0.8\nocr_upscale = 2\nocr_upscale_below = 48\n', encoding="utf-8")
    Settings.from_toml(path).validate()


# ------------------------------------------------------------------------------------------ the window's start
class Start:
    """The parts of the App that the start job uses; what they post is kept, and the order of what they do is recorded
    (``order``)."""

    _job_init = jobs.JobsMixin._job_init
    _judge_gpu = jobs.JobsMixin._judge_gpu
    _watch_loads = jobs.JobsMixin._watch_loads
    _warm_page_models = jobs.JobsMixin._warm_page_models
    _revive_ollama = jobs.JobsMixin._revive_ollama
    _restart_ollama = jobs.JobsMixin._restart_ollama
    _translator_status = jobs.JobsMixin._translator_status
    _loaded_line = jobs.JobsMixin._loaded_line
    _tell_protection = jobs.JobsMixin._tell_protection
    _post = jobs.JobsMixin._post

    def __init__(self, settings: Settings, setup, order: list):
        self.settings = settings
        self._events: queue.Queue = queue.Queue()
        self._setup = setup
        self.order = order
        self._status_render = None
        self.translator = None
        self.pipeline = None

    def _check_setup(self):
        self.order.append("health")
        return self._setup

    def events(self) -> list[tuple[str, dict]]:
        """What was posted, in order, without the "models_loading" indicator (on and off, its off from a thread of its
        own: tests/test_model_at_start.py follows it)."""
        out = []
        while not self._events.empty():
            event = self._events.get_nowait()
            if event[0] != "models_loading":
                out.append(event)
        return out


class StubEngine:
    def __init__(self, order: list, loading: threading.Event | None = None):
        order.append("ocr")
        if loading is not None:
            loading.set()


def worker(order: list) -> list:
    """What the start did in the worker, in its order: the OCR model loads in a thread of its own."""
    return [step for step in order if step != "ocr"]


@pytest.fixture
def start(monkeypatch, tmp_path):
    """A stand-in and its recorded order, with the warm-up, the OCR engine and the pipeline standing in."""
    import taslation.ocr
    import taslation.pipeline

    order: list = []
    loading = threading.Event()

    def warm_up(self, model=None, keep_alive=None, timeout=None):
        order.append(("warm-up", model))
        warm_up.overlapped = loading.wait(5.0)  # the OCR model loads while Ollama loads its model
        if getattr(warm_up, "fails", False):
            raise TranslationError(Message("ollama.timeout", seconds=300.0))
        return 3.4

    monkeypatch.setattr(OllamaTranslator, "warm_up", warm_up)
    monkeypatch.setattr(taslation.ocr, "Readers", lambda path, threads=0: StubEngine(order, loading))
    monkeypatch.setattr(jobs, "ollama_compute", lambda log=None: "")  # (not this machine's Ollama log)
    monkeypatch.setattr(taslation.pipeline, "Pipeline",
                        lambda settings, ocr=None, translator=None: SimpleNamespace(ocr=ocr, translator=translator))

    def make(setup, **settings) -> Start:
        settings.setdefault("ollama_keep_alive", "-1")  # the settings that load the model at the start
        settings.setdefault("load_model_at_start", False)  # (the start as before it: tests/test_model_at_start.py)
        return Start(Settings(state_dir=tmp_path / "state", **settings), setup, order)

    make.order = order
    make.warm_up = warm_up
    make.loading = loading
    return make


def test_the_start_checks_then_loads_ollama_s_model_while_the_ocr_model_loads(start):
    w = start(([], ["qwen3.5:4b", "gemma3:4b"]))
    w._job_init()
    assert worker(start.order) == ["health", ("warm-up", "qwen3.5:4b")] and start.order.count("ocr") == 1
    assert start.warm_up.overlapped  # the OCR model loaded while Ollama loaded its model
    events = w.events()
    kinds = [k for k, _d in events]
    assert kinds == ["health", "status", "status", "models", "ready", "compute", "status"]
    assert events[1][1] == {"key": "Getting the translator ready..."}
    assert events[2][1]["key"].startswith("Getting the Japanese reader ready")
    line = events[-1][1]["text"]  # after "ready": what loaded where, before what the line said then
    w._status_render = lambda: "Ready."
    assert line() == "Translator ready.  Ready."
    w._status_render = lambda: "something else"  # taken at the first look: what the line said when it was ready
    assert line().endswith("Ready.")
    assert w.translator.keep_alive == -1 and w.pipeline.ocr is not None


def test_the_viewer_chooser_waits_for_the_starts_judgement_of_the_gpu_and_never_comes_after_quit(start, monkeypatch):
    seen = []
    judge = jobs.JobsMixin._judge_gpu

    def judging(self, asks_ollama=True):
        seen.append(getattr(self, "_start_judged", None))  # (not yet while the GPU's memory is judged)
        return judge(self, asks_ollama)

    monkeypatch.setattr(Start, "_judge_gpu", judging)
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    assert seen == [None] and w._start_judged is True  # (`see_menu.chooser_tick` may bring it now)
    monkeypatch.setattr(Start, "_judge_gpu", lambda self, asks_ollama=True: False)  # Quit at the GPU's dialog
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    assert w._start_judged is False


def test_the_start_loads_nothing_of_ollama_unless_the_settings_keep_the_model(start):
    for setting in ("5m", "30m", "0"):
        start.order.clear()
        w = start(([], ["qwen3.5:4b"]), ollama_keep_alive=setting)
        w._job_init()
        assert worker(start.order) == ["health"] and start.order.count("ocr") == 1
        assert not any("Loading Ollama" in str(d.get("key", "")) or "text" in d for _k, d in w.events())


def test_an_install_with_one_reader_says_so_in_that_line_and_is_no_error(start, monkeypatch):
    import taslation.ocr

    monkeypatch.setattr(taslation.ocr, "Readers", lambda path, threads=0: SimpleNamespace(missing=["manga-ocr-nar-small"]))
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    events = w.events()
    assert [k for k, _d in events] == ["health", "status", "status", "models", "ready", "compute", "status"]
    w._status_render = lambda: "Ready."
    line = events[-1][1]["text"]()
    assert "basic form" in line and "install.cmd" in line and line.endswith("Ready.")


def test_the_loaded_line_in_the_window_s_language(start):
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    line = w.events()[-1][1]["text"]
    try:
        i18n.set_language("ja")
        w._status_render = lambda: "準備完了"
        text = line()
    finally:
        i18n.set_language("en")
    assert "翻訳の準備ができました。" in text
    assert text.endswith("  準備完了")


def test_nothing_is_warmed_while_ollama_is_down(start):
    w = start(([Message("health.ollama_down", url="http://127.0.0.1:11434")], None))
    w._job_init()
    assert worker(start.order) == ["health"] and start.order.count("ocr") == 1
    events = w.events()
    assert not any(d.get("key", "").startswith("Getting the translator") for _k, d in events)


def test_the_model_the_window_falls_back_to_is_warmed(start):
    # a model set by hand that Ollama lacks: the first one Ollama has, as before
    w = start(([Message("health.other_model", wanted="qwen3.5:4b", used="gemma3:4b")], ["gemma3:4b"]),
              ollama_model="qwen3.5:4b")
    w._job_init()
    assert worker(start.order) == ["health", ("warm-up", "gemma3:4b")] and "ocr" in start.order


def test_a_failed_warm_up_still_loads_the_ocr_model(start):
    start.warm_up.fails = True
    try:
        w = start(([], ["qwen3.5:4b"]))
        w._job_init()
    finally:
        start.warm_up.fails = False
    assert worker(start.order) == ["health", ("warm-up", "qwen3.5:4b")] and "ocr" in start.order
    assert not any("text" in d for _k, d in w.events())  # nothing loaded to say


def test_a_missing_ocr_model_is_said_and_the_start_goes_on(start, monkeypatch):
    import taslation.ocr
    from taslation.ocr import ModelNotInstalled

    def missing(path, threads=0):
        start.order.append("ocr")
        raise ModelNotInstalled(Message("ocr.model_missing", path="x", missing="config.json", command="y"))

    monkeypatch.setattr(taslation.ocr, "Readers", missing)
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    events = w.events()
    assert ("error" in [k for k, _d in events]) and [k for k, _d in events][-3:-1] == ["ready", "compute"]
    w._status_render = None
    assert events[-1][1]["text"]() == "Translator ready."


class Reader:
    """One reader of the OCR model: what it was given to read, and in which thread, is kept."""

    def __init__(self, read: list, name: str, fails: bool = False):
        self.seen, self.name, self.fails = read, name, fails

    def read(self, image):
        self.seen.append((self.name, image.size, threading.current_thread().name))
        if self.fails:
            raise RuntimeError("no first read")
        return ""


def test_the_ocr_model_loads_beside_the_setup_check_and_each_reader_reads_a_crop_before_the_pipeline(start, monkeypatch):
    """The OCR model's load and the setup check wait here for each other: one after the other, the start would wait
    in vain. A first read that fails is no error: the first page meets what is wrong, as ever."""
    import taslation.ocr
    import taslation.pipeline

    loading, checked = threading.Event(), threading.Event()
    read: list = []

    def readers(path, threads=0):
        start.order.append("ocr")
        loading.set()
        assert checked.wait(5.0)  # the setup is checked meanwhile
        return SimpleNamespace(missing=[], charspot=Reader(read, "charspot"), _nar=Reader(read, "nar"),
                               _cpt=Reader(read, "cpt", fails=True))

    monkeypatch.setattr(taslation.ocr, "Readers", readers)
    monkeypatch.setattr(taslation.pipeline, "Pipeline", lambda settings, ocr=None, translator=None:
                        start.order.append(("pipeline", len(read))) or SimpleNamespace(ocr=ocr, translator=translator))
    w = start(([], ["qwen3.5:4b"]), ollama_keep_alive="5m")
    check = w._check_setup

    def check_setup():
        assert loading.wait(5.0)  # the OCR model loads meanwhile
        checked.set()
        return check()

    w._check_setup = check_setup
    w._job_init()
    assert worker(start.order) == ["health", ("pipeline", 3)]  # the pipeline after the readers' first reads
    assert read == [(name, (32, 32), "taslation-load-ocr") for name in ("charspot", "nar", "cpt")]
    assert w.pipeline.ocr is not None and not getattr(w, "_ocr_failed", False)
    events = w.events()
    assert [k for k, _d in events][:5] == ["health", "status", "models", "ready", "compute"]
    assert events[1][1]["key"].startswith("Getting the Japanese reader ready") and events[3][1] == {"ocr": True}


def test_a_page_asked_for_as_the_window_opens_waits_for_the_ocr_model_loaded_once(start, monkeypatch):
    import taslation.ocr

    release, checked = threading.Event(), threading.Event()
    made: list = []

    def readers(path, threads=0):
        made.append(threading.current_thread().name)
        assert release.wait(5.0)
        return SimpleNamespace(missing=["manga-ocr-nar-small"])

    monkeypatch.setattr(taslation.ocr, "Readers", readers)
    w = start(([], ["qwen3.5:4b"]), ollama_keep_alive="5m")
    check = w._check_setup
    w._check_setup = lambda: (checked.set(), check())[1]
    w._jobs = queue.Queue()
    pages: list = []
    w._jobs.put(w._job_init)
    w._jobs.put(lambda: pages.append(w.pipeline.ocr))  # a page asked for while the start runs
    threading.Thread(target=jobs.JobsMixin._worker_loop, args=(w,), daemon=True).start()
    assert checked.wait(5.0)
    time.sleep(0.3)  # Ollama started, the setup checked: the start waits for the OCR model, and the page with it
    assert pages == [] and "ready" not in [k for k, _d in w.events()]
    release.set()
    for _ in range(500):
        if pages:
            break
        time.sleep(0.01)
    assert len(pages) == 1 and pages[0].missing == ["manga-ocr-nar-small"]
    assert made == ["taslation-load-ocr"]  # loaded once, in its own thread
    assert "ready" in [k for k, _d in w.events()]


def test_an_ocr_model_that_cannot_be_loaded_is_said_as_ever_and_the_window_starts_without_it(start, monkeypatch):
    import taslation.ocr

    def broken(path, threads=0):
        start.order.append("ocr")
        raise RuntimeError("weights damaged")

    monkeypatch.setattr(taslation.ocr, "Readers", broken)
    w = start(([], ["qwen3.5:4b"]), ollama_keep_alive="5m")
    w._ocr_failed = False
    w._job_init()
    events = w.events()
    assert [k for k, _d in events][:6] == ["health", "status", "error", "models", "ready", "compute"]
    error = events[2][1]
    assert error["cached_note"] is True and "RuntimeError: weights damaged" in str(error["message"])
    assert events[4][1] == {"ocr": False} and w._ocr_failed and w.pipeline.ocr is None


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    yield
    netguard.uninstall()


def test_the_command_line_loads_ollama_s_model_before_the_ocr_model(cli_env, monkeypatch, tmp_path, capsys):
    import taslation.ocr
    from taslation import cli

    order: list = []
    engine = SimpleNamespace()
    imported = threading.Event()
    monkeypatch.setattr(charspot, "import_libraries", imported.set)
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: order.append("health") or ["qwen3.5:4b"])
    monkeypatch.setattr(OllamaTranslator, "warm_up",
                        lambda self, model=None, keep_alive=None, timeout=None:
                        order.append(("warm-up", model, imported.wait(5.0))) or 2.5)
    monkeypatch.setattr(taslation.ocr, "Readers", lambda path, threads=0: order.append("ocr") or engine)
    s = Settings(state_dir=tmp_path / "state")
    cli.build_pipeline(s, "ollama", None, warm_first=True)
    # (Ollama's models are looked at to choose the model: "health"; the order of the loads is what counts)
    loads = lambda: [x for x in order if x != "health"]  # noqa: E731
    assert loads() == ["ocr"]  # the settings as they come: the first request loads it
    order.clear()
    s = Settings(state_dir=tmp_path / "state", ollama_keep_alive="-1")
    pipeline = cli.build_pipeline(s, "ollama", None, warm_first=True)
    assert loads() == [("warm-up", "qwen3.5:4b", True), "ocr"] and pipeline.ocr is engine
    assert order[0] == "health"
    err = capsys.readouterr().err
    assert "note: Translator ready." in err
    order.clear()
    cli.build_pipeline(s, "ollama", None)  # the other commands: no warm-up
    assert loads() == ["ocr"]
    order.clear()
    cli.build_pipeline(s, "echo", None, warm_first=True)  # no Ollama: nothing to warm
    assert order == ["ocr"]
    order.clear()
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: order.append("health") or None)
    cli.build_pipeline(s, "ollama", None, warm_first=True)  # Ollama down: the OCR model all the same
    assert loads() == ["ocr"] and "health" in order
    order.clear()
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: order.append("health") or ["gemma3:4b"])
    cli.build_pipeline(s, "ollama", None, warm_first=True)  # the language's model missing: the command says so
    assert loads() == ["ocr"] and "health" in order


class _Built(Exception):
    pass


def test_audit_loads_in_that_order(cli_env, monkeypatch, tmp_path):
    from taslation import cli

    seen: list[dict] = []

    def build(settings, translator_kind="ollama", book=None, with_ocr=True, series=None, warm_first=False):
        seen.append({"kind": translator_kind, "warm_first": warm_first})
        raise _Built()

    monkeypatch.setattr(cli, "build_pipeline", build)
    monkeypatch.setattr(cli, "_notice_once", lambda settings: None)
    monkeypatch.setattr("taslation.capture.enable_dpi_awareness", lambda: None)  # the test process stays as it is
    s = Settings(state_dir=tmp_path / "state")
    netguard.install(audit_hook=False)  # audit lists the calls the guard let through
    with pytest.raises(_Built):
        cli.cmd_audit(argparse.Namespace(image=tmp_path / "page.png", translator="ollama"), s)
    assert seen == [{"kind": "ollama", "warm_first": True}]
