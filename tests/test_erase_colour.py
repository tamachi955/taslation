"""The erase stays within the bubble's outline, takes the bubble's own paper colour, keeps a gradient, and takes only
lettering for stray lettering, on a page in colour and in black and white; ``erase_mode = "classic"`` is the erase of
before, byte for byte."""

from __future__ import annotations

import copy

import cv2
import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr

from taslation.detect import BubbleDetector
from taslation.regions import TextRegion
from taslation.render.erase import (STRAY_KINDS, bubble_background, erase_region, erase_rings, erase_stray,
                                    fill_paper, paper_colour, within_outline)

CREAM = (250, 238, 205)  # a ground as light as paper (grey level 238 > white_threshold)
INK = (30, 25, 20)
LINE = (60, 40, 30)  # a thin dark brown outline
WHITE = (255, 255, 255)


def _lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.ascontiguousarray(rgb).astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def _de(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((_lab(a) - _lab(b)) ** 2).sum(axis=-1))


def _glyph(img: np.ndarray, x: int, y: int, rng: np.random.Generator, s: int = 16, colour=INK, t: int = 3) -> None:
    """A mark like a glyph: a few strokes of varied length in an s x s cell (no two alike, as in real lettering)."""
    for _ in range(int(rng.integers(2, 5))):
        if rng.random() < 0.5:
            yy = int(rng.integers(0, s - t))
            xa, xb = sorted(int(v) for v in rng.integers(0, s, 2))
            cv2.rectangle(img, (x + xa, y + yy), (x + max(xb, xa + 4), y + yy + t - 1), colour, -1)
        else:
            xx = int(rng.integers(0, s - t))
            ya, yb = sorted(int(v) for v in rng.integers(0, s, 2))
            cv2.rectangle(img, (x + xx, y + ya), (x + xx + t - 1, y + max(yb, ya + 4)), colour, -1)


def _letter(img: np.ndarray, ex: np.ndarray, x0: int, x1: int, y0: int, y1: int, seed: int = 7, colour=INK,
            s: int = 16, step: int = 22) -> None:
    """Columns of glyph-like marks where they lie well inside the ellipse *ex* (< 0.85)."""
    rng = np.random.default_rng(seed)
    for x in range(x1 - s, x0 - 1, -step):
        for y in range(y0, y1 - s, step):
            if all(ex[cy, cx] < 0.85 for cx, cy in ((x, y), (x + s, y), (x, y + s), (x + s, y + s))):
                _glyph(img, x, y, rng, s, colour)


def _bubble(shape=(800, 640), ground=CREAM, centre=(160, 200), axes=(100, 140), paper=WHITE, line=LINE,
            thickness: int = 2, gaps: tuple[float, ...] = (), gap: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """A page of *ground* with an elliptical bubble of *paper* in a thin *line*, the outline cut by a gap of *gap* px
    at each angle of *gaps* (degrees, clockwise from the right). Returns the page and the ellipse's equation (< 1
    inside)."""
    h, w = shape
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = ground
    cv2.ellipse(img, centre, axes, 0, 0, 360, paper, -1)
    cv2.ellipse(img, centre, axes, 0, 0, 360, line, thickness)
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = (xx - centre[0]) / axes[0], (yy - centre[1]) / axes[1]
    ex = u ** 2 + v ** 2
    for deg in gaps:
        t = np.deg2rad(deg)
        across = np.abs(-np.sin(t) * (xx - centre[0]) + np.cos(t) * (yy - centre[1]) * axes[0] / axes[1])
        along = np.cos(t) * u + np.sin(t) * v
        strip = (across <= gap / 2.0) & (along > 0.85) & (along < 1.15)
        img[strip & (ex < 1)] = paper
        img[strip & (ex >= 1)] = ground
    return img, ex


def _outline(img: np.ndarray, ex: np.ndarray) -> np.ndarray:
    return (cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) < 140) & (ex > 0.9) & (ex < 1.12)


def _region(ex: np.ndarray, img: np.ndarray, kind: str = "bubble", erode: float = 0.93) -> TextRegion:
    """A region as the detector makes one for the bubble *ex*: the interior a little in from the outline, the text
    box round the lettering."""
    inside = ex < erode
    ys, xs = np.nonzero(inside)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    ink = (gray > 140) if kind == "dark-bubble" else (gray < 140)
    ty, tx = np.nonzero(ink & inside)
    box = (int(tx.min()), int(ty.min()), int(tx.max()) + 1, int(ty.max()) + 1)
    mask = np.ascontiguousarray(inside[y0:y1, x0:x1].astype(np.uint8) * 255)
    return TextRegion(x0, y0, x1, y1, mask, box, kind=kind, glyph=16.0)


@pytest.mark.parametrize("ground, line", [(CREAM, LINE), (WHITE, (50, 50, 50))])
def test_a_broken_outline_stays_whole(ground, line):
    """The case of the colour page, and of a page in black and white: a thin outline broken in two places (2 px
    gaps) leaves a short arc on its own, inside the text box; it passed for a glyph of stray lettering and was
    painted the paper's white, which left a gap in the outline (and white over the cream beyond)."""
    img, ex = _bubble(ground=ground, line=line, gaps=(299, 341))
    _letter(img, ex, 75, 250, 80, 330)
    regions = BubbleDetector().detect(img)
    assert len(regions) == 1 and regions[0].kind == "bubble"
    region = regions[0]
    tb = region.text_box
    outline = _outline(img, ex)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(outline.astype(np.uint8), connectivity=8)
    arcs = [i for i in range(1, n) if max(stats[i][2], stats[i][3]) <= 90]
    assert len(arcs) == 1  # the arc between the gaps is a piece of its own, short enough to pass for a glyph
    x, y, w, h = (int(v) for v in stats[arcs[0]][:4])
    overlap = max(0, min(x + w, tb[2] + 2) - max(x, tb[0] - 2)) * max(0, min(y + h, tb[3] + 2) - max(y, tb[1] - 2))
    assert overlap >= 0.5 * w * h  # ... and it lies inside the text box: what made it stray lettering
    out = img.copy()
    mask_before = region.mask.copy()
    bg = erase_region(out, region)
    assert bg == WHITE
    changed = np.any(out != img, axis=2)
    assert not (changed & outline).any()  # the outline is whole
    assert not (changed & (ex >= 1.0)).any()  # nothing beyond it changed
    assert (cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)[ex < 0.85] > 245).all()  # the lettering is gone
    assert np.array_equal(region.mask, mask_before)  # nothing was cut: the mask is left as it is


def test_a_mask_that_ran_out_through_a_gap_is_cut_back_to_the_bubble():
    """A 5 px gap faces the panel's border across a cream strip as light as paper: the detector's white area runs
    out through the gap and round the outline, the mask takes in the strip and the outline, and the fill painted
    them white. The erase seals the gap and leaves the strip and the outline alone."""
    img, ex = _bubble(gaps=(0,), gap=5)
    border = np.zeros(img.shape[:2], np.uint8)
    cv2.rectangle(border, (40, 45), (272, 355), 255, 2)
    img[border > 0] = LINE
    _letter(img, ex, 75, 250, 80, 330)
    region = max(BubbleDetector().detect(img), key=lambda r: r.area)
    full = np.zeros(img.shape[:2], bool)
    full[region.y0:region.y1, region.x0:region.x1] = region.mask > 0
    assert (full & (ex > 1.1)).sum() > 5000  # the mask ran out over the strip ...
    outline = _outline(img, ex)
    assert (full & outline).sum() > 0.8 * outline.sum()  # ... and round the outline
    out = img.copy()
    erase_region(out, region)
    changed = np.any(out != img, axis=2)
    assert not (changed & (outline | (border > 0))).any()  # the outline and the border are whole
    assert not (changed & (ex >= 1.0)).any()  # the strip is untouched, at the gap too
    assert (cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)[ex < 0.85] > 245).all()  # the lettering is gone
    narrowed = np.zeros(img.shape[:2], bool)
    narrowed[region.y0:region.y1, region.x0:region.x1] = region.mask > 0
    # the region's mask is the bubble now, so the translation is set inside it
    assert not (narrowed & (ex >= 1.0)).any() and narrowed.sum() > 0.9 * (ex < 0.95).sum()


def test_within_outline_leaves_a_closed_bubble_alone():
    img, ex = _bubble()
    _letter(img, ex, 75, 250, 80, 330)
    region = BubbleDetector().detect(img)[0]
    mask = region.mask > 0
    assert within_outline(img, region, mask) is mask


def test_a_cream_bubble_on_a_white_page_gets_its_cream():
    """A cream bubble darker than the white threshold, on a white page: filled with its own cream, light judged
    against that cream; the page around stays white."""
    cream = (238, 220, 175)
    assert cv2.cvtColor(np.array([[cream]], np.uint8), cv2.COLOR_RGB2GRAY)[0, 0] < 225
    img, ex = _bubble(ground=WHITE, paper=cream)
    _letter(img, ex, 75, 250, 80, 330)
    region = _region(ex, img)
    out = img.copy()
    bg = erase_region(out, region)
    assert _de(np.array([[bg]], np.uint8), np.array([[cream]], np.uint8))[0, 0] < 2
    inside = np.zeros(img.shape[:2], bool)
    inside[region.y0:region.y1, region.x0:region.x1] = region.mask > 0
    assert (_de(out, np.full_like(out, cream))[inside] < 3).all()  # cream everywhere, the lettering gone
    assert not np.any(out != img, axis=2)[ex >= 1.0].any()


def test_paper_is_judged_against_its_own_colour():
    """Cream paper with a few white highlights and lettering: the white highlights are the only pixels over the
    fixed white threshold, so the grey-level rule takes white; the paper's own colour is cream."""
    cream = (236, 218, 172)
    crop = np.zeros((100, 100, 3), np.uint8)
    crop[:] = cream
    crop[:12, :] = WHITE  # highlights
    rng = np.random.default_rng(3)
    for x in range(10, 80, 22):
        for y in range(20, 80, 22):
            _glyph(crop, x, y, rng)
    mask = np.full((100, 100), 255, np.uint8)
    assert bubble_background(crop, mask) == WHITE
    assert _de(np.array([[paper_colour(crop, mask)]], np.uint8), np.array([[cream]], np.uint8))[0, 0] < 2


def test_a_gradient_bubble_keeps_its_gradient():
    """A bubble shaded from pink at the top to pale blue at the bottom: every pixel of it after the erase is the
    paper as it was there, not one colour for the whole bubble."""
    img, ex = _bubble(ground=WHITE)
    h = img.shape[0]
    top, bottom = np.array([255, 228, 232], np.float32), np.array([222, 236, 255], np.float32)
    t = np.clip((np.arange(h, dtype=np.float32) - 60) / 280.0, 0, 1)[:, None]
    paper = np.repeat(np.round(top * (1 - t) + bottom * t)[:, None, :], img.shape[1], axis=1).astype(np.uint8)
    clean = img.copy()
    clean[ex < 1] = paper[ex < 1]
    cv2.ellipse(clean, (160, 200), (100, 140), 0, 0, 360, LINE, 2)
    img = clean.copy()
    _letter(img, ex, 75, 250, 80, 330)
    region = _region(ex, img)
    out = img.copy()
    erase_region(out, region)
    inside = np.zeros(img.shape[:2], bool)
    inside[region.y0:region.y1, region.x0:region.x1] = region.mask > 0
    assert float(_de(paper[:1], paper[-1:]).max()) > 15  # a real gradient: one colour would be off by half of it
    assert (_de(out, clean)[inside] < 5).all()
    assert not np.any(out != img, axis=2)[ex >= 1.0].any()


def test_a_dark_bubble_in_colour():
    """Light lettering in a navy bubble on a cream page: the lettering goes, the navy stays navy."""
    navy = (25, 30, 70)
    img, ex = _bubble(paper=navy, line=(10, 10, 20))
    _letter(img, ex, 75, 250, 80, 330, colour=(240, 240, 235))
    region = _region(ex, img, kind="dark-bubble")
    out = img.copy()
    bg = erase_region(out, region, dark=True)
    assert _de(np.array([[bg]], np.uint8), np.array([[navy]], np.uint8))[0, 0] < 3
    inside = np.zeros(img.shape[:2], bool)
    inside[region.y0:region.y1, region.x0:region.x1] = region.mask > 0
    assert (_de(out, np.full_like(out, navy))[inside] < 5).all()
    assert not np.any(out != img, axis=2)[ex >= 1.0].any()


def _hair_page() -> tuple[np.ndarray, np.ndarray]:
    """A white bubble interior (left) beside brown hair (right) on a colour page, with outlined glyphs (a dark
    stroke in a white ring) on the hair: two inside the text box, one outside it (part of the drawing)."""
    img = np.full((120, 160, 3), 255, np.uint8)
    img[:, 80:] = (90, 50, 30)

    def glyph(x: int, y: int) -> None:
        cv2.rectangle(img, (x - 2, y - 2), (x + 13, y + 13), WHITE, -1)
        cv2.rectangle(img, (x, y), (x + 11, y + 11), (0, 0, 0), -1)

    glyph(95, 30)
    glyph(95, 60)
    glyph(130, 90)
    mask = np.zeros((120, 160), np.uint8)
    mask[:, :80] = 255
    return img, mask


def test_outlined_lettering_over_hair_is_still_erased():
    img, mask = _hair_page()
    region = TextRegion(0, 0, 160, 120, mask, (20, 20, 115, 80), kind="bubble")
    erase_region(img, region)
    hair = np.full((16, 16, 3), (90, 50, 30), np.uint8)
    assert (_de(img[28:44, 93:109], hair) < 8).all() and (_de(img[58:74, 93:109], hair) < 8).all()
    assert (img[88:90, 128:144] == 255).all()  # the drawing's own ring, outside the text box, stays


@pytest.mark.parametrize("frame, pane", [((70, 60, 50), (225, 245, 228)), ((60, 60, 60), (236, 236, 236))])
def test_light_pieces_of_the_ground_are_not_taken_for_rings(frame, pane):
    """Beyond the bubble but inside the text box: a pale pane (green, or grey in black and white) and a white one in
    a dark window frame. Light and glyph-sized, they passed for the rings of outlined glyphs and were painted the
    frame's dark."""
    img = np.full((160, 220, 3), 0, np.uint8)
    img[:] = frame
    img[:, :100] = 255  # the bubble's interior
    img[20:60, 120:160] = pane
    img[80:120, 120:160] = (250, 250, 250)  # a white pane
    rng = np.random.default_rng(5)
    for y in range(20, 130, 22):
        _glyph(img, 40, y, rng)
    mask = np.zeros((160, 220), np.uint8)
    mask[:, :94] = 255
    region = TextRegion(0, 0, 220, 160, mask, (20, 10, 170, 140), kind="bubble", glyph=16.0)
    out = img.copy()
    erase_region(out, region)
    assert np.array_equal(out[20:60, 120:160], img[20:60, 120:160])
    assert np.array_equal(out[80:120, 120:160], img[80:120, 120:160])
    assert (cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)[:, :94] > 245).all()


def test_lettering_on_the_page_keeps_its_ground():
    """Lettering set straight on a patterned colour ground (a text block): only the strokes and their fringe are
    painted, from the ground around them; the faint stripes of the ground away from the strokes stay."""
    img = np.zeros((120, 120, 3), np.uint8)
    img[:] = (250, 246, 236)
    img[::6] = (200, 214, 200)  # faint stripes, one row in six: darker than the ground, far lighter than a stroke
    rng = np.random.default_rng(11)
    for y in range(20, 80, 22):
        _glyph(img, 52, y, rng)
    crop = img.copy()
    mask = np.zeros((120, 120), bool)
    mask[10:110, 30:90] = True
    fill_paper(crop, mask, (250, 246, 236), whole=False)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    assert (gray[mask] > 190).all()  # the strokes are gone
    far = mask.copy()
    far[8:100, 40:80] = False  # away from the strokes
    assert np.array_equal(crop[far], img[far])  # the ground there, stripes and all, is as it was


def _classic(image: np.ndarray, region: TextRegion, white_threshold: int = 225, dark_threshold: int = 140,
             dark: bool = False) -> tuple[int, int, int]:
    """The erase of before, put together from its parts as erase_region did it: the median of the light pixels,
    the stray pieces and the rings by light and dark alone, the whole mask in one colour."""
    crop = image[region.y0:region.y1, region.x0:region.x1]
    mask = region.mask
    bg = bubble_background(crop, mask, white_threshold, dark)
    if region.kind in STRAY_KINDS and region.text_box is not None:
        tb = region.text_box
        local = (tb[0] - region.x0, tb[1] - region.y0, tb[2] - region.x0, tb[3] - region.y0)
        erase_stray(crop, mask, local, dark_threshold, white_threshold)
        if not dark:
            erase_rings(crop, mask, local, dark_threshold, white_threshold)
    crop[mask > 0] = bg
    return bg


def _pages() -> list[tuple[np.ndarray, list[TextRegion]]]:
    """Pages where the erase of before went wrong: the broken outline, the leak, and the outlined lettering on hair."""
    out = []
    img, ex = _bubble(gaps=(299, 341))
    _letter(img, ex, 75, 250, 80, 330)
    out.append((img, BubbleDetector().detect(img)))
    img, ex = _bubble(gaps=(0,), gap=5)
    cv2.rectangle(img, (40, 45), (272, 355), LINE, 2)
    _letter(img, ex, 75, 250, 80, 330)
    out.append((img, BubbleDetector().detect(img)))
    img, mask = _hair_page()
    out.append((img, [TextRegion(0, 0, 160, 120, mask, (20, 20, 115, 80), kind="bubble")]))
    return out


def test_classic_mode_is_the_erase_of_before(sample_page, sample_page2):
    pages = _pages()
    for fixture in (sample_page, sample_page2):  # black and white
        rgb = np.ascontiguousarray(np.asarray(fixture.convert("RGB")))
        regions = BubbleDetector().detect(rgb) + BubbleDetector().detect(rgb, inverted=True)
        assert regions
        pages.append((rgb, regions))
    for img, regions in pages:
        for region in regions:
            dark = region.kind == "dark-bubble"
            ours, theirs = img.copy(), img.copy()
            bg = erase_region(ours, copy.deepcopy(region), "classic", dark=dark)
            assert bg == _classic(theirs, region, dark=dark)
            assert np.array_equal(ours, theirs)


def test_the_pipeline_in_classic_mode_erases_as_before(monkeypatch, settings, sample_page):
    """The black-and-white fixture through the whole pipeline with ``erase_mode = "classic"`` comes out as with the
    erase of before put in its place."""
    import taslation.pipeline as pipeline_module
    from taslation.pipeline import Pipeline
    from taslation.translate import DictTranslator

    settings.erase_mode = "classic"
    settings.validate()
    ours = np.asarray(Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).process(
        sample_page, use_cache=False).image)
    monkeypatch.setattr(pipeline_module, "erase_region",
                        lambda image, region, _mode, wt, dt, dark: _classic(image, region, wt, dt, dark))
    theirs = np.asarray(Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).process(
        sample_page, use_cache=False).image)
    assert np.array_equal(ours, theirs)


def test_the_default_keeps_what_classic_painted_over():
    """On a black-and-white page with a broken outline the two modes part: classic paints the arc, the default
    keeps it."""
    img, ex = _bubble(ground=WHITE, line=(50, 50, 50), gaps=(299, 341))
    _letter(img, ex, 75, 250, 80, 330)
    region = BubbleDetector().detect(img)[0]
    default, classic = img.copy(), img.copy()
    erase_region(default, copy.deepcopy(region))
    erase_region(classic, copy.deepcopy(region), "classic")
    outline = _outline(img, ex)
    assert not np.any(default != img, axis=2)[outline].any()
    assert int(np.any(classic != img, axis=2)[outline].sum()) > 100
