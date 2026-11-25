"""Window enumeration and capture on Windows.

Implemented with ``ctypes`` on top of user32/gdi32 only, and nothing here can
talk to the network.

Design notes (own implementation; Translumo, Apache-2.0, was studied for the
general approach of capturing a target window by handle and polling it for
changes - no code was taken from it, it is a C# project):

* Frames come from Windows.Graphics.Capture (`taslation.capture.wgc`), which
  follows a viewer behind other windows; the client area is cut out of them
  (`capture_window`, `wgc.crop_box`).
* Where that cannot be used, ``PrintWindow`` with ``PW_RENDERFULLCONTENT``
  captures many windows even when they are partly covered by other windows.
* If ``PrintWindow`` yields a blank frame (some GPU-rendered windows), we fall
  back to a ``BitBlt`` of the window's client rectangle from the screen, which
  requires the window to be visible.
* A viewer that stops drawing while it is covered is raised for a moment
  without activation (`raise_window`) and put back.
* TASlation sends the viewer no key and no click, and moves or resizes no window
  of another program: the reader turns the pages in the viewer itself. The one
  window it puts back is a viewer's that a version up to 1.0.1 left enlarged
  (`restore_window`, once, at the start: `taslation.recovery`). A window of the
  program is given the foreground without a key press (`give_foreground`).
* What happens to windows comes from out-of-context WinEvent hooks
  (`WindowEvents`: which window comes to the front, the viewer's window renamed,
  moved or closed), so that the window need not capture the viewer just to
  notice; the callbacks only take notes (see the class for why). Every change
  of the window in front is noted for the see-through mode's log of the
  foreground as well (`ForegroundNotes`: kinds and processes, no title).
* Which window is the viewer is decided on a browser window's *tab title*
  (`tab_title`: its title without " - Google Chrome" and the like), by rules
  that never guess between windows: a query names one window or the caller
  hears of the several it fits (`match_windows`); a window looks like a viewer
  when it was chosen as the viewer before, or a viewer's part learned or "book"
  is a word of its title, not part
  of a longer run of characters such as a chat page's title that runs the
  viewer's name into other words (`looks_like_viewer`, `viewer_candidates`). No store or viewer is named here:
  what of a title is the viewer's, and which window was the reader's viewer, is learned on the reader's computer
  (`taslation.viewerparts`).

What goes wrong is a `CaptureError` whose ``.message`` is a
`taslation.messages.Message` (``viewer.gone``, ``viewer.no_area``, ...).
"""

from __future__ import annotations

import atexit
import ctypes
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Callable, NamedTuple, Sequence

import numpy as np
from PIL import Image

from ..messages import Message, as_message
from . import wgc

IS_WINDOWS = sys.platform == "win32"


class CaptureError(RuntimeError):
    """Capturing or driving a window failed. ``.message`` is a Message (``viewer.*``); ``str(error)`` is its English
    text. Given a plain string, the message is ``viewer.error`` carrying that text."""

    message: Message

    def __init__(self, message: Message | str = ""):
        self.message = as_message(message, "viewer.error")
        super().__init__(self.message)


class ViewerCovered(CaptureError):
    """The viewer draws nothing (PrintWindow gives a blank frame) while a dialog of TASlation's own lies over its
    place on the screen: a copy of the screen there would be a picture of TASlation itself, so none is taken. Nothing
    is said of it (the last good frame stays: `ui.live`); its message is a ``viewer.error`` for the log."""

    def __init__(self, message: Message | str = ""):
        super().__init__(message or "the viewer draws nothing behind a dialog of TASlation")


Rect = tuple[int, int, int, int]  # left, top, right, bottom in screen pixels (right and bottom exclusive)


def rects_overlap(a: Rect, b: Rect) -> bool:
    """Whether two screen rectangles share at least one pixel."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def screen_shows_own(viewer: Rect, own: Sequence[Rect]) -> bool:
    """Whether the screen at the viewer's place (*viewer*) shows part of one of this program's own windows (*own*;
    empty rectangles are left out): a copy of the screen there would read TASlation's pixels, not the viewer's."""
    return any(r[2] > r[0] and r[3] > r[1] and rects_overlap(viewer, r) for r in own)


def covers(own: Sequence[Rect], viewer: Rect) -> bool:
    """Whether the rectangles *own* together take in every pixel of *viewer* (an empty *viewer* is covered)."""
    x0, y0, x1, y1 = viewer
    if x1 <= x0 or y1 <= y0:
        return True
    boxes = [(max(r[0], x0), max(r[1], y0), min(r[2], x1), min(r[3], y1)) for r in own]
    boxes = [b for b in boxes if b[2] > b[0] and b[3] > b[1]]
    if not boxes:
        return False
    xs = sorted({x0, x1, *(b[0] for b in boxes), *(b[2] for b in boxes)})
    ys = sorted({y0, y1, *(b[1] for b in boxes), *(b[3] for b in boxes)})
    for xa, xb in zip(xs, xs[1:]):  # every cell of the grid the edges make must lie in one of the rectangles
        for ya, yb in zip(ys, ys[1:]):
            if not any(b[0] <= xa and xb <= b[2] and b[1] <= ya and yb <= b[3] for b in boxes):
                return False
    return True


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    pid: int
    rect: tuple[int, int, int, int]  # left, top, right, bottom in screen pixels
    program: str = ""  # the file name of the window's program, lower case ("" when it cannot be told)

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]

    @property
    def tab_title(self) -> str:
        """The title of the page a browser window shows (`tab_title`); other windows' whole title."""
        return tab_title(self.title, self.class_name)

    def label(self) -> str:
        return f"{self.title}  ({self.width}x{self.height})"


# ------------------------------------------------------------------ which window is the viewer
BROWSER_CLASSES = ("Chrome_WidgetWin_1", "MozillaWindowClass")  # Chrome, Edge and the other Chromium browsers; Firefox
BROWSER_NAMES = ("google chrome", "microsoft edge", "mozilla firefox", "firefox", "chromium", "brave", "opera",
                 "vivaldi")
# The profile a browser names between the tab's title and its own name ("<tab> - 個人 - Microsoft Edge").
PROFILE = re.compile(r"(?:個人|personal|work|職場|仕事|guest|ゲスト|\[?inprivate\]?|(?:profile|person|プロファイル|ユーザー) ?\d+)",
                     re.IGNORECASE)
MORE_PAGES = re.compile(r"(?:\s+and \d+ more pages?|\s*(?:と|、)\s*他\s*\d+\s*(?:個の)?ページ)$", re.IGNORECASE)
SEPARATOR = re.compile(r"\s+[-–—]\s+")  # " - " (Chrome, Edge), " — " (Firefox)
INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏﻿"))  # "Microsoft​ Edge" has a zero-width space

NOT_VIEWERS = ("facebook", "notebook", "bookmark", "booking", "macbook", "workbook", "onenote", "- excel")
# Words of a reading program that name none: a title with one of them as a word looks like a viewer's. No store or
# viewer is named anywhere in TASlation: which window is the reader's viewer is learned on the reader's computer
# (`taslation.viewerparts`).
VIEWER_WORDS = ("book", "books", "ebook", "ebooks", "電子書籍", "本棚")
# What ends a word or segment of a title: a word inside a longer run of characters (a viewer's name run into the
# Japanese words of a chat page's title, "Facebook", a store's name with "book" inside it) is not one.
EDGE = r"\s|｜:：()（）\[\]【】「」『』!！?？,，、。・☆★"
_WORDS: dict[str, re.Pattern[str]] = {}


def _word(name: str) -> re.Pattern[str]:
    """*name* as a word of a title (`EDGE`), compiled once."""
    found = _WORDS.get(name)
    if found is None:
        if len(_WORDS) > 512:
            _WORDS.clear()
        found = _WORDS[name] = re.compile(rf"(?<![^{EDGE}]){re.escape(name)}(?![^{EDGE}])", re.IGNORECASE)
    return found


def _plain(text: str) -> str:
    """*text* without zero-width characters, its spaces as single spaces, lower case: what titles are compared as."""
    return " ".join(text.translate(INVISIBLE).split()).lower()


def _is_browser_name(segment: str) -> bool:
    plain = _plain(segment)
    return any(plain == name or plain.startswith(name + " ") for name in BROWSER_NAMES)


def tab_title(title: str, class_name: str = "") -> str:
    """The title of the tab a browser window shows: the part of *title* before the browser's own name ("<tab> -
    Google Chrome", "<tab> — Mozilla Firefox"), without the profile Edge names before its own ("<tab> - 個人 -
    Microsoft Edge") or what follows it, nor Edge's "and 2 more pages". The whole *title* for a window of another
    *class_name* than a browser's (`BROWSER_CLASSES`), and for a browser window that names no browser (an app
    window, Electron)."""
    return browser_tab(title) if class_name in BROWSER_CLASSES else title.strip()


def browser_tab(title: str) -> str:
    """`tab_title` of a title known to be a browser window's, or one whose window is not known: all of *title* when
    it names no browser."""
    parts = SEPARATOR.split(title.strip())
    at = next((i for i in range(len(parts) - 1, 0, -1) if _is_browser_name(parts[i])), None)
    if at is None:
        return title.strip()
    parts = parts[:at]
    if len(parts) > 1 and PROFILE.fullmatch(_plain(parts[-1])):
        parts = parts[:-1]
    return MORE_PAGES.sub("", " - ".join(parts)).strip()


def taskbar_title(window: "WindowInfo") -> str:
    """What a list to choose a window from calls *window*, as its taskbar button does: a browser window by the title of
    the tab it shows and the browser's name ("<tab> - Google Chrome": without the profile Edge names before its own,
    nor its "and 2 more pages": `browser_tab`), any other by its title; its spaces as single spaces, without
    zero-width characters."""
    title = " ".join(window.title.translate(INVISIBLE).split())
    if window.class_name not in BROWSER_CLASSES:
        return title
    parts, marks = SEPARATOR.split(title), SEPARATOR.findall(title)
    at = next((i for i in range(len(parts) - 1, 0, -1) if _is_browser_name(parts[i])), None)
    if at is None:
        return title
    tab = browser_tab(title)
    return f"{tab} {marks[at - 1].strip()} {parts[at]}" if tab else parts[at]


def _has_word(text: str, name: str) -> bool:
    return _word(name).search(text.translate(INVISIBLE)) is not None


def looks_like_viewer(window: "WindowInfo | str") -> bool:
    """The window to choose when none was named: a book viewer by what was learned on this computer
    (`viewerparts.remembered`: a viewer's part at the start or the end of its tab title, a window chosen as the
    viewer before), or a title (a browser window's: its tab's, `tab_title`) with a viewer's part or a reading word
    (`VIEWER_WORDS`: "book", ...) as a word, or that ends as a window chosen before did with another book before it
    (`viewerparts.shares_an_end`). Not where the word is part of a longer run of characters (a chat page whose title
    runs the viewer's name into other words), nor a Facebook page, a notebook, the browser's bookmarks or an Excel
    workbook such as "Book1 - Excel" (`NOT_VIEWERS`), unless it was learned."""
    from .. import viewerparts

    if viewerparts.remembered(window):
        return True
    title = window.tab_title if isinstance(window, WindowInfo) else window
    low = _plain(title)
    if any(word in low for word in NOT_VIEWERS):
        return False
    memory = viewerparts.current()
    return (any(_has_word(title, name) for name in (*VIEWER_WORDS, *memory.parts))
            or viewerparts.shares_an_end(" ".join(title.split()), memory))


def viewer_rank(window: WindowInfo) -> int | None:
    """How surely *window* is the viewer: 0 for one the viewer by what was learned on this computer
    (`viewerparts.remembered`: chosen before by its title or its program, or a viewer's part at the start or the end
    of its tab title), 1 for another window that looks like a viewer (`looks_like_viewer`), None for the rest."""
    from .. import viewerparts

    if viewerparts.remembered(window):
        return 0
    return 1 if looks_like_viewer(window) else None


def viewer_candidates(windows: Sequence[WindowInfo]) -> list[WindowInfo]:
    """The windows that look most surely like the viewer (`viewer_rank`), in the order given: one to choose, or
    several of equal rank that only the reader can tell apart (none: no viewer is open)."""
    ranked = [(viewer_rank(w), w) for w in windows]
    best = min((rank for rank, _w in ranked if rank is not None), default=None)
    return [w for rank, w in ranked if best is not None and rank == best]


def match_windows(query: str, windows: Sequence[WindowInfo] | None = None) -> list[WindowInfo]:
    """The windows *query* names, case-insensitively, by the first of these rules that any window meets: the exact
    title; the exact tab title (a browser window's: `tab_title`; the whole title of other windows); a tab title that
    starts with the query; a window that looks like a viewer (`looks_like_viewer`) whose tab title contains it; any
    title containing it. One window is the one named; several mean the query is not enough to tell them apart (the
    caller says so and asks for a fuller title); none, that no window matches yet. The incident behind the order: a
    chat page whose title began with the viewer's name ("<viewer>画面翻訳アプリ - <chat> - Google Chrome") contains
    that name just as the reader's tab "<viewer> - Google Chrome" does."""
    q = _plain(query)
    if not q:
        return []
    wins = list(windows) if windows is not None else list_windows()
    tabs = [(w, _plain(w.tab_title)) for w in wins]
    rules = (
        lambda w, tab: _plain(w.title) == q,
        lambda w, tab: tab == q,
        lambda w, tab: tab.startswith(q),
        lambda w, tab: q in tab and looks_like_viewer(w),
        lambda w, tab: q in _plain(w.title),
    )
    for rule in rules:
        found = [w for w, tab in tabs if rule(w, tab)]
        if found:
            return found
    return []


if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    try:
        dwmapi: ctypes.WinDLL | None = ctypes.WinDLL("dwmapi")
    except OSError:  # pragma: no cover
        dwmapi = None

    ULONG_PTR = wintypes.WPARAM
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    # --- prototypes (explicit so 64-bit handles are never truncated) ---
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetShellWindow.restype = wintypes.HWND
    user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                      wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
    user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
                                       wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
    user32.SetWinEventHook.restype = wintypes.HANDLE
    user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    user32.UnhookWinEvent.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.NotifyWinEvent.argtypes = [wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG]
    user32.NotifyWinEvent.restype = None
    user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HANDLE, wintypes.UINT]
    user32.RedrawWindow.restype = wintypes.BOOL

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.BitBlt.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    if dwmapi is not None:
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

    PW_CLIENTONLY = 0x1
    PW_RENDERFULLCONTENT = 0x2
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    DIB_RGB_COLORS = 0
    BI_RGB = 0
    GA_ROOT = 2
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    DWMWA_CLOAKED = 14
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    SW_RESTORE = 9


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise CaptureError(Message("viewer.windows_only"))


def enable_dpi_awareness() -> None:
    """Make this process DPI aware so window rectangles are in physical pixels."""
    if not IS_WINDOWS:
        return
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except Exception:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def _window_text(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _is_cloaked(hwnd: int) -> bool:
    if dwmapi is None:
        return False
    cloaked = wintypes.DWORD(0)
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return hr == 0 and cloaked.value != 0


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        raise CaptureError(Message("viewer.window_api_failed", call="GetWindowRect", hwnd=int(hwnd)))
    return (r.left, r.top, r.right, r.bottom)


def window_rect(hwnd: int) -> Rect:
    """A window's rectangle on the screen, frame included; for a child window (a Tk widget's handle), that of the
    top-level window it belongs to."""
    _require_windows()
    root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    return _window_rect(int(root))


def visible_rect(hwnd: int) -> Rect | None:
    """`window_rect` of a window that is on the screen; None for one that is hidden, minimised or gone."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    try:
        return window_rect(hwnd)
    except CaptureError:
        return None


def window_exists(hwnd: int) -> bool:
    return bool(IS_WINDOWS and user32.IsWindow(hwnd))


def window_title(hwnd: int) -> str:
    """Current title of a window (for a browser window: the title of its active tab)."""
    _require_windows()
    return _window_text(hwnd)


def window_class(hwnd: int) -> str:
    """The class name of a window ("" outside Windows and for a handle that is no window)."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return ""
    return _class_name(hwnd)


def window_shown(hwnd: int) -> bool:
    """Whether the window *hwnd* exists, is visible and is not minimised (False outside Windows)."""
    return bool(IS_WINDOWS and user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd))


def is_browser_class(class_name: str) -> bool:
    """Whether a window of the class *class_name* is a browser's, whose title is its active tab's
    (`BROWSER_CLASSES`). A class that is not known ("": a window picked by its title alone) counts as a browser's:
    its title is checked as before."""
    return not class_name or class_name in BROWSER_CLASSES


def still_the_book(win: WindowInfo, current_title: str, query: str = "", shown: bool = True) -> bool:
    """Does the window *win* (as it was picked for the book) still show it, its title being *current_title* now?

    A browser window's title is its active tab's: it is the book while that title is (`same_book_window`). Any
    other window is the viewer itself, whose title may change with every page (an image viewer names the file it
    shows, a reader the page): it is the book as long as it is there and *shown* (`window_shown`: visible, not
    minimised), whatever its title says.
    """
    if not is_browser_class(win.class_name):
        return bool(shown)
    return same_book_window(current_title, win.title, query)


def same_book_window(current_title: str, expected_title: str, query: str = "") -> bool:
    """Does a browser window that was picked for a book still show it? (A window of any other kind: `still_the_book`.)

    A browser window's title is its active tab's, so the title changes when the
    reader's tab is switched away. The title it was picked by, the query it
    matched as a word or segment of the title (not inside a longer run: the
    tab switched from "<viewer>" to a chat page "<viewer>画面翻訳アプリ" is
    another page), or the same book name (page numbers in the title do not count, wherever they are:
    `viewerparts.unpaged`) all mean the book is still there.
    """
    from .. import viewerparts

    if not current_title or not expected_title:
        return False
    if current_title == expected_title:
        return True
    q = _plain(query)
    if q and re.search(rf"(?<![^{EDGE}]){re.escape(q)}(?![^{EDGE}])", _plain(current_title)):
        return True
    return (viewerparts.book_key_from_title(current_title) == viewerparts.book_key_from_title(expected_title)
            or viewerparts.unpaged(current_title) == viewerparts.unpaged(expected_title))


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def program_name(pid: int) -> str:
    """The file name of the program of the process *pid*, lower case ("" outside Windows and when it cannot be told:
    a process of another user or gone). Only its name is read: what TASlation remembers a viewer app by."""
    if not IS_WINDOWS or pid <= 0:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return os.path.basename(buffer.value).lower()
    finally:
        kernel32.CloseHandle(handle)


def list_windows(include_own: bool = False) -> list[WindowInfo]:
    """Visible, titled top-level windows, largest first, each with its program's file name (`program_name`)."""
    _require_windows()
    found: list[WindowInfo] = []
    own_pid = os.getpid()
    shell = user32.GetShellWindow()
    programs: dict[int, str] = {}

    @WNDENUMPROC
    def callback(hwnd, _lparam):  # type: ignore[no-untyped-def]
        try:
            if hwnd == shell or not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetAncestor(hwnd, GA_ROOT) != hwnd:
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            title = _window_text(hwnd)
            if not title or _is_cloaked(hwnd):
                return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not include_own and pid.value == own_pid:
                return True
            rect = _window_rect(hwnd)
            if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
                return True
            if pid.value not in programs:
                programs[pid.value] = program_name(pid.value)
            found.append(WindowInfo(int(hwnd), title, _class_name(hwnd), pid.value, rect, programs[pid.value]))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback, 0)
    found.sort(key=lambda w: w.width * w.height, reverse=True)
    return found


def find_window(query: str, windows: Sequence[WindowInfo] | None = None) -> WindowInfo | None:
    """The one window *query* names (`match_windows`); None when none does, and when several do (`match_windows`
    gives them, for the caller to say)."""
    found = match_windows(query, windows)
    return found[0] if len(found) == 1 else None


def client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the client area in screen pixels."""
    _require_windows()
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        raise CaptureError(Message("viewer.window_api_failed", call="GetClientRect", hwnd=int(hwnd)))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top)


def caption_rows(hwnd: int) -> int:
    """How many rows at the top of the client area are the window's own title bar. A WinUI window draws it inside the
    client area, under a child window of the class CAPTION_CHILD_CLASS that takes the title bar's input (48 rows on
    the Windows image viewer); other windows have nothing there. 0 outside Windows, for a window that is gone, in the
    window's own full screen (the bar is gone, the child stays) and when that child does not lie along the top of the
    client area."""
    if not IS_WINDOWS or not hwnd or not user32.IsWindow(hwnd) or is_fullscreen(hwnd):
        return 0
    found: list[int] = []

    @WNDENUMPROC
    def callback(child, _lparam):  # type: ignore[no-untyped-def]
        if _class_name(child) == CAPTION_CHILD_CLASS and user32.IsWindowVisible(child):
            found.append(int(child))
            return False
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    if not found:
        return 0
    return title_band(_window_rect(found[0]), client_rect_on_screen(hwnd))


def title_band(caption: Rect, client: tuple[int, int, int, int]) -> int:
    """The rows of *client* (x, y, width, height) the rectangle *caption* takes when it is a title bar: along the top,
    at least half as wide as the client area, less than a quarter as high; else 0."""
    x, y, width, height = client
    rows = caption[3] - y
    return rows if abs(caption[1] - y) <= 1 and (caption[2] - caption[0]) * 2 >= width and 0 < rows * 4 < height else 0


def _client_box(hwnd: int) -> tuple[int, int, int, int]:
    """(x, y, width, height) on the screen of what a capture of the client area shows: the client area without a
    title bar drawn in it (`caption_rows`)."""
    x, y, width, height = client_rect_on_screen(hwnd)
    rows = caption_rows(hwnd)
    return x, y + rows, width, height - rows


def _frame_bounds(hwnd: int) -> Rect:
    """The rectangle of the window as the compositor shows it (without the invisible resize borders), which is what a
    frame of Windows.Graphics.Capture holds."""
    rc = wintypes.RECT()
    if dwmapi is None or dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rc),
                                                      ctypes.sizeof(rc)) != 0:
        return _window_rect(hwnd)
    return (rc.left, rc.top, rc.right, rc.bottom)


def _compositor_frame(hwnd: int, client_only: bool) -> Image.Image | None:
    """The window's latest frame from Windows.Graphics.Capture (`wgc`), cut to the client area. A frame of another size
    than the window's (it was resized, and the session may give no frame of the new size until the window draws
    again) starts the session over, whose first frame is the window as it is (`wgc.restart`, once for every size).
    None: no frame to be had."""
    if user32.IsIconic(hwnd):
        return None
    frame = wgc.latest(hwnd)
    if frame is None:
        return None
    bounds = _frame_bounds(hwnd)
    box = wgc.crop_box(frame.size, bounds, _client_box(hwnd) if client_only else None)
    if box is None and wgc.restart(hwnd, (bounds[2] - bounds[0], bounds[3] - bounds[1])):
        frame = wgc.latest(hwnd)
        if frame is not None:
            box = wgc.crop_box(frame.size, _frame_bounds(hwnd), _client_box(hwnd) if client_only else None)
    return frame.image(box) if frame is not None and box is not None else None


def _dib_to_array(mem_dc: int, bmp: int, width: int, height: int) -> np.ndarray:
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down rows
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    buf = ctypes.create_string_buffer(width * height * 4)
    lines = gdi32.GetDIBits(mem_dc, bmp, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    if lines != height:
        raise CaptureError(Message("viewer.api_failed", call="GetDIBits"))
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)
    return np.ascontiguousarray(arr[:, :, [2, 1, 0]])  # BGRA -> RGB (copy; buf is released after return)


def _is_blank(arr: np.ndarray) -> bool:
    if arr.size == 0:
        return True
    sample = arr[:: max(1, arr.shape[0] // 64), :: max(1, arr.shape[1] // 64)]
    return int(sample.max()) - int(sample.min()) < 8


def is_blank(image: Image.Image) -> bool:
    """Whether a capture is one flat colour: what PrintWindow gives for a window it cannot draw."""
    return _is_blank(np.asarray(image))


BLACK_MEAN = 5  # a capture area darker than this on average (of 255) shows nothing: a black page with a spinner, say
BLACK_FLAT = 40  # a frame of one flat colour is black up to this: a white one is a blank page of the book


def is_black(image: Image.Image, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> bool:
    """Whether the viewer's frame *image* shows nothing: its capture area (what *margins* leave) nearly black on
    average, or the whole frame of one dark colour (`is_blank`)."""
    arr = np.asarray(image)
    if arr.size == 0:
        return True
    height, width = arr.shape[:2]
    left, top, right, bottom = (max(0, int(m)) for m in margins)
    area = arr[top:max(top, height - bottom), left:max(left, width - right)]
    if area.size == 0:
        area = arr
    if float(area[::2, ::2].mean()) < BLACK_MEAN:
        return True
    return _is_blank(arr) and float(arr[::4, ::4].mean()) < BLACK_FLAT


def capture_screen_rect(x: int, y: int, width: int, height: int) -> Image.Image:
    """Copy a rectangle of the screen (all monitors share one virtual desktop)."""
    _require_windows()
    if width <= 0 or height <= 0:
        raise CaptureError(Message("viewer.empty_rect"))
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise CaptureError(Message("viewer.api_failed", call="GetDC(screen)"))
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    try:
        old = gdi32.SelectObject(mem_dc, bmp)
        ok = gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, x, y, SRCCOPY | CAPTUREBLT)
        gdi32.SelectObject(mem_dc, old)
        if not ok:
            raise CaptureError(Message("viewer.api_failed", call="BitBlt"))
        arr = _dib_to_array(mem_dc, bmp, width, height)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
    return Image.fromarray(arr)


def capture_window(hwnd: int, client_only: bool = True, allow_screen_fallback: bool = True) -> Image.Image:
    """Capture a window's content (client area by default, without a title bar drawn in it: `caption_rows`) as an RGB
    image: its latest frame from Windows.Graphics.Capture, however old (a frame comes only when the window changes),
    which is what the window shows now, blank or not; else `PrintWindow`, else a copy of the screen."""
    _require_windows()
    if not user32.IsWindow(hwnd):
        raise CaptureError(Message("viewer.gone"))
    drawn = _compositor_frame(hwnd, client_only)
    if drawn is not None:
        return drawn
    if client_only:
        _, _, width, height = client_rect_on_screen(hwnd)
        flags = PW_CLIENTONLY | PW_RENDERFULLCONTENT
    else:
        left, top, right, bottom = _window_rect(hwnd)
        width, height = right - left, bottom - top
        flags = PW_RENDERFULLCONTENT
    if width <= 0 or height <= 0:
        raise CaptureError(Message("viewer.no_area"))

    win_dc = user32.GetWindowDC(hwnd)
    if not win_dc:
        raise CaptureError(Message("viewer.api_failed", call="GetWindowDC"))
    mem_dc = gdi32.CreateCompatibleDC(win_dc)
    bmp = gdi32.CreateCompatibleBitmap(win_dc, width, height)
    try:
        old = gdi32.SelectObject(mem_dc, bmp)
        ok = user32.PrintWindow(hwnd, mem_dc, flags)
        gdi32.SelectObject(mem_dc, old)
        arr = _dib_to_array(mem_dc, bmp, width, height) if ok else None
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, win_dc)
    if arr is not None and client_only:
        arr = arr[caption_rows(hwnd):]

    if arr is None or _is_blank(arr):
        # (never a copy of the screen where another window lies over the viewer: that would read that window)
        if not allow_screen_fallback or user32.IsIconic(hwnd) or behind_others(hwnd):
            if arr is None:
                raise CaptureError(Message("viewer.api_failed", call="PrintWindow"))
            return Image.fromarray(arr)
        x, y, w, h = _client_box(hwnd) if client_only else (*_window_rect(hwnd)[:2], width, height)
        return capture_screen_rect(x, y, w, h)
    return Image.fromarray(arr)


# --- the windows' children, the foreground ----------------------------------------

CAPTION_CHILD_CLASS = "InputNonClientPointerSource"  # WinUI's child over the title bar it draws (`caption_rows`)


def give_foreground(hwnd: int) -> bool:
    """Give the foreground to *hwnd*, a window of this program that is on the screen, from whichever window has it
    (the viewer, say). No key is pressed for it (an ALT tap, the usual way to be let through, would reach the
    viewer: Chrome takes a lone ALT for its menu, and the reader's next key would go there): for a moment this
    thread shares its input with the foreground window's, which is what lets Windows hand the foreground over.
    Returns whether *hwnd* has it now; a minimised or hidden window is left as it is."""
    _require_windows()
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False
    front = user32.GetForegroundWindow()
    if front == hwnd:
        return True
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(front, None) if front else 0
    attached = bool(other) and other != me and bool(user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return user32.GetForegroundWindow() == hwnd


# --- monitors ------------------------------------------------------------------

MONITOR_DEFAULTTONEAREST = 2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0004, 0x0010
SWP_STAY = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE  # the order of the windows changes, nothing else
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
WS_EX_TOPMOST = 0x00000008
GW_HWNDPREV, GW_OWNER = 3, 4  # the window above in the order of the windows; the window that owns another
WS_EX_TRANSPARENT = 0x00000020
MAX_WINDOWS_ABOVE = 2048  # the order of the windows can change during the walk: it ends at this many


def monitor_rect(hwnd: int) -> Rect | None:
    """The whole rectangle (taskbar included) of the monitor that holds most of the window *hwnd*, or the one
    nearest to it; None outside Windows or when it cannot be had."""
    if not IS_WINDOWS or not hwnd:
        return None
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


def work_area(hwnd: int) -> Rect | None:
    """The rectangle of the monitor nearest to the window *hwnd* without the taskbar; None outside Windows or when
    it cannot be had."""
    if not IS_WINDOWS or not hwnd:
        return None
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    r = info.rcWork
    return (r.left, r.top, r.right, r.bottom)


def move_window(hwnd: int, rect: Rect) -> bool:
    """Put the top-level window of *hwnd* exactly on *rect* (screen pixels, frame included), neither raised nor
    activated. Tk follows a window moved this way (its geometry is read back from Windows)."""
    if not IS_WINDOWS or not hwnd or rect[2] <= rect[0] or rect[3] <= rect[1]:
        return False
    root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    return bool(user32.SetWindowPos(root, None, rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1],
                                    SWP_NOZORDER | SWP_NOACTIVATE))


# --- a viewer's window a version up to 1.0.1 enlarged, put back -----------------

def _size(rect: Rect) -> tuple[int, int]:
    return rect[2] - rect[0], rect[3] - rect[1]


@dataclass
class Enlarged:
    """A viewer's window a version up to 1.0.1 enlarged: its rectangle *before*, and the one it was *given* (what the
    window made of the size it was offered). Such a version kept it in the state folder's ui.json until it was put
    back; one left there is put back once at the start (`recovery.put_back_enlarged`, `restore_window`)."""

    hwnd: int
    before: Rect
    given: Rect

    @property
    def changed(self) -> bool:
        """Whether the window's size changed at all (a window of a fixed size stays as it was)."""
        return _size(self.given) != _size(self.before)

    def has_its_size(self, rect: Rect) -> bool:
        """Whether the window rectangle *rect* still has the size it was given."""
        return _size(rect) == _size(self.given)


FULL_SCREEN_SLACK = 2  # pixels a window may stop short of its monitor and still fill it


def is_fullscreen(hwnd: int) -> bool:
    """Whether the window *hwnd* takes in the whole of its monitor (its own full-screen view, or a borderless window
    as large); False outside Windows or when that cannot be told."""
    if not IS_WINDOWS or not hwnd:
        return False
    monitor = monitor_rect(hwnd)
    try:
        rect = window_rect(hwnd)
    except CaptureError:
        return False
    if monitor is None:
        return False
    # a browser's full screen stops FULL_SCREEN_SLACK short of the monitor (Chrome: one row, for an auto-hidden taskbar)
    return (rect[0] - monitor[0] <= FULL_SCREEN_SLACK and rect[1] - monitor[1] <= FULL_SCREEN_SLACK
            and monitor[2] - rect[2] <= FULL_SCREEN_SLACK and monitor[3] - rect[3] <= FULL_SCREEN_SLACK)


LWA_COLORKEY, LWA_ALPHA = 0x1, 0x2
WS_EX_LAYERED, WS_EX_TOOLWINDOW = 0x00080000, 0x00000080
TASKBAR_CLASS = "Shell_TrayWnd"


def fully_opaque(hwnd: int) -> bool:
    """Whether the top-level window *hwnd* hides what lies under it, as Chromium's occlusion tracker counts a window
    that covers a browser (`gfx::IsWindowVisibleAndFullyOpaque`, ui/gfx/win/hwnd_util.cc): shown, not minimised nor
    cloaked, not click-through, not a tool window (the taskbar is), and not layered with an alpha below 255 or a
    colour key (or with attributes that cannot be read: UpdateLayeredWindow). TASlation's see-through lettering and panes
    are not."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False
    if _is_cloaked(hwnd):
        return False
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TRANSPARENT or (ex & WS_EX_TOOLWINDOW and window_class(hwnd) != TASKBAR_CLASS):
        return False
    if ex & WS_EX_LAYERED:
        key, alpha, flags = wintypes.DWORD(), ctypes.c_ubyte(), wintypes.DWORD()
        if not user32.GetLayeredWindowAttributes(hwnd, ctypes.byref(key), ctypes.byref(alpha), ctypes.byref(flags)):
            return False
        if flags.value & LWA_COLORKEY or (flags.value & LWA_ALPHA and alpha.value < 255):
            return False
    return True


def covered_by_opaque(hwnd: int) -> bool:
    """Whether a window that hides what lies under it (`fully_opaque`) lies over any of the client area of *hwnd*:
    only then may a browser have stopped drawing behind it (fully covered), and draw itself anew - black for a moment
    - once it gets the foreground. A browser under see-through windows only (TASlation's lettering and panes) never
    stopped drawing. False outside Windows or for a window that is gone."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return False
    try:
        x, y, width, height = client_rect_on_screen(hwnd)
    except CaptureError:
        return False
    viewer = (x, y, x + width, y + height)
    above = user32.GetWindow(user32.GetAncestor(hwnd, GA_ROOT) or hwnd, GW_HWNDPREV)
    for _ in range(MAX_WINDOWS_ABOVE):
        if not above:
            return False
        if fully_opaque(above):
            try:
                if rects_overlap(viewer, _window_rect(above)):
                    return True
            except CaptureError:
                pass
        above = user32.GetWindow(above, GW_HWNDPREV)
    return False


SW_SHOWNOACTIVATE = 4  # shown in its most recent size and position, not activated


def window_minimised(hwnd: int) -> bool:
    """Whether the window *hwnd* exists and is minimised (False outside Windows)."""
    return bool(IS_WINDOWS and hwnd and user32.IsWindow(hwnd) and user32.IsIconic(hwnd))


def unminimise_window(hwnd: int, below: int | None = None) -> bool:
    """The minimised window *hwnd* shown again as it was before it was minimised - in its last normal size, or
    maximised when it was maximised then (ShowWindow SW_SHOWNOACTIVATE honours WPF_RESTORETOMAXIMIZED) - neither
    activated nor brought to the foreground, and no key pressed. It is then put directly behind the window *below*
    (TASlation's own): it covers nothing of TASlation, and it does not go to the bottom either, where a browser fully
    covered by opaque windows stops drawing (`covered_by_opaque`). Under a topmost *below* it stays where Windows
    puts it (placed after a topmost window it would become topmost itself). Returns whether it was restored; nothing
    is done outside Windows, or for a window that is gone or not minimised."""
    if not window_minimised(hwnd):
        return False
    root = int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)
    user32.ShowWindow(root, SW_SHOWNOACTIVATE)
    if user32.IsIconic(root):
        return False
    if below and below != root and user32.IsWindow(below) \
            and not user32.GetWindowLongW(below, GWL_EXSTYLE) & WS_EX_TOPMOST:
        user32.SetWindowPos(root, below, 0, 0, 0, 0, SWP_STAY)
    return True


def restore_window(enlarged: Enlarged) -> bool:
    """The enlarged window back on its rectangle before, only while it still has the size it was given (the
    reader may have resized it since, or minimised, maximised or closed it). No key is pressed for it. Returns whether
    it was put back."""
    hwnd = enlarged.hwnd
    if not window_shown(hwnd) or user32.IsZoomed(hwnd):
        return False
    try:
        if not enlarged.has_its_size(window_rect(hwnd)):
            return False
    except CaptureError:
        return False
    return move_window(hwnd, enlarged.before)


# --- a viewer that does not draw behind other windows, raised for a moment -----------

@dataclass
class Raised:
    """A window raised for a moment (`raise_window`): its top-level window and the window that was above it."""

    hwnd: int
    above: int


_raised: dict[int, Raised] = {}  # what is raised now: never left so, also at exit


def _window_above(root: int) -> int:
    """The window to put *root* back under: the nearest one above it that is shown and not its own (a hidden window it
    owns, as its IME window, moves up with it). 0 when it lay on top of the ordinary windows, which is where
    HWND_NOTOPMOST puts it (under a topmost window it would become topmost itself)."""
    above = user32.GetWindow(root, GW_HWNDPREV)
    for _ in range(MAX_WINDOWS_ABOVE):
        if not above or user32.GetWindowLongW(above, GWL_EXSTYLE) & WS_EX_TOPMOST:
            return 0
        if user32.IsWindowVisible(above) and user32.GetWindow(above, GW_OWNER) != root:
            return int(above)
        above = user32.GetWindow(above, GW_HWNDPREV)
    return 0


def raise_window(hwnd: int) -> Raised | None:
    """The window *hwnd* made topmost: it comes to the top of the screen and redraws, with no key and no change of the
    foreground (SWP_NOACTIVATE; HWND_TOP with it does not raise the window). `lower_window` puts it back; prefer
    `raised_window`. None, and nothing touched, for a window that is gone or minimised, raised already or topmost of
    its own."""
    if not IS_WINDOWS or not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    root = int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)
    if root in _raised or user32.GetWindowLongW(root, GWL_EXSTYLE) & WS_EX_TOPMOST:
        return None
    above = _window_above(root)
    if not user32.SetWindowPos(root, HWND_TOPMOST, 0, 0, 0, 0, SWP_STAY):
        return None
    _raised[root] = raised = Raised(root, above)
    return raised


def lower_window(raised: Raised) -> None:
    """The window raised with `raise_window` no longer topmost, and back under the window that was above it."""
    if _raised.pop(raised.hwnd, None) is None or not user32.IsWindow(raised.hwnd):
        return
    user32.SetWindowPos(raised.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_STAY)
    if raised.above and user32.IsWindow(raised.above):
        user32.SetWindowPos(raised.hwnd, raised.above, 0, 0, 0, 0, SWP_STAY)


def _lower_all() -> None:
    for raised in list(_raised.values()):
        lower_window(raised)


atexit.register(_lower_all)


# --- the viewer kept directly under TASlation's window -----------------------------------
GW_HWNDNEXT = 2  # the window below in the order of the windows
HWND_TOP = 0
TK_CLASSES = "Tk"  # (the start of the class name of the windows Tk makes: TkTopLevel, TkChild)


@dataclass(frozen=True)
class Placed:
    """A top-level window as the walk of the order of the windows sees it (`windows_between`): shown (visible, not
    minimised, not cloaked), topmost, click-through (WS_EX_TRANSPARENT), its process, its class, the top-level window
    that owns it (GA_ROOTOWNER: itself when none does) and its rectangle."""

    hwnd: int
    shown: bool = True
    topmost: bool = False
    see_through: bool = False
    pid: int = 0
    class_name: str = ""
    root_owner: int = 0
    rect: Rect = (0, 0, 0, 0)


def windows_between(own: int, viewer: int, below: Callable[[int], int], about: Callable[[int], Placed],
                    own_pid: int) -> list[int] | None:
    """The windows between TASlation's top-level window *own* and the viewer's *viewer* in the order of the windows
    that could hide some of the viewer, from the top down: shown, not topmost (one that is stays above the viewer
    whatever is done: the viewer is never made topmost), not click-through, not the viewer's own (its dialogs and
    popups, which Windows keeps above it and moves with it), not TASlation's own (one its window owns - a dialog, the
    panel beside a bubble, an input method's window - or one Tk made in its process), and over some of the viewer's
    rectangle. *below*(h): the window under *h* (0: none); *about*(h): what is known of it (`Placed`). None when the
    viewer does not lie under *own* (above it, or gone) - nothing to do then."""
    target = about(viewer).rect
    found: list[int] = []
    h = below(own)
    for _ in range(MAX_WINDOWS_ABOVE):
        if not h:
            return None
        if h == viewer:
            return found
        w = about(h)
        mine = w.root_owner == own or (w.pid == own_pid and w.class_name.startswith(TK_CLASSES))
        if (w.shown and not w.topmost and not w.see_through and w.root_owner != viewer and not mine
                and rects_overlap(w.rect, target)):
            found.append(h)
        h = below(h)
    return None


class _Order:
    """What `keep_viewer_under` asks of Windows (user32), one call each; tests give a list of made-up windows."""

    def root(self, hwnd: int) -> int:
        return int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd) if user32.IsWindow(hwnd) else 0

    def minimised(self, hwnd: int) -> bool:
        return bool(user32.IsIconic(hwnd))

    def topmost(self, hwnd: int) -> bool:
        return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)

    def below(self, hwnd: int) -> int:
        return int(user32.GetWindow(hwnd, GW_HWNDNEXT) or 0)

    def about(self, hwnd: int) -> Placed:
        ex = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
        shown = bool(user32.IsWindowVisible(hwnd)) and not user32.IsIconic(hwnd) and not _is_cloaked(hwnd)
        try:
            rect = _window_rect(hwnd) if shown else (0, 0, 0, 0)
        except CaptureError:
            rect = (0, 0, 0, 0)
        return Placed(hwnd, shown, bool(ex & WS_EX_TOPMOST), bool(ex & WS_EX_TRANSPARENT), window_pid(hwnd),
                      window_class(hwnd) if shown else "", int(user32.GetAncestor(hwnd, GA_ROOTOWNER) or hwnd), rect)

    def own_pid(self) -> int:
        return os.getpid()

    def place(self, hwnd: int, after: int) -> bool:
        return bool(user32.SetWindowPos(hwnd, after, 0, 0, 0, 0, SWP_STAY))

    def tell(self, hwnd: int) -> None:
        user32.NotifyWinEvent(EVENT_OBJECT_LOCATIONCHANGE, hwnd, OBJID_WINDOW, CHILDID_SELF)


def keep_viewer_under(viewer: int, own: int, order: _Order | None = None, between: list[int] | None = None) -> str:
    """The viewer's window *viewer* put directly under TASlation's window *own* in the order of the windows when a
    window that could hide some of it lies between the two (`windows_between`): SetWindowPos with SWP_NOACTIVATE and
    neither its place nor its size changed - no activation, no change of the foreground, no key, no click; only the
    viewer's place in the order. A window that lay between is not moved: it lies under the viewer from then on, above
    what lay under the viewer before. Under a topmost *own* the viewer goes to the top
    of the windows that are not topmost (HWND_TOP), right under the topmost ones: put after a topmost window it would
    become topmost itself. What was done: "placed", "" (nothing between could hide it), or why nothing was:
    "not windows", "gone", "minimised" (either window), "topmost" (the viewer is topmost: nothing can lie over it but
    other topmost windows), "above" (the viewer does not lie under TASlation's window), "refused" (Windows did not take
    it: a viewer that runs as administrator, say). *between* (a list) is given the windows that lay between, from the
    top down. Once placed, a location change of the viewer's window is announced (NotifyWinEvent
    EVENT_OBJECT_LOCATIONCHANGE, OBJID_WINDOW: an event to the programs that listen for window events, nothing sent to
    the viewer): a browser's occlusion tracking (Chromium's, Firefox's) looks again at a window event and does not at a
    change of the order alone - seen on the stand-in: put over the window that hid it, it drew nothing for 13.7 s more,
    until another program's window moved. (TASlation's own watch of the viewer asks only for the events of the viewer's
    process: this one is not among them.) (Checked on throwaway windows, the viewer's of another process, the caller not in front: put after
    TASlation's window it lies directly under it; under a topmost one HWND_TOP puts it over a window that lay between
    and leaves it not topmost, where put after the topmost window it became topmost.)"""
    if order is None:
        if not IS_WINDOWS:
            return "not windows"
        order = _Order()
    viewer, own = order.root(viewer), order.root(own)
    if not viewer or not own or viewer == own:
        return "gone"
    if order.minimised(viewer) or order.minimised(own):
        return "minimised"
    if order.topmost(viewer):
        return "topmost"
    found = windows_between(own, viewer, order.below, order.about, order.own_pid())
    if found is None:
        return "above"
    if not found:
        return ""
    if between is not None:
        between.extend(found)
    if not order.place(viewer, HWND_TOP if order.topmost(own) else own):
        return "refused"
    order.tell(viewer)
    return "placed"


def behind_others(hwnd: int) -> bool:
    """Whether another window on the screen lies over the client area of the window *hwnd*: a copy of the screen
    there would show that window. Click-through overlays (WS_EX_TRANSPARENT) and windows that are cloaked, hidden or
    minimised do not count. False outside Windows or for a window that is gone."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return False
    try:
        x, y, width, height = client_rect_on_screen(hwnd)
    except CaptureError:
        return False
    viewer = (x, y, x + width, y + height)
    above = user32.GetWindow(user32.GetAncestor(hwnd, GA_ROOT) or hwnd, GW_HWNDPREV)
    for _ in range(MAX_WINDOWS_ABOVE):
        if not above:
            return False
        if (user32.IsWindowVisible(above) and not user32.IsIconic(above) and not _is_cloaked(above)
                and not user32.GetWindowLongW(above, GWL_EXSTYLE) & WS_EX_TRANSPARENT):
            try:
                if rects_overlap(viewer, _window_rect(above)):
                    return True
            except CaptureError:
                pass
        above = user32.GetWindow(above, GW_HWNDPREV)
    return False


# --- whether a viewer draws while it is covered, found out with no key ---------------
RDW_INVALIDATE, RDW_ALLCHILDREN = 0x0001, 0x0080


def windows_over(hwnd: int, opaque: bool = False) -> list[Rect]:
    """The rectangles of the windows above the top-level window of *hwnd* that a copy of the screen would show, as
    `behind_others` counts them (shown, not minimised nor cloaked, not click-through), the nearest first; with
    *opaque* only those that hide what lies under them (`fully_opaque`: not TASlation's see-through windows, say). []
    outside Windows or for a window that is gone."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return []
    found: list[Rect] = []
    above = user32.GetWindow(user32.GetAncestor(hwnd, GA_ROOT) or hwnd, GW_HWNDPREV)
    for _ in range(MAX_WINDOWS_ABOVE):
        if not above:
            break
        if opaque and not fully_opaque(above):
            pass
        elif (user32.IsWindowVisible(above) and not user32.IsIconic(above) and not _is_cloaked(above)
                and not user32.GetWindowLongW(above, GWL_EXSTYLE) & WS_EX_TRANSPARENT):
            try:
                found.append(_window_rect(above))
            except CaptureError:
                pass
        above = user32.GetWindow(above, GW_HWNDPREV)
    return found


SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79


def fully_covered(hwnd: int, opaque: bool = False) -> bool:
    """Whether the windows above *hwnd* (`windows_over`) hide every pixel of its client area that lies on the screens
    (what lies off them is seen by no one either; Chromium's occlusion tracking counts it so too): only then can a
    viewer have stopped drawing for being covered - Windows composes every window from a surface of its own, so a
    window partly in sight draws as one in front does, and Chromium and Firefox stop only for a window hidden wholly.
    With *opaque* only the windows that hide what lies under them count (`fully_opaque`): what a browser stops drawing
    under. False outside Windows, for a window that is gone, minimised or hidden."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False
    try:
        x, y, width, height = client_rect_on_screen(hwnd)
    except CaptureError:
        return False
    if width <= 0 or height <= 0:
        return False
    vx, vy = user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw, vh = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if vw <= 0 or vh <= 0:
        vx, vy, vw, vh = x, y, width, height
    seen = (max(x, vx), max(y, vy), min(x + width, vx + vw), min(y + height, vy + vh))
    return covers(windows_over(hwnd, opaque), seen)


def ask_repaint(hwnd: int) -> bool:
    """Ask the window *hwnd* (its top-level window and its children) to paint itself anew: `RedrawWindow` with
    RDW_INVALIDATE | RDW_ALLCHILDREN, what Windows itself asks of a window when another one moves off it. It sends no
    key, takes no focus and changes neither the foreground nor the order of the windows. Returns whether Windows took
    the request."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return False
    root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    return bool(user32.RedrawWindow(root, None, None, RDW_INVALIDATE | RDW_ALLCHILDREN))


def fresh_frame(hwnd: int, seq: int) -> bool:
    """Whether the capture (`wgc`) holds a frame of the window *hwnd* newer than frame *seq* and of the window's
    present size: the window drew it since. Nothing is waited for; a session is started when there is none (it has
    no frame of its own yet, so False)."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return False
    frame = wgc.latest(hwnd, 0.0)
    return frame is not None and frame.seq > seq and wgc.crop_box(frame.size, _frame_bounds(hwnd)) is not None


def window_pid(hwnd: int) -> int:
    """The id of the process that owns the window *hwnd* (0 outside Windows or for a window that is gone)."""
    if not IS_WINDOWS or not user32.IsWindow(hwnd):
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


# --- who is in front, and what happens to the viewer's window --------------------

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
EVENT_OBJECT_NAMECHANGE = 0x800C
WINEVENT_OUTOFCONTEXT = 0x0000
OBJID_WINDOW = 0
CHILDID_SELF = 0
GA_ROOTOWNER = 3
VIEWER_NOTES = {EVENT_OBJECT_DESTROY: "closed", EVENT_OBJECT_LOCATIONCHANGE: "moved",
                EVENT_OBJECT_NAMECHANGE: "renamed"}
MAX_NOTES = 512  # notes kept until they are taken (a window dragged for long gives one "moved" a step)


def foreground_window() -> int:
    """The window in front (0: none, or not Windows)."""
    return int(user32.GetForegroundWindow() or 0) if IS_WINDOWS else 0


def last_input() -> int:
    """When the last input of the session came (a key, a click, the wheel, the pointer moved), in Windows' millisecond
    ticks; only to tell that some came (0 outside Windows)."""
    if not IS_WINDOWS:
        return 0
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    return int(info.dwTime) if user32.GetLastInputInfo(ctypes.byref(info)) else 0


def window_at_pointer() -> int:
    """The top-level window under the mouse pointer (0: none, or not Windows)."""
    if not IS_WINDOWS:
        return 0
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return 0
    hwnd = user32.WindowFromPoint(point)
    return int(user32.GetAncestor(hwnd, GA_ROOT) or 0) if hwnd else 0


def front_owner(pid: int, tops: Sequence[int], own_pid: int, viewer: int) -> str:
    """Whose window is in front, from that window's process *pid* and its top-level windows *tops* (itself, its root,
    its owner's root): "own" (a window of this program: the see-through window, a pane, a dialog, a message box),
    "viewer" (the viewer's window *viewer*, or a popup it owns), "other" (anything else, or nothing)."""
    if pid and pid == own_pid:
        return "own"
    if viewer and viewer in tops:
        return "viewer"
    return "other"


def foreground_owner(hwnd: int, viewer: int, own_pid: int | None = None) -> str:
    """`front_owner` of the window *hwnd* (the one in front) for the viewer's window *viewer*."""
    if not IS_WINDOWS or not hwnd:
        return "other"
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    tops = (int(hwnd), int(user32.GetAncestor(hwnd, GA_ROOT) or 0), int(user32.GetAncestor(hwnd, GA_ROOTOWNER) or 0))
    return front_owner(pid.value, tops, os.getpid() if own_pid is None else own_pid, int(viewer or 0))


class WindowEvents:
    """What Windows says about windows, from out-of-context WinEvent hooks (``SetWinEventHook``): which window comes
    to the front (any window, `start`), and the watched window (the viewer's, `watch`) renamed - a browser window's
    title is its active tab's -, moved or resized, or closed.

    The callbacks come in while the thread that set the hooks reads its messages: Tk's event loop, for the window.
    They only take notes - ("front", hwnd), ("renamed" | "moved" | "closed", the watched hwnd) - which `take` hands
    over: calling into Tk from such a callback breaks Python (Tk's own thread state is not there for it; the window
    takes the notes on a timer of its own). The callback object is kept as long as the hooks are; `close` removes
    them, from the same thread."""

    def __init__(self) -> None:
        self.front = 0  # the window that came to the front last
        self.viewer = 0  # the window watched
        self.notes: list[tuple[str, int]] = []
        self._hooks: list[int] = []
        self._viewer_hooks: list[int] = []
        self._proc = WINEVENTPROC(self._note) if IS_WINDOWS else None

    @classmethod
    def start(cls) -> "WindowEvents | None":
        """The hook on the window in front; None outside Windows or when it cannot be set."""
        if not IS_WINDOWS:
            return None
        events = cls()
        hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, events._proc, 0, 0,
                                      WINEVENT_OUTOFCONTEXT)
        if not hook:
            return None
        events._hooks.append(int(hook))
        events.front = foreground_window()
        return events

    @property
    def active(self) -> bool:
        return bool(self._hooks)

    def watch(self, hwnd: int | None) -> bool:
        """Watch the window *hwnd* (renamed, moved or resized, closed) in place of the one watched before; None: no
        window. Only the events of its process and thread are asked for, and only its own are noted. False when a
        hook cannot be set (then none is)."""
        self._unhook(self._viewer_hooks)
        self.viewer = int(hwnd or 0)
        if not self.viewer:
            return True
        if not IS_WINDOWS or not self._hooks:
            return False
        pid = wintypes.DWORD(0)
        thread = user32.GetWindowThreadProcessId(self.viewer, ctypes.byref(pid))
        if not thread:
            return False
        for first, last in ((EVENT_OBJECT_DESTROY, EVENT_OBJECT_DESTROY),
                            (EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_NAMECHANGE)):
            hook = user32.SetWinEventHook(first, last, None, self._proc, pid.value, thread, WINEVENT_OUTOFCONTEXT)
            if not hook:
                self._unhook(self._viewer_hooks)
                return False
            self._viewer_hooks.append(int(hook))
        return True

    def take(self) -> list[tuple[str, int]]:
        """The notes taken since the last call, oldest first."""
        notes, self.notes = self.notes, []
        return notes

    def close(self) -> None:
        """Remove every hook (no note comes in after this)."""
        self._unhook(self._viewer_hooks)
        self._unhook(self._hooks)
        self.viewer = 0

    def _unhook(self, hooks: list[int]) -> None:
        while hooks:
            hook = hooks.pop()
            if IS_WINDOWS:
                user32.UnhookWinEvent(hook)

    def _note(self, _hook, event, hwnd, id_object, id_child, _thread, _ms) -> None:  # type: ignore[no-untyped-def]
        """The callback: a note of what happened, nothing more (no call into Tk: see the class)."""
        try:
            if event == EVENT_SYSTEM_FOREGROUND:
                self.front = int(hwnd or 0)
                self._add("front", self.front)
            elif (hwnd and int(hwnd) == self.viewer and id_object == OBJID_WINDOW and id_child == CHILDID_SELF
                  and event in VIEWER_NOTES):
                self._add(VIEWER_NOTES[event], self.viewer)
        except Exception:  # noqa: BLE001 - a callback from Windows must never raise
            pass

    def _add(self, kind: str, hwnd: int) -> None:
        note = (kind, hwnd)
        if self.notes and self.notes[-1] == note:  # a window dragged: one note for the run
            return
        if len(self.notes) >= MAX_NOTES:  # not taken for long: the oldest go
            del self.notes[: len(self.notes) - MAX_NOTES + 1]
        self.notes.append(note)


class Fronted(NamedTuple):
    """A window that came to the front (`ForegroundNotes`): when (``time.monotonic``), the window, its process, its
    top-level window and the one that owns it (GA_ROOTOWNER), and - for a window of this process only - its class
    name ("" for any other program's: nothing of another program is kept but that it was another)."""

    at: float
    hwnd: int
    pid: int
    root: int
    owner: int
    own_class: str


class ForegroundNotes:
    """Every change of the window in front, from an out-of-context WinEvent hook (EVENT_SYSTEM_FOREGROUND) of the
    thread that sets it: its callbacks come while that thread reads its messages (Tk's loop, for the window), and only
    note what came (`Fronted`, at most MAX_NOTES kept until `take`n) - no call into Tk. Under Tk's loop the hook was
    seen to bring one of two changes in a stand-in run: `now` gives the window in front at the log's tick as well.
    For the see-through mode's log of the foreground (`ui.seethrough.foreground_tick`): no title, no text of any
    window is read."""

    def __init__(self) -> None:
        self.notes: list[Fronted] = []
        self._hook = 0
        self._me = os.getpid()
        self._proc = WINEVENTPROC(self._note) if IS_WINDOWS else None

    @classmethod
    def start(cls) -> "ForegroundNotes | None":
        """The hook set (on this thread); None outside Windows. Where the hook cannot be set the notes are there all
        the same, with no hook (`hooked` False): `now` is all they give."""
        if not IS_WINDOWS:
            return None
        notes = cls()
        hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, notes._proc, 0, 0,
                                      WINEVENT_OUTOFCONTEXT)
        notes._hook = int(hook or 0)
        return notes

    @property
    def hooked(self) -> bool:
        return bool(self._hook)

    def take(self) -> list[Fronted]:
        """The windows that came to the front since the last call, oldest first."""
        notes, self.notes = self.notes, []
        return notes

    def now(self) -> Fronted:
        """The window in front now, as a note (the log looks at it on each of its ticks as well: a change the hook
        did not bring is not lost)."""
        return fronted(foreground_window(), self._me)

    def close(self) -> None:
        """The hook removed (from the thread that set it): no note comes in after this."""
        hook, self._hook = self._hook, 0
        if hook and IS_WINDOWS:
            user32.UnhookWinEvent(hook)

    def _note(self, _hook, event, hwnd, _id_object, _id_child, _thread, _ms) -> None:  # type: ignore[no-untyped-def]
        """The callback: what came to the front, noted (see the class)."""
        try:
            if event != EVENT_SYSTEM_FOREGROUND:
                return
            self.notes.append(fronted(int(hwnd or 0), self._me))
            if len(self.notes) > MAX_NOTES:  # (not taken for long: the oldest go)
                del self.notes[: len(self.notes) - MAX_NOTES]
        except Exception:  # noqa: BLE001 - a callback from Windows must never raise
            pass


def fronted(hwnd: int, own_pid: int | None = None) -> Fronted:
    """The window *hwnd* that came to the front now, as `ForegroundNotes` notes it."""
    at = time.monotonic()
    if not IS_WINDOWS or not hwnd:
        return Fronted(at, int(hwnd or 0), 0, 0, 0, "")
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    root = int(user32.GetAncestor(hwnd, GA_ROOT) or 0)
    owner = int(user32.GetAncestor(hwnd, GA_ROOTOWNER) or 0)
    me = os.getpid() if own_pid is None else own_pid
    return Fronted(at, int(hwnd), int(pid.value), root, owner, _class_name(hwnd) if pid.value == me else "")


def stay_on_top(hwnd: int) -> bool:
    """The top-level window *hwnd* made topmost, neither activated nor given the foreground (SetWindowPos with
    SWP_NOACTIVATE, its place and size kept): a dialog that came by itself stays in sight above a full-screen viewer
    and takes nothing from it. Whether it is topmost now (False outside Windows, for a handle that is no window)."""
    if not IS_WINDOWS or not hwnd or not user32.IsWindow(hwnd):
        return False
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_STAY)
    return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)
