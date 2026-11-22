"""Each region of a page unit judged as soon as it is read (`pipeline.JUDGE_AT_READ`): the page's usual size is taken
only when a gate needs it (`pipeline._UsualLater`), and every region's fate, the book's sizes and what is told are
what reading all the regions for that size first gives. Fake readers stand in; the real ones read the repository's
own pages both ways at the end (tools/judge_order_check.py, which also reads the sample dataset and the gold set's
screens where this machine has them)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from conftest import requires_ocr
from PIL import Image

from taslation import pipeline as pipeline_mod
from taslation.config import Settings
from taslation.ocr.charspot import CharspotChar, CharspotReading, charspot_accepts
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import judge_order_check  # noqa: E402


def reading(text: str, size: float = 18.0, score: float = 0.9) -> CharspotReading:
    chars = tuple(CharspotChar(c, (0.0, 0.0, size, size), score) for c in text)
    return CharspotReading(text, chars, score)


class Engine:
    """Charspot's reading per region (told by the crop's first pixel) and the others' settling, each call logged."""

    def __init__(self, readings: list[CharspotReading]):
        self.readings = readings
        self.calls: list[tuple[str, int]] = []

    @staticmethod
    def index(image: Image.Image) -> int:
        return image.convert("RGB").getpixel((5, 5))[0] - 1

    def read_chars(self, image: Image.Image) -> CharspotReading:
        i = self.index(image)
        self.calls.append(("charspot", i))
        return self.readings[i]

    def settle(self, image: Image.Image, read: CharspotReading) -> CharspotReading:
        self.calls.append(("settle", self.index(image)))
        return read


def page(n: int, model: tuple[int, ...] = ()) -> tuple[np.ndarray, list[TextRegion]]:
    """*n* bubbles one under the other (those numbered in *model* the layout model's), each crop's first pixel its
    number."""
    rgb = np.full((60 * n + 20, 200, 3), 255, np.uint8)
    regions = []
    for i in range(n):
        y0 = 10 + 60 * i
        rgb[y0:y0 + 50, 10:190] = (i + 1, 200, 200)
        regions.append(TextRegion(10, y0, 190, y0 + 50, np.full((50, 180), 255, np.uint8), (10, y0, 190, y0 + 50),
                                  from_model=i in model))
    return rgb, regions


def read(readings: list[CharspotReading], judge_at_read: bool, monkeypatch, model: tuple[int, ...] = (),
         book: tuple[float, ...] = ()) -> tuple[list[TextRegion], Engine, Pipeline, list[str]]:
    monkeypatch.setattr(pipeline_mod, "JUDGE_AT_READ", judge_at_read)
    engine = Engine(readings)
    rgb, regions = page(len(readings), model)
    p = Pipeline(Settings(), ocr=engine, translator=None)
    p._add_sizes(book)
    told: list[str] = []
    p._ocr_regions(rgb, regions, lambda m: told.append(repr(m)))
    return regions, engine, p, told


def test_a_sure_line_is_settled_before_the_next_region_is_read(monkeypatch):
    regions, engine, _p, _told = read([reading("今日はいい天気"), reading("明日は雨だろう")], True, monkeypatch)
    assert engine.calls == [("charspot", 0), ("settle", 0), ("charspot", 1), ("settle", 1)]
    assert [r.status for r in regions] == ["untranslated", "untranslated"]


def test_read_the_old_way_every_region_is_read_before_any_is_settled(monkeypatch):
    _regions, engine, _p, _told = read([reading("今日はいい天気"), reading("明日は雨だろう")], False, monkeypatch)
    assert engine.calls == [("charspot", 0), ("charspot", 1), ("settle", 0), ("settle", 1)]


def test_a_reading_the_size_decides_waits_for_every_region_s_sample(monkeypatch):
    """Less sure than the gate's sure score: the page's usual size decides, so every region is read for it first."""
    readings = [reading("今日はいい天気", score=0.68), reading("明日は雨だろう"), reading("明後日も雨だ")]
    _regions, engine, _p, _told = read(readings, True, monkeypatch)
    assert engine.calls[:4] == [("charspot", 0), ("charspot", 1), ("charspot", 2), ("settle", 0)]


@pytest.mark.parametrize("model", [(), (0, 1, 2, 3, 4, 5), (1, 3, 4)], ids=["classical", "model", "both"])
def test_both_ways_judge_every_region_alike(monkeypatch, model):
    """Large characters a gate holds to the page's size, sure and unsure, short and empty readings, the book's sizes
    with samples of their own: the same fates, texts, progress and book's sizes either way."""
    readings = [reading("ねえ聞いてよ", 60.0, 0.68), reading("今日はいい天気", 18.0, 0.9),
                reading("あい", 70.0, 0.69), reading("明日は雨だろう", 20.0, 0.8), CharspotReading(),
                reading("ドーン", 90.0, 0.95)]
    runs = [read(readings, way, monkeypatch, model, book=(25.0, 30.0)) for way in (False, True)]
    (ra, _ea, pa, ta), (rb, _eb, pb, tb) = runs
    assert judge_order_check.fingerprint(ra) == judge_order_check.fingerprint(rb)
    assert ta == tb and list(pa._book_sizes) == list(pb._book_sizes)
    assert {r.status for r in rb} >= {"untranslated", "ocr-noise"}  # (the size decided some)


class Wide(Engine):
    """`Engine` whose characters are a tenth of the crop's width: a region read in a narrower box reads smaller."""

    def read_chars(self, image: Image.Image) -> CharspotReading:
        base = super().read_chars(image)
        size = image.width / 10.0
        return CharspotReading(base.text, tuple(CharspotChar(c, (0.0, 0.0, size, size), base.score)
                                                for c in base.text), base.score)


def test_a_region_judged_before_the_size_is_needed_gave_its_sample_as_it_was(monkeypatch):
    """The column a dark bubble's detection took in past its interior, put back by the reading of the first region
    before the second one's gate needs the size: the first is sampled with that column, as reading all first does."""
    sizes: list[list[float]] = []
    real = pipeline_mod.usual_size
    monkeypatch.setattr(pipeline_mod, "usual_size", lambda page, book=(): (sizes.append(list(page)), real(page, book))[1])
    for way in (False, True):
        monkeypatch.setattr(pipeline_mod, "JUDGE_AT_READ", way)
        engine = Wide([reading("今日はいい天気"), reading("明日は雨だろう", score=0.68)])
        rgb, regions = page(2)
        r = regions[0]
        r.beyond_box = (120, r.y0, 190, r.y1)
        r.before_beyond = ((10, r.y0, 120, r.y1), (10, r.y0, 120, r.y1), np.full((50, 110), 255, np.uint8), 0)
        Pipeline(Settings(), ocr=engine, translator=None)._ocr_regions(rgb, regions, lambda _m: None)
        assert r.text_box == (10, r.y0, 120, r.y1)  # (taken back: the reading with the column read no more)
    assert sizes[0] == sizes[1] == [18.0]


def test_the_gate_takes_a_size_given_later_only_where_the_size_decides():
    asked = []

    def usual() -> float:
        asked.append(1)
        return 18.0

    assert charspot_accepts(reading("今日は", 18.0, 0.9), usual) and not asked  # sure: any size
    assert not charspot_accepts(reading("今", 18.0, 0.5), usual) and not asked  # too short
    assert charspot_accepts(reading("今日は", 18.0, 0.5), usual) and asked == [1]
    assert not charspot_accepts(reading("今日は", 60.0, 0.5), usual)
    assert charspot_accepts(reading("今日は", 60.0, 0.5), 25.0) is charspot_accepts(reading("今日は", 60.0, 0.5), lambda: 25.0)


@requires_ocr
@pytest.mark.page_models
def test_the_real_readers_judge_the_repository_s_pages_alike_both_ways():
    """The layout model's regions and the classical ones, read by the real readers: every region the same."""
    results = judge_order_check.check(["repo"], ["on", "off"], log=lambda _m: None)
    assert results and all(r["pages"] and r["different"] == 0 for r in results.values())
