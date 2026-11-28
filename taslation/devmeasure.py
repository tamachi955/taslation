"""Developer measuring: a session kept whole on this computer, for the owner's own development on their own computer.

This mode exists only in a source checkout (a ``.git`` beside the package: `available`). An installed copy - the
release's ZIP, which has none - has no such mode at all: `Session` refuses to start there (`Refused`), the window offers
no entry for it (`ui.measure`), and nothing starts it by itself: it is off at every start and never remembered. It is
the owner's exception, for this mode alone, to the rules "no page image on disk" and "no page text on disk".

While it is on (`Session`), under ``<state dir>/dev-measure/<the session's start>/`` (`FOLDER`; the state folder is
outside the repository; a ``README.txt`` there says what it holds and that it is private):

* for each page read (every `Pipeline.process`, its number ``n`` the analysis log's): ``pNNNN-frame.png`` (the frame as
  captured), ``pNNNN-erased.png`` (erased, before its lettering), ``pNNNN-lettered.png`` (the whole lettered page: the
  frame with every patch composed in, as it is seen over the viewer) and ``pNNNN.json`` (every region: its boxes, kind,
  tier, what each reader read and charspot's confidence, the settled reading, the translation, the flags, the helpers
  that acted on it, the fit taken; the page's analysis line; the requests made for it);
* each later finished state of a page the person changed or had translated again (`edited`): ``pNNNN-sK-lettered.png``
  and ``pNNNN-sK.json``, K from 1;
* ``requests.jsonl``: each request to the translator - the prompt's parts, the prompt and the raw answer;
* ``analysis.jsonl``: the session's lines of the analysis log (numbers only, as ever); ``log.txt``: the session's lines
  of the program's log (as log.txt writes them); ``input.jsonl``: what the person asked for and when (`InputWatch`).

The input record's limits are not negotiable: keys are recorded only while the viewer's window or one of TASlation's
is the foreground window, and only their KIND (`KEY_NAMES`: left, right, up, down, space, page up, page down, home,
end, enter, escape, Insert, Delete; every other key "other", with nothing of which it was) - never a character, never
while another program is in front, so nothing typed elsewhere (a password, a message) can reach the file; of the
mouse, presses on TASlation's lettering and side panes with their place and button, and the wheel's ticks over the
viewer. The keys and the wheel are seen through Windows' low-level hooks (``WH_KEYBOARD_LL``, ``WH_MOUSE_LL``),
installed on a thread of their own only while the mode is on and the viewer or TASlation is in front (looked at every
`WATCH_MS`), removed otherwise; each event is looked at again against the window in front when it comes. What they
cost: every key and mouse event of the whole desktop passes through the hook's callback while it is installed - a few
microseconds of Python that looks at the window in front, compares and appends, then `CallNextHookEx` -, plus the wait
for Python's interpreter lock where another thread of TASlation's holds it (Python hands it over every 5 ms), and
nothing at all while it is not installed - from `WATCH_MS` at the most after another program came in front; an event
in between is looked at against the window in front and dropped.

With the mode on every page is read, translated, erased and lettered afresh: the normal cache is neither read nor
written (`Pipeline.measuring`; the window gives the pipeline a cache of the session's own, under ``_stores`` in its
folder and deleted when the mode ends, so that a change the person makes is kept nowhere else), no line is reused from
another, nothing is read behind the reader (the backlog's work would be thrown away: `backlog.tracking_for`), and the
series sheet and the book's marks (its settings, areas, regions added or left out) are read as ever and never written
(`ReadOnly`): a change made to them while measuring lasts until the mode ends.

Nothing of the folder is read by the program afterwards, nothing of it is sent anywhere (the offline guard holds as
ever), and an export of the books never includes it (`backup.NEVER_EXPORTED`). The tools never open the kept pictures or
texts of the owner's sessions: `tools/analysis_summary.py` reads the numbers (``analysis.jsonl``, ``input.jsonl``)."""

from __future__ import annotations

import json
import logging
import queue
import shutil
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

from . import analysis

LOG = logging.getLogger(__name__)
FOLDER = "dev-measure"
README_NAME = "README.txt"
STORES = "_stores"  # the session's own cache and page information (deleted when the mode ends)
WATCH_MS = 100  # the window in front looked at so often, to install or remove the hooks
PNG_LEVEL = 1  # zlib level of the pictures (fast)

README = """TASlation - developer measuring (private)

This folder holds what TASlation's developer measuring mode kept, one folder per session (named by its start).
It exists only on this computer, for the developer's own measurements; nothing of it is sent anywhere, the
program never reads it again, and an export of the books leaves it out.

Each session folder can hold, for each page read: the frame as captured (pNNNN-frame.png), the page erased
(pNNNN-erased.png), the lettered page (pNNNN-lettered.png) and its regions with their readings and translations
(pNNNN.json); the later states of a page that was changed (pNNNN-sK-*); the requests made to the translator with
their answers (requests.jsonl); the session's analysis lines, numbers only (analysis.jsonl); a copy of the program's
log lines (log.txt); and the kind of each key pressed and the presses and wheel ticks while the viewer or TASlation
was in front (input.jsonl: the kind of key only, never a character).

These files hold pages of your books and their text: keep them private. Delete a session's folder, or this whole
folder, at any time (Menu > Developer measuring > Delete all sessions..., or tools/dev_measure.py).
"""

# the keys recorded by name; every other key is "other" (`key_kind`)
KEY_NAMES = {0x25: "left", 0x27: "right", 0x26: "up", 0x28: "down", 0x20: "space", 0x21: "page_up", 0x22: "page_down",
             0x24: "home", 0x23: "end", 0x0D: "enter", 0x1B: "escape", 0x2D: "insert", 0x2E: "delete"}
TURN_KEYS = frozenset({"left", "right", "up", "down", "space", "page_up", "page_down", "home", "end"})
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_MOUSEWHEEL = 0x0201, 0x0204, 0x0207, 0x020A
BUTTONS = {WM_LBUTTONDOWN: "left", WM_RBUTTONDOWN: "right", WM_MBUTTONDOWN: "middle"}


class Refused(RuntimeError):
    """Developer measuring asked for where it does not exist (an installed copy)."""


def available(root: Path | str | None = None) -> bool:
    """Whether this copy offers developer measuring: a source checkout only (`analysis.source_checkout`)."""
    return analysis.source_checkout(root)


def key_kind(vk: int) -> str:
    """What is recorded of the key *vk*: its name among `KEY_NAMES`, else "other" (nothing of which key it was)."""
    return KEY_NAMES.get(int(vk), "other")


def base_folder(state_dir: Path | str) -> Path:
    return Path(state_dir) / FOLDER


def sessions(state_dir: Path | str) -> list[Path]:
    """The kept sessions' folders, oldest first."""
    base = base_folder(state_dir)
    try:
        return sorted(p for p in base.iterdir() if p.is_dir())
    except OSError:
        return []


def delete_sessions(state_dir: Path | str, names: list[str] | None = None, keep: Path | None = None) -> int:
    """The sessions named *names* (their folders' names; None: all) deleted, but *keep* (the one under way);
    how many."""
    gone = 0
    for folder in sessions(state_dir):
        if (names is not None and folder.name not in names) or (keep is not None and folder == keep):
            continue
        shutil.rmtree(folder, ignore_errors=True)
        gone += not folder.exists()
    return gone


# ------------------------------------------------------------ the series sheet and the book's marks read, never written
class ReadOnly:
    """A store (`annotations.GlossaryStore`: the series sheets; `annotations.AnnotationStore`: the book's marks and its
    series' defaults) whose files are read as ever and never written while measuring: what it opens is used as ever in
    memory, and its save does nothing (said once in the log, by *what*), nor does a delete. A book's marks keep their
    series' defaults read only too (``series_store``, ``inherited``)."""

    def __init__(self, store: Any, what: str):
        self.store = store
        self.what = what
        self._said = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.store, name)

    def open(self, *args: Any, **kwargs: Any) -> Any:
        got = self.store.open(*args, **kwargs)
        self.hold(got)
        return got

    def hold(self, got: Any) -> None:
        """*got* (a sheet, a book's marks, a series' defaults) saved nowhere from now on."""
        try:
            got.save = self._not_saved  # type: ignore[method-assign]
        except AttributeError:
            pass
        inner = getattr(got, "series_store", None)
        if inner is not None and not isinstance(inner, ReadOnly):
            try:
                got.series_store = ReadOnly(inner, self.what)
            except AttributeError:
                pass
        inherited = getattr(got, "inherited", None)
        if inherited is not None:
            try:
                inherited.save = self._not_saved
            except AttributeError:
                pass

    def delete(self, *_args: Any, **_kwargs: Any) -> bool:
        self._not_saved()
        return False

    def _not_saved(self, *_args: Any, **_kwargs: Any) -> None:
        if not self._said:
            self._said = True
            LOG.info("developer measuring: the %s is read only (not saved)", self.what)


# ------------------------------------------------------------------ the window in front (Windows)
_USER32: Any = None


def _user32() -> Any:
    """user32 of this module's own (its functions' signatures set here, not on ``ctypes.windll``'s shared ones)."""
    global _USER32
    if _USER32 is None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        _USER32 = user32
    return _USER32


def foreground_root() -> int:
    """The top-level window in front (0: none, or not Windows)."""
    if sys.platform != "win32":
        return 0
    user32 = _user32()
    fg = user32.GetForegroundWindow() or 0
    return int(user32.GetAncestor(fg, 2) or fg) if fg else 0  # GA_ROOT


def root_of(hwnd: int) -> int:
    """*hwnd*'s top-level window (0 for none)."""
    if not hwnd or sys.platform != "win32":
        return int(hwnd or 0)
    return int(_user32().GetAncestor(hwnd, 2) or hwnd)


def window_pid(hwnd: int) -> int:
    """The process of the window *hwnd* (0 for none)."""
    if not hwnd or sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    pid = wintypes.DWORD(0)
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


# ------------------------------------------------------------------ the session
def _region_json(r: Any) -> dict[str, Any]:
    trace = getattr(r, "trace", None)
    trace = trace if isinstance(trace, dict) else {}

    def box(b: Any) -> list[int] | None:
        return [int(v) for v in b] if b is not None else None

    return {"order": int(getattr(r, "order", 0)), "unit": int(getattr(r, "unit", 0)), "box": box(r.bbox),
            "text_box": box(getattr(r, "text_box", None)), "letter_box": box(getattr(r, "letter_box", None)),
            "kind": r.kind, "tag": getattr(r, "tag", ""), "tier": int(getattr(r, "tier", 0) or 0),
            "from_model": bool(getattr(r, "from_model", False)), "status": r.status,
            "readings": trace.get("readings"), "settled": r.source_text,
            "confidence": float(getattr(r, "ocr_confidence", 1.0) or 0.0),
            "split": bool(getattr(r, "ocr_split", False)),
            "translation": r.translated_text, "reused": getattr(r, "reused_text", ""),
            "from_cache": bool(getattr(r, "from_cache", False)), "flags": list(getattr(r, "flags", []) or []),
            "letter_flags": list(getattr(r, "letter_flags", ()) or ()), "fitted": getattr(r, "fitted", ""),
            "font_size": int(getattr(r, "font_size", 0) or 0), "size_cap": int(getattr(r, "size_cap", 0) or 0),
            "sound": getattr(r, "sound", ""), "angle": float(getattr(r, "angle", 0.0) or 0.0),
            "acted": sorted(trace.get("acted", ()))}


class Session:
    """One measuring session (see the module's notes): its folder made, the analysis log's lines and pages handed to
    it, the log's lines copied, its files written on a thread of its own. Refused outside a source checkout."""

    def __init__(self, state_dir: Path | str, root: Path | str | None = None, now: float | None = None):
        if not available(root):
            raise Refused("developer measuring exists only in a source checkout")
        base = base_folder(state_dir)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now if now is not None else time.time()))
        folder = base / stamp
        k = 1
        while folder.exists():
            k += 1
            folder = base / f"{stamp}-{k}"
        folder.mkdir(parents=True)
        (base / README_NAME).write_text(README, encoding="utf-8")
        self.folder = folder
        self.stores = folder / STORES
        self.t0 = time.time()
        self._queue: queue.Queue[Callable[[], None] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._states: dict[int, int] = {}  # page n -> its later states kept
        self._requests: dict[int, list[dict[str, Any]]] = {}
        self._last: analysis.Page | None = None
        self._writer = threading.Thread(target=self._write_loop, name="taslation-dev-measure", daemon=True)
        self._writer.start()
        self.log = analysis.ensure()
        self.log.sinks.append(folder / analysis.FILE_NAME)
        self.log.listeners.append(self)
        from .errorlog import PrivacyFormatter

        self._handler = logging.FileHandler(folder / "log.txt", encoding="utf-8")
        self._handler.setFormatter(PrivacyFormatter())
        self._handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self._handler)
        self.input = InputLog(folder / "input.jsonl", self._queue)
        self.closed = False
        LOG.info("developer measuring on: a session folder of its own")

    # (the analysis log's listener)
    def begin(self, page: analysis.Page) -> None:
        page.keep = {}
        self._last = page

    def __call__(self, page: analysis.Page, result: Any) -> None:
        if self.closed:
            return
        n = page.n
        line = dict(page.line or {})
        with self._lock:
            requests = self._requests.pop(n, [])
        erased = (page.keep or {}).get("erased")
        if result is None:
            self._json(f"p{n:04d}.json", {"analysis": line, "regions": [], "requests": requests})
            return
        frame, lettered = result.original, result.image
        regions = [_region_json(r) for r in result.regions]
        self._png(f"p{n:04d}-frame.png", frame)
        if erased is not None:
            self._png(f"p{n:04d}-erased.png", erased)
        self._png(f"p{n:04d}-lettered.png", lettered)
        self._json(f"p{n:04d}.json", {"analysis": line, "regions": regions, "requests": requests})

    def edited(self, kind: str, result: Any) -> None:
        if self.closed or result is None:
            return
        n = int(getattr(result, "analysis_n", 0) or 0)
        with self._lock:
            k = self._states.get(n, 0) + 1
            self._states[n] = k
        self._png(f"p{n:04d}-s{k}-lettered.png", result.image)
        self._json(f"p{n:04d}-s{k}.json", {"change": kind, "regions": [_region_json(r) for r in result.regions]})

    def request(self, page: analysis.Page | None, data: dict[str, Any]) -> None:
        if self.closed:
            return
        page = page or self._last
        n = page.n if page is not None else 0
        entry = {"t": int(time.time() * 1000), "page": n, **data}
        with self._lock:
            self._requests.setdefault(n, []).append(entry)
        text = json.dumps(entry, ensure_ascii=False) + "\n"
        self._queue.put(lambda: self._append("requests.jsonl", text))

    # (the files)
    def _png(self, name: str, picture: Any) -> None:
        from PIL import Image

        image = picture if isinstance(picture, Image.Image) else Image.fromarray(picture)
        path = self.folder / name
        self._queue.put(lambda: image.save(path, format="PNG", compress_level=PNG_LEVEL))

    def _json(self, name: str, data: dict[str, Any]) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=1, default=str)
        path = self.folder / name
        self._queue.put(lambda: path.write_text(text, encoding="utf-8"))

    def _append(self, name: str, text: str) -> None:
        with open(self.folder / name, "a", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def _write_loop(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            try:
                job()
            except Exception:  # noqa: BLE001 - a file less, said once
                LOG.debug("developer measuring: a file could not be written", exc_info=True)

    def close(self) -> None:
        """The session ended: no more pages, the files written, the hooks off, the session's stores deleted."""
        if self.closed:
            return
        self.closed = True
        try:
            self.log.listeners.remove(self)
        except ValueError:
            pass
        try:
            self.log.sinks.remove(self.folder / analysis.FILE_NAME)
        except ValueError:
            pass
        self.input.flush()
        self._queue.put(None)
        self._writer.join(timeout=30)
        logging.getLogger().removeHandler(self._handler)
        self._handler.close()
        shutil.rmtree(self.stores, ignore_errors=True)
        LOG.info("developer measuring off")


# ------------------------------------------------------------------ the input record
class InputLog:
    """The input record's lines (``input.jsonl``): the kinds of keys, the presses on TASlation's windows, the wheel's
    ticks over the viewer, with their times (ms). `allowed` (the window in front is the viewer's or TASlation's) is
    asked of every event: one that comes while another program is in front is dropped, whatever it is."""

    def __init__(self, path: Path, writes: "queue.Queue[Callable[[], None] | None] | None" = None):
        self.path = path
        self.writes = writes
        self.allowed: Callable[[], bool] = lambda: False
        self.pending: deque[dict[str, Any]] = deque()
        self.kept = 0

    def key(self, vk: int, t_ms: int | None = None) -> bool:
        """A key pressed (*vk*): its kind kept when the viewer or TASlation is in front; whether it was."""
        if not self.allowed():
            return False
        self._keep({"t": t_ms if t_ms is not None else int(time.time() * 1000), "type": "key", "key": key_kind(vk)})
        return True

    def press(self, button: str, x: int, y: int, ours: bool, t_ms: int | None = None) -> bool:
        """A mouse press at (*x*, *y*) on the screen: kept with its button when it is on a window of TASlation's
        (*ours*: the lettering, a side pane) and the viewer or TASlation is in front."""
        if not ours or not self.allowed() or button not in BUTTONS.values():
            return False
        self._keep({"t": t_ms if t_ms is not None else int(time.time() * 1000), "type": "press", "button": button,
                    "x": int(x), "y": int(y)})
        return True

    def wheel(self, delta: int, over_viewer: bool, t_ms: int | None = None) -> bool:
        """The wheel turned *delta* (120 a tick) over the viewer (*over_viewer*; its lettering counts): its ticks
        kept."""
        if not over_viewer or not self.allowed():
            return False
        self._keep({"t": t_ms if t_ms is not None else int(time.time() * 1000), "type": "wheel",
                    "ticks": round(int(delta) / 120, 2)})
        return True

    def _keep(self, entry: dict[str, Any]) -> None:
        self.pending.append(entry)
        self.kept += 1
        if len(self.pending) >= 16:
            self.flush()

    def flush(self) -> None:
        lines = []
        while self.pending:
            lines.append(json.dumps(self.pending.popleft(), separators=(",", ":")) + "\n")
        if not lines:
            return
        text = "".join(lines)

        def write() -> None:
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(text)

        if self.writes is not None:
            self.writes.put(write)
        else:
            write()


class InputWatch:
    """The low-level hooks that feed an `InputLog` (Windows only): a thread of its own with a message loop; every
    `WATCH_MS` it looks at the window in front and installs the keyboard and mouse hooks while *in_front*() (the viewer
    or TASlation), removes them otherwise. *ours*(hwnd) and *viewer*(hwnd) tell a window under the pointer."""

    def __init__(self, log: InputLog, in_front: Callable[[], bool], ours: Callable[[int], bool],
                 viewer: Callable[[int], bool]):
        self.log, self.in_front, self.ours, self.viewer = log, in_front, ours, viewer
        log.allowed = in_front
        self.hooked = False
        self.installs = 0
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._stop = threading.Event()

    def start(self) -> None:
        if sys.platform != "win32":
            return
        self._thread = threading.Thread(target=self._run, name="taslation-dev-input", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread_id:
            import ctypes

            ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=2)
            LOG.info("developer measuring: input hooks installed %d times in the session", self.installs)
        self.log.flush()

    def _run(self) -> None:  # pragma: no cover - Windows' hooks
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")  # (signatures of its own: below)
        self._thread_id = kernel32.GetCurrentThreadId()
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HANDLE
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        user32.GetAncestor.restype = wintypes.HWND
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        class KBD(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class MOUSE(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        hooks: list[Any] = []

        def on_key(code: int, wparam: int, lparam: int) -> int:
            if code >= 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                try:
                    self.log.key(ctypes.cast(lparam, ctypes.POINTER(KBD)).contents.vkCode)
                except Exception:  # noqa: BLE001 - never in the way of a key
                    pass
            return user32.CallNextHookEx(None, code, wparam, lparam)

        def on_mouse(code: int, wparam: int, lparam: int) -> int:
            if code >= 0 and (wparam in BUTTONS or wparam == WM_MOUSEWHEEL):
                try:
                    m = ctypes.cast(lparam, ctypes.POINTER(MOUSE)).contents
                    under = user32.GetAncestor(user32.WindowFromPoint(m.pt), 2) or 0  # GA_ROOT
                    if wparam == WM_MOUSEWHEEL:
                        delta = ctypes.c_short((m.mouseData >> 16) & 0xFFFF).value
                        self.log.wheel(delta, self.viewer(under) or self.ours(under))
                    else:
                        self.log.press(BUTTONS[wparam], m.pt.x, m.pt.y, self.ours(under))
                except Exception:  # noqa: BLE001 - never in the way of the mouse
                    pass
            return user32.CallNextHookEx(None, code, wparam, lparam)

        key_proc, mouse_proc = HOOKPROC(on_key), HOOKPROC(on_mouse)  # (kept alive while the thread runs)

        def install() -> None:
            hmod = kernel32.GetModuleHandleW(None)
            k = user32.SetWindowsHookExW(13, key_proc, hmod, 0)  # WH_KEYBOARD_LL
            m = user32.SetWindowsHookExW(14, mouse_proc, hmod, 0)  # WH_MOUSE_LL
            hooks[:] = [h for h in (k, m) if h]
            self.hooked = bool(hooks)
            self.installs += 1
            if self.installs == 1:  # (said once: whether the record can work on this computer)
                LOG.info("developer measuring: input hooks %s", "installed" if len(hooks) == 2 else
                         f"not installed ({2 - len(hooks)} of 2 refused)")

        def remove() -> None:
            for h in hooks:
                user32.UnhookWindowsHookEx(h)
            hooks.clear()
            self.hooked = False

        timer = user32.SetTimer(None, 0, WATCH_MS, None)
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0113:  # WM_TIMER: the window in front looked at
                    want = bool(self.in_front())
                    if want and not self.hooked:
                        install()
                    elif not want and self.hooked:
                        remove()
                        self.log.flush()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            remove()
            user32.KillTimer(None, timer)
