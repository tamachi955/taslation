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
TASlation's process by Windows. Its environment is TASlation's (what the reader set for Ollama comes with it), with two
variables added when TASlation's lacks them (`server_env`; a value that is set anywhere is never changed):

* ``LLAMA_ARG_CACHE_RAM``, how many MiB of RAM llama.cpp's server, which runs Ollama's model, may keep as a cache of
  earlier prompts (8 GiB unless told): the value Windows keeps for the user or the computer (as a process started now
  would get it: an older install.ps1 set it for the user), else 0;
* ``OLLAMA_KV_CACHE_TYPE``, the KV cache's precision: the value Windows keeps, else ``q8_0`` on an NVIDIA GPU of 6 GB
  or less (`small_gpu`, as install.ps1 decides from the same number, NVML's, which nvidia-smi gives it), where the
  model's whole context fits in video memory only so (about 4 times the speed); nothing on a larger GPU or none.

Only the address Ollama serves by default is started (`startable`): an Ollama set up elsewhere is the setup of whoever
set it up, and starting one here would not answer there.

Owning: the server TASlation started is written down in ``<state folder>/ollama-started.json`` (`RECORD_FILE`; plain,
no text of a book) - its process number, its program and when it started (pids are reused: the three together name
it), the address, and the TASlation processes that use it (the window and a ``taslation`` command at once), each by
its number and start time. A process that starts Ollama, or finds the recorded server running, puts itself into the
record (a "claim" of this process); one whose look finds an Ollama that is not recorded owns nothing. The record is
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
uninstaller ends them, for at most `KILL_WAIT_S` more. One still running after that is left, and the record kept for
the next end. Nothing here ever waits without a bound.

Messages of `OllamaStarter.start` (None when Ollama answers):

* ``health.ollama_not_installed``: none was found;
* ``health.ollama_no_answer``: one was started and did not answer within `START_WAIT_S`;
* ``health.ollama_down`` {url}: nothing was started, or the wait was cancelled (the banner's line; no popup).

`OllamaStarter` is what the window and the commands hold: at most one try every `RETRY_GAP_S`, so that requests that
find Ollama gone (`OllamaTranslator.revive`) never start it in a loop. Everything here waits, and runs in a worker
thread, never on Tk's."""

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
POPUP_CODES = frozenset({"health.ollama_not_installed", "health.ollama_no_answer"})  # what the window's popup says
# llama.cpp's server keeps up to 8 GiB of earlier prompts in RAM unless this says otherwise (MiB; 0: no cache). In a
# whole-book run on the GPU the translator's server peaked at 9.8 GB working set with it and at 1.7 GB without, and
# translated at the same speed; without the GPU it peaked at 7.4 GB and 4.0 GB, and translated 8 % faster with it
# (docs/OFFLINE_VERIFICATION.md, "Ollama's prompt cache in RAM").
CACHE_RAM_VAR = "LLAMA_ARG_CACHE_RAM"
CACHE_RAM_OFF = "0"  # what an Ollama TASlation starts gets when the variable is set nowhere
# A GPU of 6 GB or less holds the translator's whole context only with a quantized KV cache (install.ps1's rule, by the
# same number: the video memory NVIDIA's driver reports, in MiB).
KV_CACHE_VAR = "OLLAMA_KV_CACHE_TYPE"
KV_CACHE_SMALL_GPU = "q8_0"
SMALL_GPU_MIB = 6144
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


def server_env() -> dict[str, str] | None:
    """The environment of the Ollama TASlation starts: TASlation's own (None: inherited) when it has both variables of
    the module's docstring; else TASlation's with each one it lacks as this user or the computer has it set (TASlation
    was started before it was), else `CACHE_RAM_OFF`, and `KV_CACHE_SMALL_GPU` on a small GPU (`small_gpu`)."""
    added: dict[str, str] = {}
    if CACHE_RAM_VAR not in os.environ:
        added[CACHE_RAM_VAR] = stored_value(CACHE_RAM_VAR) or CACHE_RAM_OFF
    if KV_CACHE_VAR not in os.environ:
        kept = stored_value(KV_CACHE_VAR)
        if kept:
            added[KV_CACHE_VAR] = kept
        elif small_gpu():
            added[KV_CACHE_VAR] = KV_CACHE_SMALL_GPU
    return {**os.environ, **added} if added else None


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
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
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


def _info_of(handle: Any) -> ProcessInfo | None:
    import ctypes
    from ctypes import wintypes

    k = _kernel32()
    if k.WaitForSingleObject(handle, 0) != _WAIT_TIMEOUT:
        return None  # it has ended (its handle is signalled)
    times = [wintypes.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        return None
    size = wintypes.DWORD(32768)
    name = ctypes.create_unicode_buffer(size.value)
    if not k.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
        return None
    return ProcessInfo(name.value, (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)


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
    """The server *pid* (the process that started at *started*) stopped as the module's docstring says: asked, then
    terminated with its descendants; whether it is gone. At most `HELPER_TIMEOUT_S` + `STOP_WAIT_S` + `KILL_WAIT_S`."""
    children = descendants(pid, started)
    if ask_to_stop(pid) and wait_exit(pid, started, STOP_WAIT_S):
        for child, child_started in children:  # (Ollama ends them itself; one left behind goes too)
            terminate(child, child_started)
        return True
    for child, child_started in dict.fromkeys(descendants(pid, started) + children):
        terminate(child, child_started)
    terminate(pid, started)
    return wait_exit(pid, started, KILL_WAIT_S)


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
    """This process among the users of the recorded server (written when it was not), and its claim on it."""
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


STOPPED = "The translation program TASlation started was stopped."
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
    a bound."""
    with _claims_lock:
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
             path: Path | None, own: Iterable[str]) -> Message | None:
    """Ollama, found not to answer at *url*, started (or the server TASlation started and recorded at *path* adopted)
    and waited for (see the module's docstring)."""
    down = Message("health.ollama_down", url=url)
    if not startable(url) or (cancel is not None and cancel.is_set()):
        return down
    with _Lock(path) if path is not None else contextlib.nullcontext():
        record = _valid(path, url) if path is not None else None
        if record is not None:
            _use(path, record, url, own)  # a server TASlation started (by another process, or before a crash)
        elif health.ollama_running(url):
            return None  # one came up meanwhile, not TASlation's
        else:
            command = find_ollama()
            if command is None:
                return Message("health.ollama_not_installed")
            if on_starting is not None:
                on_starting()
            try:
                proc = launch(command, server_env())
            except OSError:
                return Message("health.ollama_no_answer")
            info = process_info(proc.pid)
            if path is not None and info is not None:
                record = {"what": "the Ollama server TASlation started; it stops it when the last TASlation that uses "
                                  "it ends", "pid": proc.pid, "exe": info.exe, "started": info.started, "url": url,
                          "users": []}
                _use(path, record, url, own)
    pause = cancel if cancel is not None else threading.Event()  # never set, without a caller's event
    deadline = time.monotonic() + START_WAIT_S
    while not health.ollama_running(url):
        if time.monotonic() >= deadline:
            return Message("health.ollama_no_answer")
        if pause.wait(POLL_S):
            return down
    return None


class OllamaStarter:
    """Ollama at one address made to answer (see the module's docstring), with at most one try every `RETRY_GAP_S` (a
    window's or a command's whole life: the start, then the requests that find Ollama gone). *on_starting* says so
    where the reader looks. *state_dir*: where the server TASlation starts is recorded (`RECORD_FILE`), which makes it
    TASlation's to stop at the end (`finish_all`); None records nothing (a server started then is never stopped).
    *own*: the names of models that count as TASlation's own at the end besides `MODELS` (`own_models`)."""

    def __init__(self, url: str, on_starting: Callable[[], None] | None = None, state_dir: Path | str | None = None,
                 own: Iterable[str] = ()):
        self.url = url
        self.on_starting = on_starting
        self.record = record_path(state_dir)
        self.own = tuple(own)
        self._last: float | None = None  # when the last try began
        self._lock = threading.Lock()

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
        return _started(self.url, cancel, self.on_starting, self.record, self.own)

    def _join(self) -> None:
        """The Ollama that answers, when it is the server TASlation started (recorded), used by this process too, so
        that another TASlation's end leaves it running while this one needs it."""
        path = self.record
        if path is None or not startable(self.url) or not path.is_file():
            return
        with _Lock(path):
            record = _valid(path, self.url)
            if record is not None:
                _use(path, record, self.url, self.own)

    def revive(self, cancel: threading.Event | None = None) -> bool:
        """Whether Ollama answers now (`OllamaTranslator.revive`)."""
        return self.start(cancel) is None


@contextlib.contextmanager
def held(url: str, state_dir: Path | str | None, own: Iterable[str] = ()) -> Iterator[Message | None]:
    """Ollama at *url* made to answer for a block (`OllamaStarter.start`), and what this process started or used of it
    given up at the block's end (`finish_all`). What stands in the way, None when it answers."""
    try:
        yield OllamaStarter(url, state_dir=state_dir, own=own).start()
    finally:
        finish_all()
