"""A reader's rectangle (drawn, or a region resized or moved) is wiped on its paper alone when it reaches across a
bubble's outline: the outline and the drawing beyond it stay (`render.erase.within_paper`)."""

import cv2
import numpy as np

from taslation.pipeline import manual_region
from taslation.render.erase import erase_region, within_paper


def _page() -> np.ndarray:
    """A grey drawing with a white bubble (a black outline 3 px wide) that holds two columns of lettering."""
    rgb = np.full((240, 300, 3), 170, np.uint8)
    cv2.line(rgb, (0, 30), (299, 60), (20, 20, 20), 2)  # a line of the drawing
    cv2.ellipse(rgb, (150, 120), (70, 85), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(rgb, (150, 120), (70, 85), 0, 0, 360, (0, 0, 0), 3)
    for x in (130, 160):
        for y in range(70, 170, 22):
            cv2.rectangle(rgb, (x, y), (x + 12, y + 14), (0, 0, 0), -1)  # a glyph
    return rgb


def _lettering(rgb: np.ndarray) -> int:
    return int((rgb[66:190, 126:176].max(axis=2) < 100).sum())


def test_a_rectangle_across_the_outline_keeps_the_outline_and_the_drawing():
    rgb = _page()
    before = rgb.copy()
    region = manual_region(rgb, (60, 20, 240, 220))  # wider than the bubble on every side
    assert region.kind == "manual" and region.mask.min() == 255
    erase_region(rgb, region, mode="fill")
    assert _lettering(rgb) == 0  # the lettering is gone
    outline = np.zeros(rgb.shape[:2], np.uint8)
    cv2.ellipse(outline, (150, 120), (70, 85), 0, 0, 360, 255, 1)
    assert (rgb[outline > 0].max(axis=1) < 100).mean() > 0.97  # the outline is still there, all round
    beyond = np.zeros(rgb.shape[:2], np.uint8)
    cv2.ellipse(beyond, (150, 120), (76, 91), 0, 0, 360, 255, -1)
    assert np.array_equal(rgb[beyond == 0], before[beyond == 0])  # the drawing beyond the outline is untouched
    assert region.mask.min() == 0 and region.mask[100, 90] == 255  # the translation is set inside the bubble


def test_a_rectangle_inside_the_bubble_is_wiped_whole_as_before():
    rgb = _page()
    region = manual_region(rgb, (115, 60, 190, 180))
    erase_region(rgb, region, mode="fill")
    assert _lettering(rgb) == 0 and region.mask.min() == 255
    assert (rgb[60:180, 115:190] == 255).all()


def test_a_rectangle_on_the_drawing_is_wiped_whole_as_before():
    rgb = np.full((120, 200, 3), 170, np.uint8)
    for x in range(40, 160, 22):
        cv2.rectangle(rgb, (x, 50), (x + 12, 64), (0, 0, 0), -1)
    cv2.line(rgb, (0, 20), (199, 100), (20, 20, 20), 2)  # the drawing runs through the lettering
    region = manual_region(rgb, (30, 40, 170, 75))
    erase_region(rgb, region, mode="fill")
    assert region.mask.min() == 255 and int((rgb[40:75, 30:170].max(axis=2) < 100).sum()) == 0


def test_lettering_on_both_sides_of_a_line_is_wiped_as_drawn():
    rgb = np.full((120, 220, 3), 255, np.uint8)
    cv2.line(rgb, (110, 0), (110, 119), (0, 0, 0), 3)  # a panel's border between two captions
    for x in (30, 60, 140, 170):
        for y in (30, 60):
            cv2.rectangle(rgb, (x, y), (x + 12, y + 14), (0, 0, 0), -1)
    mask = np.ones((80, 190), bool)
    assert within_paper(rgb[20:100, 15:205], mask) is mask
    region = manual_region(rgb, (15, 20, 205, 100))
    erase_region(rgb, region, mode="fill")
    assert int((rgb[20:100, 15:205].max(axis=2) < 100).sum()) == 0 and region.mask.min() == 255


def test_a_dark_rectangle_is_left_to_the_erase_of_before():
    rgb = np.full((100, 160, 3), 20, np.uint8)
    cv2.rectangle(rgb, (60, 30), (72, 44), (255, 255, 255), -1)
    region = manual_region(rgb, (20, 10, 140, 80))
    assert region.kind == "manual-dark"
    erase_region(rgb, region, mode="fill", dark=True)
    assert region.mask.min() == 255 and int((rgb[10:80, 20:140].min(axis=2) > 150).sum()) == 0
