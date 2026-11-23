"""TASlation's icon in the notification area, for see-through mode (`ui.seethrough`), where TASlation's own window is
never on the screen: the icon and its menu are the way to the program while no viewer is in front and the side panes
are hidden.

* ``Shell_NotifyIconW`` through ctypes (no package of its own), on a thread of its own with a hidden window of its own
  (never shown) for the icon's messages; the icon is the application's own (`ui.layout.ICON_ICO`).
* A click on it (left or right) is only noted here (`take_clicks`: which button, where the pointer was); the Tk thread
  acts on it - its menu (`ui.see_menu`). Nothing here takes the foreground or presses anything.
* Explorer started again (the "TaskbarCreated" message every top-level window gets): the icon is put back.
* `close` takes the icon away and ends the thread; an icon that could not be added (`start` gives None then) leaves
  nothing behind."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"

CLASS = "TASlationTray"
CALLBACK = 0x8000 + 0x51  # (WM_APP + 0x51) the message the icon's events come in
ICON_ID = 1
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
WM_DESTROY, WM_CLOSE, WM_LBUTTONUP, WM_RBUTTONUP = 0x0002, 0x0010, 0x0202, 0x0205
WS_EX_TOOLWINDOW = 0x00000080
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
SM_CXSMICON, SM_CYSMICON = 49, 50
ERROR_CLASS_ALREADY_EXISTS = 1410
START_S = 2.0  # how long `start` waits for the icon to be added
CLICKS_KEPT = 8

if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                    ("guidItem", ctypes.c_ubyte * 16), ("hBalloonIcon", wintypes.HICON)]

    _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                        wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.DefWindowProcW.restype = LRESULT
    _user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _user32.GetMessageW.restype = wintypes.BOOL
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.restype = LRESULT
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.PostQuitMessage.argtypes = [ctypes.c_int]
    _user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    _user32.RegisterWindowMessageW.restype = wintypes.UINT
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.GetCursorPos.restype = wintypes.BOOL
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                   wintypes.UINT]
    _user32.LoadImageW.restype = wintypes.HANDLE
    _user32.DestroyIcon.argtypes = [wintypes.HICON]
    _user32.DestroyIcon.restype = wintypes.BOOL
    _shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
    _shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def shell_notify(action: int, data: Any) -> bool:
    """``Shell_NotifyIconW(action, data)``; whether the shell took it. (The tests put their own in its place: no icon
    of theirs shows.)"""
    return bool(_shell32.Shell_NotifyIconW(action, ctypes.byref(data)))


_trays: dict[int, "Tray"] = {}  # the icon's hidden window -> its Tray


def _proc(hwnd, message, wparam, lparam):  # type: ignore[no-untyped-def]
    tray = _trays.get(int(hwnd or 0))
    if tray is not None:
        out = tray._message(int(message), int(wparam or 0), int(lparam or 0))
        if out is not None:
            return out
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


def _load_icon(path: Path | None) -> int:
    """The small icon of the .ico *path* at the system's small-icon size (0: none - the shell then shows none)."""
    if path is None or not Path(path).is_file():
        return 0
    size = (_user32.GetSystemMetrics(SM_CXSMICON), _user32.GetSystemMetrics(SM_CYSMICON))
    return int(_user32.LoadImageW(None, str(path), IMAGE_ICON, size[0], size[1], LR_LOADFROMFILE) or 0)


def _cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(point)):
        return 0, 0
    return int(point.x), int(point.y)


class Tray:
    """The icon and its thread (see the module's notes): made with `start` (None where there can be none), its clicks
    taken by the Tk thread (`take_clicks`), ended with `close`. ``counts`` are numbers only."""

    def __init__(self, icon: Path | None, tip: str):
        self.icon_path, self.tip = icon, str(tip)[:127]
        self.hwnd = 0
        self.added = False
        self.counts = {"adds": 0, "readds": 0, "clicks": 0, "failed": 0}
        self._clicks: deque[tuple[str, int, int, float]] = deque(maxlen=CLICKS_KEPT)
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._icon = 0
        self._taskbar_created = 0

    @classmethod
    def start(cls, icon: Path | None, tip: str) -> "Tray | None":
        if not IS_WINDOWS or not _register_class():
            return None
        self = cls(icon, tip)
        self._thread = threading.Thread(target=self._run, name="taslation-tray", daemon=True)
        self._thread.start()
        if not self._ready.wait(START_S) or not self.hwnd or not self.added:
            self.close()
            return None
        return self

    def take_clicks(self) -> list[tuple[str, int, int, float]]:
        """The clicks on the icon since the last call: (button "left" or "right", the pointer's x and y on the screen,
        when), the oldest first."""
        out = []
        while self._clicks:
            try:
                out.append(self._clicks.popleft())
            except IndexError:
                break
        return out

    def close(self) -> None:
        hwnd = self.hwnd
        if hwnd:
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(2.0)

    # ------------------------------------------------------------------ the icon's thread
    def _run(self) -> None:
        self._taskbar_created = int(_user32.RegisterWindowMessageW("TaskbarCreated") or 0)
        hwnd = _user32.CreateWindowExW(WS_EX_TOOLWINDOW, CLASS, "TASlation tray", 0, 0, 0, 0, 0, None, None,
                                       _kernel32.GetModuleHandleW(None), None)
        self.hwnd = int(hwnd or 0)
        if self.hwnd:
            _trays[self.hwnd] = self
            self._icon = _load_icon(self.icon_path)
            self.added = self._add()
        self._ready.set()
        if not self.hwnd:
            return
        msg = wintypes.MSG()
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._delete()
            _trays.pop(self.hwnd, None)
            if _user32.IsWindow(self.hwnd):
                _user32.DestroyWindow(self.hwnd)
            if self._icon:
                _user32.DestroyIcon(self._icon)
                self._icon = 0
            self.hwnd = 0

    def _data(self) -> Any:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = ICON_ID
        data.uFlags = NIF_MESSAGE | NIF_TIP | (NIF_ICON if self._icon else 0)
        data.uCallbackMessage = CALLBACK
        data.hIcon = self._icon
        data.szTip = self.tip
        return data

    def _add(self) -> bool:
        if shell_notify(NIM_ADD, self._data()):
            self.counts["adds"] += 1
            return True
        self.counts["failed"] += 1
        return False

    def _delete(self) -> None:
        if self.added:
            shell_notify(NIM_DELETE, self._data())
            self.added = False

    def _message(self, message: int, wparam: int, lparam: int) -> int | None:
        """(the icon's thread) A message of its hidden window: what it returns, None for Windows' own handling."""
        if message == CALLBACK:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_RBUTTONUP):
                x, y = _cursor()
                self._clicks.append(("left" if event == WM_LBUTTONUP else "right", x, y, time.monotonic()))
                self.counts["clicks"] += 1
            return 0
        if self._taskbar_created and message == self._taskbar_created:
            self.added = self._add()  # (Explorer started again: its icons are gone)
            self.counts["readds"] += 1
            return 0
        if message == WM_CLOSE:
            self._delete()
            _user32.DestroyWindow(self.hwnd)
            return 0
        if message == WM_DESTROY:
            _user32.PostQuitMessage(0)
            return 0
        return None
