"""The person told when a long run ends while they are elsewhere: a whole-book run that finishes, or stops with a
problem, while TASlation is not the foreground window flashes TASlation's taskbar button (Windows' FlashWindowEx,
through ctypes: the button flashes and stays lit until the window is brought forward - no focus is taken, no window
is raised) and, when the reader chose it, plays the system's default sound (`winsound.MessageBeep`).

Both are settings: ``flash_when_done`` (on by default) and ``sound_when_done`` (off by default). A run the reader
stopped (Stop, Esc) says nothing more: the reader is there. Nothing here ever raises; elsewhere than on Windows nothing
is done."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from typing import Any

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
# FLASHWINFO's dwFlags: the taskbar button flashes, and stays lit until the window comes to the foreground
FLASHW_TRAY = 0x2
FLASHW_TIMERNOFG = 0xC
FLASH_COUNT = 5  # flashes before the button stays lit
# The endings the reader asked for: nothing to tell
STOPPED_BY_READER = frozenset({"batch.stopped", "batch.stopped_reading", "batch.stopped_translating"})


class _FlashInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_ulong),
                ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_ulong)]


def worth_telling(summary: Any) -> bool:
    """Whether a run's ending is worth telling a reader who is elsewhere: it finished (`batch.finished`, whatever its
    reason: the end of the book, the page limit, a disk that cannot be written), or it stopped with a problem (every
    request failed, no page of the book seen); not a run the reader stopped."""
    code = str(getattr(summary, "code", "") or "")
    return bool(code) and code not in STOPPED_BY_READER


def in_front(hwnd: int | None = None) -> bool:
    """Whether a window of TASlation's (the main one or one of its dialogs) is the foreground window. True elsewhere
    than on Windows and whenever it cannot be told (nothing is then done)."""
    if not IS_WINDOWS:
        return True
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        front = user32.GetForegroundWindow()
        if not front:
            return False  # (the desktop locked, a switch in progress: nobody looks at TASlation)
        if hwnd and int(front) == int(hwnd):
            return True
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(ctypes.c_void_p(front), ctypes.byref(pid))
        return pid.value == os.getpid()
    except Exception as e:  # noqa: BLE001 - nothing to tell then
        log.debug("foreground window not known: %s", e)
        return True


def flash(hwnd: int) -> bool:
    """TASlation's taskbar button flashed FLASH_COUNT times, then lit until the window is brought forward (no focus
    taken). Returns whether Windows took the request."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        info = _FlashInfo(ctypes.sizeof(_FlashInfo), ctypes.c_void_p(int(hwnd)), FLASHW_TRAY | FLASHW_TIMERNOFG,
                          FLASH_COUNT, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))  # type: ignore[attr-defined]
        return True  # (its return value is whether the window was lit before, not success)
    except Exception as e:  # noqa: BLE001 - the button stays as it is
        log.debug("FlashWindowEx failed: %s", e)
        return False


def beep() -> bool:
    """The system's default sound (Windows' sound scheme decides which, and the reader's volume how loud); returns
    whether it was asked for."""
    if not IS_WINDOWS:
        return False
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
        return True
    except Exception as e:  # noqa: BLE001 - no sound device: silence
        log.debug("MessageBeep failed: %s", e)
        return False


def tell_run_ended(window: Any, summary: Any) -> tuple[str, ...]:
    """A run has ended with *summary*: when it is worth telling (`worth_telling`) and no window of TASlation's is in
    front, the taskbar button flashes (``flash_when_done``) and the sound plays (``sound_when_done``). Returns what
    was done ("flash", "sound"), for the tests."""
    if not worth_telling(summary):
        return ()
    settings = getattr(window, "settings", None)
    flashes = bool(getattr(settings, "flash_when_done", True))
    sounds = bool(getattr(settings, "sound_when_done", False))
    if not flashes and not sounds:
        return ()
    own = getattr(window, "_own_hwnd", None)
    try:
        hwnd = int(own()) if own is not None else 0
    except Exception:  # noqa: BLE001 - a window going away: nothing to flash
        hwnd = 0
    if in_front(hwnd):
        return ()
    done: list[str] = []
    if flashes and flash(hwnd):
        done.append("flash")
    if sounds and beep():
        done.append("sound")
    return tuple(done)
