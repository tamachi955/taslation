"""A page some viewers drag along with the pointer while the button is held, and turn once it is let go at the screen's
edge: nothing is learnt from a frame of it, and no pane's control fires on it (tests/test_follow.py and
tests/test_window_layout.py have the follow's and the capture area's part; tools/standin_e2e.py's scenario "s" plays
it on the stand-in viewer). Here: the side panes' ground taken only from a frame of the page at rest in its place
(`ui.seethrough.note_frame`, `rest_tick`), a pane's click only a press and its release on the pane itself
(`capture.seethrough._pane_proc`, `SeeThrough._pane_presses`), the right pane's plates left as they are while the
button is held (`_right_plates`), and the button read as the primary one, a mouse's buttons swapped too
(`button_down`)."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from test_seethrough import Facts, page, see_app

from taslation.capture import seethrough as window
from taslation.ui import seethrough as ui

REAL_BUTTON_DOWN = window.button_down  # (taken at import: tests/conftest.py puts a stand-in in its place in each test)
UP_AT = 12 | (34 << 16)  # (the lParam of a release at (12, 34) in the pane's pixels)


# ------------------------------------------------------------------ the button
def test_the_button_is_the_primary_one_with_the_mouse_s_buttons_swapped_too(monkeypatch):
    if not window.IS_WINDOWS:
        pytest.skip("Windows only")
    state = SimpleNamespace(swapped=0, down=set())
    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        GetSystemMetrics=lambda index: state.swapped if index == window.SM_SWAPBUTTON else 0,
        GetAsyncKeyState=lambda key: -32768 if key in state.down else 0))  # (the high bit: held now)
    assert REAL_BUTTON_DOWN() is False
    state.down = {window.VK_LBUTTON}
    assert REAL_BUTTON_DOWN() is True
    state.swapped = 1  # (for the left hand: the right button is the primary one)
    assert REAL_BUTTON_DOWN() is False
    state.down = {window.VK_RBUTTON}
    assert REAL_BUTTON_DOWN() is True


# ------------------------------------------------------------------ a pane's click
@pytest.fixture
def pane(monkeypatch):
    """The left pane's window procedure on a window of the test's (no window made), its presses and clicks kept on
    the test's clock."""
    if not window.IS_WINDOWS:
        pytest.skip("Windows only")
    clock = SimpleNamespace(now=50.0)
    downs: dict[int, float] = {}
    taken: list[tuple[int, int]] = []
    monkeypatch.setattr(window, "_pane_downs", downs)
    monkeypatch.setattr(window, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setitem(window._pane_clicks, 501, lambda x, y: taken.append((x, y)))
    over = window.SeeThrough()
    over.panes["left"] = 501
    over._pane_shown["left"] = (1, (100, 200), (150, 300))  # (on the screen at 100-250, 200-500)
    notes: list[str] = []
    over._note = lambda kind, **facts: notes.append(kind)
    return SimpleNamespace(clock=clock, downs=downs, taken=taken, over=over, notes=notes)


def test_a_release_over_a_pane_is_a_click_only_after_a_press_on_the_pane(pane):
    window._pane_proc(501, window.WM_LBUTTONUP, 0, UP_AT)  # a press that began on the viewer (a page dragged along)
    assert pane.taken == []  # ... let go over a control of the pane: nothing fires
    window._pane_proc(501, window.WM_LBUTTONDOWN, 1, UP_AT)
    window._pane_proc(501, window.WM_LBUTTONUP, 0, UP_AT)
    assert pane.taken == [(12, 34)] and pane.downs == {}  # pressed and let go on the pane: a click
    window._pane_proc(501, window.WM_LBUTTONUP, 0, UP_AT)
    assert pane.taken == [(12, 34)]  # (a release with no press before it)


def test_a_press_on_a_pane_let_go_elsewhere_is_forgotten_and_nothing_stays_stuck(pane):
    over, now = pane.over, pane.clock.now
    window._pane_proc(501, window.WM_LBUTTONDOWN, 1, UP_AT)
    on, off = (120, 220), (10, 10)
    over._pane_presses(off, True, now + 2)  # held, the pointer dragged off the pane: kept
    over._pane_presses(on, False, now + 2)  # back over it and let go: its release is on its way
    over._pane_presses(off, False, now + window.PRESS_STALE_S / 2)  # just pressed: the same
    assert 501 in pane.downs and pane.notes == []
    over._pane_presses(off, False, now + window.PRESS_STALE_S)  # let go over another window: forgotten
    assert pane.downs == {} and pane.notes == ["press_forgotten"]
    window._pane_proc(501, window.WM_LBUTTONUP, 0, UP_AT)  # a later release over the pane (a drag that began on the
    assert pane.taken == []  # viewer): no click from the old press
    window._pane_proc(501, window.WM_LBUTTONDOWN, 1, UP_AT)  # and the pane takes the next click as ever
    window._pane_proc(501, window.WM_LBUTTONUP, 0, UP_AT)
    assert pane.taken == [(12, 34)]
    window._pane_proc(501, window.WM_LBUTTONDOWN, 1, UP_AT)
    over._pane_shown.pop("left")  # (the pane hidden while pressed: forgotten too, once the button is up)
    over._pane_presses(on, False, now + 5)
    assert pane.downs == {}


def test_the_right_pane_s_plates_stay_as_they_are_while_the_button_is_held(monkeypatch):
    styles = {9: window.EX_STYLE}
    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        GetWindowLongW=lambda hwnd, index: styles[hwnd],
        SetWindowLongW=lambda hwnd, index, value: styles.__setitem__(hwnd, value) or 1,
        ShowWindow=lambda hwnd, cmd: 1))
    over = window.SeeThrough()
    over.panes["right"] = 9
    over._pane_shown["right"] = (3, (1000, 200), (200, 300))
    panes = {"right": (3, None, (10, 10, 210, 310), ((0, 0, 200, 27), (0, 31, 200, 58)))}
    over._right_plates((1050, 210), panes, held=True)  # a press from the viewer comes over a plate: still the viewer's
    assert styles[9] & window.WS_EX_TRANSPARENT and not over._right_takes
    over._right_plates((1050, 210), panes)  # let go there: the plate takes the next click
    assert not styles[9] & window.WS_EX_TRANSPARENT and over._right_takes
    over._right_plates((1050, 230), panes, held=True)  # pressed on the plate and dragged off it: as it was
    assert over._right_takes


# ------------------------------------------------------------------ the panes' ground
def _frames():
    at_rest = Image.fromarray(page(ground=0, box=(100, 0, 300, 300)))
    slid = Image.fromarray(page(ground=0, box=(180, 0, 380, 300)))  # the page dragged 80 px to the right
    slid_far = Image.fromarray(page(ground=0, box=(10, 0, 390, 300)))  # half of it and half of the next: no room
    return at_rest, slid, slid_far


@pytest.fixture
def ground(monkeypatch):
    """`note_frame` on the test's clock, the button the test's."""
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock.now)
    app = see_app()
    app.held = False
    app._held_in_viewer = lambda: app.held
    return SimpleNamespace(clock=clock, app=app)


def _note(app, image):
    ui.note_frame(app, image, Facts(image))
    return app._see_ground


def test_the_panes_ground_is_taken_from_the_page_at_rest_alone(ground):
    app, clock = ground.app, ground.clock
    at_rest, slid, slid_far = _frames()
    assert _note(app, at_rest)[1] == (100, 0, 300, 300)  # (the first frame of a viewer: at rest)
    rest = app._see_ground
    app.held = True  # the page dragged along with the pointer: nothing of it is taken
    for image in (slid, slid_far, slid_far):
        clock.now += 0.1
        assert _note(app, image) is rest and app._see_rest_box == (100, 0, 300, 300)
    clock.now += 2.0
    ui.rest_tick(app)  # (held there still)
    assert app._see_ground is rest
    app.held = False  # let go: the page snaps back - a frame of it in its place again
    clock.now += 0.05
    assert _note(app, at_rest) is rest
    clock.now += ui.REST_S + 0.001
    ui.rest_tick(app)
    assert app._see_ground[1] == (100, 0, 300, 300)


def test_a_frame_out_of_its_place_becomes_the_page_at_rest_once_it_stayed(ground):
    app, clock = ground.app, ground.clock
    at_rest, slid, slid_far = _frames()
    _note(app, at_rest)
    rest = app._see_ground
    assert _note(app, slid_far) is rest  # a box another than the last frame's, no press: a page moving (a turn drawn
    clock.now += ui.REST_S / 2  # as a slide) - not taken yet
    ui.rest_tick(app)
    assert app._see_ground is rest
    clock.now += 0.01
    assert _note(app, slid) is rest  # a new frame: its own wait from it
    clock.now += ui.REST_S - 0.02
    ui.rest_tick(app)
    assert app._see_ground is rest
    clock.now += 0.03
    ui.rest_tick(app)  # stayed REST_S: the page at rest now
    assert app._see_ground[1] == (180, 0, 380, 300) and app._see_rest_box == (180, 0, 380, 300)
    assert _note(app, slid)[1] == (180, 0, 380, 300)  # the same box again: at rest at once
    app.held = True  # a press after the frame: the wait starts again from its release - RELEASE_S, the frame noted
    clock.now += 0.01  # while the button was held (the viewer may answer the release yet)
    _note(app, at_rest)
    clock.now += ui.REST_S * 3
    ui.rest_tick(app)
    app.held = False
    clock.now += ui.REST_S + 0.01
    ui.rest_tick(app)
    assert app._see_ground[1] == (180, 0, 380, 300)
    clock.now += ui.RELEASE_S - ui.REST_S
    ui.rest_tick(app)
    assert app._see_ground[1] == (100, 0, 300, 300)  # (no other picture came: the viewer left it so)


def test_a_frame_of_no_page_on_a_flat_ground_hides_the_panes_only_at_rest(ground):
    app, clock = ground.app, ground.clock
    at_rest, _slid, _far = _frames()
    _note(app, at_rest)
    rest = app._see_ground
    noise =Image.fromarray(np.random.default_rng(3).integers(0, 255, (300, 400, 3), dtype=np.uint8))  # no flat ground
    assert _note(app, noise) is rest  # (no box: another than the last frame's)
    assert _note(app, noise) is rest  # no box again: no page in its place yet (`_keeps_ground`) ...
    clock.now += ui.REST_S + 0.001
    ui.rest_tick(app)
    assert app._see_ground is None  # ... until it stayed: the panes hide, as ever
    assert app._see_rest_box == (100, 0, 300, 300)  # (the last box at rest kept: it tells half a spread)
    clock.now += 1
    assert _note(app, at_rest) is None  # back: a box another than the frame before's ...
    assert _note(app, at_rest)[1] == (100, 0, 300, 300)  # ... and at rest on the next


def test_a_slide_s_frames_with_no_page_box_leave_the_ground_until_a_page_is_at_rest(ground):
    """The stand-in's scenario "s" on GitHub's runners (2 runs of 3): both panes hid for about 0.2 s, 0.5 s after the
    release of a slide to the screen's edge ("no ground"): the frames held showed the page slid half out of the frame,
    where no page box is found, and the frame captured right after the release, no box either, was taken for the page
    at rest by being as the frame before."""
    app, clock = ground.app, ground.clock
    at_rest, _slid, _far = _frames()
    half_out = Image.fromarray(page(ground=0, box=(2, 0, 398, 300)))  # (the page out to the frame's edges: no box)
    assert ui.frame_look(app, half_out, Facts(half_out)).box is None
    _note(app, at_rest)
    rest = app._see_ground
    app.held = True
    for _n in range(3):  # slid with the pointer
        clock.now += 0.1
        assert _note(app, half_out) is rest
    app.held = False  # let go at the edge
    for _n in range(3):  # the slid picture captured again, and again: not the page at rest
        clock.now += 0.1
        assert _note(app, half_out) is rest
    turned = Image.fromarray(page(seed=2, ground=0, box=(120, 0, 320, 300)))  # the next screen drawn in its place
    clock.now += 0.1
    assert _note(app, turned) is rest
    clock.now += 0.1
    assert _note(app, turned)[1] == (120, 0, 320, 300)  # at rest: its own ground
    # the very picture captured again (its facts shared) keeps its wait: a page on no flat ground at rest hides them
    noise = Image.fromarray(np.random.default_rng(3).integers(0, 255, (300, 400, 3), dtype=np.uint8))
    facts = Facts(noise)
    for _n in range(4):
        ui.note_frame(app, noise, facts)
        clock.now += ui.REST_S / 3
        ui.rest_tick(app)
    assert app._see_ground is None


def test_the_frame_held_last_does_not_become_the_page_at_rest_once_the_next_screen_is_drawn(ground):
    """... the other way it hid them: the frame held last, the page half out, became the page at rest REST_S after
    the release, the next screen's soft frame drawn meanwhile being one to wait out."""
    app, clock = ground.app, ground.clock
    at_rest, _slid, _far = _frames()
    half_out = Image.fromarray(page(ground=0, box=(2, 0, 398, 300)))
    soft = np.zeros((300, 400, 3), np.uint8)
    soft[:, 120:320] = np.random.default_rng(4).integers(215, 250, (300, 200, 1), dtype=np.uint8)  # pale, no ink
    soft = Image.fromarray(soft)
    assert ui.frame_look(app, soft, Facts(soft)).kind == "washed"
    _note(app, at_rest)
    rest = app._see_ground
    app.held = True
    clock.now += 0.1
    assert _note(app, half_out) is rest
    app.held = False  # let go at the edge: the next screen drawn soft first
    clock.now += 0.05
    ui.rest_tick(app)
    assert _note(app, soft) is rest
    for _n in range(4):
        clock.now += ui.REST_S / 2
        ui.rest_tick(app)
        assert app._see_ground is rest
    turned = Image.fromarray(page(seed=2, ground=0, box=(120, 0, 320, 300)))  # sharp
    assert _note(app, turned) is rest
    clock.now += ui.REST_S + 0.001
    ui.rest_tick(app)
    assert app._see_ground[1] == (120, 0, 320, 300)


def test_the_picture_held_captured_again_once_let_go_waits_for_the_viewer_s_answer(ground):
    """The stand-in's scenario "s" on GitHub's runners (once, after six runs that passed): the right pane alone hid
    for a quarter of a second, 0.7 s after the release of a slide to the screen's edge. The one picture of the slide
    that reached the capture showed the page some 200 px to the right, on the ground still; captured again once the
    button was up, it was taken for the page at rest by being as the frame before (itself), and the page's right edge
    came over the right pane's place. The next screen reached the capture 0.7 s after the release."""
    app, clock = ground.app, ground.clock
    at_rest, slid, _far = _frames()
    _note(app, at_rest)
    rest = app._see_ground
    app.held = True
    clock.now += 0.1
    facts = Facts(slid)  # (the one picture of the slide captured: each capture of it shares its facts)
    ui.note_frame(app, slid, facts)
    for _n in range(3):  # held at the edge: the capture has that picture still
        clock.now += 0.4
        ui.note_frame(app, slid, facts)
        ui.rest_tick(app)
        assert app._see_ground is rest
    app.held = False  # let go: the very picture captured again, the viewer's answer not there yet
    for _n in range(6):
        clock.now += 0.1
        ui.note_frame(app, slid, facts)
        ui.rest_tick(app)
        assert app._see_ground is rest
    turned = Image.fromarray(page(seed=2, ground=0, box=(120, 0, 320, 300)))  # the next screen, 0.7 s after it
    clock.now += 0.1
    assert _note(app, turned) is rest  # (a box another than the picture before's)
    clock.now += ui.REST_S + 0.001
    ui.rest_tick(app)
    assert app._see_ground[1] == (120, 0, 320, 300)


def _washed():
    soft = np.zeros((300, 400, 3), np.uint8)
    soft[:, 120:320] = np.random.default_rng(4).integers(215, 250, (300, 200, 1), dtype=np.uint8)  # pale, no ink
    return Image.fromarray(soft)


def test_a_picture_the_button_was_held_over_is_the_page_at_rest_only_release_s_after_the_release(ground):
    from taslation.ui import live

    assert ui.RELEASE_S * 1000 == live.RELEASE_ANSWER_MS  # (as the live view waits for the viewer's answer)
    app, clock = ground.app, ground.clock
    at_rest, slid, _far = _frames()
    _note(app, at_rest)
    rest = app._see_ground
    app.held = True
    clock.now += 0.1
    _note(app, slid)
    clock.now += 1.0
    ui.rest_tick(app)
    app.held = False  # let go, and no capture meanwhile (a busy computer)
    clock.now += ui.REST_S + 0.01
    ui.rest_tick(app)
    assert app._see_ground is rest  # (REST_S after the release it was the slid page's ground)
    soft = _washed()  # the next screen's preview, a frame to wait out: the picture held is not on show any more
    assert ui.frame_look(app, soft, Facts(soft)).kind == "washed"
    assert _note(app, soft) is rest
    clock.now += ui.RELEASE_S
    ui.rest_tick(app)
    assert app._see_ground is rest and app._see_unrested is None  # dropped, the ground left as it is
    app.held = True  # a page the viewer leaves where it was dragged (no other picture after it) ...
    clock.now += 0.1
    _note(app, slid)
    app.held = False
    clock.now += ui.RELEASE_S - 0.01
    ui.rest_tick(app)
    assert app._see_ground is rest
    clock.now += 0.02
    ui.rest_tick(app)
    assert app._see_ground[1] == (180, 0, 380, 300)  # ... is the page at rest RELEASE_S after the release


def test_a_frame_of_another_size_or_viewer_is_at_rest_on_its_own(ground):
    app = ground.app
    at_rest, slid, _far = _frames()
    _note(app, at_rest)
    wider = Image.fromarray(page(ground=0, box=(180, 0, 380, 300))).resize((420, 300))  # (the window resized)
    assert _note(app, wider)[0] == (420, 300)
    app.selected = SimpleNamespace(hwnd=31)  # (another viewer chosen)
    assert _note(app, slid)[1] == (180, 0, 380, 300)
