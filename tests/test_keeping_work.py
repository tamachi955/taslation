"""What the reader and the model made is not lost: a typed translation or one a gate turns down through a run, a temporary
name's sheet, "Translate again" that comes to nothing, a save that fails, a replacement and its undo, the reader's
order on a cached page."""
from __future__ import annotations

import errno
import json
import threading
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book, store_json
from test_batch import _fake_viewer

from taslation import cache as cachemod
from taslation.annotations import AnnotationStore
from taslation.batch import BatchReader, fatal
from taslation.cache import CachedBubble, CachedPage, CacheStore, TextEdit
from taslation.config import Settings
from taslation.messages import Message
from taslation.notes import is_temporary_name, series_key
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator, OllamaTranslator
from taslation.translate.base import worth_asking_again
from taslation.ui import app as app_mod
from taslation.ui import jobs, translator as translator_mod
from taslation.ui.history import EditHistory
from taslation.ui.dialogs import caches

TYPED = "Typed by the reader."


class BlindOcr(FakeOcr):
    """Reads nothing in crops of *blind* size (a rectangle over lettering the OCR cannot read)."""

    blind: tuple[int, int] | None = None

    def read(self, image):
        if self.blind is not None and image.size == self.blind:
            return ""
        return super().read(image)


def manual_page(settings, sample_page):
    """A page with a rectangle of the reader's the OCR reads nothing in, and a translation typed in it."""
    cache = CacheStore(settings.cache_dir).open("Manual", "m")
    annotations = AnnotationStore(settings.annotations_dir).open("Manual")
    ocr = BlindOcr()
    p = Pipeline(settings, ocr=ocr, translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache, annotations=annotations)
    first = p.process(sample_page)
    box = (30, 30, 110, 70)
    ocr.blind = (box[2] - box[0], box[3] - box[1])
    assert p.add_region(first, box)
    again = p.process(sample_page, complete=True)
    region = next(r for r in again.regions if r.kind.startswith("manual"))
    assert region.status == "ocr-empty" and p.set_translation(again, region, TYPED)
    return p, cache


def on_disk(cache) -> list[str]:
    return [b["text"] for page in store_json(cache.path)["pages"] for b in page["bubbles"]]


# ------------------------------------------------------------------ a run keeps what is stored
def test_a_run_keeps_a_typed_translation_of_a_manual_region_the_ocr_cannot_read(settings, sample_page):
    p, cache = manual_page(settings, sample_page)
    unit = p.scan(sample_page, skip_cached=True).units[0]
    assert unit.dropped == 0 and TYPED in [b.text for b in unit.kept]
    assert TYPED in on_disk(cache)
    assert any(r.translated_text == TYPED for r in p.process(sample_page).regions)


def test_a_run_that_translates_again_keeps_it_too(settings, sample_page):
    p, cache = manual_page(settings, sample_page)
    scan = p.scan(sample_page, skip_cached=True, fresh=True)
    assert TYPED in [b.text for b in scan.units[0].kept]
    p.commit_unit(scan.units[0], {})
    assert TYPED in on_disk(cache)


def test_a_gate_on_a_second_pass_drops_no_stored_translation(settings, sample_page, monkeypatch):
    cache = CacheStore(settings.cache_dir).open("Gate", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    p.process(sample_page)
    stored = sorted(b.text for b in cache.pages[0].bubbles)
    monkeypatch.setattr(Pipeline, "_verdict", lambda *_a: "ocr-noise")  # the book's sizes moved: the gate says no
    unit = p.scan(sample_page, skip_cached=True).units[0]
    assert unit.dropped == 0 and unit.cached and sorted(on_disk(cache)) == stored


def test_a_bubble_no_region_corresponds_to_is_still_stale(settings, sample_page):
    cache = CacheStore(settings.cache_dir).open("Stale", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    p.process(sample_page)
    page = cache.pages[0]
    stale = CachedBubble(box=(0.94, 0.94, 0.99, 0.99), text="From an old run.")
    p._save_page(page.fingerprint, page.aspect, [*page.bubbles, stale])
    unit = p.scan(sample_page, skip_cached=True).units[0]
    assert unit.dropped == 1 and "From an old run." not in on_disk(cache)


# ------------------------------------------------------------------ temporary names
def test_two_temporary_names_have_two_series(tmp_path):
    from taslation.rename import Stores, rename_book

    a, b = "Untitled book 2026-11-01 1430", "無題の本 2026-11-02 0915"
    assert is_temporary_name(a) and is_temporary_name(b)
    assert series_key(a) == a and series_key(b) == b and series_key(a) != series_key(b)
    for name in ("Some Title 3", "Title 2026", "Title 2026-11-01", "Title 2026-13-01 1430", "Title 2026-11-01 2561"):
        assert not is_temporary_name(name)
    assert series_key("Some Title 3") == "Some Title"
    state = Settings(state_dir=tmp_path / "state")
    state.validate()
    stores = Stores.of(state)
    for book in (a, b):
        cache = stores.cache.open(book, "m", "English")
        cache.add(CachedPage(book[-1] * 80, 0.7, [CachedBubble((0, 0, .1, .1), "A line.")], seq=-1))
        cache.save()
    sheet = stores.sheets.open(series_key(b), "English")
    sheet.set("剣", "Blade of book B")
    sheet.save()
    assert stores.sheets.open(series_key(a), "English").is_empty  # the other book's sheet is not this one's
    rename_book(stores, a, "Real Title 3", "English")  # Use on the colophon of book A
    assert "Blade of book B" in stores.sheets.open(series_key(b), "English").format()


def test_a_temporary_name_is_no_viewers_last_name(monkeypatch, tmp_path):
    kept: list[str] = []
    monkeypatch.setattr("taslation.bookid.remember_name", lambda _dir, _title, name: kept.append(name))
    w = SimpleNamespace(selected=SimpleNamespace(title="A browser"), settings=SimpleNamespace(state_dir=tmp_path))
    jobs.JobsMixin._remember_viewer_name(w, "Untitled book 2026-11-01 1430")
    jobs.JobsMixin._remember_viewer_name(w, "Some Title 3")
    assert kept == ["Some Title 3"]


# ------------------------------------------------------------------ "Translate again"
class Again(translator_mod.TranslatorMixin):
    """What `retranslate_page` and `_job_translate` need of the window; the job runs at once."""

    _job_translate = jobs.JobsMixin._job_translate
    _say_failed_save = jobs.JobsMixin._say_failed_save
    _use_model = jobs.JobsMixin._use_model

    def __init__(self, pipeline, result, cancel=None):
        self.pipeline, self.last_result, self.cancel = pipeline, result, cancel
        self.translator = SimpleNamespace(model="m")
        self.settings = Settings()
        self.busy = False
        self.posted: list[tuple[str, dict]] = []
        self.history = EditHistory()
        self._jobs = SimpleNamespace(put=lambda job: job())  # the worker, at once

    def _result_on_show(self):
        return True

    def _post(self, kind, **data):
        self.posted.append((kind, data))

    def _ensure_cache(self, *_a):
        return True

    def _look_for_colophon(self, *_a):
        pass

    def _start_translate(self, image, complete=None, thumb=None, again=None):
        self._job_translate(image, "Book", "m", "English", complete, self.cancel, again)

    def kinds(self):
        return [kind for kind, _data in self.posted]


@pytest.fixture
def asked(monkeypatch):
    questions: list[str] = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *_a, **_k: questions.append(text) or True)
    return questions


def translated_page(settings, sample_page, translator=None):
    cache = CacheStore(settings.cache_dir).open("Again", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=translator or DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    result = p.process(sample_page)
    p.set_translation(result, result.regions[0], TYPED)
    return p, cache, result


def test_translate_again_cancelled_keeps_the_translations(settings, sample_page, asked):
    p, cache, result = translated_page(settings, sample_page)
    before = sorted(on_disk(cache))
    cancel = threading.Event()
    cancel.set()
    w = Again(p, result, cancel)
    w.retranslate_page()
    assert asked and "page_cancelled" in w.kinds() and w.kinds()[-1] == "translate_done"
    assert sorted(on_disk(cache)) == before and TYPED in before
    assert sorted(b.text for b in CacheStore(settings.cache_dir).open("Again", "m").pages[0].bubbles) == before


def test_translate_again_with_the_model_gone_keeps_them_and_shows_them(settings, sample_page, asked):
    from taslation.translate import TranslationError

    p, cache, result = translated_page(settings, sample_page)
    before = sorted(on_disk(cache))

    class Down(DictTranslator):
        def translate_page(self, *_a, **_k):
            raise TranslationError(Message("ollama.unreachable", url="http://127.0.0.1:11434"))

    p.translator = Down({})
    w = Again(p, result)
    w.retranslate_page()
    assert sorted(on_disk(cache)) == before
    shown = dict(w.posted)["result"]["result"]
    assert TYPED in [r.translated_text for r in shown.regions] and shown.error


def test_translate_again_that_fails_keeps_them(settings, sample_page, asked):
    p, cache, result = translated_page(settings, sample_page)
    before = sorted(on_disk(cache))
    p.process = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("the job broke"))
    with pytest.raises(RuntimeError):
        Again(p, result).retranslate_page()
    assert sorted(on_disk(cache)) == before


def test_translate_again_replaces_them_once_something_is_translated(settings, sample_page, asked):
    p, cache, result = translated_page(settings, sample_page)
    w = Again(p, result)
    w.retranslate_page()
    assert TYPED not in on_disk(cache) and len(cache) == 1 and on_disk(cache)


def test_a_job_begun_or_a_page_turned_while_the_question_was_up_stops_it(settings, sample_page, monkeypatch):
    p, cache, result = translated_page(settings, sample_page)
    before = sorted(on_disk(cache))
    w = Again(p, result)
    for change in (lambda: setattr(w, "busy", True), lambda: setattr(w, "last_result", object())):
        monkeypatch.setattr(caches, "ask", lambda *_a, change=change, **_k: change() or True)
        w.busy, w.last_result = False, result
        w.retranslate_page()
        assert w.posted == [] and sorted(on_disk(cache)) == before


# ------------------------------------------------------------------ a save that fails
def full_disk(*_a, **_k):
    raise OSError(errno.ENOSPC, "No space left on device")


def test_a_failed_save_is_said(settings, sample_page, sample_page2, monkeypatch):
    cache = CacheStore(settings.cache_dir).open("Full", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    assert p.save_error == ""
    real = cachemod.write_atomic
    monkeypatch.setattr(cachemod, "write_atomic", full_disk)
    # the window: the status line, after the page
    w = Again(p, None)
    w._job_translate(sample_page, "Full", "m", "English")
    assert p.save_error == "No space left on device" and p.pages_not_saved and cache.dirty
    said = [data for kind, data in w.posted if kind == "status"]
    assert len(said) == 1 and said[0]["values"] == {"error": "No space left on device"}
    assert w.kinds()[-3:] == ["result", "status", "translate_done"]
    # closing the window: one more try, and a warning when it fails too
    warned: list[str] = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: warned.append(text))
    app_mod.last_save(p, object())
    assert len(warned) == 1 and "No space left on device" in warned[0]
    # a save that works writes what waited, and all is well again
    monkeypatch.setattr(cachemod, "write_atomic", real)
    app_mod.last_save(p)
    assert len(warned) == 1 and not cache.dirty and on_disk(cache)
    p._save_page(cache.pages[0].fingerprint, cache.pages[0].aspect, cache.pages[0].bubbles)
    assert p.save_error == ""
    w.posted.clear()
    w._job_translate(sample_page, "Full", "m", "English")
    assert "status" not in w.kinds()


@pytest.mark.parametrize("context_mode", [False, True])
def test_a_run_on_a_full_disk_ends_and_says_why(context_mode, settings, sample_page, sample_page2, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Full run", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    monkeypatch.setattr(cachemod, "write_atomic", full_disk)
    progress = read_book(BatchReader(p, hwnd=1, settings=settings, context_mode=context_mode))
    assert progress.reason == Message("batch.save_failed", error="No space left on device")
    assert progress.pages == (3 if context_mode else 0)  # not one page more; a whole-book run stores after the last
    assert progress.summary.code == "batch.finished" and "cannot be saved" in str(progress.summary)


def test_stop_does_not_hide_a_failed_save(settings, sample_page, sample_page2, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    cache = CacheStore(settings.cache_dir).open("Full stop", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    reader = BatchReader(p, hwnd=1, settings=settings, context_mode=False)
    monkeypatch.setattr(cachemod, "write_atomic", full_disk)
    real = p.process

    def process(*a, **k):
        out = real(*a, **k)
        reader.stop()
        return out

    p.process = process
    assert "cannot be saved" in str(read_book(reader).summary)


def test_annotations_that_cannot_be_saved_are_said_too(settings, sample_page, monkeypatch):
    annotations = AnnotationStore(settings.annotations_dir).open("Locked")
    p = Pipeline(settings, ocr=FakeOcr(), translator=None, annotations=annotations)
    monkeypatch.setattr(annotations, "save", lambda: full_disk())
    p.save_annotations()
    assert p.save_error and not p.pages_not_saved


# ------------------------------------------------------------------ a replacement and its undo
def test_the_undo_gives_a_replacement_its_text_back(settings):
    cache = CacheStore(settings.cache_dir).open("Undo", "m")
    bubble = CachedBubble(box=(0.1, 0.1, 0.3, 0.3), text="Old.", flags=["long"])
    cache.add(CachedPage("a" * 80, 0.7, [bubble], seq=-1))
    made = cache.put_texts([TextEdit("a" * 80, bubble.box, "Old.", "New.")])
    assert bubble.text == "New." and bubble.flags == ["long"]
    cache.put_texts([e.undone() for e in made])
    assert bubble.text == "Old."
    cache.put_texts(made)  # made again
    assert bubble.text == "New."


# ------------------------------------------------------------------ the reader's order
def test_a_cached_page_keeps_the_readers_order(settings, sample_page):
    cache = CacheStore(settings.cache_dir).open("Order", "m")
    annotations = AnnotationStore(settings.annotations_dir).open("Order")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache, annotations=annotations)
    first = p.process(sample_page)
    wanted = list(reversed(first.regions))
    assert p.set_reading_order(first, wanted)
    again = p.process(sample_page)
    assert again.cache_hits and [r.bbox for r in again.regions] == [r.bbox for r in wanted]


# ------------------------------------------------------------------ a model that is not installed
MISSING = b'{"error":"model \'x\' not found"}'


def test_a_model_of_the_readers_gets_the_pull_command(settings):
    tr = OllamaTranslator(model="some-other:1b")
    error = tr._http_failure(404, MISSING, "/api/chat").message
    assert error.code == "health.chosen_model_missing" and "ollama pull some-other:1b" in str(error)
    assert "install.cmd" not in str(error)
    assert fatal(error) and not worth_asking_again(error)  # as for the default model: the next request fails the same


def test_the_default_model_goes_to_install_cmd(settings):
    error = OllamaTranslator(model="qwen3.5:4b")._http_failure(404, MISSING, "/api/chat").message
    assert error.code == "ollama.model_missing" and "install.cmd" in str(error) and fatal(error)


def test_batch_save_failed_reads_in_every_language():
    from taslation.message_texts import LANGUAGES, catalog
    from taslation.messages import render

    for lang in LANGUAGES:
        text = render(Message("batch.save_failed", error="E!"), catalog(lang))
        assert "E!" in text and "{" not in text, lang
