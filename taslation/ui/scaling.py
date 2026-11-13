"""The size of the window's text: Tk's scaling made from the DPI of the monitor the window is on, times the reader's
UI scale (`Settings.ui_scale`), set at the start (`apply_scale`) and again when the window moves to a monitor of
another DPI (`DpiWatch`).

TASlation runs per-monitor DPI aware (`capture.enable_dpi_awareness`), so Windows does not stretch the window's
pixels: when the window goes from a monitor at 150 % to one at 100 %, it is the window's own business to draw its text
smaller. Tk 8.6 sets its scaling once, from the system's DPI, and never again; so the DPI of the window's monitor is
looked at whenever the window has moved (`<Configure>`, once the moves stop: `CHECK_MS`), and on a change Tk's scaling
is set again and every named font is told, which makes Tk measure it anew in the new scaling (a font sized in points
follows; one sized in pixels, a negative size, keeps its pixels). What is laid out in pixels (a canvas, a fixed
width) keeps its pixels.
"""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from ..config import MAX_UI_SCALE, MIN_UI_SCALE

UI_SCALES = (0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0)  # the Settings dialog's choices (any value in the bounds loads)
BASE_DPI_VAR = "::taslation_base_dpi"  # the Tcl variable that keeps the DPI Tk measured at its start
CHECK_MS = 250  # a move's Configure events come in bursts: the monitor is looked at once they have stopped this long
POINTS_PER_INCH = 72.0  # Tk's scaling is pixels per point


def clamp_scale(value: float) -> float:
    """*value* within the bounds of `Settings.ui_scale` (1.0 for what is no number)."""
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return 1.0
    if scale != scale:  # NaN
        return 1.0
    return max(MIN_UI_SCALE, min(MAX_UI_SCALE, scale))


def window_dpi(widget: tk.Misc) -> int | None:
    """The DPI of the monitor *widget*'s window is on (Windows 10 1607 and later: ``GetDpiForWindow``), None where it
    cannot be told (another system, a window not on the screen yet)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        hwnd = int(widget.winfo_toplevel().wm_frame(), 16)
        if not hwnd:
            return None
        dpi = int(ctypes.windll.user32.GetDpiForWindow(ctypes.c_void_p(hwnd)))
    except (AttributeError, OSError, ValueError, tk.TclError):
        return None
    return dpi if dpi > 0 else None


def base_dpi(root: tk.Misc) -> float:
    """The DPI Tk measured at its start, before any scale of TASlation's: kept on the interpreter the first time it is
    asked for, since Tk's own measure of an inch follows the scaling set since."""
    try:
        kept = root.tk.call("set", BASE_DPI_VAR)
        return float(kept)
    except (tk.TclError, ValueError):
        dpi = float(root.winfo_fpixels("1i"))
        root.tk.call("set", BASE_DPI_VAR, dpi)
        return dpi


def refresh_fonts(root: tk.Misc) -> int:
    """Every named font told its size again, so that Tk measures it in the scaling in force (the widgets that use it
    are laid out anew). How many."""
    count = 0
    for name in tkfont.names(root):
        try:
            font = tkfont.nametofont(name, root)
            font.configure(size=font.cget("size"))
            count += 1
        except tk.TclError:  # (a font deleted meanwhile)
            continue
    return count


def apply_scale(root: tk.Misc, ui_scale: float = 1.0, dpi: float | None = None) -> float:
    """Tk's scaling set to *dpi* (that of the window's monitor, else the one Tk measured at its start) times
    *ui_scale*, and the named fonts told (`refresh_fonts`). The scaling set, in pixels per point."""
    measured = float(dpi or window_dpi(root) or base_dpi(root))
    base_dpi(root)  # (kept before the scaling changes what Tk calls an inch)
    scaling = measured / POINTS_PER_INCH * clamp_scale(ui_scale)
    try:
        current = float(root.tk.call("tk", "scaling"))
    except (tk.TclError, ValueError):
        current = 0.0
    if abs(current - scaling) > 1e-6:
        root.tk.call("tk", "scaling", scaling)
        refresh_fonts(root)
    return scaling


class DpiWatch:
    """Looks at the DPI of *root*'s monitor once the window has stopped moving (`<Configure>`, then `CHECK_MS`) and,
    on a change, scales Tk again with the UI scale *ui_scale* gives (`apply_scale`), then calls *on_change* (the DPI)
    for what the window lays out itself. ``dpi``: the DPI the window was last scaled for."""

    def __init__(self, root: tk.Misc, ui_scale: Callable[[], float], on_change: Callable[[int], None] | None = None):
        self.root = root
        self.ui_scale = ui_scale
        self.on_change = on_change
        self.dpi: int | None = window_dpi(root)
        self._job: str | None = None
        root.bind("<Configure>", self._moved, add="+")

    def _moved(self, event: tk.Event) -> None:
        if event.widget is not self.root:  # (a child laid out: no move of the window)
            return
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except tk.TclError:
                pass
        try:
            self._job = self.root.after(CHECK_MS, self.check)
        except tk.TclError:  # the window is going
            self._job = None

    def check(self) -> bool:
        """The monitor's DPI looked at now; whether it changed (and Tk was scaled for it)."""
        self._job = None
        dpi = window_dpi(self.root)
        if dpi is None or dpi == self.dpi:
            return False
        self.dpi = dpi
        apply_scale(self.root, self.ui_scale(), dpi)
        if self.on_change is not None:
            self.on_change(dpi)
        return True

    def rescale(self) -> float:
        """The UI scale changed (Settings): Tk scaled again for the monitor the window is on now."""
        self.dpi = window_dpi(self.root) or self.dpi
        return apply_scale(self.root, self.ui_scale(), self.dpi)
