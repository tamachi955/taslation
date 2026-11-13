"""The geometry of rectangles a pointer takes hold of (Set area dialog, translator mode): no display needed."""
from __future__ import annotations

import pytest

from taslation.ui import area

SIZE = (1000, 800)


def test_margins_and_boxes_convert_both_ways_as_the_pipeline_reads_margins():
    assert area.margins_to_box((0, 85, 0, 0), SIZE) == (0, 85, 1000, 800)
    assert area.margins_to_box((10, 20, 30, 40), SIZE) == (10, 20, 970, 760)
    for margins in ((0, 0, 0, 0), (0, 85, 0, 0), (10, 20, 30, 40), (499, 0, 500, 799)):
        assert area.box_to_margins(area.margins_to_box(margins, SIZE), SIZE) == margins
    assert area.margins_to_box((5000, 0, 0, 0), SIZE) == (999, 0, 1000, 800)  # too big: one pixel is left
    assert area.margins_to_box((-3, 0, 0, 0), SIZE)[0] == 0
    assert area.box_to_margins((-20, -5, 2000, 900), SIZE) == (0, 0, 0, 0)  # clamped to the capture
    assert area.box_to_margins((300, 200, 100, 50), SIZE) == (100, 50, 700, 600)  # corners in any order


def test_handles_sit_on_the_corners_and_the_middles_of_the_sides():
    points = area.handles((100, 50, 300, 250))
    assert list(points) == list(area.HANDLES)
    assert points["nw"] == (100, 50) and points["se"] == (300, 250)
    assert points["n"] == (200, 50) and points["e"] == (300, 150) and points["s"] == (200, 250) and points["w"] == (100, 150)


def test_a_press_takes_hold_of_a_handle_a_side_the_inside_or_nothing():
    box = (100, 100, 400, 300)
    assert area.grip_at(box, 102, 97) == "nw"
    assert area.grip_at(box, 398, 305) == "se"
    assert area.grip_at(box, 250, 100) == "n"  # the middle handle
    assert area.grip_at(box, 160, 103) == "n"  # anywhere along the side
    assert area.grip_at(box, 405, 220) == "e"
    assert area.grip_at(box, 97, 200) == "w"
    assert area.grip_at(box, 250, 200) == "move"
    assert area.grip_at(box, 600, 200) is None and area.grip_at(box, 250, 80) is None
    small = (100, 100, 124, 112)  # a small box keeps its middle for moving
    assert area.grip_at(small, 112, 106) == "move"
    assert area.grip_at(small, 100, 100) == "nw"


def test_resizing_follows_the_handle_and_stops_at_the_image_and_the_minimum():
    box = (100, 100, 400, 300)
    assert area.resize(box, "se", 50, 20, SIZE, 24) == (100, 100, 450, 320)
    assert area.resize(box, "nw", -30, -40, SIZE, 24) == (70, 60, 400, 300)
    assert area.resize(box, "n", 500, 500, SIZE, 24) == (100, 276, 400, 300)  # stops short of the bottom side
    assert area.resize(box, "e", 9999, 7, SIZE, 24) == (100, 100, 1000, 300)  # the image's edge; n/s untouched
    assert area.resize(box, "w", -9999, 0, SIZE, 24) == (0, 100, 400, 300)
    assert area.resize(box, "sw", 1000, -1000, SIZE, 24) == (376, 100, 400, 124)
    assert area.resize(box, "s", 0.4, 0, SIZE, 24) == (100, 100, 400, 300)  # whole pixels


def test_moving_keeps_the_size_and_stops_at_the_edges():
    box = (100, 100, 400, 300)
    assert area.move(box, 50, -20, SIZE) == (150, 80, 450, 280)
    assert area.move(box, -500, -500, SIZE) == (0, 0, 300, 200)
    assert area.move(box, 5000, 5000, SIZE) == (700, 600, 1000, 800)
    assert area.move((0, 0, 1200, 900), 10, 10, SIZE) == (0, 0, 1000, 800)  # larger than the image: the image


@pytest.mark.parametrize("grip, now, expected", [
    ("move", (220, 230), (120, 130, 420, 330)),
    ("se", (220, 230), (100, 100, 420, 330)),
    (None, (40, 30), (40, 30, 200, 200)),  # a new box from the press, dragged up and left
    (None, (2000, -50), (200, 0, 1000, 200)),  # clamped to the image
])
def test_a_drag_from_the_press_point(grip, now, expected):
    assert area.drag((100, 100, 400, 300), grip, (200, 200), now, SIZE, 24) == expected


def test_too_small_and_canvas_coordinates():
    assert area.big_enough((0, 0, 24, 24), 24) and not area.big_enough((0, 0, 23, 100), 24)
    scale, offset = 0.5, (10, 20)
    assert area.to_canvas(100, 200, scale, offset) == (60, 120)
    assert area.to_image(60, 120, scale, offset) == (100, 200)
    assert area.to_image(5, 10, scale, offset) == (-10, -20)  # outside the picture: not clamped
    assert area.box_to_canvas((100, 200, 300, 400), scale, offset) == (60, 120, 160, 220)
    assert area.to_image(30, 40, 0, (0, 0)) == (30, 40)  # no picture drawn yet: scale taken as 1


def test_the_shade_outside_the_box():
    frame = (0, 0, 100, 80)
    parts = area.outside((20, 10, 70, 60), frame)
    assert parts == [(0, 0, 100, 10), (0, 60, 100, 80), (0, 10, 20, 60), (70, 10, 100, 60)]
    assert sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in parts) == 100 * 80 - 50 * 50
    assert area.outside(frame, frame) == []
    assert area.outside((0, 0, 100, 40), frame) == [(0, 40, 100, 80)]


def test_a_picture_fits_its_canvas_clear_of_the_edges():
    assert area.fit((800, 600), (400, 300)) == ((400, 300), (0, 0))
    assert area.fit((800, 600), (416, 316), inset=8) == ((400, 300), (8, 8))  # handles on its edges show whole
    assert area.fit((200, 100), (400, 300)) == ((200, 100), (100, 100))  # never enlarged ...
    assert area.fit((200, 100), (400, 300), enlarge=True) == ((400, 200), (0, 50))  # ... unless asked
    assert area.fit((10, 10), (4, 4), inset=8) == ((1, 1), (1, 1))  # a canvas too small: one pixel, no failure


def test_groups_flow_into_rows_and_none_is_cut():
    sizes = [(300, 24), (200, 30), (250, 24), (500, 26)]
    places, height, rows = area.flow(sizes, 800, gap=10, row_gap=4)
    assert rows == 2 and places[:3] == [(0, 3), (310, 0), (520, 3)]  # the next would pass 800: a new row
    assert places[3] == (0, 34) and height == 30 + 4 + 26
    for (x, _y), (w, _h) in zip(places, sizes):
        assert x + w <= 800
    places, height, rows = area.flow(sizes, 2000, gap=10)
    assert rows == 1 and height == 30
    places, _height, rows = area.flow([(900, 20), (100, 20)], 800)  # wider than a row: a row of its own
    assert rows == 2 and places == [(0, 0), (0, 20)]
    assert area.flow([], 800) == ([], 0, 0)


# ---------------------------------------------------------------- a turned frame and its rotate handle
def _on_circle(centre, radius, degrees):
    """The point *radius* from *centre* in the way *degrees* counter-clockwise from straight up (screen)."""
    import math

    a = math.radians(degrees)
    return (centre[0] - radius * math.sin(a), centre[1] - radius * math.cos(a))


def test_the_rotate_handle_stands_over_the_top_side_and_turns_with_the_frame():
    box = (100, 100, 300, 160)
    stalk, knob = area.rotate_handle(area.box_corners(box))
    assert stalk == (200, 100) and knob == (200, 100 - area.ROTATE_GAP)
    turned = area.turn_corners(area.box_corners(box), 90)  # counter-clockwise: its up is the page's left
    stalk, knob = area.rotate_handle(turned)
    assert stalk == pytest.approx((170, 130)) and knob == pytest.approx((170 - area.ROTATE_GAP, 130))
    stalk, knob = area.rotate_handle(area.box_corners((100, 5, 300, 60)), room=(0, 0, 800, 600))
    assert stalk == (200, 60) and knob == (200, 60 + area.ROTATE_GAP)  # no room above it: under the bottom side


def test_a_press_on_the_rotate_handle_takes_hold_of_it_on_upright_and_turned_frames():
    box = (100, 100, 300, 160)
    corners = area.box_corners(box)
    assert area.grip_on_frame(corners, 200, 100 - area.ROTATE_GAP) == "rotate"
    assert area.grip_on_frame(corners, 203, 100 - area.ROTATE_GAP + 4) == "rotate"
    assert area.grip_on_frame(corners, 200, 100) == "n" and area.grip_on_frame(corners, 200, 40) is None
    turned = area.turn_corners(corners, 30)
    knob = area.rotate_handle(turned)[1]
    assert area.grip_on_frame(turned, *knob) == "rotate"
    assert area.grip_on_frame(turned, 200, 100 - area.ROTATE_GAP) != "rotate"  # where the upright one had it
    for name, (x, y) in area.frame_handles(turned).items():  # its handles, named in its own directions
        assert area.grip_on_frame(turned, x, y) == name
    assert area.grip_on_frame(turned, 200, 130) == "move"
    assert area.grip_on_frame(turned, 110, 105) is None  # inside the upright box, outside the turned frame


def test_an_upright_frame_takes_hold_as_its_box_does():
    for box in ((100, 100, 400, 300), (50, 60, 62, 75)):
        corners = area.box_corners(box)
        assert area.frame_handles(corners) == area.handles(box)
        for x in range(box[0] - 12, box[2] + 13, 3):
            for y in range(box[1] - 12, box[3] + 13, 3):
                if area.grip_on_frame(corners, x, y) != "rotate":
                    assert area.grip_on_frame(corners, x, y) == area.grip_at(box, x, y), (box, x, y)
        assert all(area.page_handle(name, corners) == name for name in area.HANDLES)


def test_a_turned_frames_handles_resize_the_side_of_the_box_they_point_to():
    corners = area.box_corners((100, 100, 300, 160))
    turned = area.turn_corners(corners, 90)
    assert [area.page_handle(n, turned) for n in ("n", "e", "s", "w", "ne")] == ["w", "n", "e", "s", "nw"]
    assert [area.page_handle(n, area.turn_corners(corners, -90)) for n in ("n", "e")] == ["e", "s"]
    assert [area.page_handle(n, area.turn_corners(corners, 20)) for n in area.HANDLES] == list(area.HANDLES)
    assert area.page_handle("move", turned) == "move"


def test_the_frame_of_a_box_filled_whole_holds_the_box():
    box = (100, 100, 300, 160)
    assert area.full_frame(box, 0) == area.box_corners(box)
    frame = area.full_frame(box, 30)
    right, down, w, h = area.frame_axes(frame)
    assert area.frame_centre(frame) == pytest.approx((200, 130))
    assert w == pytest.approx(200 * 0.8660254 + 60 * 0.5) and h == pytest.approx(200 * 0.5 + 60 * 0.8660254)
    assert right == pytest.approx((0.8660254, -0.5))  # its top side rises to the right: counter-clockwise


def test_the_angle_follows_the_pointer_round_the_middle():
    c = (200.0, 200.0)
    assert area.pointer_angle(c, (200, 100)) == pytest.approx(0)
    assert area.pointer_angle(c, (100, 200)) == pytest.approx(90)  # to the left: counter-clockwise
    assert area.pointer_angle(c, (300, 200)) == pytest.approx(-90)
    press = _on_circle(c, 80, 10)  # the handle of a frame at 10 degrees, taken a little off its middle
    assert area.turn_angle(10, c, press, _on_circle(c, 80, 37.4)) == 37.0
    assert area.turn_angle(10, c, press, _on_circle(c, 30, -25)) == -25.0  # how far out does not matter
    assert area.turn_angle(10, c, press, press) == 10.0


def test_shift_snaps_to_steps_and_near_upright_is_upright():
    c = (0.0, 0.0)
    press = _on_circle(c, 50, 0)
    angle = lambda d, steps=False: area.turn_angle(0, c, press, _on_circle(c, 50, d), steps)  # noqa: E731
    assert angle(22.0, True) == 15.0 and angle(23.0, True) == 30.0 and angle(-7.4, True) == 0.0
    assert angle(52.0, True) == 45.0 and angle(-68, True) == -75.0
    assert angle(2.9) == 0.0 and angle(-3.0) == 0.0 and angle(3.6) == 4.0 and angle(-3.6) == -4.0
    assert str(angle(-1.0)) == "0.0"  # never -0


def test_the_angle_stays_within_the_range_the_cache_takes():
    c = (0.0, 0.0)
    press = _on_circle(c, 50, 0)
    assert area.turn_angle(0, c, press, _on_circle(c, 50, 95)) == area.MAX_TURN == 89.0
    assert area.turn_angle(0, c, press, _on_circle(c, 50, -135)) == -89.0
    assert area.turn_angle(0, c, press, _on_circle(c, 50, 90), steps=True) == 89.0
    assert area.turn_angle(80, c, press, _on_circle(c, 50, 30)) == 89.0  # past 90 from the start: still within
    assert area.snap_angle(-170.0) == -89.0
