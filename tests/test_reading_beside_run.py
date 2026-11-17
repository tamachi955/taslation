"""Reading the viewer's pages while a whole-book run translates: once the run has done the reading it needs the viewer
no more (`BatchReader.viewer_free`), and the window follows the viewer as without a run. A page the run has stored
shows translated, drawn from the cache with no model request (`BatchReader.viewer_page`); a page not translated yet
shows the viewer's frame with a line that says so, and asks nothing of the worker or the model; the reading stage is
as before; once the run is over, the window reads as ever. The run is the real `BatchReader` on stand-in pages (no
book's page) for the run's side, and the window is the App's live view borrowed onto the stand-in of
tests/test_follow.py, on its fake clock; no real window, nothing under the real state folder."""
from __future__ import annotations

import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image

from taslation import batch as batch_mod
from taslation.batch import BatchReader, ViewerPage
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import live
from taslation.ui.constants import viewer_rests
from taslation.ui.strip import RunPage

from test_batch_follows_reader import desk  # noqa: F401 - (a fixture)
from test_follow import _page, setup  # noqa: F401 - (a fixture, the viewer's stand-in pages)


# ------------------------------------------------------------------ the run's side
class Gated(DictTranslator):
    """A model whose second request waits for *gate*: the first page is stored, the others are not yet."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.gate, self.asked = threading.Event(), threading.Event()
        self.free_at: list[bool] = []
        self.reader: BatchReader | None = None

    def translate_page(self, texts, *args, **kwargs):
        out = super().translate_page(texts, *args, **kwargs)
        self.free_at.append(bool(self.reader is not None and self.reader.viewer_free))
        if len(self.calls) == 2:
            self.asked.set()
            self.gate.wait(20)
        return out


def _run_in_hand(reader, desk):
    done: list = []
    thread = threading.Thread(target=lambda: done.append(read_book(reader, desk)), daemon=True)
    thread.start()
    return thread, done


def test_the_page_the_viewer_shows_is_drawn_from_the_cache_while_the_run_translates_the_rest(
        desk, settings, sample_page, sample_page2, monkeypatch):
    settings.chunk_bubbles = 1  # a request a page: page 1 is stored before page 2 is asked for
    desk.pages[:] = [sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT)]
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    model = Gated(EN_TEXTS)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=model, cache=cache)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[],
                         show=lambda kind, data: None)
    model.reader = reader
    free_while_captured: list[bool] = []
    capture = batch_mod.capture_window

    def captured(*args, **kwargs):  # (the run's own captures: all of them while it reads)
        free_while_captured.append(reader.viewer_free)
        return capture(*args, **kwargs)

    monkeypatch.setattr(batch_mod, "capture_window", captured)
    written: list[int] = []
    for name in ("add", "save", "put", "set_page", "update", "remove"):
        original = getattr(type(cache), name, None)
        if original is None:
            continue

        def spy(self, *args, _original=original, **kwargs):
            written.append(threading.get_ident())
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(type(cache), name, spy)
    assert not reader.viewer_free
    thread, done = _run_in_hand(reader, desk)
    try:
        assert model.asked.wait(30)
        assert reader.viewer_free and free_while_captured and not any(free_while_captured)
        requests = len(model.calls)
        page1 = reader.viewer_page(desk.pages[0])  # stored already
        assert page1.state == "translated" and page1.seq == 1
        assert np.array_equal(np.asarray(page1.image), np.asarray(pipeline.page_picture(reader.images, 1)))
        assert not np.array_equal(np.asarray(page1.image), np.asarray(desk.pages[0]))  # lettered
        assert np.array_equal(np.asarray(page1.frame), np.asarray(desk.pages[0]))  # on the page as captured
        assert [p.state for p in (reader.viewer_page(desk.pages[1]), reader.viewer_page(desk.pages[2]))] == [
            "waiting", "waiting"]  # being translated, still to come
        other = reader.viewer_page(sample_page2.transpose(Image.FLIP_LEFT_RIGHT))  # a page the run never read
        assert other.state == "untranslated" and other.seq == 0 and other.image is None
        assert reader.viewer_page(Image.new("RGB", sample_page.size, "white")).state == "none"
        assert len(model.calls) == requests  # no request of its own
        assert threading.get_ident() not in written  # nothing stored or written from the window's side
    finally:
        model.gate.set()
        thread.join(30)
    assert done and done[0].summary.code == "batch.finished"
    assert model.free_at and all(model.free_at)  # (the translation, all of it, with the viewer free)


def test_a_page_lettered_before_in_the_session_comes_from_the_memo_of_its_pixels(settings, sample_page):
    """A page the cache holds that is not one of the run's (read before it, page by page) shows from the session's
    memo of the very pixels; without one, it is "later": no detection or erase runs for it beside the run."""
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    pipeline.process(sample_page)  # read page by page before the run: translated, stored ...
    shown = pipeline.process(sample_page)  # ... and shown again from the cache: kept in the memo
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[])
    reader.viewer_free = True
    detect = pipeline._detect
    pipeline._detect = lambda *a, **k: (_ for _ in ()).throw(AssertionError("detection beside the run"))
    try:
        page = reader.viewer_page(sample_page)
        assert page.state == "translated" and page.seq == 0
        assert np.array_equal(np.asarray(page.image), np.asarray(shown.image))
        pipeline.shown_pages.clear()
        assert reader.viewer_page(sample_page).state == "later"
    finally:
        pipeline._detect = detect


def test_the_readers_keys_go_on_while_the_run_reads_and_again_once_it_translates():
    run = SimpleNamespace(following=False, viewer_free=False)
    window = SimpleNamespace(batch=run, _batching=True)
    assert viewer_rests(window)  # done reading, the erase ahead to finish: the viewer rests
    run.viewer_free = True
    assert not viewer_rests(window)  # translating: the viewer is the reader's again
    run.viewer_free, run.following = False, True
    assert not viewer_rests(window)


# ------------------------------------------------------------------ the window's side
class Run:
    """The run as the window sees it while it translates: *answers* maps a frame to what `viewer_page` says."""

    def __init__(self):
        self.following, self.viewer_free = True, False
        self.answers: dict[int, ViewerPage] = {}
        self.asked: list[Image.Image] = []
        self.threads: list[str] = []

    def viewer_page(self, frame):
        self.asked.append(frame)
        self.threads.append(threading.current_thread().name)
        return self.answers.get(id(frame), ViewerPage("untranslated"))

    def stop(self):
        pass


def _beside_window(setup, **kwargs):
    w = setup.make(**kwargs)
    w._events = queue.Queue()
    w.batch, w._batching = Run(), True
    w._go_busy()  # (a run keeps the window busy from its start to its end)
    w.start()
    return w, w.batch


def pump(w):
    """The run's answers taken in on the Tk side, as the event pump does (`JobsMixin._poll_events`)."""
    b = getattr(w, "_beside", None)
    end = time.monotonic() + 5
    while b is not None and b.thread is not None and time.monotonic() < end:
        time.sleep(0.005)
    while True:
        try:
            kind, data = w._events.get_nowait()
        except queue.Empty:
            return
        w._handle_event(kind, data)


def sent(viewer):
    """The keys that went to the viewer, posted or pressed (a viewer of real keys gets them in one handover)."""
    return [key for _t, key in sorted(viewer.keys + viewer.pressed)]


def lettered(frame):
    out = frame.copy()
    out.paste((255, 0, 0), (10, 10, 200, 60))
    return out


def test_while_the_run_translates_a_page_turned_in_the_viewer_shows_from_the_cache_or_says_it_is_not_translated(setup):
    v = setup.viewer
    page1 = v.frames[0][1]
    w, run = _beside_window(setup, owner="viewer", auto=False)
    setup.clock.run(5)  # the run reads the pages: it captures them, the window nothing
    assert v.captures == [] and getattr(w, "_beside", None) is None
    run_view = RunPage(4, page1, lettered(page1))  # the run's page being translated, on the page area
    w._run_view = run_view
    run.following, run.viewer_free = False, True  # Finished reading: the translation
    setup.clock.run(1)
    assert v.captures and w._beside is not None and w._beside.base is not None
    assert run.asked == [] and w._picture()[0] is run_view.image  # the page on show: the run's progress stays
    page2, page3 = _page(2), _page(3)
    run.answers[id(page2)] = ViewerPage("translated", lettered(page2), page2, seq=2)
    run.answers[id(page3)] = ViewerPage("waiting", seq=3)

    v.frames.append((setup.clock.now + 0.2, page2))  # the reader turns the page in the viewer
    setup.clock.run(3)
    pump(w)
    assert run.asked == [page2] and set(run.threads) == {"beside-run-page"}  # asked of the run, off the Tk thread
    assert getattr(w, "_run_view", None) is None  # the run's page left the page area
    image = w._picture()[0]
    assert np.array_equal(np.asarray(image), np.asarray(run.answers[id(page2)].image))  # shown translated
    assert w._jobs.empty() and w._queued is None and w.new_pages == []  # no page job, no request waiting

    v.frames.append((setup.clock.now + 0.2, page3))  # a page the run has not translated yet
    setup.clock.run(3)
    pump(w)
    assert run.asked[-1] is page3 and w._picture()[0] is page3  # the viewer's page as it is ...
    assert w.canvas.note == live.beside_line("waiting") and w.canvas.note  # ... and the line that says why
    assert w._jobs.empty() and w._queued is None and w.new_pages == []
    assert w._beside_translation_page({"seq": 7}) and not w._beside_translation_page({"seq": 3})  # its progress only
    run.answers[id(page3)] = ViewerPage("translated", lettered(page3), page3, seq=3)
    w._beside_stage({"seq": 3, "stage": "translate", "state": "done"})  # the run has stored it meanwhile
    pump(w)
    assert np.array_equal(np.asarray(w._picture()[0]), np.asarray(run.answers[id(page3)].image))
    assert w.canvas.note == "" and len(run.asked) == 3

    w.forward_key("Left")  # the reader's own key goes on to the viewer again
    setup.clock.run(0.3)
    assert sent(v) == ["Left"]


def test_the_busy_badge_tells_of_the_runs_page_and_goes_once_the_reader_turns_beside_the_run(setup):
    """The badge on the page area is the run's progress: on the run's page being translated, gone as soon as the reader
    turns to a page of their own beside the run (the band says the run's progress), back only while the viewer shows
    the very page being translated."""
    v = setup.viewer
    page1 = v.frames[0][1]
    w, run = _beside_window(setup, owner="viewer", auto=False)
    w._on_translation_page = lambda data: setattr(w, "_run_view", RunPage(data["seq"], data["frame"], data["image"]))
    setup.clock.run(5)  # (the strip's part of it: tests/test_page_strip.py)
    w._run_view = RunPage(4, page1, lettered(page1))
    run.following, run.viewer_free = False, True
    setup.clock.run(1)
    w._handle_event("progress", {"text": "Translating 1 bubble(s) with qwen3.5:4b..."})
    assert w.canvas.badge  # on the run's page being translated
    page3 = _page(3)
    run.answers[id(page3)] = ViewerPage("waiting", seq=3)
    v.frames.append((setup.clock.now + 0.2, page3))  # the reader turns to a page the run has not come to
    setup.clock.run(3)
    pump(w)
    assert w._picture()[0] is page3 and w.canvas.note == live.beside_line("waiting")
    assert not w.canvas.badge  # no word of the run's work on a page it does not work on
    w._handle_event("progress", {"text": "Translating 2 bubble(s) with qwen3.5:4b..."})
    assert not w.canvas.badge and w._busy_shown  # (the run's progress goes on, off the page)
    w._handle_event("translation_page", {"seq": 7, "image": lettered(page1), "frame": page1})  # another page of it
    assert not w.canvas.badge and w._picture()[0] is page3
    w._handle_event("translation_page", {"seq": 3, "image": lettered(page3), "frame": page3})  # the run comes to it
    assert w.canvas.badge  # its progress, on the very page the viewer shows


def test_the_run_over_the_window_reads_as_ever(setup):
    v = setup.viewer
    w, run = _beside_window(setup, owner="viewer")
    run.following, run.viewer_free = False, True
    setup.clock.run(1)
    page2 = _page(2)
    v.frames.append((setup.clock.now + 0.2, page2))
    setup.clock.run(3)
    pump(w)
    assert run.asked == [page2] and w.new_pages == []
    w.batch, w._batching, w.busy = None, False, False  # the run has ended
    setup.clock.run(0.2)
    assert getattr(w, "_beside", None) is None
    page3 = _page(3)
    v.frames.append((setup.clock.now + 0.2, page3))
    setup.clock.run(3)
    assert run.asked == [page2] and [p for _t, p in w.new_pages] == [page3]  # a page job, as without a run


def test_while_the_run_reads_nothing_changes(setup):
    """The reading stage as before: the run captures the viewer, the window none of it, and asks nothing of the run;
    the reader's keys go on to the viewer; between the reading and the translation the viewer rests."""
    v = setup.viewer
    w, run = _beside_window(setup, owner="viewer")
    setup.clock.run(10)
    v.frames.append((setup.clock.now + 0.2, _page(2)))
    setup.clock.run(10)
    assert v.captures == [] and run.asked == [] and getattr(w, "_beside", None) is None
    w.forward_key("Left")
    setup.clock.run(0.3)
    assert sent(v) == ["Left"]
    run.following = False  # the reading over, the erase ahead not yet: no key, and the run's turn is not followed
    w.forward_key("Left")
    setup.clock.run(5)
    assert sent(v) == ["Left"] and run.asked == [] and getattr(w, "_beside", None) is None


def test_a_browser_in_front_or_taslation_both_follow_the_viewer_beside_the_run(setup):
    """Follow = "poll" too: the page turned is asked of the run, nothing else."""
    v = setup.viewer
    w, run = _beside_window(setup, follow="poll")
    run.following, run.viewer_free = False, True
    setup.clock.run(2)
    page2 = _page(2)
    run.answers[id(page2)] = ViewerPage("later", seq=0)
    v.frames.append((setup.clock.now + 0.2, page2))
    setup.clock.run(4)
    pump(w)
    assert run.asked == [page2] and w.new_pages == [] and w._jobs.empty()
    assert w.canvas.note == live.beside_line("later")
