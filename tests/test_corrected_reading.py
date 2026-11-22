"""A misreading corrected in the region editor ("Read as:"): Ask again translates the person's reading, and so does
whatever reads that region again this session (the page translated again, read again from the cache, the region
moved, the page read behind the reader); Save keeps the translation, and the line memo keys it by the corrected reading,
never by the misread one. The reading itself stays in memory: nothing of it reaches the cache, the line memo, the
annotations, the log or any other file of the state folder. Ctrl+Z takes back the translation, not the reading."""
from __future__ import annotations

import json
import logging

import pytest
from helpers import EN_TEXTS, FakeOcr, store_text
from test_translator_mode import Window

from taslation import errorlog, linememo, protect
from taslation.annotations import BookAnnotations
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.regions import region_meta
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod

MISREAD = "どこへ行くの"  # what the OCR reads in that bubble (`helpers.FakeOcr`)
CORRECTED = "どこへ行くのかしら"  # what the person reads there
ANSWER = "Where might you be going?"  # the model's translation of the corrected reading
TYPED = "Where are you off to, then?"


class Asking(Window):
    _ask_model = app_mod.App._ask_model


def _pipeline(settings, book="Book"):
    cache = CacheStore(settings.cache_dir).open(book, "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / f"{book}.json", book)
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator({**EN_TEXTS, CORRECTED: ANSWER}, default="ok"),
                    cache=cache, annotations=ann)


@pytest.fixture
def window(settings, sample_page):
    settings.reuse_lines = True  # (the line memo keeps the person's translation: by which reading is looked at here)
    pipeline = _pipeline(settings)
    result = pipeline.process(sample_page, complete=True)
    assert any(r.source_text == MISREAD for r in result.regions)
    return Asking(pipeline, result)


def _region(w, source=MISREAD):
    return next(r for r in w.last_result.regions if r.source_text == source)


def _data(region, **changed):
    data = {"text": region.translated_text, "speaker": "", "kind": "", "continues": False, "note": "",
            "reader_note": "", "source": region.source_text}
    data.update(changed)
    return data


def _forms(text):
    """The ways a text can be written in a file: UTF-8, UTF-16 either way round, and JSON's ASCII escapes."""
    return [text.encode("utf-8"), text.encode("utf-16-le"), text.encode("utf-16-be"),
            json.dumps(text).strip('"').encode("ascii")]


def _everything_written(root):
    """Every file under *root*, as its bytes and, for a protected store, as TASlation reads it."""
    out = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        raw = path.read_bytes()
        out.append((path, raw))
        try:
            out.append((path, protect.read(path)))
        except Exception:  # noqa: BLE001 - not a protected file: its bytes are what it holds
            pass
    return out


def _sent(translator):
    return [t for call in translator.calls for t in call]


# ------------------------------------------------------------------ Ask again and Save
def test_ask_again_sends_the_corrected_reading_and_save_keeps_its_translation(window):
    w = window
    region = _region(w)
    asked = len(w.pipeline.translator.calls)
    answer = {"source": CORRECTED + "\n"}  # (the editor's field, as it hands it over)
    assert w._ask_model(region, "again", answer, w.last_result)
    assert w.pipeline.translator.calls[asked:] == [[CORRECTED]]
    assert w.events[-1] == ("asked", {"mode": "again", "texts": [ANSWER]})
    assert region.source_text == MISREAD  # nothing reached the region before Save
    w._edit_region(region, _data(region, text=ANSWER, source=CORRECTED), w.last_result)
    assert region.source_text == CORRECTED and region.ocr_reading == MISREAD and region.translated_text == ANSWER
    unit = w.last_result.units[0]
    hit = w.pipeline.cache.lookup(unit.fingerprint, unit.aspect, 36)
    assert ANSWER in [b.text for b in hit[0].bubbles]
    lines = linememo.held_lines(w.pipeline)
    scope = linememo.scope(w.pipeline.translator, w.pipeline.settings.target_language)
    kept = lines.find(scope, linememo.material(CORRECTED, region_meta(region)))
    assert kept is not None and kept.text == ANSWER and kept.edited  # under the corrected reading
    wrong = lines.find(scope, linememo.material(MISREAD, region_meta(region)))
    assert wrong is None or (not wrong.edited and wrong.text != ANSWER)  # never under the misread one


def test_without_a_correction_ask_again_sends_the_reading_as_it_was(window):
    w = window
    region = _region(w)
    asked = len(w.pipeline.translator.calls)
    w._ask_model(region, "again", {"source": ""}, w.last_result)
    w._ask_model(region, "again", {}, w.last_result)
    assert w.pipeline.translator.calls[asked:] == [[MISREAD], [MISREAD]]


def test_the_corrected_reading_is_written_nowhere(window, settings, sample_page, monkeypatch, caplog):
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama 0.0-test")
    errorlog.setup(settings, force=True)  # the session's log, in the test's own state folder
    caplog.set_level(logging.DEBUG)
    try:
        w = window
        region = _region(w)
        w._ask_model(region, "again", {"source": CORRECTED}, w.last_result)
        w._edit_region(region, _data(region, text=ANSWER, source=CORRECTED, speaker="Mio", note="to her friend"),
                       w.last_result)
        w._edit_region(region, _data(region, text=TYPED), w.last_result)  # a typed translation on top of it
        p = w.pipeline
        p.forget_page(w.last_result)  # translated again, read from the cache, read behind the reader
        again = p.process(sample_page, complete=True, reuse=False)
        p.process(sample_page, complete=True)
        p.scan(sample_page, skip_cached=False, behind=True)
        p.cache.save()
        p.save_annotations()
        logging.getLogger("taslation").warning("a line of the session's log")
    finally:
        errorlog.shutdown()
    assert any(r.source_text == CORRECTED for r in again.regions)
    written = _everything_written(settings.state_dir)
    assert any(path.name == "log.txt" for path, _data in written)  # (the log was written)
    assert any(ANSWER.encode() in data for _path, data in written)  # the translation is kept
    for path, data in written:
        for form in _forms(CORRECTED):
            assert form not in data, path
    assert CORRECTED not in caplog.text and CORRECTED not in "".join(r.getMessage() for r in caplog.records)
    assert CORRECTED not in "".join(store_text(p) for p in settings.cache_dir.glob("*.json"))


def test_undo_takes_back_the_translation_and_leaves_the_corrected_reading(window):
    w = window
    region = _region(w)
    before = region.translated_text
    w._edit_region(region, _data(region, text=ANSWER, source=CORRECTED), w.last_result)
    w._edit_region(region, _data(region, text=TYPED), w.last_result)
    w.undo_edit()
    assert region.translated_text == ANSWER and region.source_text == CORRECTED
    w.undo_edit()
    assert w.said[-1] == "Edit taken back." and region.translated_text == before
    assert region.source_text == CORRECTED and region.ocr_reading == MISREAD  # the reading is no change of the stores
    w.redo_edit()
    assert region.translated_text == ANSWER and region.source_text == CORRECTED
    nothing = len(w.history)
    w._edit_region(region, _data(region, source=CORRECTED + "よ"), w.last_result)  # the reading alone: no change to undo
    assert len(w.history) == nothing and region.source_text == CORRECTED + "よ"


# ------------------------------------------------------------------ the rest of the session reads it as corrected
def test_translate_again_and_a_read_behind_the_reader_take_the_region_as_corrected(window, sample_page):
    w = window
    p = w.pipeline
    region = _region(w)
    box = region.bbox
    assert p.correct_reading(w.last_result, region, CORRECTED)
    p.forget_page(w.last_result)
    asked = len(_sent(p.translator))
    again = p.process(sample_page, complete=True, reuse=False)  # "Translate again"
    hit = next(r for r in again.regions if r.bbox == box)
    assert hit.source_text == CORRECTED and hit.ocr_reading == MISREAD and hit.translated_text == ANSWER
    assert CORRECTED in _sent(p.translator)[asked:] and MISREAD not in _sent(p.translator)[asked:]
    scan = p.scan(sample_page, skip_cached=False, behind=True)  # the page read again behind the reader
    assert any(r.source_text == CORRECTED for u in scan.units for r in u.regions)
    assert not any(r.source_text == MISREAD for u in scan.units for r in u.regions)


def test_a_cached_page_read_again_gives_the_corrected_reading(window, settings, sample_page):
    w = window
    p = w.pipeline
    assert p.correct_reading(w.last_result, _region(w), CORRECTED)
    shown = p.process(sample_page, complete=True)  # from the cache: no Japanese on its regions
    reread = [p.read_source(shown, r) for r in shown.regions]
    assert CORRECTED in reread and MISREAD not in reread
    fresh = _pipeline(settings)  # another session: the correction was never kept
    shown = fresh.process(sample_page, complete=True)
    assert MISREAD in [fresh.read_source(shown, r) for r in shown.regions]


def test_a_moved_region_keeps_the_corrected_reading(window):
    w = window
    region = _region(w)
    w._edit_region(region, _data(region, text=TYPED, source=CORRECTED), w.last_result)
    x0, y0, x1, y1 = region.bbox
    asked = len(_sent(w.pipeline.translator))
    w.pipeline.ocr = FakeOcr([MISREAD])  # what it reads in the box grown round it: the same misreading
    w._move_region(region, (x0 - 2, y0 - 2, x1 + 2, y1 + 2))  # grown: read again
    assert region.source_text == CORRECTED and region.translated_text == TYPED
    assert MISREAD not in _sent(w.pipeline.translator)[asked:]


def test_the_ocr_reading_given_back_ends_the_correction(window, sample_page):
    w = window
    p = w.pipeline
    region = _region(w)
    assert p.correct_reading(w.last_result, region, CORRECTED)
    assert not p.correct_reading(w.last_result, region, CORRECTED)  # already so
    assert not p.correct_reading(w.last_result, region, " \n")  # nothing typed: the reading stays
    assert p.correct_reading(w.last_result, region, MISREAD)
    assert region.source_text == MISREAD and region.ocr_reading is None and not p.corrected_readings
    p.forget_page(w.last_result)
    assert any(r.source_text == MISREAD for r in p.process(sample_page, complete=True, reuse=False).regions)


def test_a_reading_typed_where_the_ocr_read_nothing_is_translated(settings, sample_page):
    p = _pipeline(settings)
    p.ocr = FakeOcr([""])  # nothing read anywhere
    result = p.process(sample_page, complete=True)
    region = next(r for r in result.regions if r.status == "ocr-empty")
    assert p.correct_reading(result, region, CORRECTED)
    assert region.status == "untranslated" and region.source_text == CORRECTED and region.ocr_reading == ""
    assert p.ask_again(result, region) == ANSWER
