"""What stands in the way, with a button for what fixes it: the lines of the setup banner over the page each get one
button, which does what the line asks of the person where TASlation can do it for them (never a key or a click to the
viewer):

* the viewer (`viewer_trouble`, looked at by the event pump every `TROUBLE_LOOK_S`): several windows
  that look like a viewer equally well, or the viewer closed - Choose viewer opens the Viewer list
  (`choose_viewer`); the viewer's window minimised, or black - Show viewer (`show_viewer`: a minimised window shown
  again behind TASlation's, as choosing it does, `viewers.show_minimised`; else the viewer's window put in front of
  the others, not activated, so that the person can click the book and reload it).
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

from ..capture import lower_window, raise_window, window_exists, window_minimised
from ..i18n import _
from .constants import VIEWER_BLACK, VIEWER_CLOSED, VIEWER_RESTORED
from .progress import code_of, rendered
from .viewers import show_minimised

TROUBLE_LOOK_S = 0.5  # how often the event pump looks at the viewer for the banner's line
LINES_PER_PAGE = 8  # a manga page's lines, about: what the seconds a page come from
CPU_SECONDS_PER_LINE = 4.0  # PLaMo 3 Translate 2B on a laptop's processor, about
LOG_HEAD = 256 * 1024  # bytes of Ollama's server log read: the devices are written at its start

TIED, CLOSED, MINIMISED, BLACK = "tied", "closed", "minimised", "black"
CHOOSE, SHOW = "choose", "show"
TROUBLE_ACTIONS = {TIED: CHOOSE, CLOSED: CHOOSE, MINIMISED: SHOW, BLACK: SHOW}
DOWN_CODES = frozenset({"health.ollama_down", "health.ollama_no_answer"})
MODEL_CODES = frozenset({"translator.model_missing", "translator.other_model", "health.model_missing",
                         "health.other_model"})


def viewer_trouble(window: Any) -> str | None:
    """What keeps TASlation from reading the viewer: `TIED`, `CLOSED`, `MINIMISED` or `BLACK`; None when
    nothing does (or no viewer is chosen yet and none was closed: the page says how to choose one)."""
    win = getattr(window, "selected", None)
    if win is None:
        if getattr(window, "_tied_said", ()):
            return TIED
        return CLOSED if getattr(window, "_viewer_closed", None) is not None else None
    if window_minimised(win.hwnd):
        return MINIMISED
    watch = getattr(window, "_black_watch", None)
    if watch is not None and getattr(watch, "told", False):
        return BLACK
    return None


def trouble_line(kind: str) -> str:
    """The banner's line for *kind*, in the window's language."""
    if kind == TIED:
        return _("Several windows look like a viewer: choose the right one in Menu > Viewer...")
    if kind == CLOSED:
        return _(VIEWER_CLOSED)
    if kind == MINIMISED:
        return _("The viewer's window is minimised, so TASlation cannot see the page.")
    return _(VIEWER_BLACK)


def action_button(window: Any, action: str) -> tuple[str, Callable[[], None]]:
    """The button for *action* (`CHOOSE`, `SHOW`), in the window's language."""
    if action == CHOOSE:
        return _("Choose viewer"), lambda: choose_viewer(window)
    return _("Show viewer"), lambda: show_viewer(window)


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
    """Choose viewer: the Viewer list opens (as a click on it), rescanned (its postcommand); in see-through mode,
    where the window is never on the screen, the viewer chooser (`see_menu.ViewerDialog`)."""
    if getattr(window, "_see_hidden", False):
        from . import see_menu, seethrough

        seethrough.asked(window)
        see_menu.open_viewer(window)
        return
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


def cpu_page_seconds() -> int:
    """About how many seconds a page takes on the processor: `LINES_PER_PAGE` lines at `CPU_SECONDS_PER_LINE`."""
    return max(1, int(round(LINES_PER_PAGE * CPU_SECONDS_PER_LINE)))


def cpu_line(seconds: int) -> str:
    """The banner's notice that the translator runs on the processor, in the window's language."""
    return _("The translator runs on the processor (no graphics card is used for it), so a page takes about {seconds} s to translate.").format(seconds=seconds)
