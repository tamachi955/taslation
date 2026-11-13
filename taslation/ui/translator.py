"""Translator mode: its strip under the toolbar (the tools - reading order, skip page, translate again, book settings,
series sheet, review, find and replace, undo, redo - and a line on what the pointer does), the page's regions
selected, moved, resized, rotated by a round handle as a word processor's shapes are (Shift+click and a Shift+drag
rubber band select several, and a drag, the Alt+arrow keys, Delete and T then act on all of them as one change:
`chosen_regions`, the rest in `selection`), edited (with the formatting of their lettering, shown on the page as it is
set: `LivePreview`), added and dropped with the pointer,
every one of those changes taken back and made again (Ctrl+Z, Ctrl+Y: `history`), the model asked again from the
editor (the Japanese read again first on a page shown from the cache), the editor taken through the page's regions in
reading order (Previous, Next), and a rendering the reader changed offered to the series sheet; in reader mode a click
on the page goes to the viewer."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import replace
import tkinter as tk
from pathlib import Path
from string import Formatter
from tkinter import ttk
from typing import Any, Callable

from PIL import Image

from ..annotations import CharacterSheet, RegionStyle
from ..bookid import generic_book_name
from ..cache import language_key
from ..capture import CaptureError, caption_rows, post_click
from ..i18n import _, load_ui_flag, load_ui_table, save_ui_entry, save_ui_flag
from ..messages import message_of
from ..notes import series_key
from ..pipeline import unit_for
from ..render.fonts import font_families
from .font_memory import FontMemory
from ..render.slant import slanted_outline
from .. import review as checks
from ..review import rendering_changes, sheet_item_for
from ..translate import TranslationError
from . import area, shortcuts
from .constants import FIRST_PAGE, FORWARDED_KEYS, READER_AFTER_RUN, THIS_PAGE, book_read, in_a_run, viewer_rests
from .dialogs import caches as boxes
from .dialogs.review import DIRECTION_WORDS, EditBubbleDialog, ReviewDialog, review_rows
from .history import BookStep, Step, carry, owner, page_units, put_back, stores_differ, unit_states
from .layout import FlowBar, wrap_label
from .progress import rendered
from .sheet_changes import rename_edits, shown_pairs
from .tooltip import tip

# what the pointer and the keys do on the page in translator mode: the strip under the toolbar says it while the role
# is chosen, each key as the keymap has it (`hint_text`: a part whose action has no key is left out)
HINT = ("Click: select · drag: move · drag a handle: resize · drag the round handle: rotate (Shift: 15° steps) · "
        "double-click or {edit}: edit · Esc: deselect · drag on empty space: add · {drop}: drop · "
        "{direction}: text direction · {undo}: undo · {redo}: redo · {next}: next region · {nudge}: move by 1 px")
HINT_KEYS = {"edit": "edit_box", "drop": "remove_box", "direction": "text_direction", "undo": "undo", "redo": "redo",
             "next": "next_region"}  # the hint's placeholders and their actions (`shortcuts.ACTIONS`); {nudge}: `nudge_keys`
NUDGE_WORDS = "Alt+arrow keys"  # the four nudges on their keys of the table
# the strip's buttons that name their key: (label, action)
KEYED_TOOLS = (("Text direction", "text_direction"), ("Undo", "undo"), ("Redo", "redo"))
# Tab and Shift+Tab on the page: the region selected, said in the status line
REGION_OF = "Region {n} of {total}: Enter edits it, Alt with the arrow keys moves it."
# Alt+arrows on the page: the selected region moved by a pixel (with Shift by NUDGE_FAR); presses this close together
# are one move, stored once (`_nudge_done`) and taken back with one Ctrl+Z
NUDGES = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}
NUDGE_FAR = 10
NUDGE_MS = 500
# the text directions translator mode's T and its button go through on the selected region, in turn
DIRECTION_CYCLE = ("", "down", "up", "stacked")
# the spellcheck setting is on by default, but its word lists come from an optional package; where it is missing the
# editor says so once (ui.json SPELLING_SAID), never anything online
SPELLING_OFF = ("Spelling is not checked: the spellcheck setting is on, but the optional pyspellchecker package is not "
                "installed (pip install pyspellchecker; its word lists stay on this PC). This is said only once.")
SPELLING_SAID = "spelling_unavailable_said"
# what the status line says on a click on the page that selects nothing
CLICK_HINT = ("Translator mode: click a region to select it, drag it to move it, its handles to resize it or its round "
              "handle to rotate it, double-click to edit it, drag on empty space to add one.")
FRAME_COLOUR = "#ffd400"  # the selected region's frame and handles (two-tone: `preview.EDGE` runs under it)
NEW_REGION_COLOUR, DRAG_TAG = "#4da3ff", "drag-rect"  # the rectangle a drag on empty space draws, two-tone too
BAND_TAG = "band-rect"  # the rubber band a Shift+drag draws to select the regions inside it (the selection's colour)
FRAMES_KEPT = 64  # turned frames kept (`_frame_of`), by region
HINT_COLOUR = "#4a4a4a"
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
# what is said once it is done, and why it is not offered during a run
SHEET_OFFER = "{n} line(s) already translated use the series sheet's earlier rendering ({changes}). Give them the new one? Ctrl+Z takes it back."
SHEET_APPLY = "Apply to the {n} line(s)"
SHEET_LEAVE = "Leave them as they are"
SHEET_APPLIED = "Applied to {n} translated line(s) on {pages} page(s). Ctrl+Z takes it back."
SHEET_IN_A_RUN = "The lines already translated were not changed: a run is reading the book. Find and replace can change them once it is done."
SHEET_WAIT_MS = 300  # how often the offer looks whether the window is free (a page at work) or the cache is open


ROLE_TABLE, ROLES_KEPT = "roles", 500  # ui.json: the role the reader chose for a book, by its name (the latest books)
ROLE_DELAY_MS = 400  # the Book box rests this long before the role for its book is decided


def nudge_keys(keymap: shortcuts.Keymap) -> str:
    """The keys that nudge the selected regions, as the strip's hint names them: "Alt+arrow keys" in the window's
    language while the four are on their keys of the table, else those they have ("Ctrl+H/Ctrl+L"; "" for none)."""
    names = [f"nudge_{direction.lower()}" for direction in NUDGES]
    if not any(name in keymap.own for name in names):
        return _(NUDGE_WORDS)
    return "/".join(keymap.shown(name) for name in names if keymap.of(name))


def hint_text(keymap: shortcuts.Keymap) -> str:
    """The strip's hint (`HINT`) in the window's language with the keys as *keymap* has them; a part whose action has
    no key is left out with its separator ("·", or "・" in Japanese)."""
    keys = {field: keymap.shown(name) for field, name in HINT_KEYS.items()}
    keys["nudge"] = nudge_keys(keymap)
    pieces = re.split(r"(\s*[·・]\s*)", _(HINT))
    out: list[str] = []
    for i, part in enumerate(pieces[0::2]):
        if all(keys.get(field) for _text, field, _spec, _conv in Formatter().parse(part) if field):
            out += [pieces[2 * i - 1]] if out else []
            out.append(part.format(**keys))
    return "".join(out)


def chosen_role(state_dir: Any, book: str) -> str:
    """The role the reader chose for *book* ("reader" or "translator"); "" for none."""
    role = load_ui_table(Path(state_dir), ROLE_TABLE).get(book, "")
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
    """The regions selected on the page in translator mode: the selected one (`_chosen_region`, the one Tab goes on
    from and the editor opens on) first, then those Shift+click and a Shift+drag added (`_also_chosen`) that are still
    on the page on show; none while nothing is selected. With several, Delete, T, Paste format, Alt+arrows, a drag and
    the Page menu's Set kind... and Set text size... act on all of them, each as one change (`selection`)."""
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
        self.asked: tuple[int, str, RegionStyle] | None = None  # (number, text, style): the newest request
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
            sheet = self.glossary_store.open(series_key(book), language)
        except OSError as e:  # the file is locked, or another series has its name
            self.say("Could not open the series sheet: {error}", error=e)
            return
        changed = False
        editor = getattr(self, "_editor", None)  # an editor open by now (Next): the question over it, its grab back after
        parent = editor if editor is not None and editor.winfo_exists() else self
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
                        line: Callable[[BookStep], tuple[str, dict[str, Any]]]) -> BookStep:
        """The worker gives every translated line of *cache* (the pipeline's) the new renderings of *pairs* (old ->
        new, whole words: `sheet_changes.rename_edits`), on what the cache holds then, as one change on no page in
        particular that Ctrl+Z takes back (`history.BookStep`, as a replacement across the book); the page on show is
        lettered again (`_stored`) and *line* of the step is said, or what went wrong."""
        step = BookStep(owner(pipeline))
        self.history.record(step, pipeline.settings.fingerprint_max_distance)
        result = self.last_result

        def job() -> None:
            try:
                cache.refresh()  # what another process saved meanwhile
                step.edits = cache.put_texts(rename_edits(cache, pairs))
                step.state = "done" if step.edits else "empty"
                lines = self._stored(pipeline, result, step.edits)
                self._post("find", lines=lines or [line(step)])
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
        book's cache is opened by the worker first when the window holds another one; while a page is at work the
        question waits until it is done; during a run nothing is offered, and a line says why."""
        pairs = [(old, new) for old, new in pairs if old and new and old != new]
        pipeline = self.pipeline
        if not pairs or pipeline is None or not book or generic_book_name(book):
            return
        if in_a_run(self):
            self.say(SHEET_IN_A_RUN)
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
        count = len(rename_edits(cache, pairs))
        if not count:
            return
        box_parent = parent if parent is not None and parent.winfo_exists() else self
        if not boxes.ask(box_parent, _(SHEET_OFFER).format(n=count, changes=shown_pairs(pairs)),
                         _(SHEET_APPLY).format(n=count), _(SHEET_LEAVE)):
            return
        if self.pipeline is not pipeline or getattr(pipeline, "cache", None) is not cache or in_a_run(self):
            return  # the window moved on while the question was up
        self.say("Storing your changes...")
        self._rename_in_book(pipeline, cache, pairs, lambda step: (
            (SHEET_APPLIED, {"n": len(step.edits), "pages": len({e.fingerprint for e in step.edits})})
            if step.edits else ("Nothing was changed.", {})))

    def _refresh_premises(self, book: str, language: str) -> None:
        """The worker: the pipeline takes the book's premises again; a store that cannot be opened is said."""
        try:
            self._job_refresh_premises(book, language)
        except OSError as e:
            self._post("status", key="Could not open the book's premises: {error}", values={"error": str(e)})

    # ------------------------------------------------------------------ the tools
    def _build_translator_tools(self, parent: tk.Misc) -> None:
        """Translator mode's strip under the toolbar: its tools in groups that flow into rows as the toolbar's do
        (reading order, skip page, translate again; book settings, series sheet, review; find and replace, the
        selected region's text direction, undo, redo)
        and a line on what the pointer does on the page: these tools are here and nowhere else. `_sync_tools` shows it
        while the Translator role is chosen; reading mode hides it with the toolbar. Ctrl+Y makes again what Ctrl+Z took
        back. The buttons and the line name the keys as the keymap has them (`KEYED_TOOLS`, `hint_text`; again after a
        change: `_show_tool_keys`)."""
        keymap = getattr(self, "keymap", None) or shortcuts.current()
        keyed = dict(KEYED_TOOLS)
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
                   (_("Review..."), self.open_review, _("List the text areas of this page that are worth a look."))),
                  ((_("Find and replace..."), self.open_find_replace,
                    _("Search this book's translations and replace a word on every page.")),
                   ("Text direction", self._turn_direction,
                    _("Change the selected region's text direction: Auto, rotated 90°, rotated 270°, stacked, and Auto again.")),
                   ("Undo", self.undo_edit, _("Take back your last change.")),
                   ("Redo", self.redo_edit, _("Make the last change again."))))
        self._keyed_tools: list[tuple[ttk.Button, str, str]] = []  # (button, label, action) of `KEYED_TOOLS`
        for chunk in chunks:
            group = tools.group()
            for i, (text, command, explanation) in enumerate(chunk):
                shown = shortcuts.with_keys(text, keyed[text], keymap) if text in keyed else text
                button = ttk.Button(group, text=shown, command=command)
                button.pack(side="left", padx=(4 if i else 0, 0))
                tip(explanation, button)
                self.tool_btns.append(button)
                if text in keyed:
                    self._keyed_tools.append((button, text, keyed[text]))
        hint = ttk.Label(strip, text=hint_text(keymap), anchor="w", justify="left", foreground=HINT_COLOUR,
                         padding=(8, 0, 8, 4))
        hint.pack(fill="x")
        hint.bind("<Configure>", lambda e: wrap_label(hint, e.width - 16))
        self._tool_strip, self.tools_bar, self.hint_label = strip, tools, hint

    def _show_tool_keys(self, keymap: shortcuts.Keymap) -> None:
        """The strip's keyed buttons and its hint with the keys as *keymap* has them (`App._show_keys`)."""
        for button, label, name in getattr(self, "_keyed_tools", ()):
            button.configure(text=shortcuts.with_keys(label, name, keymap))
        self.hint_label.configure(text=hint_text(keymap))

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
            self.say("Reading order: click the regions in the order they are read, then press Finish order (Esc cancels).")
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
            self.say("Give the book a name first (the Book field).")
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
            self.say("Give the book a name first (the Book field).")

    def retranslate_page(self) -> None:
        """Translator mode's "Translate again": the page is translated again with the premises as they
        are now, and what that translates replaces its cached translations; a job that translates nothing (Stop, a new
        page, Ollama down) leaves them as they were (`_job_translate`). The page may have moved on, or a job begun,
        while the question was up. Ctrl+Z puts the translations it replaced back."""
        if self.busy or self.pipeline is None or not self._page_to_work_on():
            return
        result = self.last_result
        if not boxes.ask(self, _("Translate this page again? Its present translations are replaced."), _("Translate again"),
                         _("Cancel")):
            return
        if self.busy or self.pipeline is None or self.last_result is not result:
            return
        pipeline = self.pipeline
        step, settle = self._kept_after_reading("again", result)
        units = list(result.units)

        def begin() -> None:  # the worker, as the reading starts: the translations it replaces
            step.before = unit_states(pipeline, units)

        self._jobs.put(begin)
        self._start_translate(result.original, complete=True, again=result)
        self._jobs.put(settle)

    def _speaker_names(self) -> list[str]:
        """The speakers the series sheet knows, for the editor's list; none (and the status line says why) when the
        sheet cannot be opened."""
        book = self.book_var.get().strip()
        if not book:
            return []
        try:
            return self.glossary_store.open(series_key(book), self.lang_var.get().strip() or "English").speaker_names()
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

    def _reader_after_run(self, book: str, language: str) -> bool:
        """A whole-book run has finished: with the book translated now (`book_read`: its cache holds enough pages) the
        window goes to reader mode, the role a translated book opens in - unless the reader chose a role for this
        book (`chosen_role`: their choice wins) or another book is in the Book box by now. Said in the status line.
        Whether it switched."""
        if (self.role_var.get() != "translator" or not book or generic_book_name(book)
                or book != self.book_var.get().strip() or chosen_role(self.settings.state_dir, book)):
            return False
        try:
            pages = self.store.page_count(book, language or "English")
        except Exception:  # noqa: BLE001 - cannot be told: the role stays
            pages = None
        if not book_read(pages):
            return False
        self._role_book = book  # decided for this book: the Book box's own decision does not come back on it
        self.role_var.set("reader")
        self._on_role_changed(chosen=False)
        self.say(READER_AFTER_RUN)
        return True

    def _apply_role(self, role: str, chosen: bool) -> None:
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
        if self.role_var.get() == "translator":  # the strip under the toolbar says the rest
            self.say("Translator mode: the line under the toolbar says what the pointer does on the page; keys still turn the viewer's pages.")
            self._complete_on_show()
        else:
            self.say("Reader mode: keys and clicks on the page go to the viewer.")

    def _complete_on_show(self) -> None:
        """Translator mode came on over a page taken from the cache in reader mode: the regions found on it that the
        cache has no bubble for were never read ("unmatched"; most are pieces of the drawing a run judged no text,
        whose judgement the cache does not keep). The page is read again as translator mode reads a page
        (`translate_now`: those regions read and judged, a line among them translated), so that they are outlined
        and labelled for what they are - or not at all (`_page_regions`). Not while a run is on or a job runs."""
        result = self.last_result
        if (result is None or self.reading or self.batch is not None or getattr(self, "_batching", False)
                or not self.ready or self.busy or not any(r.status == "unmatched" for r in result.regions)):
            return
        self.after_idle(self.translate_now)

    # ------------------------------------------------------------------ the regions under the pointer
    def _editing(self) -> bool:
        """Whether the page's regions are edited by the pointer (translator mode, not in the reading window, and
        the page on show is the one they belong to)."""
        return self.role_var.get() == "translator" and not self.reading and self._result_on_show()

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

    def _tab_region(self, step: int) -> str | None:
        """Tab (*step* 1) or Shift+Tab (-1) on the page in translator mode: the next or the previous region in reading
        order is selected (the first or the last when none is; round from the last to the first), and the status line
        says which; "break" keeps the keys on the page. Elsewhere (the Reader role, a page not on show, the reading
        order being set) Tab moves the focus as it always does (None)."""
        if not self._editing() or self._ordering is not None or self.last_result is None:
            return None
        regions = self._page_regions()
        if not regions:
            return "break"
        at = next((i for i, r in enumerate(regions) if r is self._chosen_region), None)
        target = (0 if step > 0 else len(regions) - 1) if at is None else (at + step) % len(regions)
        self._grip_box = None
        self._choose(regions[target])
        self.say(REGION_OF, n=target + 1, total=len(regions))
        return "break"

    def _nudge_key(self, event: tk.Event, keysym: str) -> str:
        """A nudge's key on the page (Alt with an arrow key: `shortcuts.ACTIONS`' nudge_left... on their keys; *keysym*
        the way it moves): in translator mode the selected region moves by a pixel (by `NUDGE_FAR` with Shift) at once
        on the page, and is stored as one move once the presses stop (`NUDGE_MS`, `_nudge_done`); several selected
        move together. Anywhere else an arrow pressed goes on to the viewer as the plain arrow does (`forward_key`),
        another key does nothing."""
        if not self._editing() or self._ordering is not None or self.last_result is None:
            pressed = str(getattr(event, "keysym", "") or "")
            if pressed in FORWARDED_KEYS:
                self.forward_key(FORWARDED_KEYS[pressed])
            return "break"
        region = self._chosen_region
        if region is None:
            self.say("Select a region first (click it).")
            return "break"
        if self.busy:
            return "break"
        far = NUDGE_FAR if int(getattr(event, "state", 0) or 0) & 0x0001 else 1
        dx, dy = NUDGES[keysym]
        group = chosen_regions(self)
        if len(group) > 1:  # several selected: all of them, by the same amount (`area.shift_within`)
            ox, oy = group_offset(self)
            sx, sy = area.shift_within([r.bbox for r in group], ox + dx * far, oy + dy * far,
                                       self.last_result.original.size)
            self._grip_box = (region.x0 + sx, region.y0 + sy, region.x1 + sx, region.y1 + sy)
        else:
            self._grip_box = area.move(self._grip_box or region.bbox, dx * far, dy * far,
                                       self.last_result.original.size)
        self._draw_frame()
        pending = getattr(self, "_nudging", None)
        if pending is not None:
            self.after_cancel(pending)
        self._nudging = self.after(NUDGE_MS, self._nudge_done)
        return "break"

    def _nudge_done(self) -> None:
        """The arrows let go: the selected region stored at the box they moved it to (one move for Ctrl+Z), several
        selected all of them by as much (`_move_regions`, one move too); a box back where it began, a page gone or a
        job begun meanwhile change nothing."""
        self._nudging = None
        region, box = self._chosen_region, self._grip_box
        if region is None or box is None or box == region.bbox or self.busy or not self._editing():
            self._grip_box = None
            self._draw_frame()
            return
        group = chosen_regions(self)
        if len(group) > 1:
            self._move_regions(group, box[0] - region.x0, box[1] - region.y0)
            return
        self._move_region(region, box)  # its outline stays at the new box until the region is there

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
        if not self._editing():  # a click that is not TASlation's own goes on to the viewer (`_forward_click`)
            if not moved:
                self._forward_click(e)
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

    def _open_editor(self, region: Any, result: Any = None, at: tuple[int, int] | None = None) -> None:
        """The region editor, its header naming the bubble's place on the page and its picture the region as the
        capture has it (`editor_crop`, in memory); the model can be asked from it when a translator is there, the
        Japanese read again where the page came from the cache (`_read_source`), and Previous and Next go through the
        page's regions in reading order (`_step_editor`). What the editor shows is lettered on the page behind it a
        moment after each change (`LivePreview`). The editor belongs to the page it opens on (*result*: the last one
        when None): Auto may turn the page behind it, and Save, Drop and the model's answers still go to that page. A
        region of a page gone by now (a review list left open) is refused. *at*: where on the screen it opens."""
        result = result if result is not None else self.last_result
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
        self._editor = EditBubbleDialog(self, region, self._speaker_names(),
                                        on_save=lambda data, r=region: (self._end_preview(preview, keep=holds(result, r)),
                                                                        self._edit_region(r, data, result)),
                                        on_drop=lambda r=region: self._drop_region(r, result),
                                        on_ask=(lambda mode, answer, r=region: self._ask_model(r, mode, answer, result))
                                        if can_ask else None,
                                        place=(number, max(number, len(shown))),
                                        on_preview=lambda text, style: self._preview_region(preview, text, style),
                                        on_cancel=lambda: self._end_preview(preview),
                                        families=lambda: font_families(fonts_dir), faces=faces,
                                        crop=editor_crop(getattr(result, "original", None), region.bbox),
                                        on_read=(lambda done, r=region: self._read_source(r, result, done))
                                        if pipeline is not None else None,
                                        on_step=lambda delta, data, place, r=region: self._step_editor(
                                            r, result, preview, delta, data, place),
                                        at=at, note=self._spelling_note(),
                                        clip=self.format_clip() if hasattr(self, "format_clip") else None,
                                        font_memory=FontMemory(self.settings.state_dir))

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
    def _preview_region(self, preview: LivePreview | None, text: str, style: RegionStyle) -> None:
        """The editor asks for its text and formatting on the page: lettered in the worker (the newest request only;
        one that waited behind another job takes what the editor shows by then), shown once it is there."""
        if preview is None or not preview.open or self.pipeline is None:
            return
        pipeline = self.pipeline
        preview.serial += 1
        preview.asked = (preview.serial, text, style)

        def job() -> None:
            asked = preview.asked
            if not preview.open or asked is None or (preview.made is not None and preview.made[0] >= asked[0]):
                return
            number, text_now, style_now = asked
            try:
                if preview.bed is None:
                    preview.bed = pipeline.page_without(preview.result, preview.region)
                page, done = pipeline.preview_region(preview.bed, preview.region, text_now, style_now)
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
        on. The answers go to the open editor
        (`EditBubbleDialog.show_answers`), whatever happens, with the model's error in *answer* when there was one.
        False when the model cannot be asked."""
        result, pipeline = result if result is not None else self.last_result, self.pipeline
        if pipeline is None or result is None:
            return False
        answer = answer if answer is not None else {}
        self.say("Asking the model...")

        def job() -> None:
            texts: list[str] = []
            try:
                texts = [pipeline.ask_again(result, region)]
            except TranslationError as e:
                answer["error"] = rendered(message_of(e))
            finally:  # the editor waits for the answers: they come in any case
                self._post("asked", mode=mode, texts=[t for t in texts if t])
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
        if self.role_var.get() != "translator" or self.pipeline is None or self.busy or self.reading:
            return
        if self._ordering is not None:
            self.say("Reading order: click the regions in the order they are read, then press Finish order (Esc cancels).")
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
            self.say("Could not record the rectangle: give the book a name first (the Book field).")
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
                    self._post("status", key="Could not record the rectangle: give the book a name first (the Book field).")
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
        `_rotate_region`; "direction": T's, `_turn_direction`). A region that left that page meanwhile is refused."""
        result, pipeline = result if result is not None else self.last_result, self.pipeline
        if pipeline is None or result is None:
            return
        if not holds(result, region):
            self.say(NO_REGION)
            return
        text = str(data.get("text", "")).strip()
        style = data.get("style")
        step = self._record(kind, result)
        self._go_busy()
        self.say("Storing your changes...")

        def job() -> None:
            try:
                step.begin(pipeline, [region])
                pipeline.set_region_note(result, region, str(data.get("speaker", "")), str(data.get("kind", "")),
                                         bool(data.get("continues")), str(data.get("note", "")))
                reader_note = str(data.get("reader_note", "")).strip()
                if reader_note != getattr(region, "reader_note", ""):
                    pipeline.set_reader_note(result, region, reader_note)
                if isinstance(style, RegionStyle) and style != (getattr(region, "style", None) or RegionStyle()):
                    if not pipeline.set_region_style(result, region, style):  # before the page is lettered again
                        self._post("status", key="Could not store the formatting: give the book a name first (the Book field).")
                if text and text != region.translated_text:
                    old = region.translated_text
                    if not pipeline.set_translation(result, region, text):
                        self._post("status", key="Could not keep the translation: give the book a name first (the Book field).")
                        pipeline.rerender(result)  # the page as it is stored, not as the editor's preview showed it
                    else:
                        changes = rendering_changes(pipeline.check_sheet(), region.source_text, old, text, region.speaker)
                        if changes:
                            self._post("propose", changes=changes)
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
                    self._post("status", key="Region dropped; Ctrl+Z brings it back.")
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")

        self._jobs.put(job)
        offer = getattr(self, "_offer_ignore_everywhere", None)  # (`book_areas`: a part of the window)
        if offer is not None:
            offer(region, result, step)

    # ------------------------------------------------------------------ a click on the page goes to the viewer
    def _forward_click(self, event: tk.Event) -> None:
        """A click on the page that is not TASlation's own goes on to the viewer at the same place (a viewer that turns
        its pages by clicks, its toolbar, a panel's close button), the person's click passed on as a page key is: in the
        Reader role, in reading mode, and in the Translator role while the page on show is not the translated one
        (`_editing`: there a click selects and edits the text areas, and the page keys turn the pages). It is followed
        as a page-turn key is (`_follow_change`): from the frame Auto took last, else from the frame on show - also
        before Auto has taken any page. In the Translator role the status line says so, as it does for a key."""
        if self.selected is None or (self.last_result is None and self._live is None) or viewer_rests(self):
            return
        if not self.canvas.inside(event.x, event.y) or self.canvas.in_busy_band(event.x, event.y):
            return  # beside the page, or on the busy band
        if not self._book_in_front():
            return
        x, y = self.canvas.to_image_coords(event.x, event.y)
        try:
            # the capture is the viewer's client area, without a title bar drawn in it
            post_click(self.selected.hwnd, x, y + caption_rows(self.selected.hwnd))
        except CaptureError as e:
            self.say("Viewer: {error}", error=e)
            return
        hwnd = self.selected.hwnd
        if not self.reading and self.role_var.get() == "translator":  # a reader sees the page turn
            self.status(lambda: _("Sent a click to the viewer..."))
        reference = self._auto_last if self._auto_last is not None else self._live_thumb
        self._follow_change(hwnd, reference, "", time.monotonic(), retried=True)
