"""TASlation's window over a full-screen viewer as Windows' on-screen keyboard is over the program it types into: it
stays above in the order of the windows and never takes the foreground (Windows only).

* The window gets WS_EX_NOACTIVATE and is made topmost with SWP_NOACTIVATE (`set_over`): a click on it does not make
  it the foreground window ("Extended Window Styles", learn.microsoft.com), so the viewer keeps the foreground and
  the reader's keys go to it as they would with nothing in between. Measured with Tk 8.6.15 over a throwaway Chrome
  156 in full screen (2026-11-03): real clicks on a ttk button and on a canvas whose binding calls ``focus`` left the
  browser in front, and it went on drawing at about 60 frames a second (the window stays below alpha 255:
  `ui.constants.WINDOW_ALPHA`); so did a click on the menu bar, over the browser in a window. No window-procedure
  subclass was needed for WM_MOUSEACTIVATE (Tk's ``focus`` without -force only notes the focus while the program is
  not in front). Tk's ``-topmost`` keeps the style and the handle; Tk's ``-fullscreen`` makes the window anew without
  the style and activates it, so the style goes on again after it (`has_over`) and the foreground is handed back.
* TASlation's own keys while the viewer has the foreground are hot keys (`HotKeys`: ``RegisterHotKey`` on a
  message-only window of the thread that runs Tk, whose event loop hands it WM_HOTKEY). A hot key is the system's for
  as long as it is registered, whoever is in front: the caller registers only the keys it needs and only while it
  needs them. The window procedure only takes notes (as `windows.WindowEvents` does): calling into Tk from it would
  break Python.

Nothing here presses a key or moves the foreground."""

from __future__ import annotations

import ctypes
import sys
import time

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
OVER_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE  # the order of the windows changes, nothing else, never activated
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000  # a key held down gives one hot key, not one per repeat
HWND_MESSAGE = -3
ERROR_CLASS_ALREADY_EXISTS = 1410
HOTKEY_CLASS = "TASlationHotKeys"
MAX_NOTES = 64  # hot keys kept until they are taken

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM


def over_style(ex_style: int, on: bool) -> int:
    """The extended style *ex_style* with WS_EX_NOACTIVATE put on (*on*) or taken off; nothing else changes (Tk's
    WS_EX_LAYERED for the alpha stays, and so does WS_EX_TOPMOST, which only `SetWindowPos` changes)."""
    return (ex_style | WS_EX_NOACTIVATE) if on else (ex_style & ~WS_EX_NOACTIVATE)


def over_order(on: bool, topmost: bool) -> int:
    """Where `set_over` puts the window in the order of the windows: topmost while it is over the viewer, else where
    the reader's Always on top (or reading mode) has it."""
    return HWND_TOPMOST if on or topmost else HWND_NOTOPMOST


def has_over(hwnd: int) -> bool:
    """Whether the window *hwnd* has WS_EX_NOACTIVATE now (Tk may have made its window anew without it)."""
    if not IS_WINDOWS or not hwnd or not user32.IsWindow(hwnd):
        return False
    return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_NOACTIVATE)


def set_over(hwnd: int, on: bool, topmost: bool = False) -> bool:
    """The top-level window *hwnd* over the viewer (*on*: WS_EX_NOACTIVATE, topmost) or back to a normal window
    (topmost when *topmost*), with SWP_NOACTIVATE: neither change activates it (a SetWindowPos without that flag
    would). Returns whether Windows took both."""
    if not IS_WINDOWS or not hwnd or not user32.IsWindow(hwnd):
        return False
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    wanted = over_style(style, on)
    if wanted != style:
        ctypes.set_last_error(0)
        if not user32.SetWindowLongW(hwnd, GWL_EXSTYLE, wanted) and ctypes.get_last_error():
            return False
    return bool(user32.SetWindowPos(hwnd, over_order(on, topmost), 0, 0, 0, 0, OVER_FLAGS))


_notes: dict[int, list[tuple[int, float]]] = {}  # message-only window -> the hot keys that came, (id, when)


def _hotkey_proc(hwnd, message, wparam, lparam):  # type: ignore[no-untyped-def]
    if message == WM_HOTKEY:
        notes = _notes.get(int(hwnd or 0))
        if notes is not None and len(notes) < MAX_NOTES:
            notes.append((int(wparam), time.monotonic()))
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


_PROC = WNDPROC(_hotkey_proc) if IS_WINDOWS else None  # kept for the life of the process: the class points at it
_class_ready = False


def _register_class() -> bool:
    global _class_ready
    if _class_ready:
        return True
    wc = WNDCLASSW()
    wc.lpfnWndProc = _PROC
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = HOTKEY_CLASS
    if not user32.RegisterClassW(ctypes.byref(wc)) and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
        return False
    _class_ready = True
    return True


class HotKeys:
    """Keys of TASlation's that work while another window has the foreground: each one registered by name with
    `register` (a key with no modifier, MOD_NOREPEAT), taken back with `unregister` or `clear`, and what was pressed
    handed over by `take`. Made, used and closed on the thread that runs Tk's event loop (the hot keys are that
    thread's, and its loop gives the message-only window its WM_HOTKEY). `start` gives None where there is none to
    be had."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self._ids: dict[str, int] = {}  # name -> hot-key id, while registered
        self._names: dict[int, str] = {}
        self._next = 1
        _notes[hwnd] = []

    @classmethod
    def start(cls) -> "HotKeys | None":
        if not IS_WINDOWS or not _register_class():
            return None
        hwnd = user32.CreateWindowExW(0, HOTKEY_CLASS, "TASlation", 0, 0, 0, 0, 0, HWND_MESSAGE, None,
                                      kernel32.GetModuleHandleW(None), None)
        return cls(int(hwnd)) if hwnd else None

    @property
    def registered(self) -> frozenset[str]:
        return frozenset(self._ids)

    def register(self, name: str, vk: int) -> bool:
        """The key *name* (virtual-key code *vk*) TASlation's from now on; False when another program has it (it is
        then left to that program)."""
        if name in self._ids:
            return True
        hot = self._next
        self._next += 1
        if not user32.RegisterHotKey(self.hwnd, hot, MOD_NOREPEAT, vk):
            return False
        self._ids[name] = hot
        self._names[hot] = name
        return True

    def unregister(self, name: str) -> None:
        hot = self._ids.pop(name, None)
        if hot is not None:
            user32.UnregisterHotKey(self.hwnd, hot)
            self._names.pop(hot, None)

    def clear(self) -> None:
        for name in list(self._ids):
            self.unregister(name)

    def take(self) -> list[str]:
        """The names of the hot keys pressed since the last call, oldest first (a key no longer registered is
        dropped)."""
        notes = _notes.get(self.hwnd)
        if not notes:
            return []
        taken = [self._names[hot] for hot, _when in notes if hot in self._names]
        notes.clear()
        return taken

    def close(self) -> None:
        self.clear()
        _notes.pop(self.hwnd, None)
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = 0
