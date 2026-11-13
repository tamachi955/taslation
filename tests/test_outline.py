"""Lettering that ran past a bubble's interior is erased with the drawing kept, and text set on a drawing gets an
outline."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from taslation.regions import TextRegion
from taslation.render import Lettering, busy_under, letter_text, erase_region, find_font, styled_font
from taslation.render.erase import stray_pieces


def stray_lettering(gray: np.ndarray, mask: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Every piece `stray_pieces` finds, as one mask (255 where a piece is)."""
    out = np.zeros(gray.shape, np.uint8)
    for piece in stray_pieces(gray, mask, box):
        out[piece] = 255
    return out


def _page() -> tuple[np.ndarray, np.ndarray]:
    """A white bubble interior (left half) beside black hair (right half), with outlined glyph strokes on the hair."""
    img = np.full((120, 160, 3), 255, np.uint8)
    img[:, 80:] = 0

    def glyph(x: int, y: int) -> None:  # a dark 12x12 stroke with a 2 px white ring, on the hair
        cv2.rectangle(img, (x - 2, y - 2), (x + 13, y + 13), (255, 255, 255), -1)
        cv2.rectangle(img, (x, y), (x + 11, y + 11), (0, 0, 0), -1)

    glyph(95, 30)
    glyph(95, 60)  # these two lie inside the text box: lettering that left the interior
    glyph(130, 90)  # this one is outside the text box: part of the drawing
    mask = np.zeros((120, 160), np.uint8)
    mask[:, :80] = 255
    return img, mask


def test_stray_lettering_is_the_glyph_sized_pieces_outside_the_mask_inside_the_box():
    img, mask = _page()
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    stray = stray_lettering(gray, mask, (20, 20, 115, 80))
    assert stray[28:44, 93:109].all() and stray[58:74, 93:109].all()  # both glyphs, rings included
    assert not stray[85:105, 125:145].any()  # the drawing outside the box
    assert not stray[:, :80].any()  # nothing inside the interior
    assert not stray_lettering(gray, mask, (20, 20, 60, 80)).any()  # a box inside the interior: nothing outside it


def test_erase_paints_the_stray_lettering_with_the_drawings_colour():
    img, mask = _page()
    r = TextRegion(0, 0, 160, 120, mask, (20, 20, 115, 80), kind="bubble")
    assert erase_region(img, r, "fill") == (255, 255, 255)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    assert gray[28:44, 93:109].max() < 40 and gray[58:74, 93:109].max() < 40  # the hair is whole again
    assert gray[88:90, 128:144].min() == 255  # the drawing's own ring stays
    img2, mask2 = _page()
    block = TextRegion(0, 0, 160, 120, mask2, (20, 20, 115, 80), kind="text")  # a text block: its mask is the lettering
    erase_region(img2, block, "fill")
    assert cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)[28:44, 93:109].max() == 255  # untouched outside its mask


def _tone(w: int = 300, h: int = 120) -> Image.Image:
    bands = (np.indices((h, w)).sum(axis=0) // 3) % 2 == 0
    return Image.fromarray(np.where(bands, 70, 190).astype(np.uint8)).convert("RGB")


def test_text_on_a_tone_gets_an_outline_and_text_on_a_flat_ground_does_not():
    tone = _tone()
    assert busy_under(tone, (0, 0, 300, 120)) and not busy_under(Image.new("RGB", (50, 50), (255, 255, 255)), (0, 0, 50, 50))
    assert not busy_under(tone, (0, 0, 1, 1))
    mask = np.full((120, 300), 255, np.uint8)
    region = TextRegion(0, 0, 300, 120, mask, (20, 20, 280, 100), kind="text")
    font = find_font().path
    size = letter_text(tone, region, "Over the tone", font, 9, 60).size
    arr = np.asarray(tone.convert("L"))
    assert size >= 9 and (arr == 255).sum() > 200 and (arr == 0).sum() > 200  # black glyphs in a white contour
    plain = _tone()
    letter_text(plain, region, "Over the tone", font, 9, 60, outline=False)
    assert (np.asarray(plain.convert("L")) == 255).sum() == 0
    flat = Image.new("RGB", (300, 120), (255, 255, 255))
    letter_text(flat, region, "On a flat ground", font, 9, 60)
    inked = np.asarray(flat.convert("L")) < 128
    assert inked.any()
    dark = Image.new("RGB", (300, 120), (0, 0, 0))
    letter_text(dark, region, "On a dark ground", font, 9, 60, background=(0, 0, 0))
    assert (np.asarray(dark.convert("L")) == 255).sum() > 200


def test_the_outline_is_drawn_around_synthetic_italic_too():
    tone = _tone(200, 80)
    styled_font(Lettering(None, italic=True), 30).draw(tone, 5, 5, "Leaning", (0, 0, 0), ((255, 255, 255), 2))
    arr = np.asarray(tone.convert("L"))
    assert (arr == 255).sum() > 100 and (arr == 0).sum() > 100
