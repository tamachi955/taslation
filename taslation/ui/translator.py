"""The Translator role, which the left pane's Edit turns on (`see_edit`, on the lettering laid over the viewer): its
tools (reading order, skip page, translate again, book settings, series sheet, review, find and replace, undo, redo),
the page's regions selected, moved, resized, rotated by a round handle as a word processor's shapes are (several
selected act as one change: `chosen_regions`, the rest in `selection`), edited (with the formatting of their
lettering, shown as it is set: `LivePreview`), added and dropped,
every one of those changes taken back and made again (Ctrl+Z, Ctrl+Y: `history`), the model asked again from the
editor (the Japanese read again first on a page shown from the cache), the editor taken through the page's regions in
reading order (Previous, Next), and a rendering the reader changed offered to the series sheet. (The hidden main
window keeps the strip and the page canvas these methods were written for, as the state they work on.)"""

from __future__ import annotations

import threading
from dataclasses import replace
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from PIL import Image

from ..annotations import CharacterSheet, RegionStyle
from ..bookid import generic_book_name
from ..bookname import entry_for
from ..cache import language_key
from ..i18n import _, load_ui_flag, load_ui_table, save_ui_entry, save_ui_flag
from ..messages import message_of
from ..notes import sheet_key
from ..pipeline import OWN_PART, unit_for
from ..render.fonts import font_families
from .font_memory import FontMemory
from ..render.slant import slanted_outline
from .. import review as checks
from ..review import rendering_changes, sheet_item_for
from ..translate import TranslationError
from ..translate.base import HINT_FOLLOWS, hint_support
from . import area, seethrough, theme
from .constants import FIRST_PAGE, THIS_PAGE
from .dialogs import caches as boxes
from .dialogs.review import DIRECTION_WORDS, EditBubbleDialog, ReviewDialog, review_rows
from .history import BookStep, Step, carry, owner, page_units, put_back, stores_differ, unit_states
from .layout import FlowBar
from .progress import rendered
from .series_scope import (ALL_VOLUMES, VolumeCount, change_volumes, changed_lines, changed_somewhere,
                           count_in_volumes, in_the_worker, series_volumes, volume_lines, volume_store)
from .sheet_changes import rename_edits, shown_pairs
from .tooltip import tip

# the text directions translator mode's T and its button go through on the selected region, in turn
DIRECTION_CYCLE = ("", "down", "up", "stacked")
# the spellcheck setting is off by default; turned on, its word lists come from an optional package that TASlation
# does not install. Where it is missing the editor says so once (ui.json SPELLING_SAID), and where the setting is
# turned off - no command line, never anything online
SPELLING_OFF = ("Spelling is not checked: the spellcheck setting is on, but the word lists it needs are an optional "
                "extra that TASlation does not install. To turn the setting off, open Settings..., press Open "
                "settings file and change spellcheck = true to spellcheck = false; it applies at the next start. This "
                "is said only once.")
SPELLING_SAID = "spelling_unavailable_said"
# the editor of a region whose translation was reused from an identical line before it (`linememo`), not asked for
REUSED_NOTE = "This translation was reused from an earlier identical line; the model was not asked. Ask again gives a fresh one."
# what the status line says on a click on the page that selects nothing
CLICK_HINT = ("Translator mode: click a region to select it, drag it to move it, its handles to resize it or its round "
              "handle to rotate it, double-click to edit it, drag on empty space to add one.")
FRAME_COLOUR = "#ffd400"  # the selected region's frame and handles (two-tone: `preview.EDGE` runs under it)
NEW_REGION_COLOUR, DRAG_TAG = "#4da3ff", "drag-rect"  # the rectangle a drag on empty space draws, two-tone too
BAND_TAG = "band-rect"  # the rubber band a Shift+drag draws to select the regions inside it (the selection's colour)
FRAMES_KEPT = 64  # turned frames kept (`_frame_of`), by region
HINT_COLOUR = theme.LIGHT["tool_hint"]  # the strip's line on what the pointer does (light: `theme.colour("tool_hint")`)
HAND = "hand2"  # the pointer over a region that a click selects
TOOLBAR_GAP = (10, 4)  # between the toolbar's groups and its rows (and the strip's)
# what the status line says once a change is taken back (Ctrl+Z) or made again (Ctrl+Y), by the kind of change
TAKEN_BACK = {"edit": "Edit taken back.", "move": "Move taken back.", "resize": "Resize taken back.",
              "rotate": "Rotation taken back.", "direction": "Text direction taken back.",
              "add": "The region you added is gone again.",
              "drop": "The dropped region is back.",
              "skip": "Skip page taken back.", "order": "Reading order taken back.",
              "again": "Translate again taken back: the earlier translations are back.",
              "paste": "Paste format taken back."}
MADE_AGAIN = {"edit": "Edit made again.", "move": "Move made again.", "resize": "Resize made again.",
              "rotate": "Rotation made again.", "direction": "Text direction made again.", "add": "Region added again.",
              "drop": "Region dropped again.", "skip": "Skip page made again.", "order": "Reading order made again.",
              "again": "Translate again made again: its translations are back.", "paste": "Paste format made again."}
# the changes a page is read again from the stores for, when they are taken back or made again: they touch no region
# of the window's (the page's regions were made anew by them)
REREAD_KINDS = frozenset({"add", "skip", "order", "again"})
PREVIEW_POLL_MS = 40  # how often the window looks for the editor's preview, while one is being lettered
NO_REGION = "This region is no longer on the page: nothing was changed."
# a rendering changed in the series sheet: the offer to give the lines already translated the new one, its buttons,
# and what is said once it is done
SHEET_OFFER = "{n} line(s) already translated use the series sheet's earlier rendering ({changes}). Give them the new one? Menu > Undo takes it back."
SHEET_APPLY = "Apply to the {n} line(s)"
SHEET_LEAVE = "Leave them as they are"
SHEET_APPLIED = "Applied to {n} translated line(s) on {pages} page(s). Menu > Undo takes it back."
# "Translate again" on a page with lines the person corrected (`CachedBubble.edited`): the question and its box to
# tick (`locales.features.corrections`)
AGAIN_KEEPS = ("Translate this page again? Its present translations are replaced, but for the {n} line(s) you "
               "corrected: they stay as they are.")
REPLACE_MINE_TOO = "Replace the lines I corrected too"
# ... and when other volumes of the series use the earlier rendering too (`_ask_sheet_renames`): under the offer, the
# volumes with their lines and the box that takes them too (with its button); or the offer for them alone
SHEET_OTHERS_TOO = ("Other volumes of the series use it too:\n{volumes}\n\nTick the box to give them the new one as "
                    "well. They are saved at once, and Menu > Undo does not reach them; a copy of each file as it was is kept "
                    "beside it (<file>.before-replace.<date>.json). To take it back, change the rendering back here and "
                    "apply it to all volumes, or put that copy back.")
SHEET_GIVE = "Give them the new one"
SHEET_OTHERS_ONLY = ("No line of this book uses the series sheet's earlier rendering ({changes}), but other volumes of "
                     "the series do:\n{volumes}\n\nGive them the new one? They are saved at once, and Menu > Undo does not "
                     "reach them; a copy of each file as it was is kept beside it (<file>.before-replace.<date>.json). "
                     "To take it back, change the rendering back here, or put that copy back.")
SHEET_WAIT_MS = 300  # how often the offer looks whether the window is free (a page at work) or the cache is open


ROLE_TABLE, ROLES_KEPT = "roles", 500  # ui.json: the role the reader chose for a book, by its name (the latest books)
ROLE_DELAY_MS = 400  # the Book box rests this long before the role for its book is decided



def chosen_role(state_dir: Any, book: str) -> str:
    """The role the reader chose for *book* ("reader" or "translator"); "" for none. Under another spelling of the
    same book too (`bookname.entry_for`: chosen before it was renamed to the one spelling)."""
    role = entry_for(load_ui_table(Path(state_dir), ROLE_TABLE), book)
    return role if role in ("reader", "translator") else ""


def remember_role(state_dir: Any, book: str, role: str) -> None:
    """*role*, chosen by the reader for *book*, kept in ui.json (book names only, nothing of their pages)."""
    if role in ("reader", "translator"):
        save_ui_entry(Path(state_dir), ROLE_TABLE, book, role, keep=ROLES_KEPT)


def start_role(translated: bool) -> str:
    """The role a book opens in with no choice of the reader's: translator mode while nothing of it is translated
    (there is work to check), reader mode once its pages are."""
    return "reader" if translated else "translator"


def holds(result: Any, region: Any) -> bool:
    """Whether *region* is one of the regions of the page *result*, by identity: `==` on regions reaches their masks."""
    return result is not None and any(r is region for r in result.regions)


SHIFT = 0x0001  # an event's state with Shift held


def shift_held(event: Any) -> bool:
    return bool(int(getattr(event, "state", 0) or 0) & SHIFT)


def chosen_regions(window: Any) -> list[Any]:
    """The regions selected on the page in translator mode: the selected one (`_chosen_region`, the one the editor
    opens on) first, then those Shift+click added (`_also_chosen`) that are still on the page on show; none while
    nothing is selected. With several, Drop the chosen regions, Text direction, Paste format, a drag and the Menu's
    Page > Set kind... and Set text size... act on all of them, each as one change (`selection`)."""
    primary = getattr(window, "_chosen_region", None)
    if primary is None:
        return []
    others = getattr(window, "_also_chosen", None) or []
    if not others:
        return [primary]
    result = getattr(window, "last_result", None)
    return [primary, *(r for r in others if r is not primary and holds(result, r))]


def group_offset(window: Any) -> tuple[int, int]:
    """How far the selected regions are being moved together (a drag, Alt+arrows) before they are stored: the
    selected one's `_grip_box` from its box."""
    box, region = getattr(window, "_grip_box", None), getattr(window, "_chosen_region", None)
    if box is None or region is None:
        return (0, 0)
    return (int(box[0] - region.x0), int(box[1] - region.y0))


def editor_regions(result: Any) -> list[Any]:
    """The regions the editor counts on the page *result* ("Bubble n of N") and goes through with Previous and Next:
    all but the dropped ones, in reading order."""
    return [] if result is None else [r for r in result.regions if r.status != "dropped"]


EDITOR_CROP_PAD = 6  # pixels of the page around a region in the editor's picture of it


def editor_crop(page: Image.Image | None, box: tuple[int, int, int, int],
                pad: int = EDITOR_CROP_PAD) -> Image.Image | None:
    """The region *box* of the capture *page* with a little of the page round it, for the editor: a new picture in
    memory, never written anywhere. None without a page or for a box off it."""
    if page is None:
        return None
    x0, y0 = max(0, int(box[0]) - pad), max(0, int(box[1]) - pad)
    x1, y1 = min(page.width, int(box[2]) + pad), min(page.height, int(box[3]) + pad)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return page.crop((x0, y0, x1, y1))


class LivePreview:
    """The region editor's preview of one region on the page on show: the page with every other region lettered
    (made once, in the worker, at the first change), the region erased and lettered on it with the text and the
    formatting the editor shows, the newest one asked for only. The picture takes the place of the page's own
    rendering until the editor closes: Save keeps it until the saved page comes, any other way out puts the page's
    own back. Not a change to undo, and nothing is stored."""

    def __init__(self, result: Any, region: Any):
        self.result, self.region = result, region
        self.before = result.image  # the page's own rendering, put back unless the editor saves
        self.mine: Any = None  # the preview's own picture on the page last (only that one is taken off again)
        self.bed: Any = None  # the page with every other region lettered (worker)
        # (number, text, style, the part set larger: the editor's, or `OWN_PART`): the newest request
        self.asked: tuple[int, str, RegionStyle, Any] | None = None
        self.made: tuple[int, Image.Image | None, Any] | None = None  # (number, picture, what the lettering did)
        self.serial = 0  # requests made so far
        self.shown = 0  # the newest request whose picture is on the page
        self.polling = False
        self.open = True


class TranslatorMixin:
    """Translator mode. A part of `app.App` (no `__init__`: the state it uses is made by `App.__init__`; the other
    parts are reached through ``self``)."""

    # ------------------------------------------------------------------ a rendering offered to the series sheet
    def _propose_renderings(self, changes: list[tuple[str, str]]) -> None:
        """The reader replaced a rendering in a translation (*changes*: the sheet's rendering, what the reader wrote):
        offer it as the series sheet's new rendering."""
        book, language = self.book_var.get().strip(), self.lang_var.get().strip()
        if not book or self.pipeline is None:
            return
        merged = self.pipeline.check_sheet()
        try:
            sheet = self.glossary_store.open(sheet_key(self.glossary_store, book), language)
        except OSError as e:  # the file is locked, or another series has its name
            self.say("Could not open the series sheet: {error}", error=e)
            return
        changed = False
        editor = getattr(self, "_editor", None)  # an editor open by now (Next): the question over it, its grab back after
        parent = editor if editor is not None and editor.winfo_exists() else self
        seethrough.asked(self)  # (see-through mode: the question the reader's Save brought takes the keys)
        for old, new in changes:
            item = sheet_item_for(merged, old) if merged is not None else None
            if item is None:
                continue
            question = _("You wrote \"{new}\" where the series sheet says \"{old}\". Use \"{new}\" from now on?")
            agreed = boxes.ask(parent, question.format(new=new, old=old), _("Use \"{new}\"").format(new=new),
                               _("Keep \"{old}\"").format(old=old))
            if parent is not self:
                try:
                    if parent.winfo_exists():
                        parent.grab_set()
                except tk.TclError:
                    pass
            if not agreed:
                continue
            kind, key = item
            if kind == "term":
                sheet.set(key, new)
            else:
                existing = sheet.get_character(key)
                if existing is None:
                    sheet.set_character(CharacterSheet(name=key, rendering=new))
                else:
                    existing.rendering = new
            changed = True
        if changed:
            try:
                sheet.save()
            except OSError as e:
                self.say("Could not save the series sheet: {error}", error=e)
                return
            pipeline = self.pipeline
            cache = getattr(pipeline, "cache", None)
            pairs = [(old, new) for old, new in changes if sheet_item_for(merged, old) is not None]
            if cache is not None and pairs:  # the pages translated before get the same spelling: one change for Ctrl+Z
                self._rename_in_book(pipeline, cache, pairs, lambda step: (
                    "Series sheet updated; changed in {n} translated line(s). New translations use it.",
                    {"n": len(step.edits)}))
            else:
                self.say("Series sheet updated; changed in {n} translated line(s). New translations use it.", n=0)
            self._jobs.put(lambda: self._refresh_premises(book, language))

    def _rename_in_book(self, pipeline: Any, cache: Any, pairs: list[tuple[str, str]],
                        line: Callable[[BookStep], tuple[str, dict[str, Any]]],
                        also: Callable[[], list[tuple[str, dict[str, Any]]]] | None = None) -> BookStep:
        """The worker gives every translated line of *cache* (the pipeline's) the new renderings of *pairs* (old ->
        new, whole words: `sheet_changes.rename_edits`), on what the cache holds then, as one change on no page in
        particular that Ctrl+Z takes back (`history.BookStep`, as a replacement across the book); the page on show is
        lettered again (`_stored`) and *line* of the step is said, or what went wrong. *also*, in the same job after
        it, gives the other volumes of the series the new renderings (saved at once, beyond Ctrl+Z:
        `series_scope.change_volumes`) and the lines that say so; *line* is not said then while this book had none."""
        step = BookStep(owner(pipeline))
        self.history.record(step, pipeline.settings.fingerprint_max_distance)
        result = self.last_result

        def job() -> None:
            try:
                cache.refresh()  # what another process saved meanwhile
                step.edits = cache.put_texts(rename_edits(cache, pairs))
                step.state = "done" if step.edits else "empty"
                lines = self._stored(pipeline, result, step.edits)
                elsewhere = also() if also is not None else []
                if not lines and (step.edits or not changed_somewhere(elsewhere)):
                    lines = [line(step)]
                self._post("find", lines=lines + elsewhere)
            finally:
                if step.state == "pending":
                    step.state = "failed"

        self._jobs.put(job)
        return step

    def _offer_sheet_renames(self, pairs: list[tuple[str, str]], book: str, language: str,
                             parent: tk.Misc | None = None, waited: bool = False) -> None:
        """The series sheet of *book* in *language* (open in its dialog, *parent*) gave terms or characters another
        rendering (*pairs*: old, new): when lines already translated have the old one, the reader is told how many and
        asked whether they get the new one (`SHEET_OFFER`); yes renames them as one change (`_rename_in_book`). The
        lines of the other volumes of the series kept in the language are counted first, in the worker
        (`series_scope`, as `taslation glossary apply` finds the volumes), and the question offers them too
        (`_ask_sheet_renames`: this book unless its box is ticked). The book's cache is opened by the worker first
        when the window holds another one; while a page is at work the question waits until it is done."""
        pairs = [(old, new) for old, new in pairs if old and new and old != new]
        pipeline = self.pipeline
        if not pairs or pipeline is None or not book or generic_book_name(book):
            return
        def later() -> None:
            self._offer_sheet_renames(pairs, book, language, parent, waited=True)

        cache = getattr(pipeline, "cache", None)
        if cache is None or cache.book != book or language_key(cache.language) != language_key(language):
            if waited:  # the worker opened what there is: nothing kept for the book in that language
                return
            opened: dict[str, bool] = {}
            model = self.model_var.get().strip()

            def open_it() -> None:  # the worker
                try:
                    self._ensure_cache(book, model, language)
                finally:
                    opened["done"] = True

            self._jobs.put(open_it)

            def look() -> None:
                if opened.get("done"):
                    later()
                else:
                    self.after(SHEET_WAIT_MS, look)

            self.after(SHEET_WAIT_MS, look)
            return
        if self.busy:  # a page at work: asked once it is done
            self.after(SHEET_WAIT_MS, lambda: self._offer_sheet_renames(pairs, book, language, parent, waited))
            return
        store, volume_language = volume_store(self, cache), cache.language

        def edits_of(volume: Any) -> list[Any]:
            return rename_edits(volume, pairs)

        def work() -> tuple[list[str], list[VolumeCount]]:  # the worker: the other volumes of the series, counted
            books = series_volumes(store, cache.book, volume_language)
            return books, count_in_volumes(store, books, volume_language, edits_of)

        def moved_on() -> bool:
            return self.pipeline is not pipeline or getattr(pipeline, "cache", None) is not cache

        def then(found: tuple[list[str], list[VolumeCount]]) -> None:
            if moved_on():
                return
            if self.busy:  # a page began meanwhile: asked once it is done
                self.after(SHEET_WAIT_MS, lambda: then(found))
                return
            books, counts = found
            self._ask_sheet_renames(pipeline, cache, pairs, parent, store, books, counts, edits_of, moved_on)

        in_the_worker(self, work, then)

    def _ask_sheet_renames(self, pipeline: Any, cache: Any, pairs: list[tuple[str, str]], parent: tk.Misc | None,
                           store: Any, books: list[str], counts: list[VolumeCount],
                           edits_of: Callable[[Any], list[Any]], moved_on: Callable[[], bool]) -> None:
        """The offer of `_offer_sheet_renames`, its lines counted in this book and, volume by volume, in the other
        volumes of the series (*counts*, `series_scope.count_in_volumes`). With none in another volume, the question of
        before; with some there too, the same question names each volume with its count, says that the other volumes
        are saved at once, beyond Ctrl+Z, and how to take them back, and its box "All volumes of the series" (unticked:
        this book only) takes them too; with lines in other volumes only, it asks about those. Yes renames as one
        change for Ctrl+Z in this book (`_rename_in_book`) and, with the other volumes, in each of them, saved at once
        with a copy of its file kept beside it (`series_scope.change_volumes`)."""
        here = len(rename_edits(cache, pairs))
        elsewhere = sum(c.lines for c in counts)
        if not here and not elsewhere:
            return
        box_parent = parent if parent is not None and parent.winfo_exists() else self
        changes = shown_pairs(pairs)
        seethrough.asked(self)  # (see-through mode: the question the reader's change of the sheet brought takes the keys)
        if not elsewhere:
            go, series = boxes.ask(box_parent, _(SHEET_OFFER).format(n=here, changes=changes),
                                   _(SHEET_APPLY).format(n=here), _(SHEET_LEAVE)), False
        elif not here:
            go, series = boxes.ask(box_parent, _(SHEET_OTHERS_ONLY).format(changes=changes, volumes=volume_lines(counts)),
                                   _(SHEET_APPLY).format(n=elsewhere), _(SHEET_LEAVE)), True
        else:
            text = (_(SHEET_OFFER).format(n=here, changes=changes) + "\n\n"
                    + _(SHEET_OTHERS_TOO).format(volumes=volume_lines(counts)))
            go, series = boxes.ask_choice(box_parent, text, _(ALL_VOLUMES), _(SHEET_GIVE), _(SHEET_LEAVE))
        if not go or moved_on():
            return  # (the window moved on while the question was up)
        self.say("Storing your changes...")
        also = ((lambda: changed_lines(change_volumes(store, books, cache.language, edits_of))) if series else None)
        self._rename_in_book(pipeline, cache, pairs, lambda step: (
            (SHEET_APPLIED, {"n": len(step.edits), "pages": len({e.fingerprint for e in step.edits})})
            if step.edits else ("Nothing was changed.", {})), also=also)

    def _refresh_premises(self, book: str, language: str) -> None:
        """The worker: the pipeline takes the book's premises again; a store that cannot be opened is said."""
        try:
            self._job_refresh_premises(book, language)
        except OSError as e:
            self._post("status", key="Could not open the book's premises: {error}", values={"error": str(e)})

    # ------------------------------------------------------------------ the tools
    def _build_translator_tools(self, parent: tk.Misc) -> None:
        """Translator mode's strip under the hidden toolbar: its tools in groups (reading order, skip page, translate
        again; book settings, series sheet, review, my corrections, lines to review; find and replace, the selected
        region's text direction, undo, redo), never seen - the left pane's Edit menu has them (`see_edit`) -, kept for
        the state they hold (`_sync_tools`, enabled in the Translator role)."""
        strip = ttk.Frame(parent)
        ttk.Separator(strip, orient="horizontal").pack(fill="x", padx=8)
        tools = FlowBar(strip, gap=TOOLBAR_GAP)
        tools.pack(fill="x")
        self.tool_btns = []
        chunks = (((_("Reading order"), self.toggle_order, _("Click the text areas in the order they are read.")),
                   (_("Skip page"), self.toggle_skip, _("Leave this page out: nothing on it is translated.")),
                   (_("Translate again"), self.retranslate_page,
                    _("Replace this page's kept translations with new ones."))),
                  ((_("Book settings..."), self.open_book_settings, _("Settings that apply to this book only.")),
                   (_("Series sheet..."), self.open_glossary,
                    _("The names, terms and style the translations of this series keep to.")),
                   (_("Review..."), self.open_review, _("List the text areas of this page that are worth a look.")),
                   (_("My corrections..."), self.open_corrections,
                    _("List the translations you corrected in this book, page by page.")),
                   (_("Lines to review..."), self.open_lines_to_review,
                    _("List the lines of the whole book that are worth a look, page by page."))),
                  ((_("Find and replace..."), self.open_find_replace,
                    _("Search this book's translations and replace a word on every page.")),
                   (_("Text direction"), self._turn_direction,
                    _("Change the selected region's text direction: Auto, rotated 90°, rotated 270°, stacked, and Auto again.")),
                   (_("Undo"), self.undo_edit, _("Take back your last change.")),
                   (_("Redo"), self.redo_edit, _("Make the last change again."))))
        for chunk in chunks:
            group = tools.group()
            for i, (text, command, explanation) in enumerate(chunk):
                button = ttk.Button(group, text=text, command=command)
                button.pack(side="left", padx=(4 if i else 0, 0))
                tip(explanation, button)
                self.tool_btns.append(button)
        self._tool_strip, self.tools_bar = strip, tools

    def _sync_tools(self) -> None:
        """Translator mode's tools follow the role: the strip under the toolbar shows while the Translator role is
        chosen, and its tools work in translator mode only."""
        translator = self.role_var.get() == "translator"
        state = "normal" if translator else "disabled"
        for b in self.tool_btns:
            b["state"] = state
        strip = getattr(self, "_tool_strip", None)
        if strip is None:
            return
        try:
            shown = bool(strip.winfo_manager())
            if translator and not shown:
                strip.pack(fill="x")
            elif not translator and shown:
                strip.pack_forget()
        except tk.TclError:
            pass

    def _label_order(self, text: str) -> None:
        """The reading-order tool's label: "Reading order", or "Finish order" while an order is being set."""
        self.tool_btns[0]["text"] = text

    def _page_to_work_on(self) -> bool:
        """Whether the tools for the page on show have a page to act on: one translated (`_result_on_show`); else a
        line says what to do first."""
        if self.last_result is None or self.pipeline is None:
            self.say(FIRST_PAGE)
            return False
        if not self._result_on_show():
            self.say(THIS_PAGE)
            return False
        return True

    def _end_order(self) -> bool:
        """The reading order being set goes, with what was clicked (its regions belong to the page it began on).
        Whether one was being set."""
        if self._ordering is None:
            return False
        self._ordering = None
        self._label_order(_("Reading order"))
        return True

    def toggle_order(self) -> None:
        """Translator mode: click the regions in reading order, then press the button again. Ctrl+Z takes the order
        back."""
        if self._ordering is None:
            if not self._page_to_work_on():
                return
            self._ordering = []
            self._chosen_region = None
            self._label_order(_("Finish order"))
            self.say("Reading order: click the bubbles in the order they are read, then choose Finish order in the Menu.")
            self._redisplay()
            return
        ordered = self._ordering
        self._end_order()
        result, pipeline = self.last_result, self.pipeline
        before = unit_states(pipeline, result.units) if ordered and result is not None else []
        if ordered and pipeline.set_reading_order(result, ordered):
            self._kept_at_once("order", result, before)
            self.say("Reading order saved for {n} region(s). Translate again applies it.", n=len(ordered))
        elif ordered:  # nothing can be kept under a name that names no book
            self.say("Give the book a name first (its series in the Series field, and its volume beside it if it has one).")
        self._redisplay()

    def _kept_at_once(self, kind: str, result: Any, before: list) -> Step:
        """A change the window's thread made at once on the page *result* (*before*: the stores before it), kept in
        the history for Ctrl+Z. The jobs queued before it have run or write other pages: what the stores hold now is
        what it left."""
        pipeline = self.pipeline
        step = self._record(kind, result)
        step.before = before
        step.after = unit_states(pipeline, result.units)
        step.state = "done" if stores_differ(step.before, step.after) else "empty"
        return step

    def _kept_after_reading(self, kind: str, result: Any, before: list | None = None
                            ) -> tuple[Step, Callable[[], None]]:
        """A change on the page *result* whose page the jobs just queued read again (Skip page, Translate again), kept
        in the history for Ctrl+Z: the stores before it (*before*, or as the worker finds them when the reading
        starts) and after it, in the worker; the reading's new page replaces *result* in the window, so the stores
        are compared by *result*'s units. One that changed nothing (Stop, a frame with no page) is not kept. Returns
        the step and the job that settles it, to queue after the reading."""
        pipeline = self.pipeline
        step = self._record(kind, result)
        units = list(result.units)
        if before is not None:
            step.before = before

        def settle() -> None:  # the worker, once the page is read again
            step.after = unit_states(pipeline, units)
            step.state = "done" if stores_differ(step.before, step.after) else "empty"

        return step, settle

    def toggle_skip(self) -> None:
        """Translator mode: nothing on this page (an advertisement, the viewer's own panel) is translated. The page
        is read again; the status line says what was done once it is. Ctrl+Z takes it back."""
        if self.busy or not self._page_to_work_on():
            return
        result, pipeline = self.last_result, self.pipeline
        skip = not pipeline.is_skipped(result)
        before = unit_states(pipeline, result.units)
        if pipeline.set_page_skip(result, skip):
            _step, settle = self._kept_after_reading("skip", result, before)
            self._start_translate(result.original, complete=True)
            self._jobs.put(settle)
            if skip:
                self._jobs.put(lambda: self._post("status", key="Page marked as skipped: nothing on it is translated."))
            else:
                self._jobs.put(lambda: self._post("status", key="Page no longer skipped."))
        else:  # nothing can be kept under a name that names no book
            self.say("Give the book a name first (its series in the Series field, and its volume beside it if it has one).")

    def retranslate_page(self) -> None:
        """Translator mode's "Translate again": the page is translated again with the premises as they
        are now, and what that translates replaces its cached translations; a job that translates nothing (Stop, a new
        page, Ollama down) leaves them as they were (`_job_translate`). The lines the person corrected
        (`CachedBubble.edited`) stay as they are, and the model is not asked for them, unless the question's box
        "Replace the lines I corrected too" is ticked (it is asked only on a page that has some). The page may have
        moved on, or a job begun, while the question was up. Ctrl+Z puts the translations it replaced back."""
        if self.busy or self.pipeline is None or not self._page_to_work_on():
            return
        result = self.last_result
        counted = getattr(self.pipeline, "corrections_on", None)
        mine = counted(result) if counted is not None else 0
        if mine:
            go, replace = boxes.ask_choice(self, _(AGAIN_KEEPS).format(n=mine), _(REPLACE_MINE_TOO),
                                           _("Translate again"), _("Cancel"))
        else:
            go = boxes.ask(self, _("Translate this page again? Its present translations are replaced."),
                           _("Translate again"), _("Cancel"))
            replace = False
        if not go:
            return
        if self.busy or self.pipeline is None or self.last_result is not result:
            return
        pipeline = self.pipeline
        step, settle = self._kept_after_reading("again", result)
        units = list(result.units)

        def begin() -> None:  # the worker, as the reading starts: the translations it replaces
            step.before = unit_states(pipeline, units)

        self._jobs.put(begin)
        self._start_translate(result.original, complete=True, again=result, **({"replace_edited": True} if replace else {}))
        self._jobs.put(settle)

    def _speaker_names(self) -> list[str]:
        """The speakers the series sheet knows, for the editor's list; none (and the status line says why) when the
        sheet cannot be opened."""
        book = self.book_var.get().strip()
        if not book:
            return []
        try:
            language = self.lang_var.get().strip() or "English"
            return self.glossary_store.open(sheet_key(self.glossary_store, book), language).speaker_names()
        except OSError as e:  # the file is locked, or another series has its name
            self.say("Could not open the series sheet: {error}", error=e)
            return []

    # ------------------------------------------------------------------ the role a book opens in
    def _book_for_role(self) -> None:
        """The Book box changed: the role for the book it names is decided once the box rests (`_decide_role`)."""
        job = getattr(self, "_role_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._role_job = self.after(ROLE_DELAY_MS, self._decide_role)

    def _decide_role(self) -> None:
        """A book opens: in the role the reader chose for it, else in translator mode while it has no translations yet
        and in reader mode once its pages are translated (counted in a thread of its own: `_start_role_known`). A name
        that names no book, and the book already decided for, change nothing."""
        self._role_job = None
        book = self.book_var.get().strip()
        if not book or generic_book_name(book) or book == getattr(self, "_role_book", ""):
            return
        self._role_book = book
        chosen = chosen_role(self.settings.state_dir, book)
        if chosen:
            self._apply_role(chosen, chosen=True)
            return
        language = self.lang_var.get().strip() or "English"
        store = self.store

        def count() -> None:
            try:
                pages = store.page_count(book, language)
            except Exception:  # noqa: BLE001 - cannot tell: the role stays
                pages = None
            self._post("start_role", book=book, pages=pages)

        threading.Thread(target=count, daemon=True).start()

    def _start_role_known(self, data: dict[str, Any]) -> None:
        """The book's translated pages are counted: its role, unless the box names another book by now or the reader
        has chosen one for it meanwhile."""
        book, pages = data.get("book", ""), data.get("pages")
        if pages is None or book != self.book_var.get().strip() or chosen_role(self.settings.state_dir, book):
            return
        self._apply_role(start_role(int(pages) > 0), chosen=False)

    def _apply_role(self, role: str, chosen: bool) -> None:
        """The role a book opens in (*chosen*: the reader's for it). In see-through mode, where the Translator role is
        the left pane's Edit (`see_edit`), only the reader's own choice for the book: Edit stays as the start had it
        otherwise (off, unless the start asked for the Translator role)."""
        if getattr(self, "_see_hidden", False) and not chosen:
            return
        if self.role_var.get() == role:
            return
        self.role_var.set(role)
        self._on_role_changed(chosen=False)
        if not chosen:  # why it changed by itself
            self.say("This book has no translations yet, so it opens in translator mode." if role == "translator"
                     else "This book's pages are translated, so it opens in reader mode.")

    def _on_role_changed(self, chosen: bool = True) -> None:
        """The role changed: the reader *chose* it (kept for the book in the Book box, `remember_role`, which opens in
        it next time), or the book's start set it (`_apply_role`)."""
        book = self.book_var.get().strip()
        if chosen and book and not generic_book_name(book):
            remember_role(self.settings.state_dir, book, self.role_var.get())
        self._sync_tools()
        if self.role_var.get() != "translator":
            self._close_find()
        if self._ordering is not None:
            self._on_escape()
        self._chosen_region = None
        self._redisplay()
        from .see_edit import EDIT_OFF, EDIT_ON

        self.say(EDIT_ON if self.role_var.get() == "translator" else EDIT_OFF)
        if self.role_var.get() == "translator":
            self._complete_on_show()

    def _complete_on_show(self) -> None:
        """Translator mode came on over a page taken from the cache in reader mode: the regions found on it that the
        cache has no bubble for were never read ("unmatched"; most are pieces of the drawing judged no text,
        whose judgement the cache does not keep). The page is read again as translator mode reads a page
        (`translate_now`: those regions read and judged, a line among them translated), so that they are outlined
        and labelled for what they are - or not at all (`_page_regions`). Not while a job runs."""
        result = self.last_result
        if (result is None or not self.ready or self.busy
                or not any(r.status == "unmatched" for r in result.regions)):
            return
        self.after_idle(self.translate_now)

    # ------------------------------------------------------------------ the regions under the pointer
    def _editing(self) -> bool:
        """Whether the page's regions are edited (translator mode, Edit on, and the page on show is the one they
        belong to)."""
        return self.role_var.get() == "translator" and self._result_on_show()

    def _turn_of(self, region: Any) -> float:
        """The slant *region* is lettered at: the reader's (`RegionStyle.slant`, the editor's Slant), else its own
        (`TextRegion.angle`)."""
        style = getattr(region, "style", None)
        if style is not None and style.slant is not None:
            return float(style.slant)
        return float(getattr(region, "angle", 0.0) or 0.0)

    def _frame_of(self, region: Any) -> area.Corners:
        """The frame *region* is lettered in (image pixels): its box when upright, else the turned frame
        (`slanted_outline` at `_turn_of`), kept while the region, its box, mask and slant stay as they are."""
        angle = self._turn_of(region)
        if not angle:
            return area.box_corners(region.bbox)
        key = (region.bbox, angle, id(region.mask))
        kept = getattr(self, "_frame_cache", None)
        if not isinstance(kept, dict):  # by region: several selected are drawn at every motion of a drag
            kept = self._frame_cache = {}
        found = kept.get(id(region))
        if found is not None and found[0] == key and found[1] is region:
            return found[2]
        corners = [(float(x), float(y)) for x, y in slanted_outline(region, angle)]
        if len(kept) >= FRAMES_KEPT:
            kept.clear()
        kept[id(region)] = (key, region, corners)
        return corners

    def _shown_frame(self, region: Any) -> tuple[area.Corners, bool]:
        """The selected region's frame as it shows now (image pixels) and whether it is upright: turned about its
        middle while its rotate handle is dragged, moved with it while it is moved, and while it is resized the frame
        the new box is lettered in (`area.full_frame`: a resized region is a rectangle of the reader's)."""
        frame = self._frame_of(region)
        turn = getattr(self, "_turn", None)
        if turn is not None:
            change = turn["angle"] - turn["start"]
            return (area.turn_corners(frame, change) if change else frame), not turn["angle"]
        angle = self._turn_of(region)
        box = self._grip_box
        if box is None:
            return frame, not angle
        if (box[2] - box[0], box[3] - box[1]) == (region.width, region.height):
            return area.shift_corners(frame, box[0] - region.x0, box[1] - region.y0), not angle
        return area.full_frame(box, angle), not angle

    def _grip_of(self, x: float, y: float) -> str | None:
        """What a press at the canvas point (x, y) takes hold of on the selected region's frame: its rotate handle
        ("rotate"), a handle (named in the frame's own directions), "move" or None. With several selected, which have
        no handles, "move" inside any of their frames (they move together), else None."""
        region = self._chosen_region
        if region is None or self.last_result is None:
            return None
        group = chosen_regions(self)
        if len(group) > 1:
            for r in group:
                corners = [area.to_canvas(px, py, self.canvas.scale, self.canvas.offset) for px, py in self._frame_of(r)]
                if area.inside_frame(corners, x, y):
                    return "move"
            return None
        corners = [area.to_canvas(px, py, self.canvas.scale, self.canvas.offset) for px, py in self._frame_of(region)]
        return area.grip_on_frame(corners, x, y, room=self.canvas.room())

    def _page_grip(self, grip: str | None) -> str | None:
        """The handle of the region's upright box that *grip*, a handle of its frame, resizes (`area.page_handle`:
        itself on an upright frame); any other grip as it is."""
        region = self._chosen_region
        if grip not in area.HANDLES or region is None:
            return grip
        return area.page_handle(grip, self._frame_of(region))

    def _choose(self, region: Any) -> None:
        """Translator mode: select *region* on the page alone (None: nothing; the regions Shift added go too)."""
        self._chosen_region = region
        self._also_chosen = []
        self._draw_chosen()

    def _draw_chosen(self) -> None:
        """Over the page after every redraw (and when the selection changes): the selected region (`_draw_frame`)."""
        self._draw_frame()

    def _draw_frame(self) -> None:
        """The selected region's frame with its eight handles and its rotate handle, where it is or where it is being
        dragged or turned to (`_shown_frame`): an upright region's box, a slanted one's turned frame (the slant the
        reader set, or its own) with the handles on it, as a word processor draws a turned shape. Several selected:
        each one's frame alone, without handles, moved with the others while they are dragged or nudged."""
        self.canvas.delete("chosen")
        region = self._chosen_region
        group = chosen_regions(self) if region is not None else []
        if len(group) > 1 and self._editing() and self.last_result is not None:
            dx, dy = group_offset(self)
            for r in group:
                if self._turn_of(r):
                    self.canvas.draw_turned_frame(area.shift_corners(self._frame_of(r), dx, dy), "chosen",
                                                  colour=FRAME_COLOUR, with_handles=False)
                else:
                    self.canvas.draw_frame((r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy), "chosen", colour=FRAME_COLOUR,
                                           with_handles=False)
            return
        if region is not None and self._editing() and self.last_result is not None:
            frame, upright = self._shown_frame(region)
            if upright:
                self.canvas.draw_frame(self._grip_box or region.bbox, "chosen", colour=FRAME_COLOUR)
            else:
                self.canvas.draw_turned_frame(frame, "chosen", colour=FRAME_COLOUR)
            self.canvas.draw_rotate_handle(frame, "chosen", colour=FRAME_COLOUR)

    def _on_motion(self, e: tk.Event) -> None:
        """Translator mode: the pointer shows what a press would do there - circling arrows on the rotate handle of
        the selected region (`area.ROTATE_CURSORS`, the first this Tk has), a resize cursor on one of its handles (the
        way the handle points on the page), the move cursor on it, a hand on any other region (a click selects it,
        or while the reading order is set, numbers it), a cross on the page's empty space (a drag adds a region)."""
        cursor = ""
        wanted: tuple[str, ...] = ()
        if self._editing() and not self.busy:
            grip = self._grip_of(e.x, e.y) if self._ordering is None else None
            if grip == "rotate":
                wanted = area.ROTATE_CURSORS
            elif grip is not None:
                cursor = area.CURSORS[self._page_grip(grip)]
            elif self.canvas.inside(e.x, e.y):
                if self._region_at(*self.canvas.to_image_coords(e.x, e.y)) is not None:
                    cursor = HAND
                elif self._ordering is None:
                    cursor = area.CURSORS[None]
        wanted = wanted or (cursor,)
        if str(self.canvas.cget("cursor")) in wanted:
            return
        for name in wanted:
            try:
                self.canvas.configure(cursor=name)
                return
            except tk.TclError:  # a cursor this system does not have: the next one, or the one there stays
                continue

    def _on_press(self, e: tk.Event) -> None:
        """A press on the page in translator mode takes hold of what is there (`_grip_of`): a handle or the rotate
        handle of the selected region, the selection to move it, else the region there, which is selected (none on
        empty space). With Shift held anywhere but on a handle, the release decides: a click adds the region there to
        the selection or takes it out of it, a drag draws a rubber band (`_banding`; `selection`)."""
        self.canvas.focus_set()
        self._drag_start = (e.x, e.y)
        if self._drag_rect is not None:
            self.canvas.delete(self._drag_rect)
            self._drag_rect = None
        self._banding, self._pressed = False, None
        if not self._editing() or self._ordering is not None or self.last_result is None or self.busy:
            return
        self._grip = self._grip_start = self._grip_box = self._turn = None
        grip = self._grip_of(e.x, e.y)
        if shift_held(e) and grip not in (*area.HANDLES, "rotate"):
            self._banding = True
            return
        if grip == "move" and len(chosen_regions(self)) > 1:  # a click without a drag selects the one there alone
            self._pressed = self._region_at(*self.canvas.to_image_coords(e.x, e.y))
        if grip is None:  # off the selected region: the region there is selected (and held to be moved), or none
            region = self._region_at(*self.canvas.to_image_coords(e.x, e.y)) if self.canvas.inside(e.x, e.y) else None
            if region is not self._chosen_region or len(chosen_regions(self)) > 1:
                self._choose(region)
            grip = "move" if region is not None else None
        if grip is not None and self._chosen_region is not None:
            self._grip = grip
            self._grip_start = area.to_image(e.x, e.y, self.canvas.scale, self.canvas.offset)
            if grip == "rotate":  # the angle follows the pointer round the frame's middle (`area.turn_angle`)
                corners = [area.to_canvas(x, y, self.canvas.scale, self.canvas.offset)
                           for x, y in self._frame_of(self._chosen_region)]
                start = self._turn_of(self._chosen_region)
                self._turn = {"start": start, "angle": start, "centre": area.frame_centre(corners),
                              "press": (float(e.x), float(e.y))}

    def _on_drag(self, e: tk.Event) -> None:
        if self._drag_start is None or not self._editing():
            return
        if getattr(self, "_banding", False):  # Shift: the rubber band, in the selection's colour
            if self._drag_rect is not None:
                self.canvas.delete(self._drag_rect)
            self.canvas.edged_rectangle(self._drag_start[0], self._drag_start[1], e.x, e.y, FRAME_COLOUR, BAND_TAG,
                                        width=1, dash=(3, 2))
            self._drag_rect = BAND_TAG
            return
        group = chosen_regions(self)
        if self._grip == "move" and self._grip_start is not None and len(group) > 1:  # several move together
            assert self.last_result is not None
            now = area.to_image(e.x, e.y, self.canvas.scale, self.canvas.offset)
            dx, dy = area.shift_within([r.bbox for r in group], now[0] - self._grip_start[0],
                                       now[1] - self._grip_start[1], self.last_result.original.size)
            box = self._chosen_region.bbox
            self._grip_box = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
            self._draw_frame()
            return
        if self._grip is not None and self._grip_start is not None and self._chosen_region is not None:
            assert self.last_result is not None
            turn = getattr(self, "_turn", None)
            if self._grip == "rotate" and turn is not None:  # Shift: steps of 15 degrees
                turn["angle"] = area.turn_angle(turn["start"], turn["centre"], turn["press"], (e.x, e.y),
                                                steps=bool(int(getattr(e, "state", 0) or 0) & 0x0001))
                self._draw_frame()
                status = getattr(self, "status", None)
                if status is not None:
                    angle = turn["angle"]
                    status(lambda: f"{_('Slant:')} {angle:g}°")
                return
            now = area.to_image(e.x, e.y, self.canvas.scale, self.canvas.offset)
            self._grip_box = area.drag(self._chosen_region.bbox, self._page_grip(self._grip), self._grip_start, now,
                                       self.last_result.original.size, area.MIN_REGION)
            self._draw_frame()  # the marks over the page stay as they are while it is dragged
            return
        if self._drag_rect is not None:
            self.canvas.delete(self._drag_rect)
        self.canvas.edged_rectangle(self._drag_start[0], self._drag_start[1], e.x, e.y, NEW_REGION_COLOUR, DRAG_TAG,
                                    dash=(4, 2))
        self._drag_rect = DRAG_TAG  # the rectangle and its dark edge, deleted together

    def _cancel_drag(self) -> bool:
        """Esc while the pointer drags: the drag ends with nothing changed - the region's frame back where it was,
        a rectangle being drawn gone. Whether a drag was on."""
        if getattr(self, "_drag_start", None) is None or (self._grip is None and self._drag_rect is None):
            return False
        self._drag_start = None
        self._grip = self._grip_start = self._grip_box = self._turn = None
        if self._drag_rect is not None:
            self.canvas.delete(self._drag_rect)
            self._drag_rect = None
        self._draw_frame()
        return True

    def _on_double(self, e: tk.Event) -> None:
        """Translator mode: a double-click on a region opens the editor; anywhere else it is a second click."""
        region = None
        if self._editing() and self._ordering is None and self.last_result is not None and self.canvas.inside(e.x, e.y):
            region = self._region_at(*self.canvas.to_image_coords(e.x, e.y))
        if region is None:
            self._on_press(e)
            return
        self._drag_start = None
        self._choose(region)
        self._edit_chosen()

    def _edit_chosen(self) -> None:
        """Enter (or a double-click): the editor on the selected region."""
        if self._chosen_region is not None and self._editing() and not self.busy:
            self._open_editor(self._chosen_region)

    def _drop_chosen(self) -> None:
        """Delete: the selected region is dropped (Ctrl+Z brings it back); several selected are dropped together, one
        change (`_drop_regions`)."""
        region = self._chosen_region
        if region is not None and self._editing() and not self.busy:
            group = chosen_regions(self)
            self._choose(None)
            if len(group) > 1:
                self._drop_regions(group)
            else:
                self._drop_region(region)

    def _on_release(self, e: tk.Event) -> None:
        start, self._drag_start = self._drag_start, None
        grip, self._grip, self._grip_start = self._grip, None, None
        turn, self._turn = getattr(self, "_turn", None), None
        banding, self._banding = getattr(self, "_banding", False), False
        pressed, self._pressed = getattr(self, "_pressed", None), None
        if self._drag_rect is not None:
            self.canvas.delete(self._drag_rect)
            self._drag_rect = None
        if start is None:
            return
        moved = abs(e.x - start[0]) > 6 or abs(e.y - start[1]) > 6
        if not self._editing():
            return
        if self.last_result is None or self.busy or self.pipeline is None:
            return
        if self._ordering is not None:
            if not moved:
                x, y = self.canvas.to_image_coords(e.x, e.y)
                region = self._region_at(x, y)
                if region is not None and not any(r is region for r in self._ordering):
                    self._ordering.append(region)
                    self._redisplay()
            return
        if banding:  # Shift: a click adds the region there or takes it out, a band adds the regions inside it
            if moved:
                (x0, y0), (x1, y1) = self.canvas.to_image_coords(*start), self.canvas.to_image_coords(e.x, e.y)
                self._band_select((x0, y0, x1, y1))
            else:
                region = (self._region_at(*self.canvas.to_image_coords(e.x, e.y))
                          if self.canvas.inside(e.x, e.y) else None)
                if region is not None:
                    self._toggle_chosen(region)
            return
        if grip == "move" and len(chosen_regions(self)) > 1:  # the selection held: moved together, or one chosen
            region, box = self._chosen_region, self._grip_box
            nudged = abs(e.x - start[0]) > 2 or abs(e.y - start[1]) > 2
            if region is not None and box is not None and nudged and box != region.bbox:
                self._move_regions(chosen_regions(self), box[0] - region.x0, box[1] - region.y0)
            else:
                self._grip_box = None
                if pressed is not None and not nudged:
                    self._choose(pressed)
                else:
                    self._draw_chosen()
            return
        if grip == "rotate":  # the region turned: its slant stored as the editor's Slant stores it
            region = self._chosen_region
            if region is not None and turn is not None and turn["angle"] != turn["start"]:
                self._rotate_region(region, turn["angle"])
            else:
                self._draw_chosen()
            return
        if grip is not None:  # the selected region was held: moved or resized, or only selected
            region, box = self._chosen_region, self._grip_box
            nudged = abs(e.x - start[0]) > 2 or abs(e.y - start[1]) > 2
            if region is not None and box is not None and nudged and box != region.bbox:
                self._move_region(region, box)  # its outline stays at the new box until the region is there
            else:
                self._grip_box = None
                self._draw_chosen()
            return
        if moved:
            (x0, y0), (x1, y1) = self.canvas.to_image_coords(*start), self.canvas.to_image_coords(e.x, e.y)
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            if x1 - x0 >= area.MIN_REGION and y1 - y0 >= area.MIN_REGION:
                self._add_region((x0, y0, x1, y1))
            return
        self.say(CLICK_HINT)

    def _rotate_region(self, region: Any, angle: float) -> None:
        """The rotate handle let go at *angle*: the region's slant set to it (`RegionStyle.slant`, what the editor's
        Slant field sets, Auto unticked), through the editor's Save (`_restyle`)."""
        self._restyle(region, replace(getattr(region, "style", None) or RegionStyle(), slant=float(angle)), "rotate")

    def _turn_direction(self) -> None:
        """T (and the strip's Text direction): the selected region's text direction, the next of `DIRECTION_CYCLE`
        (Auto, rotated 90°, rotated 270°, stacked; "horizontal" goes on as Auto does), stored as the editor's Text
        direction stores it (`_restyle`); the status line names it. Several selected all take the direction after the
        selected one's, one change (`_restyle_regions`). Without a selected region a line says to select one."""
        region = self._chosen_region
        if not self._editing() or self.busy:
            return
        if region is None:
            self.say("Select a region first (click it).")
            return
        style = getattr(region, "style", None) or RegionStyle()
        now = DIRECTION_CYCLE.index(style.direction) if style.direction in DIRECTION_CYCLE else 0
        direction = DIRECTION_CYCLE[(now + 1) % len(DIRECTION_CYCLE)]
        group = chosen_regions(self)
        if len(group) > 1:
            self._restyle_regions([(r, replace(getattr(r, "style", None) or RegionStyle(), direction=direction))
                                   for r in group], "direction")
        else:
            self._restyle(region, replace(style, direction=direction), "direction")
        self._jobs.put(lambda: self._post("status", key="Text direction: {direction}",
                                          values={"direction": _(DIRECTION_WORDS[direction])}))

    def _restyle(self, region: Any, style: RegionStyle, kind: str) -> None:
        """The region's formatting set to *style* from the page (the rotate handle, T), its other premises, its note
        and its translation as they are, through the editor's Save (`_edit_region`): stored with the book's
        premises, the page lettered again, one change of *kind* to take back (Ctrl+Z)."""
        data = {"text": region.translated_text, "speaker": region.speaker, "kind": region.tag,
                "continues": bool(region.continues), "note": region.remark, "reader_note": region.reader_note,
                "style": style}
        self._edit_region(region, data, self.last_result, kind=kind)

    # ------------------------------------------------------------------ the editor and the review list
    def _spelling_note(self) -> str:
        """`SPELLING_OFF` the first time an editor opens while spelling is to be checked (the spellcheck setting, a
        target language with a word list) and cannot be (the optional package is not installed), then never again
        (ui.json); else ""."""
        settings = self.settings
        if not getattr(settings, "spellcheck", True):
            return ""
        first = (settings.target_language or "").strip().lower().split()
        if not first or first[0] not in checks.SPELL_LANGUAGES:
            return ""
        state_dir = Path(settings.state_dir)
        if load_ui_flag(state_dir, SPELLING_SAID) or checks.spell_checker(settings.target_language) is not None:
            return ""
        try:
            save_ui_flag(state_dir, SPELLING_SAID)
        except OSError:
            pass  # said again next time
        return _(SPELLING_OFF)

    def _editor_note(self, region: Any) -> str:
        """The lines under the region editor's header: that its translation was reused from an identical line before
        it (`REUSED_NOTE`), and `_spelling_note`; "" for none."""
        return "\n".join(n for n in (_(REUSED_NOTE) if getattr(region, "reused", False) else "",
                                     self._spelling_note()) if n)

    def _open_editor(self, region: Any, result: Any = None, at: Any = None) -> None:
        """The region editor, its header naming the bubble's place on the page and its picture the region as the
        capture has it (`editor_crop`, in memory); the model can be asked from it when a translator is there, the
        Japanese read again where the page came from the cache (`_read_source`), and Previous and Next go through the
        page's regions in reading order (`_step_editor`). What the editor shows is lettered on the page behind it a
        moment after each change (`LivePreview`). The editor belongs to the page it opens on (*result*: the last one
        when None): Auto may turn the page behind it, and Save, Drop and the model's answers still go to that page. A
        region of a page gone by now (a review list left open) is refused. *at*: where on the screen it opens. How far
        the translation model in use follows a region's hint (`translate.base.hint_support`: PLaMo only sometimes) the
        editor says under it. A translation reused from an identical line before it (`linememo`) is said to be one
        (`REUSED_NOTE`, under the header). In see-through mode it goes beside the region on the viewer
        (`see_edit.editor_place`), Previous and Next's ones too, and its Show original, held, shows the viewer's
        original under the region (`see_edit.set_bare`); one the reader asked for takes the keys."""
        result = result if result is not None else self.last_result
        if seethrough.hidden(self):
            seethrough.asked(self)
        pipeline = self.pipeline
        if not holds(result, region):
            self.say(NO_REGION)
            return
        shown = editor_regions(result)
        number = next((i for i, r in enumerate(shown) if r is region), len(shown)) + 1
        can_ask = pipeline is not None and pipeline.translator is not None
        preview = LivePreview(result, region) if pipeline is not None else None
        faces = (False, False)  # whether the region's automatic lettering is bold, italic (what B and I show then)
        if pipeline is not None:
            try:
                lettering = pipeline.lettering_for(region.translated_text, region.tag)
                faces = (lettering.bold, lettering.italic)
            except Exception:  # noqa: BLE001 - the editor opens all the same
                pass
        fonts_dir = self.settings.fonts_dir
        original: Callable[[bool], None] | None = None
        if seethrough.hidden(self):  # (see-through mode: beside the region on the viewer, its original shown when held)
            from . import see_edit

            at = see_edit.editor_place(self, region) or at
            original = lambda shown, r=region: see_edit.set_bare(self, r, shown)  # noqa: E731
        self._editor = EditBubbleDialog(self, region, self._speaker_names(),
                                        on_save=lambda data, r=region: (self._end_preview(preview, keep=holds(result, r)),
                                                                        self._edit_region(r, data, result)),
                                        on_drop=lambda r=region: self._drop_region(r, result),
                                        on_ask=(lambda mode, answer, r=region: self._ask_model(r, mode, answer, result))
                                        if can_ask else None,
                                        place=(number, max(number, len(shown))),
                                        on_preview=lambda text, style, large=OWN_PART: self._preview_region(
                                            preview, text, style, large),
                                        on_cancel=lambda: self._end_preview(preview),
                                        families=lambda: font_families(fonts_dir), faces=faces,
                                        crop=editor_crop(getattr(result, "original", None), region.bbox),
                                        on_read=(lambda done, r=region: self._read_source(r, result, done))
                                        if pipeline is not None else None,
                                        on_step=lambda delta, data, place, r=region: self._step_editor(
                                            r, result, preview, delta, data, place),
                                        at=at, note=self._editor_note(region),
                                        clip=self.format_clip() if hasattr(self, "format_clip") else None,
                                        font_memory=FontMemory(self.settings.state_dir),
                                        hint_support=hint_support(pipeline.translator) if can_ask else HINT_FOLLOWS,
                                        sizes=bool(getattr(self.settings, "size_emphasis", True)),
                                        on_original=original)

    def _step_editor(self, region: Any, result: Any, preview: LivePreview | None, delta: int,
                     data: dict[str, Any] | None, at: tuple[int, int]) -> None:
        """The editor's Previous (-1) or Next (+1): what was changed in it saved as Save saves it (*data*; None:
        nothing changed, nothing is stored), then the editor on the region before or after it among the page's
        regions in reading order (`editor_regions`), at the same place on the screen, and that region selected on the
        page while it is on show."""
        if data is not None:
            self._end_preview(preview, keep=holds(result, region))
            self._edit_region(region, data, result)
        else:
            self._end_preview(preview)
        shown = editor_regions(result)
        at_now = next((i for i, r in enumerate(shown) if r is region), None)
        if at_now is None or not 0 <= at_now + delta < len(shown):
            return
        target = shown[at_now + delta]
        if result is self.last_result:
            self._choose(target)
        self._open_editor(target, result, at)

    @staticmethod
    def _japanese(region: Any) -> str:
        return str(getattr(region, "source_text", "") or "").strip()

    def _japanese_of(self, result: Any, region: Any, then: Callable[[str, str], None]) -> None:
        """*region*'s Japanese handed to *then* (the text, and what went wrong: a key of `seethrough.NOT_READ`): at
        once when it has it, else once it is read from its crop of *result*'s capture in the worker (`_read_source`,
        nothing stored); a reading under way for it serves every request that comes meanwhile (the right pane's Copy
        the Japanese)."""
        text = self._japanese(region)
        if text:
            then(text, "")
            return
        waiting = getattr(self, "_japanese_waiting", None)
        if waiting is None:
            waiting = self._japanese_waiting = {}
        key = id(region)
        if key in waiting:
            waiting[key][1].append(then)
            return
        waiting[key] = (region, [then])

        def done(text: str, error: str) -> None:
            for step in waiting.pop(key, (None, []))[1]:
                step(text.strip(), error)

        reader = getattr(self, "_read_source", None)
        if reader is None or reader(region, result, done) is False:  # the reading model is not loaded yet
            done("", "no-ocr")

    def _to_clipboard(self, text: str, said: str) -> None:
        """*text* on the clipboard, in place of what was there (the reader asked for it), and *said* in the status
        line (without the text)."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.say(said)

    def _read_source(self, region: Any, result: Any, done: Callable[[str, str], None]) -> bool:
        """The editor's "Read the Japanese" (and its Ask again on a region with none): the region's Japanese read
        again from the capture in the worker (`Pipeline.read_source`, in memory, nothing stored), handed to *done*
        (the text, and what went wrong) once it is there. False while the reading model is not loaded."""
        pipeline = self.pipeline
        if pipeline is None or getattr(pipeline, "ocr", None) is None or result is None:
            return False
        got: dict[str, Any] = {}

        def job() -> None:
            try:
                got["text"] = pipeline.read_source(result, region)
            except Exception:  # noqa: BLE001 - the editor says nothing was read
                got["text"] = ""
            finally:
                got["done"] = True

        self._jobs.put(job)
        self.after(PREVIEW_POLL_MS, lambda: self._source_read(got, done))
        return True

    def _source_read(self, got: dict[str, Any], done: Callable[[str, str], None]) -> None:
        """The reading of `_read_source`, once the worker has made it, to the editor that asked (looked for again
        until then; an editor closed meanwhile takes nothing)."""
        if not got.get("done"):
            self.after(PREVIEW_POLL_MS, lambda: self._source_read(got, done))
            return
        try:
            done(str(got.get("text", "")), "" if got.get("text") else "none")
        except tk.TclError:  # the editor is gone
            pass

    # ------------------------------------------------------------------ the editor's live preview
    def _preview_region(self, preview: LivePreview | None, text: str, style: RegionStyle,
                        large: Any = OWN_PART) -> None:
        """The editor asks for its text and formatting on the page, *large* its part set larger (a range of *text*
        and a ratio, None: none; by default the region's own): lettered in the worker (the newest request only; one
        that waited behind another job takes what the editor shows by then), shown once it is there."""
        if preview is None or not preview.open or self.pipeline is None:
            return
        pipeline = self.pipeline
        preview.serial += 1
        preview.asked = (preview.serial, text, style, large)

        def job() -> None:
            asked = preview.asked
            if not preview.open or asked is None or (preview.made is not None and preview.made[0] >= asked[0]):
                return
            number, text_now, style_now, large_now = asked
            try:
                if preview.bed is None:
                    preview.bed = pipeline.page_without(preview.result, preview.region)
                part = {} if large_now is OWN_PART else {"part": large_now}
                page, done = pipeline.preview_region(preview.bed, preview.region, text_now, style_now, **part)
                preview.made = (number, Image.fromarray(page), done)
            except Exception:  # noqa: BLE001 - a preview that fails shows nothing new; Save letters the page all the same
                preview.made = (number, None, None)

        self._jobs.put(job)
        if not preview.polling:
            preview.polling = True
            self.after(PREVIEW_POLL_MS, lambda: self._show_preview(preview))

    def _show_preview(self, preview: LivePreview) -> None:
        """The newest preview that is there goes on the page (while the page on show is the editor's), and the
        editor says what the lettering could not do as formatted; looked for again while one is still to come."""
        preview.polling = False
        if not preview.open:
            return
        made = preview.made
        if made is not None and made[0] > preview.shown:
            preview.shown = made[0]
            if made[1] is not None and self.last_result is preview.result:
                if preview.result.image is not preview.mine:  # the page lettered anew meanwhile (a Save before it)
                    preview.before = preview.result.image
                preview.result.image = preview.mine = made[1]
                self._redisplay()
            editor = self._editor
            if made[2] is not None and editor is not None and editor.winfo_exists():
                editor.show_fit(made[2].flags, made[2].size)
        if preview.asked is not None and preview.shown < preview.asked[0]:
            preview.polling = True
            self.after(PREVIEW_POLL_MS, lambda: self._show_preview(preview))

    def _end_preview(self, preview: LivePreview | None, keep: bool = False) -> None:
        """The editor closes: with *keep* (Save) the preview stays on the page until the saved page comes; else the
        page's own rendering is back, where the preview's picture is still on it (a page lettered anew since stays)."""
        if preview is None or not preview.open:
            return
        preview.open = False
        if keep or preview.mine is None or preview.result.image is not preview.mine:
            return
        preview.result.image = preview.before
        if self.last_result is preview.result:
            try:
                self._redisplay()
            except tk.TclError:  # the window is going
                pass

    def _ask_model(self, region: Any, mode: str, answer: dict[str, str] | None = None, result: Any = None) -> bool:
        """From the editor: one more translation of the region ("again"), on the page *result* the editor was opened
        on, of the reading in *answer*'s "source" (the editor's "Read as:", which the person may have corrected; the
        region's own reading when there is none). The answers go to the open editor
        (`EditBubbleDialog.show_answers`), whatever happens, with the model's error in *answer* when there was one,
        and where the region's Japanese lettering set a part larger, the part of each answer to set larger
        (`Pipeline.large_of`: "larges", given only when one was found). False when the model cannot be asked."""
        result, pipeline = result if result is not None else self.last_result, self.pipeline
        if pipeline is None or result is None:
            return False
        answer = answer if answer is not None else {}
        self.say("Asking the model...")

        def job() -> None:
            texts: list[str] = []
            larges: list[Any] = []
            try:
                source = str(answer.get("source") or "")
                texts = [pipeline.ask_again(result, region, source) if source else pipeline.ask_again(result, region)]
                texts = [t for t in texts if t]
                find = getattr(pipeline, "large_of", None)
                if find is not None and getattr(region, "size_mix", None) is not None:
                    try:
                        larges = [find(result, region, t, source or None) for t in texts]
                    except Exception:  # noqa: BLE001 - the answer comes all the same, at one size
                        larges = []
            except TranslationError as e:
                answer["error"] = rendered(message_of(e))
            finally:  # the editor waits for the answers: they come in any case
                found = {"larges": larges} if any(large is not None for large in larges) else {}
                self._post("asked", mode=mode, texts=[t for t in texts if t], **found)
                if answer.get("error"):
                    self._post("status", text=answer["error"])

        self._jobs.put(job)
        return True

    def open_review(self) -> None:
        """Translator mode: the page's regions worth a look, each opening the editor."""
        if self.last_result is None:
            self.say(FIRST_PAGE)
            return
        rows = review_rows(self.last_result.regions)
        if self._review is not None and self._review.winfo_exists():
            self._review.fill(rows)
            self._review.lift()
            return
        self._review = ReviewDialog(self, rows, on_edit=self._open_editor)

    def open_corrections(self) -> None:
        """Translator mode's "My corrections...": the translations the person wrote in the book of the Book field,
        page by page (`dialogs.corrections.CorrectionsDialog`), from its cache alone; the list already open is made
        again and brought to the front. Selecting a row only says its page: nothing goes to the viewer."""
        from .dialogs import corrections

        self._open_book_list("_corrections", lambda: corrections.CorrectionsDialog(self, self._correction_rows))

    def open_lines_to_review(self) -> None:
        """Translator mode's "Lines to review...": every line of the book of the Book field worth a look, page by page
        (`dialogs.review_list.LinesToReviewDialog`: flagged as it was translated, or with a note for the reader), from
        its cache alone, with what the checks of the lettering found on the page on show; as "My corrections", the
        list already open is made again and brought to the front, and selecting a row only says its page: nothing goes
        to the viewer."""
        from .dialogs import review_list

        self._open_book_list("_to_review", lambda: review_list.LinesToReviewDialog(self, self._review_list_rows))

    def _open_book_list(self, attr: str, make: Callable[[], Any]) -> None:
        """A list of the book's lines by page (`dialogs.page_list`) kept in *attr*: the one open made again and
        brought to the front, else *make*() opens it. When another book was chosen since the last page, the worker
        opens its cache (as the next page would, and as Find does), and the list is made again then (the "find"
        event: `_refresh_corrections`)."""
        shown = getattr(self, attr, None)
        if shown is not None and shown.winfo_exists():
            shown.fill()
            shown.lift()
        else:
            setattr(self, attr, make())
        book, language = self.book_var.get().strip(), self.lang_var.get().strip() or "English"
        if (self.pipeline is not None and book and not generic_book_name(book) and not self.busy
                and self._book_cache() is None):
            model = self.model_var.get().strip()
            self._jobs.put(lambda: (self._ensure_cache(book, model, language), self._post("find")))

    def _correction_rows(self) -> list[Any] | None:
        """The rows of "My corrections" (`BookCache.corrections`): of the cache of the book and language in the boxes
        (`ReplaceMixin._book_cache`); none while it is being opened; None while the Book field names no book."""
        book = self.book_var.get().strip()
        if not book or generic_book_name(book):
            return None
        cache = self._book_cache()
        return cache.corrections() if cache is not None else []

    def _review_list_rows(self) -> list[Any] | None:
        """The rows of "Lines to review" (`review_list.book_lines`): of the cache of the book and language in the
        boxes, with what the checks of the lettering found on the page on show when it is a page of that cache
        (`review_list.with_lettering`; those are kept nowhere); none while it is being opened; None while the Book
        field names no book."""
        from .dialogs.review_list import book_lines, with_lettering

        book = self.book_var.get().strip()
        if not book or generic_book_name(book):
            return None
        cache = self._book_cache()
        if cache is None:
            return []
        rows = book_lines(cache)
        pipeline = self.pipeline
        settings = getattr(pipeline, "settings", None)
        if self.last_result is not None and settings is not None and getattr(pipeline, "cache", None) is cache:
            rows = with_lettering(rows, cache, self.last_result, settings)
        return rows

    def _refresh_corrections(self) -> None:
        """The translations may have changed (a page's result, an edit, a replacement, its undo): the open lists of
        the book's lines - "My corrections", "Lines to review" - are made again."""
        for attr in ("_corrections", "_to_review"):
            shown = getattr(self, attr, None)
            try:
                if shown is not None and shown.winfo_exists():
                    shown.fill()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ undo and redo
    def undo_edit(self) -> None:
        """Ctrl+Z (Undo on the strip): the newest change on the page on show is taken back - an edit, a region moved,
        resized, added or dropped."""
        self._step_through(back=True)

    def redo_edit(self) -> None:
        """Ctrl+Y (Redo on the strip): the newest change taken back on the page on show is made again."""
        self._step_through(back=False)

    def _step_through(self, back: bool) -> None:
        """Take back (*back*) or make again the newest change on the page on show. When the page on show is the very
        one the change was made on, its regions are put back in place; else (the page was read again since) the
        page is read again from the stores. The status line says what was done."""
        if self.role_var.get() != "translator" or self.pipeline is None or self.busy:
            return
        if self._ordering is not None:
            self.say("Reading order: click the bubbles in the order they are read, then choose Finish order in the Menu.")
            return
        result, pipeline = self.last_result, self.pipeline
        wide = self.history.book_step(owner(pipeline), undone=not back)
        if wide is not None:  # a replacement (a formatting, `formats`; an area, `book_areas`) across the book: on
            # whatever page is on show
            carry_wide = {"styles": "_carry_book_styles", "areas": "_carry_book_areas"}.get(wide.kind,
                                                                                            "_carry_replacement")
            getattr(self, carry_wide)(wide, back)
            return
        step = None
        if result is not None and self._result_on_show():
            step = self.history.last(page_units(result), owner(pipeline), pipeline.settings.fingerprint_max_distance,
                                     undone=not back)
        if step is None:
            if not back:
                self.say("Nothing to redo.")
            elif len(self.history):
                self.say("Nothing to undo on this page.")
            else:
                self.say("Nothing to undo.")
            return
        (self.history.taken_back if back else self.history.made_again)(step)
        frm, to = (step.after, step.before) if back else (step.before, step.after)
        message = (TAKEN_BACK if back else MADE_AGAIN)[step.kind]
        errors: list[str] = []

        def stores() -> None:
            if step.state == "done":
                errors.extend(carry(pipeline, frm, to, step.scope))

        def said() -> None:
            if errors:
                self._post("status", key="Could not save the change: {error}", values={"error": errors[0]})
            else:
                self._post("status", key=message)

        if step.result is result and step.kind not in REREAD_KINDS:
            if step.touched:  # the region it changed is selected: it shows where the change went (gone again: none)
                self._choose(step.touched[-1].region)
                if len(step.touched) > 1:  # a change on several regions: all of them, once they are on the page
                    self._also_chosen = [t.region for t in step.touched[:-1]]
            self._go_busy()
            self.say("Storing your changes...")

            def job() -> None:
                try:
                    stores()
                    put_back(result, step.touched, before=back)
                    pipeline.rerender(result)
                    self._post("result", result=result)
                    said()
                finally:
                    self._post("translate_done")

            self._jobs.put(job)
            return
        self._jobs.put(stores)  # the stores first, then the page read from them, then the line
        self._start_translate(result.original, complete=True)
        self._jobs.put(said)

    def _record(self, kind: str, result: Any) -> Step:
        """A change about to be made on the page *result*, kept in the history (its job fills it in)."""
        pipeline = self.pipeline
        return self.history.record(Step(kind, result, owner(pipeline), page_units(result)),
                                   pipeline.settings.fingerprint_max_distance)

    # ------------------------------------------------------------------ the regions changed
    def _region_at(self, x: int, y: int):
        if self.last_result is None:
            return None
        hits = [r for r in self._page_regions() if r.x0 <= x < r.x1 and r.y0 <= y < r.y1]
        return min(hits, key=lambda r: r.area) if hits else None

    def _add_region(self, box: tuple[int, int, int, int], style: RegionStyle | None = None) -> None:
        """Translator mode: a rectangle drawn on empty space becomes a region of the reader's; the page is read again
        (the rectangle read and translated). Ctrl+Z takes it back. *style*: its formatting (a region pasted:
        `formats.FormatMixin.paste_region`), stored with it in the same change."""
        if self.pipeline is None or self.last_result is None:
            return
        result, pipeline = self.last_result, self.pipeline
        if pipeline.annotations is None:
            self.say("Could not record the rectangle: give the book a name first (its series in the Series field, and its volume beside it if it has one).")
            return
        if not result.units:
            return
        before = unit_states(pipeline, result.units)
        if not pipeline.add_region(result, box):  # the file could not be written: the rectangle goes again
            carry(pipeline, unit_states(pipeline, result.units), before)
            self.say("Could not save the rectangle: the book's premises cannot be written now (is the file open in another program?).")
            return
        unit = unit_for(result.units, box) if style is not None and not style.is_empty else None
        if unit is not None:  # the pasted region's formatting, at the box the page will read it at
            pipeline.annotations.page(unit.fingerprint, unit.aspect).set_style(
                unit.normalize(box), style, pipeline.settings.match_min_iou)
            pipeline.save_annotations()
        step = self._record("add", result)
        step.before = before
        step.scope = {i: u.normalize(box) for i, u in enumerate(result.units)}
        self.say("Text rectangle added; reading and translating it...")
        self._start_translate(result.original, complete=True)

        def settle() -> None:  # the worker, once the page is read again: the stores as the rectangle left them
            step.after = unit_states(pipeline, result.units)
            step.state = "done" if stores_differ(step.before, step.after, step.scope) else "empty"

        self._jobs.put(settle)

    def _move_region(self, region: Any, box: tuple[int, int, int, int]) -> None:
        """Translator mode: the selected region resized or moved; it is read and translated again only where needed.
        Ctrl+Z takes it back."""
        if self.pipeline is None or self.last_result is None:
            return
        result, pipeline = self.last_result, self.pipeline
        step = self._record("move" if (box[2] - box[0], box[3] - box[1]) == (region.width, region.height) else "resize",
                            result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, [region])
                ok = pipeline.move_region(result, region, box, progress=lambda m: self._post("progress", text=m))
                if not ok:
                    self._post("status", key="Could not record the rectangle: give the book a name first (its series in the Series field, and its volume beside it if it has one).")
                step.settle(pipeline, ok)
                self._post("result", result=result)
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def _edit_region(self, region: Any, data: dict[str, Any], result: Any = None, kind: str = "edit") -> None:
        """The editor's Save: on the page *result* it was opened on (none: the last one), which Auto may have turned
        by now, the region's premises, its note for the reader, the formatting of its lettering and its translation
        stored, the page lettered again; one change to take back (Ctrl+Z), of *kind* ("rotate": the rotate handle's,
        `_rotate_region`; "direction": T's, `_turn_direction`). A region that left that page meanwhile is refused.
        A translation saved is marked as the person's (`CachedBubble.edited`: "Translate again" keeps it, "My
        corrections" lists it), but for the model's answer to Ask again saved as it came ("asked"), which clears
        the mark. The part of the translation set larger ("large") is stored with it; where only that changed, it is
        stored alone (`Pipeline.set_large`) and the translation stays whose it was.
        A reading the person corrected ("source": the editor's "Read as:") the region takes first, in memory only
        (`Pipeline.correct_reading`): no change of the stores, and none Ctrl+Z takes back; the translation is kept
        for that reading (`linememo.remember_edit`)."""
        result, pipeline = result if result is not None else self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        if not holds(result, region):
            self.say(NO_REGION)
            return
        text = str(data.get("text", "")).strip()
        style = data.get("style")
        reading = str(data.get("source") or "")
        step = self._record(kind, result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                correct = getattr(pipeline, "correct_reading", None)
                if reading and correct is not None and reading != getattr(region, "source_text", ""):
                    correct(result, region, reading)
                step.begin(pipeline, [region])
                pipeline.set_region_note(result, region, str(data.get("speaker", "")), str(data.get("kind", "")),
                                         bool(data.get("continues")), str(data.get("note", "")))
                reader_note = str(data.get("reader_note", "")).strip()
                if reader_note != getattr(region, "reader_note", ""):
                    pipeline.set_reader_note(result, region, reader_note)
                if isinstance(style, RegionStyle) and style != (getattr(region, "style", None) or RegionStyle()):
                    if not pipeline.set_region_style(result, region, style):  # before the page is lettered again
                        self._post("status", key="Could not store the formatting: give the book a name first (its series in the Series field, and its volume beside it if it has one).")
                # the part of the translation set larger, as the editor has it (an editor of before: as it follows)
                large = data["large"] if "large" in data else ...
                if text and text != region.translated_text:
                    old = region.translated_text
                    # the person's translation (`CachedBubble.edited`), but for the model's answer to Ask again taken
                    # as it came ("asked")
                    if not pipeline.set_translation(result, region, text, edited=not data.get("asked"),
                                                    **({} if large is ... else {"large": large})):
                        self._post("status", key="Could not keep the translation: give the book a name first (its series in the Series field, and its volume beside it if it has one).")
                        pipeline.rerender(result)  # the page as it is stored, not as the editor's preview showed it
                    else:
                        changes = rendering_changes(pipeline.check_sheet(), region.source_text, old, text, region.speaker)
                        if changes:
                            self._post("propose", changes=changes)
                elif (text and large is not ... and large != getattr(region, "large", None)
                      and hasattr(pipeline, "set_large")):  # only the part set larger changed: the text stays whose it is
                    if not pipeline.set_large(result, region, large):
                        self._post("status", key="Could not keep the translation: give the book a name first (its series in the Series field, and its volume beside it if it has one).")
                        pipeline.rerender(result)
                else:
                    pipeline.rerender(result)
                step.settle(pipeline)
                self._post("result", result=result, edited=True)
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)

    def _drop_region(self, region: Any, result: Any = None) -> None:
        """Translator mode: the region is dropped from the page *result* (none: the last one; `_edit_region`) - its
        translation leaves the cache and the spot is remembered as not text. Ctrl+Z brings it back, translation and
        all. Once it is stored, a place dropped on another page of the book too is offered as an area to ignore on
        all pages (`book_areas.AreaMixin._offer_ignore_everywhere`)."""
        result, pipeline = result if result is not None else self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        if not holds(result, region):
            self.say(NO_REGION)
            return
        step = self._record("drop", result)
        self._go_busy()
        self.say("Dropping the region...")

        def job() -> None:
            try:
                step.begin(pipeline, [region])
                ok = pipeline.drop_region(result, region)
                for i, r in enumerate(result.regions):  # numbered as the review list and the editor count them
                    r.order = i
                step.settle(pipeline, ok)
                self._post("result", result=result, edited=True)
                if ok:
                    self._post("status", key="Region dropped; Menu > Undo brings it back.")
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)
        offer = getattr(self, "_offer_ignore_everywhere", None)  # (`book_areas`: a part of the window)
        if offer is not None:
            offer(region, result, step)

    # ------------------------------------------------------------------ a click on the page goes to the viewer
