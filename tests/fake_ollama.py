"""A fake Ollama on a free localhost port for the message, cancel, health and reply tests: it answers /api/version,
/api/tags and /api/chat, can be slow in every way a real one is (before the headers, before the first piece,
between pieces), can answer with an error, streams chunked as Ollama does (or HTTP/1.0 until the connection
closes), and notices when the client goes away. ``answer`` scripts the model: given the bubbles of a request
(the items of its JSON line) and the request, it returns the reply's content, an (HTTP status, JSON body) error,
or None for the usual reply. With ``tracks_loads`` it also keeps a model in memory as Ollama does: a request loads
it, /api/ps shows it (else /api/ps is a 404, as on a server without it, and no load is checked), an empty request
with ``keep_alive`` 0 unloads it, and ``shares`` says how much of each load lands on the GPU."""
from __future__ import annotations

import json
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


class FakeOllama(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.models: list[str] = ["qwen3.5:4b", "gemma3:4b"]
        self.chat_error: tuple[int, Any] | None = None  # (status, JSON body) for /api/chat
        self.before_headers = 0.0  # seconds of silence before anything is sent
        self.before_first = 0.0  # seconds after the headers before the first piece (a model that is loading)
        self.between = 0.0  # seconds between pieces
        self.endless = False  # pieces keep coming until the client goes away
        self.chunked = True  # HTTP/1.1 chunked, as Ollama streams; False: HTTP/1.0 until the connection closes
        # (items, request) -> the reply's content, (status, body) for an error, or None for the usual reply
        self.answer: Callable[[list[dict[str, Any]], dict[str, Any]], Any] | None = None
        self.done_reason = "stop"  # what the last line of a streamed answer says
        self.requests: list[dict[str, Any]] = []
        self.tracks_loads = False  # /api/ps answers and models load and unload
        self.loaded: set[str] = set()  # the models in memory
        self.loads = 0  # how many times a model was loaded
        self.shares: list[float] = []  # the GPU share of the next loads (then 1.0)
        self.share = 1.0  # the GPU share of the model in memory
        self.gone = threading.Event()  # the client closed the connection before the answer was over
        self.port = self.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=lambda: self.serve_forever(poll_interval=0.05), daemon=True)

    def __enter__(self) -> "FakeOllama":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.shutdown()
        self.server_close()


class _Handler(BaseHTTPRequestHandler):
    server: FakeOllama

    def log_message(self, *args: Any) -> None:  # silence
        pass

    def _json(self, status: int, obj: Any) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/version":
            self._json(200, {"version": "0.0-fake"})
        elif self.path == "/api/tags":
            self._json(200, {"models": [{"name": n} for n in self.server.models]})
        elif self.path == "/api/ps" and self.server.tracks_loads:
            size = 3_000_000_000
            self._json(200, {"models": [{"name": n, "model": n, "size": size, "size_vram": int(size * self.server.share)}
                                        for n in sorted(self.server.loaded)]})
        else:
            self._json(404, {"error": "404 page not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        server = self.server
        server.requests.append(payload)
        if not self._wait(server.before_headers):
            return
        if server.chat_error is not None:
            status, body = server.chat_error
            self._json(status, body)
            return
        if not payload["messages"]:  # how Ollama is told to unload
            server.loaded.discard(payload["model"])
            self._json(200, {"model": payload["model"], "done": True, "done_reason": "unload"})
            return
        if server.tracks_loads and payload["model"] not in server.loaded:
            server.loaded.add(payload["model"])
            server.loads += 1
            server.share = server.shares.pop(0) if server.shares else 1.0
        user = payload["messages"][-1]["content"]
        items: list[dict[str, Any]] = []
        try:  # the bubbles' JSON line of a translation request
            items = json.loads(next(line for line in reversed(user.splitlines()) if line.startswith("[{")))
            content = json.dumps({"translations": [{"id": it["id"], "text": "T:" + it["ja"]} for it in items]})
        except (StopIteration, ValueError):  # the translator's notes, say
            content = json.dumps({"characters": [], "terms": [], "synopsis": "A short story."})
        if server.answer is not None:
            scripted = server.answer(items, payload)
            if isinstance(scripted, tuple):
                self._json(*scripted)
                return
            if scripted is not None:
                content = scripted
        if not payload.get("stream"):
            self._json(200, {"message": {"role": "assistant", "content": content}, "done": True,
                             "done_reason": server.done_reason})
            return
        self._stream(content)

    def _wait(self, seconds: float) -> bool:
        """Wait *seconds*, watching whether the client goes away (then False)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            readable, _, _ = select.select([self.connection], [], [], 0.02)
            if readable:
                try:
                    if self.connection.recv(1, socket.MSG_PEEK) == b"":
                        self.server.gone.set()
                        return False
                except OSError:
                    self.server.gone.set()
                    return False
        return True

    def _stream(self, content: str) -> None:
        server = self.server
        chunked = server.chunked
        if chunked:
            self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def line(obj: Any) -> None:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            if chunked:
                data = b"%x\r\n%s\r\n" % (len(data), data)
            self.wfile.write(data)
            self.wfile.flush()

        try:
            self.wfile.flush()
            if not self._wait(server.before_first):
                return
            pieces = [content[i:i + 3] for i in range(0, len(content), 3)]
            i = 0
            while i < len(pieces) or server.endless:
                piece = pieces[i] if i < len(pieces) else ""
                line({"message": {"role": "assistant", "content": piece}, "done": False})
                i += 1
                if server.between and not self._wait(server.between):
                    return
            line({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": server.done_reason,
                  "eval_count": 7})
            if chunked:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except OSError:  # the client went away while we wrote
            server.gone.set()
        self.close_connection = True


def free_port() -> int:
    """A localhost port nothing listens on (bound and let go)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
