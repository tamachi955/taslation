"""Ollama started when it is not running, so that a reader never has to.

`OllamaStarter.start` looks at the Ollama the settings name and, when it does not answer, starts it: the tray app the
Ollama installer starts (`%LOCALAPPDATA%\\Programs\\Ollama\\ollama app.exe`, which then runs the server), else
``ollama.exe`` beside it, else ``ollama`` from the PATH, these two as ``ollama serve`` (`find_ollama`). The process is
detached, has no console and no shell, and outlives TASlation: it is an Ollama like one the reader started, and
TASlation never stops it. Its environment is TASlation's, unchanged.

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


def launch(command: list[str]) -> None:
    """*command* started detached: no console, no shell, nothing shared with this process (standard streams, the
    working folder: a folder in use could not be removed), and it lives on after TASlation ends."""
    options: dict[str, Any] = {}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
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
        launch(command)
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
