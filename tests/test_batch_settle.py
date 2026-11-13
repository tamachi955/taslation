"""The whole-book scan takes a page once its picture has settled: as it is for settle_ms, and no longer getting sharper,
or, when the reader turns on sooner, once it was on show for STILL_SHARE of that. A viewer such as a browser-based one
draws a soft picture of the page first, whose thumbnail is the sharp page's; the scan takes the sharp one, and a page the
reader turned on from before its sharp picture came is said to have gone by, never taken soft (`batch.PageWatch`; the
fine detail of a frame, `batch.detail` and `batch.sharper`, is the live view's own test, `batch.crispness` tells a soft
picture from a sharp one of another page by the soft and sharp pictures the run's viewer drew). The watch decides frame
by frame, with the time given: these tests need no clock and no thread."""
from __future__ import annotations

import pytest
from PIL import ImageFilter
from test_follow import _page

from taslation import batch as batch_mod
from taslation.batch import (GLIMPSE_SHARE, MISSED, SHARPER_TAKEN, STILL_SHARE, TAKE, BatchReader, PageWatch,
                             crispness, detail, frames_differ, thumbnail)
from taslation.ui import constants

SETTLE, RECHECK = 0.4, 1.0


def _soft(page, radius: float):
    """*page* as a viewer draws it before its sharp picture has come: blurred by *radius* pixels."""
    return page.filter(ImageFilter.GaussianBlur(radius))


def _watch() -> PageWatch:
    return PageWatch(SETTLE, RECHECK, detail, crispness)


def _taken(decisions):
    return [image for kind, image in decisions if kind == TAKE]


def test_the_scan_settles_on_the_sharp_picture_not_on_a_soft_one_before_it():
    sharp = _page(4)
    softer, soft = _soft(sharp, 1.0), _soft(sharp, 0.5)
    for before, after in ((softer, soft), (soft, sharp)):  # alike to a look at thumbnails ...
        assert not frames_differ(thumbnail(before), thumbnail(after), 0.5)  # ... which alone settled on `soft`
    w = _watch()
    assert w.see(softer, 0.0) == [] and w.see(soft, 0.1) == [] and w.see(sharp, 0.2) == []
    assert w.tick(0.2 + SETTLE - 0.01) == []  # as it is since the sharp picture came: settle_ms from then
    assert _taken(w.tick(0.2 + SETTLE)) == [sharp] and w.soft_first  # this viewer draws soft first
    assert w.see(sharp, 1.0) == [] and w.shown is None  # the page taken, on show still: nothing more


def test_a_page_drawn_sharp_at_once_is_taken_at_settle_ms_and_a_viewer_that_never_draws_soft_pays_nothing():
    pages = [_page(seed) for seed in (1, 2, 3)]
    w = _watch()
    t = 0.0
    for page in pages:
        assert w.see(page, t) == [] and w.due(t) == pytest.approx(SETTLE)
        assert _taken(w.tick(t + SETTLE + 1e-6)) == [page]
        t += 1.0
    assert not w.soft_first


def test_after_a_page_drawn_soft_first_a_soft_picture_that_stays_waits_for_the_sharp_one():
    first, second, third = _page(1), _page(2), _page(3)
    w = _watch()
    w.see(_soft(first, 1.0), 0.0)
    w.see(first, 0.1)
    assert _taken(w.tick(0.5)) == [first] and w.soft_first
    soft_second = _soft(second, 1.0)
    w.see(soft_second, 1.0)
    assert w.tick(1.0 + SETTLE) == [] and w.due(1.0 + SETTLE) > 0  # soft, longer than settle_ms: not taken ...
    w.see(second, 1.7)
    assert _taken(w.tick(1.7 + SETTLE + 1e-6)) == [second]  # ... the sharp one is
    soft_third = _soft(third, 1.0)
    w.see(soft_third, 3.0)  # a picture that never comes sharper is taken as it is recheck_s on
    assert w.tick(3.0 + RECHECK - 0.01) == [] and _taken(w.tick(3.0 + RECHECK + 1e-6)) == [soft_third]


def test_a_page_the_reader_turned_on_from_while_it_was_soft_went_by_and_is_never_taken_soft():
    first, second, third = _page(1), _page(2), _page(3)
    w = _watch()
    w.see(_soft(first, 1.0), 0.0)
    w.see(first, 0.1)
    w.tick(0.5)
    soft_second = _soft(second, 1.0)
    w.see(soft_second, 1.0)
    decisions = w.see(_soft(third, 1.0), 1.3)  # turned on 300 ms later, the sharp picture not come
    assert decisions == [(MISSED, soft_second)]
    w.see(third, 1.45)  # this one came sharp before the reader turned on: taken
    assert w.see(_page(5), 1.6) == [(TAKE, third)]


def test_a_page_is_taken_when_the_reader_turns_on_after_still_share_of_settle_ms_and_a_glimpse_is_said():
    assert 0 < GLIMPSE_SHARE < STILL_SHARE < 1
    pages = [_page(seed) for seed in range(1, 6)]
    w = _watch()
    w.see(pages[0], 0.0)
    assert w.see(pages[1], STILL_SHARE * SETTLE) == [(TAKE, pages[0])]  # on show 200 ms of 400: a page
    assert w.see(pages[2], STILL_SHARE * SETTLE * 2 - 0.01) == [(MISSED, pages[1])]  # a little less: went by
    t = STILL_SHARE * SETTLE * 2 - 0.01
    assert w.see(pages[3], t + GLIMPSE_SHARE * SETTLE - 0.01) == []  # shorter still: a step of the drawing
    assert w.shown.image is pages[3]


def test_a_sharper_picture_of_the_page_taken_last_takes_its_place():
    page = _page(6)
    soft = _soft(page, 1.0)
    w = _watch()
    w.see(soft, 0.0)
    assert _taken(w.tick(SETTLE)) == [soft]  # soft for longer than settle_ms, before this viewer was known to
    assert w.see(page, 0.9) == [(SHARPER_TAKEN, page)] and w.soft_first
    assert w.see(page, 1.0) == []  # (the very frame again)


def test_once_the_viewer_drew_soft_first_a_page_that_looks_sharp_is_taken_though_it_never_came_sharper():
    first, second, third = _page(1), _page(2), _page(3)
    w = _watch()
    w.see(_soft(first, 1.5), 0.0)
    w.see(first, 0.1)
    w.tick(0.5)
    w.see(second, 1.0)  # drawn sharp at once (the viewer had it already)
    assert _taken(w.tick(1.0 + SETTLE + 1e-6)) == [second]  # not waited for till recheck_s: it looks sharp
    assert w.see(_soft(third, 1.5), 2.0) == []
    assert w.tick(2.0 + SETTLE) == []  # the soft one looks soft


def test_crispness_tells_soft_from_sharp_across_pages():
    sharp = [crispness(_page(seed)) for seed in (1, 2, 3)]
    soft = [crispness(_page(seed, soft=2)) for seed in (1, 2, 3)] + [crispness(_soft(_page(4), 1.0))]
    assert min(sharp) > 1.5 * max(soft)


def _chrome_pages(count: int):
    """Synthetic pages framed as the stand-in viewer shows them, and their soft pictures as Chrome draws them first
    (`fast_turn_eval.chrome_soft`: aliased, from a picture 6 times smaller)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import fast_turn_eval

    raw = [_page(i + 1, size=(830, 1170)) for i in range(count)]  # (strokes of ink: as hard as Chrome makes it)
    return ([fast_turn_eval.framed(p, i, count) for i, p in enumerate(raw)],
            [fast_turn_eval.framed(p, i, count, chrome=True) for i, p in enumerate(raw)])


def test_a_soft_picture_drawn_as_chrome_draws_it_is_the_same_page_as_its_sharp_one():
    sharp, soft = _chrome_pages(6)
    # the plain thumbnails differ by more than frames_differ's 2.0 (the false "missed" pages of the e2e run) ...
    assert all(frames_differ(thumbnail(a), thumbnail(b)) for a, b in zip(soft, sharp))
    pages = [batch_mod.page_thumb(thumbnail(f)) for f in sharp]
    softs = [batch_mod.page_thumb(thumbnail(f)) for f in soft]
    for i in range(6):  # ... the page is the same all the same, and no two pages are
        assert batch_mod.same_page(softs[i], pages[i], detail(soft[i]), detail(sharp[i]))
        for j in range(6):
            if j != i:
                assert not batch_mod.same_page(softs[i], pages[j], detail(soft[i]), detail(sharp[j]))
                assert not batch_mod.same_page(pages[i], pages[j], detail(sharp[i]), detail(sharp[j]))
    w = _watch()
    t, out = 0.0, []
    for a, b in zip(soft, sharp):  # every page soft for 250 ms, then sharp for 750 (one page a second)
        out += w.see(a, t)
        out += w.see(b, t + 0.25)
        out += w.tick(t + 0.25 + SETTLE + 1e-6)
        t += 1.0
    assert out == [(TAKE, b) for b in sharp]  # each taken once, sharp, none said to have gone by
    assert w.scale is not None and w.scale > 3 * batch_mod.page_distance(softs[0], pages[0]) / batch_mod.SOFT_SHARE


def test_the_bounds_follow_how_far_apart_the_runs_pages_are():
    (a, b), (soft, _) = _chrome_pages(2)  # (a soft picture whose plain thumbnail is more than 2.0 off its page's)
    pa, pb, ps = (batch_mod.page_thumb(thumbnail(x)) for x in (a, b, soft))
    assert not batch_mod.same_page(pa, pb) and not batch_mod.same_page(pa, pb, detail(a), detail(b))
    # two pages that are both sharp are never one, however close; a soft picture and its sharp one within the bound
    assert not batch_mod.same_page(pa, pb, detail(a), detail(b), scale=1e6)
    apart = batch_mod.page_distance(ps, pa)
    assert batch_mod.same_page(ps, pa, detail(soft), detail(a), scale=apart / batch_mod.SOFT_SHARE * 1.01)
    assert not batch_mod.same_page(ps, pa, detail(soft), detail(a), scale=apart / batch_mod.SOFT_SHARE * 0.99)
    w = _watch()
    for k in range(batch_mod.PAGES_LEARNT + 1):  # (the first page has none before it)
        w.see(_page(10 + k), float(k))
        assert (w.scale is None) == (k < batch_mod.PAGES_LEARNT)
        w.tick(k + SETTLE + 1e-6)


def test_the_recheck_is_the_live_views():
    assert batch_mod.RECHECK_MS == constants.RECHECK_MS and BatchReader.recheck_s == constants.RECHECK_MS / 1000
