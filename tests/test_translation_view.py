"""While a whole-book run translates, the window's page area follows it (`translation_view`): the page whose lines the
model answers, each line lettered as it comes (provisional), the stored page the cache's picture exactly, nothing
provisional ever stored; and the window's side (`ui.strip`): the page on show, the strip's outline, a thumbnail clicked
that shows nothing (reading is on the viewer), an open editor or a reading order holding the viewer's page on show, and
the run's end - done, stopped, failed - handing the page area back to the live view at once."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image

from taslation import translation_view
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

from test_batch_follows_reader import desk  # noqa: F401 - (a fixture)


class Paced(DictTranslator):
    """A model that answers one line at a time, *seconds* apart (as PLaMo answers line by line, or Ollama streams)."""

    def __init__(self, mapping, seconds=0.1):
        super().__init__(mapping)
        self.seconds = seconds

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                       on_slow=None):
        out = [self.mapping.get(t, self.default) for t in texts]
        self.calls.append(list(texts))
        for i, text in enumerate(out):
            if cancel is not None and cancel.is_set():
                break
            time.sleep(self.seconds)
            if on_item is not None and text:
                on_item(i, text)
        return out


def whole_book(desk, settings, sample_page, sample_page2, translator=None):
    desk.pages[:] = [sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT)]
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=translator or Paced(EN_TEXTS), cache=cache)
    shown: list[tuple[str, dict]] = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[],
                         show=lambda kind, data: shown.append((kind, data)))
    return reader, pipeline, shown


def pictures(shown):
    return [data for kind, data in shown if kind == "translation_page"]


def stored(reader, seq):
    """The page *seq* as the cache letters it now on the run's images (`Pipeline.page_picture`, what the view ends on
    once the page is stored)."""
    return reader.pipeline.page_picture(reader.images, seq)


@pytest.fixture
def often(monkeypatch):
    """The window told after every change (the stand-in model answers faster than a real one)."""
    monkeypatch.setattr(translation_view, "GAP_S", 0.0)


def test_the_page_being_translated_is_shown_line_by_line_and_ends_as_the_cache_letters_it(
        desk, settings, sample_page, sample_page2, often):
    settings.chunk_bubbles = 1  # a request a page: each page is stored before the next one is asked for
    reader, pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)
    progress = read_book(reader, desk)
    assert progress.summary.code == "batch.finished"
    told = pictures(shown)
    seqs = [d["seq"] for d in told]
    assert set(seqs) == {1, 2, 3} and seqs == sorted(seqs)  # the view moves on with the run, never back
    for seq in (1, 2, 3):
        mine = [d for d in told if d["seq"] == seq]
        frame = desk.pages[seq - 1].convert("RGB")
        assert all(d["frame"].tobytes() == frame.tobytes() for d in mine)  # Show original: the page as captured
        assert all(d["image"].size == frame.size for d in mine)
        assert len({id(d["image"]) for d in mine}) == len(mine)  # a picture of its own each time
        waiting = [d["waiting"] for d in mine]
        everything = max(waiting, key=len)
        assert len(everything) >= 2, seq  # (the page has lines to wait for)
        for before, after in zip(waiting, waiting[1:]):  # lines only ever come, in reading order
            assert set(after) <= set(before)
            assert after == everything[len(everything) - len(after):]
        assert waiting[-1] == []
        middle = [d for d in mine if 0 < len(d["waiting"]) < len(everything)]
        assert middle, seq  # some lines lettered, some still to come: shown so
        final = np.asarray(mine[-1]["image"])
        assert np.array_equal(final, np.asarray(stored(reader, seq))), seq  # the cache's picture, exactly
        assert not np.array_equal(np.asarray(middle[0]["image"]), final)
        assert not np.array_equal(np.asarray(middle[0]["image"]), np.asarray(frame))  # lettered before it is stored
    assert reader._view is None  # the view ended with the translation


def test_one_request_over_several_pages_moves_the_view_from_page_to_page(desk, settings, sample_page, sample_page2,
                                                                          often):
    reader, pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)  # (the three pages: one request)
    read_book(reader, desk)
    assert len(pipeline.translator.calls) == 1
    told = pictures(shown)
    seqs = [d["seq"] for d in told]
    assert set(seqs) == {1, 2, 3} and seqs == sorted(seqs)
    for seq in (1, 2):  # left while the request went on: shown with its lines lettered, not stored yet
        mine = [d for d in told if d["seq"] == seq]
        assert any(not np.array_equal(np.asarray(d["image"]), np.asarray(desk.pages[seq - 1])) for d in mine)
    last = [d for d in told if d["seq"] == 3][-1]  # the page on show when the request was stored: the cache's
    assert last["waiting"] == [] and np.array_equal(np.asarray(last["image"]), np.asarray(stored(reader, 3)))


def test_nothing_provisional_is_stored_and_the_view_writes_nothing(desk, settings, sample_page, sample_page2, often,
                                                                   monkeypatch):
    reader, pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)
    written: list[str] = []
    for name in ("add", "save", "put", "set_page", "update"):
        original = getattr(type(pipeline.cache), name, None)
        if original is None:
            continue

        def spy(self, *args, _original=original, **kwargs):
            written.append(threading.current_thread().name)
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(type(pipeline.cache), name, spy)
    saved = Image.Image.save
    monkeypatch.setattr(Image.Image, "save", lambda self, fp, *a, **k: (_ for _ in ()).throw(
        AssertionError("a picture went to a file")) if not hasattr(fp, "write") else saved(self, fp, *a, **k))
    read_book(reader, desk)
    assert pictures(shown) and written
    assert "batch-translation-view" not in written  # the view never writes to the cache
    plain = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS),
                     cache=CacheStore(settings.cache_dir).open("Book", "fake"))
    for i, frame in enumerate(desk.pages):  # what was stored is what a run without a window stores
        assert [r.translated_text for r in plain.process(frame).regions if r.status == "translated"] == [
            r.translated_text for r in pipeline.process(frame).regions if r.status == "translated"], i


def test_a_line_that_is_no_translation_stays_outlined_until_the_page_is_over(desk, settings, sample_page,
                                                                             sample_page2, often):
    settings.chunk_bubbles = 1
    copied = Paced({**EN_TEXTS, "ありがとう": "ありがとう"})  # a line copied back (each page has one): no translation
    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2, translator=copied)
    read_book(reader, desk)
    for seq in (1, 2, 3):
        mine = [d for d in pictures(shown) if d["seq"] == seq]
        assert all(len(d["waiting"]) >= 1 for d in mine[:-1]) and any(len(d["waiting"]) == 1 for d in mine)
        assert mine[-1]["waiting"] == []  # the page's translation over: nothing is waited for


def test_a_model_that_does_not_stream_shows_each_request_as_stored(desk, settings, sample_page, sample_page2, often):
    settings.chunk_bubbles = 1  # (the view stays on the first page of a request until it is stored)
    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2,
                                          translator=DictTranslator(EN_TEXTS))
    reader.pipeline.translator.translate_page = lambda texts, *_a, **_k: [EN_TEXTS.get(t, "") for t in texts]
    read_book(reader, desk)
    told = pictures(shown)
    assert [d["seq"] for d in told] == sorted(d["seq"] for d in told) and {d["seq"] for d in told} == {1, 2, 3}
    for seq in (1, 2, 3):  # (the page as captured first, unless it was stored by the time the view came to it)
        mine = [d for d in told if d["seq"] == seq]
        assert np.array_equal(np.asarray(mine[-1]["image"]), np.asarray(stored(reader, seq)))
        assert mine[-1]["waiting"] == []


def test_lines_of_a_request_that_failed_go_when_the_page_is_over(desk, settings, sample_page, sample_page2, often):
    from taslation.translate import TranslationError

    class Breaks(Paced):
        def translate_page(self, texts, *args, on_item=None, **kwargs):
            if on_item is not None:
                on_item(0, self.mapping.get(texts[0], ""))  # a line comes, then the request fails
            time.sleep(0.05)
            raise TranslationError("the model went away (test)")

    settings.chunk_bubbles = 1
    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2, translator=Breaks(EN_TEXTS))
    read_book(reader, desk)
    told = pictures(shown)
    assert any(not np.array_equal(np.asarray(d["image"]), np.asarray(desk.pages[d["seq"] - 1].convert("RGB")))
               for d in told)  # (a line was lettered while its request went on)
    for seq in {d["seq"] for d in told}:
        last = [d for d in told if d["seq"] == seq][-1]
        assert last["waiting"] == []  # over (failed): nothing waited for, nothing provisional left
        assert np.array_equal(np.asarray(last["image"]), np.asarray(stored(reader, seq)))
        assert np.array_equal(np.asarray(last["image"]), np.asarray(desk.pages[seq - 1].convert("RGB")))


def test_a_page_no_longer_held_shows_nothing_of_the_run(desk, settings, sample_page, sample_page2, often):
    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)
    gone = reader.images.original
    reader.images.original = lambda seq: None if seq == 2 else gone(seq)  # the memory cap made room for page 2
    progress = read_book(reader, desk)
    assert progress.summary.code == "batch.finished"
    told = pictures(shown)
    assert [d for d in told if d["seq"] == 2] and all(d["image"] is None and d["frame"] is None
                                                       for d in told if d["seq"] == 2)
    assert all(d["image"] is not None for d in told if d["seq"] != 2)


def test_stop_ends_the_view_and_nothing_is_told_after(desk, settings, sample_page, sample_page2, often):
    gate = threading.Event()

    class Held(Paced):
        def translate_page(self, texts, *args, **kwargs):
            kwargs["on_item"](0, self.mapping.get(texts[0], ""))
            gate.wait(10)
            return super().translate_page(texts, *args, **kwargs)

    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2, translator=Held(EN_TEXTS))
    done: list = []
    thread = threading.Thread(target=lambda: done.append(read_book(reader, desk)), daemon=True)
    thread.start()
    end = time.monotonic() + 20
    while not pictures(shown) and time.monotonic() < end:
        time.sleep(0.01)
    assert pictures(shown)
    view = reader._view
    reader.stop()
    gate.set()
    thread.join(20)
    assert done and reader._view is None and not view.thread.is_alive()
    count = len(pictures(shown))
    view.line(None, 0, "", "")  # (told after the end: nothing happens)
    time.sleep(0.05)
    assert len(pictures(shown)) == count


def test_the_view_costs_the_translation_little(desk, settings, sample_page, sample_page2):
    """The lettering is on the view's own thread: the run's thread only notes the lines (measured: well under a
    millisecond a line)."""
    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)
    noted: list[float] = []
    real = translation_view.TranslationView._put

    def timed(self, job):
        began = time.perf_counter()
        real(self, job)
        noted.append(time.perf_counter() - began)

    translation_view.TranslationView._put = timed
    try:
        read_book(reader, desk)
    finally:
        translation_view.TranslationView._put = real
    assert noted and max(noted) < 0.05 and sum(noted) / len(noted) < 0.002


# ------------------------------------------------------------------ the window's side
@pytest.fixture
def window(hidden_root):
    """A window with the strip and the page area's choice of picture (`LiveViewMixin._picture`), on the shared root."""
    from taslation.ui import strip as strip_mod
    from taslation.ui.live import LiveViewMixin
    from taslation.ui.strip import StripMixin

    class Window(StripMixin, tk.Frame):
        _picture = LiveViewMixin._picture
        _result_on_show = LiveViewMixin._result_on_show

        def __init__(self, master):
            tk.Frame.__init__(self, master)
            self.status_bar = tk.Frame(self)
            self.status_bar.pack(fill="x")
            self.reading = False
            self.batch = None
            self.pipeline = SimpleNamespace(release_page_images=lambda: None)
            self._batching = False
            self._fill = self.last_result = self._live = None
            self._ordering = self._editor = None
            self._fill_dirty = False
            self.original_var = tk.BooleanVar(value=False)
            self.said: list[str] = []
            self.redisplays = 0
            self._build_page_strip()

        def say(self, key, **values):
            self.said.append(key)

        def _redisplay(self):
            self.redisplays += 1

    w = Window(hidden_root)
    for seq in (1, 2, 3):
        w._on_page_stage({"seq": seq, "fingerprint": f"f{seq}", "thumb": Image.new("RGB", (40, 60)),
                          "stage": "translate", "state": "waiting"})
    yield w, strip_mod


def told(seq, waiting=((1, 2, 10, 12),)):
    return {"seq": seq, "frame": Image.new("RGB", (60, 80), "white"), "image": Image.new("RGB", (60, 80), "grey"),
            "waiting": [list(b) for b in waiting]}


def test_the_window_shows_the_page_being_translated_and_outlines_its_thumbnail(window):
    w, strip = window
    w._on_translation_page(told(2))
    assert w._run_view is None  # no run: nothing of it
    w._batching = True
    data = told(2)
    w._on_translation_page(data)
    image, overlay, outlines = w._picture()
    assert image is data["image"] and overlay == [] and outlines == [((1, 2, 10, 12), strip.FILL_COLOUR, False)]
    assert w.page_strip.chosen == 2 and w._fill_dirty and not w._result_on_show()
    w.original_var.set(True)
    assert w._picture()[0] is data["frame"]  # Show original: the page as it was captured
    w.original_var.set(False)
    w._on_translation_page(told(3, waiting=()))
    assert w.page_strip.chosen == 3 and w._picture()[2] == []


OPEN_IN_VIEWER = "Page {n} of this run. To read it, open it in the viewer: TASlation shows the translation over it."


def test_a_thumbnail_clicked_while_the_run_translates_shows_nothing_and_the_view_goes_on(window):
    """Reading is on the viewer: a click on a thumbnail - another page, the page being translated, a page done - says
    to open the page in the viewer and leaves the run's progress on show; the view goes on with the run."""
    w, strip = window
    w._batching = True
    data = told(2)
    w._on_translation_page(data)
    w._on_page_stage({"seq": 1, "stage": "translate", "state": "done"})  # (page 1 stored: its picture is in the cache)
    for seq in (1, 2, 3):
        w._pick_page(seq)
        assert w.said[-1] == OPEN_IN_VIEWER
        assert w._picture()[0] is data["image"] and w.page_strip.chosen == 2
    later = told(3)
    w._on_translation_page(later)  # the run moves on: the page area with it
    assert w._picture()[0] is later["image"] and w.page_strip.chosen == 3
    for name in ("_peek", "_run_told"):
        assert not hasattr(w, name), name  # nothing of the run is held to be shown on a click


def test_an_editor_or_a_reading_order_keeps_the_viewers_page_on_show_and_outlines_no_page_of_the_run(window):
    """`follow_held`: while the reader edits the viewer's page, the run's page is not shown and the strip outlines
    none; once the editor is closed (the order set) the run's progress is shown again."""
    w, strip = window
    w._batching = True
    w._live = Image.new("RGB", (60, 80), "black")  # the viewer's page
    w._on_translation_page(told(2))
    assert w.page_strip.chosen == 2
    w._editor = SimpleNamespace(winfo_exists=lambda: True)  # an editor open on the viewer's page
    assert strip.follow_held(w) and w._picture()[0] is w._live and strip.run_page_on_show(w) is None
    w._fill_dirty = False
    later = told(3)
    w._on_translation_page(later)  # the run goes on meanwhile
    assert w._picture()[0] is w._live and w.page_strip.chosen is None and not w._fill_dirty
    w._editor = SimpleNamespace(winfo_exists=lambda: False)  # closed
    assert w._picture()[0] is later["image"]
    w._on_translation_page(told(3))
    assert w.page_strip.chosen == 3
    w._editor, w._ordering = None, []  # a reading order being set on the viewer's page
    w._on_translation_page(told(3))
    assert w._picture()[0] is w._live and w.page_strip.chosen is None
    w._ordering = None
    assert w._picture()[0] is not w._live


def _ending(w, monkeypatch):
    """The window's end of a run (`JobsMixin._batch_done`) on the stand-in, with nothing of the real window's."""
    from taslation.ui import jobs as jobs_mod

    w._batch_done = jobs_mod.JobsMixin._batch_done.__get__(w)
    w._keep_pace = jobs_mod.JobsMixin._keep_pace.__get__(w)
    w._apply_found_margins = w._show_band = w._sync_stop = w._run_queued = w._hide_busy = lambda: None
    w.translate_now = lambda: None
    w._set_busy = lambda busy: None
    w.status = lambda text: w.said.append(text)
    w._reader_after_run = lambda book, language: False
    w._resume_auto, w._auto_before_batch, w._scan, w._job_frame = False, None, None, None
    w._batch_for = ("", "", "")
    w.settings = SimpleNamespace(flash_when_done=False, sound_when_done=False)
    monkeypatch.setattr(jobs_mod, "tell_run_ended", lambda window, summary: ())


@pytest.mark.parametrize("ending", ["done", "stopped", "failed", "stopped while an editor was open"])
def test_the_runs_end_hands_the_page_area_back_to_the_live_view_at_once(window, monkeypatch, ending):
    """However the run ends, the page it was translating leaves the page area at once: the viewer's page is shown, the
    strip outlines none, and a picture told late shows nothing."""
    from taslation.messages import Message

    w, strip = window
    _ending(w, monkeypatch)
    w._batching = True
    w._live = Image.new("RGB", (60, 80), "black")  # the viewer's page
    data = told(2)
    w._on_translation_page(data)
    assert w._picture()[0] is data["image"] and w.page_strip.chosen == 2
    if ending.endswith("open"):
        w._editor = SimpleNamespace(winfo_exists=lambda: True)
    summary, reason = {"done": (Message("batch.finished"), ""), "failed": (None, Message("batch.failed_requests"))}.get(
        ending, (Message("batch.stopped_translating"), ""))
    drawn = w.redisplays
    w._batch_done(SimpleNamespace(summary=summary, reason=reason))
    w._editor = None
    assert w._run_view is None and w.page_strip.chosen is None and w.redisplays == drawn + 1
    assert w._picture()[0] is w._live
    w._on_translation_page(told(3))  # told after the end: nothing of it
    assert w._run_view is None and w._picture()[0] is w._live


def test_a_picture_gone_falls_back_and_the_runs_end_hands_back_to_the_live_view(window):
    w, strip = window
    w._batching = True
    w._on_translation_page(told(2))
    w._on_translation_page({"seq": 2, "frame": None, "image": None, "waiting": []})
    assert w._run_view is None and w._picture()[0] is None and w.page_strip.chosen is None
    w._on_translation_page(told(3))
    assert w._run_view.seq == 3
    w._batching = False
    assert strip.end_follow(w) and w._run_view is None and w.page_strip.chosen is None
    assert not strip.end_follow(w)
    w._batching = True
    w._on_translation_page(told(1))
    strip.new_run(w)
    assert w._run_view is None
