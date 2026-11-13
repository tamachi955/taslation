"""A reader who turns pages fast loses none, and is told at once of a page that went by too quickly to be taken.

The sampler follows every new frame (the capture's frame events, `wgc.wait`) and only captures and compares
(`batch.PageWatch`); packing and fingerprints run on the packer's thread. Measured with the stand-in viewer of
`tools/fast_turn_eval.py` (synthetic pages here; OpenMantra pages with the tool itself): no page lost at 2 pages a second,
also on a viewer that draws every page soft first for 150-400 ms, and at 3 a second every page not taken is told
(``page_missed``), never taken soft. A page that went by gets its seq and ``page_stage`` read "missed"; turning back to
it takes it under that seq."""
from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import fast_turn_eval  # noqa: E402

from taslation import batch as batch_mod  # noqa: E402
from taslation.batch import BatchReader  # noqa: E402
from taslation.capture import wgc  # noqa: E402
from taslation.messages import TEMPLATES, Message, render  # noqa: E402
from taslation.message_texts import LANGUAGES  # noqa: E402
from taslation.pageimages import PageImages, pack, unpack  # noqa: E402


@pytest.fixture(scope="module")
def book():
    raw = [fast_turn_eval.synthetic(i) for i in range(12)]
    sharp = [fast_turn_eval.framed(p, i, len(raw)) for i, p in enumerate(raw)]
    return sharp, [fast_turn_eval.soft_of(f) for f in sharp]


@pytest.mark.parametrize("soft_first", (False, True))
def test_no_page_is_lost_at_two_pages_a_second(book, soft_first):
    sharp, soft = book
    got = fast_turn_eval.measure(sharp, soft if soft_first else None, 2.0, seed=1)
    assert got["taken_sharp"] == len(sharp) and got["told"] == 0 and got["false_soft"] == 0
    assert got["soft_never_sharp"] == 0 and got["unknown"] == 0


def test_at_three_a_second_every_page_not_taken_is_told_and_none_is_taken_soft(book):
    sharp, soft = book
    got = fast_turn_eval.measure(sharp, soft, 3.0, seed=2)
    assert got["untold"] == 0 and got["false_soft"] == 0 and got["told"] == got["not_taken"]
    plain = fast_turn_eval.measure(sharp, None, 3.0, seed=2)  # a viewer that draws sharp at once: none lost
    assert plain["taken_sharp"] == len(sharp) and plain["told"] == 0


@pytest.fixture(scope="module")
def chrome_book():
    from test_follow import _page

    # strokes of ink: their soft pictures as Chrome draws them differ from the sharp ones by 2.1-2.3 on the plain
    # thumbnails, as the e2e viewer's pages did (`fast_turn_eval.chrome_soft`)
    raw = [_page(i + 1, size=(830, 1170)) for i in range(12)]
    return ([fast_turn_eval.framed(p, i, len(raw)) for i, p in enumerate(raw)],
            [fast_turn_eval.framed(p, i, len(raw), chrome=True) for i, p in enumerate(raw)])


@pytest.mark.parametrize("rate", (1.0, 2.0))
def test_on_a_viewer_that_draws_soft_as_chrome_does_every_page_is_taken_once_and_none_said_to_have_gone_by(
        chrome_book, rate):
    sharp, soft = chrome_book
    got = fast_turn_eval.measure(sharp, soft, rate, seed=4)
    assert got["taken_sharp"] == len(sharp) and got["told"] == 0 and got["false_missed"] == 0
    assert got["cells"] == len(sharp) and got["taken_twice"] == 0 and got["placeholders_left"] == 0
    assert got["false_soft"] == 0 and got["unknown"] == 0


def test_without_frame_events_two_pages_a_second_lose_nothing(book):
    sharp, soft = book
    got = fast_turn_eval.measure(sharp, soft, 2.0, seed=3, poll=True, capture_ms=30)
    assert got["taken_sharp"] == len(sharp) and got["told"] == 0 and got["false_soft"] == 0


def _reader(settings, shown):
    settings.margins = (0, 0, 0, 0)
    return BatchReader(SimpleNamespace(ocr=None, translator=None), hwnd=1, settings=settings, preflight=[],
                       show=lambda kind, data: shown.append((kind, data)))


def test_a_page_that_went_by_is_said_marked_and_taken_under_its_seq_when_the_reader_turns_back(book, settings):
    sharp, soft = book
    shown: list = []
    reader = _reader(settings, shown)
    said = []
    reader.on_progress = lambda p, _r: said.append((getattr(p.message, "code", ""), p.waiting))
    assert reader._take(sharp[0])
    reader._went_by(soft[1])  # page 2 went by soft
    assert reader._take(sharp[2])
    stages = [(d["seq"], d["state"]) for kind, d in shown if kind == "page_stage"]
    assert stages == [(1, "waiting"), (2, "missed"), (3, "waiting")]
    missed = [d for kind, d in shown if kind == "page_missed"]
    assert len(missed) == 1 and missed[0]["seq"] == 2 and missed[0]["pages"] == 1
    assert isinstance(missed[0]["thumb"], Image.Image) and missed[0]["thumb"].height <= 96
    assert reader.progress.waiting.code == "batch.page_missed" and reader.progress.missed == 1
    reader._went_by(soft[1])  # the same page going by again is told once
    assert len([1 for kind, _d in shown if kind == "page_missed"]) == 1
    assert reader._take(sharp[1])  # the reader turned back to it
    assert [(d["seq"], d["state"]) for kind, d in shown if kind == "page_stage"][-1] == (2, "waiting")
    assert reader.progress.waiting is None and reader.progress.missed == 0 and reader._retaken
    assert ("batch.missed_taken", None) in said and said[-1][1] is None
    keys = [reader._backlog.get_nowait().key for _ in range(3)]
    assert keys == [1, 3, 2] and reader._seq == 3
    reader._went_by(sharp[0])  # a page this run has taken is no page gone by
    assert len([1 for kind, _d in shown if kind == "page_missed"]) == 1


def test_a_page_that_went_by_and_is_known_all_the_same_leaves_no_placeholder(book, settings):
    sharp, soft = book
    shown: list = []
    reader = _reader(settings, shown)
    assert reader._take(sharp[0])
    reader._went_by(soft[1])  # page 2 went by soft: a placeholder, seq 2
    assert reader.progress.missed == 1
    reader.progress.seen.extend(reader._fingerprints(sharp[1]))  # an earlier run had read it
    assert reader._take(sharp[1])  # the reader turned back: nothing to read, and the placeholder goes
    assert [(d["seq"], d["state"]) for kind, d in shown if kind == "page_stage"][-1] == (2, "merged")
    assert reader.progress.missed == 0 and reader.progress.waiting is None and reader.stage_of(2, "read") == ""
    reader._close_stages()
    assert not [d for kind, d in shown if kind == "page_stage" and d["seq"] == 2 and d["state"] == "skipped"]


def test_at_the_end_of_the_reading_a_placeholder_of_a_page_taken_under_another_seq_is_merged(book, settings):
    sharp, soft = book
    shown: list = []
    reader = _reader(settings, shown)
    assert reader._take(sharp[0])
    reader._went_by(soft[1])  # seq 2
    assert reader._take(sharp[2])  # seq 3
    fps, page, d = reader._missed[2]
    reader._missed[2] = (("f" * 64,), batch_mod.page_thumb(batch_mod.thumbnail(sharp[2])), d)  # (as page 3 went by)
    reader._merge_taken_missed()
    merged = [(d["seq"], d["stage"], d.get("into")) for kind, d in shown
              if kind == "page_stage" and d["state"] == "merged"]
    assert merged == [(2, "read", 3)]
    assert not reader._missed and reader.progress.missed == 0
    reader._went_by(soft[1])  # a page that truly went by stays said
    reader._merge_taken_missed()
    assert reader.progress.missed == 1


def test_a_missed_page_ends_as_missed_and_the_run_notes_it(book, settings):
    sharp, soft = book
    reader = _reader(settings, [])
    reader._take(sharp[0])
    reader._went_by(soft[1])
    reader._close_stages()
    assert reader.stage_of(2, "read") == "missed" and reader.stage_of(2, "translate") == "skipped"
    text = render(Message("batch.page_missed", pages=1))
    assert "1 page" in text and "turn back" in text


def test_the_new_messages_are_in_every_language():
    for code in ("batch.page_missed", "batch.missed_taken", "batch.note_missed"):
        assert code in TEMPLATES
        for lang in LANGUAGES:
            catalog = importlib.import_module("taslation.message_texts." + lang.replace("-", "_")).TEMPLATES
            assert code in catalog, (lang, code)
            if code != "batch.missed_taken":
                assert "{pages" in catalog[code], (lang, code)


def test_a_sharper_picture_replaces_a_frame_only_while_it_waits_to_be_read():
    images = PageImages(10 * 1024 * 1024)
    soft = Image.fromarray(np.full((40, 30, 3), 100, np.uint8))
    sharp = Image.fromarray(np.full((40, 30, 3), 200, np.uint8))
    assert images.put_frame(1, pack(soft))
    assert images.replace_unread(1, pack(sharp)) and np.asarray(images.frame(1))[0, 0, 0] == 200
    images.read(1, erase=False)
    assert not images.replace_unread(1, pack(soft)) and np.asarray(images.frame(1))[0, 0, 0] == 200
    assert not images.replace_unread(2, pack(soft))
    assert unpack(pack(sharp)).size == (30, 40)


def test_the_frame_events_wake_a_waiter_at_the_next_frame(monkeypatch):
    session = wgc._Session.__new__(wgc._Session)
    session.hwnd, session._seq, session._frame, session.ended_at = 5, 3, object(), None
    session._changed = threading.Condition()
    monkeypatch.setattr(wgc, "_session", session)
    assert wgc.wait(5, 2, 1.0) == 3  # already past: at once
    assert wgc.wait(5, 3, 0.01) == 3  # none came: as it is, after the wait (every time)
    assert wgc.wait(5, 3, 0.01) == 3
    assert wgc.wait(6, 3, 1.0) is None  # no session of that window: the caller looks for itself

    def arrive():
        with session._changed:
            session._seq = 4
            session._changed.notify_all()

    timer = threading.Timer(0.05, arrive)
    timer.start()
    assert wgc.wait(5, 3, 5.0) == 4
    timer.join()
    session.ended_at = 1.0
    assert wgc.wait(5, 4, 1.0) is None
