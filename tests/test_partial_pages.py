"""What was translated is always kept: a page unit with one real translation or more enters the cache, marked
(`CachedPage.incomplete`) while a bubble lacks one, and the next reading or whole-book run asks for that alone."""
from __future__ import annotations

import json
import threading
from collections import deque

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, JA_TEXTS, read_book, store_json, store_text
from test_batch import _fake_viewer

from taslation import fingerprint as fp
from taslation.batch import BatchReader
from taslation.cache import BookCache, CacheStore, CachedBubble, CachedPage
from taslation.messages import Message
from taslation.pipeline import Cancelled, Pipeline, ScannedRegion, ScannedUnit
from taslation.translate import DictTranslator, TranslationError

FP = "a" * 80


def _unit(texts: list[str] = ("一", "二", "三")) -> ScannedUnit:  # type: ignore[assignment]
    regions = [ScannedRegion((10 + 30 * i, 10, 30 + 30 * i, 40), (10 + 30 * i, 10, 30 + 30 * i, 40),
                             [(0.0, 0.0), (20.0, 0.0), (20.0, 30.0)], text, "untranslated")
               for i, text in enumerate(texts)]
    return ScannedUnit(0, (0, 0, 200, 300), FP, 0.67, regions)


def _pipeline(settings, translator=None, name: str = "Partial", ocr=None) -> Pipeline:
    cache = CacheStore(settings.cache_dir).open(name, "fake")
    return Pipeline(settings, ocr=ocr or FakeOcr(), translator=translator, cache=cache)


class Unreliable(DictTranslator):
    """Leaves *never* unanswered while it is in the set, and can fail altogether."""

    def __init__(self, mapping, never=(), fail=False):
        super().__init__(mapping)
        self.never, self.fail = set(never), fail

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                       on_slow=None):
        if self.fail:
            self.calls.append(list(texts))
            raise TranslationError(Message("ollama.timeout", seconds=900.0))
        out = super().translate_page(texts, context, notes, upcoming, meta, on_item, cancel, on_slow)
        return ["" if t in self.never else o for t, o in zip(texts, out)]


# --- commit_unit --------------------------------------------------------------------------------------------------

def test_a_brand_new_unit_with_two_of_three_translations_is_stored_and_not_complete(settings):
    pipeline = _pipeline(settings)
    unit = _unit()
    assert pipeline.commit_unit(unit, {0: "One.", 2: "Three."}) is False
    assert [b.text for b in pipeline.cache.pages[0].bubbles] == ["One.", "Three."]
    assert pipeline.cache.pages[0].incomplete
    assert store_json(pipeline.cache.path)["pages"][0]["incomplete"] is True


def test_a_unit_with_nothing_real_enters_no_cache_and_the_copied_japanese_never_does(settings):
    pipeline = _pipeline(settings)
    assert pipeline.commit_unit(_unit(), {0: "一", 1: "", 2: "  "}) is False
    assert len(pipeline.cache) == 0 and not pipeline.cache.path.exists()
    assert pipeline.commit_unit(_unit(), {0: "一", 1: "Two."}) is False
    raw = store_text(pipeline.cache.path)
    assert "一" not in raw and [b.text for b in pipeline.cache.pages[0].bubbles] == ["Two."]


def test_a_complete_unit_clears_the_mark(settings):
    pipeline = _pipeline(settings)
    pipeline.commit_unit(_unit(), {0: "One."})
    assert pipeline.commit_unit(_unit(), {0: "One.", 1: "Two.", 2: "Three."}) is True
    assert len(pipeline.cache) == 1 and not pipeline.cache.pages[0].incomplete
    assert "incomplete" not in store_json(pipeline.cache.path)["pages"][0]


# --- the cache file -------------------------------------------------------------------------------------------------

def _page(fingerprint: str = FP, incomplete: bool = False, text: str = "Hello") -> CachedPage:
    return CachedPage(fingerprint, 0.7, [CachedBubble((0.1, 0.1, 0.2, 0.2), text)], incomplete=incomplete)


def test_cache_files_of_before_load_and_only_a_marked_page_writes_the_mark(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"schema": 1, "book": "b", "pages": [
        {"fp": "a" * 80, "aspect": 0.7, "seq": 0, "bubbles": [{"box": [0, 0, 1, 1], "text": "Hi"}]},
        {"fp": "b" * 80, "aspect": 0.7, "seq": 1, "bubbles": [], "incomplete": True},
        {"fp": "c" * 80, "aspect": 0.7, "seq": 2, "bubbles": [], "incomplete": "yes"},  # only true is true
    ]}), encoding="utf-8")
    cache = BookCache.load(path)
    assert [p.incomplete for p in cache.pages] == [False, True, False]
    pages = cache.to_json()["pages"]
    assert ["incomplete" in p for p in pages] == [False, True, False]


def test_a_marked_page_survives_a_merging_save_and_a_save_that_completes_it_clears_it(tmp_path):
    store = CacheStore(tmp_path)
    first = store.open("b", "m")
    first.add(_page(incomplete=True))
    first.save()
    other = store.open("b", "m")
    other.add(_page("b" * 80))
    other.save()
    first.add(_page("c" * 80))
    first.save()  # merges what the other process saved: the mark stays
    assert {p.fingerprint[0]: p.incomplete for p in store.open("b", "m").pages} == {"a": True, "b": False, "c": False}
    other.refresh()
    other.add(_page(text="Done."))  # the same page, complete now
    other.save()
    first.add(_page("d" * 80))
    first.save()
    assert {p.fingerprint[0]: p.incomplete for p in store.open("b", "m").pages}["a"] is False


def test_a_rename_keeps_the_mark(tmp_path):
    cache = CacheStore(tmp_path).open("b", "m")
    cache.add(_page(incomplete=True))
    assert cache.rename([("Hello", "Hi")]) == 1
    cache.save()
    assert CacheStore(tmp_path).open("b", "m").pages[0].incomplete


def test_export_and_import_carry_the_mark(tmp_path):
    pytest.importorskip("cryptography")
    from taslation import backup

    store = CacheStore(tmp_path / "a")
    cache = store.open("b", "m")
    cache.add(_page(incomplete=True))
    cache.save()
    path = tmp_path / "export.bin"
    backup.export_cache(store, "b", path, "a long enough passphrase")
    for replace in (False, True):
        other = CacheStore(tmp_path / f"to-{replace}")
        backup.import_cache(other, path, "a long enough passphrase", replace=replace)
        assert other.open("b", "m").pages[0].incomplete


def test_keying_a_page_of_before_anew_keeps_the_mark(sample_page, settings):
    pipeline = _pipeline(settings, DictTranslator(EN_TEXTS))
    cache = pipeline.cache
    rgb = np.asarray(sample_page.convert("RGB"))
    unit = fp.analyze(rgb)[0]
    old_box = (unit.box[0], unit.box[1], unit.box[2], (unit.box[1] + unit.box[3]) // 2)
    old = fp.PageUnit(old_box, "f" * 80, 0)
    cache.add(CachedPage(old.fingerprint, old.aspect, [CachedBubble((0.1, 0.1, 0.2, 0.2), "Kept.")], seq=3,
                         incomplete=True))
    hit = pipeline._lookup_before(unit, [old])
    assert hit is not None and hit[0].incomplete and len(cache) == 1 and cache.pages[0].incomplete


# --- reading a page --------------------------------------------------------------------------------------------------

def test_reading_a_marked_page_translates_what_is_missing_once_and_clears_the_mark(sample_page, settings):
    never = JA_TEXTS[0]
    tr = Unreliable(EN_TEXTS, never=[never])
    pipeline = _pipeline(settings, tr)
    first = pipeline.process(sample_page)
    assert not first.error and len(first.translated) == 5 and pipeline.cache.pages[0].incomplete
    assert [r.status for r in first.regions if r.source_text == never] == ["untranslated"]
    asked = len(tr.calls)
    tr.never.clear()
    second = pipeline.process(sample_page)
    assert second.cache_hits == 1 and tr.calls[asked:] == [[never]]  # only the line that was missing, once
    assert len(second.translated) == 6 and not second.error
    assert [r.from_cache for r in second.translated].count(False) == 1  # a run counts it
    page = pipeline.cache.pages[0]
    assert not page.incomplete and len(page.bubbles) == 6
    assert not any(b.text == never for b in page.bubbles)
    calls = len(tr.calls)
    third = pipeline.process(sample_page)  # complete now: as any page from the cache
    assert len(tr.calls) == calls and third.cache_hits == 1 and len(third.translated) == 6
    assert all(r.from_cache for r in third.translated)


def test_a_window_is_told_of_the_missing_line_alone(sample_page, settings):
    never = JA_TEXTS[0]
    tr = Unreliable(EN_TEXTS, never=[never])
    pipeline = _pipeline(settings, tr)
    pipeline.process(sample_page)
    tr.never.clear()
    events: list[tuple[str, dict]] = []
    pipeline.process(sample_page, events=lambda kind, data: events.append((kind, data)))
    assert [len(data["boxes"]) for kind, data in events if kind == "regions"] == [1]
    assert [data["text"] for kind, data in events if kind == "translated"] == [EN_TEXTS[never]]
    assert [kind for kind, _data in events][-1] == "page"


def test_a_failing_model_leaves_a_marked_page_as_it_is_and_asks_no_more_than_for_a_page(sample_page, settings):
    never = JA_TEXTS[0]
    tr = Unreliable(EN_TEXTS, never=[never])
    pipeline = _pipeline(settings, tr)
    pipeline.process(sample_page)
    stored = [b.text for b in pipeline.cache.pages[0].bubbles]
    asked = len(tr.calls)
    again = pipeline.process(sample_page)  # no answer again: the line alone, and the one time it is asked again
    assert tr.calls[asked:] == [[never], [never]] and not again.error
    assert [r.status for r in again.regions if r.source_text == never] == ["untranslated"]
    assert pipeline.cache.pages[0].incomplete and [b.text for b in pipeline.cache.pages[0].bubbles] == stored
    asked = len(tr.calls)
    tr.fail = True
    failed = pipeline.process(sample_page)
    assert "too long" in failed.error and len(failed.translated) == 5
    assert tr.calls[asked:] == [[never]]  # a timeout is not asked again
    assert pipeline.cache.pages[0].incomplete and [b.text for b in pipeline.cache.pages[0].bubbles] == stored


def test_a_marked_page_is_shown_without_a_model_and_without_a_request(sample_page, settings):
    pipeline = _pipeline(settings, Unreliable(EN_TEXTS, never=[JA_TEXTS[0]]))
    pipeline.process(sample_page)
    ocr_calls = pipeline.ocr.calls
    pipeline.translator = None
    shown = pipeline.process(sample_page)
    assert not shown.error and len(shown.translated) == 5 and pipeline.ocr.calls == ocr_calls
    assert pipeline.cache.pages[0].incomplete
    pipeline.translator = DictTranslator(EN_TEXTS)
    assert len(pipeline.process(sample_page, translate=False).translated) == 5
    assert pipeline.translator.calls == []


def test_a_marked_page_with_nothing_left_to_translate_loses_the_mark(sample_page, settings):
    tr = DictTranslator(EN_TEXTS)
    pipeline = _pipeline(settings, tr)
    pipeline.process(sample_page)
    page = pipeline.cache.pages[0]
    page.incomplete = True
    calls = len(tr.calls)
    assert len(pipeline.process(sample_page).translated) == 6
    assert len(tr.calls) == calls and not pipeline.cache.pages[0].incomplete


def test_what_came_back_before_a_failure_is_stored(sample_page, settings):
    """The request failed, the line-by-line asking got some of the lines: those are kept, with the error."""

    class WholeFails(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                           on_slow=None):
            if len(texts) > 1:
                self.calls.append(list(texts))
                raise TranslationError("the model's reply broke off")
            if texts[0] == JA_TEXTS[0]:
                raise TranslationError("the model's reply broke off")
            return super().translate_page(texts, context, notes, upcoming, meta, on_item, cancel, on_slow)

    pipeline = _pipeline(settings, WholeFails(EN_TEXTS))
    result = pipeline.process(sample_page)
    assert result.error and len(result.translated) == 5
    assert len(pipeline.cache) == 1 and pipeline.cache.bubble_count == 5 and pipeline.cache.pages[0].incomplete


def test_a_page_cancelled_before_its_translation_came_back_leaves_nothing(sample_page, settings):
    cancel = threading.Event()

    class Stopped(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None,
                           on_slow=None):
            cancel.set()
            return super().translate_page(texts, context, notes, upcoming, meta, on_item, cancel, on_slow)

    pipeline = _pipeline(settings, Stopped(EN_TEXTS))
    with pytest.raises(Cancelled):
        pipeline.process(sample_page, cancel=cancel)
    assert len(pipeline.cache) == 0 and not pipeline.cache.path.exists()


def test_an_edit_on_a_marked_page_keeps_the_mark_until_the_line_is_there(sample_page, settings):
    never = JA_TEXTS[0]
    tr = Unreliable(EN_TEXTS, never=[never])
    pipeline = _pipeline(settings, tr)
    result = pipeline.process(sample_page)
    assert pipeline.set_translation(result, result.translated[0], "Edited.")
    assert pipeline.set_reader_note(result, result.translated[0], "A note.")
    assert pipeline.cache.pages[0].incomplete
    missing = next(r for r in result.regions if r.source_text == never)
    assert pipeline.set_translation(result, missing, "By hand.")
    calls = len(tr.calls)
    assert len(pipeline.process(sample_page).translated) == 6
    assert len(tr.calls) == calls and not pipeline.cache.pages[0].incomplete


# --- a whole-book run ----------------------------------------------------------------------------------------------

def _run(settings, translator, cache):
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=translator, cache=cache)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True)
    return read_book(reader), pipeline


def test_a_line_the_model_never_answers_leaves_the_rest_stored_and_the_page_lettered(sample_page, sample_page2, settings,
                                                                                     monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    never = JA_TEXTS[0]
    tr = Unreliable(EN_TEXTS, never=[never])
    cache = CacheStore(settings.cache_dir).open("Never", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache)
    shown: list[tuple[str, dict]] = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True,
                         show=lambda kind, data: shown.append((kind, data)))
    progress = read_book(reader)
    assert progress.finished and len(cache) == 3 and cache.bubble_count == 15
    assert all(page.incomplete for page in cache.pages)
    assert progress.translated == 15 and progress.checked == 15
    codes = [n.code for n in progress.notes]
    assert codes.count("batch.note_unit_incomplete") == 3
    # the page as the window gets it: the page's translations lettered, the line left as drawn
    viewer.index = 0
    shown = pipeline.process(sample_page, translate=False)
    assert len(shown.translated) == 5 and not np.array_equal(np.asarray(shown.image), np.asarray(sample_page))
    assert sum(1 for r in shown.regions if r.status != "translated") == 1
    # the next run is asked for that line alone
    viewer.index = 0
    tr2 = DictTranslator(EN_TEXTS)
    again, _pipeline_ = _run(settings, tr2, cache)
    assert all(set(call) == {never} for call in tr2.calls)
    assert again.translated == 3
    assert cache.bubble_count == 18 and not any(page.incomplete for page in cache.pages)


def test_a_partly_stored_page_is_counted_once_and_completed_by_the_next_commit(settings):
    pipeline = _pipeline(settings, Unreliable({"一": "One.", "二": "Two.", "三": "Three."}, never=["三"]))
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True)
    unit = _unit()
    reader._translate_units([unit], deque(maxlen=5), "", [], "English")
    p = reader.progress
    assert (p.translated, p.bubbles, p.checked) == (2, 2, 2) and pipeline.cache.pages[0].incomplete
    assert [n.code for n in p.notes] == ["batch.note_incomplete", "batch.note_unit_incomplete"]
    assert "translated when its page is read" in str(p.notes[-1])
    # the next run has the two kept, the third to do
    hit = pipeline.cache.pages[0]
    rest = _unit()
    rest.kept, rest.regions, rest.stored_fingerprint = list(hit.bubbles), rest.regions[2:], hit.fingerprint
    pipeline.translator.never.clear()
    reader._translate_units([rest], deque(maxlen=5), "", [], "English")
    assert (p.translated, p.bubbles, p.checked) == (3, 3, 3)
    assert pipeline.cache.bubble_count == 3 and not pipeline.cache.pages[0].incomplete


def test_a_kept_page_a_request_failed_for_is_marked_so_reading_translates_the_rest(settings):
    pipeline = _pipeline(settings, Unreliable({}, fail=True))
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True)
    unit = _unit()
    unit.kept, unit.regions = [CachedBubble((0.1, 0.1, 0.2, 0.2), "Kept.")], unit.regions[1:]
    reader._translate_units([unit], deque(maxlen=5), "", [], "English")
    assert [n.code for n in reader.progress.notes][-1] == "batch.note_unit_failed"
    page = pipeline.cache.pages[0]
    assert [b.text for b in page.bubbles] == ["Kept."] and page.incomplete


def test_a_marked_page_that_a_scan_finds_whole_loses_the_mark(sample_page, settings):
    pipeline = _pipeline(settings, DictTranslator(EN_TEXTS))
    pipeline.process(sample_page)
    pipeline.cache.pages[0].incomplete = True
    unit = pipeline.scan(sample_page).units[0]
    assert unit.cached and not pipeline.cache.pages[0].incomplete
