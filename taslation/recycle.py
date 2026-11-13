"""Files moved to the Windows Recycle Bin instead of deleted, so that a delete the reader regrets can be undone there
(Explorer's Recycle Bin > Restore). The shell's own file operation (`SHFileOperationW` with FOF_ALLOWUNDO) through
ctypes: no package, nothing over the network. Nothing is ever deleted for good from here: a drive without a Recycle
Bin, or a file the bin will not take, leaves the files where they are and says so (OSError)."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Iterable

FO_DELETE = 0x0003
FOF_SILENT = 0x0004  # no progress window
FOF_NOCONFIRMATION = 0x0010  # no "Are you sure?" of the shell's own: TASlation has asked already
FOF_ALLOWUNDO = 0x0040  # to the Recycle Bin
FOF_NOERRORUI = 0x0400  # an error is returned, not shown
FOF_WANTNUKEWARNING = 0x4000  # a file that would be deleted for good asks first, despite FOF_NOCONFIRMATION
FLAGS = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING


class NoRecycleBin(OSError):
    """The files could not go to the Recycle Bin (none on their drive, none on this system, or the shell refused):
    they stay where they are."""


def available() -> bool:
    """Whether this system has a Recycle Bin to move files to (Windows)."""
    return sys.platform == "win32"


def _has_bin(path: Path) -> bool:
    """Whether the drive of *path* has a Recycle Bin (`SHQueryRecycleBinW` answers for it; a network share does not)."""

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]

    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(info)
    root = os.path.splitdrive(str(path))[0] + "\\"
    return ctypes.windll.shell32.SHQueryRecycleBinW(ctypes.c_wchar_p(root), ctypes.byref(info)) == 0


def to_recycle_bin(paths: Iterable[Path]) -> list[Path]:
    """Move the files *paths* to the Recycle Bin in one operation (one entry to restore in Explorer); those that do not
    exist are passed by. Returns the files moved. NoRecycleBin when there is no Recycle Bin for them (nothing is moved)
    or the shell did not move them all (those it did not move stay in their place; none is deleted for good)."""
    files = [Path(os.path.abspath(p)) for p in paths if Path(p).exists()]
    if not files:
        return []
    if not available():
        raise NoRecycleBin("there is no Recycle Bin on this system")
    if not all(_has_bin(p) for p in files):
        raise NoRecycleBin("the drive of these files has no Recycle Bin")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _pack_ = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8  # shellapi.h packs it on 32-bit Windows only
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]

    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = "\0".join(str(p) for p in files) + "\0\0"  # a list ended by two nulls
    op.fFlags = FLAGS
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    left = [p for p in files if p.exists()]
    if code != 0 or op.fAnyOperationsAborted or left:
        raise NoRecycleBin(f"the Recycle Bin did not take {len(left) or len(files)} file(s) (code {code:#x})")
    return files


__all__ = ["FLAGS", "NoRecycleBin", "available", "to_recycle_bin"]
