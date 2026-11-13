"""Ollama started when it is not running, so that a reader never has to.

`OllamaStarter.start` looks at the Ollama the settings name and, when it does not answer, starts it: the tray app the
Ollama installer starts (`%LOCALAPPDATA%\\Programs\\Ollama\\ollama app.exe`, which then runs the server), else
``ollama.exe`` beside it, else ``ollama`` from the PATH, these two as ``ollama serve`` (`find_ollama`). The process is
detached, has no console and no shell, and outlives TASlation: it is an Ollama like one the reader started, and
TASlation never stops it. Its environment is TASlation's (what the reader set for Ollama comes with it), with one
variable added when TASlation's lacks it (`server_env`): ``LLAMA_ARG_CACHE_RAM``, how many MiB of RAM llama.cpp's
server, which runs Ollama's model, may keep as a cache of earlier prompts (8 GiB unless told). install.ps1 sets it to
0 for the user, and every process started after that has it. A TASlation started before (from a window that was open
then) or installed by an older install.ps1 lacks it; the Ollama it starts gets the value Windows keeps for the user or
the computer, as a process started now would, else 0, the install's value. A value that is set is never changed.

Only the address Ollama serves by default is started (`startable`): an Ollama set up elsewhere is the setup of whoever
set it up, and starting one here would not answer there.

The result is None when Ollama answers, else a `taslation.messages.Message`:

* ``health.ollama_not_installed``: none was found;
* ``health.ollama_no_answer``: one was started and did not answer within `START_WAIT_S`;
* ``health.ollama_down`` {url}: nothing was started, or the wait was cancelled (the banner's line; no popup).

`OllamaStarter` is what the window and the commands hold: at most one try every `RETRY_GAP_S`, so that requests that
find Ollama gone (`OllamaTranslator.revive`) never start it in a loop. Everything here waits, and runs in a worker
thread, never on Tk's."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from . import health
from .messages import Message

DEFAULT_HOSTS = ("127.0.0.1", "localhost")  # where Ollama listens unless told otherwise ...
DEFAULT_PORT = 11434  # ... and on which port
START_WAIT_S = 30.0  # how long a started Ollama is given to answer (install.ps1 gives it the same)
POLL_S = 0.25  # how often it is asked meanwhile
RETRY_GAP_S = 60.0  # at most one try in this many seconds
POPUP_CODES = frozenset({"health.ollama_not_installed", "health.ollama_no_answer"})  # what the window's popup says
# llama.cpp's server keeps up to 8 GiB of earlier prompts in RAM unless this says otherwise (MiB; 0: no cache). In a
# whole-book run on the GPU the translator's server peaked at 9.8 GB working set with it and at 1.7 GB without, and
# translated at the same speed; without the GPU it peaked at 7.4 GB and 4.0 GB, and translated 8 % faster with it
# (docs/OFFLINE_VERIFICATION.md, "Ollama's prompt cache in RAM").
CACHE_RAM_VAR = "LLAMA_ARG_CACHE_RAM"
CACHE_RAM_OFF = "0"  # what install.ps1 sets for the user
# where Windows keeps the variables of the user and of the computer, from which a new process's environment is made
USER_ENV_KEY = "Environment"
MACHINE_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

_launched: list[subprocess.Popen] = []  # kept so that a process still running is not reported as dropped


def startable(url: str) -> bool:
    """Whether *url* is the address Ollama serves by default, the only one TASlation starts it for."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return parsed.scheme == "http" and parsed.hostname in DEFAULT_HOSTS and port == DEFAULT_PORT


def find_ollama() -> list[str] | None:
    """The command that starts Ollama on this computer; None when it is not installed."""
    programs = os.environ.get("LOCALAPPDATA")
    if programs:
        home = Path(programs) / "Programs" / "Ollama"
        if (home / "ollama app.exe").is_file():
            return [str(home / "ollama app.exe")]
        if (home / "ollama.exe").is_file():
            return [str(home / "ollama.exe"), "serve"]
    found = shutil.which("ollama")
    return [found, "serve"] if found else None


def stored_value(name: str) -> str | None:
    """The variable *name* as Windows keeps it for this user, else for the computer (what a process started now would
    get); None when neither has it, or off Windows."""
    if sys.platform != "win32":
        return None
    import winreg

    for root, key in ((winreg.HKEY_CURRENT_USER, USER_ENV_KEY), (winreg.HKEY_LOCAL_MACHINE, MACHINE_ENV_KEY)):
        try:
            with winreg.OpenKey(root, key) as opened:
                value, kind = winreg.QueryValueEx(opened, name)
        except OSError:
            continue
        if kind == winreg.REG_EXPAND_SZ:
            value = winreg.ExpandEnvironmentStrings(value)
        if isinstance(value, str) and value:
            return value
    return None


def server_env() -> dict[str, str] | None:
    """The environment of the Ollama TASlation starts: None, TASlation's own (inherited), when it has
    `CACHE_RAM_VAR`; else TASlation's with that variable as this user or the computer has it set (TASlation was
    started before it was), else `CACHE_RAM_OFF`."""
    if CACHE_RAM_VAR in os.environ:
        return None
    return {**os.environ, CACHE_RAM_VAR: stored_value(CACHE_RAM_VAR) or CACHE_RAM_OFF}


def launch(command: list[str], env: dict[str, str] | None = None) -> None:
    """*command* started detached: no console, no shell, nothing shared with this process (standard streams, the
    working folder: a folder in use could not be removed), and it lives on after TASlation ends. Its environment is
    *env*, else this process's."""
    options: dict[str, Any] = {}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    if env is not None:
        options["env"] = env
    _launched.append(subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, shell=False, cwd=str(Path(command[0]).parent),
                                      **options))


def _started(url: str, cancel: threading.Event | None, on_starting: Callable[[], None] | None) -> Message | None:
    """Ollama, found not to answer at *url*, started and waited for (see the module's docstring)."""
    down = Message("health.ollama_down", url=url)
    if not startable(url) or (cancel is not None and cancel.is_set()):
        return down
    command = find_ollama()
    if command is None:
        return Message("health.ollama_not_installed")
    if on_starting is not None:
        on_starting()
    try:
        launch(command, server_env())
    except OSError:
        return Message("health.ollama_no_answer")
    pause = cancel if cancel is not None else threading.Event()  # never set, without a caller's event
    deadline = time.monotonic() + START_WAIT_S
    while not health.ollama_running(url):
        if time.monotonic() >= deadline:
            return Message("health.ollama_no_answer")
        if pause.wait(POLL_S):
            return down
    return None


class OllamaStarter:
    """Ollama at one address made to answer (see the module's docstring), with at most one try every `RETRY_GAP_S` (a window's or a command's whole
    life: the start, then the requests that find Ollama gone). *on_starting* says so where the reader looks."""

    def __init__(self, url: str, on_starting: Callable[[], None] | None = None):
        self.url = url
        self.on_starting = on_starting
        self._last: float | None = None  # when the last try began
        self._lock = threading.Lock()

    def start(self, cancel: threading.Event | None = None) -> Message | None:
        """None when Ollama answers (started now if it has to be); else what stands in the way, and for a look
        within `RETRY_GAP_S` of the last try ``health.ollama_down``, with nothing started."""
        if health.ollama_running(self.url):
            return None
        with self._lock:
            now = time.monotonic()
            if self._last is not None and now - self._last < RETRY_GAP_S:
                return Message("health.ollama_down", url=self.url)
            self._last = now
        return _started(self.url, cancel, self.on_starting)

    def revive(self, cancel: threading.Event | None = None) -> bool:
        """Whether Ollama answers now (`OllamaTranslator.revive`)."""
        return self.start(cancel) is None
