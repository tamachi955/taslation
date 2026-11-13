"""The OCR's gate: a reading is held to the page's usual character size, whatever order the regions were read in, and
regions the reader added skip it. A fake engine stands in (no model needed); the real model has its own test."""
from __future__ import annotations

import numpy as np
import pytest
from conftest import requires_ocr
from PIL import Image

from taslation.config import Settings
from taslation.ocr import CharspotEngine, ModelNotInstalled
from taslation.ocr.charspot import (DEFAULT_USUAL_SIZE, CharspotChar, CharspotReading, charspot_accepts, check_model_dir,
                                    read_crop, size_sample, usual_size, written)
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion


def reading(text: str, size: float = 18.0, score: float = 0.9, n: int | None = None) -> CharspotReading:
    chars = tuple(CharspotChar("あ", (0.0, 0.0, size, size), score) for _ in range(len(text) if n is None else n))
    return CharspotReading(text, chars, score)


def test_the_size_of_a_reading_is_the_median_of_its_characters():
    chars = (CharspotChar("あ", (0, 0, 10, 20), 0.9), CharspotChar("い", (0, 0, 30, 10), 0.9), CharspotChar("う", (0, 0, 40, 40), 0.9))
    assert CharspotReading("あいう", chars, 0.9).size == 30


def test_the_gate():
    assert charspot_accepts(reading("あいう", 54), 18)
    assert not charspot_accepts(reading("あいう", 55, score=0.68), 18)  # three times the usual size at most
    assert not charspot_accepts(reading("あ", 18), 18)  # one character is not enough on its own


def test_the_usual_size_falls_back_on_the_book_then_the_default():
    assert usual_size([10, 20, 60], [500]) == 20
    assert usual_size([], [30, 40]) == 35
    assert usual_size([], []) == DEFAULT_USUAL_SIZE
    assert size_sample(reading("あいうえ", 20, 0.75)) == 20
    assert size_sample(reading("あいう", 20, 0.9)) is None  # too short to say
    assert size_sample(reading("あいうえ", 20, 0.74)) is None  # too unsure to say


def test_marks_are_written_as_the_rest_of_the_program_expects():
    assert written("な に ?!") == "なに？！"
    assert written("そう……") == "そう......" .replace(".", "\uff0e")
    assert written("A1") == "\uff21\uff11"


def test_a_simple_engine_is_read_through_the_same_seam():
    class Plain:
        def read(self, image):
            return "あい"

    class Sure:
        def read_with_confidence(self, image):
            return "あい", 0.8

    image = Image.new("RGB", (8, 8))
    assert read_crop(Plain(), image) == CharspotReading("あい", (), 1.0)
    assert read_crop(Sure(), image) == CharspotReading("あい", (), 0.8)


class Page:
    """Regions on a white page, each with what the fake engine reads there, told by the crop's first pixel."""

    def __init__(self, readings: list[CharspotReading], kind: str = "bubble"):
        self.rgb = np.full((60 * len(readings) + 20, 200, 3), 255, np.uint8)
        self.regions, self.by_colour = [], {}
        for i, one in enumerate(readings):
            y0 = 10 + 60 * i
            self.rgb[y0:y0 + 50, 10:190] = (i + 1, 200, 200)
            mask = np.full((50, 180), 255, np.uint8)
            self.regions.append(TextRegion(10, y0, 190, y0 + 50, mask, (10, y0, 190, y0 + 50), kind=kind))
            self.by_colour[i + 1] = one

    def read_chars(self, image: Image.Image) -> CharspotReading:
        return self.by_colour[image.convert("RGB").getpixel((5, 5))[0]]


def _read(page: Page, regions=None, settings: Settings | None = None) -> Pipeline:
    p = Pipeline(settings or Settings(), ocr=page, translator=None)
    p._ocr_regions(page.rgb, list(page.regions if regions is None else regions), lambda _m: None)
    return p


def test_huge_characters_on_a_page_of_normal_lettering_are_noise():
    page = Page([reading("今日はいい天気", 18), reading("明日は雨だろう", 18), reading("今日も晴れたね", 60, 0.68)])
    _read(page)
    assert [r.status for r in page.regions] == ["untranslated", "untranslated", "ocr-noise"]


def test_a_low_score_is_low_confidence():
    page = Page([reading("今日はいい天気", 18), reading("明日は雨だろう", 18, 0.6)])
    _read(page)
    assert [r.status for r in page.regions] == ["untranslated", "low-confidence"]


def test_the_score_is_kept_as_the_confidence_and_the_reading_as_the_text():
    page = Page([reading("今日はいい天気", 18, 0.83)])
    _read(page)
    assert page.regions[0].source_text == "今日はいい天気" and page.regions[0].ocr_confidence == 0.83


def test_the_result_does_not_depend_on_the_order_of_reading():
    make = lambda: Page([reading("今日も晴れたね", 60, 0.68), reading("今日はいい天気", 18), reading("明日は雨だろう", 18)])  # noqa: E731
    first, second = make(), make()
    _read(first)
    _read(second, list(reversed(second.regions)))
    assert [r.status for r in first.regions] == [r.status for r in second.regions]
    assert [r.y0 for r in second.regions] == [10, 70, 130]  # reading moves no region


def test_a_page_without_samples_takes_the_book_s_size():
    book = Page([reading("今日はいい天気", 40)])
    p = _read(book)
    page = Page([reading("そうだ", 100, 0.68)])  # 100 <= 3 x 40, and too short to be a sample itself
    p.ocr = page
    p._ocr_memo.clear()
    p._ocr_regions(page.rgb, page.regions, lambda _m: None)
    assert page.regions[0].status == "untranslated"
    page = Page([reading("そうだ", 130, 0.68)])
    p._ocr_memo.clear()  # the same pixels as the page before
    p.ocr = page
    p._ocr_regions(page.rgb, page.regions, lambda _m: None)
    assert page.regions[0].status == "ocr-noise"


@pytest.mark.parametrize("one", [reading("あ", 200, 0.75), reading("そうだね", 200, 0.4)], ids=["one character", "unsure and huge"])
def test_a_region_the_reader_added_skips_every_gate(one):
    page = Page([one], kind="manual")
    _read(page)
    assert page.regions[0].status == "untranslated" and page.regions[0].source_text == one.text


def test_a_missing_model_is_said(tmp_path):
    assert check_model_dir(tmp_path) == ["model.safetensors", "vocab.json", "config.json"]
    with pytest.raises(ModelNotInstalled) as info:
        CharspotEngine(tmp_path)
    assert info.value.message.code == "ocr.model_missing"


@requires_ocr
def test_the_real_model_reads_the_sample_page(sample_page, sample_truth, settings):
    engine = CharspotEngine(settings.ocr_model_dir)
    x0, y0, x1, y1 = sample_truth[0]["text_box"]
    got = engine.read_chars(sample_page.crop((x0 - 4, y0 - 4, x1 + 4, y1 + 4)))
    assert got.text and got.chars and 0.0 < got.score <= 1.0 and got.size > 0
    assert engine.read_with_confidence(sample_page.crop((x0 - 4, y0 - 4, x1 + 4, y1 + 4))) == (got.text, got.score)


def test_a_reading_this_sure_is_lettering_at_any_size():
    assert charspot_accepts(reading("あいう", 90, score=0.7), 18)
    assert not charspot_accepts(reading("あいう", 90, score=0.69), 18)
    assert not charspot_accepts(reading("あ", 90, score=0.99), 18)  # still two characters at least
