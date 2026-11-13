"""The region editor's flow: the region's picture from the frame in memory, its Japanese read again on demand on a page
shown from the cache (which keeps none), "Read as:" and Ask again then working there, Previous and Next through the
page's regions in reading order (saving what changed), and the question before what was typed is dropped."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, store_text
from PIL import Image

from taslation.annotations import BookAnnotations, RegionStyle
from taslation.cache import CacheStore
from taslation.i18n import CATALOGS
from taslation.pipeline import Pipeline, manual_region
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import translator
from taslation.ui.dialogs import caches, review
from taslation.ui.history import EditHistory
from taslation.ui.translator import LivePreview, editor_crop, editor_regions


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Jobs:
    def put(self, job):
        job()


def _pipeline(settings, book="Book"):
    cache = CacheStore(settings.cache_dir).open(book, "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / f"{book}.json", book)
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                    annotations=ann)


@pytest.fixture
def cached(settings, sample_page):
    """A page translated once, then shown from the cache by a pipeline of a new start: no region knows its Japanese."""
    first = _pipeline(settings)
    first.process(sample_page, complete=True)
    pipeline = _pipeline(settings)
    result = pipeline.process(sample_page, complete=True)
    assert result.translated and all(r.from_cache and not r.source_text for r in result.translated)
    return pipeline, result


# ------------------------------------------------------------------ the Japanese read again, on demand
def test_a_region_of_a_cached_page_is_read_again_in_memory_and_nothing_is_stored(cached, settings):
    pipeline, result = cached
    files = {p.name: p.read_bytes() for p in settings.cache_dir.glob("*.json")}
    region = result.translated[0]
    text, status = region.translated_text, region.status
    read = pipeline.read_source(result, region)
    assert read and region.source_text == read and region.translated_text == text and region.status == status
    assert {p.name: p.read_bytes() for p in settings.cache_dir.glob("*.json")} == files  # nothing written
    assert read not in "".join(store_text(p) for p in settings.cache_dir.glob("*.json"))
    pipeline.ocr = None
    assert pipeline.read_source(result, result.translated[1]) == "" and not result.translated[1].source_text


class Reader:
    """What the editor's reading needs of the window: the worker's jobs and its timers run at once."""

    _read_source = app_mod.App._read_source
    _source_read = app_mod.App._source_read

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self._jobs = Jobs()

    def after(self, _ms, callback):
        callback()


def test_the_window_reads_the_japanese_in_its_worker_and_hands_it_to_the_editor(cached):
    pipeline, result = cached
    region = result.translated[0]
    got = []
    w = Reader(pipeline)
    assert w._read_source(region, result, lambda text, error: got.append((text, error)))
    assert got == [(region.source_text, "")] and region.source_text
    pipeline.ocr = None  # the reading model is not loaded yet
    assert not w._read_source(result.translated[1], result, lambda *_a: got.append("asked"))
    assert got[-1] != "asked"


def _region(source="今日はいい天気だね"):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = "translated", "Nice weather today, huh?", source
    return r


def test_the_editor_shows_the_region_and_reads_its_japanese_on_demand(hidden_root):
    region = _region(source="")
    asked_to_read, asked = [], []
    crop = Image.new("RGB", (60, 150), "white")
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                on_ask=lambda mode, answer: (asked.append(mode), True)[1], crop=crop,
                                on_read=lambda done: (asked_to_read.append(done), True)[1])
    assert d.crop_label is not None and (d._crop_photo.width(), d._crop_photo.height()) == (80, 200)  # enlarged
    assert d.read_btn.winfo_manager() == "pack" and not d.source_label.winfo_manager()
    (ask_again,) = d.ask_btns  # there, though nothing was read yet: it reads first
    ask_again.invoke()
    assert len(asked_to_read) == 1 and not asked and d.busy_var.get() == "Reading the Japanese..."
    assert all(str(b.cget("state")) == "disabled" for b in (d.save_btn, ask_again, d.read_btn))
    asked_to_read[0]("今日はいい天気だね", "")  # the window hands the reading over: the question goes on
    assert region.source_text == "今日はいい天気だね" and d.source_var.get() == "Read as: 今日はいい天気だね"
    assert d.source_label.winfo_manager() == "pack" and not d.read_btn.winfo_manager() and asked == ["again"]
    d.destroy()

    region = _region(source="")
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                on_read=lambda done: (asked_to_read.append(done), True)[1])
    assert not d.ask_btns and d.crop_label is None  # no translator: no Ask again; no frame: no picture
    d.read()
    asked_to_read[-1]("", "none")
    assert d.busy_var.get() == "No Japanese was read in this region." and d.read_btn.winfo_manager() == "pack"
    assert str(d.read_btn.cget("state")) == "normal"
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, _region(source=""), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_read=lambda done: False)
    d.read()
    assert d.busy_var.get() == "The reading model is not loaded yet. Try again in a moment."
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.source_var.get() == "Read as: 今日はいい天気だね" and not d.read_btn.winfo_manager()  # read on this page
    d.destroy()


def test_the_editors_picture_is_a_crop_of_the_frame_in_memory():
    page = Image.new("RGB", (200, 100), "white")
    crop = editor_crop(page, (10, 20, 50, 60))
    assert crop.size == (52, 52) and crop is not page
    assert editor_crop(page, (190, 90, 260, 140)).size == (16, 16)  # clamped to the page
    assert editor_crop(None, (0, 0, 10, 10)) is None and editor_crop(page, (300, 300, 310, 310)) is None
    assert review.fitted_crop(Image.new("RGB", (2000, 100))).size == (460, 23)


# ------------------------------------------------------------------ Previous and Next, and closing with changes
def test_previous_and_next_hand_on_what_changed_and_stop_at_the_ends(hidden_root):
    stepped = []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_step=lambda delta, data, at: stepped.append((delta, data)), place=(1, 3))
    assert str(d.step_btns[-1].cget("state")) == "disabled" and str(d.step_btns[1].cget("state")) == "normal"
    d.step(-1)
    assert not stepped and d.winfo_exists()  # nothing before the first region
    d.step(1)
    assert stepped == [(1, None)] and d._closed  # nothing changed: nothing to save
    cancelled = []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_step=lambda delta, data, at: stepped.append((delta, data)), place=(3, 3),
                                on_cancel=lambda: cancelled.append(True))
    assert str(d.step_btns[1].cget("state")) == "disabled"
    d.text.delete("1.0", "end")
    d.text.insert("1.0", "What a day.")
    d._step_key(SimpleNamespace(widget=d.text), -1)  # Alt+Up in the translation
    assert stepped[-1][0] == -1 and stepped[-1][1]["text"] == "What a day." and not cancelled  # the window ends it
    assert d._step_key(SimpleNamespace(widget=d.kind_box), -1) is None  # a list's own Alt+Down stays its own


def test_esc_asks_before_changes_are_dropped(hidden_root, monkeypatch):
    answers, questions, cancelled = [False], [], []
    monkeypatch.setattr(caches, "ask", lambda parent, text, *a, **k: (questions.append((text, k)), answers[0])[1])
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_cancel=lambda: cancelled.append(True))
    d.close_asked()  # nothing changed: closed at once
    assert not questions and cancelled == [True] and d._closed
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_cancel=lambda: cancelled.append(True))
    d.speaker_var.set("Piyo")
    d.close_asked()
    assert questions[-1] == ("Discard your changes to this region?", {"no_first": True}) and d.winfo_exists()
    assert not d._closed and len(cancelled) == 1  # "Keep editing": the editor stays as it is
    answers[0] = True
    d.close_asked()
    assert d._closed and len(cancelled) == 2
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    d.set_style(RegionStyle(bold=True))  # the formatting counts too
    assert d.changed()
    d.destroy()


class Editing:
    """The window's side of Previous and Next on the real pipeline: Save's job runs at once, the editor is recorded."""

    _record = app_mod.App._record
    _edit_region = app_mod.App._edit_region
    _end_preview = app_mod.App._end_preview
    _step_editor = app_mod.App._step_editor

    def __init__(self, pipeline, result):
        self.pipeline, self.last_result = pipeline, result
        self.history = EditHistory()
        self.busy = False
        self.opened, self.chosen, self.said = [], [], []
        self._jobs = Jobs()

    def _open_editor(self, region, result=None, at=None):
        self.opened.append((region, result, at))

    def _choose(self, region):
        self.chosen.append(region)

    def _post(self, kind, **data):
        if kind == "translate_done":
            self.busy = False

    def _go_busy(self):
        self.busy = True

    def say(self, key, **values):
        self.said.append(key)

    def _redisplay(self):
        pass


def test_next_saves_what_changed_as_one_change_and_opens_the_region_after_it(cached):
    pipeline, result = cached
    w = Editing(pipeline, result)
    shown = editor_regions(result)
    first, second = shown[0], shown[1]
    w._step_editor(first, result, None, 1, None, (40, 50))
    assert w.opened[-1] == (second, result, (40, 50)) and w.chosen[-1] is second and not w.history.done
    data = {"text": "Changed.", "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": ""}
    w._step_editor(second, result, None, -1, data, (40, 50))
    assert second.translated_text == "Changed." and w.history.done[-1].kind == "edit"
    assert w.opened[-1][0] is first
    w._step_editor(first, result, None, -1, None, (0, 0))  # before the first: nowhere to go
    assert w.opened[-1][0] is first and len(w.opened) == 2


def test_a_preview_ended_after_the_page_was_lettered_anew_leaves_the_new_page(cached):
    """Next saved the region before (its page lettered anew in the worker), and the next editor's preview ends: the
    page the save lettered stays; a preview of its own on the page goes again."""
    pipeline, result = cached
    region = result.translated[0]
    preview = LivePreview(result, region)
    stale = preview.before
    result.image = Image.new("RGB", result.image.size, "white")  # what the save lettered meanwhile
    lettered = result.image
    w = SimpleNamespace(last_result=result, _redisplay=lambda: None)
    app_mod.App._end_preview(w, preview)
    assert result.image is lettered and result.image is not stale
    preview = LivePreview(result, region)
    preview.mine = result.image = Image.new("RGB", result.image.size, "black")  # its own picture on the page
    app_mod.App._end_preview(w, preview)
    assert result.image is lettered


def test_every_new_line_of_the_editor_is_in_every_language():
    keys = [*review.NOT_READ.values(), review.READING, review.DISCARD, *review.STEP_WORDS.values(),
            *review.STEP_TIPS.values()]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
    assert translator.EDITOR_CROP_PAD > 0
