"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: a plain window of a process of its own over the stand-in viewer's
window, for `standin_e2e.py --start-behind`.

    python tools/standin_cover.py --over HWND [--part F] [--rect X,Y,W,H] [--front] [--tool-pid PID]

What another program's window over the viewer is - in a process of its own, so that TASlation (which runs in the
e2e tool's process) sees another program in front, never one of its own (`capture.foreground_owner` tells its own by
the process). A grey window with a caption, laid directly above the stand-in's window (COVER_MARGIN beyond it on
every side; *--part F*: its left F alone; *--rect*: that place instead - a window maximised on the stand-in's monitor:
its work area), shown with no activation; with *--front* it takes the foreground as it shows - only while the
stand-in has it -, as a program the reader brought to the front over the viewer does, and lets the tool's process
(*--tool-pid*) take it in turn (``AllowSetForegroundWindow``: a person's click on TASlation's dialog then).

It prints "ready HWND FRONT" (FRONT 1 when it took the foreground) and then reads its standard input, a word a
line: "raise" - the stand-in put over it and given the foreground, as a person's click on the viewer does (the cover
stays, under it); "front" - the cover given the foreground, only while the stand-in has it (this thread shares its
input with the stand-in's for that moment), as a person's click on another program does: the keys go there; "end"
(or the input closed) - the foreground given back to the stand-in when the cover holds it, and the cover closed.
Each answered with a line of what was done. Nothing is pressed or clicked; only the stand-in's window and its own
are touched. ctypes and the standard library only: nothing of TASlation's is imported."""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
from ctypes import wintypes

COVER_CLASS = "StandinToolCoverOwn"
COVER_MARGIN = 24  # the cover's reach beyond the stand-in's window on every side
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0004, 0x0010, 0x0040
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
WM_CLOSE, WM_DESTROY, WM_APP = 0x0010, 0x0002, 0x8000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32")
gdi32 = ctypes.WinDLL("gdi32")
PROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
gdi32.GetStockObject.restype = wintypes.HGDIOBJ


class WndClass(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", PROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


def front() -> int:
    return int(user32.GetForegroundWindow() or 0)


def place(standin: int, part: float, rect: tuple[int, int, int, int] | None) -> tuple[int, int, int, int]:
    """The cover's place (x, y, w, h): over the stand-in's window and COVER_MARGIN beyond it, its left *part* alone,
    or *rect*."""
    if rect is not None:
        return rect
    r = wintypes.RECT()
    user32.GetWindowRect(standin, ctypes.byref(r))
    x, y = r.left - COVER_MARGIN, r.top - COVER_MARGIN
    w, h = r.right - r.left + 2 * COVER_MARGIN, r.bottom - r.top + 2 * COVER_MARGIN
    if part < 1.0:
        w = COVER_MARGIN + max(1, int((r.right - r.left) * part))
    return x, y, w, h


def raise_standin(standin: int) -> dict[str, int]:
    """The stand-in at the top of the ordinary windows (topmost for a moment, then ordinary again: no activation by
    that) and, when this process holds the foreground, given it - what a person's click on the viewer does."""
    stay = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    user32.SetWindowPos(standin, HWND_TOPMOST, 0, 0, 0, 0, stay)
    user32.SetWindowPos(standin, HWND_NOTOPMOST, 0, 0, 0, 0, stay)
    given = 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(wintypes.HWND(front()), ctypes.byref(pid))
    if front() and pid.value == kernel32.GetCurrentProcessId():
        given = int(bool(user32.SetForegroundWindow(standin)))
    return {"raised": 1, "given": given}


def take_front(standin: int, hwnd: int) -> dict[str, int]:
    """The cover given the foreground - only while the stand-in has it: its thread's input shared with the stand-in's
    for the moment of the hand-over (no key, no click) -, as a person's click on another program gives it that."""
    if front() != standin:
        return {"took": 0, "standin_had_it": 0}
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(wintypes.HWND(standin), None)
    attached = bool(other) and other != me and bool(user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return {"took": int(front() == hwnd), "standin_had_it": 1}


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        raise SystemExit("Windows only")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--over", type=int, required=True, help="the stand-in's window handle")
    ap.add_argument("--part", type=float, default=1.0)
    ap.add_argument("--rect", default="", help="X,Y,W,H")
    ap.add_argument("--front", action="store_true")
    ap.add_argument("--tool-pid", type=int, default=0)
    args = ap.parse_args(argv)
    standin = int(args.over)
    rect = tuple(int(v) for v in args.rect.split(",")) if args.rect else None
    x, y, w, h = place(standin, args.part, rect)  # type: ignore[arg-type]

    def proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        if msg == WM_APP:  # ("raise", from the reading thread: done on the window's own thread)
            done.update(raise_standin(standin))
            answered.set()
            return 0
        if msg == WM_APP + 1:  # ("front", as "raise")
            done.update(take_front(standin, int(hwnd)))
            answered.set()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    done: dict[str, int] = {}
    answered = threading.Event()
    callback = PROC(proc)
    instance = kernel32.GetModuleHandleW(None)
    wc = WndClass(0, callback, 0, 0, instance, None, None, gdi32.GetStockObject(2), None, COVER_CLASS)  # GRAY_BRUSH
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
    user32.RegisterClassW(ctypes.byref(wc))
    style = 0x00C00000 | 0x00080000  # WS_CAPTION | WS_SYSMENU: a window as any program's
    hwnd = int(user32.CreateWindowExW(0, COVER_CLASS, "stand-in cover", style, x, y, w, h, None, None, instance, None)
               or 0)
    took = 0
    if hwnd:
        above = user32.GetWindow(standin, 3)  # GW_HWNDPREV: the window just above the stand-in, if any
        after = above if above and int(above) != hwnd else wintypes.HWND(0)  # (else HWND_TOP)
        user32.SetWindowPos(hwnd, after, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        # (moved by a pixel too: a window shown with no activation and not moved is not seen by Chromium's occlusion
        # tracking until some other window event)
        user32.SetWindowPos(hwnd, None, x + 1, y, w, h, SWP_NOACTIVATE | SWP_NOZORDER)
        if args.front and front() == standin:
            took = int(bool(user32.SetForegroundWindow(hwnd)))
        if args.tool_pid:
            user32.AllowSetForegroundWindow(int(args.tool_pid))
    print(f"ready {hwnd} {took}", flush=True)

    def read() -> None:
        for line in sys.stdin:
            word = line.strip()
            if word == "raise":
                answered.clear()
                user32.PostMessageW(hwnd, WM_APP, 0, 0)
                answered.wait(3.0)
                print("raised " + " ".join(f"{k}={v}" for k, v in sorted(done.items())), flush=True)
            elif word == "front":
                answered.clear()
                done.clear()
                user32.PostMessageW(hwnd, WM_APP + 1, 0, 0)
                answered.wait(3.0)
                print("fronted " + " ".join(f"{k}={v}" for k, v in sorted(done.items())), flush=True)
            elif word == "end":
                break
        gave = 0
        if hwnd and front() == hwnd:
            gave = int(bool(user32.SetForegroundWindow(standin)))
        print(f"ended {gave}", flush=True)
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    threading.Thread(target=read, name="cover-input", daemon=True).start()
    msg = wintypes.MSG()
    while hwnd and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
