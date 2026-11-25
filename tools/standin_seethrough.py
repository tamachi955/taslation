"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the see-through window (`taslation.capture.seethrough`) watched in an
end-to-end run on the stand-in viewer (``tools/standin_e2e.py``: see-through mode, the program's one mode), numbers
only.

What `SeeWatch` notes while the run goes on, from the tool's own thread (nothing is sent to any window, no key, no
click, no message; the foreground is only read):

* every frame the stand-in's capture session delivers (`wgc.add_listener`: when), so that the frames a second of the
  browser while its bars fade or its spinner turns can be told with the see-through window over it;
* which window is in front, every FRONT_EVERY_S, and each change (the stand-in, this process, another);
* TASlation's own window once a second (`_own_states`): never on a monitor, at alpha 0, an application's window with
  its taskbar button (it stays shown in Windows' sense), the dialogs of the process on the screen, and when the viewer chooser or
  the banner's dialog came and went;
* the side panes once a second (`_pane_watch`), one click on the left pane's lettering switch posted to the pane
  (`_click_lettering`), and the patch under the pointer (`_hover_measure`: the pointer the see-through window reads is
  this tool's for the whole run, `install`; the real pointer is never moved) - or, with *edit* (the left pane's Edit
  on), Edit on the overlay instead (`_edit_measure`: a click and a drag on a region, posted to the lettering's own
  window);
* every HIT_EVERY_S, which window `WindowFromPoint` gives at the middle of each patch shown, at the page's middle and
  on the ground beside it: the stand-in's, never the see-through window;
* the process's CPU time and working set, every CPU_EVERY_S, with whether a page job ran, and the CPU time of the
  stand-in's processes (`process_seconds`: its sandboxed ones too); every GPU_EVERY_S, the GPU memory this process
  and the stand-in's hold (`GpuMemory`: Windows' own counter);
* the Tk thread's steps, each call's ms (`install`: see-through mode's tick, its patches handed over, the panes' rows,
  sizes and pictures, the window's redisplay and its canvas' picture), and `seethrough.make_patches` on the patch
  thread (`ui.seethrough.Patcher`);
* which screen of the stand-in's each patch set was made from (its frame's code cells, `standin_viewer.decode`);
* with *truth*: a copy of the stand-in's place on the screen every TRUTH_EVERY_S (in memory; two of them written as
  PNG into the scratch folder for the developer's eyes - they show the public sample pages and the lettering -, to be
  deleted after), and in each the patches visible of a page other than the one the copy shows (an old patch over a new
  page: its letters on the copy, and the patch not in the viewer's own frame of that moment, which the see-through
  window is never in - a patch's white over a white part of the new page, or over the new page's own lettering, is
  not it), and how the patches of the page shown lie on it (0 px off at 100 %).

`report` turns the notes and the see-through window's own (`SeeThrough.notes`) into the run's ``see_through`` block:
the time from the stand-in's change of screen (its spinner, its washed-out picture or its draw) to the window showing
none of the old page's patches (median, p90, max), the hits, the foreground's changes, the frames a second, the CPU,
what the run cost (`_cost`), the stand-in's own frame times (`_viewer_frames`: its ``anim`` and ``painted`` lines),
see-through mode's steps (`_pipeline`, `_tk_steps`), each change of screen's first and whole page over the viewer
(``on_screen``) and the truth check's findings."""

from __future__ import annotations

import bisect
import ctypes
import os
import statistics
import sys
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
GPU_EVERY_S = 5.0  # the GPU memory of this process and the stand-in's (Windows' counter, `GpuMemory`)
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
WM_MOUSEMOVE, WM_CLOSE = 0x0200, 0x0010
GWL_EXSTYLE, WS_EX_TRANSPARENT = -20, 0x00000020
EDIT_FOR_S = 60.0  # (with *edit*) a region to measure Edit on is waited for so long at the most
EDIT_DRAG = (24, 12)  # px (at 100 %) the region's box is dragged by
EDIT_MIN_BOX = 24  # px: the least side of a box the measure takes
EDITOR_TITLE = "Edit region"  # (the region editor's title, the window's language being English in a run)
# (with *add*) adding text areas: the rectangle drawn on the page's empty space, px at 100 %, and how far from every
# region's box and from the rectangles drawn before; the messages posted to TASlation's own windows
ADD_BOX, ADD_CLEAR = (90, 50), 14
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_HOTKEY, VK_INSERT = 0x0204, 0x0205, 0x0312, 0x2D

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


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MemoryCounters), wintypes.DWORD]
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def working_set_mib() -> tuple[float, float] | None:
    """This process's working set and its peak so far, MiB (read only)."""
    counters = _MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not _kernel32.K32GetProcessMemoryInfo(_kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return counters.WorkingSetSize / 2 ** 20, counters.PeakWorkingSetSize / 2 ** 20


_ntdll = ctypes.WinDLL("ntdll")
_ntdll.NtQuerySystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                            ctypes.POINTER(ctypes.c_ulong)]
_ntdll.NtQuerySystemInformation.restype = ctypes.c_long
SYSTEM_PROCESS_INFORMATION = 5
# (SYSTEM_PROCESS_INFORMATION on 64 bits: NextEntryOffset at 0, UserTime at 40, KernelTime at 48, UniqueProcessId at 80)
_SPI_NEXT, _SPI_USER, _SPI_KERNEL, _SPI_PID = 0, 40, 48, 80


def process_seconds(pids: set[int]) -> dict[int, float]:
    """The CPU seconds (kernel and user) each process of *pids* has used so far: one look at every process's times
    (NtQuerySystemInformation, read only - a browser's sandboxed processes cannot be opened by another), or, where that
    fails, those of *pids* that can be opened (PROCESS_QUERY_LIMITED_INFORMATION)."""
    wanted = {int(p) for p in pids}
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        size = 1 << 19
        for _ in range(4):
            buffer = ctypes.create_string_buffer(size)
            needed = ctypes.c_ulong(0)
            status = _ntdll.NtQuerySystemInformation(SYSTEM_PROCESS_INFORMATION, buffer, size, ctypes.byref(needed))
            if status == 0:
                out: dict[int, float] = {}
                raw, offset = buffer.raw, 0
                while True:
                    pid = int.from_bytes(raw[offset + _SPI_PID:offset + _SPI_PID + 8], "little")
                    if pid in wanted:
                        user = int.from_bytes(raw[offset + _SPI_USER:offset + _SPI_USER + 8], "little", signed=True)
                        kernel = int.from_bytes(raw[offset + _SPI_KERNEL:offset + _SPI_KERNEL + 8], "little",
                                                signed=True)
                        out[pid] = (user + kernel) / 1e7
                    step = int.from_bytes(raw[offset + _SPI_NEXT:offset + _SPI_NEXT + 4], "little")
                    if not step:
                        return out
                    offset += step
            size = max(size * 2, int(needed.value) + 65536)
    out = {}
    for pid in wanted:
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            continue
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if _kernel32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                kernel, user = ((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:])
                out[int(pid)] = (kernel + user) / 1e7
        finally:
            _kernel32.CloseHandle(handle)
    return out


class _PdhValue(ctypes.Union):
    _fields_ = [("longValue", ctypes.c_long), ("doubleValue", ctypes.c_double), ("largeValue", ctypes.c_longlong),
                ("text", ctypes.c_void_p)]


class _PdhFmtValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("value", _PdhValue)]


class _PdhItem(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _PdhFmtValue)]


class GpuMemory:
    """The GPU memory each process holds, read from Windows' own counter (``\\GPU Process Memory(*)\\Dedicated
    Usage``, by its English name: PDH, read only); `read` gives pid -> MiB, {} where the counter is not there."""

    PDH_FMT_LARGE, PDH_MORE_DATA = 0x400, 0x800007D2

    def __init__(self) -> None:
        self._query = self._counter = None
        try:
            self._pdh = ctypes.WinDLL("pdh")
            query, counter = ctypes.c_void_p(), ctypes.c_void_p()
            if self._pdh.PdhOpenQueryW(None, None, ctypes.byref(query)) != 0:
                return
            if self._pdh.PdhAddEnglishCounterW(query, "\\GPU Process Memory(*)\\Dedicated Usage", None,
                                               ctypes.byref(counter)) != 0:
                self._pdh.PdhCloseQuery(query)
                return
            self._query, self._counter = query, counter
        except (OSError, AttributeError):
            self._query = self._counter = None

    def read(self) -> dict[int, float]:
        if self._query is None:
            return {}
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            return {}
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(self._counter, self.PDH_FMT_LARGE, ctypes.byref(size),
                                                        ctypes.byref(count), None) & 0xFFFFFFFF
        if status != self.PDH_MORE_DATA or not size.value:
            return {}
        buffer = (ctypes.c_byte * size.value)()
        if self._pdh.PdhGetFormattedCounterArrayW(self._counter, self.PDH_FMT_LARGE, ctypes.byref(size),
                                                  ctypes.byref(count), buffer) != 0:
            return {}
        items = ctypes.cast(buffer, ctypes.POINTER(_PdhItem * count.value)).contents
        out: dict[int, float] = {}
        for item in items:
            name = item.szName or ""
            if not name.startswith("pid_"):
                continue
            try:
                pid = int(name.split("_")[1])
            except (IndexError, ValueError):
                continue
            out[pid] = out.get(pid, 0.0) + item.FmtValue.value.largeValue / 2 ** 20
        return out

    def close(self) -> None:
        if self._query is not None:
            self._pdh.PdhCloseQuery(self._query)
            self._query = None


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
                 front_before: int = 0, activations: Activations | None = None, pane_shot: Path | None = None,
                 viewer_pids: Callable[[], set[int]] | None = None, edit: bool = False, standin: Any = None,
                 top: int = 0, state_of: Callable[[Any], str] | None = None, add: bool = False) -> None:
        self.app, self.hwnd, self.decode = app, int(hwnd), decode
        self.edit = bool(edit)  # (the left pane's Edit on: `_edit_measure` in place of `_hover_measure`)
        self.add = bool(add)  # (adding text areas measured, `_add_measure`, in place of both; Edit as *edit* has it)
        self.add_result: dict[str, Any] = {}
        # (scenario s) the stand-in's browser (`standin_viewer.StandinBrowser`: what its page says), whose slides of
        # the page the pointer the window reads follows (`_follow_slides`; no hover measure then); *top*: the rows
        # above the page's content in the client area; *state_of*: a frame to what the stand-in drew in it ("slide":
        # the page out of its place, `standin_viewer.Shown.state`)
        self.standin, self.top, self.state_of = standin, int(top), state_of
        self.fake_button = False  # whether the see-through window and the live view are told the button is held
        self._said = 0
        self._slide: dict[str, Any] | None = None
        self.slide_rows: list[dict[str, Any]] = []
        self.slide_sets: set[int] = set()  # the keys of the patch sets made of a frame of a page slid out of place
        self.slide_error = ""
        self.edit_result: dict[str, Any] = {}
        self.viewer_pids = viewer_pids  # (the stand-in's processes: their CPU and GPU memory, `cost`)
        self.viewer_cpu: list[tuple[float, bool, dict[int, float]]] = []  # (ms, a job ran, pid -> CPU seconds)
        self.memory: list[tuple[float, float]] = []  # (ms, this process's working set in MiB)
        self.gpu: list[tuple[float, float, float]] = []  # (ms, this process's GPU memory MiB, the stand-in's)
        self._gpu: GpuMemory | None = None
        self.patch_ms: list[float] = []  # `seethrough.make_patches`, each call's ms (the patch thread)
        self.tk_steps: dict[str, list[tuple[float, float]]] = {}  # step -> (ms since the epoch at its end, its ms)
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
        self.root_facts: dict[str, Any] = {}  # (`_own_states`: the hidden window's taskbar button as last looked at)
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
        # ... and so is the button (`fake_button`: held only while a slide of scenario s presses the page), so that a
        # press of the person's own elsewhere on the computer changes nothing in a run either
        window.button_down = lambda: self.fake_button
        pairs = ui.pairs

        def noted(app: Any) -> Any:
            out = pairs(app)
            for original, _lettered, _final, _state in out:
                key = id(original)
                if not any(img is original for _k, img in self._made):
                    self.screens[key] = self.decode(original)
                    self._made = [(key, original), *self._made[:63]]
                    if self.state_of is not None and self.state_of(original) == "slide":
                        self.slide_sets.add(key)
            return out

        ui.pairs = noted
        from taslation import seethrough as st

        make = st.make_patches

        def timed(*a: Any, **k: Any) -> Any:
            t = time.perf_counter()
            try:
                return make(*a, **k)
            finally:
                self.patch_ms.append((time.perf_counter() - t) * 1000)

        st.make_patches = timed
        # the Tk thread's own steps, each call timed (`tk_steps`): what see-through mode and the window spend there
        from taslation import panes as pn

        for owner, name, label in ((ui, "tick", "see.tick"), (ui, "present", "see.present"),
                                   (ui, "panes_tick", "see.panes_tick"), (ui, "left_rows", "see.left_rows"),
                                   (ui, "right_rows", "see.right_rows"), (pn, "width_for", "panes.width_for"),
                                   (pn, "render", "panes.render"), (self.app, "_redisplay", "window._redisplay"),
                                   (getattr(self.app, "canvas", None), "set_image", "canvas.set_image")):
            if owner is not None and callable(getattr(owner, name, None)):
                self._time_calls(owner, name, label)

    def _time_calls(self, owner: Any, name: str, label: str) -> None:
        """*owner*'s *name* (a module's function, or an object's method put on the object itself) timed at each call."""
        inner = getattr(owner, name)
        calls = self.tk_steps.setdefault(label, [])

        def timed(*a: Any, **k: Any) -> Any:
            t = time.perf_counter()
            try:
                return inner(*a, **k)
            finally:
                calls.append((time.time() * 1000, (time.perf_counter() - t) * 1000))

        setattr(owner, name, timed)

    def _frame(self, hwnd: int, _seq: int) -> None:
        if hwnd == self.hwnd:
            self.frames.append(time.time() * 1000)

    def start(self) -> None:
        self.thread.start()

    def acting(self) -> bool:
        """Whether a scene of the watch's own (the pointer on a bubble, Edit's click and drags, Add area) is being
        acted now: the run's end waits for it (`standin_e2e.Director.step`), so that its measures are not cut."""
        thread = self.hover_thread
        return thread is not None and thread.is_alive()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(3.0)
        if self.hover_thread is not None:
            self.hover_thread.join(3.0)
        from taslation.capture import wgc

        wgc.remove_listener(self._frame)
        if self.activations is not None:
            self.activations.release()
        if self._gpu is not None:
            self._gpu.close()

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
        next_gpu = time.monotonic() + GPU_EVERY_S
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
                at = time.time() * 1000
                self.cpu.append((at, time.process_time(), bool(getattr(self.app, "busy", False))))
                memory = working_set_mib()
                if memory is not None:
                    self.memory.append((at, memory[0]))
                if self.viewer_pids is not None:
                    try:
                        self.viewer_cpu.append((at, self.cpu[-1][2], process_seconds(set(self.viewer_pids()))))
                    except Exception:  # noqa: BLE001 - a look that failed is a look less
                        pass
                next_cpu = now + CPU_EVERY_S
            if now >= next_gpu:
                try:
                    if self._gpu is None:
                        self._gpu = GpuMemory()
                    held = self._gpu.read()
                    viewer = set(self.viewer_pids()) if self.viewer_pids is not None else set()
                    if held:
                        self.gpu.append((time.time() * 1000, held.get(self.own_pid, 0.0),
                                         sum(v for p, v in held.items() if p in viewer)))
                except Exception:  # noqa: BLE001 - a look that failed is a look less
                    pass
                next_gpu = now + GPU_EVERY_S
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
            if self.standin is not None:
                if not self.slide_error:
                    try:
                        self._follow_slides()
                    except Exception as e:  # noqa: BLE001 - noted, and no more slides followed
                        self.fake_button, self.fake_point = False, None
                        self.slide_error = type(e).__name__
            elif self.hover_thread is None and now - self.started >= HOVER_AFTER_S:
                measure = self._add_safe if self.add else self._edit_safe if self.edit else self._hover_safe
                self.hover_thread = threading.Thread(target=measure, name="see-hover", daemon=True)
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

    def _follow_slides(self) -> None:
        """(scenario s) The stand-in's slides of its page as its page says them: the pointer the see-through window
        and the live view read (`fake_point`, `fake_button`: this tool's own, the real pointer is never moved)
        pressed where the page was pressed, moved along with it to where the slide ends and let go at the release. On
        a slide to the left, once it is held at its end, the pointer is put on the left pane's lettering switch with
        the button still down - a move with the button's flag posted to the pane -, and at the release the button's
        release is posted to the pane as well, as if the viewer had held no capture (`_probe_plate`): the switch must
        not change."""
        from taslation.capture import windows

        said = self.standin.said(self._said)
        self._said += len(said)
        for _mono, e in said:
            if e.get("ev") != "slide":
                continue
            if e.get("on") == "1" and "x0" in e:
                x, y, _w, _h = windows._client_box(self.hwnd)
                start = (x + int(e["x0"]), y + self.top + int(e["y"]))
                end = (x + int(e["x1"]), start[1])
                s: dict[str, Any] = {"dir": e.get("dir"), "edge": e.get("edge") == "1", "start": start, "end": end,
                                     "moves_at": float(e["t"]) + float(e.get("press", 0)),
                                     "ms": max(1.0, float(e.get("ms", 1))), "on_t": float(e["t"]), "held_t": None,
                                     "off_t": None, "probe": None}
                self._slide = s
                self.fake_point, self.fake_button = start, True
            elif e.get("held") == "1" and self._slide is not None:
                self._slide["held_t"] = float(e["t"])
                if self._slide["dir"] == "l":
                    self._probe_plate(self._slide)
            elif e.get("on") == "0":
                s, self._slide = self._slide, None  # type: ignore[assignment]
                self.fake_button = False
                if s is None:
                    continue
                s["off_t"], s["turned"] = float(e["t"]), e.get("turn") == "1"
                probe = s.get("probe")
                if probe and probe.get("lparam") is not None:
                    _user32.PostMessageW(probe["pane"], WM_LBUTTONUP, 0, probe["lparam"])
                    probe["released_t"] = time.time() * 1000
                self.fake_point = None
                self.slide_rows.append(s)
        s = self._slide
        if s is not None and s["probe"] is None:  # the pointer along with the page
            share = min(1.0, max(0.0, (time.time() * 1000 - s["moves_at"]) / s["ms"]))
            self.fake_point = (round(s["start"][0] + (s["end"][0] - s["start"][0]) * share), s["start"][1])
        for row in self.slide_rows:
            probe = row.get("probe")
            if probe and probe.get("released_t") and "after" not in probe \
                    and time.time() * 1000 - probe["released_t"] > 1500:
                probe["after"] = self._plate_state()

    def _plate_state(self) -> dict[str, Any]:
        over = self.over()
        return {"lettering_on": None if over is None else bool(over.on),
                "acted_on": len(getattr(self.app, "_see_clicked", ()) or ()),
                "clicks_taken": None if over is None else int(over.counts.get("clicks", 0))}

    def _probe_plate(self, s: dict[str, Any]) -> None:
        """The pointer, its button held since the page was pressed, put on the left pane's lettering switch from
        outside it: a WM_MOUSEMOVE with MK_LBUTTON posted to the pane (its release follows at the slide's, posted
        too: `_follow_slides`)."""
        over = self.over()
        memo = (getattr(self.app, "_see_pane_memo", None) or {}).get("left")
        box = over.pane_shown("left") if over is not None else None
        plate = dict(memo[1].hits).get("lettering") if memo is not None else None
        pane = over.panes.get("left", 0) if over is not None else 0
        if box is None or plate is None or not pane:
            s["probe"] = {"done": False, "why": "the left pane hidden" if box is None else "no switch"}
            return
        x, y = (plate[0] + plate[2]) // 2, (plate[1] + plate[3]) // 2
        lparam = (y << 16) | (x & 0xFFFF)
        self.fake_point = (box[0] + x, box[1] + y)
        s["probe"] = {"done": True, "pane": pane, "lparam": lparam, "before": self._plate_state()}
        _user32.PostMessageW(pane, WM_MOUSEMOVE, MK_LBUTTON, lparam)

    def slide_report(self, jobs: dict[str, Any]) -> dict[str, Any]:
        """(scenario s) Each slide of the page with the pointer: ms from its press, whether it turned the page, each
        spell a side pane was hidden from the press until 10 s after the release (from, to - None: not back -, why),
        the pane moves while the button was held, the patches made of a frame of the page out of place shown more than
        300 ms after the release, and what the left pane's switch did with a press that did not begin on it
        (`_probe_plate`); *jobs*: what the window made of such frames (`standin_e2e.slide_jobs`)."""
        over = self.over()
        notes = list(over.notes) if over is not None else []
        marks = [(n["t"] * 1000 + self.delta_ms, n["side"], n["ev"] == "pane", n.get("why")) for n in notes
                 if n["ev"] in ("pane", "pane_hide")]
        serial_key = {n["set"]: n["key"] for n in notes if n["ev"] == "present"}
        shows = [(n["t"] * 1000 + self.delta_ms, n["set"]) for n in notes if n["ev"] == "show" and n.get("shown")]

        def shown_at(side: str, t: float) -> bool:
            got = False
            for when, s, shown, _why in marks:
                if when > t:
                    break
                if s == side:
                    got = shown
            return got

        rows = []
        for s in self.slide_rows:
            on, off = s["on_t"], s["off_t"]
            spells: list[list[Any]] = []
            for side in ("left", "right"):
                open_: list[Any] | None = None if shown_at(side, on - 1) else [side, None, None, "before"]
                for t, sd, shown, why in marks:
                    if sd != side or t < on or t > off + 10000:
                        continue
                    if not shown and open_ is None:
                        open_ = [side, round(t - on), None, why]
                    elif shown and open_ is not None:
                        open_[2] = round(t - on)
                        spells.append(open_)
                        open_ = None
                if open_ is not None:
                    spells.append(open_)
            moved = sum(1 for t, _sd, shown, _w in marks if shown and on <= t <= off)
            late = [round(t - off) for t, serial in shows if serial_key.get(serial) in self.slide_sets and t > off + 300]
            probe = s.get("probe")
            if probe:
                probe = {k: v for k, v in probe.items() if k in ("done", "why", "before", "after")}
            rows.append({"dir": s["dir"], "to_the_edge": s["edge"], "turned": s.get("turned"),
                         "release_ms": round(off - on), "held_ms": None if s["held_t"] is None else round(off - s["held_t"]),
                         "panes_shown_before": {side: shown_at(side, on - 1) for side in ("left", "right")},
                         "panes_shown_at_release": {side: shown_at(side, off) for side in ("left", "right")},
                         "hidden_spells_ms_from_press": spells, "pane_draws_while_pressed": moved,
                         "slide_patches_shown_after_release_ms": late[:10], "plate_probe": probe})
        return {"slides": rows, "error": self.slide_error or None,
                "sets_made_of_slide_frames": len(self.slide_sets),
                "slide_set_shows": sum(1 for _t, serial in shows if serial_key.get(serial) in self.slide_sets),
                "jobs": jobs}

    def _hover_safe(self) -> None:
        try:
            self._hover_measure()
        except Exception as e:  # noqa: BLE001 - noted
            self.fake_point = None
            self.hover = {"error": type(e).__name__}

    def _hover_measure(self) -> None:
        """(a thread of its own, from HOVER_AFTER_S on) The pointer on a patch and off it again, HOVER_ROUNDS times,
        as the see-through window reads it (this tool's `fake_point`: the real pointer is never moved): how long until
        the patch is gone (the hover delay, ``hover_delay_ms``, and the look after it) and until it is back, whether the
        others stay, how long until the right pane holds the bubble's block and whether it is still there once the
        pointer has left the patch; then at the edge of a patch with no other one
        near that side (HOVER_IN_PX off hides it, HOVER_OUT_PX off keeps it hidden, farther shows it again, a px farther
        than HOVER_IN_PX keeps it shown; each point held 0.3 s and the hover delay). Each round takes the page shown
        then (two patches or
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
                    block = wait(lambda: getattr(self.app, "_see_right_used", "") == "bubble", 1.0)  # (the right pane
                    # with the bubble's block: Tk's next tick)
                    time.sleep(0.25)
                    self.fake_point = None
                    back = wait(lambda: now() is None or index in now())
                    if during is None or now() is None:
                        turned += 1
                        continue
                    rounds.append({"gone_ms": gone, "back_ms": back, "others_stayed": all(i in during for i in rest),
                                   "bubble_block_ms": block,
                                   "bubble_kept": getattr(self.app, "_see_right_used", "") == "bubble"})
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
                    time.sleep(0.3 + float(getattr(over, "_hover_delay", 0.0)))  # (left out once it has rested so long)
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
        over = self.over()
        self.hover = {"delay_ms": round(float(getattr(over, "_hover_delay", 0.0)) * 1000) if over is not None else None,
                      "rounds": rounds, "gone_ms": spread([r["gone_ms"] for r in rounds]),
                      "bubble_block_ms": spread([r["bubble_block_ms"] for r in rounds]),
                      "bubble_kept": all(r["bubble_kept"] for r in rounds) if rounds else None,
                      "back_ms": spread([r["back_ms"] for r in rounds]),
                      "others_stayed": all(r["others_stayed"] for r in rounds) if rounds else None,
                      "edge": edges[0] if edges else None, "begun_again_for_another_page": turned,
                      "pages_without_room_at_an_edge": no_room,
                      "front_same": int(_user32.GetForegroundWindow() or 0) == front,
                      "other_windows_in_front_meanwhile": sorted(others_in_front)}

    def _edit_safe(self) -> None:
        try:
            self._edit_measure()
        except Exception as e:  # noqa: BLE001 - noted
            self.fake_point = None
            self.edit_result = {**self.edit_result, "error": type(e).__name__}

    def _editor_window(self) -> int:
        """The region editor on the screen: a shown top-level window of this process titled EDITOR_TITLE; 0: none."""
        found: list[int] = []

        def each(hwnd, _l):  # type: ignore[no-untyped-def]
            if window_pid(hwnd) != self.own_pid or not _user32.IsWindowVisible(hwnd):
                return True
            title = ctypes.create_unicode_buffer(64)
            _user32.GetWindowTextW(hwnd, title, 64)
            if title.value == EDITOR_TITLE:
                found.append(int(hwnd))
                return False
            return True

        _user32.EnumWindows(ENUMPROC(each), 0)
        return found[0] if found else 0

    def _edit_measure(self) -> None:
        """(a thread of its own, from HOVER_AFTER_S on, with *edit*: the left pane's Edit on) Edit on the overlay, by
        messages POSTED to the lettering's own window (no input of the system's, nothing to any other window; the
        pointer the window reads is this tool's, and its look at the physical button - which a posted press does not
        hold - is left out, `SeeThrough._edit_held`): on a region of the page on show, its box at least EDIT_MIN_BOX px
        a side, its middle in no other box nor on a pane: whether the window takes the mouse (no WS_EX_TRANSPARENT),
        which window `WindowFromPoint` gives on the box (the overlay) and beside every box (the stand-in); the pointer
        on it (its patches stay, outlined, and the right pane holds the bubble's block); a click: how long until the
        region editor is on the screen, whether it lies over the box, on a monitor, the box's own, whether it took the
        foreground (it takes the keys) and the region it holds (the page done: its set handed over as final); a
        WM_CLOSE posted to it: how long until it is gone and
        the stand-in is in front again; then a drag of the box by EDIT_DRAG px: the press handed over, the box
        outlined at its new place meanwhile, how long until the change is stored and the page's marks have the box
        there, and the fewest patches shown meanwhile against those before; then a drag of its bottom right corner by
        as much: handed over as a resize, and how long until the page's marks have the box at its new size."""
        from taslation import seethrough as st
        from taslation.capture import seethrough as window

        front = int(_user32.GetForegroundWindow() or 0)
        fronts: set[str] = set()
        out: dict[str, Any] = {"front_before": self._who(front)}
        self.edit_result = out

        def wait(until: Callable[[], bool], limit: float) -> float | None:
            t = time.monotonic()
            while time.monotonic() - t < limit and not self.stop.is_set():
                fronts.add(self._who(int(_user32.GetForegroundWindow() or 0)))
                if until():
                    return round((time.monotonic() - t) * 1000, 1)
                time.sleep(0.002)
            return None

        def pick() -> tuple[Any, ...] | None:
            over = self.over()
            if over is None or not over._edit_takes or over._marks_live is None or over._press is not None:
                return None
            look, shown, marks = over._last_look, over.shown(), over._marks_live
            if look is None or shown is None or marks.locked or getattr(self.app, "busy", False):
                return None
            if not any(s.serial == shown[0] and s.final for s in list(over._store.sets)):
                return None  # (a page done, not one filling in: its patches stay the same set)
            origin, size = look[5], look[6]
            panes = [b for b in (over.pane_shown(s) for s in ("left", "right")) if b is not None]
            dx, dy = st.scaled(EDIT_DRAG[0], over._dpi), st.scaled(EDIT_DRAG[1], over._dpi)
            for i, b in enumerate(marks.boxes):
                if i in over._left_out or b[2] - b[0] < EDIT_MIN_BOX or b[3] - b[1] < EDIT_MIN_BOX:
                    continue
                cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
                if any(j != i and o[0] <= cx < o[2] and o[1] <= cy < o[3] for j, o in enumerate(marks.boxes)):
                    continue
                if b[2] + dx > size[0] or b[3] + dy > size[1]:
                    continue
                sx, sy = origin[0] + cx, origin[1] + cy
                if any(p[0] <= sx < p[2] and p[1] <= sy < p[3] for p in panes):
                    continue
                return over, marks, i, b, (cx, cy), origin, size, (dx, dy)
            return None

        def lp(x: int, y: int) -> int:
            return (y & 0xFFFF) << 16 | (x & 0xFFFF)

        def who_at(x: int, y: int) -> str:
            return self._who(int(_user32.GetAncestor(_user32.WindowFromPoint(wintypes.POINT(x, y)), GA_ROOT) or 0))

        got: list[tuple[Any, ...]] = []

        def picked() -> bool:
            found = pick()
            if found is not None:
                got.append(found)
            return found is not None

        out["region_wait_ms"] = wait(picked, EDIT_FOR_S)
        if not got:
            out["region"] = None
            return
        over, marks, index, box, (cx, cy), origin, size, (dx, dy) = got[-1]
        over._edit_held = lambda: None  # (a posted press holds no button: not given up for that)
        out["region"] = {"boxes": len(marks.boxes), "size": [box[2] - box[0], box[3] - box[1]]}
        style = int(window._user32.GetWindowLongW(over.hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
        out["takes_the_mouse"] = not style & WS_EX_TRANSPARENT
        out["hit_box"] = who_at(origin[0] + cx, origin[1] + cy)
        beside = next(((x, y) for x, y in ((12, size[1] * 93 // 100), (size[0] - 12, size[1] * 93 // 100),
                                           (size[0] // 2, size[1] - 6))
                       if not any(b[0] - 8 <= x < b[2] + 8 and b[1] - 8 <= y < b[3] + 8 for b in marks.boxes)), None)
        out["hit_beside"] = who_at(origin[0] + beside[0], origin[1] + beside[1]) if beside is not None else None
        # the pointer on the box: its patches stay (none gives way in Edit), the box outlined, the bubble's block
        first = over.shown()
        before = tuple(first[1]) if first is not None else ()
        self.fake_point = (origin[0] + cx, origin[1] + cy)
        time.sleep(0.3 + float(getattr(over, "_hover_delay", 0.0)))
        during = over.shown()
        state = over._shown
        same = first is not None and during is not None and during[0] == first[0]  # (the same set: comparable)
        out["hover"] = {"patches_before": len(before), "patches_on_it": None if during is None else len(during[1]),
                        "kept": (set(before) <= set(during[1])) if same else "another set meanwhile",
                        "outlined": state is not None and len(state) > 4 and state[4][1] == index,
                        "bubble_block_ms": wait(lambda: getattr(self.app, "_see_right_used", "") == "bubble", 1.0)}
        # a click: the region editor beside the box, taking the keys
        t = time.monotonic()
        _user32.PostMessageW(over.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp(cx, cy))
        _user32.PostMessageW(over.hwnd, WM_LBUTTONUP, 0, lp(cx, cy))
        shown_ms = wait(lambda: self._editor_window() != 0, 6.0)
        editor = self._editor_window()
        click: dict[str, Any] = {"editor_ms": shown_ms}
        out["click"] = click
        if editor:
            focus_ms = wait(lambda: int(_user32.GetForegroundWindow() or 0) == editor, 1.5)
            facts = window.window_facts(editor) or {}
            rect = facts.get("rect") or (0, 0, 0, 0)
            screen_box = (origin[0] + box[0], origin[1] + box[1], origin[0] + box[2], origin[1] + box[3])
            overlap = max(0, min(rect[2], screen_box[2]) - max(rect[0], screen_box[0])) * max(
                0, min(rect[3], screen_box[3]) - max(rect[1], screen_box[1]))

            def monitor(r: tuple[int, ...]) -> int:
                rc = wintypes.RECT(*r)
                return int(window._user32.MonitorFromRect(ctypes.byref(rc), 2) or 0)  # (MONITOR_DEFAULTTONEAREST)

            held = getattr(getattr(self.app, "_editor", None), "region", None)
            click.update(on_monitor=facts.get("on_monitor"), over_the_box_px=overlap,
                         side="right" if rect[0] >= screen_box[2] else "left" if rect[2] <= screen_box[0] else "over",
                         same_monitor=monitor(rect) == monitor(screen_box), took_the_keys_ms=focus_ms,
                         holds_the_region=held is not None and tuple(int(v) for v in held.bbox) == tuple(box),
                         marks_held=wait(lambda: getattr(over._marks_live, "held", None) == index, 1.0))
            t = time.monotonic()
            _user32.PostMessageW(editor, WM_CLOSE, 0, 0)
            click["closed_ms"] = wait(lambda: not _user32.IsWindowVisible(editor), 3.0)
            click["viewer_in_front_ms"] = wait(lambda: int(_user32.GetForegroundWindow() or 0) == self.hwnd, 3.0)
            click["since_close_ms"] = round((time.monotonic() - t) * 1000, 1)
        self.fake_point = None
        # a drag of the box: stored as a move, outlined at its new place meanwhile
        unlocked = wait(lambda: (over._marks_live is not None and not over._marks_live.locked
                                 and not getattr(self.app, "busy", False)), 5.0)
        marks = over._marks_live
        drag: dict[str, Any] = {"unlocked_ms": unlocked}
        out["drag"] = drag
        if marks is None or index >= len(marks.boxes) or tuple(marks.boxes[index]) != tuple(box):
            drag["region"] = "gone"
        else:
            to = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
            fewest = [len((over.shown() or (0, ()))[1])]
            before_n = fewest[0]
            serial_before = over._edit_serial
            t = time.monotonic()
            _user32.PostMessageW(over.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp(cx, cy))
            _user32.PostMessageW(over.hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp(cx + dx // 2, cy + dy // 2))
            _user32.PostMessageW(over.hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp(cx + dx, cy + dy))
            _user32.PostMessageW(over.hwnd, WM_LBUTTONUP, 0, lp(cx + dx, cy + dy))
            drag["handed_ms"] = wait(lambda: over._edit_serial > serial_before, 2.0)
            drag["handed_as"] = next((n["ev"] for n in reversed(list(over.notes)) if n["ev"].startswith("edit_")
                                      and n["ev"] != "edit"), None)
            drag["ghost"] = over._ghost is not None and any(tuple(g) == to for g in over._ghost[1])
            drag["job_ms"] = wait(lambda: bool(getattr(self.app, "busy", False)), 3.0)

            def stored() -> bool:
                fewest.append(len((over.shown() or (0, ()))[1]))
                m = over._marks_live
                return (not getattr(self.app, "busy", False) and m is not None
                        and any(max(abs(a - b) for a, b in zip(o, to)) <= 2 for o in m.boxes))

            drag["stored_ms"] = wait(stored, 60.0)
            drag["since_release_ms"] = round((time.monotonic() - t) * 1000, 1)
            m = over._marks_live
            drag["nearest_px"] = None if m is None or not m.boxes else min(
                max(abs(a - b) for a, b in zip(o, to)) for o in m.boxes)
            drag["patches_before"], drag["patches_fewest_meanwhile"] = before_n, min(fewest)
            # then its bottom right corner dragged by EDIT_DRAG px: stored as a resize
            wait(lambda: over._marks_live is not None and not over._marks_live.locked, 3.0)
            m = over._marks_live
            at = None if m is None else next((i for i, o in enumerate(m.boxes) if tuple(o) == to), None)
            corner = (to[2], to[3])
            why = ("no marks" if m is None else "locked" if m.locked else "not found" if at is None else
                   "no room" if to[2] + dx > size[0] or to[3] + dy > size[1] else "")
            if not why:
                grown = (to[0], to[1], to[2] + dx, to[3] + dy)
                serial_before = over._edit_serial
                t = time.monotonic()
                _user32.PostMessageW(over.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp(*corner))
                _user32.PostMessageW(over.hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp(corner[0] + dx, corner[1] + dy))
                _user32.PostMessageW(over.hwnd, WM_LBUTTONUP, 0, lp(corner[0] + dx, corner[1] + dy))
                resize: dict[str, Any] = {"handed_ms": wait(lambda: over._edit_serial > serial_before, 2.0)}
                resize["handed_as"] = next((n["ev"] for n in reversed(list(over.notes))
                                            if n["ev"].startswith("edit_") and n["ev"] != "edit"), None)
                to = grown
                resize["stored_ms"] = wait(stored, 60.0)
                m = over._marks_live
                resize["nearest_px"] = None if m is None or not m.boxes else min(
                    max(abs(a - b) for a, b in zip(o, grown)) for o in m.boxes)
                resize["since_release_ms"] = round((time.monotonic() - t) * 1000, 1)
                drag["resize"] = resize
            else:
                drag["resize"] = why
        kinds = Counter(n["ev"] for n in list(over.notes)
                        if n["ev"] in ("edit", "press", "edit_click", "edit_move", "edit_resize", "edit_add",
                                       "press_given_up"))
        out["window_notes"] = dict(kinds)
        out["fronts_meanwhile"] = sorted(fronts)

    def _add_safe(self) -> None:
        try:
            self._add_measure()
        except Exception as e:  # noqa: BLE001 - noted
            self.fake_point = None
            self.add_result = {**self.add_result, "error": type(e).__name__}

    def _add_measure(self) -> None:
        """(a thread of its own, from HOVER_AFTER_S on, with *add*) Adding text areas, with Edit on or off as *edit*
        has it, by messages POSTED to TASlation's own windows only (the left pane, the lettering's window; the pointer
        the window reads is this tool's, and its look at the physical button - which a posted press does not hold - is
        left out, `SeeThrough._edit_held`). Once a page is done and on show, each way of asking in turn - the left
        pane's Add area row ("row") and the Insert key's message (``WM_HOTKEY``, "key"); a window that has neither gets
        what the Menu's entry sets ("flag") -, then a rectangle of ADD_BOX px dragged on the page's empty space: how
        long until the row shows pressed and the sheet is drawn (the whole page takes the mouse), which window
        `WindowFromPoint` gives there, the drag handed over as an "add", the job, the page with a region of the
        reader's at the rectangle (its status), and with Edit off how long until every click is the viewer's again.
        Then the ways of giving it up (the row again, the key again, a right click: how long until nothing is to be
        added and the page lets the mouse through). Meanwhile, every 50 ms, who is in front (the stand-in, a window of
        TASlation's, another program: read only, the tool moves no foreground) against whether the key is held; and
        the hot key's registrations, releases, failures and presses (`SeeThrough.counts`)."""
        from taslation import seethrough as st
        from taslation.capture import seethrough as window
        from taslation.ui import seethrough as ui

        app = self.app
        new = "add_area" in getattr(ui, "PANE_ACTIONS", {})
        out: dict[str, Any] = {"edit_on": self.edit, "row_and_key": new}
        self.add_result = out

        def wait(until: Callable[[], bool], limit: float) -> float | None:
            t = time.monotonic()
            while time.monotonic() - t < limit and not self.stop.is_set():
                if until():
                    return round((time.monotonic() - t) * 1000, 1)
                time.sleep(0.002)
            return None

        def lp(x: int, y: int) -> int:
            return (y & 0xFFFF) << 16 | (x & 0xFFFF)

        def who_at(x: int, y: int) -> str:
            return self._who(int(_user32.GetAncestor(_user32.WindowFromPoint(wintypes.POINT(x, y)), GA_ROOT) or 0))

        found: list[tuple[Any, ...]] = []

        def page_done() -> bool:
            over = self.over()
            if over is None or getattr(app, "last_result", None) is None or getattr(app, "busy", False):
                return False
            shown, look = over.shown(), over._last_look
            if shown is None or look is None or not any(s.serial == shown[0] and s.final for s in list(over._store.sets)):
                return False
            found.append((over, look[5], look[6]))
            return True

        out["page_wait_ms"] = wait(page_done, EDIT_FOR_S)
        if not found:
            out["page"] = None
            return
        over, origin, size = found[-1]
        over._edit_held = lambda: None  # (a posted press holds no button: not given up for that)
        drawn: list[tuple[int, int, int, int]] = []

        def spot() -> tuple[int, int, int, int] | None:
            """Empty space on the page at rest: ADD_BOX px, ADD_CLEAR px from every region's box, from the rectangles
            drawn before and from the panes."""
            result = getattr(app, "last_result", None)
            boxes = [tuple(int(v) for v in r.bbox) for r in (result.regions if result is not None else ())] + drawn
            page = getattr(app, "_see_rest_box", None) or (0, 0, size[0], size[1])
            w, h = st.scaled(ADD_BOX[0], over._dpi), st.scaled(ADD_BOX[1], over._dpi)
            clear = st.scaled(ADD_CLEAR, over._dpi)
            panes = [b for b in (over.pane_shown(s) for s in ("left", "right")) if b is not None]
            for y in range(int(page[1]) + clear, int(page[3]) - h - clear, max(8, h // 2)):
                for x in range(int(page[0]) + clear, int(page[2]) - w - clear, max(8, h // 2)):
                    box = (x, y, x + w, y + h)
                    if any(box[0] - clear < b[2] and b[0] - clear < box[2] and box[1] - clear < b[3]
                           and b[1] - clear < box[3] for b in boxes):
                        continue
                    sx, sy = origin[0] + x, origin[1] + y
                    if any(p[0] - clear < sx + w and sx < p[2] + clear and p[1] - clear < sy + h and sy < p[3] + clear
                           for p in panes):
                        continue
                    return box
            return None

        def row_click(name: str) -> bool:
            memo = (getattr(app, "_see_pane_memo", None) or {}).get("left")
            pane = over.panes.get("left", 0)
            hit = dict(memo[1].hits).get(name) if memo is not None and memo[2] is not None else None
            if hit is None or not pane:
                return False
            at = lp((hit[0] + hit[2]) // 2, (hit[1] + hit[3]) // 2)
            _user32.PostMessageW(pane, WM_LBUTTONDOWN, MK_LBUTTON, at)
            _user32.PostMessageW(pane, WM_LBUTTONUP, 0, at)
            return True

        def key() -> bool:
            _user32.PostMessageW(over.hwnd, WM_HOTKEY, int(getattr(window, "HOTKEY_ID", 0)), VK_INSERT << 16)
            return True

        def flag() -> bool:  # (what the Menu's Add a text area sets, in a window without the row or the key)
            app._see_adding = True
            return True

        ask: dict[str, Callable[[], bool]] = {"row": lambda: row_click("add_area"), "key": key, "flag": flag}

        def adding() -> bool:
            return bool(getattr(app, "_see_adding", False))

        def sheet() -> bool:  # (drawn: the window's shown state has the sheet, after UpdateLayeredWindow)
            marks, shown = over._marks_live, over._shown
            return bool(over._edit_takes and marks is not None and marks.adding and shown is not None
                        and len(shown) > 4 and shown[4] is not None and shown[4][3])

        def let_through() -> bool:  # (nothing to add, no sheet drawn; with Edit off the window click-through again)
            shown = over._shown
            drawn = shown is not None and len(shown) > 4 and shown[4] is not None and shown[4][3]
            return not adding() and not drawn and (self.edit or not over._edit_takes)

        def row_on() -> bool | None:
            memo = (getattr(app, "_see_pane_memo", None) or {}).get("left")
            rows = memo[0][0] if memo is not None else ()
            row = next((r for r in rows if getattr(r, "name", "") == "add_area"), None)
            return None if row is None else bool(row.on)

        def idle() -> bool:
            return not getattr(app, "busy", False) and over._press is None and not adding()

        def held() -> bool:
            return bool(getattr(over, "_key_held", False))

        # who is in front against whether the key is held, every 50 ms while the measure runs (read only: the tool
        # moves no foreground - which window is in front is the owner's doing): (owner, held) -> samples
        fronts: Counter = Counter()
        sampling = threading.Event()

        def sample() -> None:
            from taslation.capture import windows

            while not sampling.is_set() and not self.stop.is_set():
                owner = windows.foreground_owner(windows.foreground_window(), self.hwnd)
                fronts[f"{owner}:{'held' if held() else 'free'}"] += 1
                time.sleep(0.05)

        sampler = threading.Thread(target=sample, name="add-fronts", daemon=True)
        if new:
            sampler.start()
        out["key_held_at_start"] = held() if new else None
        rounds: list[dict[str, Any]] = []
        out["rounds"] = rounds
        for how in (("row", "key") if new else ("flag",)):
            r: dict[str, Any] = {"how": how}
            rounds.append(r)
            r["idle_ms"] = wait(idle, 30.0)
            box = spot()
            r["spot"] = None if box is None else [box[2] - box[0], box[3] - box[1]]
            if box is None:
                continue
            r["key_held"] = held() if how == "key" else None
            serial, t = over._edit_serial, time.monotonic()
            if not ask[how]():
                r["asked"] = False
                continue
            r["armed_ms"] = wait(adding, 2.0)
            r["row_pressed_ms"] = wait(lambda: row_on() is True, 1.0) if new else None
            r["sheet_ms"] = wait(sheet, 3.0)
            style = int(window._user32.GetWindowLongW(over.hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
            r["takes_the_mouse"] = not style & WS_EX_TRANSPARENT
            r["hit"] = who_at(origin[0] + (box[0] + box[2]) // 2, origin[1] + (box[1] + box[3]) // 2)
            x0, y0, x1, y1 = box
            self.fake_point = (origin[0] + x0, origin[1] + y0)
            _user32.PostMessageW(over.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp(x0, y0))
            _user32.PostMessageW(over.hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp((x0 + x1) // 2, (y0 + y1) // 2))
            _user32.PostMessageW(over.hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp(x1, y1))
            _user32.PostMessageW(over.hwnd, WM_LBUTTONUP, 0, lp(x1, y1))
            r["handed_ms"] = wait(lambda: over._edit_serial > serial, 2.0)
            r["handed_as"] = next((n["ev"] for n in reversed(list(over.notes)) if n["ev"].startswith("edit_")), None)
            self.fake_point = None
            drawn.append(box)
            r["job_ms"] = wait(lambda: bool(getattr(app, "busy", False)), 3.0)

            def made() -> list[Any]:
                result = getattr(app, "last_result", None)
                return [g for g in (result.regions if result is not None else ())
                        if str(getattr(g, "kind", "")).startswith("manual")
                        and max(abs(int(a) - int(b)) for a, b in zip(g.bbox, box)) <= 4]

            r["stored_ms"] = wait(lambda: not getattr(app, "busy", False) and bool(made()), 60.0)
            r["since_ask_ms"] = round((time.monotonic() - t) * 1000, 1)
            regions = made()
            r["region_status"] = regions[0].status if regions else None
            r["adding_after"] = adding()
            r["row_pressed_after"] = row_on() if new else None
            r["back_to_reading_ms"] = None if self.edit else wait(lambda: not over._edit_takes, 3.0)
        if new:
            for how in ("row", "key", "right"):
                r = {"how": how + " cancel"}
                rounds.append(r)
                r["idle_ms"] = wait(idle, 30.0)
                ask["row" if how == "right" else how]()
                r["armed_ms"] = wait(adding, 2.0)
                r["sheet_ms"] = wait(sheet, 3.0)
                serial, t = over._edit_serial, time.monotonic()
                if how == "right":
                    page = getattr(app, "_see_rest_box", None) or (0, 0, size[0], size[1])
                    at = lp((int(page[0]) + int(page[2])) // 2, (int(page[1]) + int(page[3])) // 2)
                    _user32.PostMessageW(over.hwnd, WM_RBUTTONDOWN, 0x0002, at)
                    _user32.PostMessageW(over.hwnd, WM_RBUTTONUP, 0, at)
                else:
                    ask[how]()
                r["given_up_ms"] = wait(let_through, 3.0)
                r["row_released_ms"] = wait(lambda: row_on() is False, 1.0)
                notes = [n for n in list(over.notes)[-50:] if n["ev"] == "edit_add" and n.get("press", 0) > serial
                         and n["t"] >= t]
                r["added"] = any(not n.get("given_up") for n in notes)  # (a rectangle handed over: none expected)
                r["handed_given_up"] = any(n.get("given_up") for n in notes)  # (a right click: an "add" of no box)
            sampling.set()
            sampler.join(1.0)
        out["fronts"] = dict(fronts)  # ("viewer:held", "other:free", "own:free" are right; the rest a look's lag)
        out["hot_key"] = {k: int(over.counts.get(k, 0)) for k in ("key_registered", "key_released", "key_failed",
                                                                  "keys")}
        out["key_held_at_end"] = held() if new else None
        kinds = Counter(n["ev"] for n in list(over.notes) if n["ev"] in ("edit", "press", "edit_add", "press_given_up",
                                                                         "key", "key_held"))
        out["window_notes"] = dict(kinds)

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
        it lies on no monitor (MonitorFromRect, MONITOR_DEFAULTTONULL), at alpha 0, an application's window with its
        taskbar button (no tool window, owned by none) titled "TASlation" and not minimised; "not shown" before Tk
        first shows it (IsWindowVisible false); else the aspects that fail (once shown it is shown in Windows' sense all
        the while: Tk's dialogs need a master in its normal state) -, and the other top-level windows of this process
        that are shown on a
        monitor (TASlation's dialogs; tips and menus have no frame and are not Tk's top-levels), how many at each look.
        Without it: the window titled TASlation shown, minimised or hidden, as before. The viewer chooser that came by
        itself and the banner's dialog are noted with their times (`self.dialogs`)."""
        from taslation.capture import seethrough as window

        app = self.app
        if app is not None and getattr(app, "_see_hidden", False):
            root = int(getattr(app, "_see_root_hwnd", 0) or 0)
            facts = window.window_facts(root) if root else None
            if facts is not None:
                self.root_facts = {k: facts[k] for k in ("button", "tool", "app", "owned", "title")}
            if facts is None:
                state = "no handle yet"
            elif not facts["visible"]:
                state = "not shown"  # (not yet shown by Tk: before that its handle is not the window's frame)
            else:
                wrong = [name for name, bad in (("on a monitor", facts["on_monitor"]), ("alpha", facts["alpha"] != 0),
                                                ("no taskbar button", not facts["button"]),
                                                ("title", facts["title"] != "TASlation"),
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
        looks ={k.split(":", 1)[1]: v for k, v in self.own_states.items() if k.startswith("hidden:")}
        dialogs = Counter({k.split(":", 1)[1]: v for k, v in self.own_states.items() if k.startswith("dialogs shown:")})
        return {"looks": looks, "looks_off": looks.get("off", 0), "looks_not_off": sum(
                    v for k, v in looks.items() if k not in ("off", "no handle yet", "not shown")),
                "dialogs_shown_at_looks": dict(dialogs), "dialogs": self.dialogs,
                "fixes": dict(getattr(app, "_see_hidden_fixes", {}) or {}),
                "handed_back": int(getattr(app, "_see_handed_back", 0) or 0),
                "front": dict(getattr(app, "_see_front", {}) or {}), "button": dict(self.root_facts),
                "menus_opened": len(getattr(app, "_see_menu_opened", []) or []),
                # (the log of the foreground's counts: kinds only, `seethrough.foreground_tick`; and how often a
                # dialog's closing gave the foreground back at once, `seethrough.closing`)
                "foreground": dict(getattr(app, "_see_foreground", {}) or {}),
                "foreground_lines": list(getattr(app, "_see_foreground_lines", []) or []),
                "foreground_notes": int(getattr(app, "_see_front_notes", 0) or 0),
                "foreground_polled": int(getattr(app, "_see_front_polled", 0) or 0),
                "foreground_hooked": bool(getattr(getattr(app, "_see_fronts", None), "hooked", False)),
                "closing_gave_back": int(getattr(app, "_see_closing", 0) or 0)}

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
        cost = self._cost(changes)
        viewer_frames = self._viewer_frames(events, changes)
        pipeline = self._pipeline(notes)
        # what the reader sees of each change of screen: from its draw to the first patches of the new screen shown
        # over the viewer, and to its whole page's (a set handed over as final) - before the next change
        final_of = {n["set"]: bool(n.get("final")) for n in notes if n["ev"] == "present"}
        shows = [(n["t"] * 1000 + self.delta_ms, n["set"]) for n in notes if n["ev"] == "show" and n.get("shown")]
        on_screen = []
        for i, c in enumerate(changes):
            until = changes[i + 1]["t"] if i + 1 < len(changes) else float("inf")
            mine = [(t, s) for t, s in shows if c["draw_t"] <= t < until and screen_of(s) == c["to"]]
            first = mine[0][0] - c["draw_t"] if mine else None
            final = next((t - c["draw_t"] for t, s in mine if final_of.get(s)), None)
            on_screen.append({"t": round(c["draw_t"]), "to": list(c["to"]), "why": c["why"],
                              "first_ms": None if first is None else round(first),
                              "final_ms": None if final is None else round(final)})
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
                # what the window being in front gave instead (`front_tick`) and the menus opened
                "hidden_window": self._hidden_report(),
                # each time the bars went from a page read under them (`ui.seethrough.after_bars`): ms on the run's
                # clock, pages carried over to the frame without them, bubbles left out (cut by a bar: read again)
                "carries": [[round(t * 1000 + self.delta_ms - (changes[0]["t"] if changes else 0)), c, d]
                            for t, c, d in getattr(self.app, "_see_carries", None) or ()],
                "frames_per_s": fps, "cpu": cpu, "cost": cost, "viewer_frames": viewer_frames, "pipeline": pipeline,
                "tk_steps": self._tk_steps(changes), "on_screen": on_screen,
                "panes": self.pane_report(),
                "edit": self.edit_result if self.edit and not self.add else None,  # (`_edit_measure`: Edit on)
                "add": self.add_result if self.add else None,  # (`_add_measure`: text areas added)
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

    def _cost(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        """What the run cost: this process's working set (MiB, each CPU_EVERY_S, and its peak), the stand-in's CPU (per
        cent of one processor, its processes together, at rest and while following as `_cpu` tells them), the GPU memory
        this process and the stand-in held (Windows' counter, MiB, each GPU_EVERY_S) and PyTorch's own peak here."""
        times = [c["t"] for c in changes]
        rest, follow = [], []
        spans = {"rest": [0.0, 0.0], "following": [0.0, 0.0]}  # (CPU s, wall s) - its mean: the median of a viewer
        # idle between its draws is 0
        for (t0, busy0, c0), (t1, busy1, c1) in zip(self.viewer_cpu, self.viewer_cpu[1:]):
            both = set(c0) & set(c1)
            if t1 <= t0 or not both:
                continue
            used = sum(c1[p] - c0[p] for p in both)
            share = 100 * used * 1000 / (t1 - t0)
            kind = None
            if any(t1 - 3000 <= t <= t1 for t in times):
                follow.append(share)
                kind = "following"
            elif not busy0 and not busy1:
                rest.append(share)
                kind = "rest"
            if kind is not None:
                spans[kind][0] += used
                spans[kind][1] += (t1 - t0) / 1000
        peak = None
        torch = sys.modules.get("torch")
        try:
            if torch is not None and torch.cuda.is_available():
                peak = round(torch.cuda.max_memory_reserved() / 2 ** 20)
        except Exception:  # noqa: BLE001 - not told
            peak = None
        memory = working_set_mib()
        return {"working_set_mib": spread([m for _t, m in self.memory]),
                "peak_working_set_mib": round(memory[1]) if memory is not None else None,
                "viewer_cpu": {"rest": spread(rest), "following": spread(follow),
                               **{f"{k}_mean": round(100 * c / w, 1) if w else None for k, (c, w) in spans.items()},
                               "all_s": round(sum(sum(c.values()) for _t, _b, c in self.viewer_cpu[-1:]) - sum(
                                   sum(c.values()) for _t, _b, c in self.viewer_cpu[:1]), 1) if self.viewer_cpu else None},
                "gpu_mib": {"own": spread([g[1] for g in self.gpu]), "viewer": spread([g[2] for g in self.gpu])},
                "torch_peak_reserved_mib": peak}

    def _viewer_frames(self, events: list[dict[str, Any]], changes: list[dict[str, Any]]) -> dict[str, Any]:
        """The stand-in's own frames: from each change of screen's draw to the first frame its capture session
        delivered after it (ms: the system's composition and the capture), its own time from a turn's draw to the frame
        after the one that showed it (``ev=painted``), and the gaps between its animation frames (``ev=anim``: the bars'
        fade, the spinner) - each animation's median, p90 and longest gap, and the frames a second over all."""
        frames = sorted(self.frames)
        to_frame = []
        for c in changes:
            i = bisect.bisect_left(frames, c["draw_t"])
            if i < len(frames) and frames[i] - c["draw_t"] < 1000:
                to_frame.append(frames[i] - c["draw_t"])

        def number(e: dict[str, Any], key: str) -> float | None:
            try:
                return float(e[key])
            except (KeyError, TypeError, ValueError):
                return None

        painted = [number(e, "ms") for e in events if e["ev"] == "painted"]
        anim: dict[str, Any] = {}
        for kind in ("bars", "spinner"):
            rows = [e for e in events if e["ev"] == "anim" and e.get("kind") == kind]
            frames_n = sum(number(e, "frames") or 0 for e in rows)
            ms_sum = sum(number(e, "ms") or 0 for e in rows)
            anim[kind] = {"animations": len(rows), "frames_per_s": round(frames_n * 1000 / ms_sum, 1) if ms_sum else None,
                          "median_gap_ms": spread([number(e, "median") for e in rows]),
                          "p90_gap_ms": spread([number(e, "p90") for e in rows]),
                          "max_gap_ms": spread([number(e, "max") for e in rows])}
        return {"draw_to_captured_frame_ms": spread(to_frame), "painted_ms": spread([p for p in painted if p is not None]),
                "anim": anim}

    def _tk_steps(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        """The Tk thread's steps timed (`install`): per step, each call's ms, its calls a second over the run, their
        seconds together, and the per cent of one processor it took at rest, while a page job ran and while following
        (a change of screen in the 3 s before), the spans told apart as `_cpu` does."""
        times = sorted(c["t"] for c in changes)
        spans: list[tuple[float, float, str]] = []
        for (t0, _c0, busy0), (t1, _c1, busy1) in zip(self.cpu, self.cpu[1:]):
            if t1 <= t0:
                continue
            i = bisect.bisect_left(times, t1 - 3000)
            kind = ("following" if i < len(times) and times[i] <= t1 else "rest" if not busy0 and not busy1 else "job")
            spans.append((t0, t1, kind))
        wall: Counter[str] = Counter()
        for t0, t1, kind in spans:
            wall[kind] += t1 - t0
        starts = [s[0] for s in spans]
        whole_s = (spans[-1][1] - spans[0][0]) / 1000 if spans else 0.0
        out: dict[str, Any] = {}
        for label, calls in self.tk_steps.items():
            used: Counter[str] = Counter()
            for at, ms in calls:
                i = bisect.bisect_right(starts, at) - 1
                if 0 <= i < len(spans) and at <= spans[i][1]:
                    used[spans[i][2]] += ms
            out[label] = {"ms": spread([ms for _at, ms in calls]),
                          "per_s": round(len(calls) / whole_s, 1) if whole_s else None,
                          "total_s": round(sum(ms for _at, ms in calls) / 1000, 2),
                          **{f"{kind}_pct": round(100 * used[kind] / wall[kind], 1) if wall[kind] else None
                             for kind in ("rest", "job", "following")}}
        return out

    def _pipeline(self, notes: list[dict[str, Any]]) -> dict[str, Any]:
        """See-through mode's own steps for a page: `seethrough.make_patches` per call (ms, the patch thread), from each set
        handed over (``present``) to its first showing (``show``, the window's thread), and when each set was handed
        over (ms since the epoch: the e2e puts them against the window's displays, `see_lags`)."""
        handed: dict[Any, float] = {}
        lags, times = [], []
        for n in notes:
            if n["ev"] == "present":
                handed[n["set"]] = n["t"]
                times.append(round(n["t"] * 1000 + self.delta_ms))
            elif n["ev"] == "show" and n.get("set") in handed:
                lags.append((n["t"] - handed.pop(n["set"])) * 1000)
        return {"make_patches_ms": spread(self.patch_ms), "present_to_show_ms": spread(lags), "presents_t": times}
