"""A page translated at one window size is drawn from the cache at another (`fingerprint.readings`,
`Pipeline._resolve`): the content box a page's fingerprint is taken over comes out otherwise when the capture area,
joined from the page panels seen at a size, takes in a sliver of the viewer's ground beside a page whose edges are
black art, when a thin line that decides where the ink ends is drawn a pixel thinner, and when a window too narrow
for a spread shows its pages one at a time. The pages are drawn; the fingerprints, the readings and the cache are
the real ones."""

from __future__ import annotations

import random

import cv2
import numpy as np
from helpers import EN_TEXTS, FakeOcr
from PIL import Image, ImageDraw
from test_page_units import StandInDetector

from taslation import fingerprint as fp
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

GROUND = (43, 43, 43)  # the viewer's dark ground
PAGE = (600, 840)
BUBBLES = ((80, 160, 220, 330), (330, 470, 470, 640))  # on each page, in its white part


def _edged(seed: int) -> Image.Image:
    """A page of PAGE size whose top, bottom and outer (right) edges are black art with grey lines across it, white
    within, with blots of art and the two BUBBLES."""
    rng = random.Random(seed)
    w, h = PAGE
    page = Image.new("RGB", PAGE, (255, 255, 255))
    d = ImageDraw.Draw(page)
    for box in ((0, 0, w - 1, 70), (0, h - 71, w - 1, h - 1), (w - 60, 0, w - 1, h - 1)):
        d.rectangle(box, fill=(0, 0, 0))
    for y in range(0, h, 13):
        d.line((0, y, w, y + rng.randint(0, 30)), fill=(90, 90, 90), width=1)
    d.rectangle((60, 75, w - 66, h - 76), fill=(255, 255, 255))
    for _ in range(14):
        x, y = rng.randint(20, w - 180), rng.randint(90, h - 200)
        d.ellipse((x, y, x + rng.randint(40, 100), y + rng.randint(30, 90)), fill=(rng.randint(0, 180),) * 3)
    for box in BUBBLES:
        d.ellipse(box, fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    return page


def _touching(seed: int, right: bool, outer: int = 0) -> Image.Image:
    """A page of PAGE size of a spread whose pages touch: framed panels and blots of art from its inner edge (its
    left one for the *right* page) to *outer* pixels short of its outer edge, and the two BUBBLES."""
    rng = random.Random(seed)
    w, h = PAGE
    page = Image.new("RGB", PAGE, (255, 255, 255))
    d = ImageDraw.Draw(page)
    lo, hi = (0, w - outer) if right else (outer, w)
    for y in (30, 300, 560):
        d.rectangle((lo, y, hi - 1, y + 230), outline=(0, 0, 0), width=3)
    for _ in range(18):
        x, y = rng.randint(lo + 5, hi - 110), rng.randint(40, h - 130)
        d.ellipse((x, y, x + rng.randint(40, 100), y + rng.randint(30, 90)), fill=(rng.randint(0, 180),) * 3)
    for box in BUBBLES:
        d.ellipse(box, fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    return page


def _viewer(pages: list[Image.Image], size: tuple[int, int], scale: float) -> tuple[Image.Image, fp.Box, list[fp.Box]]:
    """The viewer at a window of *size* showing *pages* (right page first, side by side, touching) centred at
    *scale*: the capture, the paper's box in it and the bubbles' boxes, the right page's first."""
    w, h = round(PAGE[0] * scale), round(PAGE[1] * scale)
    img = Image.new("RGB", size, GROUND)
    right, y = (size[0] + w * len(pages)) // 2, (size[1] - h) // 2
    bubbles = []
    for n, page in enumerate(pages):
        x = right - w * (n + 1)
        img.paste(page.resize((w, h), Image.LANCZOS), (x, y))
        bubbles += [(x + round(b[0] * scale), y + round(b[1] * scale), x + round(b[2] * scale),
                     y + round(b[3] * scale)) for b in BUBBLES]
    return img, (right - w * len(pages), y, right, y + h), bubbles


def _sliver(paper: fp.Box, size: tuple[int, int], by: int = 2) -> tuple[int, int, int, int]:
    """The capture area (margins) *by* pixels wider than the paper on its left and right, as a size's area joined
    from a spread's panels is beside a page alone."""
    return paper[0] - by, paper[1], size[0] - paper[2] - by, size[1] - paper[3]


BIG, SMALL = ((1500, 1000), 1.0), ((1300, 900), 0.9)  # two window sizes: the frame's size and the page's scale
NARROW = ((800, 900), 0.9)  # a window too narrow for a spread


def _nearest(units: list[fp.PageUnit], fingerprint: str) -> int:
    return min(fp.hamming(u.fingerprint, fingerprint) for u in units)


def _best(rgb: np.ndarray, fingerprint: str, margins=(0, 0, 0, 0)) -> int:
    """The distance of the nearest unit of any reading of *rgb* to *fingerprint*."""
    return min(_nearest(r, fingerprint) for r in fp.readings(rgb, margins) if r)


def test_a_sliver_of_ground_beside_a_page_with_black_edges_moves_its_content_box_and_a_reading_finds_it():
    """At the big size the page is read in the whole capture (its black edges are ink against the ground); at the
    small size in an area two pixels wider than the paper, where the ring of the area is the page's own black and
    the sliver is taken for paper: the content box comes out otherwise and so does the fingerprint, by far more than
    a lookup takes. One of the readings at the small size is the page as it was read at the big one."""
    page = _edged(1)
    big, big_paper, _bubbles = _viewer([page], *BIG)
    (stored,) = fp.analyze(np.asarray(big))
    small, paper, _bubbles = _viewer([page], *SMALL)
    rgb, margins = np.asarray(small), _sliver(paper, SMALL[0])
    (found,) = fp.analyze(rgb, margins)
    assert fp.hamming(found.fingerprint, stored.fingerprint) > 36
    assert fp.hamming(fp.analyze(rgb)[0].fingerprint, stored.fingerprint) <= 16  # (read in its whole capture: found)
    assert _best(rgb, stored.fingerprint, margins) <= 16
    # ... and the other way round: stored as read with the sliver, found in the whole capture at the other size
    (with_sliver,) = fp.analyze(np.asarray(big), _sliver(big_paper, BIG[0]))
    assert fp.hamming(fp.analyze(rgb)[0].fingerprint, with_sliver.fingerprint) > 36
    assert _best(rgb, with_sliver.fingerprint) <= 16


def test_a_different_page_is_far_from_every_reading():
    """A page drawn alike (the same black edges, other art and bubbles): none of the readings of it comes near the
    stored page."""
    (stored,) = fp.analyze(np.asarray(_viewer([_edged(1)], *BIG)[0]))
    other, paper, _bubbles = _viewer([_edged(2)], *SMALL)
    rgb = np.asarray(other)
    for margins in ((0, 0, 0, 0), _sliver(paper, SMALL[0])):
        assert min(_nearest(fp.analyze(rgb, margins), stored.fingerprint), _best(rgb, stored.fingerprint, margins)) > 60


def _lined(dots: int) -> np.ndarray:
    """A white page with blots of art in its lower part and, near its top, a line *dots* pixels long: the dark
    pixels a row needs to count as ink (2 here), or one fewer, as the page drawn at another scale may have it."""
    rng = random.Random(7)
    img = Image.new("RGB", PAGE, (255, 255, 255))
    d = ImageDraw.Draw(img)
    for _ in range(18):
        x, y = rng.randint(20, 480), rng.randint(250, 700)
        d.ellipse((x, y, x + rng.randint(40, 100), y + rng.randint(30, 90)), fill=(rng.randint(0, 180),) * 3)
    for x in range(100, 100 + dots):
        d.point((x, 12), fill=(0, 0, 0))
    return np.asarray(img)


def test_an_edge_a_pixel_of_ink_would_move_is_read_so_too():
    two, one = _lined(2), _lined(1)
    moved: list[tuple[int, int]] = []
    gray = cv2.cvtColor(one, cv2.COLOR_RGB2GRAY)
    box = fp.content_box(gray, moved=moved)
    assert box == fp.content_box(gray) and box[1] > 250  # (noting the edges changes nothing)
    assert moved == [(1, -1)]  # the top edge, with a pixel less needed
    lined = fp.content_box(cv2.cvtColor(two, cv2.COLOR_RGB2GRAY))
    assert fp.content_box(gray, slack=(0, -1, 0, 0))[1] == lined[1] == 12
    (stored,), (found,) = fp.analyze(two), fp.analyze(one)
    assert fp.hamming(found.fingerprint, stored.fingerprint) > 36
    assert _best(one, stored.fingerprint) == 0


def _spread() -> tuple[Image.Image, Image.Image]:
    """The right and left pages of a spread whose pages touch, the left page's ink keeping 60 px from its outer edge:
    the spread is split at the middle of its content box, 30 px into the right page."""
    return _touching(1, right=True), _touching(2, right=False, outer=60)


def test_a_page_alone_in_a_narrow_window_is_found_as_a_page_of_its_spread_and_the_other_way_round():
    """The right page, cut short at its inner edge by the spread's split, is told from the page alone by more than a
    lookup takes; cut at that side by a few hundredths of its width, the page alone is the spread's page. A spread
    whose pages were stored alone: split at its paper's middle, its pages are those."""
    right, left = _spread()
    wide = np.asarray(_viewer([right, left], *BIG)[0])
    spread = fp.analyze(wide)
    alone = np.asarray(_viewer([right], *NARROW)[0])
    (page,) = fp.analyze(alone)
    assert fp.hamming(page.fingerprint, spread[0].fingerprint) > 36
    assert _best(alone, spread[0].fingerprint) <= 8
    stored = [fp.analyze(np.asarray(_viewer([p], *NARROW)[0]))[0] for p in (right, left)]
    assert all(fp.hamming(s.fingerprint, u.fingerprint) > 36 for s, u in zip(stored, spread))
    halves = [r for r in fp.readings(wide) if len(r) == 2 and r[0].box[0] == (BIG[0][0] // 2)]
    assert len(halves) == 1 and [u.index for u in halves[0]] == [0, 1]
    assert all(fp.hamming(s.fingerprint, u.fingerprint) <= 8 for s, u in zip(stored, halves[0]))


def test_noting_what_would_move_changes_no_split_and_no_unit(sample_page, sample_page2):
    w, h = sample_page.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(sample_page2, (0, 20))
    spread.paste(sample_page, (w + 60, 20))
    gray = cv2.cvtColor(np.asarray(spread), cv2.COLOR_RGB2GRAY)
    box = fp.content_box(gray)
    moved: list[fp.Nudge] = []
    assert fp.split_spread(gray, box, moved=moved) == fp.split_spread(gray, box)
    assert fp._analyze(np.asarray(spread), (0, 0, 0, 0), True, None, True, moved=[]) == fp.analyze(np.asarray(spread))


def test_the_readings_are_not_kept_among_the_shared_analyses(monkeypatch):
    monkeypatch.setattr(fp, "_shared", [])
    small, paper, _bubbles = _viewer([_edged(1)], *SMALL)
    rgb = np.asarray(small)  # (read-only: what `analyze` shares)
    assert len(list(fp.readings(rgb, _sliver(paper, SMALL[0])))) >= 2
    assert fp._shared == []


# ------------------------------------------------------------------ the pipeline
def _pipeline(settings, cache):
    settings.detect_dark_bubbles = settings.detect_text_blocks = False
    tr = DictTranslator(EN_TEXTS, default="ok")
    detector = StandInDetector([])
    return Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache, detector=detector), tr, detector


def _show(pipeline, detector, capture, bubbles, margins=(0, 0, 0, 0)):
    """The pipeline reading *capture* in the capture area *margins*, the bubbles found where they are drawn."""
    pipeline.set_margins(margins)
    detector.boxes, detector.origin = list(bubbles), margins[:2]
    return pipeline.process(capture)


def _near(a, b, by=2) -> bool:
    return all(abs(p - q) <= by for p, q in zip(a, b))


def test_a_page_translated_at_one_size_is_drawn_from_the_cache_at_another(settings):
    """Translated in the whole capture at the big size; at the small size, in an area a sliver wider than the paper:
    the page comes from the cache with no request, its lettering in the bubbles where they are at that size, by the
    box of the reading that found it; the cache keeps its one page under the fingerprint it was stored by."""
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, tr, detector = _pipeline(settings, cache)
    page = _edged(1)
    big, _paper, big_bubbles = _viewer([page], *BIG)
    first = _show(pipeline, detector, big, big_bubbles)
    assert first.cache_misses == 1 and len(first.translated) == 2 and len(tr.calls) == 1
    (stored,) = cache.pages
    kept = stored.fingerprint
    small, paper, small_bubbles = _viewer([page], *SMALL)
    margins = _sliver(paper, SMALL[0])
    assert fp.hamming(fp.analyze(np.asarray(small), margins)[0].fingerprint, kept) > 36  # (by default: a miss)
    again = _show(pipeline, detector, small, small_bubbles, margins)
    assert again.cache_hits == 1 and again.cache_misses == 0 and len(tr.calls) == 1
    assert all(r.from_cache for r in again.translated)
    got = sorted(r.bbox for r in again.translated)
    assert len(got) == 2 and all(_near(a, b) for a, b in zip(got, sorted(small_bubbles))), (got, small_bubbles)
    (unit,) = again.units
    assert _near(unit.box, paper) and fp.hamming(unit.fingerprint, kept) <= 36  # (the page as a whole, as stored)
    assert [p.fingerprint for p in cache.pages] == [kept]  # nothing stored, nothing re-keyed


def test_a_page_of_a_spread_translated_in_a_wide_window_is_drawn_from_the_cache_alone_in_a_narrow_one(settings):
    """The spread translated in the wide window; its right page alone in the narrow one (by default more than a
    lookup takes from the spread's page, which the split cut short): from the cache, its lettering in its bubbles."""
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, tr, detector = _pipeline(settings, cache)
    right, left = _spread()
    wide, _paper, wide_bubbles = _viewer([right, left], *BIG)
    first = _show(pipeline, detector, wide, wide_bubbles)
    assert first.cache_misses == 2 and len(cache.pages) == 2 and len(tr.calls) == 2  # (a request per page)
    narrow, _paper, bubbles = _viewer([right], *NARROW)
    again = _show(pipeline, detector, narrow, bubbles)
    assert again.cache_hits == 1 and len(tr.calls) == 2 and all(r.from_cache for r in again.translated)
    got = sorted(r.bbox for r in again.translated)
    assert len(got) == 2 and all(_near(a, b) for a, b in zip(got, sorted(bubbles))), (got, bubbles)
    assert len(cache.pages) == 2


def test_a_different_page_at_the_other_size_is_not_given_the_cached_one(settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, tr, detector = _pipeline(settings, cache)
    big, _paper, big_bubbles = _viewer([_edged(1)], *BIG)
    _show(pipeline, detector, big, big_bubbles)
    other, paper, other_bubbles = _viewer([_edged(2)], *SMALL)
    res = _show(pipeline, detector, other, other_bubbles, _sliver(paper, SMALL[0]))
    assert res.cache_hits == 0 and res.cache_misses == 1 and len(tr.calls) == 2
    assert not any(r.from_cache for r in res.translated) and len(cache.pages) == 2


def test_no_reading_is_made_for_an_empty_cache_nor_for_a_page_the_cache_holds_as_found(settings, monkeypatch):
    read = []
    real = fp.readings
    monkeypatch.setattr(fp, "readings", lambda *a, **k: read.append(1) or real(*a, **k))
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, _tr, detector = _pipeline(settings, cache)
    big, _paper, big_bubbles = _viewer([_edged(1)], *BIG)
    _show(pipeline, detector, big, big_bubbles)  # (the cache empty)
    small, _paper, small_bubbles = _viewer([_edged(1)], *SMALL)
    assert _show(pipeline, detector, small, small_bubbles).cache_hits == 1  # (found as it is read)
    assert read == []
