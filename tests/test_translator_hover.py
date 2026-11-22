"""A bubble's original under the pointer in the Translator role's normal window (`ui.hover`, `ui.zoom`,
`ui.in_place`, `ui.bubble_text`), beside the Translator's own pointer (`TranslatorMixin`): the original shows after
the rest in both ways - a panel beside the bubble, the bubble itself -, with `bubble_zoom` and Show original as ever;
it never shows while a button is down, during a drag, a move or a rectangle drawn, on a handle of the selected region,
or with the region editor or a modal dialog open; a press takes it away and still selects; the panel keeps clear of
the selected region's handles; the bubble shown in its place leaves the frames, numbers and the selection drawn over it
and changes nothing of the page. The stand-in of `test_hover_reveal` (on the shared hidden root, never mapped; the
popup made but not shown) with the Translator's handlers borrowed from the window, called in the order the window's
bindings have them (the panel's binding tag first, then the page's own): no event of the system's, no real window
chosen or touched, a scratch state folder, and nothing of a page written anywhere."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image
from test_hover_reveal import INK, SET, WORK, Window, _labels

from taslation.config import Settings
from taslation.ui import app as app_mod
from taslation.ui import area, zoom
from taslation.ui.live import LiveViewMixin
from taslation.ui.progress import Filling
from taslation.ui.selection import BADGE_TAG
from taslation.ui.zoom import HOLD_MS, ZOOM_DELAY_MS, ZOOM_GAP, ZOOM_REST_MS

A = app_mod.App
B1 = 0x100  # an event's state with the left button held


class Desk(Window):
    """`test_hover_reveal.Window` in the Translator role's normal window, with the Translator's own pointer: a press
    selects, a drag moves, resizes, turns or draws (`TranslatorMixin._on_press`, `_on_drag`, `_on_release`), a double
    click opens the region editor (a stand-in, modal while open); the regions' frames with their labels and numbers
    (`LiveViewMixin._overlay_items`, `SelectionMixin._draw_order_badges`) and the selected region's frame and handles
    drawn over the page as the window draws them."""

    _editing = A._editing
    _on_press = A._on_press
    _on_drag = A._on_drag
    _on_release = A._on_release
    _on_double = A._on_double
    _on_motion = A._on_motion
    _cancel_drag = A._cancel_drag
    _grip_of = A._grip_of
    _page_grip = A._page_grip
    _turn_of = A._turn_of
    _frame_of = A._frame_of
    _shown_frame = A._shown_frame
    _choose = A._choose
    _draw_chosen = A._draw_chosen
    _draw_frame = A._draw_frame
    _edit_chosen = A._edit_chosen
    _region_at = A._region_at
    _overlay_items = LiveViewMixin._overlay_items
    _noted_regions = LiveViewMixin._noted_regions
    _page_drawn = A._page_drawn
    _draw_order_badges = A._draw_order_badges

    def __init__(self, root, settings):
        self._drag_start = self._drag_rect = self._grip = self._grip_start = self._grip_box = None
        self._turn = self._frame_cache = self._ordering = self._chosen_region = self._editor = None
        self._also_chosen: list = []
        self._banding, self._pressed, self.busy = False, None, False
        self.moved: list = []
        self.added: list = []
        self.edited: list = []
        self.patch_at_press: list = []
        super().__init__(root, settings)
        self.order_numbers_var = tk.BooleanVar(self, value=True)
        self.canvas.focus_set = lambda: None  # (the stand-in's page takes no focus)
        self.canvas.on_redraw = self._page_drawn
        self.role_var.set("translator")
        self._redisplay()

    # what the Translator's changes would do: noted, nothing stored
    def _move_region(self, region, box):
        self.moved.append((region, box))

    def _add_region(self, box, style=None):
        self.added.append(box)

    def _open_editor(self, region, result=None, at=None):
        self.edited.append(region)
        self._editor = SimpleNamespace(winfo_exists=lambda: True)  # (open: it holds the window's input)

    # the test's hands, in canvas pixels, as the window's bindings take them (`Zoom<canvas>` first, then the page's)
    def _event(self, cx, cy, state=0):
        self.pointer = (1000 + cx, 100 + cy)
        return SimpleNamespace(x=cx, y=cy, state=state)

    def move(self, cx, cy, state=0):
        """The pointer moved to (cx, cy): <Motion> on the panel's tag, then the page's <Motion> or <B1-Motion>."""
        event = self._event(cx, cy, state)
        self._bubbles_motion(event)
        if state & B1:
            self._on_drag(event)
        else:
            self._on_motion(event)

    def press(self, cx, cy):
        event = self._event(cx, cy)
        self._hold_press(event)  # the panel's tag: <ButtonPress-1>
        self.patch_at_press.append(self.canvas.patch)  # (what the page showed as the Translator's press came)
        self._on_press(event)  # the page's own

    def release(self, cx, cy):
        event = self._event(cx, cy, B1)
        if self._hold_release(event) != "break":
            self._on_release(event)

    def double(self, cx, cy):
        event = self._event(cx, cy)
        self._hold_press(event)
        self._on_double(event)  # the page's <Double-Button-1> in place of its <ButtonPress-1>

    def at(self, x, y):
        """The canvas point of the page point (x, y)."""
        return self.canvas.from_image_coords(x, y)

    def pending(self):
        return [getattr(f, "__name__", "") for _ms, f, _job in self.later
                if getattr(f, "__name__", "") in ("_zoom_due", "_reveal_due", "_hold_due")]


@pytest.fixture
def desk(hidden_root, monkeypatch, tmp_path):
    monkeypatch.setattr(zoom, "reveal", lambda popup: None)
    monkeypatch.setattr(zoom.layout, "work_area", lambda widget, x=None, y=None: WORK)
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))

    def no_file(*_a, **_k):
        raise AssertionError("nothing of the page is written anywhere")

    monkeypatch.setattr(Image.Image, "save", no_file)

    def made(reveal="panel", shows="original"):
        settings = Settings(state_dir=tmp_path / "state", config_path=tmp_path / "taslation.toml",
                            hover_shows=shows, hover_reveal=reveal)
        return Desk(hidden_root, settings)

    return made


def _popup_box(w):
    """Where the panel was put on the screen (left, top, right, bottom)."""
    popup = w._zoom_popup
    place = popup.geometry().split("+")
    x, y = int(place[1]), int(place[2])
    return x, y, x + popup.winfo_reqwidth(), y + popup.winfo_reqheight()


def _overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# ------------------------------------------------------------------ after the rest, and a press
def test_the_panel_shows_the_original_after_the_rest_and_a_press_takes_it_away_and_still_selects(desk):
    w = desk("panel")
    small, wide = w.last_result.regions[:2]
    assert w.shown_at(150, 200) == SET  # the translated page with its frames, as ever
    assert w.canvas.find_withtag("overlay")
    w.move(*w.at(150, 200))
    assert w.pending() == ["_zoom_due"] and w.delays("_zoom_due") == [ZOOM_DELAY_MS]  # (hard to read where it is)
    w.due("_zoom_due")
    labels = _labels(w._zoom_popup)
    picture = next(lbl for lbl in labels if str(lbl.cget("image")))
    assert (picture.image.width(), picture.image.height()) == (150, 300)  # the original, from memory, enlarged
    assert "A small thought." in [str(lbl.cget("text")) for lbl in labels]
    assert w.shown_at(150, 200) == SET and w.canvas.patch is None  # the page does not change
    w.press(*w.at(150, 200))  # a press: the panel goes at once, and the press selects as ever
    assert w._zoom_popup is None and w.pending() == [] and w._chosen_region is small
    assert w.delays("_hold_due") == []  # (a press held is the start of a drag here: no hold)
    w.release(*w.at(150, 200))
    assert w._chosen_region is small and w.moved == [] and w._zoom_popup is None
    w.move(*w.at(155, 205))  # resting again, on the selected bubble (inside its frame): the original again
    assert w.pending() == ["_zoom_due"]
    w.due("_zoom_due")
    assert w._zoom_popup is not None and w._chosen_region is small
    w.move(*w.at(550, 150))  # another bubble: the one before goes, this one after the longer rest
    assert w._zoom_popup is None and w.delays("_zoom_due") == [ZOOM_REST_MS]
    w.due("_zoom_due")
    assert w._zoom_popup is not None
    w._zoom_escape()  # Esc takes the panel only while it shows, as in the Reader role
    assert w._zoom_popup is None and w._chosen_region is small
    w.move(*w.at(750, 550))  # the bare page: nothing
    assert w.pending() == []
    assert wide.bbox == (400, 100, 700, 200)


def test_the_bubble_itself_shows_its_original_lettering_under_the_frames_and_goes_back_on_a_press(desk):
    w = desk("in_place")
    result = w.last_result
    small = result.regions[0]
    image, regions = result.image, [(r.bbox, r.translated_text, r.status) for r in result.regions]
    w.press(*w.at(550, 150))  # the wide bubble selected: its frame and handles over the page
    w.release(*w.at(550, 150))
    w.move(*w.at(150, 200))
    assert w.pending() == ["_reveal_due"] and w.delays("_reveal_due") == [ZOOM_DELAY_MS]
    w.due("_reveal_due")
    assert w._zoom_popup is None and w.canvas.patch is not None
    assert w.shown_at(125, 130) == INK and w.shown_at(150, 200) == INK  # the Japanese where it is
    assert w.shown_at(450, 150) == SET  # the other bubble stays translated
    order = w.canvas.find_all()  # (bottom to top)
    patch = w.canvas.find_withtag("patch")
    assert len(patch) == 1 and order.index(patch[0]) == order.index(w.canvas.find_withtag("picture")[0]) + 1
    above = [*w.canvas.find_withtag("overlay"), *w.canvas.find_withtag("chosen"), *w.canvas.find_withtag(BADGE_TAG)]
    assert w.canvas.find_withtag("chosen") and w.canvas.find_withtag(BADGE_TAG)
    assert all(order.index(item) > order.index(patch[0]) for item in above)  # frames, numbers, selection over it
    w.press(*w.at(150, 200))  # a press: the picture back before the press selects
    assert w.patch_at_press[-1] is None and w.canvas.patch is None and not w.canvas.find_withtag("patch")
    assert w._chosen_region is small and w.shown_at(150, 200) == SET
    w.release(*w.at(150, 200))
    w.move(*w.at(152, 202))
    w.due("_reveal_due")
    assert w.canvas.patch is not None
    w._bubbles_left()  # the pointer off the page
    assert w.canvas.patch is None and not w.canvas.find_withtag("patch")
    # nothing of the page, its regions or its frames changed: not an edit
    assert result.image is image and [(r.bbox, r.translated_text, r.status) for r in result.regions] == regions
    assert w.moved == w.added == w.edited == [] and w.last_result is result
    assert w.shown_at(150, 200) == SET


# ------------------------------------------------------------------ never while the Translator's pointer is at work
def test_nothing_shows_while_a_button_is_down_during_a_drag_a_move_or_a_rectangle_drawn(desk):
    for reveal in ("panel", "in_place"):
        w = desk(reveal)
        due = "_zoom_due" if reveal == "panel" else "_reveal_due"
        w.press(*w.at(40, 40))  # empty space: a drag there draws a new region ...
        w.move(*w.at(120, 150), state=B1)  # ... over a bubble: nothing due
        w.move(*w.at(150, 200), state=B1)
        assert w.pending() == [] and w._drag_rect is not None, reveal
        w.release(*w.at(150, 200))
        assert w.added == [(40, 40, 150, 200)], reveal
        w.move(*w.at(152, 202))  # the button let go: the pointer is free again
        assert w.pending() == [due], reveal
        w.press(*w.at(550, 150))  # the wide bubble selected and moved over the small one
        w.move(*w.at(450, 160), state=B1)
        w.move(*w.at(150, 200), state=B1)
        assert w.pending() == [] and w._grip_box is not None, reveal
        w.release(*w.at(150, 200))
        assert len(w.moved) == 1 and w.moved[0][0] is w.last_result.regions[1], reveal
        w.press(*w.at(550, 150))  # a drag Esc called off, the button still held: nothing either
        w.move(*w.at(450, 160), state=B1)
        assert w._cancel_drag() and w._drag_start is None
        w.move(*w.at(150, 200), state=B1)
        assert w.pending() == [] and w._zoom_popup is None and w.canvas.patch is None, reveal
        w.release(*w.at(150, 200))
        assert len(w.moved) == 1, reveal  # (the drag called off moved nothing)
        w.move(*w.at(151, 201))
        assert w.pending() == [due], reveal
        w.due(due)
        assert (w._zoom_popup is not None) if reveal == "panel" else (w.canvas.patch is not None), reveal
        w.move(*w.at(152, 202), state=B1)  # a button held while it shows (a press elsewhere came first): it goes
        assert w._zoom_popup is None and w.canvas.patch is None, reveal


def test_nothing_shows_on_a_handle_of_the_selected_region_and_it_goes_when_the_pointer_reaches_one(desk):
    for reveal in ("panel", "in_place"):
        w = desk(reveal)
        due = "_zoom_due" if reveal == "panel" else "_reveal_due"
        small = w.last_result.regions[0]
        w.press(*w.at(150, 200))
        w.release(*w.at(150, 200))
        assert w._chosen_region is small
        x0, y0, x1, y1 = area.box_to_canvas(small.bbox, w.canvas.scale, w.canvas.offset)
        corners = [area.to_canvas(x, y, w.canvas.scale, w.canvas.offset) for x, y in w._frame_of(small)]
        knob = area.rotate_handle(corners, room=w.canvas.room())[1]
        for name, point in (("se", (x1, y1)), ("e", (x1, (y0 + y1) / 2)), ("rotate", knob)):
            w.move(*point)
            assert w._grip_of(*point) == name and w.pending() == [], (reveal, name)  # resize or turn: nothing
        w.move((x0 + x1) / 2, (y0 + y1) / 2)  # inside its frame (a press moves it): free
        assert w.pending() == [due], reveal
        w.due(due)
        assert (w._zoom_popup is not None) if reveal == "panel" else (w.canvas.patch is not None), reveal
        w.move(x1 - 1, y1 - 1)  # onto its corner handle, still on the bubble: it goes
        assert w._zoom_popup is None and w.canvas.patch is None and w.pending() == [], reveal
        assert str(w.canvas.cget("cursor")) == area.CURSORS["se"]  # (the Translator's cursor, as ever)


def test_nothing_shows_while_the_region_editor_or_a_modal_dialog_is_open_and_what_shows_goes_when_one_opens(desk):
    for reveal in ("panel", "in_place"):
        w = desk(reveal)
        due = "_zoom_due" if reveal == "panel" else "_reveal_due"
        watch = "_zoom_watch" if reveal == "panel" else "_reveal_watch"
        w.double(*w.at(150, 200))  # a double click opens the editor, as ever
        assert w.edited == [w.last_result.regions[0]] and w._editor is not None, reveal
        w.move(*w.at(550, 150))
        assert w.pending() == [], reveal
        w._editor = None  # closed
        w.move(*w.at(551, 151))
        assert w.pending() == [due], reveal
        w.due(due)
        w._editor = SimpleNamespace(winfo_exists=lambda: True)  # an editor opens (a key, the review list)
        w.due(watch)
        assert w._zoom_popup is None and w.canvas.patch is None, reveal
        w._editor = None
        w.grab_current = lambda w=w: w  # a modal dialog holding the window's input
        w.move(*w.at(150, 200))
        assert w.pending() == [], reveal
        w.grab_current = lambda: None
        w.move(*w.at(151, 201))
        assert w.pending() == [due], reveal
        w.grab_current = lambda w=w: w  # (one opening while the original is due: not shown)
        w.due(due)
        assert w._zoom_popup is None and w.canvas.patch is None, reveal


# ------------------------------------------------------------------ the choices, as in the Reader role
def test_bubble_zoom_off_shows_nothing_and_what_the_page_shows_stays_the_translator_s(desk):
    for reveal in ("panel", "in_place"):
        w = desk(reveal)
        w.settings.bubble_zoom = False
        w.move(*w.at(150, 200))
        assert w.pending() == [], reveal
        w.show_japanese()  # the key of "show_japanese" pins the panel whatever bubble_zoom says, as ever
        assert w._zoom_pinned and w._zoom_for[1] is w.last_result.regions[0], reveal
        w.press(*w.at(550, 150))  # a press: the pinned panel goes, and the press selects
        assert w._zoom_popup is None and w._chosen_region is w.last_result.regions[1], reveal
        w.release(*w.at(550, 150))
    w = desk("panel", shows="translation")  # the original on the page is the Reader's: the Translator's page stays
    assert w.shown_at(150, 200) == SET
    w.move(*w.at(150, 200))
    w.due("_zoom_due")
    assert any(str(lbl.cget("image")) for lbl in _labels(w._zoom_popup))  # the original, not the translation alone
    w.move(*w.at(550, 150))
    assert w.delays("_zoom_due") == [ZOOM_REST_MS]  # (the delays of the translation on the page)
    assert str(w._original_entry[0].entrycget(0, "state")) == "normal"  # Show original as ever for the Translator


def test_with_show_original_the_bubble_itself_shows_nothing_and_the_panel_still_opens(desk):
    w = desk("in_place")
    w.original_var.set(True)
    w._redisplay()
    assert w.shown_at(150, 200) == INK  # the whole page as the viewer has it, frames over it
    w.move(*w.at(150, 200))
    assert w.pending() == []
    w.set_hover_reveal("panel", save=False)
    w.move(*w.at(151, 201))
    assert w.pending() == ["_zoom_due"]


def test_neither_a_press_held_still_nor_a_right_click_pins_anything_in_the_translator_role(desk):
    w = desk("panel")
    w.move(*w.at(150, 200))
    w.due("_zoom_due")
    w.press(*w.at(150, 200))  # held still: the start of a drag, no hold
    assert w.delays("_hold_due") == [] and w._zoom_popup is None
    w.release(*w.at(150, 200))
    assert w._chosen_region is w.last_result.regions[0]
    w.move(*w.at(151, 201))
    w.due("_zoom_due")
    w._hold_right(w._event(*w.at(550, 150)))  # a right click: the panel goes, nothing pinned
    assert w._zoom_popup is None and not getattr(w, "_zoom_pinned", False)
    assert HOLD_MS > 0


def test_the_panel_keeps_clear_of_the_selected_region_s_handles(desk):
    w = desk("panel")
    small, wide = w.last_result.regions[:2]
    w.move(*w.at(150, 200))
    w.due("_zoom_due")
    bubble = w._zoom_screen_box(small)
    alone = _popup_box(w)
    assert alone[0] == bubble[2] + ZOOM_GAP and w._zoom_clear == ()  # nothing selected: to its right, as ever
    w._zoom_hide()
    w.press(*w.at(550, 150))  # the wide bubble, to the right of the small one, selected
    w.release(*w.at(550, 150))
    w.move(*w.at(151, 201))
    w.due("_zoom_due")
    (handles,) = w._zoom_clear
    frame = w._zoom_screen_box(wide)
    assert handles[0] < frame[0] and handles[1] < frame[1] - area.ROTATE_GAP and handles[2] > frame[2]
    placed = _popup_box(w)
    assert not _overlaps(placed, handles) and not _overlaps(placed, bubble)  # its left side instead
    assert placed[2] == bubble[0] - ZOOM_GAP
    w._zoom_hide()
    w.press(*w.at(150, 200))  # the small bubble itself selected: beside it, clear of its own handles
    w.release(*w.at(150, 200))
    w.move(*w.at(151, 201))
    w.due("_zoom_due")
    (handles,) = w._zoom_clear
    assert not _overlaps(_popup_box(w), handles)


# ------------------------------------------------------------------ the keys, and the pages that are not the result
def test_the_bubble_keys_work_in_the_translator_role_and_a_press_closes_their_panel(desk):
    w = desk("in_place")
    regions = w.last_result.regions
    regions[0].source_text = "テスト"  # (made up; read in this session)
    w.move(*w.at(150, 200))
    w.show_japanese()
    assert w._zoom_pinned and w._zoom_for[1] is regions[0] and w.canvas.patch is None
    w.copy_translation()
    assert w.clipboard[-1] == ("append", "A small thought.")
    w.next_bubble()
    assert w._zoom_for[1] is regions[1]
    w.move(*w.at(750, 550))  # the pointer leaves for the panel: it stays
    assert w._zoom_popup is not None
    w.press(*w.at(750, 550))  # a click on the page: the panel goes and the press does the Translator's thing
    assert w._zoom_popup is None and w._chosen_region is None
    w.release(*w.at(750, 550))
    assert w.added == []  # (a click, no drag: nothing drawn)


def test_a_page_filling_in_shows_nothing_under_the_pointer_as_in_the_reader_role(desk):
    for reveal in ("panel", "in_place"):
        for role in ("translator", "reader"):
            w = desk(reveal)
            w.role_var.set(role)
            result = w.last_result
            w._fill = Filling(frame=result.original, base=result.original, boxes=[r.bbox for r in result.regions])
            w._redisplay()
            w.move(*w.at(150, 200))
            assert w.pending() == [], (reveal, role)
            w._fill = None
            w._redisplay()
            w.move(*w.at(152, 202))
            assert w.pending() == ["_zoom_due" if reveal == "panel" else "_reveal_due"], (reveal, role)


def test_the_full_screen_keeps_the_pointer_of_the_role_chosen(desk):
    for reading in (False, True):  # in the window and on the full screen alike
        w = desk("panel")
        w.reading = reading
        w.role_var.set("reader")
        w._redisplay()
        assert not w.canvas.find_withtag("overlay"), reading  # (no frames: the Reader's page)
        w.move(*w.at(150, 200), state=B1)  # the reader's pointer: a button held changes nothing, as ever
        assert w.pending() == ["_zoom_due"], reading
        w._hold_press(w._event(*w.at(150, 200)))  # a press held still pins the panel there
        assert w.delays("_hold_due") == [HOLD_MS], reading
        w.due("_hold_due")
        assert w._zoom_pinned, reading
        w._zoom_hide()
        w.role_var.set("translator")  # the Translator's: a held press is the start of a drag, never a pin
        w._redisplay()
        assert w.canvas.find_withtag("overlay"), reading  # the regions' frames and marks, as in the window
        w._hold_press(w._event(*w.at(550, 150)))
        assert w.delays("_hold_due") == [], reading
        w.move(*w.at(150, 200))  # its hover reveal while the pointer is free
        assert w.pending() == ["_zoom_due"], reading
