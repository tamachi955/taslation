"""Every text region belongs to a page unit (`pipeline.unit_for`): a unit cut short of its page (analyze stopping
at black panels it could not see as paper) loses none of the page's text, a rectangle of the reader's stays with
the unit it was stored under, and only what lies outside the capture area is left out. The page units and the
detection are stand-ins on a drawn capture: what is tested is what the pipeline does with them."""

from __future__ import annotations

import numpy as np
from helpers import EN_TEXTS, FakeOcr
from PIL import Image, ImageDraw

from taslation import fingerprint
from taslation.annotations import AnnotationStore, BookAnnotations
from taslation.cache import CacheStore
from taslation.detect import DetectorConfig
from taslation.fingerprint import PageUnit
from taslation.pipeline import Pipeline, unit_for
from taslation.regions import TextRegion
from taslation.translate import DictTranslator

RIGHT, LEFT = (460, 60, 860, 660), (60, 60, 460, 660)  # a spread's pages in the capture
SHORT = (460, 60, 860, 360)  # the right page's unit, cut where the black panels of its lower half begin
ABOVE = (520, 120, 640, 290)  # a bubble within the short unit
BELOW = (680, 375, 800, 500)  # a bubble in the black panels, outside the short unit (y 1.05-1.47 in its terms)
FP_RIGHT, FP_LEFT = "3c" * 40, "a5" * 40


def _capture() -> Image.Image:
    """The two pages on a black viewer, the right one white in its upper half only; a bubble with its own column
    of strokes at ABOVE and BELOW (so the OCR's memo tells them apart) and on the left page."""
    img = Image.new("RGB", (920, 720), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((LEFT[0], LEFT[1], LEFT[2] - 1, LEFT[3] - 1), fill=(255, 255, 255))
    d.rectangle((SHORT[0], SHORT[1], SHORT[2] - 1, SHORT[3] - 1), fill=(255, 255, 255))
    for n, box in enumerate((ABOVE, BELOW, (140, 400, 260, 570))):
        d.ellipse(box, fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        cx = (box[0] + box[2]) // 2
        for k in range(2 + n):
            d.line((cx - 10, box[1] + 40 + 28 * k, cx + 10, box[1] + 52 + 28 * k), fill=(0, 0, 0), width=3)
    return img


class StandInDetector:
    """Finds the bubbles at *boxes* (capture coordinates; the capture area starts at *origin*)."""

    def __init__(self, boxes, origin=(0, 0)):
        self.cfg = DetectorConfig()
        self.boxes, self.origin = list(boxes), origin

    def detect(self, image, inverted=False):
        if inverted:
            return []
        ox, oy = self.origin
        out = []
        for x0, y0, x1, y1 in self.boxes:
            x0, y0, x1, y1 = x0 - ox, y0 - oy, x1 - ox, y1 - oy
            ix, iy = min(20, (x1 - x0) // 4), min(25, (y1 - y0) // 4)  # the lettering inside the bubble
            out.append(TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8),
                                  text_box=(x0 + ix, y0 + iy, x1 - ix, y1 - iy)))
        return out


def _units(*units: PageUnit):
    return lambda rgb, margins=(0, 0, 0, 0), **_found_as: [PageUnit(u.box, u.fingerprint, u.index) for u in units]


def _pipeline(settings, monkeypatch, units, boxes=(ABOVE, BELOW), cache=None, annotations=None, margins=(0, 0, 0, 0)):
    settings.detect_dark_bubbles = settings.detect_text_blocks = False
    settings.margins = margins
    monkeypatch.setattr(fingerprint, "analyze", _units(*units))
    tr = DictTranslator(EN_TEXTS, default="ok")
    return Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache, annotations=annotations,
                    detector=StandInDetector(boxes, margins[:2])), tr


def test_a_region_below_a_unit_cut_short_is_read_translated_and_cached_under_it(settings, monkeypatch):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, tr = _pipeline(settings, monkeypatch, [PageUnit(SHORT, FP_RIGHT, 0)], cache=cache)
    res = pipeline.process(_capture())
    assert sorted(r.bbox for r in res.translated) == [ABOVE, BELOW] and {r.unit for r in res.regions} == {0}
    assert len(tr.calls) == 1 and len(tr.calls[0]) == 2  # both lines go to the model, as one page
    (page,) = cache.pages
    assert sorted(b.box[1] > 1 for b in page.bubbles) == [False, True]  # the lower one below its unit's box
    again = pipeline.process(_capture())  # from the cache: the bubble below is matched to its region again
    assert again.cache_hits == 1 and sorted(r.bbox for r in again.translated) == [ABOVE, BELOW]
    assert all(r.from_cache for r in again.translated) and len(tr.calls) == 1


def test_the_batch_scan_keeps_a_region_below_a_unit_cut_short(settings, monkeypatch):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline, _tr = _pipeline(settings, monkeypatch, [PageUnit(SHORT, FP_RIGHT, 0)], cache=cache)
    (unit,) = pipeline.scan(_capture()).units
    assert sorted(r.bbox for r in unit.japanese()) == [ABOVE, BELOW]
    assert pipeline.commit_unit(unit, {i: EN_TEXTS.get(r.source_text, "ok") for i, r in enumerate(unit.japanese())})
    assert len(cache.pages) == 1 and len(cache.pages[0].bubbles) == 2
    res = pipeline.process(_capture())
    assert res.cache_hits == 1 and len(res.translated) == 2 and all(r.from_cache for r in res.translated)
    assert pipeline.scan(_capture()).units[0].cached  # scanned again: nothing left to translate


def test_a_region_outside_the_capture_area_is_still_left_out(settings, monkeypatch):
    header = (500, 4, 820, 34)  # the viewer's own lettering above the capture area
    pipeline, _tr = _pipeline(settings, monkeypatch, [PageUnit(SHORT, FP_RIGHT, 0)], boxes=(ABOVE, BELOW, header),
                              margins=(0, 40, 0, 0))
    res = pipeline.process(_capture())
    assert sorted(r.bbox for r in res.regions) == [ABOVE, BELOW]
    units = [PageUnit(SHORT, FP_RIGHT, 0), PageUnit(LEFT, FP_LEFT, 1)]
    capture = (0, 40, 920, 720)
    assert unit_for(units, header, capture) is None and unit_for(units, header) is units[0]
    assert unit_for(units, BELOW, capture) is units[0]  # the columns of the unit cut short
    assert unit_for(units, (455, 400, 463, 420), capture) is units[1]  # in the gutter: the nearer unit (the left)
    assert unit_for(units, (880, 300, 910, 330), capture) is units[0]  # beside the spread: the nearer unit
    assert unit_for(units, ABOVE, capture, named=1) is units[1] and unit_for([], ABOVE) is None


def test_a_reader_rectangle_below_a_unit_cut_short_is_stored_under_it_and_comes_back(settings, monkeypatch):
    """The spread's left unit is cut short this time: a rectangle drawn below it is that unit's, not the right
    page's (the first unit, which took every rectangle no unit held); the premises file keeps it, and the next
    reading reads and translates it as a region of that unit."""
    left_short = (60, 60, 460, 420)
    units = [PageUnit(RIGHT, FP_RIGHT, 0), PageUnit(left_short, FP_LEFT, 1)]
    store = AnnotationStore(settings.annotations_dir)
    pipeline, _tr = _pipeline(settings, monkeypatch, units, boxes=(ABOVE,), annotations=store.open("Book"))
    drawn = (140, 430, 260, 560)
    assert pipeline.add_region(pipeline.process(_capture()), drawn)
    reopened = store.open("Book")
    (page,) = reopened.pages
    assert page.fingerprint == FP_LEFT and len(page.add) == 1 and 1 < page.add[0][1] < page.add[0][3] < 1.5
    pipeline.set_annotations(reopened)
    again = pipeline.process(_capture())
    (manual,) = [r for r in again.regions if r.kind.startswith("manual")]
    assert manual.bbox == drawn and manual.unit == 1 and manual.status == "translated"
    assert [r.bbox for r in again.regions if r.unit == 0] == [ABOVE]


def test_a_rectangle_moved_below_the_other_pages_unit_goes_to_that_page(settings, monkeypatch):
    left_short = (60, 60, 460, 420)
    units = [PageUnit(RIGHT, FP_RIGHT, 0), PageUnit(left_short, FP_LEFT, 1)]
    pipeline, _tr = _pipeline(settings, monkeypatch, units, boxes=(ABOVE,),
                              annotations=AnnotationStore(settings.annotations_dir).open("Book"))
    res = pipeline.process(_capture())
    (region,) = res.regions
    assert region.unit == 0 and pipeline.move_region(res, region, (140, 430, 260, 560))
    assert region.unit == 1 and pipeline.annotations.lookup(FP_LEFT, units[1].aspect, 0).add[0][1] > 1


def test_a_skipped_page_and_the_readers_facts_reach_the_regions_below_its_unit(settings, monkeypatch):
    """The page's premises are matched to its regions wherever its unit's box ends: what the reader said of the
    bubble below the unit reaches it, and a page marked as skipped has none of its regions read."""
    annotations = BookAnnotations(settings.state_dir / "ann.json", "Book")
    unit = PageUnit(SHORT, FP_RIGHT, 0)
    annotations.page(FP_RIGHT, unit.aspect).set_note(unit.normalize(BELOW), speaker="ピヨ", kind="shout")
    pipeline, _tr = _pipeline(settings, monkeypatch, [unit], annotations=annotations)
    res = pipeline.process(_capture())
    below = next(r for r in res.regions if r.bbox == BELOW)
    assert below.speaker == "ピヨ" and below.tag == "shout"
    annotations.page(FP_RIGHT, unit.aspect).skip = True
    assert pipeline.process(_capture()).regions == []
