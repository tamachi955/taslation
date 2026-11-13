"""End-to-end checks with the real OCR model. Skipped until setup_models.py has run."""

from __future__ import annotations

import difflib

import numpy as np
from conftest import requires_ocr
from helpers import EN_TEXTS
from PIL import Image

from taslation import netguard
from taslation.cache import CacheStore
from taslation.ocr import CharspotEngine
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

pytestmark = requires_ocr


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def test_real_ocr_reads_the_sample_bubbles(sample_page, sample_truth, settings):
    netguard.install()
    engine = CharspotEngine(settings.ocr_model_dir)
    good = 0
    for t in sample_truth:
        x0, y0, x1, y1 = t["text_box"]
        crop = sample_page.crop((x0 - 12, y0 - 12, x1 + 12, y1 + 12))
        text = engine.read(crop)
        if similarity(text, t["text"]) >= 0.6:
            good += 1
    assert good >= len(sample_truth) - 1, "OCR disagreed with the ground truth on more than one bubble"


def test_real_ocr_confidence_separates_text_from_noise(sample_page, sample_truth, settings):
    netguard.install()
    engine = CharspotEngine(settings.ocr_model_dir)
    x0, y0, x1, y1 = sample_truth[0]["text_box"]
    text, conf = engine.read_with_confidence(sample_page.crop((x0 - 12, y0 - 12, x1 + 12, y1 + 12)))
    assert text and 0.0 <= conf <= 1.0
    assert conf > 0.5  # clean lettering is read with confidence
    assert engine.read(sample_page.crop((x0 - 12, y0 - 12, x1 + 12, y1 + 12))) == text
    noise = sample_page.crop((70, 110, 230, 300))  # scribbled artwork, no text
    _, noise_conf = engine.read_with_confidence(noise)
    assert noise_conf < conf


def test_full_pipeline_offline_with_real_ocr(sample_page, sample_truth, settings):
    """Real OCR + a dictionary translator, under the guard: nothing may try to reach out."""
    st = netguard.install()
    before = len(st.blocked)
    engine = CharspotEngine(settings.ocr_model_dir)
    expected = {t["text"]: EN_TEXTS.get(t["text"], "OK") for t in sample_truth}
    cache = CacheStore(settings.cache_dir).open("Offline Book", "dict")
    pipeline = Pipeline(settings, ocr=engine, translator=DictTranslator(expected, default="(?)"), cache=cache)
    res = pipeline.process(sample_page)
    assert len(res.translated) >= len(sample_truth) - 1
    assert len(st.blocked) == before
    assert len(cache) == 1
    out = np.asarray(res.image)
    assert out.shape == np.asarray(sample_page).shape
    # exact OCR text for at least most bubbles
    exact = sum(1 for r in res.regions if r.source_text in expected)
    assert exact >= len(sample_truth) - 2
    # a second, smaller view is served from the cache without OCR
    res2 = pipeline.process(sample_page.resize((900, 1273), Image.LANCZOS))
    assert res2.cache_hits == 1
