"""The page's reading order on the boxes in translator mode: each region's place in a small badge beside it, clear of
the neighbouring regions and labels, hidden while the order is set by clicks and in reader mode, View > Reading-order
numbers turning them off and on (remembered in ui.json); Page > Place in reading order... putting the selected
regions at one place of the order, one change that Ctrl+Z takes back, on the real pipeline and stores; its question;
every line in every language."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from test_reading_window import Shapes, _region
from test_translator_mode import Window, _skipped_and_order, window  # noqa: F401 - the fixture, on the real pipeline

from taslation.i18n import CATALOGS, load_ui_flag, save_ui_flag
from taslation.ui import app as app_mod
from taslation.ui import area, selection
from taslation.ui.dialogs import selection as asks
from taslation.ui.preview import BADGE_TAG


def _overlap(a, b) -> bool:
    """Whether two boxes cover each other by more than a pixel's edge."""
    return min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 1


class Numbered(Shapes):
    """`test_reading_window.Shapes` with the badges drawn after every redraw, as the window draws them."""

    _page_drawn = app_mod.App._page_drawn
    _draw_order_badges = app_mod.App._draw_order_badges
    toggle_order_numbers = app_mod.App.toggle_order_numbers

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


def test_the_badges_hide_while_the_order_is_set_in_reader_mode_and_when_turned_off(numbered, tmp_path):
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
    w.order_numbers_var.set(False)  # View > Reading-order numbers, as the checkbutton sets it
    w.toggle_order_numbers()
    assert not w.canvas.find_withtag(BADGE_TAG) and load_ui_flag(tmp_path, selection.ORDER_HIDDEN)
    w.order_numbers_var.set(True)
    w.toggle_order_numbers()
    assert len(w.badge_boxes()) == 4 and not load_ui_flag(tmp_path, selection.ORDER_HIDDEN)


def test_the_choice_is_remembered_for_the_next_start(hidden_root, tmp_path):
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


class Ordered(Window):
    """`test_translator_mode.Window` with Page > Place in reading order..."""

    _also_chosen = ()
    _acting_on = app_mod.App._acting_on
    _editing = app_mod.App._editing
    place_in_order = app_mod.App.place_in_order
    _place_regions = app_mod.App._place_regions
    _focus_back = app_mod.App._focus_back

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
    w.place_in_order()
    placed = [before[-1], *before[:-1]]
    assert w.texts() == placed and w.said[-1] == selection.PLACED and len(w.history.done) == 1
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
    keys = [selection.PLACED, selection.PLACED_ALREADY, selection.PAGE_SELECTION_TIPS[2], selection.ORDER_NUMBERS_TIP,
            asks.PLACE_LINE, asks.PLACE_OF, "Place in reading order...", "Reading-order numbers", selection.ORDERING]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
            for key in keys:
                for field in ("{n}", "{place}", "{total}"):
                    assert (field in key) == (field in catalog[key]), (code, key)
