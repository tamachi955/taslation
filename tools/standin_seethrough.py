"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the see-through window (`taslation.capture.seethrough`) watched in an
end-to-end run on the stand-in viewer (``tools/standin_e2e.py --see-through``), numbers only.

What `SeeWatch` notes while the run goes on, from the tool's own thread (nothing is sent to any window, no key, no
click, no message; the foreground is only read):

* every frame the stand-in's capture session delivers (`wgc.add_listener`: when), so that the frames a second of the
  browser while its bars fade or its spinner turns can be told with the see-through window on and off;
* which window is in front, every FRONT_EVERY_S, and each change (the stand-in, this process, another);
* TASlation's own window once a second (`_own_states`): never on a monitor, at alpha 0, a tool window with no taskbar
  button (it stays shown in Windows' sense), the dialogs of the process on the screen, and when the viewer chooser or
  the banner's dialog came and went;
* the side panes once a second (`_pane_watch`), one click on the left pane's lettering switch posted to the pane
  (`_click_lettering`), and the patch under the pointer (`_hover_measure`: the pointer the see-through window reads is
  this tool's for the whole run, `install`; the real pointer is never moved);
* every HIT_EVERY_S, which window `WindowFromPoint` gives at the middle of each patch shown, at the page's middle and
  on the ground beside it: the stand-in's, never the see-through window;
* the process's CPU time, every CPU_EVERY_S, with whether a page job ran;
* which screen of the stand-in's each patch set was made from (its frame's code cells, `standin_viewer.decode`);
* with *truth*: a copy of the stand-in's place on the screen every TRUTH_EVERY_S (in memory; two of them written as
  PNG into the scratch folder for the developer's eyes - they show the public sample pages and the lettering -, to be
  deleted after), and in each the patches visible of a page other than the one the copy shows (an old patch over a new
  page: its letters on the copy, and the patch not in the viewer's own frame of that moment, which the see-through
  window is never in - a patch's white over a white part of the new page, or over the new page's own lettering, is
  not it), and how the patches of the page shown lie on it (0 px off at 100 %).

`report` turns the notes and the see-through window's own (`SeeThrough.notes`) into the run's ``see_through`` block:
the time from the stand-in's change of screen (its spinner, its washed-out picture or its draw) to the window showing
none of the old page's patches (median, p90, max), the hits, the foreground's changes, the frames a second, the CPU
and the truth check's findings."""

from __future__ import annotations

import ctypes
import os
import statistics
import threading
import time
from collections import Counter
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

FRONT_EVERY_S = 0.05
HIT_EVERY_S = 1.0
CPU_EVERY_S = 0.5
TRUTH_EVERY_S = 0.033
VISIBLE_TOL = 8  # a patch's pixel is on the screen when every channel is within this
VISIBLE_SHARE = 0.9  # a patch is on the screen when so many of its opaque pixels looked at are
INK_LEVEL = 100  # a patch's pixel darker than this (every channel) is of its letters (an old patch: its letters seen)
SHOTS_KEPT = 2
SHOT_CUT_MARGIN = 32  # px kept free above another program's pixels where a copy is cut (`_pane_watch`)
SHOT_EDGE = 8  # ... and the rim of the part kept that its second look leaves out
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
GA_ROOT = 2
PANE_CLICK_AFTER_S = 8.0  # the lettering's switch on the left pane is clicked (posted to the pane) once after so long
HOVER_AFTER_S = 14.0  # the pointer the see-through window reads (the tool's, `install`) is put on a patch after so long
HOVER_ROUNDS = 5
HOVER_FOR_S = 60.0  # ... for so long at the most (a round in which another page came is begun again)
WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 0x0201, 0x0202, 0x0001

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC,
                          ctypes.c_int, ctypes.c_int, wintypes.DWORD]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.UINT]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def screen_copy(x: int, y: int, w: int, h: int) -> np.ndarray:
    """The screen's pixels in the rectangle (RGB, (h, w, 3)): the tool's own copy, layered windows included."""
    screen = _user32.GetDC(None)
    dc = _gdi32.CreateCompatibleDC(screen)
    bmp = _gdi32.CreateCompatibleBitmap(screen, w, h)
    try:
        old = _gdi32.SelectObject(dc, bmp)
        _gdi32.BitBlt(dc, 0, 0, w, h, screen, x, y, SRCCOPY | CAPTUREBLT)
        _gdi32.SelectObject(dc, old)
        info = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        _gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(info), 0)
        arr = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
        return np.ascontiguousarray(arr[:, :, 2::-1])
    finally:
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(dc)
        _user32.ReleaseDC(None, screen)


def foreign_tiles(copy: np.ndarray, frames: list[np.ndarray | None], masks: list[tuple[int, int, int, int]],
                  tile: int = 16, level: int = 24, share: float = 0.2) -> tuple[int, tuple[int, ...] | None]:
    """How many *tile*-px squares of the screen copy *copy* (RGB, the viewer's client area) show something else than
    the viewer's own frames *frames* (RGB, the same area: a pixel counts when it is more than *level* off in a channel
    from every one of them) on more than *share* of their pixels outside *masks* (client boxes where TASlation's own
    windows draw): another program's window over the viewer (a notification, say), which a copy must not show - and
    the client box round those squares; (-1, None) when there is no frame of the copy's size to tell it by."""
    if not frames or any(f is None or f.shape != copy.shape for f in frames):
        return -1, None
    h, w = copy.shape[:2]
    differs = np.ones((h, w), bool)
    for f in frames:
        differs &= np.abs(copy.astype(np.int16) - f.astype(np.int16)).max(axis=2) > level
    for x0, y0, x1, y1 in masks:
        differs[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = False
    padded = np.zeros((-(-h // tile) * tile, -(-w // tile) * tile), bool)
    padded[:h, :w] = differs
    counts = padded.reshape(padded.shape[0] // tile, tile, padded.shape[1] // tile, tile).sum(axis=(1, 3))
    rows, cols = np.nonzero(counts > tile * tile * share)
    if not len(rows):
        return 0, None
    box = (int(cols.min()) * tile, int(rows.min()) * tile, int(cols.max() + 1) * tile, int(rows.max() + 1) * tile)
    return int(len(rows)), box


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def visible_share(copy: np.ndarray, patch: Any, dx: int = 0, dy: int = 0, step: int = 3,
                  ink: bool = False) -> float | None:
    """The share of *patch*'s opaque pixels (every *step*-th; *ink*: its dark ones only) that *copy* (RGB, the client
    area) shows as they are, the patch moved by (*dx*, *dy*); None when it has too few or lies outside."""
    left, top, right, bottom = patch.box
    left, top, right, bottom = left + dx, top + dy, right + dx, bottom + dy
    if left < 0 or top < 0 or bottom > copy.shape[0] or right > copy.shape[1]:
        return None
    alpha = patch.bgra[::step, ::step, 3] > 0
    if int(alpha.sum()) < 20:
        return None
    want = patch.bgra[::step, ::step, 2::-1].astype(np.int16)
    have = copy[top:bottom:step, left:right:step].astype(np.int16)
    if have.shape != want.shape:
        return None
    same = np.all(np.abs(have - want) <= VISIBLE_TOL, axis=2)
    if ink:  # only the patch's dark pixels, its letters: a white patch over another white place says nothing
        alpha = alpha & (want.max(axis=2) < INK_LEVEL)
        if int(alpha.sum()) < 10:
            return None
    return float(same[alpha].mean())


WH_CBT, HCBT_ACTIVATE = 5, 5
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = ctypes.c_ssize_t
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]


class Activations:
    """The activations of the calling thread's own windows (TASlation's window and its dialogs: the Tk thread), told
    by a CBT hook of that thread alone that refuses none of them; taken before the window is made, so that its first
    showing is counted too. `count`: how many; `release` takes the hook away."""

    def __init__(self) -> None:
        self.count = 0
        self.wheres: list[dict[str, Any]] = []  # each: the window's code that asked (file:line), the window's class,
        # whether it is TASlation's main window (its title is never kept), its owner, rectangle, minimised, shown

        def proc(code, wparam, lparam):  # type: ignore[no-untyped-def]
            if code == HCBT_ACTIVATE:
                self.count += 1
                import traceback

                name = ctypes.create_unicode_buffer(64)
                _user32.GetClassNameW(wparam, name, 64)
                title = ctypes.create_unicode_buffer(16)
                _user32.GetWindowTextW(wparam, title, 16)
                r = wintypes.RECT()
                _user32.GetWindowRect(wparam, ctypes.byref(r))
                self.wheres.append({"stack": [f"{Path(f.filename).name}:{f.lineno} {f.name}"
                                              for f in traceback.extract_stack()[-12:-1]],
                                    "class": name.value, "main": title.value.startswith("TASlation"),
                                    "owner": int(_user32.GetWindow(wparam, 4) or 0),
                                    "rect": [r.left, r.top, r.right, r.bottom],
                                    "iconic": bool(_user32.IsIconic(wparam)),
                                    "visible": bool(_user32.IsWindowVisible(wparam))})
            return _user32.CallNextHookEx(None, code, wparam, lparam)

        self._proc = HOOKPROC(proc)
        self._hook = _user32.SetWindowsHookExW(WH_CBT, self._proc, None, _kernel32.GetCurrentThreadId())

    def release(self) -> None:
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None


def spread(values: list[float]) -> dict[str, Any]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0}
    p90 = vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))]
    return {"n": len(vals), "median": round(statistics.median(vals), 1), "p90": round(p90, 1),
            "max": round(vals[-1], 1)}


class SeeWatch:
    """The notes of a run with the see-through window (see the module's notes). *decode*: a frame (PIL) to the
    stand-in's screen it shows, (page, spread) or None; *top*: rows above the page's content in a client capture."""

    def __init__(self, app: Any, hwnd: int, decode: Callable[[Any], Any], truth: bool, shots: Path | None,
                 front_before: int = 0, activations: Activations | None = None, pane_shot: Path | None = None) -> None:
        self.app, self.hwnd, self.decode = app, int(hwnd), decode
        self.truth, self.shots = truth, shots
        self.pane_shot = pane_shot  # (`_pane_watch`: one copy with both panes beside a spread, into this folder)
        self.panes: Counter[str] = Counter()  # (side, page kind, shown or hidden) at each look
        self.pane_overlap: dict[str, int] = {}  # (side, page kind) -> the most px a pane shared with the page box
        self.pane_gaps: Counter[str] = Counter()  # (side, page kind, px between the pane and the page)
        self.pane_edges: Counter[str] = Counter()  # (side, page kind, px between the pane and its edge of the area)
        self.pane_x: Counter[str] = Counter()  # (side, page kind, its columns in the client: the same on both kinds)
        self.pane_sizes: Counter[str] = Counter()  # (side, w x h)
        self.fake_point: tuple[int, int] | None = None  # where the see-through window is told the pointer is
        self.hover: dict[str, Any] = {}  # (`_hover_measure`)
        self.hover_thread: threading.Thread | None = None
        self.pane_click: dict[str, Any] = {}  # (`_click_lettering`)
        self.pane_shot_saved: str | None = None
        self.pane_shot_skipped = 0  # (looks at which another program's window lay over the stand-in: no copy then)
        self.pane_shot_why: Counter[str] = Counter()  # (why, numbers only: the client box of the squares that differ)
        self.pane_shot_cut = 0  # (rows left out at the copy's foot: another program's pixels there)
        self.started = time.monotonic()
        self.front_before = int(front_before)  # (the window in front just before TASlation's window was made)
        self.activations = activations
        self.own_states: Counter = Counter()  # (`_own_states`)
        self.dialogs: dict[str, list[list[Any]]] = {}  # (`_own_states`: "chooser", "banner" -> [ms shown, ms gone,
        # came by itself], ms from the watch's start)
        self._tray: Any = None  # (the notification-area icon, kept for the report)
        self.own_pid = os.getpid()
        self._over = None
        self.front_before_who = self._who(self.front_before)
        self.delta_ms = time.time() * 1000 - time.monotonic() * 1000
        self.own_pid = os.getpid()
        self.lock = threading.Lock()
        self.frames: list[float] = []
        self.fronts: list[tuple[float, str]] = []
        self.hits: Counter[str] = Counter()
        self.cpu: list[tuple[float, float, bool]] = []
        self.screens: dict[int, Any] = {}  # set key -> screen
        self._made: list[tuple[int, Any]] = []  # (set key, its frame): held, so that no other frame takes its key
        self._over: Any = None  # the see-through window, kept for the report (the window lets go of it at its close)
        self.copies = 0
        self.truth_rows: list[dict[str, Any]] = []
        self.saved: list[str] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="see-watch", daemon=True)

    # the hooks
    def install(self) -> None:
        from taslation.capture import seethrough as window
        from taslation.capture import wgc
        from taslation.ui import seethrough as ui

        wgc.add_listener(self._frame)
        # the pointer as the see-through window reads it is this tool's (`fake_point`: none but while `_hover_measure`
        # sets one): the real pointer is never moved, and wherever it rests it changes nothing in a run
        window.cursor_pos = lambda: self.fake_point
        pairs = ui.pairs

        def noted(app: Any) -> Any:
            out = pairs(app)
            for original, _lettered, _final, _state in out:
                key = id(original)
                if not any(img is original for _k, img in self._made):
                    self.screens[key] = self.decode(original)
                    self._made = [(key, original), *self._made[:63]]
            return out

        ui.pairs = noted

    def _frame(self, hwnd: int, _seq: int) -> None:
        if hwnd == self.hwnd:
            self.frames.append(time.time() * 1000)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(3.0)
        if self.hover_thread is not None:
            self.hover_thread.join(3.0)
        from taslation.capture import wgc

        wgc.remove_listener(self._frame)
        if self.activations is not None:
            self.activations.release()

    def over(self) -> Any:
        over = getattr(self.app, "_see_through", None) if self.app is not None else None
        if over is not None:
            self._over = over
        return over if over is not None else self._over

    def _who(self, hwnd: int) -> str:
        if not hwnd:
            return "none"
        if hwnd == self.hwnd:
            return "standin"
        over = self.over()
        if over is not None and hwnd == over.hwnd:
            return "overlay"
        if over is not None and hwnd in set(getattr(over, "panes", {}).values()):
            return "pane"
        return "own" if window_pid(hwnd) == self.own_pid else "other"

    def _run(self) -> None:
        next_hit = next_cpu = next_copy = 0.0
        last_front = None
        while not self.stop.wait(0.01):
            now = time.monotonic()
            front = int(_user32.GetForegroundWindow() or 0)
            who = self._who(front)
            if who != last_front:
                self.fronts.append((time.time() * 1000, who))
                last_front = who
            self.over()  # (kept)
            if now >= next_cpu:
                self.cpu.append((time.time() * 1000, time.process_time(), bool(getattr(self.app, "busy", False))))
                next_cpu = now + CPU_EVERY_S
            if now >= next_hit:
                self._hit_test()
                try:
                    self._pane_watch()
                except Exception:  # noqa: BLE001 - a look that failed is a look less
                    pass
                next_hit = now + HIT_EVERY_S
            if not self.pane_click and now - self.started >= PANE_CLICK_AFTER_S:
                try:
                    self._click_lettering()
                except Exception as e:  # noqa: BLE001 - noted
                    self.pane_click = {"error": type(e).__name__}
            if self.hover_thread is None and now - self.started >= HOVER_AFTER_S:
                self.hover_thread = threading.Thread(target=self._hover_safe, name="see-hover", daemon=True)
                self.hover_thread.start()
            if self.truth and now >= next_copy:
                try:
                    self._copy()
                except Exception:  # noqa: BLE001 - a copy that failed is a copy less
                    pass
                next_copy = now + TRUTH_EVERY_S

    def _hit_test(self) -> None:
        over = self.over()
        shown = over.shown() if over is not None else None
        points: list[tuple[str, int, int]] = []
        if shown is not None:
            serial, indices, origin, size = shown
            sets = {s.serial: s for s in list(over._store.sets)}
            chosen = sets.get(serial)
            if chosen is not None:
                for i in indices[:6]:
                    left, top, right, bottom = chosen.patches[i].box
                    points.append(("patch", origin[0] + (left + right) // 2, origin[1] + (top + bottom) // 2))
            points.append(("page", origin[0] + size[0] // 2, origin[1] + size[1] // 2))
            points.append(("ground", origin[0] + 12, origin[1] + size[1] * 93 // 100))  # (below the panes' band)
        for where, x, y in points:
            hwnd = int(_user32.GetAncestor(_user32.WindowFromPoint(wintypes.POINT(x, y)), GA_ROOT) or 0)
            self.hits[f"{where}:{self._who(hwnd)}"] += 1
        self._own_states()

    def _pane_watch(self) -> None:
        """The side panes, once a second: shown or hidden beside which kind of page (a single page or a spread, by
        its box), how many px each shares with the page box (none, ever), how far from it, their sizes, and which window
        `WindowFromPoint` gives on the right pane (the stand-in: it is click-through), on a control of the left one
        (the pane) and between two of its rows (the stand-in: nothing there). With *pane_shot*, the first time both
        show beside a spread whose page is done, one copy of the stand-in's place on the screen."""
        over = self.over()
        ground = getattr(self.app, "_see_ground", None)
        if over is None or ground is None:
            self.panes["no ground"] += 1
            return
        from taslation import panes as pn
        from taslation.capture import windows

        x0, y0, _w, _h = windows._client_box(self.hwnd)
        page = ground[1]
        kind = "spread" if page[2] - page[0] > page[3] - page[1] else "cover"
        screen_page = (x0 + page[0], y0 + page[1], x0 + page[2], y0 + page[3])
        boxes = {side: over.pane_shown(side) for side in ("left", "right")}
        for side, box in boxes.items():
            self.panes[f"{side}:{kind}:{'shown' if box is not None else 'hidden'}"] += 1
            if box is None:
                continue
            key = f"{side}:{kind}"
            self.pane_overlap[key] = max(self.pane_overlap.get(key, 0), pn.overlap(box, screen_page))
            gap = screen_page[0] - box[2] if side == "left" else box[0] - screen_page[2]
            self.pane_gaps[f"{key}:{gap}"] += 1
            columns = ground[4] if len(ground) > 4 else (0, ground[0][0])
            edge = box[0] - (x0 + columns[0]) if side == "left" else (x0 + columns[1]) - box[2]
            self.pane_edges[f"{key}:{edge}"] += 1
            self.pane_x[f"{key}:{box[0] - x0}..{box[2] - x0}"] += 1
            self.pane_sizes[f"{side}:{box[2] - box[0]}x{box[3] - box[1]}"] += 1

            def who(x: int, y: int) -> str:
                return self._who(int(_user32.GetAncestor(_user32.WindowFromPoint(wintypes.POINT(x, y)), GA_ROOT) or 0))

            if side == "right":
                self.hits[f"pane_right:{who((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)}"] += 1
                continue
            memo = (getattr(self.app, "_see_pane_memo", None) or {}).get("left")
            if memo is None:
                continue
            hits = dict(memo[1].hits)
            control = hits.get("lettering")
            if control is not None:
                self.hits[f"pane_left_control:{who(box[0] + (control[0] + control[2]) // 2, box[1] + (control[1] + control[3]) // 2)}"] += 1
            first, second = hits.get("translate") or hits.get("stop"), hits.get("auto")
            if first is not None and second is not None and second[1] > first[3]:
                self.hits[f"pane_left_gap:{who(box[0] + (first[0] + first[2]) // 2, box[1] + (first[3] + second[1]) // 2)}"] += 1
        shown = over.shown()
        hovering = self.fake_point is not None or (self.hover_thread is not None and self.hover_thread.is_alive())
        if (self.pane_shot is not None and self.pane_shot_saved is None and kind == "spread" and not hovering
                and all(b is not None for b in boxes.values()) and shown is not None
                and any(s.serial == shown[0] and s.final for s in list(over._store.sets))):
            from taslation.capture import seethrough as window

            x, y, w, h = windows._client_box(self.hwnd)
            if window.cover_rects(self.hwnd, (x, y, x + w, y + h), over.own_windows()):
                self.pane_shot_skipped += 1  # (another program's window over the stand-in: its contents are not this
                self.pane_shot_why["a window above"] += 1  # tool's to copy; a later look)
                return
            # a notification lies in a band of the window order of its own, which `cover_rects` does not walk: the copy
            # is kept only when, outside where TASlation's windows draw, it shows the viewer's own frame
            serial, _indices, origin, _size = shown
            chosen = {s.serial: s for s in list(over._store.sets)}.get(serial)
            dx, dy = origin[0] - x, origin[1] - y
            masks = [] if chosen is None else [  # (every patch of the page: shown or not, as a look may change it)
                (b[0] + dx - 3, b[1] + dy - 3, b[2] + dx + 3, b[3] + dy + 3) for b in (p.box for p in chosen.patches)]
            masks += [(b[0] - x - 2, b[1] - y - 2, b[2] - x + 2, b[3] - y + 2) for b in boxes.values() if b is not None]
            before = self._viewer_frame()
            copy = screen_copy(x, y, w, h)
            frames = [before, self._viewer_frame()]
            tiles, where = (-1, None) if chosen is None else foreign_tiles(copy, frames, masks)
            panes_end = max(b[3] - y for b in boxes.values() if b is not None)
            if tiles > 0 and where is not None and where[1] - SHOT_CUT_MARGIN >= max(h * 2 // 3, panes_end):
                # another program's pixels in the bottom third only (a notification that stays until it is put
                # away, which is not this tool's to do): the copy is cut above them, both panes whole, and the part
                # kept is looked at again square by square, a single pixel off being enough to give it up
                cut = where[1] - SHOT_CUT_MARGIN
                copy = np.ascontiguousarray(copy[:cut])
                kept = [None if f is None else f[:cut] for f in frames]
                edge = SHOT_EDGE  # (the copy's rows at the window's top edge differ from the frame's: not looked at)
                rim = [(0, 0, w, edge), (0, 0, edge, cut), (w - edge, 0, w, cut), (0, cut - edge, w, cut)]
                tiles, where = foreign_tiles(copy, kept, masks + rim, tile=8, share=0.0)
                if tiles == 0:
                    self.pane_shot_cut = h - cut
            del before, frames
            if tiles != 0:
                del copy  # (never kept, never looked at)
                self.pane_shot_skipped += 1
                self.pane_shot_why["no frame to tell by" if tiles < 0 else
                                   f"another program's pixels: {tiles} squares in {where}"] += 1
                return
            self.pane_shot.mkdir(parents=True, exist_ok=True)
            path = self.pane_shot / "see_through_panes.png"
            Image.fromarray(copy).save(path)
            self.pane_shot_saved = str(path)

    def _click_lettering(self) -> None:
        """The lettering's switch on the left pane clicked twice (off, then on again) once a page is lettered: a left
        button's press and release POSTED to the pane's own window (no input of the system's, nothing to any other
        window), each time noting how long until the lettering's state changed and whether the window in front
        changed."""
        over = self.over()
        memo = (getattr(self.app, "_see_pane_memo", None) or {}).get("left")
        if over is None or memo is None or over.pane_shown("left") is None or over.shown() is None:
            return
        box = dict(memo[1].hits).get("lettering")
        pane = over.panes.get("left", 0)
        if box is None or not pane:
            return
        x, y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        lparam = (y << 16) | (x & 0xFFFF)
        front = int(_user32.GetForegroundWindow() or 0)
        rows: list[dict[str, Any]] = []
        others: set[str] = set()  # (any other window in front meanwhile, looked at every 5 ms)

        def wait(seconds: float, until: Callable[[], bool] = lambda: False) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end and not until():
                now = int(_user32.GetForegroundWindow() or 0)
                if now != front:
                    others.add(self._who(now))
                time.sleep(0.005)

        for _ in range(2):
            before = over.on
            t = time.monotonic()
            _user32.PostMessageW(pane, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            _user32.PostMessageW(pane, WM_LBUTTONUP, 0, lparam)
            wait(2.0, lambda: over.on != before)
            ms = round((time.monotonic() - t) * 1000, 1)
            wait(0.4)
            after = int(_user32.GetForegroundWindow() or 0)
            rows.append({"on_before": before, "on_after": over.on, "ms": ms, "front_same": after == front,
                         "front": self._who(after)})
        rows.append({"other_windows_in_front_meanwhile": sorted(others)})
        clicked = [n for _t, n in getattr(self.app, "_see_clicked", ())]
        self.pane_click = {"posted_to_the_pane": 4, "rows": rows, "front_before": self._who(front),
                           "acted_on": clicked}

    def _hover_safe(self) -> None:
        try:
            self._hover_measure()
        except Exception as e:  # noqa: BLE001 - noted
            self.fake_point = None
            self.hover = {"error": type(e).__name__}

    def _hover_measure(self) -> None:
        """(a thread of its own, from HOVER_AFTER_S on) The pointer on a patch and off it again, HOVER_ROUNDS times,
        as the see-through window reads it (this tool's `fake_point`: the real pointer is never moved): how long until
        the patch is gone and until it is back, whether the others stay; then at the edge of a patch with no other one
        near that side (HOVER_IN_PX off hides it, HOVER_OUT_PX off keeps it hidden, farther shows it again, a px farther
        than HOVER_IN_PX keeps it shown). Each round takes the page shown then (two patches or
        more); a round in which another page came is begun again, for HOVER_FOR_S at the most."""
        from taslation import seethrough as st
        from taslation.capture import seethrough as window

        front = int(_user32.GetForegroundWindow() or 0)
        others_in_front: set[str] = set()
        rounds: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        turned = no_room = 0
        end = time.monotonic() + HOVER_FOR_S

        def wait(until: Callable[[], bool], limit: float = 2.0) -> float | None:
            t = time.monotonic()
            while time.monotonic() - t < limit and not self.stop.is_set():
                if until():
                    return round((time.monotonic() - t) * 1000, 1)
                now = int(_user32.GetForegroundWindow() or 0)
                if now != front:
                    others_in_front.add(self._who(now))
                time.sleep(0.001)
            return None

        def pick() -> tuple[Any, ...] | None:
            over = self.over()
            shown = over.shown() if over is not None else None
            if shown is None or len(shown[1]) < 2:
                return None
            serial, indices, origin, size = shown
            chosen = {s.serial: s for s in list(over._store.sets)}.get(serial)
            if chosen is None:
                return None
            return over, serial, tuple(indices), origin, size, chosen

        def gap(b: tuple[int, ...], x: int, y: int) -> int:  # (as `seethrough.hovered` takes it)
            return max(b[0] - x, x - (b[2] - 1), b[1] - y, y - (b[3] - 1), 0)

        def edge_plan(over: Any, chosen: Any, indices: tuple[int, ...], origin: tuple[int, int],
                      size: tuple[int, int], offsets: list[int], keep: int) -> tuple[int, str, list[Any]] | None:
            """A patch shown and a side of it where the points *offsets* px off its edge lie on the page, on no side
            pane, and farther than *keep* px from every other patch shown (which they could otherwise make hide or
            keep hidden instead)."""
            panes = [b for b in (over.pane_shown(side) for side in ("left", "right")) if b is not None]
            for index in indices:
                b = chosen.patches[index].box
                cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
                for side in ("right", "left", "below", "above"):
                    points = [(b[2] - 1 + d, cy) if side == "right" else (b[0] - d, cy) if side == "left" else
                              (cx, b[3] - 1 + d) if side == "below" else (cx, b[1] - d) for d in offsets]
                    if all(0 <= px < size[0] and 0 <= py < size[1]
                           and not any(p[0] <= origin[0] + px < p[2] and p[1] <= origin[1] + py < p[3] for p in panes)
                           and all(gap(chosen.patches[j].box, px, py) > keep for j in indices if j != index)
                           for px, py in points):
                        return index, side, points
            return None

        try:
            while time.monotonic() < end and not self.stop.is_set() and (len(rounds) < HOVER_ROUNDS or not edges):
                got = pick()
                if got is None:
                    time.sleep(0.1)
                    continue
                over, serial, indices, origin, size, chosen = got
                index, rest = indices[0], indices[1:]
                box = chosen.patches[index].box
                centre = (origin[0] + (box[0] + box[2]) // 2, origin[1] + (box[1] + box[3]) // 2)

                def now() -> tuple[int, ...] | None:
                    s = over.shown()
                    return tuple(s[1]) if s is not None and s[0] == serial else None

                if len(rounds) < HOVER_ROUNDS:
                    self.fake_point = centre
                    gone = wait(lambda: now() is None or index not in now())
                    during = now()
                    time.sleep(0.25)
                    self.fake_point = None
                    back = wait(lambda: now() is None or index in now())
                    if during is None or now() is None:
                        turned += 1
                        continue
                    rounds.append({"gone_ms": gone, "back_ms": back, "others_stayed": all(i in during for i in rest)})
                    time.sleep(0.25)
                    continue
                dpi = getattr(over, "_dpi", st.BASE_DPI)
                grow, keep = st.scaled(window.HOVER_IN_PX, dpi), st.scaled(window.HOVER_OUT_PX, dpi)
                labels = (("within_in", grow), ("within_out", keep), ("beyond_out", keep + 2),
                          ("near_again", grow + 1), ("within_in_again", grow))
                plan = edge_plan(over, chosen, indices, origin, size, [d for _label, d in labels], keep)
                if plan is None:  # (no patch of this page with room round it: another page)
                    no_room += 1
                    time.sleep(0.5)
                    continue
                index, side, points = plan
                steps: list[dict[str, Any]] = []
                for (label, off), (px, py) in zip(labels, points):
                    self.fake_point = (origin[0] + px, origin[1] + py)
                    time.sleep(0.3)
                    current = now()
                    steps.append({"at": label, "px_off_patch": off,
                                  "patch_shown": None if current is None else index in current,
                                  "others_shown": None if current is None else
                                  all(i in current for i in indices if i != index)})
                self.fake_point = None
                wait(lambda: now() is None or index in now(), 1.0)
                if any(s["patch_shown"] is None for s in steps):
                    turned += 1
                    continue
                edges.append({"side": side, "steps": steps, "grow_keep_px": [grow, keep],
                              "expected_shown": [False, False, True, True, False]})
        finally:
            self.fake_point = None
        self.hover = {"rounds": rounds, "gone_ms": spread([r["gone_ms"] for r in rounds]),
                      "back_ms": spread([r["back_ms"] for r in rounds]),
                      "others_stayed": all(r["others_stayed"] for r in rounds) if rounds else None,
                      "edge": edges[0] if edges else None, "begun_again_for_another_page": turned,
                      "pages_without_room_at_an_edge": no_room,
                      "front_same": int(_user32.GetForegroundWindow() or 0) == front,
                      "other_windows_in_front_meanwhile": sorted(others_in_front)}

    def pane_report(self) -> dict[str, Any]:
        over = self.over()
        counts = dict(over.counts) if over is not None else {}
        return {"looks": dict(self.panes), "overlap_px_max": dict(self.pane_overlap),
                "gaps_px": dict(self.pane_gaps), "edges_px": dict(self.pane_edges), "x_in_client": dict(self.pane_x),
                "sizes": dict(self.pane_sizes), "hover": self.hover,
                "hits": {k: v for k, v in self.hits.items() if k.startswith("pane_")},
                "click": self.pane_click, "shot": self.pane_shot_saved, "shot_put_off": self.pane_shot_skipped,
                "shot_put_off_why": dict(self.pane_shot_why.most_common(8)), "shot_rows_cut": self.pane_shot_cut,
                "window": {k: counts.get(k) for k in ("pane_draws", "pane_moves", "pane_hides", "clicks", "hovers")},
                "hides_by_why": dict(Counter(n["why"] for n in (list(over.notes) if over is not None else [])
                                             if n["ev"] == "pane_hide"))}

    def _own_states(self) -> None:
        """How TASlation's own main window is on the screen, counted once a second. With it hidden (see-through mode,
        `ui.seethrough.hidden`): its handle (``_see_root_hwnd``) read with `capture.seethrough.window_facts` - "off" when
        it lies on no monitor (MonitorFromRect, MONITOR_DEFAULTTONULL), at alpha 0, a tool window not marked for the
        taskbar and not minimised; "not shown" before Tk first shows it (IsWindowVisible false); else the aspects that
        fail (once shown it is shown in Windows' sense all the while: Tk's dialogs need a master in its normal state) -,
        and the other top-level windows of this process that are shown on a
        monitor (TASlation's dialogs; tips and menus have no frame and are not Tk's top-levels), how many at each look.
        Without it: the window titled TASlation shown, minimised or hidden, as before. The viewer chooser that came by
        itself and the banner's dialog are noted with their times (`self.dialogs`)."""
        from taslation.capture import seethrough as window

        app = self.app
        if app is not None and getattr(app, "_see_hidden", False):
            root = int(getattr(app, "_see_root_hwnd", 0) or 0)
            if getattr(app, "_see_tray", None) is not None:
                self._tray = app._see_tray  # (kept for the report: the window lets go of it at its close)
            facts = window.window_facts(root) if root else None
            if facts is None:
                state = "no handle yet"
            elif not facts["visible"]:
                state = "not shown"  # (not yet shown by Tk: before that its handle is not the window's frame)
            else:
                wrong = [name for name, bad in (("on a monitor", facts["on_monitor"]), ("alpha", facts["alpha"] != 0),
                                                ("not a tool window", not facts["tool"]), ("taskbar", facts["app"]),
                                                ("minimised", facts["iconic"])) if bad]
                state = "off" if not wrong else "+".join(wrong)
            self.own_states[f"hidden:{state}"] += 1
            shown = 0

            def each_dialog(hwnd, _l):  # type: ignore[no-untyped-def]
                nonlocal shown
                if hwnd == root or window_pid(hwnd) != self.own_pid:
                    return True
                name = ctypes.create_unicode_buffer(32)
                _user32.GetClassNameW(hwnd, name, 32)
                if name.value == "TkTopLevel" and _user32.IsWindowVisible(hwnd):
                    facts = window.window_facts(hwnd)
                    if facts is not None and facts["on_monitor"] and not facts["iconic"] and facts["alpha"] != 0:
                        shown += 1
                return True

            _user32.EnumWindows(ENUMPROC(each_dialog), 0)
            self.own_states[f"dialogs shown:{shown}"] += 1
            now = round((time.monotonic() - self.started) * 1000)
            for what in ("_see_chooser", "_see_banner"):
                dialog = getattr(app, what, None)
                key = what.removeprefix("_see_")
                seen = self.dialogs.setdefault(key, [])
                if dialog is not None and (not seen or seen[-1][1] is not None):
                    seen.append([now, None, bool(getattr(dialog, "by_itself", False))])
                elif dialog is None and seen and seen[-1][1] is None:
                    seen[-1][1] = now
            return
        found: list[str] = []

        def each(hwnd, _l):  # type: ignore[no-untyped-def]
            if window_pid(hwnd) != self.own_pid:
                return True
            name = ctypes.create_unicode_buffer(32)
            _user32.GetClassNameW(hwnd, name, 32)
            title = ctypes.create_unicode_buffer(16)
            _user32.GetWindowTextW(hwnd, title, 16)
            if name.value == "TkTopLevel" and title.value.startswith("TASlation"):
                found.append("minimised" if _user32.IsIconic(hwnd) else
                             "shown" if _user32.IsWindowVisible(hwnd) else "hidden")
            return True

        _user32.EnumWindows(ENUMPROC(each), 0)
        self.own_states[",".join(found) or "none"] += 1

    def _hidden_report(self) -> dict[str, Any] | None:
        app = self.app
        if app is None or not getattr(app, "_see_hidden", False) and not getattr(app, "_see_root_hwnd", 0):
            return None
        tray = getattr(app, "_see_tray", None) or self._tray
        looks = {k.split(":", 1)[1]: v for k, v in self.own_states.items() if k.startswith("hidden:")}
        dialogs = Counter({k.split(":", 1)[1]: v for k, v in self.own_states.items() if k.startswith("dialogs shown:")})
        return {"looks": looks, "looks_off": looks.get("off", 0), "looks_not_off": sum(
                    v for k, v in looks.items() if k not in ("off", "no handle yet", "not shown")),
                "dialogs_shown_at_looks": dict(dialogs), "dialogs": self.dialogs,
                "fixes": dict(getattr(app, "_see_hidden_fixes", {}) or {}),
                "handed_back": int(getattr(app, "_see_handed_back", 0) or 0),
                "tray": None if tray is None else dict(tray.counts),
                "menus_opened": len(getattr(app, "_see_menu_opened", []) or [])}

    def _viewer_frame(self) -> np.ndarray | None:
        """The viewer's newest captured frame, cut to its client area as the see-through window lies on it (RGB)."""
        from taslation.capture import wgc, windows

        frame = wgc.peek(self.hwnd)
        if frame is None:
            return None
        box = wgc.crop_box(frame.size, windows._frame_bounds(self.hwnd), windows._client_box(self.hwnd))
        if box is None:
            return None
        return np.ascontiguousarray(frame.bgra[box[1]:box[3], box[0]:box[2], 2::-1])

    def _copy(self) -> None:
        over = self.over()
        if over is None:
            return
        from taslation.capture import windows

        x, y, w, h = windows._client_box(self.hwnd)
        t = time.time() * 1000
        own = self._viewer_frame()  # (before the copy: the viewer's own picture, the see-through window never in it)
        copy = screen_copy(x, y, w, h)
        self.copies += 1
        screen = self.decode(Image.fromarray(copy))
        with over._lock:
            sets = list(over._store.sets)
        shown = over.shown()
        row: dict[str, Any] = {"t": t, "screen": screen, "old_visible": 0, "own_visible": 0, "offsets": [],
                               "old_in_frame": 0, "old_sets": []}
        for s in sets:
            made_of = self.screens.get(s.key)
            for p in s.patches:
                share = visible_share(copy, p)
                if share is None or share < VISIBLE_SHARE:
                    continue
                if made_of is not None and screen is not None and made_of != screen:
                    in_frame = own is not None and own.shape == copy.shape and (
                        visible_share(own, p) or 0.0) >= VISIBLE_SHARE
                    letters = (visible_share(copy, p, ink=True) or 0.0) >= VISIBLE_SHARE
                    if in_frame or not letters:  # the viewer's own page there looks like the patch, or only its
                        row["old_in_frame"] += 1  # white is seen (the new page's own lettering over the place)
                        continue
                    row["old_visible"] += 1
                    if len(row["old_sets"]) < 2:
                        row["old_sets"].append([s.serial, shown is not None and shown[0] == s.serial, made_of])
                elif made_of == screen:
                    row["own_visible"] += 1
                    if len(row["offsets"]) < 3:
                        best = max(((visible_share(copy, p, dx, dy) or 0.0, -abs(dx) - abs(dy), dx, dy)
                                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)))  # (a tie: the place itself)
                        row["offsets"].append([best[2], best[3]])
        row["shown"] = shown is not None
        self.truth_rows.append(row)
        final = shown is not None and any(s.serial == shown[0] and s.final for s in sets)  # (a page done, not filling)
        if (self.shots is not None and len(self.saved) < SHOTS_KEPT and row["own_visible"] >= 3 and final
                and (not self.saved or t - float(self.saved[-1].split("@")[1]) > 20000)):
            self.shots.mkdir(parents=True, exist_ok=True)
            path = self.shots / f"see_through_{len(self.saved) + 1}.png"
            Image.fromarray(copy).save(path)
            self.saved.append(f"{path}@{t}")

    # the report
    def report(self, events: list[dict[str, Any]], offset: float, end_ms: float) -> dict[str, Any]:
        over = self.over()
        notes = list(over.notes) if over is not None else []
        counts = dict(over.counts) if over is not None else {}
        serial_key = {n["set"]: n["key"] for n in notes if n["ev"] == "present"}
        state: list[tuple[float, int | None]] = []
        own_ms: list[float] = []  # the window's own time from a frame's arrival to its showing or hiding
        for n in notes:
            t = n["t"] * 1000 + self.delta_ms
            if n["ev"] == "show":
                state.append((t, n["set"]))
            elif n["ev"] == "hide":
                state.append((t, None))
            if n["ev"] in ("show", "hide") and n.get("arrived") and n.get("new"):  # (a look a new frame started)
                own_ms.append((n["t"] - n["arrived"]) * 1000)

        def screen_of(serial: int | None) -> Any:
            return None if serial is None else self.screens.get(serial_key.get(serial, -1))

        def shown_at(t: float) -> int | None:
            got = None
            for when, serial in state:
                if when > t:
                    break
                got = serial
            return got

        # the stand-in's changes of screen: each turn or jump, from its first change on the screen (spinner, black,
        # its washed-out picture or its draw)
        changes = []
        last_screen = None
        pending: float | None = None
        for e in events:
            t = e["t"] + offset
            ev = e["ev"]
            if ev in ("spinner", "black") and e.get("on") == "1":
                pending = t if pending is None else pending
            elif ev == "draw":
                screen = (int(e["page"]), e.get("spread") == "1")
                if e.get("why") in ("next", "previous", "jump") and screen != last_screen:
                    changes.append({"t": pending if pending is not None else t, "draw_t": t, "to": screen,
                                    "from": last_screen, "why": e.get("why"), "kind": e.get("kind")})
                last_screen = screen
                pending = None
        stale: list[float] = []
        rows = []
        nothing = 0
        for c in changes:
            before = shown_at(c["t"] - 1)
            old = screen_of(before)
            if before is None:
                nothing += 1
                continue
            if old == c["to"]:
                continue
            gone = None
            for when, serial in state:
                if when < c["t"] - 1:
                    continue
                if serial is None or screen_of(serial) != old:
                    gone = when
                    break
            ms = None if gone is None else max(0.0, gone - c["t"])
            if ms is not None:
                stale.append(ms)
            rows.append({"t": round(c["t"]), "why": c["why"], "kind": c["kind"], "stale_ms": ms})
        # the truth check: old patches over a new page, and how long after the change of that page
        late, old_rows = [], []
        for r in self.truth_rows:
            if not r["old_visible"]:
                continue
            since = [c["t"] for c in changes if c["t"] <= r["t"] and c["to"] == r["screen"]]
            late.append(round(r["t"] - since[-1]) if since else None)
            if len(old_rows) < 20:  # (each: the page on the copy, the page the old patch was made of, the time since
                last = [c for c in changes if c["t"] <= r["t"]]  # the last change of screen of any kind, and the time
                ahead = [c for c in changes if c["t"] > r["t"] and c["to"] == r["screen"]]  # to the change to the
                old_rows.append({"screen": r["screen"], "sets": r["old_sets"], "since_last_ms":  # copy's page if it
                                 round(r["t"] - last[-1]["t"]) if last else None,  # is logged after the copy)
                                 "last_to": last[-1]["to"] if last else None,
                                 "until_next_ms": round(ahead[0]["t"] - r["t"]) if ahead else None})
        offsets = Counter(tuple(o) for r in self.truth_rows for o in r["offsets"])
        # the comparison's margins: the worst share of changed pixels among the patches shown, and the least among
        # those hidden (`seethrough.CHANGED_SHARE` between them), each as a frame came
        worst = sorted(n["worst"] for n in notes if n["ev"] == "show" and n.get("new") and n.get("worst") is not None)
        least = sorted([n["least_hidden"] for n in notes if n["ev"] == "show" and n.get("new")
                        and (n.get("least_hidden") or -1) >= 0]
                       + [n["least"] for n in notes
                          if n["ev"] == "hide" and n.get("new") and n.get("least") is not None])

        def shares(v: list[float]) -> dict[str, Any]:
            if not v:
                return {"n": 0}
            return {"n": len(v), "min": round(v[0], 4), "p10": round(v[int(0.1 * (len(v) - 1))], 4),
                    "median": round(statistics.median(v), 4), "p90": round(v[int(0.9 * (len(v) - 1))], 4),
                    "max": round(v[-1], 4)}
        fps = self._fps(events, offset)
        cpu = self._cpu(changes, end_ms)
        return {"counts": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in counts.items()},
                "stale_ms": spread(stale), "stale_rows": rows, "changes_with_nothing_shown": nothing,
                "own_frame_to_change_ms": spread(own_ms),
                "hides_by_why": dict(Counter(n["why"] for n in notes if n["ev"] == "hide")),
                "shares": {"shown_worst": shares(worst), "hidden_least": shares(least)},
                "hits": dict(self.hits), "front_changes": len(self.fronts) - 1 if self.fronts else 0,
                "fronts": [[round(t - (changes[0]["t"] if changes else t)), w] for t, w in self.fronts],
                # the window in front before TASlation's was made, how often one of TASlation's came in front after,
                # how often none was, and the activations of TASlation's own windows from before it was made
                # (`Activations`: none refused)
                "foreground": {"before": self.front_before_who,
                               "first_seen": self.fronts[0][1] if self.fronts else None,
                               "own_came_in_front": sum(1 for _t, w in self.fronts if w in ("own", "overlay", "pane")),
                               "none_in_front": sum(1 for _t, w in self.fronts if w == "none"),
                               "not_standin": sorted({w for _t, w in self.fronts if w != "standin"}),
                               "own_activations": None if self.activations is None else self.activations.count,
                               "own_activations_from": None if self.activations is None else self.activations.wheres,
                               "own_window": dict(self.own_states)},
                # TASlation's own window hidden (`_own_states`): what kept it so, the dialogs that came by themselves,
                # the notification-area icon and the menus opened
                "hidden_window": self._hidden_report(),
                # each time the bars went from a page read under them (`ui.seethrough.after_bars`): ms on the run's
                # clock, pages carried over to the frame without them, bubbles left out (cut by a bar: read again)
                "carries": [[round(t * 1000 + self.delta_ms - (changes[0]["t"] if changes else 0)), c, d]
                            for t, c, d in getattr(self.app, "_see_carries", None) or ()],
                "frames_per_s": fps, "cpu": cpu, "panes": self.pane_report(),
                "truth": {"copies": self.copies, "with_old_patch": len(late), "old_patch_ms_after_change": late[:20],
                          "old_rows": old_rows,
                          "max_ms": max((v for v in late if v is not None), default=None),
                          # (patches of another page that the viewer's own frame shows alike, or whose letters are not
                          # on the copy - white over white -: not the see-through window's, left out above; and the
                          # old patches of the set it showed)
                          "like_the_frame": sum(r.get("old_in_frame", 0) for r in self.truth_rows),
                          "old_of_the_set_shown": sum(1 for r in self.truth_rows
                                                      if any(o[1] for o in r.get("old_sets", []))),
                          "patch_offsets": {f"{dx},{dy}": n for (dx, dy), n in offsets.items()},
                          "shots": [s.split("@")[0] for s in self.saved]},
                "sets_made_of": len(self.screens)}

    def _fps(self, events: list[dict[str, Any]], offset: float) -> dict[str, Any]:
        """The stand-in's frames a second while its bars fade (from "bars" to "bars_done") and its spinner turns."""
        spans: dict[str, list[tuple[float, float]]] = {"bars": [], "spinner": []}
        open_: dict[str, float] = {}
        for e in events:
            t = e["t"] + offset
            if e["ev"] == "bars":
                open_["bars"] = t
            elif e["ev"] == "bars_done" and "bars" in open_:
                spans["bars"].append((open_.pop("bars"), t))
            elif e["ev"] == "spinner":
                if e.get("on") == "1":
                    open_["spinner"] = t
                elif "spinner" in open_:
                    spans["spinner"].append((open_.pop("spinner"), t))
        out = {}
        frames = sorted(self.frames)
        for kind, got in spans.items():
            rates = []
            for a, b in got:
                if b - a < 100:
                    continue
                n = sum(1 for f in frames if a <= f <= b)
                rates.append(n * 1000 / (b - a))
            out[kind] = spread(rates)
        return out

    def _cpu(self, changes: list[dict[str, Any]], end_ms: float) -> dict[str, Any]:
        """The process's CPU (per cent of one processor) at rest - no page job and no change of screen in the 3 s
        before - and while following (a change of screen in the 3 s before)."""
        rest, follow = [], []
        times = [c["t"] for c in changes]
        for (t0, c0, busy0), (t1, c1, busy1) in zip(self.cpu, self.cpu[1:]):
            if t1 <= t0:
                continue
            share = 100 * (c1 - c0) * 1000 / (t1 - t0)
            recent = any(t1 - 3000 <= t <= t1 for t in times)
            if recent:
                follow.append(share)
            elif not busy0 and not busy1:
                rest.append(share)
        return {"rest": spread(rest), "following": spread(follow)}
