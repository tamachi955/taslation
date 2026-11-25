"""The pages behind in normal reading as the right side pane counts them (`ui.side`, `ui.side_model`) and the Reader's
status slot (`ui.status_slot`): each screen's mark from the engine's events, another book told by its fingerprint,
the counts and the backlog the pane reads, the events through the hidden window's own event handler, the slot's cases
and what the pane says of them. Made-up pages and events (`fake_side`); no window but the test's own, nothing sent to
any other."""

from __future__ import annotations

import queue
import tkinter as tk
from types import SimpleNamespace

import pytest
from fake_side import Cache, bubble_boxes, fingerprint, page, result, story

from taslation.capture import windows as capture_windows
from taslation.messages import Message
from taslation.ui import app as app_mod
from taslation.ui import seethrough
from taslation.ui import side as side_mod
from taslation.ui import status_slot
from taslation.ui import translator as translator_mod
from taslation.ui.jobs import JobsMixin
from taslation.ui.live import LiveViewMixin
from taslation.ui.progress import Filling
from taslation.ui.side import SideMixin
from taslation.ui.side_model import SideModel


# ------------------------------------------------------------------ the marks
def model_from(events):
    model = SideModel()
    for e in events:
        model.update(e.get("seq"), e.get("fingerprint", ""), e.get("stage"), e.get("state"))
    return model


def told(**kw):
    out = []
    story(lambda kind, data: out.append((kind, data)), **kw)
    return out


def test_marks_come_from_the_stage_events_in_any_order():
    events = [d for k, d in told(pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
              if k == "page_stage"]
    model = model_from(events)
    marks = {seq: model.screens[seq].mark for seq in model.order}
    assert [marks[s] for s in (1, 6, 7, 8, 9, 10, 11, 12)] == ["done", "done", "working", "waiting", "waiting",
                                                               "missed", "missed", "working"]
    assert model.screens[10].state("translate") == "missed"  # nothing waits for its translation either
    assert model.screens[8].state("translate") == "waiting"
    reversed_model = model_from(reversed(events))  # the latest event of a stage wins, whatever the order
    assert set(reversed_model.order) == set(model.order)
    model.update(9, stage="erase", state="working")  # normal reading has no erase: nothing changes
    assert model.screens[9].mark == "waiting"
    model.update(9, stage="translate", state="failed")
    assert model.screens[9].mark == "failed"
    model.update(10, stage="read", state="merged")  # a placeholder taken all the same under another number
    assert 10 not in model.screens and 10 not in model.order
    model.update(11, stage="read", state="skipped")  # nothing new on it (it was in the cache)
    assert model.screens[11].mark == "done"


def test_the_thumbnail_is_not_kept():
    model = SideModel()
    assert model.update(3, fingerprint(3), "read", "working")  # a screen not seen before
    assert not model.update(3, fingerprint(3), "read", "done")
    assert set(vars(model.screens[3])) == {"seq", "fingerprint", "stages"}  # nothing shows it: memory spared


def test_another_book_numbered_from_one_again_is_told_by_its_fingerprint():
    model = SideModel()
    model.update(1, fingerprint(1), "read", "done")
    assert not model.renumbered(1, fingerprint(1), 36)
    assert model.renumbered(1, fingerprint(77), 36)


def test_the_counts_and_the_backlog_are_what_the_right_pane_reads():
    model = model_from(d for k, d in told(pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
                       if k == "page_stage")
    assert model.counts() == {"done": 6, "working": 2, "waiting": 2, "failed": 0, "missed": 2}
    assert model.working()
    assert model.set_backlog(4, 24, False, 0) and not model.set_backlog(4, 24, False, 0)  # told again: no change
    assert (model.backlog.pages, model.backlog.lines, model.backlog.paused, model.backlog.dropped) == (4, 24, False, 0)
    model.set_backlog("x", None, None, True)  # the drop told as True, unreadable counts as none
    assert (model.backlog.pages, model.backlog.lines, model.backlog.dropped) == (0, 0, 0)
    assert model.show(5) and not model.show(5) and model.on_show == 5
    model.clear()
    assert len(model) == 0 and model.on_show is None and model.counts()["done"] == 0


# ------------------------------------------------------------------ the window's part
@pytest.fixture
def no_way_to_the_viewer(monkeypatch):
    def trap(*_a, **_k):
        raise AssertionError("something was sent to the viewer")

    for module in (capture_windows, translator_mod):
        for name in ("post_key", "post_click", "press_key", "press_briefly", "press_page_key"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, trap)
    return trap


class Window(SideMixin, tk.Frame):
    """The hidden window's parts the pages behind and the slot live with: its own event handler (`App._handle_event`,
    through `JobsMixin._handle_event`: normal reading's events to the model) with its event queue (`_post`, `pump`),
    and the page on show (`_live`, `last_result`, `_fill`)."""

    _result_on_show = LiveViewMixin._result_on_show
    _fill_on_show = LiveViewMixin._fill_on_show
    _handle_event = app_mod.App._handle_event
    _post = JobsMixin._post

    def __init__(self, master, rtl=True):
        tk.Frame.__init__(self, master)
        self.settings = SimpleNamespace(fingerprint_max_distance=36)
        self.cache = Cache()
        self.pipeline = SimpleNamespace(rtl=rtl, cache=self.cache, settings=self.settings)
        self._fill = self.last_result = self._live = None
        self._ordering = self._editor = self._job_frame = None
        self.busy, self._busy_shown, self._busy_since, self._progress = False, False, 0.0, ""
        self._queued, self.ready = None, True
        self.role_var = tk.StringVar(master=master, value="reader")
        self.said: list = []
        self._events: queue.Queue = queue.Queue()
        self._build_side()

    def pump(self):
        """The events queued handled, as the window's event pump does (`JobsMixin._poll_events`)."""
        while True:
            try:
                kind, data = self._events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(kind, data)
        self.update()

    def status(self, text):
        self.said.append(text() if callable(text) else text)

    def say(self, key, **values):
        self.said.append(key)

    def _shows_page(self, image, frame):
        return image is frame

    def _sharper_than(self, frame, image):
        return False

    def _same_page(self, result, live):
        return live is result.original

    def _redisplay(self):
        pass

    def post(self, kind, data):
        """An event handled at once: the engine's three by the window's own handler, the others (a result, an error)
        as the slot takes them around it."""
        if kind in ("page_stage", "page_on_show", "backlog"):
            self._handle_event(kind, data)
            return
        noted = side_mod.before(self, kind, data)
        side_mod.after(self, kind, data, noted)

    def show(self, image, on_show=None):
        self._live, self.last_result = image, on_show


def pane_lines(w):
    """What the right side pane says (`seethrough.right_rows`: its changing rows, then its foot's)."""
    changing, foot = seethrough.right_rows(w)
    return [row.text for row in (*changing, *foot)]


@pytest.fixture
def window(hidden_root, no_way_to_the_viewer):
    made = []

    def make(**kw):
        w = Window(hidden_root, **kw)
        hidden_root.update()
        made.append(w)
        return w

    yield make
    for w in made:
        w.destroy()


def test_the_engines_events_reach_the_model_through_the_windows_own_handler(window):
    w = window()
    story(w.post, pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
    model = w._side.model
    assert len(model) == 12 and model.on_show == 12 and model.counts()["missed"] == 2
    assert (model.backlog.pages, model.backlog.dropped) == (3, 2)
    lines = pane_lines(w)
    assert "Working on the others: 3 page(s), 18 line(s) to go." in lines
    assert "2 turned too fast to catch: turn back to them in the viewer to have them read." in lines
    w.post("backlog", {"pages": 0, "lines": 0, "paused": False, "dropped": True, "reading": True})  # dropped
    assert len(model) == 0 and not any("too fast" in line or "others" in line for line in pane_lines(w))


# ------------------------------------------------------------------ the Reader's status slot
def test_the_slot_says_what_the_page_waits_for_from_one_second_and_goes_with_the_first_bubble(window):
    w = window()
    frame = page(2)
    w.show(frame)
    w.busy, w._busy_shown, w._busy_since, w._job_frame = True, True, 50.0, frame
    w._progress = Message("pipeline.stage_reading", total=3)
    state = w._side.slot
    assert status_slot.wanted(w, state, 50.9) is None  # under a second: nothing said
    assert status_slot.wanted(w, state, 51.0) == (status_slot.READING_KEY, False)
    w._progress = Message("pipeline.stage_translating", bubbles=3)
    assert status_slot.wanted(w, state, 52.0) == (status_slot.TRANSLATING_KEY, False)
    w._progress = Message("ollama.loading")
    assert status_slot.wanted(w, state, 52.0) == (status_slot.LOADING_KEY, False)
    w._fill = Filling(frame, frame, bubble_boxes(2))
    w._fill.states[0] = "lettered"
    assert status_slot.wanted(w, state, 53.0) is None  # a bubble lettered: the page is the progress
    w.role_var.set("translator")
    w._fill = None
    assert status_slot.wanted(w, state, 53.0) is None  # the Translator role: nothing in the slot


def test_the_slot_is_said_in_the_right_pane(window):
    w = window()
    frame = page(2)
    w.show(frame)
    w.busy, w._busy_shown, w._job_frame = True, True, frame
    w._busy_since = __import__("time").monotonic() - 2
    status_slot.tick(w)
    assert w._side.slot.shown[0] == (status_slot.READING_KEY, False)
    assert "Reading the page..." in pane_lines(w)
    w.busy = w._busy_shown = False
    status_slot.tick(w)
    assert w._side.slot.shown[0] is None and "Reading the page..." not in pane_lines(w)


def test_a_page_that_could_not_be_translated_says_so_with_its_mark(window):
    w = window()
    failed = result(2, ["", "", ""], error="made-up")
    w.show(failed.original, failed)
    assert status_slot.wanted(w, w._side.slot, 0.0) == (status_slot.ERROR_KEY, True)
    frame = page(3)
    w._job_frame = frame
    w.post("error", {"text": "made-up"})
    w.show(frame)
    assert status_slot.wanted(w, w._side.slot, 0.0) == (status_slot.ERROR_KEY, True)  # the job's page on show
    w.show(page(4))
    assert status_slot.wanted(w, w._side.slot, 0.0) is None  # another page: gone


def test_loading_the_models_is_said_in_either_role_until_the_start_s_loads_are_over(window):
    """The start's one indicator (`jobs.JobsMixin._watch_loads`, the "models_loading" event): the window is usable
    meanwhile, and a page under way says its own stage instead."""
    w = window()
    w.show(page(2))
    w._handle_event("models_loading", {"on": True})
    assert status_slot.wanted(w, w._side.slot, 0.0) == (status_slot.MODELS_KEY, False)
    assert w._side.slot.shown[0] == (status_slot.MODELS_KEY, False) and "Loading the models..." in pane_lines(w)
    w.role_var.set("translator")
    assert status_slot.wanted(w, w._side.slot, 0.0) == (status_slot.MODELS_KEY, False)  # (in either role)
    w.role_var.set("reader")
    frame = page(3)
    w.show(frame)
    w.busy, w._busy_shown, w._busy_since, w._job_frame = True, True, 50.0, frame
    w._progress = Message("pipeline.stage_reading", total=3)
    assert status_slot.wanted(w, w._side.slot, 51.0) == (status_slot.READING_KEY, False)  # the page's own stage
    w.busy, w._busy_shown, w._job_frame, w._progress = False, False, None, ""
    assert status_slot.wanted(w, w._side.slot, 51.0) == (status_slot.MODELS_KEY, False)
    w._handle_event("models_loading", {"on": False})
    assert status_slot.wanted(w, w._side.slot, 51.0) is None  # all loaded: gone


def test_nothing_to_read_is_said_for_four_seconds(window, monkeypatch):
    w = window()
    empty = result(2, [])
    empty.regions = []
    w.show(empty.original, empty)
    monkeypatch.setattr(status_slot.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(side_mod.time, "monotonic", lambda: 10.0)
    w.post("result", {"result": empty})
    assert status_slot.wanted(w, w._side.slot, 13.9) == (status_slot.NOTHING_KEY, False)
    assert status_slot.wanted(w, w._side.slot, 14.1) is None
