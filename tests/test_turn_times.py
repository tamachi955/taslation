"""The viewer's turns as the live view measures them for its confirmation time (`live._note_leg`, `live.confirm_ms`):
one turn is the leg of the page the frame stays on, from the last moment the frame before it was known on show to its
last change, the final sharp frame (one after the confirmation too: `_tail_turn`); a turn whose beginning was not
seen, one with a flash in it, and the same page seen again note nothing; a sequence of flips is noted by its last leg
alone; the time the window spends on a frame (its thumbnail drawn, its page units read) is not taken off the turn; a
soft picture longer than settle_ms is learnt past it. The window, the viewer, the clock and the worker are
tests/test_early_start.py's (turns during a page job: tests/test_job_watch.py)."""
from __future__ import annotations

from PIL import Image
from test_early_start import _learnt, follow  # noqa: F401 - the fixture
from test_follow import VIEWER, _page

from taslation.config import Settings
from taslation.ui.constants import FRAME_STEP_MS
from taslation.ui.live import confirm_ms


def _seen(w):
    return list(w._turns_seen(VIEWER.hwnd))


def test_a_turn_first_seen_settled_notes_nothing(follow):
    w, worker = follow.make()
    before = _seen(w)
    w._following.owner = "other"  # neither window in front: the window does not look ...
    follow.show((0.0, "2 soft", _page(2, soft=3)), (0.25, "2", _page(2)), run=1.0)  # ... while the page turns
    assert [j.name for j in worker.jobs] == ["1"]
    w._following.owner, w._following.look_at = "viewer", follow.clock.now  # the viewer in front again: one look
    follow.clock.run(2.0)
    assert worker.one("2").how == "done"  # the page is taken as ever ...
    assert _seen(w) == before  # ... and its turn, whose beginning was not seen, is no measurement


def test_a_page_seen_again_while_the_models_load_notes_its_turn_once(follow):
    w, worker = follow.make()
    before = _seen(w)
    w.ready = False  # the models load: a page that settles waits for them, and is followed again at each poll
    follow.show((0.0, "2", _page(2)), run=3.0)
    assert [j.name for j in worker.jobs] == ["1"] and w._queued is not None
    assert len(_seen(w)) == len(before) + 1  # the turn once, not once per look at the same page


def test_pages_flipped_through_are_noted_by_the_last_leg_alone(follow):
    _learnt(follow, 300)  # a long confirmation: the flips never settle on the way
    w, worker = follow.make()
    before = _seen(w)
    frames = []
    for k in range(5):  # five pages flipped 120 ms apart, each soft first and sharp 60 ms later; the last one stays
        frames += [(0.12 * k, f"p{k} soft", _page(40 + k, soft=3)), (0.12 * k + 0.06, f"p{k}", _page(40 + k))]
    follow.show(*frames)
    seen = _seen(w)
    assert len(seen) == len(before) + 1, seen  # one turn ...
    assert 60 <= seen[-1] <= 60 + 2 * FRAME_STEP_MS, seen  # ... the last page's, soft to sharp: not the 540 ms of all
    assert worker.kept == ["1", "p4"]


def test_a_flash_within_a_turn_notes_nothing(follow):
    w, worker = follow.make()
    w.settings.black_wait_s = Settings().black_wait_s
    before = _seen(w)
    soft, sharp = _page(2, soft=3), _page(2)
    black = Image.new("RGB", soft.size, "black")
    follow.show((0.0, "2 soft", soft), (0.1, "black", black), (0.8, "2", sharp))  # a focus flash of 700 ms
    assert worker.kept[-1] == "2"  # the sharp page is translated ...
    assert _seen(w) == before  # ... and the turn, the flash's time in it, is no measurement


def test_a_frame_of_another_size_notes_nothing(follow):
    """The viewer's window narrowed, its page laid out anew: while the size changes, its frame count says nothing of
    what it shows (the browser-type stand-in viewer's was noted as a 0 ms turn, its frame seen 424 ms late)."""
    w, worker = follow.make()
    before = _seen(w)
    follow.show((0.0, "2 narrow", _page(2).resize((480, 720))))
    assert worker.kept[-1] == "2 narrow"  # the page is taken as ever ...
    assert _seen(w) == before  # ... and its turn is no measurement


def test_the_time_spent_on_the_first_frame_is_not_taken_off_the_turn(follow):
    """Before, the turn was measured from after the window had worked out its first frame (the thumbnail drawn, the
    page units read for the cache: 30-170 ms on the stand-in), and noted that much short (141 ms for 312)."""
    w, worker = follow.make()
    clock = follow.clock
    cached = w._all_cached

    def slow(image):  # reading the frame's page units takes 120 ms of the Tk thread
        clock.now += 0.12
        return cached(image)

    w._all_cached = slow
    before = _seen(w)
    follow.show((0.0, "3 soft", _page(3, soft=3)), (0.3, "3", _page(3)))
    seen = _seen(w)
    assert len(seen) == len(before) + 1 and 300 <= seen[-1] <= 300 + 2 * FRAME_STEP_MS, seen


def test_a_soft_picture_that_outlasts_settle_ms_is_never_confirmed_and_is_learnt_past_it(follow):
    """The browser-type stand-in viewer draws its soft picture up to 400-420 ms on the screen: with the confirmation
    at most settle_ms (400 ms), and settle_ms for a viewer not seen yet, those soft frames were confirmed and asked the
    model, and their turns were noted as the 15-30 ms to the soft frame."""
    w, worker = follow.make()  # a viewer not seen yet: twice settle_ms
    for k in range(4):
        follow.show((0.0, f"p{k} soft", _page(70 + k, soft=3)), (0.42, f"p{k}", _page(70 + k)))
    seen = _seen(w)[-4:]
    assert all(420 <= ms <= 420 + 2 * FRAME_STEP_MS for ms in seen), seen  # each turn, soft to sharp
    assert confirm_ms(seen[:3], 400) >= 420 + 80  # learnt past settle_ms
    soft = [j for j in worker.jobs if j.name.endswith("soft")]
    assert len(soft) == 4 and all(j.gate.confirmed_at is None and j.asked is None for j in soft)  # none confirmed
    assert worker.kept == ["1", "p0", "p1", "p2", "p3"]


def test_the_learnt_time_is_never_short_of_the_longest_soft_phase(follow):
    w, worker = follow.make()
    for k, soft_ms in enumerate((180, 310, 240)):  # three turns, each soft first, the longest 310 ms
        follow.show((0.0, f"{k} soft", _page(60 + k, soft=3)), (soft_ms / 1000, f"{k}", _page(60 + k)))
    seen = _seen(w)
    assert len(seen) == 3 and all(ms >= soft for ms, soft in zip(seen, (180, 310, 240))), seen
    assert confirm_ms(seen, 400) >= 310 + 80  # the margin on top of the longest, as ever
