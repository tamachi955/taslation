"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the guard and the helpers that tools/intro_video.py,
tools/promo_video.py and tools/standin_e2e.py share - never part of a release.

This file recorded a whole-book run, the README's recording until November 15, 2026. TASlation has no whole-book run
any more, and the recording went with it: run, the file says so and ends (exit code 2). What stays, imported by the
others:

* the guard (`Guard`, `GUARDED`, `replace_everywhere`): the only windows the app may act on are the stand-in viewer and
  this process's own; every function of ``capture.windows`` that captures, moves, raises, enlarges, focuses or sends a
  key or a click to a window is checked against them (a key or a click: the stand-in alone; a copy of the screen
  never), and a refused call raises (`Refused`);
* the sample pages (`page_files`, `screens_of`): one title of the OpenMantra dataset ("Towards Fully Automated Manga
  Translation", Ryota Hinami, Shonosuke Ishiwatari, Kazuhiko Yasuda, Yusuke Matsui, AAAI 2021; published by Mantra
  Inc.; Creative Commons Attribution-NonCommercial 4.0, not TASlation's licence), read from
  ``~/.taslation/datasets/openmantra`` where `tools/fetch_openmantra.py` put it, a page or two to a screen (the first
  on the right); the stand-in's title and ground (`VIEWER_TITLE`, `GROUND`);
* a state folder of the run's own (`scratch_state`), the window closed as its own Close does (`finish_app`), a child
  process ended (`_process_alive`, `_end_process`), every widget under one (`walk`)."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

from PIL import Image

DATASET = Path.home() / ".taslation" / "datasets" / "openmantra"  # read only: its pages
VIEWER_TITLE = "Sample Viewer - OpenMantra sample"
GROUND = "#2b2b2b"  # the stand-in's ground round the pages (as tools/fake_viewer.py)


# ---------------------------------------------------------------------------------------------------- the pages
def page_files(title: str, first: int, pages: int) -> list[Path]:
    """The dataset's *pages* page files of *title* from page *first* (the dataset's page_index, 1-based)."""
    folder = DATASET / "images" / title / "ja"
    files = [folder / f"{n - 1:03d}.jpg" for n in range(first, first + pages)]
    missing = [f.name for f in files if not f.is_file()]
    if missing:
        raise SystemExit(f"not in the dataset ({folder}): {', '.join(missing)}; tools/fetch_openmantra.py fetches it")
    return files


def screens_of(files: list[Path], single: bool) -> list[Image.Image]:
    """What the stand-in shows screen by screen: each page alone, or two pages side by side, the first on the right."""
    pages = [Image.open(f).convert("RGB") for f in files]
    if single:
        return pages
    out = []
    for i in range(0, len(pages), 2):
        pair = pages[i:i + 2]
        if len(pair) == 1:
            out.append(pair[0])
            continue
        right, left = pair
        both = Image.new("RGB", (right.width + left.width, max(right.height, left.height)), (255, 255, 255))
        both.paste(left, (0, 0))
        both.paste(right, (left.width, 0))
        out.append(both)
    return out


def _process_alive(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32")
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def _end_process(pid: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32")
    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if handle:
        kernel32.TerminateProcess(handle, 1)
        kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------------------------------- the guard
class Refused(RuntimeError):
    """A call the demo does not allow: the window it was for is not the stand-in nor one of this process's own."""


class Guard:
    """The only windows the app may act on: the stand-in (*viewer*) and this process's own. Every refused call is noted
    (`refused`) and raises; `used` counts what reached the stand-in."""

    def __init__(self, viewer: int):
        self.viewer = viewer
        self.own_pid = os.getpid()
        self.refused: list[str] = []
        self.used: dict[str, int] = {}
        self.chosen: set[int] = set()
        self.user32 = ctypes.WinDLL("user32")
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    def _root(self, hwnd: int) -> int:
        return int(self.user32.GetAncestor(hwnd, 2) or 0) or int(hwnd)  # GA_ROOT

    def is_viewer(self, hwnd: Any) -> bool:
        try:
            return bool(hwnd) and self._root(int(hwnd)) == self.viewer
        except (TypeError, ValueError, OSError):
            return False

    def is_own(self, hwnd: Any) -> bool:
        try:
            pid = wintypes.DWORD(0)
            self.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
            return bool(hwnd) and pid.value == self.own_pid
        except (TypeError, ValueError, OSError):
            return False

    def refuse(self, name: str) -> None:
        self.refused.append(name)
        raise Refused(f"the demo does not allow {name} here")

    def wrap(self, name: str, original: Callable[..., Any], allow: str,
             target: Callable[..., Any]) -> Callable[..., Any]:
        """*original* behind a check of its window, *target*(args, kwargs): "viewer" (the stand-in alone), "ours" (the
        stand-in or this process's own) or "never"."""

        def guarded(*args: Any, **kwargs: Any) -> Any:
            hwnd = None if allow == "never" else target(args, kwargs)
            ok = allow != "never" and (self.is_viewer(hwnd) or (allow == "ours" and self.is_own(hwnd)))
            if not ok:
                self.refuse(name)
            if self.is_viewer(hwnd):
                self.used[name] = self.used.get(name, 0) + 1
            return original(*args, **kwargs)

        guarded.__wrapped__ = original  # type: ignore[attr-defined]
        return guarded


def first_arg(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return args[0] if args else kwargs.get("hwnd")


def hwnd_of_first(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    held = args[0] if args else next(iter(kwargs.values()), None)
    return getattr(held, "hwnd", None)


# name -> (who it may act on, where its window is): every function of `capture.windows` that captures, moves, raises,
# enlarges, focuses or sends a key or a click to a window
GUARDED = {
    "capture_window": ("ours", first_arg), "enlarge_window": ("ours", first_arg), "move_window": ("ours", first_arg),
    "unminimise_window": ("ours", first_arg), "raise_window": ("ours", first_arg), "ask_repaint": ("ours", first_arg),
    "give_foreground": ("ours", first_arg),
    "restore_window": ("ours", hwnd_of_first), "lower_window": ("ours", hwnd_of_first),
    "press_key": ("viewer", first_arg), "press_briefly": ("viewer", first_arg), "post_key": ("viewer", first_arg),
    "post_click": ("viewer", first_arg),
    "capture_screen_rect": ("never", first_arg),
}


def taslation_modules() -> list[Any]:
    return [m for name, m in list(sys.modules.items()) if m is not None and (name == "taslation" or
                                                                             name.startswith("taslation."))]


def replace_everywhere(original: Any, replacement: Any) -> int:
    """*original* replaced by *replacement* in every module of TASlation that holds it (imported by name or its own)."""
    n = 0
    for module in taslation_modules():
        for attr, value in list(vars(module).items()):
            if value is original:
                setattr(module, attr, replacement)
                n += 1
    return n


# ---------------------------------------------------------------------------------------------------- the window
def walk(widget: Any) -> list[Any]:
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(walk(child))
    return out


def scratch_state() -> Path:
    """A state folder of its own for the run (TASLATION_STATE_DIR): the legal notice dismissed, TASlation in
    English."""
    from taslation import notice
    from taslation.i18n import save_ui_language

    state = Path(os.environ["TASLATION_STATE_DIR"])
    notice.save_country(state, "JP")
    notice.dismiss(state, "en")
    save_ui_language(state, "en")
    return state


def finish_app(app: Any) -> None:
    """The window closed as its own Close does, with nothing asked (what is translated saved, the viewer's window put
    back, the translator's model let go); torn down if that fails."""
    try:
        app._on_close()
    except Exception:  # noqa: BLE001 - the window goes all the same
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    """The recording this file made, of a whole-book run: gone with that run. It says so and ends (exit code 2)."""
    sys.stderr.write("tools/demo_video.py recorded a whole-book run, which TASlation no longer has: there is nothing to "
                     "record. tools/intro_video.py records the README's video; this file keeps only the guard and the "
                     "helpers the other tools import.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
