from __future__ import annotations

import json

import numpy as np
from helpers import EN_TEXTS, FailingTranslator, FakeOcr, JA_TEXTS, store_json, store_text
from PIL import Image

from taslation.cache import BookCache, CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator


def test_translate_render_and_cache(sample_page, settings):
    ocr = FakeOcr()
    tr = DictTranslator(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Test Book", "fake")
    pipeline = Pipeline(settings, ocr=ocr, translator=tr, cache=cache)

    res = pipeline.process(sample_page)
    assert res.cache_misses == 1 and res.cache_hits == 0 and not res.error
    assert len(res.translated) >= 6
    assert len(tr.calls) == 1 and ocr.calls >= 6
    assert [r.order for r in res.regions] == list(range(len(res.regions)))
    before, after = np.asarray(sample_page), np.asarray(res.image)
    for r in res.translated:
        assert (before[r.y0:r.y1, r.x0:r.x1] != after[r.y0:r.y1, r.x0:r.x1]).any()
        assert r.font_size >= settings.min_font_size

    # cache: translated text + geometry only, written to disk
    assert cache.path.is_file()
    raw = store_text(cache.path)
    data = json.loads(raw)
    assert data["pages"] and data["pages"][0]["bubbles"]
    assert all(b["text"] in EN_TEXTS.values() for b in data["pages"][0]["bubbles"])
    for ja in JA_TEXTS:
        assert ja not in raw  # the original text is never stored

    # second pass: served from the cache, no OCR, no translator
    ocr_calls, tr_calls = ocr.calls, len(tr.calls)
    p2 = Pipeline(settings, ocr=ocr, translator=tr, cache=BookCache.load(cache.path))
    res2 = p2.process(sample_page)
    assert res2.cache_hits == 1 and res2.cache_misses == 0
    assert ocr.calls == ocr_calls and len(tr.calls) == tr_calls
    assert len(res2.translated) == len(res.translated)
    assert all(r.from_cache for r in res2.translated)

    # the same page shown smaller (different window size) still hits and renders
    small = sample_page.resize((sample_page.width * 2 // 3, sample_page.height * 2 // 3), Image.LANCZOS)
    res3 = p2.process(small)
    assert res3.cache_hits == 1
    assert len(res3.translated) == len(res.translated)


def test_non_japanese_text_is_left_alone(sample_page, settings):
    tr = DictTranslator({})
    pipeline = Pipeline(settings, ocr=FakeOcr(["Hello", "12345"]), translator=tr)
    res = pipeline.process(sample_page, use_cache=False)
    assert tr.calls == []
    assert {r.status for r in res.regions} <= {"not-japanese"}
    assert np.array_equal(np.asarray(res.image), np.asarray(sample_page))


def test_translation_failure_is_reported_not_cached(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=FailingTranslator(), cache=cache)
    res = pipeline.process(sample_page)
    assert "cannot reach Ollama" in res.error
    assert res.translated == []
    assert len(cache) == 0 and not cache.path.exists()


def test_echoed_source_never_reaches_the_cache(sample_page, settings):
    """An echoing translator (or a model that copies the Japanese) must not poison the cache."""
    from taslation.translate import EchoTranslator

    cache = CacheStore(settings.cache_dir).open("Echo Book", "echo")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=EchoTranslator(), cache=cache)
    res = pipeline.process(sample_page)
    assert res.translated == []
    assert all(r.status == "untranslated" for r in res.regions)
    assert len(cache) == 0 and not cache.path.exists()


def test_partially_translated_page_is_cached_and_marked(sample_page, settings):
    mapping = dict(EN_TEXTS)
    mapping.pop("こんにちは")  # one bubble stays untranslated
    cache = CacheStore(settings.cache_dir).open("Partial", "dict")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(mapping), cache=cache)
    res = pipeline.process(sample_page)
    assert len(res.translated) >= 5
    assert any(r.status == "untranslated" for r in res.regions)
    assert len(cache) == 1 and cache.pages[0].incomplete  # what came is kept, what is missing is asked for later
    assert cache.bubble_count == len(res.translated)


def test_page_without_ocr_engine_is_not_cached(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("NoOcr", "dict")
    Pipeline(settings, ocr=None, translator=DictTranslator(EN_TEXTS), cache=cache).process(sample_page)
    assert len(cache) == 0
    # ... and the next run with OCR therefore still reads the page
    ocr = FakeOcr()
    res = Pipeline(settings, ocr=ocr, translator=DictTranslator(EN_TEXTS), cache=cache).process(sample_page)
    assert ocr.calls >= 6 and len(res.translated) >= 6 and len(cache) == 1


def test_cached_geometry_is_clamped_to_the_image(sample_page, settings):
    from taslation.cache import BookCache, CachedBubble, CachedPage
    from taslation import fingerprint as fp

    settings.render_unmatched_cached = True
    unit = fp.analyze(np.asarray(sample_page))[0]
    cache = BookCache(settings.cache_dir / "x.json", "X", "m")
    cache.add(CachedPage(unit.fingerprint, unit.aspect, [CachedBubble(box=(-0.2, -0.2, 0.1, 0.1), text="Edge")], seq=0))
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator({}), cache=cache)
    res = pipeline.process(sample_page)
    assert res.cache_hits == 1
    edge = [r for r in res.regions if r.translated_text == "Edge"]
    assert edge and edge[0].x0 >= 0 and edge[0].y0 >= 0


def test_stale_cached_bubbles_are_not_drawn_and_are_pruned_on_rescan(sample_page, settings):
    """A cache made by an earlier, worse detector: a junk bubble over artwork must neither be drawn nor survive a re-scan."""
    from taslation.cache import BookCache, CachedBubble, CachedPage
    from taslation import fingerprint as fp

    unit = fp.analyze(np.asarray(sample_page))[0]
    cache = BookCache(settings.cache_dir / "stale.json", "Stale", "m")
    junk = CachedBubble(box=(0.05, 0.05, 0.15, 0.12), text="Then...")  # top-left corner: scribbles, no text
    cache.add(CachedPage(unit.fingerprint, unit.aspect, [junk], seq=0))
    cache.save()
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    # live mode: the junk is not composited
    res = pipeline.process(sample_page)
    assert res.cache_hits == 1 and not any(r.translated_text == "Then..." for r in res.regions)
    # re-scan: the junk is dropped, the real bubbles are new work
    scan = pipeline.scan(sample_page)
    u = scan.units[0]
    assert u.dropped == 1 and u.kept == [] and len(u.japanese()) >= 6 and not u.cached
    translations = {i: EN_TEXTS.get(r.source_text, "ok") for i, r in enumerate(u.japanese())}
    assert pipeline.commit_unit(u, translations)
    data = store_json(cache.path)
    texts = [b["text"] for p in data["pages"] for b in p["bubbles"]]
    assert "Then..." not in texts and len(texts) >= 6
    # a second re-scan keeps everything and translates nothing
    again = pipeline.scan(sample_page).units[0]
    assert again.cached and again.dropped == 0 and len(again.kept) == len(texts)


def test_is_real_translation():
    from taslation.pipeline import is_real_translation

    assert is_real_translation("こんにちは", "Hello")
    assert not is_real_translation("こんにちは", "こんにちは")
    assert not is_real_translation("こんにちは", "こんにちは (hello)")
    assert not is_real_translation("こんにちは", "こんにちは", target_language="Japanese")
    assert is_real_translation("こんにちは", "やあ", target_language="Japanese")


def test_ocr_only(sample_page, settings):
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
    res = pipeline.process(sample_page, use_cache=False, translate=False)
    assert res.translated == []
    assert all(r.status == "untranslated" and r.source_text for r in res.regions)


def test_without_ocr_engine(sample_page, settings):
    res = Pipeline(settings, ocr=None, translator=None).process(sample_page, use_cache=False)
    assert all(r.status == "ocr-unavailable" for r in res.regions)


def test_context_carries_over_pages(sample_page, sample_page2, settings):
    tr = DictTranslator(EN_TEXTS, default="...")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr)
    pipeline.process(sample_page, use_cache=False)
    assert pipeline.context_pairs()
    pipeline.process(sample_page2, use_cache=False)
    assert len(tr.calls) == 2
