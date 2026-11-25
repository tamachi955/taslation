"""Several regions selected at once in translator mode (editing), as shapes in an office program, and the page's reading
order shown and fixed on the boxes (`SelectionMixin`, a part of `app.App`).

Shift+click adds a region to the selection or takes it out of it (`_toggle_chosen`: the overlay's, `see_edit.act`);
`_band_select` adds every region lying wholly inside a rubber band (the canvas's pointer handlers',
`translator.TranslatorMixin._on_press`, which nothing binds while the window is hidden). The selected region (`_chosen_region`) stays the first of
them and the others are `_also_chosen`; `translator.chosen_regions` names them all. With several selected they are
framed without handles, and these act on all of them, each one change that Undo takes back and that selects them all
again: Drop the chosen regions (`_drop_regions`), Text direction (`_restyle_regions`), Paste format
(`formats.FormatMixin._format_targets`), a drag of any of them (`_move_regions`: the same move for each, stopping where
the first meets the page's edge), and the Menu's Page > Set kind... (`set_kind_of_selection`) and Set text size...
(`set_size_of_selection`). A click on one of them without a drag selects it alone, as a click elsewhere and Esc do.

Each region's place in the page's reading order (`_page_regions`) shows in a small badge beside its box
(`_draw_order_badges`, `preview.ImageCanvas.draw_badges`: placed as a label is, clear of the neighbouring regions),
unless an earlier version's View > Reading-order numbers turned them off (ui.json `ORDER_HIDDEN`, still read). While
the reading order is set by clicks the labels carry the numbers instead. Page > Place in reading order... puts the
selected regions at one place of the page's order without clicking the whole page again (`place_in_order`), one
"order" change, as the reading order tool's is. Nothing here is kept but what the stores keep; no page image leaves
memory."""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

from ..annotations import ERASE_ONLY, RegionStyle
from ..i18n import load_ui_flag
from . import area
from .dialogs import selection as asks
from .formats import NO_BOOK, SELECT_FIRST
from .history import unit_states
from .preview import BADGE_TAG
from .translator import MADE_AGAIN, TAKEN_BACK, chosen_regions, holds

log = logging.getLogger(__name__)

ORDER_HIDDEN = "order_numbers_hidden"  # ui.json: the reader turned the reading-order badges off
# what the status line says
SEVERAL = "{n} regions selected: a drag and the entries of Menu > Page act on all of them."
NOTHING_TO_CHANGE = "Nothing to change: the selected region(s) have it already."
DROPPED = "{n} regions dropped; Menu > Undo brings them back."
KIND_SET = "Kind set on {n} region(s). Menu > Undo takes it back."
SIZE_SET = "Text size set on {n} region(s). Menu > Undo takes it back."
PLACED = "Put at place {place} of {total} in the reading order. Menu > Undo takes it back."
PLACED_ALREADY = "The selected region(s) are at that place in the reading order already."
PLACED_ASKED = ("Put at place {place} of {total} in the reading order; {n} line(s) after it translated again. "
                "Menu > Undo takes it all back.")
ORDERING = "Reading order: click the bubbles in the order they are read, then choose Finish order in the Menu."
NAME_FIRST = "Give the book a name first (Menu > Series and Volume...)."
# the changes on several regions, taken back and made again (`TranslatorMixin._step_through` says them)
UNDONE = {"drops": "The dropped regions are back.", "kind": "Kind taken back.", "size": "Text size taken back."}
REDONE = {"drops": "Regions dropped again.", "kind": "Kind set again.", "size": "Text size set again."}
TAKEN_BACK.update(UNDONE)
MADE_AGAIN.update(REDONE)


def ask_dialog(make: Callable[[], asks.ValueDialog]) -> Any:
    """The answer of the question *make* opens (None: cancelled), once it is closed."""
    dialog = make()
    if dialog.winfo_exists():
        dialog.wait_window()
    return dialog.answer


def placed_order(regions: Sequence[Any], chosen: Sequence[Any], place: int) -> list[Any]:
    """The reading order *regions* with *chosen* among them (by identity) taken out and put back together, in their
    order, from *place* (1 the first) on."""
    moving = [r for r in regions if any(r is c for c in chosen)]
    rest = [r for r in regions if not any(r is c for c in chosen)]
    at = max(0, min(len(rest), int(place) - 1))
    return rest[:at] + moving + rest[at:]


def front_first(regions: Sequence[Any], dx: float, dy: float) -> list[Any]:
    """*regions* in the order to move them by (dx, dy): the one furthest along the move first, so that none is
    stored where another still is (the notes go by where a region is)."""
    return sorted(regions, key=lambda r: -((r.x0 + r.x1) * dx + (r.y0 + r.y1) * dy))


class SelectionMixin:
    """Several regions selected and acted on together, and the reading order on the boxes. A part of `app.App`."""

    _also_chosen: Sequence[Any] = ()  # (always replaced, never changed in place)

    def _init_selection(self) -> None:
        """The state of the selection and of the badges (made once: a language switch keeps them)."""
        self._also_chosen = []
        self._banding, self._pressed = False, None
        hidden = load_ui_flag(Path(self.settings.state_dir), ORDER_HIDDEN)
        self.order_numbers_var = tk.BooleanVar(self, value=not hidden)

    # ------------------------------------------------------------------ the selection
    def _toggle_chosen(self, region: Any) -> None:
        """Shift+click on *region*: added to the selection, or taken out of it (the next one is then the first)."""
        group = chosen_regions(self)
        if not any(r is region for r in group):
            self._set_chosen([*group, region])
        else:
            self._set_chosen([r for r in group if r is not region])
        self._say_selection()

    def _band_select(self, band: tuple[float, float, float, float]) -> None:
        """Shift+drag: the regions lying wholly inside the band (image pixels) added to the selection, in reading
        order."""
        regions = self._page_regions()
        inside = [regions[i] for i in area.boxes_within(band, [r.bbox for r in regions])]
        group = chosen_regions(self)
        self._set_chosen([*group, *(r for r in inside if not any(r is g for g in group))])
        self._say_selection()

    def _set_chosen(self, regions: Sequence[Any]) -> None:
        """*regions* selected, the first of them the one the editor opens on."""
        regions = list(regions)
        self._grip_box = None
        self._chosen_region = regions[0] if regions else None
        self._also_chosen = regions[1:]
        self._draw_chosen()

    def _say_selection(self) -> None:
        count = len(chosen_regions(self))
        if count > 1:
            self.say(SEVERAL, n=count)

    def _acting_on(self) -> list[Any]:
        """The selected regions a command of the Page menu acts on, or none (and the status line says why)."""
        if not self._editing() or self.busy or self.pipeline is None:
            return []
        if self._ordering is not None:
            self.say(ORDERING)
            return []
        group = [r for r in chosen_regions(self) if holds(self.last_result, r)]
        if not group:
            self.say(SELECT_FIRST)
        return group

    # ------------------------------------------------------------------ several at once, one change each
    def _drop_regions(self, regions: Sequence[Any]) -> None:
        """Delete with several selected: all of them dropped from the page on show as `_drop_region` drops one (each
        translation leaves the cache, each spot is remembered as not text), one change ("drops") that Ctrl+Z takes
        back."""
        result, pipeline = self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        regions = sorted((r for r in regions if holds(result, r)),
                         key=lambda r: -next(i for i, s in enumerate(result.regions) if s is r))  # (back in order)
        if not regions:
            return
        step = self._record("drops", result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, regions)
                done = sum(1 for r in regions if pipeline.drop_region(result, r))
                for i, r in enumerate(result.regions):  # numbered as the review list and the editor count them
                    r.order = i
                step.settle(pipeline, bool(done))
                self._post("result", result=result, edited=True)
                if done:
                    self._post("status", key=DROPPED, values={"n": done})
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def _restyle_regions(self, changes: Sequence[tuple[Any, RegionStyle]], kind: str, line: str = "") -> None:
        """Each region of *changes* of the page on show formatted with its style (T with several selected, Set text
        size...), its premises, note and translation as they are: stored with the book's premises, the page lettered
        again once, one change of *kind*; *line* ({n}: how many) said once it is done."""
        result, pipeline = self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        changes = [(r, s) for r, s in changes if holds(result, r) and (r.style or RegionStyle()) != s]
        if not changes:
            self.say(NOTHING_TO_CHANGE)
            return
        if pipeline.annotations is None:
            self.say(NO_BOOK)
            return
        step = self._record(kind, result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, [r for r, _s in changes])
                done = sum(1 for r, s in changes if pipeline.set_region_style(result, r, s))
                pipeline.rerender(result)
                step.settle(pipeline, bool(done))
                self._post("result", result=result, edited=True)
                if line:
                    self._post("status", key=line, values={"n": done})
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def _set_kinds(self, regions: Sequence[Any], kind: str) -> None:
        """*regions* of the page on show given the kind of text *kind* (a premise the model is told, and the
        lettering the series sheet gives that kind), their speaker, note and formatting as they are, as the editor's
        Save stores a kind: one change ("kind")."""
        result, pipeline = self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        regions = [r for r in regions if holds(result, r) and r.tag != kind]
        if not regions:
            self.say(NOTHING_TO_CHANGE)
            return
        if pipeline.annotations is None:
            self.say(NO_BOOK)
            return
        step = self._record("kind", result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, regions)
                done = sum(1 for r in regions if pipeline.set_region_note(result, r, r.speaker, kind,
                                                                           bool(r.continues), r.remark))
                pipeline.rerender(result)
                step.settle(pipeline, bool(done))
                self._post("result", result=result, edited=True)
                self._post("status", key=KIND_SET, values={"n": done})
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def _move_regions(self, regions: Sequence[Any], dx: int, dy: int) -> None:
        """Several selected moved together by (dx, dy) image pixels (a drag, Alt+arrows), each as `_move_region`
        moves one (read and translated again only where needed), the one furthest along first (`front_first`): one
        move for Ctrl+Z. Their frames stay at the new place until the regions are there."""
        result, pipeline = self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        regions = [r for r in regions if holds(result, r)]
        if not regions or not (dx or dy):
            self._grip_box = None
            self._draw_chosen()
            return
        step = self._record("move", result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, regions)
                ok = False
                for r in front_first(regions, dx, dy):
                    box = (r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy)
                    ok = pipeline.move_region(result, r, box, progress=lambda m: self._post("progress", text=m)) or ok
                if not ok:
                    self._post("status", key="Could not record the rectangle: give the book a name first (Menu > Series and Volume...).")
                step.settle(pipeline, ok)
                self._post("result", result=result)
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    # ------------------------------------------------------------------ the Page menu
    def set_kind_of_selection(self) -> None:
        """Page > Set kind...: the kind of text of the selected regions, one or several, asked for (`KindDialog`, the
        first one's kind shown first) and stored (`_set_kinds`)."""
        group = self._acting_on()
        if not group:
            return
        kind = ask_dialog(lambda: asks.KindDialog(self, len(group), group[0].tag))
        if kind is not None and not self.busy and all(holds(self.last_result, r) for r in group):
            self._set_kinds(group, kind)

    def set_size_of_selection(self) -> None:
        """Page > Set text size...: a fixed text size for the selected regions, one or several, or Auto (the largest
        that fits), asked for (`SizeDialog`) and stored as the editor's Size stores it (`_restyle_regions`)."""
        group = self._acting_on()
        if not group:
            return
        size = ask_dialog(lambda: asks.SizeDialog(self, len(group), (group[0].style or RegionStyle()).size))
        if size is not None and not self.busy and all(holds(self.last_result, r) for r in group):
            self._restyle_regions([(r, replace(r.style or RegionStyle(), size=int(size))) for r in group], "size",
                                  SIZE_SET)

    def place_in_order(self) -> None:
        """Page > Place in reading order...: the selected regions put at one place of the page's reading order, the
        others' order kept (`placed_order`), without clicking the whole page in order again; stored as the reading
        order tool stores an order (`Pipeline.set_reading_order`), one "order" change (Ctrl+Z)."""
        group = self._acting_on()
        if not group:
            return
        result = self.last_result
        regions = self._page_regions()
        chosen = [r for r in regions if any(r is g for g in group)]
        if not chosen:
            self.say(SELECT_FIRST)
            return
        now = next(i for i, r in enumerate(regions) if r is chosen[0]) + 1
        place = ask_dialog(lambda: asks.PlaceDialog(self, len(chosen), len(regions), now))
        if place is None or self.busy or self.last_result is not result or self._ordering is not None:
            return
        self._place_regions(chosen, int(place))

    def _place_regions(self, chosen: Sequence[Any], place: int, ask: bool = False) -> None:
        """*chosen* (regions of the page on show) at *place* of its reading order: the whole order stored, one change
        ("order"); the page shows it at once. With *ask* (a number typed on a region's plate in see-through mode,
        `see_edit.PlaceEntry`) the lines whose earlier lines the change made others - from the first place whose
        region changed on, as the translator is given them: the page's lines before each one in reading order - are
        asked of the translator again (`_ask_after_order`), but those the person corrected; the order and their new
        translations are one change, which Menu > Undo takes back whole."""
        result, pipeline = self.last_result, self.pipeline
        regions = self._page_regions()
        ordered = placed_order(regions, chosen, place)
        if all(a is b for a, b in zip(ordered, regions)):
            self.say(PLACED_ALREADY)
            return
        before = unit_states(pipeline, result.units)
        if not pipeline.set_reading_order(result, ordered):  # nothing can be kept under a name that names no book
            self.say(NAME_FIRST)
            return
        rest = [r for r in result.regions if not any(r is o for o in ordered)]
        result.regions = [*ordered, *rest]  # the order asked for (the pipeline's hints restart on each page unit)
        for i, r in enumerate(result.regions):
            r.order = i
        at = next(i for i, r in enumerate(ordered) if r is chosen[0]) + 1
        first = next(i for i, (a, b) in enumerate(zip(ordered, regions)) if a is not b)
        lines = [r for r in ordered[first:] if r.status == "translated" and r.tag != ERASE_ONLY
                 and not pipeline.corrected(result, r)] if ask else []
        if lines and getattr(pipeline, "translator", None) is not None:
            self._ask_after_order(result, lines, before, at, len(ordered))
            self._redisplay()
            return
        self._kept_at_once("order", result, before)
        self.say(PLACED, place=at, total=len(ordered))
        self._redisplay()

    def _ask_after_order(self, result: Any, lines: list[Any], before: list, place: int, total: int) -> None:
        """(`_place_regions` with *ask*) The *lines* of the page *result* asked of the translator again in the worker,
        one by one in reading order, each after the page's lines before it as they are by then (`Pipeline.ask_again`;
        the Japanese read first where the page came from the cache: `Pipeline.read_source`), each answer kept as the
        model's (`Pipeline.set_translation`, not the person's) and lettered as it comes; the order and those answers
        one "order" change (its stores before: *before*). The status line says "Asking the model..." meanwhile and
        then how many were translated again, or the model's error."""
        from ..messages import message_of
        from ..translate import TranslationError
        from .progress import rendered

        pipeline = self.pipeline
        _step, settle = self._kept_after_reading("order", result, before)
        self._go_busy()
        self.say("Asking the model...")

        def job() -> None:  # the worker
            done = 0
            try:
                last = max((i for i, r in enumerate(result.regions) if any(r is line for line in lines)), default=-1)
                for region in result.regions[:last + 1]:  # the lines before each one are its context: read them
                    if (region.status == "translated" and region.tag != ERASE_ONLY
                            and not str(region.source_text or "").strip()):
                        pipeline.read_source(result, region)
                for region in lines:
                    if not holds(result, region):
                        continue
                    text = pipeline.ask_again(result, region)
                    if text and text != region.translated_text and pipeline.set_translation(result, region, text,
                                                                                             edited=False):
                        done += 1
                        self._post("result", result=result, edited=True, quiet=True)
                self._post("status", key=PLACED_ASKED, values={"place": place, "total": total, "n": done})
            except TranslationError as e:
                self._post("status", key="No answer from the model: {error}", values={"error": rendered(message_of(e))})
            except Exception:  # noqa: BLE001 - the page stays as the order left it
                log.debug("the lines after a new reading order could not be asked again", exc_info=True)
            finally:
                settle()
                self._post("translate_done")

        self._jobs.put(job)

    # ------------------------------------------------------------------ the reading order on the boxes
    def _page_drawn(self) -> None:
        """The canvas's hook after every redraw: the reading-order badges, then the selection over them."""
        self._draw_order_badges()
        self._draw_chosen()

    def _draw_order_badges(self) -> None:
        """Each region's place in the page's reading order (`_page_regions`) in a small badge beside its box, in
        translator mode on the page it belongs to, unless the badges were turned off (`ORDER_HIDDEN`); not while the
        reading order is being set (the labels carry the numbers then)."""
        canvas = self.canvas
        canvas.delete(BADGE_TAG)
        var = getattr(self, "order_numbers_var", None)
        if var is None or not var.get() or self._ordering is not None or not self._editing():
            return
        regions = self._page_regions()
        if regions:
            canvas.draw_badges([(r.bbox, str(i + 1)) for i, r in enumerate(regions)])


__all__ = ["ORDER_HIDDEN", "SelectionMixin", "front_first", "placed_order"]
