"""One HTTP connection to Ollama kept per thread that talks to it (`OllamaTranslator._held`), opened again without a
word when the server closed it meanwhile, never shared between threads; a streamed answer read to its end keeps it, a
cancelled one closes it (Ollama then stops writing); and /api/ps asked before a request only when the model has not
answered for a while (`PS_RECHECK_S`, half the keep_alive when shorter), after a request that failed and after a
release. Against a stand-in server that keeps its connections open (HTTP/1.1, as Ollama does)."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from taslation import netguard
from taslation.messages import Cancelled
from taslation.translate import TranslationError
from taslation.translate import ollama as ollama_module
from taslation.translate.models import PLAMO
from taslation.translate.plamo import PlamoTranslator

MODEL = PLAMO.ollama_name


class Server(ThreadingHTTPServer):
    daemon_threads = True
    connections: int  # how many connections were opened to it
    socks: list  # their sockets
    asked: int  # how many lines it was asked to translate
    paths: list[str]  # every request's path, in order
    loaded: set[str]
    close_after: bool  # close each connection after its answer, without saying so (a server's idle close)
    slow_pieces: float  # seconds between the pieces of a streamed answer
    failing: bool  # answer every generation with an error
    gone: threading.Event  # a client went away during a streamed answer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.server.connections += 1
        self.server.socks.append(self.connection)

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if self.server.close_after:
            self.close_connection = True  # (no "Connection: close": the client finds out at its next request)

    def do_GET(self):
        self.server.paths.append(self.path)
        if self.path == "/api/ps":
            self._send(200, {"models": [{"name": n, "model": n, "size": 10, "size_vram": 10}
                                        for n in sorted(self.server.loaded)]})
        else:
            self._send(200, {"version": "0.40-stand-in"})

    def do_POST(self):
        server = self.server
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        server.paths.append(self.path)
        if not payload.get("prompt"):  # a load, or (keep_alive 0) an unload
            if payload.get("keep_alive") == 0:
                server.loaded.discard(payload["model"])
            else:
                server.loaded.add(payload["model"])
            self._send(200, {"response": "", "done": True})
            return
        if server.failing:
            self._send(500, {"error": "something broke"})
            return
        server.loaded.add(payload["model"])
        server.asked += 1
        answer = "A line."
        if not payload.get("stream"):
            self._send(200, {"response": answer, "done": True, "done_reason": "stop"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(obj) -> None:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

        try:
            for i in range(0, len(answer), 2):
                chunk({"response": answer[i:i + 2], "done": False})
                if server.slow_pieces:
                    time.sleep(server.slow_pieces)
            chunk({"response": "", "done": True, "done_reason": "stop"})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except OSError:
            server.gone.set()
            self.close_connection = True
        if server.close_after:
            self.close_connection = True


@pytest.fixture
def server():
    srv = Server(("127.0.0.1", 0), Handler)
    serve(srv)
    port = srv.server_address[1]
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        yield srv, f"http://127.0.0.1:{port}"
    finally:
        netguard.uninstall()
        srv.shutdown()
        srv.server_close()


def serve(srv: Server) -> None:
    srv.connections, srv.socks, srv.asked, srv.paths, srv.loaded = 0, [], 0, [], set()
    srv.close_after, srv.slow_pieces, srv.failing, srv.gone = False, 0.0, False, threading.Event()
    threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.05), daemon=True).start()


# ------------------------------------------------------------------------------------------------ the connection
def test_one_connection_carries_a_threads_requests(server):
    srv, url = server
    tr = PlamoTranslator(url=url)
    for k in range(5):
        assert tr.translate_page([f"行{k}です。"]) == ["A line."]
    assert tr.version() == "0.40-stand-in"
    assert srv.connections == 1


def test_a_streamed_answer_read_to_its_end_keeps_the_connection(server):
    srv, url = server
    tr = PlamoTranslator(url=url)
    stop = threading.Event()
    for k in range(3):
        assert tr.translate_page([f"行{k}です。"], cancel=stop) == ["A line."]  # (streamed: there is a cancel)
    tr.translate_page(["次です。"])  # in one piece, on the same connection
    assert srv.connections == 1


def test_each_thread_has_a_connection_of_its_own(server):
    srv, url = server
    tr = PlamoTranslator(url=url)
    done = []

    def ask(k: int) -> None:
        for j in range(3):
            done.append(tr.translate_page([f"行{k}-{j}です。"]))

    threads = [threading.Thread(target=ask, args=(k,)) for k in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(done) == 9 and srv.connections == 3


def test_a_connection_the_server_closed_is_opened_again_without_a_word(server):
    srv, url = server
    srv.close_after = True  # every connection closed after its answer, the client not told
    tr = PlamoTranslator(url=url)
    stop = threading.Event()
    for k in range(4):
        assert tr.translate_page([f"行{k}です。"], cancel=stop if k % 2 else None) == ["A line."]
    assert srv.asked == 4  # each line asked once: nothing sent twice
    assert srv.connections >= 4


def test_a_server_gone_and_back_is_reached_again(server):
    srv, url = server
    tr = PlamoTranslator(url=url)
    tr.translate_page(["一です。"])
    port = srv.server_address[1]
    srv.shutdown()
    srv.server_close()
    import socket

    for sock in srv.socks:  # (a server that ended: its connections end with it, the kept one too)
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
    back = Server(("127.0.0.1", port), Handler)
    serve(back)
    try:
        assert tr.translate_page(["二です。"]) == ["A line."]
        assert back.asked == 1 and back.connections == 1
    finally:
        back.shutdown()
        back.server_close()


def test_a_cancelled_stream_closes_its_connection_and_the_next_opens_one(server):
    srv, url = server
    tr = PlamoTranslator(url=url)
    tr.translate_page(["一です。"])
    srv.slow_pieces = 0.3
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    with pytest.raises(Cancelled):
        tr.translate_page(["二です。"], cancel=stop)
    assert srv.gone.wait(3.0)  # the server noticed: Ollama stops writing then
    srv.slow_pieces = 0.0
    assert tr.translate_page(["三です。"]) == ["A line."]
    assert srv.connections == 2


def test_a_server_that_does_not_answer_still_times_out(server):
    srv, url = server
    tr = PlamoTranslator(url=url, timeout=0.5)
    tr.translate_page(["一です。"])
    srv.slow_pieces = 2.0
    began = time.monotonic()
    with pytest.raises(TranslationError) as e:
        tr.translate_page(["二です。"], cancel=threading.Event())
    assert e.value.message.code == "ollama.timeout" and time.monotonic() - began < 1.8


# ------------------------------------------------------------------------------------------------ /api/ps
def test_ps_is_asked_only_when_the_model_has_not_answered_lately(server):
    srv, url = server
    tr = PlamoTranslator(url=url)
    for k in range(4):
        tr.translate_page([f"行{k}です。"])
    # before the first request, and the model's place in GPU memory after it loaded it; then the model answered
    assert srv.paths.count("/api/ps") == 2 and srv.asked == 4


def test_ps_is_asked_again_after_the_window_after_a_failure_and_after_a_release(server, monkeypatch):
    srv, url = server
    tr = PlamoTranslator(url=url)
    tr.translate_page(["一です。"])
    asked = srv.paths.count("/api/ps")
    # after a failed request
    srv.failing = True
    with pytest.raises(TranslationError):
        tr.translate_page(["二です。"])
    srv.failing = False
    tr.translate_page(["三です。"])
    assert srv.paths.count("/api/ps") == asked + 1  # (the failed one came in the window: not checked before it)
    # after Release the model now: the next line looks, and loads
    assert tr.release_now() == [MODEL]
    before = srv.paths.count("/api/ps")
    tr.translate_page(["四です。"])
    assert srv.paths.count("/api/ps") > before and MODEL in srv.loaded
    # once the window is over
    now = srv.paths.count("/api/ps")
    tr.translate_page(["五です。"])
    assert srv.paths.count("/api/ps") == now
    monkeypatch.setattr(ollama_module, "PS_RECHECK_S", 0.0)
    tr._answered(tr.model)
    tr.translate_page(["六です。"])
    assert srv.paths.count("/api/ps") == now + 1


def test_the_window_is_never_longer_than_half_the_keep_alive():
    tr = PlamoTranslator(keep_alive="10s")
    tr._answered(tr.model)
    model, until = tr._fresh
    assert model == tr.model and 4.0 < until - time.monotonic() <= 5.0
    tr = PlamoTranslator(keep_alive="-1")
    tr._answered(tr.model)
    assert tr._fresh[1] - time.monotonic() <= ollama_module.PS_RECHECK_S
    tr = PlamoTranslator(keep_alive="0")
    tr._answered(tr.model)
    assert tr._fresh == ("", 0.0)
    assert ollama_module.keep_alive_seconds("1h30m") == 5400 and ollama_module.keep_alive_seconds("500ms") == 0.5
