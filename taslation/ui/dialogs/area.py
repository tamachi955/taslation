"""The Set area dialog: the part of the viewer that shows the page, set over a fresh capture (the geometry is
`ui.area`'s)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from PIL import Image

from ...i18n import _
from .. import area
from ..layout import place_window
from ..preview import ImageCanvas
from ..tooltip import tip
from .help import explain_button

INNER_COLOUR = "#4fb3ff"  # the page panel found inside the area: what is read of it
INNER_DASH = (6, 4)


class AreaDialog(tk.Toplevel):
    """The part of the viewer that shows the page, over a fresh capture: the current area - the reader's, or the page
    panel found so far when there is none - as a rectangle with eight handles, the picture drawn clear of the
    canvas's edges so that handles on them show whole. A handle resizes it, a drag inside moves it, a drag elsewhere
    draws a new one. Enter (or OK) applies, Esc cancels, and Clear area (with
    *clear*) closes the dialog and leaves the reader no area of their own: the page is looked for again. *inner* gives the page panel found inside a rectangle (None: none, or the rectangle itself): it shows
    dashed inside the area, found again whenever the area has changed, so that the reader sees what is read. How to
    use the dialog is behind the "?"."""

    def __init__(self, master: tk.Misc, image: Image.Image,
                 callback: Callable[[tuple[int, int, int, int], tuple[int, int]], None],
                 margins: tuple[int, int, int, int] = (0, 0, 0, 0),
                 inner: Callable[[tuple[int, int, int, int]], tuple[int, int, int, int] | None] | None = None,
                 clear: Callable[[], None] | None = None):
        super().__init__(master)
        self.title(_("Set area - drag over the page, then press Enter"))
        self.image = image
        self.callback = callback
        self.box = area.margins_to_box(margins, image.size)
        self.inner = inner
        self.clear = clear
        self.inner_box: tuple[int, int, int, int] | None = None  # the page panel found inside the area, if any
        self._find_inner()
        self._grip: str | None = None
        self._start: tuple[float, float] | None = None
        self._start_box = self.box
        w = min(image.width + 2 * area.HANDLE, self.winfo_screenwidth() - 160)
        h = min(image.height + 2 * area.HANDLE, self.winfo_screenheight() - 260)
        self.geometry(f"{max(560, w)}x{max(440, h + 90)}")
        head = ttk.Frame(self, padding=(8, 4))
        head.pack(fill="x")
        explain_button(head, _("Drag the handles to resize the area, drag inside it to move it, or drag elsewhere to draw a new one. Keep only the page inside it: the browser's tabs and address bar would otherwise be read as part of the page. Enter = use it, Esc = cancel.")).pack(side="right")
        foot = ttk.Frame(self, padding=(8, 4))
        foot.pack(side="bottom", fill="x")  # packed before the canvas so that it always shows
        ttk.Button(foot, text=_("Cancel"), command=self.destroy).pack(side="right")
        ttk.Button(foot, text=_("OK"), command=self._accept).pack(side="right", padx=(0, 6))
        if clear is not None:
            button = ttk.Button(foot, text=_("Clear area"), command=self._clear)
            button.pack(side="right", padx=(0, 16))
            tip(_("Forget this area: TASlation looks for the page by itself again."), button)
        self.canvas = ImageCanvas(self, bg="#202020")
        self.canvas.inset = area.HANDLE  # the handles on the capture's edges show whole
        self.canvas.trim = False  # the whole capture: the area is set on it
        self.canvas.pack(fill="both", expand=True)
        self.canvas.on_redraw = self._draw
        self.canvas.set_image(image)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Motion>", self._hover)
        for keysym in ("Return", "KP_Enter"):
            self.bind(f"<{keysym}>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(master)
        place_window(self, master)
        self.grab_set()

    def margins(self) -> tuple[int, int, int, int]:
        return area.box_to_margins(self.box, self.image.size)

    def _find_inner(self) -> None:
        """The page panel inside the area as it is now (*inner*), shown dashed: what is read of the area."""
        try:
            self.inner_box = self.inner(self.box) if self.inner is not None else None
        except Exception:  # noqa: BLE001 - none shown: the area itself is read
            self.inner_box = None

    def _grip_at(self, x: float, y: float) -> str | None:
        c = self.canvas
        return area.grip_at(area.box_to_canvas(self.box, c.scale, c.offset), x, y)

    def _press(self, e: tk.Event) -> None:
        self._grip = self._grip_at(e.x, e.y)
        self._start = area.to_image(e.x, e.y, self.canvas.scale, self.canvas.offset)
        self._start_box = self.box

    def _drag(self, e: tk.Event) -> None:
        if self._start is None:
            return
        now = area.to_image(e.x, e.y, self.canvas.scale, self.canvas.offset)
        self.box = area.drag(self._start_box, self._grip, self._start, now, self.image.size, area.MIN_AREA)
        self._draw()

    def _release(self, e: tk.Event) -> None:
        if self._start is None:
            return
        self._drag(e)
        if self._grip is None and not area.big_enough(self.box, area.MIN_AREA):
            self.box = self._start_box  # a click beside the area, or too small a rectangle: the area stays
        self._start, self._grip = None, None
        if self.box != self._start_box:
            self._find_inner()
        self._draw()

    def _hover(self, e: tk.Event) -> None:
        cursor = area.CURSORS[self._grip_at(e.x, e.y)]
        if str(self.canvas.cget("cursor")) != cursor:
            try:
                self.canvas.configure(cursor=cursor)
            except tk.TclError:  # a cursor this system does not have
                pass

    def _draw(self) -> None:
        c = self.canvas
        c.delete("area")
        frame = area.box_to_canvas((0, 0, self.image.width, self.image.height), c.scale, c.offset)
        for part in area.outside(area.box_to_canvas(self.box, c.scale, c.offset), frame):  # what is left out
            try:
                c.create_rectangle(*part, fill="#000000", outline="", stipple="gray50", tags="area")
            except tk.TclError:  # no stipple patterns on this system: no shade
                break
        c.draw_frame(self.box, "area")
        if self.inner_box is not None and self._start is None:  # (not while the area is dragged: found again after)
            x0, y0, x1, y1 = area.box_to_canvas(self.inner_box, c.scale, c.offset)
            c.create_rectangle(x0, y0, x1, y1, outline=INNER_COLOUR, width=2, dash=INNER_DASH,
                               tags=("area", "area-inner"))

    def _clear(self) -> None:
        self.destroy()
        self.clear()

    def _accept(self) -> None:
        self.callback(self.box, self.image.size)
        self.destroy()
