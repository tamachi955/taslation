"""The see-through window (a prototype behind ``Settings.see_through``, off by default; Windows only): TASlation's
lettering laid over the viewer's own window, which goes on taking every click and key itself.

* A window of its own, not Tk's: per-pixel alpha needs a layered window drawn with ``UpdateLayeredWindow`` from a
  premultiplied BGRA picture, which Tk cannot give. Its extended styles are WS_EX_LAYERED | WS_EX_TRANSPARENT (no
  hit-test: every click, wheel and pointer move goes to the window under it, and ``WindowFromPoint`` never gives it) |
  WS_EX_NOACTIVATE (never the foreground) | WS_EX_TOPMOST | WS_EX_TOOLWINDOW (no taskbar button, not in Alt+Tab); its
  window procedure answers WM_NCHITTEST with HTTRANSPARENT and WM_MOUSEACTIVATE with MA_NOACTIVATE besides. It
  sends, posts and presses nothing, and never moves the foreground.
* It lies on the viewer's client area as it is captured (`windows._client_box`, cut from the frame with
  `wgc.crop_box`): its pixel (x, y) is the captured frame's pixel (x, y), at every scale - the process is per-monitor
  DPI aware (`windows.enable_dpi_awareness`), so the client rectangle, the frame and this window are all in the screen's
  own pixels. It follows the viewer's moves and sizes at every look; while the viewer is minimised, hidden or cloaked
  it shows nothing, and a patch that a window above the viewer meets is left out (`cover_rects`).
* Its own thread runs the window and its message loop, and looks at the viewer's frames as they come: the capture
  tells it of each one (`wgc.add_listener`: an event set on the capture's thread), and it compares the frame there and
  then (`seethrough.visible`), with no wait for Tk. The Tk thread only hands it the patches of the page as they are
  lettered (`present`: immutable arrays under a lock). So a turn hides the old lettering at the first frame that
  shows another page, whatever Tk is doing.

What it shows is decided by one rule (`taslation.seethrough`): a patch belongs to the pixels it was made from."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections import deque
from typing import Any

import numpy as np

from .. import seethrough as st
from . import wgc

IS_WINDOWS = sys.platform == "win32"

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x00080000, 0x00000020, 0x08000000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW = 0x00000008, 0x00000080
EX_STYLE = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
WM_NCHITTEST, HTTRANSPARENT = 0x0084, -1
WM_MOUSEACTIVATE, MA_NOACTIVATE = 0x0021, 3
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
PM_REMOVE = 0x0001
ULW_ALPHA, AC_SRC_OVER, AC_SRC_ALPHA = 0x2, 0x0, 0x1
GW_HWNDPREV, GA_ROOT, GWL_EXSTYLE = 3, 2, -20
BI_RGB, DIB_RGB_COLORS = 0, 0
CLASS = "TASlationSeeThrough"
ERROR_CLASS_ALREADY_EXISTS = 1410

LOOK_S = 0.05  # with no frame coming, the window looks at the viewer this often (moved, minimised, covered)
COVER_S = 0.1  # the windows over the viewer are looked for at most this often
MAX_ABOVE = 512  # the order of the windows is walked this far up from the viewer
LOG_KEPT = 50000  # notes kept in memory for the tools (`notes`)
START_S = 2.0  # how long `start` waits for the window to be made

if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                        wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.DefWindowProcW.restype = LRESULT
    _user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                     wintypes.UINT]
    _user32.PeekMessageW.restype = wintypes.BOOL
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.restype = LRESULT
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, wintypes.UINT]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                            ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                            ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                            ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
    _user32.UpdateLayeredWindow.restype = wintypes.BOOL
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = wintypes.LONG
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    _gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR

MONITOR_DEFAULTTONEAREST, MDT_EFFECTIVE_DPI = 2, 0
_shcore: Any = None  # (shcore.dll, loaded at the first `viewer_dpi`)


def viewer_dpi(viewer: int) -> int:
    """The DPI of the monitor the viewer's window *viewer* is on (its effective DPI: 96 at 100 %, 120 at 125 %, 144 at
    150 %), which is how much larger than at 100 % the viewer's frames show what it draws - whether the viewer scales
    itself or Windows stretches it; st.BASE_DPI where it cannot be told (not Windows, no window, an older Windows)."""
    global _shcore
    if not IS_WINDOWS or not viewer:
        return st.BASE_DPI
    try:
        if _shcore is None:
            _shcore = ctypes.WinDLL("shcore")
            _shcore.GetDpiForMonitor.argtypes = [wintypes.HMONITOR, ctypes.c_int, ctypes.POINTER(wintypes.UINT),
                                                 ctypes.POINTER(wintypes.UINT)]
            _shcore.GetDpiForMonitor.restype = ctypes.c_long
        monitor = _user32.MonitorFromWindow(viewer, MONITOR_DEFAULTTONEAREST)
        x, y = wintypes.UINT(0), wintypes.UINT(0)
        if monitor and _shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(x), ctypes.byref(y)) == 0 \
                and x.value > 0:
            return int(x.value)
    except (AttributeError, OSError):
        pass
    return st.BASE_DPI


def _proc(hwnd, message, wparam, lparam):  # type: ignore[no-untyped-def]
    if message == WM_NCHITTEST:
        return HTTRANSPARENT
    if message == WM_MOUSEACTIVATE:
        return MA_NOACTIVATE
    return _user32.DefWindowProcW(hwnd, message, wparam, lparam)


_PROC = WNDPROC(_proc) if IS_WINDOWS else None  # kept for the life of the process: the class points at it
_class_ready = False


def _register_class() -> bool:
    global _class_ready
    if _class_ready:
        return True
    wc = WNDCLASSW()
    wc.lpfnWndProc = _PROC
    wc.hInstance = _kernel32.GetModuleHandleW(None)
    wc.lpszClassName = CLASS
    if not _user32.RegisterClassW(ctypes.byref(wc)) and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
        return False
    _class_ready = True
    return True


def cover_rects(viewer: int, client: st.Box, own: int = 0) -> list[st.Box]:
    """The screen rectangles of the windows above the viewer's window *viewer* that meet its client area *client*
    (screen pixels): shown, not minimised nor cloaked, not click-through (this window, *own*, never counts), by the
    rectangle the compositor shows of them (without the invisible resize borders)."""
    from . import windows

    out: list[st.Box] = []
    root = _user32.GetAncestor(viewer, GA_ROOT) or viewer
    above = _user32.GetWindow(root, GW_HWNDPREV)
    for _ in range(MAX_ABOVE):
        if not above:
            break
        h = int(above)
        if (h != own and _user32.IsWindowVisible(h) and not _user32.IsIconic(h) and not windows._is_cloaked(h)
                and not _user32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TRANSPARENT):
            try:
                r = windows._frame_bounds(h)
            except Exception:  # noqa: BLE001 - a window gone meanwhile
                r = None
            if r is not None and r[0] < client[2] and client[0] < r[2] and r[1] < client[3] and client[1] < r[3]:
                out.append(tuple(int(v) for v in r))  # type: ignore[arg-type]
        above = _user32.GetWindow(above, GW_HWNDPREV)
    return out


class SeeThrough:
    """The see-through window and its thread (see the module's notes). Made with `start` (None where there can be
    none), told which viewer to lie over (`follow`), handed the patches of the pages (`present`, `forget`, `clear`),
    hidden and shown by the reader's hot key (`set_on`), ended with `close`. Its notes (`notes`) are numbers and
    flags only: when it showed what, from which frame, and how long its work took."""

    def __init__(self) -> None:
        self.hwnd = 0
        self._viewer = 0
        self._on = True
        self._lock = threading.Lock()
        self._store = st.SetStore()
        self._changed = 0  # bumped by every change from the Tk thread
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._arrived: dict[int, float] = {}  # frame count -> when the capture told of it
        self.notes: deque[dict[str, Any]] = deque(maxlen=LOG_KEPT)
        self.counts = {"frames": 0, "looks": 0, "draws": 0, "hides": 0, "moves": 0, "errors": 0,
                       "compare_ms": 0.0, "draw_ms": 0.0}
        # the window thread's own state
        self._shown: tuple[Any, ...] | None = None  # (set serial, indices, origin, size) on show; None: hidden
        self._seq = -1
        self._seen_changed = -1
        self._covers: list[st.Box] = []
        self._covers_at = 0.0
        self._geometry: tuple[Any, ...] | None = None
        self._new_frame = False  # whether the look under way was started by a frame not looked at before
        self._dib: tuple[int, int, int, np.ndarray, tuple[int, int]] | None = None  # (dc, bitmap, old, pixels, size)

    # ------------------------------------------------------------------ from the Tk thread
    @classmethod
    def start(cls) -> "SeeThrough | None":
        if not IS_WINDOWS or not _register_class():
            return None
        self = cls()
        self._thread = threading.Thread(target=self._run, name="taslation-see-through", daemon=True)
        self._thread.start()
        if not self._ready.wait(START_S) or not self.hwnd:
            self.close()
            return None
        return self

    def follow(self, viewer: int | None) -> None:
        """The viewer's window to lie over (None or 0: none; nothing shows)."""
        viewer = int(viewer or 0)
        with self._lock:
            if viewer != self._viewer:
                self._viewer = viewer
                self._changed += 1
        self._wake.set()

    def set_on(self, on: bool) -> None:
        """The reader's hot key: the lettering shown (*on*) or hidden; the patches are kept."""
        with self._lock:
            if bool(on) != self._on:
                self._on = bool(on)
                self._changed += 1
        self._note("on", on=int(bool(on)))
        self._wake.set()

    @property
    def on(self) -> bool:
        return self._on

    def present(self, key: int, size: tuple[int, int], patches: tuple[st.Patch, ...], final: bool = False) -> None:
        """The patches of the page read from the frame *key* (of *size*) as lettered now: they replace the set of that
        key, and become the newest."""
        with self._lock:
            s = self._store.put(key, size, patches, final)
            self._changed += 1
        self._note("present", key=key, set=s.serial, patches=len(patches), final=int(final))
        self._wake.set()

    def forget(self, key: int) -> None:
        with self._lock:
            self._store.drop(key)
            self._changed += 1
        self._wake.set()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._changed += 1
        self._wake.set()

    def shown(self) -> tuple[Any, ...] | None:
        """(set serial, patch indices, screen origin, size) of what shows now; None when nothing does."""
        return self._shown

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(2.0)

    # ------------------------------------------------------------------ the window's thread
    def _note(self, kind: str, **facts: Any) -> None:
        self.notes.append({"t": time.monotonic(), "ev": kind, **facts})

    def _on_frame(self, hwnd: int, seq: int) -> None:
        if hwnd == self._viewer:
            self._arrived[seq] = time.monotonic()
            if len(self._arrived) > 256:
                for old in sorted(self._arrived)[:128]:
                    self._arrived.pop(old, None)
            self._wake.set()

    def _run(self) -> None:
        hwnd = _user32.CreateWindowExW(EX_STYLE, CLASS, "TASlation see-through", WS_POPUP, 0, 0, 1, 1, None, None,
                                       _kernel32.GetModuleHandleW(None), None)
        self.hwnd = int(hwnd or 0)
        self._ready.set()
        if not self.hwnd:
            return
        wgc.add_listener(self._on_frame)
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                self._wake.wait(LOOK_S)
                self._wake.clear()
                while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    _user32.TranslateMessage(ctypes.byref(msg))
                    _user32.DispatchMessageW(ctypes.byref(msg))
                try:
                    self._step()
                except Exception as e:  # noqa: BLE001 - one look's fault: noted, the next look goes on
                    self.counts["errors"] += 1
                    self._note("error", why=type(e).__name__)
        finally:
            wgc.remove_listener(self._on_frame)
            self._hide("closed")
            self._free_dib()
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = 0

    def _step(self) -> None:
        from . import windows

        with self._lock:
            viewer, on, changed = self._viewer, self._on, self._changed
            sets = list(self._store.sets)
        self.counts["looks"] += 1
        if not viewer or not on:
            self._hide("off" if viewer else "no viewer")
            return
        if not _user32.IsWindow(viewer):
            self._hide("gone")
            return
        if _user32.IsIconic(viewer) or not _user32.IsWindowVisible(viewer) or windows._is_cloaked(viewer):
            self._hide("minimised")
            return
        frame = wgc.peek(viewer)
        if frame is None:
            self._hide("no frame")
            return
        client = windows._client_box(viewer)
        bounds = windows._frame_bounds(viewer)
        now = time.monotonic()
        geometry = (client, bounds, frame.size)
        new_frame = frame.seq != self._seq
        if not new_frame and changed == self._seen_changed and geometry == self._geometry and \
                now - self._covers_at < COVER_S:
            return
        box = wgc.crop_box(frame.size, bounds, client)
        if box is None:
            self._hide("size")
            self._seq, self._seen_changed, self._geometry = frame.seq, changed, geometry
            return
        origin = (bounds[0] + box[0], bounds[1] + box[1])
        size = (box[2] - box[0], box[3] - box[1])
        if now - self._covers_at >= COVER_S or geometry != self._geometry:
            screen = (origin[0], origin[1], origin[0] + size[0], origin[1] + size[1])
            self._covers = cover_rects(viewer, screen, self.hwnd)
            self._covers_at = now
        self._seq, self._seen_changed, self._geometry = frame.seq, changed, geometry
        self._new_frame = new_frame
        if new_frame:
            self.counts["frames"] += 1
        started = time.perf_counter()
        view = frame.bgra[box[1]:box[3], box[0]:box[2]]
        chosen, shown, shares = st.visible(sets, view)
        compare_ms = (time.perf_counter() - started) * 1000
        self.counts["compare_ms"] += compare_ms
        if chosen is not None:
            shown = tuple(i for i in shown if not st.covered(chosen.patches[i].box, origin, self._covers))
        if chosen is None or not shown:
            why = "covered" if chosen is not None else ("no match" if sets else "no patches")
            self._hide(why, frame.seq, compare_ms, shares)
            return
        state = (chosen.serial, shown, origin, size)
        if state == self._shown:
            return
        self._draw(chosen, shown, origin, size, frame.seq, compare_ms, shares)

    def _free_dib(self) -> None:
        if self._dib is not None:
            dc, bitmap, old, _pixels, _size = self._dib
            _gdi32.SelectObject(dc, old)
            _gdi32.DeleteObject(bitmap)
            _gdi32.DeleteDC(dc)
            self._dib = None

    def _surface(self, size: tuple[int, int]) -> tuple[int, np.ndarray]:
        """The memory DC and its pixels (premultiplied BGRA, top row first) for a picture of *size*."""
        if self._dib is not None and self._dib[4] == size:
            return self._dib[0], self._dib[3]
        self._free_dib()
        width, height = size
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # top-down
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        screen = _user32.GetDC(None)
        try:
            dc = _gdi32.CreateCompatibleDC(screen)
            bitmap = _gdi32.CreateDIBSection(screen, ctypes.byref(info), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        finally:
            _user32.ReleaseDC(None, screen)
        if not bitmap or not bits.value:
            _gdi32.DeleteDC(dc)
            raise OSError("CreateDIBSection failed")
        old = _gdi32.SelectObject(dc, bitmap)
        buffer = (ctypes.c_ubyte * (width * height * 4)).from_address(bits.value)
        pixels = np.frombuffer(buffer, np.uint8).reshape(height, width, 4)
        self._dib = (dc, bitmap, old, pixels, size)
        return dc, pixels

    def _draw(self, chosen: st.PatchSet, shown: tuple[int, ...], origin: tuple[int, int], size: tuple[int, int],
              seq: int, compare_ms: float, shares: list[float]) -> None:
        started = time.perf_counter()
        before = self._shown
        same_picture = before is not None and before[0] == chosen.serial and before[1] == shown and before[3] == size
        dc, pixels = self._surface(size)
        if not same_picture:
            st.compose(size, [chosen.patches[i] for i in shown], pixels)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        screen = _user32.GetDC(None)
        try:
            ok = _user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wintypes.POINT(*origin)),
                                             ctypes.byref(wintypes.SIZE(*size)), dc,
                                             ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
        finally:
            _user32.ReleaseDC(None, screen)
        if before is None:
            _user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        self._shown = (chosen.serial, shown, origin, size)
        draw_ms = (time.perf_counter() - started) * 1000
        self.counts["draws" if not same_picture else "moves"] += 1
        self.counts["draw_ms"] += draw_ms
        self._note("show", seq=seq, new=int(self._new_frame), arrived=self._arrived.get(seq), set=chosen.serial,
                   shown=len(shown),
                   of=len(chosen.patches), ok=int(bool(ok)), moved=int(same_picture),
                   x=origin[0], y=origin[1], w=size[0], h=size[1], compare_ms=round(compare_ms, 2),
                   draw_ms=round(draw_ms, 2), worst=round(max(shares[i] for i in shown), 4) if shown else None,
                   least_hidden=round(min((v for i, v in enumerate(shares) if i not in shown), default=-1), 4))

    def _hide(self, why: str, seq: int | None = None, compare_ms: float = 0.0, shares: list[float] | None = None
              ) -> None:
        if self._shown is None:
            return
        _user32.ShowWindow(self.hwnd, SW_HIDE)
        self._shown = None
        self.counts["hides"] += 1
        self._note("hide", why=why, seq=seq, new=int(seq is not None and self._new_frame),
                   arrived=self._arrived.get(seq) if seq is not None else None,
                   compare_ms=round(compare_ms, 2),
                   least=round(min(shares), 4) if shares else None)
