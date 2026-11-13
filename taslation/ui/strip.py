"""The page strip at the bottom of the window during a whole-book run: one thumbnail per page as the reader turns it,
left to right in the order the run first saw them, each with three bars under it - reading the text, erasing the
Japanese, the translation - that say how far that page is, and a line on how much memory the run's page pictures take.

* `StripModel`: what the strip shows, no Tk: the pages by their run number (``seq``), the state of each stage. The
  run's ``page_stage`` events may come in any order; the latest one for a stage wins.
* `PageStrip`: the strip itself, a canvas that scrolls sideways. A bar says its state three ways - its letter, its
  colour and its pattern (empty, a moving stripe, filled, crossed, hatched) - never by colour alone. While any bar is
  at work one `after` timer moves the stripes of all of them, and none runs while nothing works.
* `StripMixin`: the window's side (a part of `app.App`): the events, and the click on a thumbnail (`_pick_page`): the
  status line says how to read that page - open it in the viewer, where TASlation shows its translation over it - and
  nothing else happens: no page of the run's memory goes on the page area, and no key or click goes to the viewer.
  `StripModel.unfinished` gives the pages the window's question at closing is about (`app.App._close_allowed`, in
  TASlation's own `WarningBox`), and `release_run_images` lets go of the last run's pictures (the window closes,
  another book).

Reading is on the viewer only. The page images a run holds in memory (`pageimages.PageImages`) are shown only as the
run's progress, the page the run is working on: while it reads, the page the viewer shows as the run takes it (the
batch's ``batch_page``, with the regions read outlined); while it translates, the page being translated. Outside that,
the page area shows what it showed before whole-book runs were made: the viewer's current frame, the cached
translation laid over it while its fingerprint matches (`LiveViewMixin._picture`). No page can be paged through in
TASlation from memory, during the run or after it: TASlation must not become a way to read a book without the viewer,
which matters where what is paid depends on what is viewed. The strip says how far each page is, and nothing more.

A page that went by before the run could take it (``page_stage`` read "missed") has a placeholder in its place: a
dashed frame with its number and a question mark, its reading bar dotted; when the reader turns back to it, its
thumbnail comes as for any page, and when the run finds it took that page all the same under another number (read
"merged"), the placeholder goes.

While the run translates, the page area follows it (``translation_page``, `translation_view`): the page being
translated (`RunPage`), its lines lettered as the model answers them and those still to come outlined, the strip's
outline on its thumbnail and the strip scrolled to it as the run moves on. An open region editor or a reading order
being set holds the page area on the viewer's page meanwhile (`follow_held`: the run's page is not shown then, and the
strip outlines none). A page whose picture is no longer held shows nothing of the run: the page area shows what it
showed before, and the band and the strip go on. The run over (done, stopped, failed), the run's page goes from the
page area at once, whatever held it, and the live view takes over again (`end_follow`).

The thumbnails live in memory only, like every page picture of the window; nothing of them is written anywhere. They
are 96 px high at most as the run sends them, and smaller on the strip: a sign of progress, not a page to read."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageTk

from ..i18n import _
from .constants import in_a_run
from .progress import FILL_COLOUR
from .tooltip import Tooltip

STAGES = ("read", "erase", "translate")
STATES = ("waiting", "working", "done", "failed", "skipped", "missed")
MERGED = "merged"  # read "merged": a page that went by was taken all the same, under another seq: its placeholder goes
UNFINISHED = ("waiting", "working")  # a page with a stage in one of these is not finished: its picture is still needed

THUMB_BOX = (58, 80)  # a thumbnail is fitted into this many pixels (the run sends them up to 96 px tall) ...
CELL_W = 66  # ... in a cell this wide on the strip: a page (about 0.7 as wide as tall) fills its height
# the viewer's even ground around the page is cut off a thumbnail (`trim_ground`): a line of it belongs to the page
# once more than TRIM_SHARE of its pixels differ from the corners' colour by more than TRIM_LEVELS grey levels (a
# page number, a viewer's small marks do not make a line of the page)
TRIM_LEVELS, TRIM_SHARE = 16, 0.04
PAPER = 224  # grey level: corners this light are the page's paper (it fills the frame), not a viewer's ground
PAD = 4
BAR_H, BAR_GAP = 11, 2  # a stage bar's height, and the room between two
LETTER_W = 14  # the stage letter, left of its bar (a Japanese or Chinese one too)
STRIP_H = PAD + THUMB_BOX[1] + 4 + 3 * BAR_H + 2 * BAR_GAP + PAD
ANIM_MS = 120  # the working stripes move this often (one timer for the whole strip)
STRIPE_W = 8
STRIPE_STEP = 3  # pixels a stripe moves per tick

# Colours on the strip's dark ground, from the Okabe-Ito set (told apart with the common colour blindnesses), and
# every state has its own pattern besides.
GROUND = "#202020"  # as the page area around the page
EDGE = "#8a8a8a"  # a bar's outline
TEXT = "#eeeeee"
DONE = "#56b4e9"  # sky blue, filled
WORKING = "#e69f00"  # orange, a moving stripe
FAILED = "#d55e00"  # vermillion, filled and crossed
SKIPPED = "#6e6e6e"  # grey, hatched
CHOSEN = "#ffd400"  # the outline of the page being translated, on show (as a chosen region's handles)
MISSED = "#cc79a7"  # reddish purple, dotted: a page that went by before it could be taken


def stage_letter(stage: str) -> str:
    """A stage's letter on the strip, in the window's language."""
    return {"read": _("R"), "erase": _("E"), "translate": _("T")}[stage]


def stage_name(stage: str) -> str:
    return {"read": _("Reading the text"), "erase": _("Erasing the Japanese"), "translate": _("Translation")}[stage]


def state_word(state: str) -> str:
    return {"waiting": _("not started yet"), "working": _("under way"), "done": _("done"),
            "failed": _("did not work"), "skipped": _("not needed"),
            "missed": _("went by before it could be taken: turn back to it")}[state]


def bar_tip(stage: str, state: str) -> str:
    """What a bar's tooltip says: the stage and its state; the translation also says when it comes."""
    line = _("{stage}: {state}").format(stage=stage_name(stage), state=state_word(state))
    if stage == "translate" and state == "waiting":
        line += "\n" + _("The whole book is translated together after Finished reading, so that each page is translated with the story around it.")
    return line


def page_tip(seq: int, missed: bool = False) -> str:
    """What a thumbnail's tooltip says, and its click in the status line (`StripMixin._pick_page`): a page is read in
    the viewer, never from the strip."""
    if missed:
        return _("Page {n} went by before it could be taken. Turn back to it in the viewer and it is read like any other.").format(n=seq)
    return _("Page {n} of this run. To read it, open it in the viewer: TASlation shows the translation over it.").format(n=seq)


# ------------------------------------------------------------------ the state
@dataclass
class PageCell:
    """A page on the strip: its run number, its fingerprint, its thumbnail (once one came) and each stage's state."""

    seq: int
    fingerprint: str = ""
    thumb: Image.Image | None = None
    stages: dict[str, str] = field(default_factory=lambda: {s: "waiting" for s in STAGES})

    @property
    def unfinished(self) -> bool:
        """A stage is still to come (a page that went by is not: there is no picture of it to lose)."""
        return not self.missed and any(state in UNFINISHED for state in self.stages.values())

    @property
    def working(self) -> bool:
        return any(state == "working" for state in self.stages.values())

    @property
    def missed(self) -> bool:
        """The page went by before the run could take it (and has not been taken since)."""
        return self.stages["read"] == "missed"


def trim_ground(image: Image.Image) -> Image.Image:
    """*image* - a frame of the viewer - without the even ground around the page: the rows and columns at its edges
    that are of the colour its four corners share (see TRIM_LEVELS). A frame whose corners differ (the viewer's bars
    reach them) or are as light as paper (the page fills the frame; on a white viewer the page's edge cannot be
    told) is left whole, and so is one that would keep less than a tenth of either side."""
    grey = np.asarray(image.convert("L"), dtype=np.int16)
    if grey.shape[0] < 4 or grey.shape[1] < 4:
        return image
    corners = np.array([grey[0, 0], grey[0, -1], grey[-1, 0], grey[-1, -1]])
    if int(corners.max()) - int(corners.min()) > TRIM_LEVELS or int(np.median(corners)) >= PAPER:
        return image
    differs = np.abs(grey - int(np.median(corners))) > TRIM_LEVELS
    rows = np.flatnonzero(differs.mean(axis=1) > TRIM_SHARE)
    cols = np.flatnonzero(differs.mean(axis=0) > TRIM_SHARE)
    if not len(rows) or not len(cols):
        return image
    box = (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)
    if box[2] - box[0] < image.width / 10 or box[3] - box[1] < image.height / 10:
        return image
    return image.crop(box) if box != (0, 0, image.width, image.height) else image


def fit_thumb(image: Image.Image) -> Image.Image:
    """*image* without the viewer's ground around the page (`trim_ground`), made to fit `THUMB_BOX` (a copy; the
    run's own thumbnail is not kept)."""
    thumb = trim_ground(image)
    thumb = thumb.convert("RGB") if thumb.mode not in ("RGB", "L") else thumb.copy()
    thumb.thumbnail(THUMB_BOX, Image.BILINEAR)
    return thumb


class StripModel:
    """The run's pages in the order of first sight, and their stages."""

    def __init__(self) -> None:
        self.pages: dict[int, PageCell] = {}
        self.order: list[int] = []
        self.view: tuple[float, float] = (0.0, 1.0)  # the part of the strip in view (`PageStrip`)

    def __len__(self) -> int:
        return len(self.order)

    def clear(self) -> None:
        self.pages.clear()
        self.order.clear()
        self.view = (0.0, 1.0)

    def update(self, seq: Any, fingerprint: Any = "", thumb: Any = None, stage: Any = None, state: Any = None) -> bool:
        """One ``page_stage`` event; True when it brought a page not seen before. An unknown stage or state changes
        nothing but the page's being there; a thumbnail is taken whenever the page has none yet."""
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return False
        if stage == "read" and state == MERGED:  # (its placeholder goes: the page is in the strip as another)
            if self.pages.pop(seq, None) is not None:
                self.order.remove(seq)
            return False
        cell = self.pages.get(seq)
        new = cell is None
        if cell is None:
            cell = self.pages[seq] = PageCell(seq)
            self.order.append(seq)
        if fingerprint and not cell.fingerprint:
            cell.fingerprint = str(fingerprint)
        if cell.thumb is None and isinstance(thumb, Image.Image):
            cell.thumb = fit_thumb(thumb)
        if stage in STAGES and state in STATES:
            cell.stages[stage] = state
        return new

    def working(self) -> bool:
        return any(cell.working for cell in self.pages.values())

    def unfinished(self) -> list[int]:
        """The pages a stage of which has not ended yet, in the strip's order."""
        return [seq for seq in self.order if self.pages[seq].unfinished]

    def memory_bytes(self) -> int:
        """What the thumbnails take, about (the pixels)."""
        return sum(len(c.thumb.getbands()) * c.thumb.width * c.thumb.height for c in self.pages.values()
                   if c.thumb is not None)


# ------------------------------------------------------------------ the strip
class CanvasTip(Tooltip):
    """A tooltip whose text depends on where the pointer is over the canvas (`text_at`); moving onto another part of
    the strip starts it again."""

    def __init__(self, canvas: tk.Canvas, text_at: Callable[[int, int], str]):
        self.text_at = text_at
        self._at: str = ""
        super().__init__(canvas, "")
        canvas.bind("<Motion>", self._moved, add="+")

    def current(self) -> str:
        try:
            x = self.widget.winfo_pointerx() - self.widget.winfo_rootx()
            y = self.widget.winfo_pointery() - self.widget.winfo_rooty()
        except tk.TclError:
            return ""
        return self.text_at(x, y)

    def _moved(self, event: tk.Event) -> None:
        text = self.text_at(event.x, event.y)
        if text != self._at:
            self._at = text
            self._leave()
            self._enter()


class PageStrip(ttk.Frame):
    """The strip: the canvas of thumbnails, its scroll bar and the memory line beside it. *on_pick*: a thumbnail was
    clicked (its run number)."""

    def __init__(self, master: tk.Misc, model: StripModel, on_pick: Callable[[int], None]):
        super().__init__(master)
        self.model, self.on_pick = model, on_pick
        self.canvas = tk.Canvas(self, height=STRIP_H, bg=GROUND, highlightthickness=0, takefocus=0)
        self.canvas.pack(side="top", fill="x")
        row = ttk.Frame(self)
        row.pack(side="top", fill="x")
        self.memory_var = tk.StringVar(value="")
        self.memory_label = ttk.Label(row, textvariable=self.memory_var, anchor="e", padding=(8, 0))
        self.memory_label.pack(side="right")
        self.scroll = ttk.Scrollbar(row, orient="horizontal", command=self.canvas.xview)
        self.scroll.pack(side="left", fill="x", expand=True)
        self.canvas.configure(xscrollcommand=self._scrolled)
        self._photos: dict[int, ImageTk.PhotoImage] = {}
        self._phase = 0
        self._anim_job: str | None = None
        self.chosen: int | None = None
        self._font = tkfont.Font(self, family=tkfont.nametofont("TkDefaultFont").cget("family"), size=8)
        self.canvas.bind("<ButtonRelease-1>", self._clicked)
        for sequence in ("<MouseWheel>", "<Shift-MouseWheel>"):
            self.canvas.bind(sequence, self._wheel)
        self.tip = CanvasTip(self.canvas, self.text_at)
        self.redraw()

    def _scrolled(self, first: str, last: str) -> None:
        self.scroll.set(first, last)
        self.model.view = (float(first), float(last))  # where the strip was scrolled to, for a strip made anew

    # ---------------------------------------------------------------- drawing
    def redraw(self) -> None:
        """Every page again (a new strip: after a language switch, or a new run), scrolled where it was."""
        self.canvas.delete("all")
        self._photos = {k: v for k, v in self._photos.items() if k in self.model.pages}
        for index, seq in enumerate(self.model.order):
            self._draw_cell(index, seq)
        self._scroll_region()
        first, last = self.model.view
        self.canvas.xview_moveto(1.0 if last >= 0.999 else first)  # (at the end: at the end again)
        self._sync_animation()

    def page_changed(self, seq: int, new: bool) -> None:
        """A page's event came: its cell drawn again (a new one at the end, the view following it there when it was
        at the end already)."""
        at_end = self.canvas.xview()[1] >= 0.999
        try:
            index = self.model.order.index(seq)
        except ValueError:
            return
        self.canvas.delete(f"p{seq}")
        self._draw_cell(index, seq)
        if new:
            self._scroll_region()
            if at_end:
                self.canvas.xview_moveto(1.0)
        self._sync_animation()

    def show_page(self, seq: int) -> None:
        """The strip scrolled so that the page *seq* is in view (not moved when it is)."""
        try:
            index = self.model.order.index(seq)
        except ValueError:
            return
        total = max(1, len(self.model.order) * CELL_W)
        first, last = self.canvas.xview()
        left, right = index * CELL_W / total, (index + 1) * CELL_W / total
        if left < first or right > last:
            self.canvas.xview_moveto(max(0.0, left - (last - first) / 2))

    def _scroll_region(self) -> None:
        self.canvas.configure(scrollregion=(0, 0, max(1, len(self.model.order) * CELL_W), STRIP_H))

    def _photo(self, cell: PageCell) -> ImageTk.PhotoImage | None:
        photo = self._photos.get(cell.seq)
        if photo is None and cell.thumb is not None:
            photo = self._photos[cell.seq] = ImageTk.PhotoImage(cell.thumb, master=self.canvas)
        return photo

    def _bar_box(self, index: int, row: int) -> tuple[int, int, int, int]:
        x0 = index * CELL_W + PAD + LETTER_W
        y0 = PAD + THUMB_BOX[1] + 4 + row * (BAR_H + BAR_GAP)
        return x0, y0, index * CELL_W + CELL_W - PAD, y0 + BAR_H

    def _draw_cell(self, index: int, seq: int) -> None:
        cell = self.model.pages[seq]
        tag, c = f"p{seq}", self.canvas
        left = index * CELL_W
        mid = left + CELL_W // 2
        photo = self._photo(cell)
        top, bottom = PAD, PAD + THUMB_BOX[1]
        if photo is not None:
            c.create_image(mid, PAD + THUMB_BOX[1] // 2, image=photo, tags=(tag,))
            top = PAD + (THUMB_BOX[1] - photo.height()) // 2
            bottom = top + photo.height()
            half = photo.width() // 2
        elif cell.missed:  # went by: a dashed frame, its number and a question mark
            half = THUMB_BOX[0] // 2
            c.create_rectangle(mid - half, top, mid + half, bottom, outline=MISSED, dash=(3, 3), width=2, tags=(tag,))
            c.create_text(mid, (top + bottom) // 2, text=f"{seq}\n?", fill=TEXT, font=self._font, justify="center",
                          tags=(tag,))
        else:  # no picture came (yet): a frame and the page's number
            half = THUMB_BOX[0] // 2
            c.create_rectangle(mid - half, top, mid + half, bottom, outline=EDGE, tags=(tag,))
            c.create_text(mid, (top + bottom) // 2, text=str(seq), fill=TEXT, font=self._font, tags=(tag,))
        if self.chosen == seq:
            c.create_rectangle(mid - half - 2, top - 2, mid + half + 1, bottom + 1, outline=CHOSEN, width=2,
                               tags=(tag,))
        for row, stage in enumerate(STAGES):
            self._draw_bar(index, row, stage, cell.stages[stage], tag)

    def _draw_bar(self, index: int, row: int, stage: str, state: str, tag: str) -> None:
        c = self.canvas
        x0, y0, x1, y1 = self._bar_box(index, row)
        c.create_text(x0 - LETTER_W // 2 - 1, (y0 + y1) // 2, text=stage_letter(stage), fill=TEXT, font=self._font,
                      tags=(tag,))
        if state == "done":
            c.create_rectangle(x0, y0, x1, y1, fill=DONE, outline=DONE, tags=(tag,))
        elif state == "failed":
            c.create_rectangle(x0, y0, x1, y1, fill=FAILED, outline=FAILED, tags=(tag,))
            mid = (x0 + x1) // 2
            for a, b in ((-3, 3), (3, -3)):  # a cross in the middle
                c.create_line(mid + a, y0 + 1, mid + b, y1 - 1, fill=TEXT, width=2, tags=(tag,))
        elif state == "missed":
            c.create_rectangle(x0, y0, x1, y1, outline=MISSED, tags=(tag,))
            for x in range(x0 + 3, x1 - 1, 5):  # dotted
                c.create_rectangle(x, (y0 + y1) // 2 - 1, x + 1, (y0 + y1) // 2 + 1, fill=MISSED, outline=MISSED,
                                   tags=(tag,))
        elif state == "skipped":
            c.create_rectangle(x0, y0, x1, y1, outline=SKIPPED, tags=(tag,))
            for x in range(x0 + 2, x1, 5):  # hatched
                c.create_line(x, y1 - 1, min(x1 - 1, x + BAR_H - 2), y0 + 1, fill=SKIPPED, tags=(tag,))
        else:  # waiting (empty) or working (its stripe comes with the timer)
            c.create_rectangle(x0, y0, x1, y1, outline=EDGE, tags=(tag, f"bar{state}"))
            if state == "working":
                self._draw_stripe(x0, y0, x1, y1, tag)

    def _draw_stripe(self, x0: int, y0: int, x1: int, y1: int, tag: str) -> None:
        span = max(1, x1 - x0 - STRIPE_W)
        travel = self._phase * STRIPE_STEP % (2 * span)
        offset = travel if travel <= span else 2 * span - travel  # to and fro
        self.canvas.create_rectangle(x0 + 1 + offset, y0 + 1, x0 + offset + STRIPE_W, y1, fill=WORKING, outline="",
                                     tags=(tag, "stripe"))

    # ---------------------------------------------------------------- the one timer
    def _sync_animation(self) -> None:
        """The timer runs while a bar is at work, and only then."""
        if self.model.working():
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
        c = self.canvas
        c.delete("stripe")
        for index, seq in enumerate(self.model.order):
            cell = self.model.pages[seq]
            for row, stage in enumerate(STAGES):
                if cell.stages[stage] == "working":
                    self._draw_stripe(*self._bar_box(index, row), f"p{seq}")
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
        """The page (its run number) and the stage under the canvas point (x, y) (the stage None: its thumbnail)."""
        cx, cy = int(self.canvas.canvasx(x)), int(self.canvas.canvasy(y))
        index = cx // CELL_W
        if cx < 0 or not 0 <= index < len(self.model.order) or not 0 <= cy < STRIP_H:
            return None, None
        seq = self.model.order[index]
        for row, stage in enumerate(STAGES):
            _x0, y0, _x1, y1 = self._bar_box(index, row)
            if y0 - 1 <= cy <= y1 + 1:
                return seq, stage
        return seq, None

    def text_at(self, x: int, y: int) -> str:
        seq, stage = self.at(x, y)
        if seq is None:
            return ""
        if stage is None:
            return page_tip(seq, self.model.pages[seq].missed)
        return bar_tip(stage, self.model.pages[seq].stages[stage])

    def _clicked(self, event: tk.Event) -> None:
        seq, _stage = self.at(event.x, event.y)
        if seq is not None:
            self.on_pick(seq)

    def _wheel(self, event: tk.Event) -> None:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    def choose(self, seq: int | None) -> None:
        """The page being translated, outlined while the page area shows it (None: none)."""
        before, self.chosen = self.chosen, seq
        for one in (before, seq):
            if one is not None and one in self.model.pages:
                self.page_changed(one, False)

    def set_memory(self, used_mb: float, cap_mb: float) -> None:
        self.memory_var.set(_("Page pictures in memory: {used} of {cap} MB").format(
            used=int(round(used_mb)), cap=int(round(cap_mb))))


# ------------------------------------------------------------------ the window's side
# (functions of the window, so that the window's other parts and their tests' stand-ins call them whether or not
# the stand-in has a strip)
def place_strip(window: Any) -> None:
    """The strip under the page, over the status line, while it is to show (never in the reading window)."""
    strip = getattr(window, "page_strip", None)
    if strip is None:
        return
    try:
        if getattr(window, "_strip_shown", False) and not getattr(window, "reading", False):
            if not strip.winfo_manager():
                strip.pack(fill="x", before=window.status_bar)
        elif strip.winfo_manager():
            strip.pack_forget()
    except tk.TclError:
        pass


@dataclass
class RunPage:
    """The page the run is translating, as the window was last told it (``translation_page``): *frame* the page as it
    was captured, *image* with what is lettered so far, *waiting* the boxes of its lines not answered yet."""

    seq: int
    frame: Image.Image
    image: Image.Image
    waiting: list[tuple[int, int, int, int]] = field(default_factory=list)

    def outlines(self) -> list[tuple[tuple[int, int, int, int], str, bool]]:
        """The lines not answered yet, outlined as a page filling in outlines the regions read (solid)."""
        return [(box, FILL_COLOUR, False) for box in self.waiting]


def follow_held(window: Any) -> bool:
    """Whether the page area keeps the viewer's page it shows rather than follow the run's translation: a region editor
    open on that page, a reading order being set on it. Neither can keep anything of the run on show: while one holds,
    the run's page is not shown at all (`run_page_on_show`), and the run's end lets go of the run's page whatever
    holds (`end_follow`)."""
    if getattr(window, "_ordering", None) is not None:
        return True
    editor = getattr(window, "_editor", None)
    try:
        return editor is not None and bool(editor.winfo_exists())
    except tk.TclError:
        return False


def run_page_on_show(window: Any) -> RunPage | None:
    """The page being translated, when the page area shows it (`follow_held`: not now). The only page of the run's
    memory the window ever shows (reading is on the viewer: see the module's docstring), and only while the run
    translates: `_on_translation_page` takes none outside a run, and `end_follow` drops it as the run ends."""
    view = getattr(window, "_run_view", None)
    return None if view is None or follow_held(window) else view


def end_follow(window: Any, redisplay: bool = True) -> bool:
    """The run's translation is over (the run ended - done, stopped, failed -, another starts, the window closes): the
    run's page leaves the page area, which shows the viewer's page as it does without a run; False when it did not
    follow one."""
    if getattr(window, "_run_view", None) is None:
        return False
    window._run_view = None
    strip = getattr(window, "page_strip", None)
    if strip is not None:
        strip.choose(None)
    if redisplay:
        window._redisplay()
    return True


def new_run(window: Any) -> None:
    """A run starts: the strip starts empty (it shows with the run's first page)."""
    model = getattr(window, "_strip_model", None)
    if model is None:
        return
    end_follow(window, redisplay=False)
    model.clear()
    window._strip_memory = None
    window._strip_shown = False
    window.page_strip.memory_var.set("")
    window.page_strip.redraw()
    place_strip(window)


def hide_strip(window: Any) -> None:
    """The scan band closed: the strip goes with it (its pages are kept for the question at closing)."""
    if getattr(window, "_strip_model", None) is None:
        return
    window._strip_shown = False
    place_strip(window)


def close_warning(window: Any) -> str | None:
    """What closing *window* would lose of a whole-book run, as the question at closing says it
    (`app.App._close_allowed`); None when nothing would be lost. In this order: a run reading the pages - what it read
    lives only in memory until it is translated (Finished reading); the readings a stopped run left (`Readings`,
    held for the next run: the band's Translate the pages read takes them); the pages of the strip whose pictures are
    still needed (`StripModel.unfinished`; the translations done so far are saved)."""
    scan = getattr(window, "_scan", None)
    running = getattr(window, "batch", None) is not None or getattr(window, "_batching", False)
    if running and scan is not None and scan.context and scan.scanning and scan.pages + scan.queued > 0:
        return _("The whole-book run has read {n} page(s), and none is translated yet. What it read is kept only while TASlation is open, so closing now loses it, and those pages must be turned again.\n\nPress Finished reading to translate them first. Close anyway?").format(
            n=scan.pages + scan.queued)
    held = getattr(window, "_readings", None)
    if held is not None and held[1].units:
        return _("{n} page(s) read in the whole-book run are not translated yet. TASlation keeps what it read only while it is open, so closing loses it, and those pages must be turned again. To translate them, keep TASlation open and press Translate the pages read on the band, or run Read whole book... again.\n\nClose anyway?").format(
            n=len(held[1].units))
    model = getattr(window, "_strip_model", None)
    left = model.unfinished() if model is not None else []
    if left:
        return _("{n} page(s) of the whole-book run are not finished yet. Their pictures are kept only while TASlation is open, so they are lost when it closes. The translations done so far are saved.\n\nClose anyway?").format(n=len(left))
    return None


def release_run_images(window: Any) -> None:
    """Let go of the last whole-book run's page pictures the pipeline holds (`Pipeline.release_page_images`): the
    window closes. Until then they serve the render alone - the erase done ahead, for a page the viewer shows
    (`Pipeline.erased_ahead`) -, never a picture of their own on the page area. Another book lets go of them in the
    worker (`jobs._ensure_cache`). A run still going keeps its own until it ends."""
    end_follow(window, redisplay=False)
    release = getattr(getattr(window, "pipeline", None), "release_page_images", None)
    if release is not None:
        release()


class StripMixin:
    """The page strip in the window. A part of `app.App` (no `__init__`; `_build_page_strip` makes the strip's
    widget, again after a language switch, keeping the pages)."""

    def _build_page_strip(self) -> None:
        if getattr(self, "_strip_model", None) is None:
            self._strip_model = StripModel()
            self._strip_shown = False
            self._strip_memory: tuple[float, float] | None = None
            self._run_view: RunPage | None = None  # the page the run is translating (`translation_page`)
        self.page_strip = PageStrip(self, self._strip_model, self._pick_page)
        if self._strip_memory is not None:
            self.page_strip.set_memory(*self._strip_memory)
        if run_page_on_show(self) is not None:
            self.page_strip.choose(self._run_view.seq)  # type: ignore[union-attr]
        place_strip(self)

    def _on_translation_page(self, data: dict[str, Any]) -> None:
        """The run's translation has lettered more of a page, or come to another (`translation_view`): the page area
        shows it unless the reader holds the viewer's page on show (`follow_held`), the strip outlining its thumbnail
        and scrolled to it when the run comes to it. Only while a run is on: a picture told after its end shows
        nothing. No picture: the page's is no longer held, and the page area shows what it showed without the run's.
        Only the page on show is kept, as the run last told it: no other page of the run is held by the window."""
        if not in_a_run(self):
            return
        try:
            seq = int(data.get("seq"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        image, frame = data.get("image"), data.get("frame")
        before = self._run_view
        if image is None or frame is None:
            if before is not None:
                self._run_view = None
                self.page_strip.choose(None)
                self._fill_dirty = True
            return
        self._run_view = RunPage(seq, frame, image, [tuple(b) for b in data.get("waiting") or ()])
        if follow_held(self):  # (the viewer's page on show: no page of the run is outlined as on show)
            if self.page_strip.chosen is not None:
                self.page_strip.choose(None)
            return
        if self.page_strip.chosen != seq:
            self.page_strip.choose(seq)
        if before is None or before.seq != seq:
            self.page_strip.show_page(seq)
        self._fill_dirty = True

    def _on_page_missed(self, data: dict[str, Any]) -> None:
        """A page went by before the run could take it (``page_missed``): its placeholder brought into view (the band
        says what to do: ``batch.page_missed``)."""
        try:
            seq = int(data.get("seq"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if seq in self._strip_model.pages:
            self.page_strip.show_page(seq)

    def _on_page_stage(self, data: dict[str, Any]) -> None:
        model = self._strip_model
        new = model.update(data.get("seq"), data.get("fingerprint", ""), data.get("thumb"), data.get("stage"),
                           data.get("state"))
        try:
            seq = int(data.get("seq"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if seq not in model.pages:  # a placeholder merged into the page it was: the cells after it move up
            self.page_strip.redraw()
            return
        if not self._strip_shown:
            self._strip_shown = True
            place_strip(self)
        self.page_strip.page_changed(seq, new)

    def _on_batch_memory(self, data: dict[str, Any]) -> None:
        try:
            used, cap = float(data.get("used_mb", 0)), float(data.get("cap_mb", 0))
        except (TypeError, ValueError):
            return
        self._strip_memory = (used, cap)
        self.page_strip.set_memory(used, cap)

    def _pick_page(self, seq: int) -> None:
        """A click on a thumbnail: the status line says how to read that page - in the viewer, where TASlation shows
        its translation over it (a page that went by: turn back to it there). That is all: the page area keeps what it
        shows (the viewer's page, or the run's progress), during the run and after it, for no page of the run's memory
        is ever shown to be read (see the module's docstring); nothing goes to the viewer."""
        cell = self._strip_model.pages.get(seq)
        if cell is not None and cell.missed:
            self.say("Page {n} went by before it could be taken. Turn back to it in the viewer and it is read like any other.", n=seq)
            return
        self.say("Page {n} of this run. To read it, open it in the viewer: TASlation shows the translation over it.", n=seq)
