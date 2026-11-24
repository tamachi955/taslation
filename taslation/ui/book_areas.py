"""An area ignored on every page of the book - a watermark, a page number, a banner (`annotations.BookArea`, kept in
the book's annotations): Page > Ignore this area on all pages of this book makes one of the selected region's place
(`AreaMixin.ignore_area_everywhere`), and a region dropped at a place where one was dropped on another page of the book
before brings the same question once the drop is stored (`_offer_ignore_everywhere`; a "no" is not asked again in the
window). Adding one is one change across the book (`BookAreas`, a `history.BookStep` of kind "areas") that Ctrl+Z
takes back whichever page is on show; the page on show is read again from the stores when the area touches it.
Detection leaves out what lies mostly inside an area (`Pipeline._annotate`), on a page on show and on the pages turned
past alike; Book settings lists the areas and removes one, with its Undo (`dialogs.book_settings`). Nothing of a page
is kept: an area is four numbers, a side and the page's shape.

Book settings' Use these areas for the series (`use_areas_for_series`), and the Page menu's entry of that name
(`AreaMixin.use_areas_for_series_now`, greyed while the book has no series: `series_areas_ready`), keep the areas in
force for the book as its series' areas (`annotations.SeriesDefaults`), which a new volume of the series starts with.
An area is in the page's own terms (0..1 of its width and height, the page cropped to its ink as within one volume)
with the page's width / height, so it lies at the same place on a volume captured at another size, and leaves a
volume whose pages have another shape alone (`BookArea.applies`)."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from ..annotations import BookAnnotations, BookArea, unit_side
from ..fingerprint import hamming
from ..i18n import _
from .dialogs import caches as boxes
from .history import OWN_PAGE, BookStep, owner
from .translator import holds

# the entry of the Menu's Page (`see_edit.build_menu`), and the tip the window's Page menu had for it
IGNORE_EVERYWHERE = "Ignore this area on all pages of this book"
IGNORE_TIP = ("Translator mode: what is found mostly inside the selected region's place is left as drawn on every page "
              "of this book (watermarks, page numbers, banners); Book settings lists these areas.")
# a region dropped where one was dropped on another page before: the question and its buttons
AREA_QUESTION = ("You dropped a region at this place on another page of this book too. Ignore this area on all pages "
                 "of this book? What is found mostly inside it is left as drawn on every page. Book settings lists it, "
                 "and Menu > Undo takes it back.")
AREA_YES = "Ignore on all pages"
AREA_NO = "Only this page"
# what the status line says
AREA_ADDED = "This area is ignored on all pages of this book. Menu > Undo takes it back; Book settings lists it."
AREA_THERE = "This area is ignored on all pages of this book already."
AREA_BACK = "The area ignored on all pages is taken back: text is looked for there again."
AREA_AGAIN = "The area is ignored on all pages again."
SELECT_FIRST = "Select a region first (click it)."
NO_BOOK = "Could not record the rectangle: give the book a name first (Menu > Series and Volume...)."
SAVE_FAILED = "Could not save the change: {error}"
OFFER_POLL_MS = 100  # how often the question after a drop looks whether the drop is stored and the window free
# Book settings' button that keeps the areas listed as the series' areas, its tip, and what it says once they are
USE_FOR_SERIES = "Use these areas for the series"
USE_FOR_SERIES_TIP = ("Start every new volume of {series} with the areas listed here. A volume that has areas of its "
                      "own keeps them.")
AREAS_SHARED = "Saved: a new volume of {series} starts with these {n} area(s)."
AREAS_SHARED_NONE = "Saved: a new volume of {series} starts with no areas ignored."
# the Menu's Page entry of the same name (`USE_FOR_SERIES`): the tip the window's Page menu had for it, and what is
# said when the series' file cannot be written (Book settings' line, `dialogs.book_settings.SHARE_FAILED`)
SERIES_AREAS_TIP = ("Start every new volume of this book's series with the areas this book ignores on all pages. A "
                    "volume that has areas of its own keeps them.")
SERIES_AREAS_FAILED = "Could not save the series' defaults: {error}"


class BookAreas(BookStep):
    """An area ignored on every page of the book, added in translator mode: one change on no page in particular
    (`BookStep`), the *area* itself; taking it back removes it from the book's annotations, making it again adds it."""

    def __init__(self, owner: tuple[str, ...], area: BookArea):
        super().__init__(owner)
        self.kind = "areas"
        self.area = area


def area_for(result: Any, region: Any) -> BookArea | None:
    """The area of *region*'s place on its page unit of the capture *result* (`BookArea.around`: its box grown a
    little, the unit's side of a spread and its shape); None for a region of no unit."""
    units = getattr(result, "units", None) or []
    if not 0 <= region.unit < len(units):
        return None
    unit = units[region.unit]
    return BookArea.around(unit.normalize(region.bbox), unit_side(unit, units), unit.aspect)


def dropped_elsewhere(annotations: BookAnnotations, fingerprint: str, area: BookArea) -> bool:
    """Whether a region was dropped inside *area* on another page of the book than the one of *fingerprint* (more
    than `OWN_PAGE` bits from it) of the area's shape: an "ignore" rectangle of that page that the area holds."""
    for page in annotations.pages:
        if hamming(page.fingerprint, fingerprint) <= OWN_PAGE or not area.applies("", page.aspect):
            continue
        if any(area.holds(box) for box in page.ignore):
            return True
    return False


def covered(annotations: BookAnnotations, area: BookArea) -> bool:
    """Whether an area of the book holds *area*'s place already (one alike, or one that holds most of it)."""
    return any(a.same(area) or (a.side in ("", area.side) and a.holds(area.box)) for a in annotations.areas)


def touches(result: Any, area: BookArea, inside: bool = True) -> bool:
    """Whether *area* applies to a page unit of the capture *result* (its side of a spread, its shape) and, with
    *inside*, a region found on it (not one the reader added) lies mostly inside the area."""
    units = getattr(result, "units", None) or []
    for unit in units:
        if not area.applies(unit_side(unit, units), unit.aspect):
            continue
        if not inside:
            return True
        for r in result.regions:
            if (0 <= r.unit < len(units) and units[r.unit] is unit and r.status != "dropped"
                    and not r.kind.startswith("manual") and area.holds(unit.normalize(r.bbox))):
                return True
    return False


def use_areas_for_series(pipeline: Any) -> tuple[str, dict[str, Any]]:
    """Use these areas for the series: the areas in force for the pipeline's book kept as its series' areas
    (`BookAnnotations.share_areas`), which a new volume of the series starts with; the book's own file is saved when the
    book takes the series' areas again (it follows its series, and its own list was the same). Nothing on the book's
    pages changes. Returns what to say: a key (`AREAS_SHARED`, `AREAS_SHARED_NONE`) and its values. ValueError for a
    book without a series; OSError when the series' file cannot be written."""
    annotations = pipeline.annotations
    if annotations.share_areas():
        pipeline.save_annotations()
    n = len(annotations.areas)
    return (AREAS_SHARED if n else AREAS_SHARED_NONE), {"series": annotations.series_name, "n": n}


def _save_error(pipeline: Any) -> str:
    """Why the last save failed, in the operating system's words ("": all is written)."""
    error = getattr(pipeline, "save_error", "")
    return str(error() if callable(error) else error or "")


class AreaMixin:
    """The areas ignored on every page of the book, from translator mode, and the Page menu's Use these areas for the
    series. A part of `app.App`."""

    def series_areas_ready(self) -> bool:
        """Whether Page > Use these areas for the series can act now: the book in the Book box is the one whose
        annotations the window holds, it has a series (`BookAnnotations.can_share`: its name has a volume), and no job
        is on."""
        annotations = getattr(getattr(self, "pipeline", None), "annotations", None)
        if annotations is None or not getattr(annotations, "can_share", False):
            return False
        book_var = getattr(self, "book_var", None)
        if book_var is not None and getattr(annotations, "book", None) != book_var.get().strip():
            return False
        return not getattr(self, "busy", False)

    def _sync_series_areas_entry(self) -> None:
        """The window's Page menu's Use these areas for the series greyed unless it can act (`series_areas_ready`):
        when the menu opens (its postcommand). Nothing calls it now: the Menu's Page is built afresh each time it opens,
        its entry's state read then (`see_edit.build_menu`)."""
        entry = getattr(self, "_series_areas_entry", None)
        if entry is None:
            return
        menu, index = entry
        try:
            menu.entryconfigure(index, state="normal" if self.series_areas_ready() else "disabled")
        except tk.TclError:
            pass

    def use_areas_for_series_now(self) -> None:
        """Page > Use these areas for the series: the areas in force for the book kept as its series' areas, as Book
        settings' button keeps them (`use_areas_for_series`); the status line says what was saved, or why it was not.
        Nothing on the page changes. Only while the entry can act (`series_areas_ready`)."""
        if not self.series_areas_ready():
            return
        try:
            key, values = use_areas_for_series(self.pipeline)
        except (OSError, ValueError) as e:
            self.say(SERIES_AREAS_FAILED, error=e)
            return
        self.say(key, **values)

    def ignore_area_everywhere(self) -> None:
        """Page > Ignore this area on all pages of this book: the selected region's place (`area_for`) ignored on
        every page from now on, as one change across the book (`_add_book_area`); the page on show is read again, so
        that the region goes."""
        if not self._editing() or self.busy:
            return
        region, result, pipeline = self._chosen_region, self.last_result, self.pipeline
        if pipeline is None or region is None or not holds(result, region):
            self.say(SELECT_FIRST)
            return
        if pipeline.annotations is None:
            self.say(NO_BOOK)
            return
        area = area_for(result, region)
        if area is None:
            return
        if any(a.same(area) for a in pipeline.annotations.areas):
            self.say(AREA_THERE)
            return
        self._add_book_area(area, result)

    def _offer_ignore_everywhere(self, region: Any, result: Any, step: Any = None) -> None:
        """A region dropped from the page *result* (`_drop_region`, its change *step*): once the drop is stored and
        the window is free, when a region was dropped inside the same place on another page of the book too
        (`dropped_elsewhere`) and no area holds it yet, the reader is asked whether to ignore that place on all pages
        (`AREA_QUESTION`); yes adds it (`_add_book_area`). Not for a rectangle of the reader's own, and a place the
        reader said no to is not asked about again in this window."""
        pipeline = self.pipeline
        if pipeline is None or result is None or region.kind.startswith("manual"):
            return
        area = area_for(result, region)
        if area is None:
            return
        fingerprint = result.units[region.unit].fingerprint

        def look() -> None:
            if (step is not None and step.state == "pending") or self.busy:
                self.after(OFFER_POLL_MS, look)
                return
            if step is not None and step.state != "done":
                return  # the drop failed, or dropped nothing
            self._ask_ignore_everywhere(pipeline, area, fingerprint, result)

        look()

    def _ask_ignore_everywhere(self, pipeline: Any, area: BookArea, fingerprint: str, result: Any) -> None:
        annotations = getattr(pipeline, "annotations", None)
        if pipeline is not self.pipeline or annotations is None:
            return
        declined: list[BookArea] | None = getattr(self, "_areas_declined", None)
        if declined is None:
            declined = self._areas_declined = []
        if any(area.same(a) for a in declined) or covered(annotations, area):
            return
        if not dropped_elsewhere(annotations, fingerprint, area):
            return
        if not boxes.ask(self, _(AREA_QUESTION), _(AREA_YES), _(AREA_NO)):
            declined.append(area)
            return
        if self.pipeline is pipeline and not self.busy:
            self._add_book_area(area, result)

    def _add_book_area(self, area: BookArea, result: Any) -> None:
        """*area* ignored on every page of the book: one change across the book (`BookAreas`) for Ctrl+Z."""
        pipeline = self.pipeline
        step = BookAreas(owner(pipeline), area)
        self.history.record(step, pipeline.settings.fingerprint_max_distance)
        self._carry_area(step, back=False, first=True)

    def _carry_book_areas(self, step: BookAreas, back: bool) -> None:
        """Ctrl+Z (*back*) or Ctrl+Y on an area added across the book, whichever page is on show."""
        (self.history.taken_back if back else self.history.made_again)(step)
        self._carry_area(step, back)

    def _carry_area(self, step: BookAreas, back: bool, first: bool = False) -> None:
        """The worker adds the step's area to the book's annotations (or, *back*, removes it) and saves them; the page
        on show is read again from the stores when the area touches it (a region on it inside the area goes; taken
        back, what it held comes again), else it stays as it is. The status line says what was done. *first*: the
        change being made, which is kept only when it added the area."""
        pipeline, result = self.pipeline, self.last_result
        reread = (result is not None and self._result_on_show()
                  and touches(result, step.area, inside=not back))
        message = AREA_ADDED if first else (AREA_BACK if back else AREA_AGAIN)
        error: list[str] = []

        def store() -> None:
            try:
                annotations = pipeline.annotations
                changed = bool(annotations is not None and (annotations.remove_area(step.area) if back
                                                            else annotations.add_area(step.area)))
                if first:
                    step.state = "done" if changed else "empty"
                if changed:
                    pipeline.save_annotations()
                    error.append(_save_error(pipeline))
            finally:
                if step.state == "pending":
                    step.state = "failed"

        def said() -> None:
            if error and error[0]:
                self._post("status", key=SAVE_FAILED, values={"error": error[0]})
            else:
                self._post("status", key=message if step.state != "empty" else AREA_THERE)

        if reread:  # the stores first, then the page read from them, then the line
            self._jobs.put(store)
            self._start_translate(result.original, complete=True)
            self._jobs.put(said)
            return
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                store()
                said()
            finally:
                self._post("translate_done")

        self._jobs.put(job)


__all__ = ["AREAS_SHARED", "AREAS_SHARED_NONE", "AREA_QUESTION", "AreaMixin", "BookAreas", "IGNORE_EVERYWHERE",
           "IGNORE_TIP", "SERIES_AREAS_FAILED", "SERIES_AREAS_TIP", "USE_FOR_SERIES", "USE_FOR_SERIES_TIP", "area_for",
           "covered", "dropped_elsewhere", "touches", "use_areas_for_series"]
