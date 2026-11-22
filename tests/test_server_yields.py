"""The work behind the reader yields the processor (`ollama_start.asking_behind`, `yield_server`, `before_request`):
a step of the backlog that asks the translator has the server TASlation started - and the processes it started -
compute at below-normal priority from the step's start until a request that is not the backlog's has the server
compute; each then goes back to the class the server had. Only the server this process started and alone uses, never
one at a class that low already. With fakes under it, then on stand-ins of this test's own (``python -c``), never on
Ollama; invented lines only."""
from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import threading
import time

import pytest
from conftest import windows_only
from fake_ollama import FakeOllama
from helpers import EN_TEXTS
from test_backlog import Turning, _confirmed, _drain, _job, _pipeline

from taslation import ollama_start
from taslation.backlog import Backlog
from taslation.ollama_start import BELOW_NORMAL_PRIORITY_CLASS as BELOW
from taslation.ollama_start import IDLE_PRIORITY_CLASS as IDLE
from taslation.ollama_start import NORMAL_PRIORITY_CLASS as NORMAL
from taslation.ollama_start import asking_behind, before_request, server_yields
from taslation.translate import DictTranslator, OllamaTranslator

pytestmark = windows_only  # (Windows' priority classes: elsewhere nothing is lowered)

URL = "http://127.0.0.1:11435"
REAL_SET = ollama_start.set_priority_class  # (conftest refuses it during a test; the stand-ins' tests put it back)
REAL_TERMINATE = ollama_start.terminate  # (likewise: for the stand-ins' children a failed test left)
SERVER, RUNNER = (501, 11), (502, 12)


class Classes:
    """The processes as the code sees them: each one's priority class, what the server started, the changes made."""

    def __init__(self):
        self.of = {SERVER: NORMAL, RUNNER: NORMAL}
        self.children = [RUNNER]
        self.sets: list[tuple[tuple[int, int], int]] = []
        self.refuse: set[tuple[int, int]] = set()

    def get(self, pid, started):
        return self.of.get((pid, started))

    def set(self, pid, started, value):
        if (pid, started) not in self.of or (pid, started) in self.refuse:
            return False
        self.sets.append(((pid, started), value))
        self.of[(pid, started)] = value
        return True


@pytest.fixture
def classes(monkeypatch):
    c = Classes()
    monkeypatch.setattr(ollama_start, "own_server", lambda url: SERVER if url == URL else None)
    monkeypatch.setattr(ollama_start, "priority_class", c.get)
    monkeypatch.setattr(ollama_start, "set_priority_class", c.set)
    monkeypatch.setattr(ollama_start, "descendants", lambda pid, started: list(c.children) if (pid, started) == SERVER
                        else [])
    return c


def test_the_backlog_s_requests_are_computed_low_until_a_request_of_another_s(classes):
    with asking_behind(URL):
        assert classes.of == {SERVER: BELOW, RUNNER: BELOW} and server_yields()
        before_request("/api/generate")  # (the backlog's own request: it stays low)
        assert classes.of == {SERVER: BELOW, RUNNER: BELOW}
    assert classes.of == {SERVER: BELOW, RUNNER: BELOW}  # (not as the step ends: its request given up may compute on)
    for path in ("/api/ps", "/api/show", "/api/tags", "/api/version"):  # (looks: nothing computed)
        before_request(path)
    assert classes.of == {SERVER: BELOW, RUNNER: BELOW}
    before_request("/api/chat")  # (the page on show's first request)
    assert classes.of == {SERVER: NORMAL, RUNNER: NORMAL} and not server_yields()
    done = len(classes.sets)
    before_request("/api/generate")
    assert len(classes.sets) == done  # (none lowered: nothing asked of Windows)


def test_a_runner_started_while_it_was_low_goes_back_with_it(classes):
    with asking_behind(URL):
        pass
    late = (503, 13)
    classes.of[late] = BELOW  # (a model loaded meanwhile: its process got the server's class)
    classes.children.append(late)
    before_request("/api/generate")
    assert classes.of == {SERVER: NORMAL, RUNNER: NORMAL, late: NORMAL}


def test_each_goes_back_to_the_class_the_server_had_and_a_low_one_is_never_raised(classes):
    classes.of[SERVER] = 0x8000  # ABOVE_NORMAL: TASlation's own, which the server it started got
    with asking_behind(URL):
        assert classes.of[SERVER] == BELOW
    before_request("/api/generate")
    assert classes.of == {SERVER: 0x8000, RUNNER: 0x8000}

    for low in (BELOW, IDLE):  # (as low already, or lower: nothing changed, nothing set back)
        classes.of = {SERVER: low, RUNNER: low}
        classes.sets.clear()
        with asking_behind(URL):
            assert not server_yields()
        before_request("/api/generate")
        assert classes.sets == [] and classes.of == {SERVER: low, RUNNER: low}


def test_a_server_this_process_did_not_start_or_shares_is_never_touched(classes):
    with asking_behind("http://127.0.0.1:11434"):  # (`own_server`: none for that address)
        pass
    with asking_behind(None):  # (a translator that is no server's)
        pass
    before_request("/api/generate")
    assert classes.sets == []


def test_a_process_that_cannot_be_set_is_left_and_nothing_raises(classes, monkeypatch):
    classes.refuse = {SERVER}
    with asking_behind(URL):
        assert not server_yields()
    assert classes.sets == []  # (the server refused: its runner is not lowered alone)
    classes.refuse = {RUNNER}
    with asking_behind(URL):
        assert classes.of == {SERVER: BELOW, RUNNER: NORMAL}
    before_request("/api/generate")
    assert classes.of == {SERVER: NORMAL, RUNNER: NORMAL}

    def broken(*_a):
        raise OSError("gone")

    monkeypatch.setattr(ollama_start, "descendants", broken)
    classes.refuse = set()
    with asking_behind(URL):  # (the step asks all the same: its server low, its runner not found)
        assert classes.of == {SERVER: BELOW, RUNNER: NORMAL}
    before_request("/api/generate")  # (and so does the request: the server back all the same)
    assert classes.of == {SERVER: NORMAL, RUNNER: NORMAL}


def test_a_request_of_another_thread_is_no_backlog_s(classes):
    lowered = threading.Event()
    go_on = threading.Event()

    def step():
        with asking_behind(URL):
            lowered.set()
            go_on.wait(5)

    thread = threading.Thread(target=step)
    thread.start()
    assert lowered.wait(5)
    before_request("/api/generate")  # (a load for the page on show, on a thread of its own)
    assert classes.of == {SERVER: NORMAL, RUNNER: NORMAL}
    go_on.set()
    thread.join(5)


def test_the_backlog_s_translation_step_asks_behind_the_reader(settings, sample_page, monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(ollama_start, "yield_server", lambda url: asked.append(url) or True)

    class Server(DictTranslator):
        base = URL  # (as `OllamaTranslator` has it)

        def translate_page(self, texts, *args, **kwargs):
            self.behind.append(getattr(ollama_start._behind, "on", False))
            return super().translate_page(texts, *args, **kwargs)

    b = Backlog(lambda kind, **data: None)
    p = _pipeline(settings, Turning(EN_TEXTS, answer=1))
    _job(p, b, sample_page, _confirmed())  # (turned past after its first line: caught)
    assert len(b.entries) == 1
    p.translator = translator = Server(EN_TEXTS)
    translator.behind = []
    assert "translate" in _drain(p, b)
    assert asked == [URL] and translator.behind and all(translator.behind)
    assert not getattr(ollama_start._behind, "on", False)  # (the step over: the worker's next request is the page's)


def test_the_translator_says_each_request_before_it_is_sent(monkeypatch):
    paths: list[tuple[str, bool]] = []
    monkeypatch.setattr(ollama_start, "before_request",
                        lambda path: paths.append((path, getattr(ollama_start._behind, "on", False))))
    with FakeOllama() as server:
        translator = OllamaTranslator(url=server.url, model="qwen3.5:4b")
        payload = {"model": "qwen3.5:4b", "messages": [{"role": "user", "content": "notes"}], "options": {}}
        translator._chat_once(dict(payload), 10.0)  # (in one piece)
        translator._chat_once(dict(payload), 10.0, cancel=threading.Event())  # (streamed)
        translator._request_once("/api/tags")
        with asking_behind(None):
            translator._chat_once(dict(payload), 10.0, cancel=threading.Event())
    assert paths == [("/api/chat", False), ("/api/chat", False), ("/api/tags", False), ("/api/chat", True)]


# ------------------------------------------------------------------------------------------ on stand-ins of its own
BASE_PYTHON = getattr(sys, "_base_executable", "") or sys.executable
# Ollama's server as a stand-in: one child at once (the model's process), one more once a file says so (a model loaded
# while it is low), then a wait in short sleeps.
SERVER_CODE = ("import os, subprocess, sys, time\n"
               "model = [sys.executable, '-I', '-S', '-c', 'import time; time.sleep(60)']\n"
               "kids = [subprocess.Popen(model)]\n"
               "flag = sys.argv[1]\n"
               "while True:\n"
               "    if len(kids) == 1 and os.path.exists(flag):\n"
               "        kids.append(subprocess.Popen(model))\n"
               "    time.sleep(0.05)\n")


@pytest.fixture
def stand_in(monkeypatch, tmp_path):
    monkeypatch.setattr(ollama_start, "set_priority_class", REAL_SET)
    procs: list[tuple[subprocess.Popen, int]] = []

    def start(code: str, *args: str) -> tuple[int, int]:
        proc = subprocess.Popen([BASE_PYTHON, "-I", "-S", "-c", code, *args], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        deadline = time.monotonic() + 10
        info = ollama_start.process_info(proc.pid)
        while info is None and time.monotonic() < deadline:
            time.sleep(0.05)
            info = ollama_start.process_info(proc.pid)
        procs.append((proc, info.started))
        return proc.pid, info.started

    yield start
    for proc, began in procs:  # (*proc* holds the stand-in's number: what has it as its parent's is the stand-in's)
        for child, child_started in ollama_start.descendants(proc.pid, began):
            REAL_TERMINATE(child, child_started)
        with contextlib.suppress(OSError):
            proc.kill()


def _pythons(server: tuple[int, int], count: int) -> list[tuple[int, int]]:
    """The stand-in's own children (Pythons, as it is: not its console's host), once there are *count* of them."""
    import os

    python = os.path.normcase(os.path.abspath(BASE_PYTHON))
    deadline = time.monotonic() + 10
    found: list[tuple[int, int]] = []
    while time.monotonic() < deadline:
        found = [(pid, started) for pid, started in ollama_start.descendants(*server)
                 if (info := ollama_start.process_info(pid)) is not None
                 and os.path.normcase(os.path.abspath(info.exe)) == python]
        if len(found) >= count:
            return found
        time.sleep(0.05)
    return found


def _claimed(monkeypatch, tmp_path, server: tuple[int, int], users: list[dict]) -> None:
    """*server* written down as the server TASlation started for URL, with *users*, and claimed by this process."""
    path = tmp_path / ollama_start.RECORD_FILE
    info = ollama_start.process_info(server[0])
    path.write_text(json.dumps({"pid": server[0], "started": server[1], "exe": info.exe, "url": URL, "users": users}),
                    "utf-8")
    monkeypatch.setattr(ollama_start, "_claims", {path: ollama_start._Claim(URL, frozenset())})


def test_the_server_and_what_it_starts_compute_low_and_go_back(stand_in, monkeypatch, tmp_path):
    flag = tmp_path / "load another"
    server = stand_in(SERVER_CODE, str(flag))
    first = _pythons(server, 1)
    assert len(first) == 1
    assert ollama_start.priority_class(*server) == NORMAL  # (as this test's process: a server started from it)
    _claimed(monkeypatch, tmp_path, server, [ollama_start.this_process()])
    assert ollama_start.own_server(URL) == server
    with asking_behind(URL):
        assert ollama_start.priority_class(*server) == BELOW and ollama_start.priority_class(*first[0]) == BELOW
    flag.write_text("", "utf-8")  # (a model loaded while it is low: its process gets the server's class)
    both = _pythons(server, 2)
    assert len(both) == 2
    assert all(ollama_start.priority_class(*p) == BELOW for p in both)
    before_request("/api/generate")
    assert ollama_start.priority_class(*server) == NORMAL
    assert all(ollama_start.priority_class(*p) == NORMAL for p in both)


def test_a_server_another_taslation_uses_is_left_as_it_is(stand_in, monkeypatch, tmp_path):
    server = stand_in(SERVER_CODE, str(tmp_path / "never"))
    other = stand_in("import time; time.sleep(60)")  # (another TASlation's process, that runs)
    _claimed(monkeypatch, tmp_path, server, [ollama_start.this_process(), {"pid": other[0], "started": other[1]}])
    assert ollama_start.own_server(URL) is None
    with asking_behind(URL):
        assert ollama_start.priority_class(*server) == NORMAL
    _claimed(monkeypatch, tmp_path, server, [ollama_start.this_process(), {"pid": other[0], "started": other[1] + 1}])
    assert ollama_start.own_server(URL) == server  # (a user that no longer runs: a number reused since)
