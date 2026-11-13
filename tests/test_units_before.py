"""A cache kept before 2026-10-31 keeps serving its pages (`Pipeline._lookup_before`): since then the paper on a dark
viewer grows through a page's black panels, so such a page has a larger unit and another fingerprint than the cache
kept for it. When the unit's own fingerprint finds nothing, the units as analyze found them then
(``fingerprint.analyze(grow=False)``, made once per capture and only then) are looked for; a page found so is served
and re-keyed under the unit of today, its bubbles moved to that unit's box. The page units are stand-ins on the
drawn capture of test_page_units: what is tested is what the pipeline does with them."""

from __future__ import annotations

import json

from helpers import EN_TEXTS
from test_page_units import ABOVE, BELOW, FP_LEFT, FP_RIGHT, LEFT, RIGHT, SHORT, _capture, _pipeline

from taslation import fingerprint
from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.fingerprint import PageUnit

FP_GROWN = "c3" * 40  # the right page's unit today (RIGHT, grown through its black panels)
TOP_RIGHT, TOP_LEFT = (660, 60, 860, 360), (460, 60, 660, 360)  # the upper panels split as a spread, as once found


def _stand_in(monkeypatch, today, before):
    """analyze as a stand-in: the units of *today*, and with ``grow=False`` those of *before*; the calls of the
    latter are counted."""
    asked: list[bool] = []

    def analyze(rgb, margins=(0, 0, 0, 0), grow=True, known=None):
        if not grow:
            asked.append(True)
        return [PageUnit(u.box, u.fingerprint, u.index) for u in (today if grow else before)]

    monkeypatch.setattr(fingerprint, "analyze", analyze)
    return asked


def _kept_before(cache, *pages):
    """Pages as a cache kept them before the unit grew: (fingerprint, unit box, bubble boxes in the capture)."""
    for fingerprint_, box, bubbles in pages:
        unit = PageUnit(box, fingerprint_, 0)
        cache.add(CachedPage(fingerprint=fingerprint_, aspect=unit.aspect, seq=-1,
                             bubbles=[CachedBubble(box=unit.normalize(b), text="From before.") for b in bubbles]))
    cache.save()


def _near(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_a_page_cached_before_the_unit_grew_is_served_and_rekeyed(settings, monkeypatch):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    _kept_before(cache, (FP_LEFT, LEFT, [(140, 400, 260, 570)]), (FP_RIGHT, SHORT, [ABOVE]))
    seq = cache.lookup(FP_RIGHT, 0.0, 0)[0].seq
    pipeline, tr = _pipeline(settings, monkeypatch, [], cache=cache)
    asked = _stand_in(monkeypatch, [PageUnit(RIGHT, FP_GROWN, 0)], [PageUnit(SHORT, FP_RIGHT, 0)])
    res = pipeline.process(_capture())
    assert res.cache_hits == 1 and len(asked) == 1
    above = next(r for r in res.regions if r.bbox == ABOVE)
    assert above.from_cache and above.translated_text == "From before."  # served where it was
    below = next(r for r in res.regions if r.bbox == BELOW)
    assert below.status == "unmatched" and not tr.calls  # never read then; the reader's mode leaves it
    page = cache.lookup(FP_GROWN, 0.0, 0)[0]  # re-keyed: today's fingerprint, the bubble in today's unit
    assert page.seq == seq and _near(page.bubbles[0].box, PageUnit(RIGHT, FP_GROWN, 0).normalize(ABOVE))
    assert cache.lookup(FP_RIGHT, 0.0, 6) is None and len(cache.pages) == 2
    on_disk = {p["fp"] for p in json.loads(cache.path.read_text(encoding="utf-8"))["pages"]}
    assert on_disk == {FP_LEFT, FP_GROWN}  # saved at once

    again = pipeline.process(_capture())  # from now on found as any page: the units as found before not made
    assert again.cache_hits == 1 and len(asked) == 1
    assert next(r for r in again.regions if r.bbox == ABOVE).translated_text == "From before."


def test_the_units_as_found_before_are_made_only_on_a_miss_and_once_per_capture(settings, monkeypatch):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    _kept_before(cache, (FP_GROWN, RIGHT, [ABOVE]))  # kept today
    pipeline, _tr = _pipeline(settings, monkeypatch, [], cache=cache)
    asked = _stand_in(monkeypatch, [PageUnit(RIGHT, FP_GROWN, 0)], [PageUnit(SHORT, FP_RIGHT, 0)])
    assert pipeline.process(_capture()).cache_hits == 1 and not asked  # found at once: nothing more

    asked = _stand_in(monkeypatch, [PageUnit(RIGHT, "5a" * 40, 0), PageUnit(LEFT, "69" * 40, 1)],
                      [PageUnit(SHORT, "96" * 40, 0), PageUnit(LEFT, "69" * 40, 1)])
    res = pipeline.process(_capture())  # a new spread: both units miss, the old units made once
    assert res.cache_hits == 0 and len(asked) == 1
    assert {p.fingerprint for p in cache.pages} >= {FP_GROWN}


def test_only_a_page_kept_within_the_replace_distance_and_inside_the_unit_is_taken(settings, monkeypatch):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    near = f"{int(FP_RIGHT, 16) ^ 0xFF:080x}"  # 8 bits off: within a lookup's 36, beyond the replace distance
    _kept_before(cache, (near, SHORT, [ABOVE]))
    pipeline, tr = _pipeline(settings, monkeypatch, [], cache=cache)
    _stand_in(monkeypatch, [PageUnit(RIGHT, FP_GROWN, 0)], [PageUnit(SHORT, FP_RIGHT, 0)])
    res = pipeline.process(_capture())
    assert res.cache_hits == 0 and len(tr.calls) == 1  # translated as a new page
    assert cache.lookup(near, 0.0, 0) is not None  # the old entry untouched

    cache = CacheStore(settings.cache_dir / "other").open("Book", "m")
    _kept_before(cache, (FP_RIGHT, LEFT, [(140, 400, 260, 570)]))
    pipeline, _tr = _pipeline(settings, monkeypatch, [], cache=cache)
    _stand_in(monkeypatch, [PageUnit(RIGHT, FP_GROWN, 0)], [PageUnit(LEFT, FP_RIGHT, 0)])  # the old unit elsewhere
    assert pipeline.process(_capture()).cache_hits == 0 and cache.lookup(FP_RIGHT, 0.0, 0) is not None


def test_two_units_found_before_inside_one_unit_become_one_page(settings, monkeypatch):
    """The upper panels of a page whose lower half is black panels were once split as if they were a spread: both
    halves' pages join under today's unit, with the first one's sequence number."""
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    a, b = "0f" * 40, "f0" * 40
    _kept_before(cache, (a, TOP_RIGHT, [(700, 120, 820, 290)]), (b, TOP_LEFT, [ABOVE]))
    seqs = sorted(p.seq for p in cache.pages)
    pipeline, _tr = _pipeline(settings, monkeypatch, [], cache=cache)
    _stand_in(monkeypatch, [PageUnit(RIGHT, FP_GROWN, 0)], [PageUnit(TOP_RIGHT, a, 0), PageUnit(TOP_LEFT, b, 1)])
    unit = PageUnit(RIGHT, FP_GROWN, 0)
    hit = pipeline._lookup(unit, lambda: fingerprint.analyze(None, grow=False))
    (page,) = cache.pages
    assert hit is not None and hit[0] is page and page.fingerprint == FP_GROWN and page.seq == seqs[0]
    assert sorted(bb.box for bb in page.bubbles) == sorted(unit.normalize(x) for x in ((700, 120, 820, 290), ABOVE))


def test_the_batch_scan_finds_a_page_cached_before_the_unit_grew(settings, monkeypatch):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    _kept_before(cache, (FP_RIGHT, SHORT, [ABOVE]))
    pipeline, _tr = _pipeline(settings, monkeypatch, [], cache=cache)
    _stand_in(monkeypatch, [PageUnit(RIGHT, FP_GROWN, 0)], [PageUnit(SHORT, FP_RIGHT, 0)])
    (unit,) = pipeline.scan(_capture()).units
    assert unit.stored_fingerprint == FP_GROWN and len(unit.kept) == 1  # the bubble above: kept
    assert [r.bbox for r in unit.regions] == [BELOW] and not unit.cached  # the one below: to translate
    assert pipeline.commit_unit(unit, {0: EN_TEXTS.get(unit.regions[0].source_text, "ok")})
    (page,) = cache.pages
    assert page.fingerprint == FP_GROWN and len(page.bubbles) == 2
