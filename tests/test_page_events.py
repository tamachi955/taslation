"""How a page fills in while it is translated: the pipeline's page events (regions, read, translated, page)."""
from __future__ import annotations

import numpy as np
from helpers import EN_TEXTS, FakeOcr

from taslation.cache import CacheStore
from taslation.pipeline import PageFill, Pipeline, takes_items
from taslation.regions import TextRegion
from taslation.translate import DictTranslator

LONG = "I honestly cannot believe that you would go and do something like this to me of all people."


class Events:
    """Records the page events in the order they come."""

    def __init__(self, log=None):
        self.events: list[tuple[str, dict]] = []
        self.log = log

    def __call__(self, kind, data):
        self.events.append((kind, dict(data)))
        if self.log is not None and kind == "translated":
            self.log.append(("lettered", data["index"]))

    def kinds(self):
        return [k for k, _d in self.events]

    def of(self, kind):
        return [d for k, d in self.events if k == kind]


def _region(x0, y0, x1, y1, text_box):
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box, status="untranslated",
                      source_text="こんにちは")


def test_the_page_fills_in_region_by_region_and_ends_as_without_events(sample_page, settings):
    events = Events()
    tr = DictTranslator(EN_TEXTS)
    res = Pipeline(settings, ocr=FakeOcr(), translator=tr).process(sample_page, use_cache=False, events=events)
    plain = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).process(sample_page, use_cache=False)
    final = np.asarray(res.image)
    assert np.array_equal(final, np.asarray(plain.image))  # the events change nothing on the finished page
    n = len(res.regions)
    kinds = events.kinds()
    assert n >= 6 and kinds[0] == "regions" and kinds[-1] == "page" and kinds.count("page") == 1
    announced = events.of("regions")[0]
    assert announced["boxes"] == [r.bbox for r in res.regions] and announced["size"] == sample_page.size
    assert [d["index"] for d in events.of("read")] == list(range(n))
    assert {d["status"] for d in events.of("read")} == {"untranslated"}
    assert [d["box"] for d in events.of("read")] == [r.bbox for r in res.regions]  # where each one is once read
    last_read = max(i for i, k in enumerate(kinds) if k == "read")
    assert all(i > last_read for i, k in enumerate(kinds) if k == "translated")  # read first, then lettered
    lettered = events.of("translated")
    assert [d["index"] for d in lettered] == list(range(n))  # each once, in reading order
    assert [d["text"] for d in lettered] == [r.translated_text for r in res.regions]
    assert tr.kwargs[-1]["streamed"]  # the translator handed them over one by one
    for d, r in zip(lettered, res.regions):
        x0, y0, x1, y1 = d["box"]
        assert x0 <= r.x0 and y0 <= r.y0 and x1 >= r.x1 and y1 >= r.y1  # the region, and its lettering past it
        assert d["patch"].size == (x1 - x0, y1 - y0)
        assert np.array_equal(np.asarray(d["patch"]), final[y0:y1, x0:x1])  # bubbles apart: as on the finished page
    assert np.array_equal(np.asarray(events.of("page")[0]["image"]), final)


def test_translations_are_lettered_while_the_model_is_still_writing(sample_page, settings):
    log: list[tuple[str, int | None]] = []

    class Writing(DictTranslator):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None):
            out = [self.mapping.get(t, "") for t in texts]
            for i, text in enumerate(out):
                log.append(("written", i))
                on_item(i, text)
            log.append(("done", None))
            return out

    Pipeline(settings, ocr=FakeOcr(), translator=Writing(EN_TEXTS)).process(sample_page, use_cache=False,
                                                                            events=Events(log))
    assert log.index(("lettered", 0)) < log.index(("written", 1)) < log.index(("done", None))
    assert log.index(("lettered", 1)) < log.index(("done", None))


def test_a_translator_that_cannot_hand_over_fills_the_page_at_the_end(sample_page, settings):
    events = Events()
    answered: list[int] = []

    class Whole:  # no on_item: one answer for the whole page
        name = "whole"

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            answered.append(len(events.events))
            return [EN_TEXTS.get(t, "") for t in texts]

    assert not takes_items(Whole()) and takes_items(DictTranslator({}))
    res = Pipeline(settings, ocr=FakeOcr(), translator=Whole()).process(sample_page, use_cache=False, events=events)
    kinds = events.kinds()
    assert len(res.translated) >= 6 and kinds.count("translated") == len(res.translated)
    assert all(i >= answered[0] for i, k in enumerate(kinds) if k == "translated")  # all after the answer
    assert kinds[-1] == "page"


def test_each_translation_is_lettered_once_as_it_comes(settings):
    tr = DictTranslator({"こんにちは": LONG})
    p = Pipeline(settings, ocr=None, translator=tr)
    page = np.full((400, 400, 3), 255, np.uint8)
    small, big = _region(0, 0, 60, 40, (5, 5, 55, 35)), _region(0, 100, 400, 400, (150, 200, 250, 300))
    events = Events()
    fill = PageFill(p, page, events)
    fill.announce([small, big])
    assert events.of("regions")[0]["boxes"] == [small.bbox, big.bbox]
    assert p._translate_regions([small, big], lambda _m: None, fill) == ""
    lettered = events.of("translated")
    assert [(d["index"], d["text"]) for d in lettered] == [(0, LONG), (1, LONG)]  # no shorter version comes again
    assert small.translated_text == LONG and "small" in small.flags  # set small, and flagged
    assert np.asarray(lettered[0]["patch"]).min() < 128  # lettered: there is ink in it


def test_a_draft_that_does_not_last_gives_the_region_back(settings):
    p = Pipeline(settings, ocr=None, translator=None)
    page = np.full((300, 300, 3), 255, np.uint8)
    page[40:60, 40:60] = 0  # the original lettering
    r = _region(20, 20, 120, 100, (30, 30, 110, 90))
    events = Events()
    fill = PageFill(p, page, events)
    fill.announce([r])
    fill.draft(r, "こんにちは")  # the Japanese copied back: never lettered
    fill.draft(r, "  Hello *there  ")  # stray emphasis dropped, as tighten would
    assert [d["text"] for d in events.of("translated")] == ["Hello there"]
    erased = np.asarray(events.of("translated")[0]["patch"])
    assert erased[40 - 20:60 - 20, 40 - 20:60 - 20].mean() > 128  # the original text is erased in it
    r.status, r.translated_text = "untranslated", ""  # the final answer has nothing for it
    fill.settle([r])
    last = events.of("translated")[-1]
    x0, y0, x1, y1 = last["box"]
    assert last["text"] == "" and np.array_equal(np.asarray(last["patch"]), page[y0:y1, x0:x1])
    fill.draft(TextRegion(0, 0, 4, 4, np.full((4, 4), 255, np.uint8), (0, 0, 4, 4)), "Hi")  # not announced: nothing
    assert len(events.of("translated")) == 2


def test_a_page_from_the_cache_gets_only_the_finished_page(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Events", "fake")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    p.process(sample_page)
    events = Events()
    res = p.process(sample_page, events=events)
    assert res.cache_hits == 1 and events.kinds() == ["page"]
    assert np.array_equal(np.asarray(events.of("page")[0]["image"]), np.asarray(res.image))
