"""The progress of a whole-book translation on TASlation's taskbar button (Windows' ITaskbarList3, through ctypes:
no package, no file). `TaskbarProgress.show` takes how far the run is and in what state: a green bar while it
translates, a yellow one while the run waits for the reader, none otherwise. Nothing here ever raises: a Windows
without the interface, a window without a taskbar button (a hidden test window), any COM failure leave the button
as it is, and the window works the same."""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any, Callable

log = logging.getLogger(__name__)

CLSID_TASKBAR_LIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_TASKBAR_LIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 2
# ITaskbarList3's methods by their place in its table: IUnknown (0-2), ITaskbarList (3-7), ITaskbarList2 (8), then
# its own
HR_INIT, SET_PROGRESS_VALUE, SET_PROGRESS_STATE = 3, 9, 10
# TBPFLAG
NO_PROGRESS, INDETERMINATE, NORMAL, ERROR, PAUSED = 0, 1, 2, 4, 8
STEPS = 1000  # the bar's resolution


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort),
                ("data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _Guid:
    guid = _Guid()
    if ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(guid)) != 0:  # type: ignore[attr-defined]
        raise OSError(f"CLSIDFromString {text}")
    return guid


class _TaskbarList:
    """ITaskbarList3, made once (on the window's thread: COM objects belong to the thread that made them)."""

    def __init__(self) -> None:
        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)  # S_FALSE or RPC_E_CHANGED_MODE: COM is there already
        self._ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(_guid(CLSID_TASKBAR_LIST)), None, CLSCTX_INPROC_SERVER,
                                    ctypes.byref(_guid(IID_TASKBAR_LIST3)), ctypes.byref(self._ptr))
        if hr != 0 or not self._ptr.value:
            raise OSError(f"CoCreateInstance(TaskbarList) {hr & 0xFFFFFFFF:#x}")
        table = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        hresult = ctypes.c_long

        def method(index: int, *args: Any) -> Callable[..., int]:
            return ctypes.WINFUNCTYPE(hresult, ctypes.c_void_p, *args)(table[index])  # type: ignore[attr-defined]

        self._init = method(HR_INIT)
        self._value = method(SET_PROGRESS_VALUE, ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_ulonglong)
        self._state = method(SET_PROGRESS_STATE, ctypes.c_void_p, ctypes.c_int)
        hr = self._init(self._ptr)
        if hr != 0:
            raise OSError(f"ITaskbarList3.HrInit {hr & 0xFFFFFFFF:#x}")

    def set(self, hwnd: int, state: int, fraction: float) -> None:
        self._state(self._ptr, ctypes.c_void_p(hwnd), state)
        if state in (NORMAL, PAUSED, ERROR):
            self._value(self._ptr, ctypes.c_void_p(hwnd), int(round(max(0.0, min(1.0, fraction)) * STEPS)), STEPS)


class TaskbarProgress:
    """The bar on a window's taskbar button. *hwnd*: the window's top-level handle, asked when the bar is first
    shown (`int(window.wm_frame(), 16)` for Tk); *factory* makes the COM object (by default ITaskbarList3; tests give
    their own). Shows only what changed."""

    def __init__(self, hwnd: Callable[[], int], factory: Callable[[], Any] | None = None):
        self._hwnd = hwnd
        self._factory = factory if factory is not None else (_TaskbarList if sys.platform == "win32" else None)
        self._list: Any = None
        self._failed = self._factory is None
        self._shown: tuple[int, int] = (NO_PROGRESS, -1)

    @property
    def available(self) -> bool:
        """Whether the bar can be shown (False after a failure: it is not tried again)."""
        return not self._failed

    def show(self, state: int, fraction: float = 0.0) -> None:
        """*state* (`NORMAL`, `PAUSED`, `NO_PROGRESS`, ...) at *fraction* (0 to 1) on the button."""
        if self._failed:
            return
        step = int(round(max(0.0, min(1.0, float(fraction))) * STEPS)) if state != NO_PROGRESS else -1
        if (state, step) == self._shown:
            return
        if state == NO_PROGRESS and self._list is None:
            return  # nothing was ever shown: nothing to take away
        try:
            if self._list is None:
                self._list = self._factory()
            self._list.set(int(self._hwnd()), state, float(fraction))
            self._shown = (state, step)
        except Exception as e:  # noqa: BLE001 - the button stays as it is; the window works the same
            log.info("taskbar progress unavailable: %s", type(e).__name__)
            self._failed = True

    def clear(self) -> None:
        """No bar on the button."""
        self.show(NO_PROGRESS)
