"""While the model writes, a page's drafts are lettered on a thread of their own (`pipeline.DRAFTS_BESIDE`) and measure
only their new line (`pipeline.DRAFT_SIZES_KEPT`), and a translator that puts no room in its request (PLaMo:
`uses_room`) is asked before the rooms are measured. None of it changes anything: the drafts sent, the finished page,
the regions as kept (their masks, rooms and sizes) and the cache are what they were with the drafts lettered in line,
measured afresh, and the rooms measured first."""
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
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator, OllamaTranslator
from taslation.translate.base import uses_room
from taslation.translate.plamo import PlamoTranslator


class Writing(DictTranslator):
    """Hands each line over as it is written (as PLaMo does); *twice*: the first line is handed over once more, written
    another way (the page is lettered again); *final*: the first line's final text differs from what was handed over
    (settled afterwards)."""

    def __init__(self, mapping, twice=False, final=False, room=True):
        super().__init__(mapping)
        self.twice, self.final, self.uses_room = twice, final, room
        self.metas: list = []

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None):
        self.metas.append([dict(m) for m in (meta or [])])
        out = super().translate_page(texts, context, notes, upcoming, meta, cancel=cancel)
        for i, text in enumerate(out):
            if on_item is not None:
                on_item(i, text)
                if i == 0 and self.twice:
                    on_item(0, text + " Again.")
        if self.final and out:
            out = [out[0] + " At last.", *out[1:]]
        return out


def _spread(right: Image.Image, left: Image.Image) -> Image.Image:
    w, h = right.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(left, (0, 20))
    spread.paste(right, (w + 60, 20))
    return spread


def _run(settings, page, book, beside, kept, **writing):
    """The page read and translated with the drafts beside (or in line) and their sizes kept (or measured afresh):
    what was sent, the result, and what the cache holds."""
    events: list[tuple[str, dict]] = []
    old = pipeline_mod.DRAFTS_BESIDE, pipeline_mod.DRAFT_SIZES_KEPT
    pipeline_mod.DRAFTS_BESIDE, pipeline_mod.DRAFT_SIZES_KEPT = beside, kept
    try:
        cache = CacheStore(settings.cache_dir).open(book, "fake")
        p = Pipeline(settings, ocr=FakeOcr(), translator=Writing(EN_TEXTS, **writing), cache=cache)
        result = p.process(page.copy(), events=lambda kind, data: events.append((kind, dict(data))))
    finally:
        pipeline_mod.DRAFTS_BESIDE, pipeline_mod.DRAFT_SIZES_KEPT = old
    return events, result, p


def _sent(events) -> list:
    out = []
    for kind, data in events:
        if kind == "translated":
            out.append((kind, data["index"], data["text"], data["box"], np.asarray(data["patch"]).tobytes()))
        elif kind == "page":
            out.append((kind, np.asarray(data["image"]).tobytes()))
        else:
            out.append((kind, repr(sorted(data.items()))))
    return out


def _kept(result, p) -> list:
    regions = [(r.bbox, r.status, r.translated_text, r.room, r.size_cap, r.font_size, tuple(r.letter_flags),
                np.asarray(r.mask).tobytes(), tuple(r.flags)) for r in result.regions]
    pages = [(c.fingerprint, c.seq, c.incomplete, [(b.box, b.text, b.poly, b.flags) for b in c.bubbles])
             for c in p.cache.pages]
    return [regions, pages, np.asarray(result.image).tobytes()]


@pytest.mark.parametrize("which", ["one", "other", "spread"])
@pytest.mark.parametrize("writing", [{}, {"twice": True}, {"final": True}, {"room": False}])
def test_the_drafts_beside_send_and_keep_what_the_drafts_in_line_did(which, writing, settings, sample_page,
                                                                    sample_page2):
    page = {"one": sample_page, "other": sample_page2, "spread": _spread(sample_page, sample_page2)}[which]
    before = _run(settings, page, "In line", beside=False, kept=False)  # as ever (rooms first: a translator of rooms)
    after = _run(settings, page, "Beside", beside=True, kept=True, **writing)
    if writing:
        before = _run(settings, page, "In line 2", beside=False, kept=False, **{**writing, "room": True})
    assert _sent(after[0]) == _sent(before[0])
    assert _kept(after[1], after[2]) == _kept(before[1], before[2])
    assert any(kind == "translated" for kind, _d in after[0])


def test_a_translator_without_rooms_is_asked_before_they_are_measured(settings, sample_page, monkeypatch):
    assert uses_room(DictTranslator({})) and uses_room(OllamaTranslator()) and not uses_room(PlamoTranslator())
    measured: list[int] = []
    real = pipeline_mod.translation_room

    def room(*args, **kwargs):
        measured.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline_mod, "translation_room", room)
    at_request: list[int] = []

    class Plain(Writing):
        def translate_page(self, texts, *a, **k):
            at_request.append(len(measured))
            return super().translate_page(texts, *a, **k)

    tr = Plain(EN_TEXTS, room=False)
    result = Pipeline(settings, ocr=FakeOcr(), translator=tr).process(sample_page, use_cache=False)
    assert at_request[0] == 0 and len(measured) == len([r for r in result.regions if r.source_text and
                                                         r.status in ("translated", "untranslated")])
    assert all("room" not in m for m in tr.metas[0])
    with_rooms = Writing(EN_TEXTS)
    again = Pipeline(settings, ocr=FakeOcr(), translator=with_rooms).process(sample_page, use_cache=False)
    assert [r.room for r in again.regions] == [r.room for r in result.regions]


def test_a_page_with_room_to_measure_gets_the_same_rooms(settings):
    """(a bubble too small for its line: a room that is not 0, measured either way)"""
    page = np.full((400, 400, 3), 255, np.uint8)
    from taslation.regions import TextRegion

    def region():
        return TextRegion(20, 20, 80, 60, np.full((40, 60), 255, np.uint8), (25, 25, 75, 55), status="untranslated",
                          source_text="こんにちはこんにちはこんにちは")

    rooms = []
    for room in (True, False):
        p = Pipeline(settings, ocr=None, translator=Writing({"こんにちはこんにちはこんにちは": "Hello."}, room=room))
        r = region()
        p._translate_regions([r], lambda _m: None, pipeline_mod.PageFill(p, page, lambda k, d: None))
        rooms.append(r.room)
    assert rooms[0] == rooms[1] and rooms[0] > 0


def test_the_page_waits_for_slow_drafts(settings, sample_page, monkeypatch):
    real = Pipeline.letter_region

    def slow(self, *args, **kwargs):
        time.sleep(0.03)
        return real(self, *args, **kwargs)

    before = _run(settings, sample_page, "Quick", beside=False, kept=False)
    monkeypatch.setattr(Pipeline, "letter_region", slow)
    after = _run(settings, sample_page, "Slow", beside=True, kept=True)
    assert _sent(after[0]) == _sent(before[0]) and after[0][-1][0] == "page"
    assert _kept(after[1], after[2]) == _kept(before[1], before[2])


def test_a_page_stopped_while_its_drafts_wait_sends_none_after(settings, sample_page, monkeypatch):
    real = Pipeline.letter_region
    monkeypatch.setattr(Pipeline, "letter_region",
                        lambda self, *a, **k: (time.sleep(0.05), real(self, *a, **k))[1])
    cancel = threading.Event()

    class Stopping(Writing):
        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, on_item=None, cancel=None):
            for i, t in enumerate(texts):
                on_item(i, self.mapping.get(t, ""))
            cancel.set()
            raise Cancelled()

    events: list[str] = []
    cache = CacheStore(settings.cache_dir).open("Stopped", "fake")
    p = Pipeline(settings, ocr=FakeOcr(), translator=Stopping(EN_TEXTS), cache=cache)
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel, events=lambda kind, data: events.append(kind))
    sent = list(events)
    time.sleep(0.3)
    assert events == sent and sent.count("translated") < 6  # dropped, and nothing after the stop
    assert pipeline_mod._drafts_pool().submit(lambda: 1).result(timeout=2) == 1  # the drafts' thread is free
    assert len(cache) == 0


def test_the_drafts_measure_only_their_new_line(settings, sample_page, monkeypatch):
    counts = {}
    for kept in (False, True):
        measures = []
        real = Pipeline._set_text

        def counted(self, image, *a, **k):
            if image is None:
                measures.append(1)
            return real(self, image, *a, **k)

        monkeypatch.setattr(Pipeline, "_set_text", counted)
        _run(settings, sample_page, f"Measured {kept}", beside=True, kept=kept)
        monkeypatch.setattr(Pipeline, "_set_text", real)
        counts[kept] = len(measures)
    assert counts[True] < counts[False]


def test_the_book_sizes_are_never_changed_in_place(settings):
    p = Pipeline(settings, ocr=None, translator=None)
    p._add_sizes([20.0, 22.0])
    old = p._book_sizes
    seen = list(old)
    p._add_sizes([30.0])
    assert p._book_sizes is not old and list(old) == seen and list(p._book_sizes) == [20.0, 22.0, 30.0]
    assert p._book_sizes.maxlen == old.maxlen
    p.set_cache(None)
    assert not p._book_sizes and list(old) == seen
