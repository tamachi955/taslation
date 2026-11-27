"""Lettering on the drawing: which regions go to the inpainting, what its mask takes, which model on which device, what
happens when one fails; and the two things that came with it: credits left alone, and no box for a missing glyph."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from taslation.config import LAMA_MODEL, Settings
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.render import artwork
from taslation.render.artwork import ArtEraser, art_mask, is_dash, on_art, ring_comp, window


def region(kind="text", box=(100, 100, 200, 300), **more):
    x0, y0, x1, y1 = box
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box=box, kind=kind, **more)


def flat(value=255, size=(500, 500)):
    return np.full((*size, 3), value, np.uint8)


def toned():
    page = flat(200)
    page[::4] = 90  # a tone: the ground is no flat colour
    return page


def ringed_glyphs(gray, x=40):
    """Dark strokes with a white ring on *gray*."""
    for y in (40, 90, 140):
        cv2.rectangle(gray, (x - 3, y - 3), (x + 23, y + 23), 255, -1)  # a 3 px white outline
        cv2.rectangle(gray, (x, y), (x + 20, y + 20), 0, 3)


# ------------------------------------------------------------------ the lettering's mask
def test_a_glyph_ringed_by_white_is_lettering_even_on_black():
    gray = np.zeros((200, 100), np.uint8)
    ringed_glyphs(gray)
    mask = ring_comp(gray)
    assert mask[50, 40] and mask[100, 40]  # a stroke
    assert mask[38, 38]  # its ring
    assert not mask[100, 5]  # the black around stays


def test_a_dark_area_with_no_ring_is_no_lettering():
    assert not ring_comp(np.full((200, 100), 30, np.uint8)).any()


def test_a_piece_may_be_as_wide_as_its_column_but_no_wider():
    gray = np.full((120, 300), 255, np.uint8)
    gray[50:60, 20:170] = 0  # 150 px: over 1.15 x 120 and no dash in line with a glyph
    assert not ring_comp(gray)[55, 80]
    gray = np.full((200, 300), 255, np.uint8)
    gray[50:60, 20:170] = 0  # the same on a box whose short side is 200: a wide glyph
    assert ring_comp(gray)[55, 80]


def _stats(gray):
    return cv2.connectedComponentsWithStats((gray < 150).astype(np.uint8), connectivity=8)[2]


def test_a_long_dash_in_line_with_a_glyph_is_lettering():
    gray = np.full((400, 200), 255, np.uint8)
    gray[30:60, 90:120] = 0  # the glyph
    gray[70:350, 100:106] = 0  # the dash below it
    st = _stats(gray)
    assert is_dash(st, 2, 200, 400) or is_dash(st, 1, 200, 400)
    assert ring_comp(gray)[200, 102]


def test_a_line_that_touches_the_boxs_edge_or_stands_alone_is_the_drawing():
    alone = np.full((400, 200), 255, np.uint8)
    alone[70:350, 100:106] = 0
    assert not is_dash(_stats(alone), 1, 200, 400)
    edge = np.full((400, 200), 255, np.uint8)
    edge[30:60, 90:120] = 0
    edge[70:400, 100:106] = 0
    st = _stats(edge)
    assert not any(is_dash(st, i, 200, 400) for i in (1, 2) if st[i][3] > 100)


def test_light_lettering_ringed_by_dark_is_found_on_the_negative():
    page = flat(255)
    gray = np.zeros((200, 100), np.uint8)
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([255 - gray] * 3)
    mask = art_mask(page, region("text-dark", (100, 100, 200, 300)))
    assert mask is not None and mask[150, 140]


def test_a_box_with_too_little_lettering_is_left_alone():
    page = flat(120)
    assert art_mask(page, region()) is None


def test_the_mask_is_of_the_lettering_box_where_there_is_one():
    page = flat(60)  # outlined lettering on dark art
    gray = np.full((200, 100), 60, np.uint8)
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    r = region("text", (50, 50, 400, 400), letter_box=(100, 100, 200, 300))
    mask = art_mask(page, r)
    assert not mask[:90].any() and not mask[310:].any()


def outlined_on_texture(ring=6):
    """Three glyphs with a white ring of *ring* px on a drawing's texture, and a text block's box drawn round their
    strokes alone (the ring lies past it)."""
    page = drawn()
    for y in (140, 190, 240):
        cv2.rectangle(page, (140 - ring, y - ring), (160 + ring, y + 20 + ring), (255, 255, 255), -1)
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 3)
    return page, region("text", (130, 130, 170, 270), letter_box=(140, 140, 161, 261))


def test_the_hole_takes_the_white_ring_past_a_box_drawn_round_the_strokes():
    """A text block's box holds the strokes and not their ring: the ring is taken all the same, with `GROW` px more,
    so that no white ring is left round the hole for LaMa to draw the glyphs back from; the drawing further off
    stays."""
    page, r = outlined_on_texture(ring=6)
    mask = art_mask(page, r)
    assert mask is not None
    assert mask[150, 134:166].all() and mask[134, 150] and mask[266, 150]  # the ring, past the box on every side
    assert mask[150, 134 - artwork.GROW] and mask[266 + artwork.GROW, 150]  # and a little more
    assert not mask[150, :120].any() and not mask[150, 180:].any() and not mask[:120].any()  # the drawing beyond


def test_a_plain_ground_is_painted_ring_and_all_before_the_paper_fill(tmp_path):
    """Outlined lettering on a flat grey with the panel's lines round it: no model, the hole (strokes and white ring)
    painted the grey of the ground, and the paper fill called for whatever is left."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = flat(120)
    page[[88, 90, 92, 308, 310, 312], :] = 40  # lines of the panel round the box: it is on the art
    page[:, [88, 90, 92, 208, 210, 212]] = 40
    for y in (140, 190, 240):
        cv2.rectangle(page, (134, y - 6), (166, y + 26), (255, 255, 255), -1)
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 3)
    r = region("text", (100, 100, 200, 300), letter_box=(140, 140, 161, 261))
    eraser.erase(page, r)
    assert eraser.counts["ground"] == 1 and eraser._model.runs == 0 and calls
    assert np.abs(page[130:275, 128:172].astype(int) - 120).max() <= 2  # no ring, no stroke
    assert (page[90, :] == 40).all()  # the panel's lines stay


def test_outlined_lettering_on_a_flat_ground_has_its_ring_painted_that_ground(tmp_path):
    """A flat grey ground is not the art (no model), but the white ring of outlined lettering on it is painted grey
    before the paper fill, which took a thick ring for paper and left it; lettering on white paper stays the fill's."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = flat(120)
    for y in (140, 190, 240):
        cv2.rectangle(page, (134, y - 6), (166, y + 26), (255, 255, 255), -1)
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 3)
    r = region("text", (100, 100, 200, 300), letter_box=(130, 130, 171, 271))
    assert not on_art(page, r)
    eraser.erase(page, r)
    assert eraser.counts["plain"] == 1 and eraser._model.runs == 0 and len(calls) == 1
    assert np.abs(page[125:280, 125:176].astype(int) - 120).max() <= 2
    white = flat(255)
    cv2.rectangle(white, (140, 140), (160, 160), (0, 0, 0), 3)
    eraser.erase(white, r)
    assert eraser._model.runs == 0 and len(calls) == 2 and (white[:130] == 255).all()


def test_a_shaded_ground_under_the_lettering_is_painted_as_a_shading():
    """`fill_ground` paints the hole with the surface fitted to the band round it: a gradient goes on through it, it is
    not one colour (what the paper fill would paint); `paste` puts the model's pixels on the hole alone."""
    ramp = np.tile(np.linspace(80, 220, 400).round().astype(np.uint8), (300, 1))
    page = np.dstack([ramp] * 3)
    truth = page.copy()
    hole = np.zeros(page.shape[:2], bool)
    hole[100:200, 120:280] = True
    page[hole] = 0
    assert artwork.plain_ground(page, hole) and artwork.fill_ground(page, hole)
    assert np.abs(page.astype(int) - truth).max() <= 2
    where, pixels = artwork.paste(page, np.zeros_like(page), hole)
    assert (where == hole).all() and pixels.shape == (int(hole.sum()), 3)


def test_the_ground_beyond_the_ring_tells_art_from_paper(tmp_path):
    """Outlined lettering on a drawing with a box round its strokes alone: the ground right round the hole is the
    drawing past the ring, so the model takes it (within the box, the ring alone passed for white paper)."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page, r = outlined_on_texture(ring=6)
    eraser.erase(page, r)
    assert eraser.counts["art"] == 1 and not calls


def test_the_window_is_512_more_for_a_larger_box_and_stays_on_the_page():
    assert window((1000, 800), 100, 100, 50, 50) == (0, 0, 512, 512)
    assert window((1000, 800), 700, 900, 50, 50) == (288, 488, 800, 1000)
    x0, y0, x1, y1 = window((1000, 800), 100, 100, 700, 50)
    assert y1 - y0 == 764 and x1 - x0 == 512


# ------------------------------------------------------------------ which regions
@pytest.mark.parametrize("kind", ["text", "text-on-page", "text-dark", "text-on-dark"])
def test_lettering_on_a_tone_goes_to_the_model_on_flat_ground_it_does_not(kind):
    assert on_art(toned(), region(kind))
    assert not on_art(flat(), region(kind))


@pytest.mark.parametrize("kind", ["bubble", "dark-bubble"])
def test_bubbles_stay_on_paper_fill_whatever_lies_round_them(kind):
    assert not on_art(toned(), region(kind))
    assert not on_art(toned(), region(kind, tier=1))


@pytest.mark.parametrize("ground, expected", [(toned, True), (flat, True)])
def test_a_model_bubble_that_could_not_be_closed_always_goes_to_the_model(ground, expected):
    assert on_art(ground(), region("bubble", tier=3)) is expected


def test_a_model_bubble_on_a_white_area_goes_by_its_ground():
    assert on_art(toned(), region("bubble", tier=2))
    assert not on_art(flat(), region("bubble", tier=2))


def narrow_bubble_on_hatching():
    """A tall narrow white bubble (a 3 px outline) on hatching, and a column of glyphs nearly as wide as it: the ring
    round the column's box crosses the outline onto the hatching. The column's box."""
    page = flat(255, (600, 400))
    page[::5] = 60
    cv2.ellipse(page, (200, 300), (34, 150), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (200, 300), (34, 150), 0, 0, 360, (0, 0, 0), 3)
    for y in range(190, 390, 26):
        cv2.rectangle(page, (182, y), (218, y + 18), (0, 0, 0), 4)
    return page, (182, 190, 219, 391)


@pytest.mark.parametrize("kind, tier", [("text-on-page", 0), ("text", 0), ("bubble", 2), ("bubble", 3)])
def test_lettering_on_paper_closed_all_round_stays_with_the_paper_fill(kind, tier):
    """Whatever the detectors called it (text on the page, a model bubble they could not shape), a column in a tall
    narrow bubble is judged on the bubble's paper, not on the hatching its box's ring reaches past the outline: it went
    to the inpainting, which left grey ghosts of the glyphs on the paper."""
    page, box = narrow_bubble_on_hatching()
    found = artwork.closed_interior(page, box)
    assert found is not None
    (wx0, wy0, _wx1, _wy1), inside, _paper = found
    assert inside[300 - wy0, 170 - wx0] and not inside[300 - wy0, 100 - wx0]  # the bubble's paper, not the page's
    assert not on_art(page, region(kind, box, tier=tier, from_model=True))


def test_white_rings_closed_on_the_drawing_are_no_paper():
    """Outlined lettering on a tone: its white rings close on the tone, but hold no paper clear of the ink - it stays
    on the art."""
    page = toned()
    gray = np.ascontiguousarray(page[..., 0])
    ringed_glyphs(gray, 140)
    page = np.repeat(gray[..., None], 3, axis=2)
    box = (137, 37, 164, 164)
    assert artwork.closed_interior(page, box) is None
    assert on_art(page, region("text-on-page", box))


def bubble_with_column(through=False, touching=False, rim=False):
    """A white bubble closed all round, a column of seven glyphs in it and the reading's characters, as a model bubble
    with no shape of its own (tier 3): *through*, a line of the drawing seen through the bubble crosses the column and
    ends inside it (hair); *touching*, the last glyph is joined to the outline; *rim*, the bubble lies on a dark ground
    with a white rim round its outline."""
    page = flat(40 if rim else 255, (600, 400))
    if not rim:
        page[::5] = 60  # a hatching round the bubble
    if rim:
        cv2.ellipse(page, (200, 290), (68, 123), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (200, 290), (60, 115), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (200, 290), (60, 115), 0, 0, 360, (0, 0, 0), 3)
    column = [(188, y, 212, y + 24) for y in range(190, 380, 30)]
    for x0, y0, x1, y1 in column:
        cv2.rectangle(page, (x0 + 2, y0 + 2), (x1 - 3, y1 - 3), (0, 0, 0), 3)
    if through:
        cv2.line(page, (150, 250), (250, 320), (0, 0, 0), 2)
    if touching:
        cv2.line(page, (200, 391), (200, 406), (0, 0, 0), 2)
    r = region("bubble", (182, 186, 218, 398), tier=3, from_model=True, glyph=24.0)
    r.char_boxes = column
    return page, r


@pytest.mark.parametrize("touching, rim", [(False, False), (True, False), (False, True)])
def test_a_white_bubble_the_detectors_could_not_shape_stays_with_the_paper_fill(touching, rim):
    """Paper closed round the lettering of a model bubble with no shape of its own is the bubble's: no ink joined to
    its lettering runs on into it - a glyph joined to the outline, a white rim round the outline, are its edge."""
    page, r = bubble_with_column(touching=touching, rim=rim)
    found = artwork.closed_interior(page, artwork.box_of(page, r))
    assert found is not None and not artwork.see_through(page, r, found)
    assert not on_art(page, r)


def test_a_model_bubble_the_drawing_shows_through_is_on_the_art():
    """A bubble drawn see-through over the drawing: closed all round, but a line of the drawing crosses its lettering
    and runs on inside its paper (hair, a hand, a gun) - lettering on the drawing, whose lines the paper fill cut, not
    closed paper (it goes to the inpainting where that runs)."""
    page, r = bubble_with_column(through=True)
    found = artwork.closed_interior(page, artwork.box_of(page, r))
    assert found is not None and artwork.see_through(page, r, found)
    assert on_art(page, r)
    r.char_boxes = []
    assert not artwork.see_through(page, r, found)  # (without the reading's characters: no)


def joined_bubbles(neck=True):
    """Two white bubbles joined into one on a hatching, the line where they join drawn part of the way across
    (*neck*: the paper runs on between them; else the line closes the small one), a column of lettering in the small
    one: its paper reaches past the window three times its box's size round it, into the large bubble."""
    page = flat(255, (800, 1000))
    page[::5] = 60  # a hatching round the bubbles
    for centre, axes in (((250, 400), (40, 90)), ((400, 400), (120, 110))):
        cv2.ellipse(page, centre, axes, 0, 0, 360, (0, 0, 0), 3)
    for centre, axes in (((250, 400), (37, 87)), ((400, 400), (117, 107))):
        cv2.ellipse(page, centre, axes, 0, 0, 360, (255, 255, 255), -1)
    if neck:
        cv2.line(page, (276, 340), (276, 385), (0, 0, 0), 3)  # the line where they join, open from y 385 to 415
        cv2.line(page, (276, 415), (276, 460), (0, 0, 0), 3)
    else:
        cv2.line(page, (276, 325), (276, 475), (0, 0, 0), 3)
    for y in range(340, 460, 30):
        cv2.rectangle(page, (240, y + 2), (259, y + 21), (0, 0, 0), 3)
    return page, (234, 336, 266, 462)


@pytest.mark.parametrize("neck", [True, False])
def test_lettering_in_one_of_two_joined_bubbles_is_on_their_paper(neck):
    """Lettering in the smaller of two bubbles joined into one: their paper runs past the window three times the
    lettering box's size round it (`CLOSED_REACH`), where it was no closed paper - the ring round the box reached the
    line where they join, the lettering went to the inpainting, and its hole took that line. The paper is looked for
    again in a wider window (`CLOSED_WIDE`): closed paper, the paper fill's."""
    page, box = joined_bubbles(neck)
    found = artwork.closed_interior(page, box)
    assert found is not None
    (wx0, wy0, wx1, _wy1), inside, _paper = found
    assert inside[395 - wy0, 225 - wx0] and not inside[202 - wy0, 250 - wx0]  # the bubbles' paper, not the page's
    assert (wx1 > 450 and inside[395 - wy0, 450 - wx0]) if neck else wx1 < 450  # (closed by the line: as before)
    assert not on_art(page, region("text-on-page", box))  # (the ring round its box reaches the line and the hatching)


def test_paper_open_to_the_page_past_the_wider_window_is_no_closed_paper():
    """Paper that runs on past the wider window too (out to the page's white ground) is no closed paper."""
    page, box = joined_bubbles()
    page[380:420, 400:1000] = 255  # the large bubble opened to the page's edge
    assert artwork.closed_interior(page, box) is None


@pytest.mark.parametrize("kind", ["manual", "manual-dark"])
def test_a_readers_rectangle_goes_by_its_ground_as_a_detected_region(kind):
    """(tests/test_drawn_on_art.py: in a bubble, out of one, on a flat box.)"""
    assert on_art(toned(), region(kind))
    assert not on_art(flat(), region(kind))


def test_a_cached_region_stays_with_the_paper_fill():
    assert not on_art(toned(), region("cached"))


# ------------------------------------------------------------------ the model's handling
class FakeModel:
    """Fills every hole with grey, or fails."""

    def __init__(self, fails=False, device="cpu"):
        self.fails = fails
        self.runs = 0
        self.device = device

    def run(self, image, mask):
        self.runs += 1
        if self.fails:
            raise RuntimeError("no memory")
        out = image.copy()
        out[mask] = 128
        return out


def drawn(size=(500, 500)):
    """A ground with a drawing's texture: no colour, no shading, no lettering."""
    noise = np.random.default_rng(7).integers(150, 256, size, dtype=np.uint8)
    return np.dstack([cv2.GaussianBlur(noise, (0, 0), 1.0)] * 3)


def lettered(ground=None):
    """Outlined lettering on *ground* (by default a drawing's texture) in the box (100, 100, 200, 300)."""
    page = drawn() if ground is None else ground
    gray = np.ascontiguousarray(page[100:300, 100:200, 0])
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    return page


def fallback_calls():
    calls = []

    def erase(image, region, *args):
        calls.append(args)
        return (1, 2, 3)
    return calls, erase


def test_the_model_fills_the_lettering_only(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = lettered()
    before = page.copy()
    bg = eraser.erase(page, region())
    assert not calls and eraser.counts["art"] == 1 and len(bg) == 3
    changed = (page != before).any(axis=2)
    assert changed[100:300, 100:200].any() and not changed[:90].any() and not changed[:, :90].any()
    assert (page[changed] == 128).all()


def test_a_region_on_flat_ground_goes_to_the_app_with_all_it_was_given(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    assert eraser.erase(flat(), region(), "fill", 225, 140, False) == (1, 2, 3)
    assert calls == [("fill", 225, 140, False)] and eraser._model.runs == 0


@pytest.mark.parametrize("ground", ["black", "white", "gradient"])
def test_lettering_on_a_flat_or_shaded_ground_goes_to_the_app(tmp_path, ground):
    """A black panel, a white one, a smooth gradient: the paper fill paints what lay there, the model would blotch it."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = {"black": flat(0), "white": flat(255),
            "gradient": np.repeat(np.linspace(40, 220, 500).astype(np.uint8)[:, None, None], 500, axis=1).repeat(3, axis=2)}[ground]
    page[[88, 90, 92, 308, 310, 312], :] = 128  # lines of the panel's drawing round the box: it is on the art
    page[:, [88, 90, 92, 208, 210, 212]] = 128
    page = lettered(page)
    # (on the white panel the lines close a white box round the lettering: on paper as such, `closed_interior`)
    assert on_art(page, region()) is (ground != "white")
    eraser.erase(page, region())
    assert calls and eraser.counts["ground" if ground != "white" else "plain"] == 1 and eraser._model.runs == 0


def test_too_little_lettering_goes_to_the_app(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = np.repeat(np.linspace(160, 250, 500).astype(np.uint8)[None, :, None], 500, axis=0).repeat(3, axis=2)
    eraser.erase(page, region())
    assert calls and eraser.counts["weak"] == 1


def test_a_page_too_small_for_the_models_goes_to_the_app(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = lettered()[:230]
    eraser.erase(page, region("text", (100, 20, 200, 200)))
    assert calls and eraser._model.runs == 0 and not eraser.failed


def test_no_model_at_all_leaves_the_page_to_the_app(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    assert eraser.erase(lettered(), region()) == (1, 2, 3)
    assert eraser.failed and not eraser.ready()


def test_a_failure_on_the_gpu_moves_to_the_cpu(tmp_path, monkeypatch):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel(fails=True, device="cuda")
    devices = []

    def load(device):
        devices.append(device)
        eraser._model = FakeModel()

    monkeypatch.setattr(eraser, "_load", load)
    eraser.erase(lettered(), region())
    assert devices == ["cpu"] and not calls and eraser.counts["art"] == 1 and not eraser.failed


@pytest.fixture
def cache(monkeypatch):
    """torch's caching allocator as a stand-in: *reserved* and *allocated* MiB, and how often it was emptied."""
    import torch

    state = SimpleNamespace(initialized=True, reserved=1000, allocated=800, emptied=0)
    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: state.initialized)
    monkeypatch.setattr(torch.cuda, "memory_reserved", lambda *a: state.reserved * 2 ** 20)
    monkeypatch.setattr(torch.cuda, "memory_allocated", lambda *a: state.allocated * 2 ** 20)

    def empty():
        state.emptied += 1
        state.reserved = state.allocated
    monkeypatch.setattr(torch.cuda, "empty_cache", empty)
    return state


def test_more_than_128_mib_left_idle_is_given_back(cache):
    assert artwork.give_back_idle() and cache.emptied == 1 and cache.reserved == 800  # 200 idle
    cache.reserved = 800 + artwork.IDLE_MIB
    assert not artwork.give_back_idle() and cache.emptied == 1  # (128: kept)
    cache.reserved, cache.initialized = 2000, False
    assert not artwork.give_back_idle() and cache.emptied == 1  # (no CUDA in use: nothing asked)


def test_a_window_filled_on_the_gpu_gives_its_idle_memory_back_and_one_on_the_cpu_does_not(tmp_path, cache):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel(device="cuda")
    eraser.erase(lettered(), region())
    assert eraser.counts["art"] == 1 and cache.emptied == 1
    cache.reserved = 1000
    eraser._model = FakeModel(device="cpu")
    eraser.erase(lettered(), region())
    assert eraser.counts["art"] == 2 and cache.emptied == 1 and not calls


def test_a_cache_that_cannot_be_read_leaves_the_window_filled(tmp_path, monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: True)
    monkeypatch.setattr(torch.cuda, "memory_reserved", lambda *a: 1 / 0)
    assert not artwork.give_back_idle()
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel(device="cuda")
    eraser.erase(lettered(), region())
    assert eraser.counts["art"] == 1 and not calls and not eraser.failed


def test_a_failure_on_the_cpu_gives_up_for_good(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    model = eraser._model = FakeModel(fails=True)
    eraser.erase(lettered(), region())
    assert calls and eraser.failed and eraser._model is None  # (and its memory given back)
    eraser.erase(lettered(), region())
    assert len(calls) == 2 and model.runs == 1


def test_release_gives_the_model_back_and_the_next_erase_loads_it(tmp_path, monkeypatch):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    eraser.release()
    assert eraser._model is None
    eraser.release()
    loaded = []
    monkeypatch.setattr(eraser, "_load", lambda device: (loaded.append(device), setattr(eraser, "_model", FakeModel())))
    eraser.erase(lettered(), region())
    assert loaded == [ArtEraser._device()]  # the device torch has


# ------------------------------------------------------------------ the rule: where the erase runs (art_erase)
def _weights(folder: Path) -> Path:
    """LaMa's weights as a file that only exists (nothing in this part of the tests loads it)."""
    (folder / LAMA_MODEL.dirname).mkdir(parents=True, exist_ok=True)
    (folder / LAMA_MODEL.dirname / LAMA_MODEL.installed[0]).write_bytes(b"x")
    return folder


@pytest.fixture
def torch_says(monkeypatch):
    """Stands in for torch's answer to whether it has a CUDA GPU (`torch.cuda.is_available`), counting the asks; the
    rule's own memory of it starts empty (the suite's fixture already set it so for a ``page_models`` test)."""
    import torch

    asked = []

    def answer(value: bool) -> list:
        def is_available():
            asked.append(1)
            return value

        monkeypatch.setattr(torch.cuda, "is_available", is_available)
        monkeypatch.setattr(artwork, "_cuda", None)
        return asked
    return answer


@pytest.mark.page_models
@pytest.mark.parametrize("gpu", [True, False], ids=["gpu", "no-gpu"])
def test_auto_runs_lama_only_with_a_gpu_lama_always_and_off_never(tmp_path, torch_says, gpu):
    asked = torch_says(gpu)
    _weights(tmp_path)
    assert artwork.available(tmp_path, "auto") is gpu and artwork.available(tmp_path) is gpu  # ("auto": the default)
    assert artwork.available(tmp_path, "lama") and not artwork.available(tmp_path, "off")
    assert artwork.runs_here("auto") is gpu and artwork.runs_here("lama") and not artwork.runs_here("off")
    assert len(asked) == 1  # torch asked once, and only for "auto"
    assert artwork.available(tmp_path, "auto", cuda=not gpu) is (not gpu)  # (a caller that knows says so)
    assert not (tmp_path / LAMA_MODEL.dirname / LAMA_MODEL.files[0][0]).exists()  # the checkpoint is not needed


@pytest.mark.page_models
@pytest.mark.parametrize("gpu", [True, False], ids=["gpu", "no-gpu"])
def test_without_lamas_weights_nothing_runs_and_torch_is_not_asked(tmp_path, torch_says, gpu):
    asked = torch_says(gpu)
    assert not any(artwork.available(tmp_path, setting) for setting in artwork.ART_ERASES)
    assert asked == []


@pytest.mark.page_models
def test_off_and_lama_and_the_settings_themselves_never_ask_torch(tmp_path, torch_says):
    asked = torch_says(True)
    assert artwork.runs_here("lama") and not artwork.runs_here("off")
    s = Settings(state_dir=tmp_path)
    s.validate()
    (tmp_path / "taslation.toml").write_text('art_erase = "auto"\n', encoding="utf-8")
    assert Settings.from_toml(tmp_path / "taslation.toml").art_erase == "auto" == s.art_erase
    assert asked == []


@pytest.mark.page_models
def test_a_torch_that_cannot_say_counts_as_no_gpu(torch_says, monkeypatch):
    import torch

    torch_says(True)

    def broken():
        raise RuntimeError("no driver")

    monkeypatch.setattr(torch.cuda, "is_available", broken)
    assert not artwork.has_cuda() and not artwork.runs_here("auto")


def _art_page() -> tuple[np.ndarray, TextRegion]:
    """Lettering on a tone (a region `on_art`), as LaMa would take it out if it ran."""
    page = lettered()
    r = region()
    assert on_art(page, r) and art_mask(page, r) is not None
    return page, r


@pytest.mark.page_models
def test_the_default_on_a_computer_without_a_gpu_letters_byte_for_byte_as_off(tmp_path, torch_says, monkeypatch,
                                                                             sample_page):
    """Weights installed and every page model allowed to come, but no CUDA: the default settings make no eraser and no
    layout model, never load LaMa, and letter the page exactly as art_erase "off" does."""
    from helpers import EN_TEXTS, FakeOcr

    from taslation.config import PAGE_MODELS
    from taslation.translate import DictTranslator

    torch_says(False)
    for model in PAGE_MODELS:  # (the layout model too: "auto" for it would follow the erase)
        for name in model.installed or [n for n, _sha in model.files]:
            (tmp_path / "models" / model.dirname).mkdir(parents=True, exist_ok=True)
            (tmp_path / "models" / model.dirname / name).write_bytes(b"x")
    monkeypatch.setattr(ArtEraser, "_load", lambda self, device: pytest.fail("LaMa was loaded"))
    out = {}
    for name, extra in (("default", {}), ("off", {"art_erase": "off"}), ("auto, auto", {"detect_model": "auto"}),
                        ("the default before 0.2.0", {"detect_model": "off"})):
        s = Settings(state_dir=tmp_path / name, models_dir=tmp_path / "models", **extra)
        p = Pipeline(s, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None)
        assert p.art_eraser is None and p.layout is None and p.gpu_releases == [], name
        page, r = _art_page()
        p.letter_region(page, r, "Hello")
        out[name] = (page.tobytes(), np.asarray(p.process(sample_page, use_cache=False).image).tobytes())
    assert out["default"] == out["off"] == out["auto, auto"] == out["the default before 0.2.0"]


@pytest.mark.page_models
def test_the_default_where_the_page_models_were_declined_letters_byte_for_byte_as_before(tmp_path, torch_says,
                                                                                         monkeypatch, sample_page):
    """A computer with a GPU where the person answered no to the two page models at the installation: the default
    settings make neither model and letter the page exactly as the defaults before 0.2.0 (detect_model "off")."""
    from helpers import EN_TEXTS, FakeOcr

    from taslation.translate import DictTranslator

    torch_says(True)
    monkeypatch.setattr(ArtEraser, "_load", lambda self, device: pytest.fail("LaMa was loaded"))
    out = {}
    for name, extra in (("default", {}), ("the default before 0.2.0", {"detect_model": "off"})):
        s = Settings(state_dir=tmp_path / name, models_dir=tmp_path / "models", **extra)
        p = Pipeline(s, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None)
        assert p.art_eraser is None and p.layout is None and p.gpu_releases == [], name
        page, r = _art_page()
        p.letter_region(page, r, "Hello")
        out[name] = (page.tobytes(), np.asarray(p.process(sample_page, use_cache=False).image).tobytes())
    assert out["default"] == out["the default before 0.2.0"]


def test_the_network_has_the_checkpoints_tensors_and_keeps_the_size_it_was_given():
    import torch

    from taslation.render import lama

    net = lama.Lama()
    names = {k for k in net.state_dict() if not k.endswith("num_batches_tracked")}
    assert len(names) == 837 and "model.5.conv1.ffc.convg2g.fu.conv_layer.weight" in names
    assert tuple(net.state_dict()["model.4.ffc.convl2g.weight"].shape) == (384, 256, 3, 3)
    model = lama.LamaInpainter.__new__(lama.LamaInpainter)
    model.device, model.net = "cpu", net.eval()
    image = np.full((37, 53, 3), 128, np.uint8)
    out = model.run(image, np.zeros((37, 53), bool))
    assert out.shape == image.shape and out.dtype == np.uint8
    assert torch.get_num_threads() >= 1


def test_the_fourier_unit_gives_back_what_a_neutral_spectral_step_leaves_alone():
    """With the spectral convolution set to pass its input through and nothing clipped, the unit is the identity: the
    real inverse FFT undoes the forward one (the network as trained, not an export's variant)."""
    import torch

    from taslation.render.lama import FourierUnit

    unit = FourierUnit(2).eval()
    with torch.no_grad():
        unit.conv_layer.weight.copy_(torch.eye(4)[:, :, None, None])
        unit.bn.running_mean.zero_(); unit.bn.running_var.fill_(1 - 1e-5); unit.bn.weight.fill_(1); unit.bn.bias.zero_()
        unit.relu = torch.nn.Identity()
        x = torch.randn(1, 2, 8, 6)
        assert torch.allclose(unit(x), x, atol=1e-5)


def test_weights_of_another_network_are_refused(tmp_path):
    import torch
    from safetensors.torch import save_file

    from taslation.render import lama

    save_file({"model.1.ffc.convl2l.weight": torch.zeros(64, 4, 7, 7)}, str(tmp_path / "w.safetensors"))
    with pytest.raises(ValueError, match="not this network"):
        lama.load(tmp_path / "w.safetensors", "cpu")


# ------------------------------------------------------------------ in the pipeline
def test_an_early_look_skips_the_model_and_the_finished_page_does_not(settings):
    p = Pipeline(settings, translator=None, cache=None)
    used = []
    p.art_eraser = SimpleNamespace(erase=lambda *a: used.append("model") or (255, 255, 255), release=lambda: None)
    page = flat(255, (400, 400))
    r = region("text", (50, 50, 150, 250))
    p.letter_region(page, r, "Hello", quick=True)
    assert used == []
    p.letter_region(page, r, "Hello")
    assert used == ["model"]


def test_classic_stays_byte_for_byte_with_the_models_folder_full(settings, monkeypatch):
    monkeypatch.setattr(artwork, "available", lambda *a: True)
    settings.erase_mode = "classic"
    assert Pipeline(settings, translator=None, cache=None).art_eraser is None


# ------------------------------------------------------------------ the real model
REAL = Settings()
needs_lama = pytest.mark.skipif(bool(LAMA_MODEL.missing(REAL.models_dir)), reason="LaMa not set up")


@needs_lama
def test_the_real_model_takes_the_lettering_off_a_tone():
    page = lettered()
    eraser = ArtEraser(REAL.models_dir, "lama")
    before = page.copy()
    eraser.erase(page, region())
    eraser.release()
    assert eraser.counts["art"] == 1 and not eraser.failed
    assert (page != before).any()


@needs_lama
def test_lama_under_the_network_guard_and_without_onnx_runtime():
    """Loading and running LaMa try nothing online, and nothing imports ONNX Runtime."""
    code = """
import sys
from taslation import netguard
netguard.install()
import numpy as np
from taslation.config import Settings
from taslation.render.artwork import ArtEraser
e = ArtEraser(Settings().models_dir, "lama")
e._load("cpu")
out = e._model.run(np.full((256, 256, 3), 200, np.uint8), np.zeros((256, 256), bool))
assert out.shape == (256, 256, 3)
assert not netguard._state.blocked, netguard._state.blocked
assert "onnxruntime" not in sys.modules and "onnx" not in sys.modules
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]


def _unclosed_bubble(ground):
    """Glyphs in a model bubble whose thin outline is open at the bottom (tier 3: the detectors could not close it)."""
    page = ground
    cv2.ellipse(page, (150, 190), (60, 110), 0, 200, 340 + 180, (60, 60, 60), 1)  # thin, grey, with a gap
    for y in (110, 150, 190, 230):
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 3)
    return page


def test_a_model_bubble_with_paper_under_its_lettering_goes_to_the_paper_fill(tmp_path):
    """An unclosed model bubble whose ground between the strokes is paper: its open outline was what the detectors
    missed, and the paper fill paints the lettering alone; on a drawing's texture it is still the model's."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    r = region("bubble", (120, 100, 180, 260), tier=3, from_model=True)
    paper = _unclosed_bubble(flat(255))
    assert artwork.on_paper(paper, r)
    eraser.erase(paper, r)
    assert calls and eraser.counts["ground"] == 1 and eraser._model.runs == 0
    assert not artwork.on_paper(_unclosed_bubble(drawn()), r)
    assert not artwork.on_paper(paper, region("bubble", (120, 100, 180, 260), tier=0, from_model=True))


def _in_a_bubble_on_a_tone():
    """A white bubble with a black outline on a tone, outlined lettering inside it; the lettering box (125, 125, 175,
    275) round it, the bubble's inside (63, 63, 297, 397)."""
    page = toned()
    cv2.rectangle(page, (60, 60), (300, 400), (255, 255, 255), -1)
    cv2.rectangle(page, (60, 60), (300, 400), (0, 0, 0), 3)
    gray = np.ascontiguousarray(page[100:300, 100:200, 0])
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    return page


def model_text(box, letter_box, adopted=True):
    """A layout model's text region with the text box *box*, shaped (tier 0) by a classical region round *letter_box*
    (or by none)."""
    own = region("text-on-page", letter_box) if adopted else None
    return region("text-on-page", box, from_model=True, tier=0, letter_box=letter_box, adopted=own)


def test_a_model_region_shaped_by_a_classical_one_is_judged_on_that_one_s_lettering_box(tmp_path):
    """Lettering on a bubble's white paper, whose model text box reaches the bubble's outline: the ring round that box
    is not flat, the one round the classical region's lettering box is, and the paper fill takes it as it did without
    the model; the hole would still take in the model's box."""
    page = _in_a_bubble_on_a_tone()
    r = model_text((64, 64, 296, 396), (125, 125, 175, 275))
    judged = artwork.as_judged(r)
    assert artwork.box_of(page, judged) == (125, 125, 175, 275) and artwork.box_of(page, r) == (64, 64, 296, 396)
    assert r.from_model and not on_art(page, r)
    # judged on the union, whose ring crosses the outline onto the tone: on the bubble's paper all the same (the ring
    # taken inside the paper closed round it, `closed_interior`)
    assert not on_art(page, model_text((64, 64, 296, 396), (125, 125, 175, 275), adopted=False))
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    eraser.erase(page, r)
    assert calls and eraser._model.runs == 0 and not eraser.counts["art"]


def test_a_model_region_shaped_by_a_classical_one_takes_the_paper_fill_where_its_own_lettering_lies_on_paper(tmp_path):
    """Its own ring reaches a small bubble's outline (on the art as it was without the model, before the ring was taken
    inside the paper closed round the lettering, `closed_interior`); the ground right round its own lettering's hole
    is the bubble's paper, and that hole alone is painted. The lettering followed in the model's larger text box took
    the small outline for a stroke ringed by white."""
    page = _in_a_bubble_on_a_tone()
    cv2.rectangle(page, (114, 114), (186, 286), (0, 0, 0), 2)  # a small bubble's outline, 10 px from the lettering
    r = model_text((64, 64, 296, 396), (125, 125, 175, 275))
    hole = art_mask(page, artwork.as_judged(r))
    assert not on_art(page, r) and artwork.plain_ground(page, hole) and not hole[200, 114]
    assert art_mask(page, r)[200, 114]
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    eraser.erase(page, r)
    assert calls and eraser._model.runs == 0 and eraser.counts["plain"] == 1
    assert (page[200, 114] == 0).all() and (page[150, 140] == 255).all()  # the outline stays, a stroke is painted


def test_a_model_region_shaped_by_a_classical_one_on_the_art_still_goes_to_the_model(tmp_path):
    page = lettered()
    r = model_text((90, 90, 210, 310), (100, 100, 200, 300))
    assert on_art(page, r)
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    eraser.erase(page, r)
    assert not calls and eraser.counts["art"] == 1


# ------------------------------------------------------------------ the page's scale
def test_the_page_scale_holds_the_measures_to_pages_smaller_than_the_sample_sets_and_never_grows_them():
    from taslation.render import pagescale

    assert pagescale.page_scale(pagescale.TUNED_HEIGHT) == 1.0 and pagescale.page_scale(2400) == 1.0
    assert pagescale.page_scale(1000) == pytest.approx(1000 / 1170)
    assert pagescale.page_scale(100) == pagescale.LEAST and pagescale.page_scale(0) == 0.0
    assert pagescale.of(region()) == 1.0 and pagescale.of(region(scale=0.5)) == 0.5
    # (at the scale the measures were set at, every one is as it was: nothing changes on the sample set's pages)
    assert [pagescale.side(n, 1.0) for n in (5, 7, 9, 13, 15, 21)] == [5, 7, 9, 13, 15, 21]
    assert pagescale.px(artwork.RING_OUT, 1.0) == artwork.RING_OUT and pagescale.area(60, 1.0) == 60
    assert pagescale.side(13, 1000 / 1170) == 11 and pagescale.px(artwork.RING_OUT, 1000 / 1170) == 12
    assert pagescale.side(7, 0.4) == 3 and pagescale.side(3, 0.1) == 3  # (a kernel reaches a pixel at the least)


def _open_box_on_hatching(gap):
    """A white rectangle *gap* px round a column of lettering, its 3 px outline open at the top, on hatching."""
    page = flat(255, (600, 600))
    page[::5] = 40  # the drawing round the bubble
    x0, y0, x1, y1 = 260, 150, 320, 450
    cv2.rectangle(page, (x0 - gap - 3, y0 - gap - 3), (x1 + gap + 2, y1 + gap + 2), (0, 0, 0), -1)
    page[y0 - gap:y1 + gap, x0 - gap:x1 + gap] = 255
    page[y0 - gap - 3:y0 - gap, x0 + 20:x0 + 40] = 255  # the opening: no paper closed all round
    for y in range(y0 + 5, y1 - 30, 40):
        page[y:y + 26, x0 + 17:x0 + 43] = 0
    return page, (x0, y0, x1, y1)


def test_lettering_on_a_smaller_page_is_judged_on_a_ring_as_far_out_as_on_the_full_size_page():
    """The same bubble at the sample set's size (18 px of paper round its lettering) and at half that: the ring of
    `RING_OUT` 14 px stays on the paper of the first and reached the outline and the hatching past it on the second,
    which went to the inpainting; at its page's scale (`TextRegion.scale`) it stays on the paper there too."""
    full, box = _open_box_on_hatching(18)
    assert artwork.closed_interior(full, box) is None and not on_art(full, region("text-on-page", box))
    small = cv2.resize(full, (300, 300), interpolation=cv2.INTER_AREA)
    half = tuple(v // 2 for v in box)
    assert artwork.closed_interior(small, half, scale=0.5) is None
    assert on_art(small, region("text-on-page", half))  # the measures of the full-size page
    assert not on_art(small, region("text-on-page", half, scale=0.5))


def test_the_pipeline_takes_the_page_scale_from_the_paper_or_the_capture_area():
    host = SimpleNamespace(settings=SimpleNamespace(margins=(0, 0, 0, 0)))
    white = flat(255, (1000, 1400))
    assert Pipeline.page_scale(host, white) == pytest.approx(1000 / 1170)
    viewer = flat(30, (1000, 1400))  # a dark viewer round a page 800 px high
    viewer[100:900, 300:1100] = 255
    viewer[300:340, 500:540] = 0
    assert Pipeline.page_scale(host, viewer) == pytest.approx(800 / 1170, abs=0.01)
    host.settings.margins = (0, 85, 0, 0)  # the capture area the margins leave
    assert Pipeline.page_scale(host, white) == pytest.approx(915 / 1170)
    assert Pipeline.page_scale(host, flat(255, (1600, 1200))) == 1.0
    r = region()
    unit = SimpleNamespace(index=1, box=(0, 0, 10, 10))
    from taslation import pipeline as pl

    pl._place(r, unit, 0.8)
    assert (r.unit, r.scale) == (1, 0.8)


# ------------------------------------------------------------------ a ground that repeats itself
def dot_tone(size=(500, 500), pitch=6, dot=2):
    """A screentone: dark dots every *pitch* px on white, in rows offset by half a pitch."""
    page = flat(255, size)
    for y in range(0, size[0], pitch):
        for x in range((y // pitch % 2) * pitch // 2, size[1], pitch):
            cv2.circle(page, (x, y), dot, (40, 40, 40), -1)
    return page


def white_ringed(page, box=(150, 120, 230, 380)):
    """A column of strokes with a white ring of 4 px, on *page*, in *box*."""
    x0, y0, x1, y1 = box
    for y in range(y0 + 10, y1 - 40, 50):
        cv2.rectangle(page, (x0 + 6, y - 4), (x1 - 6, y + 34), (255, 255, 255), -1)
        cv2.rectangle(page, (x0 + 10, y), (x1 - 10, y + 30), (0, 0, 0), 4)
    return page


def test_lettering_with_a_white_ring_on_a_dot_tone_is_painted_over_with_the_tone(tmp_path):
    """LaMa made rows of stripes of a dot tone round lettering with a white ring; the tone repeats itself, so the hole
    is painted from the tone round it, the dots going on through it."""
    tone = dot_tone()
    page = white_ringed(tone.copy())
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    r = region("text", (150, 120, 230, 380))
    assert on_art(page, r)
    eraser.erase(page, r)
    assert eraser.counts["tone"] == 1 and eraser._model.runs == 0 and not calls
    inside = page[130:370, 160:220].astype(int)
    assert np.abs(inside - tone[130:370, 160:220]).mean() < 3  # the tone, dot for dot: no stripes, no white left


def test_with_no_inpainting_model_lettering_on_a_tone_is_painted_over_with_the_tone_all_the_same():
    """A computer without a GPU runs no LaMa (`art_erase` "auto"): `Pipeline._erase` paints the hole on a ground
    that repeats itself from that ground there too (`artwork.tone_erase`), the change within what its erase is
    recorded over (`_erase_reach`); any other ground, and an early look, the paper fill erases as before."""
    host = SimpleNamespace(settings=SimpleNamespace(erase_mode="fill", white_threshold=225, dark_threshold=140),
                           art_eraser=None, _paper_erase=Pipeline._paper_erase, ERASE_REACH=Pipeline.ERASE_REACH)
    box = (150, 120, 230, 380)
    tone = dot_tone()
    page = white_ringed(tone.copy())
    before = page.copy()
    r = region("text", box)
    Pipeline._erase(host, page, r)
    assert np.abs(page[130:370, 160:220].astype(int) - tone[130:370, 160:220]).mean() < 3  # the tone, dot for dot
    x0, y0, x1, y1 = Pipeline._erase_reach(host, page, region("text", box))
    changed = (page != before).any(axis=2)
    assert changed.sum() == changed[y0:y1, x0:x1].sum() > 0
    quick, paper = white_ringed(tone.copy()), white_ringed(tone.copy())
    Pipeline._erase(host, quick, region("text", box), quick=True)
    Pipeline._paper_erase(paper, region("text", box))
    assert np.array_equal(quick, paper)  # an early look: the paper fill
    for ground in (drawn(), flat(255)):
        page, paper = white_ringed(ground.copy()), white_ringed(ground.copy())
        Pipeline._erase(host, page, region("text", box))
        Pipeline._paper_erase(paper, region("text", box))
        assert np.array_equal(page, paper)


def test_hatching_repeats_itself_too_and_a_drawing_does_not():
    hatched = flat(230)
    hatched[::5] = 60
    hole = np.zeros(hatched.shape[:2], bool)
    hole[200:300, 200:260] = True
    assert artwork.tone_shifts(hatched, hole) is not None
    assert artwork.tone_shifts(drawn(), hole) is None  # a drawing's texture: no repeat
    assert artwork.tone_shifts(flat(200), hole) is None  # an even ground
    smooth = np.dstack([np.repeat(np.linspace(60, 230, 500).astype(np.uint8)[None], 500, axis=0)] * 3)
    cv2.line(smooth, (0, 100), (499, 400), (0, 0, 0), 3)
    assert artwork.tone_shifts(smooth, hole) is None  # a smooth drawing correlates near by and never repeats


def test_a_hole_the_tone_cannot_reach_goes_to_the_model(tmp_path, monkeypatch):
    page = white_ringed(dot_tone())
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    monkeypatch.setattr(artwork, "TONE_SHIFTS", 2)  # (too few repeats to paint all of the hole from)
    eraser.erase(page, region("text", (150, 120, 230, 380)))
    assert eraser.counts["tone"] == 0 and eraser.counts["art"] == 1
