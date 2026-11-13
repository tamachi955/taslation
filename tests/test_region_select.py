"""Several regions selected at once in translator mode: Shift+click adds or takes out one, a Shift+drag rubber band
adds those inside it, and with several selected a drag, Alt+arrows, Delete, T, Paste format and Page > Set kind... and
Set text size... act on all of them, each one change that Ctrl+Z takes back (selecting them all again); Esc, Tab and a
plain click select one or none again. The pointer on the real canvas with what it starts recorded, the changes on the
real pipeline and stores; the geometry; the two questions; every line in every language."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from test_formats import two_pages  # noqa: F401 - the fixture: the window on page 1 of a book, with Paste format
from test_reading_window import Shapes, _region
from test_translator_mode import Rotating, _move, _picture, window  # noqa: F401 - the fixture, on the real pipeline

from taslation.annotations import STYLE_SIZES, RegionStyle
from taslation.i18n import CATALOGS
from taslation.ui import app as app_mod
from taslation.ui import area, selection, shortcuts, translator
from taslation.ui.dialogs import review
from taslation.ui.dialogs import selection as asks
from taslation.ui.translator import BAND_TAG, chosen_regions, group_offset

SHIFT = SimpleNamespace(state=0x0001)


def _at(x, y, shift=False):
    return SimpleNamespace(x=x, y=y, state=0x0001 if shift else 0)


def _ids(regions):
    return [id(r) for r in regions]


# ------------------------------------------------------------------ the geometry
def test_a_point_is_inside_a_turned_frame_only_within_its_own_sides():
    square = area.box_corners((0, 0, 100, 100))
    assert area.inside_frame(square, 50, 50) and area.inside_frame(square, 0, 100)  # the edges count
    assert not area.inside_frame(square, 101, 50) and not area.inside_frame(square, 50, -1)
    diamond = area.turn_corners(square, 45.0)
    assert area.inside_frame(diamond, 50, 50)
    assert not area.inside_frame(diamond, 3, 3)  # inside the box round it, outside the turned frame


def test_several_boxes_move_together_and_stop_where_the_first_meets_the_edge():
    boxes = [(50, 50, 150, 120), (200, 150, 300, 250)]
    assert area.shift_within(boxes, 10, -5, (400, 300)) == (10, -5)
    assert area.shift_within(boxes, 500, 0, (400, 300)) == (100, 0)  # the right one stops at the page's edge
    assert area.shift_within(boxes, -80, -80, (400, 300)) == (-50, -50)  # the left one at the top left
    assert area.shift_within([], 10, 10, (400, 300)) == (0, 0)


def test_a_rubber_band_takes_in_the_boxes_wholly_inside_it_drawn_either_way():
    boxes = [(50, 50, 150, 120), (200, 150, 300, 250), (320, 20, 390, 80)]
    assert area.boxes_within((30, 30, 310, 260), boxes) == [0, 1]  # the third is only partly inside
    assert area.boxes_within((310, 260, 30, 30), boxes) == [0, 1]  # dragged up and to the left
    assert area.boxes_within((0, 0, 10, 10), boxes) == []


def test_the_selected_regions_are_the_selected_one_first_and_the_others_still_on_the_page():
    a, b, c = (SimpleNamespace(x0=x, y0=x, bbox=(x, x, x + 10, x + 10)) for x in (0, 20, 40))
    w = SimpleNamespace(_chosen_region=None, _also_chosen=[b], last_result=SimpleNamespace(regions=[a, b]))
    assert chosen_regions(w) == []  # nothing selected: the others do not count
    w._chosen_region = a
    assert chosen_regions(w) == [a, b]
    w._also_chosen = [b, c, a]  # c is on no page on show; a is the selected one already
    assert chosen_regions(w) == [a, b]
    assert chosen_regions(SimpleNamespace(_chosen_region=a)) == [a]  # a window part without the others: one
    assert group_offset(w) == (0, 0)
    w._grip_box = (5, -3, 15, 7)
    assert group_offset(w) == (5, -3)


# ------------------------------------------------------------------ the pointer and the keys
class Several(Shapes):
    """`test_reading_window.Shapes` with the selection of several; the changes on all of them are recorded."""

    _toggle_chosen = app_mod.App._toggle_chosen
    _band_select = app_mod.App._band_select
    _set_chosen = app_mod.App._set_chosen
    _say_selection = app_mod.App._say_selection
    _tab_region = app_mod.App._tab_region
    _nudge_key = app_mod.App._nudge_key
    _nudge_done = app_mod.App._nudge_done

    def __init__(self, root, regions):
        super().__init__(root, regions)
        self._also_chosen = []
        self.group_moves, self.group_drops, self.later = [], [], []

    def _move_regions(self, regions, dx, dy):
        self.group_moves.append((_ids(regions), dx, dy))
        self._grip_box = None

    def _drop_regions(self, regions):
        self.group_drops.append(_ids(regions))

    def after(self, _ms, call):
        self.later.append(call)
        return "nudge"

    def after_cancel(self, _job):
        pass

    def shift_click(self, x, y, to=None):
        self._on_press(_at(x, y, shift=True))
        if to:
            self._on_drag(_at(to[0], to[1], shift=True))
        end = to or (x, y)
        self._on_release(_at(end[0], end[1], shift=True))


@pytest.fixture
def page3(hidden_root):
    a, b, c = _region((50, 50, 150, 120)), _region((200, 150, 300, 250)), _region((320, 20, 390, 80))
    return Several(hidden_root, [a, b, c]), a, b, c


def test_shift_click_adds_a_region_and_takes_it_out_again(page3):
    w, a, b, _c = page3
    w.click(100, 80)
    w.shift_click(250, 200)  # Shift+click: b added
    assert _ids(chosen_regions(w)) == _ids([a, b]) and w._status_key == selection.SEVERAL
    # each framed two-tone, without handles and without the rotate handle (they move together, one resize each is
    # for one region alone)
    assert len(w.canvas.find_withtag("chosen")) == 2 * 2
    w.shift_click(250, 200)  # again: taken out
    assert _ids(chosen_regions(w)) == _ids([a]) and len(w.canvas.find_withtag("chosen")) == 2 + 8 + 3
    w.shift_click(100, 80)  # the only one taken out: nothing selected
    assert chosen_regions(w) == [] and not w.canvas.find_withtag("chosen")
    w.shift_click(250, 200)  # with nothing selected, Shift+click selects
    assert _ids(chosen_regions(w)) == _ids([b])
    w.shift_click(10, 290)  # Shift+click on empty space changes nothing
    assert _ids(chosen_regions(w)) == _ids([b]) and not w.added


def test_a_shift_drag_draws_a_band_and_selects_the_regions_wholly_inside_it(page3):
    w, a, b, c = page3
    w._on_press(_at(30, 30, shift=True))
    w._on_drag(_at(200, 160, shift=True))
    w._on_drag(_at(310, 260, shift=True))
    assert w.canvas.find_withtag(BAND_TAG)  # the band shows while it is drawn
    w._on_release(_at(310, 260, shift=True))
    assert not w.canvas.find_withtag(BAND_TAG) and not w.added  # no region was added: the band selects
    assert _ids(chosen_regions(w)) == _ids([a, b]) and w._status_key == selection.SEVERAL  # c is partly outside
    w._on_press(_at(395, 10, shift=True))  # another band adds to the selection
    w._on_release(_at(310, 90, shift=True))
    assert _ids(chosen_regions(w)) == _ids([a, b, c])


def test_a_drag_on_any_selected_region_moves_them_all_and_a_click_selects_one_alone(page3):
    w, a, b, _c = page3
    w.click(100, 80)
    w.shift_click(250, 200)
    w._on_press(_at(250, 200))  # b, the second selected: they all move
    w._on_drag(_at(260, 215))
    assert w._grip_box == (60, 65, 160, 135)  # the first one's box, moved: every frame goes with it
    frames = sorted(tuple(round(v) for v in w.canvas.coords(i)) for i in w.canvas.find_withtag("chosen")
                    if "edge" not in w.canvas.gettags(i))
    assert frames == [(60, 65, 160, 135), (210, 165, 310, 265)]
    w._on_release(_at(260, 215))
    assert w.group_moves == [(_ids([a, b]), 10, 15)] and not w.moved  # one move of both
    assert _ids(chosen_regions(w)) == _ids([a, b])
    w.click(250, 200, to=(500, 200))  # far to the right: they stop where b meets the page's edge
    assert w.group_moves[-1] == (_ids([a, b]), 100, 0)
    w.click(250, 200, to=(251, 201))  # pressed and barely moved: b alone
    assert _ids(chosen_regions(w)) == _ids([b]) and len(w.group_moves) == 2


def test_esc_tab_and_a_click_elsewhere_select_one_or_none_again(page3):
    w, a, b, _c = page3
    w.click(100, 80)
    w.shift_click(250, 200)
    w._on_escape()
    assert chosen_regions(w) == [] and not w.canvas.find_withtag("chosen")
    w.click(100, 80)
    w.shift_click(250, 200)
    assert w._tab_region(1) == "break"
    assert len(chosen_regions(w)) == 1 and chosen_regions(w)[0] is not a  # the next one in reading order, alone
    w.click(100, 80)
    w.shift_click(355, 50)
    w.click(250, 200)  # a plain click on a region not selected: it alone
    assert _ids(chosen_regions(w)) == _ids([b])
    w.shift_click(355, 50)
    w.click(10, 290)  # on empty space: none
    assert chosen_regions(w) == []


def test_delete_drops_the_selected_regions_together_and_shift_on_a_handle_still_resizes(page3):
    w, a, b, _c = page3
    w.click(100, 80)
    w.shift_click(250, 200)
    w._drop_chosen()
    assert w.group_drops == [_ids([a, b])] and not w.dropped and chosen_regions(w) == []
    w.click(100, 80)
    w._drop_chosen()  # one selected: as before
    assert w.dropped == [a] and len(w.group_drops) == 1
    w.click(250, 200)
    w.shift_click(300, 250, to=(320, 260))  # Shift on the selected region's handle: a resize, not a band
    assert w.moved == [(b, (200, 150, 320, 260))]


def test_a_plain_drag_on_empty_space_still_adds_a_region(page3):
    w, a, b, _c = page3
    w.click(100, 80)
    w.shift_click(250, 200)
    w.click(10, 200, to=(40, 290))
    assert w.added == [(10, 200, 40, 290)] and chosen_regions(w) == []


def test_alt_arrows_move_the_selected_regions_together_as_one_move(page3):
    w, a, b, _c = page3
    w.click(100, 80)
    w.shift_click(250, 200)
    w._nudge_key(SimpleNamespace(state=0), "Right")
    w._nudge_key(SimpleNamespace(state=0), "Right")
    w._nudge_key(SHIFT, "Down")
    assert w._grip_box == (52, 60, 152, 130)
    w.later[-1]()  # the presses stop
    assert w.group_moves == [(_ids([a, b]), 2, 10)] and not w.moved
    for _ in range(9):
        w._nudge_key(SHIFT, "Down")  # b meets the bottom: they stop together
    w.later[-1]()
    assert w.group_moves[-1] == (_ids([a, b]), 0, 50)


def test_a_turned_region_among_several_is_framed_turned_without_handles(page3):
    w, a, b, _c = page3
    b.style = RegionStyle(slant=30.0)
    w.click(100, 80)
    w.shift_click(250, 200)
    items = w.canvas.find_withtag("chosen")
    assert len(items) == 2 * 2 and any(w.canvas.type(i) == "polygon" for i in items)


# ------------------------------------------------------------------ on the real pipeline: one change each
class Group(Rotating):
    """`test_translator_mode.Rotating` (the pointer on the real pipeline) with the selection of several, its changes
    and the Page menu's questions."""

    _also_chosen = ()
    _toggle_chosen = app_mod.App._toggle_chosen
    _set_chosen = app_mod.App._set_chosen
    _say_selection = app_mod.App._say_selection
    _acting_on = app_mod.App._acting_on
    _drop_regions = app_mod.App._drop_regions
    _restyle_regions = app_mod.App._restyle_regions
    _set_kinds = app_mod.App._set_kinds
    _move_regions = app_mod.App._move_regions
    _drop_chosen = app_mod.App._drop_chosen
    set_kind_of_selection = app_mod.App.set_kind_of_selection
    set_size_of_selection = app_mod.App.set_size_of_selection
    _focus_back = app_mod.App._focus_back

    def _choose(self, region):
        self._chosen_region, self._also_chosen = region, []

    def select(self, *texts):
        self._set_chosen([self.region(t) for t in texts])


def test_several_dropped_at_once_are_one_change_and_come_back_selected(window):
    w = Group(window.pipeline, window.last_result)
    start, picture = w.state(), _picture(w)
    w.select("Where are you going?", "Thank you.")
    gone = list(chosen_regions(w))
    count = len(w.last_result.regions)
    w._drop_chosen()
    assert len(w.last_result.regions) == count - 2 and not any(r is g for r in w.last_result.regions for g in gone)
    assert w.said[-1] == selection.DROPPED and len(w.history.done) == 1 and w.history.done[-1].kind == "drops"
    assert [r.order for r in w.last_result.regions] == list(range(count - 2))
    dropped = w.state()
    w.undo_edit()
    assert w.said[-1] == "The dropped regions are back." and w.state() == start
    assert np.array_equal(_picture(w), picture) and sorted(_ids(chosen_regions(w))) == sorted(_ids(gone))
    w.redo_edit()
    assert w.said[-1] == "Regions dropped again." and w.state() == dropped and chosen_regions(w) == []


def test_t_with_several_selected_turns_them_all_as_one_change(window):
    w = Group(window.pipeline, window.last_result)
    start = w.state()
    w.select("Hello there!", "It's fine.")
    w._turn_direction()
    assert all(r.style.direction == "down" for r in chosen_regions(w)) and len(w.history.done) == 1
    w.undo_edit()
    assert w.said[-1] == "Text direction taken back." and w.state() == start
    assert len(chosen_regions(w)) == 2


def test_set_kind_and_set_text_size_act_on_the_selected_regions_one_change_each(window, monkeypatch):
    w = Group(window.pipeline, window.last_result)
    start = w.state()
    answers = iter(["shout", 30, 0])
    asked = []
    monkeypatch.setattr(selection, "ask_dialog", lambda make: (asked.append(make), next(answers))[1])
    w.set_kind_of_selection()
    assert w.said[-1] == "Select a region first (click it)." and not asked  # nothing selected: nothing asked
    w.select("Hello there!", "It's fine.")
    group = chosen_regions(w)
    w.set_kind_of_selection()
    assert [r.tag for r in group] == ["shout", "shout"] and w.said[-1] == selection.KIND_SET
    assert len(w.history.done) == 1 and w.history.done[-1].kind == "kind"
    kinds = w.state()
    w.set_size_of_selection()
    assert [r.style.size for r in group] == [30, 30] and w.said[-1] == selection.SIZE_SET
    assert len(w.history.done) == 2 and w.history.done[-1].kind == "size"
    w.set_size_of_selection()  # Auto again
    assert [(r.style or RegionStyle()).size for r in group] == [0, 0] and len(w.history.done) == 3  # (no style left)
    w.undo_edit()
    w.undo_edit()
    assert w.said[-1] == "Text size taken back." and w.state() == kinds
    w.undo_edit()
    assert w.said[-1] == "Kind taken back." and w.state() == start and [r.tag for r in group] == ["", ""]
    w.redo_edit()
    assert w.said[-1] == "Kind set again." and [r.tag for r in group] == ["shout", "shout"]
    w._set_kinds(group, "shout")  # what they have already: no change
    assert w.said[-1] == selection.NOTHING_TO_CHANGE and len(w.history.done) == 1


def test_a_drag_of_several_on_the_real_pipeline_is_one_move_that_undo_takes_back(window):
    w = Group(window.pipeline, window.last_result)
    start = w.state()
    w.select("Thank you.", "It's fine.")
    first, second = chosen_regions(w)
    old = (first.bbox, second.bbox)
    x, y = (first.x0 + first.x1) // 2, (first.y0 + first.y1) // 2
    w._on_press(_move(x, y))
    w._on_drag(_move(x + 4, y + 3))
    w._on_drag(_move(x + 8, y + 6))
    assert [i[0] for i in w.canvas.items] == ["box", "box"]  # two frames, no handles, no rotate handle
    w._on_release(_move(x + 8, y + 6))
    assert len(w.history.done) == 1 and w.history.done[-1].kind == "move"
    assert first.bbox == tuple(v + d for v, d in zip(old[0], (8, 6, 8, 6)))
    assert second.bbox == tuple(v + d for v, d in zip(old[1], (8, 6, 8, 6)))
    w.undo_edit()
    assert w.said[-1] == "Move taken back." and (first.bbox, second.bbox) == old and w.state() == start
    assert sorted(_ids(chosen_regions(w))) == sorted(_ids([first, second]))


def test_paste_format_puts_the_formatting_on_every_selected_region(two_pages):
    w, _second = two_pages
    result = w.last_result
    targets = [r for r in result.regions if r.translated_text in ("Thank you.", "It's fine.")]
    w.format_clip().style = RegionStyle(colour="white", outline=False)
    w._chosen_region, w._also_chosen = targets[0], [targets[1]]
    assert w._format_targets() == targets
    w.paste_format()
    assert all(r.style == RegionStyle(colour="white", outline=False) for r in targets) and len(w.history) == 1
    w.undo_edit()
    assert all(r.style is None for r in targets)


# ------------------------------------------------------------------ the questions and the lines
def test_the_kind_question_gives_the_kind_chosen_and_cancel_gives_none(hidden_root):
    d = asks.KindDialog(hidden_root, 3, "shout")
    assert d.kind_var.get() == "Shout" and "3" in str(d.line.cget("text"))
    d.kind_var.set(review.REGION_KIND_WORDS["thought"])
    d._ok()
    assert d.answer == "thought" and not d.winfo_exists()
    d = asks.KindDialog(hidden_root, 2)
    d.destroy()  # Cancel, Esc, the close box
    assert d.answer is None


def test_the_size_question_gives_a_size_within_bounds_or_auto(hidden_root):
    d = asks.SizeDialog(hidden_root, 2, 0)
    assert d.auto_var.get() and str(d.size_spin.cget("state")) == "disabled"
    d._ok()
    assert d.answer == 0  # Auto
    d = asks.SizeDialog(hidden_root, 2, 40)
    assert not d.auto_var.get() and d.size_var.get() == "40"
    d.size_var.set("not a size")
    d._ok()
    assert d.answer is None and d.winfo_exists()  # it rings and stays
    d.size_var.set("5000")
    d._ok()
    assert d.answer == STYLE_SIZES[1]
    assert asks.whole("12,6") == 13 and asks.whole("") is None


def test_every_line_of_the_selection_is_in_every_language():
    keys = [selection.SEVERAL, selection.NOTHING_TO_CHANGE, selection.DROPPED, selection.KIND_SET, selection.SIZE_SET,
            *selection.UNDONE.values(), *selection.REDONE.values(), *selection.PAGE_SELECTION_TIPS[:2],
            asks.KIND_LINE, asks.SIZE_LINE, "Set kind...", "Set text size..."]
    keys += [text for row in shortcuts.FIXED_GESTURES for text in row  # the Keys topic's rows of the selection
             if text.startswith(("Shift+click", "Shift+drag", "Several selected", "Add a region to", "Add every",
                                 "Removing, the text"))]
    assert len(keys) == 23
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
    for key in keys:  # the placeholders survive the translation
        for code, catalog in CATALOGS.items():
            if code != "en":
                assert ("{n}" in key) == ("{n}" in catalog[key]), (code, key)
    assert all(v in translator.TAKEN_BACK.values() for v in selection.UNDONE.values())
