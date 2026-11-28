"""A page's time budget (`taslation.budget`) and the bounds of the helpers whose cost grows with what the page holds:
LaMa's windows, pixels and hole per page and its part's pixels per window, OpenCV's fill past them, the tone fill's
look and its rounds, large unsure lettering on a colour picture left as drawn, a page over its budget said in the log
with its stage and helper, and each stage of the made-up screens (tools/book_screens.py, and its harder cover) inside a
budget scaled to the computer it runs on. Before, a colour cover took 80 s on a computer with a GPU (detection 23 s,
erase and lettering 53 s): LaMa had no bound per page nor per window, and on the processor - where a failure on the
GPU sends it for the session - it takes some 5 s a million pixels. Made-up pages and fakes only; no model is loaded."""
from __future__ import annotations

import logging
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from taslation import analysis, budget
from taslation.regions import TextRegion
from taslation.render import artwork
from taslation.render.artwork import ArtEraser

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import book_screens  # noqa: E402


@pytest.fixture(autouse=True)
def no_budget_left_over():
    yield
    while budget.current() is not None:
        budget.end(budget.current())
    analysis.stop()


def region(kind="text", box=(100, 100, 200, 300), **more):
    x0, y0, x1, y1 = box
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box=box,
                      kind=kind, **more)


class FakeModel:
    """Fills every hole with grey and keeps the shapes it was run on; *seconds_per_mpx* of sleep a million pixels."""

    def __init__(self, device="cpu", seconds_per_mpx=0.0):
        self.device, self.seconds_per_mpx = device, seconds_per_mpx
        self.shapes: list[tuple[int, int]] = []

    def run(self, image, mask):
        self.shapes.append(image.shape[:2])
        if self.seconds_per_mpx:
            time.sleep(self.seconds_per_mpx * image.shape[0] * image.shape[1] / 1e6)
        out = image.copy()
        out[mask] = 128
        return out


def drawn(size=(600, 1400), seed=7):
    """A ground with a drawing's texture (no flat colour, no repeat)."""
    noise = np.random.default_rng(seed).integers(150, 256, size, dtype=np.uint8)
    return np.dstack([cv2.GaussianBlur(noise, (0, 0), 1.0)] * 3)


def ringed(page, x0, y0):
    """Three glyphs of strokes with a white ring at (*x0*, *y0*) on *page*: lettering on the drawing, its box
    (x0 - 10, y0 - 10, x0 + 30, y0 + 160)."""
    for y in (y0, y0 + 50, y0 + 100):
        cv2.rectangle(page, (x0 - 6, y - 6), (x0 + 26, y + 26), (255, 255, 255), -1)
        cv2.rectangle(page, (x0, y), (x0 + 20, y + 20), (0, 0, 0), 3)
    return region("text", (x0 - 10, y0 - 10, x0 + 30, y0 + 160), letter_box=(x0, y0, x0 + 21, y0 + 121))


def eraser_with(tmp_path, model):
    calls = []

    def fallback(image, r, *args):
        calls.append(r)
        return (1, 2, 3)
    eraser = ArtEraser(tmp_path, "lama", fallback)
    eraser._model, eraser._checked = model, True
    return eraser, calls


# ------------------------------------------------------------------ the page's budget
def test_lama_is_refused_past_the_pages_windows_pixels_hole_and_time():
    assert budget.lama_refused(10 ** 9, 10 ** 9, False) == ""  # (no page: nothing refused)
    page = budget.begin(area=1000 * 1000, seconds=100.0)
    for _ in range(budget.LAMA_PAGE_WINDOWS):
        assert budget.lama_refused(1000, 10, True) == ""
    assert budget.lama_refused(1000, 10, True) == "windows"
    budget.end(page)
    page = budget.begin(area=1000 * 1000, seconds=100.0)
    assert budget.lama_refused(10 ** 8, 10, False) == ""  # (a page's first window: never for its pixels or hole)
    assert budget.lama_refused(1000, 10, False) == "pixels"
    budget.end(page)
    page = budget.begin(area=1000 * 1000, seconds=100.0)
    assert budget.lama_refused(1000, 100_000, True) == ""
    assert budget.lama_refused(1000, int(budget.LAMA_PAGE_HOLE * 10 ** 6), True) == "hole"
    page.started -= budget.LAMA_UNTIL * 100.0 + 1  # (the page has spent more of its budget than LaMa may)
    assert budget.lama_refused(1000, 10, True) == "time"
    assert page.refused == {"hole": 1, "time": 1}
    budget.end(page)
    assert budget.current() is None


def test_the_budget_follows_the_threads_that_work_for_the_page():
    import threading

    page = budget.begin(seconds=7.0)
    seen = []

    def work():
        seen.append(budget.current())
        with budget.adopt(page):
            seen.append(budget.current())
        seen.append(budget.current())
    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert seen == [None, page, None] and budget.current() is page
    inner = budget.begin(seconds=1.0)  # (a page read inside another: the outer one back at its end)
    budget.end(inner)
    assert budget.current() is page
    budget.end(page)


def test_past_the_budget_lettering_on_the_drawing_gets_opencvs_fill_and_no_lama(tmp_path, monkeypatch):
    """Past `LAMA_PAGE_WINDOWS` windows the regions on the drawing are filled by OpenCV's inpainting (milliseconds):
    the lettering gone all the same, nothing kept on the region to use again, the analysis log told why. (On the
    processor its pixels stop it sooner: five windows of 512 x 512.)"""
    monkeypatch.setattr(budget, "LAMA_PAGE_CPU_PX", 10 ** 9)  # (the windows' rule alone)
    model = FakeModel()
    eraser, calls = eraser_with(tmp_path, model)
    page = drawn()
    regions = [ringed(page, 40 + 90 * k, 200) for k in range(budget.LAMA_PAGE_WINDOWS + 2)]
    analysis.start(tmp_path, "on")
    line_page = analysis.begin(None, None)
    spending = budget.begin(area=page.shape[0] * page.shape[1], seconds=100.0)
    for r in regions:
        eraser.erase(page, r)
    budget.end(spending)
    line = analysis.end(line_page, SimpleNamespace(regions=regions, timings={}, units=[1]))
    assert len(model.shapes) == budget.LAMA_PAGE_WINDOWS and eraser.counts["art"] == budget.LAMA_PAGE_WINDOWS
    assert eraser.counts["telea"] == 2 and not calls and spending.refused == {"windows": 2}
    for r in regions[-2:]:
        assert r.inpainted is None and "telea" in r.trace["acted"]
        x0, y0, x1, y1 = r.letter_box
        assert page[y0:y1, x0:x1].min() > 60  # (no stroke left: the drawing's levels are 150 and more)
    assert line["counts"]["lama.refused.windows"] == 2 and line["effect"]["telea"] == 2
    monkeypatch.undo()
    model.shapes.clear()
    page = drawn()
    regions = [ringed(page, 40 + 90 * k, 200) for k in range(8)]
    spending = budget.begin(area=page.shape[0] * page.shape[1], seconds=100.0)
    for r in regions:
        eraser.erase(page, r)
    budget.end(spending)
    assert len(model.shapes) == 5 and spending.refused == {"pixels": 3}  # (1.5 Mpx: five windows of 512 x 512)


def test_a_part_larger_than_lamas_pixels_is_run_scaled_down_and_filled_back_at_its_size(tmp_path, monkeypatch):
    monkeypatch.setattr(artwork, "LAMA_PART_CPU_PX", 200 * 300)
    model = FakeModel()
    eraser, _calls = eraser_with(tmp_path, model)
    part = np.full((400, 600, 3), 200, np.uint8)
    hole = np.zeros((400, 600), bool)
    hole[150:250, 250:350] = True
    filled = eraser._fill(part, hole)
    (shape,) = model.shapes
    assert shape[0] * shape[1] <= 200 * 300 and filled.shape == part.shape
    assert (filled[hole] == 128).all()  # (the fill scaled back over all of the hole)
    small, taken = artwork.scaled_part(part, hole, 10 ** 6)
    assert small is part and taken is hole  # (within the pixels: as it is)


def test_the_tone_fill_is_bounded_in_what_it_looks_at_and_in_its_rounds(monkeypatch):
    tone = np.full((500, 500, 3), 255, np.uint8)
    for y in range(0, 500, 6):
        for x in range((y // 6 % 2) * 3, 500, 6):
            cv2.circle(tone, (x, y), 2, (40, 40, 40), -1)
    hole = np.zeros((500, 500), bool)
    hole[150:350, 200:280] = True
    assert artwork.tone_shifts(tone, hole) is not None
    monkeypatch.setattr(artwork, "TONE_MOST_PX", 100 * 100)
    assert artwork.tone_shifts(tone, hole) is None  # (a window this large: LaMa's, or the fill past it)
    monkeypatch.undo()
    page = tone.copy()
    page[hole] = 0
    monkeypatch.setattr(artwork, "TONE_ROUNDS", 1)  # (one round from the hole's edge, and no other repeats after it)
    monkeypatch.setattr(artwork, "TONE_SHIFTS", artwork.TONE_NEAR)
    assert not artwork.fill_tone(page, hole) and (page[hole] == 0).all()  # (not all painted: nothing is)
    monkeypatch.undo()
    assert artwork.fill_tone(page, hole)


# ------------------------------------------------------------------ large unsure lettering on a colour picture
def test_large_unsure_lettering_on_a_colour_picture_is_left_as_drawn():
    """On the harder cover's picture: lettering read unsure three times the body's size is left as drawn (S3 in the
    log at the most); read with confidence, small, on paper, or set by hand, it stays to translate."""
    from taslation.pipeline import Pipeline

    rgb = book_screens.hard_cover("strokes")
    x0, y0 = book_screens.COVER[:2]

    def read(box, size, conf, kind="text"):
        r = region(kind, box, source_text="あいうえお", status="untranslated", char_size=size, ocr_confidence=conf)
        return r

    big = read((x0 + 40, y0 + 400, x0 + 400, y0 + 490), 84, 0.7)
    sure = read((x0 + 40, y0 + 500, x0 + 400, y0 + 590), 84, 0.95)
    small = read((x0 + 300, y0 + 600, x0 + 360, y0 + 700), 26, 0.7)
    paper = np.full_like(rgb, 255)
    on_paper = read((x0 + 40, y0 + 400, x0 + 400, y0 + 490), 84, 0.7)
    by_hand = read((x0 + 40, y0 + 400, x0 + 400, y0 + 490), 84, 0.7, kind="manual")
    host = SimpleNamespace(_sizes_seen=lambda: deque([26.0, 25.0]))
    analysis.start(None, "on")
    page = analysis.begin(None, None)
    regions = [big, sure, small, by_hand]
    Pipeline._big_unsure(host, rgb, regions, 26.0, None, (x0, y0, book_screens.COVER[2], book_screens.COVER[3]))
    Pipeline._big_unsure(host, paper, [on_paper], 26.0, None, (0, 0, 1920, 1032))
    assert big.status == "low-confidence" and "big_unsure" in big.trace["acted"]
    assert sure.status == small.status == on_paper.status == by_hand.status == "untranslated"
    cases, minor = analysis.page_defects([big])
    assert not cases and minor == {"unsure_left_as_drawn": 1}  # (S3: never an S1 or S2 case)
    analysis.end(page, None)
    # a cover with no body lettering yet: the body taken as a thirtieth of its unit's height at the most
    alone = read((x0 + 40, y0 + 400, x0 + 400, y0 + 490), 84, 0.7)
    Pipeline._big_unsure(SimpleNamespace(_sizes_seen=lambda: deque()), rgb, [alone], 84.0, None, (0, 0, 1920, 942))
    assert alone.status == "low-confidence"


# ------------------------------------------------------------------ a page over its budget
def test_a_page_over_its_budget_is_said_in_the_log_with_its_stage_and_helper(tmp_path, monkeypatch, caplog):
    from helpers import EN_TEXTS, FakeOcr

    from taslation.config import Settings
    from taslation.pipeline import Pipeline
    from taslation.translate.simple import DictTranslator

    monkeypatch.setattr(budget, "PAGE_BUDGET_CPU_S", 0.0)  # (any page is over it)
    monkeypatch.setattr(budget, "PAGE_BUDGET_S", 0.0)
    settings = Settings(state_dir=tmp_path / "state")
    settings.validate()
    settings.margins = book_screens.BARS_ONLY
    analysis.start(tmp_path, "on")
    caplog.set_level(logging.WARNING, logger="taslation.pipeline")
    result = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None).process(
        Image.fromarray(book_screens.cover("strokes")))
    said = [r.getMessage() for r in caplog.records if "over its time budget" in r.getMessage()]
    assert len(said) == 1 and "(S1)" in said[0]
    stage = max(result.timings.items(), key=lambda kv: kv[1])[0]
    assert f"slowest stage {stage}" in said[0] and "slowest helper " in said[0] and "not timed" not in said[0]
    (case,) = [c for c in analysis.records()[-1]["cases"] if c["code"] == "page_slow"]
    assert case["level"] == "s1" and case["stage"] and case["helper"] and case["budget_s"] == 0.0
    analysis.stop()
    caplog.clear()
    Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None).process(
        Image.fromarray(book_screens.cover("strokes")))
    said = [r.getMessage() for r in caplog.records if "over its time budget" in r.getMessage()]
    assert len(said) == 1 and "not timed (the analysis log is off)" in said[0]


# ------------------------------------------------------------------ each stage inside a budget scaled to the computer
# The stages' seconds on the made-up screens with the classical detectors, a fake OCR and a dictionary for the
# translator (no model): on the development machine at most detect 0.067, ocr 0.026, translate 0.005, render 0.024,
# fingerprint 0.006, a page 0.13 s (measured 2026-11-28, the worst of three); the budgets give some eight times that,
# and a computer slower by the factor `machine_factor` measures gets as much more.
STAGE_BUDGET_S = {"detect": 0.5, "ocr": 0.25, "translate": 0.1, "render": 0.25}
OTHER_STAGE_S = 0.1
PAGE_S = 1.0
REFERENCE_S = 0.014  # `machine_factor`'s work on the development machine (13 to 15 ms)


def machine_factor() -> float:
    """How much slower than the development machine this one is at the work a page does (blurs, a distance transform,
    connected pieces over a frame), at least 1: the best of five runs against `REFERENCE_S`."""
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 256, (1032, 1920), dtype=np.uint8)
    best = float("inf")
    for _ in range(5):
        t = time.perf_counter()
        blur = cv2.GaussianBlur(frame, (0, 0), 2.0)
        dist = cv2.distanceTransform((blur > 128).astype(np.uint8), cv2.DIST_L2, 3)
        cv2.connectedComponentsWithStats((blur < 100).astype(np.uint8), connectivity=8)
        float(dist.mean())
        best = min(best, time.perf_counter() - t)
    return max(1.0, best / REFERENCE_S)


@pytest.mark.parametrize("make", [book_screens.cover, book_screens.colour_spread, book_screens.grey_spread,
                                  book_screens.hard_cover], ids=lambda f: f.__name__)
def test_each_stage_of_the_made_up_screens_stays_in_its_scaled_budget(tmp_path, make):
    from helpers import EN_TEXTS, FakeOcr

    from taslation.config import Settings
    from taslation.pipeline import Pipeline
    from taslation.translate.simple import DictTranslator

    settings = Settings(state_dir=tmp_path / "state")
    settings.validate()
    settings.margins, settings.reuse_lines = book_screens.BARS_ONLY, False
    pipe = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None)
    image = Image.fromarray(make("strokes"))
    pipe.process(image)  # (the first page: what is loaded and imported once)
    pipe.forget_shown()
    t = time.perf_counter()
    result = pipe.process(image, use_cache=False)
    took = time.perf_counter() - t
    factor = machine_factor()
    over = {k: round(v, 3) for k, v in result.timings.items() if v > STAGE_BUDGET_S.get(k, OTHER_STAGE_S) * factor}
    assert not over, f"stages over their budget x {factor:.1f}: {over}"
    assert took <= PAGE_S * factor <= budget.PAGE_BUDGET_CPU_S


def test_a_slow_lama_on_the_harder_cover_keeps_the_page_in_its_budget(tmp_path, monkeypatch):
    """LaMa on the processor (some 5.4 s a million pixels, here a twentieth of it with the budget a twentieth too):
    the harder cover's regions on the drawing take LaMa until the budget says no more, and the page stays in its
    budget with every region erased."""
    from helpers import EN_TEXTS, FakeOcr

    from taslation.config import Settings
    from taslation.pipeline import Pipeline
    from taslation.render.erase import erase_region
    from taslation.translate.simple import DictTranslator

    scale = 1 / 20
    monkeypatch.setattr(budget, "PAGE_BUDGET_CPU_S", budget.PAGE_BUDGET_CPU_S * scale * machine_factor())
    monkeypatch.setattr(budget, "PAGE_BUDGET_S", budget.PAGE_BUDGET_CPU_S)
    settings = Settings(state_dir=tmp_path / "state")
    settings.validate()
    settings.margins, settings.reuse_lines = book_screens.BARS_ONLY, False
    pipe = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None)
    model = FakeModel(seconds_per_mpx=5.4 * scale)
    pipe.art_eraser, _calls = eraser_with(tmp_path, model)
    pipe.art_eraser.fallback = erase_region
    image = Image.fromarray(book_screens.hard_cover("strokes"))
    t = time.perf_counter()
    result = pipe.process(image, use_cache=False)
    took = time.perf_counter() - t
    assert took <= budget.PAGE_BUDGET_CPU_S
    assert len(model.shapes) <= budget.LAMA_PAGE_WINDOWS
    assert sum(h * w for h, w in model.shapes) <= budget.LAMA_PAGE_CPU_PX + artwork.LAMA_PART_CPU_PX
    assert all(h * w <= artwork.LAMA_PART_CPU_PX for h, w in model.shapes)
    assert any(r.status == "translated" for r in result.regions)
