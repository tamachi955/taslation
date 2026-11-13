"""Frames and labels that show on any page: translator mode's selection, its handles, the rotate handle, the found
regions' outlines and the rectangle a drag draws are two-tone (a dark stroke under the colour: the yellow frame alone
is 1.4:1 on white, the new region's blue 2.6:1), and a region's label goes where it covers no neighbouring region
when there is room (the "not text" label used to cover part of the bubble above it)."""
from __future__ import annotations

from types import SimpleNamespace

from PIL import Image
from test_reading_window import Shapes, _region, _sized

from taslation.ui import area, preview, translator
from taslation.ui.preview import ImageCanvas


# ------------------------------------------------------------------ where a label goes
def test_a_label_goes_above_its_region_when_that_is_free():
    assert area.place_label((40, 12), (100, 100, 200, 160), [], (0, 0, 400, 300)) == (100, 100 - 3 - 12)


def test_a_label_leaves_the_region_above_in_view():
    above = (100, 40, 200, 95)  # a bubble just above: the label above would cover its bottom
    x, y = area.place_label((40, 12), (100, 100, 200, 160), [above], (0, 0, 400, 300))
    assert (x, y) == (100, 163) and area._overlap((x, y, x + 40, y + 12), above) == 0  # below it


def test_a_label_takes_the_next_free_side_in_order():
    box, size, bounds = (100, 100, 200, 160), (40, 12), (0, 0, 400, 300)
    over_both_tops = (90, 80, 210, 99)
    assert area.place_label(size, box, [over_both_tops], bounds) == (100, 163)  # below, at the left
    below_too = (90, 161, 210, 180)
    assert area.place_label(size, box, [over_both_tops, below_too], bounds) == (100 - 3 - 40, 100)  # beside, left


def test_a_label_stays_on_the_picture():
    assert area.place_label((40, 12), (5, 2, 100, 60), [], (0, 0, 400, 300)) == (5, 63)  # no room above: below
    assert area.place_label((40, 12), (0, 0, 400, 300), [], (0, 0, 400, 300)) == (3, 3)  # nowhere outside: inside


def test_where_every_side_covers_something_the_least_covered_or_inside():
    box, size, bounds = (100, 100, 200, 160), (40, 12), (0, 0, 400, 300)
    walls = [(0, 0, 400, 99), (0, 161, 400, 300), (0, 0, 99, 300), (201, 0, 400, 300)]
    assert area.place_label(size, box, walls, bounds) == (103, 103)  # inside covers nothing but its own lettering
    grazed = [(0, 0, 400, 99), (0, 161, 400, 300), (0, 0, 99, 300), (201, 100, 210, 104)]
    assert area.place_label(size, box, grazed, bounds) == (203, 100)  # a corner of it covered: still outside


# ------------------------------------------------------------------ the strokes
def _items(canvas, tag):
    return [(canvas.type(i), canvas.itemcget(i, "outline" if canvas.type(i) != "line" else "fill"),
             float(canvas.itemcget(i, "width"))) for i in canvas.find_withtag(tag)]


def test_the_selection_is_two_tone_and_its_handles_edged_more(hidden_root):
    c = _sized(ImageCanvas(hidden_root))
    c.set_image(Image.new("RGB", (400, 300), "white"))
    c.draw_frame((50, 50, 150, 120), "chosen", colour=translator.FRAME_COLOUR)
    items = c.find_withtag("chosen")
    edge, frame = items[0], items[1]
    assert c.itemcget(edge, "outline") == preview.EDGE and float(c.itemcget(edge, "width")) == 4
    assert c.itemcget(frame, "outline") == translator.FRAME_COLOUR and float(c.itemcget(frame, "width")) == 2
    assert all(float(c.itemcget(i, "width")) == preview.HANDLE_EDGE_WIDTH for i in items[2:])
    assert c.find_withtag("edge") == (edge,)
    c.draw_frame((10, 10, 40, 40), "area")  # anything else keeps its look (the capture area's frame)
    assert len(c.find_withtag("area")) == 1 + 8 and not set(c.find_withtag("area")) & set(c.find_withtag("edge"))


def test_the_rotate_handle_and_a_turned_frame_are_two_tone(hidden_root):
    c = _sized(ImageCanvas(hidden_root))
    c.set_image(Image.new("RGB", (400, 300), "white"))
    corners = [(80, 90), (150, 70), (160, 110), (90, 130)]
    c.draw_turned_frame(corners, "chosen", colour=translator.FRAME_COLOUR)
    kinds = [c.type(i) for i in c.find_withtag("chosen")]
    assert kinds[:2] == ["polygon", "polygon"] and c.itemcget(c.find_withtag("chosen")[0], "outline") == preview.EDGE
    assert len(c.find_withtag("edge")) == 1


def test_found_regions_and_outlines_are_two_tone(hidden_root):
    c = _sized(ImageCanvas(hidden_root))
    c.overlay = [((50, 50, 150, 120), "#ff5050", "not text"), ((50, 130, 150, 200), "#50c878", "")]
    c.outlines = [((200, 50, 300, 100), "#ffd400", True)]
    c.set_image(Image.new("RGB", (400, 300), "white"))
    assert len(c.find_withtag("overlay-edge")) == 2 and len(c.find_withtag("outline-edge")) == 1
    assert len(c.find_withtag("outline-dashed")) == 1  # the edges are not counted as outlines
    for i in c.find_withtag("overlay-edge") + c.find_withtag("outline-edge"):
        assert c.itemcget(i, "outline") == preview.EDGE and float(c.itemcget(i, "width")) == 4
    under, over = c.find_withtag("overlay-edge")[0], c.find_withtag("overlay")[0]
    assert c.find_all().index(under) < c.find_all().index(over)  # the dark one runs under the colour


def test_a_label_leaves_the_bubble_above_it_in_view(hidden_root):
    c = _sized(ImageCanvas(hidden_root))
    above, below = (100, 40, 220, 96), (100, 100, 220, 180)  # the bubble above ends 4 px over the region
    c.overlay = [(above, "#50c878", ""), (below, "#ff5050", "not text")]
    c.set_image(Image.new("RGB", (400, 300), "white"))
    (label_box,) = c.find_withtag("overlay-label-box")
    lx0, ly0, lx1, ly1 = c.bbox(label_box)
    ax0, ay0 = c.from_image_coords(*above[:2])
    ax1, ay1 = c.from_image_coords(*above[2:])
    assert area._overlap((lx0 + 1, ly0 + 1, lx1 - 1, ly1 - 1), (ax0, ay0, ax1, ay1)) == 0
    (text,) = c.find_withtag("overlay-label")
    tx0, ty0, tx1, ty1 = c.bbox(text)
    assert lx0 <= tx0 and tx1 <= lx1 and ly0 <= ty0 and ty1 <= ly1 + 1  # the text in its box


def test_the_rectangle_a_drag_draws_is_two_tone_and_goes_as_one(hidden_root):
    a = _region((50, 50, 150, 120))
    w = Shapes(hidden_root, [a])
    w._on_press(SimpleNamespace(x=250, y=150))
    w._on_drag(SimpleNamespace(x=300, y=200))
    w._on_drag(SimpleNamespace(x=320, y=220))
    items = w.canvas.find_withtag(translator.DRAG_TAG)
    assert len(items) == 2 and w.canvas.itemcget(items[0], "outline") == preview.EDGE
    assert w.canvas.itemcget(items[1], "outline") == translator.NEW_REGION_COLOUR
    w._on_release(SimpleNamespace(x=320, y=220))
    assert not w.canvas.find_withtag(translator.DRAG_TAG) and w.added
