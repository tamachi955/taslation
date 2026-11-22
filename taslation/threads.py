"""The window's threads with Windows: a worker thread's lower priority (`lower_priority`: the pipeline's models
warmed and its reading beside the page on show, so that the viewer and the window keep up with the reader), and the PC
and the display kept awake while the window is open (`keep_awake`, `release_awake`). Elsewhere than on Windows none of
it does anything."""

from __future__ import annotations

import ctypes
import sys


def thread_priority() -> int | None:
    """The calling thread's Windows priority (0 normal, -1 below normal; None elsewhere or when it cannot be read)."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.GetThreadPriority.argtypes = [ctypes.c_void_p]
        value = int(kernel32.GetThreadPriority(kernel32.GetCurrentThread()))
    except Exception:  # noqa: BLE001 - nothing depends on it
        return None
    return None if value == 0x7FFFFFFF else value  # THREAD_PRIORITY_ERROR_RETURN


def set_priority(priority: int) -> bool:
    """Set the calling thread's Windows priority (THREAD_PRIORITY_*: -1 below normal, 0 normal); False elsewhere."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        return bool(kernel32.SetThreadPriority(kernel32.GetCurrentThread(), int(priority)))
    except Exception:  # noqa: BLE001
        return False


BELOW_NORMAL = -1  # THREAD_PRIORITY_BELOW_NORMAL


def lower_priority() -> int | None:
    """The calling thread at BELOW_NORMAL priority (a worker beside the page on show); what it had before."""
    before = thread_priority()
    set_priority(BELOW_NORMAL)
    return before


def keep_awake(display: bool) -> None:
    """Keep the PC from sleeping (Windows), and with *display* the display too: the window asks for both while it is
    open, since a viewer stops repainting once the display is off (`release_awake` lets go of both)."""
    if sys.platform != "win32":
        return
    try:
        es_continuous, es_system, es_display = 0x80000000, 0x00000001, 0x00000002
        flags = es_continuous | es_system | (es_display if display else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def release_awake() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass
