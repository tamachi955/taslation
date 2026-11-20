"""The indicator beside the page joined to the engine: the REAL `taslation.backlog.Backlog` (its `screen_for`, `tell`,
`show`, `totals`, `catch`, `drop`, `merge_missed`, `close`) posting into the window's own event handler
(`App._handle_event` through `JobsMixin._handle_event` and `backlog.reading_event` to the ``_on_reading_<kind>``
handlers), the events drained as the window's event pump drains them. The window is `test_side_indicator.Window`
(the page area, the strip and the status bar of the window, with the indicator built as `App` builds it); the pages
are made-up ones (`fake_side`); no viewer, no model, nothing sent to any window."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fake_side import fingerprint, page, result
from fake_strip import thumb
from test_side_indicator import Window, no_way_to_the_viewer  # noqa: F401 - the window, and its fixture

from taslation.backlog import Backlog, backlog_of, drop_backlog, merge_missed
from taslation.ui import app as app_mod
from taslation.ui.side_model import summary_lines
from taslation.ui.strip import new_run

WITHIN = 4  # the fingerprint distance the backlog is given here (the window's own is 36: another book is far)


def unit(fp: str) -> SimpleNamespace:
    """A capture's first page unit, as `Backlog.screen_for` reads it."""
    return SimpleNamespace(fingerprint=fp, aspect=0.7)


def near(fp: str, bits: int) -> str:
    """*fp* with its *bits* lowest bits flipped."""
    return format(int(fp, 16) ^ ((1 << bits) - 1), f"0{len(fp)}x")


@pytest.fixture
def seam(hidden_root, no_way_to_the_viewer):  # noqa: F811
    made = []

    def make(**kw):
        w = Window(hidden_root, **kw)
        hidden_root.update()
        posted: list = []
        post = w._post

        def recorded(kind, **data):
            posted.append((kind, data))
            post(kind, **data)

        w._post = recorded
        backlog = backlog_of(w)  # (made as the window's first page job makes it: its events to the window's _post)
        assert isinstance(backlog, Backlog) and w._backlog is backlog
        made.append((w, backlog))
        return w, backlog, posted

    yield make
    for w, backlog in made:
        backlog.close()
        w.destroy()


def tell_on_show(b: Backlog, screen, image, read_done: bool = False) -> None:
    """A page job's screen confirmed on show, as `Tracking._report` tells it."""
    b.tell(screen, "read", "done" if read_done else "working", image)
    if read_done:
        b.tell(screen, "translate", "working", image)
    b.show(screen)
    b.totals()


def test_a_screen_told_its_stages_the_page_on_show_and_the_totals(seam):
    w, b, posted = seam(size=(1560, 900))
    model = w._side.model
    s1 = b.screen_for([unit(fingerprint(1))], WITHIN)
    w.show(page(1))
    tell_on_show(b, s1, page(1))
    w.pump()
    assert all(d.get("reading") for _k, d in posted)  # (the shape the engine gives them)
    assert model.order == [1] and model.on_show == 1 and model.screens[1].mark == "working"
    assert model.screens[1].thumb is not None and model.screens[1].thumb.height <= 80  # memory only, small
    b.tell(s1, "read", "done", page(1))
    b.tell(s1, "translate", "working", page(1))
    w.pump()
    assert model.screens[1].stages == {"read": "done", "translate": "working"}
    view = w._side.view
    assert view.shown and view.layout.kind == "column" and view.animating  # its stripe moves
    # turned past while it was at work: caught, its frame to read behind the reader
    s2 = b.screen_for([unit(fingerprint(2))], WITHIN)
    w.show(page(2))
    tell_on_show(b, s2, page(2))
    assert b.catch(s1, page(1), None, None, hwnd=1)
    b.tell(s1, "read", "waiting", page(1))
    b.tell(s1, "translate", "waiting", page(1))
    b.totals()
    w.pump()
    assert model.order == [1, 2] and model.on_show == 2 and model.screens[1].mark == "waiting"
    assert model.backlog.pages == 1
    assert "Working on the others: 1 page(s), 0 line(s) to go." in summary_lines(model, 0.0)
    assert w._strip_model.pages == {}  # normal reading's screens never reach the run's strip


def test_the_work_behind_finishing_a_page_seen_marks_it_updated_from_the_cache(seam):
    w, b, _posted = seam(size=(1560, 900))
    s1 = b.screen_for([unit(fingerprint(1))], WITHIN)
    seen = result(1, ["Who's there?", "", "Wait!"])
    w.show(seen.original)
    tell_on_show(b, s1, seen.original, read_done=True)
    w.pump()
    w.show(seen.original, seen)  # seen lettered, one bubble still in its original
    assert 1 in w._side.seen.shown
    s2 = b.screen_for([unit(fingerprint(2))], WITHIN)
    w.show(page(2))
    tell_on_show(b, s2, page(2))
    assert b.catch(s1, seen.original, None, None, hwnd=1)
    w.pump()
    entry = next(e for e in b.entries if e.screen is s1)
    w.cache.put(1, ["Who is there?", "Look.", "Wait!"])  # stored first (`_Host._store_unit`) ...
    b._finish(entry, "translate", "done")  # ... then told done
    w.pump()
    w.update()  # (the cache is looked at once the events are in)
    assert w._side.model.screens[1].updated and w._side.model.screens[1].mark == "done"


def test_a_screen_that_went_by_one_not_caught_and_one_merged_into_the_next(seam):
    w, b, _posted = seam(size=(1560, 900))
    model = w._side.model
    s1 = b.screen_for([unit(fingerprint(1))], WITHIN)
    tell_on_show(b, s1, page(1))
    gone = b.screen_for([unit(fingerprint(2))], WITHIN)  # went by too fast: told without a picture
    gone.missed = True
    b.tell(gone, "read", "missed")
    b.totals()
    w.pump()
    assert model.screens[2].mark == "missed" and model.screens[2].thumb is None
    assert model.screens[2].state("translate") == "missed" and model.backlog.dropped == 1
    w.show(page(1))
    assert any("1 turned too fast" in line for line in summary_lines(model, 0.0))
    # a soft picture that went by, then its page confirmed: the placeholder merged into it
    soft = b.screen_for([unit(near(fingerprint(3), 6))], WITHIN)
    soft.missed = True
    b.tell(soft, "read", "missed")
    sharp = b.screen_for([unit(fingerprint(3))], WITHIN)
    assert sharp is not soft  # (6 bits apart: another screen at WITHIN, the same page at twice that)
    b.tell(sharp, "read", "working", page(3))
    merge_missed(b, sharp, WITHIN)
    b.show(sharp)
    b.totals()
    w.pump()
    assert soft.seq == 3 and 3 not in model.screens and model.order == [1, 2, 4] and model.on_show == 4
    # on show, turned past and not caught: its read done, its translation "missed" - read when shown again
    b.tell(sharp, "read", "done", page(3))
    b.tell(sharp, "translate", "missed", page(3))
    sharp.missed = True
    b.totals()
    w.pump()
    assert model.screens[4].mark == "missed" and model.screens[4].thumb is not None
    assert model.backlog.dropped == 2
    assert [line for line in summary_lines(model, 0.0) if "too fast" in line] == [
        "2 turned too fast to catch: turn back to them in the viewer to have them read."]


def test_the_page_on_show_before_its_screen_is_numbered_is_none(seam):
    w, b, _posted = seam(size=(1560, 900))
    s1 = b.screen_for([unit(fingerprint(1))], WITHIN)
    tell_on_show(b, s1, page(1))
    w.pump()
    b.show(b.screen_for([unit(fingerprint(2))], WITHIN))  # its units known, its frame not confirmed yet
    w.pump()
    assert w._side.model.on_show is None and 2 not in w._side.model.screens


def test_a_drop_then_a_new_screen_one_of_another_book(seam):
    w, b, posted = seam(size=(1560, 900))
    model = w._side.model
    for n in (1, 2, 3):
        tell_on_show(b, b.screen_for([unit(fingerprint(n))], WITHIN), page(n))
    w.pump()
    w.show(page(3))
    assert model.order == [1, 2, 3]
    told = len(posted)
    b.drop("another book")
    w.pump()
    if any(k == "backlog" and d.get("dropped") is True for k, d in posted[told:]):
        assert len(model) == 0 and model.on_show is None  # (the drop told: everything went at once)
    else:  # (a drop told only by its totals: the screen on show is none of the book's until the next one comes)
        assert model.on_show is None
    other = b.screen_for([unit(fingerprint(101))], WITHIN)
    w.show(page(101))
    tell_on_show(b, other, page(101))
    w.pump()
    assert other.seq == 1  # (numbered from 1 again)
    assert model.order == [1] and model.screens[1].fingerprint == fingerprint(101) and model.on_show == 1


def test_a_drop_told_as_such_clears_and_the_totals_after_it_count(seam):
    w, b, _posted = seam(size=(1560, 900))
    model = w._side.model
    for n in (1, 2):
        tell_on_show(b, b.screen_for([unit(fingerprint(n))], WITHIN), page(n))
    w.pump()
    model.screens[1].updated = True
    w._post("backlog", pages=0, lines=0, paused=False, dropped=True, reading=True)  # (the drop: `Backlog.drop`)
    w.pump()
    assert len(model) == 0 and model.backlog.dropped == 0 and not w._side.seen.shown
    w._post("backlog", pages=2, lines=9, paused=True, dropped=1, reading=True)  # (the totals after it)
    w.pump()
    assert (model.backlog.pages, model.backlog.lines, model.backlog.paused, model.backlog.dropped) == (2, 9, True, 1)


def test_a_whole_book_run_starting_puts_the_indicator_away_and_its_stages_go_to_the_strip(seam):
    w, b, _posted = seam(size=(1560, 900))
    screens = [b.screen_for([unit(fingerprint(n))], WITHIN) for n in (1, 2)]
    for n, s in zip((1, 2), screens):
        tell_on_show(b, s, page(n))
    w.pump()
    w.show(page(2))
    assert w._side.view.shown and len(w._side.model) == 2
    # as `JobsMixin._start_batch` starts a run
    drop_backlog(w, "a whole-book run")
    w._batching = True
    new_run(w)
    w._post("page_stage", seq=1, fingerprint=fingerprint(201), stage="read", state="working",
            thumb=thumb(page(201)))  # the run's own: no ``reading``
    b.tell(screens[0], "translate", "done")  # a step of the backlog that ended after the drop: a dropped screen
    w.pump()
    w.show(page(201))
    assert 1 in w._strip_model.pages and w._strip_model.pages[1].stages["read"] == "working"
    assert len(w._side.model) == 0 and not w._side.view.shown
    assert w.canvas._shown[0] == (1560 - 600) // 2  # nothing kept clear during the run


def test_the_window_closing_closes_its_backlog_and_never_fails_for_it(seam):
    w, b, posted = seam()
    tell_on_show(b, b.screen_for([unit(fingerprint(1))], WITHIN), page(1))
    w.pump()
    app_mod.close_backlog(w)  # (`App._on_close`)
    assert b.screens == [] and b._packer._shutdown  # dropped, its thread let go
    assert posted[-1][0] in ("page_on_show", "backlog")  # (what the drop tells: the window is gone by then)

    def refuse():
        raise RuntimeError("made-up")

    app_mod.close_backlog(SimpleNamespace(_backlog=SimpleNamespace(close=refuse)))  # never in the way of the close
    app_mod.close_backlog(SimpleNamespace())  # (a window without a backlog)
    assert backlog_of(SimpleNamespace(), make=False) is None


def test_an_event_the_indicator_cannot_take_never_reaches_the_event_pump(seam, monkeypatch):
    from taslation.ui import side as side_mod

    w, _b, _posted = seam()
    monkeypatch.setattr(side_mod, "on_stage", lambda *_a: 1 / 0)
    w._post("page_stage", seq=1, fingerprint=fingerprint(1), stage="read", state="working", reading=True)
    w._post("page_on_show", seq="not a number", reading=True)
    w._post("backlog", pages=None, lines="x", paused=None, dropped=None, reading=True)
    w.pump()  # (nothing raised)
    assert w._side.model.on_show is None and w._side.model.backlog.pages == 0
