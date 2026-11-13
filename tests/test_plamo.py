"""The PLaMo 3 Translate translator (`taslation.translate.plamo`) against a stand-in Ollama that answers /api/generate,
and the choice of the model by the target language (`taslation.translate.models`): the raw PFML3 prompt (the
beginning-of-sequence token first, the target language's code, the earlier pairs, the series sheet as context and as
glossary), one request per line, the stops, context size and temperature in every request, a line asked for again
drawn with another seed, a model missing said as ``translator.model_missing``, Stop, the load and the release; and
Brazilian Portuguese and Turkish going to Qwen."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from taslation import health, netguard
from taslation.annotations import Glossary, Premises
from taslation.config import Settings
from taslation.messages import Cancelled
from taslation.translate import OllamaTranslator, TranslationError
from taslation.translate import models
from taslation.translate.models import (PLAMO, QWEN, choose, follow, make_translator, model_for_language, plamo_code,
                                        wanted_name)
from taslation.translate.plamo import BOS, NUM_CTX, STOPS, PlamoTranslator, glossary_for, pfml_prompt

SOURCE_TAIL = "<|plamo:tag|>output<|plamo:key|>lang<|plamo:val|>"


class StubGenerate(HTTPServer):
    requests: list[dict]
    missing = False  # the model is not installed: 404 as Ollama says it
    loaded = False
    answer = None  # a function of the prompt, else "EN:" + the line


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": PLAMO.ollama_name + ":latest"}]})
        else:
            self._send(200, {"version": "0.40-stub"})

    def do_POST(self):
        server = self.server
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        if self.path == "/api/ps":
            self._send(200, {"models": [{"name": PLAMO.ollama_name + ":latest", "size": 10, "size_vram": 10}]
                             if server.loaded else []})
            return
        server.requests.append({"path": self.path, **payload})
        if self.path != "/api/generate":
            self._send(404, {"error": "no"})
            return
        if server.missing:
            self._send(404, {"error": f"model '{payload['model']}' not found"})
            return
        if not payload.get("prompt"):  # a load, or (keep_alive 0) an unload
            server.loaded = payload.get("keep_alive") != 0
            self._send(200, {"response": "", "done": True, "done_reason": "load" if server.loaded else "unload"})
            return
        prompt = payload["prompt"]
        line = prompt.rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0]  # the last input's text
        text = server.answer(prompt) if server.answer else "EN:" + line
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for i in range(0, len(text), 4):
                self.wfile.write((json.dumps({"response": text[i:i + 4], "done": False}) + "\n").encode("utf-8"))
            self.wfile.write((json.dumps({"response": "", "done": True, "eval_count": 3}) + "\n").encode("utf-8"))
            self.close_connection = True
            return
        self._send(200, {"response": text, "done": True, "done_reason": "stop", "eval_count": 3})


@pytest.fixture
def stub():
    server = StubGenerate(("127.0.0.1", 0), Handler)
    server.requests = []
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        yield server, f"http://127.0.0.1:{port}"
    finally:
        netguard.uninstall()
        server.shutdown()
        server.server_close()


def generates(server):
    return [r for r in server.requests if r["path"] == "/api/generate" and r.get("prompt")]


def sheet() -> Glossary:
    g = Glossary(Path("eval.json"), "series", "English")
    g.set("魔導書", "grimoire")
    return g


# ------------------------------------------------------------------ the prompt
def test_the_prompt_is_the_chat_templates_with_the_bos_first():
    p = pfml_prompt("こんにちは", "en", "ctx", [("前", "Before")], [("樫戸", "Kashidou")])
    assert p.startswith(BOS + "<|plamo:tag|>dataset<|plamo:msg|>translation<|plamo:tag|>context<|plamo:msg|>ctx")
    assert "<|plamo:val|>ja<|plamo:msg|>前<|plamo:tag|>output<|plamo:key|>lang<|plamo:val|>en<|plamo:msg|>Before" in p
    assert "<|plamo:tag|>glossary<|plamo:index|>樫戸<|plamo:item|>Kashidou" in p
    assert p.endswith("<|plamo:msg|>こんにちは" + SOURCE_TAIL + "en<|plamo:msg|>")
    assert "<|plamo:bos|>" not in pfml_prompt("a<|plamo:bos|>b", "en")[1:]  # reserved tokens never pass through


def test_the_sheets_renderings_a_line_names_are_its_glossary():
    premises = Premises(sheet().format(), sheet())
    assert glossary_for(premises, "これは魔導書だ") == [("魔導書", "grimoire")]
    assert glossary_for(premises, "何もない") == []


@pytest.mark.parametrize("language, code", [("English", "en"), ("Chinese (Simplified)", "zh-hans"),
                                            ("Chinese (Traditional)", "zh-hant"), ("Korean", "ko"), ("Thai", "th"),
                                            ("Arabic", "ar"), ("Hebrew", "he"), ("Hindi", "hi"), ("Bengali", "bn")])
def test_every_language_plamo_writes_has_its_code(language, code):
    assert plamo_code(language) == code and model_for_language(language) is PLAMO


def test_every_window_language_has_a_model():
    from taslation.ui.constants import LANGUAGES

    for language in LANGUAGES:
        model = model_for_language(language)
        assert (model is QWEN) == (language in ("Portuguese (Brazil)", "Turkish")), language


@pytest.mark.parametrize("language", ["Portuguese (Brazil)", "Turkish", "pt-BR", "Klingon"])
def test_what_plamo_cannot_write_goes_to_qwen(language):
    assert model_for_language(language) is QWEN and plamo_code(language) is None


# ------------------------------------------------------------------ the requests
def test_one_raw_request_per_line_with_stops_context_and_temperature(stub):
    server, url = stub
    tr = PlamoTranslator(url, target_language="Chinese (Simplified)", seed=7)
    got = []
    out = tr.translate_page(["一", "二"], [("前", "Before")], Premises(sheet().format(), sheet()),
                            meta=[{"speaker": "Aki"}, {}], on_item=lambda i, t: got.append(i))
    assert out == ["EN:一", "EN:二"] and got == [0, 1]
    first, second = generates(server)
    for r in (first, second):
        assert r["raw"] is True and r["model"] == PLAMO.ollama_name and r["keep_alive"] == "5m"
        assert r["options"]["stop"] == STOPS and r["options"]["num_ctx"] == NUM_CTX
        assert r["options"]["temperature"] == 0.2 and r["options"]["seed"] == 7
        assert r["prompt"].startswith(BOS) and SOURCE_TAIL + "zh-hans<|plamo:msg|>" in r["prompt"]
        assert "grimoire" in r["prompt"]  # the series sheet as context
    assert "Speaker of the line: Aki" in first["prompt"] and "Speaker of the line" not in second["prompt"]
    assert "<|plamo:msg|>一<|plamo:tag|>output" in second["prompt"]  # the line before, as an earlier pair


def test_a_line_asked_for_again_is_another_draw(stub):
    server, url = stub
    tr = PlamoTranslator(url, seed=1)
    tr.translate_page(["同じ"])
    tr.translate_page(["同じ"])
    assert [r["options"]["seed"] for r in generates(server)] == [1, 2]
    app = PlamoTranslator(url)  # the app sends no seed, but one for a line asked for again
    app.translate_page(["また"])
    app.translate_page(["また"])
    first, again = generates(server)[2:]
    assert "seed" not in first["options"] and isinstance(again["options"]["seed"], int)


def test_a_reply_with_nothing_is_a_bad_answer(stub):
    server, url = stub
    server.answer = lambda prompt: "<|plamo:tag|>"
    with pytest.raises(TranslationError) as e:
        PlamoTranslator(url).translate_page(["一"])
    assert e.value.message.code == "ollama.bad_answer"


def test_streamed_with_cancel_and_stop_ends_it(stub):
    server, url = stub
    tr = PlamoTranslator(url)
    cancel = threading.Event()
    assert tr.translate_page(["一"], cancel=cancel, on_slow=lambda s: None) == ["EN:一"]
    assert generates(server)[-1]["stream"] is True
    cancel.set()
    with pytest.raises(Cancelled):
        tr.translate_page(["二"], cancel=cancel)


def test_a_missing_model_is_the_languages_model_to_install(stub):
    server, url = stub
    server.missing = True
    s = Settings()
    s.ollama_url = url
    tr = make_translator(s)
    assert isinstance(tr, PlamoTranslator) and tr.auto_model is PLAMO
    with pytest.raises(TranslationError) as e:
        tr.translate_page(["一"])
    assert e.value.message.code == "translator.model_missing"
    assert dict(e.value.message.params) == {"model": PLAMO.ollama_name, "name": PLAMO.display_name, "language": "English"}


def test_a_language_plamo_cannot_write_is_refused_before_a_request(stub):
    server, url = stub
    with pytest.raises(TranslationError) as e:
        PlamoTranslator(url, target_language="Turkish").translate_page(["一"])
    assert e.value.message.code == "plamo.cannot_write" and not generates(server)


def test_load_on_demand_and_release(stub):
    server, url = stub
    tr = PlamoTranslator(url)
    statuses = []
    tr.on_status = lambda m: statuses.append(m.code)
    tr.translate_page(["一"])
    loads = [r for r in server.requests if r["path"] == "/api/generate" and r.get("prompt") == ""]
    assert loads and loads[0]["options"]["num_ctx"] == NUM_CTX
    assert statuses[:2] == ["ollama.loading", "ollama.loaded"]
    tr.release()
    assert server.requests[-1]["keep_alive"] == 0 and server.requests[-1]["path"] == "/api/generate"
    assert not server.loaded


# ------------------------------------------------------------------ the choice
def test_the_setting_auto_follows_the_language():
    assert Settings().ollama_model == "auto"
    assert wanted_name("auto", "English") == PLAMO.ollama_name
    assert wanted_name("auto", "Portuguese (Brazil)") == QWEN.ollama_name == wanted_name("auto", "Turkish")
    assert wanted_name("gemma3:4b", "English") == "gemma3:4b"


def test_choose_with_what_ollama_has():
    both = [PLAMO.ollama_name + ":latest", QWEN.ollama_name]
    assert choose("auto", "English", both) == (PLAMO.ollama_name, PLAMO, None)
    assert choose("auto", "Turkish", both) == (QWEN.ollama_name, QWEN, None)
    stand_in = choose("auto", "English", [QWEN.ollama_name])  # only Qwen: it translates meanwhile, and says so
    assert stand_in.name == QWEN.ollama_name and stand_in.problem.code == "translator.other_model"
    missing = choose("auto", "Turkish", [PLAMO.ollama_name])  # PLaMo cannot write Turkish: nothing stands in
    assert missing.name == QWEN.ollama_name and missing.problem.code == "translator.model_missing"
    assert dict(missing.problem.params)["language"] == "Turkish"
    assert choose("auto", "English", None) == (PLAMO.ollama_name, PLAMO, None)  # Ollama silent: the wanted one
    assert choose("gemma3:4b", "English", ["llama3:8b"]).name == "llama3:8b"  # a model of one's own: as before


def test_make_translator_gives_the_right_class():
    s = Settings()
    assert isinstance(make_translator(s), PlamoTranslator)
    s.target_language = "Portuguese (Brazil)"
    qwen = make_translator(s)
    assert type(qwen) is OllamaTranslator and qwen.model == QWEN.ollama_name and qwen.auto_model is QWEN
    s.ollama_model = "gemma3:4b"
    own = make_translator(s)
    assert type(own) is OllamaTranslator and own.model == "gemma3:4b" and own.auto_model is None


def test_follow_rebuilds_only_for_the_other_kind():
    s = Settings()
    tr = make_translator(s)
    tr.revive = revive = lambda cancel=None: True
    same = follow(tr, s, PLAMO.ollama_name, "Korean")
    assert same is tr and tr.target_language == "Korean"
    other = follow(tr, s, QWEN.ollama_name, "Turkish")
    assert type(other) is OllamaTranslator and other.target_language == "Turkish" and other.revive is revive
    back = follow(other, s, PLAMO.ollama_name, "English")
    assert isinstance(back, PlamoTranslator)


def test_health_says_which_model_the_language_needs(monkeypatch, tmp_path):
    s = Settings()
    monkeypatch.setattr(health, "check_ocr", lambda _dir: [])
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: [PLAMO.ollama_name])
    assert health.check(s) == []
    assert health.check(s, language="Turkish")[0].code == "translator.model_missing"
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: [QWEN.ollama_name])
    notice = health.check(s)
    assert [m.code for m in notice] == ["translator.other_model"]
    from taslation.ui.banner import blocking

    assert not blocking(notice) and health.check(s, language="Turkish") == []  # Qwen writes Turkish
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: [])
    assert health.check(s)[0].code == "translator.model_missing"


def test_the_interface_the_installer_codes_against():
    assert (PLAMO.kind, PLAMO.ollama_name) == ("plamo", "taslation-plamo3-translate-2b")
    assert (QWEN.kind, QWEN.ollama_name) == ("qwen", "qwen3.5:4b")
    assert PLAMO.size_gb > 0 and QWEN.size_gb > 0 and PLAMO.licence and QWEN.display_name
    assert models.MODEL_MISSING == "translator.model_missing" and "turkish" in models.QWEN_LANGUAGES


def test_a_long_history_is_kept_whole_while_it_fits(stub):
    """Sixty earlier pairs of manga lines fit in the context: none is cut, so the prompts of a request share their
    beginning (Ollama computes it once); only a history beyond the context loses its oldest pairs."""
    from taslation.translate.plamo import tokens_about

    server, url = stub
    pairs = [(f"これは{i}番目の台詞です", f"This is line number {i}.") for i in range(60)]
    PlamoTranslator(url).translate_page(["一", "二"], pairs)
    first, second = generates(server)
    assert "これは0番目の台詞です" in first["prompt"] and "これは0番目の台詞です" in second["prompt"]
    assert second["prompt"].startswith(first["prompt"].rsplit("<|plamo:tag|>input", 1)[0])  # the shared beginning
    assert tokens_about("<|plamo:tag|>") == 1 and tokens_about("漢字") == 2 and tokens_about("abcdef") == 2
    long = [("長" * 200, "long " * 100)] * 80
    PlamoTranslator(url).translate_page(["三"], long)
    assert tokens_about(generates(server)[-1]["prompt"]) <= NUM_CTX
