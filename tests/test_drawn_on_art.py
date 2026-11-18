"""A rectangle the reader drew, or a region they resized or moved, is judged as a region the detectors found is: on the
drawing its lettering alone goes - filled in by the inpainting model where it runs, else its strokes filled in from the
drawing round them (`render.erase.erase_strokes`) - and never the whole rectangle in one colour; in a bubble, reaching
out of one, or on a flat box it is wiped on its paper as before (`render.artwork.drawn_on_art`,
`Pipeline._paper_erase`). The page lettered again (Ask again, the editor's save), shown again from the cache and
translated again erases it alike."""

from __future__ import annotations

import cv2
import numpy as np
from helpers import FakeOcr
from PIL import Image
from test_artwork import FakeModel, drawn, flat, lettered, ringed_glyphs
from test_page_units import StandInDetector

from taslation import fingerprint
from taslation.annotations import BookAnnotations
from taslation.cache import CacheStore
from taslation.fingerprint import PageUnit
from taslation.pipeline import Pipeline, manual_region
from taslation.render.artwork import ArtEraser, art_mask, drawn_on_art, on_art, plain_ground
from taslation.render.erase import within_paper
from taslation.translate import DictTranslator

BOX = (100, 100, 200, 300)  # the lettering of `test_artwork.lettered` lies in it


def _flat_share(before: np.ndarray, after: np.ndarray, box=BOX) -> float:
    """The share of *box* that the erase painted in its one most common new colour (a flat rectangle: nearly all)."""
    x0, y0, x1, y1 = box
    a, b = before[y0:y1, x0:x1], after[y0:y1, x0:x1]
    changed = (a != b).any(axis=2)
    if not changed.any():
        return 0.0
    colours, counts = np.unique(b[changed].reshape(-1, 3), axis=0, return_counts=True)
    top = colours[int(np.argmax(counts))]
    return float((changed & (b == top).all(axis=2)).sum()) / changed.size


def _strokes(page: np.ndarray, box=BOX) -> int:
    x0, y0, x1, y1 = box
    return int((page[y0:y1, x0:x1].max(axis=2) < 40).sum())


def _bubble_page() -> np.ndarray:
    """A drawing round a white bubble with outlined-free lettering (dark strokes on its paper) at BOX."""
    page = drawn()
    cv2.ellipse(page, (150, 200), (90, 150), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (150, 200), (90, 150), 0, 0, 360, (0, 0, 0), 3)
    for y in (130, 180, 230):
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 3)
    return page


# ------------------------------------------------------------------ where a rectangle lies
def test_a_rectangle_on_the_drawing_lies_on_the_art():
    page = lettered()
    r = manual_region(page, BOX)
    assert r.kind == "manual" and drawn_on_art(page, r) and on_art(page, r)


def test_a_rectangle_in_a_bubble_lies_on_its_paper():
    page = _bubble_page()
    r = manual_region(page, BOX)  # the ring round it takes in the outline and the drawing beyond
    assert not drawn_on_art(page, r) and not on_art(page, r)


def test_a_rectangle_hugging_a_bubbles_outline_lies_on_its_paper():
    """Its lettering near the outline: the ground right round the lettering reaches past the rectangle onto the outline
    and the drawing beyond; within the rectangle it is the bubble's paper."""
    page = drawn()
    cv2.ellipse(page, (150, 200), (50, 150), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (150, 200), (50, 150), 0, 0, 360, (0, 0, 0), 3)
    for x in (115, 165):  # by the rectangle's edges
        for y in (150, 190, 230):
            cv2.rectangle(page, (x, y), (x + 16, y + 18), (0, 0, 0), 3)
    r = manual_region(page, (112, 120, 188, 280))  # its corners a few pixels inside the outline
    hole = art_mask(page, r)
    assert hole is not None and not plain_ground(page, hole)  # past the rectangle: the outline, the drawing
    assert not drawn_on_art(page, r)
    before = page.copy()
    Pipeline._paper_erase(page, r)
    assert (page[120:280, 112:188] == 255).all()  # wiped on its paper, as before
    assert np.array_equal(page[:, :95], before[:, :95])  # the outline and the drawing beyond stay


def test_a_rectangle_on_a_bubbles_even_white_lies_on_its_paper_whatever_lies_by_its_lettering():
    """A line by the lettering (a mark of the drawing in the bubble) is no plain ground round it, but the rectangle's
    own ground is a bubble's white, even all over (`PAPER_SURE`)."""
    page = drawn()
    cv2.ellipse(page, (150, 200), (50, 150), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (150, 200), (50, 150), 0, 0, 360, (0, 0, 0), 3)
    for y in (150, 190, 230):
        cv2.rectangle(page, (130, y), (148, y + 18), (0, 0, 0), 3)
    cv2.line(page, (158, 135), (158, 265), (0, 0, 0), 3)
    r = manual_region(page, (112, 120, 188, 280))
    within = np.zeros(page.shape[:2], bool)
    within[120:280, 112:188] = True
    assert not plain_ground(page, art_mask(page, r), within=within)
    assert not drawn_on_art(page, r)


def test_a_rectangle_reaching_out_of_a_bubble_lies_on_its_paper():
    page = _bubble_page()
    r = manual_region(page, (40, 30, 260, 370))  # wider than the bubble on every side
    assert not drawn_on_art(page, r)


def test_a_rectangle_on_a_gradient_lies_on_the_art_and_keeps_it():
    """The paper fill cut it back to the gradient's light half (the dark half passed for ink) and painted that one
    colour, the lettering on the dark half left; the light half is no even paper."""
    row = np.interp(np.arange(500), (100, 200), (60, 255)).astype(np.uint8)  # dark to white across the rectangle
    page = np.ascontiguousarray(np.repeat(np.repeat(row[None, :, None], 500, 0), 3, 2))
    for x in (120, 165):  # lettering on both halves
        for y in (140, 200):
            cv2.rectangle(page, (x, y), (x + 18, y + 20), (0, 0, 0), 3)
    before = page.copy()
    box = (100, 100, 200, 300)
    r = manual_region(page, box)
    crop = page[100:300, 100:200]
    assert within_paper(crop, r.mask > 0) is not (r.mask > 0)  # cut back to the light half
    assert drawn_on_art(page, r)
    Pipeline._paper_erase(page, r)
    assert (page[100:300, 100:200].max(axis=2) < 40).sum() == 0  # all the lettering is gone
    assert _flat_share(before, page, box) < 0.3
    far = np.ones((200, 100), bool)
    for x in (120, 165):
        for y in (140, 200):
            far[y - 100 - 13:y - 100 + 34, x - 100 - 13:x - 100 + 32] = False  # a glyph, its ring and growth
    assert np.abs(page[100:300, 100:200].astype(int) - before[100:300, 100:200].astype(int))[far].max() == 0


def test_a_rectangle_on_a_flat_box_lies_on_its_paper():
    page = drawn()
    cv2.rectangle(page, (50, 60), (250, 340), (20, 20, 20), -1)  # a black caption box on the drawing
    for y in (130, 180, 230):
        cv2.rectangle(page, (140, y), (160, y + 20), (255, 255, 255), 3)
    r = manual_region(page, BOX)
    assert r.kind == "manual-dark" and not drawn_on_art(page, r)
    assert not drawn_on_art(flat(), manual_region(flat(), BOX))  # on the white page


# ------------------------------------------------------------------ how it is erased
def test_without_the_model_the_lettering_goes_and_the_drawing_stays():
    page = lettered()
    before = page.copy()
    r = manual_region(page, BOX)
    Pipeline._paper_erase(page, r)
    assert _strokes(before) > 300 and _strokes(page) == 0  # the strokes are gone
    assert _flat_share(before, page) < 0.3  # not a box of one colour
    x0, y0, x1, y1 = BOX
    gray = np.ascontiguousarray(before[y0:y1, x0:x1, 0])
    near = np.zeros(gray.shape, np.uint8)
    for y in (40, 90, 140):  # the glyphs of `ringed_glyphs`, ring and all, and the fill's reach round them
        near[y - 12:y + 36, 40 - 12:40 + 36] = 1
    unchanged = (page[y0:y1, x0:x1] == before[y0:y1, x0:x1]).all(axis=2)
    assert unchanged[near == 0].all()  # the drawing away from the lettering is as it was


def test_with_the_model_it_fills_the_lettering_alone(tmp_path):
    page = lettered()
    before = page.copy()
    eraser = ArtEraser(tmp_path, "auto", Pipeline._paper_erase)
    eraser._model = FakeModel()
    r = manual_region(page, BOX)
    eraser.erase(page, r)
    assert eraser._model.runs == 1 and eraser.counts["art"] == 1 and r.inpainted is not None
    changed = (page != before).any(axis=2)
    assert changed.any() and (page[changed] == 128).all()  # only the model's fill, in the lettering's hole
    assert changed.sum() < 0.5 * (BOX[2] - BOX[0]) * (BOX[3] - BOX[1])


def test_when_the_model_finds_too_little_the_lettering_is_erased_as_on_the_page(tmp_path):
    noise = np.random.default_rng(3).integers(110, 190, (500, 500), dtype=np.uint8)
    page = np.dstack([cv2.GaussianBlur(noise, (0, 0), 1.0)] * 3)  # a mid-grey drawing: nothing white round a stroke
    for y in (140, 200):  # dark strokes with no white ring: no lettering the model's mask takes
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 2)
    before = page.copy()
    eraser = ArtEraser(tmp_path, "auto", Pipeline._paper_erase)
    eraser._model = FakeModel()
    r = manual_region(page, BOX)
    eraser.erase(page, r)
    assert eraser._model.runs == 0 and eraser.counts["weak"] == 1
    assert _strokes(page) < _strokes(before) // 4 and _flat_share(before, page) < 0.3


def test_without_the_model_the_drawings_lines_through_the_rectangle_stay():
    """The strokes that are erased are pieces of a glyph's size clear of the rectangle's edge: a line of the drawing
    across it, or one longer than a glyph inside it, is no lettering."""
    noise = np.random.default_rng(3).integers(60, 240, (500, 500), dtype=np.uint8)
    page = np.dstack([cv2.GaussianBlur(noise, (0, 0), 1.0)] * 3)  # a drawing's light and dark: no even paper
    cv2.line(page, (60, 250), (260, 270), (0, 0, 0), 2)  # across the rectangle and past it
    cv2.line(page, (110, 105), (110, 235), (0, 0, 0), 2)  # inside it, longer than a glyph
    for y in (140, 180):
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 2)  # lettering
    before = page.copy()
    r = manual_region(page, BOX)
    assert drawn_on_art(page, r)
    Pipeline._paper_erase(page, r)
    assert (page[140:201, 138:163].max(axis=2) < 40).sum() == 0  # the lettering is gone
    assert (page[248:272, 100:200].max(axis=2) < 40).sum() == (before[248:272, 100:200].max(axis=2) < 40).sum()
    assert (page[103:238, 108:113].max(axis=2) < 40).sum() == (before[103:238, 108:113].max(axis=2) < 40).sum()


def test_in_a_bubble_it_is_wiped_on_its_paper_as_before(tmp_path):
    page = _bubble_page()
    eraser = ArtEraser(tmp_path, "auto", Pipeline._paper_erase)
    eraser._model = FakeModel()
    r = manual_region(page, BOX)
    eraser.erase(page, r)
    assert eraser._model.runs == 0 and (page[100:300, 100:200] == 255).all()


# ------------------------------------------------------------------ the page lettered again, from the cache, again
UNIT = PageUnit((0, 0, 500, 500), "5a" * 40, 0)


def test_asked_again_shown_from_the_cache_and_translated_again_it_is_erased_alike(settings, monkeypatch):
    settings.detect_dark_bubbles = settings.detect_text_blocks = False
    monkeypatch.setattr(fingerprint, "analyze", lambda rgb, margins=(0, 0, 0, 0), **_k: [
        PageUnit(UNIT.box, UNIT.fingerprint, UNIT.index)])
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    tr = DictTranslator({}, default="ok")
    p = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache, annotations=ann, detector=StandInDetector(()))
    model = FakeModel()
    p.art_eraser = ArtEraser(settings.models_dir, "lama", p._paper_erase)
    p.art_eraser._model = model
    page = Image.fromarray(lettered())
    assert not p.process(page).regions  # nothing found there by the detectors
    ann.add_box(UNIT.fingerprint, UNIT.aspect, UNIT.normalize(BOX), "add")
    first = p.process(page, complete=True)
    (r,) = first.regions
    assert r.kind == "manual" and r.translated_text == "ok" and model.runs >= 1
    shown = np.asarray(first.image)
    assert ((shown != np.asarray(page)).any(axis=2)[:, :90]).sum() == 0  # nothing beyond the rectangle
    x0, y0, x1, y1 = BOX
    assert (shown[y0:y1, x0:x1] == 128).all(axis=2).any()  # the model's fill shows past the lettering
    assert _flat_share(np.asarray(page), shown) < 0.5
    # Ask again: the answer taken, the page lettered again
    assert p.set_translation(first, r, "ok", edited=False)
    assert np.array_equal(np.asarray(first.image), shown)
    # shown again from the cache, lettered afresh
    p.shown_pages.clear()
    p.erased_regions.clear()
    again = p.process(page, complete=True)
    assert again.cache_hits == 1 and np.array_equal(np.asarray(again.image), shown)
    # translated again
    p.erased_regions.clear()
    fresh = p.process(page, use_cache=False, complete=True)
    assert np.array_equal(np.asarray(fresh.image), shown)


def test_the_glyphs_ringed_on_black_are_the_lettering_of_a_dark_rectangle():
    page = drawn()
    gray = np.ascontiguousarray(page[100:300, 100:200, 0])
    gray[:] = (gray - 150) // 2  # a dark drawing (its texture kept)
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    r = manual_region(page, BOX)
    assert r.kind == "manual-dark" and drawn_on_art(page, r)
