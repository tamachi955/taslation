"""The model is told the room a small bubble has beforehand; a translation that would be set too small is set smaller
and flagged "small" (nothing is asked of the model again since 2026-11-06)."""

from __future__ import annotations

import numpy as np

from taslation.pipeline import Pipeline, ScannedRegion, lettering_size, translation_room
from taslation.regions import TextRegion
from taslation.translate import DictTranslator

LONG = "I honestly cannot believe that you would go and do something like this to me of all people."


def _region(x0, y0, x1, y1, text_box, **kw) -> TextRegion:
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box, status="untranslated",
                      source_text="こんにちは", **kw)


def test_a_small_bubble_gets_the_hint_and_a_long_line_there_is_flagged(settings):
    tr = DictTranslator({"こんにちは": LONG})
    p = Pipeline(settings, ocr=None, translator=tr)
    small = _region(0, 0, 60, 40, (5, 5, 55, 35))
    big = _region(0, 100, 400, 400, (150, 200, 250, 300))
    assert p._translate_regions([small, big], lambda _m: None) == ""
    assert small.translated_text == big.translated_text == LONG and len(tr.calls) == 1  # one request, no other
    assert "small" in small.flags and "small" not in big.flags
    meta = tr.kwargs[-1]["meta"]
    assert meta[0].get("room") and not meta[1].get("room")  # the model is told the room only where it is short


def test_no_hint_and_no_flag_when_the_feature_is_off(settings):
    settings.readable_font_size = 0
    tr = DictTranslator({"こんにちは": LONG})
    p = Pipeline(settings, ocr=None, translator=tr)
    small = _region(0, 0, 60, 40, (5, 5, 55, 35))
    p._translate_regions([small], lambda _m: None)
    assert small.translated_text == LONG and "small" not in small.flags
    assert not any(m.get("room") for m in tr.kwargs[-1]["meta"] or [])


def test_scanned_region_rebuilds_its_mask_from_the_outline():
    r = ScannedRegion(bbox=(10, 10, 70, 50), text_box=(15, 15, 65, 45), poly=[(0, 0), (59, 0), (59, 39), (0, 39)],
                      source_text="x", status="untranslated")
    assert r.mask.shape == (40, 60) and r.mask.min() == 255


def test_lettering_size_and_room(settings):
    assert lettering_size((0, 0, 40, 200), "あいうえお", 11, 18) == 18  # 40 px columns: large lettering
    assert lettering_size((0, 0, 20, 60), "あいうえおかきくけこ", 11, 18) == 11  # tiny lettering: the readable floor
    mask = np.full((300, 400), 255, np.uint8)
    assert translation_room(mask, (150, 100, 250, 200), "こんにちは", settings) == 0  # plenty of room: no hint
    small = np.full((40, 60), 255, np.uint8)
    assert 4 <= translation_room(small, (5, 5, 55, 35), "こんにちは", settings) < 20
