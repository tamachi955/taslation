"""A whole-book translation's progress in view: the band moves line by line (the lines the request under way has
answered, `BatchProgress.answering`), its bar and the taskbar button's follow, the time left is given once it can be
trusted (the rate since the first line, started from the last run's when there is one) with the time of day for a
long run, and while the pages are read the band says how long reading a page takes."""
from __future__ import annotations

import sys
import tkinter as tk
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from test_batch import _fake_viewer
from test_start_flow import Flow, _batch_event

from taslation import batch as batch_mod
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.i18n import set_language
from taslation.messages import Message
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import banner, jobs, taskbar
from taslation.ui.banner import ScanState, band_fraction, band_text

TRANSLATING = "translate"


def _translating(scan, now, checked=0, answering=0, found=100):
    scan.update(Message("batch.translating_chunk", chunk=1, chunks=4, bubbles=30), TRANSLATING, 12, checked, found, now,
                checked=checked, answering=answering)


# ------------------------------------------------------------------ the estimate
def test_no_time_left_until_the_rate_can_be_trusted_and_the_models_loading_is_left_out():
    scan = ScanState()
    _translating(scan, 0.0)
    _translating(scan, 40.0, answering=1)  # the first line after 40 s of loading: the rate starts here
    assert scan.left is None and scan.started == 40.0
    _translating(scan, 50.0, answering=7)  # 6 lines in 10 s: too few, too soon
    assert scan.left is None
    assert band_text(scan) == "Translating: 7 of 100 lines. The viewer is not used during this step."
    _translating(scan, 56.0, answering=11)  # 10 lines in 16 s: 89 more take about 2 min 22 s
    assert scan.left == pytest.approx(89 / (10 / 16))
    assert band_text(scan) == "Translating: 11 of 100 lines, about 2 min left. The viewer is not used during this step."
    _translating(scan, 150.0, checked=95)
    assert band_text(scan) == ("Translating: 95 of 100 lines, less than a minute left. The viewer is not used during "
                               "this step.")


def test_the_last_runs_rate_starts_the_estimate_and_this_runs_takes_over():
    scan = ScanState(seed=0.5)
    _translating(scan, 0.0, found=600)
    assert scan.left == pytest.approx(600 / 0.5)  # from the start: 20 min
    _translating(scan, 30.0, answering=1, found=600)
    for now in range(40, 400, 10):  # this run does a line a second: twice the seed's
        _translating(scan, float(now), answering=1 + (now - 30), found=600)
    rate = (scan.done - 1) / (390.0 - 30.0)
    assert scan.left < (600 - scan.done) / 0.9  # close to this run's rate ...
    assert scan.measured(390.0) == pytest.approx(rate)  # ... which is what the next run starts from
    assert ScanState().measured(10.0) is None


def test_a_long_translation_says_when_it_will_be_done():
    scan = ScanState(seed=0.2)
    _translating(scan, 0.0, found=1000)  # 1,000 lines at 0.2 a second: 83 min
    wall = 1_800_000_000.0
    at = banner.time.strftime("%H:%M", banner.time.localtime(wall + 5000))
    assert band_text(scan, clock=wall) == (f"Translating: 0 of 1,000 lines, about 1 h 23 min left (done at about {at})."
                                           " The viewer is not used during this step.")
    set_language("ja")
    try:
        assert band_text(scan, clock=wall) == f"翻訳中: 全1,000行中0行（残り約1時間23分、{at}ごろ終了）。この間はビューアを操作しません。"
    finally:
        set_language("en")


def test_the_lines_shown_done_never_go_back():
    scan = ScanState()
    _translating(scan, 0.0, answering=30)  # the request answered its 30 lines ...
    assert scan.done == 30 and band_fraction(scan) == pytest.approx(0.3)
    _translating(scan, 1.0, checked=27)  # ... 27 were usable and stored, 3 are asked again
    assert scan.done == 30
    _translating(scan, 2.0, checked=27, answering=3)
    assert scan.done == 30
    _translating(scan, 3.0, checked=100, answering=40, found=100)  # never past the total
    assert scan.done == 100 and band_fraction(scan) == 1.0


def test_the_bar_is_only_for_the_translation_of_a_whole_book():
    scan = ScanState()
    scan.update(Message("batch.read_page", page=3, lines=4, pages=3, bubbles=12, cached=0, seconds=9.0, dropped=0),
                "read", 3, 0, 12, 0.0)
    assert band_fraction(scan) is None and band_fraction(None) is None
    assert band_fraction(ScanState(context=False, phase=TRANSLATING, found=9)) is None
    _translating(scan, 1.0, found=0)
    assert band_fraction(scan) is None  # nothing to translate


def test_the_reading_says_how_long_a_page_takes():
    scan = ScanState()
    read = Message("batch.read_page", page=4, lines=6, pages=4, bubbles=20, cached=0, seconds=12.0, dropped=0)
    scan.update(read, "read", 4, 0, 20, 0.0, queued=1)
    assert "takes about" not in band_text(scan)
    scan.update(read, "read", 4, 0, 20, 1.0, queued=1, page_seconds=2.6)
    assert band_text(scan).startswith("Reading the pages you turn. Read: 4. Waiting: 1. Reading a page takes about 3 s.")
    scan.update(Message("batch.scanning_page", page=5), "read", 4, 0, 20, 2.0)  # (said with every message)
    assert "about 3 s" in band_text(scan)


# ------------------------------------------------------------------ the batch tells each line
def test_the_batch_tells_each_line_the_model_answers(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    monkeypatch.setattr(batch_mod, "LINE_SAID_S", 0.0)
    translator = DictTranslator(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Lines", "fake")
    settings.chunk_bubbles = 100  # one request for the book: only its lines can move the band
    seen = []
    reader = BatchReader(Pipeline(settings, ocr=FakeOcr(), translator=translator, cache=cache), hwnd=1,
                         settings=settings, context_mode=True,
                         on_progress=lambda p, _r: seen.append((p.phase, p.checked, p.answering, p.page_seconds)))
    progress = read_book(reader)
    assert progress.reason.code == "batch.finished_reading" and progress.checked > 0
    assert all(k["streamed"] for k in translator.kwargs)  # every request hands its lines over as they come
    answered = [a for phase, checked, a, _s in seen if phase == TRANSLATING and checked == 0 and a]
    assert answered == list(range(1, len(answered) + 1)) and len(answered) == len(translator.calls[0])
    assert progress.answering == 0  # stored: counted in checked
    assert progress.page_seconds > 0 and all(s >= 0 for *_x, s in seen)


# ------------------------------------------------------------------ the window: the bar, the taskbar, the rate kept
@pytest.fixture
def flow(hidden_root, tmp_path):
    yield Flow(hidden_root, tmp_path)


def test_the_band_and_the_taskbar_button_show_the_translation(flow):
    flow._scan = ScanState(context=True)
    read = Message("batch.read_page", page=2, lines=3, pages=2, bubbles=6, cached=0, seconds=4.0, dropped=0)
    _batch_event(flow, read, "read", pages=2, found=6)
    assert flow.scan_band.fraction() is None and flow.taskbar_seen.shown == []  # the reading: no bar
    covered = Message("batch.waiting_covered")
    _batch_event(flow, covered, "read", pages=2, found=6, waiting=covered)
    assert flow.taskbar_seen.shown[-1] == (taskbar.PAUSED, 1.0)  # the run waits for the reader: yellow
    _batch_event(flow, Message("batch.translating_chunk", chunk=1, chunks=1, bubbles=40), TRANSLATING, pages=2,
                 found=40)
    chunk = Message("batch.translating_chunk", chunk=1, chunks=1, bubbles=40)
    said = SimpleNamespace(message=chunk, phase=TRANSLATING, pages=2, translated=0, found=40, checked=0)
    flow._handle_event("batch", {"progress": said, "result": None, "message": chunk,
                                 "phase": TRANSLATING, "pages": 2, "found": 40, "checked": 0, "answering": 10,
                                 "waiting": None, "queued": 0})
    assert flow.scan_band.texts()[0].startswith("Translating: 10 of 40 lines.")
    assert flow.scan_band.fraction() == pytest.approx(0.25) and flow.taskbar_seen.shown[-1] == (taskbar.NORMAL, 0.25)
    flow._band = {"kind": "summary", "summary": Message("batch.scan_ended"), "resumed": False}
    flow._show_band()
    assert flow.scan_band.fraction() is None and flow.taskbar_seen.shown[-1][0] == taskbar.NO_PROGRESS


def test_the_rate_of_a_run_is_kept_for_the_next_run_with_the_model(flow):
    assert flow._pace("qwen3.5:4b") is None
    scan = ScanState(context=True)
    _translating(scan, 0.0, answering=1)
    _translating(scan, 20.0, answering=21)  # 20 lines in 20 s
    flow._batch_for = ("Book", "qwen3.5:4b", "English")
    real = jobs.time.monotonic
    try:
        jobs.time.monotonic = lambda: 20.0
        flow._keep_pace(scan)
    finally:
        jobs.time.monotonic = real
    assert flow._pace("qwen3.5:4b") == pytest.approx(1.0) and flow._pace("other") is None
    flow._keep_pace(ScanState(context=True))  # a run with no rate to trust keeps the one before
    assert flow._pace("qwen3.5:4b") == pytest.approx(1.0)


def test_the_taskbar_bar_never_breaks_the_window():
    def broken():
        raise OSError("no taskbar here")

    bar = taskbar.TaskbarProgress(lambda: 1, factory=broken)
    bar.show(taskbar.NORMAL, 0.5)  # nothing raised, and not tried again
    assert not bar.available
    bar.show(taskbar.NORMAL, 0.6)
    bar.clear()
    seen = []

    class List:
        def set(self, hwnd, state, fraction):
            seen.append((hwnd, state, fraction))

    bar = taskbar.TaskbarProgress(lambda: 7, factory=List)
    bar.clear()  # nothing shown yet: the COM object is not even made
    bar.show(taskbar.NORMAL, 0.5)
    bar.show(taskbar.NORMAL, 0.5)  # the same: not shown again
    bar.show(taskbar.NORMAL, 0.5004)  # (the same step of the bar)
    bar.show(taskbar.PAUSED, 0.5)
    bar.clear()
    assert seen == [(7, taskbar.NORMAL, 0.5), (7, taskbar.PAUSED, 0.5), (7, taskbar.NO_PROGRESS, 0.0)]


@pytest.mark.skipif(sys.platform != "win32", reason="ITaskbarList3 is Windows'")
def test_the_taskbar_interface_answers_on_this_windows(hidden_root):
    window = tk.Toplevel(hidden_root)
    window.withdraw()
    bar = taskbar.TaskbarProgress(lambda: int(window.wm_frame(), 16))
    bar.show(taskbar.NORMAL, 0.4)
    bar.clear()
    assert bar.available
    window.destroy()
