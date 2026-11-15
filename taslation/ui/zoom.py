"""The panel beside a bubble while reading: in reading mode and in the Reader role, the pointer resting on a
translated bubble shows a panel beside it with what the page does not show (`Settings.hover_shows`, `hover`), when
that is how a bubble shows its other side (`Settings.hover_reveal` "panel", the default; "in_place" changes the
bubble itself instead: `in_place`):

* with the translation on the page (the default): the bubble's original lettering, cropped from the frame in memory
  (never written anywhere) and enlarged, beside its translation at a readable size;
* with the original on the page: the translation alone, at a readable size, in the faces of the bubble's kind
  (`faces`: a thought italic, a shout bold), so that the Japanese on the page and the translation beside it are seen
  together. While the page is being translated, the panel of a box whose translation has not come says so with a
  running bar (`FILL_WAIT`), one lettered already shows its translation, and once the page is done the panel of the
  bubble under the pointer opens at once.

* When: after `ZOOM_DELAY_MS` on a bubble that is hard to read where it is (`hard_to_read`: flagged "small" or
  "long", or lettered on the screen under `Settings.readable_font_size`) and on every bubble with the original on
  the page, after `ZOOM_REST_MS` on any other one, so that a pointer passing over the page opens nothing. Not in the
  Translator role's normal window, where the pointer selects and edits the regions; with the translation on the page,
  not with `Settings.bubble_zoom` off.
* Size: the translation at twice the readable size and never smaller than it is lettered on the screen
  (`zoom_text_px`); the crop as large as the page shows it or larger, beside the text (above it for a wide bubble).
  Under them, the key that pins the panel with the bubble's Japanese (`ZOOM_HINT`, when that action has one).
* Where: beside the bubble, never over it (so never under the pointer: no flicker), within the page area when it fits
  there, else within the monitor's work area (`zoom_place`). One bubble at a time: the pointer on another bubble
  takes the panel away, and that one's opens after the same rest.
* Gone: when the pointer leaves the bubble or the page, on a click (which goes on to the viewer as ever), the wheel,
  a page key, Esc (taken by the panel only while it shows), and as soon as the page on show is no longer the one it
  belongs to (`_zoom_watch`, every `ZOOM_WATCH_MS` while it shows).
* Pinned (`bubble_text`): the key of "show_japanese" opens the panel on the bubble under the pointer in either mode,
  either way of showing and whatever `bubble_zoom` says, with the bubble's Japanese as text to select and its Copy
  buttons; the pointer may
  then leave the bubble for it. It goes on a click on the page, the wheel, Esc, its Close button, the key again, and
  when its page is gone; no other panel opens while it is there. The keys of "next_bubble" and "previous_bubble" pin
  it on the next or the previous bubble without the pointer, and so does a press held still on a bubble
  (`HOLD_MS` within `STILL_PX`, for a touch screen, where there is no hover: `_hold_press`) or a right click on one
  (Windows makes a touch held still a right click while its "press and hold" is on). The release of such a press is
  TASlation's; a tap or a click goes on to the viewer exactly as ever.
* Pinned with the original on the page (`hover.reverse_on`): the reader reads the Japanese and looks at the
  translation only when asked (to test oneself, or to take the Japanese as text unspoilt), so the pinned panel opens
  with the Japanese alone and a "Show the translation" button where the translation goes (`SHOW_TRANSLATION`,
  `_zoom_unveil`: the button, or the key of "show_japanese" again, which closes the panel only then). Every panel
  pinned anew, on another bubble too, holds it back again. The panel that opens on a rest of the pointer shows the
  translation at once as ever; the key of "copy_translation" copies it either way.
* Focus: the panel is a borderless window, as a tooltip is (Tk shows such a window without activating it, measured:
  the active window and the focus stay where they were), with WS_EX_NOACTIVATE on it besides (`capture.overlay
  .set_over`), so over the full-screen viewer the viewer keeps the foreground and the keys; and it takes no click
  unless the pointer is taken to a pinned one, since it never lies under the pointer. Hover and not a click opens it:
  a click on the page is the viewer's (`TranslatorMixin._forward_click`), and taking one for the panel would change
  what a click does."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any

from PIL import Image, ImageTk

from ..annotations import DEFAULT_LETTERING, LetteringStyle
from ..capture import IS_WINDOWS
from ..capture.overlay import set_over
from ..i18n import _
from ..render.lettering import strip_marks
from . import layout, shortcuts
from .hover import hover_usable, reveal_wanted, reverse_on
from .strip import run_page_on_show
from .wrap import wrap_text

ZOOM_DELAY_MS = 450  # the pointer on a bubble hard to read where it is, or any with the original on the page: this
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
ZOOM_COLOURS = {"edge": "#5c5c5c", "ground": "#1d1d1d", "text": "#f2f2f2", "hint": "#b4b4b4"}
ZOOM_HINT = "{key}: its Japanese, to select and copy"  # the panel's last line, with the key of "show_japanese"
FILL_WAIT = "This bubble is being translated..."  # the panel of a box of the page filling in, before its translation
FILL_SHOWN = ("found", "read", "lettered")  # the states of such a box the panel opens on (not one without text)
HOLD_MS = 600  # a press on a bubble held this long ...
STILL_PX = 6  # ... moving no more than this (canvas pixels; as a click that is no drag) pins its panel
SHOW_TRANSLATION = "Show the translation"  # the button of a panel pinned with the original on the page

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


class FillBox:
    """A box of the page filling in while it is translated (`progress.Filling`), as a target of the panel: the
    filling and the box's index, with a region's coordinates. Two are the same box when they are of the same filling
    (by identity: a filling compares its pictures) and of the same index (`same_target`)."""

    __slots__ = ("fill", "index")

    def __init__(self, fill: Any, index: int):
        self.fill, self.index = fill, index

    @property
    def bbox(self) -> Box:
        return tuple(int(v) for v in self.fill.boxes[self.index])  # type: ignore[return-value]

    x0 = property(lambda self: self.bbox[0])
    y0 = property(lambda self: self.bbox[1])
    x1 = property(lambda self: self.bbox[2])
    y1 = property(lambda self: self.bbox[3])

    @property
    def state(self) -> str:
        return self.fill.states[self.index] if 0 <= self.index < len(self.fill.states) else ""

    @property
    def text(self) -> str:
        """Its translation once it is lettered, "" before."""
        return str(self.fill.texts.get(self.index, "")) if self.state == "lettered" else ""


def text_target(region: Any, untranslated: bool = False) -> bool:
    """Whether *region* is a bubble the panel opens on: translated with a translation; with *untranslated*, one read
    and left without a translation as well (its Japanese can be shown)."""
    status = getattr(region, "status", "")
    if status == "translated" and str(getattr(region, "translated_text", "") or "").strip():
        return True
    return untranslated and status == "untranslated"


def same_target(a: Any, b: Any) -> bool:
    """Whether two targets of the panel are the same bubble: the same region, or the same box of the same filling."""
    if isinstance(a, FillBox) and isinstance(b, FillBox):
        return a.fill is b.fill and a.index == b.index
    return a is b


def faces(region: Any, pipeline: Any) -> tuple[bool, bool]:
    """(bold, italic) of *region*'s translation in the panel that shows it alone: as its lettering is set - the
    region's own formatting, else the series sheet's for its kind (`Pipeline.kind_lettering`), else the default (a
    thought italic, a shout bold)."""
    style = getattr(region, "style", None)
    kind = str(getattr(region, "tag", "") or "")
    try:
        sheet = pipeline.kind_lettering(kind) if pipeline is not None else None
    except Exception:  # noqa: BLE001 - the panel shows all the same
        sheet = None
    if sheet is None:
        sheet = DEFAULT_LETTERING.get(kind) or LetteringStyle()
    bold = getattr(style, "bold", None)
    italic = getattr(style, "italic", None)
    return (bool(sheet.bold) if bold is None else bool(bold)), (bool(sheet.italic) if italic is None else bool(italic))


class BubbleZoomMixin:
    """The panel beside a bubble. A part of `app.App` through `reading.ReadingMixin` (no `__init__`: its state starts
    on first use; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the page watched
    def _watch_bubbles(self) -> None:
        """The page watches the pointer and the keys for the panel and for a bubble shown in its place (`in_place`;
        called as the page is made: `App._build_ui`): on a binding tag of its own, first among the page's, so that the
        page's other handlers stay as they are - a click still goes on to the viewer, a page key still turns the page
        - and Esc is theirs only while one shows. A press of the left button is watched for a hold (`_hold_press`;
        only the release of a hold is kept from the page), a right click on a bubble pins its panel (`_hold_right`)."""
        canvas = self.canvas
        tag = f"Zoom{canvas}"  # (a tag, not a window: it may not begin with a dot)
        if tag in canvas.bindtags():
            return
        canvas.bindtags((tag, *canvas.bindtags()))
        canvas.bind_class(tag, "<Motion>", self._bubbles_motion)
        for sequence in ("<Leave>", "<KeyPress>"):  # (a pinned panel stays: the pointer may go to it, a key copies)
            canvas.bind_class(tag, sequence, lambda _e: self._bubbles_left())
        for sequence in ("<ButtonPress>", "<MouseWheel>"):
            canvas.bind_class(tag, sequence, lambda _e: self._bubbles_away())
        # (the left and the right button's own, which Tk takes for them in place of <ButtonPress>: away first too)
        canvas.bind_class(tag, "<ButtonPress-1>", lambda e: self._hold_press(e))
        canvas.bind_class(tag, "<ButtonRelease-1>", lambda e: self._hold_release(e))
        canvas.bind_class(tag, "<ButtonPress-3>", lambda e: self._hold_right(e))
        canvas.bind_class(tag, "<Escape>", self._zoom_escape)

    def _bubbles_motion(self, event: tk.Event) -> None:
        """The pointer moved on the page: the panel's (`_zoom_motion`) and the bubble's in its place
        (`InPlaceMixin._reveal_motion`; only one of them ever finds a bubble, by `Settings.hover_reveal`); a press
        held for a hold that moves beyond `STILL_PX` is no hold any more (a drag, or a swipe)."""
        hold = getattr(self, "_hold", None)
        if hold is not None and (abs(event.x - hold[0]) > STILL_PX or abs(event.y - hold[1]) > STILL_PX):
            self._hold_cancel()
        self._zoom_motion(event)
        motion = getattr(self, "_reveal_motion", None)
        if motion is not None:
            motion(event)

    def _bubbles_left(self) -> None:
        """The pointer off the page, or a key: no panel (unless it is pinned) nor a bubble's other side in its place."""
        self._zoom_loose()
        hide = getattr(self, "_reveal_hide", None)
        if hide is not None:
            hide()

    def _bubbles_away(self) -> None:
        """A click on the page or the wheel: no panel nor a bubble's other side in its place."""
        self._zoom_hide()
        hide = getattr(self, "_reveal_hide", None)
        if hide is not None:
            hide()

    # ------------------------------------------------------------------ a press held on a bubble (a touch screen)
    def _hold_bubble(self, x: float, y: float) -> Any:
        """The bubble at the canvas point (x, y) whose panel a hold may pin (`text_target`, one left without a
        translation too), where the pinned panel may open (reading mode or the Reader role, the translated page on
        show: `hover.hover_usable`); else None. The Translator's pointer selects and edits the regions: never there."""
        if self.last_result is None or not hover_usable(self) or not self._result_on_show():
            return None
        return self._zoom_region_at(x, y, untranslated=True)

    def _hold_press(self, event: tk.Event) -> None:
        """The left button pressed on the page: no panel nor a bubble's other side in its place (`_bubbles_away`, as
        any press), and - on a bubble whose panel may be pinned - a hold due after `HOLD_MS` (`_hold_due`). The press
        goes on to the page's own handlers as ever (never "break")."""
        self._bubbles_away()
        self._hold_cancel(fired_too=True)
        if self._hold_bubble(event.x, event.y) is None:
            return
        self._hold = (event.x, event.y, False)  # where it was pressed, and whether its panel was pinned
        self._hold_job = self.after(HOLD_MS, self._hold_due)

    def _hold_due(self) -> None:
        """The press was held still on its bubble for `HOLD_MS`: that bubble's panel pinned
        (`BubbleTextMixin._pin_bubble`), and the release kept from the page (`_hold_release`)."""
        self._hold_job = None
        hold = getattr(self, "_hold", None)
        region = self._hold_bubble(hold[0], hold[1]) if hold is not None else None
        if region is None:
            self._hold = None
            return
        self._hold = (hold[0], hold[1], True)
        pin = getattr(self, "_pin_bubble", None)
        if pin is not None:
            pin(region)
        else:
            self._zoom_show(region, pinned=True)

    def _hold_release(self, _event: tk.Event) -> str | None:
        """The left button let go: after a hold that pinned a panel the release is TASlation's ("break": the page's
        own handlers do not see it, so no click goes on to the viewer, and the press is forgotten there too); after a
        tap or a drag nothing changes (None: the page's release as ever, a tap passed on to the viewer)."""
        fired = bool(getattr(self, "_hold", None) and self._hold[2])
        self._hold_cancel(fired_too=True)
        if not fired:
            return None
        if hasattr(self, "_drag_start"):  # (`TranslatorMixin._on_press` noted the press)
            self._drag_start = None
        return "break"

    def _hold_right(self, event: tk.Event) -> None:
        """A right click on the page: no panel nor a bubble's other side in its place, then - on a bubble whose panel
        may be pinned - that panel pinned. Windows makes a touch held still a right click (its "press and hold" on, as
        it is at first), sent as the finger lifts, and a right click on the page was nobody's: none goes to the
        viewer."""
        self._bubbles_away()
        self._hold_cancel(fired_too=True)
        region = self._hold_bubble(event.x, event.y)
        if region is None:
            return
        pin = getattr(self, "_pin_bubble", None)
        if pin is not None:
            pin(region)
        else:
            self._zoom_show(region, pinned=True)

    def _hold_cancel(self, fired_too: bool = False) -> None:
        """No hold due any more (a press that moved, or the next press); with *fired_too* one that has pinned its
        panel is forgotten as well (its release came)."""
        job = getattr(self, "_hold_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
            self._hold_job = None
        hold = getattr(self, "_hold", None)
        if hold is not None and (fired_too or not hold[2]):
            self._hold = None

    def _zoom_wanted(self) -> bool:
        """Whether the panel may open on a bubble of the translated page now: the page on show the one translated, the
        panel the way chosen (`Settings.hover_reveal`), the pointer not the Translator's own (reading mode, or the
        Reader role), and - with the translation on the page - the setting `bubble_zoom` on (with the original on the
        page the panel is the way to the translation: `hover.reverse_on`): `hover.reveal_wanted`."""
        if self.last_result is None or not reveal_wanted(self, "panel"):
            return False
        return self._result_on_show()

    def _zoom_filling(self) -> Any:
        """The page filling in on show while it is translated (`progress.Filling`), when the panel may open on its
        boxes: with the original on the page (`hover.reverse_on`), where nothing else says how far a bubble is, and the
        panel the way chosen; else None. A whole-book run's page on show is not one."""
        fill = getattr(self, "_fill", None)
        if fill is None or not reverse_on(self) or not reveal_wanted(self, "panel"):
            return None
        if run_page_on_show(self) is not None:
            return None
        return fill

    def _panel_wanted(self) -> bool:
        """Whether a panel pinned with a bubble's Japanese may stay (`bubble_text`): the page on show the one
        translated, in reading mode or the Reader role, whatever `bubble_zoom` says."""
        if self.last_result is None or (not self.reading and self.role_var.get() != "reader"):
            return False
        return self._result_on_show()

    def _zoom_region_at(self, x: float, y: float, untranslated: bool = False) -> Any:
        """The translated bubble under the canvas point (x, y) - the smallest where they nest -, or None; with
        *untranslated*, a bubble read and left without a translation as well (its Japanese can be shown)."""
        canvas = self.canvas
        if not canvas.inside(x, y):
            return None
        ix, iy = canvas.to_image_coords(int(x), int(y))
        hits = [r for r in self._page_regions()
                if text_target(r, untranslated) and r.x0 <= ix < r.x1 and r.y0 <= iy < r.y1]
        return min(hits, key=lambda r: r.area) if hits else None

    def _zoom_box_at(self, fill: Any, x: float, y: float) -> FillBox | None:
        """The box of the page filling in under the canvas point (x, y) that is to be translated or is lettered -
        the smallest where they nest -, or None."""
        canvas = self.canvas
        if not canvas.inside(x, y):
            return None
        ix, iy = canvas.to_image_coords(int(x), int(y))
        hits = [FillBox(fill, i) for i, (b, state) in enumerate(zip(fill.boxes, fill.states))
                if state in FILL_SHOWN and b[0] <= ix < b[2] and b[1] <= iy < b[3]]
        return min(hits, key=lambda t: (t.x1 - t.x0) * (t.y1 - t.y0)) if hits else None

    def _zoom_target_at(self, x: float, y: float) -> Any:
        """What the panel opens on at the canvas point (x, y): a bubble of the translated page (`_zoom_region_at`),
        or a box of the page filling in (`_zoom_box_at`, the original on the page); None."""
        if self._zoom_wanted():
            return self._zoom_region_at(x, y)
        fill = self._zoom_filling()
        return self._zoom_box_at(fill, x, y) if fill is not None else None

    def _zoom_screen_box(self, region: Any) -> Box:
        """*region*'s box (or a box of the page filling in) on the screen, as the page shows it now."""
        canvas = self.canvas
        x0, y0 = canvas.from_image_coords(region.x0, region.y0)
        x1, y1 = canvas.from_image_coords(region.x1, region.y1)
        rx, ry = canvas.winfo_rootx(), canvas.winfo_rooty()
        return rx + x0, ry + y0, rx + x1, ry + y1

    # ------------------------------------------------------------------ the pointer
    def _zoom_motion(self, event: tk.Event) -> None:
        """The pointer moved on the page: onto another bubble, the panel of the one before goes and this one's is due
        (`ZOOM_DELAY_MS`, or `ZOOM_REST_MS` on a bubble that reads well on a translated page); off the bubbles it
        goes. A panel pinned with a bubble's Japanese stays, and none other opens meanwhile."""
        if getattr(self, "_zoom_pinned", False):
            return
        target = self._zoom_target_at(event.x, event.y)
        if target is not None and same_target(target, getattr(self, "_zoom_target", None)):
            return
        self._zoom_hide()
        if target is None:
            return
        readable = int(getattr(self.settings, "readable_font_size", 0) or 0)
        soon = isinstance(target, FillBox) or reverse_on(self) or hard_to_read(target, self.canvas.scale, readable)
        self._zoom_target = target
        self._zoom_job = self.after(ZOOM_DELAY_MS if soon else ZOOM_REST_MS, self._zoom_due)

    def _zoom_due(self) -> None:
        """The pointer rested on the bubble: its panel, if it is still there and the pointer on it."""
        self._zoom_job = None
        target = getattr(self, "_zoom_target", None)
        if target is None or not self._zoom_valid(target) or not self._zoom_pointer_on(target):
            self._zoom_hide()
            return
        self._zoom_show(target)

    def _zoom_valid(self, target: Any) -> bool:
        """Whether a panel may open or stay on *target*: a box of the page filling in while it fills in and its
        translation is to come or there; a bubble of the translated page while that page is on show."""
        if isinstance(target, FillBox):
            return self._zoom_filling() is target.fill and target.state in FILL_SHOWN
        return self._zoom_wanted()

    def _zoom_pointer_on(self, region: Any) -> bool:
        """Whether the pointer is on *region* as the page shows it now."""
        try:
            px, py = self.winfo_pointerxy()
        except tk.TclError:
            return False
        x0, y0, x1, y1 = self._zoom_screen_box(region)
        return x0 <= px < x1 and y0 <= py < y1

    def _zoom_loose(self) -> None:
        """The pointer off the page, or a key: the panel goes, unless it is pinned with a bubble's Japanese."""
        if not getattr(self, "_zoom_pinned", False):
            self._zoom_hide()

    def _zoom_escape(self, _event: tk.Event | None = None) -> str | None:
        """Esc on the page: the panel goes, or the bubble shown in its place goes back, and Esc does nothing else then;
        with neither Esc is the window's as ever."""
        revealed = getattr(self, "_reveal_shown", None) is not None
        if revealed:
            self._reveal_hide()
        if getattr(self, "_zoom_popup", None) is None:
            return "break" if revealed else None
        self._zoom_hide()
        return "break"

    # ------------------------------------------------------------------ the panel
    def _zoom_show(self, region: Any, pinned: bool = False, at: tuple[int, int] | None = None) -> None:
        """The panel for *region* beside it (`zoom_place`, in the work area of the monitor of *at* - a point on the
        screen: the bubble's middle when a key chose the bubble - else of the pointer), then watched (`_zoom_watch`):

        * with the translation on the page: the original cropped from the frame in memory and the translation at
          `zoom_text_px` (none for a bubble left without one);
        * with the original on the page (`hover.reverse_on`): the translation alone at `zoom_text_px`, in the faces
          of the bubble's kind (`faces`); for a box of the page filling in, its translation once lettered, else a
          line that it is being translated with a running bar;
        * *pinned*: and under it the bubble's Japanese to select and its Copy buttons
          (`BubbleTextMixin._panel_text`), the panel staying while the pointer leaves the bubble - with the original
          on the page, the translation held back behind a "Show the translation" button (`_zoom_unveil`) -; else
          the key that pins it (`ZOOM_HINT`), on a bubble of the translated page."""
        filling = isinstance(region, FillBox)
        reverse = filling or reverse_on(self)
        result = region.fill if filling else self.last_result
        canvas = self.canvas
        bubble = self._zoom_screen_box(region)
        try:
            pointer = at if at is not None else self.winfo_pointerxy()
        except tk.TclError:
            return
        work = layout.work_area(self, *pointer)
        readable = int(getattr(self.settings, "readable_font_size", 0) or 0)
        px = zoom_text_px(readable, float(getattr(region, "font_size", 0) or 0) * canvas.scale)
        bold, italic = (False, False) if not reverse or filling else faces(region, getattr(self, "pipeline", None))
        family = tkfont.nametofont("TkDefaultFont").actual("family")
        font = tkfont.Font(family=family, size=-px, weight="bold" if bold else "normal",
                           slant="italic" if italic else "roman")
        shown = None
        if not reverse:
            original = result.original.convert("RGB").crop(region.bbox)  # (memory only)
            shown = crop_shown(original.size, canvas.scale, work)
            if shown != original.size:
                original = original.resize(shown, Image.LANCZOS)
        stacked = shown is not None and shown[0] > shown[1] * 1.3  # a wide bubble: the original above the text
        width = max(ZOOM_TEXT_EMS * px, shown[0] if stacked else 0)
        width = int(min(width, (work[2] - work[0]) * 0.45))
        text = strip_marks(region.text if filling else str(region.translated_text or ""))
        lines = "\n".join(line.rstrip(" ") for part in wrap_text(text, width, font.measure) for line in part)
        colours = ZOOM_COLOURS
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)  # above the reading window and a window always on top
        popup.configure(bg=colours["edge"], takefocus=0)
        inner = tk.Frame(popup, bg=colours["ground"], padx=10, pady=8)
        inner.pack(padx=1, pady=1)
        top = tk.Frame(inner, bg=colours["ground"])
        top.pack(side="top", anchor="w")
        if shown is not None:
            photo = ImageTk.PhotoImage(original, master=popup)
            picture = tk.Label(top, image=photo, bg=colours["ground"], borderwidth=0)
            picture.image = photo  # (kept with the label)
            picture.pack(side="top" if stacked else "left", anchor="w" if stacked else "n")
        panel = getattr(self, "_panel_text", None)
        pinned = pinned and panel is not None and not filling
        keymap = getattr(self, "keymap", None) or shortcuts.current()
        self._zoom_veiled = None
        if lines:
            words = tk.Label(top, text=lines, font=font, fg=colours["text"], bg=colours["ground"], justify="left")
            place = {"side": "top" if stacked or shown is None else "left", "anchor": "w" if stacked else "n",
                     **({"pady": (8, 0)} if stacked else {"padx": (10, 0)} if shown is not None else {})}
            if pinned and reverse:  # the original on the page: the Japanese first, the translation when asked
                button = ttk.Button(top, text=shortcuts.with_keys(SHOW_TRANSLATION, "show_japanese", keymap),
                                    command=self._zoom_unveil, takefocus=0)
                button.pack(side="top", anchor="w")
                self._zoom_veiled = (words, place, button, [])
            else:
                words.pack(**place)
        elif filling:  # its translation is on the way
            tk.Label(top, text=_(FILL_WAIT), fg=colours["text"], bg=colours["ground"], justify="left",
                     wraplength=width).pack(side="top", anchor="w")
            bar = ttk.Progressbar(top, mode="indeterminate", length=120)
            bar.pack(side="top", anchor="w", pady=(6, 0))
            bar.start(15)
        if pinned:
            panel(popup, inner, region, result, width, font)
        elif not filling:
            key = keymap.shown("show_japanese")
            if key:
                tk.Label(inner, text=_(ZOOM_HINT).format(key=key), fg=colours["hint"], bg=colours["ground"],
                         justify="left").pack(side="top", anchor="w", pady=(6, 0))
        popup.update_idletasks()
        size = (popup.winfo_reqwidth(), popup.winfo_reqheight())
        page = (canvas.winfo_rootx(), canvas.winfo_rooty(), canvas.winfo_rootx() + canvas.winfo_width(),
                canvas.winfo_rooty() + canvas.winfo_height())
        within = (max(page[0], work[0]), max(page[1], work[1]), min(page[2], work[2]), min(page[3], work[3]))
        self._zoom_where = (bubble, within, work, pointer)
        self._zoom_place(popup, size)
        self._zoom_popup, self._zoom_for = popup, (result, region)
        self._zoom_pinned = pinned
        self._zoom_state = region.state if filling else ""  # (a box lettered meanwhile: its panel is made anew)
        self._zoom_font = font
        reveal(popup)
        self._zoom_watch_job = self.after(ZOOM_WATCH_MS, self._zoom_watch)

    def _zoom_unveil(self) -> bool:
        """The translation a panel pinned with the original on the page holds back (`_zoom_show`), shown where its
        "Show the translation" button was (that button, or the key of "show_japanese" again:
        `BubbleTextMixin.show_japanese`), and the panel placed again for its new size; False when none is held back
        (the key closes the panel then)."""
        veiled, popup = getattr(self, "_zoom_veiled", None), getattr(self, "_zoom_popup", None)
        if veiled is None or popup is None:
            return False
        self._zoom_veiled = None
        words, place, button, then = veiled
        try:
            button.destroy()
            words.pack(**place)
            for step in then:  # (the panel's Close names the key again: `BubbleTextMixin._panel_text`)
                step()
            popup.update_idletasks()
            self._zoom_place(popup, (popup.winfo_reqwidth(), popup.winfo_reqheight()))
        except tk.TclError:  # (the panel is going)
            pass
        return True

    def _zoom_place(self, popup: tk.Toplevel, size: tuple[int, int]) -> None:
        """*popup* of *size* beside its bubble (`zoom_place`, within the page area, else the work area; else in the
        work area's corner away from the pointer), as `_zoom_show` found them; again when it grew (a pinned panel's
        Japanese read)."""
        bubble, within, work, pointer = self._zoom_where
        place = (zoom_place(size, bubble, within) or zoom_place(size, bubble, work)
                 or fallback_place(size, pointer, work))
        popup.geometry(f"+{place[0]}+{place[1]}")

    def _zoom_watch(self) -> None:
        """While the panel shows: it goes as soon as its page is no longer on show (a page turned in the viewer, or
        the page read again), its bubble is gone, the pointer is off the bubble (unless it is pinned), or it may not
        show any more. A box of the page filling in whose translation came gets its panel anew; once that page is
        done, the panel of the bubble under the pointer on the translated page opens at once (the pointer rested
        there)."""
        self._zoom_watch_job = None
        shown = getattr(self, "_zoom_for", None)
        if getattr(self, "_zoom_popup", None) is None or shown is None:
            return
        source, region = shown
        if isinstance(region, FillBox):
            on = self._zoom_pointer_on(region)
            if on and self._zoom_valid(region):
                if region.state != getattr(self, "_zoom_state", ""):
                    self._zoom_hide()
                    self._zoom_show(region)
                    return
                self._zoom_watch_job = self.after(ZOOM_WATCH_MS, self._zoom_watch)
                return
            self._zoom_hide()
            if on and getattr(self, "_fill", None) is not source and self._zoom_wanted():
                try:
                    px, py = self.winfo_pointerxy()
                except tk.TclError:
                    return
                found = self._zoom_region_at(px - self.canvas.winfo_rootx(), py - self.canvas.winfo_rooty())
                if found is not None:
                    self._zoom_target = found
                    self._zoom_show(found)
            return
        pinned = getattr(self, "_zoom_pinned", False)
        if (self.last_result is not source or not any(r is region for r in source.regions)  # (`==` reaches masks)
                or not (self._panel_wanted() if pinned else self._zoom_wanted())
                or not (pinned or self._zoom_pointer_on(region))):
            self._zoom_hide()
            return
        self._zoom_watch_job = self.after(ZOOM_WATCH_MS, self._zoom_watch)

    def _zoom_hide(self) -> None:
        """The panel away, and the one that was due not shown; the page takes the keys back when a click to select
        the Japanese had given them to the panel."""
        for name in ("_zoom_job", "_zoom_watch_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except (tk.TclError, ValueError):
                    pass
                setattr(self, name, None)
        self._zoom_target = self._zoom_for = None
        self._zoom_pinned = False
        self._zoom_pinned_at = None  # (where the pointer was as it was pinned: `BubbleTextMixin._pin_bubble`)
        self._zoom_veiled = None  # (the translation a pinned panel holds back: `_zoom_unveil`)
        self._zoom_japanese = None  # (the pinned panel's line of Japanese: `BubbleTextMixin._panel_text`)
        popup, self._zoom_popup = getattr(self, "_zoom_popup", None), None
        if popup is None:
            return
        try:
            focused = self.focus_get() if hasattr(self, "focus_get") else None
        except (KeyError, tk.TclError):
            focused = None
        try:
            inside = focused is not None and focused.winfo_toplevel() is popup
            popup.destroy()
        except tk.TclError:
            inside = False
        if inside:
            focus = getattr(self, "_focus_page", None)
            if focus is not None:
                focus()
