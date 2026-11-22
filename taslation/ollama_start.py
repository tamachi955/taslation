"""Ollama started when TASlation needs it and stopped when TASlation ends, so that a reader never has to, and so that
an Ollama nobody uses does not keep running from every sign-in.

Most people who install TASlation use Ollama for nothing else. install.ps1 therefore keeps an Ollama it installs from
starting with Windows, and TASlation runs Ollama's server only while it needs it, unless the person runs Ollama
themselves: an Ollama that answers when TASlation looks, which TASlation did not start, is theirs and is never stopped.

Starting (`OllamaStarter.start`): when nothing answers at the address the settings name, the server itself is
started, ``ollama.exe serve`` (beside Ollama's tray app in ``%LOCALAPPDATA%\\Programs\\Ollama``, else ``ollama`` from
the PATH: `find_ollama`), never the tray app, which would start Ollama with Windows from its first start on and stay
in the tray after TASlation. The process has a console of its own that is never shown (``CREATE_NO_WINDOW``) and a
process group of its own (``CREATE_NEW_PROCESS_GROUP``: what lets it be asked to stop), no shell, nothing shared with
this process (standard streams, the working folder: a folder in use could not be removed), and it is not ended with
TASlation's process by Windows. Its environment is TASlation's (what the reader set for Ollama comes with it), with
three variables added when TASlation's lacks them (`server_setup`, `server_env`; a value that is set anywhere is never
changed):

* ``OLLAMA_KV_CACHE_TYPE``, the KV cache's precision: the value Windows keeps for the user or the computer (as a
  process started now would get it), else ``q8_0`` on an NVIDIA GPU of 6 GB or less (`small_gpu`, as install.ps1
  decides from the same number, NVML's, which nvidia-smi gives it), where the model's whole context fits in video
  memory only so (about 4 times the speed); nothing on a larger GPU or none;
* ``LLAMA_ARG_SWA_FULL``, whether llama.cpp's server, which runs Ollama's model, keeps the cache of the layers with a
  sliding window (21 of PLaMo's 24) full-size: then it keeps no "context checkpoints", a request that extends the last
  one computes only its new tokens, and one that parts from it within its pairs computes from there instead of from
  its start (OpenMantra, the 6 GB card: translation 26 to 27 % faster with the cache below; 132 MiB more GPU memory
  with q8_0, 220 with f16; docs/OFFLINE_VERIFICATION.md, "The full-size window cache"). The value Windows keeps,
  else ``1`` as ``ollama_window_cache`` says (`window_choice`): "on" always, "off" never, "auto" (the default) unless
  the OCR readers would leave the GPU for it - where `taslation.ocr.place`'s rule keeps them there with the model at
  its footprint without the cache and puts them on the CPU with it (`place.full_window_placements`; asked once, at the
  start; a computer without a usable GPU, and a fixed ``ocr_runs_on``, get it);
* ``LLAMA_ARG_CACHE_RAM``, how many MiB of RAM the server may keep as a cache of earlier prompts (8 GiB unless told):
  the value Windows keeps (an older install.ps1 set it for the user), else `CACHE_RAM_WITH_WINDOW` (256) where the
  window cache is full-size and the setting is not "off" (a saved prompt is then tens of MB, and the request after
  one whose ``context`` differs finds the state before it), else 0 (with checkpoints a saved prompt took 1.5 to 2 GB,
  for no speed with a GPU).

What the server got (`ServerSetup`: the KV type, the window, the RAM cache, why, and the room the rule found both
ways) is kept for the address (`setup_of`, `server_cache`: `taslation.ocr.place` counts the translation model by it)
and in the record below, and the log says it once (numbers only).

Only the address Ollama serves by default is started (`startable`): an Ollama set up elsewhere is the setup of whoever
set it up, and starting one here would not answer there.

Owning: the server TASlation started is written down in ``<state folder>/ollama-started.json`` (`RECORD_FILE`; plain,
no text of a book) - its process number, its program and when it started (pids are reused: the three together name
it), the address, what it was given (``setup``), and the TASlation processes that use it (the window and a
``taslation`` command at once), each by its number and start time. A process that starts Ollama, or finds the
recorded server running, puts itself into the record (a "claim" of this process); one whose look finds an Ollama
that is not recorded owns nothing. The record is
read and written under a lock that every TASlation process of this Windows session shares (`_Lock`). A record that
names a server no longer running, or another process under its number, is dropped; one that names a live server
TASlation started (a TASlation that crashed left it) is adopted: used, and stopped at the end as below.

Stopping (`finish_all`: the window once it has closed, a command of `taslation.cli` at its end, Ctrl+C included, and
at the interpreter's exit as a last resort): for each claim this process holds, the process leaves the record, and the
recorded server is stopped only when ALL hold: it is still the process that was started (its number, program and start
time); no other TASlation process that uses it is still running; and nobody else is using it: Ollama's ``/api/ps``
lists no model but TASlation's own (`taslation.translate.models.MODELS`, and a model the settings name by hand). With
another program's model loaded, the server is left running and no longer owned (the record goes; the log names the
models). The stop is Ollama's own (what its tray app does to the server it runs: `ask_to_stop`, a CTRL_BREAK to the
server's process group through its console; Ollama then ends the model's process itself), for at most `STOP_WAIT_S`;
a server that does not end then is terminated with its descendants (llama.cpp's ``llama-server``), as Ollama's own
uninstaller ends them, for at most `KILL_WAIT_S` more. Either way, once the server has ended, what it started that
still runs, and theirs, is terminated and waited for within that bound, and looked for again until none is left: a
process may outlive the server by a moment (the console host Windows gives the server's hidden console), and one
started after the first look, or one the request did not reach, is in no earlier list. The server is held open
meanwhile (`pinned`), so that no other process gets its number and passes for the parent of what it starts. One still
running after that (the server, or a process it started) is left, and the record kept for the next end. Nothing here
ever waits without a bound.

Messages of `OllamaStarter.start` (None when Ollama answers):

* ``health.ollama_not_installed``: none was found;
* ``health.ollama_no_answer``: one was started and did not answer within `START_WAIT_S`;
* ``health.ollama_down`` {url}: nothing was started, or the wait was cancelled (the banner's line; no popup).

`OllamaStarter` is what the window and the commands hold: at most one try every `RETRY_GAP_S`, so that requests that
find Ollama gone (`OllamaTranslator.revive`) never start it in a loop.

Restarting (`OllamaStarter.restart`): a request that gets no answer twice, or whose /api/ps look gets none either
(`taslation.translate.ollama`, `OllamaTranslator.restart`), has the server stopped and started again - only the
server TASlation started (the record names it and it still runs as that process) and only while /api/ps lists no
model but TASlation's own; at most once in `RESTART_GAP_S`. It is stopped as at the end (`stop_server`), started as
above with what `server_setup` gives it now, its record carrying the other TASlation processes that used the old one,
and waited for `START_WAIT_S`. An Ollama the person runs is never stopped, restarted or reconfigured: the request
then ends with a sentence that asks the reader to restart it. Everything here waits, and runs in a worker thread,
never on Tk's.

Yielding (`asking_behind`, `yield_server`, `before_request`): the work behind the reader - a step of the backlog that
asks the translator for the pages turned past (`taslation.backlog`) - is computed by the server TASlation started at
below-normal priority: the server and the processes it started (the model's runner), from the step's start until the
next request that has the server compute and is not such work (the page on show's, a load: `before_request`, which
`translate.ollama` calls before each request); each then goes back to the class the server had. Not as the step ends:
a request the step gave up is still computed to the end of the prompt batch under way, and that is what a turn meets.
On a computer without a GPU the server's prompt takes the processor from everything the reader sees (GitHub's runners,
4 logical processors: a request of the backlog's asked from its start, 700 to 1000 tokens, kept the server at work 6-7
s right after a page was done; the window's captures of the viewer stalled 1.5-3 s with 30-80 ms of processor time of
their own, and the stand-in viewer, a browser drawing on the processor, drew 4 and 7 of 10 quick turns); at
below-normal priority it computes on what the desktop leaves. Only for a server this process alone uses (another
TASlation's requests are not this one's to slow) and only on Windows; a process that cannot be set is left as it is.
An Ollama the person runs is never touched."""

from __future__ import annotations

import atexit
import contextlib
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, NamedTuple
from urllib.parse import urlparse

from . import health
from .messages import Message

LOG = logging.getLogger(__name__)

DEFAULT_HOSTS = ("127.0.0.1", "localhost")  # where Ollama listens unless told otherwise ...
DEFAULT_PORT = 11434  # ... and on which port
START_WAIT_S = 30.0  # how long a started Ollama is given to answer (install.ps1 gives it the same)
POLL_S = 0.25  # how often it is asked meanwhile
RETRY_GAP_S = 60.0  # at most one try in this many seconds
RESTART_GAP_S = 600.0  # at most one restart of the server TASlation started in this many seconds (`restart`)
POPUP_CODES = frozenset({"health.ollama_not_installed", "health.ollama_no_answer"})  # what the window's popup says
# llama.cpp's server keeps up to 8 GiB of earlier prompts in RAM unless this says otherwise (MiB; 0: no cache). In a
# whole-book run on the GPU the translator's server peaked at 9.8 GB working set with it and at 1.7 GB without, and
# translated at the same speed; without the GPU it peaked at 7.4 GB and 4.0 GB, and translated 8 % faster with it
# (docs/OFFLINE_VERIFICATION.md, "Ollama's prompt cache in RAM").
CACHE_RAM_VAR = "LLAMA_ARG_CACHE_RAM"
CACHE_RAM_OFF = "0"  # what an Ollama TASlation starts gets when the variable is set nowhere ...
# ... and with the full-size window cache, where a saved prompt is the cache alone: 256 MiB held about 15 prompts in a
# whole-book run, and 1024 MiB translated no faster (OpenMantra, 296.3 and 294.4 s)
CACHE_RAM_WITH_WINDOW = "256"
# A GPU of 6 GB or less holds the translator's whole context only with a quantized KV cache (install.ps1's rule, by the
# same number: the video memory NVIDIA's driver reports, in MiB).
KV_CACHE_VAR = "OLLAMA_KV_CACHE_TYPE"
KV_CACHE_SMALL_GPU = "q8_0"
KV_CACHE_DEFAULT = "f16"  # Ollama's own where the variable is set nowhere
SMALL_GPU_MIB = 6144
# llama.cpp's server keeps the cache of the windowed layers full-size (no context checkpoints) where this is true
SWA_FULL_VAR = "LLAMA_ARG_SWA_FULL"
SWA_FULL_ON = "1"
TRUE_VALUES = ("1", "true", "on", "enabled")  # what llama.cpp's server takes as true for a flag's variable
WINDOW_CACHE_VALUES = ("auto", "off", "on")  # ``ollama_window_cache``
# why the server's window cache is as it is (`ServerSetup.why`)
WHY_SET, WHY_SETTING, WHY_OCR_SET, WHY_NO_GPU, WHY_NO_LOSS, WHY_READERS = (
    "set", "setting", "ocr_set", "no_gpu", "no_loss", "readers")
# where Windows keeps the variables of the user and of the computer, from which a new process's environment is made
USER_ENV_KEY = "Environment"
MACHINE_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
RECORD_FILE = "ollama-started.json"  # in the state folder: the server TASlation started, and who uses it
STOP_WAIT_S = 5.0  # how long the server is given to end when asked (Ollama's tray app gives its server as long)
KILL_WAIT_S = 2.0  # how long a terminated server is given to be gone
HELPER_TIMEOUT_S = 3.0  # the helper that asks the server to stop (`ask_to_stop`)
LOCK_WAIT_S = 10.0  # how long the record's lock is waited for; after that the record is used without it
PS_TIMEOUT_S = 2.0  # /api/ps at the end: it only looks

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
    """The command that runs Ollama's server on this computer, ``ollama.exe serve``: the one beside Ollama's tray app
    where Ollama's installer puts it, else the one on the PATH; None when it is not installed. Never the tray app."""
    programs = os.environ.get("LOCALAPPDATA")
    if programs:
        exe = Path(programs) / "Programs" / "Ollama" / "ollama.exe"
        if exe.is_file():
            return [str(exe), "serve"]
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


def small_gpu() -> bool:
    """Whether this computer's first NVIDIA GPU has 6 GB of video memory or less (`devices.nvml_memory_mib`: NVIDIA's
    driver library, no torch); False without one, or when its driver does not say."""
    from .devices import nvml_memory_mib

    mib = nvml_memory_mib()
    return 0 < mib <= SMALL_GPU_MIB


def is_true(value: Any) -> bool:
    """Whether *value* of a flag's variable is true as llama.cpp's server reads it (`TRUE_VALUES`)."""
    return str(value or "").strip().lower() in TRUE_VALUES


@dataclass(frozen=True)
class ServerSetup:
    """What the Ollama TASlation starts is given (`server_setup`): its KV cache type *kv_cache* (`KV_CACHE_DEFAULT`
    where it is set nowhere), whether its window cache is full-size (*full_window*), its RAM cache in MiB
    (*cache_ram*), *why* the window cache is as it is (`WHY_SET`, ...), the variables TASlation adds to its own
    environment (*added*), and the room the OCR readers' rule found at the peak without the window cache and with it
    (*rooms*: MiB, None where it did not measure)."""

    kv_cache: str
    full_window: bool
    cache_ram: str
    why: str
    added: dict[str, str] = field(default_factory=dict, compare=False)
    rooms: tuple[int | None, int | None] = (None, None)

    def to_record(self) -> dict[str, Any]:
        return {"kv_cache": self.kv_cache, "full_window": self.full_window, "cache_ram": self.cache_ram,
                "why": self.why, "rooms": list(self.rooms)}

    @classmethod
    def from_record(cls, data: Any) -> "ServerSetup | None":
        if not isinstance(data, dict) or not isinstance(data.get("full_window"), bool):
            return None
        rooms = data.get("rooms")
        if not (isinstance(rooms, list) and len(rooms) == 2
                and all(r is None or (isinstance(r, int) and not isinstance(r, bool)) for r in rooms)):
            rooms = [None, None]
        return cls(str(data.get("kv_cache") or KV_CACHE_DEFAULT), data["full_window"], str(data.get("cache_ram") or ""),
                   str(data.get("why") or ""), rooms=(rooms[0], rooms[1]))


def window_setting(settings: Any) -> str:
    """``ollama_window_cache`` of *settings* ("auto" where it says nothing known)."""
    value = str(getattr(settings, "ollama_window_cache", "auto") or "auto").strip().lower()
    return value if value in WINDOW_CACHE_VALUES else "auto"


def window_choice(settings: Any, kv: str) -> tuple[bool, str, tuple[int | None, int | None]]:
    """Whether the server TASlation starts with the KV cache *kv* gets the full-size window cache by
    ``ollama_window_cache`` of *settings* (the module's docstring), why (`WHY_SETTING`, `WHY_OCR_SET`, `WHY_NO_GPU`,
    `WHY_NO_LOSS`, `WHY_READERS`), and the rooms the readers' rule found without it and with it. Asked once, as the
    server starts; NVML first, so that a computer without an NVIDIA GPU never loads torch for it."""
    setting = window_setting(settings)
    if setting != "auto":
        return setting == "on", WHY_SETTING, (None, None)
    if str(getattr(settings, "ocr_runs_on", "auto") or "auto") in ("cpu", "gpu"):
        return True, WHY_OCR_SET, (None, None)
    from .ocr import place

    if place.card_memory() is None:
        return True, WHY_NO_GPU, (None, None)
    try:
        before, after = place.full_window_placements(settings, kv)
    except Exception as e:  # noqa: BLE001 - nothing to judge on: the readers' room is not known either way
        LOG.info("the room for the OCR readers could not be measured for Ollama's start (%s)", type(e).__name__)
        return True, WHY_NO_LOSS, (None, None)
    rooms = (before.room, after.room)
    if before.why == place.NO_CUDA:
        return True, WHY_NO_GPU, rooms
    if before.device == "gpu" and after.device != "gpu":
        return False, WHY_READERS, rooms
    return True, WHY_NO_LOSS, rooms


def _settings_or_saved(settings: Any) -> Any:
    """*settings*, else the saved ones (`Settings.load`), else the defaults."""
    if settings is not None:
        return settings
    from .config import Settings

    try:
        return Settings.load()
    except Exception:  # noqa: BLE001 - a file that does not load: the defaults
        return Settings()


def server_setup(settings: Any = None) -> ServerSetup:
    """What the Ollama TASlation starts for *settings* (the saved ones when None) is given, the module's docstring's
    three variables: each one TASlation's environment lacks as this user or the computer has it set (TASlation was
    started before it was), else as TASlation decides it. A value that is set anywhere is never changed."""
    added: dict[str, str] = {}
    kv = os.environ.get(KV_CACHE_VAR)
    if kv is None:
        kv = stored_value(KV_CACHE_VAR) or (KV_CACHE_SMALL_GPU if small_gpu() else None)
        if kv:
            added[KV_CACHE_VAR] = kv
    kv = (kv or "").strip() or KV_CACHE_DEFAULT
    rooms: tuple[int | None, int | None] = (None, None)
    own = os.environ.get(SWA_FULL_VAR)
    if own is None:
        own = stored_value(SWA_FULL_VAR)
        if own:
            added[SWA_FULL_VAR] = own
    if own is not None:
        full, why = is_true(own), WHY_SET
    else:
        settings = _settings_or_saved(settings)
        full, why, rooms = window_choice(settings, kv)
        if full:
            added[SWA_FULL_VAR] = SWA_FULL_ON
    ram = os.environ.get(CACHE_RAM_VAR)
    if ram is None:
        ram = stored_value(CACHE_RAM_VAR)
        if not ram:
            with_window = full and window_setting(_settings_or_saved(settings)) != "off"
            ram = CACHE_RAM_WITH_WINDOW if with_window else CACHE_RAM_OFF
        added[CACHE_RAM_VAR] = ram
    return ServerSetup(kv, full, ram, why, added, rooms)


def server_env(settings: Any = None, setup: ServerSetup | None = None) -> dict[str, str] | None:
    """The environment of the Ollama TASlation starts: TASlation's own (None: inherited) when it has the module's
    docstring's three variables; else TASlation's with what *setup* adds (`server_setup` for *settings* when None)."""
    added = (setup if setup is not None else server_setup(settings)).added
    return {**os.environ, **added} if added else None


WHY_TEXT = {  # the log's and the tests' words for `ServerSetup.why`
    WHY_SET: "LLAMA_ARG_SWA_FULL as set on this computer",
    WHY_SETTING: "as ollama_window_cache says",
    WHY_OCR_SET: "ocr_runs_on is set",
    WHY_NO_GPU: "no NVIDIA GPU with CUDA for the OCR readers",
    WHY_NO_LOSS: "the OCR readers run in the same place either way",
    WHY_READERS: "with it the OCR readers would leave the GPU",
}


def _say_setup(setup: ServerSetup) -> None:
    """The log's line on what the server TASlation started got (numbers and settings only)."""
    before, after = setup.rooms
    LOG.info("Ollama started by TASlation: the full-size window cache %s (%s), KV cache %s, prompt cache in RAM %s "
             "MiB; the OCR readers' room at the peak %s MiB without the window cache, %s MiB with it",
             "on" if setup.full_window else "off", WHY_TEXT.get(setup.why, setup.why), setup.kv_cache,
             setup.cache_ram, "?" if before is None else before, "?" if after is None else after)


_setups: dict[str, ServerSetup] = {}  # address -> what the server TASlation started there got (this process, a record)
_setups_lock = threading.Lock()


def _address(url: Any) -> str:
    return str(url or "").rstrip("/")


def _keep_setup(url: str, setup: ServerSetup | None) -> None:
    with _setups_lock:
        if setup is None:
            _setups.pop(_address(url), None)
        else:
            _setups[_address(url)] = setup


def setup_of(url: str, state_dir: Path | str | None = None) -> ServerSetup | None:
    """What the server TASlation started at *url* got: as the record in *state_dir* says while it names that server
    running (whichever TASlation started it; read only: nothing is claimed), else as this process started or joined it;
    None for an Ollama TASlation did not start (or one recorded before the record kept it)."""
    path = record_path(state_dir)
    if path is not None and path.is_file():
        record = _read(path)
        if record is not None and _same_url(record.get("url"), url) and _server_alive(record):
            setup = ServerSetup.from_record(record.get("setup"))
            if setup is not None:
                return setup
    with _setups_lock:
        return _setups.get(_address(url))


def server_cache(url: str, state_dir: Path | str | None = None) -> tuple[str, bool]:
    """(KV cache type, whether the window cache is full-size) of the Ollama at *url*: as TASlation started it
    (`setup_of`); else as the variables of this process, then those Windows keeps, say, with ``q8_0`` on a small GPU
    where none names the KV type (what TASlation would give a server it starts; install.ps1 sets it so for an Ollama
    that was there before). A guess for an Ollama TASlation did not start: `taslation.ocr.place` tells the caches apart
    by /api/ps's size once the model is loaded."""
    setup = setup_of(url, state_dir)
    if setup is not None:
        return setup.kv_cache, setup.full_window
    kv = os.environ.get(KV_CACHE_VAR) or stored_value(KV_CACHE_VAR) or (KV_CACHE_SMALL_GPU if small_gpu() else "")
    full = os.environ.get(SWA_FULL_VAR)
    return kv.strip() or KV_CACHE_DEFAULT, is_true(full if full is not None else stored_value(SWA_FULL_VAR))


def launch(command: list[str], env: dict[str, str] | None = None) -> subprocess.Popen:
    """*command* started as the module's docstring says: a console of its own never shown, a process group of its own,
    no shell, nothing shared with this process, its folder as the working folder. Its environment is *env*, else this
    process's. Raises OSError when it cannot be started."""
    options: dict[str, Any] = {}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    if env is not None:
        options["env"] = env
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            shell=False, cwd=str(Path(command[0]).parent), **options)
    _launched.append(proc)
    return proc


# ------------------------------------------------------------------ processes (Windows; nothing elsewhere)
class ProcessInfo(NamedTuple):
    """A running process as Windows knows it: its program's full path and when it started (a FILETIME: 100 ns since
    1601, as GetProcessTimes gives it; the same number names the same process, a reused pid has another)."""

    exe: str
    started: int


_SYNCHRONIZE = 0x00100000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
NORMAL_PRIORITY_CLASS = 0x00000020
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
IDLE_PRIORITY_CLASS = 0x00000040
_WAIT_OBJECT_0 = 0
_WAIT_ABANDONED = 0x80
_WAIT_TIMEOUT = 0x102
_TH32CS_SNAPPROCESS = 0x2
_kernel32_dll: Any = None


def _kernel32() -> Any:
    """kernel32 with the signatures used here (handles are pointers on a 64-bit Python)."""
    global _kernel32_dll
    if _kernel32_dll is None:
        import ctypes
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD))
        k.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        k.GetPriorityClass.restype = wintypes.DWORD
        k.GetPriorityClass.argtypes = (wintypes.HANDLE,)
        k.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        k.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        _kernel32_dll = k
    return _kernel32_dll


def _open(pid: int, access: int) -> Any:
    if sys.platform != "win32" or not isinstance(pid, int) or pid <= 0:
        return None
    return _kernel32().OpenProcess(access | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid) or None


def _start_time(handle: Any) -> int | None:
    """When the process *handle* opens started (`ProcessInfo.started`), whether it has ended or not; None when Windows
    does not say."""
    import ctypes
    from ctypes import wintypes

    times = [wintypes.FILETIME() for _ in range(4)]
    if not _kernel32().GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        return None
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def _info_of(handle: Any) -> ProcessInfo | None:
    import ctypes
    from ctypes import wintypes

    k = _kernel32()
    if k.WaitForSingleObject(handle, 0) != _WAIT_TIMEOUT:
        return None  # it has ended (its handle is signalled)
    started = _start_time(handle)
    if started is None:
        return None
    size = wintypes.DWORD(32768)
    name = ctypes.create_unicode_buffer(size.value)
    if not k.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
        return None
    return ProcessInfo(name.value, started)


def process_info(pid: int) -> ProcessInfo | None:
    """The running process *pid* (`ProcessInfo`); None when no process has that number now, or it cannot be asked."""
    handle = _open(pid, _SYNCHRONIZE)
    if handle is None:
        return None
    try:
        return _info_of(handle)
    finally:
        _kernel32().CloseHandle(handle)


def descendants(pid: int, started: int) -> list[tuple[int, int]]:
    """The processes *pid* (which started at *started*) started, and theirs, as (pid, started): each one started after
    its parent (a parent's number in a process list may be an ended process's, reused). Empty off Windows."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k = _kernel32()
    snapshot = k.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return []
    parents: dict[int, list[int]] = {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents.setdefault(int(entry.th32ParentProcessID), []).append(int(entry.th32ProcessID))
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    found: list[tuple[int, int]] = []
    todo = [(pid, started)]
    while todo:
        parent, parent_started = todo.pop()
        for child in parents.get(parent, []):
            if child == parent or any(child == f for f, _s in found):
                continue
            info = process_info(child)
            if info is not None and info.started >= parent_started:
                found.append((child, info.started))
                todo.append((child, info.started))
    return found


def same_process(pid: Any, started: Any, exe: str | None = None) -> bool:
    """Whether process *pid* runs and is the one that started at *started* (and runs *exe*, when given)."""
    if not isinstance(pid, int) or not isinstance(started, int):
        return False
    info = process_info(pid)
    if info is None or info.started != started:
        return False
    return exe is None or os.path.normcase(os.path.abspath(info.exe)) == os.path.normcase(os.path.abspath(exe))


def wait_exit(pid: int, started: int, seconds: float) -> bool:
    """Whether process *pid* (the one that started at *started*) is gone, waited for up to *seconds*."""
    handle = _open(pid, _SYNCHRONIZE)
    if handle is None:
        return True
    try:
        info = _info_of(handle)
        if info is None or info.started != started:
            return True
        return _kernel32().WaitForSingleObject(handle, max(0, int(seconds * 1000))) == _WAIT_OBJECT_0
    finally:
        _kernel32().CloseHandle(handle)


def terminate(pid: int, started: int) -> bool:
    """Process *pid* ended at once (TerminateProcess), when it is still the one that started at *started*. Whether
    it was told to."""
    handle = _open(pid, _SYNCHRONIZE | _PROCESS_TERMINATE)
    if handle is None:
        return False
    try:
        info = _info_of(handle)
        return info is not None and info.started == started and bool(_kernel32().TerminateProcess(handle, 1))
    finally:
        _kernel32().CloseHandle(handle)


def priority_class(pid: int, started: int) -> int | None:
    """Process *pid*'s priority class (`NORMAL_PRIORITY_CLASS`, ...), when it is still the one that started at
    *started*; None otherwise, and when Windows does not say."""
    handle = _open(pid, _SYNCHRONIZE)
    if handle is None:
        return None
    try:
        info = _info_of(handle)
        if info is None or info.started != started:
            return None
        return int(_kernel32().GetPriorityClass(handle)) or None
    finally:
        _kernel32().CloseHandle(handle)


def set_priority_class(pid: int, started: int, value: int) -> bool:
    """Process *pid* given the priority class *value*, when it is still the one that started at *started*. Whether
    it was."""
    handle = _open(pid, _SYNCHRONIZE | _PROCESS_SET_INFORMATION)
    if handle is None:
        return False
    try:
        info = _info_of(handle)
        return info is not None and info.started == started and bool(_kernel32().SetPriorityClass(handle, value))
    finally:
        _kernel32().CloseHandle(handle)


@contextlib.contextmanager
def pinned(pid: int, started: int) -> Iterator[bool]:
    """Process *pid* held open for a block: while it is, Windows gives its number to no other process, even once it has
    ended, so that the processes a look finds with that number as their parent's are its own (`descendants`). Whether
    the process held is the one that started at *started* (False: no process has that number, or another one has it
    now, and nothing of the one that started then can be told apart any more)."""
    handle = _open(pid, _SYNCHRONIZE)
    try:
        yield handle is not None and _start_time(handle) == started
    finally:
        if handle is not None:
            _kernel32().CloseHandle(handle)


# What Ollama's tray app does to stop the server it started (app/server, server_windows.go): attach to the server's
# console, take no Ctrl+C itself, and send a Ctrl+Break to the server's process group (Go hands it to Ollama as an
# interrupt: Ollama's graceful shutdown). A process can attach to another's console only when it has none of its own,
# which a command run in a terminal has: so it is done by a short-lived Python of its own, which gives up its own
# console first (about 0.1 s).
_ASK_TO_STOP = r"""
import ctypes, sys
k = ctypes.WinDLL("kernel32")
pid = int(sys.argv[1])
k.FreeConsole()
if not k.AttachConsole(pid):
    sys.exit(2)
k.SetConsoleCtrlHandler(None, True)
sent = k.GenerateConsoleCtrlEvent(1, pid)
k.FreeConsole()
sys.exit(0 if sent else 3)
"""


def ask_to_stop(pid: int) -> bool:
    """Ollama's server *pid* asked to stop as its tray app asks it (a CTRL_BREAK to its process group, through its
    console): Ollama then unloads its models, ends their processes and exits. Whether the request was delivered."""
    if sys.platform != "win32":
        return False
    # the interpreter itself (a virtual environment's python.exe starts it as a process of its own), with a console of
    # its own never shown, which it gives up for the server's
    python = getattr(sys, "_base_executable", "") or sys.executable
    try:
        done = subprocess.run([python, "-I", "-S", "-c", _ASK_TO_STOP, str(pid)], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=HELPER_TIMEOUT_S,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def stop_server(pid: int, started: int) -> bool:
    """The server *pid* (the process that started at *started*) stopped as the module's docstring says: asked, else
    terminated with its descendants, and what it started ended with it (`_end_left`); whether it and all of those are
    gone. At most `HELPER_TIMEOUT_S` + `STOP_WAIT_S` + `KILL_WAIT_S`."""
    with pinned(pid, started) as the_server:
        if not the_server:
            return True  # it has ended (and its number may be another process's: nothing is touched)
        children = descendants(pid, started)
        if ask_to_stop(pid) and wait_exit(pid, started, STOP_WAIT_S):
            # (Ollama ends them itself; one left behind goes too, and one ending is waited for)
            return _end_left(pid, started, children, time.monotonic() + KILL_WAIT_S)
        for child, child_started in dict.fromkeys(descendants(pid, started) + children):
            terminate(child, child_started)
        terminate(pid, started)
        deadline = time.monotonic() + KILL_WAIT_S
        gone = wait_exit(pid, started, KILL_WAIT_S)
        return _end_left(pid, started, children, deadline) and gone


def _end_left(pid: int, started: int, listed: list[tuple[int, int]], deadline: float) -> bool:
    """What the server *pid* (the process that started at *started*, held by `pinned`, ended or told to end) started,
    and theirs, ended: those of *listed* (found while it ran: one whose parent has ended since is no longer found from
    it) and those a look finds now, each terminated and waited for until *deadline*, then looked for again, as one may
    have started another meanwhile (once more after *deadline*, without a wait). Whether none is left; the log says how
    many are."""
    known, last = list(listed), False
    while True:
        known = list(dict.fromkeys(known + descendants(pid, started)))
        left = [(child, child_started) for child, child_started in known if same_process(child, child_started)]
        if not left:
            return True
        if last:
            LOG.warning("%d process(es) of the Ollama TASlation started did not end", len(left))
            return False
        for child, child_started in left:
            terminate(child, child_started)
        ended = all(not same_process(child, child_started)
                    or wait_exit(child, child_started, max(0.0, deadline - time.monotonic()))
                    for child, child_started in left)
        last = not ended or time.monotonic() >= deadline


def this_process() -> dict[str, int]:
    """This process as the record names a user of the server: its number and when it started."""
    info = process_info(os.getpid())
    return {"pid": os.getpid(), "started": info.started if info is not None else 0}


# ------------------------------------------------------------------ the record
def record_path(state_dir: Path | str | None) -> Path | None:
    """Where the server TASlation started is written down for *state_dir* (None: nowhere)."""
    return Path(state_dir) / RECORD_FILE if state_dir else None


class _Lock:
    """The record's lock, shared by every TASlation process of this Windows session: a named mutex made from the
    record's path (Windows gives it up when a process that holds it ends). Waited for up to `LOCK_WAIT_S`; after that
    the record is used without it (said in the log) rather than nothing being done. Off Windows, this process's."""

    _local = threading.RLock()

    def __init__(self, path: Path):
        self.name = "Local\\TASlation-ollama-" + hashlib.sha1(str(path).lower().encode("utf-8")).hexdigest()[:20]
        self.handle: Any = None
        self.held = False

    def __enter__(self) -> "_Lock":
        if sys.platform != "win32":
            self.held = self._local.acquire(timeout=LOCK_WAIT_S)
            return self
        k = _kernel32()
        self.handle = k.CreateMutexW(None, False, self.name)
        if self.handle:
            self.held = k.WaitForSingleObject(self.handle, int(LOCK_WAIT_S * 1000)) in (_WAIT_OBJECT_0, _WAIT_ABANDONED)
        if not self.held:
            LOG.warning("the record of the Ollama TASlation started was used without its lock")
        return self

    def __exit__(self, *_exc: Any) -> None:
        if sys.platform != "win32":
            if self.held:
                self._local.release()
            return
        k = _kernel32()
        if self.held:
            k.ReleaseMutex(self.handle)
        if self.handle:
            k.CloseHandle(self.handle)


def _read(path: Path) -> dict[str, Any] | None:
    """The record at *path*; None when there is none or it cannot be read as one."""
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int) or not isinstance(data.get("started"), int):
        return None
    users = data.get("users")
    data["users"] = [u for u in users if isinstance(u, dict)] if isinstance(users, list) else []
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    from .atomic import write_atomic

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, (json.dumps(data, indent=1) + "\n").encode("utf-8"))
    except OSError as e:
        LOG.warning("the record of the Ollama TASlation started could not be written (%s)", type(e).__name__)


def _drop(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def _server_alive(record: dict[str, Any]) -> bool:
    """Whether the server *record* names still runs as the process TASlation started."""
    return same_process(record.get("pid"), record.get("started"), record.get("exe"))


def _alive(user: dict[str, Any]) -> bool:
    return same_process(user.get("pid"), user.get("started"))


def _is(user: dict[str, Any], me: dict[str, int]) -> bool:
    return user.get("pid") == me["pid"] and user.get("started") == me["started"]


def _same_url(a: Any, b: str) -> bool:
    return str(a or "").rstrip("/") == b.rstrip("/")


def _valid(path: Path, url: str) -> dict[str, Any] | None:
    """The record at *path* when it names a server TASlation started for *url* that still runs; one that does not (an
    ended server, a reused number, another address) is dropped. Under the lock."""
    record = _read(path)
    if record is None:
        return None
    if not _same_url(record.get("url"), url) or not _server_alive(record):
        _drop(path)
        return None
    return record


# ------------------------------------------------------------------ this process's claims
class _Claim(NamedTuple):
    url: str
    own: frozenset[str]  # the names of TASlation's own models besides `MODELS` (a model the settings name)


_claims: dict[Path, _Claim] = {}
_claims_lock = threading.Lock()
_exit_hooked = False
_ends = 0  # how often `finish_all` ran in this process: a start under way across one launches nothing after it


def _register_exit() -> None:
    """`finish_all` at the interpreter's exit, once (the window and the commands call it themselves before)."""
    global _exit_hooked
    if not _exit_hooked:
        _exit_hooked = True
        atexit.register(_at_exit)


def _at_exit() -> None:
    try:
        finish_all()
    except Exception:  # noqa: BLE001 - nothing at exit may raise
        pass


def _claim(path: Path, url: str, own: Iterable[str]) -> None:
    with _claims_lock:
        before = _claims.get(path)
        _claims[path] = _Claim(url, frozenset(own) | (before.own if before else frozenset()))
    _register_exit()


def _use(path: Path, record: dict[str, Any], url: str, own: Iterable[str]) -> None:
    """This process among the users of the recorded server (written when it was not), and its claim on it; what the
    server got (``setup``) kept for its address (`setup_of`)."""
    setup = ServerSetup.from_record(record.get("setup"))
    if setup is not None:
        _keep_setup(url, setup)
    me = this_process()
    if not any(_is(u, me) for u in record["users"]):
        record["users"] = [u for u in record["users"] if _alive(u)] + [me]
        _write(path, record)
    _claim(path, url, own)


def owns_server() -> bool:
    """Whether this process holds a claim on a server TASlation started."""
    with _claims_lock:
        return bool(_claims)


def count_as_own(*names: Any) -> None:
    """The models *names* count as TASlation's own at the end for every claim of this process (the window's model,
    named in the settings during the session)."""
    more = frozenset(str(n).strip() for n in names if n and str(n).strip())
    if not more:
        return
    with _claims_lock:
        for path, claim in list(_claims.items()):
            _claims[path] = _Claim(claim.url, claim.own | more)


def _ours(name: Any, own: Iterable[str]) -> bool:
    """Whether the loaded model *name* is one of TASlation's own (`MODELS`, or one of *own*)."""
    from .translate.models import by_ollama_name
    from .translate.ollama import same_model

    return by_ollama_name(name) is not None or any(same_model(name, m) or same_model(m, str(name)) for m in own)


# ------------------------------------------------------------------ the work behind the reader yields (see the top)
COMPUTING_PATHS = ("/api/generate", "/api/chat")  # the requests that have the server compute (`before_request`)
_yield_lock = threading.Lock()
_yielded: dict[tuple[int, int], int] = {}  # a server lowered (pid, started): the priority class it had before
_behind = threading.local()  # ``on``: this thread asks for work behind the reader (`asking_behind`)


def own_server(url: Any) -> tuple[int, int] | None:
    """The server TASlation started for *url* (pid, started) when this process holds a claim on it, it still runs as
    that process and no other TASlation process that uses it still runs; else None."""
    if not url:
        return None
    with _claims_lock:
        paths = [path for path, claim in _claims.items() if _same_url(claim.url, str(url))]
    if not paths:
        return None
    me = this_process()
    for path in paths:
        record = _read(path)
        if record is None or not _same_url(record.get("url"), str(url)) or not _server_alive(record):
            continue
        if all(_is(user, me) for user in record["users"] if _alive(user)):
            return int(record["pid"]), int(record["started"])
    return None


def _set_all(server: tuple[int, int], value: int) -> int:
    """*server*, then every process it started now (`descendants`), given the priority class *value*; how many were.
    The server first: what it started is looked for after it (a look that fails leaves them as they are)."""
    count = int(set_priority_class(*server, value))
    try:
        started = descendants(*server)
    except Exception as e:  # noqa: BLE001
        LOG.debug("the processes the server started were not found (%s)", type(e).__name__)
        return count
    for pid, began in started:
        count += set_priority_class(pid, began, value)
    return count


def yield_server(url: Any) -> bool:
    """The server TASlation started for *url* (`own_server`) and every process it started at below-normal priority,
    the class the server had kept for `unyield_server` (a process started while it is lowered gets it from the
    server). Whether it is lowered now; nothing changed for a server whose class is that low already, or lower."""
    if sys.platform != "win32":
        return False
    server = own_server(url)
    if server is None:
        return False
    with _yield_lock:
        if server not in _yielded:
            was = priority_class(*server)
            if was is None or was in (BELOW_NORMAL_PRIORITY_CLASS, IDLE_PRIORITY_CLASS):
                return False
            if not set_priority_class(*server, BELOW_NORMAL_PRIORITY_CLASS):
                return False  # (the server refused: nothing it started is lowered alone)
            _yielded[server] = was
        _set_all(server, BELOW_NORMAL_PRIORITY_CLASS)  # (each step: a model loaded meanwhile with another class)
        return True


def unyield_server() -> int:
    """Every server `yield_server` lowered, and the processes it started now, back at the class the server had; how
    many processes were set (a server that has ended since: none)."""
    with _yield_lock:
        lowered = list(_yielded.items())
        _yielded.clear()
        return sum(_set_all(server, was) for server, was in lowered)


def server_yields() -> bool:
    """Whether a server is lowered now (`yield_server`)."""
    return bool(_yielded)


@contextlib.contextmanager
def asking_behind(url: Any) -> Iterator[None]:
    """(a step of the backlog's that asks the translator, on the window's worker) What this thread asks meanwhile is
    work behind the reader: the server TASlation started for *url* computes it at below-normal priority
    (`yield_server`), from now until a request that is not such work has the server compute (`before_request`)."""
    before = getattr(_behind, "on", False)
    _behind.on = True
    try:
        try:
            yield_server(url)
        except Exception as e:  # noqa: BLE001 - the step asks all the same, at the server's own priority
            LOG.debug("the server's priority was not lowered (%s)", type(e).__name__)
        yield
    finally:
        _behind.on = before


def before_request(path: Any) -> None:
    """(`translate.ollama`, before each request) A request that has the server compute (`COMPUTING_PATHS`) and is not
    work behind the reader (`asking_behind`): a server lowered for that work back at its own priority first. Nothing
    to do (the rule, at once) while none is lowered."""
    if not _yielded or getattr(_behind, "on", False) or str(path) not in COMPUTING_PATHS:
        return
    try:
        unyield_server()
    except Exception as e:  # noqa: BLE001 - the request goes all the same
        LOG.debug("the server's priority was not set back (%s)", type(e).__name__)


STOPPED ="The translation program TASlation started was stopped."
IN_USE = "The translation program TASlation started is left running: another TASlation still uses it."
FOREIGN = ("The translation program TASlation started is left running, and TASlation no longer stops it: another "
           "program has {count} model(s) loaded in it ({names}).")
KEPT = ("The translation program TASlation started did not stop within {seconds:.0f} s; it is left running, and "
        "TASlation stops it the next time it ends.")


def _finish(path: Path, claim: _Claim) -> str | None:
    """This process's claim on the server recorded at *path* given up, and the server stopped when the module's
    docstring says so. What came of it (one of the lines above), None when there was nothing to stop."""
    with _Lock(path):
        record = _valid(path, claim.url)
        _keep_setup(claim.url, None)  # (whatever comes of it, this process no longer knows the server as TASlation's)
        if record is None:
            return None  # ended already (or another process gave it up)
        me = this_process()
        others = [u for u in record["users"] if not _is(u, me) and _alive(u)]
        if others:
            record["users"] = others
            _write(path, record)
            return IN_USE
        loaded = health.loaded_models(claim.url, PS_TIMEOUT_S) or []
        foreign = sorted({str(m) for m in loaded if not _ours(m, claim.own)})
        if foreign:
            _drop(path)
            line = FOREIGN.format(count=len(foreign), names=", ".join(foreign))
            LOG.info("Ollama left running: %d model(s) of another program loaded (%s)", len(foreign),
                     ", ".join(foreign))
            return line
        began = time.monotonic()
        if stop_server(record["pid"], record["started"]):
            _drop(path)
            LOG.info("Ollama, started by TASlation, stopped in %.1f s", time.monotonic() - began)
            return STOPPED
        record["users"] = []
        _write(path, record)
        LOG.warning("Ollama, started by TASlation, did not stop; kept for the next end")
        return KEPT.format(seconds=STOP_WAIT_S + KILL_WAIT_S)


def finish_all() -> list[str]:
    """TASlation ends here: every claim of this process given up, and each server stopped that the module's docstring
    says to stop. What came of each (`_finish`); empty when this process held none. Never raises, never waits without
    a bound. A start still under way (`_started`, on a worker thread: the window closed while its server was being
    started) launches nothing after this, and gives up at once what it adopted or launched meanwhile."""
    global _ends
    with _claims_lock:
        _ends += 1
        claims = list(_claims.items())
        _claims.clear()
    said: list[str] = []
    for path, claim in claims:
        try:
            line = _finish(path, claim)
        except Exception:  # noqa: BLE001 - the end goes on
            LOG.exception("stopping the Ollama TASlation started failed")
            continue
        if line:
            said.append(line)
    return said


def own_models(settings: Any) -> tuple[str, ...]:
    """The model the settings name by hand (``ollama_model`` other than "auto"), which counts as TASlation's own at the
    end besides `MODELS`."""
    from .translate.models import is_auto

    setting = getattr(settings, "ollama_model", "auto")
    return () if is_auto(setting) else (str(setting).strip(),)


# ------------------------------------------------------------------ starting
def _started(url: str, cancel: threading.Event | None, on_starting: Callable[[], None] | None,
             path: Path | None, own: Iterable[str], settings: Any = None) -> Message | None:
    """Ollama, found not to answer at *url*, started with what `server_setup` gives it for *settings* (or the server
    TASlation started and recorded at *path* adopted) and waited for (see the module's docstring). TASlation's end
    (`finish_all`) while this is under way: nothing launched after it, and what was adopted or launched meanwhile given
    up at once (a server left running by a window closed during its start, else)."""
    began = _ends
    if not startable(url) or (cancel is not None and cancel.is_set()):
        return Message("health.ollama_down", url=url)
    with _Lock(path) if path is not None else contextlib.nullcontext():
        record = _valid(path, url) if path is not None else None
        if record is not None:
            _use(path, record, url, own)  # a server TASlation started (by another process, or before a crash)
        elif health.ollama_running(url):
            return None  # one came up meanwhile, not TASlation's
        elif _ends != began:
            return Message("health.ollama_down", url=url)  # (TASlation ended meanwhile: nothing launched)
        else:
            failed = _launch(url, on_starting, path, own, settings)
            if failed is not None:
                return failed
    if _ends != began:  # (it ended while this was launched or adopted: given up as its end gives up the others)
        with _claims_lock:
            claim = _claims.pop(path, None) if path is not None else None
        if claim is not None:
            try:
                _finish(path, claim)
            except Exception:  # noqa: BLE001 - said; the start ends all the same
                LOG.exception("stopping the Ollama TASlation started failed")
        return Message("health.ollama_down", url=url)
    return _wait_answer(url, cancel)


def _launch(url: str, on_starting: Callable[[], None] | None, path: Path | None, own: Iterable[str],
            settings: Any = None, users: Iterable[dict[str, Any]] = ()) -> Message | None:
    """``ollama serve`` started for *url* with what `server_setup` gives it for *settings*, and recorded at *path* with
    this process and *users* (the TASlation processes that used the server it replaces) as its users. Under the
    record's lock. None when it was started; else what stands in the way."""
    command = find_ollama()
    if command is None:
        return Message("health.ollama_not_installed")
    if on_starting is not None:
        on_starting()
    setup = server_setup(settings)
    try:
        proc = launch(command, server_env(setup=setup))
    except OSError:
        return Message("health.ollama_no_answer")
    _keep_setup(url, setup)
    _say_setup(setup)
    info = process_info(proc.pid)
    if path is not None and info is not None:
        me = this_process()
        record = {"what": "the Ollama server TASlation started; it stops it when the last TASlation that uses "
                          "it ends", "pid": proc.pid, "exe": info.exe, "started": info.started, "url": url,
                  "setup": setup.to_record(), "users": [u for u in users if not _is(u, me)]}
        _use(path, record, url, own)
    return None


def _wait_answer(url: str, cancel: threading.Event | None) -> Message | None:
    """A server just started at *url* waited for, `START_WAIT_S` at most: None once it answers;
    ``health.ollama_no_answer`` when it did not by then, ``health.ollama_down`` when *cancel* was set meanwhile."""
    pause = cancel if cancel is not None else threading.Event()  # never set, without a caller's event
    deadline = time.monotonic() + START_WAIT_S
    while not health.ollama_running(url):
        if time.monotonic() >= deadline:
            return Message("health.ollama_no_answer")
        if pause.wait(POLL_S):
            return Message("health.ollama_down", url=url)
    return None


class OllamaStarter:
    """Ollama at one address made to answer (see the module's docstring), with at most one try every `RETRY_GAP_S` (a
    window's or a command's whole life: the start, then the requests that find Ollama gone). *on_starting* says so
    where the reader looks. *state_dir*: where the server TASlation starts is recorded (`RECORD_FILE`), which makes it
    TASlation's to stop at the end (`finish_all`); None records nothing (a server started then is never stopped).
    *own*: the names of models that count as TASlation's own at the end besides `MODELS` (`own_models`). *settings*:
    those a server started is given its window cache by (`server_setup`; the saved ones when None), read at each
    start."""

    def __init__(self, url: str, on_starting: Callable[[], None] | None = None, state_dir: Path | str | None = None,
                 own: Iterable[str] = (), settings: Any = None):
        self.url = url
        self.on_starting = on_starting
        self.record = record_path(state_dir)
        self.own = tuple(own)
        self.settings = settings
        self._last: float | None = None  # when the last try began
        self._lock = threading.Lock()
        self._restarted: float | None = None  # when the last restart began (`restart`)
        self._restart_lock = threading.Lock()

    def start(self, cancel: threading.Event | None = None) -> Message | None:
        """None when Ollama answers (started now if it has to be); else what stands in the way, and for a look
        within `RETRY_GAP_S` of the last try ``health.ollama_down``, with nothing started. An Ollama that answers and
        is the server TASlation started is used by this process too (`_join`)."""
        if health.ollama_running(self.url):
            self._join()
            return None
        with self._lock:
            now = time.monotonic()
            if self._last is not None and now - self._last < RETRY_GAP_S:
                return Message("health.ollama_down", url=self.url)
            self._last = now
        return _started(self.url, cancel, self.on_starting, self.record, self.own, self.settings)

    def _join(self) -> None:
        """The Ollama that answers, when it is the server TASlation started (recorded), used by this process too, so
        that another TASlation's end leaves it running while this one needs it; one that is not is nobody's setup of
        TASlation's (`setup_of`)."""
        path = self.record
        if path is None or not startable(self.url):
            return
        if not path.is_file():
            _keep_setup(self.url, None)
            return
        with _Lock(path):
            record = _valid(path, self.url)
            if record is not None:
                _use(path, record, self.url, self.own)
            else:
                _keep_setup(self.url, None)

    def revive(self, cancel: threading.Event | None = None) -> bool:
        """Whether Ollama answers now (`OllamaTranslator.revive`)."""
        return self.start(cancel) is None

    def restart(self, cancel: threading.Event | None = None,
                on_restarting: Callable[[], Any] | None = None) -> bool | None:
        """The server at this address, which gets requests and gives no answer (`OllamaTranslator.restart`, in the
        request's thread), stopped and started again as the module's docstring says; *on_restarting*() is called once
        that is under way (just before the stop), never when nothing is done. True when it answers again; False when
        it was not started again or did not come back (within `RESTART_GAP_S` of the last restart, it would not stop,
        it would not start, it did not answer within `START_WAIT_S`, *cancel* set); None when it is not the server
        TASlation started (no record names it, or another program's model is loaded in it): it is left as it is. The
        log says what was done, numbers only."""
        path = self.record
        if path is None or not startable(self.url):
            LOG.warning("no answer: the translation program is not one TASlation started here; left as it is")
            return None
        with self._restart_lock:
            now = time.monotonic()
            if self._restarted is not None and now - self._restarted < RESTART_GAP_S:
                LOG.warning("no answer: the translation program TASlation started was started again %.0f s ago; not "
                            "again within %.0f s", now - self._restarted, RESTART_GAP_S)
                return False
            with _Lock(path):
                record = _valid(path, self.url)
                if record is None:
                    LOG.warning("no answer: no record names the translation program as one TASlation started; left as "
                                "it is")
                    return None
                loaded = health.loaded_models(self.url, PS_TIMEOUT_S) or []  # (a silent server lists none)
                foreign = sorted({str(m) for m in loaded if not _ours(m, self.own)})
                if foreign:
                    LOG.warning("no answer: another program has %d model(s) loaded in the translation program "
                                "TASlation started; left as it is", len(foreign))
                    return None
                self._restarted = now
                if on_restarting is not None:
                    try:
                        on_restarting()
                    except Exception:  # noqa: BLE001 - whoever is told must not keep the server from its restart
                        LOG.exception("no answer: telling of the restart failed")
                if not stop_server(record["pid"], record["started"]):
                    LOG.warning("no answer: the translation program TASlation started would not stop (%.1f s)",
                                time.monotonic() - now)
                    return False
                _drop(path)
                _keep_setup(self.url, None)
                stopped = time.monotonic() - now
                if cancel is not None and cancel.is_set():
                    LOG.warning("no answer: the translation program TASlation started was stopped (%.1f s); the "
                                "request was cancelled before it was started again", stopped)
                    return False
                users = [u for u in record["users"] if _alive(u)]
                failed = _launch(self.url, None, path, self.own, self.settings, users)
            if failed is not None:
                LOG.warning("no answer: the translation program TASlation started was stopped (%.1f s) and could not "
                            "be started again (%s)", stopped, failed.code)
                return False
            failed = _wait_answer(self.url, cancel)
            LOG.warning("no answer: the translation program TASlation started was stopped (%.1f s) and started again; "
                        "%s after %.1f s", stopped, "it answers" if failed is None else failed.code,
                        time.monotonic() - now)
            return failed is None


@contextlib.contextmanager
def held(url: str, state_dir: Path | str | None, own: Iterable[str] = (),
         settings: Any = None) -> Iterator[Message | None]:
    """Ollama at *url* made to answer for a block (`OllamaStarter.start`, with *settings*), and what this process
    started or used of it given up at the block's end (`finish_all`). What stands in the way, None when it answers."""
    try:
        yield OllamaStarter(url, state_dir=state_dir, own=own, settings=settings).start()
    finally:
        finish_all()
