"""A whole-book run's work kept safe: Stop asks once more than a few pages are read, Esc never ends a run by itself,
the question offers to translate the pages read (the run goes on to the translation, `finish(partial=True)`), a
stopped run's readings can be translated from the band, and closing the window warns while pages read are not
translated yet."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from test_batch import _fake_viewer
from test_start_flow import Flow, button_texts

from taslation.batch import BatchReader, Readings
from taslation.cache import CacheStore
from taslation.messages import Message
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import banner, jobs
from taslation.ui import strip as strip_mod
from taslation.ui.dialogs.stop import StopQuestion

A = app_mod.App


class Run:
    """A stand-in for the batch's reader: what the window asks of it."""

    def __init__(self):
        self.stopped = self.finished = False
        self.partial = None

    def stop(self):
        self.stopped = True

    def finish(self, partial=False):
        self.finished, self.partial = True, partial


@pytest.fixture
def flow(hidden_root, tmp_path, monkeypatch):
    w = Flow(hidden_root, tmp_path)
    w.dialogs = []
    w.questions = []

    def ask(master, text, choices):
        w.questions.append((text, [a for a, _label in choices], [label for _a, label in choices]))
        return w.answer

    monkeypatch.setattr(jobs, "ask_stop", ask)
    w.answer = "keep"
    yield w


def _reading(w, pages, queued=0, finishing=False):
    w._scan = banner.ScanState(context=True)
    w._scan.update(Message("batch.read_page", page=pages, lines=3, pages=pages, bubbles=3 * pages, cached=0,
                           seconds=10.0, dropped=0), "read", pages, 0, 3 * pages, 0.0, queued=queued)
    w._scan.finishing = finishing
    w.batch, w._batching = Run(), True


# ------------------------------------------------------------------ Stop and Esc
def test_stop_ends_a_run_of_a_few_pages_at_once_and_asks_once_more_are_read(flow):
    _reading(flow, jobs.FEW_PAGES)
    flow.stop_batch()
    assert flow.batch.stopped and flow.questions == []  # a few pages are turned again in a minute
    _reading(flow, jobs.FEW_PAGES, queued=1)  # one more waiting to be read: it asks
    flow.stop_batch()
    assert not flow.batch.stopped and len(flow.questions) == 1
    text, answers, labels = flow.questions[0]
    assert answers == ["keep", "stop", "translate"]  # the safe answer first (Esc, Return, the close button)
    assert labels == ["Keep reading", "Stop without translating", "Translate the pages read"]
    assert "4 page(s) are read" in text and "kept only until you close TASlation" in text


@pytest.mark.parametrize("answer, stopped, partial", [("keep", False, None), ("stop", True, None), ("translate", False, True)])
def test_the_answer_keeps_reading_stops_or_translates_the_pages_read(flow, answer, stopped, partial):
    _reading(flow, 12)
    flow.answer = answer
    flow.stop_batch()
    assert flow.batch.stopped == stopped and flow.batch.partial == partial
    if partial:  # the run goes on to the translation: the band says so, and the status line what comes after
        assert flow._scan.finishing and flow.batch.finished
        assert flow.status_var.get().startswith("The pages read so far are translated now.")


def test_esc_never_ends_a_run_by_itself(flow):
    flow._ordering = flow._chosen_region = None
    flow._cancel_drag = lambda: False
    for pages in (0, 2, 40):
        _reading(flow, pages)
        A._on_escape(flow)
        assert not flow.batch.stopped  # Keep reading: the box's first answer, also Esc's in it
    assert [q[1] for q in flow.questions] == [["keep", "stop"], ["keep", "stop", "translate"],
                                             ["keep", "stop", "translate"]]
    assert flow.questions[0][0] == "Stop the whole-book run? No page is read yet."
    flow.answer = "stop"
    A._on_escape(flow)
    assert flow.batch.stopped


def test_the_question_follows_the_phase_of_the_run(flow):
    _reading(flow, 30, finishing=True)  # Finished reading pressed: the translation comes anyway
    flow.stop_batch()
    assert flow.questions[-1][1] == ["keep", "stop"] and "You pressed Finished reading" in flow.questions[-1][0]
    flow._scan.update(Message("batch.translated_chunk", chunk=2, chunks=9, bubbles=60, seconds=90.0), "translate",
                      30, 60, 270, 0.0, checked=60)
    flow.stop_batch()
    text, answers, labels = flow.questions[-1]
    assert answers == ["keep", "stop"] and labels == ["Keep translating", "Stop"]
    assert text.startswith("Stop the translation? 60 of 270 lines are translated and saved")
    flow._scan = banner.ScanState(context=False)  # page by page: each page is saved as it is translated
    flow._scan.update(Message("batch.translated_page", page=9, bubbles=4, seconds=50.0, error=""), "translate", 9,
                      30, 30, 0.0)
    flow.stop_batch()
    assert flow.batch.stopped and len(flow.questions) == 2


def test_a_run_that_ended_while_the_question_was_open_is_left_alone(flow, monkeypatch):
    _reading(flow, 20)
    run = flow.batch

    def ended(master, text, choices):
        flow.batch, flow._batching = None, False  # the run ended meanwhile (the reader finished, a failure)
        return "stop"

    monkeypatch.setattr(jobs, "ask_stop", ended)
    flow.stop_batch()
    assert not run.stopped


def test_the_stop_question_answers_keep_reading_to_esc_return_and_its_close_button(hidden_root):
    choices = [("keep", "Keep reading"), ("stop", "Stop without translating"), ("translate", "Translate the pages read")]
    for event in ("<Escape>", "<Return>", None):
        box = StopQuestion(hidden_root, "TASlation", "Stop?", choices)
        assert box.labels() == ["Translate the pages read", "Stop without translating", "Keep reading"]
        assert str(box.buttons["keep"].cget("default")) == "active"
        if event is None:
            box.tk.call(box.protocol("WM_DELETE_WINDOW"))  # (the close button)
        else:
            box.event_generate(event)
        assert box.answer == "keep"
        if box.winfo_exists():
            box.destroy()
    box = StopQuestion(hidden_root, "TASlation", "Stop?", choices)
    box.press("translate")
    assert box.answer == "translate" and not box.winfo_exists()


# ------------------------------------------------------------------ translating what was read
def test_the_pages_read_so_far_are_translated_and_a_later_run_reads_on(sample_page, sample_page2, settings,
                                                                       monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("So far", "fake")
    reader = BatchReader(Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache), hwnd=1,
                         settings=settings, context_mode=True, keep_readings=True)

    finish = reader.finish
    reader.finish = lambda: None  # the person at the viewer never presses Finished reading: the question's answer

    def told(p, _result):
        if p.message.code == "batch.read_page" and p.message.params.get("page") == 2:
            finish(partial=True)

    reader.on_progress = told
    progress = read_book(reader)
    assert progress.reason.code == "batch.read_so_far" and progress.summary.code == "batch.finished"
    assert progress.translated == progress.found > 0 and len(cache) >= 2
    assert not reader._read_through  # the book is not read to its end: a later run reads on from the page on show
    assert str(progress.summary).endswith("you asked for the pages read so far.")


def test_a_finished_book_is_not_made_partial(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Whole", "fake")
    reader = BatchReader(Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache), hwnd=1,
                         settings=settings, context_mode=True)
    reader.finish()
    reader.finish(partial=True)  # (the question's answer after Finished reading)
    assert not reader._partial


def test_the_band_after_a_stop_translates_what_was_read(flow):
    flow.book_var.set("My Book 1")
    units = [SimpleNamespace(fingerprint="f1"), SimpleNamespace(fingerprint="f2")]
    flow._readings = (("My Book 1", "qwen3.5:4b", "English"), Readings(units, pages=2, complete=False))
    summary = Message("batch.stopped_reading", pages=2, seconds=30.0, kept=1, again=0)
    flow._band = {"kind": "summary", "summary": summary, "resumed": False}
    flow._show_band()
    assert button_texts(flow.scan_band) == ["Translate the pages read", "Close"]
    started = []
    flow._start_batch = lambda *options, **kw: started.append((options, kw))
    flow.scan_band.press("Translate the pages read")
    assert started == [((flow.selected, 0, True), {"at_once": True})]
    flow._readings = (("My Book 1", "qwen3.5:4b", "English"), Readings(units, pages=2, complete=True))
    flow._band = {"kind": "summary", "summary": Message("batch.stopped_translating", done=3, total=9, pages=2,
                                                      seconds=60.0, kept=1, again=0), "resumed": False}
    flow._show_band()
    assert button_texts(flow.scan_band) == ["Translate the rest", "Close"]
    flow.book_var.set("Another Book 2")  # another book in the box: those readings are not its own
    flow._show_band()
    assert button_texts(flow.scan_band) == ["Close"]


def test_a_run_started_to_translate_what_was_read_finishes_at_once(flow, monkeypatch):
    made = []

    class Reader:
        def __init__(self, *args, **kwargs):
            self.left, self.progress, self.calls = None, SimpleNamespace(), []
            made.append(self)

        def stop(self):
            self.calls.append("stop")

        def finish(self, partial=False):
            self.calls.append(("finish", partial))

        def run(self):
            self.calls.append("run")

    monkeypatch.setattr(jobs, "BatchReader", Reader)
    monkeypatch.setattr(jobs, "preflight", lambda settings, model=None: [])
    flow.pipeline, flow.window_query = SimpleNamespace(), ""
    flow.translator = SimpleNamespace(model="")
    monkeypatch.setattr(flow, "_use_model", lambda model, language: None, raising=False)
    flow._job_batch(7, "My Book 1", "m", "English", 0, True, at_once=True)
    assert made[0].calls == [("finish", True), "run"]


# ------------------------------------------------------------------ closing the window
def _window(**kw):
    base = dict(batch=None, _batching=False, _scan=None, _readings=None, _strip_model=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_closing_warns_while_pages_read_are_not_translated():
    assert strip_mod.close_warning(_window()) is None
    scan = banner.ScanState(context=True)
    scan.update(Message("batch.read_page", page=5, lines=2, pages=5, bubbles=10, cached=0, seconds=9.0, dropped=0),
                "read", 5, 0, 10, 0.0, queued=2)
    text = strip_mod.close_warning(_window(batch=Run(), _scan=scan))
    assert text.startswith("The whole-book run has read 7 page(s), and none is translated yet.")
    assert "Press Finished reading" in text
    held = Readings([SimpleNamespace()] * 3, pages=4)
    text = strip_mod.close_warning(_window(_readings=(("B", "m", "English"), held)))
    assert text.startswith("3 page(s) read in the whole-book run are not translated yet.")
    assert "Translate the pages read" in text
    unfinished = SimpleNamespace(unfinished=lambda: [4, 5])
    assert strip_mod.close_warning(_window(_strip_model=unfinished)).startswith(
        "2 page(s) of the whole-book run are not finished yet.")


def test_the_close_box_asks_with_the_warning(hidden_root, monkeypatch):
    shown = []

    class Box:
        def __init__(self, master, title, text, **kw):
            shown.append((text, kw))
            self.answer = False

        def winfo_exists(self):
            return False

    monkeypatch.setattr(app_mod, "WarningBox", Box)
    released = []
    monkeypatch.setattr(app_mod, "release_run_images", lambda w: released.append(w))
    w = _window(_readings=(("B", "m", "English"), Readings([SimpleNamespace()], pages=1)))
    assert not A._close_allowed(w)
    assert shown[0][0].startswith("1 page(s) read in the whole-book run") and shown[0][1]["stay_first"]
    assert released == []
    assert A._close_allowed(_window())
