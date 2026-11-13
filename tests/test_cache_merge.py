"""The cache file is shared by every process that has the book open (the app and a batch run): saves merge."""
from __future__ import annotations

import json

import numpy as np

from taslation.cache import BookCache, CacheStore, CachedBubble, CachedPage
from taslation.regions import TextRegion
from helpers import store_json

FP_X = "a" * 80
FP_P = "b" * 80
FP_Q = "c" * 80


def _page(fp: str, texts: list[str], seq: int = -1) -> CachedPage:
    return CachedPage(fingerprint=fp, aspect=0.71, seq=seq,
                      bubbles=[CachedBubble(box=(0.1 * (i + 1), 0.1, 0.1 * (i + 1) + 0.05, 0.2), text=t)
                               for i, t in enumerate(texts)])


def _texts(path) -> dict[str, list[str]]:
    data = store_json(path)
    return {p["fp"]: [b["text"] for b in p["bubbles"]] for p in data["pages"]}


def test_two_processes_merge_their_saves(tmp_path):
    """A stale copy (the app, open since before a batch run) must not undo what the batch pruned or added."""
    store = CacheStore(tmp_path)
    first = store.open("b", "m")
    first.add(_page(FP_X, ["Hello", "Then..."]))
    first.save()
    app = store.open("b", "m")  # the app loads the file ...
    batch = store.open("b", "m")  # ... and so does a batch run
    batch.add(_page(FP_X, ["Hello"]))  # the batch prunes the junk bubble
    batch.add(_page(FP_P, ["New page"]))
    batch.save()
    app.add(_page(FP_Q, ["Live page"]))  # the stale app copy saves something of its own afterwards
    app.save()
    texts = _texts(app.path)
    assert texts[FP_X] == ["Hello"]  # the pruning survived
    assert texts[FP_P] == ["New page"] and texts[FP_Q] == ["Live page"]
    seqs = [p["seq"] for p in store_json(app.path)["pages"]]
    assert len(seqs) == len(set(seqs)) == 3  # both appended a page: no sequence number is shared
    # and the batch copy, saving again, keeps the app's page too
    batch.add(_page(FP_X, ["Hello!"]))
    batch.save()
    texts = _texts(app.path)
    assert texts[FP_X] == ["Hello!"] and texts[FP_Q] == ["Live page"] and len(texts) == 3


def test_refresh_picks_up_pages_saved_by_another_process(tmp_path):
    store = CacheStore(tmp_path)
    writer = store.open("b", "m")
    writer.add(_page(FP_X, ["Hello"]))
    writer.save()
    reader = store.open("b", "m")
    assert reader.refresh() is False  # nothing changed since it was loaded
    writer.add(_page(FP_P, ["New page"]))
    writer.save()
    assert reader.lookup(FP_P, 0.71, max_distance=10) is None
    assert reader.refresh() is True
    assert reader.lookup(FP_P, 0.71, max_distance=10) is not None
    assert reader.refresh() is False


def test_pipeline_rescan_replaces_the_matched_entry_even_when_the_fingerprint_drifted(sample_page, settings):
    """The same page captured again differs by a few bits: pruning must update that entry, not add a second one."""
    from test_pipeline import EN_TEXTS, DictTranslator, FakeOcr

    from taslation import fingerprint as fp
    from taslation.pipeline import Pipeline

    unit = fp.analyze(np.asarray(sample_page))[0]
    drifted = format(int(unit.fingerprint, 16) ^ ((1 << 12) - 1), "080x")  # 12 bits flipped: still the same page
    cache = BookCache(settings.cache_dir / "drift.json", "Drift", "m")
    cache.add(CachedPage(drifted, unit.aspect, [CachedBubble(box=(0.05, 0.05, 0.15, 0.12), text="Then...")], seq=0))
    cache.save()
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    u = pipeline.scan(sample_page).units[0]
    assert u.dropped == 1 and u.stored_fingerprint == drifted and not u.cached
    assert pipeline.commit_unit(u, {i: EN_TEXTS.get(r.source_text, "ok") for i, r in enumerate(u.japanese())})
    data = store_json(cache.path)
    assert len(data["pages"]) == 1 and data["pages"][0]["fp"] == drifted
    assert "Then..." not in [b["text"] for b in data["pages"][0]["bubbles"]]


class _StubOcr:
    def __init__(self, text: str, confidence: float = 0.95):
        self.text, self.confidence = text, confidence

    def read_with_confidence(self, crop):
        return self.text, self.confidence


def _region(kind: str, pieces: int) -> TextRegion:
    return TextRegion(x0=0, y0=0, x1=60, y1=60, mask=np.full((60, 60), 255, np.uint8), text_box=(5, 5, 55, 55),
                      kind=kind, pieces=pieces)


def test_many_pieces_but_little_text_is_noise_for_bubbles_too(settings):
    """A face inside a white shape: dozens of dark pieces, a handful of guessed characters."""
    from taslation.pipeline import Pipeline

    rgb = np.full((60, 60, 3), 255, np.uint8)
    face = _region("bubble", pieces=36)
    Pipeline(settings, ocr=_StubOcr("あいうえおか"), translator=None)._ocr_regions(rgb, [face], lambda _m: None)
    assert face.status == "ocr-noise"
    real = _region("bubble", pieces=28)  # 15 characters from 28 pieces: ordinary lettering
    Pipeline(settings, ocr=_StubOcr("あいうえおかきくけこさしすせそ"), translator=None)._ocr_regions(rgb, [real], lambda _m: None)
    assert real.status == "untranslated"
    unknown = _region("cached", pieces=0)  # no piece count: the rule does not apply
    Pipeline(settings, ocr=_StubOcr("あい"), translator=None)._ocr_regions(rgb, [unknown], lambda _m: None)
    assert unknown.status == "untranslated"
