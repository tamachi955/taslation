"""What a reading is: dialogue to translate or why not (`Pipeline._judge`), on stub readings with confidences."""
from __future__ import annotations

import numpy as np
import pytest

from taslation.pipeline import Pipeline
from taslation.regions import TextRegion


def _region(kind: str = "text-on-page", size: int = 44, pieces: int = 2) -> TextRegion:
    """A small region as the detector leaves a small bubble: cut down to its lettering, under min_short_bubble."""
    return TextRegion(x0=100, y0=100, x1=100 + size, y1=104 + size, mask=np.full((size + 4, size), 255, np.uint8),
                      text_box=(112, 106, 88 + size, 102 + size), kind=kind, pieces=pieces)


def _judge(settings, text: str, confidence: float, kind: str = "text-on-page", size: int = 44, pieces: int = 2,
           unanimous: bool = False) -> str:
    return Pipeline(settings, ocr=None, translator=None)._judge(_region(kind, size, pieces), text, confidence, pieces,
                                                                unanimous)


@pytest.mark.parametrize("kind", ["bubble", "dark-bubble", "text-on-page", "text-on-dark"])
def test_a_short_line_in_a_small_bubble_is_dialogue(settings, kind):
    """One or two characters the OCR is sure of, in a small region the bubble detector closed: a short line."""
    assert max(_region().width, _region().height) < settings.min_short_bubble
    for text in ("ねえ", "やだ", "誰？", "よ", "嘘"):
        assert _judge(settings, text, 0.99, kind, pieces=3 if len(text) == 2 else 2) == "untranslated", len(text)


def test_a_short_line_needs_the_ocr_to_be_sure(settings):
    assert _judge(settings, "ねえ", 0.95) == "untranslated"
    assert _judge(settings, "ねえ", 0.94) == "ocr-noise"  # the tiny-region rule, as before
    assert _judge(settings, "よ", 0.9) == "ocr-noise"  # one character: the pieces rule, as before
    assert _judge(settings, "ねえ", 0.5) == "low-confidence"


def test_a_short_line_all_the_readers_read_needs_less_confidence(settings):
    assert _judge(settings, "ねえ", 0.92, unanimous=True) == "untranslated"
    assert _judge(settings, "ねえ", 0.9, unanimous=True) == "untranslated"
    assert _judge(settings, "ねえ", 0.89, unanimous=True) == "ocr-noise"
    assert _judge(settings, "ねえ", 0.92) == "ocr-noise"
    for text in ("ドン", "っ", "ー", "あ♪"):  # what is no short line stays none, whatever the readers say
        assert _judge(settings, text, 0.99, "bubble", unanimous=True) == "ocr-noise", text
    assert _judge(settings, "ねえ", 0.99, "text", unanimous=True) == "ocr-noise"


def test_one_character_passes_charspot_s_gate_only_when_all_the_readers_read_it(settings):
    """The gate wants two characters (`charspot_accepts`): a short line all the readers read is spared it."""
    from taslation.ocr.charspot import CharspotChar, CharspotReading

    pipeline = Pipeline(settings, ocr=None, translator=None)
    one = CharspotReading("よ", (CharspotChar("よ", (0.0, 0.0, 30.0, 30.0), 0.99),), 0.99)
    assert pipeline._verdict(_region(), one, 2, 20.0) == "ocr-noise"
    assert pipeline._verdict(_region(), one, 2, 20.0, unanimous=True) == "untranslated"
    assert pipeline._verdict(_region("text"), one, 2, 20.0, unanimous=True) == "ocr-noise"
    assert pipeline._verdict(_region(size=200), one, 4, 20.0, unanimous=True) == "ocr-noise"  # four pieces: a face


@pytest.mark.parametrize("kind", ["text", "text-dark"])
def test_text_blocks_have_no_short_lines(settings, kind):
    """Lettering found without an outline around it: one or two characters there are still noise when small."""
    assert _judge(settings, "ねえ", 1.0, kind) == "ocr-noise"
    assert _judge(settings, "よ", 1.0, kind) == "ocr-noise"


@pytest.mark.parametrize("text", ["ドン", "ゴゴ", "っ", "ょお", "ー", "ーー", "〜あ", "あ♪"])
def test_katakana_small_kana_marks_and_symbols_are_no_short_lines(settings, text):
    """Pieces of drawn sound effects, a small kana or a long-vowel mark at the start, a symbol: noise when small."""
    assert _judge(settings, text, 1.0, "bubble") == "ocr-noise"


def test_many_pieces_read_as_one_character_stay_noise(settings):
    """A face or a drawing read as one character with confidence: more dark pieces than a glyph and a mark."""
    assert _judge(settings, "よ", 1.0, "bubble", pieces=3) == "untranslated"
    assert _judge(settings, "よ", 1.0, "bubble", pieces=4) == "ocr-noise"
    assert _judge(settings, "ねえ", 1.0, "bubble", pieces=7) == "ocr-noise"  # a small region, too many pieces
    # a large region: the pieces rule as before (two characters from 15 dark pieces of a bubble are artwork)
    assert _judge(settings, "ねえ", 1.0, "bubble", size=200, pieces=15) == "ocr-noise"
    assert _judge(settings, "ねえ", 1.0, "bubble", size=200, pieces=14) == "untranslated"


def test_other_verdicts_are_unchanged(settings):
    assert _judge(settings, "", 1.0) == "ocr-empty"
    assert _judge(settings, "！？", 1.0) == "not-japanese"  # marks only: the lettering stays as drawn
    assert _judge(settings, "OK", 1.0) == "not-japanese"
    assert _judge(settings, "まさか", 1.0, "text") == "untranslated"  # three characters were never short
    assert _judge(settings, "ねえ", 0.8, "text", size=60) == "untranslated"  # not under min_short_bubble


def test_min_short_bubble_still_decides_for_other_short_readings(settings):
    settings.min_short_bubble = 30
    assert _judge(settings, "ねえ", 0.8, "text") == "untranslated"  # the region is not small any more
    settings.min_short_bubble = 60
    assert _judge(settings, "ねえ", 0.8, "text") == "ocr-noise"


class _StubOcr:
    def __init__(self, text: str, confidence: float):
        self.text, self.confidence = text, confidence

    def read_with_confidence(self, crop):
        return self.text, self.confidence


def test_a_small_bubble_with_a_short_line_is_read_for_translation(settings):
    """Through the OCR stage: the region's status, text and confidence as the translation sees them."""
    rgb = np.full((300, 300, 3), 255, np.uint8)
    line, fleck = _region(), _region()
    Pipeline(settings, ocr=_StubOcr("ねえ", 0.99), translator=None)._ocr_regions(rgb, [line], lambda _m: None)
    Pipeline(settings, ocr=_StubOcr("ねえ", 0.8), translator=None)._ocr_regions(rgb, [fleck], lambda _m: None)
    assert (line.status, line.source_text, line.ocr_confidence) == ("untranslated", "ねえ", 0.99)
    assert fleck.status == "ocr-noise"
