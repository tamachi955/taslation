"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the browser-type stand-in viewer, its Python side.

`standin.html` beside this file is a page that draws sample pages as a browser-based e-book reader does (its
docstring says how); this module starts it in a throwaway browser window and talks to it, for
`tools/standin_e2e.py`:

* the script the page runs by itself (`Step`, `format_script`, `parse_script`): no key, no click, nothing sent to
  any window;
* the page's behaviour profiles (`PROFILES`, ``profile=dark|light``: two kinds of web viewer, their parts each
  switchable alone, `PROFILE_OPTIONS`, `parse_options`), off unless asked for;
* the page list and the control file, both written into a scratch folder given (`write_page_list`,
  `write_control`), never anywhere else: the list names the pictures by file URL where they are (a dataset read in
  place, or the repository's test fixtures), and no picture is copied or written;
* the browser: Chrome or Edge as found on this computer (`find_browser`), started on a scratch profile with its own
  window (`browser_command`, `StandinBrowser`) and its offer to translate the page off (`make_profile`), found
  again by the process tree it started AND the token in its title (`find_window`: a window of another process is
  never asked its title), closed with that process tree alone, and its profile deleted;
* what the page says (`parse_line`: its console lines, from the browser's log on standard error) and the cells it
  draws in its band (`decode`: which screen a captured frame shows, soft or sharp, with the spinner or black);
* the guard on what TASlation chose (`SelectionGuard`): anything but the stand-in's window stops the run.

Standard library, numpy and Pillow only."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import quote, urlencode

HTML = Path(__file__).resolve().with_name("standin.html")
TITLE = "Stand-in reader"  # the page's title, the token after it
PAGE_LIST, CONTROL = "pages.js", "control.js"
REPLACE_TRIES_S = 2.0  # the control file's rename is tried again so long while the browser holds it open
# go, wait, next, previous, jump, flash, spinner, soft time, blur factor, mark, end, hold, keep, turn released, the
# bars shown for a while (a profile), the side arrows shown (a profile), the page slid with the pointer to the right
# and to the left (ms; to the window's edge, or "-D" CSS px), let go
OPS = "gwnpjfstbmehkuvarlo"
WITH_NUMBER = "gwjmh"  # steps that need a number
RANGED = "wrl"  # steps that take a second number: a wait's range (low to high), a slide's distance
CELL, CODE_X, CODE_Y = 6, 12, 12  # the page's code cells (CSS pixels from the content's top left), as standin.html
LEAD = (1, 0, 1, 0)
# the page's behaviour profiles (``profile=``) and the names of their parts, each switchable alone in the query (as
# PROFILES in standin.html, whose docstring says what each does)
PROFILES = ("dark", "light")
PROFILE_OPTIONS = ("ground", "cover", "bars", "bar_top", "bar_bottom", "bar_style", "bar_fade_ms", "bar_hide_ms",
                   "bar_key_hide", "arrows", "arrow_show", "arrow_hide_ms", "arrow_inset", "page_clicks",
                   "ground_clicks", "jump", "jump_ms", "jump_half", "half_ms", "preview", "preview_ms", "resize",
                   "resize_ms", "focus_black", "counter")
OPTION_VALUE = re.compile(r"[A-Za-z0-9_.\-]*")
DARK = 16  # a frame no brighter than this at every point looked at is black


# ---------------------------------------------------------------------------------------------------- the script
@dataclass(frozen=True)
class Step:
    """One step of the page's script: *op* one of `OPS`, *a* its number (ms, page, go, mark), *b* the end of a range
    of waits (``w6000-8000``) or a slide's distance in CSS px (``r700-120``: slid 120 px over 700 ms, not to the
    edge)."""

    op: str
    a: int | None = None
    b: int | None = None

    def __post_init__(self) -> None:
        if self.op not in OPS or len(self.op) != 1:
            raise ValueError(f"unknown step {self.op!r}")
        if self.op in WITH_NUMBER and self.a is None:
            raise ValueError(f"step {self.op!r} needs a number")
        if self.b is not None and (self.op not in RANGED or self.a is None or (self.op == "w" and self.b < self.a)):
            raise ValueError("a range is for a wait, low to high (or a slide's distance)")
        for v in (self.a, self.b):
            if v is not None and (not isinstance(v, int) or v < 0):
                raise ValueError("numbers are whole and not negative")

    def text(self) -> str:
        return self.op + ("" if self.a is None else str(self.a)) + ("" if self.b is None else f"-{self.b}")


STEP = re.compile(r"([a-z])(\d+)?(?:-(\d+))?")


def format_script(steps: Iterable[Step]) -> str:
    return ",".join(s.text() for s in steps)


def parse_script(text: str) -> list[Step]:
    out = []
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        m = STEP.fullmatch(part)
        if m is None:
            raise ValueError(f"bad step {part!r}")
        out.append(Step(m.group(1), None if m.group(2) is None else int(m.group(2)),
                        None if m.group(3) is None else int(m.group(3))))
    return out


# ---------------------------------------------------------------------------------------------------- the files
def file_url(path: Path) -> str:
    """A file URL for *path* (absolute), its characters quoted as a browser wants them."""
    p = Path(path).resolve().as_posix()
    return "file:///" + quote(p.lstrip("/"), safe="/:")


def _inside(folder: Path, name: str) -> Path:
    folder = Path(folder).resolve()
    path = (folder / name).resolve()
    if path.parent != folder:
        raise ValueError("the stand-in writes into its scratch folder only")
    return path


def write_page_list(folder: Path, pictures: Sequence[Path | tuple[Path, str]]) -> Path:
    """The page list (`PAGE_LIST`) in the scratch *folder*, which must exist: a script that hands the page the file
    URLs of *pictures* (each a path, or a path and a flip, "h", "v" or "hv"), in reading order. Nothing else is
    written, no picture is copied."""
    files = []
    for item in pictures:
        path, flip = (item if isinstance(item, tuple) else (item, ""))
        files.append({"url": file_url(Path(path)), "flip": flip} if flip else {"url": file_url(Path(path))})
    target = _inside(folder, PAGE_LIST)
    target.write_text("standinPages(" + json.dumps({"files": files}) + ");\n", encoding="utf-8")
    return target


def write_control(folder: Path, go: int = 0, band: int | None = None, hold: int | None = None,
                  sharp: int | None = None, turns: int | None = None) -> Path:
    """The control file (`CONTROL`) in the scratch *folder*: how far the page's script may go (*go*), the height
    of its band (CSS pixels; None: as it is), and, for a script that has them, how far its holds may go (*hold*,
    ``hN``), how many of its turns kept soft may be drawn sharp (*sharp*, ``kN``) and the turns released so far
    for its ``u`` steps (*turns*); None: not in the file. Written whole at once (a file beside it renamed over it);
    while the browser has the file open for a read, Windows refuses the rename, and it is tried again for up to
    REPLACE_TRIES_S (a run stopped on it at its first release once)."""
    target = _inside(folder, CONTROL)
    data: dict[str, int] = {"go": int(go)}
    if band is not None:
        data["band"] = int(band)
    if hold is not None:
        data["hold"] = int(hold)
    if sharp is not None:
        data["sharp"] = int(sharp)
    if turns is not None:
        data["turns"] = int(turns)
    temporary = _inside(folder, CONTROL + ".new")
    temporary.write_text("standinControl(" + json.dumps(data) + ");\n", encoding="utf-8")
    end = time.monotonic() + REPLACE_TRIES_S
    while True:
        try:
            os.replace(temporary, target)
            return target
        except PermissionError:
            if time.monotonic() >= end:
                raise
            time.sleep(0.02)


def parse_options(texts: Iterable[str]) -> dict[str, str]:
    """``NAME=VALUE`` words (a profile's parts, `PROFILE_OPTIONS`) as a dict; a name not known or a value with other
    than letters, digits, ``_ . -`` refused."""
    out: dict[str, str] = {}
    for text in texts:
        name, sep, value = str(text).partition("=")
        name = name.strip()
        if not sep or name not in PROFILE_OPTIONS or not OPTION_VALUE.fullmatch(value.strip()):
            names = ", ".join(PROFILE_OPTIONS)
            raise ValueError(f"not a profile option: {text!r} (NAME=VALUE, NAME one of {names})")
        out[name] = value.strip()
    return out


def page_url(token: str, steps: Sequence[Step], folder: Path, seed: int = 1, band: int = 54,
             soft: tuple[int, int] = (150, 400), factor: int = 6, flash_ms: int = 800, layout: str = "auto",
             soft_first: bool | None = None, slider: int = 0, profile: str = "",
             options: dict[str, Any] | None = None) -> str:
    """The stand-in page's URL: the page itself (`HTML`), its token, the page list and the control file in the
    scratch *folder*, its draws; the script in the hash. *soft_first* False (``soft_first=0`` in the query): the page
    draws every turn sharp at once and nothing after it; *slider* 1 or 2 (``slider=N``): the page slider under the
    page, 2 with the pages drawn as its knob is dragged (standin.html says how). *profile* "dark" or "light"
    (``profile=``): it behaves as that kind of web viewer, each of its parts in *options* (`PROFILE_OPTIONS`) given
    another value; a profile draws every turn sharp at once unless *soft_first* is True (``soft_first=1``). With none
    of them the URL is what it always was."""
    if slider not in (0, 1, 2):
        raise ValueError("slider is 0, 1 or 2")
    if profile not in ("", *PROFILES):
        raise ValueError(f"profile is one of {PROFILES} or none")
    options = dict(options or {})
    if options and not profile:
        raise ValueError("options are a profile's")
    parse_options(f"{k}={v}" for k, v in options.items())
    folder = Path(folder).resolve()
    if profile:
        first = {"soft_first": 1} if soft_first else {}
    else:
        first = {} if soft_first is None or soft_first else {"soft_first": 0}
    query = urlencode({"token": token, "pages": file_url(folder / PAGE_LIST), "control": file_url(folder / CONTROL),
                       "seed": seed, "band": band, "soft_min": soft[0], "soft_max": soft[1], "factor": factor,
                       "flash_ms": flash_ms, "layout": layout, **first,
                       **({"slider": slider} if slider else {}), **({"profile": profile} if profile else {}),
                       **{k: options[k] for k in PROFILE_OPTIONS if k in options}})
    return file_url(HTML) + "?" + query + "#s=" + format_script(steps)


# ---------------------------------------------------------------------------------------------------- the browser
BROWSERS = {
    "chrome": [r"Google\Chrome\Application\chrome.exe"],
    "edge": [r"Microsoft\Edge\Application\msedge.exe"],
}


def find_browser(prefer: str = "auto") -> tuple[str, Path] | None:
    """(name, program) of Chrome or Edge on this computer (*prefer* "chrome", "edge" or "auto": Chrome first, as the
    engine the browser-type readers are checked on), or None."""
    names = ["chrome", "edge"] if prefer == "auto" else [prefer]
    roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    for name in names:
        for root in (r for r in roots if r):
            for part in BROWSERS.get(name, []):
                path = Path(root) / part
                if path.is_file():
                    return name, path
    return None


# Flags: its own profile and window, no first-run prompt, no sync, nothing fetched in the background. The occlusion
# tracking and the timers stay as in any browser (a window wholly covered by opaque ones stops drawing, as the real
# readers' does). A flag the browser warns about in a bar over the page is left out: the bar would be in the frames.
FLAGS = ("--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--disable-component-update", "--disable-default-apps", "--disable-extensions", "--disable-domain-reliability",
         "--disable-client-side-phishing-detection", "--metrics-recording-only", "--no-pings",
         "--disable-features=Translate,OptimizationHints,MediaRouter,AutofillServerCommunication,"
         "InterestFeedContentSuggestions,SidePanelPinning", "--proxy-server=127.0.0.1:9",
         "--enable-logging=stderr", "--v=0")


# ... and, for a run that must not depend on the windows of a person at the machine (`draws_covered`), the occlusion
# tracking off: the stand-in draws on under any window, as a viewer that draws while covered does.
DRAWS_COVERED = ("--disable-backgrounding-occluded-windows",)
OCCLUSION_FEATURE = "CalculateNativeWinOcclusion"

# The browser's offer to translate the page (its own bubble: a window of its own over the page's top corner, so never
# in a frame of the stand-in's window, but on the screen) is turned off at both ends: the page says it is not to be
# translated (standin.html: translate="no" and the "notranslate" meta), and the throwaway profile is made with the
# offer off (`make_profile`: "translate.enabled", the setting the browser's own settings page turns off). Each end
# alone keeps the offer away in Chrome 157 and Edge 158; neither has a switch for it ("--disable-features=Translate"
# in FLAGS leaves it on, and their programs hold no "--disable-translate" any more: checked on 2026-11-23).
PREFERENCES = {"translate": {"enabled": False}}


def make_profile(profile: Path) -> Path:
    """The throwaway *profile* made (it must not exist yet) with PREFERENCES in its default profile, and nothing else
    written: the browser makes the rest at its start."""
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=False)
    (profile / "Default").mkdir()
    (profile / "Default" / "Preferences").write_text(json.dumps(PREFERENCES), encoding="utf-8")
    return profile


def browser_command(program: Path, url: str, profile: Path, rect: tuple[int, int, int, int],
                    scale: float = 1.0, draws_covered: bool = False, full_screen: bool = False) -> list[str]:
    """The command that opens *url* in a window of its own (``--app``) at *rect* (x, y, width, height) on the
    throwaway *profile*; *scale* other than 1: the browser draws as on a display of that scale
    (``--force-device-scale-factor``: its own window and the page's devicePixelRatio, no setting of the system's);
    *draws_covered*: it goes on drawing while other windows hide it wholly (DRAWS_COVERED, and the occlusion
    feature added to the one list of features turned off); *full_screen*: the window in the browser's full screen
    from its start (``--start-fullscreen``, as the reader's F11 has it)."""
    x, y, w, h = rect
    scaled = [f"--force-device-scale-factor={scale:g}"] if scale != 1.0 else []
    flags = list(FLAGS)
    if draws_covered:
        flags = [f + "," + OCCLUSION_FEATURE if f.startswith("--disable-features=") else f for f in flags]
        flags += DRAWS_COVERED
    full = ["--start-fullscreen"] if full_screen else []
    return [str(program), f"--user-data-dir={profile}", *flags, *scaled, *full, f"--window-position={x},{y}",
            f"--window-size={w},{h}", f"--app={url}"]


# a console line of the page, as the browser's log writes it: ... CONSOLE ... "STANDIN ev=... t=...", source: ...
LINE = re.compile(r'"STANDIN ([^"]*)"')


def parse_line(line: str) -> dict[str, str] | None:
    """What the page said on one line of the browser's log (its ``key=value`` words), or None for another line."""
    m = LINE.search(line)
    if m is None:
        return None
    out = {}
    for word in m.group(1).split():
        key, sep, value = word.partition("=")
        if sep:
            out[key] = value
    return out if "ev" in out and "t" in out else None


if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.OpenProcess.restype = wintypes.HANDLE


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def processes() -> list[tuple[int, int]]:
    """(process, parent) of every process now (a snapshot of the system's list; names are not read)."""
    snap = _kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    out = []
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snap)
    return out


def process_tree(root: int, table: Iterable[tuple[int, int]] | None = None) -> set[int]:
    """*root* and every process started under it, from *table* ((process, parent) pairs; now by default)."""
    pairs = list(processes() if table is None else table)
    tree, grown = {int(root)}, True
    while grown:
        grown = False
        for pid, parent in pairs:
            if parent in tree and pid not in tree and pid != parent:
                tree.add(pid)
                grown = True
    return tree


def top_windows() -> list[tuple[int, int]]:
    """(window, process) of every visible top-level window (no title is read here)."""
    found: list[tuple[int, int]] = []

    @_WNDENUMPROC
    def callback(hwnd, _lparam):  # type: ignore[no-untyped-def]
        if _user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((int(hwnd), int(pid.value)))
        return True

    _user32.EnumWindows(callback, 0)
    return found


def window_text(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def find_window(pids: set[int], token: str, windows: Iterable[tuple[int, int]] | None = None,
                title: Callable[[int], str] | None = None) -> int | None:
    """The stand-in's window: a window of a process in *pids* (the tree the tool started) whose title holds *token*
    as a word of its own, and only such a window's title is read; None when there is none, or more than one."""
    if not token:
        return None
    title = title or window_text
    found = [hwnd for hwnd, pid in (windows if windows is not None else top_windows())
             if pid in pids and token in title(hwnd).split()]
    return found[0] if len(found) == 1 else None


class StandinBrowser:
    """The throwaway browser that shows the stand-in page: started on *profile* (a scratch folder made here, its
    offer to translate off, `make_profile`, and deleted at `close`), its log on standard error read line by line into
    `events` (what the page said, with the time it came), its window found by `wait_window`. `close` asks the window
    to close, then ends what is left of the process tree it started, and of nothing else."""

    def __init__(self, program: Path, url: str, profile: Path, rect: tuple[int, int, int, int], token: str,
                 scale: float = 1.0, draws_covered: bool = False, full_screen: bool = False):
        self.profile = make_profile(profile)
        self.token = token
        self.proc = subprocess.Popen(browser_command(program, url, self.profile, rect, scale, draws_covered,
                                                     full_screen),
                                     stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                     errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.events: list[tuple[float, dict[str, str]]] = []
        self.lock = threading.Lock()
        self.hwnd: int | None = None
        self.tree: set[int] = {self.proc.pid}
        self._reader = threading.Thread(target=self._read, name="standin-log", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        for line in self.proc.stderr:  # type: ignore[union-attr]
            said = parse_line(line)
            if said is not None:
                with self.lock:
                    self.events.append((time.monotonic(), said))

    def said(self, since: int = 0) -> list[tuple[float, dict[str, str]]]:
        with self.lock:
            return self.events[since:]

    def wait_window(self, seconds: float = 20.0) -> int:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                raise RuntimeError("the stand-in browser ended at its start")
            self.tree = process_tree(self.proc.pid)
            hwnd = find_window(self.tree, self.token)
            if hwnd is not None:
                self.hwnd = hwnd
                return hwnd
            time.sleep(0.2)
        raise RuntimeError("the stand-in browser's window did not come")

    def wait_event(self, ev: str, seconds: float, since: int = 0) -> dict[str, str]:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for _t, said in self.said(since):
                if said.get("ev") == ev:
                    return said
            if self.proc.poll() is not None:
                raise RuntimeError("the stand-in browser ended")
            time.sleep(0.05)
        raise RuntimeError(f"the stand-in page said no {ev!r}")

    def alive(self) -> bool:
        return self.proc.poll() is None

    def refresh_tree(self) -> None:
        """The processes the browser started since (its renderers come and go), while it runs."""
        if self.alive():
            self.tree |= process_tree(self.proc.pid)

    def close(self) -> dict[str, Any]:
        """The window closed (WM_CLOSE to it), the processes of the tree still there after a while ended, the profile
        deleted. What was done, numbers and flags only."""
        out: dict[str, Any] = {"closed_by_window": False, "processes_ended": 0, "profile_deleted": False}
        if self.hwnd is not None and self.alive():
            _user32.PostMessageW(self.hwnd, 0x0010, 0, 0)  # WM_CLOSE
            try:
                self.proc.wait(10)
                out["closed_by_window"] = True
            except subprocess.TimeoutExpired:
                pass
        self.refresh_tree()
        left = process_tree(self.proc.pid) if self.alive() else self._descendants_left()
        for pid in sorted(left):
            if _end_process(pid):
                out["processes_ended"] += 1
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        out["processes_left"] = len(self._descendants_left()) + (1 if self.alive() else 0)
        for _attempt in range(20):
            shutil.rmtree(self.profile, ignore_errors=True)
            if not self.profile.exists():
                out["profile_deleted"] = True
                break
            time.sleep(0.5)
        return out

    def _descendants_left(self) -> set[int]:
        """The browser's process ended: the processes of the tree seen last that are still there and still its
        children's (a process number taken again by another program is not one: its parent is no longer in the tree)."""
        table = processes()
        alive = {pid: parent for pid, parent in table}
        return {pid for pid in self.tree if pid in alive and alive[pid] in self.tree and pid != self.proc.pid}


def _end_process(pid: int) -> bool:
    handle = _kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if not handle:
        return False
    try:
        return bool(_kernel32.TerminateProcess(handle, 1))
    finally:
        _kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------------------------------- the frames
@dataclass(frozen=True)
class Shown:
    """What a captured frame of the stand-in shows: the screen (its first *page*, a *spread* or a single page), the
    picture *soft* or sharp, the *spinner* over it (both: the page slid with the pointer, out of its place); or
    *black*; *known* False when the cells could not be read."""

    page: int = -1
    spread: bool = False
    soft: bool = False
    spinner: bool = False
    black: bool = False
    known: bool = False

    @property
    def screen(self) -> tuple[int, bool] | None:
        return (self.page, self.spread) if self.known and not self.black else None

    def state(self) -> str:
        if self.black:
            return "black"
        if not self.known:
            return "unknown"
        if self.spinner and self.soft:
            return "slide"
        return "spinner" if self.spinner else "soft" if self.soft else "sharp"


def check_of(data: int) -> int:
    return ((data & 15) + ((data >> 4) & 15) * 3 + ((data >> 8) & 15) * 5 + 7) & 15


def cells_of(page: int, spread: bool, soft: bool, spinner: bool) -> list[int]:
    """The cells the page draws for a screen (as standin.html's ``code``)."""
    data = (page & 511) | (int(spread) << 9) | (int(soft) << 10) | (int(spinner) << 11)
    check = check_of(data)
    return [*LEAD, *((data >> k) & 1 for k in range(12)), *((check >> k) & 1 for k in range(4))]


def decode(image: Any, top: int, dpr: float = 1.0) -> Shown:
    """What the frame *image* (a capture of the stand-in's client area, RGB) shows: its cells read at their place,
    *top* the rows above the page's content (the browser's own title bar in the client area). A frame dark at every
    point looked at is black. Only some forty pixels are read."""
    if image is None:
        return Shown()
    width, height = image.size
    cell = max(1, round(CELL * dpr))
    x0, y0 = round(CODE_X * dpr), top + round(CODE_Y * dpr)
    points = [(x0 + k * cell + cell // 2, y0 + cell // 2) for k in range(20)]
    probes = [(x0 - max(2, cell // 2), y0 + cell // 2)]
    probes += [(width * i // 6, top + (height - top) * j // 6) for i in range(1, 6) for j in range(1, 6)]
    if not all(0 <= x < width and 0 <= y < height for x, y in points + probes):
        return Shown()
    pick = image.getpixel
    if all(max(pick(p)[:3]) <= DARK for p in probes):
        return Shown(black=True, known=True)
    bits = [1 if sum(pick(p)[:3]) > 3 * 128 else 0 for p in points]
    if tuple(bits[:4]) != LEAD:
        return Shown()
    data = sum(b << k for k, b in enumerate(bits[4:16]))
    check = sum(b << k for k, b in enumerate(bits[16:20]))
    if check != check_of(data):
        return Shown()
    return Shown(page=data & 511, spread=bool(data >> 9 & 1), soft=bool(data >> 10 & 1), spinner=bool(data >> 11 & 1),
                 known=True)


# ---------------------------------------------------------------------------------------------------- the guard
class SelectionGuard:
    """What TASlation chose, checked before anything else and at every step: nothing or the stand-in's window
    (*hwnd*); anything else stops the run (`check` says why: never a title, only that it happened)."""

    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)
        self.stopped = ""

    def check(self, selected: Any) -> str:
        if self.stopped:
            return self.stopped
        hwnd = getattr(selected, "hwnd", None) if selected is not None else None
        if selected is not None and hwnd != self.hwnd:
            self.stopped = "TASlation chose a window that is not the stand-in's"
        return self.stopped


__all__ = ["CONTROL", "HTML", "OPS", "PAGE_LIST", "PROFILES", "PROFILE_OPTIONS", "SelectionGuard", "Shown", "StandinBrowser", "Step", "TITLE",
           "browser_command", "cells_of", "decode", "file_url", "find_browser", "find_window", "format_script",
           "make_profile", "page_url", "parse_line", "parse_options", "parse_script", "process_tree", "write_control",
           "write_page_list"]
