"""A spread on show in the window reads its next page unit while the one before it is translated (`pipeline.ReadBeside`,
`SPREAD_READ`). None of it changes anything: what the page tells (the progress, the regions read, the drafts, the
finished page) comes in the order it came with the unit read in its turn, the regions, the cache and the book's sizes
are what they were, and the drafts of the first unit letter at the book's sizes as they were before the second was
read. Stop, an error of the reading and a unit before it that fails end it as they ended the reading in its turn."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation import pipeline as pipeline_mod
from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.ocr.charspot import CharspotChar, CharspotReading
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

BESIDE = "taslation-read-beside"


def _spread(right: Image.Image, left: Image.Image) -> Image.Image:
    w, h = right.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(left, (0, 20))
    spread.paste(right, (w + 60, 20))
    return spread


class SlowOcr(FakeOcr):
    """Reads a moment per crop and keeps on which thread and when each read was."""

    def __init__(self, texts=None, seconds=0.01, fail_after=None):
        super().__init__(texts)
        self.seconds, self.fail_after = seconds, fail_after
        self.reads: list[tuple[str, float]] = []

    def read(self, image):
        time.sleep(self.seconds)
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise RuntimeError("the reader broke (test)")
        self.reads.append((threading.current_thread().name, time.monotonic()))
        return super().read(image)


class SizedOcr(SlowOcr):
    """`SlowOcr` with the characters' boxes, sized by the crop: each region read gives the book's sizes a sample."""

    def read_chars(self, image):
        text = self.read(image)
        size = 14.0 + image.width % 13
        return CharspotReading(text, tuple(CharspotChar(ch, (0.0, 0.0, size, size), 0.95) for ch in text), 0.95)


class Writing(DictTranslator):
    """Hands each line over as it is written, a moment apart, and keeps when each page's request began and ended and
    the book's sizes it saw at its end."""

    def __init__(self, mapping, pipeline_ref, seconds=0.05, fail=None):
        super().__init__(mapping)
        self.seconds, self.ref, self.fail = seconds, pipeline_ref, fail
        self.spans: list[tuple[float, float]] = []
        self.sizes: list[list[float]] = []

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None):
        began = time.monotonic()
        out = super().translate_page(texts, context, notes, upcoming, meta, cancel=cancel)
        for i, text in enumerate(out):
            time.sleep(self.seconds)
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if on_item is not None:
                on_item(i, text)
        if self.fail is not None and not self.spans:
            raise self.fail
        self.sizes.append(list(self.ref[0]._book_sizes))
        self.spans.append((began, time.monotonic()))
        return out


def _run(settings, page, book, *, spread_read=True, window=True, cancel=None, ocr=None, **writing):
    """The page read and translated as the window's page job reads it (*window*), the next unit read beside or in its
    turn: what it told (events and progress, in one list), the result, the pipeline, the translator."""
    told: list[tuple] = []
    old = pipeline_mod.SPREAD_READ
    pipeline_mod.SPREAD_READ = spread_read
    ref: list = []
    try:
        cache = CacheStore(settings.cache_dir).open(book, "fake")
        tr = Writing(EN_TEXTS, ref, **writing)
        p = Pipeline(settings, ocr=ocr or SlowOcr(), translator=tr, cache=cache)
        p._add_sizes([21.0, 23.0])  # (pages before this one)
        ref.append(p)
        kwargs = dict(events=lambda kind, data: told.append(("event", kind, dict(data))),
                      progress=lambda m: told.append(("progress", m.code, repr(sorted(m.params.items())))),
                      cancel=cancel if cancel is not None else threading.Event())
        if window:
            with p.page_on_show():
                result = p.process(page.copy(), **kwargs)
        else:
            result = p.process(page.copy(), **kwargs)
    finally:
        pipeline_mod.SPREAD_READ = old
    return told, result, p, tr


def _told(told) -> list:
    out = []
    for item in told:
        if item[0] == "event":
            _e, kind, data = item
            if kind == "translated":
                out.append((kind, data["index"], data["text"], data["box"], np.asarray(data["patch"]).tobytes()))
            elif kind == "page":
                out.append((kind, np.asarray(data["image"]).tobytes()))
            else:
                out.append((kind, repr(sorted(data.items()))))
        else:
            out.append(item)
    return out


def _kept(result, p) -> list:
    regions = [(r.bbox, r.status, r.source_text, r.translated_text, r.room, r.size_cap, r.font_size,
                tuple(r.letter_flags), np.asarray(r.mask).tobytes(), tuple(r.flags), r.unit, r.order)
               for r in result.regions]
    pages = [(c.fingerprint, c.seq, c.incomplete, [(b.box, b.text, b.poly, b.flags) for b in c.bubbles])
             for c in p.cache.pages]
    return [regions, pages, np.asarray(result.image).tobytes(), list(p._book_sizes)]


def _no_reading_beside() -> bool:
    return not any(t.name == BESIDE and t.is_alive() for t in threading.enumerate())


@pytest.mark.parametrize("sized", [False, True])
def test_the_next_unit_is_read_while_the_first_is_translated_and_all_is_as_ever(sized, settings, sample_page,
                                                                                 sample_page2):
    page = _spread(sample_page, sample_page2)
    reader = SizedOcr if sized else SlowOcr
    before = _run(settings, page, "In turn", spread_read=False, ocr=reader())
    after = _run(settings, page, "Beside", ocr=reader())
    assert _told(after[0]) == _told(before[0])
    assert _kept(after[1], after[2]) == _kept(before[1], before[2])
    assert len(after[1].units) == 2 and after[1].cache_misses == 2
    # it was read beside: on its own thread, while the first unit was translated
    reads, (first, _second) = after[2].ocr.reads, after[3].spans
    beside = [t for name, t in reads if name == BESIDE]
    assert beside and beside[0] < first[1]
    assert not any(name == BESIDE for name, _t in before[2].ocr.reads)
    # the first unit's translation saw the book's sizes without the second's samples, as it did in its turn
    assert after[3].sizes[0] == before[3].sizes[0] and after[3].sizes[1] == before[3].sizes[1]
    if sized:
        assert len(after[3].sizes[1]) > len(after[3].sizes[0]) > 2
    assert _no_reading_beside()


def test_the_analysis_log_times_each_unit_s_reading_its_wait_and_its_translation_from_the_page_s_start(
        settings, sample_page, sample_page2, tmp_path):
    """The page's line keeps each unit's reading (the second's read beside, on its own thread, while the first is
    translated), the wait for it and each unit's translation, in ms from the page's start; read in its turn, the
    second's reading comes after the first's translation and is not beside."""
    from taslation import analysis

    page = _spread(sample_page, sample_page2)
    analysis.start(tmp_path / "beside", "on")
    try:
        _run(settings, page, "Timed beside", ocr=SlowOcr(seconds=0.03))
        (line,) = [ln for ln in analysis.records() if ln.get("type") == "page"]
    finally:
        analysis.stop()
    units = {u["unit"]: u for u in line["read_units"]}
    assert sorted(units) == [0, 1] and not units[0]["beside"] and units[1]["beside"]
    zero, one = units[0], units[1]
    assert zero["read_end_ms"] <= zero["translate_start_ms"]
    assert one["read_start_ms"] < zero["translate_end_ms"]  # (read while the first was translated)
    assert zero["translate_end_ms"] <= one["wait_start_ms"] <= one["wait_end_ms"] <= one["translate_start_ms"]
    assert one["read_ms"] > 0 and zero["read_ms"] > 0
    analysis.start(tmp_path / "in turn", "on")
    try:
        _run(settings, page, "Timed in turn", spread_read=False, ocr=SlowOcr(seconds=0.03))
        (line,) = [ln for ln in analysis.records() if ln.get("type") == "page"]
    finally:
        analysis.stop()
    units = {u["unit"]: u for u in line["read_units"]}
    assert not units[1]["beside"]
    assert units[1]["read_start_ms"] >= units[0]["translate_end_ms"] and "wait_start_ms" not in units[1]


def test_a_page_of_one_unit_and_a_page_outside_the_window_read_nothing_beside(settings, sample_page, sample_page2):
    one = _run(settings, sample_page, "One")
    assert not any(name == BESIDE for name, _t in one[2].ocr.reads)
    page = _spread(sample_page, sample_page2)
    outside = _run(settings, page, "Outside", window=False)
    assert not any(name == BESIDE for name, _t in outside[2].ocr.reads)
    inside = _run(settings, page, "Inside", spread_read=False)
    assert _kept(outside[1], outside[2]) == _kept(inside[1], inside[2])


def test_stop_while_the_next_unit_is_read_ends_both(settings, sample_page, sample_page2):
    page = _spread(sample_page, sample_page2)
    cancel = threading.Event()
    ocr = SlowOcr(seconds=0.05)
    threading.Timer(0.8, cancel.set).start()
    told: list = []
    with pytest.raises(Cancelled):
        try:
            _run(settings, page, "Stopped", cancel=cancel, ocr=ocr, seconds=0.4)
        finally:
            told.extend(ocr.reads)
    assert _no_reading_beside()
    stopped_at = time.monotonic()
    time.sleep(0.2)
    assert all(t < stopped_at for _name, t in ocr.reads)  # nothing read after the stop
    cache = CacheStore(settings.cache_dir).open("Stopped", "fake")
    assert len(cache) == 0


def test_stop_reaches_the_reading_beside(settings, sample_page, sample_page2):
    """The page stopped while the first unit's request is sent and the next unit read: Stop raised, the reading
    stops between its regions and tells nothing."""
    page = _spread(sample_page, sample_page2)
    cancel = threading.Event()
    ocr = SlowOcr(seconds=0.08)

    class Stopping(Writing):
        def translate_page(self, texts, *a, cancel=None, **k):
            deadline = time.monotonic() + 3.0
            while not any(name == BESIDE for name, _t in ocr.reads) and time.monotonic() < deadline:
                time.sleep(0.01)
            cancel.set()
            raise Cancelled()

    ref: list = []
    told: list = []
    cache = CacheStore(settings.cache_dir).open("Stopped beside", "fake")
    p = Pipeline(settings, ocr=ocr, translator=Stopping(EN_TEXTS, ref), cache=cache)
    with pytest.raises(Cancelled):
        with p.page_on_show():
            p.process(page.copy(), cancel=cancel, events=lambda kind, data: told.append((kind, dict(data))))
    assert _no_reading_beside()
    assert any(name == BESIDE for name, _t in ocr.reads)  # it was reading
    # what was read beside was not told: only the first unit's regions were said read (those told before the first
    # unit's first draft, the unit read in its turn)
    in_turn = _run(settings, page, "First alone", spread_read=False)
    events = [(x[1], x[2]) for x in in_turn[0] if x[0] == "event"]
    first_draft = next(i for i, (kind, _d) in enumerate(events) if kind == "translated")
    first_unit = {d["index"] for kind, d in events[:first_draft] if kind == "read"}
    second_unit = {d["index"] for kind, d in events[first_draft:] if kind == "read"}
    read_indices = {d["index"] for kind, d in told if kind == "read"}
    assert read_indices and read_indices <= first_unit and second_unit and not read_indices & second_unit
    assert len(cache) == 0


def test_an_error_of_the_reading_beside_comes_in_its_turn(settings, sample_page, sample_page2):
    page = _spread(sample_page, sample_page2)
    first = _run(settings, page, "Count", spread_read=False)
    reads_of_first = sum(1 for _name, t in first[2].ocr.reads if t < first[3].spans[0][0])
    outcomes = []
    for spread_read in (False, True):
        ocr = SlowOcr(fail_after=reads_of_first + 1)  # (the second unit's second reading)
        book = f"Broken {spread_read}"
        with pytest.raises(RuntimeError, match="broke"):
            _run(settings, page, book, spread_read=spread_read, ocr=ocr)
        cache = CacheStore(settings.cache_dir).open(book, "fake")
        outcomes.append([(c.fingerprint, [(b.box, b.text, b.poly) for b in c.bubbles]) for c in cache.pages])
        assert any(name == BESIDE for name, _t in ocr.reads) == spread_read
    assert outcomes[0] == outcomes[1] and len(outcomes[0]) == 1  # the first unit stored, either way
    assert _no_reading_beside()


def test_a_first_unit_that_fails_ends_the_reading_beside(settings, sample_page, sample_page2, monkeypatch):
    page = _spread(sample_page, sample_page2)
    real = Pipeline._store_regions

    def broken(self, unit, regions):
        raise OSError("the disk is full (test)")

    monkeypatch.setattr(Pipeline, "_store_regions", broken)
    ocr = SlowOcr(seconds=0.05)
    with pytest.raises(OSError):
        _run(settings, page, "Failed", ocr=ocr)
    assert _no_reading_beside()
    stopped_at = time.monotonic()
    time.sleep(0.2)
    assert all(t < stopped_at for _name, t in ocr.reads)
    monkeypatch.setattr(Pipeline, "_store_regions", real)
