"""A page turned in the viewer while a page job runs (follow = "events", the viewer in front: the live view's
`_look_over_job`): one look at another page puts the viewer's frame on the page as it is - the old page's lettering
goes at once - while the job goes on; the job is cancelled only once the new page has stayed as it is for
`live.LEFT_PAGE_MS`, and the new page is then started early - a gate of its own - as soon as the worker is free; a
frame back on the job's page before that letters it again, the job never cancelled. A black flash and frames of the
same page drawn again (a spinner) change nothing. A page job done before its frame was confirmed is shown only once it
is (`JobsMixin._show_held`). The window, the viewer, the clock and the worker are tests/test_early_start.py's; this
worker also fills the page in as the pipeline does (its regions found once it is read, one lettered while the model
answers)."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw
import test_early_start as early
from test_early_start import KEEP_S, READ_S, Worker, _after, follow  # noqa: F401 - the fixture
from test_follow import _page

from taslation.config import Settings
from taslation.ui.constants import FRAME_STEP_MS
from taslation.ui.live import LEFT_PAGE_MS

BOX = (100, 100, 300, 220)  # the page's one region


class FillingWorker(Worker):
    """`Worker`, whose job also fills the page in: its region found once the page is read, lettered halfway through
    the model's answer (as the pipeline's page events do: `JobsMixin._on_page_event`)."""

    def _tick(self, job):
        now, w = self.clock.now, self.w
        if not job.cancel.is_set() and getattr(job, "found", None) is None and now - job.start + 1e-9 >= READ_S:
            job.found = now
            w._handle_event("regions", {"boxes": [BOX], "size": job.frame.size})
            w._flush_fill()
        if (not job.cancel.is_set() and job.asked is not None and getattr(job, "lettered", None) is None
                and now - job.asked + 1e-9 >= early.ASK_S / 2):
            job.lettered = now
            patch = Image.new("RGB", (BOX[2] - BOX[0], BOX[3] - BOX[1]), (200, 30, 30))
            w._handle_event("translated", {"index": 0, "box": BOX, "patch": patch, "text": "-"})
            w._flush_fill()
        super()._tick(job)


class CachedWorker(Worker):
    """`Worker`, whose page's one region is in the cache: lettered from it as soon as the page is read, no model
    asked (as a page partly in the cache is, before its frame is confirmed)."""

    def _tick(self, job):
        w = self.w
        if not job.cancel.is_set() and getattr(job, "found", None) is None and self.clock.now - job.start + 1e-9 >= READ_S:
            job.found = self.clock.now
            w._handle_event("regions", {"boxes": [BOX], "size": job.frame.size})
            patch = Image.new("RGB", (BOX[2] - BOX[0], BOX[3] - BOX[1]), (30, 30, 200))
            w._handle_event("translated", {"index": 0, "box": BOX, "patch": patch, "text": "-"})
            w._flush_fill()
        super()._tick(job)


class FinishingWorker(CachedWorker):
    """`CachedWorker`, whose page is then finished whole (the pipeline's "page" event, its finished picture)."""

    def _tick(self, job):
        lettered = getattr(job, "found", None) is not None
        super()._tick(job)
        if not lettered and getattr(job, "found", None) is not None and job.ended is None:
            self.w._handle_event("page", {"image": job.frame.copy()})
            self.w._flush_fill()


TAIL_S = 2.0  # what a job does after its page is on show (`Pipeline.keep_shown`: the page lettered once more)


class TailWorker(Worker):
    """`Worker`, whose job goes on for TAIL_S once its page is shown and kept, as the window's page job lays the page
    out again for its next showing (`Pipeline.keep_shown`): a cancel ends it CANCEL_S later, with no page_cancelled
    (the page is done; the job only ends)."""

    def _tick(self, job):
        now = self.clock.now
        tail = getattr(job, "tail", None)
        if tail is not None:
            if job.cancel.is_set():
                if job.cancel_seen is None:
                    job.cancel_seen = now
                if now - job.cancel_seen + 1e-9 < early.CANCEL_S:
                    return self._again(job)
                return Worker._end(self, job, "tail cut")
            if now - tail + 1e-9 < TAIL_S:
                return self._again(job)
            return Worker._end(self, job, "done")
        super()._tick(job)

    def _end(self, job, how):
        if how == "done" and job.shown is not None and getattr(job, "tail", None) is None:
            job.tail = self.clock.now  # (shown and kept: what comes after the page begins)
            return self._again(job)
        Worker._end(self, job, how)


@pytest.fixture
def watch(follow, monkeypatch):
    """`follow`, the model answering for 3 s: page 2's job, started at its first frame, is read by 0.3 s, confirmed at
    0.8 s, lettered at 1.8 s and done at 3.3 s - the viewer turns meanwhile."""

    def make():
        w, worker = follow.make()  # (page 1 done as ever)
        monkeypatch.setattr(early, "ASK_S", 3.0)
        w._jobs = worker = FillingWorker(w, follow.clock, worker.name, True)
        w.settings.black_wait_s = Settings().black_wait_s
        return w, worker

    follow.make_watched = make
    return follow


def _shown(w):
    """What the page shows (`_hidden_picture`: what the see-through window letters the viewer with)."""
    return w._hidden_picture()


def _lettered_page(w):
    """The page filling in, lettered, is what the page shows."""
    fill = w._fill
    return fill is not None and fill.page is not None and _shown(w) is fill.page


def _spinner(page, k):
    """*page* with a small spinner over it, turned by *k* steps (the viewer drawing its page again)."""
    img = page.copy()
    d = ImageDraw.Draw(img)
    x, y = img.width // 2, img.height // 2
    d.arc((x - 20, y - 20, x + 20, y + 20), 30 * k, 30 * k + 270, fill=(255, 255, 255), width=5)
    return img


def test_one_look_at_another_page_hides_the_old_lettering_but_does_not_cancel(watch):
    w, worker = watch.make_watched()
    two, three, again = _page(2), _page(3), _page(2)
    watch.show((0.0, "2", two), (2.0, "3", three), (2.1, "2 again", again), run=0.3 + 1.99)
    job = worker.one("2")
    assert _lettered_page(w)  # page 2 being translated, lettered so far
    watch.clock.run(0.03)  # page 3 came: one look (within a frame step)
    assert _shown(w) is three and w._live is three  # the viewer's frame as it is, nothing of page 2 on it
    assert not job.cancel.is_set()  # the job goes on
    watch.clock.run(0.12)  # back on page 2 before page 3 had stayed LEFT_PAGE_MS (150 ms)
    assert _lettered_page(w) and not job.cancel.is_set()  # lettered again
    watch.clock.run(4)
    assert job.how == "done" and worker.kept == ["2"] and [j.name for j in worker.jobs] == ["2"]
    assert w.last_result is job.result


def test_a_new_page_that_stays_cancels_the_job_and_is_started_with_a_gate_of_its_own(watch):
    w, worker = watch.make_watched()
    three = _page(3)
    turned = watch.show((0.0, "2", _page(2)), (2.0, "3", three), run=0.3 + 2.0 + 0.02)
    job = worker.one("2")
    assert _shown(w) is three and not job.cancel.is_set()  # shown at once ...
    watch.clock.run(5)
    # ... cancelled once page 3 stayed LEFT_PAGE_MS (and the step that saw it)
    lag = job.cancel_seen - (turned + 2.0)
    assert job.how == "cancelled" and LEFT_PAGE_MS / 1000 <= lag <= LEFT_PAGE_MS / 1000 + 3 * FRAME_STEP_MS / 1000, lag
    new = worker.one("3")
    assert new.start - job.ended <= 0.016 and new.how == "done" and worker.kept == ["3"]
    # started early as soon as the worker was free: what it stored kept once page 3 stayed twice settle_ms
    assert new.gate is not None and _after(new.gate.confirmed_at - (turned + 2.0), KEEP_S)
    assert new.asked < new.gate.confirmed_at  # (its request did not wait for that)


def test_a_job_past_its_page_gives_way_to_a_new_page_at_once(follow):
    # page 2 read by 0.3 s, confirmed at 0.8 s, answered and shown at 1.3 s; then it is laid out for its next
    # showing until 3.3 s - the viewer turns to page 3 at 2.0 s, meanwhile
    w, worker = follow.make(ask_s=1.0, worker=TailWorker)
    three = _page(3)
    turned = follow.show((0.0, "2", _page(2)), (2.0, "3", three), run=0.3 + 2.0 + 0.002)
    job = worker.one("2")
    assert job.tail is not None and w.last_result is job.result  # page 2 on show, its job past it
    follow.clock.run(4)
    # cancelled at the first look at page 3 (a frame step), not once page 3 had stayed LEFT_PAGE_MS
    lag = job.cancel_seen - (turned + 2.0)
    assert job.how == "tail cut" and lag <= 2 * FRAME_STEP_MS / 1000 + 0.011 < LEFT_PAGE_MS / 1000, lag
    new = worker.one("3")
    assert new.start - job.ended <= 0.016 and new.how == "done" and worker.kept == ["1", "2", "3"]
    assert new.start - (turned + 2.0) < LEFT_PAGE_MS / 1000  # (before, at LEFT_PAGE_MS and the job's end after it)
    assert new.gate is not None and _after(new.gate.confirmed_at - (turned + 2.0), KEEP_S)  # a gate of its own
    assert not any("Stopped" in str(s) for s in w.statuses)  # (no page was stopped: page 2 was done)


def test_a_job_still_on_its_page_is_not_cut_short_by_a_frame_that_does_not_stay(follow):
    # page 2's job before its result: a frame of page 3 for 0.1 s changes nothing (LEFT_PAGE_MS as ever)
    w, worker = follow.make(ask_s=1.0, worker=TailWorker)
    follow.show((0.0, "2", _page(2)), (1.0, "3", _page(3)), (1.1, "2 again", _page(2)), run=0.3 + 1.0 + 0.5)
    job = worker.one("2")
    assert job.cancel_seen is None and job.shown is not None
    follow.clock.run(3)
    assert job.how == "done" and [j.name for j in worker.jobs] == ["1", "2"] and w.last_result is job.result


def test_a_page_that_sharpens_while_the_cancelled_job_goes_is_on_show_and_read_sharp(watch, monkeypatch):
    monkeypatch.setattr(early, "CANCEL_S", 0.5)  # a job slow to stop (a request on its way)
    w, worker = watch.make_watched()
    soft, sharp = _page(3, soft=3), _page(3)
    turned = watch.show((0.0, "2", _page(2)), (2.0, "3 soft", soft), (2.45, "3", sharp), run=0.3 + 2.0 + 0.47)
    job = worker.one("2")
    assert job.cancel.is_set() and job.ended is None  # cancelled once the soft frame had stayed, still going ...
    assert w._live is sharp and _shown(w) is sharp  # ... while the sharp picture is on show as it came
    watch.clock.run(4)
    assert [j.name for j in worker.jobs] == ["2", "3"] and worker.kept == ["3"]  # read from the sharp frame alone
    assert _after(worker.one("3").gate.confirmed_at - (turned + 2.45), KEEP_S)


def test_a_page_that_sharpens_while_nothing_looks_is_read_sharp(watch, monkeypatch):
    monkeypatch.setattr(early, "CANCEL_S", 0.5)
    w, worker = watch.make_watched()
    watch.show((0.0, "2", _page(2)), (2.0, "3 soft", _page(3, soft=3)), run=0.3 + 2.0 + 0.2)
    assert worker.one("2").cancel.is_set()
    w._following.owner = "own"  # TASlation in front ...
    watch.show((-0.05, "3", _page(3)), run=4)  # ... and the page sharpens while the job goes
    assert [j.name for j in worker.jobs] == ["2", "3"] and worker.kept == ["3"]


def test_a_black_flash_over_the_page_being_translated_changes_nothing(watch):
    w, worker = watch.make_watched()
    two = _page(2)
    black = Image.new("RGB", two.size, "black")
    watch.show((0.0, "2", two), (1.9, "black", black), (2.7, "2 after", _page(2)), run=0.3 + 2.3)
    job = worker.one("2")
    assert _lettered_page(w) and not job.cancel.is_set()  # through the flash: lettered, the job going on
    watch.clock.run(0.5)
    assert _lettered_page(w) and not job.cancel.is_set()  # the page back after it
    watch.clock.run(4)
    assert job.how == "done" and worker.kept == ["2"] and [j.name for j in worker.jobs] == ["2"]


def test_a_spinner_over_the_page_being_translated_changes_nothing(watch):
    w, worker = watch.make_watched()
    two = _page(2)
    spinning = [(1.9 + 0.05 * k, f"2 spinner {k}", _spinner(two, k)) for k in range(25)]
    watch.show((0.0, "2", two), *spinning, (3.15, "2 after", _page(2)), run=0.3 + 2.6)
    job = worker.one("2")
    assert _lettered_page(w) and not job.cancel.is_set()
    watch.clock.run(4)
    assert job.how == "done" and worker.kept == ["2"] and [j.name for j in worker.jobs] == ["2"]


def test_a_page_done_before_its_frame_is_confirmed_shows_only_once_it_is(follow):
    # every line reused: the page is done at READ_S, before the confirmation (twice settle_ms)
    w, worker = follow.make(asks=False)
    follow.show((0.0, "2", _page(2)), run=0.3 + READ_S + 0.02)
    job = worker.one("2")
    assert job.shown is not None and job.gate.state == "pending"
    assert w.last_result is not job.result and w._held_result is not None  # done, not shown: no "translated" yet
    statuses = len(w.statuses)
    follow.clock.run(KEEP_S - READ_S + 0.03)
    assert job.gate.confirmed_at is not None and w.last_result is job.result and w._held_result is None
    assert len(w.statuses) > statuses


def test_lettering_laid_on_a_soft_frame_goes_from_the_page_as_the_sharp_frame_comes(follow, monkeypatch):
    monkeypatch.setattr(early, "CANCEL_S", 0.2)  # the job on the soft frame slow to go
    w, worker = follow.make()  # the soft frame is never confirmed
    w._jobs = worker = CachedWorker(w, follow.clock, worker.name, True)
    soft, sharp = _page(4, soft=3), _page(4)
    follow.show((0.0, "4 soft", soft), (READ_S + 0.05, "4", sharp), run=0.3 + READ_S + 0.02)
    assert _lettered_page(w) and w._fill.frame is soft  # what the cache holds, lettered on the blurry picture ...
    follow.clock.run(0.05)
    assert worker.one("4 soft").ended is None and _shown(w) is sharp  # ... not on show once the sharp frame came
    follow.clock.run(0.2 + READ_S + 0.05)
    assert _lettered_page(w) and w._fill.frame is sharp  # lettered again on the sharp frame


def test_a_page_finished_before_its_frame_is_confirmed_stays_filling_in_until_then(follow):
    w, worker = follow.make(asks=False)
    w._jobs = worker = FinishingWorker(w, follow.clock, worker.name, False)
    follow.show((0.0, "2", _page(2)), run=0.3 + READ_S + 0.02)
    job = worker.one("2")
    assert job.gate.state == "pending" and job.shown is not None  # finished: its picture and its result came ...
    assert _lettered_page(w) and w._fill.final is None and w.last_result is not job.result  # ... neither on show
    follow.clock.run(KEEP_S - READ_S + 0.03)
    assert job.gate.confirmed_at is not None and w.last_result is job.result and w._fill is None


def test_a_page_done_on_a_frame_then_dropped_is_never_shown(follow):
    w, worker = follow.make(asks=False)
    shown = []
    redisplay = w._redisplay
    w._redisplay = lambda: shown.append(w.last_result) or redisplay()
    soft, sharp = _page(4, soft=3), _page(4)
    follow.show((0.0, "4 soft", soft), (READ_S + 0.05, "4", sharp))
    first, second = worker.one("4 soft"), worker.one("4")
    assert first.shown is not None and first.discarded  # done on the soft frame, dropped with it ...
    assert all(r is not first.result for r in shown)  # ... and never on the page
    assert w.last_result is second.result and w._held_result is None
