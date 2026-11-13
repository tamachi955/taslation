"""What the Ollama client says when a request fails: a TranslationError whose .message is a coded Message, with no
raw JSON and none of the operating system's (localised) error text."""
from __future__ import annotations

import threading
import time

import pytest
from fake_ollama import FakeOllama, free_port

from taslation import netguard
from taslation.translate import TranslationError
from taslation.translate.ollama import OllamaTranslator, error_text


@pytest.fixture
def server():
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            yield fake
        finally:
            netguard.uninstall()


@pytest.mark.parametrize("streamed", [False, True])
def test_a_model_ollama_lacks_is_named(server, streamed):
    server.chat_error = (404, {"error": "model 'qwen9:1b' not found"})  # what Ollama 0.40 answers
    tr = OllamaTranslator(server.url, model="qwen9:1b")
    with pytest.raises(TranslationError) as info:
        tr.translate_page(["こんにちは"], cancel=threading.Event() if streamed else None)
    m = info.value.message
    assert m.code == "health.chosen_model_missing"
    assert dict(m.params) == {"model": "qwen9:1b", "command": "ollama pull qwen9:1b"}
    assert str(info.value) == str(m) and "{" not in str(m)  # no raw JSON
    assert "install.cmd" not in str(m) and "ollama pull qwen9:1b" in str(m)  # install.cmd brings the default model only


@pytest.mark.parametrize("streamed", [False, True])
def test_other_http_errors_say_what_the_server_said(server, streamed):
    server.chat_error = (500, {"error": "llama runner process has terminated"})
    tr = OllamaTranslator(server.url)
    with pytest.raises(TranslationError) as info:
        tr.translate_page(["こんにちは"], cancel=threading.Event() if streamed else None)
    m = info.value.message
    assert m.code == "ollama.http_error"
    assert dict(m.params) == {"status": 500, "path": "/api/chat", "detail": "llama runner process has terminated"}
    assert str(m) == "The translation program refused (500). Press F5 to try again; if it repeats, restart your PC."


def test_error_text_reads_the_error_of_the_json():
    assert error_text(b'{"error":"model \'x\' not found"}') == "model 'x' not found"
    assert error_text(b"404 page not found") == "404 page not found"
    assert len(error_text(b"x" * 1000)) == 300


@pytest.mark.parametrize("streamed", [False, True])
def test_an_ollama_that_is_not_running_is_unreachable(streamed):
    port = free_port()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        url = f"http://127.0.0.1:{port}"
        tr = OllamaTranslator(url, timeout=5)
        with pytest.raises(TranslationError) as info:
            tr.translate_page(["x"], cancel=threading.Event() if streamed else None)
    finally:
        netguard.uninstall()
    m = info.value.message
    assert m.code == "ollama.unreachable" and dict(m.params) == {"url": url}
    assert info.value.message.params["url"] == url and "WinError" not in str(info.value)  # not in the system's language


@pytest.mark.parametrize("streamed", [False, True])
def test_an_answer_that_does_not_come_times_out(server, streamed):
    server.before_headers = 5.0
    tr = OllamaTranslator(server.url, timeout=0.6)
    started = time.monotonic()
    with pytest.raises(TranslationError) as info:
        tr.translate_page(["こんにちは"], cancel=threading.Event() if streamed else None)
    assert time.monotonic() - started < 3.0
    m = info.value.message
    assert m.code == "ollama.timeout" and m.params["seconds"] == pytest.approx(0.6)
    assert str(m) == "The translation took too long. Press F5 to try again."


def test_an_answer_without_translations_says_how_long_it_was(server):
    server.chat_error = (200, {"message": {"role": "assistant", "content": "I cannot help with that."}, "done": True})
    with pytest.raises(TranslationError) as info:
        OllamaTranslator(server.url).translate_page(["こんにちは"])
    m = info.value.message
    assert m.code == "ollama.bad_answer" and m.params["chars"] == len("I cannot help with that.")


def test_a_url_off_this_computer_is_refused_with_a_message():
    with pytest.raises(TranslationError) as info:
        OllamaTranslator("http://192.168.1.10:11434")
    assert info.value.message.code == "ollama.not_loopback"
    assert info.value.message.params["url"] == "http://192.168.1.10:11434"


