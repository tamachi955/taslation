"""Reader-made premises: annotations (text rectangles per page), glossary, and how the pipeline uses them."""
from __future__ import annotations

import json

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, store_json, store_text

from taslation import fingerprint as fp
from taslation import protect
from taslation.annotations import (
    AnnotationStore,
    BookAnnotations,
    Glossary,
    GlossaryStore,
    RegionStyle,
    format_glossary,
    join_premises,
)
from taslation.cache import CacheStore
from taslation.config import ConfigError, Settings
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

FP_A = "a" * 80
FP_B = "b" * 80


def test_annotations_roundtrip_and_lookup(tmp_path):
    store = AnnotationStore(tmp_path / "ann")
    ann = store.open("Book")
    ann.add_box(FP_A, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
    ann.add_box(FP_A, 0.7, (0.1, 0.1, 0.3, 0.2), "add")  # the same rectangle twice is stored once
    ann.add_box(FP_A, 0.7, (0.5, 0.5, 0.6, 0.7), "ignore")
    ann.save()
    loaded = store.open("Book")
    assert len(loaded) == 1 and loaded.box_count == 2
    drifted = "a" * 79 + "b"  # a few bits off: still the same page
    page = loaded.lookup(drifted, 0.7, max_distance=36)
    assert page is not None and len(page.add) == 1 and len(page.ignore) == 1
    assert loaded.lookup(FP_B, 0.7, max_distance=36) is None
    assert loaded.lookup(FP_A, 1.6, max_distance=36) is None  # another aspect: another page
    assert loaded.remove_box(FP_A, 0.7, (0.1, 0.1, 0.3, 0.2)) == 1 and loaded.box_count == 1
    data = store_json(loaded.path)
    assert data["kind"] == "annotations" and set(data["pages"][0]) == {"fp", "aspect", "add", "ignore"}
    assert store.list()[0]["book"] == "Book" and store.delete("Book") and not store.list()


def test_a_box_past_its_page_units_box_is_kept_and_one_bad_box_loses_only_itself(tmp_path):
    """A rectangle drawn below a page unit cut short of its page was stored at y 1.71 in the unit's terms (the
    reported file): it loads. A box that is no box (out of reach, malformed, a note's) is left out alone, the page
    and its other boxes stay."""
    store = AnnotationStore(tmp_path / "ann")
    ann = store.open("Book")
    ann.add_box(FP_A, 0.7, (0.2, 1.09, 0.55, 1.71), "add")
    ann.save()
    (page,) = store.open("Book").pages
    assert page.add == [(0.2, 1.09, 0.55, 1.71)]
    data = store_json(ann.path)
    raw = data["pages"][0]
    raw["add"] += [[0.1, 1.5, 0.4, 2.5], [0.3, 0.3, 0.2, 0.4], "x", [0.6, 0.6, 0.7, 0.8]]
    raw["ignore"] = [[0.1, 0.1, 0.2, 0.2], [-1.5, 0.1, 0.2, 0.2]]
    raw["order"] = [[0.2, 1.09, 0.55, 1.71], [0.1, 0.1, 0.2, 9.0]]
    raw["notes"] = [{"box": [0.2, 1.09, 0.55, 1.71], "speaker": "ピヨ"}, {"box": [0, 0, 1, 3], "speaker": "X"},
                    {"box": [0.6, 0.6, 0.7, 0.8], "speaker": "ユウ", "style": "bold"}]
    ann.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (page,) = store.open("Book").pages
    assert page.add == [(0.2, 1.09, 0.55, 1.71), (0.6, 0.6, 0.7, 0.8)]
    assert page.ignore == [(0.1, 0.1, 0.2, 0.2)] and page.order == [(0.2, 1.09, 0.55, 1.71)]
    assert [n.speaker for n in page.notes] == ["ピヨ", "ユウ"]
    assert page.set_note((0.3, 1.2, 0.6, 1.9), speaker="ピヨ").speaker == "ピヨ"  # the reader's facts, that far too
    assert page.set_style((-0.8, 0.1, -0.6, 0.3), RegionStyle(bold=True)) is not None
    with pytest.raises(ValueError):
        page.set_note((0.3, 1.2, 0.6, 2.2), speaker="ピヨ")  # beyond reach


def test_glossary_roundtrip_format_and_merge(tmp_path):
    store = GlossaryStore(tmp_path / "gl")
    g = store.open("Series")
    g.set("ピーヨ", "Piiyo", "the mascot's cry")
    g.set("ピーヨ", "Piiyo!", "")  # update keeps one entry
    g.set("魔法少女", "magical girl")
    g.save()
    loaded = store.open("Series")
    assert len(loaded) == 2 and loaded.get("ピーヨ").rendering == "Piiyo!"
    text = loaded.format()
    assert text.startswith("Glossary") and "ピーヨ = Piiyo!" in text and "魔法少女 = magical girl" in text
    assert format_glossary([]) == ""
    other = Glossary(tmp_path / "x.json", "Series")
    other.set("ピーヨ", "Peeyo")  # a different rendering elsewhere does not override mine
    other.set("先輩", "senpai")
    assert loaded.merge(other) == 1 and loaded.get("ピーヨ").rendering == "Piiyo!" and loaded.get("先輩")
    assert loaded.remove("先輩") and not loaded.remove("先輩")
    assert store.path_for("Series", "French").name.endswith(".french.json")
    assert join_premises("", "  ", "a", "b") == "a\n\nb"


def test_saves_never_go_through_a_fixed_temporary_name(tmp_path):
    """Two processes saving at once used to share <file>.json.tmp, and a file of the reader's of that name was
    written over; the JSON looks as before."""
    ann = AnnotationStore(tmp_path / "ann").open("Book")
    ann.add_box(FP_A, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
    gl = GlossaryStore(tmp_path / "gl").open("Series")
    gl.set("ピーヨ", "Piiyo", "the mascot's cry")
    for path in (ann.path, gl.path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_name(path.name + ".tmp").write_text("a file of the reader's", encoding="utf-8")
    ann.save()
    gl.save()
    for path in (ann.path, gl.path):
        assert path.with_name(path.name + ".tmp").read_text(encoding="utf-8") == "a file of the reader's"
        assert protect.is_protected(path.read_bytes())  # saved protected; inside, the JSON as it was dumped
        raw = protect.read(path)
        assert raw == json.dumps(json.loads(raw), ensure_ascii=False, indent=1).encode("utf-8")
        assert sorted(p.name for p in path.parent.iterdir()) == sorted([path.name, path.name + ".tmp"])
    assert "ピーヨ".encode("utf-8") in protect.read(gl.path) and "ピーヨ".encode("utf-8") not in gl.path.read_bytes()


def test_the_store_files_contain_no_text(tmp_path):
    ann = AnnotationStore(tmp_path / "ann").open("Book 1")
    ann.add_box(FP_A, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
    ann.save()
    gl = GlossaryStore(tmp_path / "gl").open("Book")
    gl.set("ピーヨ", "Piiyo")
    gl.save()

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    for path in (ann.path, gl.path):  # geometry and the sheet only: no field could carry a line of the book
        assert "text" not in set(keys(store_json(path)))
    data = store_json(ann.path)
    assert set(data["pages"][0]) == {"fp", "aspect", "add", "ignore"} and data["pages"][0]["fp"] == FP_A
    assert set(store_json(gl.path)["entries"][0]) == {"term", "rendering"}


def test_settings_modes_are_validated():
    Settings(scan_mode="page", role="translator").validate()
    for bad in ({"scan_mode": "all"}, {"role": "editor"}):
        try:
            Settings(**bad).validate()
        except ConfigError:
            continue
        raise AssertionError(bad)


def _pipeline(settings, annotations=None, cache=None):
    tr = DictTranslator(EN_TEXTS, default="ok")
    return Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache, annotations=annotations), tr


def test_glossary_reaches_the_model(sample_page, settings):
    pipeline, tr = _pipeline(settings)
    pipeline.glossary_text = "Glossary (provided by the reader; use these renderings exactly):\n- ピーヨ = Piiyo"
    pipeline.process(sample_page, use_cache=False)
    notes = tr.kwargs[0]["notes"]
    assert notes.startswith("Glossary") and "ピーヨ = Piiyo" in notes  # the series sheet alone: no notes of the model


def test_ignore_box_removes_a_detection_and_add_box_makes_a_region(sample_page, settings):
    plain, _ = _pipeline(settings)
    before = plain.process(sample_page, use_cache=False)
    first = before.translated[0]
    unit = before.units[first.unit]
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    ann.add_box(unit.fingerprint, unit.aspect, unit.normalize(first.text_box), "ignore")
    corner = (0.03, 0.03, 0.18, 0.11)  # top-left corner: scribbles, no bubble there
    ann.add_box(unit.fingerprint, unit.aspect, corner, "add")
    pipeline, _ = _pipeline(settings, annotations=ann)
    after = pipeline.process(sample_page, use_cache=False)
    assert not any(r.x0 <= (first.text_box[0] + first.text_box[2]) / 2 < r.x1
                   and r.y0 <= (first.text_box[1] + first.text_box[3]) / 2 < r.y1 for r in after.regions)
    manual = [r for r in after.regions if r.kind.startswith("manual")]
    assert len(manual) == 1 and manual[0].status == "translated" and manual[0].translated_text
    assert manual[0].bbox == unit.denormalize(corner) and manual[0].mask.min() == 255
    assert len(after.translated) == len(before.translated)  # one dropped, one added


def test_translator_mode_completes_a_cached_page_and_edits_it(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, tr = _pipeline(settings, annotations=ann, cache=cache)
    res = pipeline.process(sample_page)  # miss: translated and cached
    assert res.cache_misses == 1 and len(cache) == 1
    n = cache.pages[0].bubbles.__len__()
    # the reader marks a spot the detector missed; a plain re-read leaves it 'unmatched', translator mode completes it
    assert pipeline.add_region(res, unit_box(res, (0.03, 0.03, 0.18, 0.11)))
    plain = pipeline.process(sample_page)
    assert plain.cache_hits == 1 and any(r.status == "unmatched" and r.kind == "manual" for r in plain.regions)
    assert len(cache.pages[0].bubbles) == n
    done = pipeline.process(sample_page, complete=True)
    manual = [r for r in done.regions if r.kind == "manual"]
    assert manual and manual[0].status == "translated" and manual[0].from_cache
    assert len(cache.pages[0].bubbles) == n + 1
    # editing a translation changes the cache and the picture; dropping a region removes its bubble and records the spot
    target = done.translated[0]
    before_pixels = np.asarray(done.image).copy()
    assert pipeline.set_translation(done, target, "Edited line")
    assert "Edited line" in [b.text for b in cache.pages[0].bubbles]
    assert not np.array_equal(before_pixels, np.asarray(done.image))
    victim = next(r for r in done.translated if r is not target and not r.kind.startswith("manual"))
    count = len(cache.pages[0].bubbles)
    assert pipeline.drop_region(done, victim)
    assert len(cache.pages[0].bubbles) == count - 1 and victim not in done.regions
    page = ann.lookup(res.units[0].fingerprint, res.units[0].aspect, 36)
    assert page is not None and len(page.ignore) == 1 and len(page.add) == 1
    again = pipeline.process(sample_page)  # the dropped spot stays empty on the next read
    assert not any(r.bbox == victim.bbox for r in again.regions)
    data = store_json(cache.path)
    assert "Edited line" in [b["text"] for p in data["pages"] for b in p["bubbles"]]


def unit_box(result, nbox):
    u = result.units[0]
    return u.denormalize(nbox)


def test_manual_region_on_dark_background_is_dark(settings):
    from taslation.pipeline import manual_region

    rgb = np.zeros((100, 100, 3), np.uint8)
    rgb[:50] = 255
    assert manual_region(rgb, (10, 5, 90, 45)).kind == "manual"
    dark = manual_region(rgb, (10, 55, 90, 95))
    assert dark.kind == "manual-dark" and dark.dark


def test_scan_applies_annotations_too(sample_page, settings):
    plain, _ = _pipeline(settings)
    before = plain.scan(sample_page, skip_cached=False).units[0]
    unit = fp.analyze(np.asarray(sample_page))[0]
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    for r in before.regions:
        ann.add_box(unit.fingerprint, unit.aspect, unit.normalize(r.text_box), "ignore")
    pipeline, _ = _pipeline(settings, annotations=ann)
    assert pipeline.scan(sample_page, skip_cached=False).units[0].regions == []


def test_translator_mode_resizes_and_moves_a_region_keeping_its_premises(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "ann.json", "Book")
    pipeline, tr = _pipeline(settings, annotations=ann, cache=cache)
    res = pipeline.process(sample_page)
    target = next(r for r in res.translated if not r.kind.startswith("manual") and r.source_text != "大丈夫だよ")
    text = target.translated_text
    assert pipeline.set_region_note(res, target, speaker="ピヨ", kind="shout")
    x0, y0, x1, y1 = old = target.bbox
    reads, asked = pipeline.ocr.calls, len(tr.calls)
    smaller = (x0 + 4, y0 + 4, x1 - 4, y1 - 4)
    assert pipeline.move_region(res, target, smaller)
    assert target.bbox == smaller and target.kind.startswith("manual") and target.mask.min() == 255
    assert target.status == "translated" and target.translated_text == text and target.speaker == "ピヨ"
    assert pipeline.ocr.calls == reads and len(tr.calls) == asked  # nothing new taken in: neither read nor asked
    unit = res.units[target.unit]
    page = ann.lookup(unit.fingerprint, unit.aspect, 36)
    assert len(page.add) == 1 and len(page.ignore) == 1 and page.note_at(unit.normalize(smaller)).speaker == "ピヨ"
    again = pipeline.process(sample_page)  # the next read finds it there, from the cache, with its premises
    moved = [r for r in again.regions if r.bbox == smaller]
    assert len(moved) == 1 and moved[0].translated_text == text and moved[0].from_cache and moved[0].speaker == "ピヨ"
    assert not any(r.bbox == old for r in again.regions)

    target = moved[0]
    pipeline.ocr = FakeOcr(["大丈夫だよ"])
    grown = (x0 - 6, y0 - 6, x1 + 6, y1 + 6)
    assert pipeline.move_region(again, target, grown)  # it takes in more: read again; a new reading, a new translation
    assert pipeline.ocr.calls == 1 and target.source_text == "大丈夫だよ" and target.translated_text == EN_TEXTS["大丈夫だよ"]
    assert tr.calls[-1] == ["大丈夫だよ"] and target.speaker == "ピヨ"
    page = ann.lookup(unit.fingerprint, unit.aspect, 36)
    assert len(page.add) == 1 and len(page.ignore) == 1  # the reader's own rectangle moved: still one of each
    assert EN_TEXTS["大丈夫だよ"] in [b.text for b in cache.pages[0].bubbles] and text not in [b.text for b in cache.pages[0].bubbles]
    asked = len(tr.calls)
    assert pipeline.move_region(again, target, (x0 - 10, y0 - 10, x1 + 10, y1 + 10))  # the same reading: kept
    assert pipeline.ocr.calls == 2 and len(tr.calls) == asked and target.translated_text == EN_TEXTS["大丈夫だよ"]
    assert not pipeline.move_region(again, target, (x0, y0, x0 + 3, y0 + 3))  # too small
    plain, _ = _pipeline(settings, cache=cache)  # no premises file (the book has no name): nothing is moved
    assert not plain.move_region(again, target, smaller) and target.bbox == (x0 - 10, y0 - 10, x1 + 10, y1 + 10)
