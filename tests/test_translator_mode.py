"""Translator mode: every change to the page's regions - a translation edited, a region moved, resized, added or
dropped - taken back with Ctrl+Z and made again with Ctrl+Y, alone and mixed, on the real pipeline and stores; the
pointer's cursors; the editor's header, Kind words and the model being asked; the review list on a clean page; the
stores that cannot be opened or written. The window's parts are borrowed onto stand-ins whose jobs run at once."""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation.annotations import BookAnnotations, PageAnnotations, RegionNote
from taslation.cache import CachedBubble, CacheStore
from taslation.i18n import CATALOGS, set_language
from taslation.pipeline import Pipeline, manual_region
from taslation.translate import DictTranslator, TranslationError
from taslation.ui import app as app_mod
from taslation.ui import area, history, translator
from taslation.ui.dialogs import review
from taslation.ui.history import EditHistory, Step, UnitState
from taslation.ui.preview import ImageCanvas


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Jobs:
    """The worker's queue, with every job run as it is put (in the order they are put, as the worker would)."""

    def put(self, job):
        job()


class Window:
    """The parts of the App that translator mode's changes, undo and redo use, on the real pipeline."""

    _record = app_mod.App._record
    _move_region = app_mod.App._move_region
    _drop_region = app_mod.App._drop_region
    _edit_region = app_mod.App._edit_region
    _add_region = app_mod.App._add_region
    _region_at = app_mod.App._region_at
    _page_regions = app_mod.App._page_regions
    undo_edit = app_mod.App.undo_edit
    redo_edit = app_mod.App.redo_edit
    _step_through = app_mod.App._step_through
    toggle_skip = app_mod.App.toggle_skip
    toggle_order = app_mod.App.toggle_order
    retranslate_page = app_mod.App.retranslate_page
    _end_order = app_mod.App._end_order
    _kept_at_once = app_mod.App._kept_at_once
    _kept_after_reading = app_mod.App._kept_after_reading
    _page_to_work_on = app_mod.App._page_to_work_on

    def __init__(self, pipeline, result):
        self.pipeline, self.last_result = pipeline, result
        self.history = EditHistory()
        self.role_var, self.book_var, self.lang_var = Var("translator"), Var("Book"), Var("English")
        self.reading = self.busy = False
        self._ordering = self._chosen_region = None
        self.on_show = True
        self.events: list[tuple[str, dict]] = []
        self.said: list[str] = []
        self.read_again = 0
        self._jobs = Jobs()

    def _choose(self, region):
        self._chosen_region = region

    def _post(self, kind, **data):
        self.events.append((kind, data))
        if kind == "result":  # as the window takes a page: the selection stays while its region is on it
            self.last_result = data["result"]
            if not any(r is self._chosen_region for r in self.last_result.regions):
                self._chosen_region = None
        elif kind == "translate_done":
            self.busy = False
        elif kind == "status" and "key" in data:
            self.said.append(data["key"])

    def _go_busy(self):
        self.busy = True

    def say(self, key, **values):
        self.said.append(key)

    def _result_on_show(self):
        return self.on_show

    def _start_translate(self, image, complete=None, thumb=None, again=None):
        self.busy = True
        self.read_again += 1
        if again is not None:  # Translate again: what it translates anew replaces the cached page
            self.pipeline.forget_page(again)
        self._jobs.put(lambda: (self._post("result", result=self.pipeline.process(image, complete=True)),
                                self._post("translate_done")))

    def _label_order(self, text):
        pass

    def _redisplay(self):
        pass

    # what the tests look at
    def region(self, text):
        return next(r for r in self.last_result.regions if r.translated_text == text)

    def state(self):
        """The page as the stores hold it and as the window shows it (boxes rounded as a saved file has them)."""
        unit = self.last_result.units[0]
        page = self.pipeline.annotations.lookup(unit.fingerprint, unit.aspect, 6)
        notes = (sorted(json.dumps(b) for b in page.to_json()["add"]), sorted(json.dumps(b) for b in page.to_json()["ignore"]),
                 sorted(json.dumps(n) for n in page.to_json().get("notes", [])), page.to_json().get("order", [])
                 ) if page is not None else ([], [], [], [])
        hit = self.pipeline.cache.lookup(unit.fingerprint, unit.aspect, 36)
        bubbles = sorted(json.dumps(b.to_json(), ensure_ascii=False) for b in hit[0].bubbles) if hit else []
        regions = [(r.bbox, r.kind, r.status, r.translated_text, r.speaker, r.tag, r.reader_note)
                   for r in self.last_result.regions]
        return notes, bubbles, regions


@pytest.fixture
def window(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    result = pipeline.process(sample_page, complete=True)
    assert len(result.translated) >= 4 and len(cache) == 1
    return Window(pipeline, result)


def _picture(w):
    return np.asarray(w.last_result.image).copy()


# ------------------------------------------------------------------ each change taken back and made again
def test_an_edit_is_taken_back_and_made_again_with_its_premises(window):
    w = window
    start, picture = w.state(), _picture(w)
    target = w.region("Hello there!")
    w._edit_region(target, {"text": "Hi!", "speaker": "ピヨ", "kind": "shout", "continues": True, "note": "a pun",
                            "reader_note": "a note"})
    edited = w.state()
    assert target.translated_text == "Hi!" and target.tag == "shout" and target.reader_note == "a note"
    assert edited != start and "Hi!" in "".join(edited[1]) and any("shout" in n for n in edited[0][2])
    w.undo_edit()
    assert w.said[-1] == "Edit taken back." and w.state() == start and np.array_equal(_picture(w), picture)
    assert target.translated_text == "Hello there!" and target.tag == "" and target.reader_note == ""
    w.redo_edit()
    assert w.said[-1] == "Edit made again." and w.state() == edited and target.translated_text == "Hi!"
    w.undo_edit()
    assert w.state() == start and w.read_again == 0  # the page on show is the one edited: put back in place


def test_save_goes_to_the_page_the_editor_was_opened_on(window, sample_page2):
    """Auto turned the page behind the open editor: Save and Drop go to the page it was opened on, and the page on show
    stays the last result."""
    w = window
    first, target = w.last_result, w.region("Hello there!")
    victim = w.region("Thank you.")
    second = w.pipeline.process(sample_page2, complete=True)
    w.last_result = second  # the page turned while the editor stood open
    stored = (second.units[0].fingerprint, [r.translated_text for r in second.regions])
    w._edit_region(target, {"text": "Hi!", "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": ""},
                   first)
    assert target.translated_text == "Hi!" and w.history.done[-1].result is first
    hit = w.pipeline.cache.lookup(first.units[0].fingerprint, first.units[0].aspect, 36)
    assert any(b.text == "Hi!" for b in hit[0].bubbles)
    assert [r.translated_text for r in second.regions] == stored[1] and "Hi!" not in stored[1]
    assert [data.get("edited") for kind, data in w.events if kind == "result"][-1] is True  # the window keeps its page
    w.last_result = second
    w._drop_region(victim, first)
    assert all(r is not victim for r in first.regions) and len(second.regions) == len(stored[1])

    gone = w.said[:]  # a region that left that page is refused, with a line, and nothing is recorded
    done = len(w.history.done)
    w._edit_region(victim, {"text": "No."}, first)
    w._drop_region(victim, first)
    assert w.said[len(gone):] == [translator.NO_REGION] * 2 and len(w.history.done) == done


def test_a_move_and_a_resize_are_taken_back_and_made_again(window):
    w = window
    start, picture = w.state(), _picture(w)
    target = w.region("Thank you.")
    x0, y0, x1, y1 = old = target.bbox
    w._move_region(target, (x0 + 12, y0 + 9, x1 + 12, y1 + 9))
    moved = w.state()
    assert target.bbox == (x0 + 12, y0 + 9, x1 + 12, y1 + 9) and target.kind.startswith("manual")
    assert w.history.done[-1].kind == "move" and len(moved[0][0]) == 1 and len(moved[0][1]) == 1  # an add, an ignore
    w.undo_edit()
    assert w.said[-1] == "Move taken back." and target.bbox == old and not target.kind.startswith("manual")
    assert w.state() == start and np.array_equal(_picture(w), picture)  # nothing left of it: no mark, no stray bubble
    w.redo_edit()
    assert w.said[-1] == "Move made again." and w.state() == moved
    w.undo_edit()
    w._move_region(target, (x0 + 3, y0 + 3, x1 - 3, y1 - 3))
    assert w.history.done[-1].kind == "resize" and target.bbox == (x0 + 3, y0 + 3, x1 - 3, y1 - 3)
    w.undo_edit()
    assert w.said[-1] == "Resize taken back." and w.state() == start and target.bbox == old


def test_a_dropped_region_comes_back_whole_and_its_spot_is_text_again(window):
    w = window
    start, picture = w.state(), _picture(w)
    victim = w.region("Where are you going?")
    at = next(i for i, r in enumerate(w.last_result.regions) if r is victim)
    w._drop_region(victim)
    dropped = w.state()
    assert all(r is not victim for r in w.last_result.regions) and w.said[-1] == "Region dropped; Ctrl+Z brings it back."
    assert len(dropped[0][1]) == 1 and len(dropped[1]) == len(start[1]) - 1  # remembered as not text; its bubble gone
    assert [r.order for r in w.last_result.regions] == list(range(len(w.last_result.regions)))
    w.undo_edit()
    assert w.said[-1] == "The dropped region is back." and w._chosen_region is victim  # selected: here it is
    assert w.last_result.regions[at] is victim and victim.status == "translated" and victim.translated_text == "Where are you going?"
    assert w.state() == start and np.array_equal(_picture(w), picture)  # the "not text" mark is gone, the bubble is back
    again = w.pipeline.process(w.last_result.original, complete=True)  # and the next reading finds it there
    assert any(r.translated_text == "Where are you going?" for r in again.regions)
    w.redo_edit()
    assert w.said[-1] == "Region dropped again." and w.state() == dropped and w._chosen_region is None


def test_an_added_region_is_taken_back_and_made_again_without_asking_the_model(window):
    w = window
    start = w.state()
    unit = w.last_result.units[0]
    box = unit.denormalize((0.03, 0.03, 0.18, 0.11))  # a corner with no bubble
    w._add_region(box)
    added = w.state()
    manual = [r for r in w.last_result.regions if r.kind.startswith("manual")]
    assert len(manual) == 1 and manual[0].status == "translated" and w.read_again == 1
    assert len(added[0][0]) == 1 and len(added[1]) == len(start[1]) + 1 and w.history.done[-1].state == "done"
    w.undo_edit()
    assert w.said[-1] == "The region you added is gone again." and w.read_again == 2  # the page read again from the stores
    assert w.state() == start and not any(r.kind.startswith("manual") for r in w.last_result.regions)
    asked = len(w.pipeline.translator.calls)
    w.redo_edit()
    assert w.said[-1] == "Region added again." and w.state() == added
    assert len(w.pipeline.translator.calls) == asked  # its translation came back from the stores


def test_an_edit_made_before_a_move_is_still_taken_back_after_it(window):
    """The review's case: an edit, then a move of the same region; Ctrl+Z twice takes back both, newest first."""
    w = window
    start = w.state()
    target = w.region("It's fine.")
    w._edit_region(target, {"text": "All good.", "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": ""})
    edited = w.state()
    x0, y0, x1, y1 = target.bbox
    w._move_region(target, (x0 + 4, y0 + 4, x1 - 4, y1 - 4))  # smaller: nothing new to read, the edit stays
    assert target.translated_text == "All good." and target.kind.startswith("manual")
    w.undo_edit()
    assert w.said[-1] == "Resize taken back." and w.state() == edited
    w.undo_edit()
    assert w.said[-1] == "Edit taken back." and w.state() == start and target.translated_text == "It's fine."
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo."


def test_a_mixed_sequence_is_taken_back_in_reverse_and_made_again_in_order(window):
    w = window
    states = [w.state()]
    a, b, c = w.region("Hello there!"), w.region("Thank you."), w.region("Nice weather today, huh?")
    w._edit_region(a, {"text": "Hey!", "speaker": "", "kind": "thought", "continues": False, "note": "", "reader_note": ""})
    states.append(w.state())
    w._move_region(b, (b.x0 + 8, b.y0, b.x1 + 8, b.y1))
    states.append(w.state())
    w._drop_region(c)
    states.append(w.state())
    unit = w.last_result.units[0]
    w._add_region(unit.denormalize((0.03, 0.03, 0.18, 0.11)))
    states.append(w.state())
    w._edit_region(w.region("Hey!"), {"text": "Hey you!", "speaker": "", "kind": "thought", "continues": False,
                                      "note": "", "reader_note": ""})  # on the page read again after the add
    states.append(w.state())
    for expected in reversed(states[:-1]):
        w.undo_edit()
        assert w.state() == expected, w.said[-1]
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo."
    for expected in states[1:]:
        w.redo_edit()
        assert w.state() == expected, w.said[-1]
    w.redo_edit()
    assert w.said[-1] == "Nothing to redo."


def test_a_new_change_ends_the_redo_of_the_changes_taken_back_on_its_page(window):
    w = window
    a = w.region("Hello there!")
    w._edit_region(a, {"text": "One", "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": ""})
    w.undo_edit()
    w._edit_region(a, {"text": "Two", "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": ""})
    w.redo_edit()
    assert w.said[-1] == "Nothing to redo." and a.translated_text == "Two"
    nothing = len(w.history)
    w._edit_region(a, {"text": "Two", "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": ""})
    assert len(w.history) == nothing  # a save that changed nothing is not a change to take back
    w.undo_edit()
    assert a.translated_text == "Hello there!"


def test_a_change_on_a_page_read_again_is_taken_back_from_the_stores(window):
    """The page was read again after the move (turned away and back): Ctrl+Z puts the stores back and reads it."""
    w = window
    start = w.state()
    target = w.region("Thank you.")
    w._move_region(target, (target.x0 + 10, target.y0, target.x1 + 10, target.y1))
    w.last_result = w.pipeline.process(w.last_result.original, complete=True)  # another reading of the same page
    w.undo_edit()
    assert w.read_again == 1 and w.said[-1] == "Move taken back." and w.state()[:2] == start[:2]
    assert sorted(r[0] for r in w.state()[2]) == sorted(r[0] for r in start[2])


def test_undo_says_when_there_is_nothing_on_this_page_or_another_page_is_on_show(window, sample_page2):
    w = window
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo."
    w.redo_edit()
    assert w.said[-1] == "Nothing to redo."
    w._drop_region(w.region("Thank you."))
    first = w.last_result
    w.last_result = w.pipeline.process(sample_page2, complete=True)  # another page on show
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo on this page."
    w.on_show = False  # the viewer shows a page not translated yet
    w.last_result = first
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo on this page."
    w.on_show = True
    w.role_var.set("reader")  # nor in the reader role, nor while busy, nor while a reading order is set
    w.undo_edit()
    w.role_var.set("translator")
    w._ordering = []
    w.undo_edit()
    assert w.said[-1].startswith("Reading order:")
    w._ordering = None
    w.undo_edit()
    assert w.said[-1] == "The dropped region is back."


def test_a_store_that_cannot_be_written_is_said_and_the_change_stays_in_memory(window, monkeypatch):
    w = window
    start = w.state()
    w._drop_region(w.region("Thank you."))

    def locked():
        raise PermissionError(13, "The process cannot access the file", "Book.json")

    monkeypatch.setattr(w.pipeline.annotations, "save", locked)
    w.undo_edit()
    assert w.said[-1] == "Could not save the change: {error}" and w.state() == start
    error = next(d for k, d in reversed(w.events) if k == "status")
    assert "cannot access" in error["values"]["error"]


def test_the_status_line_says_a_page_skipped_after_it_is_read_again(window):
    w = window
    w.toggle_skip()
    assert w.said[-1] == "Page marked as skipped: nothing on it is translated." and not w.last_result.translated
    w.toggle_skip()
    assert w.said[-1] == "Page no longer skipped." and w.last_result.translated


def _skipped_and_order(w):
    unit = w.last_result.units[0]
    page = w.pipeline.annotations.lookup(unit.fingerprint, unit.aspect, 6)
    return (page.skip, len(page.order)) if page is not None else (False, 0)


def test_skip_page_is_taken_back_and_made_again(window):
    w = window
    start = w.state()
    w.toggle_skip()
    assert _skipped_and_order(w)[0] and not w.last_result.translated
    w.undo_edit()
    assert w.said[-1] == "Skip page taken back." and not _skipped_and_order(w)[0]
    assert w.state()[1:] == start[1:]  # the cached translations and the page shown as before
    w.redo_edit()
    assert w.said[-1] == "Skip page made again." and _skipped_and_order(w)[0] and not w.last_result.translated
    w.undo_edit()
    assert not _skipped_and_order(w)[0] and w.state()[1:] == start[1:]


def test_a_reading_order_is_taken_back_and_made_again(window):
    w = window
    regions = w._page_regions()
    w._ordering = list(reversed(regions))
    w.toggle_order()
    assert w.said[-1] == "Reading order saved for {n} region(s). Translate again applies it."
    assert _skipped_and_order(w) == (False, len(regions))
    w.undo_edit()
    assert w.said[-1] == "Reading order taken back." and _skipped_and_order(w) == (False, 0)
    w.redo_edit()
    assert w.said[-1] == "Reading order made again." and _skipped_and_order(w) == (False, len(regions))


def test_translate_again_is_taken_back_and_made_again(window, monkeypatch):
    from taslation.ui.dialogs import caches

    w = window
    start = w.state()
    monkeypatch.setattr(caches, "ask", lambda *_a, **_k: True)
    w.pipeline.translator = DictTranslator({}, default="Said anew.")
    w.retranslate_page()
    anew = w.state()
    assert anew[1] != start[1] and all(r.translated_text == "Said anew." for r in w.last_result.translated)
    w.undo_edit()
    assert w.said[-1] == "Translate again taken back: the earlier translations are back."
    assert w.state()[1] == start[1] and w.region("Hello there!")
    w.redo_edit()
    assert w.said[-1] == "Translate again made again: its translations are back." and w.state()[1] == anew[1]


def test_translate_again_that_changes_nothing_is_no_step(window, monkeypatch):
    from taslation.ui.dialogs import caches

    w = window
    monkeypatch.setattr(caches, "ask", lambda *_a, **_k: True)
    w.retranslate_page()  # the same translator: the same lines
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo."


def test_a_rectangle_not_written_leaves_nothing_behind(window, monkeypatch):
    w = window
    start = w.state()
    monkeypatch.setattr(w.pipeline.annotations, "save", lambda: (_ for _ in ()).throw(OSError("locked")))
    w._add_region(w.last_result.units[0].denormalize((0.03, 0.03, 0.18, 0.11)))
    assert w.said[-1].startswith("Could not save the rectangle:") and w.state() == start and not len(w.history)
    w.pipeline.annotations = None
    w._add_region((10, 10, 60, 60))
    assert w.said[-1] == "Could not record the rectangle: give the book a name first (the Book field)."


# ------------------------------------------------------------------ the stores carried back and forth
def test_carrying_a_change_leaves_what_else_changed_on_the_page():
    """Taking back changes only what the change made differ: a reading order set and a bubble renamed meanwhile
    stay, a bubble moved goes back to its place."""
    a, b, c = (0.1, 0.1, 0.3, 0.2), (0.5, 0.5, 0.7, 0.6), (0.52, 0.5, 0.72, 0.6)
    before = UnitState("f" * 80, 0.7, PageAnnotations("f" * 80, 0.7, order=[a, b]),
                       [CachedBubble(a, "One"), CachedBubble(b, "Two")])
    after = UnitState("f" * 80, 0.7, PageAnnotations("f" * 80, 0.7, add=[c], ignore=[b], order=[a, c],
                                                     notes=[RegionNote(c, speaker="Piyo")]),
                      [CachedBubble(a, "One"), CachedBubble(c, "Two")])
    live_page = PageAnnotations("f" * 80, 0.7, add=[c], ignore=[b], order=[c, a], notes=[RegionNote(c, speaker="Piyo")])
    live_bubbles = [CachedBubble(a, "One (renamed)"), CachedBubble(c, "Two")]

    class Store:
        def __init__(self):
            self.saved = 0

        def save(self):
            self.saved += 1

    class Ann(Store):
        def lookup(self, fp, aspect, max_distance):
            return live_page

    class Cache(Store):
        def __init__(self):
            super().__init__()
            self.added = []

        def lookup(self, fp, aspect, max_distance, hint=None):
            return (SimpleNamespace(fingerprint="f" * 80, aspect=0.7, bubbles=live_bubbles, incomplete=False), 0)

        def add(self, page):
            self.added.append(page)

    pipeline = SimpleNamespace(annotations=Ann(), cache=Cache(), settings=SimpleNamespace(fingerprint_max_distance=36))
    assert history.carry(pipeline, [after], [before]) == []
    assert live_page.add == [] and live_page.ignore == [] and live_page.notes == []
    assert live_page.order == [b, a]  # the order set meanwhile stays, the moved region's entry is back at its box
    page = pipeline.cache.added[-1]
    assert sorted((bb.box, bb.text) for bb in page.bubbles) == [(a, "One (renamed)"), (b, "Two")]
    assert pipeline.annotations.saved == 1 and pipeline.cache.saved == 1
    assert history.carry(pipeline, [before], [before]) == []  # nothing to carry: nothing written
    assert pipeline.annotations.saved == 1 and pipeline.cache.saved == 1


def test_a_page_counts_as_the_same_page_within_the_fingerprints_distance():
    h = EditHistory(limit=3)
    page = [("0" * 80, 0.7)]
    near = [("0" * 79 + "1", 0.7)]
    far = [("f" * 80, 0.7)]
    steps = [h.record(Step("edit", None, ("Book", "Book", "English"), page)) for _i in range(4)]
    assert len(h.done) == 3 and h.done[0] is steps[1]  # at most three kept
    for s in steps:
        s.state = "done"
    steps[3].state = "empty"  # changed nothing: passed by, and forgotten
    assert h.last(near, ("Book", "Book", "English")) is steps[2] and len(h.done) == 2
    assert h.last(far, ("Book", "Book", "English")) is None
    assert h.last(page, ("Other", "Other", "English")) is None  # another book's stores
    h.taken_back(steps[2])
    assert h.last(page, ("Book", "Book", "English"), undone=True) is steps[2] and len(h) == 1
    h.record(Step("move", None, ("Book", "Book", "English"), near))
    assert h.last(page, ("Book", "Book", "English"), undone=True) is None  # a new change there: no redo


# ------------------------------------------------------------------ the pointer
class Pointer:
    _editing = app_mod.App._editing
    _grip_of = app_mod.App._grip_of
    _page_grip = app_mod.App._page_grip
    _turn_of = app_mod.App._turn_of
    _frame_of = app_mod.App._frame_of
    _shown_frame = app_mod.App._shown_frame
    _choose = app_mod.App._choose
    _draw_chosen = app_mod.App._draw_chosen
    _draw_frame = app_mod.App._draw_frame
    _on_motion = app_mod.App._on_motion
    _region_at = app_mod.App._region_at
    _page_regions = app_mod.App._page_regions
    _result_on_show = app_mod.App._result_on_show

    def __init__(self, root, regions):
        self.canvas = ImageCanvas(root)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        page = Image.new("RGB", (400, 300), "white")
        self.last_result = SimpleNamespace(image=page, original=page, regions=regions)
        self.role_var = Var("translator")
        self.reading = self.busy = False
        self._fill = self._live = self._ordering = None
        self._chosen_region = self._grip_box = self._turn = self._frame_cache = None
        self.canvas.set_image(page)

    def cursor_at(self, x, y):
        self._on_motion(SimpleNamespace(x=x, y=y))
        return str(self.canvas.cget("cursor"))


def test_the_pointer_shows_what_a_press_would_do(hidden_root):
    a = manual_region(np.full((300, 400, 3), 255, np.uint8), (50, 50, 150, 120))
    b = manual_region(np.full((300, 400, 3), 255, np.uint8), (200, 150, 300, 250))
    w = Pointer(hidden_root, [a, b])
    assert w.cursor_at(100, 80) == translator.HAND and w.cursor_at(250, 200) == translator.HAND  # any region: a hand
    assert w.cursor_at(350, 30) == "crosshair"  # empty space on the page: a drag adds a region
    w._choose(a)
    assert w.cursor_at(100, 80) == "fleur" and w.cursor_at(150, 120) == "size_nw_se"  # the selected one: move, resize
    assert w.cursor_at(100, 50) == "size_ns" and w.cursor_at(50, 85) == "size_we" and w.cursor_at(250, 200) == translator.HAND
    assert w.cursor_at(100, 50 - area.ROTATE_GAP) == area.ROTATE_CURSORS[0]  # its rotate handle: circling arrows
    w._ordering = []  # setting the reading order: a hand on the regions to number, nothing else
    assert w.cursor_at(100, 80) == translator.HAND and w.cursor_at(350, 30) == ""
    w._ordering = None
    w.busy = True
    assert w.cursor_at(100, 80) == ""
    w.busy = False
    w.role_var.set("reader")  # the reader's pointer is the viewer's
    assert w.cursor_at(100, 80) == "" and w.cursor_at(350, 30) == ""


class Drawn:
    """A canvas that keeps what is drawn on it, in image pixels (scale 1, no offset)."""

    scale, offset = 1.0, (0, 0)

    def __init__(self):
        self.items: list[tuple] = []

    def delete(self, tag):
        self.items.clear()

    def draw_frame(self, box, tag, colour="", with_handles=True):
        self.items.append(("box", tuple(box), area.handles(box)))

    def draw_turned_frame(self, corners, tag, colour="", with_handles=True):
        self.items.append(("turned", list(corners), area.frame_handles(list(corners))))

    def draw_rotate_handle(self, corners, tag, colour=""):
        self.items.append(("rotate", area.rotate_handle(list(corners), room=self.room())))

    def room(self):
        return (0.0, 0.0, 2000.0, 2000.0)


def test_an_upright_region_keeps_its_box_and_handles_and_a_turned_one_is_drawn_turned(hidden_root):
    from taslation.annotations import RegionStyle

    a = manual_region(np.full((300, 400, 3), 255, np.uint8), (50, 50, 150, 120))
    w = Pointer(hidden_root, [a])
    w.canvas = Drawn()
    w._choose(a)
    assert [i[0] for i in w.canvas.items] == ["box", "rotate"]
    assert w.canvas.items[0][1:] == ((50, 50, 150, 120), area.handles((50, 50, 150, 120)))  # as before
    assert w.canvas.items[1][1] == ((100, 50), (100, 50 - area.ROTATE_GAP))
    a.style = RegionStyle(slant=30.0)
    w._draw_frame()
    kind, corners, points = w.canvas.items[0]
    assert kind == "turned" and area.frame_angle(corners) == pytest.approx(30.0, abs=1.0)
    assert w.canvas.items[1][1][0] == pytest.approx(points["n"])  # the rotate handle on the turned frame's top
    w._grip_box = (60, 55, 160, 125)  # moved: the turned frame goes with it
    w._draw_frame()
    assert w.canvas.items[0][1] == pytest.approx([(x + 10, y + 5) for x, y in corners])


def test_a_turned_regions_handles_resize_the_side_they_point_to(hidden_root):
    from taslation.annotations import RegionStyle

    a = manual_region(np.full((300, 400, 3), 255, np.uint8), (150, 100, 250, 140))
    a.style = RegionStyle(slant=89.0)
    w = Pointer(hidden_root, [a])
    w._choose(a)
    points = area.frame_handles(w._frame_of(a))
    assert w._grip_of(*points["n"]) == "n" and w._page_grip("n") == "w"  # its top side lies on the page's left
    assert w.cursor_at(*points["n"]) == "size_we" and w.cursor_at(*points["e"]) == "size_ns"
    assert w._grip_of(200, 120) == "move"


def _move(x, y, state=0):
    return SimpleNamespace(x=x, y=y, state=state)


class Rotating(Window):
    """The window's pointer on the real pipeline, on a canvas that keeps what is drawn (`Drawn`)."""

    _on_press = app_mod.App._on_press
    _on_drag = app_mod.App._on_drag
    _on_release = app_mod.App._on_release
    _cancel_drag = app_mod.App._cancel_drag
    _rotate_region = app_mod.App._rotate_region
    _turn_direction = app_mod.App._turn_direction
    _restyle = app_mod.App._restyle
    _grip_of = app_mod.App._grip_of
    _page_grip = app_mod.App._page_grip
    _turn_of = app_mod.App._turn_of
    _frame_of = app_mod.App._frame_of
    _shown_frame = app_mod.App._shown_frame
    _draw_frame = app_mod.App._draw_frame
    _draw_chosen = app_mod.App._draw_chosen
    _editing = app_mod.App._editing

    def __init__(self, pipeline, result):
        super().__init__(pipeline, result)
        self.canvas = Drawn()
        self.canvas.focus_set = lambda: None
        self.canvas.inside = lambda x, y: True
        self.canvas.to_image_coords = lambda x, y: (int(x), int(y))
        self._drag_start = self._drag_rect = self._grip = self._grip_start = self._grip_box = None
        self._turn = self._frame_cache = None
        self.shown: list[str] = []

    def _choose(self, region):
        self._chosen_region = region

    def _redisplay(self):
        pass

    def status(self, line):
        self.shown.append(line())

    def turn(self, region, degrees, state=0, release=True):
        """Take hold of *region*'s rotate handle and go round its middle by *degrees*."""
        self._chosen_region = region
        corners = self._frame_of(region)
        knob = area.rotate_handle(corners, room=self.canvas.room())[1]
        centre = area.frame_centre(corners)
        r = ((knob[0] - centre[0]) ** 2 + (knob[1] - centre[1]) ** 2) ** 0.5
        now = area.pointer_angle(centre, knob) + degrees
        import math

        x, y = centre[0] - r * math.sin(math.radians(now)), centre[1] - r * math.cos(math.radians(now))
        self._on_press(_move(*knob))
        assert self._grip == "rotate"
        self._on_drag(_move((knob[0] + x) / 2, (knob[1] + y) / 2, state))
        self._on_drag(_move(x, y, state))
        if release:
            self._on_release(_move(x, y, state))


def test_the_rotate_handle_stores_the_slant_as_the_editor_does_and_undo_takes_it_back(window, hidden_root):
    w = Rotating(window.pipeline, window.last_result)
    start = w.state()
    target = w.region("Hello there!")
    assert w._turn_of(target) == 0.0
    w.turn(target, 30.0)
    assert target.style is not None and target.style.slant == 30.0 and w.history.done[-1].kind == "rotate"
    assert w.shown[-1].endswith("30°")  # the angle shows while it is turned
    rotated = w.state()
    assert rotated != start and any('"slant": 30.0' in n for n in rotated[0][2])  # with the book's premises
    unit = w.last_result.units[0]
    note = w.pipeline.annotations.page(unit.fingerprint, unit.aspect).note_at(unit.normalize(target.bbox), 0.5)
    assert note is not None and note.style.slant == 30.0
    w.undo_edit()
    assert w.said[-1] == "Rotation taken back." and w.state() == start and target.style is None
    w.redo_edit()
    assert w.said[-1] == "Rotation made again." and w.state() == rotated and target.style.slant == 30.0
    d = review.EditBubbleDialog(hidden_root, target, [], on_save=lambda data: None, on_drop=lambda: None)
    assert not d.slant_auto.get() and d.slant_var.get() == "30" and d.style().slant == 30.0  # the editor agrees
    d.destroy()


def test_shift_turns_in_steps_esc_cancels_and_a_click_on_the_handle_changes_nothing(window):
    w = Rotating(window.pipeline, window.last_result)
    target = w.region("Hello there!")
    w.turn(target, 37.0, state=0x0001)  # Shift
    assert target.style.slant == 30.0
    done = len(w.history.done)
    w.turn(target, -20.0, release=False)
    assert w._turn["angle"] == 10.0 and w.canvas.items[0][0] == "turned"
    assert w._cancel_drag() and w._turn is None
    w._on_release(_move(0, 0))
    assert len(w.history.done) == done and target.style.slant == 30.0
    assert w.canvas.items and area.frame_angle(w.canvas.items[0][1]) == pytest.approx(30.0, abs=1.0)  # back
    w.turn(target, 0.0)  # pressed and let go without turning
    assert len(w.history.done) == done
    assert not w._cancel_drag()  # nothing to cancel


# ------------------------------------------------------------------ the editor and the review list
def _region(status="translated", tag=""):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text, r.tag = status, "Nice weather today, huh?", "今日はいい天気だね", tag
    return r


def test_the_editor_names_the_bubble_and_its_kind_in_words(hidden_root):
    saved = []
    set_language("ja")
    d = review.EditBubbleDialog(hidden_root, _region(tag="thought"), [], on_save=saved.append, on_drop=lambda: None,
                                place=(4, 6))
    assert d.winfo_children()[0].winfo_children()[0].cget("text") == "吹き出し 6 個中 4 番目・訳文あり"
    assert list(d.kind_box.cget("values")) == ["（指定なし）", "台詞", "心の声", "叫び", "ナレーション", "効果音", "手書き",
                                               "消去のみ"]
    assert d.kind_var.get() == "心の声" and d._data()["kind"] == "thought"
    d.kind_var.set("叫び")
    assert d._data()["kind"] == "shout"
    d.kind_var.set("（指定なし）")
    assert d._data()["kind"] == ""
    d.destroy()
    set_language("de")
    d = review.EditBubbleDialog(hidden_root, _region("untranslated"), [], on_save=saved.append, on_drop=lambda: None,
                                place=(1, 3))
    assert d.winfo_children()[0].winfo_children()[0].cget("text") == "Sprechblase 1 von 3 · unübersetzt"
    assert "Soundeffekt" in d.kind_box.cget("values") and d.kind_var.get() == "(nicht angegeben)"
    d.destroy()
    set_language("en")
    assert review.kind_words() == ["(not set)", "Speech", "Thought", "Shout", "Narration", "Sound effect", "Handwritten",
                                   "Erase only"]
    for word in (*review.REGION_KIND_WORDS.values(), *review.ASKING.values()):
        assert all(word in CATALOGS[code] for code in CATALOGS if code != "en"), word


def test_the_editor_waits_for_the_model_and_says_what_came(hidden_root):
    asked = []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_ask=lambda mode, answer: (asked.append((mode, answer)), True)[1], place=(2, 5))
    (ask_again,) = d.ask_btns  # no Alternatives (removed 2026-11-06): Ask again alone
    ask_again.invoke()
    assert asked[-1][0] == "again" and d.busy_var.get() == "Asking the model for a new translation..."
    assert d.busy_bar.winfo_manager() == "pack"
    assert all(str(b.cget("state")) == "disabled" for b in (d.save_btn, d.drop_btn, ask_again))
    d.show_answers("again", ["A brand-new line."])  # as the window hands them over
    assert d.text.get("1.0", "end").strip() == "A brand-new line." and not d.busy_bar.winfo_manager()
    assert d.busy_var.get().startswith("The model's new translation is in the box")
    assert str(d.text.cget("background")) == review.FLASH  # the box lights up for a moment
    assert all(str(b.cget("state")) == "normal" for b in (d.save_btn, d.drop_btn, ask_again))
    ask_again.invoke()
    asked[-1][1]["error"] = "cannot reach Ollama"  # the worker says what went wrong
    d.show_answers("again", [])
    assert d.busy_var.get() == "No answer from the model: cannot reach Ollama" and str(d.save_btn.cget("state")) == "normal"
    ask_again.invoke()
    d.show_answers("again", [])
    assert d.busy_var.get() == "The model gave no other translation."
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_ask=lambda mode, answer: False)
    d.ask_btns[0].invoke()  # the model cannot be asked now: the buttons do not wait
    assert str(d.save_btn.cget("state")) == "normal" and d.busy_var.get() == "The model gave no other translation."
    d.destroy()


class Asker:
    _ask_model = app_mod.App._ask_model

    def __init__(self, answers):
        self.pipeline = SimpleNamespace(ask_again=answers)
        self.last_result = object()
        self.events, self.said = [], []
        self._jobs = Jobs()

    def say(self, key, **values):
        self.said.append(key)

    def _post(self, kind, **data):
        self.events.append((kind, data))


def test_the_model_asked_from_the_editor_always_answers_it():
    def failing(*_args):
        raise TranslationError("cannot reach Ollama (test)")

    w = Asker(failing)
    answer: dict = {}
    assert w._ask_model(SimpleNamespace(), "again", answer)
    assert w.events[0] == ("asked", {"mode": "again", "texts": []}) and answer["error"] == "cannot reach Ollama (test)"
    assert w.events[1] == ("status", {"text": "cannot reach Ollama (test)"})
    w = Asker(lambda *_args: "")  # nothing came: no text handed over
    w._ask_model(SimpleNamespace(), "again", {})
    assert w.events == [("asked", {"mode": "again", "texts": []})]
    w = Asker(lambda *_args: "Other.")
    w._ask_model(SimpleNamespace(), "again", {})
    assert w.events == [("asked", {"mode": "again", "texts": ["Other."]})]
    w.pipeline = None
    assert not w._ask_model(SimpleNamespace(), "again", {})


def test_the_review_list_says_when_nothing_on_the_page_needs_a_look(hidden_root):
    edited = []
    d = review.ReviewDialog(hidden_root, [], on_edit=edited.append)
    assert d.empty.winfo_manager() == "pack" and not d.tree.winfo_manager()
    assert str(d.empty.cget("text")) == "Nothing on this page needs a look." and str(d.edit_btn.cget("state")) == "disabled"
    flagged = _region("untranslated")
    d.fill([(flagged, "untranslated", "")])
    assert d.tree.winfo_manager() == "pack" and not d.empty.winfo_manager() and str(d.edit_btn.cget("state")) == "normal"
    d.fill([])
    assert d.empty.winfo_manager() == "pack" and not d.tree.winfo_manager()
    d.destroy()
    set_language("ja")
    d = review.ReviewDialog(hidden_root, [], on_edit=edited.append)
    assert str(d.empty.cget("text")) == "このページに確認が必要な領域はありません。"
    d.destroy()


# ------------------------------------------------------------------ stores that cannot be opened
class Sheets:
    _speaker_names = app_mod.App._speaker_names
    _propose_renderings = app_mod.App._propose_renderings
    _refresh_premises = app_mod.App._refresh_premises

    def __init__(self, error):
        def open_(*_args):
            raise error

        self.glossary_store = SimpleNamespace(open=open_)
        self.book_var, self.lang_var = Var("Book"), Var("English")
        self.pipeline = SimpleNamespace(check_sheet=lambda: None)
        self.said, self.events = [], []
        self._jobs = Jobs()

    def say(self, key, **values):
        self.said.append((key, values))

    def _post(self, kind, **data):
        self.events.append((kind, data))

    def _job_refresh_premises(self, book, language):
        self.glossary_store.open(book, language)


def test_a_series_sheet_that_cannot_be_opened_is_said_in_the_status_line():
    w = Sheets(PermissionError(13, "The process cannot access the file"))
    assert w._speaker_names() == []  # the editor opens all the same, without the sheet's speakers
    key, values = w.said[-1]
    assert key == "Could not open the series sheet: {error}" and "cannot access" in str(values["error"])
    w._propose_renderings([("Piyo", "Piyoo")])
    assert w.said[-1][0] == "Could not open the series sheet: {error}"
    w._refresh_premises("Book", "English")
    assert w.events[-1][0] == "status" and w.events[-1][1]["key"] == "Could not open the book's premises: {error}"
    w = Sheets(FileExistsError("another series has its name"))
    assert w._speaker_names() == [] and w.said[-1][0] == "Could not open the series sheet: {error}"
    w.book_var.set("")
    assert w._speaker_names() == []


def test_every_line_translator_mode_says_is_in_every_language():
    keys = [translator.HINT, translator.CLICK_HINT, *translator.TAKEN_BACK.values(), *translator.MADE_AGAIN.values()]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])


def test_t_turns_the_selected_regions_text_direction_and_undo_takes_it_back(window):
    w = Rotating(window.pipeline, window.last_result)
    start, picture = w.state(), _picture(w)
    w._chosen_region = None
    w._turn_direction()
    assert w.said[-1] == "Select a region first (click it)." and not w.history.done
    target = w.region("Hello there!")
    w._chosen_region = target
    w._turn_direction()
    assert target.style.direction == "down" and w.history.done[-1].kind == "direction"
    assert not np.array_equal(_picture(w), picture)  # lettered again, turned
    assert [d.get("values") for k, d in w.events if k == "status"][-1] == {"direction": "Rotate all text 90°"}
    turned = w.state()
    assert any('"direction": "down"' in n for n in turned[0][2])
    for expected in ("up", "stacked", ""):
        w._turn_direction()
        assert (target.style.direction if target.style is not None else "") == expected
    assert w.state() == start and np.array_equal(_picture(w), picture)  # back to Auto: as it was
    w.undo_edit()
    assert w.said[-1] == "Text direction taken back." and target.style.direction == "stacked"
    w.redo_edit()
    assert w.said[-1] == "Text direction made again." and w.state() == start
