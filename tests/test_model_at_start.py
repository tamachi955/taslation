"""The translation model loaded at the window's start (``load_model_at_start``, on by default; `JobsMixin._job_init`,
`_load_at_start`, `OllamaTranslator.ensure_loaded` *quiet*): once, while the OCR model loads, without a word in the
status line, the page models warmed only after it; one load with the page that needs the model meanwhile (which then
says that it loads); nothing with the setting off (the first line loads it, as before), with ``ollama_keep_alive`` "0",
with Ollama down or the model missing; a load that fails says nothing; Release the model now waits for it and nothing
loads after it; the window's close ends it. And the setting's row on the Settings dialog's System page. Against a
stand-in Ollama for PLaMo: the machine's own Ollama is never asked anything."""
from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from taslation import netguard
from taslation.config import Settings
from taslation.i18n import FEATURE_LANGUAGES
from taslation.locales.features import start_and_stop as texts
from taslation.translate.models import PLAMO
from taslation.ui import gpu_release, jobs
from taslation.ui.dialogs import settings as dlg
from taslation.ui.dialogs import system_page

MODEL = PLAMO.ollama_name


class Server(ThreadingHTTPServer):
    """/api/generate (a load: no prompt; an unload: ``keep_alive`` 0; else a line) and /api/ps."""

    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _answer(self, payload: dict, text: str) -> None:
        last = {"response": text, "done": True, "done_reason": "stop"}
        if not payload.get("stream"):
            self._send(200, last)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        data = (json.dumps(last) + "\n").encode("utf-8")
        self.wfile.write(b"%x\r\n%s\r\n0\r\n\r\n" % (len(data), data))
        self.wfile.flush()

    def do_GET(self):
        server = self.server
        server.log.append(self.path)
        if self.path == "/api/ps":
            self._send(200, {"models": [{"name": n, "model": n, "size": 10, "size_vram": 10}
                                        for n in sorted(server.loaded)]})
        elif self.path == "/api/tags":
            self._send(200, {"models": [{"name": MODEL}]})
        else:
            self._send(200, {"version": "0.40-stand-in"})

    def do_POST(self):
        server = self.server
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        if payload.get("keep_alive") == 0:
            server.log.append("unload")
            server.loaded.discard(payload["model"])
            self._send(200, {"response": "", "done": True, "done_reason": "unload"})
            return
        if not payload.get("prompt"):
            server.log.append("load")
            server.load_began.set()
            if not server.go.wait(10.0):
                return
            if server.fail_loads:
                self._send(500, {"error": "the model could not be loaded"})
                return
            server.loaded.add(payload["model"])
            try:
                self._answer(payload, "")
            except OSError:  # (the client went: the window closed)
                pass
            return
        server.log.append("line")
        server.loaded.add(payload["model"])
        self._answer(payload, "A line.")


@pytest.fixture
def ollama():
    server = Server(("127.0.0.1", 0), Handler)
    server.log, server.loaded, server.fail_loads = [], set(), False
    server.load_began, server.go = threading.Event(), threading.Event()
    server.go.set()
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True).start()
    port = server.server_address[1]
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        yield server, f"http://127.0.0.1:{port}"
    finally:
        server.go.set()
        netguard.uninstall()
        server.shutdown()
        server.server_close()


class Pipeline:
    """The pipeline as the start makes it: the page models' warm-ups and releases are kept, with when they came."""

    def __init__(self, settings, ocr=None, translator=None, log=None):
        self.ocr, self.translator, self.log = ocr, translator, log
        self.layout = self.art_eraser = None
        translator.before_load = self.release_gpu_models

    def warm_page_models(self):
        self.log.append("warm page models")

    def release_gpu_models(self):
        self.log.append("release page models")

    def release_translator(self):
        self.translator.release()


class Window:
    """The parts of the App that the start, the close and Release the model now use; what they post is kept."""

    _init_flow_state = jobs.JobsMixin._init_flow_state
    _job_init = jobs.JobsMixin._job_init
    _load_at_start = jobs.JobsMixin._load_at_start
    wait_load_at_start = jobs.JobsMixin.wait_load_at_start
    _warm_page_models = jobs.JobsMixin._warm_page_models
    _revive_ollama = jobs.JobsMixin._revive_ollama
    _loaded_line = jobs.JobsMixin._loaded_line
    _tell_protection = jobs.JobsMixin._tell_protection
    _release_model = jobs.JobsMixin._release_model
    _post = jobs.JobsMixin._post

    def __init__(self, settings: Settings, models):
        self._init_flow_state()
        self.settings, self.models = settings, models
        self._events: queue.Queue = queue.Queue()
        self.translator = self.pipeline = None
        self.selected = object()  # a viewer is chosen: the page models may be warmed
        self._status_render = None

    def _check_setup(self):
        return [], self.models

    def events(self) -> list[tuple[str, dict]]:
        out = []
        while not self._events.empty():
            out.append(self._events.get_nowait())
        return out

    def model_lines(self) -> list[str]:
        return [d["message"].code for k, d in self.events() if k == "model_status"]

    def loaded(self) -> None:
        """The load at the start over (its thread ended)."""
        if self._start_load is not None:
            self._start_load.join(10.0)
            assert not self._start_load.is_alive()


@pytest.fixture
def window(ollama, monkeypatch, tmp_path):
    """make(**settings): a stand-in window whose start loads the OCR model in a thread of its own, and lets it end
    once the stand-in Ollama has had the load asked (or, without one, at once), so that the two overlap."""
    import taslation.ocr
    import taslation.pipeline

    server, url = ollama
    overlap = {"wait": 2.0}

    def readers(path, threads=0):
        server.load_began.wait(overlap["wait"])  # (the model's load is asked while the OCR model loads)
        server.log.append("ocr loaded")
        return SimpleNamespace(missing=[])

    monkeypatch.setattr(taslation.ocr, "Readers", readers)
    monkeypatch.setattr(taslation.pipeline, "Pipeline",
                        lambda settings, ocr=None, translator=None: Pipeline(settings, ocr, translator, server.log))
    monkeypatch.setattr(jobs, "ollama_compute", lambda log=None: "")

    def make(models=(MODEL,), overlap_wait=True, **settings) -> Window:
        overlap["wait"] = 2.0 if overlap_wait else 0.0
        s = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", ollama_url=url,
                     cache_enabled=False, art_erase="off", **settings)
        return Window(s, list(models) if models is not None else None)

    make.server = server
    return make


def _loads(server) -> int:
    return server.log.count("load")


# ------------------------------------------------------------------ the load at the start
def test_the_model_loads_once_at_the_start_beside_the_ocr_model_and_says_nothing(window):
    server = window.server
    w = window()
    assert w.settings.load_model_at_start is True  # (the default)
    w._job_init()
    w.loaded()
    assert _loads(server) == 1 and server.loaded == {MODEL}
    assert server.log.index("load") < server.log.index("ocr loaded")  # asked while the OCR model loaded
    assert "warm page models" in server.log  # warmed once the load was over (never during it: below)
    assert w.model_lines() == []  # nothing said: no "Loading the model", no "Loaded"
    asked = server.log.count("/api/ps")
    assert w.translator.translate_page(["一行目です。"]) == ["A line."]  # the first page: the model is there
    assert _loads(server) == 1 and server.log.count("/api/ps") == asked  # not loaded again, not even looked for


def test_a_page_that_needs_the_model_meanwhile_waits_for_that_load_and_says_so(window):
    server = window.server
    server.go.clear()  # the load takes its time
    w = window()
    w._job_init()  # (ready without waiting for the model)
    assert server.load_began.wait(5.0) and "ready" in [k for k, _d in w.events()]
    got = []
    page = threading.Thread(target=lambda: got.append(w.translator.translate_page(["一行目です。"])))
    page.start()
    time.sleep(0.4)
    assert not got and server.log.count("warm page models") == 0  # waits; and no page model takes the memory
    server.go.set()
    page.join(10.0)
    w.loaded()
    assert got == [["A line."]] and _loads(server) == 1  # one load for both
    assert w.model_lines() == ["ollama.loading", "ollama.loaded"]  # the page said the load as its own
    assert "warm page models" in server.log


def test_with_the_setting_off_the_start_is_as_before_and_the_first_line_loads_the_model(window):
    server = window.server
    w = window(load_model_at_start=False, overlap_wait=False)
    w._job_init()
    assert w._start_load is None and _loads(server) == 0 and server.loaded == set()
    assert "ocr loaded" in server.log and server.log.count("warm page models") == 1  # warmed at the start, as before
    assert w.translator.translate_page(["一行目です。"]) == ["A line."]
    assert _loads(server) == 1 and w.model_lines() == ["ollama.loading", "ollama.loaded"]


@pytest.mark.parametrize("keep_alive", ["0", "-1"])
def test_no_load_of_its_own_with_a_keep_alive_of_zero_or_for_good(window, keep_alive):
    w = window(ollama_keep_alive=keep_alive, overlap_wait=False)
    w._job_init()
    assert w._start_load is None  # "0": nothing loaded ahead would stay; "-1": loaded at the start as ever
    assert _loads(window.server) == (1 if keep_alive == "-1" else 0)
    assert jobs.loads_at_start(w.settings) is False


@pytest.mark.parametrize("models", [None, []])  # Ollama down; the model not installed
def test_nothing_is_tried_while_ollama_is_down_or_lacks_the_model(window, models):
    w = window(models=models, overlap_wait=False)
    w._job_init()
    assert w._start_load is None and _loads(window.server) == 0
    assert not any(k in ("model_status", "error", "ollama_failed") for k, _d in w.events())


def test_a_load_that_fails_says_nothing_and_the_first_page_tries_again(window):
    server = window.server
    server.fail_loads = True
    w = window()
    w._job_init()
    w.loaded()
    assert _loads(server) == 1 and server.loaded == set()
    assert [k for k, _d in w.events() if k in ("model_status", "error", "ollama_failed")] == []
    assert "warm page models" in server.log  # the page models are warmed all the same
    server.fail_loads = False
    assert w.translator.translate_page(["一行目です。"]) == ["A line."]
    assert _loads(server) == 2 and w.model_lines() == ["ollama.loading", "ollama.loaded"]


# ------------------------------------------------------------------ Release the model now, the window's close
def test_release_the_model_now_waits_for_the_load_and_nothing_loads_after_it(window):
    server = window.server
    server.go.clear()
    w = window()
    w._job_init()
    assert server.load_began.wait(5.0)
    done = []
    release = threading.Thread(target=lambda: done.append(gpu_release.release_models(w)))
    release.start()  # (on the worker: the load at the start is under way)
    time.sleep(0.3)
    assert not done
    server.go.set()
    release.join(10.0)
    assert done == [([MODEL], False)] and server.loaded == set()
    assert server.log.index("unload") > server.log.index("load")
    assert server.log.count("warm page models") == 0  # not warmed after the release
    time.sleep(0.3)
    assert _loads(server) == 1 and server.loaded == set()  # nothing loads again by itself
    assert w.translator.translate_page(["一行目です。"]) == ["A line."]  # until a page needs the model
    assert _loads(server) == 2


def test_the_window_s_close_ends_the_load_under_way(window):
    server = window.server
    server.go.clear()
    w = window()
    w._job_init()
    assert server.load_began.wait(5.0)
    began = time.monotonic()
    w._release_model()
    w.loaded()
    assert time.monotonic() - began < 2.0  # ended at once (Stop), not waited for
    assert server.log.count("warm page models") == 0 and w.model_lines() == []
    assert "unload" in server.log  # what was asked to load goes with the window


# ------------------------------------------------------------------ the setting and its row
def test_the_setting_is_on_by_default_and_read_from_the_file(tmp_path):
    from pathlib import Path

    assert Settings().load_model_at_start is True
    example = Settings.from_toml(Path(__file__).resolve().parent.parent / "taslation.toml.example")
    assert example.load_model_at_start is True
    path = tmp_path / "taslation.toml"
    path.write_text("load_model_at_start = false\n", encoding="utf-8")
    assert Settings.from_toml(path).load_model_at_start is False
    assert jobs.loads_at_start(Settings()) and not jobs.loads_at_start(Settings(load_model_at_start=False))


def test_the_system_page_shows_and_saves_the_setting(hidden_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    in_force = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.system.load_at_start.get() is True and d.values()["load_model_at_start"] is True
    d.system.load_at_start.set(False)
    assert d.save() is True and got == [{"load_model_at_start": False}]
    assert Settings.from_toml(in_force.config_path).load_model_at_start is False


def test_the_strings_are_in_every_language():
    for key in (system_page.LOAD_AT_START_LABEL, system_page.LOAD_AT_START_TEXT):
        assert sorted(texts.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key
