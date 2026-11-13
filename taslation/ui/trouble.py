"""What stands in the way, with a button for what fixes it: the lines of the setup banner over the page and the
waiting lines of a whole-book run's band each get one button, which does what the line asks of the person where
TASlation can do it for them (never a key or a click to the viewer):

* the viewer (outside a run, `viewer_trouble`, looked at by the event pump every `TROUBLE_LOOK_S`): several windows
  that look like a viewer equally well, or the viewer closed - Choose viewer opens the Viewer list
  (`choose_viewer`); the viewer's window minimised, or black - Show viewer (`show_viewer`: a minimised window shown
  again behind TASlation's, as choosing it does, `viewers.show_minimised`; else the viewer's window put in front of
  the others, not activated, so that the person can click the book and reload it); the viewer covered by TASlation -
  Move TASlation aside (`move_aside`: un-maximised, then narrowed so that a strip of the viewer shows,
  `aside_rect`). A run's band has the same buttons for the same waits (`WAITING_ACTIONS`).
* the setup (`health.check`'s Messages): Ollama not running - Start translator again (the window's
  `restart_translator`); the translation model the language needs not installed - Download model
  (`ModelSwitchMixin.download_model`), with the window's own words for the line instead of "run install.cmd"
  (`setup_line`).
* the translator on the processor: one line at the start with about how long a page takes (`ollama_compute` reads
  the inference devices the running Ollama server wrote at its start in its log; `CPU_LINE`)."""

from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path
from typing import Any, Callable

from ..capture import (IS_WINDOWS, lower_window, move_window, raise_window, window_exists, window_minimised,
                       window_rect, work_area)
from ..i18n import _
from .constants import VIEWER_BLACK, VIEWER_CLOSED, VIEWER_RESTORED, in_a_run
from .progress import code_of, rendered
from .viewers import show_minimised

TROUBLE_LOOK_S = 0.5  # how often the event pump looks at the viewer for the banner's line
ASIDE_STRIP = 160  # px of the viewer left in view when TASlation is moved aside
ASIDE_MIN_WIDTH = 640  # px: TASlation's window is not made narrower than this
LINES_PER_PAGE = 8  # a manga page's lines, about: what the seconds a page come from
CPU_SECONDS_PER_LINE = 4.0  # PLaMo 3 Translate 2B on a laptop's processor, about, before a run measured its own
LOG_HEAD = 256 * 1024  # bytes of Ollama's server log read: the devices are written at its start

TIED, CLOSED, MINIMISED, COVERED, BLACK = "tied", "closed", "minimised", "covered", "black"
CHOOSE, SHOW, ASIDE = "choose", "show", "aside"
TROUBLE_ACTIONS = {TIED: CHOOSE, CLOSED: CHOOSE, MINIMISED: SHOW, BLACK: SHOW, COVERED: ASIDE}
# a run's waits with a button (`batch.BatchProgress.waiting`)
WAITING_ACTIONS = {"batch.waiting_covered": ASIDE, "batch.waiting_viewer_hidden": SHOW, "batch.viewer_black": SHOW,
                   "batch.waiting_behind": SHOW}
DOWN_CODES = frozenset({"health.ollama_down", "health.ollama_no_answer"})
MODEL_CODES = frozenset({"translator.model_missing", "translator.other_model", "health.model_missing",
                         "health.other_model"})


def viewer_trouble(window: Any) -> str | None:
    """What keeps the window from reading the viewer, outside a run (a run's band says its own): `TIED`, `CLOSED`,
    `MINIMISED`, `COVERED` or `BLACK`; None when nothing does (or no viewer is chosen yet and none was closed: the
    page says how to choose one)."""
    if in_a_run(window):
        return None
    win = getattr(window, "selected", None)
    if win is None:
        if getattr(window, "_tied_said", ()):
            return TIED
        return CLOSED if getattr(window, "_viewer_closed", None) is not None else None
    if window_minimised(win.hwnd):
        return MINIMISED
    if getattr(window, "_covered", False):
        return COVERED
    watch = getattr(window, "_black_watch", None)
    if watch is not None and getattr(watch, "told", False):
        return BLACK
    return None


def trouble_line(kind: str) -> str:
    """The banner's line for *kind*, in the window's language."""
    if kind == TIED:
        return _("Several windows look like a viewer: pick the right one in the Viewer list.")
    if kind == CLOSED:
        return _(VIEWER_CLOSED)
    if kind == MINIMISED:
        return _("The viewer's window is minimised, so TASlation cannot see the page.")
    if kind == COVERED:
        return _("The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or move it so that a strip of the viewer stays visible.")
    return _(VIEWER_BLACK)


def action_button(window: Any, action: str) -> tuple[str, Callable[[], None]]:
    """The button for *action* (`CHOOSE`, `SHOW`, `ASIDE`), in the window's language."""
    if action == CHOOSE:
        return _("Choose viewer"), lambda: choose_viewer(window)
    if action == SHOW:
        return _("Show viewer"), lambda: show_viewer(window)
    return _("Move TASlation aside"), lambda: move_aside(window)


def setup_line(message: Any) -> str:
    """A setup check's line on the banner: the Message in the window's language, but for a missing translation model,
    which the window downloads itself (Download model), not install.cmd."""
    code, params = code_of(message), dict(getattr(message, "params", {}) or {})
    if code == "translator.model_missing":
        return _("The translation model for this language, {name}, is not installed. Press Download model to install it.").format(name=params.get("name", ""))
    if code == "translator.other_model":
        return _("The translation model for this language, {name}, is not installed; translating with {used} for now. Press Download model to install it.").format(
            name=params.get("name", ""), used=params.get("used", ""))
    if code == "health.model_missing":
        return _("The translation model {model} is not installed. Press Download model to install it.").format(model=params.get("model", ""))
    if code == "health.other_model":
        return _("{wanted} is not installed; translating with {used} for now. Press Download model to install it.").format(
            wanted=params.get("wanted", ""), used=params.get("used", ""))
    return rendered(message)


def setup_button(window: Any, message: Any) -> tuple[str, Callable[[], None]] | None:
    """The button of a setup check's line: Start translator again, Download model, or none."""
    code = code_of(message)
    if code in DOWN_CODES:
        return _("Start translator again"), window.restart_translator
    if code in MODEL_CODES:
        return _("Download model"), window.download_model
    return None


# ------------------------------------------------------------------ what the buttons do
def choose_viewer(window: Any) -> None:
    """Choose viewer: the Viewer list opens (as a click on it), rescanned (its postcommand)."""
    box = getattr(window, "window_box", None)
    if box is None:
        return
    try:
        box.focus_set()
        window.tk.call("ttk::combobox::Post", box)
    except Exception:  # noqa: BLE001 - (a list that cannot open: the person clicks it)
        pass


def show_viewer(window: Any) -> None:
    """Show viewer: a minimised viewer window shown again behind TASlation's (`viewers.show_minimised`); a viewer
    window that is there put in front of the other windows, not activated and no key pressed (`front`), so that the
    person can click the book (and reload it, when it stays black)."""
    win = getattr(window, "selected", None)
    if win is None or not window_exists(win.hwnd):
        return
    if window_minimised(win.hwnd):
        if show_minimised(window, win):
            window.status(lambda: _(VIEWER_RESTORED).format(title=win.title))
        return
    front(win.hwnd)


def front(hwnd: int) -> bool:
    """The window *hwnd* on top of the ordinary windows, not activated: made topmost for a moment (it comes to the top
    and redraws) and then an ordinary window again, where it stays (`capture.raise_window`, then `lower_window` with
    no window to go back under)."""
    raised = raise_window(hwnd)
    if raised is None:
        return False
    lower_window(dataclasses.replace(raised, above=0))
    return True


def aside_rect(own: tuple[int, int, int, int], viewer: tuple[int, int, int, int], area: tuple[int, int, int, int],
               strip: int = ASIDE_STRIP, least: int = ASIDE_MIN_WIDTH) -> tuple[int, int, int, int] | None:
    """Where TASlation's window (*own*, screen rect) goes so that *strip* px of the viewer's window (*viewer*) show
    beside it on the monitor's work area (*area*): narrowed from the side where more of TASlation stays, at least
    *least* px wide; else moved to the right edge of the area at that width. None when the viewer already shows."""
    show_left = max(viewer[0], area[0])
    show_right = min(viewer[2], area[2])
    if show_right <= show_left:
        return None
    if own[0] > show_left or own[2] < show_right or own[1] > max(viewer[1], area[1]) or own[3] < min(viewer[3], area[3]):
        return None  # a part of the viewer shows already
    top, bottom = max(own[1], area[1]), min(own[3], area[3])
    from_left = (show_left + strip, top, min(own[2], area[2]), bottom)  # the strip on the viewer's left
    from_right = (max(own[0], area[0]), top, show_right - strip, bottom)  # ... or on its right
    best = max((from_left, from_right), key=lambda r: r[2] - r[0])
    if best[2] - best[0] >= least:
        return best
    width = max(least, min(area[2] - area[0] - strip, own[2] - own[0]))
    return (area[2] - width, top, area[2], bottom)


def move_aside(window: Any) -> None:
    """Move TASlation aside: its window un-maximised and narrowed (`aside_rect`) so that a strip of the viewer shows
    and the viewer draws again (it stops when TASlation covers it completely). Nothing for a viewer that shows."""
    win = getattr(window, "selected", None)
    if win is None:
        return
    try:
        if window.state() == "zoomed":
            window.state("normal")
            window.update_idletasks()
        own_hwnd = window._own_hwnd() if hasattr(window, "_own_hwnd") else None
        if not IS_WINDOWS or not own_hwnd:
            return
        area = work_area(own_hwnd)
        rect = aside_rect(window_rect(own_hwnd), window_rect(win.hwnd), area) if area is not None else None
        if rect is not None:
            move_window(own_hwnd, rect)
    except Exception:  # noqa: BLE001 - (a window that went meanwhile: nothing moved)
        return


# ------------------------------------------------------------------ the translator on the processor
def ollama_log() -> Path | None:
    """The log of the running Ollama server (``%LOCALAPPDATA%\\Ollama\\server.log``, the one Ollama's own app writes),
    None outside Windows or when there is none."""
    base = os.environ.get("LOCALAPPDATA", "")
    path = Path(base) / "Ollama" / "server.log" if base else None
    return path if path is not None and path.is_file() else None


_COMPUTE = re.compile(r'msg="inference compute".*?\blibrary=(\w+)')


def ollama_compute(log: Path | None = None) -> str:
    """Where the Ollama server translates, from the devices its log names at its start (only the first `LOG_HEAD`
    bytes are read; no book text is ever in it): "gpu" (a CUDA, ROCm, Vulkan or Metal device), "cpu" (no GPU, or
    only the processor), "" when that cannot be told."""
    path = log if log is not None else ollama_log()
    if path is None:
        return ""
    try:
        with open(path, "rb") as f:
            head = f.read(LOG_HEAD).decode("utf-8", "replace")
    except OSError:
        return ""
    libraries = [m.group(1).lower() for line in head.splitlines() for m in [_COMPUTE.search(line)] if m]
    if any(lib != "cpu" for lib in libraries):
        return "gpu"
    if libraries or "no compatible GPUs" in head:
        return "cpu"
    return ""


def cpu_page_seconds(pace: float | None) -> int:
    """About how many seconds a page takes on the processor: `LINES_PER_PAGE` lines at the last run's rate with the
    model (*pace*, lines a second) or at `CPU_SECONDS_PER_LINE`."""
    per_line = 1.0 / pace if pace else CPU_SECONDS_PER_LINE
    return max(1, int(round(LINES_PER_PAGE * per_line)))


def cpu_line(seconds: int) -> str:
    """The banner's notice that the translator runs on the processor, in the window's language."""
    return _("The translator runs on the processor (no graphics card is used for it), so a page takes about {seconds} s to translate.").format(seconds=seconds)
