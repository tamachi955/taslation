"""A request to the translator that gets no answer (`taslation.translate.ollama`, `NoAnswer`), against a stand-in
server on loopback that takes a request and sends nothing, goes silent in the middle of a stream, answers after the
client's new connection, keeps writing slowly, or whose /api/ps is silent too: the request is ended at its bound, the
connection closed, the window told once (``ollama.no_answer``), the same request asked once more on a new connection
after one /api/ps look; no answer a second time, or /api/ps silent, has the server TASlation started started again
once (`OllamaTranslator.restart`) and the request asked again, and a server the person runs is never touched: the
request ends with ``ollama.not_answering`` and the client says it does not answer (``silent``) until the next answer.
A stream that keeps writing is left alone; a load whose server stops answering /api/ps ends as no answer (a request's
own load is then taken up by the rule, and the load ahead of a page ends, and its join with it), one whose server
answers it is waited for; a request waiting for a load under way gets its slow note. The log names the incident
without any line of the book."""
from __future__ import annotations

import json
import logging
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from taslation import netguard
from taslation.messages import Message
from taslation.translate import TranslationError
from taslation.translate import ollama as ollama_mod
from taslation.translate.models import PLAMO
from taslation.translate.plamo import PlamoTranslator

LINE = "こんにちは"
BOUND_S = 0.6  # the no-answer bound for these tests (NO_ANSWER_S)
WAIT_S = 8.0  # how long a test waits for a request to end: without the rule it waits 900 s


class Stand(ThreadingHTTPServer):
    """The stand-in: *plan* says what each request with a prompt does, in order ("answer", "silent": the request
    taken and nothing sent, "mid": the headers and two pieces, then nothing, "slow": a piece every *gap* seconds);
    *ps* "answer" or "silent"; *load* what a load does ("answer", "silent", or seconds to take)."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.plan: list[str] = []
        self.ps = "answer"
        self.load: Any = "answer"
        self.loaded = True
        self.gap = 0.25
        self.pieces = 10
        self.requests: list[dict[str, Any]] = []  # each generate with a prompt: its client port and mode
        self.gone = 0  # handlers that saw their client go
        self.ps_asked = 0
        self.release = threading.Event()  # ends every silent handler (the test's end)
        self.port = self.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"


class _Handler(BaseHTTPRequestHandler):
    server: Stand
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:
        pass

    def _hang(self) -> None:
        """Nothing sent until the client goes (or the test ends)."""
        while not self.server.release.is_set():
            readable, _, _ = select.select([self.connection], [], [], 0.02)
            if readable:
                try:
                    if self.connection.recv(1, socket.MSG_PEEK) == b"":
                        self.server.gone += 1
                        break
                except OSError:
                    self.server.gone += 1
                    break
        self.close_connection = True

    def _json(self, obj: Any) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _begin_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.flush()

    def _piece(self, obj: Any) -> None:
        data = (json.dumps(obj) + "\n").encode("utf-8")
        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
        self.wfile.flush()

    def _end_stream(self) -> None:
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def do_GET(self) -> None:
        if self.path == "/api/ps":
            self.server.ps_asked += 1
            if self.server.ps == "silent":
                self._hang()
                return
            self._json({"models": [{"name": PLAMO.ollama_name + ":latest", "size": 10, "size_vram": 10}]
                        if self.server.loaded else []})
        elif self.path == "/api/tags":
            self._json({"models": [{"name": PLAMO.ollama_name + ":latest"}]})
        else:
            self._json({"version": "0.40-stand"})

    def do_POST(self) -> None:
        server = self.server
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        if not payload.get("prompt"):  # a load (or, keep_alive 0, an unload)
            if payload.get("keep_alive") == 0:
                server.loaded = False
                self._json({"response": "", "done": True, "done_reason": "unload"})
                return
            if server.load == "silent":
                self._hang()
                return
            if isinstance(server.load, (int, float)) and not isinstance(server.load, bool):
                time.sleep(float(server.load))
            server.loaded = True
            if payload.get("stream"):
                self._begin_stream()
                self._piece({"response": "", "done": True, "done_reason": "load"})
                self._end_stream()
            else:
                self._json({"response": "", "done": True, "done_reason": "load"})
            return
        mode = server.plan.pop(0) if server.plan else "answer"
        server.requests.append({"port": self.client_address[1], "mode": mode})
        line = payload["prompt"].rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0]
        text = "EN:" + line
        if mode == "silent":
            self._hang()
            return
        if not payload.get("stream"):
            self._json({"response": text, "done": True, "done_reason": "stop", "eval_count": 3})
            return
        self._begin_stream()
        if mode == "mid":
            self._piece({"response": "Half", "done": False})
            self._piece({"response": " way", "done": False})
            self._hang()
            return
        if mode == "slow":
            for i in range(server.pieces):
                time.sleep(server.gap)
                self._piece({"response": text if i == 0 else "", "done": False})
        else:
            for i in range(0, len(text), 3):
                self._piece({"response": text[i:i + 3], "done": False})
        self._piece({"response": "", "done": True, "done_reason": "stop", "eval_count": 3, "prompt_eval_count": 80,
                     "prompt_eval_duration": 80_000_000})
        self._end_stream()
        self.close_connection = False


@pytest.fixture
def stand(monkeypatch):
    server = Stand()
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True).start()
    netguard.install(allowed_ports={server.port}, audit_hook=False)
    monkeypatch.setattr(ollama_mod, "NO_ANSWER_S", BOUND_S, raising=False)
    monkeypatch.setattr(ollama_mod, "NO_ANSWER_CPU_S", 2 * BOUND_S, raising=False)
    monkeypatch.setattr(ollama_mod, "ALIVE_EVERY_S", 0.2, raising=False)
    monkeypatch.setattr(ollama_mod, "PS_TIMEOUT", 0.5)
    try:
        yield server
    finally:
        server.release.set()
        netguard.uninstall()
        server.shutdown()
        server.server_close()


def _translator(stand: Stand, restart: Any = None) -> tuple[PlamoTranslator, list[Message]]:
    told: list[Message] = []
    t = PlamoTranslator(stand.url, slow_after=0.3)
    t.on_status = told.append
    if restart is not None:
        t.restart = restart
    return t, told


def _asked(t: PlamoTranslator, cancel: threading.Event | None = None) -> dict[str, Any]:
    """A page of one line asked on a thread of its own, waited for at most WAIT_S: what came of it."""
    out: dict[str, Any] = {}
    cancel = cancel if cancel is not None else threading.Event()

    def run() -> None:
        t0 = time.monotonic()
        try:
            out["result"] = t.translate_page([LINE], cancel=cancel)
        except TranslationError as e:
            out["error"] = e.message.code
        finally:
            out["seconds"] = time.monotonic() - t0

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(WAIT_S)
    out["ended"] = not thread.is_alive()
    cancel.set()  # (a request the rule did not end: let go at the test's end)
    return out


def _codes(told: list[Message]) -> list[str]:
    return [m.code for m in told]


class Restarts:
    """A stand-in for `OllamaStarter.restart`: what it returns, how often it was asked, and what it does to the server
    (a server started again answers)."""

    def __init__(self, stand: Stand, gives: Any):
        self.stand, self.gives, self.calls = stand, gives, 0

    def __call__(self, cancel: threading.Event | None = None) -> Any:
        self.calls += 1
        if self.gives:
            self.stand.plan.clear()
            self.stand.ps, self.stand.load = "answer", "answer"
            self.stand.loaded = False  # (a new server holds no model)
        return self.gives


def test_a_request_the_server_takes_and_never_answers_ends_at_its_bound_and_is_asked_again_on_a_new_connection(stand):
    stand.plan = ["silent", "answer"]
    t, told = _translator(stand)
    out = _asked(t)
    assert out["ended"] and out.get("result") == ["EN:" + LINE], out
    assert out["seconds"] < BOUND_S + 3.0
    assert [r["mode"] for r in stand.requests] == ["silent", "answer"]
    assert stand.requests[0]["port"] != stand.requests[1]["port"]  # (a new connection)
    deadline = time.monotonic() + 2.0
    while stand.gone < 1 and time.monotonic() < deadline:  # (the connection of the first was closed)
        time.sleep(0.02)
    assert stand.gone >= 1
    assert _codes(told).count("ollama.no_answer") == 1 and t.silent == 0


TURN_S = BOUND_S / 5  # (a reader who turns a page every 6 s against the 30 s bound)


def _reader_turning(t: PlamoTranslator, told: list[Message], most: int, gap: float) -> int:
    """A reader who turns a page every TURN_S seconds - each page's request cancelled then - with *gap* seconds
    between two pages in which nothing is asked; until the window is told ``ollama.no_answer`` or *most* pages. The
    pages turned."""
    from taslation.messages import Cancelled

    turns = 0
    while turns < most and "ollama.no_answer" not in _codes(told):
        turns += 1
        cancel = threading.Event()
        timer = threading.Timer(TURN_S, cancel.set)
        timer.start()
        try:
            t.translate_page([LINE], cancel=cancel)
        except Cancelled:
            pass
        finally:
            timer.cancel()
        time.sleep(gap)
    return turns


def test_a_reader_who_turns_before_the_bound_has_the_rule_fire_once_the_waits_add_up_to_it(stand, monkeypatch):
    """(the stop of 2026-11-21: the server took every request and answered none, the reader's turns cancelled each
    after 6 to 7 s, and the 30 s bound of a request was never reached) The seconds without a byte are counted over the
    requests in a row that got none, the gaps with no request under way left out: the rule fires once they reach the
    bound, the window told of the seconds waited in all."""
    monkeypatch.setattr(ollama_mod, "POLL_S", 0.02)
    stand.plan = ["silent"] * 60
    t, told = _translator(stand)
    turns = _reader_turning(t, told, most=15, gap=BOUND_S / 2)
    said = [m for m in told if m.code == "ollama.no_answer"]
    assert said, f"the rule never fired in {turns} pages turned"
    assert turns >= 4  # (0.12 s a page: the waits reach 0.6 s on the fifth; the gaps, 0.3 s each, are not counted)
    assert BOUND_S <= said[0].params["seconds"] <= BOUND_S + 0.2
    assert len(said) == 1


def test_any_answer_between_the_turns_starts_the_count_again(stand, monkeypatch):
    """(the guard of the count: three pages turned before their answer, the fourth answered - 0.4 s in a row at most)"""
    monkeypatch.setattr(ollama_mod, "POLL_S", 0.02)
    stand.plan = ["silent", "silent", "silent", "answer"] * 4
    t, told = _translator(stand)
    assert _reader_turning(t, told, most=16, gap=0.05) == 16
    assert "ollama.no_answer" not in _codes(told) and len(stand.requests) == 16


def test_a_stream_silent_in_the_middle_is_no_answer_and_what_came_of_it_is_not_kept(stand):
    stand.plan = ["mid", "answer"]
    t, told = _translator(stand)
    out = _asked(t)
    assert out["ended"] and out.get("result") == ["EN:" + LINE], out
    assert [r["mode"] for r in stand.requests] == ["mid", "answer"]
    assert _codes(told).count("ollama.no_answer") == 1


def test_a_slow_stream_that_keeps_writing_is_left_alone(stand):
    """(the guard of the rule: a stream that writes more slowly than the bound in all, but never pauses that long)"""
    stand.plan, stand.gap, stand.pieces = ["slow"], BOUND_S / 2, 8  # (2.4 s of writing, a piece every 0.3 s)
    t, told = _translator(stand)
    out = _asked(t)
    assert out["ended"] and out.get("result") == ["EN:" + LINE], out
    assert out["seconds"] > 2 * BOUND_S and [r["mode"] for r in stand.requests] == ["slow"]
    assert "ollama.no_answer" not in _codes(told)


def test_no_answer_twice_has_the_server_taslation_started_started_again_once_and_the_request_asked_again(stand):
    stand.plan = ["silent", "silent", "answer"]
    restart = Restarts(stand, True)
    t, told = _translator(stand, restart)
    out = _asked(t)
    assert out["ended"] and out.get("result") == ["EN:" + LINE], out
    assert restart.calls == 1 and [r["mode"] for r in stand.requests] == ["silent", "silent", "answer"]
    assert _codes(told).count("ollama.no_answer") == 1 and "ollama.restarting" in _codes(told)
    assert stand.loaded  # (the model loaded on the server started again before the request)
    assert t.silent == 0


def test_ps_silent_too_goes_to_the_restart_at_once(stand):
    stand.plan, stand.ps = ["silent", "answer"], "silent"
    restart = Restarts(stand, True)
    t, told = _translator(stand, restart)
    out = _asked(t)
    assert out["ended"] and out.get("result") == ["EN:" + LINE], out
    assert restart.calls == 1 and [r["mode"] for r in stand.requests] == ["silent", "answer"]


@pytest.mark.parametrize("gives", [None, False])
def test_a_server_the_person_runs_or_a_restart_that_failed_ends_the_request_with_the_sentence_and_no_loop(stand,
                                                                                                         gives):
    """None: the server is not one TASlation started (never stopped, started again or reconfigured); False: the
    restart did not bring it back (or one was made within ten minutes)."""
    stand.plan = ["silent", "silent", "silent", "silent"]
    restart = Restarts(stand, gives)
    t, told = _translator(stand, restart)
    out = _asked(t)
    assert out["ended"] and out.get("error") == "ollama.not_answering", out
    assert restart.calls == 1 and len(stand.requests) == 2  # (asked again once, then the restart asked once)
    assert t.silent != 0  # (the backlog pauses while it is so)
    out = _asked(t)  # F5: no answer since - the incident goes on, the request ends after its bound
    assert out["ended"] and out.get("error") == "ollama.not_answering", out
    assert len(stand.requests) == 3 and restart.calls == 2
    assert _codes(told).count("ollama.no_answer") == 1  # (once per incident)
    stand.plan = ["answer"]
    assert _asked(t).get("result") == ["EN:" + LINE] and t.silent == 0  # (an answer ends the incident)


def test_without_a_way_to_restart_ps_silent_ends_the_request_at_once(stand):
    stand.plan, stand.ps = ["silent", "answer"], "silent"
    t, told = _translator(stand)
    out = _asked(t)
    assert out["ended"] and out.get("error") == "ollama.not_answering", out
    assert len(stand.requests) == 1


def test_a_cancel_during_the_incident_ends_it_as_a_cancel(stand):
    stand.plan = ["silent", "silent"]
    t, told = _translator(stand)
    cancel = threading.Event()
    out: dict[str, Any] = {}

    def run() -> None:
        try:
            t.translate_page([LINE], cancel=cancel)
        except BaseException as e:  # noqa: BLE001
            out["error"] = type(e).__name__

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(BOUND_S + 0.3)  # (the second request under way)
    cancel.set()
    thread.join(3.0)
    assert not thread.is_alive() and out["error"] == "Cancelled"


def test_the_log_names_the_incident_and_never_a_line(stand, caplog):
    stand.plan = ["silent", "answer"]
    t, _told = _translator(stand)
    with caplog.at_level(logging.INFO, logger="taslation.translate.ollama"):
        assert _asked(t).get("result") == ["EN:" + LINE]
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "no answer" in text and "asked again" in text and LINE not in text


def test_a_load_whose_server_stops_answering_ends_as_no_answer(stand):
    stand.loaded, stand.load, stand.ps = False, "silent", "answer"
    t, _told = _translator(stand)
    cancel = threading.Event()
    out: dict[str, Any] = {}

    def run() -> None:
        try:
            t.ensure_loaded(cancel)
        except TranslationError as e:
            out["error"] = e.message.code

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.3)
    stand.ps = "silent"  # (the server stops answering anything while the model loads)
    thread.join(WAIT_S)
    cancel.set()
    assert not thread.is_alive() and out.get("error") == "ollama.not_answering"
    assert not t._loading.locked()


def _silent_soon(stand: Stand, after: float = 0.3) -> None:
    """/api/ps silent from *after* seconds on (the server stops answering anything while the model loads)."""
    threading.Timer(after, lambda: setattr(stand, "ps", "silent")).start()


def test_a_request_whose_load_gets_no_answer_has_the_server_started_again_and_is_answered(stand):
    stand.loaded, stand.load = False, "silent"
    restart = Restarts(stand, True)
    t, told = _translator(stand, restart)
    _silent_soon(stand)
    out = _asked(t)
    assert out["ended"] and out.get("result") == ["EN:" + LINE], out
    assert restart.calls == 1 and [r["mode"] for r in stand.requests] == ["answer"]
    assert _codes(told).count("ollama.no_answer") == 1 and t.silent == 0


def test_a_load_ahead_of_the_page_ends_with_the_load_it_waits_for(stand):
    from types import SimpleNamespace

    from taslation.pipeline import LoadAhead

    stand.loaded, stand.load = False, "silent"
    t, _told = _translator(stand)
    ahead = LoadAhead(SimpleNamespace(translator=t, _gpu_released=0, warm_page_models=lambda: None),
                      threading.Event())
    _silent_soon(stand)
    ahead.start()
    joined = threading.Thread(target=ahead.join, daemon=True)
    joined.start()
    joined.join(WAIT_S)
    assert not joined.is_alive() and not t._loading.locked()


def test_a_load_is_waited_for_while_its_server_answers_ps(stand):
    stand.loaded, stand.load = False, 1.5  # (longer than ALIVE_MISSES looks at it)
    t, _told = _translator(stand)
    t0 = time.monotonic()
    t.ensure_loaded(threading.Event())
    assert stand.loaded and time.monotonic() - t0 >= 1.4 and stand.ps_asked >= 3


def test_a_request_waiting_for_a_load_under_way_gets_its_slow_note(stand):
    t, _told = _translator(stand)
    slow: list[float] = []
    assert t._loading.acquire(timeout=1)  # (another thread's load under way)
    try:
        cancel = threading.Event()
        thread = threading.Thread(target=lambda: t.ensure_loaded(cancel, slow.append), daemon=True)
        thread.start()
        deadline = time.monotonic() + 3.0
        while not slow and time.monotonic() < deadline:
            time.sleep(0.02)
        assert slow and slow[0] >= 0.3
    finally:
        t._loading.release()
    thread.join(3.0)
    assert not thread.is_alive()


def test_the_first_byte_may_take_three_times_the_expected_prompt_time_and_never_less_than_the_bound(monkeypatch):
    t = PlamoTranslator("http://127.0.0.1:1")
    assert t._no_answer_after(None) == ollama_mod.NO_ANSWER_S == 30.0
    assert t._no_answer_after(4.0) == 30.0 and t._no_answer_after(20.0) == 60.0
    t.num_gpu = 0  # (every layer on the processor, nothing known of the time)
    assert t._no_answer_after(None) == ollama_mod.NO_ANSWER_CPU_S == 60.0
    t.num_gpu = None
    assert t._expected_s("x" * 900) is None  # (no request measured yet)
    t._rates.extend([0.001, 0.004])  # (seconds a prompt token took: the slowest counts)
    assert t._expected_s("x" * 900) == pytest.approx(0.004 * 300)  # (`tokens_about`: 900 ASCII characters)
