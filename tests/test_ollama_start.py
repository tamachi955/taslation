"""Ollama started by TASlation (`taslation.ollama_start`), with fakes under it: no process is started, and the Ollama
that may run on this computer is never asked, started or stopped. Where it is looked for, how it is started and waited
for, the window's start with its popup, a request that finds Ollama gone, the commands, and a whole-book run that
stops rather than spins."""
from __future__ import annotations

import contextlib
import os
import subprocess
import threading
from types import SimpleNamespace

import pytest
from conftest import windows_only
from test_batch import _fake_viewer
from test_batch_messages import _reader
from test_devices import start  # noqa: F401 - the fixture of the window's start

from helpers import read_book
from taslation import cli, health, ollama_start
from taslation.batch import fatal
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.message_texts import LANGUAGES, catalog
from taslation.messages import Cancelled, Message, render
from taslation.ollama_start import OllamaStarter, find_ollama, startable
from taslation.translate import OllamaTranslator, TranslationError
from taslation.ui import jobs
from taslation.ui.dialogs import caches

URL = "http://127.0.0.1:11434"
REAL_START = OllamaStarter.start  # conftest stands in for it during a test


def start_ollama(url: str, cancel=None, on_starting=None):
    """Ollama at *url* made to answer by a starter of its own (its first try: no `RETRY_GAP_S` to wait)."""
    return REAL_START(OllamaStarter(url, on_starting), cancel)
GONE = Message("ollama.unreachable", url=URL)


class Machine:
    """This computer as the code sees it: whether Ollama answers (and how many looks after a start it takes), and the
    processes started."""

    def __init__(self):
        self.answers = False
        self.after_start: int | None = None  # looks at it after a start until it answers (None: never)
        self.started: list[tuple[list[str], dict]] = []
        self.error: OSError | None = None
        self.looks = 0

    def running(self, url, timeout=1.0):
        self.looks += 1
        if self.started and self.after_start is not None:
            if self.after_start <= 0:
                self.answers = True
            self.after_start -= 1
        return self.answers

    def popen(self, command, **options):
        if self.error is not None:
            raise self.error
        self.started.append((list(command), options))
        return SimpleNamespace()


@pytest.fixture(autouse=True)
def machine(nothing_starts_ollama, monkeypatch, tmp_path):
    m = Machine()
    monkeypatch.setattr(OllamaStarter, "start", REAL_START)
    monkeypatch.setattr(health, "ollama_running", m.running)
    monkeypatch.setattr(ollama_start.subprocess, "Popen", m.popen)
    monkeypatch.setattr(ollama_start.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(ollama_start, "START_WAIT_S", 0.05)
    monkeypatch.setattr(ollama_start, "POLL_S", 0.005)
    return m


def _install(tmp_path, *names):
    home = tmp_path / "Programs" / "Ollama"
    home.mkdir(parents=True)
    for name in names:
        (home / name).write_bytes(b"")
    return home


# ------------------------------------------------------------------------------------------ where it is found
def test_the_tray_app_comes_first_then_the_server_beside_it_then_the_path(tmp_path, monkeypatch):
    assert find_ollama() is None
    monkeypatch.setattr(ollama_start.shutil, "which", lambda name: "C:/tools/ollama.exe" if name == "ollama" else None)
    assert find_ollama() == ["C:/tools/ollama.exe", "serve"]
    home = _install(tmp_path, "ollama.exe")
    assert find_ollama() == [str(home / "ollama.exe"), "serve"]
    (home / "ollama app.exe").write_bytes(b"")
    assert find_ollama() == [str(home / "ollama app.exe")]
    monkeypatch.delenv("LOCALAPPDATA")
    assert find_ollama() == ["C:/tools/ollama.exe", "serve"]


def test_only_the_default_address_is_started_for():
    for url in (URL, "http://localhost:11434", "http://127.0.0.1:11434/"):
        assert startable(url)
    for url in ("http://127.0.0.1:11500", "http://127.0.0.1", "https://127.0.0.1:11434", "http://[::1]:11434",
                "http://127.0.0.2:11434", "http://example.com:11434", "http://127.0.0.1:port", "nonsense"):
        assert not startable(url)


# ------------------------------------------------------------------------------------------ starting it
def test_not_started_when_it_answers(machine, tmp_path):
    _install(tmp_path, "ollama app.exe")
    machine.answers = True
    assert start_ollama(URL) is None
    assert OllamaStarter(URL).start() is None and machine.started == []


@windows_only
def test_started_detached_with_no_console_and_no_shell(machine, tmp_path, monkeypatch):
    home = _install(tmp_path, "ollama app.exe")
    machine.after_start = 2
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "q8_0")
    monkeypatch.setenv("LLAMA_ARG_CACHE_RAM", "0")  # as install.ps1 sets it
    said: list[str] = []
    assert start_ollama(URL, on_starting=lambda: said.append("starting")) is None
    assert said == ["starting"] and len(machine.started) == 1
    command, options = machine.started[0]
    assert command == [str(home / "ollama app.exe")]
    assert options["creationflags"] == subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    assert options["shell"] is False
    assert (options["stdin"], options["stdout"], options["stderr"]) == (subprocess.DEVNULL,) * 3
    assert options["cwd"] == str(home)  # not TASlation's folder, which an uninstall removes
    assert "env" not in options  # what the reader set for Ollama is inherited


def test_the_server_is_run_as_ollama_serve(machine, tmp_path):
    home = _install(tmp_path, "ollama.exe")
    machine.after_start = 0
    assert start_ollama(URL) is None
    assert machine.started[0][0] == [str(home / "ollama.exe"), "serve"]


# ------------------------------------------------------------------------------------------ no prompt cache in RAM
def _started_env(machine, tmp_path, monkeypatch, stored: str | None) -> dict | None:
    """The environment the Ollama started gets (None: TASlation's own, inherited) when Windows keeps *stored* as the
    user's LLAMA_ARG_CACHE_RAM."""
    _install(tmp_path, "ollama app.exe")
    machine.after_start = 0
    asked: list[str] = []
    monkeypatch.setattr(ollama_start, "stored_value", lambda name: asked.append(name) or stored)
    assert start_ollama(URL) is None
    options = machine.started[0][1]
    if "env" not in options:
        assert asked == []  # the variable was there: nothing looked up
        return None
    assert asked == ["LLAMA_ARG_CACHE_RAM"]
    return options["env"]


def test_an_ollama_started_where_the_variable_is_set_nowhere_keeps_no_prompt_cache(machine, tmp_path, monkeypatch):
    monkeypatch.delenv("LLAMA_ARG_CACHE_RAM", raising=False)
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "q8_0")
    env = _started_env(machine, tmp_path, monkeypatch, None)
    assert env["LLAMA_ARG_CACHE_RAM"] == "0" == ollama_start.CACHE_RAM_OFF
    assert {k: v for k, v in env.items() if k != "LLAMA_ARG_CACHE_RAM"} == dict(os.environ)  # the rest unchanged
    assert env["OLLAMA_KV_CACHE_TYPE"] == "q8_0"


@pytest.mark.parametrize("stored", ["0", "4096"])
def test_the_value_windows_keeps_for_the_user_is_the_one_given(machine, tmp_path, monkeypatch, stored):
    """TASlation started before the install set the variable (or the reader set it since): the Ollama it starts gets
    what a process started now would get, the reader's 4096 as much as the install's 0."""
    monkeypatch.delenv("LLAMA_ARG_CACHE_RAM", raising=False)
    assert _started_env(machine, tmp_path, monkeypatch, stored)["LLAMA_ARG_CACHE_RAM"] == stored


@pytest.mark.parametrize("value", ["0", "4096"])
def test_a_value_in_taslation_s_own_environment_is_inherited_unchanged(machine, tmp_path, monkeypatch, value):
    monkeypatch.setenv("LLAMA_ARG_CACHE_RAM", value)
    assert _started_env(machine, tmp_path, monkeypatch, "999") is None


class _Registry:
    """winreg as `stored_value` uses it, over *values*: {(root, key): {name: (value, kind)}}."""

    def __init__(self, values):
        self.values = values

    def OpenKey(self, root, key):  # noqa: N802 - winreg's name
        if (root, key) not in self.values:
            raise FileNotFoundError(key)
        return contextlib.nullcontext((root, key))

    def QueryValueEx(self, opened, name):  # noqa: N802
        try:
            return self.values[opened][name]
        except KeyError:
            raise FileNotFoundError(name) from None


@windows_only
@pytest.mark.parametrize("user, machine_value, found", [
    ("1024", "2048", "1024"),  # the user's comes first, as in a new process's environment
    (None, "2048", "2048"),
    (None, None, None),
    ("%CACHE_MIB%", None, "512"),  # REG_EXPAND_SZ, expanded
])
def test_the_value_windows_keeps_is_the_user_s_then_the_computer_s(monkeypatch, user, machine_value, found):
    import winreg

    values = {(winreg.HKEY_CURRENT_USER, ollama_start.USER_ENV_KEY): {},
              (winreg.HKEY_LOCAL_MACHINE, ollama_start.MACHINE_ENV_KEY): {}}
    if user is not None:
        kind = winreg.REG_EXPAND_SZ if "%" in user else winreg.REG_SZ
        values[(winreg.HKEY_CURRENT_USER, ollama_start.USER_ENV_KEY)]["LLAMA_ARG_CACHE_RAM"] = (user, kind)
    if machine_value is not None:
        values[(winreg.HKEY_LOCAL_MACHINE, ollama_start.MACHINE_ENV_KEY)]["LLAMA_ARG_CACHE_RAM"] = (machine_value,
                                                                                                    winreg.REG_SZ)
    fake = _Registry(values)
    monkeypatch.setattr(winreg, "OpenKey", fake.OpenKey)
    monkeypatch.setattr(winreg, "QueryValueEx", fake.QueryValueEx)
    monkeypatch.setenv("CACHE_MIB", "512")
    assert ollama_start.stored_value("LLAMA_ARG_CACHE_RAM") == found


@windows_only
def test_a_variable_windows_does_not_keep_is_none():
    assert ollama_start.stored_value("TASLATION_TEST_NO_SUCH_VARIABLE_7F3A") is None  # (read only)


def test_not_started_for_another_port(machine, tmp_path):
    _install(tmp_path, "ollama app.exe")
    url = "http://127.0.0.1:11500"
    said = start_ollama(url)
    assert said == Message("health.ollama_down", url=url) and said.code not in ollama_start.POPUP_CODES
    assert machine.started == []


def test_not_installed(machine):
    said: list[str] = []
    assert start_ollama(URL, on_starting=lambda: said.append("x")).code == "health.ollama_not_installed"
    assert said == [] and machine.started == []  # nothing said to be starting


def test_no_answer_in_time(machine, tmp_path):
    _install(tmp_path, "ollama app.exe")
    assert start_ollama(URL).code == "health.ollama_no_answer"
    assert len(machine.started) == 1 and machine.looks >= 2  # one process, asked again and again


def test_a_process_that_cannot_start_is_no_answer(machine, tmp_path):
    _install(tmp_path, "ollama app.exe")
    machine.error = PermissionError("refused")
    assert start_ollama(URL).code == "health.ollama_no_answer"


def test_the_wait_is_cancelled_by_the_caller_s_event(machine, tmp_path, monkeypatch):
    _install(tmp_path, "ollama app.exe")
    monkeypatch.setattr(ollama_start, "START_WAIT_S", 30.0)
    cancel = threading.Event()
    timer = threading.Timer(0.02, cancel.set)
    timer.start()
    assert start_ollama(URL, cancel).code == "health.ollama_down"  # at once, and no popup's worth of failure
    timer.join()
    assert len(machine.started) == 1
    machine.started.clear()
    assert start_ollama(URL, cancel).code == "health.ollama_down" and machine.started == []  # set before: not started


def test_one_try_in_sixty_seconds(machine, tmp_path, monkeypatch):
    _install(tmp_path, "ollama app.exe")
    clock = [1000.0]
    monkeypatch.setattr(ollama_start.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ollama_start, "START_WAIT_S", 0.0)
    starter = OllamaStarter(URL)
    assert starter.start().code == "health.ollama_no_answer" and not starter.revive()
    clock[0] += 59.0
    assert starter.start() == Message("health.ollama_down", url=URL) and len(machine.started) == 1
    clock[0] += 2.0
    assert starter.start().code == "health.ollama_no_answer" and len(machine.started) == 2
    machine.answers = True
    assert starter.revive() and len(machine.started) == 2  # within the gap, and it answers: all is well


# ------------------------------------------------------------------------------------------ the window's start
def _popups(events):
    return [data["message"].code for kind, data in events if kind == "ollama_failed"]


def test_the_window_starts_ollama_before_the_setup_check(machine, start, tmp_path):  # noqa: F811
    _install(tmp_path, "ollama app.exe")
    machine.after_start = 1
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    events = w.events()
    assert events[0] == ("status", {"key": "Starting the translation program..."}) and events[1][0] == "health"
    assert _popups(events) == [] and len(machine.started) == 1
    assert start.order[0] == "health"  # and from here on as if it had been running
    assert ("warm-up", "qwen3.5:4b") in start.order


@pytest.mark.parametrize("installed, code", [(True, "health.ollama_no_answer"), (False, "health.ollama_not_installed")])
def test_a_failed_start_is_a_popup_once_and_the_window_goes_on(machine, start, tmp_path, installed, code):  # noqa: F811
    if installed:
        _install(tmp_path, "ollama app.exe")
    w = start(([Message("health.ollama_down", url=URL)], None))
    w._job_init()
    events = w.events()
    assert _popups(events) == [code]
    assert [k for k, _d in events if k in ("health", "ready")] == ["health", "ready"]
    assert "ocr" in start.order  # pages already translated still work


def test_another_port_gets_no_popup(machine, start, tmp_path):  # noqa: F811
    _install(tmp_path, "ollama app.exe")
    w = start(([Message("health.ollama_down", url="http://127.0.0.1:11500")], None), ollama_url="http://127.0.0.1:11500")
    w._job_init()
    assert _popups(w.events()) == [] and machine.started == []


def test_the_popup_says_it_in_the_window_s_box(monkeypatch):
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, title="TASlation", **_k: shown.append((title, text)))
    w = SimpleNamespace(reading=False, _over_on=False)
    w._warn_unasked = jobs.JobsMixin._warn_unasked.__get__(w)
    jobs.JobsMixin._handle_event(w, "ollama_failed", {"message": Message("health.ollama_not_installed")})
    assert shown == [("TASlation", "The translation program is not installed. Double-click install.cmd in the TASlation folder.")]
    shown.clear()
    jobs.JobsMixin._handle_event(w, "ollama_failed", {"message": Message("health.ollama_no_answer")})
    assert shown == [("TASlation", "The translation program did not start. Restart your PC, then open TASlation again. Pages already "
                                   "translated can still be read.")]


def test_a_request_that_fails_for_good_tells_the_banner(machine):
    checked: list[str] = []
    w = SimpleNamespace(_ollama=OllamaStarter(URL), _check_in_background=lambda: checked.append("checked"))
    assert not jobs.JobsMixin._revive_ollama(w)
    assert checked == ["checked"]
    machine.answers = True
    assert jobs.JobsMixin._revive_ollama(w) and checked == ["checked"]


def test_before_a_scan_s_check_ollama_is_started(machine, tmp_path):
    _install(tmp_path, "ollama app.exe")
    machine.after_start = 0
    jobs.JobsMixin._ollama_back(SimpleNamespace(_ollama=OllamaStarter(URL)))
    assert len(machine.started) == 1
    jobs.JobsMixin._ollama_back(SimpleNamespace(_ollama=None))  # the start has not got that far: nothing to do


# ------------------------------------------------------------------------------------------ a request finds it gone
class Gone:
    """`_request_once` / `_stream_once` of a translator: refused *refusals* times, then an answer."""

    def __init__(self, refusals=1):
        self.refusals = refusals
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        if self.refusals > 0:
            self.refusals -= 1
            raise TranslationError(GONE)
        return {"ok": True}


def _translator(revive):
    tr = OllamaTranslator(URL, "m")
    tr.revive = revive
    return tr


@pytest.mark.parametrize("method", ["request", "stream"])
def test_a_request_is_tried_again_once_after_the_start(method, monkeypatch):
    asked: list = []
    tr = _translator(lambda cancel: asked.append(cancel) or True)
    gone = Gone(refusals=1)
    monkeypatch.setattr(tr, f"_{method}_once", gone)
    send = (lambda: tr._request("/x")) if method == "request" else (lambda: tr._stream("/x", {}, print))
    assert send() == {"ok": True} and gone.calls == 2 and len(asked) == 1

    gone = Gone(refusals=9)
    monkeypatch.setattr(tr, f"_{method}_once", gone)
    with pytest.raises(TranslationError) as info:
        send()
    assert gone.calls == 2 and len(asked) == 2  # the second refusal is the end of it, no third request
    assert info.value.message == GONE


def test_a_failed_start_leaves_the_request_s_own_failure(monkeypatch):
    tr = _translator(lambda cancel: False)
    gone = Gone(refusals=9)
    monkeypatch.setattr(tr, "_request_once", gone)
    with pytest.raises(TranslationError) as info:
        tr._request("/x")
    assert gone.calls == 1 and info.value.message == GONE and fatal(info.value.message)


def test_other_failures_never_start_ollama(monkeypatch):
    asked: list = []
    tr = _translator(lambda cancel: asked.append(cancel) or True)

    def timed_out(*_a, **_k):
        raise TranslationError(Message("ollama.timeout", seconds=9.0))

    monkeypatch.setattr(tr, "_request_once", timed_out)
    with pytest.raises(TranslationError):
        tr._request("/x")
    assert asked == []


def test_without_a_reviver_nothing_is_tried(monkeypatch):
    tr = OllamaTranslator(URL, "m")
    assert tr.revive is None
    gone = Gone(refusals=9)
    monkeypatch.setattr(tr, "_request_once", gone)
    assert not tr.ping() and gone.calls == 1


def test_the_stop_during_the_start_cancels_the_page(monkeypatch):
    cancel = threading.Event()

    def revive(event):
        assert event is cancel
        event.set()
        return False

    tr = _translator(revive)
    monkeypatch.setattr(tr, "_stream_once", Gone(refusals=9))
    with pytest.raises(Cancelled):
        tr._stream("/x", {}, print, cancel)


def test_the_real_gate_lets_one_try_through_for_many_requests(machine, tmp_path, monkeypatch):
    _install(tmp_path, "ollama app.exe")
    tr = _translator(OllamaStarter(URL).revive)
    gone = Gone(refusals=99)
    monkeypatch.setattr(tr, "_request_once", gone)
    for _ in range(5):
        with pytest.raises(TranslationError):
            tr._request("/x")
    assert len(machine.started) == 1 and gone.calls == 5


def test_a_whole_book_run_stops_rather_than_spins(machine, sample_page, sample_page2, settings, monkeypatch, tmp_path):
    """Ollama gone during a run, and it does not come back: one start at most, one request more, and the run ends
    with the reason it always ended with."""
    _install(tmp_path, "ollama app.exe")
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 8
    tr = _translator(OllamaStarter(URL).revive)
    gone, looks = Gone(refusals=999), Gone(refusals=999)
    monkeypatch.setattr(tr, "_stream_once", gone)
    monkeypatch.setattr(tr, "_request_once", looks)  # /api/ps before a request, the release at the end
    progress = read_book(_reader(settings, tr, CacheStore(settings.cache_dir).open("Gone", "fake"), context_mode=True,
                       preflight=[]))
    assert progress.reason == GONE and progress.pages == 3  # (no request while the pages turn)
    assert len(machine.started) == 1 and gone.calls <= 2 and looks.calls <= 2


# ------------------------------------------------------------------------------------------ the commands
@pytest.fixture
def engine(monkeypatch):
    import taslation.ocr

    made = SimpleNamespace()
    monkeypatch.setattr(taslation.ocr, "Readers", lambda path, threads=0: made)
    monkeypatch.setattr(cli, "warm_ollama", lambda settings, translator: False)
    return made


@pytest.mark.parametrize("warm_first", [True, False])
def test_a_command_that_translates_starts_ollama(machine, engine, tmp_path, capsys, warm_first):
    _install(tmp_path, "ollama app.exe")
    machine.after_start = 0
    pipeline = cli.build_pipeline(Settings(state_dir=tmp_path / "state"), "ollama", None, warm_first=warm_first)
    assert len(machine.started) == 1 and pipeline.translator.revive is not None
    assert "note: Starting the translation program..." in capsys.readouterr().err


def test_a_command_says_what_stands_in_the_way(machine, engine, tmp_path, capsys):
    cli.build_pipeline(Settings(state_dir=tmp_path / "state"), "ollama", None, warm_first=True)
    assert "note: The translation program is not installed. Double-click install.cmd in the TASlation folder." in capsys.readouterr().err


def test_a_command_with_no_use_for_ollama_leaves_it_alone(machine, engine, tmp_path):
    _install(tmp_path, "ollama app.exe")
    cli.build_pipeline(Settings(state_dir=tmp_path / "state"), "echo", None, warm_first=True)
    assert machine.started == [] and machine.looks == 0


def test_doctor_starts_nothing_and_says_what_to_do(machine, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(OllamaTranslator, "ping", lambda self: False)
    args = SimpleNamespace(config=None)
    settings = Settings(state_dir=tmp_path / "state")
    assert cli.cmd_doctor(args, settings) == 1
    assert "Ollama: not installed. Run install.cmd again to install it." in capsys.readouterr().out
    _install(tmp_path, "ollama app.exe")
    assert cli.cmd_doctor(args, settings) == 1
    assert (f"Ollama: not running at {URL}. TASlation starts it when it translates; if that fails, restart your PC, "
            "then open TASlation again.") in capsys.readouterr().out
    assert cli.cmd_doctor(args, Settings(state_dir=tmp_path / "state", ollama_url="http://127.0.0.1:11500")) == 1
    assert "not running at http://127.0.0.1:11500" in capsys.readouterr().out
    assert machine.started == []


def test_translator_built_for_doctor_has_no_reviver():
    assert cli.build_translator(Settings(), "ollama").revive is None


# ------------------------------------------------------------------------------------------ the words
@pytest.mark.parametrize("lang", ["en", *LANGUAGES])
def test_the_texts_never_send_a_reader_to_a_tray_or_a_terminal(lang):
    texts = catalog(lang)
    for code in ("health.ollama_not_installed", "health.ollama_no_answer", "health.ollama_down"):
        line = render(Message(code, url=URL) if code.endswith("down") else Message(code), texts)
        assert "Ollama" not in line and "{" not in line
        for word in ("tray", "Start menu", "terminal", "start Ollama"):
            assert word not in line
    assert "install.cmd" in texts["health.ollama_not_installed"]
