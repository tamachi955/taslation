from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from taslation import netguard
from taslation.translate import TranslationError
from taslation.translate.ollama import ItemStream, OllamaTranslator, parse_translations


class StubOllama(HTTPServer):
    reject_schema = False
    reject_think = False
    truncate = False
    capabilities: list[str] | None = ["completion", "vision"]  # what /api/show lists for every model (None: nothing)
    requests: list[dict]
    reply: str | None = None  # the model's answer instead of the usual JSON
    cut_stream = False  # a streamed answer breaks off before its last line
    stream_error = False  # ... or reports an error halfway
    first_seen: threading.Event | None = None  # set by the client once it has the first bubble; the stream waits for it
    waited: bool | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.server.truncate and self.path == "/api/chat":  # type: ignore[attr-defined]
            self.wfile.write(body[: len(body) // 2])  # connection drops mid-body
            self.close_connection = True
            return
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": "qwen2.5:7b"}, {"name": "gemma3:4b"}]})
        elif self.path == "/api/version":
            self._send(200, {"version": "0.0-stub"})
        else:
            self._send(404, {"error": "no"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.requests.append(payload)  # type: ignore[attr-defined]
        if self.path == "/api/show":
            caps = self.server.capabilities  # type: ignore[attr-defined]
            self._send(200, {"model_info": {}, **({"capabilities": caps} if caps is not None else {})})
            return
        if self.path != "/api/chat":
            self._send(404, {"error": "no"})
            return
        if payload["messages"][-1].get("images"):  # a region's pixels to transcribe
            self._send(200, {"message": {"role": "assistant", "content": "読めた文です\n"}, "done": True})
            return
        if "think" in payload and self.server.reject_think:  # type: ignore[attr-defined]
            self._send(400, {"error": '"stub" does not support thinking'})
            return
        if isinstance(payload.get("format"), dict) and self.server.reject_schema:  # type: ignore[attr-defined]
            self._send(400, {"error": "format schema not supported"})
            return
        user = payload["messages"][-1]["content"]
        items = json.loads(next(l for l in reversed(user.splitlines()) if l.startswith("[")))  # the bubbles' JSON line
        content = json.dumps({"translations": [{"id": it["id"], "text": "T:" + it["ja"]} for it in items]})
        if self.server.reply is not None:  # type: ignore[attr-defined]
            content = self.server.reply  # type: ignore[attr-defined]
        if payload.get("stream"):
            self._stream(content)
            return
        self._send(200, {"message": {"role": "assistant", "content": content}, "done": True})

    def _stream(self, content: str) -> None:
        """As Ollama streams: one JSON object per line, a few characters of the answer in each, the statistics last."""
        server = self.server
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()

        def line(obj) -> None:
            self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
            self.wfile.flush()

        first = content.find("}") + 1  # the end of the first bubble's object
        for i in range(0, len(content), 3):
            if server.first_seen is not None and i < first <= i + 3:  # type: ignore[attr-defined]
                line({"message": {"role": "assistant", "content": content[i:first]}, "done": False})
                server.waited = server.first_seen.wait(5)  # type: ignore[attr-defined]
                line({"message": {"role": "assistant", "content": content[first:i + 3]}, "done": False})
                continue
            line({"message": {"role": "assistant", "content": content[i:i + 3]}, "done": False})
            if server.stream_error and i >= len(content) // 2:  # type: ignore[attr-defined]
                line({"error": "model runner has unexpectedly stopped"})
                break
        if not server.cut_stream and not server.stream_error:  # type: ignore[attr-defined]
            line({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop", "eval_count": 21})
        self.close_connection = True


@pytest.fixture
def stub():
    server = StubOllama(("127.0.0.1", 0), Handler)
    server.requests = []
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        yield server, port
    finally:
        netguard.uninstall()
        server.shutdown()
        server.server_close()


def test_translate_page_through_stub(stub):
    server, port = stub
    tr = OllamaTranslator(f"http://127.0.0.1:{port}", model="qwen2.5:7b")
    assert tr.ping()
    assert tr.version() == "0.0-stub"
    assert tr.list_models() == ["qwen2.5:7b", "gemma3:4b"]
    assert tr.has_model("qwen2.5:7b") and tr.has_model("gemma3") and not tr.has_model("llama")
    out = tr.translate_page(["こんにちは", "急いで"], context=[("前の文", "previous line")])
    assert out == ["T:こんにちは", "T:急いで"]
    req = server.requests[-1]
    assert req["stream"] is False and isinstance(req["format"], dict)
    assert req["think"] is False  # thinking models answer directly
    assert req["options"]["num_predict"] == 512  # output capped so a runaway cannot outlast the timeout
    assert req["keep_alive"] == "5m"  # every request: the model stays while pages need it
    assert "previous line" in req["messages"][-1]["content"]
    assert "English" in req["messages"][0]["content"]


def test_model_without_thinking_mode_gets_a_retry_without_think(stub):
    server, port = stub
    server.reject_think = True
    tr = OllamaTranslator(f"http://127.0.0.1:{port}")
    assert tr.translate_page(["急いで"]) == ["T:急いで"]
    assert "think" in server.requests[0] and "think" not in server.requests[1]
    assert tr.translate_page(["本当に"]) == ["T:本当に"]
    assert len(server.requests) == 3  # remembered: no third 400 round trip


def test_schema_rejected_falls_back_to_json_mode(stub):
    server, port = stub
    server.reject_schema = True
    tr = OllamaTranslator(f"http://127.0.0.1:{port}")
    assert tr.translate_page(["本当に"]) == ["T:本当に"]
    assert [r["format"] for r in server.requests] == [{"type": "object", "properties": server.requests[0]["format"]["properties"], "required": ["translations"]}, "json"]


def test_truncated_response_is_a_translation_error(stub):
    server, port = stub
    server.truncate = True
    tr = OllamaTranslator(f"http://127.0.0.1:{port}", timeout=5)
    with pytest.raises(TranslationError):
        tr.translate_page(["こんにちは"])


def test_non_loopback_url_is_refused():
    with pytest.raises(TranslationError):
        OllamaTranslator("http://192.168.1.10:11434")
    with pytest.raises(TranslationError):
        OllamaTranslator("http://ollama.example.com")


def test_unallowed_port_is_blocked_by_guard():
    netguard.install(allowed_ports={11434}, audit_hook=False)
    try:
        tr = OllamaTranslator("http://127.0.0.1:1")
        with pytest.raises(netguard.NetworkBlocked):
            tr.list_models()
    finally:
        netguard.uninstall()


def test_unreachable_server_gives_translation_error():
    netguard.install(allowed_ports={1}, audit_hook=False)
    try:
        tr = OllamaTranslator("http://127.0.0.1:1", timeout=2)
        assert not tr.ping()
        with pytest.raises(TranslationError):
            tr.translate_page(["x"])
    finally:
        netguard.uninstall()


@pytest.mark.parametrize(
    "content",
    [
        '{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]}',
        '```json\n{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]}\n```',
        '<think>hmm</think>{"translations": [{"id": 2, "text": "Bye"}, {"id": 1, "text": "Hello"}]}',
        'Sure! {"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}]} done',
        '["Hello", "Bye"]',
        '1. Hello\n2. Bye',
        '{"1": "Hello", "2": "Bye"}',
    ],
)
def test_parse_translations_variants(content):
    assert parse_translations(content, 2) == ["Hello", "Bye"]


def test_truncated_reply_is_salvaged_up_to_the_cut():
    cut = '{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "She said \\"go\\""}, {"id": 3, "text": "No way, no way, no w'
    assert parse_translations(cut, 3) == ["Hello", 'She said "go"', ""]


def test_parse_translations_missing_ids():
    assert parse_translations('{"translations": [{"id": 2, "text": "Bye"}]}', 3) == ["", "Bye", ""]
    assert parse_translations("garbage", 2) == ["", ""]


def test_room_hint_through_stub(stub):
    server, port = stub
    tr = OllamaTranslator(f"http://127.0.0.1:{port}", model="qwen2.5:7b")
    tr.translate_page(["急いで"], meta=[{"room": 12}])
    assert '"room": 12' in server.requests[-1]["messages"][-1]["content"]
    assert "room" in server.requests[-1]["messages"][0]["content"]
    assert not any(hasattr(tr, gone) for gone in ("shorten", "review", "revise", "alternatives", "extract_notes"))


def test_translate_page_hands_over_each_bubble_while_the_model_is_still_writing(stub):
    server, port = stub
    server.first_seen = threading.Event()
    tr = OllamaTranslator(f"http://127.0.0.1:{port}", model="qwen2.5:7b")
    items: list[tuple[int, str]] = []

    def on_item(index, text):
        items.append((index, text))
        server.first_seen.set()

    out = tr.translate_page(["こんにちは", "急いで", "本当に"], on_item=on_item)
    assert out == ["T:こんにちは", "T:急いで", "T:本当に"]
    assert server.waited is True  # the first bubble arrived while the rest of the answer was still to come
    assert items == [(0, "T:こんにちは"), (1, "T:急いで"), (2, "T:本当に")]
    req = server.requests[-1]
    assert req["stream"] is True and isinstance(req["format"], dict) and req["think"] is False  # one request, as before
    assert tr.last_stats["eval_count"] == 21 and tr.last_stats["done_reason"] == "stop"
    tr.translate_page(["こんにちは"])  # without on_item: in one piece, as before
    assert server.requests[-1]["stream"] is False


def test_a_streamed_answer_that_is_no_list_of_objects_is_read_at_the_end(stub):
    server, port = stub
    server.reply = "1. Hello\n2. Bye"
    tr = OllamaTranslator(f"http://127.0.0.1:{port}")
    items: list[tuple[int, str]] = []
    assert tr.translate_page(["こんにちは", "さよなら"], on_item=lambda i, t: items.append((i, t))) == ["Hello", "Bye"]
    assert items == []  # no early looks; the whole answer applied at the end, as before


def test_a_stream_that_breaks_off_or_fails_is_a_translation_error(stub):
    server, port = stub
    tr = OllamaTranslator(f"http://127.0.0.1:{port}", timeout=5)
    server.cut_stream = True
    with pytest.raises(TranslationError, match="could not use"):
        tr.translate_page(["こんにちは", "急いで"], on_item=lambda i, t: None)
    server.cut_stream, server.stream_error = False, True
    with pytest.raises(TranslationError, match="could not use"):
        tr.translate_page(["こんにちは", "急いで"], on_item=lambda i, t: None)


def test_streaming_keeps_the_fallbacks_for_older_servers(stub):
    server, port = stub
    server.reject_think = True
    server.reject_schema = True
    tr = OllamaTranslator(f"http://127.0.0.1:{port}")
    items: list[tuple[int, str]] = []
    assert tr.translate_page(["急いで"], on_item=lambda i, t: items.append((i, t))) == ["T:急いで"]
    assert items == [(0, "T:急いで")] and all(r["stream"] for r in server.requests)
    assert "think" not in server.requests[-1] and server.requests[-1]["format"] == "json"


def _fed(text: str, step: int = 1) -> list[tuple[int, dict, int]]:
    """What ItemStream hands over when *text* comes in pieces of *step* characters: (position, object, characters
    fed when it came)."""
    got: list[tuple[int, dict, int]] = []
    fed = [0]
    stream = ItemStream(lambda obj, pos: got.append((pos, obj, fed[0])))
    for i in range(0, len(text), step):
        fed[0] = min(len(text), i + step)
        stream.feed(text[i:i + step])
    return got


def test_item_stream_hands_over_each_object_the_moment_it_closes():
    text = '{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye", "note": "a pun"}]}'
    got = _fed(text)
    assert [(pos, obj) for pos, obj, _n in got] == [(0, {"id": 1, "text": "Hello"}),
                                                   (1, {"id": 2, "text": "Bye", "note": "a pun"})]
    assert got[0][2] == text.index("}") + 1  # at its closing brace, not later
    assert got[1][2] == text.index("}]") + 1
    assert [obj for _p, obj, _n in _fed(text, 7)] == [obj for _p, obj, _n in got]  # however the pieces fall


def test_item_stream_follows_strings_escapes_and_nesting():
    text = ('{"translations": [{"id": 1, "text": "a {b} [c] \\"d\\" \\\\", "flags": ["x", {"y": 1}]}, '
            '{"id": 2, "text": "}]\\u3042"}]}')
    objs = [obj for _p, obj, _n in _fed(text)]
    assert objs == [{"id": 1, "text": 'a {b} [c] "d" \\', "flags": ["x", {"y": 1}]}, {"id": 2, "text": "}]あ"}]


def test_item_stream_gives_only_what_is_complete_and_never_a_wrong_object():
    cut = '{"translations": [{"id": 1, "text": "Hello"}, {"id": 2, "text": "No way, no w'
    assert [obj["id"] for _p, obj, _n in _fed(cut)] == [1]  # a truncated answer: the bubbles before the cut
    think = '<think>maybe [{"id": 9, "text": "no"}]</think>```json\n{"translations": [{"id": 1, "text": "Hi"}]}\n```'
    assert [obj for _p, obj, _n in _fed(think)] == [{"id": 1, "text": "Hi"}]  # the reasoning is skipped
    after = '{"translations": [{"id": 1, "text": "Hi"}]} and again {"translations": [{"id": 2, "text": "Ho"}]}'
    assert [obj["id"] for _p, obj, _n in _fed(after)] == [1]  # what follows the JSON is ignored
    assert _fed('{"translations": [{"id": 1, "text": "a"]}, {"id": 2, "text": "b"}]}') == []  # brackets that do not match
    assert _fed('["Hello", "Bye"]') == [] and _fed('{"1": "Hello", "2": "Bye"}') == [] and _fed("1. Hello") == []
    assert [pos for pos, _o, _n in _fed('[{"text": "a"}, {"text": "b"}]')] == [0, 1]  # no ids: their places
