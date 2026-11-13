"""A translated bubble enlarged while reading: in reading mode and in the Reader role, the pointer resting on a
translated bubble shows a popup beside it with the translation at a readable size and the original lettering of the
bubble, cropped from the frame in memory (never written anywhere).

* When: after `ZOOM_DELAY_MS` on a bubble that is hard to read where it is (`hard_to_read`: flagged "small" or
  "long", or lettered on the screen under `Settings.readable_font_size`), after `ZOOM_REST_MS` on any other one, so
  that a pointer passing over the page opens nothing. Not in the Translator role's normal window, where the pointer
  selects and edits the regions; not with `Settings.bubble_zoom` off.
* Size: the translation at twice the readable size and never smaller than it is lettered on the screen
  (`zoom_text_px`); the crop as large as the page shows it or larger, beside the text (above it for a wide bubble).
* Where: beside the bubble, never over it (so never under the pointer: no flicker), within the page area when it fits
  there, else within the monitor's work area (`zoom_place`).
* Gone: when the pointer leaves the bubble or the page, on a click (which goes on to the viewer as ever), the wheel,
  a page key, Esc (taken by the popup only while it shows), and as soon as the page on show is no longer the one it
  belongs to (`_zoom_watch`, every `ZOOM_WATCH_MS` while it shows).
* Focus: the popup is a borderless window, as a tooltip is (Tk shows such a window without activating it, measured:
  the active window and the focus stay where they were), with WS_EX_NOACTIVATE on it besides (`capture.overlay
  .set_over`), so over the full-screen viewer the viewer keeps the foreground and the keys; and it takes no click,
  since it never lies under the pointer. Hover and not a click opens it: a click on the page is the viewer's
  (`TranslatorMixin._forward_click`), and taking one for the popup would change what a click does."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Any

from PIL import Image, ImageTk

from ..capture import IS_WINDOWS
from ..capture.overlay import set_over
from ..render.lettering import strip_marks
from . import layout
from .wrap import wrap_text

ZOOM_DELAY_MS = 450  # the pointer on a bubble hard to read where it is: the popup after this
ZOOM_REST_MS = 1200  # ... on any other translated bubble: after this
ZOOM_WATCH_MS = 150  # while the popup shows, how often it looks whether its page and its bubble are still there
ZOOM_TEXT_TIMES = 2.0  # the popup's text: this many times the readable size ...
ZOOM_ON_SCREEN = 1.25  # ... and at least this many times the size the bubble is lettered at on the screen
ZOOM_TEXT_PX = (16, 44)  # ... within these (pixels)
READABLE_DEFAULT = 11  # the readable size when the setting is 0 (no flag "small")
ZOOM_CROP_TIMES = 1.5  # the original: this many times its size on the page (at least as on the screen) ...
ZOOM_CROP_SHARE = (0.4, 0.55)  # ... and at most this share of the monitor's work area (width, height)
ZOOM_TEXT_EMS = 16  # the text wraps at about this many times its size
ZOOM_GAP = 12  # pixels between the bubble and the popup
ZOOM_COLOURS = {"edge": "#5c5c5c", "ground": "#1d1d1d", "text": "#f2f2f2"}

Box = tuple[int, int, int, int]


def zoom_text_px(readable: int, shown_px: float) -> int:
    """The popup's text size in pixels: `ZOOM_TEXT_TIMES` the readable size (*readable*, or `READABLE_DEFAULT` when
    the setting is 0), and at least `ZOOM_ON_SCREEN` times *shown_px* - the size the bubble is lettered at on the
    screen -, within `ZOOM_TEXT_PX`."""
    base = readable if readable and readable > 0 else READABLE_DEFAULT
    px = max(ZOOM_TEXT_TIMES * base, ZOOM_ON_SCREEN * max(0.0, shown_px))
    return int(round(min(ZOOM_TEXT_PX[1], max(ZOOM_TEXT_PX[0], px))))


def hard_to_read(region: Any, scale: float, readable: int) -> bool:
    """Whether *region*'s translation is hard to read where it is: flagged "small" (set under the readable size) or
    "long" (far longer than the Japanese), or lettered on the screen - its size times the page's *scale* - under the
    readable size."""
    flags = set(getattr(region, "flags", ()) or ())
    if flags & {"small", "long"}:
        return True
    size = float(getattr(region, "font_size", 0) or 0)
    base = readable if readable and readable > 0 else READABLE_DEFAULT
    return 0 < size * scale < base


def crop_shown(size: tuple[int, int], scale: float, work: Box) -> tuple[int, int]:
    """The size the original crop of *size* (page pixels) is shown at: `ZOOM_CROP_TIMES` its size on the page and at
    least as large as on the screen (*scale*), at most `ZOOM_CROP_SHARE` of the work area *work*, never under 1 px."""
    w, h = max(1, size[0]), max(1, size[1])
    factor = max(scale, 1.0) * ZOOM_CROP_TIMES
    most_w = (work[2] - work[0]) * ZOOM_CROP_SHARE[0]
    most_h = (work[3] - work[1]) * ZOOM_CROP_SHARE[1]
    factor = min(factor, most_w / w, most_h / h)
    return max(1, int(round(w * factor))), max(1, int(round(h * factor)))


def _overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def zoom_place(size: tuple[int, int], bubble: Box, bounds: Box) -> tuple[int, int] | None:
    """Where a popup of *size* goes for the bubble at *bubble* (left, top, right, bottom on the screen), within
    *bounds*: to its right, else its left (the side a right-to-left page has read already first), else below, else
    above, `ZOOM_GAP` away and moved along that side to stay within *bounds*; None when no side has room for it
    without covering the bubble."""
    w, h = size
    left, top, right, bottom = bounds
    cx, cy = (bubble[0] + bubble[2]) // 2, (bubble[1] + bubble[3]) // 2
    y = max(top, min(cy - h // 2, bottom - h))
    x = max(left, min(cx - w // 2, right - w))
    for px, py in ((bubble[2] + ZOOM_GAP, y), (bubble[0] - ZOOM_GAP - w, y), (x, bubble[3] + ZOOM_GAP),
                   (x, bubble[1] - ZOOM_GAP - h)):
        box = (px, py, px + w, py + h)
        if left <= px and px + w <= right and top <= py and py + h <= bottom and not _overlaps(box, bubble):
            return px, py
    return None


def fallback_place(size: tuple[int, int], pointer: tuple[int, int], bounds: Box) -> tuple[int, int]:
    """Where a popup of *size* goes when no side of the bubble has room (`zoom_place`): the corner of *bounds* farthest
    from the *pointer*, so that it is not under the pointer."""
    w, h = size
    left, top, right, bottom = bounds
    x = left if pointer[0] > (left + right) // 2 else max(left, right - w)
    y = top if pointer[1] > (top + bottom) // 2 else max(top, bottom - h)
    return x, y


def reveal(popup: tk.Toplevel) -> None:
    """*popup* on the screen without taking the foreground: a borderless window, which Tk shows without activating
    it, then WS_EX_NOACTIVATE and topmost with SWP_NOACTIVATE (`capture.overlay.set_over`) on Windows."""
    popup.deiconify()
    if IS_WINDOWS:
        try:
            set_over(int(popup.wm_frame(), 16), True)
        except (tk.TclError, ValueError):
            pass


class BubbleZoomMixin:
    """The popup over a translated bubble. A part of `app.App` through `reading.ReadingMixin` (no `__init__`: its
    state starts on first use; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the page watched
    def _watch_bubbles(self) -> None:
        """The page watches the pointer and the keys for the popup (called as the page is made: `App._build_ui`): on a
        binding tag of its own, first among the page's, so that the page's other handlers stay as they are - a click
        still goes on to the viewer, a page key still turns the page - and Esc is the popup's only while it shows."""
        canvas = self.canvas
        tag = f"Zoom{canvas}"  # (a tag, not a window: it may not begin with a dot)
        if tag in canvas.bindtags():
            return
        canvas.bindtags((tag, *canvas.bindtags()))
        canvas.bind_class(tag, "<Motion>", self._zoom_motion)
        for sequence in ("<Leave>", "<ButtonPress>", "<MouseWheel>", "<KeyPress>"):
            canvas.bind_class(tag, sequence, lambda _e: self._zoom_hide())
        canvas.bind_class(tag, "<Escape>", self._zoom_escape)

    def _zoom_wanted(self) -> bool:
        """Whether a bubble may show enlarged now: the setting on, the page on show the one translated, and the pointer
        not the Translator's own (reading mode, or the Reader role)."""
        if not getattr(self.settings, "bubble_zoom", True) or self.last_result is None:
            return False
        if not self.reading and self.role_var.get() != "reader":
            return False
        return self._result_on_show()

    def _zoom_region_at(self, x: float, y: float) -> Any:
        """The translated bubble under the canvas point (x, y) - the smallest where they nest -, or None."""
        canvas = self.canvas
        if not canvas.inside(x, y):
            return None
        ix, iy = canvas.to_image_coords(int(x), int(y))
        hits = [r for r in self._page_regions()
                if r.status == "translated" and str(r.translated_text or "").strip()
                and r.x0 <= ix < r.x1 and r.y0 <= iy < r.y1]
        return min(hits, key=lambda r: r.area) if hits else None

    def _zoom_screen_box(self, region: Any) -> Box:
        """*region*'s box on the screen, as the page shows it now."""
        canvas = self.canvas
        x0, y0 = canvas.from_image_coords(region.x0, region.y0)
        x1, y1 = canvas.from_image_coords(region.x1, region.y1)
        rx, ry = canvas.winfo_rootx(), canvas.winfo_rooty()
        return rx + x0, ry + y0, rx + x1, ry + y1

    # ------------------------------------------------------------------ the pointer
    def _zoom_motion(self, event: tk.Event) -> None:
        """The pointer moved on the page: onto another bubble, the popup of the one before goes and this one's is due
        (`ZOOM_DELAY_MS` or `ZOOM_REST_MS`); off the bubbles it goes."""
        region = self._zoom_region_at(event.x, event.y) if self._zoom_wanted() else None
        if region is not None and region is getattr(self, "_zoom_target", None):
            return
        self._zoom_hide()
        if region is None:
            return
        readable = int(getattr(self.settings, "readable_font_size", 0) or 0)
        delay = ZOOM_DELAY_MS if hard_to_read(region, self.canvas.scale, readable) else ZOOM_REST_MS
        self._zoom_target = region
        self._zoom_job = self.after(delay, self._zoom_due)

    def _zoom_due(self) -> None:
        """The pointer rested on the bubble: its popup, if it is still there and the pointer on it."""
        self._zoom_job = None
        region = getattr(self, "_zoom_target", None)
        if region is None or not self._zoom_wanted() or not self._zoom_pointer_on(region):
            self._zoom_hide()
            return
        self._zoom_show(region)

    def _zoom_pointer_on(self, region: Any) -> bool:
        """Whether the pointer is on *region* as the page shows it now."""
        try:
            px, py = self.winfo_pointerxy()
        except tk.TclError:
            return False
        x0, y0, x1, y1 = self._zoom_screen_box(region)
        return x0 <= px < x1 and y0 <= py < y1

    def _zoom_escape(self, _event: tk.Event | None = None) -> str | None:
        """Esc on the page: the popup goes, and Esc does nothing else then; with no popup Esc is the window's as ever."""
        if getattr(self, "_zoom_popup", None) is None:
            return None
        self._zoom_hide()
        return "break"

    # ------------------------------------------------------------------ the popup
    def _zoom_show(self, region: Any) -> None:
        """The popup for *region*: the original cropped from the frame in memory, the translation at `zoom_text_px`,
        beside the bubble (`zoom_place`); then watched (`_zoom_watch`)."""
        result = self.last_result
        canvas = self.canvas
        bubble = self._zoom_screen_box(region)
        try:
            pointer = self.winfo_pointerxy()
        except tk.TclError:
            return
        work = layout.work_area(self, *pointer)
        readable = int(getattr(self.settings, "readable_font_size", 0) or 0)
        px = zoom_text_px(readable, float(region.font_size or 0) * canvas.scale)
        original = result.original.convert("RGB").crop(region.bbox)  # (memory only)
        shown = crop_shown(original.size, canvas.scale, work)
        if shown != original.size:
            original = original.resize(shown, Image.LANCZOS)
        family = tkfont.nametofont("TkDefaultFont").actual("family")
        font = tkfont.Font(family=family, size=-px)
        stacked = shown[0] > shown[1] * 1.3  # a wide bubble: the original above the text
        width = max(ZOOM_TEXT_EMS * px, shown[0] if stacked else 0)
        width = int(min(width, (work[2] - work[0]) * 0.45))
        text = strip_marks(str(region.translated_text))
        lines = "\n".join(line.rstrip(" ") for part in wrap_text(text, width, font.measure) for line in part)
        colours = ZOOM_COLOURS
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)  # above the reading window and a window always on top
        popup.configure(bg=colours["edge"], takefocus=0)
        inner = tk.Frame(popup, bg=colours["ground"], padx=10, pady=8)
        inner.pack(padx=1, pady=1)
        photo = ImageTk.PhotoImage(original, master=popup)
        picture = tk.Label(inner, image=photo, bg=colours["ground"], borderwidth=0)
        picture.image = photo  # (kept with the label)
        words = tk.Label(inner, text=lines, font=font, fg=colours["text"], bg=colours["ground"], justify="left")
        if stacked:
            picture.pack(side="top", anchor="w")
            words.pack(side="top", anchor="w", pady=(8, 0))
        else:
            picture.pack(side="left", anchor="n")
            words.pack(side="left", anchor="n", padx=(10, 0))
        popup.update_idletasks()
        size = (popup.winfo_reqwidth(), popup.winfo_reqheight())
        page = (canvas.winfo_rootx(), canvas.winfo_rooty(), canvas.winfo_rootx() + canvas.winfo_width(),
                canvas.winfo_rooty() + canvas.winfo_height())
        within = (max(page[0], work[0]), max(page[1], work[1]), min(page[2], work[2]), min(page[3], work[3]))
        place = zoom_place(size, bubble, within) or zoom_place(size, bubble, work) or fallback_place(size, pointer, work)
        popup.geometry(f"+{place[0]}+{place[1]}")
        self._zoom_popup, self._zoom_for = popup, (result, region)
        self._zoom_font = font
        reveal(popup)
        self._zoom_watch_job = self.after(ZOOM_WATCH_MS, self._zoom_watch)

    def _zoom_watch(self) -> None:
        """While the popup shows: it goes as soon as its page is no longer on show (a page turned in the viewer, or
        the page read again), its bubble is gone, the pointer is off the bubble, or it may not show any more."""
        self._zoom_watch_job = None
        shown = getattr(self, "_zoom_for", None)
        if getattr(self, "_zoom_popup", None) is None or shown is None:
            return
        result, region = shown
        if (self.last_result is not result or not any(r is region for r in result.regions)  # (`==` reaches masks)
                or not self._zoom_wanted() or not self._zoom_pointer_on(region)):
            self._zoom_hide()
            return
        self._zoom_watch_job = self.after(ZOOM_WATCH_MS, self._zoom_watch)

    def _zoom_hide(self) -> None:
        """The popup away, and the one that was due not shown."""
        for name in ("_zoom_job", "_zoom_watch_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except (tk.TclError, ValueError):
                    pass
                setattr(self, name, None)
        self._zoom_target = self._zoom_for = None
        popup, self._zoom_popup = getattr(self, "_zoom_popup", None), None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
