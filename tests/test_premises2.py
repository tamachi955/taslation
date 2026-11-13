"""Speakers, kinds, continuations, reading order, skipped pages, book settings, page sequence, series sheet."""
from __future__ import annotations

import json

import numpy as np
from helpers import EN_TEXTS, FakeOcr, store_json

from taslation import fingerprint as fp
from taslation.annotations import (
    AnnotationStore,
    BookAnnotations,
    CharacterSheet,
    Glossary,
    GlossaryStore,
    StyleGuide,
    clean_book_settings,
)
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.translate.ollama import OllamaTranslator

FP_A = "a" * 80


def _pipeline(settings, annotations=None, cache=None):
    tr = DictTranslator(EN_TEXTS, default="ok")
    return Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache, annotations=annotations), tr


def test_region_notes_reach_the_model_and_survive_a_reload(sample_page, settings):
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, tr = _pipeline(settings, annotations=ann)
    res = pipeline.process(sample_page, use_cache=False)
    first, second = res.translated[0], res.translated[1]
    assert pipeline.set_region_note(res, first, speaker="ピヨ", kind="shout", continues=True, note="a pun on 猫")
    assert first.speaker == "ピヨ" and first.tag == "shout" and first.continues
    ann.save()
    reloaded = BookAnnotations.load(ann.path)
    pipeline2, tr2 = _pipeline(settings, annotations=reloaded)
    res2 = pipeline2.process(sample_page, use_cache=False)
    metas = [{k: v for k, v in m.items() if k != "page"} for m in tr2.kwargs[0]["meta"]]  # (every line has its page)
    assert any(m == {"speaker": "ピヨ", "kind": "shout", "continues": True, "note": "a pun on 猫"} for m in metas)
    # only the annotated region carries the reader's facts (another may carry the continuation rule's "continues")
    assert sum(1 for m in metas if set(m) - {"continues"}) == 1
    again = next(r for r in res2.regions if r.bbox == first.bbox)
    assert again.speaker == "ピヨ" and again.to_dict()["speaker"] == "ピヨ"
    # an all-empty note removes the entry
    assert pipeline.set_region_note(res, first)
    assert ann.lookup(res.units[0].fingerprint, res.units[0].aspect, 36).notes == []


def test_reading_order_override(sample_page, settings):
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, tr = _pipeline(settings, annotations=ann)
    res = pipeline.process(sample_page, use_cache=False)
    regions = list(res.regions)
    reversed_order = list(reversed(regions))
    assert pipeline.set_reading_order(res, reversed_order)
    assert [r.bbox for r in res.regions] == [r.bbox for r in reversed_order]
    res2 = pipeline.process(sample_page, use_cache=False)
    assert [r.bbox for r in res2.regions] == [r.bbox for r in reversed_order]
    assert tr.calls[-1] == [r.source_text for r in res2.regions if r.status == "translated"]


def test_skipped_page_has_no_regions(sample_page, settings):
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, _ = _pipeline(settings, annotations=ann)
    res = pipeline.process(sample_page, use_cache=False)
    assert res.regions
    assert pipeline.set_page_skip(res, True) and pipeline.is_skipped(res)
    assert pipeline.process(sample_page, use_cache=False).regions == []
    assert pipeline.scan(sample_page, skip_cached=False).units[0].regions == []
    assert pipeline.set_page_skip(res, False) and not pipeline.is_skipped(res)
    assert pipeline.process(sample_page, use_cache=False).regions


def test_book_settings_override_the_readers_settings(sample_page, settings):
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, _ = _pipeline(settings, annotations=ann)
    assert pipeline.settings.white_threshold == settings.white_threshold
    applied = pipeline.set_book_settings({"white_threshold": 200, "detect_text_blocks": False, "ollama_url": "x", "bogus": 1})
    assert applied == {"white_threshold": 200, "detect_text_blocks": False}
    assert pipeline.settings.white_threshold == 200 and pipeline.text_detector is None
    assert pipeline.detector.cfg.white_threshold == 200
    assert settings.white_threshold != 200  # the reader's own settings are untouched
    reloaded = BookAnnotations.load(ann.path)
    assert reloaded.settings == applied
    pipeline.set_book_settings({})
    assert pipeline.settings.white_threshold == settings.white_threshold and pipeline.text_detector is not None
    assert clean_book_settings({"erase_mode": " inpaint ", "min_bubble_size": 30}) == {"erase_mode": "inpaint", "min_bubble_size": 30}


def test_scan_records_the_page_sequence(sample_page, sample_page2, settings):
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, _ = _pipeline(settings, annotations=ann)
    pipeline.scan(sample_page, skip_cached=False)
    pipeline.scan(sample_page2, skip_cached=False)
    pipeline.scan(sample_page, skip_cached=False)  # seen again: not recorded twice
    assert len(ann.sequence) == 2
    unit = fp.analyze(np.asarray(sample_page2))[0]
    assert min(range(2), key=lambda i: fp.hamming(ann.sequence[i][0], unit.fingerprint)) == 1


def test_forget_page_drops_the_cached_translations(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, tr = _pipeline(settings, annotations=BookAnnotations(settings.state_dir / "a.json", "Book"), cache=cache)
    res = pipeline.process(sample_page)
    assert len(cache) == 1 and len(tr.calls) == 1
    assert pipeline.forget_page(res) == 1 and len(cache) == 0
    assert store_json(cache.path)["pages"] == []
    pipeline.process(sample_page)
    assert len(tr.calls) == 2 and len(cache) == 1


def test_series_sheet_characters_and_style(tmp_path):
    store = GlossaryStore(tmp_path / "gl")
    g = store.open("Series")
    g.set_character(CharacterSheet(name="ピヨ", rendering="Piyo", gender="female", age="teen", pronoun="私",
                                   style="polite, shy", role="the heroine", addresses={"ピーヨ": "Piiyo"}))
    g.set("魔法少女", "magical girl")
    g.style = StyleGuide(honorifics="keep", tone="light comedy; keep the puns", rules=["Sound effects stay short."])
    g.save()
    loaded = store.open("Series")
    text = loaded.format()
    assert "Characters" in text and "ピヨ = Piyo (female, teen; first person 私; polite, shy; the heroine; calls ピーヨ \"Piiyo\")" in text
    assert "Glossary" in text and "魔法少女 = magical girl" in text
    assert "Style guide" in text and "-san" in text and "light comedy" in text and "Sound effects stay short." in text
    assert loaded.speaker_names() == ["ピヨ", "Piyo"]
    other = Glossary(tmp_path / "o.json", "Series")
    other.set_character(CharacterSheet(name="ピヨ", rendering="Peeyo", gender="female", age="adult", role="x"))
    other.set_character(CharacterSheet(name="ゾリ", rendering="Zori"))
    other.style = StyleGuide(honorifics="drop", rules=["Sound effects stay short.", "Keep -sama."])
    added = loaded.merge(other)
    mine = loaded.get_character("ピヨ")
    assert mine.rendering == "Piyo" and mine.age == "teen" and loaded.get_character("Zori") is not None
    assert loaded.style.honorifics == "keep" and loaded.style.rules == ["Sound effects stay short.", "Keep -sama."]
    assert added == 2
    assert loaded.remove_character("ゾリ") and not loaded.remove_character("ゾリ")


def test_ollama_messages_carry_bubble_facts():
    tr = OllamaTranslator("http://127.0.0.1:11434", "m", 5.0, 0.2, 0, "English")
    messages = tr.build_messages(["あ", "い"], [], "notes", (), meta=[{"speaker": "ピヨ", "continues": True}, {}])
    user = messages[1]["content"]
    items = json.loads(user.split("Bubbles to translate:\n", 1)[1])
    assert items[0] == {"id": 1, "ja": "あ", "speaker": "ピヨ", "continues": True} and items[1] == {"id": 2, "ja": "い"}
    assert "speaker" in messages[0]["content"] and "continues" in messages[0]["content"]


def test_the_stores_keep_everything_across_a_reload(tmp_path):
    ann_store, gl_store = AnnotationStore(tmp_path / "ann"), GlossaryStore(tmp_path / "gl")
    ann = ann_store.open("Book 1")
    page = ann.page(FP_A, 0.7)
    page.add.append((0.1, 0.1, 0.3, 0.2))
    page.set_note((0.5, 0.5, 0.6, 0.7), speaker="ピヨ", kind="thought")
    page.order = [(0.5, 0.5, 0.6, 0.7), (0.1, 0.1, 0.3, 0.2)]
    ann.page("b" * 80, 0.7).skip = True
    ann.set_settings({"white_threshold": 210})
    ann.record_sequence(FP_A, 0.7)
    ann.record_sequence("b" * 80, 0.7)
    ann.reading_direction = "rtl"
    ann.save()
    gl = gl_store.open("Book")
    gl.set("ピーヨ", "Piiyo")
    gl.set_character(CharacterSheet(name="ピヨ", rendering="Piyo", gender="female"))
    gl.style = StyleGuide(honorifics="keep")
    gl.save()
    got = AnnotationStore(tmp_path / "ann").open("Book 1")
    gp = got.lookup(FP_A, 0.7, 36)
    assert gp.add == [(0.1, 0.1, 0.3, 0.2)]
    assert gp.notes[0].speaker == "ピヨ" and gp.notes[0].kind == "thought" and len(gp.order) == 2
    assert got.lookup("b" * 80, 0.7, 36).skip and got.settings == {"white_threshold": 210}
    assert len(got.sequence) == 2 and got.reading_direction == "rtl"
    g2 = GlossaryStore(tmp_path / "gl").open("Book")
    assert g2.get_character("ピヨ").rendering == "Piyo" and g2.style.honorifics == "keep" and g2.get("ピーヨ")


def test_the_style_guide_may_suggest_a_lettering_font_the_model_is_not_told(tmp_path):
    store = GlossaryStore(tmp_path / "gl")
    g = store.open("Series")
    g.style = StyleGuide(font="Comic Neue")
    assert not g.style.is_empty and g.style.to_json() == {"font": "Comic Neue"} and g.format() == ""
    g.save()
    loaded = store.open("Series")
    assert loaded.style.font == "Comic Neue"
    loaded.style.tone = "light comedy"
    assert "light comedy" in loaded.format() and "Comic Neue" not in loaded.format()
    assert loaded.style.fill_from(StyleGuide(font="Wild Words")) == 0 and loaded.style.font == "Comic Neue"  # mine stays
    empty = StyleGuide()
    assert empty.fill_from(StyleGuide(font="Wild Words")) == 1 and empty.font == "Wild Words"
    assert StyleGuide.from_json({"font": "x" * 100}).font == "x" * 60
