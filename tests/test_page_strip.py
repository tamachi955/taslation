"""The page strip of a whole-book run (`ui.strip`): its state (any order of events, the latest wins, skipped pages are
finished), one animation timer for the whole strip, a click on a thumbnail that says to open the page in the viewer and
shows nothing - reading is on the viewer: no page of the run's memory goes on the page area, during the run or after
it - and never sends a key or a click to the viewer, the question at closing, and the role a book opens in
(`ui.translator`: translator mode while nothing is translated, reader mode after, the reader's choice first). No real
window is touched: the window's parts run on stand-ins."""

from __future__ import annotations

import threading
import time
import tkinter as tk
import tkinter.messagebox
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation.bookid import GENERIC_NAMES
from taslation.cache import CacheStore
from taslation.capture import windows as capture_windows
from taslation.i18n import set_language
from taslation.ui import app as app_mod
from taslation.ui import reading as reading_mod
from taslation.ui import strip as strip_mod
from taslation.ui import translator as translator_mod
from taslation.batch import thumb_of
from taslation.ui.strip import (CELL_W, PAD, STAGES, STRIP_H, THUMB_BOX, PageStrip, StripMixin, StripModel, bar_tip,
                                 fit_thumb, page_tip, trim_ground)
from taslation.ui.constants import READER_AFTER_RUN
from taslation.ui.translator import chosen_role, remember_role, start_role

from fake_strip import FakeRun, picture, thumb
from test_cache import FP_A, FP_B, _page

A = app_mod.App


# ------------------------------------------------------------------ the state
def test_pages_come_in_the_order_first_seen_and_the_latest_event_of_a_stage_wins():
    model = StripModel()
    assert model.update(3, "c", stage="read", state="working") is True
    assert model.update(1, "a", stage="read", state="done") is True
    assert model.update(3, stage="read", state="done") is False
    assert model.order == [3, 1]  # first sight, not the run number
    model.update(3, stage="erase", state="done")
    model.update(3, stage="erase", state="working")  # out of order: the latest wins all the same
    assert model.pages[3].stages == {"read": "done", "erase": "working", "translate": "waiting"}
    assert model.working() and model.unfinished() == [3, 1]


def test_an_unknown_stage_or_state_only_brings_the_page():
    model = StripModel()
    assert model.update(5, stage="dance", state="done") is True
    model.update(5, stage="read", state="burnt")
    assert model.pages[5].stages == {s: "waiting" for s in STAGES}
    assert model.update("x", stage="read", state="done") is False and len(model) == 1


def test_skipped_and_failed_stages_are_finished_waiting_and_working_are_not():
    model = StripModel()
    model.update(1, stage="read", state="done")
    model.update(1, stage="erase", state="skipped")
    model.update(1, stage="translate", state="skipped")
    model.update(2, stage="read", state="done")
    model.update(2, stage="erase", state="failed")
    model.update(2, stage="translate", state="done")
    model.update(3, stage="read", state="done")
    model.update(3, stage="erase", state="done")  # its translation still waits for Finished reading
    assert model.unfinished() == [3] and not model.working()


def test_a_thumbnail_comes_with_any_event_of_the_page_and_is_made_small():
    model = StripModel()
    model.update(1, stage="read", state="working")  # (its first event had none)
    big = thumb(picture(1))
    model.update(1, thumb=big, stage="read", state="done")
    small = model.pages[1].thumb
    assert small is not None and small is not big and small.height <= THUMB_BOX[1] and small.width <= THUMB_BOX[0]
    model.update(1, thumb=Image.new("RGB", (9, 9)))
    assert model.pages[1].thumb is small  # the first one stays
    assert 0 < model.memory_bytes() <= 3 * THUMB_BOX[0] * THUMB_BOX[1]


def _viewer_frame(ground=(43, 43, 43), page_box=(624, 0, 1296, 1080), marks=True):
    """A full-HD frame of a browser viewer as the run's thumbnail has it (96 px tall): the page in the middle on the
    viewer's even ground, a page number at the bottom right and a few small marks at the bottom left."""
    frame = Image.new("RGB", (1920, 1080), ground)
    page = Image.new("RGB", (page_box[2] - page_box[0], page_box[3] - page_box[1]), "white")
    page.paste((20, 20, 20), (100, 200, 300, 260))  # a line of lettering
    frame.paste(page, page_box[:2])
    if marks:
        frame.paste((150, 150, 150), (1850, 1060, 1904, 1072))  # "1 / 36"
        for k in range(24):
            frame.paste((144, 144, 144), (8 + 8 * k, 1064, 14 + 8 * k, 1070))
    return thumb_of(frame)


def test_a_thumbnail_is_the_page_without_the_viewers_ground_and_fills_its_cell():
    small = fit_thumb(_viewer_frame())
    assert small.height == THUMB_BOX[1] and small.width >= 0.8 * THUMB_BOX[0]  # not a page 25 px wide in a frame
    assert THUMB_BOX[0] <= CELL_W - 2 * PAD and STRIP_H == PAD + THUMB_BOX[1] + 4 + 3 * 11 + 2 * 2 + PAD
    black = fit_thumb(_viewer_frame(ground=(0, 0, 0), marks=False))
    assert black.size == small.size


def test_a_frame_the_page_fills_or_with_odd_corners_is_left_whole():
    whole = Image.new("RGB", (68, 96), "white")
    whole.paste((20, 20, 20), (10, 30, 50, 40))
    assert trim_ground(whole) is whole  # the page's own paper is no ground to cut
    bars = Image.new("RGB", (171, 96), (43, 43, 43))
    bars.paste((240, 240, 240), (0, 0, 171, 8))  # the viewer's toolbar along the top
    bars.paste("white", (56, 8, 115, 96))
    assert trim_ground(bars) is bars
    blank = Image.new("RGB", (171, 96), (43, 43, 43))
    assert trim_ground(blank) is blank


def test_the_fake_run_says_what_the_run_says():
    events = []
    run = FakeRun(lambda kind, data: events.append((kind, data)), pages=12, fail_every=5, skip_every=4, keep=3)
    run.run(rate=None)
    model = StripModel()
    for kind, data in events:
        if kind == "page_stage":
            model.update(data["seq"], data["fingerprint"], data.get("thumb"), data["stage"], data["state"])
    assert model.order == list(range(1, 13)) and not model.unfinished()
    assert model.pages[5].stages["erase"] == "failed" and model.pages[4].stages["erase"] == "skipped"
    assert all(model.pages[s].thumb is not None for s in model.order)
    assert 12 in run.images and 1 not in run.images  # the older pictures are gone
    assert [kind for kind, _d in events].count("batch_memory") == 12


# ------------------------------------------------------------------ the strip
def _pending_afters(widget: tk.Misc) -> set[str]:
    return set(widget.tk.splitlist(widget.tk.call("after", "info")))


def test_one_timer_moves_every_working_bar_and_none_runs_while_nothing_works(hidden_root):
    model = StripModel()
    before = _pending_afters(hidden_root)
    strip = PageStrip(hidden_root, model, lambda seq: None)
    for seq in range(1, 51):
        model.update(seq, thumb=thumb(picture(seq)), stage="read", state="working")
        strip.page_changed(seq, True)
    assert strip.animating
    assert len(_pending_afters(hidden_root) - before) == 1  # fifty pages at work, one timer
    strip.after_cancel(strip._anim_job)  # the timer comes due
    strip._animate()
    assert len(_pending_afters(hidden_root) - before) == 1
    assert len(strip.canvas.find_withtag("stripe")) == 50
    for seq in range(1, 51):
        model.update(seq, stage="read", state="done")
        strip.page_changed(seq, False)
    assert not strip.animating and not (_pending_afters(hidden_root) - before)
    strip.destroy()


def test_the_strip_says_each_state_by_its_letter_and_its_pattern_too(hidden_root):
    model = StripModel()
    strip = PageStrip(hidden_root, model, lambda seq: None)
    counts = {}
    for seq, state in enumerate(("waiting", "working", "done", "failed", "skipped"), start=1):
        model.update(seq, stage="read", state=state)
        strip.page_changed(seq, True)
        counts[state] = len(strip.canvas.find_withtag(f"p{seq}"))
    texts = {strip.canvas.itemcget(i, "text") for i in strip.canvas.find_all() if strip.canvas.type(i) == "text"}
    assert {"R", "E", "T"} <= texts
    assert len(set(counts.values())) >= 3  # crossed and hatched bars draw more than a plain one
    assert int(float(strip.canvas.cget("height"))) == STRIP_H
    strip.destroy()


def test_the_translation_bar_says_why_it_waits_in_the_windows_language():
    assert "Finished reading" in bar_tip("translate", "waiting")
    assert "Finished reading" not in bar_tip("translate", "done") and "under way" in bar_tip("read", "working")
    set_language("ja")
    try:
        assert "読み終えた" in bar_tip("translate", "waiting")
    finally:
        set_language("en")


# ------------------------------------------------------------------ a click on a thumbnail
class Window(StripMixin, tk.Frame):
    """The parts of the window the strip uses; every way to the viewer is a trap."""

    _on_escape = A._on_escape
    _cancel_drag = A._cancel_drag
    _on_release = A._on_release
    _picture = A._picture
    _result_on_show = A._result_on_show
    _on_close = A._on_close
    _close_allowed = A._close_allowed

    def __init__(self, master, batch=None):
        super().__init__(master)
        self.status_bar = ttk.Frame(self)
        self.status_bar.pack(side="bottom")
        self.reading = False
        self.batch = batch
        self.lines, self.drawn, self.stops, self.asked_stop = [], 0, 0, 0
        self._ordering = self._chosen_region = None
        self._drag_start = self._drag_rect = self._grip = self._grip_start = None
        self._fill, self.last_result, self._live = None, None, Image.new("RGB", (4, 4))
        self.original_var = tk.BooleanVar(value=False)
        self.role_var = tk.StringVar(value="reader")
        self._build_page_strip()

    def say(self, key, **values):
        self.lines.append(key.format(**values))

    def _redisplay(self):
        self.drawn += 1

    def stop_batch(self):
        self.stops += 1

    def _ask_stop(self):
        self.asked_stop += 1

    def _editing(self):
        return False

    def _forward_click(self, event):
        raise AssertionError("a click went on to the viewer")


@pytest.fixture
def no_way_to_the_viewer(monkeypatch):
    """Every function that sends a key or a click to a window raises."""
    def trap(*_a, **_k):
        raise AssertionError("something was sent to the viewer")

    for module in (capture_windows, translator_mod, reading_mod):
        for name in ("post_key", "post_click", "press_key", "press_briefly", "press_page_key"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, trap)
    return trap


def _fed(window, pages=5):
    run = window.batch
    for seq in range(1, pages + 1):
        run.read_page(seq)


def _click(window, seq):
    index = window._strip_model.order.index(seq)
    window.page_strip.canvas.xview_moveto(0)  # (the canvas is not on the screen: the view from its left end)
    window.page_strip._clicked(SimpleNamespace(x=index * CELL_W + CELL_W // 2, y=20))


OPEN_IN_VIEWER = "Page {n} of this run. To read it, open it in the viewer: TASlation shows the translation over it."


def test_a_click_on_a_thumbnail_says_to_open_the_page_in_the_viewer_and_shows_nothing(hidden_root,
                                                                                     no_way_to_the_viewer):
    events = []
    run = FakeRun(lambda kind, data: events.append((kind, data)), pages=5)
    w = Window(hidden_root, batch=run)
    w.batch.post = lambda kind, data: A._handle_event(w, kind, data) if kind in ("page_stage", "batch_memory") else None
    _fed(w)
    assert w._strip_shown and w.page_strip.winfo_manager() and w._strip_model.order == [1, 2, 3, 4, 5]
    assert "of 512 MB" in w.page_strip.memory_var.get()
    drawn = w.drawn
    for seq in (3, 3, 4):  # the same thumbnail twice, then another: each time the line, nothing else
        _click(w, seq)
        assert w.lines[-1] == OPEN_IN_VIEWER.format(n=seq) == page_tip(seq)  # the tooltip says the same
        assert w._picture()[0] is w._live and w.page_strip.chosen is None  # the viewer's page stays on show
        assert all(w._picture()[0] is not image for image in run.images.values())
    assert w.drawn == drawn  # nothing was drawn again: no page of the run came on the page area
    w.page_strip.canvas.xview_moveto(0)
    assert w.page_strip.text_at(2 * CELL_W + CELL_W // 2, 20) == OPEN_IN_VIEWER.format(n=3)
    w._on_escape()  # Esc has nothing to go back from: it asks before a Stop, as it does without the strip
    assert w.stops == 0 and w.asked_stop == 1


def test_a_thumbnail_clicked_leaves_the_viewers_translated_page_on_show(hidden_root, no_way_to_the_viewer):
    """The page area showing the viewer's page translated (the cache's translation over the live frame): a click on a
    thumbnail of another page changes nothing on it."""
    run = FakeRun(lambda kind, data: None, pages=3)
    w = Window(hidden_root, batch=run)
    run.post = lambda kind, data: A._handle_event(w, kind, data)
    _fed(w, 3)
    live = w._live
    w.last_result = SimpleNamespace(original=live, image=Image.new("RGB", live.size, (9, 9, 9)), regions=[])
    w._overlay_items = lambda: []
    w._same_page = lambda result, frame: frame is result.original
    w._lettered = lambda result, frame: result.image
    before = w._picture()[0]
    assert before is w.last_result.image
    _click(w, 1)
    assert w._picture()[0] is before and w.lines[-1] == OPEN_IN_VIEWER.format(n=1)


def test_a_click_on_the_page_after_a_thumbnail_goes_on_as_it_always_does(hidden_root, no_way_to_the_viewer):
    """No page is shown from the strip, so a click on the page has nothing to go back from: in reader mode it goes on
    to the viewer (the window's stand-in for that only counts it), in translator mode it stays TASlation's own."""
    run = FakeRun(lambda kind, data: None, pages=2)
    w = Window(hidden_root, batch=run)
    run.post = lambda kind, data: A._handle_event(w, kind, data)
    _fed(w, 2)
    forwarded = []
    w._forward_click = forwarded.append
    _click(w, 1)
    w._drag_start = (10, 10)
    w._on_release(SimpleNamespace(x=10, y=10))
    assert len(forwarded) == 1 and w._picture()[0] is w._live
    w._editing = lambda: True
    _click(w, 2)
    w._drag_start = (10, 10)
    w._on_release(SimpleNamespace(x=10, y=10))
    assert len(forwarded) == 1 and w._picture()[0] is w._live


def test_a_page_no_longer_held_and_a_page_after_the_run_say_the_same(hidden_root, no_way_to_the_viewer):
    """Whether the run still holds a page's picture changes nothing: a page is read in the viewer."""
    run = FakeRun(lambda kind, data: None, pages=70, keep=60)
    w = Window(hidden_root, batch=run)
    run.post = lambda kind, data: A._handle_event(w, kind, data)
    _fed(w, 70)
    _click(w, 2)
    assert w.lines[-1] == OPEN_IN_VIEWER.format(n=2) and w._picture()[0] is w._live
    w.batch = None  # the run is over
    _click(w, 65)
    assert w.lines[-1] == OPEN_IN_VIEWER.format(n=65) and w._picture()[0] is w._live


def test_a_new_run_starts_an_empty_strip_and_the_closed_band_takes_it_away(hidden_root):
    run = FakeRun(lambda kind, data: None, pages=3)
    w = Window(hidden_root, batch=run)
    run.post = lambda kind, data: A._handle_event(w, kind, data)
    _fed(w, 3)
    strip_mod.hide_strip(w)
    assert not w.page_strip.winfo_manager() and len(w._strip_model) == 3  # kept for the question at closing
    strip_mod.new_run(w)
    assert len(w._strip_model) == 0 and not w._strip_shown


def test_the_strip_has_no_way_to_show_a_page_of_the_runs_memory():
    """Reading is on the viewer: what showed a page from the strip is gone, and so is what fetched its picture."""
    for name in ("end_peek", "page_picture"):
        assert not hasattr(strip_mod, name), name
    for name in ("_peek", "_peek_page", "_run_told", "_translation_stored"):
        assert not hasattr(StripMixin, name), name


# ------------------------------------------------------------------ closing
class Asked(app_mod.WarningBox):
    """The closing question, answered at once as the test says (the box is TASlation's own: its buttons say what they
    do in the window's language, unlike a system box, whose buttons are in Windows' language)."""

    asked: list = []
    answers: list = []

    def __init__(self, master, title, text, **kw):
        super().__init__(master, title, text, **kw)
        Asked.asked.append((text, self.continue_btn.cget("text"), self.cancel_btn.cget("text"), kw.get("stay_first")))
        (self.continue_btn if Asked.answers.pop(0) else self.cancel_btn).invoke()


@pytest.fixture
def asked(monkeypatch):
    monkeypatch.setattr(app_mod, "WarningBox", Asked)
    monkeypatch.setattr(tkinter.messagebox, "askyesno", lambda *a, **k: pytest.fail("a system box was asked"))
    Asked.asked, Asked.answers = [], []
    return Asked


def test_closing_with_pages_not_finished_asks_first(hidden_root, asked):
    run = FakeRun(lambda kind, data: None, pages=4)
    w = Window(hidden_root, batch=run)
    run.post = lambda kind, data: A._handle_event(w, kind, data)
    stopped = []
    run.stop = lambda: stopped.append(True)
    _fed(w, 4)  # read and erased; the translations wait
    asked.answers = [False]  # Keep TASlation open
    w._on_close()
    text, go, stay, stay_first = asked.asked[0]
    assert text.startswith("4 page(s)") and "saved" in text and not stopped  # the window stays
    assert (go, stay, stay_first) == ("Close anyway", "Keep TASlation open", True)  # keeping it open is the default
    run.translate_all()
    asked.asked.clear()
    assert w._close_allowed() and not asked.asked


def test_the_closing_question_is_in_the_windows_language(hidden_root, asked):
    set_language("ja")
    try:
        run = FakeRun(lambda kind, data: None, pages=2)
        w = Window(hidden_root, batch=run)
        run.post = lambda kind, data: A._handle_event(w, kind, data)
        _fed(w, 2)
        asked.answers = [True]
        assert w._close_allowed()
        text, go, stay, _first = asked.asked[0]
        assert "2" in text and "TASlation" in text and "Close anyway?" not in text and go != "Close anyway" and stay != "Keep TASlation open"
        assert not any("a" <= c <= "z" for c in go + stay.replace("TASlation", ""))  # no English left on the buttons
    finally:
        set_language("en")


# ------------------------------------------------------------------ a page that went by, and the pictures after the run
def test_a_page_that_went_by_has_a_placeholder_until_the_reader_turns_back_to_it(hidden_root, no_way_to_the_viewer):
    w = Window(hidden_root)

    def handle(kind, data):
        A._handle_event(w, kind, data)

    handle("page_stage", {"seq": 1, "stage": "read", "state": "waiting", "thumb": thumb(picture(1))})
    handle("page_stage", {"seq": 2, "stage": "read", "state": "missed"})
    handle("page_missed", {"seq": 2, "fingerprint": "", "thumb": thumb(picture(2)), "pages": 1})
    cell = w._strip_model.pages[2]
    assert cell.missed and cell.thumb is None and not cell.unfinished  # (no question at closing for it)
    w.page_strip.canvas.xview_moveto(0)
    assert "went by" in w.page_strip.text_at(CELL_W + CELL_W // 2, 20)
    assert "turn back" in bar_tip("read", "missed")
    _click(w, 2)
    assert w._picture()[0] is w._live and "went by" in w.lines[-1] and "turn back" in w.lines[-1].lower()
    handle("page_stage", {"seq": 2, "stage": "read", "state": "waiting", "thumb": thumb(picture(2))})
    assert not cell.missed and cell.thumb is not None


def test_a_placeholder_merged_into_the_page_it_was_goes_and_the_cells_after_it_move_up(hidden_root,
                                                                                      no_way_to_the_viewer):
    w = Window(hidden_root)

    def handle(kind, data):
        A._handle_event(w, kind, data)

    handle("page_stage", {"seq": 1, "stage": "read", "state": "waiting", "thumb": thumb(picture(1))})
    handle("page_stage", {"seq": 2, "stage": "read", "state": "missed"})
    handle("page_stage", {"seq": 3, "stage": "read", "state": "waiting", "thumb": thumb(picture(3))})
    handle("page_stage", {"seq": 2, "stage": "read", "state": "merged", "into": 3})
    model = w._strip_model
    assert model.order == [1, 3] and 2 not in model.pages and len(model) == 2
    w.page_strip.canvas.xview_moveto(0)
    assert w.page_strip.at(CELL_W + CELL_W // 2, 20)[0] == 3  # page 3 is where the placeholder was
    handle("page_stage", {"seq": 2, "stage": "read", "state": "merged"})  # (again: nothing)
    assert model.order == [1, 3]
    assert not StripModel().update(5, stage="read", state="merged")  # a merge of a page never seen brings none


def test_after_the_run_a_click_shows_none_of_the_pipelines_pictures_and_closing_lets_them_go(hidden_root,
                                                                                            no_way_to_the_viewer):
    """The pipeline holds the last run's pictures for the render of a page the viewer shows (the erase done ahead):
    a click on a thumbnail reaches none of them, and closing lets them go."""
    held = {3: picture(3)}
    released = []
    w = Window(hidden_root)
    w.pipeline = SimpleNamespace(erased_ahead=held, release_page_images=lambda: released.append(True))
    A._handle_event(w, "page_stage", {"seq": 3, "stage": "read", "state": "done", "thumb": thumb(held[3])})
    for stage in ("erase", "translate"):
        A._handle_event(w, "page_stage", {"seq": 3, "stage": stage, "state": "done"})
    _click(w, 3)  # the batch is gone
    assert w._picture()[0] is w._live and w.lines[-1] == OPEN_IN_VIEWER.format(n=3)
    assert w._close_allowed() and released == [True] and w._picture()[0] is w._live


# ------------------------------------------------------------------ the role a book opens in
def test_the_role_follows_the_book_and_the_readers_choice_wins(tmp_path):
    assert start_role(False) == "translator" and start_role(True) == "reader"
    assert chosen_role(tmp_path, "Book A") == ""
    remember_role(tmp_path, "Book A", "reader")
    remember_role(tmp_path, "Book B", "nonsense")
    assert chosen_role(tmp_path, "Book A") == "reader" and chosen_role(tmp_path, "Book B") == ""


def test_the_cache_counts_its_pages_without_building_them(tmp_path):
    store = CacheStore(tmp_path / "cache")
    assert store.page_count("Book A", "English") == 0
    cache = store.open("Book A", "m", "English")
    cache.add(_page(FP_A))
    cache.add(_page(FP_B))
    cache.save()
    assert store.page_count("Book A", "English") == 2 and store.page_count("Book A", "German") == 0


class RoleWindow:
    """The parts of the window the role choice uses."""

    _book_for_role = A._book_for_role
    _decide_role = A._decide_role
    _start_role_known = A._start_role_known
    _apply_role = A._apply_role
    _on_role_changed = A._on_role_changed
    _reader_after_run = A._reader_after_run
    _complete_on_show = A._complete_on_show

    def __init__(self, root, state_dir, pages):
        self.root = root
        self.settings = SimpleNamespace(state_dir=state_dir)
        self.book_var = tk.StringVar(root, value="")
        self.lang_var = tk.StringVar(root, value="English")
        self.role_var = tk.StringVar(root, value="reader")
        self.store = SimpleNamespace(page_count=lambda book, language: pages.get(book, 0))
        self.posted, self.lines, self.switched = [], [], 0
        self._ready = threading.Event()

    def after(self, ms, call):
        return self.root.after(ms, call)

    def after_cancel(self, job):
        self.root.after_cancel(job)

    def _post(self, kind, **data):
        self.posted.append((kind, data))
        self._ready.set()

    def say(self, key, **values):
        self.lines.append(key)

    def _sync_tools(self):
        self.switched += 1

    def _close_find(self):
        pass

    def _redisplay(self):
        pass

    _ordering = _chosen_region = last_result = None

    def open_book(self, book):
        """The Book box names *book*; the count comes back from its thread and is taken as the event pump would."""
        self._ready.clear()
        self.book_var.set(book)
        self._decide_role()
        if self._ready.wait(2):
            kind, data = self.posted[-1]
            assert kind == "start_role"
            self._start_role_known(data)


def test_a_book_with_no_translations_opens_in_translator_mode_and_a_translated_one_in_reader_mode(hidden_root, tmp_path):
    w = RoleWindow(hidden_root, tmp_path, {"Translated Book": 12})
    w.open_book("New Book")
    assert w.role_var.get() == "translator" and "no translations yet" in w.lines[-1] and w.switched == 1
    w.open_book("Translated Book")
    assert w.role_var.get() == "reader" and "translated, so it opens in reader mode" in w.lines[-1]
    switched = w.switched
    w.open_book("Translated Book")  # the same book again: nothing is decided twice
    assert w.switched == switched


def test_the_readers_choice_for_a_book_wins_over_the_automatic_one(hidden_root, tmp_path):
    w = RoleWindow(hidden_root, tmp_path, {"Translated Book": 12})
    w.open_book("Translated Book")
    w.role_var.set("translator")
    w._on_role_changed()  # the reader clicks Translator for this book
    assert chosen_role(tmp_path, "Translated Book") == "translator"
    w2 = RoleWindow(hidden_root, tmp_path, {"Translated Book": 12})  # the next start
    w2.open_book("Translated Book")
    assert w2.role_var.get() == "translator" and not w2.posted  # no count needed


def test_a_name_that_names_no_book_and_a_late_count_change_nothing(hidden_root, tmp_path):
    w = RoleWindow(hidden_root, tmp_path, {})
    w.open_book(sorted(n for n in GENERIC_NAMES if n)[0].title())  # a viewer's or a browser's name
    assert w.role_var.get() == "reader" and not w.posted
    w.book_var.set("Other Book")
    w._start_role_known({"book": "New Book", "pages": 0})  # counted for a book no longer in the box
    assert w.role_var.get() == "reader"
    w._start_role_known({"book": "Other Book", "pages": None})  # could not be told
    assert w.role_var.get() == "reader"


def test_a_finished_run_that_translated_the_book_leaves_translator_mode_unless_the_reader_chose_it(hidden_root, tmp_path):
    w = RoleWindow(hidden_root, tmp_path, {"New Book": 0})
    w.open_book("New Book")
    assert w.role_var.get() == "translator"
    w.store = SimpleNamespace(page_count=lambda book, language: {"New Book": 31}.get(book, 0))  # the run is done
    assert w._reader_after_run("New Book", "English")
    assert w.role_var.get() == "reader" and w.lines[-1] == READER_AFTER_RUN
    assert chosen_role(tmp_path, "New Book") == ""  # not the reader's choice: the next start decides afresh
    assert not w._reader_after_run("New Book", "English")  # in reader mode already: nothing to say

    # the reader chose Translator for this book: their choice wins
    w.role_var.set("translator")
    w._on_role_changed()
    assert not w._reader_after_run("New Book", "English") and w.role_var.get() == "translator"


def test_a_run_that_translated_little_or_another_book_keeps_the_role(hidden_root, tmp_path):
    w = RoleWindow(hidden_root, tmp_path, {"Short Run": 2, "Other Book": 40})
    w.open_book("Short Run")
    w.role_var.set("translator")
    assert not w._reader_after_run("Short Run", "English")  # two pages are no book translated
    assert not w._reader_after_run("Other Book", "English")  # the Book box names another book by now
    w.store = SimpleNamespace(page_count=lambda book, language: None)
    w.book_var.set("Other Book")
    assert not w._reader_after_run("Other Book", "English") and w.role_var.get() == "translator"  # cannot be told


def test_the_book_box_decides_once_it_rests(hidden_root, tmp_path):
    w = RoleWindow(hidden_root, tmp_path, {})
    for name in ("N", "Ne", "New", "New Book"):
        w.book_var.set(name)
        w._book_for_role()
    deadline = time.monotonic() + 3
    while not w.posted and time.monotonic() < deadline:
        hidden_root.update()
        time.sleep(0.02)
    assert [d["book"] for _k, d in w.posted] == ["New Book"]
