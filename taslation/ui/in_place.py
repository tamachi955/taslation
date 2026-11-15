"""A bubble the pointer rests on shows its other side in its own place (`Settings.hover_reveal` "in_place", `hover`):
in reading mode and the Reader role, the bubble itself changes while the pointer rests on it and changes back when it
leaves - the other way of showing what the panel beside a bubble shows (`zoom`, "panel").

* With the translation on the page (`Settings.hover_shows` "original"): the bubble shows the page as the viewer has
  it there - its original lettering, in its own font and style. The pixels where the translated page differs from its
  capture (the lettering erased, the translation set), within the bubble's reach and nearer to it than to any other
  region (`lettering_patch`), are taken from the viewer's frame. Not with `Settings.bubble_zoom` off, nor while
  View > Show original shows the whole page as the viewer has it anyway.
* With the original on the page ("translation"): the bubble is erased and its translation set exactly as the
  translated page has it - the same pixels, from the translated page. What was read as text, what the erase took and
  how the translation is set show where they are: the way to see a mistake of the reading or of the detection, which
  the panel does not show. While the page is being translated, a box still waiting for its translation shows the
  outline the page filling in gives it (`progress.Filling.outlines`, `hovered_outline`), one lettered already its
  lettering; once the page is done, the bubble under the pointer shows at once (the pointer has rested there).

When: after the panel's delays (`zoom.ZOOM_DELAY_MS` with the original on the page or on a bubble hard to read where
it is, `zoom.ZOOM_REST_MS` on any other one), so that a pointer passing over the page changes nothing. Until the
pointer leaves the bubble - `REVEAL_HOLD_PX` round it still keep it, so that a pointer on its edge does not make it
come and go. One bubble at a time: the pointer on another bubble takes it away, and that one shows after the same
rest. It is drawn over the picture as a part of it (`preview.ImageCanvas.set_patch`), nothing else drawn again; it
goes on a click (which goes on to the viewer as ever), the wheel, a key, Esc (taken for it while it shows), the pointer
off the page, a panel pinned with the bubble's Japanese (`bubble_text`), and as soon as its page is not on show any
more (`_reveal_watch`, every `zoom.ZOOM_WATCH_MS`). Nothing of a page is written anywhere: the patches are cut from
the pictures in memory."""

from __future__ import annotations

import tkinter as tk
from typing import Any, NamedTuple, Sequence

import numpy as np
from PIL import Image

from ..regions import ERASED
from .hover import reveal_wanted, reverse_on
from .preview import Patch
from .strip import run_page_on_show
from .zoom import FILL_SHOWN, ZOOM_DELAY_MS, ZOOM_REST_MS, ZOOM_WATCH_MS, hard_to_read

REVEAL_HOLD_PX = 6  # canvas pixels round a bubble whose other side shows: the pointer there keeps it on show

Box = tuple[int, int, int, int]


class Target(NamedTuple):
    """A bubble the pointer rests on: the translated page on show (`PageResult`) and its region, or the page being
    translated (`progress.Filling`) and the index of its box."""

    source: Any
    key: Any
    filling: bool


# ---------------------------------------------------------------- the patch of a bubble
def reach(box: Box, size: tuple[int, int]) -> Box:
    """Where a region's lettering may lie on a page of *size*: its box grown by half its width and its height on each
    side (a slanted region is lettered in so much round it, `render.slant.letter_slanted`)."""
    x0, y0, x1, y1 = box
    rx, ry = max(0, x1 - x0) // 2, max(0, y1 - y0) // 2
    return max(0, x0 - rx), max(0, y0 - ry), min(size[0], x1 + rx), min(size[1], y1 + ry)


def _gap2(box: Box, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """The squared distance from each pixel (*xs* across, *ys* down) to *box* (0 inside it)."""
    dx = np.maximum(np.maximum(box[0] - xs, xs - (box[2] - 1)), 0)
    dy = np.maximum(np.maximum(box[1] - ys, ys - (box[3] - 1)), 0)
    return dx * dx + dy * dy


def own_pixels(box: Box, others: Sequence[Box], window: Box) -> np.ndarray:
    """The pixels of *window* (a boolean array of its size) that belong to the region of *box* rather than to one of
    the regions of *others*: inside its box, or nearer to it than to any of theirs. A box too far from the window to
    be nearer than *box* anywhere in it is not looked at."""
    xs = np.arange(window[0], window[2], dtype=np.int64)[None, :]
    ys = np.arange(window[1], window[3], dtype=np.int64)[:, None]
    mine = _gap2(box, xs, ys)
    farthest = int(mine.max()) if mine.size else 0
    corners_x = np.array([[window[0], window[2] - 1]])
    corners_y = np.array([[window[1]], [window[3] - 1]])
    nearest = None
    for other in others:
        inside = other[0] < window[2] and window[0] < other[2] and other[1] < window[3] and window[1] < other[3]
        if not inside and _gap2(other, corners_x, corners_y).min() > farthest:
            continue  # (a box beyond the window, farther from all of it than its own box ever is)
        theirs = _gap2(other, xs, ys)
        nearest = theirs if nearest is None else np.minimum(nearest, theirs)
    if nearest is None:
        return np.ones(mine.shape, bool)
    return (mine == 0) | (mine < nearest)


def lettering_patch(original: Image.Image, lettered: Image.Image, box: Box, others: Sequence[Box],
                    values: Image.Image | None = None) -> Patch | None:
    """The patch that shows the region of *box* the other way: where *lettered* (the page translated) differs from
    *original* (the capture it was made from) - the lettering erased, the translation set, its outline -, within the
    region's `reach` and on its `own_pixels` against the boxes of the page's other regions that are erased or lettered
    (*others*), the pixels of *values* (*lettered* when None: the translation over the original; the viewer's frame:
    the original over the translation) opaque and the rest clear, trimmed to what it holds. None when it changes
    nothing there, or the pictures are not of one size."""
    values = lettered if values is None else values
    if original.size != lettered.size or values.size != original.size:
        return None
    window = reach(box, original.size)
    if window[2] <= window[0] or window[3] <= window[1]:
        return None
    before = np.asarray(original.crop(window).convert("RGB"))
    after = np.asarray(lettered.crop(window).convert("RGB"))
    changed = np.any(before != after, axis=2)
    if not changed.any():
        return None
    changed &= own_pixels(box, others, window)
    ys, xs = np.nonzero(changed)
    if not xs.size:
        return None
    tx0, ty0, tx1, ty1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    pixels = after if values is lettered else np.asarray(values.crop(window).convert("RGB"))
    alpha = np.where(changed[ty0:ty1, tx0:tx1], 255, 0).astype(np.uint8)
    rgba = np.ascontiguousarray(np.dstack([pixels[ty0:ty1, tx0:tx1], alpha]))
    return (window[0] + tx0, window[1] + ty0, window[0] + tx1, window[1] + ty1), Image.fromarray(rgba)


def drawn(region: Any) -> bool:
    """Whether the page translated differs from its capture at *region*: a translation set there, or "erase only"
    (as `pipeline.erases` has it)."""
    status = getattr(region, "status", "")
    return (status == "translated" and bool(getattr(region, "translated_text", ""))) or status == ERASED


def refresh(window: Any) -> None:
    """Before the page is drawn again (`LiveViewMixin._redisplay`): the bubble whose other side shows is drawn with
    it (`ImageCanvas.patch`), or no bubble once it may not show any more (`InPlaceMixin._reveal_check`)."""
    canvas = getattr(window, "canvas", None)
    shown = getattr(window, "_reveal_shown", None)
    patch = None
    if shown is not None:
        shown = window._reveal_check()
        patch = window._reveal_patch(shown) if shown is not None else None
    if canvas is not None and (patch is not None or getattr(canvas, "patch", None) is not None):
        canvas.patch = patch


def hovered_outline(window: Any, fill: Any) -> list[tuple[Box, str, bool]]:
    """While a page fills in with the original on the page: the outline of the box under the pointer, when its
    translation has not come yet (`progress.Filling.outlines`), else none."""
    shown = getattr(window, "_reveal_shown", None)
    if shown is None or not shown.filling or shown.source is not fill:
        return []
    box = tuple(fill.boxes[shown.key]) if 0 <= shown.key < len(fill.boxes) else None
    return [o for o in fill.outlines() if tuple(o[0]) == box][:1]


class InPlaceMixin:
    """A bubble's other side in its own place. A part of `app.App` through `reading.ReadingMixin` (no `__init__`: its
    state starts on first use; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the bubble under the pointer
    def _reveal_on(self) -> bool:
        """Whether a bubble shows its other side in its place now (`hover.reveal_wanted`), and - with the translation
        on the page - Show original not showing the whole page as the viewer has it anyway."""
        if not reveal_wanted(self, "in_place"):
            return False
        return reverse_on(self) or not self.original_var.get()

    def _reveal_target_at(self, x: float, y: float) -> Target | None:
        """The bubble at the canvas point (x, y) that may show its other side now - the smallest where they nest: a
        translated region of the page on show, or (with the original on the page) a box of the page filling in that is
        to be translated or is lettered -; None elsewhere, or when none may."""
        canvas = self.canvas
        if not self._reveal_on() or not canvas.inside(x, y):
            return None
        ix, iy = canvas.to_image_coords(int(x), int(y))
        if self._result_on_show():
            hits = [r for r in self._page_regions() if r.status == "translated" and str(r.translated_text or "").strip()
                    and r.x0 <= ix < r.x1 and r.y0 <= iy < r.y1]
            return Target(self.last_result, min(hits, key=lambda r: r.area), False) if hits else None
        fill = getattr(self, "_fill", None)
        if fill is None or not reverse_on(self) or run_page_on_show(self) is not None:
            return None
        hits = [i for i, (b, state) in enumerate(zip(fill.boxes, fill.states))
                if state in FILL_SHOWN and b[0] <= ix < b[2] and b[1] <= iy < b[3]]
        if not hits:
            return None
        area = lambda i: (fill.boxes[i][2] - fill.boxes[i][0]) * (fill.boxes[i][3] - fill.boxes[i][1])  # noqa: E731
        return Target(fill, min(hits, key=area), True)

    def _reveal_valid(self, target: Target) -> bool:
        """Whether *target* may still show: its page on show as it was, its region there (by identity: `==` reaches
        the masks) or its box still to be translated or lettered."""
        if not self._reveal_on():
            return False
        if target.filling:
            fill = getattr(self, "_fill", None)
            return (fill is target.source and reverse_on(self) and run_page_on_show(self) is None
                    and 0 <= target.key < len(fill.states) and fill.states[target.key] in FILL_SHOWN)
        result = self.last_result
        return (result is target.source and self._result_on_show()
                and any(r is target.key for r in result.regions) and target.key.status == "translated")

    def _reveal_box(self, target: Target) -> Box:
        """*target*'s box in the image's pixels."""
        if target.filling:
            return tuple(int(v) for v in target.source.boxes[target.key])  # type: ignore[return-value]
        return target.key.bbox

    def _reveal_canvas_box(self, target: Target, grow: int = 0) -> Box:
        """*target*'s box on the canvas as the page shows it now, *grow* canvas pixels larger on each side."""
        x0, y0, x1, y1 = self._reveal_box(target)
        cx0, cy0 = self.canvas.from_image_coords(x0, y0)
        cx1, cy1 = self.canvas.from_image_coords(x1, y1)
        return cx0 - grow, cy0 - grow, cx1 + grow, cy1 + grow

    def _reveal_pointer(self) -> tuple[int, int] | None:
        """The pointer on the canvas (its pixels), None when it cannot be told."""
        try:
            px, py = self.winfo_pointerxy()
            return px - self.canvas.winfo_rootx(), py - self.canvas.winfo_rooty()
        except tk.TclError:
            return None

    def _reveal_holds(self, target: Target, x: float, y: float) -> bool:
        """Whether the canvas point (x, y) keeps *target* on show: on its box or within `REVEAL_HOLD_PX` of it."""
        x0, y0, x1, y1 = self._reveal_canvas_box(target, REVEAL_HOLD_PX)
        return x0 <= x < x1 and y0 <= y < y1

    def _reveal_patch(self, target: Target) -> Patch | None:
        """What *target* lays over the page (`lettering_patch`, kept for the page, the region and the frame while
        they stay as they are): with the original on the page its lettering, from the translated page; with the
        translation on the page its original, from the frame the page shows lettered (the viewer's latest one of that
        page, else the capture); none for a box whose translation has not come yet (its outline shows instead:
        `hovered_outline`)."""
        if target.filling:
            fill, i = target.source, target.key
            if fill.page is None or fill.states[i] != "lettered":
                return None
            boxes = [tuple(b) for b in fill.boxes]
            return lettering_patch(fill.frame, fill.page, boxes[i], boxes[:i] + boxes[i + 1:])
        result, region = target.source, target.key
        values = None
        if not reverse_on(self):
            live = getattr(self, "_live", None)
            values = live if live is not None else result.original
        memo = getattr(self, "_reveal_memo", None)
        if memo is not None and memo[0] is result.image and memo[1] is region and memo[2] is values:
            return memo[3]
        others = [r.bbox for r in result.regions if r is not region and drawn(r)]
        patch = lettering_patch(result.original, result.image, region.bbox, others, values)
        self._reveal_memo = (result.image, region, values, patch)
        return patch

    def _reveal_motion(self, event: tk.Event) -> None:
        """The pointer moved on the page: onto another bubble, the one shown before goes back and this one's other
        side is due after the panel's delay (`ZOOM_DELAY_MS` with the original on the page or on a bubble hard to read
        where it is, else `ZOOM_REST_MS`); off the bubbles (and beyond `REVEAL_HOLD_PX` of the one on show) it goes.
        Nothing while a panel is pinned with a bubble's Japanese (`bubble_text`)."""
        if getattr(self, "_zoom_pinned", False):
            return
        target = self._reveal_target_at(event.x, event.y)
        shown, pending = getattr(self, "_reveal_shown", None), getattr(self, "_reveal_pending", None)
        current = shown or pending
        if target is not None and current is not None and target.source is current.source and target.key is current.key:
            return
        if target is None and shown is not None and self._reveal_holds(shown, event.x, event.y):
            return
        self._reveal_hide()
        if target is None:
            return
        soon = target.filling or reverse_on(self)
        if not soon:
            readable = int(getattr(self.settings, "readable_font_size", 0) or 0)
            soon = hard_to_read(target.key, self.canvas.scale, readable)
        self._reveal_pending = target
        self._reveal_job = self.after(ZOOM_DELAY_MS if soon else ZOOM_REST_MS, self._reveal_due)

    def _reveal_due(self) -> None:
        """The pointer rested on the bubble: its other side in its place, if it may still show and the pointer is on
        it; then watched (`_reveal_watch`)."""
        self._reveal_job = None
        target, self._reveal_pending = getattr(self, "_reveal_pending", None), None
        pointer = self._reveal_pointer()
        if (target is None or not self._reveal_valid(target) or pointer is None
                or not self._reveal_holds(target, *pointer) or self._reveal_target_at(*pointer) is None):
            return
        self._reveal_shown = target
        self._reveal_draw()
        self._reveal_watch_job = self.after(ZOOM_WATCH_MS, self._reveal_watch)

    def _reveal_draw(self) -> None:
        """The bubble on show drawn over the page: the patch alone over the picture as it is; a box of a page filling
        in with the page drawn again (its outline is one of the page's)."""
        shown = getattr(self, "_reveal_shown", None)
        if shown is not None and shown.filling:
            self._redisplay()
            return
        self.canvas.set_patch(self._reveal_patch(shown) if shown is not None else None)

    def _reveal_check(self) -> Target | None:
        """The bubble to show now (`refresh`, `_reveal_watch`): the one on show while it may still show; when the page
        it was filling in on is done, the bubble under the pointer on the translated page, at once (the pointer has
        rested there); else none, and nothing is watched any more."""
        shown = getattr(self, "_reveal_shown", None)
        if shown is None:
            return None
        if self._reveal_valid(shown):
            return shown
        if self._reveal_on() and shown.filling and getattr(self, "_fill", None) is not shown.source:
            pointer = self._reveal_pointer()
            found = self._reveal_target_at(*pointer) if pointer is not None else None
            if found is not None:
                self._reveal_shown = found
                return found
        self._reveal_drop()
        return None

    def _reveal_watch(self) -> None:
        """While a bubble's other side shows: it goes once its page is not on show as it was (and the page was not
        drawn again meanwhile, which would have seen to it: `refresh`), the pointer is off it, or it may not show any
        more (the choices changed)."""
        self._reveal_watch_job = None
        shown = getattr(self, "_reveal_shown", None)
        if shown is None:
            return
        pointer = self._reveal_pointer()
        now = self._reveal_check()
        if now is None or pointer is None or not self._reveal_holds(now, *pointer):
            self._reveal_hide()
            return
        if now is not shown:  # (the page filling in is done: the bubble on the translated page, at once)
            self._reveal_draw()
        self._reveal_watch_job = self.after(ZOOM_WATCH_MS, self._reveal_watch)

    def _reveal_drop(self) -> None:
        """No bubble on show nor due any more, nothing drawn (the page is being drawn again)."""
        for name in ("_reveal_job", "_reveal_watch_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except (tk.TclError, ValueError):
                    pass
                setattr(self, name, None)
        self._reveal_shown = self._reveal_pending = None

    def _reveal_hide(self) -> None:
        """The bubble as the page shows it again, and the one that was due not shown."""
        shown = getattr(self, "_reveal_shown", None)
        self._reveal_drop()
        canvas = getattr(self, "canvas", None)
        if canvas is not None and getattr(canvas, "patch", None) is not None:
            canvas.set_patch(None)
        if shown is not None and shown.filling:
            self._redisplay()  # (its outline goes)


__all__ = ["REVEAL_HOLD_PX", "InPlaceMixin", "Target", "drawn", "hovered_outline", "lettering_patch", "own_pixels",
           "reach", "refresh"]
