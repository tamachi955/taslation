"""The layout and inpainting models on real pages: a volume kept on the developer's machine in
``~/.taslation/dev-snapshots`` (tools/dev_snapshots.py) and the OpenMantra pages in ``~/.taslation/datasets``. Never shipped,
never copied: the tests read the files in place and skip unless TASLATION_REALDATA=1, the files and the models are there.
Nothing of a page is printed: the assertions compare counts."""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from taslation.annotations import AnnotationStore
from taslation.config import PAGE_MODELS, Settings
from taslation.pipeline import Pipeline
from taslation.render import artwork

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

REAL = Settings()
SNAPSHOTS = Path(REAL.state_dir) / "dev-snapshots"
WANTED = os.environ.get("TASLATION_REALDATA") == "1" and not any(m.missing(REAL.models_dir) for m in PAGE_MODELS)
GOLD = sorted(p.parent for p in SNAPSHOTS.glob("*/ocr_gold.json")) if WANTED and SNAPSHOTS.is_dir() else []
MARGINS = (0, 85, 0, 0)  # the capture area of that volume's screens
COVER = 1  # the screen of its cover

pytestmark = [pytest.mark.page_models]
volume = pytest.mark.skipif(not GOLD, reason="no gold volume in dev-snapshots, no models, or TASLATION_REALDATA is not 1")


@pytest.fixture(scope="module")
def read_volume():
    from dev_snapshots import screens
    from taslation.ocr import Readers

    # (art_erase "lama": both models on any computer, "auto" being "only where torch has a CUDA GPU")
    settings = Settings(margins=MARGINS, detect_model="auto", art_erase="lama")
    book = GOLD[0].name
    pipeline = Pipeline(settings, ocr=Readers(settings.models_dir, settings.ocr_threads), translator=None, cache=None,
                        annotations=AnnotationStore(settings.annotations_dir).open(book))

    def read(*numbers):
        return {n: (np.asarray(img), pipeline.process(img, translate=False, use_cache=False))
                for n, img in screens(book) if n in numbers}
    read.pipeline = pipeline
    yield read
    pipeline.release_gpu_models()


@volume
def test_nothing_on_the_cover_is_taken_for_dialogue(read_volume):
    """Its title is too large to read, and a credit on it reads as two kanji set across: neither goes to the model."""
    _rgb, result = read_volume(COVER)[COVER]
    assert not [r for r in result.regions if r.status == "untranslated"]
    assert Counter(r.status for r in result.regions)["print"] == 1


@volume
def test_a_page_of_the_book_reads_more_than_the_classical_detectors_found_and_no_bubble_twice(read_volume):
    from taslation.detect.layout import covered

    for _rgb, res in read_volume(12, 22, 23).values():
        read = [r for r in res.regions if r.status == "untranslated"]
        model = [r for r in read if r.from_model]
        assert len(model) > len(read) - len(model)
        assert not any(covered(r, model) for r in read if not r.from_model)


@volume
def test_the_mask_of_every_region_read_is_its_shape_not_a_plain_box_unless_it_has_none(read_volume):
    for rgb, res in read_volume(22, 25).values():
        for r in res.regions:
            if r.status == "untranslated":
                assert r.after is None and r.mask.shape == (r.height, r.width)
                assert (r.tier != 3) or (r.mask == 255).all()
                assert r.tier != 3 or artwork.on_art(rgb, r) or r.kind.startswith("text")


@volume
def test_the_title_page_has_nothing_to_translate(read_volume):
    """Screen 2: the book's title, set large across the page, and its publisher's mark."""
    _rgb, result = read_volume(2)[2]
    assert not [r for r in result.regions if r.status == "untranslated"]


@volume
def test_a_chapters_title_and_badge_are_left_as_they_are(read_volume):
    """Screen 66: the chapter's opening page, its badge and title large at the top of the right page; the dialogue of
    the left page is read as before."""
    rgb, result = read_volume(66)[66]
    read = [r for r in result.regions if r.status == "untranslated"]
    right_top = [r for r in read if r.text_box[0] >= rgb.shape[1] // 2 and r.text_box[1] < 400]
    assert not right_top and len(read) >= 4


def _changed(before, after):
    return (before != after).any(axis=2)


@volume
def test_a_plain_box_loses_only_its_lettering(read_volume):
    """Screen 31: a model region with no shape of its own (tier 3) on a busy ground: its erase paints its strokes
    and the ground right round them, never the rest of its box."""
    import cv2

    rgb, result = read_volume(31)[31]
    from taslation.pipeline import Pipeline as _P

    plain = [r for r in result.regions if r.status == "untranslated" and r.from_model and r.tier == 3]
    assert plain
    for r in plain:
        out = rgb.copy()
        _P._paper_erase(out, r)
        changed = _changed(rgb, out)[r.y0:r.y1, r.x0:r.x1]
        gray = cv2.cvtColor(rgb[r.y0:r.y1, r.x0:r.x1], cv2.COLOR_RGB2GRAY)
        near_ink = cv2.dilate((gray < 140).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        assert (changed & ~near_ink).sum() <= 0.002 * changed.size


@volume
def test_a_model_bubbles_outline_stays(read_volume):
    """Screen 80: model bubbles whose outline (dashed) the classical detectors could not close: the strokes lying along
    their box's edge (their outline, a panel's frame) are not inpainted."""
    from taslation.render import artwork

    rgb, result = read_volume(80)[80]
    eraser = artwork.ArtEraser(REAL.models_dir, "lama")
    unclosed = [r for r in result.regions if r.status == "untranslated" and r.from_model and r.tier == 3
                and r.kind in ("bubble", "dark-bubble")]
    assert unclosed
    taken = lying = 0
    for r in unclosed:
        hole = artwork.art_mask(rgb, r)
        if hole is None:
            continue
        band = np.zeros(hole.shape, bool)
        band[r.y0:r.y1, r.x0:r.x1] = True
        band[r.y0 + artwork.EDGE:r.y1 - artwork.EDGE, r.x0 + artwork.EDGE:r.x1 - artwork.EDGE] = False
        import cv2

        n, labels = cv2.connectedComponents((rgb.min(axis=2) < 140).astype(np.uint8), connectivity=8)
        on_band = np.bincount(labels[band].ravel(), minlength=n)
        every = np.bincount(labels.ravel(), minlength=n)
        along = on_band >= artwork.ALONG * np.maximum(1, every)  # the strokes lying along its edge: its outline
        along[0] = False
        outline = along[labels] & band
        core = cv2.erode(hole.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0  # (the hole is grown a pixel for anti-aliasing)
        taken += int((core & outline).sum())
        lying += int(outline.sum())
    # measured 13 of 79 (2026-11-03): where a glyph touches the dashed outline the two are one dark piece, which the edge
    # rule cannot part; the rest of the outline stays
    assert lying and taken <= 0.2 * lying
    eraser.release()


# ------------------------------------------------------------------ the holdout findings of 2026-11-06 (screens judged by
# Claude, every screen of this volume used for tuning since: the final check needs another volume)
def _read_as_text(result):
    return [r for r in result.regions if r.status == "untranslated" and r.source_text]


def _erased(pipeline, rgb, r):
    import copy

    out = rgb.copy()
    q = copy.copy(r)
    q.mask = r.mask.copy()
    pipeline._erase(out, q)
    return out, q


@volume
def test_a_small_model_bubbles_paper_is_not_painted_as_its_outline(read_volume):
    """Screen 38: a small bubble's text box holds the white gap between its shape and its outline; the stray erase took
    it for a glyph's ring and drew the outline thick and dark. No model region's erase darkens its page."""
    rgb, result = read_volume(38)[38]
    p = read_volume.pipeline
    model = [r for r in _read_as_text(result) if r.from_model]
    assert len(model) >= 10
    for r in model:
        out, _q = _erased(p, rgb, r)
        darker = rgb.astype(int).sum(axis=2) - out.astype(int).sum(axis=2) > 60
        assert darker.sum() <= 20


@volume
def test_lettering_on_a_black_panel_is_painted_black_not_inpainted(read_volume):
    """Screen 87: a narration of light lettering on a solid black panel; LaMa made grey blotches there. Its ground is
    flat: the paper fill paints it black."""
    import cv2

    rgb, result = read_volume(87)[87]
    p = read_volume.pipeline
    dark = [r for r in _read_as_text(result) if r.from_model and r.dark and r.area > 40000]
    assert dark
    for r in dark:
        out, _q = _erased(p, rgb, r)
        before = cv2.cvtColor(rgb[r.y0:r.y1, r.x0:r.x1], cv2.COLOR_RGB2GRAY)
        after = cv2.cvtColor(out[r.y0:r.y1, r.x0:r.x1], cv2.COLOR_RGB2GRAY)
        # the black between the strokes made lighter: 280 px with LaMa (2026-11-07), 13 painted
        assert ((before < 30) & (after > 60)).sum() <= 60


@volume
def test_the_back_covers_blurb_is_print(read_volume):
    """Screen 99: the blurb, lines set across on the cover's art, which the layout model sees as one block: print, never
    erased (LaMa drew it back as garbled strips)."""
    rgb, result = read_volume(99)[99]
    left = rgb.shape[1] // 2
    across = [r for r in _read_as_text(result) if r.text_box[2] <= left
              and r.text_box[2] - r.text_box[0] > 1.5 * (r.text_box[3] - r.text_box[1])]
    assert not across
    assert sum(r.status == "print" and r.text_box[2] <= left for r in result.regions) >= 4


@volume
def test_big_lettering_on_the_art_is_lettered_near_its_own_size(read_volume):
    """Screens 17 and 31: a column of big lettering on the art was set as a word of 24 px across its column. Its room
    grows by two glyphs: the translation comes out at 0.6 of the original's glyph or the largest size allowed."""
    from taslation.pipeline import _glyph_of

    p = read_volume.pipeline
    top = p.settings.max_font_size
    for rgb, result in read_volume(17, 31).values():
        big = [r for r in _read_as_text(result) if r.from_model and r.kind.startswith("text") and _glyph_of(r) >= 60]
        assert big
        for r in big:
            _box, done = p._letter_region(rgb.copy(), r, "Lorem ipsum dolor")
            assert done.size >= min(top, 0.6 * _glyph_of(r))


@volume
def test_small_white_bubbles_lose_all_their_lettering(read_volume):
    """Screens 25, 32, 80: small bubbles the classical detectors could not close, or that a block took for lettering on
    the page; LaMa left fragments of every glyph in them. Their ground is paper: the paper fill takes the lettering
    whole. Measured on the lettering box drawn in by 3 px (the outline lies beyond it)."""
    import cv2

    p = read_volume.pipeline
    for n, (rgb, result) in read_volume(25, 32, 80).items():
        checked = 0
        for r in _read_as_text(result):
            if not r.from_model or r.area > 20000:
                continue
            x0, y0, x1, y1 = artwork.box_of(rgb, r)
            ring = cv2.cvtColor(rgb[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6], cv2.COLOR_RGB2GRAY)
            if (ring >= 225).mean() < 0.6:
                continue  # not a white bubble
            if artwork.on_art(rgb, r) and not artwork.on_paper(rgb, r):
                hole = artwork.art_mask(rgb, r)
                if hole is None or not artwork.plain_ground(rgb, hole, (x0, y0, x1, y1)):
                    continue  # lettering on the drawing, the model's: the drawing stays in its box
            out, _q = _erased(p, rgb, r)
            inner = cv2.cvtColor(out[y0 + 3:y1 - 3, x0 + 3:x1 - 3], cv2.COLOR_RGB2GRAY)
            checked += 1
            assert (inner < 140).mean() <= 0.02, (n, r.bbox, r.kind, r.tier)
        assert checked
