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
* The patch under the pointer is left out too, so that the viewer's own pixels - the original - show there, once the
  pointer has rested on it the hover delay (`set_hover_delay`: ``Settings.hover_delay_ms``, 0 at once); it comes
  back once the pointer has gone (`seethrough.hovered`: its box and HOVER_IN_PX about it to hide it, HOVER_OUT_PX to
  show it again). Which one is left out is told to the Tk thread (`hovered`, with the key of the page whose patches
  the last look chose: `look_key`), whose right pane shows that bubble's words. The pointer is only read
  (`cursor_pos`, at every look: no hook, no input taken; the window stays click-through); it counts only over the
  viewer, not over a side pane nor over a window above the viewer.
* Its own thread runs the window and its message loop, and looks at the viewer's frames as they come: the capture
  tells it of each one (`wgc.add_listener`: an event set on the capture's thread), and it compares the frame there and
  then (`seethrough.visible`), with no wait for Tk. The Tk thread only hands it the patches of the page as they are
  lettered (`present`: immutable arrays under a lock). So a turn hides the old lettering at the first frame that
  shows another page, whatever Tk is doing.
* The side panes (`taslation.panes`; their pictures and their places from the Tk thread, `set_panes`) are two more
  layered windows of this thread's, topmost, never activated (WS_EX_NOACTIVATE), with no taskbar button: they lie on
  the viewer's ground at the capture area's outer edges, follow the viewer's moves as the lettering does, hide while
  it is minimised, hidden or cloaked and where a window above the viewer meets them; the lettering's switch on the
  left one hides the lettering only (`set_on`). The LEFT one (the controls) takes the clicks on its
  plates - no WS_EX_TRANSPARENT; a layered window passes on a click on a pixel of alpha 0, so between its rows and
  round them the viewer takes it -, answers WM_MOUSEACTIVATE with MA_NOACTIVATE (a click never activates it: the
  viewer keeps the keyboard), and keeps each click (`take_clicks`: where in the pane) for the Tk thread, which acts on
  it. The RIGHT one (the indicators, and the plates of the bubble last under the pointer) is click-through as the
  lettering's window is, but while the pointer is on one of the plates the Tk thread named (`set_panes`): then it
  takes the click as the left one does (`_right_plates`: WS_EX_TRANSPARENT off, at the look that finds the pointer
  there; on again at the look that finds it elsewhere), so that its words never keep a click from the viewer. The
  panes take no key, and send, post and press nothing either.
* Topmost, but never above a menu of TASlation's own: shown again or moved, the lettering's window and the panes go
  just under the lowest popup menu of this process's that is open (`own_menu`, `_raise`: the left pane's Menu, the
  one the taskbar button opens and their submenus), since a window made topmost again comes above every other topmost
  one, an open menu too. (A menu over the viewer is a window above it as well: the patches and the panes it meets are
  left out meanwhile, `cover_rects`.)

What it shows is decided by one rule (`taslation.seethrough`): a patch belongs to the pixels it was made from."""

from __future__ import annotations

import ctypes
import os
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
# the side panes: take the clicks on their plates (no WS_EX_TRANSPARENT; the right one only while the pointer is on
# one of its plates), never activated, no taskbar button
PANE_CLASS = "TASlationSeeThroughPane"
PANE_EX_STYLE = WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
IDC_ARROW = 32512
PANES = ("left", "right")
MENU_CLASS = "#32768"  # the window class of a popup menu (Tk's menus on Windows are TrackPopupMenu's)
CLICKS_KEPT = 32  # clicks on the side panes not taken yet by the Tk thread (`take_clicks`): the oldest go first

LOOK_S = 0.05  # with no frame coming, the window looks at the viewer this often (moved, minimised, covered, pointer)
HOVER_IN_PX, HOVER_OUT_PX = 4, 10  # the pointer this near a patch's box hides it, and it shows again once the pointer
# is farther than the second (px at 96 DPI, `seethrough.scaled`): no flicker at its edge
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
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    _user32.SetWindowLongW.restype = wintypes.LONG
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
    _user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    _user32.LoadCursorW.restype = wintypes.HANDLE
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.GetCursorPos.restype = wintypes.BOOL
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
    _user32.MonitorFromRect.restype = wintypes.HMONITOR
    _user32.GetLayeredWindowAttributes.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
                                                   ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wintypes.DWORD)]
    _user32.GetLayeredWindowAttributes.restype = wintypes.BOOL
    _user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowExW.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.WindowFromPoint.argtypes = [wintypes.POINT]
    _user32.WindowFromPoint.restype = wintypes.HWND
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int

MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTONEAREST, MDT_EFFECTIVE_DPI = 0, 2, 0
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
WS_EX_APPWINDOW, LWA_ALPHA = 0x00040000, 0x2
GW_OWNER = 4
DWMWA_DISALLOW_PEEK = 11
# the shell's windows a click on a taskbar button is made on: the taskbars (the primary's and the others'), a button's
# thumbnails (Windows 10's, and Windows 11's island that holds them)
SHELL_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd", "TaskListThumbnailWnd", "XamlExplorerHostIslandWindow")
_shcore: Any = None  # (shcore.dll, loaded at the first `viewer_dpi`)
_dwmapi: Any = None  # (dwmapi.dll, loaded at the first `no_peek`)


def virtual_screen() -> tuple[int, int, int, int]:
    """(left, top, width, height) of the virtual screen - every monitor's rectangle together; (0, 0, 0, 0) outside
    Windows."""
    if not IS_WINDOWS:
        return 0, 0, 0, 0
    metric = _user32.GetSystemMetrics
    return (int(metric(SM_XVIRTUALSCREEN)), int(metric(SM_YVIRTUALSCREEN)), int(metric(SM_CXVIRTUALSCREEN)),
            int(metric(SM_CYVIRTUALSCREEN)))


def window_facts(hwnd: int) -> dict[str, Any] | None:
    """How the top-level window *hwnd* is on the screen, read only (any thread): shown (``IsWindowVisible``),
    minimised, whether any part of its rectangle lies on a monitor (``MonitorFromRect``, MONITOR_DEFAULTTONULL), its
    layered alpha (0-255; None when it has none: opaque), a tool window (no taskbar button, not in Alt+Tab) or one
    marked for the taskbar, owned by another window, whether it has a taskbar button (shown, no tool window, and
    marked for the taskbar or owned by none: Windows' rule) and its title. None for no window. (TASlation's own window
    in see-through mode, `ui.seethrough`: never on a monitor, alpha 0, an application's window with its button.)"""
    if not IS_WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return None
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    on_monitor = bool(_user32.MonitorFromRect(ctypes.byref(rect), MONITOR_DEFAULTTONULL))
    ex = int(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
    alpha: int | None = None
    if ex & WS_EX_LAYERED:
        key, value, flags = wintypes.DWORD(0), ctypes.c_ubyte(255), wintypes.DWORD(0)
        if _user32.GetLayeredWindowAttributes(hwnd, ctypes.byref(key), ctypes.byref(value), ctypes.byref(flags)) \
                and flags.value & LWA_ALPHA:
            alpha = int(value.value)
    visible, tool, app = bool(_user32.IsWindowVisible(hwnd)), bool(ex & WS_EX_TOOLWINDOW), bool(ex & WS_EX_APPWINDOW)
    owned = bool(_user32.GetWindow(hwnd, GW_OWNER))
    title = ctypes.create_unicode_buffer(64)
    _user32.GetWindowTextW(hwnd, title, 64)
    return {"visible": visible, "iconic": bool(_user32.IsIconic(hwnd)),
            "on_monitor": on_monitor, "rect": (rect.left, rect.top, rect.right, rect.bottom), "alpha": alpha,
            "tool": tool, "app": app, "owned": owned, "button": visible and not tool and (app or not owned),
            "title": title.value}


def shell_at(point: tuple[int, int] | None) -> bool:
    """Whether the screen *point* lies on a taskbar or on a taskbar button's thumbnails (`SHELL_CLASSES`: the
    top-level window there, ``WindowFromPoint``), read only: where the pointer is as a taskbar button is clicked."""
    if not IS_WINDOWS or point is None:
        return False
    try:
        hwnd = _user32.WindowFromPoint(wintypes.POINT(int(point[0]), int(point[1])))
        root = _user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
        if not root:
            return False
        name = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(root, name, 64)
        return name.value in SHELL_CLASSES
    except OSError:
        return False


def no_peek(hwnd: int) -> bool:
    """The window *hwnd* left out of the taskbar's peek (``DWMWA_DISALLOW_PEEK``: the pointer resting on its
    thumbnail hides no other window to show it - TASlation's own window has nothing to show). Whether it was set."""
    global _dwmapi
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        if _dwmapi is None:
            _dwmapi = ctypes.WinDLL("dwmapi")
            _dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        value = wintypes.BOOL(True)
        return _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_DISALLOW_PEEK, ctypes.byref(value),
                                             ctypes.sizeof(value)) == 0
    except OSError:
        return False


def cursor_pos() -> tuple[int, int] | None:
    """Where the pointer is on the screen (screen pixels: the process is per-monitor DPI aware), read only -
    ``GetCursorPos``, no hook, nothing taken; None where it cannot be told. (The tools put their own in its place: they
    never move the pointer.)"""
    if not IS_WINDOWS:
        return None
    point = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(point)):
        return None
    return int(point.x), int(point.y)


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


_pane_clicks: dict[int, Any] = {}  # a left pane's window -> what takes its clicks: (x, y) in its own pixels


def _pane_proc(hwnd, message, wparam, lparam):  # type: ignore[no-untyped-def]
    if message == WM_MOUSEACTIVATE:
        return MA_NOACTIVATE  # (a click is taken, the window never activated: the viewer keeps the keyboard)
    if message == WM_LBUTTONDOWN:
        return 0
    if message == WM_LBUTTONUP:
        take = _pane_clicks.get(int(hwnd or 0))
        if take is not None:
            take(ctypes.c_short(int(lparam) & 0xFFFF).value, ctypes.c_short((int(lparam) >> 16) & 0xFFFF).value)
        return 0
    return _user32.DefWindowProcW(hwnd, message, wparam, lparam)


_PROC = WNDPROC(_proc) if IS_WINDOWS else None  # kept for the life of the process: the class points at it
_PANE_PROC = WNDPROC(_pane_proc) if IS_WINDOWS else None
_class_ready = False


def _register_class() -> bool:
    """The window classes of the lettering's window (click-through) and of the side panes (taking clicks)."""
    global _class_ready
    if _class_ready:
        return True
    instance = _kernel32.GetModuleHandleW(None)
    for name, proc, cursor in ((CLASS, _PROC, None), (PANE_CLASS, _PANE_PROC, IDC_ARROW)):
        wc = WNDCLASSW()
        wc.lpfnWndProc = proc
        wc.hInstance = instance
        wc.lpszClassName = name
        if cursor is not None:  # (the arrow over the controls, not whatever the viewer had last)
            wc.hCursor = _user32.LoadCursorW(None, ctypes.c_void_p(cursor))
        if not _user32.RegisterClassW(ctypes.byref(wc)) and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            return False
    _class_ready = True
    return True


def _make_dib(size: tuple[int, int]) -> tuple[int, int, int, np.ndarray]:
    """A memory DC with a 32-bit top-down DIB of *size* selected into it: (dc, bitmap, the DC's old bitmap, its
    pixels as BGRA, top row first); `_free_dib` lets it go."""
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
    return dc, bitmap, old, np.frombuffer(buffer, np.uint8).reshape(height, width, 4)


def _free_dib(dib: tuple[Any, ...]) -> None:
    dc, bitmap, old = dib[:3]
    _gdi32.SelectObject(dc, old)
    _gdi32.DeleteObject(bitmap)
    _gdi32.DeleteDC(dc)


def _layered(hwnd: int, dc: int, origin: tuple[int, int], size: tuple[int, int]) -> bool:
    """The layered window *hwnd* drawn from the memory DC *dc* (premultiplied BGRA of *size*) at *origin*."""
    blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
    screen = _user32.GetDC(None)
    try:
        return bool(_user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(wintypes.POINT(*origin)),
                                                ctypes.byref(wintypes.SIZE(*size)), dc,
                                                ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend),
                                                ULW_ALPHA))
    finally:
        _user32.ReleaseDC(None, screen)


def cover_rects(viewer: int, client: st.Box, own: int | frozenset[int] | set[int] = 0) -> list[st.Box]:
    """The screen rectangles of the windows above the viewer's window *viewer* that meet its client area *client*
    (screen pixels): shown, not minimised nor cloaked, not click-through (the see-through windows, *own* - one or a
    set -, never count), by the rectangle the compositor shows of them (without the invisible resize borders)."""
    from . import windows

    mine = {int(own)} if isinstance(own, int) else {int(h) for h in own}
    out: list[st.Box] = []
    root = _user32.GetAncestor(viewer, GA_ROOT) or viewer
    above = _user32.GetWindow(root, GW_HWNDPREV)
    for _ in range(MAX_ABOVE):
        if not above:
            break
        h = int(above)
        if (h not in mine and _user32.IsWindowVisible(h) and not _user32.IsIconic(h) and not windows._is_cloaked(h)
                and not _user32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TRANSPARENT):
            try:
                r = windows._frame_bounds(h)
            except Exception:  # noqa: BLE001 - a window gone meanwhile
                r = None
            if r is not None and r[0] < client[2] and client[0] < r[2] and r[1] < client[3] and client[1] < r[3]:
                out.append(tuple(int(v) for v in r))  # type: ignore[arg-type]
        above = _user32.GetWindow(above, GW_HWNDPREV)
    return out


def own_menu() -> int:
    """The lowest popup menu of this process's that is on the screen (Windows' menu class, MENU_CLASS: the
    notification-area icon's menu, the left pane's Menu, a submenu of theirs), 0 while none is."""
    if not IS_WINDOWS:
        return 0
    me, lowest, hwnd = os.getpid(), 0, None
    for _ in range(64):
        hwnd = _user32.FindWindowExW(None, hwnd, MENU_CLASS, None)  # (top to bottom in the order of the windows)
        if not hwnd:
            break
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me and _user32.IsWindowVisible(hwnd):
            lowest = int(hwnd)
    return lowest


def _raise(hwnd: int, at: tuple[int, int] | None = None) -> None:
    """*hwnd* (the lettering's window, a side pane) to the top of the topmost windows, moved to the screen point *at*
    as well (None: where it is) - but just under a menu of this process's that is open (`own_menu`), never above it;
    not activated."""
    menu = own_menu()
    x, y = at if at is not None else (0, 0)
    flags = SWP_NOSIZE | SWP_NOACTIVATE | (0 if at is not None else SWP_NOMOVE)
    _user32.SetWindowPos(hwnd, menu or HWND_TOPMOST, x, y, 0, 0, flags)


class SeeThrough:
    """The see-through window and its thread (see the module's notes). Made with `start` (None where there can be
    none), told which viewer to lie over (`follow`), handed the patches of the pages (`present`, `forget`, `clear`),
    hidden and shown by the reader's switch (`set_on`), handed the side panes (`set_panes`; the clicks on them:
    `take_clicks`) and the hover delay (`set_hover_delay`), asked which patch is left out under the pointer
    (`hovered`, `look_key`), ended with `close`. Its notes (`notes`) are numbers and flags only: when it showed what, from
    which frame, and how long its work took."""

    def __init__(self) -> None:
        self.hwnd = 0
        self.panes: dict[str, int] = {}  # "left", "right" -> the side pane's window
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
                       "compare_ms": 0.0, "draw_ms": 0.0, "pane_draws": 0, "pane_moves": 0, "pane_hides": 0,
                       "clicks": 0, "hovers": 0}
        # the side panes: side -> (picture serial, premultiplied BGRA, box in the viewer's client pixels, the boxes of
        # its plates that take a click) or None, from the Tk thread; what shows of each, (serial, screen origin, size)
        # or None, the window thread's own
        self._pane_want: dict[str, tuple[int, np.ndarray, st.Box, tuple[st.Box, ...]] | None] = {
            side: None for side in PANES}
        self._pane_serial = 0
        self._pane_shown: dict[str, tuple[int, tuple[int, int], tuple[int, int]] | None] = {s: None for s in PANES}
        self._clicks: deque[tuple[str, int, int, float]] = deque(maxlen=CLICKS_KEPT)
        # the window thread's own state
        self._shown: tuple[Any, ...] | None = None  # (set serial, indices, origin, size) on show; None: hidden
        self._seq = -1
        self._seen_changed = -1
        self._covers: list[st.Box] = []
        self._covers_at = 0.0
        self._geometry: tuple[Any, ...] | None = None
        self._new_frame = False  # whether the look under way was started by a frame not looked at before
        self._dib: tuple[int, int, int, np.ndarray, tuple[int, int]] | None = None  # (dc, bitmap, old, pixels, size)
        self._pointer: tuple[int, int] | None = None  # where the pointer was at the last look (screen pixels)
        self._hover_box: st.Box | None = None  # the box of the patch left out under the pointer
        self._hover_delay = 0.0  # s the pointer rests on a patch before it is left out (`set_hover_delay`)
        self._hover_wait: tuple[st.Box, float] | None = None  # (the patch the pointer came to, since when)
        self._hovered: tuple[int, st.Box] | None = None  # (its set's key, its box) of the patch left out, for Tk
        self._look_key: int | None = None  # the key of the set the last look chose (None: none), for Tk
        self._right_takes = False  # the right pane takes clicks now (the pointer on one of its plates)
        self._dpi = st.BASE_DPI  # the viewer's (`viewer_dpi`), at each change of its place or size
        self._last_look: tuple[Any, ...] | None = None  # (set, patches shown but for the pointer, shares, frame, ms)

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
        """The reader's switch (the left pane's Lettering): the lettering shown (*on*) or hidden; the patches are
        kept."""
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

    def set_hover_delay(self, ms: float) -> None:
        """How long the pointer rests on a patch before it is left out (`Settings.hover_delay_ms`; 0: at once)."""
        self._hover_delay = max(0.0, float(ms or 0) / 1000)

    def hovered(self) -> tuple[int, st.Box] | None:
        """(the key of its page's set, its box) of the patch left out under the pointer at the last look; None while
        none is."""
        return self._hovered

    def look_key(self) -> int | None:
        """The key of the set the last look chose (the page whose patches match the viewer's frame); None for none."""
        return self._look_key

    def set_panes(self, left: tuple[Any, ...] | None, right: tuple[Any, ...] | None) -> None:
        """The side panes as they are to be: each (its picture - premultiplied BGRA (H, W, 4), not changed after -,
        its box in the viewer's client pixels[, the boxes of its plates that take a click, in its picture's pixels:
        the right one takes clicks there alone]) or None (hidden). The same picture handed again is not drawn
        again."""
        with self._lock:
            changed = False
            for side, want in (("left", left), ("right", right)):
                old = self._pane_want.get(side)
                if want is None:
                    new = None
                else:
                    bgra, box = want[0], want[1]
                    plates = tuple(tuple(int(v) for v in b) for b in want[2]) if len(want) > 2 else ()
                    if old is not None and old[1] is bgra:
                        serial = old[0]
                    else:
                        self._pane_serial += 1
                        serial = self._pane_serial
                    new = (serial, bgra, tuple(int(v) for v in box), plates)
                if (None if old is None else (old[0], old[2])) != (None if new is None else (new[0], new[2])):
                    self._pane_want[side] = new  # type: ignore[assignment]
                    changed = True
            if changed:
                self._changed += 1
        if changed:
            self._wake.set()

    def take_clicks(self) -> list[tuple[str, int, int, float]]:
        """The clicks on the side panes since the last call: (side, x, y in the pane's picture, when), the oldest
        first."""
        out = []
        while self._clicks:
            try:
                out.append(self._clicks.popleft())
            except IndexError:
                break
        return out

    def pane_shown(self, side: str) -> tuple[int, int, int, int] | None:
        """The screen box of the side pane *side* as it shows now; None while it is hidden."""
        shown = self._pane_shown.get(side)
        if shown is None:
            return None
        (x, y), (w, h) = shown[1], shown[2]
        return x, y, x + w, y + h

    def own_windows(self) -> frozenset[int]:
        """The see-through windows: the lettering's and the side panes'."""
        return frozenset(h for h in (self.hwnd, *self.panes.values()) if h)

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

    def _clicked(self, side: str, x: int, y: int) -> None:
        """(the window thread, from a side pane's window procedure) a click on the pane, kept for the Tk thread."""
        self._clicks.append((side, int(x), int(y), time.monotonic()))
        self.counts["clicks"] += 1
        self._note("click", side=side, x=int(x), y=int(y))

    def _run(self) -> None:
        instance = _kernel32.GetModuleHandleW(None)
        hwnd = _user32.CreateWindowExW(EX_STYLE, CLASS, "TASlation see-through", WS_POPUP, 0, 0, 1, 1, None, None,
                                       instance, None)
        self.hwnd = int(hwnd or 0)
        if self.hwnd:  # the side panes: the left one takes clicks; the right one is click-through as this one is but
            # while the pointer is on one of its plates (`_right_plates`)
            for side, ex in (("left", PANE_EX_STYLE), ("right", EX_STYLE)):
                pane = int(_user32.CreateWindowExW(ex, PANE_CLASS, "TASlation pane", WS_POPUP, 0, 0, 1, 1, None, None,
                                                   instance, None) or 0)
                if pane:
                    self.panes[side] = pane
                    _pane_clicks[pane] = lambda x, y, s=side: self._clicked(s, x, y)
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
            self._panes_hide("closed")
            self._free_dib()
            for pane in self.panes.values():
                _pane_clicks.pop(pane, None)
                _user32.DestroyWindow(pane)
            self.panes = {}
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = 0

    def _step(self) -> None:
        from . import windows

        with self._lock:
            viewer, on, changed = self._viewer, self._on, self._changed
            sets = list(self._store.sets)
            panes = dict(self._pane_want)
        self.counts["looks"] += 1
        if not viewer:
            self._nothing("no viewer")
            return
        if not _user32.IsWindow(viewer):
            self._nothing("gone")
            return
        if _user32.IsIconic(viewer) or not _user32.IsWindowVisible(viewer) or windows._is_cloaked(viewer):
            self._nothing("minimised")
            return
        frame = wgc.peek(viewer)
        if frame is None:
            self._nothing("no frame")
            return
        client = windows._client_box(viewer)
        bounds = windows._frame_bounds(viewer)
        now = time.monotonic()
        geometry = (client, bounds, frame.size)
        new_frame = frame.seq != self._seq
        pointer = cursor_pos()
        moved, self._pointer = pointer != self._pointer, pointer
        if not new_frame and changed == self._seen_changed and geometry == self._geometry and \
                now - self._covers_at < COVER_S:
            self._right_plates(pointer, panes)
            waiting = self._hover_wait is not None  # (a patch the pointer rests on, to be left out once its wait is over)
            if (moved or waiting) and on and self._last_look is not None:  # only the pointer moved: the last look,
                self._new_frame = False  # less the patch under it now (no frame compared again)
                self._show_look(*self._last_look)
            return
        box = wgc.crop_box(frame.size, bounds, client)
        if box is None:
            self._nothing("size")
            self._seq, self._seen_changed, self._geometry = frame.seq, changed, geometry
            self._last_look = None
            return
        origin = (bounds[0] + box[0], bounds[1] + box[1])
        size = (box[2] - box[0], box[3] - box[1])
        if now - self._covers_at >= COVER_S or geometry != self._geometry:
            screen = (origin[0], origin[1], origin[0] + size[0], origin[1] + size[1])
            self._covers = cover_rects(viewer, screen, self.own_windows())
            self._covers_at = now
        if geometry != self._geometry:
            self._dpi = viewer_dpi(viewer)
        self._seq, self._seen_changed, self._geometry = frame.seq, changed, geometry
        self._place_panes(panes, origin, size)
        self._right_plates(pointer, panes)
        if not on:  # (the left pane's Lettering switched off: the lettering hidden, the side panes as they are)
            self._last_look = None
            self._unhover()
            self._hide("off")
            return
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
        self._last_look = (chosen, shown, shares, frame.seq, compare_ms, origin, size, bool(sets))
        self._show_look(*self._last_look)

    def _show_look(self, chosen: st.PatchSet | None, shown: tuple[int, ...], shares: list[float], seq: int,
                   compare_ms: float, origin: tuple[int, int], size: tuple[int, int], any_sets: bool) -> None:
        """What a look found shown (*shown* of the set *chosen*, none covered), less the patch under the pointer."""
        self._look_key = chosen.key if chosen is not None else None
        if chosen is None or not shown:
            why = "covered" if chosen is not None else ("no match" if any_sets else "no patches")
            self._unhover()
            self._hide(why, seq, compare_ms, shares)
            return
        under = self._under_pointer(chosen, shown, origin)
        if under is not None:
            shown = tuple(i for i in shown if i != under)
            if not shown:
                self._hide("hover", seq, compare_ms, shares)
                return
        state = (chosen.serial, shown, origin, size)
        if state == self._shown:
            return
        self._draw(chosen, shown, origin, size, seq, compare_ms, shares)

    def _under_pointer(self, chosen: st.PatchSet, shown: tuple[int, ...], origin: tuple[int, int]) -> int | None:
        """The one of the patches *shown* the pointer is over (`seethrough.hovered`, HOVER_IN_PX and HOVER_OUT_PX at
        the viewer's DPI), None for none - nor while the pointer is over a side pane or a window above the viewer.
        A patch the pointer comes to is left out once it has rested there the hover delay (`set_hover_delay`; the
        looks go on meanwhile, `_step`); one left out stays so while the pointer is near it, as ever."""
        point = self._pointer
        index, box = None, None
        if point is not None and not self._pointer_elsewhere(point):
            boxes = [chosen.patches[i].box for i in shown]
            at = st.hovered(boxes, (point[0] - origin[0], point[1] - origin[1]), self._hover_box,
                            st.scaled(HOVER_IN_PX, self._dpi), st.scaled(HOVER_OUT_PX, self._dpi))
            if at is not None:
                index, box = shown[at], boxes[at]
        if box is not None and box != self._hover_box and self._hover_delay > 0:
            now = time.monotonic()
            if self._hover_wait is None or self._hover_wait[0] != box:
                self._hover_wait = (box, now)
            if now - self._hover_wait[1] < self._hover_delay:
                self._set_hover(None)  # (the one left out before, if any, is back: the pointer has left it)
                return None
        self._hover_wait = None
        self._set_hover(box, chosen.key)
        return index

    def _unhover(self) -> None:
        self._hover_wait = None
        self._set_hover(None)

    def _pointer_elsewhere(self, point: tuple[int, int]) -> bool:
        """Whether the pointer at *point* (screen pixels) is over a side pane or a window above the viewer."""
        x, y = point
        boxes = [self.pane_shown(side) for side in PANES] + list(self._covers)
        return any(b is not None and b[0] <= x < b[2] and b[1] <= y < b[3] for b in boxes)

    def _set_hover(self, box: st.Box | None, key: int | None = None) -> None:
        self._hovered = (int(key), box) if box is not None and key is not None else None
        if box == self._hover_box:
            return
        self._hover_box = box
        if box is not None:
            self.counts["hovers"] += 1
        self._note("hover", on=int(box is not None))

    def _nothing(self, why: str) -> None:
        """Nothing to lie over (no viewer, gone, minimised, no frame, no size): the lettering and the panes hidden."""
        self._hide(why)
        self._panes_hide(why)
        self._look_key = None
        self._unhover()

    def _right_plates(self, point: tuple[int, int] | None, panes: dict[str, Any]) -> None:
        """The right pane takes a click while the pointer at *point* (screen pixels) is on one of its plates that
        take one (WS_EX_TRANSPARENT off), and lets every other one through to the viewer (on), as the lettering's
        window does."""
        hwnd = self.panes.get("right", 0)
        want, shown = panes.get("right"), self._pane_shown.get("right")
        takes = False
        if hwnd and point is not None and want is not None and shown is not None and shown[0] == want[0] and want[3]:
            x, y = point[0] - shown[1][0], point[1] - shown[1][1]
            takes = any(b[0] <= x < b[2] and b[1] <= y < b[3] for b in want[3])
        self._right_take(takes)

    def _right_take(self, takes: bool) -> None:
        hwnd = self.panes.get("right", 0)
        if takes == self._right_takes or not hwnd:
            return
        style = int(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TRANSPARENT) if takes else (style | WS_EX_TRANSPARENT))
        self._right_takes = takes
        self._note("plates", on=int(takes))

    def _free_dib(self) -> None:
        if self._dib is not None:
            _free_dib(self._dib)
            self._dib = None

    def _surface(self, size: tuple[int, int]) -> tuple[int, np.ndarray]:
        """The memory DC and its pixels (premultiplied BGRA, top row first) for a picture of *size*."""
        if self._dib is not None and self._dib[4] == size:
            return self._dib[0], self._dib[3]
        self._free_dib()
        dc, bitmap, old, pixels = _make_dib(size)
        self._dib = (dc, bitmap, old, pixels, size)
        return dc, pixels

    # ------------------------------------------------------------------ the side panes (the window's thread)
    def _place_panes(self, panes: dict[str, Any], origin: tuple[int, int], size: tuple[int, int]) -> None:
        """Each side pane where the Tk thread put it on the viewer's client area (at *origin* on the screen, *size*),
        or hidden: none asked for, beyond the client area, or a window above the viewer meets it."""
        for side in PANES:
            want = panes.get(side)
            hwnd = self.panes.get(side, 0)
            if want is None or not hwnd:
                self._pane_hide(side, "none")
                continue
            serial, bgra, box = want[:3]
            height, width = bgra.shape[:2]
            if box[0] < 0 or box[1] < 0 or box[0] + width > size[0] or box[1] + height > size[1]:
                self._pane_hide(side, "beyond")
                continue
            if st.covered((box[0], box[1], box[0] + width, box[1] + height), origin, self._covers):
                self._pane_hide(side, "covered")
                continue
            self._pane_draw(side, hwnd, serial, bgra, (origin[0] + box[0], origin[1] + box[1]))

    def _pane_draw(self, side: str, hwnd: int, serial: int, bgra: np.ndarray, at: tuple[int, int]) -> None:
        before = self._pane_shown.get(side)
        size = (int(bgra.shape[1]), int(bgra.shape[0]))
        if before is not None and before[0] == serial and before[1] == at:
            return
        if before is None or before[0] != serial:  # a new picture: drawn through a DIB of its own, let go at once
            dib = _make_dib(size)
            try:
                dib[3][:] = bgra
                _layered(hwnd, dib[0], at, size)
            finally:
                _free_dib(dib)
            self.counts["pane_draws"] += 1
        else:  # the same picture moved with the viewer
            _raise(hwnd, at)
            self.counts["pane_moves"] += 1
        if before is None:
            _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            _raise(hwnd)
        self._pane_shown[side] = (serial, at, size)
        self._note("pane", side=side, set=serial, x=at[0], y=at[1], w=size[0], h=size[1])

    def _pane_hide(self, side: str, why: str) -> None:
        if self._pane_shown.get(side) is None:
            return
        hwnd = self.panes.get(side, 0)
        if hwnd:
            _user32.ShowWindow(hwnd, SW_HIDE)
        if side == "right":
            self._right_take(False)
        self._pane_shown[side] = None
        self.counts["pane_hides"] += 1
        self._note("pane_hide", side=side, why=why)

    def _panes_hide(self, why: str) -> None:
        for side in PANES:
            self._pane_hide(side, why)

    def _draw(self, chosen: st.PatchSet, shown: tuple[int, ...], origin: tuple[int, int], size: tuple[int, int],
              seq: int, compare_ms: float, shares: list[float]) -> None:
        started = time.perf_counter()
        before = self._shown
        same_picture = before is not None and before[0] == chosen.serial and before[1] == shown and before[3] == size
        dc, pixels = self._surface(size)
        if not same_picture:
            st.compose(size, [chosen.patches[i] for i in shown], pixels)
        ok = _layered(self.hwnd, dc, origin, size)
        if before is None:
            _user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            _raise(self.hwnd)
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
