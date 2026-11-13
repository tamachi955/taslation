"""Hover tooltips (`tip`, `Tooltip`): a line on what a control does, shown after about half a second over it, beside
the control and never on it (a tip under the pointer would take the pointer off the control: flicker), kept on the
monitor's work area (`tip_place`, no Tk). The text is broken by hand at about 320 pixels (`wrap.wrap_text`), so a
Japanese or Thai line wraps too; the colours are the system's for tooltips, else those of the ttk theme's labels. A
control that is greyed out still shows its tip (its pointer events come as ever): with *disabled*, the line that says
why it is greyed out, asked at the moment the tip shows, so the code that greys it out need not know."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any

from . import layout
from .wrap import wrap_text

TIP_DELAY_MS = 500
TIP_WRAP_PX = 320
TIP_GAP = 4  # pixels between the control and its tip
TIP_POINTER_GAP = 20  # below the pointer, for a control with no room above or below it

Box = tuple[int, int, int, int]


def tip_place(size: tuple[int, int], box: Box, pointer: tuple[int, int], work: Box) -> tuple[int, int]:
    """Where a tip of *size* goes for a control at *box* (left, top, right, bottom on the screen) with the pointer at
    *pointer*, on the work area *work*: under the control from the pointer's x, moved left to stay on the area; above
    the control when there is no room under it; below the pointer when there is room neither way (a control as tall
    as the monitor). All of it stays on the area, and it covers the control only in that last case."""
    width, height = size
    left, top, right, bottom = work
    x = max(left, min(pointer[0], right - width))
    if box[3] + TIP_GAP + height <= bottom:
        return x, box[3] + TIP_GAP
    if box[1] - TIP_GAP - height >= top:
        return x, box[1] - TIP_GAP - height
    return x, max(top, min(pointer[1] + TIP_POINTER_GAP, bottom - height))


def tip_colours(widget: tk.Misc) -> tuple[str, str]:
    """The tip's background and text colours: the system's tooltip colours where Tk knows them, else the theme's."""
    try:
        widget.winfo_rgb("SystemInfoBackground")
        widget.winfo_rgb("SystemInfoText")
        return "SystemInfoBackground", "SystemInfoText"
    except tk.TclError:
        style = ttk.Style(widget)
        return str(style.lookup("TLabel", "background") or "#ffffe0"), str(style.lookup("TLabel", "foreground") or "#000000")


class Tooltip:
    """The tip of *widget*: *delay_ms* after the pointer entered it, *text* in a borderless window of its own;
    gone when the pointer leaves, on a press of a button or a key, and with the widget. ``tip`` is that window
    while it shows. A language switch builds the widgets anew, each with its text in the new language. *disabled* is
    what it says instead while the ttk widget is disabled (empty: *text* then too)."""

    def __init__(self, widget: tk.Misc, text: str, delay_ms: int = TIP_DELAY_MS, disabled: str = ""):
        self.widget, self.text, self.delay_ms, self.disabled = widget, text, delay_ms, disabled
        self.tip: tk.Toplevel | None = None
        self._job: str | None = None
        for sequence, handler in (("<Enter>", self._enter), ("<Leave>", self._leave), ("<ButtonPress>", self._leave),
                                  ("<KeyPress>", self._leave), ("<Unmap>", self._leave), ("<Destroy>", self._leave)):
            widget.bind(sequence, handler, add="+")

    def _enter(self, _event: object = None) -> None:
        self._cancel()
        if self.tip is None and self.current():
            self._job = self.widget.after(self.delay_ms, self._due)

    def _leave(self, _event: object = None) -> None:
        self._cancel()
        self.hide()

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _due(self) -> None:
        self._job = None
        if self._there():
            self.show()

    def _there(self) -> bool:
        """Whether the control is on the screen (it may have gone meanwhile: a toolbar hidden by reading mode)."""
        try:
            return bool(self.widget.winfo_viewable())
        except tk.TclError:
            return False

    def current(self) -> str:
        """What the tip says now: why the control is greyed out while it is, else what it does."""
        try:
            if self.disabled and self.widget.instate(["disabled"]):  # type: ignore[attr-defined]
                return self.disabled
        except (AttributeError, tk.TclError):  # not a ttk widget, or it is going
            pass
        return self.text

    def lines(self) -> str:
        """The text broken into lines at about `TIP_WRAP_PX` pixels."""
        measure = tkfont.nametofont("TkDefaultFont").measure
        return "\n".join(line.rstrip(" ") for part in wrap_text(self.current(), TIP_WRAP_PX, measure) for line in part)

    def show(self) -> None:
        """The tip, placed while still withdrawn so that it never shows first somewhere else."""
        if self.tip is not None:
            return
        widget = self.widget
        try:
            tip = tk.Toplevel(widget.winfo_toplevel())
            tip.withdraw()
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)  # the window may be always on top, or full screen
            back, fore = tip_colours(widget)
            tk.Label(tip, text=self.lines(), justify="left", font="TkDefaultFont", background=back, foreground=fore,
                     borderwidth=1, relief="solid", padx=6, pady=3).pack()
            tip.update_idletasks()
            pointer = widget.winfo_pointerxy()
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            place = tip_place((tip.winfo_reqwidth(), tip.winfo_reqheight()),
                              (x, y, x + widget.winfo_width(), y + widget.winfo_height()), pointer,
                              layout.work_area(widget, *pointer))
            tip.geometry(f"+{place[0]}+{place[1]}")
            self.tip = tip
            self._reveal(tip)
        except tk.TclError:  # the window is going
            self.hide()

    @staticmethod
    def _reveal(tip: tk.Toplevel) -> None:
        tip.deiconify()

    def hide(self) -> None:
        tip, self.tip = self.tip, None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass


def tip(text: str, *widgets: tk.Misc, disabled: str = "") -> None:
    """*text* as the tooltip of each of *widgets* (a control and the label that names it); *disabled*, what it says
    while the control is greyed out."""
    for widget in widgets:
        widget._tooltip = Tooltip(widget, text, disabled=disabled)  # type: ignore[attr-defined]


def tip_menu(window: tk.Misc, menu: tk.Menu, *tips: str) -> None:
    """*tips*, in the order of *menu*'s entries (separators left out), said in *window*'s status line (`status_var`)
    while the pointer is on the entry: a menu has no tooltips. To be called before the menu goes on the window: Tk gives
    the menus of a menu bar clones, which get the bindings their menu has by then."""
    entries = [i for i in range(int(menu.index("end")) + 1) if menu.type(i) != "separator"]
    by_entry = dict(zip(entries, tips))
    menu.bind("<<MenuSelect>>", lambda e: menu_tip(window, str(e.widget), by_entry))


def menu_tip(window: Any, path: str, tips: dict[int, str]) -> None:
    """The status line follows the menu at *path* (a clone has no Tkinter object): the tip of the entry under the
    pointer. What the line said comes back when the pointer leaves the entries, unless a job has said something else
    meanwhile."""
    call = window.tk.call

    def back(line: str, saved: str) -> None:
        window._menu_line = ("", "")
        if window.status_var.get() == line:
            window.status_var.set(saved)

    try:
        active = str(call(path, "index", "active"))
    except tk.TclError:
        return
    on = int(active) if active.isdigit() else None
    line, saved = getattr(window, "_menu_line", ("", ""))
    text = tips.get(on, "")
    if text:
        saved = saved if line else window.status_var.get()
        window._menu_line = (text, saved)
        window.status_var.set(text)
    elif line:
        back(line, saved)
