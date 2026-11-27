"""Ollama started and stopped by TASlation (`taslation.ollama_start`), with fakes under it: no Ollama is started or
stopped, and the Ollama that may run on this computer is never asked. Where it is looked for, how it is started (the
server itself, hidden, with its environment) and waited for, the record of the server TASlation started and of who
uses it, the end (stopped; left to another TASlation, to another program's model, to a person's own Ollama; adopted
after a crash; a reused process number; a stop that does not come), the window's start and close, a request that finds
Ollama gone, and the commands and doctor. The process functions
themselves run on Windows on stand-ins of this test's own (``python -c``), never on Ollama."""
from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import windows_only
from test_devices import start, worker  # noqa: F401 - the fixture of the window's start

from taslation import cli, devices, health, ollama_start
from taslation import translator_install as ti
from taslation.translate.sequence import fatal
from taslation.config import Settings
from taslation.message_texts import LANGUAGES, catalog
from taslation.messages import Cancelled, Message, render
from taslation.ollama_start import (FOREIGN, IN_USE, KEPT, KILL_WAIT_S, STOP_WAIT_S, STOPPED, OllamaStarter,
                                    ProcessInfo, find_ollama, finish_all, owns_server, startable)
from taslation.translate import OllamaTranslator, TranslationError
from taslation.ui import jobs
from taslation.ui.dialogs import caches

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:11434"
REAL_START = OllamaStarter.start  # conftest stands in for it during a test ...
REAL = {name: getattr(ollama_start, name) for name in (  # ... and for these
    "launch", "process_info", "descendants", "wait_exit", "terminate", "pinned", "ask_to_stop", "stop_server",
    "small_gpu")}
REAL_POPEN = subprocess.Popen
ME = os.getpid()
GONE = Message("ollama.unreachable", url=URL)


def start_ollama(url: str, cancel=None, on_starting=None, state=None, own=()):
    """Ollama at *url* made to answer by a starter of its own (its first try: no `RETRY_GAP_S` to wait)."""
    return REAL_START(OllamaStarter(url, on_starting, state_dir=state, own=own), cancel)


class Machine:
    """This computer as the code sees it: whether Ollama answers (and how many looks after a start it takes), the
    processes running (number -> program and start time: this one among them), the processes started, the models
    Ollama has loaded (/api/ps), and what was done to stop a server."""

    def __init__(self):
        self.answers = False
        self.after_start: int | None = None  # looks at it after a start until it answers (None: never)
        self.started: list[tuple[list[str], dict]] = []
        self.pids: list[int] = []  # of the processes started, in order
        self.error: OSError | None = None
        self.looks = 0
        self.clock = 1000
        self.procs: dict[int, ProcessInfo] = {ME: ProcessInfo(sys.executable, 1)}
        self.children: dict[int, list[tuple[int, int]]] = {}
        self.loaded: list[str] | None = []
        self.ps_timeouts: list[float] = []
        self.obeys = True  # a server asked to stop ends (and its children with it)
        self.killable = True
        self.asked: list[int] = []
        self.terminated: list[int] = []
        self.waits: list[float] = []
        self.window = True  # what `window_choice` says
        self.chosen: list[Any] = []  # the settings it was asked with

    def choose(self, settings):
        self.chosen.append(settings)
        return self.window

    def running(self, url, timeout=1.0):
        self.looks += 1
        if self.started and self.after_start is not None:
            if self.after_start <= 0:
                self.answers = True
            self.after_start -= 1
        return self.answers

    def spawn(self, exe: str) -> int:
        self.clock += 1
        pid = 40000 + self.clock
        self.procs[pid] = ProcessInfo(exe, self.clock)
        return pid

    def popen(self, command, **options):
        if self.error is not None:
            raise self.error
        self.started.append((list(command), options))
        self.pids.append(self.spawn(command[0]))
        return SimpleNamespace(pid=self.pids[-1])

    def info(self, pid):
        return self.procs.get(pid)

    def _end(self, pid):
        self.procs.pop(pid, None)
        for child, _started in self.children.get(pid, []):
            self.procs.pop(child, None)
        if pid in self.pids:
            self.answers = False

    def ask(self, pid):
        self.asked.append(pid)
        delivered = pid in self.procs
        if self.obeys:
            self._end(pid)
        return delivered

    def wait(self, pid, started, seconds):
        self.waits.append(seconds)
        info = self.procs.get(pid)
        return info is None or info.started != started

    def terminate(self, pid, started):
        info = self.procs.get(pid)
        if info is None or info.started != started:
            return False
        self.terminated.append(pid)
        if self.killable:
            self._end(pid)
        return True

    @contextlib.contextmanager
    def pinned(self, pid, started):
        info = self.procs.get(pid)
        yield info is not None and info.started == started

    def ps(self, url, timeout=1.0):
        self.ps_timeouts.append(timeout)
        return self.loaded


@pytest.fixture(autouse=True)
def machine(nothing_starts_ollama, monkeypatch, tmp_path):
    m = Machine()
    monkeypatch.setattr(OllamaStarter, "start", REAL_START)
    monkeypatch.setattr(health, "ollama_running", m.running)
    monkeypatch.setattr(health, "loaded_models", m.ps)
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: None)  # (never this computer's Ollama)
    monkeypatch.setattr(ollama_start, "launch", REAL["launch"])
    monkeypatch.setattr(ollama_start, "stop_server", REAL["stop_server"])
    monkeypatch.setattr(ollama_start.subprocess, "Popen", m.popen)
    monkeypatch.setattr(ollama_start, "process_info", m.info)
    monkeypatch.setattr(ollama_start, "descendants", lambda pid, started: list(m.children.get(pid, [])))
    monkeypatch.setattr(ollama_start, "ask_to_stop", m.ask)
    monkeypatch.setattr(ollama_start, "wait_exit", m.wait)
    monkeypatch.setattr(ollama_start, "terminate", m.terminate)
    monkeypatch.setattr(ollama_start, "pinned", m.pinned)
    monkeypatch.setattr(ollama_start, "small_gpu", lambda: False)
    monkeypatch.setattr(ollama_start.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("LLAMA_ARG_CACHE_RAM", "0")  # (the environment's own tests take them away)
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "q8_0")
    monkeypatch.setenv("LLAMA_ARG_SWA_FULL", "0")
    monkeypatch.delenv("OLLAMA_NO_CLOUD", raising=False)  # (the tests that want it set it)
    monkeypatch.setattr(ollama_start, "_told_cloud", set())  # (the fakes' process numbers come again in every test)
    monkeypatch.setattr(ollama_start, "window_choice", m.choose)  # (the settings it is asked with are kept)
    monkeypatch.setattr(ollama_start, "START_WAIT_S", 0.05)
    monkeypatch.setattr(ollama_start, "POLL_S", 0.005)
    return m


def _install(tmp_path, *names):
    home = tmp_path / "Programs" / "Ollama"
    home.mkdir(parents=True, exist_ok=True)
    for name in names or ("ollama app.exe", "ollama.exe"):
        (home / name).write_bytes(b"")
    return home


def _state(tmp_path) -> Path:
    return tmp_path / "state"


def _record_file(tmp_path) -> Path:
    return _state(tmp_path) / ollama_start.RECORD_FILE


def _record(tmp_path) -> dict:
    return json.loads(_record_file(tmp_path).read_text("utf-8"))


def _write_record(tmp_path, **record) -> None:
    _state(tmp_path).mkdir(parents=True, exist_ok=True)
    _record_file(tmp_path).write_text(json.dumps({"url": URL, "users": [], **record}), "utf-8")


def _started_one(machine, tmp_path, **kwargs) -> int:
    """Ollama started by this process for the state folder; its process number."""
    _install(tmp_path)
    machine.after_start = 0
    assert start_ollama(URL, state=_state(tmp_path), **kwargs) is None
    assert len(machine.pids) == 1
    return machine.pids[0]


# ------------------------------------------------------------------------------------------ where it is found
def test_the_server_beside_the_tray_app_comes_first_then_the_path_and_never_the_tray_app(tmp_path, monkeypatch):
    assert find_ollama() is None
    home = _install(tmp_path, "ollama app.exe")
    assert find_ollama() is None  # the tray app alone is never started
    monkeypatch.setattr(ollama_start.shutil, "which", lambda name: "C:/tools/ollama.exe" if name == "ollama" else None)
    assert find_ollama() == ["C:/tools/ollama.exe", "serve"]
    (home / "ollama.exe").write_bytes(b"")
    assert find_ollama() == [str(home / "ollama.exe"), "serve"]
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
    _install(tmp_path)
    machine.answers = True
    assert start_ollama(URL) is None
    assert OllamaStarter(URL).start() is None and machine.started == []


@windows_only
def test_the_server_is_started_hidden_in_a_process_group_of_its_own_with_no_shell(machine, tmp_path):
    home = _install(tmp_path)
    machine.after_start = 2
    said: list[str] = []
    assert start_ollama(URL, on_starting=lambda: said.append("starting")) is None
    assert said == ["starting"] and len(machine.started) == 1
    command, options = machine.started[0]
    assert command == [str(home / "ollama.exe"), "serve"]  # the server itself, never the tray app
    assert options["creationflags"] == subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    assert options["shell"] is False
    assert (options["stdin"], options["stdout"], options["stderr"]) == (subprocess.DEVNULL,) * 3
    assert options["cwd"] == str(home)  # not TASlation's folder, which an uninstall removes
    # TASlation's own environment (what the reader set for Ollama comes with it), Ollama's cloud features off
    assert options["env"] == {**os.environ, "OLLAMA_NO_CLOUD": "1"}


# ------------------------------------------------------------------------------------------ the server's environment
VARIABLES = ("LLAMA_ARG_CACHE_RAM", "OLLAMA_KV_CACHE_TYPE", "LLAMA_ARG_SWA_FULL")


def _started_env(machine, tmp_path, monkeypatch, stored=None, small=False, settings=None, state=None,
                 library_pull=False):
    """The environment the Ollama started gets when Windows keeps *stored* for the user, on a GPU of 6 GB or less
    (*small*), for *settings*, by a starter for *library_pull*; and the variables looked up."""
    _install(tmp_path)
    machine.after_start = 0
    asked: list[str] = []
    monkeypatch.setattr(ollama_start, "stored_value", lambda name: asked.append(name) or (stored or {}).get(name))
    monkeypatch.setattr(ollama_start, "small_gpu", lambda: small)
    assert REAL_START(OllamaStarter(URL, state_dir=state, settings=settings, library_pull=library_pull)) is None
    return machine.started[0][1].get("env"), asked


def _unset(monkeypatch, *names):
    for name in names or VARIABLES:
        monkeypatch.delenv(name)


def test_where_no_variable_is_set_the_server_gets_the_window_cache_256_mib_in_ram_and_a_small_gpu_q8(
        machine, tmp_path, monkeypatch):
    _unset(monkeypatch)
    s = Settings(state_dir=tmp_path / "s", ocr_runs_on="auto")
    env, asked = _started_env(machine, tmp_path, monkeypatch, small=True, settings=s)
    assert asked == ["OLLAMA_KV_CACHE_TYPE", "LLAMA_ARG_SWA_FULL", "LLAMA_ARG_CACHE_RAM"]
    assert machine.chosen == [s]  # the setting asked once
    assert env["OLLAMA_KV_CACHE_TYPE"] == "q8_0" == ollama_start.KV_CACHE_SMALL_GPU
    assert env["LLAMA_ARG_SWA_FULL"] == "1" == ollama_start.SWA_FULL_ON
    assert env["LLAMA_ARG_CACHE_RAM"] == "256" == ollama_start.CACHE_RAM_WITH_WINDOW
    assert env["OLLAMA_NO_CLOUD"] == "1"
    assert {k: v for k, v in env.items() if k not in (*VARIABLES, "OLLAMA_NO_CLOUD")} == dict(os.environ)


def test_without_the_window_cache_the_server_gets_no_ram_cache_either(machine, tmp_path, monkeypatch):
    _unset(monkeypatch)
    machine.window = False
    env, _asked = _started_env(machine, tmp_path, monkeypatch, small=True, settings=Settings(state_dir=tmp_path))
    assert "LLAMA_ARG_SWA_FULL" not in env and env["LLAMA_ARG_CACHE_RAM"] == "0" == ollama_start.CACHE_RAM_OFF
    assert env["OLLAMA_KV_CACHE_TYPE"] == "q8_0"


def test_a_larger_gpu_or_none_gets_no_kv_cache_setting_and_the_judgement_counts_ollama_s_own_f16(
        machine, tmp_path, monkeypatch):
    _unset(monkeypatch)
    env, _asked = _started_env(machine, tmp_path, monkeypatch, small=False, settings=Settings(state_dir=tmp_path))
    assert "OLLAMA_KV_CACHE_TYPE" not in env
    assert ollama_start.setup_of(URL).kv_cache == "f16" == ollama_start.KV_CACHE_DEFAULT
    assert (env["LLAMA_ARG_SWA_FULL"], env["LLAMA_ARG_CACHE_RAM"]) == ("1", "256")


@pytest.mark.parametrize("cache, kv, window", [("0", "q8_0", "1"), ("4096", "f16", "0"), ("0", "q4_0", "true")])
def test_the_values_windows_keeps_for_the_user_are_the_ones_given(machine, tmp_path, monkeypatch, cache, kv, window):
    """TASlation started before an install set them (or the reader set them since): the Ollama it starts gets what a
    process started now would get, the reader's own as much as an older install's (its LLAMA_ARG_CACHE_RAM=0 too)."""
    _unset(monkeypatch)
    env, _asked = _started_env(machine, tmp_path, monkeypatch, {"LLAMA_ARG_CACHE_RAM": cache,
                                                                "OLLAMA_KV_CACHE_TYPE": kv,
                                                                "LLAMA_ARG_SWA_FULL": window}, small=True)
    assert (env["LLAMA_ARG_CACHE_RAM"], env["OLLAMA_KV_CACHE_TYPE"], env["LLAMA_ARG_SWA_FULL"]) == (cache, kv, window)
    assert machine.chosen == []  # a window cache set on the computer is never decided again


def test_a_value_in_taslation_s_own_environment_is_never_changed(machine, tmp_path, monkeypatch):
    monkeypatch.setenv("LLAMA_ARG_CACHE_RAM", "4096")
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "f16")
    monkeypatch.setenv("LLAMA_ARG_SWA_FULL", "0")
    env, asked = _started_env(machine, tmp_path, monkeypatch, {"LLAMA_ARG_CACHE_RAM": "1"}, small=True)
    assert asked == [] and machine.chosen == []
    assert env == {**os.environ, "OLLAMA_NO_CLOUD": "1"}  # (theirs as they are, and the cloud features off)


@pytest.mark.parametrize("window, full, cache", [("1", True, "256"), ("0", False, "0"), ("off", False, "0"),
                                                 ("on", True, "256")])
def test_the_person_s_own_window_cache_decides_the_ram_cache_beside_it(machine, tmp_path, monkeypatch, window, full,
                                                                     cache):
    _unset(monkeypatch, "LLAMA_ARG_CACHE_RAM", "LLAMA_ARG_SWA_FULL")
    monkeypatch.setenv("LLAMA_ARG_SWA_FULL", window)
    env, asked = _started_env(machine, tmp_path, monkeypatch, small=True, settings=Settings(state_dir=tmp_path))
    assert asked == ["LLAMA_ARG_CACHE_RAM"] and machine.chosen == []
    assert env["LLAMA_ARG_CACHE_RAM"] == cache and env["LLAMA_ARG_SWA_FULL"] == window  # (inherited as it is)
    setup = ollama_start.setup_of(URL)
    assert (setup.full_window, setup.why, setup.cache_ram) == (full, ollama_start.WHY_SET, cache)


def test_only_the_missing_variable_is_added(machine, tmp_path, monkeypatch):
    _unset(monkeypatch, "LLAMA_ARG_CACHE_RAM")
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "q4_0")
    env, asked = _started_env(machine, tmp_path, monkeypatch, small=True)
    assert asked == ["LLAMA_ARG_CACHE_RAM"]
    assert (env["LLAMA_ARG_CACHE_RAM"], env["OLLAMA_KV_CACHE_TYPE"], env["LLAMA_ARG_SWA_FULL"]) == ("0", "q4_0", "0")


REAL_WINDOW_CHOICE = ollama_start.window_choice


@pytest.mark.parametrize("setting, full, cache", [("off", False, "0"), ("on", True, "256"), ("auto", True, "256")])
def test_the_setting_alone_decides_the_window_cache(machine, tmp_path, monkeypatch, setting, full, cache):
    """"on" and "auto" (the default) give it, "off" not; nothing of the GPU's is asked for it (the start's judgement
    counts the model with it at its real size, `taslation.ocr.place`)."""
    from taslation.ocr import place

    _unset(monkeypatch)
    monkeypatch.setattr(ollama_start, "window_choice", REAL_WINDOW_CHOICE)
    monkeypatch.setattr(place, "card_memory", lambda: pytest.fail("the card was asked"))
    env, _asked = _started_env(machine, tmp_path, monkeypatch, small=True,
                               settings=Settings(state_dir=tmp_path, ollama_window_cache=setting))
    assert ("LLAMA_ARG_SWA_FULL" in env) is full and env["LLAMA_ARG_CACHE_RAM"] == cache
    assert ollama_start.setup_of(URL).why == ollama_start.WHY_SETTING


def test_the_ocr_s_place_and_the_card_never_change_the_window_cache(monkeypatch, tmp_path):
    from taslation.ocr import place

    monkeypatch.setattr(place, "card_memory", lambda: pytest.fail("the card was asked"))
    for runs_on in ("auto", "cpu", "gpu"):
        for setting, full in (("auto", True), ("on", True), ("off", False)):
            s = Settings(state_dir=tmp_path, ocr_runs_on=runs_on, ollama_window_cache=setting)
            assert REAL_WINDOW_CHOICE(s) is full


def test_the_setting_is_checked_and_named_in_the_example():
    assert Settings().ollama_window_cache == "auto"
    for value in ollama_start.WINDOW_CACHE_VALUES:
        Settings(ollama_window_cache=value).validate()
    with pytest.raises(Exception, match="ollama_window_cache"):
        Settings(ollama_window_cache="yes").validate()
    example = Settings.from_toml(ROOT / "taslation.toml.example")
    assert example.ollama_window_cache == "auto" and "ollama_window_cache" not in example.ignored_keys


def test_the_decision_is_made_once_per_start_kept_in_the_record_and_logged_without_text(machine, tmp_path, monkeypatch,
                                                                                       caplog):
    _unset(monkeypatch)
    monkeypatch.setattr(ollama_start, "stored_value", lambda name: None)
    monkeypatch.setattr(ollama_start, "small_gpu", lambda: True)
    s = Settings(state_dir=_state(tmp_path))
    starter = OllamaStarter(URL, state_dir=_state(tmp_path), settings=s)
    _install(tmp_path)
    machine.after_start = 0
    with caplog.at_level(logging.INFO, logger="taslation.ollama_start"):
        assert REAL_START(starter) is None
        assert REAL_START(starter) is None  # (it answers: nothing is started, nothing decided)
        assert REAL_START(OllamaStarter(URL, state_dir=_state(tmp_path), settings=s)) is None  # (another joins it)
    assert len(machine.started) == 1 and machine.chosen == [s]
    assert _record(tmp_path)["setup"] == {"kv_cache": "q8_0", "full_window": True, "cache_ram": "256",
                                          "why": ollama_start.WHY_SETTING, "no_cloud": True}
    said = [r.getMessage() for r in caplog.records if "window cache" in r.getMessage()]
    assert said == ["Ollama started by TASlation: the full-size window cache on (as ollama_window_cache says), KV "
                    "cache q8_0, prompt cache in RAM 256 MiB, Ollama's cloud features off (OLLAMA_NO_CLOUD=1)"]
    # what the server got, for the readers' rule and the System page: this process's, and another's from the record
    assert ollama_start.server_cache(URL) == ("q8_0", True)
    with ollama_start._setups_lock:
        ollama_start._setups.clear()
    assert ollama_start.setup_of(URL) is None and ollama_start.setup_of(URL, _state(tmp_path)).full_window is True
    assert ollama_start.server_cache(URL, _state(tmp_path)) == ("q8_0", True)
    # the server gone and started again: decided again, for that start
    machine.answers, machine.after_start = False, 2  # (two looks find it gone: the start's and the starter's)
    machine.window = False
    machine.procs.pop(machine.pids[0])
    monkeypatch.setattr(ollama_start, "RETRY_GAP_S", 0.0)
    assert REAL_START(starter) is None
    assert len(machine.started) == 2 and len(machine.chosen) == 2
    assert _record(tmp_path)["setup"]["full_window"] is False and ollama_start.server_cache(URL) == ("q8_0", False)
    finish_all()
    assert ollama_start.setup_of(URL) is None  # (stopped: no longer TASlation's)


def test_an_ollama_taslation_did_not_start_is_counted_as_its_variables_say(machine, tmp_path, monkeypatch):
    _unset(monkeypatch)
    stored = {"OLLAMA_KV_CACHE_TYPE": "q8_0"}
    monkeypatch.setattr(ollama_start, "stored_value", lambda name: stored.get(name))
    monkeypatch.setattr(ollama_start, "small_gpu", lambda: False)
    machine.answers = True
    assert REAL_START(OllamaStarter(URL, state_dir=_state(tmp_path))) is None
    assert ollama_start.setup_of(URL, _state(tmp_path)) is None
    assert ollama_start.server_cache(URL, _state(tmp_path)) == ("q8_0", False)
    stored["LLAMA_ARG_SWA_FULL"] = "1"
    assert ollama_start.server_cache(URL) == ("q8_0", True)
    monkeypatch.setenv("LLAMA_ARG_SWA_FULL", "0")
    monkeypatch.setenv("OLLAMA_KV_CACHE_TYPE", "q4_0")
    assert ollama_start.server_cache(URL) == ("q4_0", False)
    stored.clear()
    _unset(monkeypatch, "LLAMA_ARG_SWA_FULL", "OLLAMA_KV_CACHE_TYPE")
    monkeypatch.setattr(ollama_start, "small_gpu", lambda: True)
    assert ollama_start.server_cache(URL) == ("q8_0", False)  # (what TASlation would give one it starts)
    monkeypatch.setattr(ollama_start, "small_gpu", lambda: False)
    assert ollama_start.server_cache(URL) == ("f16", False)


def test_the_saved_settings_decide_where_the_caller_has_none(machine, tmp_path, monkeypatch):
    _unset(monkeypatch)
    saved = tmp_path / "taslation.toml"
    saved.write_text('ollama_window_cache = "off"\n', "utf-8")
    monkeypatch.setattr(Settings, "config_file", classmethod(lambda cls, path=None: saved))
    _started_env(machine, tmp_path, monkeypatch, small=True)
    assert machine.chosen and machine.chosen[0].ollama_window_cache == "off"


# ---------------------------------------------------------------------------- Ollama's cloud features off
@pytest.mark.parametrize("own", [None, "0", "false", "1", ""])
def test_the_server_taslation_starts_is_told_not_to_use_ollama_s_cloud_whatever_its_own_environment_says(
        machine, tmp_path, monkeypatch, own):
    """(Ollama 0.40.18's server asked ollama.com by itself at every start, and every 4 hours or so, unless told so)"""
    if own is not None:
        monkeypatch.setenv("OLLAMA_NO_CLOUD", own)
    env, _asked = _started_env(machine, tmp_path, monkeypatch, settings=Settings(state_dir=_state(tmp_path)),
                               state=_state(tmp_path))
    assert env["OLLAMA_NO_CLOUD"] == "1" == ollama_start.NO_CLOUD_ON
    assert ollama_start.setup_of(URL).no_cloud is True and _record(tmp_path)["setup"]["no_cloud"] is True
    for setting in ("auto", "off"):  # (never the bare inherited one)
        built = ollama_start.server_env(Settings(state_dir=tmp_path, ollama_window_cache=setting))
        assert isinstance(built, dict) and built["OLLAMA_NO_CLOUD"] == "1"
    assert ollama_start.server_setup(Settings(state_dir=tmp_path)).added["OLLAMA_NO_CLOUD"] == "1"


@pytest.mark.parametrize("own, told", [(None, False), ("1", True), ("0", False), ("yes", True)])
def test_a_server_for_a_pull_from_ollama_s_library_alone_is_left_as_taslation_s_environment_has_it(
        machine, tmp_path, monkeypatch, caplog, own, told):
    """setup_models.py's ``ollama pull`` by hand: a pull was never tried with OLLAMA_NO_CLOUD set, so its server gets
    TASlation's own environment's value (none, usually), as before; the record and the log say so."""
    if own is not None:
        monkeypatch.setenv("OLLAMA_NO_CLOUD", own)
    with caplog.at_level(logging.INFO, logger="taslation.ollama_start"):
        env, _asked = _started_env(machine, tmp_path, monkeypatch, settings=Settings(state_dir=_state(tmp_path)),
                                   state=_state(tmp_path), library_pull=True)
    assert env.get("OLLAMA_NO_CLOUD") == own and env == {**os.environ}
    assert ollama_start.setup_of(URL).no_cloud is told and _record(tmp_path)["setup"]["no_cloud"] is told
    assert ("runs without OLLAMA_NO_CLOUD" in caplog.text) is not told
    assert ollama_start.server_env(Settings(state_dir=tmp_path), library_pull=True).get("OLLAMA_NO_CLOUD") == own


def test_a_record_an_earlier_version_wrote_counts_as_a_server_without_it_and_the_log_says_so_once(
        machine, tmp_path, caplog):
    """(the starter keeps no ``no_cloud`` in records it wrote before; the server is used as ever, not started again)"""
    _install(tmp_path)
    server = machine.spawn(str(tmp_path / "Programs" / "Ollama" / "ollama.exe"))
    older = {"kv_cache": "q8_0", "full_window": True, "cache_ram": "256", "why": "setting"}
    _write_record(tmp_path, pid=server, exe=machine.procs[server].exe, started=machine.procs[server].started,
                  setup=older, users=[{"pid": 99, "started": 5}])
    assert ollama_start.ServerSetup.from_record(older).no_cloud is False
    assert ollama_start.ServerSetup.from_record({**older, "no_cloud": True}).no_cloud is True
    machine.answers = True
    with caplog.at_level(logging.INFO, logger="taslation.ollama_start"):
        assert start_ollama(URL, state=_state(tmp_path)) is None  # (adopted: the TASlation that started it is gone)
        assert OllamaStarter(URL, state_dir=_state(tmp_path)).start() is None  # (joined again)
    assert machine.started == [] and owns_server()
    assert caplog.text.count("runs without OLLAMA_NO_CLOUD") == 1
    assert ollama_start.setup_of(URL, _state(tmp_path)).no_cloud is False
    assert finish_all() == [STOPPED]
    # the next server TASlation starts gets it
    machine.answers, machine.after_start = False, 0
    assert start_ollama(URL, state=_state(tmp_path)) is None and len(machine.started) == 1
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1" and _record(tmp_path)["setup"]["no_cloud"] is True


def test_the_restart_after_no_answer_gives_the_new_server_the_variable_too(machine, tmp_path):
    """(a server an earlier version started, recorded without ``no_cloud``, comes back with it)"""
    _install(tmp_path)
    server = machine.spawn(str(tmp_path / "Programs" / "Ollama" / "ollama.exe"))
    _write_record(tmp_path, pid=server, exe=machine.procs[server].exe, started=machine.procs[server].started,
                  setup={"kv_cache": "f16", "full_window": True, "cache_ram": "256", "why": "setting"})
    machine.loaded = None  # (hung: /api/ps is silent too)
    machine.after_start = 0
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).restart() is True
    assert machine.asked == [server] and len(machine.started) == 1
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1" and _record(tmp_path)["setup"]["no_cloud"] is True
    assert finish_all() == [STOPPED]


@pytest.mark.parametrize("pull", [False, True])
def test_held_passes_on_whether_its_server_is_for_a_library_pull(machine, tmp_path, pull):
    _install(tmp_path)
    machine.after_start = 0
    with ollama_start.held(URL, _state(tmp_path), library_pull=pull) as failed:
        assert failed is None and len(machine.started) == 1
        assert ("OLLAMA_NO_CLOUD" in machine.started[0][1]["env"]) is not pull
    assert machine.asked == machine.pids and not owns_server()


def test_the_only_launch_is_the_starter_s_own_and_it_always_passes_an_environment():
    """`_launch` is the one place ``ollama serve`` is started (the start and the restart), with `server_env`'s whole
    environment: no other call of `launch` or `server_env` in the program could give a server the bare inherited one."""
    import re

    package = ROOT / "taslation"
    calls = {path.relative_to(ROOT).as_posix(): len(re.findall(r"(?<!def )\blaunch\(command", path.read_text("utf-8")))
             for path in package.rglob("*.py")}
    assert {name: n for name, n in calls.items() if n} == {"taslation/ollama_start.py": 1}
    source = (package / "ollama_start.py").read_text("utf-8")
    assert "launch(command, server_env(setup=setup))" in source
    assert source.count("_launch(") == 3  # (its definition, the start's and the restart's)


@pytest.mark.parametrize("mib, small", [(6144, True), (4096, True), (6145, False), (8192, False), (0, False)])
def test_a_small_gpu_is_6_gb_or_less_by_nvidia_s_own_number(monkeypatch, mib, small):
    """install.ps1's rule, by the number nvidia-smi gives it (memory.total, MiB)."""
    monkeypatch.setattr(devices, "nvml_memory_mib", lambda: mib)
    assert REAL["small_gpu"]() is small  # (the fixture stands in for it elsewhere)


@windows_only
def test_nvidia_s_library_is_asked_only_for_numbers():
    assert isinstance(devices.nvml_memory_mib(), int) and devices.nvml_memory_mib() >= 0  # (0 without NVIDIA's driver)


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


# ------------------------------------------------------------------------------------------ what stands in the way
def test_not_started_for_another_port(machine, tmp_path):
    _install(tmp_path)
    url = "http://127.0.0.1:11500"
    said = start_ollama(url)
    assert said == Message("health.ollama_down", url=url) and said.code not in ollama_start.POPUP_CODES
    assert machine.started == []


def test_not_installed(machine):
    said: list[str] = []
    assert start_ollama(URL, on_starting=lambda: said.append("x")).code == "health.ollama_not_installed"
    assert said == [] and machine.started == []  # nothing said to be starting


def test_no_answer_in_time(machine, tmp_path):
    _install(tmp_path)
    assert start_ollama(URL).code == "health.ollama_no_answer"
    assert len(machine.started) == 1 and machine.looks >= 2  # one process, asked again and again


def test_a_process_that_cannot_start_is_no_answer(machine, tmp_path):
    _install(tmp_path)
    machine.error = PermissionError("refused")
    assert start_ollama(URL, state=_state(tmp_path)).code == "health.ollama_no_answer"
    assert not _record_file(tmp_path).exists() and not owns_server()


def test_the_wait_is_cancelled_by_the_caller_s_event(machine, tmp_path, monkeypatch):
    _install(tmp_path)
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
    _install(tmp_path)
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


# --------------------------------------------------------------------------------- owned, and stopped at the end
def test_the_server_taslation_starts_is_written_down_with_who_uses_it(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    record = _record(tmp_path)
    assert set(record) == {"what", "pid", "exe", "started", "url", "setup", "users"}  # no text of a book
    assert record["setup"] == {"kv_cache": "q8_0", "full_window": False, "cache_ram": "0", "why": "set",
                               "no_cloud": True}
    assert (record["pid"], record["started"], record["url"]) == (pid, machine.procs[pid].started, URL)
    assert record["exe"] == str(tmp_path / "Programs" / "Ollama" / "ollama.exe")
    assert record["users"] == [{"pid": ME, "started": 1}] and owns_server()


def test_it_is_stopped_at_the_end_once(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    machine.loaded = ["taslation-plamo3-translate-2b:latest", "qwen3.5:4b"]  # TASlation's own models
    assert finish_all() == [STOPPED]
    assert machine.asked == [pid] and pid not in machine.procs and machine.waits == [STOP_WAIT_S]
    assert machine.ps_timeouts == [ollama_start.PS_TIMEOUT_S] and machine.terminated == []
    assert not _record_file(tmp_path).exists() and not owns_server()
    assert finish_all() == [] and machine.asked == [pid]  # nothing more to give up


def test_the_end_while_the_server_is_being_launched_gives_up_what_was_launched_at_once(machine, tmp_path):
    """(the window closed while its start, on a worker thread, was launching Ollama: seen on the stand-in, a run
    stopped 1.5 s into its window left the server it had started running)"""
    _install(tmp_path)
    machine.after_start = 0
    ended: list[list[str]] = []
    starter = OllamaStarter(URL, on_starting=lambda: ended.append(finish_all()), state_dir=_state(tmp_path))
    assert starter.start() is not None  # (no answer to wait for: it is gone again)
    assert ended == [[]]  # (the end found nothing to give up yet: the launch came after it)
    pid = machine.pids[0]
    assert machine.asked == [pid] and pid not in machine.procs  # (stopped by the start itself, at once)
    assert not _record_file(tmp_path).exists() and not owns_server()


def test_the_end_before_the_launch_launches_nothing(machine, tmp_path, monkeypatch):
    _install(tmp_path)
    looks = {"n": 0}

    def running(url, timeout=1.0):  # (the end comes between the start's first look and its launch)
        looks["n"] += 1
        if looks["n"] == 2:
            finish_all()
        return False

    monkeypatch.setattr(health, "ollama_running", running)
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).start() is not None
    assert machine.started == [] and not owns_server()
    machine.after_start = 0  # (a start after the end is a start as ever: a command run later in the same process)
    monkeypatch.setattr(health, "ollama_running", machine.running)
    assert start_ollama(URL, state=_state(tmp_path)) is None and len(machine.started) == 1 and owns_server()
    assert finish_all() == [STOPPED]


def test_an_ollama_that_ran_before_is_never_owned_nor_stopped(machine, tmp_path):
    _install(tmp_path)
    machine.answers = True  # the person's own, or an Ollama that starts with Windows
    assert start_ollama(URL, state=_state(tmp_path)) is None
    assert machine.started == [] and not _record_file(tmp_path).exists() and not owns_server()
    assert finish_all() == [] and machine.asked == machine.terminated == []


def test_without_a_state_folder_nothing_is_owned(machine, tmp_path):
    _install(tmp_path)
    machine.after_start = 0
    assert start_ollama(URL) is None and len(machine.started) == 1
    assert not owns_server() and finish_all() == [] and machine.asked == []


def test_another_taslation_that_uses_it_keeps_it_running_until_the_last_one_ends(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    other = machine.spawn(sys.executable)  # the window, while a command ran too
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).start() is None  # (this process joins once only)
    record = _record(tmp_path)
    record["users"].append({"pid": other, "started": machine.procs[other].started})
    _record_file(tmp_path).write_text(json.dumps(record), "utf-8")
    assert finish_all() == [IN_USE] and machine.asked == [] and pid in machine.procs
    assert _record(tmp_path)["users"] == [{"pid": other, "started": machine.procs[other].started}]
    # the other one ends without stopping it (it crashed): the next TASlation that finds it adopts it, and stops it
    del machine.procs[other]
    assert start_ollama(URL, state=_state(tmp_path)) is None and len(machine.started) == 1
    assert _record(tmp_path)["users"] == [{"pid": ME, "started": 1}]
    assert finish_all() == [STOPPED] and machine.asked == [pid]


def test_another_program_s_model_keeps_it_running_and_it_is_no_longer_taslation_s(machine, tmp_path, caplog):
    pid = _started_one(machine, tmp_path)
    machine.loaded = ["taslation-plamo3-translate-2b:latest", "llama3.2:3b"]
    with caplog.at_level(logging.INFO, logger="taslation"):
        assert finish_all() == [FOREIGN.format(count=1, names="llama3.2:3b")]
    assert machine.asked == [] and pid in machine.procs and not _record_file(tmp_path).exists()
    assert "1 model(s) of another program loaded (llama3.2:3b)" in caplog.text
    machine.loaded = []
    assert start_ollama(URL, state=_state(tmp_path)) is None and not owns_server()  # it is theirs now
    assert finish_all() == [] and machine.asked == []


def test_the_model_the_settings_name_and_the_window_s_own_count_as_taslation_s(machine, tmp_path):
    pid = _started_one(machine, tmp_path, own=ollama_start.own_models(SimpleNamespace(ollama_model="my-translator")))
    ollama_start.count_as_own("chosen-in-the-window:7b")
    machine.loaded = ["my-translator:latest", "chosen-in-the-window:7b", "qwen3.5:4b"]
    assert finish_all() == [STOPPED] and machine.asked == [pid]
    assert ollama_start.own_models(SimpleNamespace(ollama_model="auto")) == ()


def test_a_server_that_does_not_answer_ps_is_stopped(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    machine.loaded = None  # (hung, or still starting: nobody else can be using it)
    assert finish_all() == [STOPPED] and machine.asked == [pid]


def test_a_live_server_recorded_before_a_crash_is_adopted(machine, tmp_path):
    _install(tmp_path)
    server = machine.spawn(str(tmp_path / "Programs" / "Ollama" / "ollama.exe"))
    crashed = 99  # the TASlation that started it, gone
    _write_record(tmp_path, pid=server, exe=machine.procs[server].exe, started=machine.procs[server].started,
                  users=[{"pid": crashed, "started": 5}])
    machine.answers = True
    assert start_ollama(URL, state=_state(tmp_path)) is None and machine.started == []
    assert _record(tmp_path)["users"] == [{"pid": ME, "started": 1}] and owns_server()
    assert finish_all() == [STOPPED] and machine.asked == [server] and server not in machine.procs


def test_a_recorded_server_that_runs_but_does_not_answer_is_not_started_twice(machine, tmp_path):
    _install(tmp_path)
    server = machine.spawn(str(tmp_path / "Programs" / "Ollama" / "ollama.exe"))
    _write_record(tmp_path, pid=server, exe=machine.procs[server].exe, started=machine.procs[server].started)
    assert start_ollama(URL, state=_state(tmp_path)).code == "health.ollama_no_answer"
    assert machine.started == [] and owns_server()  # waited for, as one just started
    assert finish_all() == [STOPPED] and machine.asked == [server]


@pytest.mark.parametrize("change", ["started", "exe", "url", "gone"])
def test_a_record_of_a_reused_number_another_program_or_an_ended_server_is_dropped(machine, tmp_path, change):
    _install(tmp_path)
    exe = str(tmp_path / "Programs" / "Ollama" / "ollama.exe")
    pid = machine.spawn(exe)  # whatever runs under the recorded number now: never touched
    record = {"pid": pid, "exe": exe, "started": machine.procs[pid].started, "url": URL}
    if change == "started":
        record["started"] -= 7  # the number was reused by a process that started later
    elif change == "exe":
        record["exe"] = r"C:\Other\ollama.exe"
    elif change == "url":
        record["url"] = "http://127.0.0.1:11500"
    else:
        del machine.procs[pid]
    _write_record(tmp_path, **record)
    machine.answers = True  # an Ollama answers: not the recorded one
    assert start_ollama(URL, state=_state(tmp_path)) is None
    assert not _record_file(tmp_path).exists() and not owns_server()
    assert finish_all() == [] and machine.asked == machine.terminated == []


def test_a_damaged_record_is_no_record(machine, tmp_path):
    _state(tmp_path).mkdir()
    _record_file(tmp_path).write_text("{not json", "utf-8")
    pid = _started_one(machine, tmp_path)
    assert _record(tmp_path)["pid"] == pid


def test_a_server_that_ignores_the_request_is_ended_with_its_model_s_process(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    runner = machine.spawn("llama-server.exe")
    machine.children[pid] = [(runner, machine.procs[runner].started)]
    machine.obeys = False
    assert finish_all() == [STOPPED]
    assert machine.waits == [STOP_WAIT_S, KILL_WAIT_S] and machine.terminated == [runner, pid]
    assert not machine.procs.keys() - {ME} and not _record_file(tmp_path).exists()


def test_a_server_that_will_not_end_is_left_within_a_bound_and_the_next_end_tries_again(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    machine.obeys = machine.killable = False
    assert finish_all() == [KEPT.format(seconds=STOP_WAIT_S + KILL_WAIT_S)]
    assert machine.waits == [STOP_WAIT_S, KILL_WAIT_S]  # every wait has its bound, and there are two
    assert STOP_WAIT_S + KILL_WAIT_S + ollama_start.HELPER_TIMEOUT_S <= 10
    assert _record(tmp_path)["users"] == [] and pid in machine.procs  # kept for the next end
    machine.obeys = True
    assert start_ollama(URL, state=_state(tmp_path)) is None and finish_all() == [STOPPED]


def test_the_end_never_raises(machine, tmp_path, caplog, monkeypatch):
    _started_one(machine, tmp_path)

    def broken(url, timeout=1.0):
        raise RuntimeError("broken")

    monkeypatch.setattr(health, "loaded_models", broken)
    with caplog.at_level(logging.ERROR, logger="taslation"):
        assert finish_all() == []
    assert "stopping the Ollama TASlation started failed" in caplog.text


# ------------------------------------------------------------- started again when a request gets no answer
def test_the_server_taslation_started_is_started_again_at_most_once_in_ten_minutes(machine, tmp_path, monkeypatch,
                                                                                   caplog):
    first = _started_one(machine, tmp_path)
    other = machine.spawn(sys.executable)  # another TASlation that uses it (a command beside the window)
    record = _record(tmp_path)
    record["users"].append({"pid": other, "started": machine.procs[other].started})
    _record_file(tmp_path).write_text(json.dumps(record), "utf-8")
    machine.loaded = None  # (hung: /api/ps is silent too)
    starter = OllamaStarter(URL, state_dir=_state(tmp_path))
    told: list[int] = []  # (told once the restart is under way: before the stop, with the old server still there)
    with caplog.at_level(logging.WARNING, logger="taslation"):
        assert starter.restart(on_restarting=lambda: told.append(len(machine.asked))) is True
    assert told == [0]
    assert machine.asked == [first] and first not in machine.procs and len(machine.pids) == 2
    record = _record(tmp_path)
    assert record["pid"] == machine.pids[1] and owns_server()
    assert {(u["pid"], u["started"]) for u in record["users"]} == {(ME, 1), (other, machine.procs[other].started)}
    assert "was stopped" in caplog.text and "started again; it answers" in caplog.text
    # within ten minutes: not again, nothing stopped or started, nothing told
    assert starter.restart(on_restarting=lambda: told.append(-1)) is False and told == [0]
    assert machine.asked == [first] and len(machine.pids) == 2
    assert "not again within 600 s" in caplog.text
    monkeypatch.setattr(ollama_start, "RESTART_GAP_S", 0.0)  # (ten minutes later)
    assert starter.restart() is True and machine.asked == [first, machine.pids[1]] and len(machine.pids) == 3
    del machine.procs[other]
    assert finish_all() == [STOPPED] and machine.asked[-1] == machine.pids[2]


def test_a_server_taslation_did_not_start_is_never_stopped_nor_started_again(machine, tmp_path):
    _install(tmp_path)
    machine.answers = True  # the person's own Ollama
    assert start_ollama(URL, state=_state(tmp_path)) is None and not _record_file(tmp_path).exists()
    told: list[str] = []
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).restart(on_restarting=lambda: told.append("x")) is None
    assert OllamaStarter(URL).restart(on_restarting=lambda: told.append("x")) is None  # (no state folder)
    assert OllamaStarter("http://127.0.0.1:11500", state_dir=_state(tmp_path)).restart(
        on_restarting=lambda: told.append("x")) is None
    assert machine.asked == machine.terminated == [] and machine.started == [] and told == []


def test_another_program_s_model_keeps_the_server_from_being_started_again(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    machine.loaded = ["taslation-plamo3-translate-2b:latest", "llama3.2:3b"]
    told: list[str] = []
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).restart(on_restarting=lambda: told.append("x")) is None
    assert machine.asked == machine.terminated == [] and pid in machine.procs and len(machine.started) == 1
    assert told == []


def test_a_server_that_will_not_stop_or_does_not_come_back_is_no_restart(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    machine.obeys = machine.killable = False
    told: list[str] = []  # (a restart under way that fails was told: the sentence that it does not answer follows)
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).restart(on_restarting=lambda: told.append("x")) is False
    assert pid in machine.procs and len(machine.started) == 1 and _record(tmp_path)["pid"] == pid and told == ["x"]
    machine.obeys = machine.killable = True
    machine.after_start = None  # (the one started again never answers)
    assert OllamaStarter(URL, state_dir=_state(tmp_path)).restart() is False
    assert len(machine.started) == 2 and _record(tmp_path)["pid"] == machine.pids[1]  # (stopped at the end as ever)


# ------------------------------------------------------------------------------------------ the window
def _popups(events):
    return [data["message"].code for kind, data in events if kind == "ollama_failed"]


def test_the_window_starts_ollama_before_the_setup_check_and_owns_it(machine, start, tmp_path):  # noqa: F811
    _install(tmp_path)
    machine.after_start = 1
    w = start(([], ["qwen3.5:4b"]))
    w._job_init()
    events = w.events()
    assert events[0] == ("status", {"key": "Starting the translation program..."}) and events[1][0] == "health"
    assert _popups(events) == [] and len(machine.started) == 1
    assert worker(start.order)[0] == "health"  # and from here on as if it had been running
    assert ("warm-up", "qwen3.5:4b") in start.order
    assert owns_server() and _record(tmp_path)["users"] == [{"pid": ME, "started": 1}]
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1"  # (the session's server: Ollama's cloud off)


def test_the_window_s_close_counts_its_model_as_taslation_s(machine, tmp_path):
    pid = _started_one(machine, tmp_path)
    released: list[str] = []
    w = SimpleNamespace(_page_cancel=threading.Event(), translator=SimpleNamespace(model="picked-by-hand:4b"),
                        settings=Settings(state_dir=_state(tmp_path), ollama_model="named-in-settings"),
                        pipeline=SimpleNamespace(release_translator=lambda: released.append("released")))
    jobs.JobsMixin._release_model(w)
    assert w._page_cancel.is_set() and released == ["released"]
    machine.loaded = ["picked-by-hand:4b", "named-in-settings:latest"]
    assert finish_all() == [STOPPED] and machine.asked == [pid]


def test_the_window_stops_it_once_it_has_gone(monkeypatch, tmp_path):
    from taslation.ui import app as app_module

    order: list[str] = []

    class Window:
        quit_before_start = False

        def __init__(self, settings, **_kwargs):
            pass

        def mainloop(self):
            order.append("window")
            if order.count("window") == 2:
                raise RuntimeError("Tk failed")

    monkeypatch.setattr(app_module, "App", Window)
    monkeypatch.setattr(app_module, "keep_awake", lambda **_k: None)
    monkeypatch.setattr(app_module, "release_awake", lambda: order.append("awake"))
    monkeypatch.setattr(app_module, "finish_all", lambda: order.append("finish") or [])
    assert app_module.run_app(Settings(state_dir=_state(tmp_path))) == 0
    assert order == ["window", "awake", "finish"]
    with pytest.raises(RuntimeError):
        app_module.run_app(Settings(state_dir=_state(tmp_path)))
    assert order[3:] == ["window", "awake", "finish"]  # a window that fails stops it too


@pytest.mark.parametrize("installed, code", [(True, "health.ollama_no_answer"), (False, "health.ollama_not_installed")])
def test_a_failed_start_is_a_popup_once_and_the_window_goes_on(machine, start, tmp_path, installed, code):  # noqa: F811
    if installed:
        _install(tmp_path)
    w = start(([Message("health.ollama_down", url=URL)], None))
    w._job_init()
    events = w.events()
    assert _popups(events) == [code]
    assert [k for k, _d in events if k in ("health", "ready")] == ["health", "ready"]
    assert "ocr" in start.order  # pages already translated still work


def test_another_port_gets_no_popup(machine, start, tmp_path):  # noqa: F811
    _install(tmp_path)
    w = start(([Message("health.ollama_down", url="http://127.0.0.1:11500")], None), ollama_url="http://127.0.0.1:11500")
    w._job_init()
    assert _popups(w.events()) == [] and machine.started == []


def test_the_banner_s_start_again_owns_what_it_starts(machine, tmp_path):
    _install(tmp_path)
    machine.after_start = 0
    posted: list[tuple[str, dict]] = []
    w = SimpleNamespace(settings=Settings(state_dir=_state(tmp_path)), say=lambda key: None,
                        _post=lambda kind, **data: posted.append((kind, data)), _check_in_background=lambda: None)
    jobs.JobsMixin.restart_translator(w)
    for thread in threading.enumerate():
        if thread.name == "taslation-start-ollama":
            thread.join(5)
    assert posted == [("translator_restarted", {"message": None})] and owns_server()
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1"


def test_a_failed_start_is_said_in_the_status_line_and_no_box_comes_up(monkeypatch):
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, title="TASlation", **_k: shown.append((title, text)))
    said: list[str] = []
    w = SimpleNamespace(status=said.append)
    w._warn_unasked = jobs.JobsMixin._warn_unasked.__get__(w)
    jobs.JobsMixin._handle_event(w, "ollama_failed", {"message": Message("health.ollama_not_installed")})
    assert said == ["The translation program is not installed. Double-click install.cmd in the TASlation folder."]
    said.clear()
    jobs.JobsMixin._handle_event(w, "ollama_failed", {"message": Message("health.ollama_no_answer")})
    assert said == ["The translation program did not start. Restart your PC, then open TASlation again. Pages already "
                    "translated can still be read."]
    assert shown == []  # (the reader reads in the viewer: nothing comes up over the book)


def test_a_request_that_fails_for_good_tells_the_banner(machine):
    checked: list[str] = []
    w = SimpleNamespace(_ollama=OllamaStarter(URL), _check_in_background=lambda: checked.append("checked"))
    assert not jobs.JobsMixin._revive_ollama(w)
    assert checked == ["checked"]
    machine.answers = True
    assert jobs.JobsMixin._revive_ollama(w) and checked == ["checked"]


def test_the_window_starts_its_server_again_for_a_request_without_an_answer(machine, tmp_path):
    checked: list[str] = []
    _started_one(machine, tmp_path)
    w = SimpleNamespace(_ollama=OllamaStarter(URL, state_dir=_state(tmp_path)),
                        _check_in_background=lambda: checked.append("checked"))
    told: list[str] = []
    assert jobs.JobsMixin._restart_ollama(w, None, lambda: told.append("x")) is True and len(machine.started) == 2
    assert checked == [] and told == ["x"]
    assert [options["env"]["OLLAMA_NO_CLOUD"] for _command, options in machine.started] == ["1", "1"]
    assert jobs.JobsMixin._restart_ollama(w) is False and checked == ["checked"]  # (within ten minutes)
    assert jobs.JobsMixin._restart_ollama(SimpleNamespace(_ollama=None)) is None


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
    _install(tmp_path)
    tr = _translator(OllamaStarter(URL).revive)
    gone = Gone(refusals=99)
    monkeypatch.setattr(tr, "_request_once", gone)
    for _ in range(5):
        with pytest.raises(TranslationError):
            tr._request("/x")
    assert len(machine.started) == 1 and gone.calls == 5


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
    _install(tmp_path)
    machine.after_start = 0
    pipeline = cli.build_pipeline(Settings(state_dir=_state(tmp_path)), "ollama", None, warm_first=warm_first)
    assert len(machine.started) == 1 and pipeline.translator.revive is not None
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1"
    assert pipeline.translator.restart is not None  # (a request without an answer: the server started again)
    assert "note: Starting the translation program..." in capsys.readouterr().err


def test_a_command_s_end_stops_what_it_started_and_says_so(machine, engine, tmp_path, capsys):
    pid = _started_one(machine, tmp_path)
    capsys.readouterr()
    cli.build_pipeline(Settings(state_dir=_state(tmp_path)), "ollama", None)  # (it answers: the same server)
    cli._finish_ollama("translate")
    assert f"note: {STOPPED}" in capsys.readouterr().err and machine.asked == [pid]


def test_the_window_s_end_is_in_its_log_not_on_a_console(machine, tmp_path, capsys):
    _started_one(machine, tmp_path)
    cli._finish_ollama("gui")
    assert capsys.readouterr().err == "" and not owns_server()


def test_every_command_gives_it_up_at_its_end_ctrl_c_included(monkeypatch, tmp_path):
    ended: list[str] = []
    monkeypatch.setattr(cli, "_finish_ollama", lambda command: ended.append(command))
    monkeypatch.setattr(cli.netguard, "install", lambda port: None)
    monkeypatch.setenv("TASLATION_STATE_DIR", str(_state(tmp_path)))

    def interrupted(args, settings):
        raise KeyboardInterrupt

    monkeypatch.setitem(cli.COMMANDS, "doctor", interrupted)
    assert cli.main(["doctor"]) == 130 and ended == ["doctor"]
    monkeypatch.setitem(cli.COMMANDS, "doctor", lambda args, settings: 0)
    assert cli.main(["doctor"]) == 0 and ended == ["doctor", "doctor"]


def test_a_command_says_what_stands_in_the_way(machine, engine, tmp_path, capsys):
    cli.build_pipeline(Settings(state_dir=_state(tmp_path)), "ollama", None, warm_first=True)
    assert "note: The translation program is not installed. Double-click install.cmd in the TASlation folder." in capsys.readouterr().err


def test_a_command_with_no_use_for_ollama_leaves_it_alone(machine, engine, tmp_path):
    _install(tmp_path)
    cli.build_pipeline(Settings(state_dir=_state(tmp_path)), "echo", None, warm_first=True)
    assert machine.started == [] and machine.looks == 0


@pytest.mark.parametrize("language", ["French", "Turkish"])  # (PLaMo's import, Qwen's pull)
def test_a_language_s_model_install_starts_the_server_first(machine, tmp_path, monkeypatch, language):
    """An ``ollama`` command that finds no server starts Ollama's tray app (and with it Ollama's start with Windows):
    the install of a translator model starts the server first, as TASlation starts it. That server is the window's
    (or the command's) for the rest of its session, Ollama's cloud features off for Qwen's pull too."""
    _install(tmp_path)
    machine.after_start = 0
    script = tmp_path / "setup_models.py"
    script.write_text("", "utf-8")

    class Next(Exception):
        """What the install does next: not in this test."""

    def next_step():
        raise Next

    monkeypatch.setattr(ti, "find_ollama", next_step)
    with pytest.raises(Next):
        ti.Installer(language, tmp_path / "models", _state(tmp_path), URL, script=script).run()
    assert len(machine.started) == 1 and owns_server()
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1"


def _setup_models():
    spec = importlib.util.spec_from_file_location("setup_models_ollama_start", ROOT / "setup_models.py")
    setup_models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup_models)
    return setup_models


@pytest.mark.parametrize("language, told", [("French", True), ("Turkish", False)])  # (PLaMo's import, Qwen's pull)
def test_setup_models_starts_the_server_first_and_stops_it_at_its_end(machine, tmp_path, monkeypatch, language, told):
    """Run by hand with no server running: its own, told not to use Ollama's cloud features for PLaMo's import, and
    left without the variable for a pull from Ollama's library (a pull was never tried with it set)."""
    setup_models = _setup_models()
    _install(tmp_path)
    machine.after_start = 0
    monkeypatch.setattr(setup_models.tinstall, "find_ollama", lambda: None)  # (then it says so and ends)
    assert setup_models.install_translator(language, tmp_path / "models", _state(tmp_path), URL) == 1
    assert len(machine.started) == 1 and machine.asked == machine.pids and not owns_server()
    assert (machine.started[0][1]["env"].get("OLLAMA_NO_CLOUD") == "1") is told


def test_setup_models_pull_by_name_starts_a_server_for_the_pull_alone(machine, tmp_path, monkeypatch):
    setup_models = _setup_models()
    _install(tmp_path)
    machine.after_start = 0
    pulled: list[list[str]] = []
    monkeypatch.setattr(setup_models, "_settings_for_translator", lambda: (_state(tmp_path), URL, "English"))
    monkeypatch.setattr(setup_models.shutil, "which", lambda name: "C:/fake/ollama.exe" if name == "ollama" else None)
    monkeypatch.setattr(setup_models.subprocess, "run", lambda command, **_k: pulled.append(command))
    setup_models.pull_ollama("someone/theirs:4b")
    assert pulled == [["C:/fake/ollama.exe", "pull", "someone/theirs:4b"]]
    assert len(machine.started) == 1 and "OLLAMA_NO_CLOUD" not in machine.started[0][1]["env"]
    assert machine.asked == machine.pids and not owns_server()


@pytest.fixture
def doctor(machine, monkeypatch):
    """doctor with Ollama's answers standing in (`machine`), and no look at where the stages run."""
    monkeypatch.setattr(devices, "lines", lambda settings, *a, **k: [])
    monkeypatch.setattr(OllamaTranslator, "ping", lambda self: machine.answers)
    monkeypatch.setattr(OllamaTranslator, "list_models", lambda self: ["taslation-plamo3-translate-2b:latest"])
    monkeypatch.setattr(OllamaTranslator, "has_model", lambda self, name: True)
    monkeypatch.setattr(OllamaTranslator, "version", lambda self: "0.0.0")

    def run(settings) -> str:
        cli.cmd_doctor(SimpleNamespace(config=None), settings)
        return run.capsys.readouterr().out

    return run


def test_doctor_starts_ollama_for_its_check_and_stops_it_again(machine, doctor, tmp_path, capsys):
    doctor.capsys = capsys
    _install(tmp_path)
    machine.after_start = 0
    out = doctor(Settings(state_dir=_state(tmp_path)))
    assert f"Ollama: reachable at {URL}" in out and cli.DOCTOR_STARTED in out
    assert out.index(STOPPED) < out.index("Result:") and out.rstrip().splitlines()[-1].startswith("Result:")
    assert len(machine.started) == 1 and machine.asked == machine.pids and not owns_server()
    assert machine.started[0][1]["env"]["OLLAMA_NO_CLOUD"] == "1"
    assert cli.SERVER_NO_CLOUD in out.splitlines() and cli.SERVER_THEIRS not in out


def test_doctor_leaves_a_running_ollama_alone(machine, doctor, tmp_path, capsys):
    doctor.capsys = capsys
    _install(tmp_path)
    machine.answers = True
    out = doctor(Settings(state_dir=_state(tmp_path)))
    assert f"Ollama: reachable at {URL}" in out and cli.DOCTOR_STARTED not in out and STOPPED not in out
    assert machine.started == [] and machine.asked == []
    # the person's own: theirs, with its own settings
    assert cli.SERVER_THEIRS in out.splitlines() and cli.SERVER_NO_CLOUD not in out


def test_doctor_says_which_server_has_ollama_s_cloud_off(machine, doctor, tmp_path, capsys):
    """The window's server (the record names it), and one an earlier version started (its record has no ``no_cloud``)."""
    doctor.capsys = capsys
    _install(tmp_path)
    server = machine.spawn(str(tmp_path / "Programs" / "Ollama" / "ollama.exe"))
    window = machine.spawn(sys.executable)  # (the window that uses it, still running)
    setup = {"kv_cache": "f16", "full_window": True, "cache_ram": "256", "why": "setting"}
    machine.answers = True
    for recorded, line in (({**setup, "no_cloud": True}, cli.SERVER_NO_CLOUD), (setup, cli.SERVER_WITH_CLOUD)):
        _write_record(tmp_path, pid=server, exe=machine.procs[server].exe, started=machine.procs[server].started,
                      setup=recorded, users=[{"pid": window, "started": machine.procs[window].started}])
        out = doctor(Settings(state_dir=_state(tmp_path)))
        assert line in out.splitlines() and machine.started == [] and server in machine.procs
    # (install.ps1's final check shows a failed doctor's lines that name Ollama: these never do)
    for line in (cli.SERVER_NO_CLOUD, cli.SERVER_WITH_CLOUD, cli.SERVER_THEIRS):
        assert "Ollama" not in line and line.startswith("  ")


def test_doctor_says_what_to_do_when_ollama_is_not_there_or_does_not_start(machine, doctor, tmp_path, capsys):
    doctor.capsys = capsys
    settings = Settings(state_dir=_state(tmp_path))
    assert "Ollama: not installed. Run install.cmd again to install it." in doctor(settings)
    assert machine.started == []
    _install(tmp_path)  # installed, and it does not answer when started
    out = doctor(settings)
    assert (f"Ollama: not running at {URL}, and it did not answer when it was started for this check. Restart your PC, "
            "then run this check again; if it still does not answer, run install.cmd again.") in out
    assert len(machine.started) == 1 and machine.asked == machine.pids  # and stopped again: left as it was
    assert "not running at http://127.0.0.1:11500" in doctor(Settings(state_dir=_state(tmp_path),
                                                                       ollama_url="http://127.0.0.1:11500"))
    assert len(machine.started) == 1


def test_translator_built_for_doctor_has_no_reviver():
    assert cli.build_translator(Settings(), "ollama").revive is None


# ------------------------------------------------------------------------------------------ the process functions
@pytest.fixture
def real_processes(monkeypatch):
    """The process functions themselves (the fixture above stands in for them), for stand-ins of this test's own."""
    for name, function in REAL.items():
        monkeypatch.setattr(ollama_start, name, function)
    monkeypatch.setattr(subprocess, "Popen", REAL_POPEN)
    started: list[tuple[subprocess.Popen, int]] = []

    def stand_in(code: str) -> tuple[int, int]:
        proc = REAL_POPEN([BASE_PYTHON, "-I", "-S", "-c", code], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        deadline = time.monotonic() + 10
        info = ollama_start.process_info(proc.pid)
        while info is None and time.monotonic() < deadline:
            time.sleep(0.05)
            info = ollama_start.process_info(proc.pid)
        started.append((proc, info.started))
        return proc.pid, info.started

    yield stand_in
    for proc, began in started:  # (what a failed test left; *proc* holds the stand-in's number: none is another's)
        with contextlib.suppress(OSError):
            proc.kill()
        for child, child_started in REAL["descendants"](proc.pid, began):
            REAL["terminate"](child, child_started)


BASE_PYTHON = getattr(sys, "_base_executable", "") or sys.executable  # (no virtual environment's process between)
# Ollama's server as a stand-in: *handler* set first, then one child started (its model's process), then a wait in short
# sleeps (a handler runs within one). Windows gives the stand-in's hidden console a host of its own (conhost.exe), a
# child of the stand-in too, which shows first.
PARENT = ("import signal, subprocess, sys, time\n"
          "{handler}"
          "child = subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(60)'])\n"
          "while True:\n"
          "    time.sleep(0.05)\n")
IGNORE = "signal.signal(signal.SIGBREAK, signal.SIG_IGN)\n"  # a server that ignores the request to stop
# a server that starts one more process when it is asked to stop (one that no earlier look lists and that the request
# never reaches), then ends
LAST_ONE = ("def leave(*_):\n"
            "    subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(60)'])\n"
            "    sys.exit(0)\n"
            "signal.signal(signal.SIGBREAK, leave)\n")


def _pythons(tree: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The stand-in's own children in *tree* (Pythons, as it is), not its console's host."""
    python = os.path.normcase(os.path.abspath(BASE_PYTHON))
    return [(pid, started) for pid, started in tree if (info := ollama_start.process_info(pid)) is not None
            and os.path.normcase(os.path.abspath(info.exe)) == python]


def _wait_for_child(pid: int, started: int) -> list[tuple[int, int]]:
    """What stand-in *pid* started, once its child is among it: the host of its console shows first, and a stand-in
    asked to stop before its child has started would end with none (its handler is set by then)."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        found = ollama_start.descendants(pid, started)
        if _pythons(found):
            return found
        time.sleep(0.05)
    return []


def _left(pid: int, started: int, tree: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """What of stand-in *pid* still runs: itself, what *tree* listed, and what a look finds now (its number is held by
    the fixture's Popen: what has it as its parent's is the stand-in's)."""
    found = dict.fromkeys(tree + ollama_start.descendants(pid, started))
    return [(p, s) for p, s in [(pid, started), *found] if ollama_start.same_process(p, s)]


@windows_only
def test_this_process_is_known_by_its_program_and_start_time(real_processes):
    info = ollama_start.process_info(ME)
    # (a virtual environment's python.exe runs the interpreter it was made from as a process of its own)
    programs = {os.path.normcase(os.path.abspath(p)) for p in (sys.executable, getattr(sys, "_base_executable", ""))}
    assert os.path.normcase(info.exe) in programs and info.started > 0
    assert ollama_start.same_process(ME, info.started, info.exe)
    assert not ollama_start.same_process(ME, info.started + 1) and not ollama_start.same_process(ME, info.started,
                                                                                                r"C:\x\ollama.exe")
    assert ollama_start.this_process() == {"pid": ME, "started": info.started}


@windows_only
def test_a_server_asked_to_stop_ends_with_its_children(real_processes):
    pid, started = real_processes(PARENT.format(handler=""))
    tree = _wait_for_child(pid, started)
    assert len(_pythons(tree)) == 1  # its child (beside its console's host)
    began = time.monotonic()
    assert ollama_start.stop_server(pid, started)
    took = time.monotonic() - began
    assert _left(pid, started, tree) == []  # the moment it returns
    assert took < 3.0, took


@windows_only
def test_a_server_that_ignores_the_request_is_ended_within_the_bound(real_processes, monkeypatch):
    monkeypatch.setattr(ollama_start, "STOP_WAIT_S", 0.5)
    pid, started = real_processes(PARENT.format(handler=IGNORE))
    tree = _wait_for_child(pid, started)
    assert len(_pythons(tree)) == 1
    began = time.monotonic()
    assert ollama_start.stop_server(pid, started)
    took = time.monotonic() - began
    assert _left(pid, started, tree) == []
    assert 0.4 < took < 0.5 + ollama_start.HELPER_TIMEOUT_S + ollama_start.KILL_WAIT_S, took


@windows_only
def test_a_process_the_server_starts_as_it_is_asked_to_stop_is_ended_too(real_processes, monkeypatch):
    ended: list[int] = []

    def terminate(pid, started):
        ended.append(pid)
        return REAL["terminate"](pid, started)

    monkeypatch.setattr(ollama_start, "terminate", terminate)
    pid, started = real_processes(PARENT.format(handler=LAST_ONE))
    tree = _wait_for_child(pid, started)
    assert len(_pythons(tree)) == 1
    began = time.monotonic()
    assert ollama_start.stop_server(pid, started)
    took = time.monotonic() - began
    assert _left(pid, started, tree) == []
    assert set(ended) - {p for p, _s in tree}  # the last one: found after the server had ended, and ended
    assert took < 3.0, took


@windows_only
def test_a_process_that_is_not_the_recorded_one_is_never_touched(real_processes):
    pid, started = real_processes("import time; time.sleep(60)")
    assert not ollama_start.terminate(pid, started + 1) and ollama_start.wait_exit(pid, started + 1, 5.0)
    with ollama_start.pinned(pid, started + 1) as the_server:
        assert not the_server
    assert ollama_start.stop_server(pid, started + 1)  # (ended, as far as the stop knows: nothing asked or ended)
    assert ollama_start.same_process(pid, started)
    assert ollama_start.terminate(pid, started) and ollama_start.wait_exit(pid, started, 5.0)


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
