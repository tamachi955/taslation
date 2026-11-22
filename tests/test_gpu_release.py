"""Giving the GPU back (`ui.gpu_release`, `OllamaTranslator.release_now`, ``ollama_num_gpu``): the requests of both
translators exactly as before without the setting, and with ``num_gpu`` in every request and warm-up with it; a model
split on purpose neither loaded again nor reported; Tools > Release the model now unloading TASlation's own model only
(another program's model in the same server stays), also with ``keep_alive`` "-1", refused while a translation or a
run is on, and what the status line says; the setting checked, read from the file and set from the Settings dialog's
System page. Fake servers only: the machine's own Ollama is never asked anything."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from fake_ollama import FakeOllama, free_port

from taslation import netguard
from taslation.config import ConfigError, Settings
from taslation.i18n import FEATURE_LANGUAGES, _, set_language
from taslation.locales.features import gpu_release as texts
from taslation.translate import OllamaTranslator
from taslation.translate.models import PLAMO, make_translator
from taslation.translate.ollama import NUM_GPU_MOST, num_gpu_value
from taslation.translate.plamo import STOPS, PlamoTranslator
from taslation.ui import app as app_mod
from taslation.ui import gpu_release
from taslation.ui.dialogs import settings as dlg
from taslation.ui.dialogs import system_page

MODEL = "qwen3.5:4b"
OTHER = "someone-elses:7b"  # a model another program loaded into the same server


@pytest.fixture
def ollama():
    with FakeOllama() as fake:
        fake.tracks_loads = True
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            yield fake
        finally:
            netguard.uninstall()


class Generate(ThreadingHTTPServer):
    """A stand-in Ollama for PLaMo: /api/generate (a load with an empty prompt, an unload with ``keep_alive`` 0, else a
    translation) and /api/ps, keeping what is loaded."""

    daemon_threads = True


class GenerateHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        server = self.server
        if self.path == "/api/ps":
            self._send({"models": [{"name": n, "model": n, "size": 10, "size_vram": 10} for n in sorted(server.loaded)]})
        else:
            self._send({"models": [{"name": PLAMO.ollama_name}]})

    def do_POST(self):
        server = self.server
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        server.requests.append({"path": self.path, **payload})
        if payload.get("keep_alive") == 0:
            server.loaded.discard(payload["model"])
            self._send({"response": "", "done": True, "done_reason": "unload"})
            return
        server.loaded.add(payload["model"])
        self._send({"response": "" if not payload.get("prompt") else "EN", "done": True, "done_reason": "stop"})


@pytest.fixture
def generate():
    server = Generate(("127.0.0.1", 0), GenerateHandler)
    server.requests, server.loaded = [], set()
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        yield server, f"http://127.0.0.1:{port}"
    finally:
        netguard.uninstall()
        server.shutdown()
        server.server_close()


def _warm_ups(fake):
    return [r for r in fake.requests if r["messages"] and r["messages"][-1]["content"] == "Hi"]


def _pages(fake):
    return [r for r in fake.requests if r["messages"] and r["messages"][-1]["content"] != "Hi"]


def _unloads(fake):
    return [r for r in fake.requests if not r["messages"]]


# ------------------------------------------------------------------ the setting
def test_the_setting_is_empty_by_default_and_takes_a_number_of_layers(tmp_path):
    assert Settings().ollama_num_gpu == "" and num_gpu_value("") is None and num_gpu_value(None) is None
    assert [num_gpu_value(v) for v in ("0", " 20 ", 33, str(NUM_GPU_MOST))] == [0, 20, 33, NUM_GPU_MOST]
    for bad in ("-1", "x", "1.5", "１２", True, NUM_GPU_MOST + 1):
        with pytest.raises(ValueError):
            num_gpu_value(bad)
        with pytest.raises(ConfigError, match="ollama_num_gpu"):
            Settings(state_dir=tmp_path, ollama_num_gpu=bad).validate()
    path = tmp_path / "taslation.toml"
    path.write_text("ollama_num_gpu = 0\n", encoding="utf-8")  # a number in the file: as "0" says it
    loaded = Settings.from_toml(path)
    assert loaded.ollama_num_gpu == "0" and loaded.ignored_keys == ()
    loaded.validate()


# ------------------------------------------------------------------ the chat translator's requests
def test_without_the_setting_the_chat_requests_are_as_before(ollama):
    tr = make_translator(Settings(ollama_url=ollama.url, ollama_model=MODEL))
    assert tr.num_gpu is None
    tr.translate_page(["はい"])
    (warm,), (page,) = _warm_ups(ollama), _pages(ollama)
    # the options as they were built before the setting, key for key and in that order (the JSON is the same bytes)
    assert list(warm["options"].items()) == [("num_predict", 1), ("temperature", 0), ("num_ctx", 16384)]
    assert list(page["options"].items()) == [("temperature", 0.2), ("num_ctx", 16384),
                                             ("num_predict", page["options"]["num_predict"])]
    assert "num_gpu" not in json.dumps(ollama.requests)


@pytest.mark.parametrize("setting, layers", [("0", 0), ("20", 20)])
def test_with_the_setting_every_chat_request_and_warm_up_carries_num_gpu(ollama, setting, layers):
    tr = make_translator(Settings(ollama_url=ollama.url, ollama_model=MODEL, ollama_num_gpu=setting))
    assert isinstance(tr, OllamaTranslator) and tr.num_gpu == layers
    tr.translate_page(["はい"])
    tr.translate_page(["いいえ"])
    sent = _warm_ups(ollama) + _pages(ollama)
    assert len(sent) == 3 and all(r["options"]["num_gpu"] == layers for r in sent)


def test_a_model_split_on_purpose_is_neither_loaded_again_nor_reported(ollama):
    said = []
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0, num_gpu=12)
    tr.on_status = said.append
    ollama.shares = [0.4]  # 12 layers on the GPU: part of the model on the processor, as asked
    tr.translate_page(["はい"])
    assert ollama.loads == 1 and _unloads(ollama) == []
    assert [m.code for m in said] == ["ollama.loading", "ollama.loaded"]


# ------------------------------------------------------------------ PLaMo's requests
def test_plamo_s_requests_are_as_before_without_the_setting_and_carry_num_gpu_with_it(generate):
    server, url = generate
    plain = make_translator(Settings(ollama_url=url))
    assert isinstance(plain, PlamoTranslator) and plain.num_gpu is None
    assert list(plain._options(128).items()) == [("temperature", 0.2), ("stop", list(STOPS)), ("num_predict", 128),
                                                ("num_ctx", 8192)]
    plain.translate_page(["はい"])
    warm, line = server.requests[-2:]
    assert warm["options"] == {"num_ctx": 8192} and line["prompt"] and "num_gpu" not in line["options"]
    server.requests.clear()
    server.loaded.clear()
    layered = make_translator(Settings(ollama_url=url, ollama_num_gpu="0"))
    assert layered._options(128)["num_gpu"] == 0
    layered.translate_page(["はい"])
    warm, line = server.requests[-2:]
    assert warm["options"] == {"num_ctx": 8192, "num_gpu": 0} and line["options"]["num_gpu"] == 0


def test_release_now_unloads_plamo_with_its_own_request(generate):
    server, url = generate
    tr = make_translator(Settings(ollama_url=url))
    tr.translate_page(["はい"])
    server.loaded.add(OTHER)
    assert tr.release_now() == [PLAMO.ollama_name]
    unloads = [r for r in server.requests if r.get("keep_alive") == 0]
    assert unloads == [{"path": "/api/generate", "model": PLAMO.ollama_name, "keep_alive": 0, "stream": False}]
    assert server.loaded == {OTHER}


# ------------------------------------------------------------------ releasing the model now
def test_release_now_unloads_taslation_s_model_and_leaves_another_program_s_alone(ollama):
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0)
    tr.translate_page(["はい"])
    ollama.loaded.add(OTHER)
    assert tr.release_now() == [MODEL]
    assert [r["model"] for r in _unloads(ollama)] == [MODEL] and _unloads(ollama)[0]["keep_alive"] == 0
    assert ollama.loaded == {OTHER}
    ollama.requests.clear()
    assert tr.release_now() == [] and ollama.requests == []  # nothing used since: nothing is asked to go
    tr.translate_page(["いいえ"])  # the next translation loads it again, as ever
    assert ollama.loaded == {MODEL, OTHER} and ollama.loads == 2


def test_release_now_sends_nothing_for_a_translator_that_used_no_model(ollama):
    ollama.loaded.update({MODEL, OTHER})  # loaded by someone else (another program, an earlier session)
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0)
    assert tr.release_now() == [] and ollama.requests == [] and ollama.loaded == {MODEL, OTHER}


def test_release_now_unloads_a_model_kept_for_good_too(ollama):
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0, keep_alive="-1")
    tr.warm_up()
    tr.release()  # the end of a run: kept for good
    assert ollama.loaded == {MODEL} and _unloads(ollama) == []
    assert tr.release_now() == [MODEL] and ollama.loaded == set()


def test_release_now_skips_a_model_gone_already_and_a_server_that_is_down(ollama):
    tr = OllamaTranslator(ollama.url, MODEL, timeout=10.0)
    tr.translate_page(["はい"])
    ollama.loaded.clear()  # its keep_alive ran out
    assert tr.release_now() == [] and _unloads(ollama) == []
    port = free_port()  # nothing listens there: Ollama is down
    netguard.install(allowed_ports={ollama.port, port}, audit_hook=False)
    gone = OllamaTranslator(f"http://127.0.0.1:{port}", MODEL, timeout=1.0)
    gone._used.add(MODEL)
    assert gone.release_now() == [] and gone._used == set()


# ------------------------------------------------------------------ Tools > Release the model now
class Window(SimpleNamespace):
    """What `gpu_release.release_now` uses of the window: its state, the worker's queue, the status line."""

    def __init__(self, translator=None, pipeline=None, **state):
        said, jobs, posted = [], [], []
        super().__init__(translator=translator, pipeline=pipeline, busy=False, _queued=None,
                         said=said, jobs=jobs, posted=posted,
                         say=lambda key, **values: said.append((key, values)),
                         _jobs=SimpleNamespace(put=jobs.append),
                         _post=lambda kind, **data: posted.append((kind, data)))
        for key, value in state.items():
            setattr(self, key, value)


class FakeTranslator:
    def __init__(self, names):
        self.names, self.asked, self.num_gpu = list(names), 0, None

    def release_now(self):
        self.asked += 1
        names, self.names = self.names, []
        return names


@pytest.mark.parametrize("state", [{"busy": True}, {"_queued": ("translate", ())}])
def test_it_is_refused_while_a_translation_is_on_or_waits(state):
    translator = FakeTranslator([MODEL])
    w = Window(translator, **state)
    assert gpu_release.release_now(w) is False
    assert w.said == [(gpu_release.RELEASE_REFUSED, {})] and w.jobs == [] and translator.asked == 0


def test_it_releases_on_the_worker_and_the_status_line_says_what(monkeypatch):
    translator = FakeTranslator([MODEL])
    let_go = []
    pipeline = SimpleNamespace(translator=translator, layout=SimpleNamespace(_net="loaded"), art_eraser=None,
                               release_gpu_models=lambda: let_go.append(True))
    w = Window(translator, pipeline)  # (the pipeline's translator and the window's: asked once)
    assert gpu_release.release_now(w) is True
    assert w.said == [(gpu_release.RELEASING, {})] and translator.asked == 0  # nothing done on Tk's thread
    w.jobs.pop()()
    assert translator.asked == 1 and let_go == [True]
    assert w.posted == [("status", {"key": gpu_release.RELEASED_BOTH, "values": {"model": MODEL}})]


def test_what_the_status_line_says_for_each_case():
    assert gpu_release.released_line([MODEL], False) == (gpu_release.RELEASED_MODEL, {"model": MODEL})
    assert gpu_release.released_line([], True) == (gpu_release.RELEASED_PAGES, {})
    assert gpu_release.released_line([], False) == (gpu_release.RELEASED_NOTHING, {})
    w = Window(FakeTranslator([]), SimpleNamespace(translator=None, layout=None, art_eraser=SimpleNamespace(_model=None),
                                                    release_gpu_models=lambda: None))
    assert gpu_release.release_models(w) == ([], False, False)  # a page model that holds nothing: nothing to say of it
    assert gpu_release.release_models(Window()) == ([], False, False)  # the window still starting: nothing at all


def test_the_status_line_names_the_ocr_s_gpu_memory_when_it_held_some():
    assert gpu_release.released_line([MODEL], True, True) == (gpu_release.RELEASED_ALL, {"model": MODEL})
    assert gpu_release.released_line([MODEL], False, True) == (gpu_release.RELEASED_MODEL_OCR, {"model": MODEL})
    assert gpu_release.released_line([], True, True) == (gpu_release.RELEASED_PAGES_OCR, {})
    assert gpu_release.released_line([], False, True) == (gpu_release.RELEASED_OCR, {})
    assert gpu_release.released_line([MODEL], True, False) == (gpu_release.RELEASED_BOTH, {"model": MODEL})
    assert "processor" not in gpu_release.RELEASED_BOTH  # (readers on the CPU: nothing is said of them)
    assert "OCR stays" not in gpu_release.RELEASE_TIP and "OCR readers that run on the GPU" in gpu_release.RELEASE_TIP


def test_release_now_releases_the_ocr_on_the_gpu_and_says_so():
    """The window's readers on the GPU (`Readers.holds_gpu`) let go with the page models (`Pipeline.release_gpu_models`,
    whose list has their `release_gpu`), and the status line names them; on the CPU they are not named."""
    readers = SimpleNamespace(on_gpu=True)
    readers.holds_gpu = lambda: readers.on_gpu
    readers.release_gpu = lambda: setattr(readers, "on_gpu", False)
    pipeline = SimpleNamespace(translator=None, layout=None, art_eraser=None, ocr=readers,
                               release_gpu_models=lambda: readers.release_gpu())
    w = Window(FakeTranslator([MODEL]), pipeline)
    assert gpu_release.release_now(w) is True
    w.jobs.pop()()
    assert readers.on_gpu is False
    assert w.posted == [("status", {"key": gpu_release.RELEASED_MODEL_OCR, "values": {"model": MODEL}})]
    assert gpu_release.release_models(Window(FakeTranslator([]), pipeline)) == ([], False, False)  # on the CPU now


def test_the_strings_are_in_every_language():
    from taslation.locales.features import ocr_release

    for key in (gpu_release.RELEASE_ENTRY, gpu_release.RELEASE_REFUSED, gpu_release.RELEASING,
                gpu_release.RELEASED_BOTH, gpu_release.RELEASED_MODEL, gpu_release.RELEASED_PAGES,
                gpu_release.RELEASED_NOTHING, system_page.NUM_GPU_LABEL, system_page.NUM_GPU_TEXT,
                system_page.NUM_GPU_PROBLEM):
        assert sorted(texts.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key
    for key in (gpu_release.RELEASE_TIP, gpu_release.RELEASED_ALL, gpu_release.RELEASED_MODEL_OCR,
                gpu_release.RELEASED_PAGES_OCR, gpu_release.RELEASED_OCR):
        assert sorted(ocr_release.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key
    set_language("ja")
    try:
        assert _(gpu_release.RELEASE_ENTRY) == "モデルを今すぐ解放"
    finally:
        set_language("en")


# ------------------------------------------------------------------ the Settings dialog and the window
@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def test_the_system_page_shows_saves_and_checks_the_layers(hidden_root, in_force):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.system.num_gpu.get() == "" and d.values()["ollama_num_gpu"] == ""
    for bad in ("x", "-1", str(NUM_GPU_MOST + 1), "2.5"):
        d.system.num_gpu.set(bad)
        assert d.save() is False and got == [] and not in_force.config_path.exists()
        assert d.message_var.get().replace("\n", " ") == system_page.NUM_GPU_PROBLEM.format(most=NUM_GPU_MOST)
    d.system.num_gpu.set(" 020 ")
    assert d.values()["ollama_num_gpu"] == "20" and d.save() is True and got == [{"ollama_num_gpu": "20"}]
    assert Settings.from_toml(in_force.config_path).ollama_num_gpu == "20"
    in_force.ollama_num_gpu = "20"  # (as the window sets it)
    d.system.num_gpu.set("")
    assert d.save() is True and got[-1] == {"ollama_num_gpu": ""}
    assert Settings.from_toml(in_force.config_path).ollama_num_gpu == ""


def test_saved_layers_are_set_on_the_window_s_translators(tmp_path):
    translator, other = FakeTranslator([]), FakeTranslator([])
    w = SimpleNamespace(settings=Settings(state_dir=tmp_path), translator=translator,
                        pipeline=SimpleNamespace(translator=other), last_result=None, busy=False)
    app_mod.App._settings_saved(w, {"ollama_num_gpu": "0"})
    assert w.settings.ollama_num_gpu == "0" and translator.num_gpu == 0 and other.num_gpu == 0
    app_mod.App._settings_saved(w, {"ollama_num_gpu": ""})
    assert translator.num_gpu is None and other.num_gpu is None


def test_the_tools_menu_has_the_entry():
    with open(app_mod.__file__, encoding="utf-8") as f:
        text = f.read()
    assert "tools.add_command(label=_(RELEASE_ENTRY), command=lambda: release_now(self))" in text
    assert "_(RELEASE_TIP))" in text  # (its tip, last among the Tools menu's)
