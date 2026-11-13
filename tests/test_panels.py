"""Panels and the reading order: synthetic pages, the panel-aware order, the fallback to rows, the reader's hints, the
pipeline's use of it, and the evaluation tool. With the OpenMantra dataset and TASLATION_REALDATA=1, the order on real
pages too."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from helpers import EN_TEXTS, FakeOcr, JA_TEXTS

from taslation.cache import CacheStore
from taslation.detect import find_panels, order_on_page, order_panels, order_regions
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion, apply_order_hints
from taslation.translate import DictTranslator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
import reading_order_eval  # noqa: E402

SIZE = (900, 640)  # height, width
TALL_RIGHT = [(340, 20, 620, 880), (20, 20, 320, 440), (20, 460, 320, 880)]
GRID = [(330, 20, 620, 430), (20, 20, 310, 430), (330, 450, 620, 880), (20, 450, 310, 880)]


def _region(x0, y0, x1, y1):
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), (x0, y0, x1, y1))


def page(panels, paper=255, ink=0, tone=170, size=SIZE):
    """A page of framed panels with something drawn in them; *paper* shows between them."""
    img = np.full((*size, 3), paper, np.uint8)
    for x0, y0, x1, y1 in panels:
        cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), (ink, ink, ink), 3)
        cv2.line(img, (x0 + 30, y0 + 40), (x1 - 40, y1 - 30), (tone, tone, tone), 5)
    return img


def near(found, wanted, slack=8):
    return len(found) == len(wanted) and all(
        any(all(abs(a - b) <= slack for a, b in zip(f, w)) for f in found) for w in wanted)


def test_a_tall_panel_beside_two_stacked():
    assert near(find_panels(page(TALL_RIGHT)), TALL_RIGHT)
    assert order_panels(find_panels(page(TALL_RIGHT)))[0][0] > 300  # the tall one first, on the right
    tall_low, upper, lower = _region(400, 500, 560, 620), _region(60, 60, 200, 160), _region(60, 600, 200, 700)
    tall_high = _region(400, 100, 560, 220)
    regions = [lower, upper, tall_low, tall_high]
    assert order_regions(regions) == [tall_high, upper, tall_low, lower]  # rows mix the columns
    ordered = order_on_page(page(TALL_RIGHT), (0, 0, SIZE[1], SIZE[0]), regions)
    assert ordered == [tall_high, tall_low, upper, lower]
    assert [r.order for r in ordered] == [0, 1, 2, 3]


def test_a_grid_is_read_row_by_row_right_first():
    assert order_panels(GRID) == [GRID[0], GRID[1], GRID[2], GRID[3]]
    assert order_panels(GRID, rtl=False) == [GRID[1], GRID[0], GRID[3], GRID[2]]


def test_left_to_right_mirrors_the_page():
    mirrored = [(640 - x1, y0, 640 - x0, y1) for x0, y0, x1, y1 in TALL_RIGHT]
    tall_low, upper, lower = _region(80, 500, 240, 620), _region(440, 60, 580, 160), _region(440, 600, 580, 700)
    tall_high = _region(80, 100, 240, 220)
    ordered = order_on_page(page(mirrored), (0, 0, SIZE[1], SIZE[0]), [lower, upper, tall_low, tall_high], rtl=False)
    assert ordered == [tall_high, tall_low, upper, lower]


def test_a_borderless_page_keeps_the_rows_exactly():
    img = np.full((*SIZE, 3), 255, np.uint8)
    cv2.circle(img, (320, 450), 250, (120, 120, 120), -1)
    assert len(find_panels(img)) <= 1
    regions = [_region(60, 60, 200, 160), _region(400, 70, 560, 180), _region(300, 400, 420, 500)]
    rows = order_regions(list(regions))
    assert order_on_page(img, (0, 0, SIZE[1], SIZE[0]), list(regions)) == rows
    assert order_regions(list(regions), panels=[(0, 0, 640, 900)]) == rows  # one panel is no panels
    assert order_regions(list(regions), panels=[]) == rows


def test_blank_sky_in_a_framed_panel_is_no_gutter():
    assert near(find_panels(page([(20, 20, 620, 880)], tone=255)), [(20, 20, 620, 880)])


def test_a_region_across_two_panels_goes_where_its_centre_is():
    lower_panel, upper_panel = (20, 460, 620, 880), (20, 20, 620, 440)
    mostly_upper = _region(100, 300, 200, 470)  # centre 385
    mostly_lower = _region(450, 420, 550, 620)  # centre 520
    first = _region(450, 60, 550, 160)
    ordered = order_regions([mostly_lower, mostly_upper, first], panels=[lower_panel, upper_panel])
    assert ordered == [first, mostly_upper, mostly_lower]


def test_a_bubble_on_a_gutter_does_not_hide_it():
    img = page([(20, 20, 620, 440), (20, 460, 620, 880)])
    cv2.ellipse(img, (320, 450), (130, 70), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, (320, 450), (130, 70), 0, 0, 360, (0, 0, 0), 3)
    bubble = (190, 380, 450, 520)
    assert len(find_panels(img, ignore=[bubble])) == 2


def test_black_gutters():
    img = page(GRID, paper=0, ink=255, tone=200)
    for x0, y0, x1, y1 in GRID:
        img[y0:y1, x0:x1] = 235
    assert len(find_panels(img)) == 4


def test_panels_drawn_with_a_rule_and_no_gutter():
    img = np.full((*SIZE, 3), 120, np.uint8)
    cv2.line(img, (0, 450), (639, 450), (0, 0, 0), 2)
    assert len(find_panels(img)) == 2


def test_the_panels_are_in_image_pixels_inside_the_box():
    img = np.full((1080, 1920, 3), 30, np.uint8)
    img[90:990, 500:1140] = page(TALL_RIGHT)
    found = find_panels(img, (500, 90, 1140, 990))
    assert near(found, [(x0 + 500, y0 + 90, x1 + 500, y1 + 90) for x0, y0, x1, y1 in TALL_RIGHT])
    assert find_panels(img, (0, 0, 0, 0)) == []


def slanted(across: bool = True, fall: int = 70, gap: int = 30) -> tuple[np.ndarray, list[list[tuple[int, int]]]]:
    """A page of two framed panels with a slanted gutter between them: across (top and bottom, the gutter *fall* px
    lower on the right) or down (right and left, *fall* px further right at the bottom)."""
    h, w = SIZE
    img = np.full((h, w, 3), 255, np.uint8)
    if across:
        a, b = 400, 400 + fall  # the gutter's middle at the left edge and at the right one
        polys = [[(20, 20), (w - 20, 20), (w - 20, b - gap // 2), (20, a - gap // 2)],
                 [(20, a + gap // 2), (w - 20, b + gap // 2), (w - 20, h - 20), (20, h - 20)]]
    else:
        a, b = 300, 300 + fall  # at the top edge and at the bottom one
        polys = [[(a + gap // 2, 20), (w - 20, 20), (w - 20, h - 20), (b + gap // 2, h - 20)],
                 [(20, 20), (a - gap // 2, 20), (b - gap // 2, h - 20), (20, h - 20)]]
    for poly in polys:
        pts = np.array(poly, np.int32)
        cv2.polylines(img, [pts], True, (0, 0, 0), 3)
        (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
        cv2.line(img, (int(x0) + 40, int(y0) + 60), (int(x1) - 60, int(y1) - 60), (170, 170, 170), 5)
    return img, polys


def test_a_slanted_gutter_across_cuts_the_page_and_keeps_its_slant():
    img, _ = slanted()
    found = find_panels(img)
    assert len(found) == 2 and all(p.sides for p in found)
    top, bottom = order_panels(found)
    assert top[1] < bottom[1]
    # their boxes overlap where the gutter slants: which panel a point is in goes by the gutter
    near_right, near_left = (600, 440), (40, 430)  # under the gutter's left end, over its right end
    assert top.holds(*near_right) and not bottom.holds(*near_right)
    assert bottom.holds(*near_left) and not top.holds(*near_left)


def test_regions_by_a_slanted_gutter_go_with_their_panel():
    img, _ = slanted(fall=-70)  # the gutter higher on the right
    in_top = _region(40, 340, 150, 375)  # the top panel's lower left corner
    in_bottom = _region(470, 362, 600, 400)  # the bottom panel's upper right, beside it
    first = _region(450, 60, 560, 160)
    assert order_regions([in_bottom, in_top, first]) == [first, in_bottom, in_top]  # rows: one row, right first
    assert order_on_page(img, (0, 0, SIZE[1], SIZE[0]), [in_bottom, in_top, first]) == [first, in_top, in_bottom]


def test_a_slanted_gutter_down_is_read_right_first_and_mirrors():
    img, _ = slanted(across=False)
    found = find_panels(img)
    assert len(found) == 2 and all(p.sides for p in found)
    right, left = order_panels(found)
    assert right[0] > left[0]
    assert order_panels(found, rtl=False) == [left, right]


def test_level_gutters_give_plain_boxes_in_the_order_of_their_boxes():
    found = find_panels(page(GRID))
    assert near(found, GRID) and not any(p.sides for p in found)
    assert order_panels(found) == order_panels([tuple(p) for p in found])


def test_a_steep_slant_is_no_gutter():
    """Past `MAX_SLANT` (15 degrees) a pale stretch from edge to edge is something drawn, not a gutter."""
    img, _ = slanted(fall=260)
    assert len(find_panels(img)) <= 1


def test_a_slanted_line_with_no_frame_along_it_is_no_gutter():
    """Two letterings in one balloon on a page without frames, the right one lower: the pale line between them crosses
    the outline only, but no frame runs along it, so the page is not cut there and the two keep the rows' order."""
    img = np.full((*SIZE, 3), 255, np.uint8)
    cv2.ellipse(img, (320, 450), (260, 200), 0, 0, 360, (0, 0, 0), 3)
    left, right = _region(200, 300, 230, 470), _region(400, 360, 430, 540)  # lettering, its box its text box
    for r in (left, right):
        img[r.y0:r.y1, r.x0:r.x1] = 0
    found = find_panels(img, ignore=[left.text_box, right.text_box])
    assert not any(p.sides for p in found)
    assert order_on_page(img, (0, 0, SIZE[1], SIZE[0]), [left, right]) == [right, left]
    framed, _ = slanted(fall=-70)  # a slanted gutter between two frames is one
    assert all(p.sides for p in find_panels(framed))


def test_a_sliver_a_slanted_gutter_leaves_is_no_panel():
    from taslation.detect.panels import _Page

    h, w = 200, 300
    paper = np.ones((h, w), bool)
    inside = np.zeros((h, w), bool)
    inside[10:20, 10:290] = True  # ten lines of a piece: less than a panel's height
    inside[10:20, 100:110] = False
    page_ = _Page(np.zeros((720, 500), bool), np.zeros((720, 500), bool))
    out: list = []
    _Page(~paper | ~inside, np.zeros((h, w), bool), inside, (0, 0), page_).split((0, 0, w, h), out)
    assert out == []


def test_the_finder_is_told_the_lettering_not_the_regions(monkeypatch):
    """What lies on a gutter is the lettering: a region's box (a bubble, the layout model's box round one) is wider."""
    from taslation.detect import bubbles

    seen = []
    monkeypatch.setattr(bubbles, "find_panels", lambda image, box, ignore: seen.append(list(ignore)) or [])
    a = TextRegion(100, 100, 300, 200, np.full((100, 200), 255, np.uint8), (150, 120, 250, 180))
    b = TextRegion(400, 100, 600, 200, np.full((100, 200), 255, np.uint8), (450, 120, 550, 180))
    order_on_page(np.zeros((900, 640, 3), np.uint8), (0, 0, 640, 900), [a, b])
    assert seen == [[(150, 120, 250, 180), (450, 120, 550, 180)]]


def test_lettering_on_a_gutter_does_not_hide_it():
    img = page([(20, 20, 620, 440), (20, 460, 620, 880)])
    cv2.ellipse(img, (320, 450), (130, 70), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, (320, 450), (130, 70), 0, 0, 360, (0, 0, 0), 3)
    for x in range(260, 390, 30):  # columns of lettering across the gutter's lines
        cv2.line(img, (x, 410), (x, 490), (0, 0, 0), 4)
    assert len(find_panels(img)) < 2
    assert len(find_panels(img, ignore=[(250, 400, 400, 500)])) == 2


def test_the_regions_read_as_text_are_ordered_among_themselves(settings):
    """After reading: a candidate that is no text (a tall drawing) no longer joins two rows into one."""
    img = np.full((*SIZE, 3), 255, np.uint8)
    right_top, left_top, right_low = _region(400, 100, 480, 140), _region(100, 100, 180, 140), _region(400, 300, 480, 340)
    drawing = _region(250, 90, 300, 400)
    regions = [right_top, left_top, right_low, drawing]
    for r in (right_top, left_top, right_low):
        r.status, r.source_text = "untranslated", "そうだ"
    drawing.status = "ocr-noise"
    assert [r for r in order_regions(list(regions)) if r is not drawing] == [right_top, right_low, left_top]
    pipeline = Pipeline(settings, ocr=None, translator=None)
    pipeline._order_read(img, (0, 0, SIZE[1], SIZE[0]), regions)
    assert regions == [right_top, left_top, right_low, drawing] and [r.order for r in regions] == [0, 1, 2, 3]


def test_a_cached_page_s_translations_are_ordered_among_themselves(settings):
    """A page from the cache: its translations as the regions read as text were, what the cache has nothing for after."""
    img = np.full((*SIZE, 3), 255, np.uint8)
    right_top, left_top, right_low = _region(400, 100, 480, 140), _region(100, 100, 180, 140), _region(400, 300, 480, 340)
    drawing = _region(250, 90, 300, 400)
    for r in (right_top, left_top, right_low):
        r.status, r.translated_text = "translated", "Right."
    drawing.status = "unmatched"
    regions = [drawing, left_top, right_low, right_top]
    Pipeline(settings, ocr=None, translator=None)._order_read(img, (0, 0, SIZE[1], SIZE[0]), regions)
    assert regions == [right_top, left_top, right_low, drawing] and [r.order for r in regions] == [0, 1, 2, 3]


def test_a_fresh_a_completed_and_a_cached_page_come_in_one_order(sample_page, settings):
    from test_partial_pages import Unreliable

    def text_order(res):
        return [r.bbox for r in res.regions if r.status == "translated" or (r.status == "untranslated" and r.source_text)]

    fresh = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).process(sample_page, use_cache=False)
    tr = Unreliable(EN_TEXTS, never=[JA_TEXTS[0]])
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=CacheStore(settings.cache_dir).open("Order", "fake"))
    first = pipeline.process(sample_page)  # one line left without a translation: the page is marked
    tr.never.clear()
    completed = pipeline.process(sample_page)  # that line read again, in its place
    cached = pipeline.process(sample_page)
    assert pipeline.cache.pages and completed.cache_hits == cached.cache_hits == 1
    assert len(text_order(fresh)) == 6
    assert text_order(first) == text_order(completed) == text_order(cached) == text_order(fresh)


def test_a_lone_region_gets_its_panel():
    """One region on a page of panels: the panel it is in is found all the same (it bounds its lettering)."""
    lone = _region(400, 500, 560, 620)
    order_on_page(page(TALL_RIGHT), (0, 0, SIZE[1], SIZE[0]), [lone])
    assert lone.panel is not None and near([lone.panel], [TALL_RIGHT[0]])


def test_the_order_after_reading_keeps_the_readers_hints(settings):
    img = np.full((*SIZE, 3), 255, np.uint8)
    a, b = _region(400, 100, 480, 140), _region(100, 100, 180, 140)
    for r in (a, b):
        r.status, r.source_text = "untranslated", "そうだ"
    b.order_hint = 0
    regions = [a, b]
    Pipeline(settings, ocr=None, translator=None)._order_read(img, (0, 0, SIZE[1], SIZE[0]), regions)
    assert regions == [b, a]


def test_the_pipeline_orders_again_after_reading(sample_page, settings, monkeypatch):
    calls = []
    real = Pipeline._order_read
    monkeypatch.setattr(Pipeline, "_order_read", lambda self, *a: calls.append(len(a[2])) or real(self, *a))
    res = Pipeline(settings, ocr=FakeOcr(), translator=None).process(sample_page, translate=False, use_cache=False)
    assert calls and sum(calls) == len(res.regions)


def test_the_readers_hints_win():
    a, b, c = _region(400, 100, 560, 220), _region(400, 500, 560, 620), _region(60, 60, 200, 160)
    c.order_hint = 0
    assert apply_order_hints(order_on_page(page(TALL_RIGHT), (0, 0, SIZE[1], SIZE[0]), [a, b, c])) == [c, a, b]


def test_a_page_takes_little_time_and_the_old_calls_stay():
    img = np.full((1080, 1920, 3), 255, np.uint8)
    img[0:1080, 0:1920] = cv2.resize(page(GRID), (1920, 1080), interpolation=cv2.INTER_NEAREST)
    best = min(_timed(img) for _ in range(5))
    assert best < 0.03  # about 7 ms; the bound leaves room for a busy machine
    assert order_regions([]) == [] and order_on_page(img, (0, 0, 1920, 1080), []) == []


def _timed(img):
    t0 = time.perf_counter()
    find_panels(img)
    return time.perf_counter() - t0


def test_the_pipeline_orders_by_panel_also_from_the_cache(settings, monkeypatch):
    panels = [(450, 20, 620, 880), (20, 20, 430, 440), (20, 460, 430, 880)]  # off-centre: one page unit, no spread
    img = Image.fromarray(page(panels))
    boxes = [(60, 600, 200, 700), (60, 60, 200, 160), (470, 500, 600, 620), (470, 100, 600, 220)]
    tr = DictTranslator(EN_TEXTS)
    p = Pipeline(settings, ocr=FakeOcr(JA_TEXTS[:4]), translator=tr, cache=CacheStore(settings.cache_dir).open("Panels", "fake"))
    monkeypatch.setattr(p, "_detect", lambda rgb: [_region(*b) for b in boxes])
    wanted = [boxes[3], boxes[2], boxes[1], boxes[0]]
    first = p.process(img)
    assert len(first.units) == 1 and [r.bbox for r in first.regions] == wanted
    again = p.process(img)
    assert again.cache_hits == 1 and all(r.from_cache for r in again.regions)
    assert [r.bbox for r in again.regions] == wanted


# ---------------------------------------------------------------------------------------- the evaluation tool
def test_discordant_pairs():
    assert reading_order_eval.discordant([0, 1, 2]) == (0, 3)
    assert reading_order_eval.discordant([2, 1, 0]) == (3, 3)
    assert reading_order_eval.discordant([0, 2, 1, 3]) == (1, 6)
    assert reading_order_eval.discordant([]) == (0, 0)


def test_the_pipelines_order_is_scored_unit_by_unit():
    right, left = _region(400, 100, 500, 200), _region(100, 100, 200, 200)
    right.unit, left.unit = 0, 1
    rank = {id(right): 0, id(left): 1}
    seqs = reading_order_eval.shipped([right, left], rank, [(0, 0, 300, 900), (300, 0, 640, 900)])
    assert seqs == {"rows": [0, 1], "panels": [0, 1], "gold_panels": [0, 1]}


def test_the_tool_on_a_tiny_dataset(tmp_path, capsys):
    root = tmp_path / "om"
    (root / "images/s/ja").mkdir(parents=True)
    Image.fromarray(page(TALL_RIGHT)).save(root / "images/s/ja/000.png")
    text = [{"x": x, "y": y, "w": 160, "h": 100, "text_ja": "あ", "text_en": "a", "text_zh": "a"}
            for x, y in ((400, 100), (400, 500), (60, 60), (60, 600))]
    frames = [{"x": a, "y": b, "w": c - a, "h": d - b} for a, b, c, d in TALL_RIGHT]
    data = [{"book_title": "s", "pages": [{"page_index": 1, "image_paths": {"ja": "images/s/ja/000.png"},
                                           "frame": frames, "text": text}]}]
    (root / "annotation.json").write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "numbers.json"
    assert reading_order_eval.main(["--root", str(root), "--no-pipeline", "--out", str(out)]) == 0
    numbers = json.loads(out.read_text(encoding="utf-8"))["gold boxes"]["all"]
    assert numbers["pages"] == 1 and numbers["right"] == {"rows": 0, "panels": 1, "gold_panels": 1}
    assert "recall 100.0 %, precision 100.0 %" in capsys.readouterr().out


REAL = openmantra.DEFAULT_ROOT
real_data = pytest.mark.skipif(not (REAL / "annotation.json").is_file() or os.environ.get("TASLATION_REALDATA") != "1",
                               reason="the OpenMantra dataset is not fetched, or TASLATION_REALDATA is not 1")


@real_data
def test_on_real_pages_the_panels_beat_the_rows_and_hardly_ever_lose():
    right_rows = right_panels = worse = pages = 0
    for p in openmantra.load():
        if len(p.bubbles) < 2:
            continue
        regions = [reading_order_eval.as_region(b.box) for b in p.bubbles]
        rank = {id(r): i for i, r in enumerate(regions)}
        panels = find_panels(np.asarray(p.open()), ignore=[b.box for b in p.bubbles])
        before = reading_order_eval.discordant([rank[id(r)] for r in order_regions(list(regions))])[0]
        after = reading_order_eval.discordant([rank[id(r)] for r in order_regions(list(regions), panels=panels)])[0]
        pages += 1
        right_rows += before == 0
        right_panels += after == 0
        worse += after > before
    assert pages == 199
    assert right_panels >= right_rows + 25 and worse <= 2
