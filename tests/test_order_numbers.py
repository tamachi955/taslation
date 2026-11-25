"""The page's reading order on the boxes in translator mode: each region's place in a small badge beside it, clear of
the neighbouring regions and labels, hidden while the order is set by clicks, in reader mode and while ui.json says
they were turned off; the Menu's Page > Place in reading order... putting the selected regions at one place of the
order, each on its own page of a spread (kept so by the next reading), one change that Undo takes back, on the real
pipeline and stores; every tool's new order (a plate's place, Place in reading order..., Reading order clicked
through) asking the lines whose context changed alike; its question; every line in every language."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
import test_page_units as page_units
from PIL import Image, ImageDraw
from test_reading_window import Shapes, _region
from test_translator_mode import Window, _skipped_and_order, window  # noqa: F401 - the fixture, on the real pipeline

from taslation.annotations import BookAnnotations
from taslation.cache import CacheStore
from taslation.fingerprint import PageUnit
from taslation.i18n import CATALOGS, save_ui_flag
from taslation.ui import app as app_mod
from taslation.ui import area, see_edit, selection, translator
from taslation.ui.dialogs import selection as asks
from taslation.ui.preview import BADGE_TAG


def _overlap(a, b) -> bool:
    """Whether two boxes cover each other by more than a pixel's edge."""
    return min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 1


class Numbered(Shapes):
    """`test_reading_window.Shapes` with the badges drawn after every redraw, as the window draws them."""

    _page_drawn = app_mod.App._page_drawn
    _draw_order_badges = app_mod.App._draw_order_badges

    def __init__(self, root, regions, state_dir):
        super().__init__(root, regions)
        self.settings = SimpleNamespace(state_dir=state_dir)
        self.order_numbers_var = tk.BooleanVar(master=root, value=True)
        self._also_chosen = []
        self.canvas.on_redraw = self._page_drawn
        self._redisplay()

    def _redisplay(self):
        self.canvas._redraw()

    def badges(self):
        texts = sorted(self.canvas.find_withtag("order-badge-text"), key=lambda i: int(self.canvas.itemcget(i, "text")))
        return [(self.canvas.itemcget(i, "text"), tuple(self.canvas.bbox(i))) for i in texts]

    def badge_boxes(self):
        return [tuple(self.canvas.bbox(i)) for i in self.canvas.find_withtag("order-badge-box")]


@pytest.fixture
def numbered(hidden_root, tmp_path):
    regions = [_region((250, 40, 330, 120)), _region((60, 40, 200, 110)), _region((60, 150, 160, 260)),
               _region((210, 160, 330, 200))]
    return Numbered(hidden_root, regions, tmp_path), regions


def test_every_region_shows_its_place_in_the_reading_order_clear_of_its_neighbours(numbered):
    w, regions = numbered
    assert [t for t, _box in w.badges()] == ["1", "2", "3", "4"]  # in the order of `_page_regions`
    boxes = w.badge_boxes()
    shown = [area.box_to_canvas(r.bbox, w.canvas.scale, w.canvas.offset) for r in regions]
    assert len(boxes) == 4
    for i, badge in enumerate(boxes):
        assert not any(_overlap(badge, other) for other in shown), i  # no region's text is covered
        assert not any(_overlap(badge, other) for j, other in enumerate(boxes) if j != i)  # nor another badge
        x0, y0, x1, y1 = w.canvas._shown
        assert x0 - 1 <= badge[0] and y0 - 1 <= badge[1] and badge[2] <= x1 + 1 and badge[3] <= y1 + 1  # on the page
    first = boxes[0]  # beside its own region: within a badge's height of it
    r0 = shown[0]
    assert min(abs(first[3] - r0[1]), abs(first[1] - r0[3]), abs(first[0] - r0[2]), abs(first[2] - r0[0])) <= 6
    w.click(290, 80)  # the selection is drawn over them
    assert w.canvas.find_withtag("chosen") and len(w.badge_boxes()) == 4


def test_a_badge_leaves_the_labels_free(numbered):
    w, regions = numbered
    w.canvas.overlay = [(r.bbox, "#ffb347", "speaker") for r in regions]  # each region's label (as live mode gives)
    w._redisplay()
    labels = [tuple(w.canvas.bbox(i)) for i in w.canvas.find_withtag("overlay-label-box")]
    assert len(labels) == 4
    for badge in w.badge_boxes():
        assert not any(_overlap(badge, label) for label in labels)


def test_the_badges_hide_while_the_order_is_set_in_reader_mode_and_when_turned_off(numbered):
    w, _regions = numbered
    w._ordering = []  # the reading order set by clicks: the labels carry the numbers
    w._redisplay()
    assert not w.canvas.find_withtag(BADGE_TAG)
    w._ordering = None
    w.role_var.set("reader")
    w._redisplay()
    assert not w.canvas.find_withtag(BADGE_TAG)
    w.role_var.set("translator")
    w._redisplay()
    assert len(w.badge_boxes()) == 4
    w.order_numbers_var.set(False)  # turned off (ui.json's `ORDER_HIDDEN` at the start)
    w._redisplay()
    assert not w.canvas.find_withtag(BADGE_TAG)
    w.order_numbers_var.set(True)
    w._redisplay()
    assert len(w.badge_boxes()) == 4


def test_the_choice_made_earlier_is_read_at_the_start(hidden_root, tmp_path):
    class Host(tk.Frame):
        _init_selection = app_mod.App._init_selection

    host = Host(hidden_root)
    host.settings = SimpleNamespace(state_dir=tmp_path)
    host._init_selection()
    assert host.order_numbers_var.get() and host._also_chosen == []  # on at first
    save_ui_flag(tmp_path, selection.ORDER_HIDDEN, True)
    host._init_selection()
    assert not host.order_numbers_var.get()
    host.destroy()


# ------------------------------------------------------------------ Place in reading order...
def test_the_selected_regions_go_to_the_place_asked_together_in_their_order():
    a, b, c, d, e = "abcde"
    assert selection.placed_order([a, b, c, d, e], [d], 1) == [d, a, b, c, e]
    assert selection.placed_order([a, b, c, d, e], [e, b], 2) == [a, b, e, c, d]  # in their reading order
    assert selection.placed_order([a, b, c, d, e], [a], 99) == [b, c, d, e, a]  # past the end: last
    assert selection.placed_order([a, b, c, d, e], [c], 0) == [c, a, b, d, e]


def test_a_place_on_the_facing_page_puts_the_region_first_or_last_on_its_own_page():
    a1, a2, a3, b1, b2, b3 = (SimpleNamespace(unit=0), SimpleNamespace(unit=0), SimpleNamespace(unit=0),
                              SimpleNamespace(unit=1), SimpleNamespace(unit=1), SimpleNamespace(unit=1))
    shown = [a1, a2, a3, b1, b2, b3]  # (a spread: the page read first, then the other; the numbers 1 to 6)

    def placed(chosen, place):
        return selection.placed_order(shown, chosen, place)

    assert placed([b3], 1) == [a1, a2, a3, b3, b1, b2]  # (a place on the page before: first on its own)
    assert placed([b3], 3) == [a1, a2, a3, b3, b1, b2]
    assert placed([a1], 5) == [a2, a3, a1, b1, b2, b3]  # (a place on the page after: last on its own)
    assert placed([a1], 99) == [a2, a3, a1, b1, b2, b3]
    assert placed([b3], 4) == [a1, a2, a3, b3, b1, b2]  # (on its own page: that place)
    assert placed([a3], 2) == [a1, a3, a2, b1, b2, b3]
    assert placed([a2, b3], 1) == [a2, a1, a3, b3, b1, b2]  # (several: each on its own page, the pages' places kept)


class Ordered(Window):
    """`test_translator_mode.Window` with Page > Place in reading order... and every new order taken alike (the lines
    whose context changed asked again)."""

    _also_chosen = ()
    _acting_on = app_mod.App._acting_on
    _editing = app_mod.App._editing
    place_in_order = app_mod.App.place_in_order
    _place_regions = app_mod.App._place_regions
    _order_taken = app_mod.App._order_taken
    _ask_after_order = app_mod.App._ask_after_order

    def texts(self):
        return [r.translated_text for r in self._page_regions()]


def test_place_in_reading_order_is_one_change_that_undo_takes_back(window, monkeypatch):
    w = Ordered(window.pipeline, window.last_result)
    answers = []
    monkeypatch.setattr(selection, "ask_dialog", lambda make: answers.pop(0))
    before = w.texts()
    assert len(before) >= 4 and _skipped_and_order(w) == (False, 0)
    w.place_in_order()
    assert w.said[-1] == "Select a region first (click it)."  # nothing selected
    w._chosen_region = w._page_regions()[-1]
    answers.append(None)  # Cancel: nothing changes
    w.place_in_order()
    assert w.texts() == before and not w.history.done
    answers.append(1)
    w.place_in_order()  # (the lines whose context changed asked again: the same answers here)
    placed = [before[-1], *before[:-1]]
    assert w.texts() == placed and w.said[-1] == selection.PLACED_ASKED and len(w.history.done) == 1
    assert w.history.done[-1].kind == "order" and _skipped_and_order(w) == (False, len(before))
    assert [r.order for r in w.last_result.regions] == list(range(len(w.last_result.regions)))
    w._chosen_region = w._page_regions()[0]
    answers.append(1)  # where it is already: nothing to do
    w.place_in_order()
    assert w.said[-1] == selection.PLACED_ALREADY and len(w.history.done) == 1
    w.undo_edit()
    assert w.said[-1] == "Reading order taken back." and _skipped_and_order(w) == (False, 0) and w.texts() == before
    w.redo_edit()
    assert w.said[-1] == "Reading order made again." and w.texts() == placed  # read again with the order stored


def test_several_selected_go_to_one_place_together(window, monkeypatch):
    w = Ordered(window.pipeline, window.last_result)
    monkeypatch.setattr(selection, "ask_dialog", lambda make: 2)
    before = w.texts()
    regions = w._page_regions()
    w._chosen_region, w._also_chosen = regions[3], [regions[0]]
    w.place_in_order()
    assert w.texts() == [before[1], before[0], before[3], *before[2:3], *before[4:]]
    assert len(w.history.done) == 1


def test_a_place_typed_on_a_plate_asks_the_lines_after_it_again_but_the_persons_own_and_undo_takes_all_back(
        window, monkeypatch):
    w = Ordered(window.pipeline, window.last_result)
    regions = w._page_regions()
    mine = regions[1]
    assert w.pipeline.set_translation(w.last_result, mine, "My own words.") and w.pipeline.corrected(w.last_result,
                                                                                                    mine)
    assert not w.pipeline.corrected(w.last_result, regions[0])
    start, before = w.state(), w.texts()
    asked = []

    def ask_again(result, region, source=None):
        asked.append((region, [r.translated_text for r in result.regions[:3]]))
        return "Said anew."

    monkeypatch.setattr(w.pipeline, "ask_again", ask_again)
    w._place_regions([regions[2]], 1)
    placed = [regions[2], regions[0], regions[1], *regions[3:]]
    assert all(a is b for a, b in zip(w._page_regions(), placed))
    lines = [r for r in placed if r is not mine and r.status == "translated"]
    assert len(lines) >= 3 and [r for r, _context in asked] == lines  # (from the first place changed on, in order)
    assert asked[1][1][0] == "Said anew."  # (each after the lines before it as they are by then)
    assert w.texts()[2] == "My own words." and w.texts().count("Said anew.") == len(lines)
    assert w.said[-1] == selection.PLACED_ASKED and not w.busy and len(w.history.done) == 1
    assert w.history.done[-1].kind == "order" and _skipped_and_order(w) == (False, len(before))
    w.undo_edit()
    assert w.said[-1] == "Reading order taken back." and _skipped_and_order(w) == (False, 0)
    assert w.state()[1] == start[1] and w.texts() == before  # (the translations as they were, the order too)
    asked.clear()
    w._place_regions([w._page_regions()[0]], 1)  # (where it is already: nothing asked)
    assert w.said[-1] == selection.PLACED_ALREADY and not asked


@pytest.mark.parametrize("path", ["plate", "menu", "tool"])
def test_every_tool_s_new_order_asks_the_lines_whose_context_changed_alike(window, monkeypatch, path):
    """A place typed on a plate, Page > Place in reading order... and the Menu's Reading order clicked through: the
    same order makes the same lines asked again, in the same order, as one "order" change that Undo takes back."""
    w = Ordered(window.pipeline, window.last_result)
    regions, before = w._page_regions(), w.texts()
    asked = []
    monkeypatch.setattr(w.pipeline, "ask_again",
                        lambda result, region, source=None: asked.append(region) or "Said anew.")
    placed = [regions[2], regions[0], regions[1], *regions[3:]]
    if path == "plate":
        w._place_regions([regions[2]], 1)
    elif path == "menu":
        monkeypatch.setattr(selection, "ask_dialog", lambda make: 1)
        w._chosen_region = regions[2]
        w.place_in_order()
    else:
        w._ordering = list(placed)
        w.toggle_order()
    assert all(a is b for a, b in zip(w._page_regions(), placed))
    lines = [r for r in placed if r.status == "translated"]
    assert len(lines) >= 3 and asked == lines and w.texts().count("Said anew.") == len(lines)
    assert w.said[-1] == (translator.ORDER_SAVED_ASKED if path == "tool" else selection.PLACED_ASKED)
    assert not w.busy and len(w.history.done) == 1 and w.history.done[-1].kind == "order"
    w.undo_edit()
    assert w.said[-1] == "Reading order taken back." and w.texts() == before and _skipped_and_order(w) == (False, 0)


def _spread_capture():
    """The spread of `test_page_units` with both pages white, two bubbles on each (each with its own column of
    strokes, so that the OCR's memo tells them apart)."""
    img = Image.new("RGB", (920, 720), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for page in (page_units.LEFT, page_units.RIGHT):
        d.rectangle((page[0], page[1], page[2] - 1, page[3] - 1), fill=(255, 255, 255))
    for n, box in enumerate(SPREAD_BUBBLES):
        d.ellipse(box, fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        cx = (box[0] + box[2]) // 2
        for k in range(2 + n):
            d.line((cx - 10, box[1] + 40 + 28 * k, cx + 10, box[1] + 52 + 28 * k), fill=(0, 0, 0), width=3)
    return img


SPREAD_BUBBLES = ((520, 120, 640, 290), (680, 375, 800, 500),  # the right page, read first
                  (140, 100, 260, 270), (140, 400, 260, 570))  # the left page


def _stored_order(w, index):
    unit = w.last_result.units[index]
    page = w.pipeline.annotations.lookup(unit.fingerprint, unit.aspect, 6)
    return len(page.order) if page is not None else 0


def test_a_place_on_a_spread_keeps_the_region_on_its_own_page_and_the_next_reading_keeps_the_order(
        settings, monkeypatch):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    units = [PageUnit(page_units.RIGHT, page_units.FP_RIGHT, 0), PageUnit(page_units.LEFT, page_units.FP_LEFT, 1)]
    pipeline, _tr = page_units._pipeline(settings, monkeypatch, units, boxes=SPREAD_BUBBLES, cache=cache,
                                         annotations=ann)
    w = Ordered(pipeline, pipeline.process(_spread_capture(), complete=True))
    a1, a2, b1, b2 = shown = w._page_regions()
    assert [r.unit for r in shown] == [0, 0, 1, 1] and all(r.status == "translated" for r in shown)
    asked = []
    monkeypatch.setattr(pipeline, "ask_again", lambda result, region, source=None: asked.append(region) or "Anew.")
    w._place_regions([b2], 1)  # (place 1 belongs to the right page: the left page's first)
    assert [r.bbox for r in w._page_regions()] == [a1.bbox, a2.bbox, b2.bbox, b1.bbox]
    assert w.said[-1] == selection.PLACED_ASKED and asked == [b2, b1]  # (from the first place changed on)
    assert (_stored_order(w, 0), _stored_order(w, 1)) == (0, 2)  # (the right page's order is not touched)
    w._place_regions([a1], 4)  # (place 4 belongs to the left page: the right page's last)
    order = [a2.bbox, a1.bbox, b2.bbox, b1.bbox]
    assert [r.bbox for r in w._page_regions()] == order and _stored_order(w, 0) == 2
    w.last_result = pipeline.process(_spread_capture(), complete=True)  # (the next reading: the order stays)
    assert w.last_result.cache_hits == 2 and [r.bbox for r in w._page_regions()] == order


def test_place_in_reading_order_waits_while_the_order_is_set_by_clicks(window, monkeypatch):
    w = Ordered(window.pipeline, window.last_result)
    monkeypatch.setattr(selection, "ask_dialog", lambda make: pytest.fail("asked while ordering"))
    w._chosen_region = w._page_regions()[0]
    w._ordering = []
    w.place_in_order()
    assert w.said[-1] == selection.ORDERING and not w.history.done


def test_the_place_question_gives_a_place_from_one_to_the_total(hidden_root):
    d = asks.PlaceDialog(hidden_root, 2, 5, 3)
    assert d.place_var.get() == "3" and "2" in str(d.line.cget("text"))
    d.place_var.set("9")
    d._ok()
    assert d.answer == 5 and not d.winfo_exists()
    d = asks.PlaceDialog(hidden_root, 1, 5, 1)
    d.place_var.set("x")
    d._ok()
    assert d.answer is None and d.winfo_exists()
    d.place_var.set("0")
    d._ok()
    assert d.answer == 1


def test_every_line_of_the_reading_order_numbers_is_in_every_language():
    keys = [selection.PLACED, selection.PLACED_ALREADY, asks.PLACE_LINE, asks.PLACE_OF, "Place in reading order...",
            selection.ORDERING, selection.PLACED_ASKED, translator.ORDER_SAVED, translator.ORDER_SAVED_ASKED,
            see_edit.PLACE_ASK, see_edit.PLACE_ASK_SPREAD]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
            for key in keys:
                for field in ("{n}", "{place}", "{total}"):
                    assert (field in key) == (field in catalog[key]), (code, key)
