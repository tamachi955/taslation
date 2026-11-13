"""The whole-book run follows the reader: TASlation sends no key, a sampler takes each new settled frame into a backlog in
memory, going back reads nothing twice, and the reader says when the book is done."""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image

from taslation import batch as batch_mod
from taslation import cli
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.capture import CaptureError, windows
from taslation.messages import Cancelled, Message
from taslation.pipeline import Pipeline
from taslation.regions import PageResult
from taslation.translate import DictTranslator
from taslation.ui.banner import ScanState, band_text
from taslation.ui.constants import viewer_rests
from taslation.ui.jobs import JobsMixin
from taslation.ui.live import LiveViewMixin
from taslation.ui.status import StatusMixin

KEY_FUNCTIONS = ("press_key", "press_briefly", "post_key", "post_click", "click_screen", "raise_window",
                 "lower_window", "bring_to_front", "give_foreground", "full_screen_window", "full_screen_again",
                 "enlarge_window", "restore_window", "with_foreground")


def page(i: int) -> Image.Image:
    """A page of its own: paper with ink where only this page has it."""
    rng = np.random.default_rng(i + 1)
    a = np.full((800, 600, 3), 255, np.uint8)
    for x, y, w, h in zip(rng.integers(20, 500, 60), rng.integers(20, 700, 60), rng.integers(10, 80, 60),
                          rng.integers(10, 80, 60)):
        a[y:y + h, x:x + w] = 0
    return Image.fromarray(a)


class Viewer:
    """A book in a viewer; the reader moves `index`."""

    def __init__(self, pages):
        self.pages = pages
        self.index = 0
        self.gone = False

    def capture(self, hwnd):
        if self.gone:
            raise CaptureError(Message("viewer.closed"))
        return self.pages[self.index]


class Slow:
    """The pipeline's page-by-page reading, taking its time: what was read, in order."""

    ocr = translator = None
    save_error = None
    pages_not_saved = 0

    def __init__(self, pages, seconds=0.0, gate=None):
        self.pages = pages
        self.seconds = seconds
        self.gate = gate
        self.read: list[int] = []

    def process(self, frame, **_kwargs):
        if self.gate is not None:
            self.gate.wait(20)
        time.sleep(self.seconds)
        self.read.append(self.pages.index(frame))
        return SimpleNamespace(translated=[], cache_hits=0, error=None)

    def save_annotations(self):
        pass


@pytest.fixture
def desk(settings, monkeypatch):
    """A viewer of 12 pages the batch may look at, and nothing it could press."""
    viewer = Viewer([page(i) for i in range(12)])
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: not viewer.gone)
    settings.settle_ms = 5

    def pressed(*_a, **_k):
        raise AssertionError("a key went to the viewer")

    for name in KEY_FUNCTIONS:
        monkeypatch.setattr(windows, name, pressed, raising=False)
    return viewer


def pagewise(desk, settings, **kwargs):
    pipeline = kwargs.pop("pipeline", None) or Slow(desk.pages)
    return BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False, preflight=[], **kwargs), pipeline


def whole_book(desk, settings, sample_page, sample_page2, translator=None, **kwargs):
    desk.pages[:] = [sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT)]
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    translator = translator or DictTranslator(EN_TEXTS)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=translator, cache=cache)
    return BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[], **kwargs), cache


def in_hand(target, *args):
    """*target* on a thread of its own, as the batch's job runs while the reader goes on."""
    results = []
    thread = threading.Thread(target=lambda: results.append(target(*args)), daemon=True)
    thread.start()
    return thread, results


def until(condition, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.002)
    return condition()


def test_the_batch_has_no_way_to_press_anything():
    tree = ast.parse(Path(batch_mod.__file__).read_text(encoding="utf-8"))
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    used |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert not used & {*KEY_FUNCTIONS, "press_held", "raised_window", "put_under", "next_page_key"}
    assert not hasattr(batch_mod.BatchProgress(), "turns")
    with pytest.raises(TypeError):
        BatchReader(SimpleNamespace(), 1, SimpleNamespace(), auto_turn=True)


@pytest.mark.parametrize("context_mode", (True, False))
def test_no_key_goes_to_the_viewer_in_either_mode(desk, settings, sample_page, sample_page2, context_mode):
    reader, _cache = whole_book(desk, settings, sample_page, sample_page2)
    reader.context_mode = context_mode
    assert read_book(reader, desk).pages == 3


def test_a_reader_who_turns_fast_loses_no_page_up_to_the_backlog(desk, settings):
    assert BatchReader.backlog_size is None  # (no count: the memory cap, `test_page_images`)
    reader, pipeline = pagewise(desk, settings, pipeline=Slow(desk.pages, 0.1))
    reader.sample_s = 0.002
    most = []
    reader.on_progress = lambda p, _r: most.append(p.queued)
    read_book(reader, desk)
    assert pipeline.read == list(range(12)) and max(most) > 1
    assert reader._backlog.empty()


def test_a_full_backlog_asks_the_reader_to_wait_and_takes_the_page_on_show_as_soon_as_there_is_room(desk, settings):
    gate = threading.Event()
    reader, pipeline = pagewise(desk, settings, pipeline=Slow(desk.pages, gate=gate))
    reader.backlog_size = 2
    said = []
    reader.on_progress = lambda p, _r: said.append((getattr(p.message, "code", ""), p.waiting))
    thread, _results = in_hand(reader.run)
    for i in range(3):  # the first is being read, two wait
        assert until(lambda: reader._on_show is desk.pages[i])
        desk.index = i + 1
    assert until(lambda: reader.progress.waiting is not None)
    assert reader.progress.waiting.code == "batch.backlog_full" and reader.progress.waiting.params["queued"] == 2
    desk.index = 5  # the reader went on regardless
    time.sleep(0.05)
    gate.set()
    assert until(lambda: 5 in pipeline.read)
    assert reader.progress.waiting is None and "batch.backlog_room" in [code for code, _w in said]
    reader.finish()
    thread.join(10)
    assert pipeline.read == [0, 1, 2, 5]


def test_going_back_reads_nothing_twice_and_changes_no_order(desk, settings):
    reader, pipeline = pagewise(desk, settings)
    thread, _results = in_hand(reader.run)
    for i in (0, 1, 2, 1, 0, 1, 2, 3):
        desk.index = i
        assert until(lambda: reader._on_show is desk.pages[i])
    reader.finish()
    thread.join(10)
    assert pipeline.read == [0, 1, 2, 3] and reader.progress.pages == 4


def test_a_page_already_read_is_no_new_line_for_the_translation(desk, settings, sample_page, sample_page2):
    reader, _cache = whole_book(desk, settings, sample_page, sample_page2)
    thread, _results = in_hand(reader.run)
    for i in (0, 1, 0, 1, 2):
        desk.index = i
        assert until(lambda: reader._on_show is desk.pages[i])
    reader.finish()
    thread.join(20)
    assert reader.progress.found == 18 and len(reader._units) == 3


def test_finished_reading_lets_the_backlog_drain_and_goes_on_to_the_translation(
        desk, settings, sample_page, sample_page2):
    phases = []
    reader, cache = whole_book(desk, settings, sample_page, sample_page2)
    reader.on_progress = lambda p, _r: phases.append(p.phase)
    progress = read_book(reader, desk)
    assert progress.pages == 3 and progress.reason.code == "batch.finished_reading"
    assert progress.summary.code == "batch.finished" and len(cache) == 3
    assert phases.index("read") < phases.index("translate") and "notes" not in phases
    assert reader.left is None


def test_finished_reading_takes_the_page_just_turned(desk, settings):
    reader, pipeline = pagewise(desk, settings)
    thread, _results = in_hand(reader.run)
    assert until(lambda: reader._on_show is desk.pages[0])
    desk.index = 1
    reader.finish()  # before the sampler has seen the new page
    thread.join(10)
    assert pipeline.read == [0, 1]


def test_stop_ends_the_run_with_nothing_translated_and_the_readings_kept(desk, settings, sample_page, sample_page2):
    reader, cache = whole_book(desk, settings, sample_page, sample_page2, keep_readings=True)
    asked = []
    reader.pipeline.translator.translate_page = lambda *a, **k: asked.append(a)
    thread, _results = in_hand(reader.run)
    assert until(lambda: reader.progress.pages == 1)
    reader.stop()
    thread.join(10)
    assert reader.progress.summary.code == "batch.stopped_reading" and reader.progress.summary.params["kept"] == 1
    assert not asked and len(cache) == 0
    assert reader.left is not None and not reader.left.complete and reader.left.pages == 1


def test_a_finished_book_stopped_later_is_read_no_more(desk, settings, sample_page, sample_page2):
    class StopsAtTheTranslation(DictTranslator):
        def translate_page(self, *a, **k):
            reader.stop()
            raise Cancelled()

    reader, _cache = whole_book(desk, settings, sample_page, sample_page2, StopsAtTheTranslation(EN_TEXTS),
                                keep_readings=True)
    read_book(reader, desk)
    assert reader.left is not None and reader.left.complete


def test_a_reader_who_pauses_ends_nothing_and_nothing_is_translated(desk, settings, sample_page, sample_page2,
                                                                     monkeypatch):
    awake = []
    monkeypatch.setattr(batch_mod, "release_awake", lambda: awake.append("rest"))
    monkeypatch.setattr(batch_mod, "keep_awake", lambda display: awake.append(("awake", display)))
    reader, cache = whole_book(desk, settings, sample_page, sample_page2)
    reader.manual_wait_s = 0.02
    thread, _results = in_hand(reader.run)
    assert until(lambda: reader.progress.pages == 1)
    assert until(lambda: "rest" in awake)
    time.sleep(0.1)
    assert thread.is_alive() and not reader.progress.finished and len(cache) == 0 and reader.progress.phase == "read"
    desk.index = 1
    assert until(lambda: reader.progress.pages == 2)
    assert ("awake", True) in awake[1:]  # the reader back
    reader.finish()
    thread.join(20)
    assert reader.progress.pages == 2 and len(cache) == 2


def test_a_frame_that_is_not_the_book_is_not_read_and_the_run_waits(desk, settings):
    reader, pipeline = pagewise(desk, settings)
    reader.guard_after_units = 1
    thread, _results = in_hand(reader.run)
    assert until(lambda: pipeline.read == [0])
    assert until(lambda: bool(reader._aspects))
    reader._still_the_book = lambda frame: frame != desk.pages[1]  # a store's page (the loop gets a copy)
    desk.index = 1
    assert until(lambda: reader.progress.waiting is not None)
    assert reader.progress.waiting.code == "batch.not_book" and thread.is_alive()
    desk.index = 2
    assert until(lambda: pipeline.read == [0, 2])
    assert reader.progress.waiting is None
    reader.finish()
    thread.join(10)


def test_a_viewer_closed_ends_nothing_either_the_reader_says_what_comes_next(desk, settings, sample_page, sample_page2):
    reader, cache = whole_book(desk, settings, sample_page, sample_page2)
    thread, _results = in_hand(reader.run)
    assert until(lambda: reader.progress.pages == 1)
    desk.gone = True
    assert until(lambda: reader.progress.waiting is not None)
    assert reader.progress.waiting.code == "batch.viewer_lost" and thread.is_alive() and len(cache) == 0
    reader.finish()
    thread.join(20)
    assert len(cache) == 1 and reader.progress.reason.code == "batch.finished_reading"


def test_a_capture_that_fails_while_the_window_is_there_is_waited_out(desk, settings, monkeypatch):
    reader, pipeline = pagewise(desk, settings)
    reader.wait_poll_s = 0.01
    good = batch_mod.capture_window
    bad = [True]

    def capture(hwnd, **_k):
        if bad[0]:
            raise CaptureError(Message("viewer.no_area"))
        return good(hwnd)

    monkeypatch.setattr(batch_mod, "capture_window", capture)
    thread, _results = in_hand(reader.run)
    assert until(lambda: reader.progress.waiting is not None)
    assert reader.progress.waiting.code == "batch.waiting_capture"
    bad[0] = False
    assert until(lambda: pipeline.read == [0])
    assert until(lambda: reader.progress.waiting is None)
    reader.finish()
    thread.join(10)


def test_nothing_read_at_finished_reading_says_no_page_was_seen(desk, settings):
    desk.pages[:] = [Image.new("RGB", (600, 800), "black")]  # black: the wait for the viewer
    settings.black_wait_s = 0.01
    reader, _pipeline = pagewise(desk, settings)
    reader.finish()
    assert reader.run().summary.code == "batch.not_started"


def test_no_page_reaches_the_disk(desk, settings, sample_page, sample_page2):
    reader, _cache = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    kept = [p for p in settings.state_dir.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")]
    assert not kept
    assert all(not hasattr(u, "view") for u in reader._units)  # the units kept hold no frame


# ------------------------------------------------------------------ what the band says
def test_the_band_counts_the_pages_and_keeps_a_wait_on_show():
    scan = ScanState()
    scan.update(Message("batch.read_page", page=3, lines=2, pages=3, bubbles=9, cached=0, seconds=1.0, dropped=0),
                "read", 3, 0, 9, 1.0, queued=4)
    assert "Read: 3" in band_text(scan) and "Waiting: 4" in band_text(scan) and "Finished reading" in band_text(scan)
    full = Message("batch.backlog_full", queued=24)
    scan.update(Message("batch.read_page", page=4, lines=2, pages=4, bubbles=9, cached=0, seconds=1.0, dropped=0),
                "read", 4, 0, 9, 2.0, waiting=full, queued=24)
    assert band_text(scan) == str(full)
    scan.update("", "read", 5, 0, 9, 3.0, queued=1)
    scan.finishing = True
    assert "still to read: 1" in band_text(scan)
    page_by_page = ScanState(context=False)
    page_by_page.update("", "translate", 2, 1, 1, 1.0)
    assert "Done: 2" in band_text(page_by_page)


class Band:
    _band_view = StatusMixin._band_view

    def __init__(self, scan):
        self._band = {"kind": "scan", "scan": scan}

    def stop_batch(self):
        pass

    def finish_reading(self):
        pass


def test_finished_reading_is_beside_stop_only_while_the_pages_are_read():
    scan = ScanState()
    scan.update("", "read", 1, 0, 0, 1.0)
    assert [text for text, _command in Band(scan)._band_view()[1]] == ["Finished reading", "Stop"]
    scan.finishing = True
    assert [text for text, _command in Band(scan)._band_view()[1]] == ["Stop"]
    scan.finishing = False
    scan.update("", "notes", 1, 0, 0, 1.0)
    assert [text for text, _command in Band(scan)._band_view()[1]] == ["Stop"]


def test_finished_reading_goes_to_the_run():
    finished = []
    shown = []
    window = SimpleNamespace(batch=SimpleNamespace(finish=lambda: finished.append(True)), _scan=ScanState(),
                             _show_band=lambda: shown.append(True))
    JobsMixin.finish_reading(window)
    assert finished and shown and window._scan.finishing
    JobsMixin.finish_reading(SimpleNamespace(batch=None))


# ------------------------------------------------------------------ the reader's keys, the command line
def test_the_readers_keys_go_on_only_while_the_run_reads():
    assert not viewer_rests(SimpleNamespace(batch=None, _batching=False))
    assert viewer_rests(SimpleNamespace(batch=None, _batching=True))  # the run starts
    assert not viewer_rests(SimpleNamespace(batch=SimpleNamespace(following=True), _batching=True))
    assert viewer_rests(SimpleNamespace(batch=SimpleNamespace(following=False), _batching=True))  # the translation


def test_the_batch_command_has_no_key_and_no_manual_way():
    parser = cli.build_parser()
    for words in (["batch", "--window", "x", "--manual"], ["batch", "--window", "x", "--key", "Left"]):
        with pytest.raises(SystemExit):
            parser.parse_args(words)


def test_enter_says_the_book_is_done(monkeypatch):
    done = []
    reader = SimpleNamespace(finish=lambda: done.append(True))
    monkeypatch.setattr("builtins.input", lambda: "")
    cli._finish_at_enter(reader)
    assert done == [True]

    def no_console():
        raise EOFError

    monkeypatch.setattr("builtins.input", no_console)
    cli._finish_at_enter(reader)
    assert done == [True]


# ------------------------------------------------------------------ the window shows the pages of the run
class Canvas:
    def __init__(self):
        self.busy = None

    def set_busy(self, text):
        self.busy = text


class Window:
    _handle_event = JobsMixin._handle_event
    _on_page_event = JobsMixin._on_page_event
    _batch_page = JobsMixin._batch_page
    _picture = LiveViewMixin._picture
    _keep_pace = JobsMixin._keep_pace

    def __init__(self):
        self.canvas = Canvas()
        self.last_result = self._live = self._live_thumb = self._fill = self._job_frame = None
        self._chosen_region = self._grip_box = self._scan = None
        self._fill_dirty = False
        self._progress = ""
        self._busy_shown = False
        self._busy_since = 0.0
        self._slow_before = None
        self.drawn = 0
        self.original_var = SimpleNamespace(get=lambda: False)
        self.said = []

    def _redisplay(self):
        self.drawn += 1

    def _show_notes(self):
        self.notes_shown = getattr(self, "notes_shown", 0) + 1

    def _hide_busy(self):
        self.canvas.busy = None

    def _busy_text(self):
        return "busy"

    def _overlay_items(self):
        return []

    def _same_page(self, result, live):
        return live is result.original

    def _lettered(self, result, live):
        return result.image

    def say(self, message):
        self.said.append(message)


def _result(frame, image):
    return PageResult(image=image, original=frame, regions=[])


def test_the_window_shows_each_page_at_once_fills_it_in_and_takes_the_finished_page():
    window = Window()
    frame, other = Image.new("RGB", (50, 40), "white"), Image.new("RGB", (50, 40), "gray")
    window.last_result = _result(other, other)
    window._fill = "the page before"
    window._handle_event("batch_page", {"image": frame})
    assert window._picture()[0] is frame and window.drawn == 1 and window.last_result is None and window._fill is None
    window._handle_event("regions", {"boxes": [(1, 2, 11, 12), (20, 2, 30, 12)], "size": (50, 40)})
    assert window._fill.frame is frame and window.canvas.busy is not None
    assert [box for box, _colour, dashed in window._picture()[2] if dashed] == [(1, 2, 11, 12), (20, 2, 30, 12)]
    window._handle_event("read", {"index": 0, "status": "untranslated", "box": (1, 2, 11, 12)})
    window._handle_event("translated", {"index": 0, "text": "Hi", "box": (1, 2, 11, 12),
                                        "patch": Image.new("RGB", (10, 10), "red")})
    image, _items, outlines = window._picture()
    assert image.getpixel((5, 5)) == (255, 0, 0) and len(outlines) == 1
    done = Image.new("RGB", (50, 40), "blue")
    progress = SimpleNamespace(message="", phase="read", pages=1, translated=2, found=2)
    window._handle_event("batch", {"progress": progress, "result": _result(frame, done), "message": ""})
    assert window._fill is None and window._job_frame is None and window.canvas.busy is None
    assert window._picture()[0] is done


def test_a_page_of_the_run_stopped_half_way_leaves_no_fill_behind(tmp_path):
    from taslation.config import Settings
    from taslation.ui.banner import ScanState  # noqa: F401 - the run's band goes as it does

    window = Window()
    window._batch_done = JobsMixin._batch_done.__get__(window)
    window._batching = window.busy = True
    window._apply_found_margins = window._show_band = window._sync_stop = window._run_queued = lambda: None
    window._set_busy = lambda busy: None
    window._resume_auto = False
    window._auto_before_batch = None
    window._batch_for = ("", "", "")
    window.settings = Settings(state_dir=tmp_path)
    window.role_var = SimpleNamespace(get=lambda: "reader")
    frame = Image.new("RGB", (50, 40), "white")
    window._handle_event("batch_page", {"image": frame})
    window._handle_event("regions", {"boxes": [(1, 2, 11, 12)], "size": (50, 40)})
    drawn = window.drawn
    window._batch_done(SimpleNamespace(summary=Message("batch.scan_ended"), reason=""))
    assert window._fill is None and window._job_frame is None and window.canvas.busy is None
    assert window.drawn == drawn + 1 and window._picture()[0] is frame
