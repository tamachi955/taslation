"""A viewer that was behind other windows when TASlation started, chosen and brought to the front: it comes into
sight with its bars up when the pointer rests on them (a click on its title bar or its tab leaves the pointer at its
top) or a click holds them, and keeps them while its pages are turned with the keys. Every frame then has bars over
the page; the side panes' ground was taken only from a frame without them, so the panes stayed hidden page after
page while the lettering came on each one (`ui.seethrough.note_frame`, `_ground_under_bars`). Played on the stand-in
viewer by tools/standin_e2e.py --start-behind (scenario h, `Behind`, `tools/standin_cover.py`), its bars held with
--standin-bars-held. Synthetic frames and a fake window only."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from test_see_panes import BAND, FRAME, fake_app
from test_seethrough import Facts, see_app

from taslation import panes as pn
from taslation.ui import seethrough as ui

SPREAD = (236, 0, 1668, 946)  # (on every fourth pixel: the look's step)
BARS = ((0, 94), (880, 946))  # a viewer's top bar and bottom bar (the stand-in's dark profile), across the frame


def frame(bars=True, size=FRAME, spread=SPREAD, seed=1):
    """A dark ground, a spread of noise on it and, with *bars*, a bar across the whole frame at its top and bottom."""
    rng = np.random.default_rng(seed)
    width, height = size
    out = np.full((height, width, 3), 20, np.uint8)
    left, top, right, bottom = spread
    out[top:bottom, left:right] = rng.integers(60, 250, (bottom - top, right - left, 1), dtype=np.uint8).repeat(3, 2)
    if bars:
        for start, end in BARS:
            out[start:min(end, height)] = 70
    return Image.fromarray(out)


@pytest.fixture
def app(monkeypatch):
    """`note_frame`'s side of the window on the test's clock, the button the test's."""
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock.now)
    out = see_app()
    out._see_ground = out._see_unrested = None  # (as `ui.seethrough.start` has them)
    out.held = False
    out._held_in_viewer = lambda: out.held
    out.clock = clock
    return out


def note(app, image):
    ui.note_frame(app, image, Facts(image))
    return app._see_ground


def near(box, want, step=4):
    return box is not None and all(abs(a - b) <= step for a, b in zip(box, want))


def test_a_viewer_in_sight_with_its_bars_up_from_the_first_frame_gets_its_side_panes(app, tmp_path):
    barred = frame()
    ground = note(app, barred)  # (the first frame of a viewer: at rest)
    assert app._see_bars_since is not None  # (the bars are seen as ever: the page is read under them after BAR_WAIT_S)
    assert ground is not None and ground[0] == FRAME and near(ground[1][::2], SPREAD[::2])  # the page's columns
    assert ground[2] == BAND and ground[4] == (0, FRAME[0])  # the steady band, where bars never come; the area
    assert note(app, barred) is ground  # (the same frame again: as it was)
    window = fake_app(tmp_path, _see_ground=ground)
    ui.panes_tick(window)
    left, right = window._see_through.handed[-1]
    assert left is not None and right is not None  # both panes on the screen, the bars up all the while
    for _bgra, box, *_plates in (left, right):
        assert pn.overlap(box, ground[1]) == 0  # beside the page ...
        assert box[1] >= BAND[0] and box[1] > BARS[0][1] and box[3] <= BAND[1]  # ... and under the top bar


def test_page_turns_with_the_bars_held_keep_the_panes(app):
    first = note(app, frame(seed=1))
    for seed in (2, 3, 4):  # the pages turned with the keys, the bars up all the while
        app.clock.now += 3.0
        ground = note(app, frame(seed=seed))
        if app.clock.now - app._see_bars_since < ui.BAR_WAIT_S:
            assert ground is first  # (a ground of the frame's size is had: frames with new bars leave it as it is)
        else:  # (bars that stayed: a frame at rest under them gives the ground anew - the same page box here)
            assert ground == first


def test_frames_with_bars_leave_a_ground_of_their_size_as_it_is(app):
    plain = note(app, frame(bars=False))
    assert plain is not None and app._see_bars_since is None
    other = frame(spread=(300, 0, 1600, 946))  # (bars over another box: a page in motion with its bars, say)
    assert note(app, other) is plain and note(app, other) is plain


def test_bars_that_stay_are_a_state_and_a_frame_at_rest_under_them_gives_the_ground_anew(app):
    # (the owner's window: a browser's bar under the area's top made every frame one with bars; the cover, the first
    # screen, gave the ground, and the spreads after it never did - the panes stood by the cover for 688 s)
    cover = note(app, frame(spread=(616, 0, 1288, 946)))
    assert near(cover[1][::2], (616, 1288))
    app.clock.now += 1.0
    spread = frame(seed=2)
    assert note(app, spread) is cover and note(app, spread) is cover  # (new bars: the ground as it is)
    app.clock.now += ui.BAR_WAIT_S
    note(app, spread)  # (the bars have stayed: a frame as any other - its box another than the frame before's ...)
    assert app._see_ground is cover
    app.clock.now += 0.05
    note(app, spread)  # (... and the same in the next: at rest)
    assert near(app._see_ground[1][::2], SPREAD[::2]) and app._see_rest_box == app._see_ground[1]
    assert app._see_bars_since is not None  # (the bars are there all the while: read with them painted over)


def test_a_frame_with_bars_of_another_size_gives_the_panes_their_ground_at_that_size(app):
    plain = note(app, frame(bars=False))
    assert plain[0] == FRAME
    narrower = (1500, 946)
    barred = frame(size=narrower, spread=(236, 0, 1264, 946))
    first = note(app, barred)
    assert first[0] == narrower and near(first[1][::2], (236, 1264))  # (the first frame of its size counts at rest)


def test_a_frame_with_bars_out_of_the_place_of_the_one_before_waits_its_rest(app):
    app._see_box_seen = ((0, FRAME), (10, 0, 300, 946))  # (the frame before had another box)
    barred = frame()
    assert note(app, barred) is None  # not at rest yet: kept aside
    app.clock.now += ui.REST_S / 2
    ui.rest_tick(app)
    assert app._see_ground is None
    app.clock.now += ui.REST_S
    ui.rest_tick(app)  # stayed REST_S with no frame after it: the page at rest
    assert app._see_ground is not None and near(app._see_ground[1][::2], SPREAD[::2])


def test_nothing_is_taken_from_a_frame_with_bars_while_the_button_is_held_in_the_viewer(app):
    app.held = True  # (a page some viewers drag along with the pointer: out of its place)
    for _ in range(3):
        assert note(app, frame()) is None
    app.clock.now += 2.0
    ui.rest_tick(app)
    assert app._see_ground is None
    app.held = False  # let go: the next frame of it at rest gives the ground
    app.clock.now += 0.05
    note(app, frame())
    app.clock.now += ui.REST_S + 0.01
    ui.rest_tick(app)
    assert app._see_ground is not None


def test_once_the_bars_go_the_frame_without_them_is_the_ground_again(app):
    barred = note(app, frame())
    assert barred is not None
    app.clock.now += 1.0
    plain = frame(bars=False)
    note(app, plain)  # (its box another than the barred frame's: its top under no bar)
    app.clock.now += ui.REST_S + 0.01
    ui.rest_tick(app)
    assert app._see_bars_since is None and app._see_ground is not barred
    assert near(app._see_ground[1][::2], SPREAD[::2])
