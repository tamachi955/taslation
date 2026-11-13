"""Formatting copied and pasted, as a word processor's Format Painter does it: Ctrl+Shift+C keeps the selected
region's formatting (`RegionStyle`: font, size, bold and italic, alignment, spacing, slant, text direction, text colour
and outline) in the window, Ctrl+Shift+V puts it on the regions `_format_targets` names (the selected ones), one
change that Ctrl+Z takes back however many regions it formats. The region's kind is not part of it: the kind is a
premise the model is told (set in the region editor), not a formatting. Page > Paste format on every region of
this kind... puts it on every region of the targets' kinds in the whole book (`book_spots`): the notes of that kind
in the book's annotations, which hold the kind of every region that has one, and for "(not set)" the bubbles of the
translated pages in the book's cache; a page never read has no regions yet. That is one change across the book
(`BookStyles`, a `history.BookStep`) that Ctrl+Z takes back whichever page is on show. Ctrl+C keeps the selected
region itself (its box and formatting) and Ctrl+V adds it to another page laid out alike, at the same place, as a
rectangle drawn there is added (`_add_region`: its text read and translated anew). The clip is in memory only
(`FormatClip`); nothing of a page is kept in it."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..annotations import BookAnnotations, PageAnnotations, RegionNote, RegionStyle
from ..fingerprint import hamming
from ..i18n import _
from ..regions import box_iou
from .constants import in_a_run
from .dialogs import caches as boxes
from .dialogs.review import REGION_KIND_WORDS
from .history import OWN_PAGE, BookStep, _carry_notes, owner
from .translator import chosen_regions, holds

NBox = tuple[float, float, float, float]
Box = tuple[int, int, int, int]

# what the status line says
FORMAT_COPIED = "Formatting copied: Ctrl+Shift+V puts it on the selected region."
NOTHING_COPIED = "Nothing copied yet: select a region and press Ctrl+Shift+C to copy its formatting."
FORMAT_PASTED = "Formatting pasted on {n} region(s). Ctrl+Z takes it back."
FORMAT_SAME = "The region already has this formatting."
SELECT_FIRST = "Select a region first (click it)."
NO_BOOK = "Could not store the formatting: give the book a name first (the Book field)."
# Page > Paste format on every region of this kind...: the question, its button, and what is said
KIND_QUESTION = ("Put the copied formatting on every region of the kind {kinds} in this book: {n} region(s) on {pages} "
                 "page(s)? Ctrl+Z takes it back.")
KIND_APPLY = "Paste on {n} region(s)"
KIND_NONE = "Every region of this kind in the book already has this formatting."
KIND_DONE = "Formatting pasted on {n} region(s) on {pages} page(s). Ctrl+Z takes it back."
KIND_IN_A_RUN = "The formatting was not pasted across the book: a run is reading it. Try again once it is done."
KIND_BACK = "Formatting across the book taken back on {pages} page(s)."
KIND_AGAIN = "Formatting across the book made again on {pages} page(s)."
SAVE_FAILED = "Could not save the change: {error}"
# Ctrl+C and Ctrl+V: a region itself, its box and formatting, onto another page laid out alike
REGION_COPIED = "Region copied: Ctrl+V adds it, box and formatting, at the same place on another page laid out alike."
NO_REGION_COPIED = "Nothing copied yet: select a region and press Ctrl+C to copy it."
REGION_THERE = "A region is already there: Ctrl+Shift+V puts the copied formatting on it."
REGION_ELSEWHERE = "The copied region is from a page of another size: paste it on a page laid out alike."
THERE = 0.5  # a region on the page overlapping the pasted one this much is there already
# the Page menu's entries said in the status line while the pointer is on them (`app.App._build_menus`)
PAGE_FORMAT_TIPS = (
    "Translator mode: keep the selected region's formatting (font, size, alignment, slant, direction, colours), not "
    "its kind.",
    "Translator mode: put the formatting copied last on the selected region.",
    "Translator mode: put the formatting copied last on every region of the selected region's kind in this book; "
    "it asks first.",
    "Translator mode: keep the selected region itself, its box and formatting, to add it to another page laid out "
    "alike.",
    "Translator mode: add the region copied last at the same place on this page; its text is read and translated.",
)


@dataclass
class FormatClip:
    """What was copied in the window, in memory only: the formatting (Ctrl+Shift+C; None: nothing yet) and a region
    (Ctrl+C: its box in the capture's pixels, the capture's size, its formatting)."""

    style: RegionStyle | None = None
    region: tuple[Box, tuple[int, int], RegionStyle] | None = None


@dataclass
class PageStyles:
    """One page of the book's annotations, as a change across the book found it and left it: copies of its notes."""

    fingerprint: str
    aspect: float
    before: list[RegionNote] = field(default_factory=list)
    after: list[RegionNote] = field(default_factory=list)


class BookStyles(BookStep):
    """A formatting pasted on every region of a kind in the book: one change on no page in particular (`BookStep`),
    the pages' notes before and after it (`pages`) and how many regions it formatted (`count`)."""

    def __init__(self, owner: tuple[str, ...]):
        super().__init__(owner)
        self.kind = "styles"
        self.pages: list[PageStyles] = []
        self.count = 0


# ------------------------------------------------------------------ the regions of a kind, across the book
def kind_boxes(page: PageAnnotations | None, bubbles: Sequence[Any], kinds: Sequence[str], min_iou: float = 0.4,
               more: Sequence[NBox] = ()) -> list[NBox]:
    """The boxes of the regions of *kinds* on one page unit: its notes of those kinds, its cached *bubbles* whose note
    says one of them (no note: "" - not set), and *more* (the regions on show); the spots the reader dropped are left
    out, and each region counts once."""
    notes = page.notes if page is not None else []
    ignored = page.ignore if page is not None else []
    out: list[NBox] = []

    def take(box: Sequence[float]) -> None:
        nbox = tuple(float(v) for v in box)
        if any(box_iou(nbox, i) >= min_iou for i in ignored) or any(box_iou(nbox, o) >= min_iou for o in out):
            return
        out.append(nbox)  # type: ignore[arg-type]

    for n in notes:
        if n.kind in kinds:
            take(n.box)
    for b in bubbles:
        note = page.note_at(b.box, min_iou) if page is not None else None
        if (note.kind if note is not None else "") in kinds:
            take(b.box)
    for box in more:
        take(box)
    return out


def book_spots(annotations: BookAnnotations, cache: Any, kinds: Sequence[str], style: RegionStyle,
               shown: dict[tuple[str, float], list[NBox]] | None = None, min_iou: float = 0.4
               ) -> list[tuple[str, float, list[NBox]]]:
    """The regions of *kinds* in the whole book that *style* would change, per page unit (fingerprint, aspect,
    boxes): the book's annotation pages joined to its cached pages (the same page within `OWN_PAGE` bits), with
    *shown* (the boxes of the regions on show, by their unit). Reads the stores, changes nothing."""
    units: list[list[Any]] = []  # [fingerprint, aspect, annotations page or None, cached bubbles, boxes on show]

    def entry(fingerprint: str, aspect: float) -> list[Any]:
        page = annotations.lookup(fingerprint, aspect, OWN_PAGE)
        for u in units:
            if (page is not None and u[2] is page) or (page is None and u[2] is None
                                                        and hamming(u[0], fingerprint) <= OWN_PAGE):
                return u
        u = [page.fingerprint if page is not None else fingerprint, page.aspect if page is not None else aspect,
             page, [], []]
        units.append(u)
        return u

    for page in annotations.pages:
        entry(page.fingerprint, page.aspect)
    for cached in getattr(cache, "pages", []) if cache is not None else []:
        entry(cached.fingerprint, cached.aspect)[3].extend(cached.bubbles)
    for (fingerprint, aspect), shown_boxes in (shown or {}).items():
        entry(fingerprint, aspect)[4].extend(shown_boxes)
    out: list[tuple[str, float, list[NBox]]] = []
    for fingerprint, aspect, page, bubbles, more in units:
        found = []
        for box in kind_boxes(page, bubbles, kinds, min_iou, more):
            note = page.note_at(box, min_iou) if page is not None else None
            if (note.style if note is not None else RegionStyle()) != style:
                found.append(box)
        if found:
            out.append((fingerprint, aspect, found))
    return out


def style_spots(annotations: BookAnnotations, spots: Sequence[tuple[str, float, Sequence[NBox]]], style: RegionStyle,
                min_iou: float = 0.4) -> list[PageStyles]:
    """*style* set at every box of *spots* in the annotations (a note made where there is none); the pages as they
    were and are now. The caller saves."""
    out: list[PageStyles] = []
    for fingerprint, aspect, spot_boxes in spots:
        page = annotations.page(fingerprint, aspect, OWN_PAGE)
        before = copy.deepcopy(page.notes)
        for box in spot_boxes:
            page.set_style(box, style, min_iou)
        out.append(PageStyles(page.fingerprint, page.aspect, before, copy.deepcopy(page.notes)))
    return out


def carry_styles(annotations: BookAnnotations, pages: Sequence[PageStyles], back: bool) -> int:
    """A change across the book taken back (*back*) or made again on the annotations as they are now, only at the
    notes it changed (`history._carry_notes`): what else changed on those pages meanwhile stays. The pages changed;
    the caller saves."""
    changed = 0
    for p in pages:
        frm, to = (p.after, p.before) if back else (p.before, p.after)
        live = annotations.lookup(p.fingerprint, p.aspect, OWN_PAGE)
        base = list(live.notes) if live is not None else []
        notes = _carry_notes(base, frm, to)
        if notes is not base:
            if live is None:
                live = annotations.page(p.fingerprint, p.aspect, OWN_PAGE)
            live.notes = notes
            changed += 1
    return changed


def shown_spots(result: Any, kinds: Sequence[str]) -> dict[tuple[str, float], list[NBox]]:
    """The boxes of the regions of *kinds* on the page on show, by their page unit (as the annotations keep them)."""
    out: dict[tuple[str, float], list[NBox]] = {}
    for r in result.regions:
        if r.tag in kinds and r.unit < len(result.units):
            unit = result.units[r.unit]
            out.setdefault((unit.fingerprint, unit.aspect), []).append(unit.normalize(r.bbox))
    return out


def restyle_shown(pipeline: Any, result: Any) -> None:
    """The regions on show take the formatting their notes now hold (as a page read from the stores would)."""
    annotations = pipeline.annotations
    for r in result.regions:
        if r.unit >= len(result.units):
            continue
        unit = result.units[r.unit]
        page = annotations.lookup(unit.fingerprint, unit.aspect, OWN_PAGE)
        note = page.note_at(unit.normalize(r.bbox), pipeline.settings.match_min_iou) if page is not None else None
        r.style = None if note is None or note.style.is_empty else note.style


# ------------------------------------------------------------------ in the window
class FormatMixin:
    """Copy format, Paste format (also on a whole kind in the book), Copy region and Paste region. A part of
    `app.App`."""

    _format_clip: FormatClip | None = None

    def format_clip(self) -> FormatClip:
        """What was copied in this window (the region editor shares it)."""
        if self._format_clip is None:
            self._format_clip = FormatClip()
        return self._format_clip

    def _format_targets(self) -> list:
        """The regions Paste format puts the formatting on: the selected regions, one or several (Shift+click and a
        Shift+drag select several: `translator.chosen_regions`); none: nothing."""
        return [r for r in chosen_regions(self) if holds(self.last_result, r)]

    def copy_format(self) -> None:
        """Ctrl+Shift+C (Page > Copy format): the selected region's formatting kept for Paste format (its own, or the
        automatic one: pasted, that resets the formatting); not its kind."""
        if not self._editing():
            return
        region = self._chosen_region
        if region is None or not holds(self.last_result, region):
            self.say(SELECT_FIRST)
            return
        self.format_clip().style = region.style or RegionStyle()
        self.say(FORMAT_COPIED)

    def paste_format(self) -> None:
        """Ctrl+Shift+V (Page > Paste format): the formatting copied last put on the regions of `_format_targets`."""
        if not self._editing() or self.busy:
            return
        style = self.format_clip().style
        if style is None:
            self.say(NOTHING_COPIED)
            return
        targets = self._format_targets()
        if not targets:
            self.say(SELECT_FIRST)
            return
        self._paste_styles(targets, style)

    def _paste_styles(self, regions: Sequence[Any], style: RegionStyle, kind: str = "paste") -> None:
        """*style* on each of *regions* of the page on show, their premises, notes and translations as they are:
        stored with the book's premises, the page lettered again once, one change of *kind* to take back."""
        result, pipeline = self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        changing = [r for r in regions if holds(result, r) and (r.style or RegionStyle()) != style]
        if not changing:
            self.say(FORMAT_SAME)
            return
        if pipeline.annotations is None:
            self.say(NO_BOOK)
            return
        step = self._record(kind, result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, changing)
                done = sum(1 for r in changing if pipeline.set_region_style(result, r, style))
                pipeline.rerender(result)
                step.settle(pipeline, bool(done))
                self._post("result", result=result, edited=True)
                self._post("status", key=FORMAT_PASTED, values={"n": done})
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def paste_format_on_kind(self) -> None:
        """Page > Paste format on every region of this kind...: the formatting copied last on every region of the
        kinds of `_format_targets` in the whole book (`book_spots`), once the reader said yes to how many; one change
        across the book (`BookStyles`). Not during a run."""
        if not self._editing() or self.busy:
            return
        style = self.format_clip().style
        if style is None:
            self.say(NOTHING_COPIED)
            return
        result, pipeline = self.last_result, self.pipeline
        targets = self._format_targets()
        if not targets or pipeline is None:
            self.say(SELECT_FIRST)
            return
        if pipeline.annotations is None:
            self.say(NO_BOOK)
            return
        if in_a_run(self):
            self.say(KIND_IN_A_RUN)
            return
        kinds = sorted({r.tag for r in targets})
        min_iou = pipeline.settings.match_min_iou

        def spots() -> list[tuple[str, float, list[NBox]]]:
            return book_spots(pipeline.annotations, pipeline.cache, kinds, style, shown_spots(result, kinds), min_iou)

        found = spots()
        count = sum(len(b) for _f, _a, b in found)
        if not count:
            self.say(KIND_NONE)
            return
        names = ", ".join(_(REGION_KIND_WORDS.get(k, k)) for k in kinds)
        if not boxes.ask(self, _(KIND_QUESTION).format(kinds=names, n=count, pages=len(found)),
                         _(KIND_APPLY).format(n=count)):
            return
        step = BookStyles(owner(pipeline))
        self.history.record(step, pipeline.settings.fingerprint_max_distance)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                now = spots()  # the stores as the worker finds them
                step.pages = style_spots(pipeline.annotations, now, style, min_iou)
                step.count = sum(len(b) for _f, _a, b in now)
                step.state = "done" if step.pages else "empty"
                saved = _saved(pipeline)
                restyle_shown(pipeline, result)
                pipeline.rerender(result)
                self._post("result", result=result, edited=True)
                if saved:
                    self._post("status", key=KIND_DONE, values={"n": step.count, "pages": len(step.pages)})
                else:
                    self._post("status", key=SAVE_FAILED, values={"error": _save_error(pipeline)})
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def _carry_book_styles(self, step: BookStyles, back: bool) -> None:
        """Ctrl+Z (*back*) or Ctrl+Y on a formatting pasted across the book, whichever page is on show: the notes it
        changed as they were (or as it left them), the page on show lettered as its notes now say."""
        pipeline, result = self.pipeline, self.last_result
        (self.history.taken_back if back else self.history.made_again)(step)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                carry_styles(pipeline.annotations, step.pages, back)
                saved = _saved(pipeline)
                if result is not None:
                    restyle_shown(pipeline, result)
                    pipeline.rerender(result)
                    self._post("result", result=result, edited=True)
                if saved:
                    self._post("status", key=KIND_BACK if back else KIND_AGAIN, values={"pages": len(step.pages)})
                else:
                    self._post("status", key=SAVE_FAILED, values={"error": _save_error(pipeline)})
            finally:
                self._post("translate_done")

        self._jobs.put(job)

    def copy_region(self) -> None:
        """Ctrl+C (Page > Copy region): the selected region's box and formatting kept for Paste region."""
        if not self._editing():
            return
        region, result = self._chosen_region, self.last_result
        if region is None or not holds(result, region):
            self.say(SELECT_FIRST)
            return
        self.format_clip().region = (tuple(int(v) for v in region.bbox), tuple(result.original.size),
                                     region.style or RegionStyle())
        self.say(REGION_COPIED)

    def paste_region(self) -> None:
        """Ctrl+V (Page > Paste region): the region copied last added to the page on show at the same place, with its
        formatting, as a rectangle drawn there (`_add_region`: read and translated anew; Ctrl+Z takes it back). Not on
        a page of another size, nor where a region is already."""
        if not self._editing() or self.busy:
            return
        copied, result = self.format_clip().region, self.last_result
        if result is None:
            return
        if copied is None:
            self.say(NO_REGION_COPIED)
            return
        box, size, style = copied
        if tuple(result.original.size) != tuple(size):
            self.say(REGION_ELSEWHERE)
            return
        if any(box_iou(r.bbox, box) >= THERE for r in result.regions):
            self.say(REGION_THERE)
            return
        self._add_region(box, style=style)


def _saved(pipeline: Any) -> bool:
    """The book's annotations written (`Pipeline.save_annotations`: a failure is kept, not raised)."""
    pipeline.save_annotations()
    return not _save_error(pipeline)


def _save_error(pipeline: Any) -> str:
    """Why the last save failed, in the operating system's words ("": all is written)."""
    error = getattr(pipeline, "save_error", "")
    return str(error() if callable(error) else error or "")


__all__ = ["BookStyles", "FormatClip", "FormatMixin", "PAGE_FORMAT_TIPS", "PageStyles", "book_spots", "carry_styles", "kind_boxes",
           "restyle_shown", "shown_spots", "style_spots"]
