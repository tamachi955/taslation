"""Editing on the overlay (see-through mode with TASlation's own window hidden, `ui.see_edit`): the marks laid on the page
(`seethrough.Marks`, `edit_grip`, `edit_drag`, `edit_compose`), the see-through window taking the mouse over the
regions' boxes only and what a press there does (`capture.seethrough.SeeThrough`'s Edit, with a fake user32), the Tk
side acting on it (`see_edit.act`), the editor beside the region (`editor_place`, Show original), the left pane's
switch and the Menu's entries while it is on. Synthetic pages and fake windows only; nothing is sent to another
program and the pointer is never moved."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import seethrough as st
from taslation.capture import seethrough as window
from taslation.ui import see_edit
from taslation.ui import seethrough as ui

A, B, C = (100, 100, 200, 160), (300, 100, 380, 160), (140, 120, 170, 150)  # C lies inside A


# ------------------------------------------------------------------ the marks (pure)
def test_a_press_takes_the_smallest_box_it_is_in_and_a_corner_within_reach_resizes():
    marks = st.Marks(key=1, boxes=(A, B, C))
    assert st.edit_grip(marks, (110, 140), 7) == (0, "move")
    assert st.edit_grip(marks, (150, 130), 7) == (2, "move")  # (inside both: the smaller)
    assert st.edit_grip(marks, (203, 157), 7) == (0, "se")  # (just outside a corner, within reach)
    assert st.edit_grip(marks, (166, 123), 7) == (2, "ne")  # (a corner of the smaller one, inside the larger)
    assert st.edit_grip(marks, (250, 130), 7) is None  # (between the boxes: the viewer's)
    assert st.edit_grip(marks, (150, 130), 7, frozenset({2})) == (0, "move")  # (one covered takes nothing)
    plate = np.zeros((10, 20, 4), np.uint8)
    marks = st.Marks(key=1, boxes=(A, B), plates=(None, (plate, (300, 85))))
    assert st.edit_grip(marks, (305, 90), 3) == (1, st.PLATE)  # (its number plate: a click types its place)
    assert st.edit_grip(marks, (302, 94), 7) == (1, "nw")  # (a corner within reach first)
    assert st.edit_grip(marks, (325, 90), 3) is None  # (the empty ground: a drag there draws a region)
    assert st.edit_drag(marks, 1, st.PLATE, (305, 90), (315, 95), (900, 800)) == {1: (310, 105, 390, 165)}


def test_a_drag_moves_the_chosen_together_within_the_frame_and_a_corner_resizes_to_the_least():
    marks = st.Marks(key=1, boxes=(A, B, (10, 200, 50, 240)), chosen=(0, 1))
    assert st.edit_drag(marks, 0, "move", (150, 130), (160, 135), (900, 800)) == {
        0: (110, 105, 210, 165), 1: (310, 105, 390, 165)}
    assert st.edit_drag(marks, 2, "move", (20, 210), (30, 210), (900, 800)) == {2: (20, 200, 60, 240)}  # (alone)
    far = st.edit_drag(marks, 1, "move", (0, 0), (2000, 0), (900, 800))
    assert far == {0: (620, 100, 720, 160), 1: (820, 100, 900, 160)}  # (stopped at the frame's edge, together)
    assert st.edit_drag(marks, 0, "se", (200, 160), (240, 190), (900, 800)) == {0: (100, 100, 240, 190)}
    assert st.edit_drag(marks, 0, "nw", (100, 100), (400, 400), (900, 800)) == {
        0: (200 - st.MIN_BOX, 160 - st.MIN_BOX, 200, 160)}  # (never past the opposite side)
    assert st.drawn_box((50, 60), (10, 900), (400, 300)) == (10, 60, 50, 300)


def test_the_whole_page_takes_the_mouse_every_box_is_outlined_and_the_one_under_the_pointer_more_strongly():
    out = np.zeros((300, 500, 4), np.uint8)
    out[110:120, 110:120] = (40, 40, 40, 255)  # (a patch's lettering, kept as it is)
    colours = ((132, 220, 61), (71, 179, 255))  # (BGR: translated, not translated)
    marks = st.Marks(key=1, boxes=(A, B), colours=colours)
    st.edit_compose(out, marks, None, None, 96)
    alpha = out[..., 3]
    assert alpha[130, 150] == st.EDIT_ALPHA and alpha[115, 115] == 255
    assert (alpha[alpha != 255] == st.EDIT_ALPHA).all()  # (beside the boxes too: every press the window's)
    assert (out[130, 150, :3] == 0).all() and (out[50, 50, :3] == 0).all()  # (next to nothing shows over the page)
    line = st.scaled(st.LINE_PX, 96)
    assert tuple(out[130, 100]) == (*colours[0], 255) and tuple(out[130, 100 + line]) != (*colours[0], 255)
    assert tuple(out[130, 300]) == (*colours[1], 255)  # (each in its colour, all the time)
    out = np.zeros((300, 500, 4), np.uint8)
    st.edit_compose(out, marks, 0, None, 96)
    hover = st.scaled(st.HOVER_LINE_PX, 96)
    assert hover > line and tuple(out[130, 100 + hover - 1]) == (*st.OUTLINE, 255)
    assert tuple(out[130, 100 + hover]) != (*st.OUTLINE, 255)
    assert out[100, 100, 3] == 255 and tuple(out[103, 103]) != (0, 0, 0, 0)  # (a corner handle)
    assert tuple(out[130, 300]) == (*colours[1], 255)  # (the other: its own outline)
    out = np.zeros((300, 500, 4), np.uint8)
    st.edit_compose(out, st.Marks(key=1, boxes=(A, B), colours=colours, locked=True), 0, None, 96)
    assert out[103, 103, 3] == st.EDIT_ALPHA  # (an editor open: outlined, no handles - a press only clicks)
    out = np.zeros((300, 500, 4), np.uint8)
    st.edit_compose(out, marks, None, None, 96, left_out=frozenset({1}))
    assert tuple(out[130, 300]) == (0, 0, 0, st.EDIT_ALPHA)  # (covered, or not over its page now: no outline)
    out = np.zeros((300, 500, 4), np.uint8)
    st.edit_compose(out, marks, None, None, 96, holes=((280, 90, 400, 170),))
    assert out[130, 300, 3] == 0 and out[130, 150, 3] == st.EDIT_ALPHA  # (a window over the viewer: its own)
    out = np.zeros((300, 500, 4), np.uint8)
    st.edit_compose(out, marks, None, {0: (120, 110, 220, 170)}, 96, drawing=(10, 10, 60, 60))
    assert tuple(out[140, 120]) == (*st.OUTLINE, 255) and tuple(out[30, 10]) == (*st.ADDING, 255)
    out = np.zeros((300, 500, 4), np.uint8)
    st.edit_compose(out, st.GROUND, None, None, 96, drawing=(10, 10, 60, 60))  # (a page with no marks of its own)
    assert out[200, 400, 3] == st.EDIT_ALPHA and tuple(out[30, 10]) == (*st.ADDING, 255)


def test_a_number_plate_is_laid_over_the_page_in_its_colour():
    plate = np.zeros((6, 8, 4), np.uint8)
    plate[...] = (100, 50, 20, 200)  # (premultiplied)
    out = np.zeros((300, 500, 4), np.uint8)
    out[90:96, 96:104] = (0, 0, 255, 255)
    st.edit_compose(out, st.Marks(key=1, boxes=(A,), plates=((plate, (96, 90)),)), None, None, 96)
    assert tuple(out[92, 97]) == (100, 50, 20 + (255 * 55 + 127) // 255, 255)  # (over the lettering: blended)
    assert tuple(out[92, 103]) == (100, 50, 20 + (255 * 55 + 127) // 255, 255)


def test_a_number_plate_is_large_enough_to_click_and_sits_on_the_box_s_top_clear_of_its_corner():
    from taslation import panes as pn

    for dpi in (96, 144):
        least = pn.scaled(pn.BADGE_MIN_PX, dpi)
        assert min(pn.badge("1", see_edit.TRANSLATED, dpi).shape[:2]) >= least
    assert pn.badge("123", see_edit.TRANSLATED, 96).shape[1] > pn.badge("1", see_edit.TRANSLATED, 96).shape[1]
    plate = pn.badge("2", see_edit.TRANSLATED, 96)
    h, w = plate.shape[:2]
    x, y = see_edit._place_plate(B, plate, SIZE)
    assert (x, y) == (B[0] + st.scaled(st.GRIP_PX, 96) + 1, B[1] - h)  # (above its top edge, past the corner's grip)
    marks = st.Marks(key=1, boxes=(B,), plates=((plate, (x, y)),))
    assert st.edit_grip(marks, (x + 1, y + h - 1), st.GRIP_PX) == (0, st.PLATE)  # (all of it takes the click)
    assert st.edit_grip(marks, (B[0] + 2, B[1] + 2), st.GRIP_PX) == (0, "nw")
    assert see_edit._place_plate((100, 5, 200, 60), plate, SIZE)[1] == 5  # (no room above: inside its top)
    assert see_edit._place_plate((SIZE[0] - 10, 300, SIZE[0], 360), plate, SIZE)[0] == SIZE[0] - w  # (on the frame)


# ------------------------------------------------------------------ the see-through window's side
class FakeSet:
    def __init__(self, boxes, key=5, serial=7):
        self.serial, self.key = serial, key
        self.patches = [SimpleNamespace(box=b) for b in boxes]


def lparam(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


@pytest.fixture
def over(monkeypatch):
    styles = {9: window.EX_STYLE}
    calls = []
    monkeypatch.setattr(window, "IS_WINDOWS", True)
    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        GetWindowLongW=lambda hwnd, index: styles[hwnd],
        SetWindowLongW=lambda hwnd, index, value: styles.__setitem__(hwnd, value) or 1,
        PostMessageW=lambda hwnd, message, w, l: calls.append(("post", hwnd, message)) or 1,
        SetCapture=lambda hwnd: calls.append(("capture", hwnd)) or 0,
        ReleaseCapture=lambda: calls.append(("release",)) or 1,
        GetCapture=lambda: 9,
        GetSystemMetrics=lambda index: 0,
        GetAsyncKeyState=lambda key: 0x8000,
        ShowWindow=lambda hwnd, cmd: 1))
    see = window.SeeThrough()
    see.hwnd = 9
    see.styles, see.calls, see.drawn = styles, calls, []

    def draw(chosen, shown, origin, size, *rest):
        edit_key = rest[4] if len(rest) > 4 else None
        see.drawn.append((shown, rest[3] if len(rest) > 3 else None))
        see._shown = (chosen.serial if chosen is not None else -1, shown, origin, size, edit_key)

    monkeypatch.setattr(see, "_draw", draw)
    return see


ORIGIN, SIZE = (500, 300), (900, 800)


def look(see, chosen, shown):
    see._last_look = (chosen, shown, [0.0] * len(chosen.patches), 1, 0.0, ORIGIN, SIZE, True)
    see._show_look(*see._last_look)


def screen(x, y):
    return ORIGIN[0] + x, ORIGIN[1] + y


def test_the_window_takes_the_mouse_while_editing_and_wakes_for_its_messages(over):
    marks = st.Marks(key=5, boxes=(A, B), serial=1)
    chosen = FakeSet([A, B])
    assert over._edit_message(window.WM_NCHITTEST, 0, 0) is None  # (not taking it: the window's own answer)
    over.set_edit(marks)
    over._edit_take(True, [chosen])
    assert not over.styles[9] & window.WS_EX_TRANSPARENT and over._edit_takes
    assert over._edit_message(window.WM_NCHITTEST, 0, 0) == window.HTCLIENT
    assert over._edit_message(window.WM_MOUSEACTIVATE, 0, 0) == window.MA_NOACTIVATE  # (the viewer stays in front)
    over._poke()
    assert ("post", 9, window.WM_APP) in over.calls  # (its wait for the mouse woken too)
    over._edit_take(False, [chosen])
    assert over.styles[9] & window.WS_EX_TRANSPARENT and not over._edit_takes
    assert [n["on"] for n in over.notes if n["ev"] == "edit"] == [1, 0]


def test_editing_takes_the_whole_page_with_no_marks_and_the_wheel_and_the_other_buttons_reach_nothing(over):
    for message in (*window.SWALLOWED, *window.SIDE_BUTTONS):
        assert over._edit_message(message, 0, 0) is None  # (Reader mode: the window's own answer, click-through)
    over.set_ground(True)
    assert over._ground and over._changed == 1
    over.set_ground(True)
    assert over._changed == 1  # (the same again: nothing)
    over._edit_take(over._ground, [])  # (as a look takes it: no marks of the page, not translated yet)
    assert over._edit_takes and not over.styles[9] & window.WS_EX_TRANSPARENT
    for message in (window.WM_MOUSEWHEEL, window.WM_MOUSEHWHEEL, window.WM_MBUTTONDOWN, window.WM_MBUTTONUP,
                    window.WM_RBUTTONUP):
        assert over._edit_message(message, 0, 0) == 0  # (taken, and nothing done: no window gets it)
    for message in window.SIDE_BUTTONS:
        assert over._edit_message(message, 0, 0) == 1  # (no Back, no Forward made of it)
    chosen = FakeSet([A])
    look(over, chosen, (0,))
    shown, edit = over.drawn[-1]
    assert edit[0] is st.GROUND and shown == (0,)  # (the patches as they are, the page the window's)
    over._covers = [screen(280, 90) + screen(400, 170)]  # (a window over the viewer)
    look(over, chosen, (0,))
    assert over.drawn[-1][1][6] == ((280, 90, 400, 170),)  # (left at alpha 0: a press there is that window's)
    over.set_ground(False)
    over._edit_take(over._ground, [chosen])
    assert not over._edit_takes and over.styles[9] & window.WS_EX_TRANSPARENT


def test_a_drag_on_the_empty_ground_draws_a_region_and_a_click_there_is_kept_as_one(over):
    over.set_ground(True)
    over._edit_take(True, [])
    chosen = FakeSet([A])
    look(over, chosen, (0,))
    press(over, 400, 300)
    assert over._press["draw"] is True and ("capture", 9) in over.calls
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(460, 350))
    look(over, chosen, (0,))
    assert over.drawn[-1][1][4] == (400, 300, 460, 350)  # (the rectangle drawn as the pointer goes)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(460, 350))
    press(over, 400, 300)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(401, 300))  # (no drag: a click on the ground)
    press(over, 400, 300)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(420, 302))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(420, 302))  # (too small to be a region)
    press(over, 400, 300)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(460, 350))
    over._edit_message(window.WM_RBUTTONDOWN, 0, lparam(460, 350))  # (a right click: given up)
    drawn, click, small = over.take_edits()
    assert drawn["kind"] == "draw" and drawn["box"] == (400, 300, 460, 350) and drawn["marks"] == 0
    assert drawn["key"] == 5 and click["kind"] == "ground" and small["kind"] == "draw" and small["box"] is None
    assert over._press is None and over.take_edits() == []
    marks = st.Marks(key=5, boxes=(A, B), serial=3)  # (and between the boxes of a page with its marks)
    over.set_edit(marks)
    over._edit_take(True, [chosen])
    look(over, chosen, (0,))
    press(over, 250, 130)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(290, 170))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(290, 170))
    (event,) = over.take_edits()
    assert event["kind"] == "draw" and event["box"] == (250, 130, 290, 170) and event["marks"] == 3
    assert over._ghost[1] == ((250, 130, 290, 170),)  # (outlined until the Tk thread has it)


def test_a_press_of_the_windows_own_is_no_press_on_the_viewer(over, monkeypatch):
    pointer = [screen(150, 130)]
    monkeypatch.setattr(window, "cursor_pos", lambda: pointer[0])
    assert not over.pressing()  # (not editing: the viewer's)
    over.set_ground(True)
    over._edit_take(True, [])
    look(over, FakeSet([A]), (0,))
    assert over.pressing()  # (the button down over the page: the window's, frames go on being taken)
    pointer[0] = screen(-20, 130)
    assert not over.pressing()  # (beside the page: the viewer's frame, a pane)
    over._covers = [screen(100, 100) + screen(200, 200)]
    pointer[0] = screen(150, 130)
    assert not over.pressing()  # (a window over the viewer)
    press(over, 400, 300)
    assert over.pressing()  # (one held: the window's wherever the pointer is)


def test_a_look_in_edit_keeps_the_patch_under_the_pointer_and_outlines_it(over):
    marks = st.Marks(key=5, boxes=(A, B), serial=1)
    chosen = FakeSet([A, B])
    over.set_edit(marks)
    over._edit_take(True, [chosen])
    over._pointer = screen(150, 130)
    look(over, chosen, (0, 1))
    shown, edit = over.drawn[-1]
    assert shown == (0, 1) and edit[1] == 0  # (none given way: the one under the pointer outlined)
    assert over.hovered() == (5, A)  # (the right pane's block shows its original and translation)
    assert over._marks_for(FakeSet([A, B], key=6)) is None  # (another page's set: no marks on it)


def test_a_patch_in_the_editor_stays_shown_and_its_original_shows_while_show_original_is_held(over):
    chosen = FakeSet([A, B])
    marks = st.Marks(key=5, boxes=(A, B), held=1, locked=True, serial=1)
    over.set_edit(marks)
    over._edit_take(True, [chosen])
    look(over, chosen, (0,))  # (the frame does not show B's patch: the editor's region keeps it all the same)
    assert over.drawn[-1][0] == (0, 1)
    over.set_edit(st.Marks(key=5, boxes=(A, B), held=1, bare=1, locked=True, serial=2))
    look(over, chosen, (0, 1))
    assert over.drawn[-1][0] == (0,)  # (Show original held: B's patch left out)
    over.set_edit(st.Marks(key=5, boxes=(A, B), serial=3))
    look(over, chosen, (0,))
    assert over.drawn[-1][0] == (0,) and over._left_out == frozenset({1})  # (its page's pixels not there: no hold)


def test_a_page_with_no_patch_has_its_marks_while_no_set_is_chosen(over):
    marks = st.Marks(key=6, boxes=(A,), serial=1)
    over.set_edit(marks)
    over._edit_take(True, [FakeSet([A, B], key=5)])
    assert over._patchless == 6 and over._marks_for(None) is marks
    over._edit_take(True, [FakeSet([A], key=6)])
    assert over._patchless is None and over._marks_for(None) is None


def test_a_box_with_no_patch_takes_nothing_while_the_viewer_has_other_pixels_round_it(over):
    page = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
    page[90:170, 290:390] = (30, 120, 200)  # (RGB: what lies round B in the frame read)
    original = Image.fromarray(page)
    app = SimpleNamespace()
    probe = see_edit._probe(app, original, B, SIZE, 96)
    assert probe.near == st.grow(B, st.MARGIN, SIZE) and see_edit._probe(app, original, B, SIZE, 96) is probe
    view = np.zeros((SIZE[1], SIZE[0], 4), np.uint8)
    view[..., :3] = page[:, :, ::-1]  # (the viewer's frame: BGRA)
    assert st.changed_share(probe, view) == 0.0
    marks = st.Marks(key=5, boxes=(A, B), probes=(None, probe), serial=1)
    chosen = FakeSet([A])  # (B has no patch: nothing lettered in it)
    over.set_edit(marks)
    over._edit_take(True, [chosen])
    assert over._failed_probes(chosen, view) == frozenset()
    barred = view.copy()
    barred[80:140] = (255, 255, 255, 255)  # (the viewer's bar laid over B)
    assert over._failed_probes(chosen, barred) == frozenset({B})
    over._probes_failed = over._failed_probes(chosen, barred)
    look(over, chosen, (0,))
    assert over._left_out == frozenset({1})  # (B takes nothing: a click there is the viewer's)
    over._probes_failed = over._failed_probes(chosen, view)
    over.set_edit(st.Marks(key=5, boxes=(A, B), probes=(None, probe), serial=2))
    look(over, chosen, (0,))
    assert over._left_out == frozenset()


def press(over, x, y, shift=False):
    over._edit_message(window.WM_LBUTTONDOWN, window.MK_SHIFT if shift else 0, lparam(x, y))


def test_a_click_a_drag_and_a_corner_drag_are_handed_to_the_tk_thread_with_their_marks(over):
    chosen = FakeSet([A, B])
    marks = st.Marks(key=5, boxes=(A, B), serial=4)
    over.set_edit(marks)
    over._edit_take(True, [chosen])
    over._pointer = screen(150, 130)
    look(over, chosen, (0, 1))
    press(over, 150, 130)
    assert ("capture", 9) in over.calls and over.pressing()  # (the window's until let go)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(151, 131))
    press(over, 150, 130, shift=True)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(170, 140))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(170, 140))
    press(over, 200, 160)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(220, 180))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(220, 180))
    events = over.take_edits()
    assert [e["kind"] for e in events] == ["click", "move", "resize"]
    assert events[0]["index"] == 0 and events[0]["shift"] is False
    assert events[1]["boxes"] == {0: (120, 110, 220, 170)} and events[2]["boxes"] == {0: (100, 100, 220, 180)}
    assert all(e["marks"] == 4 and e["key"] == 5 for e in events) and [e["press"] for e in events] == [1, 2, 3]
    assert over._ghost == (3, ((100, 100, 220, 180),))  # (outlined at its new place until the Tk thread has it)
    assert over.take_edits() == []
    press(over, 150, 130, shift=True)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(150, 130))
    assert over.take_edits()[0]["shift"] is True
    press(over, 250, 130)  # (between the boxes: the empty ground, a rectangle begun)
    assert over._press["draw"] is True and "index" not in over._press
    plate = np.zeros((18, 18, 4), np.uint8)
    over.set_edit(st.Marks(key=5, boxes=(A, B), plates=(None, (plate, (310, 82))), serial=5))
    look(over, chosen, (0, 1))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(250, 130))
    over.take_edits()
    press(over, 315, 90)  # (B's number plate)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(316, 90))
    press(over, 315, 90)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(325, 100))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(325, 100))
    typed, moved = over.take_edits()
    assert typed["kind"] == "plate" and typed["index"] == 1 and typed["shift"] is False
    assert moved["kind"] == "move" and moved["boxes"] == {1: (310, 110, 390, 170)}  # (a drag from it moves the box)


def test_a_right_click_or_the_capture_lost_gives_a_press_up_and_a_locked_press_only_clicks(over):
    chosen = FakeSet([A, B])
    over.set_edit(st.Marks(key=5, boxes=(A, B), serial=1))
    over._edit_take(True, [chosen])
    look(over, chosen, (0, 1))
    press(over, 150, 130)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(190, 150))
    over._edit_message(window.WM_RBUTTONDOWN, 0, lparam(190, 150))
    assert over._press is None and over.take_edits() == []
    press(over, 150, 130)
    over._edit_message(window.WM_CAPTURECHANGED, 0, 1234)
    assert over._press is None and over.take_edits() == []
    press(over, 150, 130)
    over._edit_message(window.WM_CAPTURECHANGED, 0, 9)  # (its own capture: kept)
    assert over._press is not None
    window._user32.GetAsyncKeyState = lambda key: 0  # (let go over another window: given up at the next look)
    over._edit_held()
    assert over._press is None
    window._user32.GetAsyncKeyState = lambda key: 0x8000
    over.set_edit(st.Marks(key=5, boxes=(A, B), held=0, locked=True, serial=2))
    look(over, chosen, (0, 1))
    press(over, 200, 160)  # (a corner, but an editor is open: a drag is no resize)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(240, 200))
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(240, 200))
    (event,) = over.take_edits()
    assert event["kind"] == "click" and event["index"] == 0
    press(over, 150, 130)
    over._edit_take(False, [chosen])  # (Reader mode: a press held given up)
    assert over._press is None


def test_a_rectangle_drawn_adds_a_region_and_a_press_without_a_drag_draws_none(over):
    chosen = FakeSet([A])
    over.set_edit(st.Marks(key=5, boxes=(A,), adding=True, serial=1))
    over._edit_take(True, [chosen])
    look(over, chosen, (0,))
    assert over.drawn[-1][1][0].adding and over._edit_takes  # (the whole page takes the mouse, in Reader mode too)
    press(over, 150, 130)  # (on a box: adding draws all the same)
    assert over._press["adding"] is True
    over._edit_message(window.WM_RBUTTONDOWN, 0, lparam(150, 130))
    assert over.take_edits()[0]["box"] is None  # (a right click gives the adding up)
    press(over, 400, 300)
    over._edit_message(window.WM_MOUSEMOVE, 0, lparam(460, 350))
    look(over, chosen, (0,))
    assert over.drawn[-1][1][4] == (400, 300, 460, 350)  # (the rectangle drawn as the pointer goes)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(460, 350))
    press(over, 400, 300)
    over._edit_message(window.WM_LBUTTONUP, 0, lparam(401, 300))
    first, second = over.take_edits()
    assert first["kind"] == "add" and first["box"] == (400, 300, 460, 350) and second["box"] is None


# ------------------------------------------------------------------ the Tk side
class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Region:
    """A page's region as `_page_regions` gives it: compared by its fields, so not hashable (as `TextRegion`)."""

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, box, status="translated", kind="speech", flags=None):
        self.bbox, self.status, self.kind, self.flags = box, status, kind, flags
        self.x0, self.y0 = box[0], box[1]

    def __eq__(self, other):
        return isinstance(other, Region) and self.bbox == other.bbox


class Over:
    def __init__(self):
        self.edits, self.marks, self.grounds = [], [], []

    def take_edits(self):
        out, self.edits = self.edits, []
        return out

    def set_edit(self, marks):
        self.marks.append(marks)

    def set_ground(self, on):
        self.grounds.append(on)

    def client_origin(self):
        return ORIGIN


class Editor:
    def __init__(self, region):
        self.region, self.raised = region, 0

    def winfo_exists(self):
        return True

    def lift(self):
        self.raised += 1

    def focus_force(self):
        pass


def edit_app(regions=None, host=None):
    """A window editing the page: a namespace, or *host* (a Tk widget: the place entry's parent) with its parts."""
    regions = regions if regions is not None else [Region(A), Region(B, status="unmatched"),
                                                    Region(C, kind="manual"), Region((10, 10, 40, 40), flags=["x"])]
    result = SimpleNamespace(original=Image.new("RGB", SIZE), regions=list(regions), image=None)
    calls, said = [], []
    app = host if host is not None else SimpleNamespace()
    for name, value in dict(_see_hidden=True, _see_through=Over(), role_var=Var("translator"), last_result=result,
                            busy=False, _ordering=None, _chosen_region=None, _also_chosen=[], _see_dpi=96,
                            calls=calls, said=said).items():
        setattr(app, name, value)
    app._editing = lambda: True
    app._result_on_show = lambda: True
    app._page_regions = lambda: list(result.regions)
    app.say = lambda text, **k: said.append(text)
    app._choose = lambda r: (calls.append(("choose", r)), setattr(app, "_chosen_region", r))
    app._toggle_chosen = lambda r: calls.append(("toggle", r))
    app._open_editor = lambda r, result=None, at=None: calls.append(("editor", r))
    app._move_region = lambda r, box: (calls.append(("move", r, box)), setattr(app, "busy", True))
    app._move_regions = lambda rs, dx, dy: (calls.append(("group", rs, dx, dy)), setattr(app, "busy", True))
    app._add_region = lambda box: (calls.append(("add", box)), setattr(app, "busy", True))
    app._redisplay = lambda: calls.append(("redisplay",))
    app._on_role_changed = lambda chosen=True: calls.append(("role", app.role_var.get()))
    return app


def test_the_marks_number_the_regions_in_their_colours_and_are_made_again_only_on_a_change():
    app = edit_app()
    marks = see_edit.marks_for(app)
    assert marks.key == id(app.last_result.original) and marks.boxes == (A, B, C, (10, 10, 40, 40))
    colours = []
    for bgra, (x, y) in marks.plates:
        h = bgra.shape[0]
        colours.append(tuple(int(v) for v in bgra[h // 2, 1, :3][::-1]))  # (premultiplied RGB at its left edge)
    for got, wanted in zip(colours, (see_edit.TRANSLATED, see_edit.NOT_TRANSLATED, see_edit.OWN, see_edit.FLAGGED)):
        assert all(abs(g - w * 235 // 255) <= 2 for g, w in zip(got, wanted)), (got, wanted)
    assert not marks.locked and marks.held is None and marks.chosen == ()
    assert see_edit.marks_for(app) is marks  # (nothing changed: the same marks, nothing redrawn)
    app._chosen_region = app.last_result.regions[1]
    again = see_edit.marks_for(app)
    assert again is not marks and again.chosen == (1,) and again.serial == marks.serial + 1
    app._editor = Editor(app.last_result.regions[0])
    app._see_bare = app.last_result.regions[0]
    held = see_edit.marks_for(app)
    assert held.held == 0 and held.bare == 0 and held.locked  # (an editor open: presses only click)
    app._editor = None
    assert see_edit.marks_for(app).bare is None  # (Show original only while the editor is open)
    app._editing = lambda: False  # (another page on show)
    assert see_edit.marks_for(app) is None
    app._editing = lambda: True
    app.role_var.set("reader")  # (Reader mode)
    assert see_edit.marks_for(app) is None


def test_a_change_being_stored_is_outlined_until_it_is_done():
    app = edit_app()
    app._see_pending = ((1, 2, 3, 4),)
    assert see_edit.marks_for(app).ghosts == () and app._see_pending == ()  # (no job: none begun)
    app.busy, app._see_pending = True, ((1, 2, 3, 4),)
    assert see_edit.marks_for(app).ghosts == ((1, 2, 3, 4),) and see_edit.marks_for(app).locked


def hand(app, **event):
    marks = see_edit.marks_for(app)
    app._see_through.edits.append({"press": 1, "marks": marks.serial, "key": marks.key, **event})
    see_edit.tick(app, app._see_through)


def test_a_click_opens_the_editor_shift_chooses_and_the_reading_order_numbers(monkeypatch):
    monkeypatch.setattr(see_edit.seethrough, "asked", lambda app: app.calls.append(("asked",)))
    app = edit_app()
    a, b = app.last_result.regions[:2]
    hand(app, kind="click", index=0, shift=False)
    assert app.calls == [("choose", a), ("asked",), ("editor", a)] and app._see_edit_seen == 1
    app.calls.clear()
    hand(app, kind="click", index=1, shift=True)
    assert app.calls == [("toggle", b)]
    app.calls.clear()
    app._ordering = [b]
    hand(app, kind="click", index=0, shift=False)
    hand(app, kind="click", index=0, shift=False)  # (numbered once)
    assert app._ordering == [b, a] and app.calls == [("redisplay",)]
    app._ordering, app.calls[:] = None, []
    app._editor = Editor(b)
    hand(app, kind="click", index=0, shift=False)  # (an editor open: it comes to the front, one region at a time)
    assert app._editor.raised == 1 and ("editor", a) not in app.calls
    app._editor, app.busy, app.calls[:] = None, True, []
    hand(app, kind="click", index=0, shift=False)
    assert app.calls == []  # (a change being stored: nothing)


def test_a_drag_stores_the_box_and_the_chosen_move_together_and_a_stale_press_does_nothing():
    app = edit_app()
    a, b = app.last_result.regions[:2]
    hand(app, kind="move", index=0, boxes={0: (120, 110, 220, 170)})
    assert app.calls == [("choose", a), ("move", a, (120, 110, 220, 170))]
    assert app._see_pending == ((120, 110, 220, 170),)
    app.busy, app.calls[:] = False, []
    hand(app, kind="resize", index=1, boxes={1: (300, 100, 400, 190)})
    assert app.calls == [("choose", b), ("move", b, (300, 100, 400, 190))]
    app.busy, app.calls[:] = False, []
    hand(app, kind="move", index=0, boxes={0: (110, 105, 210, 165), 1: (310, 105, 390, 165)})
    assert app.calls == [("group", [a, b], 10, 5)]
    app.busy, app.calls[:] = False, []
    marks = see_edit.marks_for(app)
    app.last_result.regions.remove(b)  # (the region gone from the page by now)
    app._see_through.edits.append({"kind": "click", "index": 1, "shift": False, "press": 2, "marks": marks.serial,
                                   "key": marks.key})
    app._see_through.edits.append({"kind": "click", "index": 0, "press": 3, "marks": marks.serial, "key": 12345})
    see_edit.tick(app, app._see_through)  # (and a press on another page's marks)
    assert app.calls == [] and app._see_edit_seen == 3


def test_a_text_area_is_added_only_when_asked_for_and_edit_off_keeps_the_adding():
    app = edit_app()
    hand(app, kind="add", box=(10, 10, 60, 60))
    assert app.calls == []  # (not asked for)
    see_edit.add_region(app)
    assert app._see_adding is True and app.said == [see_edit.ADDING] and see_edit.marks_for(app).adding
    hand(app, kind="add", box=None)
    assert app.said[-1] == see_edit.ADD_GIVEN_UP and app._see_adding is False and app.calls == []
    see_edit.add_region(app)
    hand(app, kind="add", box=(10, 10, 60, 60))
    assert app.calls == [("add", (10, 10, 60, 60))] and app._see_pending == ((10, 10, 60, 60),)
    app.busy = False
    see_edit.add_region(app)
    app.role_var.set("reader")  # (Reader mode: the adding kept, marks of no box - Add area works in Reader mode)
    see_edit.tick(app, app._see_through)
    marks = app._see_through.marks[-1]
    assert app._see_adding is True and marks.adding and marks.boxes == ()
    see_edit.toggle_adding(app)  # (Add area again)
    assert app._see_adding is False and app._see_through.marks[-1] is None


def test_one_press_s_fault_leaves_the_next_acted_on(monkeypatch):
    app = edit_app()
    a = app.last_result.regions[0]
    seen = []

    def act(app, event):
        seen.append(event["press"])
        if event["press"] == 1:
            raise RuntimeError("one press")

    monkeypatch.setattr(see_edit, "act", act)
    app._see_through.edits += [{"press": 1}, {"press": 2}]
    see_edit.tick(app, app._see_through)
    assert seen == [1, 2] and app._see_edit_seen == 2 and a is app.last_result.regions[0]


def test_the_whole_page_takes_the_mouse_while_editing_whatever_page_is_on_show():
    app = edit_app()
    over = app._see_through
    see_edit.tick(app, over)
    assert over.grounds[-1] is True and over.marks[-1] is not None
    app._editing = lambda: False  # (another page on show, not translated yet: no marks, the ground all the same)
    see_edit.tick(app, over)
    assert over.grounds[-1] is True and over.marks[-1] is None
    app.role_var.set("reader")  # (Reader mode: every click the viewer's)
    see_edit.tick(app, over)
    assert over.grounds[-1] is False and over.marks[-1] is None


def test_a_rectangle_drawn_on_the_empty_ground_adds_a_region_and_a_click_there_drops_a_choice():
    app = edit_app()
    a, b = app.last_result.regions[:2]
    hand(app, kind="draw", box=None)  # (too small to be a region)
    assert app.calls == [] and app.said == []
    hand(app, kind="draw", box=(400, 300, 460, 350))
    assert app.calls == [("add", (400, 300, 460, 350))] and app._see_pending == ((400, 300, 460, 350),)
    app.calls.clear()
    hand(app, kind="draw", box=(10, 10, 60, 60))  # (a change being stored: not now)
    assert app.calls == [] and app.said[-1] == see_edit.ADD_NOT_NOW
    app.busy = False
    app._result_on_show = lambda: False  # (the page on show not the last translated one)
    hand(app, kind="draw", box=(10, 10, 60, 60))
    assert app.calls == [] and app.said[-1] == see_edit.ADD_NOT_NOW
    app._result_on_show = lambda: True
    app._chosen_region, app._also_chosen = a, [b]
    hand(app, kind="ground")
    assert app.calls == [("choose", None), ("redisplay",)]
    app.calls.clear()
    app._chosen_region, app._also_chosen = a, []
    hand(app, kind="ground")  # (one chosen: it stays)
    assert app.calls == []
    app.role_var.set("reader")
    app._see_through.edits.append({"kind": "draw", "box": (10, 10, 60, 60), "press": 9, "marks": 0, "key": 0})
    see_edit.tick(app, app._see_through)  # (in Reader mode no rectangle is drawn on the ground)
    assert app.calls == []


def test_a_click_on_a_plate_types_its_place_enter_takes_it_and_esc_or_any_other_press_gives_it_up(hidden_root,
                                                                                                   monkeypatch):
    import tkinter as tk

    monkeypatch.setattr(tk.Toplevel, "deiconify", lambda self: None)  # (nothing shown on the screen)
    monkeypatch.setattr(tk.Misc, "focus_force", lambda self: None)  # (no window of the computer's loses the keys)
    asked, given = [], []
    monkeypatch.setattr(see_edit.seethrough, "asked", lambda app: asked.append(1))
    monkeypatch.setattr(see_edit.seethrough, "closing", lambda app, top: given.append(top) or True)
    app = edit_app(host=tk.Frame(hidden_root))
    placed = []
    app._place_regions = lambda chosen, place: placed.append((chosen, place))
    a, b = app.last_result.regions[:2]
    hand(app, kind="plate", index=1, shift=False)
    entry = app._see_place_entry
    assert entry.entry.get() == "2" and entry.total == 4 and app.calls[-1] == ("choose", b) and asked
    assert app.said[-1] == see_edit.PLACE_ASK and entry.top.wm_overrideredirect()
    entry.entry.delete(0, "end")
    entry.entry.insert(0, "9")  # (past the end: asked again)
    entry._take()
    assert app._see_place_entry is entry and entry.alive() and not placed and app.said[-1] == see_edit.PLACE_ASK
    entry.entry.delete(0, "end")
    entry.entry.insert(0, "1")
    entry._take()
    assert placed == [([b], 1)] and app._see_place_entry is None and not entry.alive()
    assert given == [entry.top]  # (the foreground given back to the viewer)
    hand(app, kind="plate", index=0, shift=False)
    entry = app._see_place_entry
    entry._give_up()  # (Esc)
    assert app._see_place_entry is None and not entry.alive() and len(given) == 2 and len(placed) == 1
    hand(app, kind="plate", index=0, shift=False)
    entry = app._see_place_entry
    hand(app, kind="ground")  # (a press anywhere else on the page)
    assert app._see_place_entry is None and not entry.alive() and len(given) == 2
    hand(app, kind="plate", index=0, shift=False)
    entry = app._see_place_entry
    entry._focus_out()  # (no keys had yet: kept)
    assert entry.alive()
    entry._focus_in()
    entry._focus_out()  # (a click on the viewer or another window)
    assert app._see_place_entry is None and not entry.alive() and len(given) == 2
    hand(app, kind="plate", index=0, shift=False)
    entry = app._see_place_entry
    entry.opened -= see_edit.PLACE_FOCUS_S + 0.1  # (the keys never came: the viewer kept them)
    see_edit.tick(app, app._see_through)
    assert app._see_place_entry is None and not entry.alive()
    app.calls.clear()
    hand(app, kind="plate", index=1, shift=True)  # (Shift: as a click on the box)
    assert app.calls == [("toggle", b)] and app._see_place_entry is None
    app._ordering = []
    hand(app, kind="plate", index=1, shift=False)  # (the order being clicked: numbered)
    assert app._ordering == [b] and app._see_place_entry is None
    app._ordering = None
    hand(app, kind="plate", index=1, shift=False)
    entry = app._see_place_entry
    see_edit.toggle(app)  # (Reader mode)
    assert app._see_place_entry is None and not entry.alive() and len(placed) == 1


def test_the_switch_is_the_translator_role_and_gives_up_what_edit_held():
    app = edit_app()
    app._see_adding, app._see_bare = True, object()
    see_edit.toggle(app)
    assert app.role_var.get() == "reader" and app.calls == [("role", "reader")]
    assert app._see_adding is False and app._see_bare is None
    see_edit.toggle(app)
    assert app.role_var.get() == "translator" and app.calls[-1] == ("role", "translator")


def test_the_left_pane_has_the_switch_only_while_the_window_is_hidden(tmp_path):
    from test_see_panes import fake_app

    app = fake_app(tmp_path, role_var=Var("translator"))
    assert "edit" not in [r.name for r in ui.left_rows(app)]
    app._see_hidden = True
    rows = {r.name: r for r in ui.left_rows(app)}
    assert rows["edit"].on is False and rows["edit"].text == "Reader mode" and rows["edit"].kind == "toggle"
    app.role_var.set("reader")  # (Reader mode: checked)
    assert {r.name: r for r in ui.left_rows(app)}["edit"].on is True
    app.role_var.set("translator")
    app._role_job = "after#1"  # (the book's role still to be decided: the switch shows the role in force)
    assert {r.name: r for r in ui.left_rows(app)}["edit"].on is False
    assert "Editing" in [r.text for r in ui.foot_rows(app)][1]
    app._role_job = None
    app.role_var.set("reader")
    toggled = []
    app._on_role_changed = lambda chosen=True: toggled.append(app.role_var.get())
    ui.PANE_ACTIONS["edit"](app)
    assert toggled == ["translator"]


def test_no_mode_reaches_the_lettering_until_the_book_s_role_is_known(tmp_path):
    """The Book box names a book: until the role it opens in is decided (`_decide_role`, once the box rests), the
    lettering takes no mouse and shows no boxes - the start's editing never applies to a book kept in Reader mode
    meanwhile -; a book decided for already, a name that names no book and the reader's own choice need no wait."""
    from types import MethodType

    from taslation.ui import translator

    app = edit_app()
    for name in ("_cancel_role_job", "_decide_role", "_apply_role"):
        setattr(app, name, MethodType(getattr(translator.TranslatorMixin, name), app))
    later = []
    app.after = lambda ms, fn: later.append((ms, fn)) or f"after#{len(later)}"
    app.after_cancel = lambda job: later.pop()
    app.book_var, app.settings = Var("Book A"), SimpleNamespace(state_dir=tmp_path)
    translator.remember_role(tmp_path, "Book A", "reader")
    translator.remember_role(tmp_path, "Book B", "translator")

    def looked() -> tuple:
        see_edit.tick(app, app._see_through)
        return app._see_through.marks[-1] is not None, app._see_through.grounds[-1]

    assert see_edit.role_known(app) and looked() == (True, True)  # (no book named yet: the start's role)
    translator.TranslatorMixin._book_for_role(app)
    assert [ms for ms, _fn in later] == [translator.ROLE_DELAY_MS] and not see_edit.role_known(app)
    assert not see_edit.on(app) and looked() == (False, False)  # (still editing by role: no boxes, no mouse)
    later.pop()[1]()  # (the box rested: Book A opens in Reader mode)
    assert app.role_var.get() == "reader" and see_edit.role_known(app) and looked() == (False, False)
    app.book_var.set("Book B")
    translator.TranslatorMixin._book_for_role(app)
    assert not see_edit.role_known(app) and looked() == (False, False)
    later.pop()[1]()  # (Book B: editing)
    assert app.role_var.get() == "translator" and looked() == (True, True)
    translator.TranslatorMixin._book_for_role(app)  # (the same book named again: decided already)
    assert not later and see_edit.role_known(app)
    app.book_var.set("")
    translator.TranslatorMixin._book_for_role(app)  # (no book: nothing to decide)
    assert not later and see_edit.role_known(app)
    app.book_var.set("Book C")
    translator.TranslatorMixin._book_for_role(app)
    assert later and not see_edit.role_known(app)
    for name in ("_sync_tools", "_close_find", "_complete_on_show"):
        setattr(app, name, lambda: None)
    app.role_var.set("reader")
    translator.TranslatorMixin._on_role_changed(app, chosen=True)  # (the reader's choice meanwhile: it stands)
    assert not later and see_edit.role_known(app) and app._role_book == "Book C"
    assert translator.chosen_role(tmp_path, "Book C") == "reader"


def test_on_a_spread_the_plate_says_the_bubble_stays_on_its_own_page():
    one, two = [SimpleNamespace(unit=0)] * 3, [SimpleNamespace(unit=0), SimpleNamespace(unit=1)]
    assert see_edit.place_ask(one) == see_edit.PLACE_ASK and see_edit.place_ask(two) == see_edit.PLACE_ASK_SPREAD
    assert see_edit.PLACE_ASK_SPREAD.startswith(see_edit.PLACE_ASK)


# ------------------------------------------------------------------ the editor beside the region
def test_the_editor_goes_beside_the_region_on_its_monitor(monkeypatch):
    from taslation.ui import layout

    monkeypatch.setattr(layout, "frame_extents", lambda: (8, 31))
    area = [(0, 0, 1920, 1040)]
    monkeypatch.setattr(layout, "work_area", lambda widget, x=None, y=None: area[0])
    app = edit_app()
    place = see_edit.editor_place(app, Region(A))  # (on the screen: 600, 400 to 700, 460)
    assert place(300, 200) == (700 + 12, 400)  # (to its right, level with its top)
    place = see_edit.editor_place(app, Region((1000, 100, 1410, 160)))  # (right edge 1910: no room to its right)
    assert place(300, 200) == (1500 - 12 - 316, 400)
    area[0] = (0, 0, 700, 1040)
    place = see_edit.editor_place(app, Region((-400, 700, 100, 760)))  # (no room either side, low on the monitor)
    assert place(300, 200) == (700 - 316, 1040 - 239)
    app._see_through.client_origin = lambda: None
    assert see_edit.editor_place(app, Region(A)) is None


def test_show_original_held_leaves_the_region_s_patches_out_until_let_go():
    app = edit_app()
    a = app.last_result.regions[0]
    app._editor = Editor(a)
    see_edit.set_bare(app, a, True)
    assert app._see_bare is a and app._see_through.marks[-1].bare == 0
    see_edit.set_bare(app, a, False)
    assert app._see_bare is None and app._see_through.marks[-1].bare is None


def test_the_editor_s_show_original_and_its_place_from_its_size(hidden_root):
    from taslation.pipeline import manual_region
    from taslation.ui.dialogs import review

    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text, region.source_text = "translated", "Hi", "やあ"
    shown, sizes = [], []

    def at(width, height):
        sizes.append((width, height))
        return (123, 45)

    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                on_original=shown.append, at=at)
    assert d.original_btn is not None and len(sizes) == 1 and min(sizes[0]) > 1
    assert d.geometry().endswith("+123+45")
    d._show_original(True)
    d._show_original(True)  # (once per hold)
    d._show_original(False)
    d._show_original(True)
    d.destroy()  # (closed while held: the lettering back)
    assert shown == [True, False, True, False]
    plain = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None)
    assert plain.original_btn is None  # (the window on the screen: none)
    plain.destroy()


# ------------------------------------------------------------------ the Menu while Edit is on
class Menu:
    def __init__(self):
        self.entries = []

    def delete(self, first, last):
        self.entries.clear()

    def add_command(self, label, command, state="normal"):
        self.entries.append((label, command, state))

    def add_separator(self):
        self.entries.append(("-", None, None))

    def add_cascade(self, label, menu):
        self.entries.append((label, menu, None))


def test_the_menu_has_the_editing_while_edit_is_on_and_its_dialogs_take_the_keys():
    app = edit_app()
    opened = []
    for name in ("undo_edit", "redo_edit", "toggle_skip", "set_kind_of_selection", "set_size_of_selection",
                 "place_in_order", "copy_format", "paste_format", "paste_format_on_kind", "copy_region",
                 "paste_region", "_drop_chosen", "ignore_area_everywhere", "use_areas_for_series_now", "open_review",
                 "open_corrections", "open_lines_to_review", "open_find_replace", "open_glossary",
                 "open_book_settings"):
        setattr(app, name, lambda name=name: opened.append((name, getattr(app, "_see_asked", None))))
    app.toggle_order = lambda: setattr(app, "_ordering", [])
    app._end_order = lambda: (setattr(app, "_ordering", None), True)[1]
    app.series_areas_ready = lambda: False
    menu, page = Menu(), Menu()
    see_edit.build_menu(app, menu, page)
    labels = [e[0] for e in menu.entries]
    assert labels == ["Undo", "Redo", "Page", "-", "Review...", "My corrections...", "Lines to review...",
                      "Find and replace...", "Series sheet...", "Book settings...", "-"]
    page_labels = [e[0] for e in page.entries]
    assert page_labels[:3] == ["Reading order", see_edit.ADD_ENTRY, "Skip page"]
    assert see_edit.DROP_CHOSEN in page_labels and page.entries[-1][2] == "disabled"  # (no areas to use yet)
    dict((e[0], e[1]) for e in menu.entries)["Review..."]()
    assert opened[-1][0] == "open_review" and opened[-1][1] is not None  # (asked for: its dialog takes the keys)
    dict((e[0], e[1]) for e in page.entries)["Reading order"]()
    assert app._ordering == [] and app.said[-1] == see_edit.ORDERING
    see_edit.build_menu(app, menu, page)
    page_labels = [e[0] for e in page.entries]
    assert page_labels[:2] == ["Finish order", see_edit.CANCEL_ORDER] and "Reading order" not in page_labels
    dict((e[0], e[1]) for e in page.entries)[see_edit.CANCEL_ORDER]()
    assert app._ordering is None and app.said[-1] == "Reading order cancelled."
