"""The same text is lettered once: text blocks keep out of bubbles, and of two nested regions only one stays."""

from __future__ import annotations

import cv2
import numpy as np
from test_detect import _draw_vertical

from taslation.detect import BubbleDetector, TextBlockDetector, drop_nested
from taslation.regions import TextRegion


def _bubble_and_loose_text() -> np.ndarray:
    img = np.full((700, 900, 3), 255, np.uint8)
    cv2.ellipse(img, (600, 260), (80, 130), 0, 0, 360, (0, 0, 0), 3)
    img = _draw_vertical(img, "大丈夫だよ", 605, 170, 22)
    img = _draw_vertical(img, "まだまだ", 575, 170, 22)
    img = _draw_vertical(img, "そのころ町では", 200, 120, 22)  # narration on the page, far from the bubble
    return img


def test_text_blocks_leave_a_bubbles_lettering_to_the_bubble():
    img = _bubble_and_loose_text()
    bubbles = BubbleDetector().detect(img)
    assert len(bubbles) == 1
    before = TextBlockDetector().detect(img)
    assert any(b.text_box[0] > 520 for b in before)  # the bubble's lettering is also a text block of its own
    after = TextBlockDetector().detect(img, taken=bubbles)
    assert len(after) == 1 and after[0].text_box[2] < 260  # only the narration


def _region(box, text_box, pieces, mask=None) -> TextRegion:
    x0, y0, x1, y1 = box
    m = np.full((y1 - y0, x1 - x0), 255, np.uint8) if mask is None else mask
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=m, text_box=text_box, pieces=pieces)


def _nested(extra_glyphs: bool = False, broken: bool = False):
    gray = np.full((400, 400), 255, np.uint8)
    if broken:  # an outline drawn in short strokes, and the two small circles of a thought bubble below it
        for a in range(0, 360, 10):
            cv2.ellipse(gray, (200, 200), (60, 90), 0, a, a + 7, 0, 1)
        cv2.circle(gray, (180, 305), 7, 0, 1)
        cv2.circle(gray, (170, 318), 4, 0, 1)
    else:
        cv2.ellipse(gray, (200, 200), (60, 90), 0, 0, 360, 0, 3)  # the bubble's outline: one long piece
    for y in (140, 170, 200, 230):
        gray[y : y + 12, 195 : 207] = 0  # its lettering
    if extra_glyphs:
        for y in (120, 160, 200):
            gray[y : y + 12, 262 : 274] = 0  # a column of the outer region's own, outside the bubble
    inner_mask = np.zeros((170, 110), np.uint8)
    cv2.ellipse(inner_mask, (55, 85), (52, 82), 0, 0, 360, 255, -1)
    inner = _region((145, 115, 255, 285), (195, 140, 207, 242), 4, inner_mask)
    outer = _region((120, 90, 290, 330), (138, 108, 274, 326), 8)
    return gray, outer, inner


def test_white_area_around_a_bubble_gives_way_to_it():
    gray, outer, inner = _nested()
    assert drop_nested([outer, inner], gray) == [inner]  # its mask would take the bubble's outline
    assert drop_nested([inner, outer], gray) == [inner]


def test_region_inside_a_text_of_its_own_gives_way():
    gray, outer, inner = _nested(extra_glyphs=True)
    assert drop_nested([outer, inner], gray) == [outer]  # the outer region has lettering outside the inner one


def test_separate_regions_are_kept():
    gray, outer, inner = _nested()
    other = _region((300, 20, 380, 100), (310, 30, 370, 90), 4)
    assert drop_nested([inner, other], gray) == [inner, other]


def test_broken_outline_and_its_circles_stay_and_a_missed_glyph_joins_the_bubble():
    """An outline drawn in short strokes and the circles below a thought bubble are glyph-sized marks outside the
    bubble, but little ink next to its lettering: the white area around still gives way. A glyph against the
    outline that the bubble's mask left out is taken in, so the outline is kept and all of the lettering erased."""
    gray, outer, inner = _nested(broken=True)
    for x in (175, 215):
        for y in (140, 170, 200, 230):
            gray[y : y + 12, x : x + 12] = 0  # two more columns of lettering
    inner.text_box = (175, 140, 227, 242)
    gray[122:134, 195:207] = 0  # a glyph at the top of the middle column ...
    inner.mask[122 - inner.y0 - 3 : 134 - inner.y0 + 3, 195 - inner.x0 - 3 : 207 - inner.x0 + 3] = 0  # ... the mask left out
    kept = drop_nested([outer, inner], gray)
    assert kept == [inner]
    assert inner.text_box[1] <= 122 and inner.mask[122 - inner.y0 : 134 - inner.y0, 195 - inner.x0 : 207 - inner.x0].all()
