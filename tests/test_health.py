"""The health checks the window runs at the start and while a problem stands: fast, localhost only, in Messages."""
from __future__ import annotations

import socket
import time

import pytest
from fake_ollama import FakeOllama, free_port

from taslation import health, netguard
from taslation.batch import preflight
from taslation.config import OCR_REQUIRED_FILES, OCR_MODEL_DIRNAME, Settings


@pytest.fixture
def server():
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)  # the checks reach nothing else
        try:
            yield fake
        finally:
            netguard.uninstall()


def _settings(tmp_path, url: str, model: str = "qwen3.5:4b", ocr: bool = True) -> Settings:
    s = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", ollama_url=url, ollama_model=model)
    if ocr:
        folder = tmp_path / "models" / OCR_MODEL_DIRNAME
        folder.mkdir(parents=True)
        for name in OCR_REQUIRED_FILES:
            (folder / name).write_text("x", encoding="utf-8")
    return s


def test_a_running_ollama_and_its_models(server):
    assert health.ollama_running(server.url)
    assert health.installed_models(server.url) == ["qwen3.5:4b", "gemma3:4b"]
    assert health.model_installed(server.url, "qwen3.5:4b") and health.model_installed(server.url, "gemma3")
    assert not health.model_installed(server.url, "llama3:8b")
    assert health.check_ollama(server.url, "qwen3.5:4b") == []


def test_has_model_follows_the_translator():
    assert health.has_model(["qwen3.5:4b"], "qwen3.5:4b") and health.has_model(["qwen3.5:4b"], "qwen3.5")
    assert not health.has_model(["qwen3.5:4b"], "qwen3.5:9b") and not health.has_model([], "qwen3.5")


def test_nothing_listening_is_told_fast():
    port = free_port()
    started = time.monotonic()
    assert not health.ollama_running(f"http://127.0.0.1:{port}")
    assert time.monotonic() - started < 1.5  # one attempt with a short timeout, not Windows' 2 s of retries
    started = time.monotonic()
    assert health.installed_models(f"http://localhost:{port}", timeout=1.0) is None
    assert time.monotonic() - started < 1.8  # both addresses of localhost, within the time given


def test_a_url_off_this_computer_is_never_contacted(monkeypatch):
    def no_connect(*args, **kwargs):
        raise AssertionError("no connection may be attempted")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    assert not health.ollama_running("http://example.com:11434")
    assert not health.ollama_running("http://192.168.1.10:11434") and health.installed_models("ftp://127.0.0.1:1") is None


def test_check_names_every_problem(server, tmp_path):
    good = _settings(tmp_path / "a", server.url)
    assert health.check(good) == []
    server.models = ["gemma3:4b"]
    (other,) = health.check(good)
    assert other.code == "health.other_model"
    assert dict(other.params) == {"wanted": "qwen3.5:4b", "used": "gemma3:4b"}
    server.models = []
    (missing,) = health.check(good)
    assert missing.code == "health.model_missing"
    assert dict(missing.params) == {"model": "qwen3.5:4b"}
    no_ocr = _settings(tmp_path / "b", server.url, ocr=False)
    server.models = ["qwen3.5:4b"]
    (ocr,) = health.check(no_ocr)
    assert ocr.code == "health.ocr_missing"
    assert dict(ocr.params) == {"path": str(no_ocr.ocr_model_dir)}
    assert not health.ocr_available(no_ocr.ocr_model_dir) and health.ocr_available(good.ocr_model_dir)


def test_the_default_model_is_install_cmds_and_no_command_is_named(server, tmp_path):
    from taslation.translate.models import PLAMO, QWEN

    assert Settings.ollama_model == "auto"  # the target language chooses (translate/models.py)
    s = _settings(tmp_path, server.url, model="auto")
    server.models = []
    (missing,) = health.check(s)
    assert missing.code == "translator.model_missing"
    assert str(missing) == ("The translation model for this language, PLaMo 3 Translate 2B, is not installed. Run "
                            "install.cmd again to install it.")
    server.models = ["gemma3:4b"]  # a model of somebody else's does not stand in for the language's own
    assert [m.code for m in health.check(s)] == ["translator.model_missing"]
    server.models = [QWEN.ollama_name]  # Qwen does, for a language PLaMo writes: a notice
    (other,) = health.check(s)
    assert other.code == "translator.other_model" and dict(other.params)["used"] == QWEN.display_name
    assert str(other).endswith("Run install.cmd again to install PLaMo 3 Translate 2B.")
    server.models = [PLAMO.ollama_name]
    assert health.check(s) == []
    # one of the two asked for by name is still install.cmd's
    named = _settings(tmp_path / "n", server.url, model=QWEN.ollama_name)
    server.models = ["gemma3:4b"]
    (by_name,) = health.check(named)
    assert str(by_name) == (f"{QWEN.ollama_name} is not installed in Ollama; translating with gemma3:4b for now. "
                            f"Run install.cmd again to install {QWEN.ollama_name}.")
    server.models = [QWEN.ollama_name]
    (ocr,) = health.check(_settings(tmp_path / "b", server.url, model=QWEN.ollama_name, ocr=False))
    assert str(ocr) == ("The part that reads Japanese is missing. Double-click install.cmd in the TASlation folder. "
                        "Pages already translated still show.")
    for message in (missing, other, by_name, ocr):
        assert "command" not in message.params and "terminal" not in str(message)


def test_a_model_set_by_hand_keeps_its_command(server, tmp_path):
    s = _settings(tmp_path, server.url, model="llama3:8b")
    server.models = []
    (missing,) = health.check(s)
    assert missing.code == "health.chosen_model_missing"
    assert dict(missing.params) == {"model": "llama3:8b", "command": "ollama pull llama3:8b"}
    assert str(missing).endswith("Run in a terminal: ollama pull llama3:8b") and "install.cmd" not in str(missing)
    server.models = ["gemma3:4b"]
    (other,) = health.check(s)
    assert other.code == "health.chosen_other_model"
    assert dict(other.params) == {"wanted": "llama3:8b", "used": "gemma3:4b", "command": "ollama pull llama3:8b"}
    assert str(other).endswith("run in a terminal: ollama pull llama3:8b") and "install.cmd" not in str(other)


def test_ollama_down_and_the_model_asked_for(server, tmp_path):
    port = free_port()
    netguard.install(allowed_ports={server.port, port}, audit_hook=False)  # the guard would refuse it otherwise
    dead = f"http://127.0.0.1:{port}"
    s = _settings(tmp_path, dead, ocr=False)
    started = time.monotonic()
    problems = health.check(s)
    assert time.monotonic() - started < 1.5
    assert [p.code for p in problems] == ["health.ocr_missing", "health.ollama_down"]
    assert problems[1].params["url"] == dead
    assert str(problems[1]).startswith("The translation program is not running,")
    assert health.check(s, model="gemma3:4b", url=server.url)[1:] == []  # another model, another URL


def test_preflight_is_the_batch_s_view_of_the_same(server, tmp_path):
    s = _settings(tmp_path, server.url)
    assert preflight(s) == [] and [p.code for p in preflight(s, model="llama3:8b")] == ["health.chosen_other_model"]
