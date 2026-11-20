"""The indicator beside the page, drawn (`SideView`): a small canvas laid over the page area's exit-side margin
(`side_model.side_layout` says where), never over the page. Two forms:

* the column - a cell a screen turned past, top to bottom in the order of first sight: its thumbnail (memory only, too
  small to read), its number, and two bars, R for reading the text and T for the translation, each saying its state
  three ways (its letter, its colour, its pattern: empty, a moving stripe, filled, crossed, hatched, dotted); a screen
  that went by too fast to catch is a dashed frame with its number and "?"; the screen on show has a yellow outline
  and a notch pointing at the page, and is kept in view as the person turns (the wheel scrolls the column); a screen
  whose words changed since the person saw them has a diamond at its thumbnail's corner on the page's side;
* the rail - a bar `RAIL_W` px wide (`RAIL_W_FULL` on the full screen) the page's height, a mark a screen from the
  top, or runs of one mark merged when the screens are many (`side_model.rail_marks`): done filled, being worked on
  half filled, waiting hollow, failed in stripes, not caught dotted; the screen on show outlined in yellow with a notch
  beside it, the updated ones a diamond beside them, both in the column of marks outside the rail.

Nothing moves but the working stripe of the column's bars: one `after` timer, which runs only while a bar is at work.
The pointer resting on a thumbnail, a bar or a mark says what it is (`CanvasTip`), anywhere else on the indicator the
summary (`side_model.summary_lines`); a click says in the status line how to read that screen - in the viewer - and
nothing else (`side.SideMixin._pick_screen`): no page from memory is ever shown, and nothing goes to the viewer."""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from PIL import ImageTk

from .side_model import (BAR_GAP_X, BAR_H, BAR_ROW, BAR_W, CELL_H, LETTER_W, MARKS_W, NOTCH_W, PAD, SideLayout,
                         SideModel, bar_line, rail_marks, rail_y, run_tip, screen_tip, summary_lines)
from .strip import (ANIM_MS, CHOSEN, DONE, EDGE, FAILED, SKIPPED, STRIPE_STEP, STRIPE_W, TEXT, THUMB_BOX, WORKING,
                    CanvasTip, stage_letter)

UPDATED = "#cc79a7"  # reddish purple (Okabe-Ito): a screen whose words changed since it was seen; the page's brackets
MISSED = EDGE  # a screen that went by too fast: grey, dashed and dotted (the purple is the updated mark's alone)
DARK = "#000000"  # the edge round a diamond and a notch, seen on any thumbnail
DIAMOND = 6  # half the updated diamond's width
ROWS = ("read", "translate")


def diamond(canvas: tk.Canvas, cx: float, cy: float, r: float, tags: tuple[str, ...]) -> None:
    """The updated mark: a diamond *r* px from its middle to each point, edged dark (seen on a page and on the
    ground)."""
    canvas.create_polygon(cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy, fill=UPDATED, outline=DARK, width=1,
                          tags=tags)


class SideView(tk.Canvas):
    """The indicator's canvas, a child of the page area's canvas, placed by `place_at`. *on_pick*: a screen was
    clicked (its number). *now*: the clock the summary's estimate is reckoned by."""

    def __init__(self, master: tk.Misc, model: SideModel, on_pick: Callable[[int], None], ground: str = "#202020",
                 now: Callable[[], float] = time.monotonic):
        super().__init__(master, bg=ground, highlightthickness=0, borderwidth=0, takefocus=0,
                         yscrollincrement=CELL_H // 2)
        self.model, self.on_pick, self.now = model, on_pick, now
        self.layout = SideLayout()
        self._photos: dict[int, ImageTk.PhotoImage] = {}
        self._phase = 0
        self._anim_job: str | None = None
        self._marks: list = []  # the rail's marks as drawn last
        self._font = tkfont.Font(self, family=tkfont.nametofont("TkDefaultFont").cget("family"), size=8)
        self.bind("<ButtonRelease-1>", self._clicked)
        self.bind("<MouseWheel>", self._wheel)
        self.tip = CanvasTip(self, self.text_at)

    # ---------------------------------------------------------------- where
    @property
    def shown(self) -> bool:
        return bool(self.layout.kind) and bool(self.winfo_manager())

    def place_at(self, layout: SideLayout, ground: str | None = None) -> None:
        """The indicator where *layout* says (its kind "": away), drawn again when that changed."""
        if ground is not None and str(self.cget("bg")) != ground:
            self.configure(bg=ground)
        if not layout.kind:
            self.layout = layout
            if self.winfo_manager():
                self.place_forget()
            self._sync_animation()
            return
        changed = layout != self.layout
        self.layout = layout
        if changed or not self.winfo_manager():
            x0, y0, x1, y1 = layout.box
            self.place(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
            self.redraw()

    def _size(self) -> tuple[int, int]:
        x0, y0, x1, y1 = self.layout.box
        return x1 - x0, y1 - y0

    # ---------------------------------------------------------------- drawing
    def redraw(self) -> None:
        """Everything again (another layout, a screen gone, another language)."""
        self.delete("all")
        self._photos = {k: v for k, v in self._photos.items() if k in self.model.screens}
        if self.layout.kind == "column":
            first = self.yview()[0]
            for index, seq in enumerate(self.model.order):
                self._draw_cell(index, seq)
            self._scroll_region()
            self.yview_moveto(first)
        elif self.layout.kind == "rail":
            self.configure(scrollregion=(0, 0, *self._size()))
            self.yview_moveto(0)
            self._draw_rail()
        self._sync_animation()

    def screen_changed(self, seq: int, new: bool) -> None:
        """A screen's event came: its cell drawn again (a new one at the end; the column follows it there while it
        showed the end and no screen is on show), or the rail again."""
        if self.layout.kind == "rail":
            self.delete("all")
            self._draw_rail()
            return
        if self.layout.kind != "column":
            return
        try:
            index = self.model.order.index(seq)
        except ValueError:
            self.redraw()
            return
        at_end = self.yview()[1] >= 0.999
        if new and index != len(self.model.order) - 1:  # (one came before others: the cells after it move down)
            self.redraw()
            return
        self.delete(f"s{seq}")
        self._draw_cell(index, seq)
        if new:
            self._scroll_region()
            if at_end and self.model.on_show is None:
                self.yview_moveto(1.0)
        self._sync_animation()

    def show(self, seq: int | None) -> None:
        """The screen on show moved to *seq*: the cells it left and came to drawn again, and the column scrolled so
        that it is in view (not moved when it is); the rail again."""
        if self.layout.kind == "rail":
            self.delete("all")
            self._draw_rail()
            return
        if self.layout.kind != "column":
            return
        self.redraw_marks()
        if seq is None or seq not in self.model.screens:
            return
        index = self.model.order.index(seq)
        total = max(1, len(self.model.order) * CELL_H)
        first, last = self.yview()
        top, bottom = index * CELL_H / total, (index + 1) * CELL_H / total
        if top < first or bottom > last:
            self.yview_moveto(max(0.0, top - (last - first) / 2 + CELL_H / total / 2))

    def redraw_marks(self) -> None:
        """The marks that follow the screen on show and the updated ones: every cell's outline, notch and diamond."""
        if self.layout.kind == "rail":
            self.delete("all")
            self._draw_rail()
            return
        self.delete("marks")
        for index, seq in enumerate(self.model.order):
            self._draw_cell_marks(index, seq)

    def _scroll_region(self) -> None:
        width, _height = self._size()
        self.configure(scrollregion=(0, 0, width, max(1, len(self.model.order) * CELL_H)))

    def _photo(self, seq: int) -> ImageTk.PhotoImage | None:
        photo = self._photos.get(seq)
        screen = self.model.screens.get(seq)
        if photo is None and screen is not None and screen.thumb is not None:
            photo = self._photos[seq] = ImageTk.PhotoImage(screen.thumb, master=self)
        return photo

    def _cell_parts(self, index: int) -> dict[str, tuple[int, int, int, int]]:
        """Where a cell's parts go (canvas pixels): its thumbnail's box, its number's place, its two bars, its notch;
        mirrored on the right of the page, so that the bars and the notch are on the page's side."""
        width, _h = self._size()
        top = index * CELL_H
        left_side = self.layout.side == "left"  # (the column left of the page: the page on its right)
        tx0 = PAD if left_side else width - PAD - THUMB_BOX[0]
        thumb = (tx0, top + PAD, tx0 + THUMB_BOX[0], top + PAD + THUMB_BOX[1])
        gx0 = thumb[2] + BAR_GAP_X if left_side else PAD + NOTCH_W  # the letters and bars
        bars = {}
        for row, stage in enumerate(ROWS):
            y0 = top + PAD + 30 + row * BAR_ROW
            bars[stage] = (gx0 + LETTER_W, y0, gx0 + LETTER_W + BAR_W, y0 + BAR_H)
        number = (gx0 + (LETTER_W + BAR_W) // 2, top + PAD + 14, 0, 0)
        nx = gx0 + LETTER_W + BAR_W if left_side else PAD
        notch = (nx, top + PAD + THUMB_BOX[1] // 2 - 6, nx + NOTCH_W, top + PAD + THUMB_BOX[1] // 2 + 6)
        return {"thumb": thumb, "number": number, "notch": notch, **bars}

    def _draw_cell(self, index: int, seq: int) -> None:
        screen = self.model.screens[seq]
        tag = f"s{seq}"
        parts = self._cell_parts(index)
        x0, y0, x1, y1 = parts["thumb"]
        mid_x, mid_y = (x0 + x1) // 2, (y0 + y1) // 2
        photo = self._photo(seq)
        if photo is not None:
            self.create_image(mid_x, mid_y, image=photo, tags=(tag,))
        elif screen.mark == "missed":  # went by too fast: a dashed frame, its number and a question mark
            self.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=MISSED, dash=(3, 3), width=2, tags=(tag,))
            self.create_text(mid_x, mid_y, text=f"{seq}\n?", fill=TEXT, font=self._font, justify="center", tags=(tag,))
        else:  # no picture came (yet): a frame
            self.create_rectangle(x0, y0, x1, y1, outline=EDGE, tags=(tag,))
        nx, ny, _a, _b = parts["number"]
        self.create_text(nx, ny, text=str(seq), fill=TEXT, font=self._font, tags=(tag,))
        for stage in ROWS:
            self._draw_bar(parts[stage], stage, screen.stages[stage], tag)
        self._draw_cell_marks(index, seq)

    def _thumb_box(self, index: int, seq: int) -> tuple[int, int, int, int]:
        """The thumbnail as drawn (a spread's is less tall than its cell)."""
        x0, y0, x1, y1 = self._cell_parts(index)["thumb"]
        photo = self._photos.get(seq)
        if photo is None:
            return x0, y0, x1, y1
        w, h = photo.width(), photo.height()
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        return cx - w // 2, cy - h // 2, cx - w // 2 + w, cy - h // 2 + h

    def _draw_cell_marks(self, index: int, seq: int) -> None:
        screen = self.model.screens[seq]
        tags = (f"s{seq}", "marks")
        x0, y0, x1, y1 = self._thumb_box(index, seq)
        toward_page = x1 if self.layout.side == "left" else x0
        if self.model.on_show == seq:
            self.create_rectangle(x0 - 2, y0 - 2, x1 + 1, y1 + 1, outline=CHOSEN, width=2, tags=tags)
            n0, n1, n2, n3 = self._cell_parts(index)["notch"]
            ny = (n1 + n3) // 2
            if self.layout.side == "left":  # a triangle pointing at the page
                points = (n0, n1, n2, ny, n0, n3)
            else:
                points = (n2, n1, n0, ny, n2, n3)
            self.create_polygon(*points, fill=CHOSEN, outline=DARK, width=1, tags=tags)
        if screen.updated:
            r = DIAMOND
            cx = toward_page - r - 1 if self.layout.side == "left" else toward_page + r + 1
            diamond(self, cx, y0 + r + 1, r, tags)

    def _draw_bar(self, box: tuple[int, int, int, int], stage: str, state: str, tag: str) -> None:
        x0, y0, x1, y1 = box
        self.create_text(x0 - LETTER_W // 2 - 1, (y0 + y1) // 2, text=stage_letter(stage), fill=TEXT,
                         font=self._font, tags=(tag,))
        if state == "done":
            self.create_rectangle(x0, y0, x1, y1, fill=DONE, outline=DONE, tags=(tag,))
        elif state == "failed":
            self.create_rectangle(x0, y0, x1, y1, fill=FAILED, outline=FAILED, tags=(tag,))
            mid = (x0 + x1) // 2
            for a, b in ((-3, 3), (3, -3)):  # a cross in the middle
                self.create_line(mid + a, y0 + 1, mid + b, y1 - 1, fill=TEXT, width=2, tags=(tag,))
        elif state == "missed":
            self.create_rectangle(x0, y0, x1, y1, outline=MISSED, dash=(2, 2), tags=(tag,))
            for x in range(x0 + 3, x1 - 1, 5):  # dotted
                self.create_rectangle(x, (y0 + y1) // 2 - 1, x + 1, (y0 + y1) // 2 + 1, fill=MISSED, outline=MISSED,
                                      tags=(tag,))
        elif state == "skipped":
            self.create_rectangle(x0, y0, x1, y1, outline=SKIPPED, tags=(tag,))
            for x in range(x0 + 2, x1, 5):  # hatched
                self.create_line(x, y1 - 1, min(x1 - 1, x + BAR_H - 2), y0 + 1, fill=SKIPPED, tags=(tag,))
        else:  # waiting (empty) or working (its stripe comes with the timer)
            self.create_rectangle(x0, y0, x1, y1, outline=EDGE, tags=(tag,))
            if state == "working":
                self._draw_stripe(x0, y0, x1, y1, tag)

    def _draw_stripe(self, x0: int, y0: int, x1: int, y1: int, tag: str) -> None:
        span = max(1, x1 - x0 - STRIPE_W)
        travel = self._phase * STRIPE_STEP % (2 * span)
        offset = travel if travel <= span else 2 * span - travel  # to and fro
        self.create_rectangle(x0 + 1 + offset, y0 + 1, x0 + offset + STRIPE_W, y1, fill=WORKING, outline="",
                              tags=(tag, "stripe"))

    def _draw_rail(self) -> None:
        """The rail: its marks top to bottom, the screen on show outlined with its notch beside it, the updated
        diamonds beside theirs."""
        layout = self.layout
        _width, height = self._size()
        rx, rw, mx = layout.rail_x, layout.rail_w, layout.marks_x
        self._marks = marks = rail_marks(self.model, height)
        self.create_rectangle(rx, 0, rx + rw - 1, height - 1, outline="#3a3a3a", tags=("rail",))
        for m in marks:
            self._draw_rail_mark(rx, rw, m)
        for m in marks:
            if m.on_show:
                self.create_rectangle(rx, m.y0, rx + rw - 1, max(m.y0 + 2, m.y1 - 1), outline=CHOSEN, width=2,
                                      tags=("rail", "on-show"))
        notch_at = rail_y(marks, self.model.on_show) if self.model.on_show is not None else None
        toward_rail = layout.side == "left"  # (the marks' column is outside the rail: the rail on its right)
        for seq in self.model.order:
            screen = self.model.screens[seq]
            if not screen.updated or seq == self.model.on_show:
                continue
            y = rail_y(marks, seq)
            if y is not None:
                diamond(self, mx + MARKS_W / 2, min(max(y, MARKS_W / 2), height - MARKS_W / 2), MARKS_W / 2,
                        ("rail", "updated"))
        if notch_at is not None:
            y = min(max(notch_at, 5), height - 5)
            if toward_rail:
                points = (mx, y - 5, mx + MARKS_W, y, mx, y + 5)
            else:
                points = (mx + MARKS_W, y - 5, mx, y, mx + MARKS_W, y + 5)
            self.create_polygon(*points, fill=CHOSEN, outline=DARK, width=1, tags=("rail", "notch"))

    def _draw_rail_mark(self, rx: int, rw: int, m) -> None:
        y0, y1 = m.y0, max(m.y0 + 1, m.y1)
        tags = ("rail", f"mark-{m.mark}")
        if m.mark == "done":
            self.create_rectangle(rx, y0, rx + rw, y1, fill=DONE, outline="", tags=tags)
        elif m.mark == "working":  # half filled: the half towards the page
            half = rw // 2
            page_half = (rx + rw - half, rx + rw) if self.layout.side == "left" else (rx, rx + half)
            self.create_rectangle(rx, y0, rx + rw - 1, y1 - 1, outline=WORKING, tags=tags)
            self.create_rectangle(page_half[0], y0, page_half[1], y1, fill=WORKING, outline="", tags=tags)
        elif m.mark == "failed":  # in stripes across
            for y in range(y0, y1, 3):
                self.create_rectangle(rx, y, rx + rw, min(y1, y + 2), fill=FAILED, outline="", tags=tags)
        elif m.mark == "missed":  # dotted
            for y in range(y0, y1, 3):
                self.create_rectangle(rx + rw // 2 - 1, y, rx + rw // 2 + 1, y + 1, fill=MISSED, outline="",
                                      tags=tags)
        else:  # waiting: hollow
            self.create_rectangle(rx, y0, rx + rw - 1, y1 - 1, outline=EDGE, tags=tags)

    # ---------------------------------------------------------------- the one timer
    def _sync_animation(self) -> None:
        """The timer runs while a bar of the column is at work, and only then."""
        if self.shown and self.layout.kind == "column" and self.model.working():
            if self._anim_job is None:
                self._anim_job = self.after(ANIM_MS, self._animate)
        elif self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    @property
    def animating(self) -> bool:
        return self._anim_job is not None

    def _animate(self) -> None:
        self._anim_job = None
        self._phase += 1
        self.delete("stripe")
        if self.layout.kind == "column":
            for index, seq in enumerate(self.model.order):
                screen = self.model.screens[seq]
                for stage in ROWS:
                    if screen.stages[stage] == "working":
                        self._draw_stripe(*self._cell_parts(index)[stage], f"s{seq}")
        self._sync_animation()

    def destroy(self) -> None:
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except tk.TclError:
                pass
            self._anim_job = None
        super().destroy()

    # ---------------------------------------------------------------- the pointer
    def at(self, x: int, y: int) -> tuple[int | None, str | None]:
        """The screen under the point (x, y) of this canvas and what of it: "thumb", a stage ("read", "translate"),
        "cell" (elsewhere in its cell), "mark" (on the rail); (None, None) elsewhere."""
        if self.layout.kind == "rail":
            for m in self._marks:
                if m.y0 - 1 <= y <= m.y1:
                    i = min(len(m.seqs) - 1, max(0, int((y - m.y0) * len(m.seqs) / max(1, m.y1 - m.y0))))
                    return m.seqs[i], "mark"
            return None, None
        if self.layout.kind != "column":
            return None, None
        cy = int(self.canvasy(y))
        index = cy // CELL_H
        if cy < 0 or not 0 <= index < len(self.model.order):
            return None, None
        seq = self.model.order[index]
        parts = self._cell_parts(index)
        for stage in ROWS:
            x0, y0, x1, y1 = parts[stage]
            if x0 - LETTER_W <= x <= x1 + 1 and y0 - 2 <= cy <= y1 + 2:
                return seq, stage
        x0, y0, x1, y1 = parts["thumb"]
        if x0 <= x <= x1 and y0 <= cy <= y1:
            return seq, "thumb"
        return seq, "cell"

    def text_at(self, x: int, y: int) -> str:
        seq, part = self.at(x, y)
        summary = "\n".join(summary_lines(self.model, self.now()))
        if seq is None or part == "cell":
            return summary
        if part == "thumb":
            return screen_tip(self.model, seq)
        if part == "mark":
            mark = next((m for m in self._marks if seq in m.seqs), None)
            line = run_tip(mark.seqs[0], mark.seqs[-1], mark.mark) if mark is not None else ""
            return line + ("\n" + screen_tip(self.model, seq) if mark is not None and len(mark.seqs) == 1 else "") \
                + "\n\n" + summary
        return bar_line(part, self.model.screens[seq].stages[part])

    def _clicked(self, event: tk.Event) -> None:
        seq, _part = self.at(event.x, event.y)
        if seq is not None:
            self.on_pick(seq)

    def _wheel(self, event: tk.Event) -> None:
        if self.layout.kind == "column":
            self.yview_scroll(-1 if event.delta > 0 else 1, "units")
