"""A page of a whole-book run shows beside it (`BatchReader.viewer_page`) as soon as none of its own lines can change
any more - its units stored complete, spelt, checked and saved - while a line of another page of the same request is
still asked for again; never before: a page with a line still to come stays "waiting", and what a page shows is what
stays stored. The run is the real `BatchReader` and `Pipeline` on stand-in pages and a stand-in model; no real window,
nothing under the real state folder."""
from __future__ import annotations

import threading

import numpy as np
from helpers import FakeOcr, read_book

from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

from test_batch_follows_reader import desk  # noqa: F401 - (a fixture)
from test_translate_beside_backlog import MAPPING, TEXTS, stored


class Holey(DictTranslator):
    """The first request's reply leaves its last line (the second page's) empty; the request that asks for that line
    again waits for *gate*."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.gate, self.asking = threading.Event(), threading.Event()
        self.hole = ""

    def translate_page(self, texts, *args, **kwargs):
        if not self.calls:
            self.hole = texts[-1]
            kwargs.pop("on_item", None)  # (the reply as a whole: the line left out is never told either)
            out = super().translate_page(texts, *args, **kwargs)
            return out[:-1] + [""]
        out = super().translate_page(texts, *args, **kwargs)
        self.asking.set()
        self.gate.wait(20)
        return out


def test_a_page_shows_once_its_lines_are_final_while_a_line_of_its_request_is_asked_again(
        desk, settings, sample_page, sample_page2):
    settings.chunk_bubbles = 12  # the two pages in one request
    settings.lookahead_bubbles = 6
    desk.pages[:] = [sample_page, sample_page2]
    cache = CacheStore(settings.cache_dir).open("Final 1", "fake")
    model = Holey(MAPPING)
    pipeline = Pipeline(settings, ocr=FakeOcr(TEXTS), translator=model, cache=cache)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[], book="Final 1",
                         show=lambda kind, data: None)
    done: list = []
    thread = threading.Thread(target=lambda: done.append(read_book(reader, desk)), daemon=True)
    thread.start()
    try:
        assert model.asking.wait(30)
        assert len(model.calls[0]) == 12 and model.calls[1] == [model.hole]  # (the line left out, asked again)
        # page 1 is over: stored complete, nothing of it asked again; page 2 waits for its line
        assert reader.stage_of(1, "translate") == "done" and reader.stage_of(2, "translate") == "working"
        page1 = reader.viewer_page(desk.pages[0])
        assert page1.state == "translated" and page1.seq == 1
        assert not np.array_equal(np.asarray(page1.image), np.asarray(desk.pages[0]))  # lettered
        page2 = reader.viewer_page(desk.pages[1])
        assert page2.state == "waiting" and page2.seq == 2 and page2.image is None  # (a line of it still to come)
        with reader._storing:
            early = stored(cache)
        assert sorted((incomplete, len(texts)) for incomplete, texts in early.values()) == [(False, 6), (True, 5)]
    finally:
        model.gate.set()
        thread.join(30)
    assert done and done[0].summary.code == "batch.finished"
    assert reader.stage_of(2, "translate") == "done"
    final = stored(cache)
    assert all(not incomplete and len(texts) == 6 for incomplete, texts in final.values())
    # what page 1 showed is what stays stored: its entry, and its picture from the cache, are the same at the end
    shown_early = [key for key, (incomplete, _texts) in early.items() if not incomplete]
    assert len(shown_early) == 1 and final[shown_early[0]] == early[shown_early[0]]
    assert np.array_equal(np.asarray(page1.image), np.asarray(pipeline.page_picture(reader.images, 1)))
    assert reader.viewer_page(desk.pages[1]).state == "translated"
