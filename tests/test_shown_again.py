"""A page from the cache shown again this session comes back from memory (`render.memo`), never with stale text."""
from __future__ import annotations

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.render import typeset
from taslation.render.memo import ErasedRegions, ShownPages, changed_pixels
from taslation.translate import DictTranslator


def _framed(page: Image.Image, size=(1400, 1000), ground=(0x2B, 0x2B, 0x2B)) -> Image.Image:
    """*page* on a full-screen viewer's dark ground, as a capture shows it."""
    out = Image.new("RGB", size, ground)
    scale = min(size[0] / page.width, size[1] / page.height)
    shown = page.resize((int(page.width * scale), int(page.height * scale)), Image.LANCZOS)
    out.paste(shown, ((size[0] - shown.width) // 2, (size[1] - shown.height) // 2))
    return out


@pytest.fixture
def cached(sample_page, settings):
    """A pipeline whose cache holds *sample_page* (translated once), and a fresh capture of that page."""
    cache = CacheStore(settings.cache_dir).open("Test Book", "fake")
    ocr, tr = FakeOcr(), DictTranslator(EN_TEXTS)
    pipeline = Pipeline(settings, ocr=ocr, translator=tr, cache=cache)
    first = pipeline.process(sample_page.copy())
    assert first.cache_misses == 1 and first.translated
    return pipeline, ocr, tr


def _count_detection(pipeline, monkeypatch) -> list[int]:
    calls = []
    real = pipeline._detect

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(pipeline, "_detect", counted)
    return calls


def test_a_page_shown_again_comes_from_memory_exactly_as_lettered(cached, sample_page, monkeypatch):
    pipeline, ocr, tr = cached
    detected = _count_detection(pipeline, monkeypatch)
    a = pipeline.process(sample_page.copy())  # from the cache: lettered, and kept
    assert len(detected) == 1 and len(pipeline.shown_pages) == 1
    calls = (ocr.calls, len(tr.calls))
    b = pipeline.process(Image.fromarray(np.asarray(sample_page).copy()))  # a new capture, the same pixels
    assert len(detected) == 1  # no detection, no OCR, no model
    assert (ocr.calls, len(tr.calls)) == calls
    assert np.array_equal(np.asarray(a.image), np.asarray(b.image))
    assert [(r.bbox, r.translated_text, r.status, r.font_size) for r in a.regions] == \
        [(r.bbox, r.translated_text, r.status, r.font_size) for r in b.regions]
    assert b.cache_hits == a.cache_hits and b.fingerprints == a.fingerprints
    assert "shown before" in b.timings
    b.regions[0].translated_text = "changed by the reader's window"  # the copy handed out is the caller's own
    b.regions[0].mask[:] = 0
    c = pipeline.process(sample_page.copy())
    assert c.regions[0].translated_text == a.regions[0].translated_text
    assert c.regions[0].mask.any()


def test_a_changed_translation_is_never_shown_stale(cached, sample_page, monkeypatch):
    pipeline, _ocr, _tr = cached
    a = pipeline.process(sample_page.copy())
    shown = np.asarray(a.image).copy()
    region = a.translated[0]
    assert pipeline.set_translation(a, region, "A brand new line.")  # (the page on show is lettered again)
    detected = _count_detection(pipeline, monkeypatch)
    b = pipeline.process(sample_page.copy())
    assert len(detected) == 1  # lettered from scratch
    assert "A brand new line." in [r.translated_text for r in b.regions]
    assert not np.array_equal(shown, np.asarray(b.image))
    assert np.array_equal(np.asarray(a.image), np.asarray(b.image))
    c = pipeline.process(sample_page.copy())  # and that one is kept in its turn
    assert len(detected) == 1 and np.array_equal(np.asarray(b.image), np.asarray(c.image))


def test_another_pixel_another_setting_or_translator_mode_letters_the_page_again(cached, sample_page, monkeypatch):
    pipeline, _ocr, _tr = cached
    pipeline.process(sample_page.copy())
    detected = _count_detection(pipeline, monkeypatch)
    touched = np.asarray(sample_page).copy()
    touched[5, 5] = (touched[5, 5].astype(int) + 40) % 256  # one pixel of the capture area
    pipeline.process(Image.fromarray(touched))
    assert len(detected) == 1
    pipeline.process(sample_page.copy(), complete=True)  # translator mode adds to the page: never from memory
    assert len(detected) == 2
    pipeline._base_settings.max_font_size -= 4  # the lettering's settings
    pipeline.process(sample_page.copy())
    assert len(detected) == 3
    pipeline.process(sample_page.copy())
    assert len(detected) == 3


def test_pixels_outside_the_capture_area_do_not_count_but_show_as_they_are(sample_page, settings, monkeypatch):
    frame = _framed(sample_page)
    settings.margins = (0, 0, 0, 40)  # a bar at the bottom of the viewer is left out
    cache = CacheStore(settings.cache_dir).open("Framed Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    pipeline.process(frame.copy())
    a = pipeline.process(frame.copy())
    detected = _count_detection(pipeline, monkeypatch)
    moved = np.asarray(frame).copy()
    moved[-20:, :200] = 200  # the viewer's bar changed (a page counter, the pointer)
    b = pipeline.process(Image.fromarray(moved))
    assert detected == []
    assert np.array_equal(np.asarray(b.image)[-20:, :200], moved[-20:, :200])
    assert np.array_equal(np.asarray(b.image)[:-40], np.asarray(a.image)[:-40])
    assert b.original is not a.original


def test_an_erase_done_live_is_taken_again_where_the_page_changed_elsewhere(cached, sample_page, monkeypatch):
    pipeline, _ocr, _tr = cached
    a = pipeline.process(sample_page.copy())
    assert len(pipeline.erased_regions) >= len(a.translated)
    erases = []
    real = pipeline._erase
    monkeypatch.setattr(pipeline, "_erase", lambda *x, **k: erases.append(1) or real(*x, **k))
    touched = np.asarray(sample_page).copy()
    far = max(a.translated, key=lambda r: r.y0)  # a pixel in the region lowest on the page changes
    cy, cx = (far.y0 + far.y1) // 2, (far.x0 + far.x1) // 2
    touched[cy, cx] = 255 - touched[cy, cx]
    reused = pipeline.erased_regions.reused
    b = pipeline.process(Image.fromarray(touched))
    assert len(erases) >= 1  # the region that changed is erased again ...
    assert pipeline.erased_regions.reused - reused == len(b.translated) - len(erases)  # ... the others are not
    fresh = Pipeline(pipeline._base_settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=pipeline.cache)
    c = fresh.process(Image.fromarray(touched))  # the same page lettered from scratch, nothing in memory
    assert np.array_equal(np.asarray(b.image), np.asarray(c.image))


def test_a_cached_page_waiting_for_the_inpainting_is_sent_early_then_finished(cached, sample_page, monkeypatch):
    pipeline, _ocr, _tr = cached
    events = []
    monkeypatch.setattr(pipeline, "_erases_on_art", lambda page, regions: True)
    res = pipeline.process(sample_page.copy(), events=lambda kind, data: events.append((kind, data)))
    kinds = [(k, bool(d.get("early"))) for k, d in events]
    assert kinds == [("regions", False), ("page", True), ("page", False)]
    assert events[0][1]["boxes"] == [] and events[0][1]["size"] == sample_page.size
    assert events[2][1]["image"] is res.image
    assert all(r.translated_text for r in res.translated)  # the early look changed nothing of the regions
    monkeypatch.setattr(pipeline, "_erases_on_art", lambda page, regions: False)
    events.clear()
    pipeline.shown_pages.clear()
    pipeline.process(sample_page.copy(), events=lambda kind, data: events.append((kind, data)))
    assert [k for k, _d in events] == ["page"]  # nothing waits: the finished page alone, as before


def test_an_early_look_only_for_pages_without_the_inpainting_held(cached, sample_page, monkeypatch):
    from taslation.render import artwork

    pipeline, _ocr, _tr = cached

    class Eraser:  # an inpainting model that is there (and erases as the paper fill does)
        failed = False
        setting = "auto"

        def erase(self, image, region, *args):
            return Pipeline._paper_erase(image, region, *args)
    monkeypatch.setattr(pipeline, "art_eraser", Eraser())
    monkeypatch.setattr(artwork, "on_art", lambda page, region: True)
    res = pipeline.process(sample_page.copy())
    rgb = np.asarray(sample_page)
    assert not pipeline._erases_on_art(rgb, res.regions)  # this session's erases hold every region
    pipeline.erased_regions.clear()
    assert pipeline._erases_on_art(rgb, res.regions)
    monkeypatch.setattr(artwork, "on_art", lambda page, region: False)
    assert not pipeline._erases_on_art(rgb, res.regions)  # on paper: the paper fill is quick anyway


def test_the_memories_keep_within_their_budgets():
    pages = ShownPages(budget=500_000)
    original = np.zeros((500, 500, 3), np.uint8)
    for i in range(5):
        lettered = original.copy()
        lettered[: 50 * (i + 1), :500] = 255
        pages.put(bytes([i]), original, lettered, [], [], None)
    assert 1 <= len(pages) < 5 and pages.get(bytes([4])) is not None and pages.get(bytes([0])) is None
    _regions, kept = pages.get(bytes([4]))
    assert (kept.lay_over(original)[..., 0] == np.where(np.arange(500)[:, None] < 250, 255, 0)).all()
    assert ErasedRegions(budget=10).budget == 10


def test_changed_pixels_finds_the_box_and_mask_of_any_channel():
    a = np.zeros((40, 60, 3), np.uint8)
    b = a.copy()
    assert changed_pixels(a, b) == ((0, 0, 0, 0), None)
    b[10, 20, 2] = 1  # one level of one channel
    b[15, 30] = 9
    box, mask = changed_pixels(a, b)
    assert box == (20, 10, 31, 16) and mask.sum() == 2 and mask[0, 0] and mask[5, 10]


def _forget_layouts() -> None:
    with typeset._LAYOUTS_LOCK:
        typeset._LAYOUTS.clear()


def test_a_layout_is_made_once_for_the_same_text_in_the_same_shape(monkeypatch):
    _forget_layouts()
    made = []
    real = typeset._layout_text
    monkeypatch.setattr(typeset, "_layout_text", lambda *a, **k: made.append(1) or real(*a, **k))
    mask = np.zeros((120, 160), np.uint8)
    mask[10:110, 10:150] = 255
    a = typeset.layout_text(mask, "Where are you going?", None, 9, 40)
    b = typeset.layout_text(mask.copy(), "Where are you going?", None, 9, 40)
    assert b is a and len(made) == 1
    typeset.layout_text(mask, "Where are you going?", None, 9, 30)  # another size limit
    other = mask.copy()
    other[50, 50] = 0
    typeset.layout_text(other, "Where are you going?", None, 9, 40)  # another shape
    assert len(made) == 3
    monkeypatch.setattr(typeset, "SHAPE_PAD", typeset.SHAPE_PAD * 2)  # a setting of the module
    typeset.layout_text(mask, "Where are you going?", None, 9, 40)
    assert len(made) == 4
    _forget_layouts()


def test_the_classical_detectors_beside_the_layout_model_find_the_same(sample_page, settings, monkeypatch):
    pipeline = Pipeline(settings)

    class Layout:  # a layout model that finds nothing (the classical regions stand alone)
        failed = False

        def boxes(self, rgb, units):
            return []
    settings.detect_model = "on"
    monkeypatch.setattr(pipeline, "layout", Layout())
    rgb = np.asarray(sample_page)
    alone = pipeline._detect(rgb)
    beside = pipeline._detect(rgb, parallel=True)
    assert [(r.bbox, r.kind) for r in alone] == [(r.bbox, r.kind) for r in beside] and alone


def test_a_page_on_show_detects_beside_the_layout_model_and_a_stand_in_detect_still_works(sample_page, settings,
                                                                                           monkeypatch):
    from taslation import pipeline as pipeline_mod

    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))

    class Layout:
        failed = False

        def boxes(self, rgb, units):
            return []
    settings.detect_model = "on"
    monkeypatch.setattr(pipeline, "layout", Layout())
    submitted = []
    pool = pipeline_mod._detect_pool()
    monkeypatch.setattr(pipeline_mod, "_detect_pool", lambda: submitted.append(1) or pool)
    pipeline.process(sample_page.copy(), use_cache=False)
    assert submitted == [1]
    pipeline.scan(sample_page.copy(), skip_cached=False)  # the batch's reading: on its own thread alone
    assert submitted == [1]
    monkeypatch.setattr(pipeline, "_detect", lambda rgb: [])  # a stand-in of one argument, as tests use
    assert pipeline.process(sample_page.copy(), use_cache=False).regions == []
