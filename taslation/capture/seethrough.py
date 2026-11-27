"""The see-through window (Windows only): TASlation's lettering laid over the viewer's own window, which goes on
taking every click and key itself.

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
  the viewer's ground at the capture area's outer edges, hide at once at any change of the viewer's place or size
  (this thread's own hook on its moves, and every look: `_rect_tick`) and come back once it has been at rest for
  PANE_REST_S, hide while it is minimised, hidden or cloaked and where a window above the viewer meets them; the
  lettering's switch on the left one hides the lettering only (`set_on`). The LEFT one (the controls) takes the clicks on its
  plates - no WS_EX_TRANSPARENT; a layered window passes on a click on a pixel of alpha 0, so between its rows and
  round them the viewer takes it -, answers WM_MOUSEACTIVATE with MA_NOACTIVATE (a click never activates it: the
  viewer keeps the keyboard), and keeps each click (`take_clicks`: where in the pane) for the Tk thread, which acts on
  it. A click is a press and its release on the pane itself: a press that began on the viewer - a page some viewers
  drag along with the pointer - fires nothing where it is let go, and a press on a pane let go elsewhere is
  forgotten (`_pane_proc`, `_pane_presses`). The RIGHT one (the indicators, and the plates of the bubble last under
  the pointer) is click-through as the lettering's window is, but while the pointer is on one of the plates the Tk
  thread named (`set_panes`): then it takes the click as the left one does (`_right_plates`: WS_EX_TRANSPARENT off, at
  the look that finds the pointer there; on again at the look that finds it elsewhere; neither while the button is
  held, `button_down`), so that its words never keep a click from the viewer. The panes take no key, and send, post
  and press nothing either.
* Editing (`set_ground`: the Tk thread is editing - Reader mode off -; `set_edit`: the regions of the page on show,
  `seethrough.Marks`): the lettering's window takes the mouse over the viewer's whole client area - no
  WS_EX_TRANSPARENT then, its window procedure answering HTCLIENT and MA_NOACTIVATE (a click never activates it: the
  viewer keeps the keyboard, and gets the keys alone), the page drawn at alpha EDIT_ALPHA wherever nothing else is,
  whatever page the viewer shows (one with no marks: `seethrough.GROUND`); the viewer's title bar and frame stay its
  own, and so do the windows over the viewer (alpha 0 there: `edit_compose`'s holes). The wheel, the middle and side
  buttons reach nothing. Every box is outlined in its colour and numbered, the one under the pointer in the stronger
  outline, the one chosen alone in it with its corner handles too; the patches of the box under the pointer give way
  to the original once it has rested there the hover delay, as in Reader mode (`_edit_out`: not while a press is
  held, nor for the box in the editor). A press takes hold of a box (the capture besides, which a window not in
  front has only over its own pixels); a drag moves the box (those chosen with it), a drag on a corner resizes it, a
  click on a box's number plate types its place in the reading order (a drag from it moves the box), a drag on the
  empty ground draws a rectangle, a click there is kept as no more than that, a right click gives a press up (and a
  region to add: an "add" with no box), and the release is kept for the Tk thread (`take_edits`: a click, a double
  click - the second press on the same box within the system's double-click time and reach, `double_click`: the class
  has no CS_DBLCLKS -, a plate, a move, a resize, a rectangle drawn - "draw", or "add" for Add area -, a click on the
  ground), which acts on it. In Reader mode, marks of no box while a region is to be added (`Marks.adding`) have
  the whole page take the mouse for that rectangle alone. The box in the editor and one being dragged keep their
  patches whatever the frame says; the one whose original is shown has none. A press the window holds is no press
  on the viewer (`pressing`: frames go on being taken). The thread then waits for its messages too
  (``MsgWaitForMultipleObjectsEx``; `_poke` posts one to its own window), so a drag follows the pointer at once. It
  sends, posts and presses nothing to another window.
* The Insert key (`set_add_key`: ``Settings.add_area_key``; the Tk thread's Add area, `ui.see_edit`) and the Delete
  key (`set_delete_key`: wanted only while editing with a region chosen; the Tk thread drops it) are the keys
  TASlation takes: hot keys of the lettering's window (``RegisterHotKey``, each alone - Shift+Insert, Ctrl+Insert,
  Shift+Delete and the like stay the viewer's - with MOD_NOREPEAT), held only while wanted and the viewer is the
  window in front and not minimised (`_key_tick`, at every look: never a keyboard hook), let go at the look that finds
  another program or a dialog of TASlation's in front, the viewer minimised or gone, or the key not wanted (the
  setting off; no region chosen any more). Each press is kept for the Tk thread (`take_keys`, `take_deletes`;
  ``WM_HOTKEY``, `_hot_key`), and a rectangle being drawn to add a region (Insert), or a box held (Delete), is given
  up there and then. A registration that fails (another program holds the key) is harmless: counted, logged once,
  and not tried again until the key is let go of and wanted once more.
* Topmost, but never above a menu of TASlation's own: shown again or moved, the lettering's window and the panes go
  just under the lowest popup menu of this process's that is open (`own_menu`, `_raise`: the left pane's Menu, the
  one the taskbar button opens and their submenus), since a window made topmost again comes above every other topmost
  one, an open menu too. (A menu over the viewer is a window above it as well: the patches and the panes it meets are
  left out meanwhile, `cover_rects`.)

What it shows is decided by one rule (`taslation.seethrough`): a patch belongs to the pixels it was made from."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from collections import deque
from dataclasses import replace
from typing import Any

import numpy as np

from .. import seethrough as st
from . import wgc

IS_WINDOWS = sys.platform == "win32"
log = logging.getLogger(__name__)

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
# Editing (`set_ground`, `set_edit`): the lettering's window takes the mouse over the whole page (no WS_EX_TRANSPARENT
# then, its window procedure answering HTCLIENT): a press, the pointer's moves while it is held and the release, a
# right click to give a drag up; the pointer shows what a press there does (the system's cursors)
WM_MOUSEMOVE, WM_RBUTTONDOWN, WM_SETCURSOR, WM_CAPTURECHANGED = 0x0200, 0x0204, 0x0020, 0x0215
# the rest of the mouse's messages (the class has no CS_DBLCLKS: no double clicks), none of which reaches anything
# while editing: the right button's release, the middle and side buttons, the wheels
WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MOUSEWHEEL = 0x0205, 0x0207, 0x0208, 0x020A
WM_XBUTTONDOWN, WM_XBUTTONUP, WM_MOUSEHWHEEL = 0x020B, 0x020C, 0x020E
SWALLOWED = frozenset({WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP, WM_MOUSEWHEEL, WM_MOUSEHWHEEL})
SIDE_BUTTONS = frozenset({WM_XBUTTONDOWN, WM_XBUTTONUP})  # (answered TRUE: no WM_APPCOMMAND - Back, Forward - made)
HTCLIENT, MK_SHIFT, WM_APP = 1, 0x0004, 0x8000
QS_ALLINPUT, MWMO_INPUTAVAILABLE = 0x04FF, 0x0004
VK_LBUTTON, VK_RBUTTON, SM_SWAPBUTTON = 0x01, 0x02, 23
CURSOR_IDS = {"move": 32649, "drag": 32646, "nw": 32642, "se": 32642, "ne": 32643, "sw": 32643, "add": 32515,
              st.PLATE: 32513, None: IDC_ARROW}  # IDC_HAND (a click chooses, a double click edits), IDC_SIZEALL,
# IDC_SIZENWSE, IDC_SIZENESW, IDC_CROSS (a rectangle drawn), IDC_IBEAM (a number plate: a click types its place)
EDITS_KEPT = 64  # presses on the regions not taken yet by the Tk thread (`take_edits`)
# a double click on a box (`double_click`): the second press within the system's double-click time of the first and
# within its reach (GetDoubleClickTime, SM_CXDOUBLECLK, SM_CYDOUBLECLK), these where the system gives none
SM_CXDOUBLECLK, SM_CYDOUBLECLK = 36, 37
DOUBLE_CLICK_S, DOUBLE_CLICK_PX = 0.5, 4
# the Insert key (`set_add_key`) and the Delete key (`set_delete_key`): hot keys of the lettering's window while the
# viewer is in front (`_key_tick`)
WM_HOTKEY, VK_INSERT, VK_DELETE, MOD_NOREPEAT = 0x0312, 0x2D, 0x2E, 0x4000
HOTKEY_ID, DELETE_ID = 0x0A11, 0x0A12  # (an application's hot keys: 0x0000-0xBFFF)
KEYS_KEPT = 16  # presses of a key not taken yet by the Tk thread (`take_keys`, `take_deletes`)
PANES = ("left", "right")
MENU_CLASS = "#32768"  # the window class of a popup menu (Tk's menus on Windows are TrackPopupMenu's)
CLICKS_KEPT = 32  # clicks on the side panes not taken yet by the Tk thread (`take_clicks`): the oldest go first

LOOK_S = 0.05  # with no frame coming, the window looks at the viewer this often (moved, minimised, covered, pointer)
HOVER_IN_PX, HOVER_OUT_PX = 4, 10  # the pointer this near a patch's box hides it, and it shows again once the pointer
# is farther than the second (px at 96 DPI, `seethrough.scaled`): no flicker at its edge
COVER_S = 0.1  # the windows over the viewer are looked for at most this often
SIZING_IN_PX = 4  # a press this near inside the viewer's frame edge sizes it too (`on_sizing_border`, px at 96 DPI)
PANE_REST_S = 0.3  # the side panes come back once the viewer's window has kept its place and size so long (`_rect_tick`)
MAX_ABOVE = 512  # the order of the windows is walked this far up from the viewer
LOG_KEPT = 50000  # notes kept in memory for the tools (`notes`)
WHERE_KEPT = 64  # (`why_not_shown`) the patches of the set chosen whose differing pixels a look places, at the most
REPORT_FPS_S = 5.0  # (`report_facts`) the viewer's frames per second are counted over so many seconds
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
    _user32.SetCapture.argtypes = [wintypes.HWND]
    _user32.SetCapture.restype = wintypes.HWND
    _user32.ReleaseCapture.argtypes = []
    _user32.ReleaseCapture.restype = wintypes.BOOL
    _user32.GetCapture.argtypes = []
    _user32.GetCapture.restype = wintypes.HWND
    _user32.SetCursor.argtypes = [wintypes.HANDLE]
    _user32.SetCursor.restype = wintypes.HANDLE
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.MsgWaitForMultipleObjectsEx.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                                    wintypes.DWORD]
    _user32.MsgWaitForMultipleObjectsEx.restype = wintypes.DWORD
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND

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


def on_sizing_border(point: tuple[int, int] | None, outer: st.Box, bounds: st.Box, inner: int) -> bool:
    """(pure) Whether the screen point *point* lies where a press sizes a window: inside its rectangle *outer*
    (``GetWindowRect``: the resize border Windows keeps unseen round its frame included) and outside its frame as seen,
    *bounds* (the DWM extended frame bounds), or within *inner* px inside that frame's top edge (where the frame has no
    unseen border: a browser takes that band for sizing)."""
    if point is None:
        return False
    x, y = point
    if not (outer[0] <= x < outer[2] and outer[1] <= y < outer[3]):
        return False
    return x < bounds[0] or x >= bounds[2] or y < bounds[1] + inner or y >= bounds[3]


def button_down() -> bool:
    """Whether the mouse's primary button is held down now (``GetAsyncKeyState``; a mouse with its buttons swapped
    for the left hand counted), read only - no hook, nothing taken; False outside Windows. (The tools put their own
    in its place, as for `cursor_pos`.)"""
    if not IS_WINDOWS:
        return False
    button = VK_RBUTTON if _user32.GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON
    return bool(_user32.GetAsyncKeyState(button) & 0x8000)


def viewer_in_front(viewer: int) -> bool:
    """Whether the viewer's window *viewer* is the window in front - it, or a window of its own (a popup it owns) -
    and not minimised, read only (``GetForegroundWindow``); False while a window of TASlation's (a dialog, a menu) or
    another program's is."""
    if not IS_WINDOWS or not viewer:
        return False
    from . import windows

    if not _user32.IsWindow(viewer) or _user32.IsIconic(viewer):
        return False
    front = int(_user32.GetForegroundWindow() or 0)
    return bool(front) and windows.foreground_owner(front, viewer) == "viewer"


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


_edit_hooks: dict[int, Any] = {}  # the lettering's window -> what makes editing's messages (`SeeThrough._edit_message`)
_key_hooks: dict[int, Any] = {}  # the lettering's window -> what takes its hot keys' presses (`SeeThrough._hot_key`)


def double_click() -> tuple[float, int, int]:
    """The system's double click: (the most seconds from one press to the next, the most px across and down between
    them), DOUBLE_CLICK_S and DOUBLE_CLICK_PX where it gives none."""
    seconds, across, down = DOUBLE_CLICK_S, DOUBLE_CLICK_PX, DOUBLE_CLICK_PX
    if IS_WINDOWS:
        try:
            ms = int(_user32.GetDoubleClickTime() or 0)
            seconds = ms / 1000 if ms > 0 else seconds
        except (AttributeError, OSError):
            pass
        try:
            across = int(_user32.GetSystemMetrics(SM_CXDOUBLECLK) or 0) or across
            down = int(_user32.GetSystemMetrics(SM_CYDOUBLECLK) or 0) or down
        except (AttributeError, OSError):
            pass
    return seconds, across, down


def _taken(kept: deque[Any]) -> list[Any]:
    """What *kept* holds, taken out of it, the oldest first (another thread appends meanwhile)."""
    out = []
    while kept:
        try:
            out.append(kept.popleft())
        except IndexError:
            break
    return out


def _proc(hwnd, message, wparam, lparam):  # type: ignore[no-untyped-def]
    if message == WM_HOTKEY:
        take = _key_hooks.get(int(hwnd or 0))
        if take is not None:
            take(int(wparam or 0))
        return 0
    hook = _edit_hooks.get(int(hwnd or 0))
    if hook is not None:
        answer = hook(message, wparam, lparam)
        if answer is not None:
            return answer
    if message == WM_NCHITTEST:
        return HTTRANSPARENT
    if message == WM_MOUSEACTIVATE:
        return MA_NOACTIVATE
    return _user32.DefWindowProcW(hwnd, message, wparam, lparam)


_pane_clicks: dict[int, Any] = {}  # a left pane's window -> what takes its clicks: (x, y) in its own pixels
# a side pane's window -> when the left button was pressed on it (`_pane_proc`): a release is a click only after a
# press on the pane itself, so that a press that began on the viewer - a page dragged with the pointer - and ends on a
# pane's control fires nothing; one whose release went elsewhere is forgotten (`SeeThrough._pane_presses`)
_pane_downs: dict[int, float] = {}
PRESS_STALE_S = 0.25  # a press on a pane is forgotten once the button is up, the pointer off the pane, so long after


def _pane_proc(hwnd, message, wparam, lparam):  # type: ignore[no-untyped-def]
    if message == WM_MOUSEACTIVATE:
        return MA_NOACTIVATE  # (a click is taken, the window never activated: the viewer keeps the keyboard)
    if message == WM_LBUTTONDOWN:
        _pane_downs[int(hwnd or 0)] = time.monotonic()
        return 0
    if message == WM_LBUTTONUP:
        pressed = _pane_downs.pop(int(hwnd or 0), None)
        take = _pane_clicks.get(int(hwnd or 0))
        if take is not None and pressed is not None:
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


def _meets(a: st.Box, b: st.Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


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
                       "clicks": 0, "hovers": 0, "keys": 0, "key_registered": 0, "key_released": 0,
                       "key_failed": 0, "deletes": 0, "delete_registered": 0, "delete_released": 0,
                       "delete_failed": 0}
        # the side panes: side -> (picture serial, premultiplied BGRA, box in the viewer's client pixels, the boxes of
        # its plates that take a click) or None, from the Tk thread; what shows of each, (serial, screen origin, size)
        # or None, the window thread's own
        self._pane_want: dict[str, tuple[int, np.ndarray, st.Box, tuple[st.Box, ...]] | None] = {
            side: None for side in PANES}
        self._pane_serial = 0
        self._pane_shown: dict[str, tuple[int, tuple[int, int], tuple[int, int]] | None] = {s: None for s in PANES}
        self._clicks: deque[tuple[str, int, int, float]] = deque(maxlen=CLICKS_KEPT)
        # the window thread's own state
        self._shown: tuple[Any, ...] | None = None  # (set serial, indices, origin, size[, the editing marks as drawn]) on
        # show; None: hidden
        self._seq = -1
        self._seen_changed = -1
        self._covers: list[st.Box] = []
        self._covers_at = 0.0
        self._geometry: tuple[Any, ...] | None = None
        self._new_frame = False  # whether the look under way was started by a frame not looked at before
        self._dib: tuple[int, int, int, np.ndarray, tuple[int, int]] | None = None  # (dc, bitmap, old, pixels, size)
        self._pointer: tuple[int, int] | None = None  # where the pointer was at the last look (screen pixels)
        self._was_held = False  # the button held at the last look
        self._sizing = False  # the viewer's window sized by the pointer: pressed on its sizing border, held since
        # (`_rect_tick`) the viewer's client area and frame bounds on the screen as last seen, and when they last
        # changed (None: at rest); the thread's own hook on the viewer's moves (`_hook_moves`: viewer, hook, callback)
        self._rect: tuple[Any, ...] | None = None
        self._rect_at: float | None = None
        self._move_hook: tuple[int, int, Any] = (0, 0, None)
        self._hover_box: st.Box | None = None  # the box of the patch left out under the pointer
        self._hover_delay = 0.0  # s the pointer rests on a patch before it is left out (`set_hover_delay`)
        self._hover_wait: tuple[st.Box, float] | None = None  # (the patch the pointer came to, since when)
        self._hovered: tuple[int, st.Box] | None = None  # (its set's key, its box) of the patch left out, for Tk
        self._look_key: int | None = None  # the key of the set the last look chose (None: none), for Tk
        # (`why_not_shown`) what the last full look found of each patch of the set it chose, and what the last drawing
        # left out and why: a new dict each time, never changed after (read by the Tk thread as it is)
        self._look_facts: dict[str, Any] = {}
        self._why: dict[str, Any] = {}
        self._frame_since: tuple[int, float] = (-1, 0.0)  # (the frame count the last full look had, since when)
        self._right_takes = False  # the right pane takes clicks now (the pointer on one of its plates)
        self._dpi = st.BASE_DPI  # the viewer's (`viewer_dpi`), at each change of its place or size
        self._last_look: tuple[Any, ...] | None = None  # (set, patches shown but for the pointer, shares, frame, ms)
        # Editing (`set_edit`): the marks from the Tk thread; the window thread's own: whether the lettering's window
        # takes the mouse, the marks the last draw laid on the page (None: none on show), the boxes left out of them
        # (covered, or their page's pixels not there), the press held, the presses for the Tk thread, the boxes of the
        # last change outlined until the Tk thread's marks have taken it (press serial, boxes)
        self._marks: st.Marks | None = None
        self._ground = False  # (the Tk thread's, `set_ground`) editing: the whole page takes the mouse
        self._away = False  # (the Tk thread's, `set_away`) the viewer's window shows another tab than the book's
        self._edit_takes = False
        self._marks_live: st.Marks | None = None
        self._left_out: frozenset[int] = frozenset()
        self._patchless: int | None = None  # the key of the marks' page while its set has no patch
        self._probes_failed: frozenset[st.Box] = frozenset()  # boxes with no patch not over their page (last look)
        self._press: dict[str, Any] | None = None
        self._edits: deque[dict[str, Any]] = deque(maxlen=EDITS_KEPT)
        self._edit_serial = 0
        self._edit_dirty = False  # a press, a move while one is held, its release: the page drawn again
        self._ghost: tuple[int, tuple[st.Box, ...]] | None = None
        self._cursors: dict[int, int] = {}
        # (the window thread's) the last click on a box: (its page's key, its index, its box, when it was pressed,
        # where), for a double click (`_edit_press`); the box whose patches give way to the original under the pointer
        # now, and the one the pointer rests on until its wait is over (box, since when)
        self._last_click: tuple[int, int, st.Box, float, tuple[int, int]] | None = None
        self._edit_out: st.Box | None = None
        self._edit_wait: tuple[st.Box, float] | None = None
        # the Insert key (`set_add_key`) and the Delete key (`set_delete_key`): wanted by the Tk thread; the window
        # thread's own: held as the hot key now, a registration failed (not tried again until the key is let go of),
        # the failure logged (once a session), its presses for the Tk thread
        self._key_wanted = False
        self._key_held = False
        self._key_failed = False
        self._key_logged = False
        self._keys: deque[float] = deque(maxlen=KEYS_KEPT)
        self._del_wanted = False
        self._del_held = False
        self._del_failed = False
        self._del_logged = False
        self._deletes: deque[float] = deque(maxlen=KEYS_KEPT)

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
        self._poke()

    def set_on(self, on: bool) -> None:
        """The reader's switch (the left pane's Lettering): the lettering shown (*on*) or hidden; the patches are
        kept."""
        with self._lock:
            if bool(on) != self._on:
                self._on = bool(on)
                self._changed += 1
        self._note("on", on=int(bool(on)))
        self._poke()

    @property
    def on(self) -> bool:
        return self._on

    def set_away(self, away: bool) -> None:
        """Whether the viewer's window shows another tab than the book's (a browser's:
        `ui.viewers.ViewerMixin._tab_now`): while it does nothing is lettered over it and the mouse is not taken there,
        editing too (the page on show is not the book's), the Insert key is let go of; the side panes stay as they are,
        the patches are kept. The book's tab back: as it was."""
        with self._lock:
            if bool(away) == self._away:
                return
            self._away = bool(away)
            self._changed += 1
        self._note("away", on=int(bool(away)))
        self._poke()

    def present(self, key: int, size: tuple[int, int], patches: tuple[st.Patch, ...], final: bool = False) -> None:
        """The patches of the page read from the frame *key* (of *size*) as lettered now: they replace the set of that
        key, and become the newest."""
        with self._lock:
            s = self._store.put(key, size, patches, final)
            self._changed += 1
        self._note("present", key=key, set=s.serial, patches=len(patches), final=int(final))
        self._poke()

    def forget(self, key: int) -> None:
        with self._lock:
            self._store.drop(key)
            self._changed += 1
        self._poke()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._changed += 1
        self._poke()

    def shown(self) -> tuple[Any, ...] | None:
        """(set serial, patch indices, screen origin, size) of what shows now; None when nothing does. (While editing the
        window's own state has what the marks are too; not given here.)"""
        shown = self._shown
        return shown[:4] if shown is not None else None

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

    def why_not_shown(self) -> dict[str, Any]:
        """What the last look and drawing made of the patches (numbers only, for the report and the log: `ui.seethrough.
        unshown`): "key" the set chosen (None: none matched - "sets" the keys of those of the frame's size), "boxes" its
        patches' boxes, "valid" those whose pixels match (`seethrough.patch_matches`), "where" for each other one where
        its compared pixels differ (`seethrough.where_differs`), "covered" those a window over the viewer meets,
        "drawn" those on show, "hover" the one left out under the pointer (editing: "original", those of the box under
        the pointer left out), "held" those kept whatever the frame says (the region in the editor, one being
        pressed), "bare" those of the region whose original is shown, "editing",
        "hidden" (why nothing shows: off, away, no viewer...), "at" (monotonic s), "frame_at" (since when the viewer's
        frame looked at was its newest: a frame at rest so long). Empty before the first look."""
        return self._why

    def report_facts(self, key: int | None = None, within_s: float = REPORT_FPS_S) -> dict[str, Any]:
        """(the Tk thread, a report: `ui.report`) The window's state as its last look left it, numbers and flags only:
        "on", "away", "editing" (the whole page takes the mouse), "takes_mouse" (the lettering's window takes it now),
        "key_held" (the Insert key), "delete_held" (the Delete key), "sizing", "moving" (the viewer's window moved or
        sized less than PANE_REST_S ago: the side panes hidden, `_rect_tick`), "dpi", "origin" and "size" of the
        viewer's client area at the last look,
        "shown" (set serial, patches on show; None: hidden), "covers" (the windows over the viewer met, screen boxes),
        "panes" (side -> screen box on show, or None) with "pane_wanted" (side -> handed a picture), "frames_per_s"
        (the viewer's frames that came in the last *within_s* s), "counts" (`counts`); and for the set of *key* (the
        page's frame) "patches": each patch's box and the share of its pixels that are not see-through."""
        now = time.monotonic()
        arrived = [t for t in list(self._arrived.values()) if now - t <= within_s]
        look = self._last_look
        shown = self._shown
        with self._lock:
            sets = list(self._store.sets)
            wanted = {side: want is not None for side, want in self._pane_want.items()}
        patches: list[tuple[st.Box, float]] | None = None
        chosen = next((s for s in sets if s.key == key), None) if key is not None else None
        if chosen is not None:
            patches = []
            for p in chosen.patches:
                alpha = p.bgra[:, :, 3] if getattr(p.bgra, "ndim", 0) == 3 else None
                share = float((alpha > 0).mean()) if alpha is not None and alpha.size else 0.0
                patches.append((tuple(int(v) for v in p.box), round(share, 3)))
        return {"on": bool(self._on), "away": bool(self._away), "editing": bool(self._ground),
                "takes_mouse": bool(self._edit_takes), "key_held": bool(self._key_held),
                "delete_held": bool(self._del_held), "sizing": bool(self._sizing),
                "moving": self.moving(), "dpi": int(self._dpi), "origin": tuple(look[5]) if look is not None else None,
                "size": tuple(look[6]) if look is not None else None,
                "shown": (int(shown[0]), len(shown[1])) if shown is not None else None,
                "covers": [tuple(int(v) for v in c) for c in list(self._covers)],
                "panes": {side: self.pane_shown(side) for side in PANES}, "pane_wanted": wanted,
                "frames_per_s": round(len(arrived) / within_s, 1) if within_s > 0 else 0.0,
                "sets": len(sets), "patches": patches, "counts": dict(self.counts)}

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
            self._poke()

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

    def moving(self) -> bool:
        """(any thread) Whether the viewer's window moved or changed its size less than PANE_REST_S ago, the side
        panes hidden meanwhile (`_rect_tick`)."""
        return self._rect_at is not None

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

    def set_edit(self, marks: st.Marks | None) -> None:
        """the editing marks on the page (`seethrough.Marks`), or None: Reader mode (the lettering's window click-through
        again, a press held given up). The same marks handed again change nothing."""
        with self._lock:
            if marks is self._marks:
                return
            self._marks = marks
            self._changed += 1
        self._poke()

    def set_ground(self, on: bool) -> None:
        """Whether the Tk thread is editing (Reader mode off, `ui.see_edit`): the lettering's window then takes the
        mouse over the viewer's whole page whatever page it shows - one with no marks of its own too (`set_edit`:
        those of the page on show), where a drag draws a rectangle ("draw", no marks) and a click does nothing - and
        the viewer gets the keys alone. Off: only marks take it (a region to add in Reader mode)."""
        with self._lock:
            if bool(on) == self._ground:
                return
            self._ground = bool(on)
            self._changed += 1
        self._poke()

    def pressing(self) -> bool:
        """Whether a press on the page is the window's own (editing: one held, or the button down over the page while
        the window takes the mouse there): no press of the viewer's, whose page some viewers drag along meanwhile
        (`ui.live`'s `_held_in_viewer`). Read from the Tk thread: the window's state as its last look left it."""
        if self._press is not None:
            return True
        if not self._edit_takes:
            return False
        shown, point = self._shown, cursor_pos()
        if shown is None or point is None:
            return False
        (x, y), (w, h) = shown[2], shown[3]
        return x <= point[0] < x + w and y <= point[1] < y + h and not any(
            c[0] <= point[0] < c[2] and c[1] <= point[1] < c[3] for c in list(self._covers))

    def take_edits(self) -> list[dict[str, Any]]:
        """The presses on the page since the last call, the oldest first: dicts with "kind" ("click", "double" - the
        second click of a double click on a box, its first handed as a "click" before it - and "plate" - a click on a
        box's number plate -: "index", "shift"; "move" and "resize": "boxes", index -> the box it was dragged
        to; "add" - Add area's rectangle - and "draw" - one drawn on the empty ground while editing -: "box", None when the
        drag drew nothing; "ground": a click on the empty ground), "press" (their serial, which `Marks.seen` gives
        back), "marks" (the serial of the marks the press was made on, 0 for none) and "key" (their page)."""
        out = []
        while self._edits:
            try:
                out.append(self._edits.popleft())
            except IndexError:
                break
        return out

    def set_add_key(self, wanted: bool) -> None:
        """Whether the Insert key adds a text area (``Settings.add_area_key``, with TASlation's own window hidden): the
        key held while the viewer is in front (`_key_tick`); not *wanted*, it is let go of at the next look."""
        if bool(wanted) != self._key_wanted:
            self._key_wanted = bool(wanted)
            self._poke()

    def key_held(self) -> bool:
        """Whether the Insert key is TASlation's now (held as the hot key: the viewer in front)."""
        return self._key_held

    def take_keys(self) -> list[float]:
        """The presses of the Insert key since the last call (when each came), the oldest first."""
        return _taken(self._keys)

    def set_delete_key(self, wanted: bool) -> None:
        """Whether the Delete key drops the region chosen (the Tk thread's: editing with a region chosen, no editor
        open, `ui.see_edit.delete_wanted`): the key held while the viewer is in front (`_key_tick`); not *wanted*, it
        is let go of at the next look, so that the viewer has its own Delete at all other times."""
        if bool(wanted) != self._del_wanted:
            self._del_wanted = bool(wanted)
            self._poke()

    def delete_held(self) -> bool:
        """Whether the Delete key is TASlation's now (held as the hot key: a region chosen, the viewer in front)."""
        return self._del_held

    def take_deletes(self) -> list[float]:
        """The presses of the Delete key since the last call (when each came), the oldest first."""
        return _taken(self._deletes)

    def client_origin(self) -> tuple[int, int] | None:
        """The screen point the viewer's client area (and the lettering's window) began at at the last look; None
        before one."""
        look = self._last_look
        return (int(look[5][0]), int(look[5][1])) if look is not None else None

    def close(self) -> None:
        self._stop.set()
        self._poke()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(2.0)

    def poke(self) -> None:
        """(any thread) Look at the viewer again at once: the viewer's window moved or resized
        (`capture.WindowEvents.on_moved`), so that its lettering follows it within a look, not LOOK_S later."""
        self._poke()

    # ------------------------------------------------------------------ the window's thread
    def _poke(self) -> None:
        """The window thread looks again at once: its event set, and a message posted to its own window (it waits
        for its messages: `_wait`)."""
        self._wake.set()
        if self.hwnd and IS_WINDOWS:
            _user32.PostMessageW(self.hwnd, WM_APP, 0, 0)

    def _wait(self) -> None:
        """Until something is to be looked at, LOOK_S at the most: the event (`_poke`, or the viewer's window moved:
        `_viewer_moved`) - while editing, any message of the thread's too (a press, the pointer's moves), so that a
        drag follows the pointer at once. The thread's messages are read meanwhile (`_pump`), so that its own hook on
        the viewer's moves is told of each at once."""
        if not IS_WINDOWS or not self.hwnd:
            self._wake.wait(LOOK_S)
        elif self._edit_takes:
            _user32.MsgWaitForMultipleObjectsEx(0, None, int(LOOK_S * 1000), QS_ALLINPUT, MWMO_INPUTAVAILABLE)
        else:
            end = time.monotonic() + LOOK_S
            while not self._wake.is_set() and not self._stop.is_set():
                left = end - time.monotonic()
                if left <= 0:
                    break
                _user32.MsgWaitForMultipleObjectsEx(0, None, max(1, int(left * 1000)), QS_ALLINPUT,
                                                    MWMO_INPUTAVAILABLE)
                self._pump()
        self._wake.clear()

    def _pump(self) -> None:
        """The thread's messages, each handed to its window (and the hook's notes to `_viewer_moved`)."""
        msg = wintypes.MSG()
        while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _note(self, kind: str, **facts: Any) -> None:
        self.notes.append({"t": time.monotonic(), "ev": kind, **facts})

    def _on_frame(self, hwnd: int, seq: int) -> None:
        if hwnd == self._viewer:
            self._arrived[seq] = time.monotonic()
            if len(self._arrived) > 256:
                for old in sorted(self._arrived)[:128]:
                    self._arrived.pop(old, None)
            self._poke()

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
        _edit_hooks[self.hwnd] = self._edit_message
        _key_hooks[self.hwnd] = self._hot_key
        wgc.add_listener(self._on_frame)
        try:
            while not self._stop.is_set():
                self._wait()
                self._pump()
                try:
                    self._step()
                except Exception as e:  # noqa: BLE001 - one look's fault: noted, the next look goes on
                    self.counts["errors"] += 1
                    self._note("error", why=type(e).__name__)
        finally:
            self._hook_moves(0)
            wgc.remove_listener(self._on_frame)
            _edit_hooks.pop(self.hwnd, None)
            self._key_tick(0)  # (the key let go of)
            _key_hooks.pop(self.hwnd, None)
            self._edit_cancel("closed")
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
            viewer, away, changed = self._viewer, self._away, self._changed
            on = self._on and not away  # (another tab on show: nothing lettered, the mouse not taken, `set_away`)
            sets = list(self._store.sets)
            panes = dict(self._pane_want)
            marks, ground = self._marks, self._ground
        self.counts["looks"] += 1
        self._key_tick(0 if away else viewer)
        self._edit_take((marks is not None or ground) and on, sets)
        if not viewer:
            self._nothing("no viewer")
            return
        if not _user32.IsWindow(viewer):
            self._nothing("gone")
            return
        self._hook_moves(viewer)
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
        resting = self._rect_tick((client, bounds), now)
        geometry = (client, bounds, frame.size)
        new_frame = frame.seq != self._seq
        pointer = cursor_pos()
        moved, self._pointer = pointer != self._pointer, pointer
        held = button_down()
        self._pane_presses(pointer, held, now)
        if self._sizing_tick(viewer, pointer, held, bounds):
            self._panes_hide("sizing")  # (before the window shrinks under them; back at the release)
        if not new_frame and changed == self._seen_changed and geometry == self._geometry and \
                now - self._covers_at < COVER_S:
            self._right_plates(pointer, panes, held)
            self._edit_held()
            # (a patch the pointer rests on, to be left out once its wait is over: Reader mode's, editing's)
            waiting = self._hover_wait is not None or self._edit_wait is not None
            if (moved or waiting or self._edit_dirty) and on and self._last_look is not None:  # only the pointer
                self._new_frame = False  # moved: the last look, less the patch under it now (no frame compared again)
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
        if not self._sizing and resting:
            self._place_panes(panes, origin, size)
        self._right_plates(pointer, panes, held)
        self._edit_held()
        if not on:  # (the left pane's Lettering switched off, another tab on show: the lettering hidden, the side
            self._last_look = None  # panes as they are)
            self._unhover()
            self._marks_live = None
            self._why = {"hidden": "away" if away else "off", "at": now}
            self._hide("away" if away else "off")
            return
        self._new_frame = new_frame
        if new_frame:
            self.counts["frames"] += 1
        started = time.perf_counter()
        view = frame.bgra[box[1]:box[3], box[0]:box[2]]
        chosen, shown, shares = st.visible(sets, view)
        compare_ms = (time.perf_counter() - started) * 1000
        self.counts["compare_ms"] += compare_ms
        valid = shown
        if chosen is not None:
            shown = tuple(i for i in shown if not st.covered(chosen.patches[i].box, origin, self._covers))
        if self._frame_since[0] != frame.seq:
            self._frame_since = (frame.seq, now)
        self._look_facts = {**self._facts_of(chosen, valid, shown, shares, sets, view, size, now),
                            "frame_at": self._frame_since[1]}
        self._probes_failed = self._failed_probes(chosen, view)
        self._last_look = (chosen, shown, shares, frame.seq, compare_ms, origin, size, bool(sets))
        self._show_look(*self._last_look)

    @staticmethod
    def _facts_of(chosen: st.PatchSet | None, valid: tuple[int, ...], shown: tuple[int, ...], shares: list[float],
                  sets: list[st.PatchSet], view: Any, size: tuple[int, int], now: float) -> dict[str, Any]:
        """(a full look) The facts `why_not_shown` gives of the set *chosen*: where the pixels of each patch whose
        pixels do not match differ (WHERE_KEPT patches at the most: a look of a page that matches has few)."""
        if chosen is None:
            return {"key": None, "sets": tuple(s.key for s in sets if s.size == size), "at": now}
        where = {}
        for i, patch in enumerate(chosen.patches):
            if i not in valid and len(where) < WHERE_KEPT:
                where[i] = st.where_differs(patch, view)
        return {"key": chosen.key, "serial": chosen.serial, "final": chosen.final,
                "boxes": tuple(p.box for p in chosen.patches), "near": tuple(p.near for p in chosen.patches),
                "valid": valid, "covered": tuple(i for i in valid if i not in shown),
                "shares": tuple(round(v, 4) for v in shares), "share_limit": st.CHANGED_SHARE, "where": where,
                "at": now}

    def _drew(self, drawn: tuple[int, ...], **more: Any) -> None:
        """What the drawing after the last full look left out (`why_not_shown`)."""
        self._why = {**self._look_facts, "drawn": tuple(drawn), "hidden": "", **more}

    def _show_look(self, chosen: st.PatchSet | None, shown: tuple[int, ...], shares: list[float], seq: int,
                   compare_ms: float, origin: tuple[int, int], size: tuple[int, int], any_sets: bool) -> None:
        """What a look found shown (*shown* of the set *chosen*, none covered), less the patch under the pointer - or,
        while editing, with the page's marks on it (`_show_edit`); while editing on a page with no marks (not translated yet,
        another one), over the whole page taking the mouse (`_show_ground`)."""
        self._look_key = chosen.key if chosen is not None else None
        marks = self._marks_for(chosen)
        if marks is not None:
            self._show_edit(chosen, shown, shares, seq, compare_ms, origin, size, marks)
            return
        self._marks_live = None
        self._left_out = frozenset()
        self._edit_rested(None)
        ground = self._edit_takes  # (editing: the whole page takes the mouse though none of its regions is edited)
        if chosen is None or not shown:
            why = "covered" if chosen is not None else ("no match" if any_sets else "no patches")
            self._unhover()
            self._drew((), editing=False, hover=None)
            if ground:
                self._show_ground(chosen, (), shares, seq, compare_ms, origin, size)
                return
            self._hide(why, seq, compare_ms, shares)
            return
        under = self._under_pointer(chosen, shown, origin)
        if under is not None:
            shown = tuple(i for i in shown if i != under)
        self._drew(shown, editing=False, hover=under)
        if under is not None:
            if not shown and not ground:
                self._hide("hover", seq, compare_ms, shares)
                return
        if ground:
            self._show_ground(chosen, shown, shares, seq, compare_ms, origin, size)
            return
        state = (chosen.serial, shown, origin, size)
        if state == self._shown:
            return
        self._draw(chosen, shown, origin, size, seq, compare_ms, shares)

    def _holes(self, origin: tuple[int, int]) -> tuple[st.Box, ...]:
        """The windows over the viewer (`cover_rects`) in the frame's pixels: left at alpha 0 while editing, their own."""
        return tuple((c[0] - origin[0], c[1] - origin[1], c[2] - origin[0], c[3] - origin[1]) for c in self._covers)

    def _show_ground(self, chosen: st.PatchSet | None, shown: tuple[int, ...], shares: list[float], seq: int,
                     compare_ms: float, origin: tuple[int, int], size: tuple[int, int]) -> None:
        """A look while editing on a page with no marks of its own (`seethrough.GROUND`): the patches *shown* (the one under
        the pointer gives way as ever), the whole page taking the mouse but the windows over the viewer, and the
        rectangle a press on it draws."""
        press = self._press
        drawing = (st.drawn_box(press["start"], press["now"], size)
                   if press is not None and press.get("draw") and press["moved"] else None)
        holes = self._holes(origin)
        key = ("ground", drawing, holes)
        self._edit_dirty = False
        state = (chosen.serial if chosen is not None else -1, shown, origin, size, key)
        if state == self._shown:
            return
        self._draw(chosen, shown, origin, size, seq, compare_ms, shares,
                   (st.GROUND, None, None, frozenset(), drawing, (), holes), key)

    # ---------------------------------------------------------------- the Insert and Delete keys (the window's thread)
    def _key_tick(self, viewer: int) -> None:
        """(every look) The Insert key held as the lettering's window's hot key while it is wanted (`set_add_key`),
        and the Delete key while it is (`set_delete_key`), and the viewer *viewer* is the window in front, not
        minimised (`viewer_in_front`); each let go of otherwise (another program or a dialog of TASlation's in front,
        the viewer minimised or gone, the key not wanted; *viewer* 0: none). A registration that fails is noted
        ("key_failed", "delete_failed"), logged the first time, and not tried again until the key has been let go of."""
        if not IS_WINDOWS or not self.hwnd:
            return
        front = bool((self._key_wanted or self._del_wanted) and viewer and viewer_in_front(viewer))
        self._key_held, self._key_failed = self._hold_key("key", HOTKEY_ID, VK_INSERT, self._key_wanted and front,
                                                          self._key_held, self._key_failed)
        self._del_held, self._del_failed = self._hold_key("delete", DELETE_ID, VK_DELETE, self._del_wanted and front,
                                                          self._del_held, self._del_failed)

    def _hold_key(self, name: str, ident: int, vk: int, wanted: bool, held: bool, failed: bool) -> tuple[bool, bool]:
        """One hot key of the lettering's window at a look (`_key_tick`): registered when *wanted* and neither *held*
        nor *failed* to be before, let go of when not *wanted*; whether it is held and whether it failed, after.
        Counted and noted under *name* ("key": Insert, "delete": Delete)."""
        if not wanted:
            if held:
                _user32.UnregisterHotKey(self.hwnd, ident)
                self.counts[name + "_released"] += 1
                self._note(name + "_held", on=0)
            return False, False
        if held or failed:
            return held, failed
        if _user32.RegisterHotKey(self.hwnd, ident, MOD_NOREPEAT, vk):
            self.counts[name + "_registered"] += 1
            self._note(name + "_held", on=1)
            return True, False
        error = ctypes.get_last_error()
        self.counts[name + "_failed"] += 1
        self._note(name + "_failed", error=int(error))
        if name == "key" and not self._key_logged:
            self._key_logged = True
            log.info("the Insert key could not be taken for Add area (Windows error %s; another program may hold "
                     "it): Add area in the left pane still works", error)
        elif name == "delete" and not self._del_logged:
            self._del_logged = True
            log.info("the Delete key could not be taken for the region chosen (Windows error %s; another program "
                     "may hold it): Menu > Page > Drop the chosen regions still works", error)
        return False, True

    def _hot_key(self, ident: int) -> None:
        """(the window thread: ``WM_HOTKEY`` to the lettering's window) Insert pressed while the viewer was in front:
        kept for the Tk thread (`take_keys`), whose Add area it starts or gives up; a rectangle being drawn to add a
        region is given up there and then. Delete: kept for the Tk thread (`take_deletes`), which drops the region
        chosen; a box held is let go of there and then (nothing done with it)."""
        if ident == DELETE_ID:
            self.counts["deletes"] += 1
            if self._press is not None:
                self._edit_cancel("delete")
            self._deletes.append(time.monotonic())
            self._note("delete")
            return
        if ident != HOTKEY_ID:
            return
        self.counts["keys"] += 1
        if self._press is not None and self._press.get("adding"):
            self._edit_cancel("key")
        self._keys.append(time.monotonic())
        self._note("key")

    # ------------------------------------------------------------------ editing (the window's thread)
    def _edit_take(self, wanted: bool, sets: list[st.PatchSet]) -> None:
        """The lettering's window takes the mouse while the Tk thread is editing (`set_ground`) or has marks for it
        (a region to add in Reader mode) and the lettering is on (no WS_EX_TRANSPARENT; its window procedure answers
        for editing, `_edit_message`), and is click-through again otherwise, a press held given up. Which page's marks
        have no patch to go by (`_patchless`)."""
        marks = self._marks
        self._patchless = None
        if marks is not None:
            own = next((s for s in sets if s.key == marks.key), None)
            if own is None or not own.patches:
                self._patchless = marks.key
        if wanted == self._edit_takes or not self.hwnd:
            return
        if not wanted:
            self._edit_cancel("off")
        style = int(_user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE))
        _user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, (style & ~WS_EX_TRANSPARENT) if wanted
                               else (style | WS_EX_TRANSPARENT))
        self._edit_takes = wanted
        self._note("edit", on=int(wanted))

    def _marks_for(self, chosen: st.PatchSet | None) -> st.Marks | None:
        """The marks a look lays on the page: the editing's, when they are of the page the look found (its set chosen; or,
        with no set chosen, a page with no patch at all - nothing tells it is not there but the Tk thread, which gives
        none once the viewer shows another page)."""
        marks = self._marks if self._edit_takes else None
        if marks is None:
            return None
        if chosen is not None:
            return marks if chosen.key == marks.key else None
        return marks if self._patchless == marks.key else None

    def _failed_probes(self, chosen: st.PatchSet | None, view: Any) -> frozenset[st.Box]:
        """(a full look) The boxes of the editing marks with no patch of their own whose pixels round them the viewer's
        frame *view* has not (`Marks.probes`): bars over them, another page. They take nothing (`_show_edit`)."""
        marks = self._marks_for(chosen)
        if marks is None or not marks.probes:
            return frozenset()
        patches = chosen.patches if chosen is not None else ()
        out = set()
        for box, probe in zip(marks.boxes, marks.probes):
            if probe is None or any(_meets(p.box, box) for p in patches):
                continue
            if st.changed_share(probe, view) > st.CHANGED_SHARE:
                out.add(box)
        return frozenset(out)

    def _edit_point(self, origin: tuple[int, int]) -> tuple[int, int] | None:
        """The pointer in the frame's pixels; None when it is not over the viewer's page (a side pane, a window over
        the viewer) or not known."""
        point = self._pointer
        if point is None or self._pointer_elsewhere(point):
            return None
        return point[0] - origin[0], point[1] - origin[1]

    def _show_edit(self, chosen: st.PatchSet | None, shown: tuple[int, ...], shares: list[float], seq: int,
                   compare_ms: float, origin: tuple[int, int], size: tuple[int, int], marks: st.Marks) -> None:
        """A look while editing: the patches the frame has (*shown*), and also those of the region in the editor and of a
        region being dragged whatever the frame says, less those of the region whose original is shown (*bare*); the
        box under the pointer is outlined more strongly, the right pane is told of that region (`hovered`), and its
        patches give way to the original once the pointer has rested on it the hover delay (`_edit_rested`; not while
        a press is held, nor for the region in the editor, whose patches show its changes). The boxes a window over
        the viewer meets, those whose patches the frame has none of, and those with no patch whose pixels round them
        it has not (`_failed_probes`), take nothing."""
        patches = chosen.patches if chosen is not None else ()
        press = self._press if self._press is not None and self._press["marks"] is marks else None
        meets = _meets
        failed = getattr(self, "_probes_failed", frozenset())

        held = {marks.held} if marks.held is not None else set()
        if press is not None and "index" in press:
            held.add(press["index"])
        held_boxes = [marks.boxes[i] for i in held if 0 <= i < len(marks.boxes)]
        bare = marks.boxes[marks.bare] if marks.bare is not None and 0 <= marks.bare < len(marks.boxes) else None
        keep = set(shown)
        for i, p in enumerate(patches):
            if any(meets(p.box, b) for b in held_boxes) and not st.covered(p.box, origin, self._covers):
                keep.add(i)
        if bare is not None:
            keep = {i for i in keep if not meets(patches[i].box, bare)}
        left_out = set()
        for i, box in enumerate(marks.boxes):
            if st.covered(box, origin, self._covers):
                left_out.add(i)
            elif i not in held:
                own = [k for k, p in enumerate(patches) if meets(p.box, box)]
                if (own and not any(k in shown for k in own)) or (not own and box in failed):
                    left_out.add(i)
        left_out_set = frozenset(left_out)
        self._marks_live, self._left_out = marks, left_out_set
        moved: dict[int, st.Box] | None = None
        drawing: st.Box | None = None
        hover: int | None = None
        if press is not None:
            if press.get("adding") or press.get("draw"):
                drawing = st.drawn_box(press["start"], press["now"], size) if press["moved"] else None
            else:
                hover = press["index"]
                if press["moved"] and not marks.locked:
                    moved = st.edit_drag(marks, press["index"], press["grip"], press["start"], press["now"], size)
        else:
            point = self._edit_point(origin)
            grip = (st.edit_grip(marks, point, st.scaled(st.GRIP_PX, self._dpi), left_out_set)
                    if point is not None and not marks.adding else None)
            hover = grip[0] if grip is not None else None
        ghost = self._ghost
        ghosts = marks.ghosts
        if ghost is not None and marks.seen < ghost[0]:
            ghosts = (*ghosts, *ghost[1])
        elif ghost is not None:
            self._ghost = None
        self._hover_wait = None
        self._set_hover(marks.boxes[hover] if hover is not None else None, marks.key)
        out = marks.boxes[hover] if press is None and hover is not None and hover not in held else None
        out = out if self._edit_rested(out) else None
        original = tuple(i for i in sorted(keep) if out is not None and meets(patches[i].box, out))
        indices = tuple(i for i in sorted(keep) if i not in original)
        self._drew(indices, editing=True, hover=None, original=original,
                   held=tuple(i for i, p in enumerate(patches) if any(meets(p.box, b) for b in held_boxes)),
                   bare=tuple(i for i, p in enumerate(patches) if bare is not None and meets(p.box, bare)),
                   left_out=tuple(sorted(left_out)), region_boxes=marks.boxes)
        holes = self._holes(origin)
        edit = (marks, hover, moved, left_out_set, drawing, ghosts, holes)
        key = (marks.serial, hover, None if moved is None else tuple(sorted(moved.items())), left_out_set, drawing,
               ghosts, holes)
        self._edit_dirty = False
        state = (chosen.serial if chosen is not None else -1, indices, origin, size, key)
        if state == self._shown:
            return
        self._draw(chosen, indices, origin, size, seq, compare_ms, shares, edit, key)

    def _edit_rested(self, box: st.Box | None) -> bool:
        """(editing, `_show_edit`) Whether the patches of *box* - the box under the pointer, None for none - give way
        to the original now: once the pointer has rested on it the hover delay (`set_hover_delay`, as in Reader mode;
        the looks go on meanwhile, `_step`), and while it stays on it."""
        if box is None:
            self._edit_out = self._edit_wait = None
            return False
        if box == self._edit_out:
            return True
        if self._hover_delay > 0:
            now = time.monotonic()
            if self._edit_wait is None or self._edit_wait[0] != box:
                self._edit_wait = (box, now)
            if now - self._edit_wait[1] < self._hover_delay:
                self._edit_out = None
                return False
        self._edit_wait = None
        self._edit_out = box
        return True

    def _edit_message(self, message: int, wparam: Any, lparam: Any) -> int | None:
        """(the window thread: the lettering's window procedure, `_proc`) What editing answers to *message* while the
        window takes the mouse; None: the window's own answer. A press takes hold of a box, or of the empty ground
        (`_edit_press`), the pointer's moves while it is held follow it, the release ends it (`_edit_release`); a right
        click, or the capture taken by another window, gives it up; the wheels, the middle and the side buttons are
        taken and do nothing (no window gets them: the viewer has the keys alone); the cursor says what a press would
        do (`_set_cursor`)."""
        if not self._edit_takes:
            return None
        if message == WM_NCHITTEST:
            return HTCLIENT
        if message == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if message == WM_SETCURSOR:
            self._set_cursor()
            return 1
        if message in SWALLOWED:
            return 0
        if message in SIDE_BUTTONS:
            return 1
        if message in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN):
            point = (ctypes.c_short(int(lparam) & 0xFFFF).value, ctypes.c_short((int(lparam) >> 16) & 0xFFFF).value)
            if message == WM_LBUTTONDOWN:
                self._edit_press(point, bool(int(wparam or 0) & MK_SHIFT))
            elif message == WM_MOUSEMOVE:
                self._edit_move(point)
            elif message == WM_LBUTTONUP:
                self._edit_release(point)
            else:  # (a right click: a drag given up - and, with a region to add, the adding too)
                marks = self._marks_live
                self._edit_cancel("right")
                if marks is not None and marks.adding:
                    self._add_given_up(marks)
            return 0
        if message == WM_CAPTURECHANGED:
            if self._press is not None and int(lparam or 0) != self.hwnd:
                self._edit_cancel("capture")
            return 0
        return None

    def _edit_size(self) -> tuple[int, int] | None:
        look = self._last_look
        return (int(look[6][0]), int(look[6][1])) if look is not None else None

    def _edit_press(self, point: tuple[int, int], shift: bool) -> None:
        """A press on the page while editing: on a box (or its number plate) it takes hold of it - a corner to resize it,
        the plate to type its place (or move the box), else the box to move it, or a click (`Marks.locked`: a click
        only; the second press of a double click, "double", without Shift: on the box the last click was on, within
        the system's double-click time and reach of it, `double_click`) -; with a region to add, it begins the
        rectangle; on the empty ground - or on a page with no marks of its own - it begins a rectangle drawn to add a
        region ("draw"; a click only while presses only click). The capture is the window's until it is let go: the
        next moves are the window's whatever the pointer passes over."""
        marks = self._marks_live
        if self._edit_size() is None or (marks is None and not self._edit_takes):
            return
        if marks is not None and marks.adding:
            press: dict[str, Any] = {"adding": True, "start": point, "now": point, "moved": False, "marks": marks}
        else:
            grip = (st.edit_grip(marks, point, st.scaled(st.GRIP_PX, self._dpi), self._left_out)
                    if marks is not None else None)
            if grip is None:
                press = {"draw": marks is None or not marks.locked, "start": point, "now": point, "moved": False,
                         "marks": marks, "key": marks.key if marks is not None else int(self._look_key or 0)}
            else:
                press = {"index": grip[0], "grip": "move" if marks.locked else grip[1], "start": point,
                         "now": point, "shift": shift, "moved": False, "marks": marks, "t": time.monotonic()}
                press["double"] = not shift and grip[1] != st.PLATE and self._double(marks, grip[0], point,
                                                                                     press["t"])
        self._press = press
        if IS_WINDOWS:
            _user32.SetCapture(self.hwnd)
        self._note("press", x=point[0], y=point[1], adding=int(bool(press.get("adding"))))
        self._edit_redraw()

    def _double(self, marks: st.Marks, index: int, point: tuple[int, int], now: float) -> bool:
        """Whether a press at *point* on the box *index* of *marks* is the second of a double click: the last click
        (`_last_click`) was on the same box of the same page, pressed no longer than the system's double-click time
        before, and no farther away than its reach (`double_click`)."""
        last = self._last_click
        if last is None or not 0 <= index < len(marks.boxes):
            return False
        key, at, box, when, where = last
        seconds, across, down = double_click()
        return (key == marks.key and at == index and tuple(box) == tuple(marks.boxes[index])
                and now - when <= seconds and abs(point[0] - where[0]) <= across and abs(point[1] - where[1]) <= down)

    def _edit_move(self, point: tuple[int, int]) -> None:
        press = self._press
        if press is None:
            return
        press["now"] = point
        if not press["moved"]:
            reach = st.scaled(st.DRAG_PX, self._dpi)
            if abs(point[0] - press["start"][0]) > reach or abs(point[1] - press["start"][1]) > reach:
                press["moved"] = True
        self._edit_dirty = True

    def _edit_release(self, point: tuple[int, int]) -> None:
        """The press let go: what it did kept for the Tk thread (`take_edits`) - a click (on a number plate: "plate";
        the second of a double click: "double"), a box moved or resized (the others chosen with it), a rectangle drawn
        (Add area's, or none: a press without a drag gives adding up; one on the empty ground, "draw"), a click on the
        empty ground -, the boxes it changed outlined at their new places until the Tk thread's marks have seen it
        (`Marks.seen`). A click on a box is remembered for a double click (`_double`); anything else forgets it."""
        press, self._press = self._press, None
        if IS_WINDOWS:
            _user32.ReleaseCapture()
        size = self._edit_size()
        if press is None or size is None:
            return
        press["now"] = point
        self._edit_move(point)
        marks = press["marks"]
        self._last_click = None
        self._edit_serial += 1
        event: dict[str, Any] = {"press": self._edit_serial, "marks": marks.serial if marks is not None else 0,
                                 "key": marks.key if marks is not None else press.get("key", 0)}
        ghosts: tuple[st.Box, ...] = ()
        if press.get("adding") or (press.get("draw") and press["moved"]):
            box = st.drawn_box(press["start"], point, size)
            big = box[2] - box[0] >= st.MIN_BOX and box[3] - box[1] >= st.MIN_BOX
            event.update(kind="add" if press.get("adding") else "draw", box=box if press["moved"] and big else None)
            ghosts = (box,) if event["box"] is not None and marks is not None else ()
        elif "index" not in press:
            event.update(kind="ground")
        elif press["moved"] and not marks.locked:
            moved = st.edit_drag(marks, press["index"], press["grip"], press["start"], point, size)
            changed = {i: b for i, b in moved.items() if b != marks.boxes[i]}
            if not changed:
                self._edit_redraw()
                return
            event.update(kind="resize" if press["grip"] in st.CORNERS else "move", boxes=changed,
                         index=press["index"])
            ghosts = tuple(changed.values())
        else:
            kind = "plate" if press["grip"] == st.PLATE else "double" if press.get("double") else "click"
            event.update(kind=kind, index=press["index"], shift=bool(press.get("shift")))
            if kind == "click" and not press.get("shift") and 0 <= press["index"] < len(marks.boxes):
                self._last_click = (marks.key, press["index"], marks.boxes[press["index"]], press["t"],
                                    press["start"])
        self._edits.append(event)
        if ghosts:
            self._ghost = (self._edit_serial, ghosts)
        self._note("edit_" + event["kind"], press=self._edit_serial)
        self._edit_redraw()

    def _edit_cancel(self, why: str) -> None:
        """A press held given up (a right click, the capture gone, Reader mode, the viewer gone, the Delete key):
        nothing is done."""
        self._last_click = None
        if self._press is None:
            return
        self._press = None
        if IS_WINDOWS and self.hwnd and _user32.GetCapture() == self.hwnd:
            _user32.ReleaseCapture()
        self._note("press_given_up", why=why)
        self._edit_dirty = True

    def _add_given_up(self, marks: st.Marks) -> None:
        """A right click while a region is to be added: kept for the Tk thread as an "add" that drew nothing (its box
        None), which gives the adding up."""
        self._edit_serial += 1
        self._edits.append({"press": self._edit_serial, "marks": marks.serial, "key": marks.key, "kind": "add",
                            "box": None})
        self._note("edit_add", press=self._edit_serial, given_up=1)
        self._edit_redraw()

    def _edit_held(self) -> None:
        """At every look: a press the window holds while the button is up after all (let go over another window
        while the capture did not reach it) is given up."""
        if self._press is None or not IS_WINDOWS:
            return
        button = VK_RBUTTON if _user32.GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON
        if not _user32.GetAsyncKeyState(button) & 0x8000:
            self._edit_cancel("let go elsewhere")

    def _edit_redraw(self) -> None:
        """The page drawn again now, with what the press changed (a box dragged, a rectangle drawn)."""
        self._edit_dirty = True
        if self._last_look is not None and self._on:
            self._show_look(*self._last_look)

    def _set_cursor(self) -> None:
        """The cursor over the window while editing: a hand on a box (a click chooses it, a double click edits it, a
        drag moves it), the text cursor on its number plate (a click types its place), the move cursor while one is
        dragged, a corner's resize cursor, a cross while a region is to be added or a rectangle is drawn on the ground;
        the arrow on the ground."""
        press, marks = self._press, self._marks_live
        name: str | None = None
        if press is not None:
            if press.get("adding") or press.get("draw"):
                name = "add" if press.get("adding") or press["moved"] else None
            else:
                name = "drag" if press["moved"] and press["grip"] in ("move", st.PLATE) else press["grip"]
        elif marks is not None and marks.adding:
            name = "add"
        elif marks is not None and self._last_look is not None:
            point = self._edit_point(self._last_look[5])
            grip = st.edit_grip(marks, point, st.scaled(st.GRIP_PX, self._dpi), self._left_out) if point else None
            name = None if grip is None else ("move" if marks.locked else grip[1])
        wanted = CURSOR_IDS.get(name, IDC_ARROW)
        handle = self._cursors.get(wanted)
        if handle is None:
            handle = self._cursors[wanted] = int(_user32.LoadCursorW(None, ctypes.c_void_p(wanted)) or 0)
        if handle:
            _user32.SetCursor(handle)

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
        self._why = {"hidden": why, "at": time.monotonic()}
        self._hide(why)
        self._panes_hide(why)
        self._look_key = None
        self._unhover()
        self._marks_live = None
        self._edit_cancel(why)

    def _sizing_tick(self, viewer: int, point: tuple[int, int] | None, held: bool, bounds: st.Box) -> bool:
        """Whether the viewer's window is being sized with the pointer: the button pressed on its sizing border (as
        the first look that finds the button down finds the pointer: `on_sizing_border`, never while maximised) and
        held since. Meanwhile the side panes hide (`_step`): a window that shrinks under a pane would leave it
        outside the window until the next look; they come back with the release, at once."""
        from . import windows

        if not held:
            if self._sizing:
                self._sizing = False
                self._geometry = None  # (the next look places the panes again, whatever else changed)
                self._note("sizing", on=0)
        elif not self._was_held:
            try:
                outer = windows.window_rect(viewer)
            except Exception:  # noqa: BLE001 - (gone meanwhile: no sizing)
                outer = None
            self._sizing = bool(outer is not None and not _user32.IsZoomed(viewer)
                                and on_sizing_border(point, outer, bounds, st.scaled(SIZING_IN_PX, self._dpi)))
            if self._sizing:
                self._note("sizing", on=1)
        self._was_held = held
        return self._sizing

    def _rect_tick(self, rect: tuple[Any, ...], now: float) -> bool:
        """Whether the viewer's window is at rest: *rect* (its client area and frame bounds on the screen) as it was,
        no change of them in the last PANE_REST_S. At any change - moved, sized, maximised, restored, snapped, by the
        pointer or in one step - the side panes hide at once, since a pane left where it was would lie outside the
        window until a look placed it again; they come back at rest (the look that finds it so places them, whatever
        else changed). Told at each look (`_step`) and by the thread's own hook at each move (`_viewer_moved`)."""
        if self._rect is not None and rect != self._rect:
            if self._rect_at is None:
                self._note("moving", on=1)
            self._rect_at = now
            self._panes_hide("moving")
        self._rect = rect
        if self._rect_at is not None and now - self._rect_at >= PANE_REST_S:
            self._rect_at = None
            self._geometry = None  # (the look places the panes again, whatever else changed)
            self._note("moving", on=0)
        return self._rect_at is None

    def _hook_moves(self, viewer: int) -> None:
        """(the window thread) This thread's own hook on the moves and size changes of the window *viewer* (0: none),
        so that the side panes hide the moment it changes (`_viewer_moved`), not at the next look nor when the Tk
        thread passes the change on (`poke`). Only the events of the viewer's process and thread are asked for."""
        if not IS_WINDOWS or viewer == self._move_hook[0]:
            return
        from . import windows

        old = self._move_hook[1]
        if old:
            windows.user32.UnhookWinEvent(old)
        self._move_hook = (int(viewer), 0, self._move_hook[2])
        if not viewer:
            return
        proc = self._move_hook[2] or windows.WINEVENTPROC(self._viewer_moved)  # (kept while the thread runs)
        pid = wintypes.DWORD(0)
        thread = windows.user32.GetWindowThreadProcessId(viewer, ctypes.byref(pid))
        hook = 0
        if thread:
            hook = int(windows.user32.SetWinEventHook(windows.EVENT_OBJECT_LOCATIONCHANGE,
                                                      windows.EVENT_OBJECT_LOCATIONCHANGE, None, proc, pid.value,
                                                      thread, windows.WINEVENT_OUTOFCONTEXT) or 0)
        self._move_hook = (int(viewer), hook, proc)
        self._note("move_hook", on=int(bool(hook)))

    def _viewer_moved(self, _hook, _event, hwnd, obj, child, _thread, _ms) -> None:  # type: ignore[no-untyped-def]
        """(the window thread, the hook's callback while it reads its messages) The viewer's window moved or changed
        its size: the side panes hide at once if its place did change (`_rect_tick`), and a look follows."""
        from . import windows

        try:
            viewer = self._viewer
            if not hwnd or int(hwnd) != viewer or obj != windows.OBJID_WINDOW or child != windows.CHILDID_SELF:
                return
            self._rect_tick((windows._client_box(viewer), windows._frame_bounds(viewer)), time.monotonic())
            self._wake.set()
        except Exception:  # noqa: BLE001 - a callback from Windows must never raise
            pass

    def _pane_presses(self, point: tuple[int, int] | None, held: bool, now: float) -> None:
        """A press on a side pane whose release did not come to it (let go over another window, the button up by
        now): forgotten once the pointer is off that pane, PRESS_STALE_S after the press, so that no later release
        on the pane is taken for a click (`_pane_proc`)."""
        if held or not _pane_downs:
            return
        for side, hwnd in self.panes.items():
            pressed = _pane_downs.get(hwnd)
            if pressed is None or now - pressed < PRESS_STALE_S:
                continue
            box = self.pane_shown(side)
            if point is None or box is None or not (box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]):
                _pane_downs.pop(hwnd, None)
                self._note("press_forgotten", side=side)

    def _right_plates(self, point: tuple[int, int] | None, panes: dict[str, Any], held: bool = False) -> None:
        """The right pane takes a click while the pointer at *point* (screen pixels) is on one of its plates that
        take one (WS_EX_TRANSPARENT off), and lets every other one through to the viewer (on), as the lettering's
        window does - as it was while the button is *held*: a press that began on the viewer and comes over a plate
        (a page dragged with the pointer) does not change which window takes it."""
        if held:
            return
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

    def _raise_under_panes(self) -> None:
        """The lettering's window, shown again, to the top of the topmost windows - and the side panes on show put
        back over it: while editing it takes the mouse over the whole page, and a pane left under it would take no
        click (its controls, Reader mode among them, out of reach)."""
        _raise(self.hwnd)
        for side in PANES:
            hwnd = self.panes.get(side, 0)
            if hwnd and self._pane_shown.get(side) is not None:
                _raise(hwnd)

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

    def _draw(self, chosen: st.PatchSet | None, shown: tuple[int, ...], origin: tuple[int, int],
              size: tuple[int, int], seq: int, compare_ms: float, shares: list[float],
              edit: tuple[Any, ...] | None = None, edit_key: Any = None) -> None:
        """The patches *shown* of the set *chosen* drawn over the viewer's client area at *origin* (*size*) - while editing
        with the marks on them (*edit*: `edit_compose`'s, *edit_key* what they are: a picture of the same is only
        moved)."""
        started = time.perf_counter()
        before = self._shown
        serial = chosen.serial if chosen is not None else -1
        same_picture = (before is not None and before[0] == serial and before[1] == shown and before[3] == size
                        and (before[4] if len(before) > 4 else None) == edit_key)
        dc, pixels = self._surface(size)
        if not same_picture:
            st.compose(size, [chosen.patches[i] for i in shown] if chosen is not None else [], pixels)
            if edit is not None:
                marks, hover, moved, left_out, drawing, ghosts, holes = edit
                if ghosts != marks.ghosts:
                    marks = replace(marks, ghosts=ghosts)
                st.edit_compose(pixels, marks, hover, moved, self._dpi, left_out, drawing, holes)
        ok = _layered(self.hwnd, dc, origin, size)
        if before is None:
            _user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self._raise_under_panes()
        self._shown = (serial, shown, origin, size) if edit is None else (serial, shown, origin, size, edit_key)
        draw_ms = (time.perf_counter() - started) * 1000
        self.counts["draws" if not same_picture else "moves"] += 1
        self.counts["draw_ms"] += draw_ms
        self._note("show", seq=seq, new=int(self._new_frame), arrived=self._arrived.get(seq), set=serial,
                   shown=len(shown), edit=int(edit is not None),
                   of=len(chosen.patches) if chosen is not None else 0, ok=int(bool(ok)), moved=int(same_picture),
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
