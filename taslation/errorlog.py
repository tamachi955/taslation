"""TASlation's error log, and the details a reader can copy for a report.

``<state dir>/log.txt`` (`LOG_FILE`, rotating at `MAX_BYTES` with `BACKUPS` older files) holds what went wrong and on
what: at the start the environment (`environment`: TASlation's version and date, Python, Tk, Windows; torch and its
GPU once torch is loaded) and the settings that differ from the defaults (`settings_lines`; paths only as "set"); then
warnings and exceptions with their tracebacks, and once after the first error the state of torch and Ollama. `setup`
makes it for the window (`taslation gui`), with hooks for what nobody caught (`install_hooks`: the main thread, the
other threads, Tk's callbacks); under pytest it writes nothing unless asked to.

It never holds what is read. Every line passes `scrub`: the state, models and program folders and the home folder by
name, with nothing after them but a program file (``<state dir>\\…``), every other path as ``<path>``, a quoted
string as ``'…'`` unless the code of the traceback names it (a key such as 'text'), any run of characters beyond ASCII
(Japanese text, a title) as ``…``, a line cut at `MAX_LINE`; tracebacks name their files within the program
(`program_name`) and show the program's code, never a value. So no page text, OCR text or translation, no book or
window title, and no path under the reader's profile but the state folder's (by name alone) reaches the file.

`details_text` is what Copy details (Help > About TASlation, an error box: `ui.copy_details`; a failed start:
`cli._complain`) gives: the environment, Ollama's version, the settings and the last error, through the same `scrub`.
"""

from __future__ import annotations

import builtins
import getpass
import importlib.metadata
import json
import logging
import logging.handlers
import os
import platform
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

LOG_FILE = "log.txt"
MAX_BYTES = 256 * 1024  # a log file this large starts the next (the oldest of BACKUPS + 1 goes)
BACKUPS = 3
MAX_LINE = 300  # characters of a line kept (a message, an exception's text)
OLLAMA_TIMEOUT_S = 1.0  # how long Copy details waits for Ollama's version
PERSONAL_SETTINGS = frozenset({"state_dir", "models_dir", "font_path"})  # paths: named "set", never by value
ELLIPSIS = "\u2026"
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

LOG = logging.getLogger("taslation")

_PATH_END = r"""[^'"\n\r,;()<>|*?]*"""  # a path goes on to a quote, a comma, a bracket or the end of the line
_SEP = r"[\\/]+"
_GENERIC_PATHS = (
    re.compile(r"(?i)file:/{2,3}" + _PATH_END),
    re.compile(r"(?i)(?<![A-Za-z0-9_<])(?:\\\\\?\\)?[a-z]:[\\/]" + _PATH_END),  # C:\..., C:/..., \\?\C:\...
    re.compile(r"(?<![A-Za-z0-9_])\\\\[^\\/\s'\"]+[\\/]" + _PATH_END),  # \\server\share\...
    re.compile(r"(?<![A-Za-z0-9_.<>])/(?:home|Users|mnt|media|tmp|var|private|Volumes|root)/" + _PATH_END),
    re.compile(r"(?<![A-Za-z0-9_])~[\\/]" + _PATH_END),
)
_PROGRAM_FILE = re.compile(r"[\\/]+[A-Za-z0-9_.\\/-]*\.pyc?")
_QUOTED = re.compile(r"""(?<![A-Za-z0-9])(?P<q>['"])(?P<body>(?:\\.|(?!(?P=q))[^\n])*)(?P=q)(?![A-Za-z0-9])""")
_PLACEHOLDER_BODY = re.compile(r"<[a-z ]+>[A-Za-z0-9_.\\/\u2026-]*")
_NON_ASCII = re.compile(r"[^\x00-\x7f]+")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_FRAME = re.compile(r'^  File "(?P<file>[^"]*)", line ')
_ALLOWED_BASE = frozenset(dir(builtins)) | {  # Python's own names, as its messages quote them
    "NoneType", "function", "method", "module", "builtin_function_or_method", "generator", "coroutine", "utf-8",
    "utf8", "ascii", "cpu", "cuda", "gpu", "rb", "wb", "r", "w"}

_lock = threading.RLock()
_roots: list[tuple[re.Pattern[str], str, bool]] = []  # (folder, its label, a program file after it is kept)
_names: list[tuple[re.Pattern[str], str]] = []  # the reader's login and the computer's name
_last_error: tuple[float, str] | None = None
_settings: Any = None  # the session's settings, for details_text
_installed: list[logging.Handler] = []
_hooks: dict[str, Any] = {}
_state_told = False


# ------------------------------------------------------------------ scrubbing
def _root_pattern(folder: str) -> re.Pattern[str] | None:
    parts = [re.escape(p) for p in re.split(r"[\\/]+", str(folder).strip().rstrip("\\/")) if p]
    if not parts:
        return None
    lead = _SEP if str(folder).startswith(("/", "\\")) else ""
    return re.compile(r"(?i)(?<![A-Za-z0-9_.])" + lead + _SEP.join(parts) + r"(?P<rest>(?:" + _SEP + _PATH_END
                      + r")?)(?![A-Za-z0-9_])")


def set_roots(state_dir: Path | str | None = None, models_dir: Path | str | None = None) -> None:
    """The folders `scrub` names (the longest first, so that the state folder wins over the home folder that holds
    it): the state folder and the models folder (nothing after them is kept), the program and Python (a program file
    after them is kept: ``<program>/taslation/ui/jobs.py``), the home folder."""
    from .config import REPO_DIR

    folders: list[tuple[str, str, bool]] = []
    for folder, label, keep in ((state_dir, "<state dir>", False), (models_dir, "<models>", False),
                                (REPO_DIR, "<program>", True), (sys.prefix, "<python>", True),
                                (sys.base_prefix, "<python>", True), (str(Path.home()), "<home>", False)):
        if folder:
            folders.append((str(Path(folder)), label, keep))
    folders.sort(key=lambda f: len(f[0]), reverse=True)
    roots = [(p, label, keep) for folder, label, keep in folders if (p := _root_pattern(folder)) is not None]
    names = []
    for name, label in ((_login(), "<user>"), (platform.node(), "<computer>")):
        if name and len(name) >= 3:
            names.append((re.compile(r"(?i)(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"), label))
    with _lock:
        _roots[:] = roots
        _names[:] = names


def _login() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no login name to hide
        return ""


def _after_root(rest: str, keep: bool) -> str:
    if not rest:
        return ""
    if keep and _PROGRAM_FILE.fullmatch(rest):
        return rest.replace("\\\\", "\\")
    return "\\" + ELLIPSIS


def _harmless(body: str, words: frozenset[str] | set[str]) -> bool:
    if not body or body == ELLIPSIS or body in words or body.replace(".", "").isdigit():
        return True
    return bool(_PLACEHOLDER_BODY.fullmatch(body))


def scrub(text: Any, allowed: Iterable[str] = ()) -> str:
    """*text* with nothing of the reader's in it: the folders `set_roots` knows by name (``<state dir>\\…``), other
    paths as ``<path>``, quoted strings as ``'…'`` unless they are in *allowed* (the words of the traceback's code) or
    Python's own names, characters beyond ASCII as ``…``, the reader's login and the computer's name, each line cut at
    `MAX_LINE`."""
    out = str(text)
    if not _roots:
        set_roots()
    with _lock:
        roots, names = list(_roots), list(_names)
    for pattern, label, keep in roots:
        out = pattern.sub(lambda m, label=label, keep=keep: label + _after_root(m.group("rest"), keep), out)
    for pattern in _GENERIC_PATHS:
        out = pattern.sub("<path>", out)
    words = _ALLOWED_BASE | set(allowed)
    out = _QUOTED.sub(lambda m: m.group(0) if _harmless(m.group("body"), words)
                      else m.group("q") + ELLIPSIS + m.group("q"), out)
    out = _NON_ASCII.sub(ELLIPSIS, out)
    for pattern, label in names:
        out = pattern.sub(label, out)
    return "\n".join(line if len(line) <= MAX_LINE else line[:MAX_LINE] + ELLIPSIS for line in out.split("\n"))


def program_name(filename: str) -> str:
    """A traceback's file within the program: ``taslation/ui/jobs.py``, ``site-packages/torch/...``, Python's own
    ``<python>/lib/...``; any other file by its name alone when that is plain ASCII, else ``<path>``."""
    if filename.startswith("<") and filename.endswith(">"):
        return filename  # <frozen ...>, <string>
    from .config import REPO_DIR

    path = filename.replace("\\", "/")
    low = path.lower()
    for marker in ("/site-packages/", "/dist-packages/"):
        at = low.rfind(marker)
        if at >= 0:
            return path[at + 1:]
    for root, label in ((str(REPO_DIR), ""), (sys.base_prefix, "<python>/"), (sys.prefix, "<python>/")):
        base = root.replace("\\", "/").rstrip("/").lower() + "/"
        if low.startswith(base):
            return label + path[len(base):]
    at = low.rfind("/taslation/")
    if at >= 0:
        return path[at + 1:]
    name = path.rsplit("/", 1)[-1]
    return name if re.fullmatch(r"[A-Za-z0-9_.-]+", name) else "<path>"


def safe_traceback(error: BaseException) -> str:
    """*error*'s traceback (its causes too) with the files named within the program (`program_name`) and the code
    lines as they are (the program's own); the exceptions' texts through `scrub`, allowing the words of that code."""
    try:
        chunks = list(traceback.TracebackException.from_exception(error).format())
    except Exception:  # noqa: BLE001 - a traceback that cannot be formatted: the type alone
        return f"{type(error).__name__}"
    words: set[str] = set()
    frames: dict[int, str] = {}
    for i, chunk in enumerate(chunks):
        m = _FRAME.match(chunk)
        if m:
            chunk = chunk.replace(m.group("file"), program_name(m.group("file")), 1)
            frames[i] = _NON_ASCII.sub(ELLIPSIS, chunk)
            for word in _WORD.findall(chunk.split("\n", 1)[-1]):
                words.add(word)
                words.update(word.split("."))
    return "".join(frames[i] if i in frames else scrub(chunk, words) for i, chunk in enumerate(chunks)).rstrip("\n")


class PrivacyFormatter(logging.Formatter):
    """A log record as one line - time, level, logger, the message through `scrub` - and its traceback
    (`safe_traceback`), indented."""

    def __init__(self) -> None:
        super().__init__(FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - arguments that do not fit the message: the message alone
            message = str(record.msg)
        line = f"{self.formatTime(record)} {record.levelname} {record.name}: {scrub(message)}"
        error = record.exc_info[1] if record.exc_info else None
        if error is not None:
            line += "\n" + "\n".join("    " + part for part in safe_traceback(error).splitlines())
        return line


# ------------------------------------------------------------------ what TASlation runs on
def program_version() -> str:
    from . import __version__

    try:
        return importlib.metadata.version("taslation")
    except importlib.metadata.PackageNotFoundError:
        return __version__


def release_date(package: Path | None = None) -> str:
    """The date of this copy of TASlation: the newest of its program files (``taslation/**/*.py``), as YYYY-MM-DD;
    "" when there are none. (A release's files keep the date they were made; the install prints the same.)"""
    folder = Path(package) if package is not None else Path(__file__).resolve().parent
    newest = 0.0
    for path in folder.rglob("*.py"):
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
    return time.strftime("%Y-%m-%d", time.localtime(newest)) if newest else ""


def torch_line() -> str:
    """torch and its GPU, when torch is loaded (nothing is loaded or started for it: CUDA is asked for its device
    only once torch has started it)."""
    torch = sys.modules.get("torch")
    if torch is None:
        return "torch: not loaded"
    version = getattr(torch, "__version__", "?")
    try:
        cuda = torch.cuda
        if cuda.is_initialized():
            return f"torch {version}, CUDA {torch.version.cuda}: {cuda.get_device_name(0)}"
        return f"torch {version}, CUDA {'available' if cuda.is_available() else 'not available'}"
    except Exception as e:  # noqa: BLE001 - a broken CUDA: said, not raised
        return f"torch {version}, CUDA: {type(e).__name__}"


def ollama_line(port: int | None = None) -> str:
    """Ollama's version from its own port on this computer (``/api/version``, `OLLAMA_TIMEOUT_S`), or that it does
    not answer. No proxy: the request never leaves the computer."""
    import urllib.request

    port = int(port or getattr(_settings, "ollama_port", 11434) or 11434)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/version", timeout=OLLAMA_TIMEOUT_S) as reply:
            version = json.loads(reply.read(4096).decode("utf-8", "replace")).get("version", "?")
        return f"Ollama {version}"
    except Exception:  # noqa: BLE001 - down, blocked or slow: said as such
        return f"Ollama: not answering on localhost:{port}"


def tk_version() -> str:
    try:
        import tkinter

        return f"Tk {tkinter.TkVersion}"
    except Exception:  # noqa: BLE001 - a Python without Tk
        return "Tk: none"


def environment(ollama: bool = False, port: int | None = None) -> list[str]:
    """What TASlation runs on, a line each: its version and date, Python, Tk, the system, torch (`torch_line`) and,
    with *ollama*, Ollama's version (`ollama_line`)."""
    date = release_date()
    lines = [f"TASlation {program_version()}" + (f" (dated {date})" if date else ""),
             f"Python {platform.python_version()} ({platform.architecture()[0]}, {platform.python_implementation()})",
             tk_version(),
             f"{platform.system()} {platform.release()} ({platform.version()}, {platform.machine()})",
             torch_line()]
    if ollama:
        lines.append(ollama_line(port))
    return [scrub(line) for line in lines]


def settings_lines(settings: Any) -> list[str]:
    """The settings that differ from the defaults, ``name = value``; the paths (`PERSONAL_SETTINGS`) only as set."""
    try:
        changed = settings.changed_from_defaults()
    except Exception:  # noqa: BLE001 - no settings to tell
        return []
    out = []
    for name, value in changed.items():
        if name in PERSONAL_SETTINGS:
            out.append(f"{name} = (set)")
        else:
            out.append(scrub(f"{name} = {value}"))  # (unquoted: a value is no text of the book)
    return out


def last_error() -> tuple[float, str] | None:
    """The last error of this session as the log has it (its time, its text), or None."""
    with _lock:
        return _last_error


def details_text(settings: Any = None, port: int | None = None, ollama: bool = True) -> str:
    """What Copy details gives, for a report: the environment, Ollama, the window's language, the target language,
    the translator setting and the other settings changed, the settings file's place by folder, and the last error -
    no text, title or path of the reader's."""
    settings = settings if settings is not None else _settings
    lines = ["TASlation details for a report (no text, titles or file names from your books):"]
    lines += environment(ollama=ollama, port=port or getattr(settings, "ollama_port", None))
    if settings is not None:
        lines.append(scrub(f"Window language: {getattr(settings, 'ui_language', '') or 'as chosen at the first start'}; "
                           f"translation into {getattr(settings, 'target_language', '?')}; "
                           f"translator: {getattr(settings, 'ollama_model', '?')}"))
        config = getattr(settings, "config_path", None)
        lines.append("Settings file: " + (scrub(str(Path(config).parent)) + " (taslation.toml)" if config else "none"))
        changed = settings_lines(settings)
        lines.append("Settings changed from the defaults: " + (", ".join(changed) if changed else "none"))
        ignored = tuple(getattr(settings, "ignored_keys", ()) or ())
        if ignored:
            lines.append(scrub("Unknown settings left out: " + ", ".join(ignored)))
    last = last_error()
    if last is None:
        lines.append("Last error: none in this session")
    else:
        lines.append(f"Last error ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last[0]))}):")
        lines.append(last[1])
    return "\n".join(lines)


# ------------------------------------------------------------------ the log
class _LastError(logging.Handler):
    """Keeps the last error (as `PrivacyFormatter` writes it) for `details_text`; after the first, the state of torch
    and Ollama goes into the log once (from a thread of its own: Ollama is asked over the network)."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.setFormatter(PrivacyFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        global _last_error, _state_told
        try:
            text = self.format(record)
        except Exception:  # noqa: BLE001 - the log never fails the program
            return
        with _lock:
            _last_error = (record.created, text)
            tell = not _state_told
            _state_told = True
        if tell and any(isinstance(h, logging.handlers.RotatingFileHandler) for h in _installed):
            thread = threading.Thread(target=_log_state, name="taslation-log-state", daemon=True)
            _hooks["state"] = thread
            thread.start()


def _log_state() -> None:
    LOG.info("state after the first error: %s; %s", torch_line(), ollama_line())


def log_path(state_dir: Path | str) -> Path:
    return Path(state_dir) / LOG_FILE


def setup(settings: Any, force: bool = False) -> Path | None:
    """The log for this session: the last error kept in memory, and ``<state dir>/log.txt`` (rotating) with the
    environment and the changed settings at the top; the hooks for what nobody caught (`install_hooks`). Under
    pytest (``PYTEST_CURRENT_TEST``) no file is written unless *force*. The file, or None without one (a state folder
    that cannot be written: the window goes on without a log)."""
    global _settings, _state_told
    _settings = settings
    set_roots(getattr(settings, "state_dir", None), getattr(settings, "models_dir", None))
    if "PYTEST_CURRENT_TEST" in os.environ and not force:
        return None
    root = logging.getLogger()
    if not any(isinstance(h, _LastError) for h in root.handlers):
        memory = _LastError()
        root.addHandler(memory)
        _installed.append(memory)
    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)
    if LOG.level == logging.NOTSET or LOG.level > logging.INFO:
        LOG.setLevel(logging.INFO)
    install_hooks()
    path = log_path(settings.state_dir)
    if any(isinstance(h, logging.handlers.RotatingFileHandler) and Path(h.baseFilename) == path for h in root.handlers):
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS,
                                                       encoding="utf-8", delay=True)
    except OSError:
        return None
    handler.setLevel(logging.INFO)
    handler.setFormatter(PrivacyFormatter())
    root.addHandler(handler)
    _installed.append(handler)
    logging.captureWarnings(True)
    with _lock:
        _state_told = False
    LOG.info("started: %s", "; ".join(environment()))
    changed = settings_lines(settings)
    LOG.info("settings changed from the defaults: %s", ", ".join(changed) if changed else "none")
    return path


def install_hooks() -> None:
    """What nobody caught goes into the log too: an exception of the main thread (`sys.excepthook`), of another
    thread (`threading.excepthook`), of a Tk callback (`tkinter.Tk.report_callback_exception`); each is then handled
    as before. Once."""
    if "sys" in _hooks:
        return
    _hooks["sys"] = sys.excepthook
    _hooks["thread"] = threading.excepthook

    def sys_hook(kind, value, tb):  # type: ignore[no-untyped-def]
        if not issubclass(kind, KeyboardInterrupt):
            LOG.critical("an error nobody caught", exc_info=(kind, value, tb))
        _hooks["sys"](kind, value, tb)

    def thread_hook(args):  # type: ignore[no-untyped-def]
        if args.exc_type is not SystemExit:
            LOG.error("an error nobody caught in a thread", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        _hooks["thread"](args)

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook
    try:
        import tkinter
    except ImportError:
        return
    _hooks["tk"] = tkinter.Tk.report_callback_exception

    def tk_hook(self, kind, value, tb):  # type: ignore[no-untyped-def]
        LOG.error("an error in a window callback", exc_info=(kind, value, tb))
        if sys.stderr is not None:
            _hooks["tk"](self, kind, value, tb)

    tkinter.Tk.report_callback_exception = tk_hook  # type: ignore[method-assign]


def shutdown() -> None:
    """The log's handlers and hooks taken away again (the tests; a second window in one process)."""
    global _last_error, _settings, _state_told
    thread = _hooks.pop("state", None)
    if thread is not None:
        thread.join(2 * OLLAMA_TIMEOUT_S)  # its line written before the file closes
    root = logging.getLogger()
    for handler in _installed:
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
    _installed.clear()
    if "sys" in _hooks:
        sys.excepthook = _hooks.pop("sys")
    if "thread" in _hooks:
        threading.excepthook = _hooks.pop("thread")
    if "tk" in _hooks:
        import tkinter

        tkinter.Tk.report_callback_exception = _hooks.pop("tk")  # type: ignore[method-assign]
    logging.captureWarnings(False)
    with _lock:
        _last_error, _settings, _state_told = None, None, False


# ------------------------------------------------------------------ without a window
def copy_to_clipboard(text: str) -> bool:
    """*text* on the Windows clipboard without Tk (the box of a failed start); whether it is there."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    data = text.encode("utf-16-le") + b"\0\0"
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT; the clipboard owns it once set
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()
