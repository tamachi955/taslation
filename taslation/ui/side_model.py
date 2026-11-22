"""What the indicator beside the page knows and where it goes, no Tk (`ui.side` puts it on the window, `ui.side_view`
draws it): the screens turned past in normal reading (`SideModel`), each with its two stages - reading the text and the
translation - from the engine's ``page_stage`` events, the screen on show (``page_on_show``), the backlog's totals
(``backlog``) and their pace (`BacklogPace`); the mark each screen gets (`Screen.mark`), the narrow rail's marks
(`rail_marks`), the hover text (`summary_lines`), and the place of it all beside the drawn picture (`side_layout`,
`room_kept`).

Where it goes. The indicator sits in the page's exit-side margin, the side a page is turned towards: left of a book
read right to left (`Pipeline.rtl`), right of one read left to right. Where that margin has room for it
(`COLUMN_NEEDS`, 141 px: the column of `COLUMN_W` 125 px with 10 px to the page and 6 px to the edge) it is a column of
thumbnails (`THUMB_BOX`, the viewer's ground trimmed off: `fit_thumb`), each with its stage bars; else a rail `RAIL_W`
px wide (`RAIL_W_FULL` on the full screen) beside the page, with the updated diamonds and the notch of the screen on
show in a column `MARKS_W` px wide outside it. Where the exit margin is under `RAIL_ROOM` (24 px) the picture is drawn
`RESERVE` px clear of that side (`room_kept`: 16 px, as the rail and its marks need), so that nothing of the indicator
ever covers the page. What decides it is the canvas's size, the part of the frame drawn and the setting
(``side_indicator``): a page turned never changes it, so the page never changes size while one reads (it does on a
resize, on the full screen in or out, and a change of the setting).

The column gives way to the rail under 141 px of exit margin. The thumbnail needs its 58 px (`THUMB_BOX`; a
spread's comes out 58 x 41 or so), and a bar narrower than about 34 px no longer shows its working stripe moving
(8 px wide, `side_view.STRIPE_W`) nor a cross on a failed stage; with the stage letter, the notch that points at the
page from the screen on show, the gaps and the pads that is 125 px, and the 16 px round it keep the column off the page
and off the window's edge."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from .. import fingerprint as fp
from ..i18n import _

MERGED = "merged"  # read "merged": a screen that went by was taken all the same, under another seq: its own goes
THUMB_BOX = (58, 80)  # a thumbnail is fitted into this many pixels (the engine sends them up to 96 px tall)
# the viewer's even ground around the page is cut off a thumbnail (`trim_ground`): a line of it belongs to the page
# once more than TRIM_SHARE of its pixels differ from the corners' colour by more than TRIM_LEVELS grey levels (a
# page number, a viewer's small marks do not make a line of the page)
TRIM_LEVELS, TRIM_SHARE = 16, 0.04
PAPER = 224  # grey level: corners this light are the page's paper (it fills the frame), not a viewer's ground


def stage_letter(stage: str) -> str:
    """A stage's letter beside its bar, in the window's language."""
    return {"read": _("R"), "erase": _("E"), "translate": _("T")}[stage]


def stage_name(stage: str) -> str:
    return {"read": _("Reading the text"), "erase": _("Erasing the Japanese"), "translate": _("Translation")}[stage]


def state_word(state: str) -> str:
    return {"waiting": _("not started yet"), "working": _("under way"), "done": _("done"),
            "failed": _("did not work"), "skipped": _("not needed"),
            "missed": _("went by before it could be taken: turn back to it")}[state]


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
    engine's own thumbnail is not kept)."""
    thumb = trim_ground(image)
    thumb = thumb.convert("RGB") if thumb.mode not in ("RGB", "L") else thumb.copy()
    thumb.thumbnail(THUMB_BOX, Image.BILINEAR)
    return thumb


SIDE_STAGES = ("read", "translate")  # normal reading has no erase of its own: a page is erased as it is shown
STATES = ("waiting", "working", "done", "failed", "skipped", "missed")
MARKS = ("done", "working", "waiting", "failed", "missed")  # a screen's mark, by its stages (`Screen.mark`)
# ``side_indicator``: the column where it fits (the rail elsewhere), the rail only, none
SETTINGS = ("column", "rail", "off")

# ------------------------------------------------------------------ the column's measures (canvas pixels)
PAD = 4
BAR_GAP_X = 6  # thumbnail to stage letter
LETTER_W = 14
BAR_W = 34
BAR_H, BAR_ROW = 11, 15  # a bar's height, and from one bar's top to the next
NOTCH_W = 5  # the notch of the screen on show, on the cell's side towards the page
# a cell of the left column, from its left: the thumbnail, the stage letters and bars, the notch (mirrored on the right)
COLUMN_W = PAD + THUMB_BOX[0] + BAR_GAP_X + LETTER_W + BAR_W + NOTCH_W + PAD  # 125
CELL_H = PAD + THUMB_BOX[1] + PAD + 6  # a screen's cell, top to bottom (the next one starts there)
COLUMN_GAP = 10  # between the column and the page ...
COLUMN_OUT = 6  # ... and between it and the canvas's edge
COLUMN_NEEDS = COLUMN_W + COLUMN_GAP + COLUMN_OUT  # an exit margin this wide holds the column
COLUMN_TOP = 8  # the column starts this far down the canvas
SLOT_ROOM = 44  # on the full screen the column stops this far above the bottom: the status slot's place

# ------------------------------------------------------------------ the rail's measures
RAIL_W, RAIL_W_FULL = 6, 8
MARKS_W = 6  # the column of the updated diamonds and the notch, outside the rail
FRAME = 1  # the screen on show's outline goes round its mark, outside the rail (its state still seen inside)
RAIL_GAP = 10  # the rail stays this far from the page, where the margin has room ...
RAIL_GAP_LEAST = 2  # ... and at least this far in the room kept for it
RAIL_ROOM = 24  # an exit margin under this many px: the picture is drawn RESERVE px clear of that side
RESERVE = 16
RAIL_PAGE_PX = 8  # with this many px a screen or more, every screen has a mark of its own; else runs of a mark merge
RUN_LEAST_PX = 2  # a run merged is drawn at least this tall ...
ON_SHOW_LEAST_PX = 6  # ... and the screen on show, a run of its own, at least this tall

# the rule for an estimate of the time left: trusted from 8 lines over 15 seconds of work, counted from the first line
# done (the model's loading is left out)
TRUST_LINES = 8
TRUST_S = 15.0

Box = tuple[int, int, int, int]


# ------------------------------------------------------------------ the state
@dataclass
class Screen:
    """A screen turned past (one page, or a spread: what is captured and cached as one): its number in the order of
    first sight, its fingerprint as the engine told it, its thumbnail (memory only, fitted into `THUMB_BOX`), its two
    stages, and whether its words changed since the person saw them (`ui.seen`: the diamond)."""

    seq: int
    fingerprint: str = ""
    thumb: Image.Image | None = None
    stages: dict[str, str] = field(default_factory=lambda: {s: "waiting" for s in SIDE_STAGES})
    updated: bool = False

    @property
    def mark(self) -> str:
        """The screen's mark: "missed" (it went by before it could be caught; or it was on show, turned past and not
        caught - its read done, its translation "missed": it is read when shown again), "working" (a stage under way,
        or the translation begun - some lines answered and kept - and not finished), "failed", "done" (translated, or
        with nothing to translate), "waiting" (caught, its work to come)."""
        read, translate = self.stages["read"], self.stages["translate"]
        if read == "missed":
            return "missed"
        if "working" in (read, translate):
            return "working"
        if "failed" in (read, translate):
            return "failed"
        if translate in ("done", "skipped") or read == "skipped":
            return "done"
        if translate == "missed":
            return "missed"
        return "waiting"

    def state(self, stage: str) -> str:
        """A stage's state as its bar shows it: the translation of a screen that went by too fast is not caught either
        (nothing waits for it until the person turns back to it)."""
        state = self.stages[stage]
        if stage == "translate" and state == "waiting" and self.stages["read"] == "missed":
            return "missed"
        return state


@dataclass
class Backlog:
    """The backlog's totals as the engine last told them (``backlog``): the screens caught and not done yet, the lines
    still to translate of those read, whether the work is paused (Auto off, Stop, the model released), and how many
    screens went by too fast to be caught (or were not caught: over the caps), not caught or done since."""

    pages: int = 0
    lines: int = 0
    paused: bool = False
    dropped: int = 0


class BacklogPace:
    """How fast the backlog's lines go, for "about X min more": the lines done (the totals going down) over the time
    worked (paused time left out), counted from the first line done; trusted from `TRUST_LINES` lines over `TRUST_S`
    seconds."""

    def __init__(self) -> None:
        self.lines: int | None = None  # the lines last told
        self.at: float | None = None  # when
        self.paused = False
        self.done = 0  # lines done since the first one
        self.worked = 0.0  # seconds worked since the first line done

    def update(self, lines: int, paused: bool, now: float) -> None:
        if self.lines is not None and self.at is not None:
            if self.done > 0 and not self.paused:
                self.worked += max(0.0, now - self.at)
            if lines < self.lines and not paused:
                self.done += self.lines - lines
        self.lines, self.at, self.paused = int(lines), now, bool(paused)

    def left(self, lines: int, now: float) -> float | None:
        """Seconds left for *lines* at the pace so far; None while it cannot be trusted (or nothing is left)."""
        worked = self.worked + (max(0.0, now - self.at) if self.at is not None and self.done > 0 and not self.paused
                                else 0.0)
        if lines <= 0 or self.done < TRUST_LINES or worked < TRUST_S:
            return None
        return lines / (self.done / worked)


class SideModel:
    """The screens of normal reading, by their number (``seq``, the order of first sight: the column top to bottom,
    the rail from its top), the screen on show, and the backlog. Events may come in any order; the latest one for a
    stage wins. Memory only, dropped with the book (`clear`)."""

    def __init__(self) -> None:
        self.screens: dict[int, Screen] = {}
        self.order: list[int] = []
        self.on_show: int | None = None
        self.backlog = Backlog()
        self.pace = BacklogPace()

    def __len__(self) -> int:
        return len(self.order)

    def clear(self) -> None:
        self.screens.clear()
        self.order.clear()
        self.on_show = None
        self.backlog = Backlog()
        self.pace = BacklogPace()

    def update(self, seq: Any, fingerprint: Any = "", thumb: Any = None, stage: Any = None, state: Any = None
               ) -> bool:
        """One ``page_stage`` event; True when it brought a screen not seen before. A stage or a state it does not
        know changes nothing but the screen's being there ("erase" among them: normal reading has none); read
        "merged" takes a placeholder away (the screen is there under another number); a thumbnail is taken when the
        screen has none yet."""
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return False
        if stage == "read" and state == MERGED:
            if self.screens.pop(seq, None) is not None:
                self.order.remove(seq)
                if self.on_show == seq:
                    self.on_show = None
            return False
        screen = self.screens.get(seq)
        new = screen is None
        if screen is None:
            screen = self.screens[seq] = Screen(seq)
            bisect.insort(self.order, seq)
        if fingerprint and not screen.fingerprint:
            screen.fingerprint = str(fingerprint)
        if screen.thumb is None and isinstance(thumb, Image.Image):
            screen.thumb = fit_thumb(thumb)
        if stage in SIDE_STAGES and state in STATES:
            screen.stages[stage] = state
        return new

    def renumbered(self, seq: Any, fingerprint: Any, within: int) -> bool:
        """Whether *fingerprint* told for the screen *seq* is another screen's than the one known under that number:
        the engine numbers the screens of another book from 1 again (the window then starts afresh: `ui.side`)."""
        try:
            screen = self.screens.get(int(seq))
        except (TypeError, ValueError):
            return False
        if screen is None or not screen.fingerprint or not fingerprint:
            return False
        try:
            return fp.hamming(screen.fingerprint, str(fingerprint)) > max(0, int(within))
        except (TypeError, ValueError):
            return screen.fingerprint != str(fingerprint)

    def show(self, seq: Any) -> bool:
        """The screen on show (``page_on_show``; None: none of the book's); whether that changed."""
        try:
            seq = None if seq is None else int(seq)
        except (TypeError, ValueError):
            seq = None
        if seq == self.on_show:
            return False
        self.on_show = seq
        return True

    def set_backlog(self, pages: Any, lines: Any, paused: Any, dropped: Any, now: float) -> bool:
        """The backlog's totals (``backlog``); whether they changed."""
        told = Backlog(_count(pages), _count(lines), bool(paused), _count(dropped) if dropped is not True else 0)
        self.pace.update(told.lines, told.paused, now)
        if told == self.backlog:
            return False
        self.backlog = told
        return True

    def working(self) -> bool:
        return any("working" in s.stages.values() for s in self.screens.values())

    def counts(self) -> dict[str, int]:
        """How many screens have each mark, and how many are updated."""
        out = {mark: 0 for mark in MARKS}
        for screen in self.screens.values():
            out[screen.mark] += 1
        out["updated"] = sum(1 for s in self.screens.values() if s.updated)
        return out


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ what it says
def duration(seconds: float) -> str:
    """About how long *seconds* are, in the window's language (`banner.duration_text`)."""
    from .banner import duration_text

    return duration_text(seconds)


def summary_lines(model: SideModel, now: float) -> list[str]:
    """The hover text of the indicator as a whole, a line each, in the window's language: done of the screens seen;
    the backlog (screens and lines to go, about how long once that can be trusted, paused); the screens that went by
    too fast to catch (the engine's count, ``dropped``, or those the indicator has so marked, whichever is more), and
    those updated since the person saw them - each only when there is one."""
    counts = model.counts()
    seen = len(model)
    lines = [_("Done: {done} of {seen} page(s) seen.").format(done=counts["done"], seen=seen)]
    backlog = model.backlog
    if backlog.pages > 0:
        lines.append(_("Working on the others: {pages} page(s), {lines} line(s) to go.").format(
            pages=backlog.pages, lines=backlog.lines))
        left = None if backlog.paused else model.pace.left(backlog.lines, now)
        if left is not None:
            lines.append(_("About {time} more.").format(time=duration(left)))
    if backlog.paused and backlog.pages > 0:
        lines.append(_("Paused for now: the pages behind wait."))
    missed = max(counts["missed"], backlog.dropped)  # (one count told two ways: never said twice)
    if missed:
        lines.append(_("{n} turned too fast to catch: turn back to them in the viewer to have them read.").format(
            n=missed))
    if counts["updated"]:
        lines.append(_("{n} updated since you saw them.").format(n=counts["updated"]))
    return lines


def screen_tip(model: SideModel, seq: int) -> str:
    """A thumbnail's hover text, and its click in the status line (`ui.side`): how to read that screen - in the viewer,
    never from here -, on show now, updated; a screen that went by too fast: turn back to it."""
    screen = model.screens.get(seq)
    if screen is not None and screen.mark == "missed":
        return _("Page {n} went by before it could be taken. Turn back to it in the viewer and it is read like any other.").format(n=seq)
    if model.on_show == seq:
        line = _("Page {n}: on show now.").format(n=seq)
    else:
        line = _("Page {n} of the pages seen so far. To read it, turn to it in the viewer: TASlation shows the translation over it.").format(n=seq)
    if screen is not None and screen.updated:
        line += " " + _("Its words changed since you saw it.")
    return line


def bar_line(stage: str, state: str) -> str:
    """A bar's hover text: its stage and its state (`stage_name`, `state_word`)."""
    return _("{stage}: {state}").format(stage=stage_name(stage), state=state_word(state))


def run_tip(first: int, last: int, mark: str) -> str:
    """A merged run of the rail: its screens and their mark."""
    word = state_word({"done": "done", "working": "working", "waiting": "waiting", "failed": "failed",
                       "missed": "missed"}[mark])
    if first == last:
        return _("Page {n}: {state}").format(n=first, state=word)
    return _("Pages {first} to {last}: {state}").format(first=first, last=last, state=word)


# ------------------------------------------------------------------ the rail's marks
@dataclass(frozen=True)
class RailMark:
    """A mark of the rail: from *y0* to *y1* (rail pixels from its top), the *mark* of its screens (*seqs*, in order),
    whether the screen on show is it."""

    y0: int
    y1: int
    mark: str
    seqs: tuple[int, ...]
    on_show: bool = False


def rail_marks(model: SideModel, height: int) -> list[RailMark]:
    """The rail's marks over *height* px: with `RAIL_PAGE_PX` or more a screen, one mark a screen (1 px apart); with
    fewer, the screens one after another with the same mark make one mark, at least `RUN_LEAST_PX` tall - and the
    screen on show is a run of its own, at least `ON_SHOW_LEAST_PX` -, the room shared by how many screens each holds.
    Hundreds of screens fit: there are never more marks than the rail has pixels for."""
    order = model.order
    n = len(order)
    if n == 0 or height <= 0:
        return []
    if height >= RAIL_PAGE_PX * n:
        step = height / n
        return [RailMark(int(round(i * step)), max(int(round(i * step)) + 1, int(round((i + 1) * step)) - 1),
                         model.screens[seq].mark, (seq,), seq == model.on_show) for i, seq in enumerate(order)]
    runs: list[tuple[str, list[int], bool]] = []  # (mark, seqs, on show)
    for seq in order:
        mark, on = model.screens[seq].mark, seq == model.on_show
        if runs and not on and not runs[-1][2] and runs[-1][0] == mark:
            runs[-1][1].append(seq)
        else:
            runs.append((mark, [seq], on))
    for run_least, show_least in ((RUN_LEAST_PX, ON_SHOW_LEAST_PX), (1, 3)):
        least = [show_least if on else run_least for _mark, _seqs, on in runs]
        if sum(least) <= height:
            break
    else:  # more runs than the rail has pixels for: a pixel row each, of its screens' weightiest mark
        return _rail_by_row(model, height)
    spare = height - sum(least)
    # each run its least, and the rest of the room by how many screens it holds; the edges rounded from the running
    # sums, so that the marks fill the rail exactly
    out: list[RailMark] = []
    low_sum, share, top = 0, 0.0, 0
    for (mark, seqs, on), low in zip(runs, least):
        low_sum += low
        share += spare * len(seqs) / n
        bottom = min(height, max(top + 1, int(round(low_sum + share))))
        out.append(RailMark(top, bottom, mark, tuple(seqs), on))
        top = bottom
    return out


WEIGHT = {"working": 4, "failed": 3, "missed": 2, "waiting": 1, "done": 0}  # a row of several screens shows the first


def _rail_by_row(model: SideModel, height: int) -> list[RailMark]:
    """The rail's marks when even a pixel a run is too much: each pixel row takes its screens (by their place in the
    order), shows the weightiest of their marks (`WEIGHT`; the screen on show above all), and rows alike join."""
    order, n = model.order, len(model.order)
    out: list[RailMark] = []
    for y in range(height):
        seqs = order[y * n // height:max(y * n // height + 1, (y + 1) * n // height)]
        on = model.on_show in seqs
        mark = max((model.screens[s].mark for s in seqs), key=lambda m: WEIGHT[m])
        last = out[-1] if out else None
        if last is not None and last.mark == mark and not on and not last.on_show:
            out[-1] = RailMark(last.y0, y + 1, mark, last.seqs + tuple(seqs), False)
        else:
            out.append(RailMark(y, y + 1, mark, tuple(seqs), on))
    return out


def rail_y(marks: list[RailMark], seq: int) -> int | None:
    """The middle of screen *seq* on the rail (rail pixels from its top): within its mark, by its place in the run."""
    for m in marks:
        if seq in m.seqs:
            i = m.seqs.index(seq)
            return int(m.y0 + (i + 0.5) * (m.y1 - m.y0) / len(m.seqs))
    return None


# ------------------------------------------------------------------ where it goes
@dataclass(frozen=True)
class SideLayout:
    """Where the indicator goes: *kind* "column", "rail" or "" (none), on the *side* "left" or "right", its *box* on
    the canvas (x0, y0, x1, y1), and in it the rail's left edge and width (*rail_x*, *rail_w*) and the marks' column
    (*marks_x*)."""

    kind: str = ""
    side: str = "left"
    box: Box = (0, 0, 0, 0)
    rail_x: int = 0
    rail_w: int = 0
    marks_x: int = 0


def exit_side(rtl: bool) -> str:
    """The side a page is turned towards: left in a book read right to left."""
    return "left" if rtl else "right"


def natural_margin(part: tuple[int, int], canvas: tuple[int, int], inset: int, enlarge: bool) -> int:
    """The margin beside a picture of *part* drawn on *canvas* with nothing kept clear (`area.fit`, centred)."""
    from .area import fit

    (w, _h), (x, _y) = fit(part, canvas, inset, enlarge)
    return min(x, canvas[0] - x - w)


def room_kept(setting: str, part: tuple[int, int], canvas: tuple[int, int], inset: int = 0,
              enlarge: bool = False, rtl: bool = True) -> tuple[int, int]:
    """The canvas pixels kept clear on its left and right of a picture of *part* (`ImageCanvas.side_room_of`):
    `RESERVE` on the exit side where the indicator is on (*setting* not "off") and the exit margin a picture drawn
    without it would leave is under `RAIL_ROOM`; (0, 0) otherwise. It depends on these alone, never on what the
    indicator shows, so the page keeps its size from page to page."""
    if setting == "off" or canvas[0] < 4 * RESERVE:
        return (0, 0)
    if natural_margin(part, canvas, inset, enlarge) >= RAIL_ROOM:
        return (0, 0)
    return (RESERVE, 0) if exit_side(rtl) == "left" else (0, RESERVE)


def side_layout(setting: str, canvas: tuple[int, int], shown: Box | None, rtl: bool, full: bool,
                top: int = 0) -> SideLayout:
    """Where the indicator goes beside the picture drawn at *shown* (canvas pixels) on a canvas of *canvas*: the
    column where *setting* is "column" and the exit margin is `COLUMN_NEEDS` or more, its middle in the margin's
    middle, from `COLUMN_TOP` down to the canvas's bottom (on the full screen *full*, `SLOT_ROOM` above it); the rail
    otherwise, as tall as the picture, `RAIL_GAP` px from the page where the margin has room for that, nearer in the
    room kept for it (`room_kept`); both below *top* (on the right, the busy badge's and the full screen's close
    button's place); nothing with *setting* "off", with no picture, or with no room at all (a margin under `RAIL_W` +
    `MARKS_W` + `RAIL_GAP_LEAST`)."""
    if setting not in ("column", "rail") or shown is None:
        return SideLayout()
    side = exit_side(rtl)
    width, height = canvas
    x0, y0, x1, y1 = (int(v) for v in shown)
    margin = x0 if side == "left" else width - x1
    edge = x0 if side == "left" else x1  # the page's edge on that side
    if setting == "column" and margin >= COLUMN_NEEDS:
        middle = margin / 2
        left = int(round(middle - COLUMN_W / 2))
        left = max(COLUMN_OUT, min(left, margin - COLUMN_GAP - COLUMN_W))
        first = max(COLUMN_TOP, top)
        bottom = max(first + CELL_H, height - (SLOT_ROOM if full else COLUMN_TOP))
        if side == "left":
            box = (left, first, left + COLUMN_W, bottom)
        else:
            box = (width - left - COLUMN_W, first, width - left, bottom)
        return SideLayout("column", side, box)
    rail = RAIL_W_FULL if full else RAIL_W
    y0 = max(y0, top)
    if margin < rail + MARKS_W + RAIL_GAP_LEAST or y1 - y0 < 4 * RAIL_PAGE_PX:
        return SideLayout()
    gap = max(RAIL_GAP_LEAST, min(RAIL_GAP, margin - rail - MARKS_W))
    if side == "left":  # (the box takes in the on-show outline's `FRAME` on the page's side: gap > FRAME always)
        rail_x = edge - gap - rail
        marks_x = rail_x - MARKS_W
        box = (marks_x, y0, edge - gap + FRAME, y1)
        return SideLayout("rail", side, box, rail_x - box[0], rail, marks_x - box[0])
    rail_x = edge + gap
    marks_x = rail_x + rail
    box = (rail_x - FRAME, y0, marks_x + MARKS_W, y1)
    return SideLayout("rail", side, box, FRAME, rail, FRAME + rail)

