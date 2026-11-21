"""A whole-book run reads the sharp picture of a page, also when it took a soft one first: a viewer that draws a page
soft first, before the run has seen that it does, has the soft picture taken when it stays as it is for settle_ms
(`batch.PageWatch`); its sharper picture takes the frame's place (`PageImages.replace_unread`). When that comes while
the page is being read, the reading is thrown away - none of its lines kept, nothing it would store stored - and the
page read again from the sharper picture (`BatchReader._scan_sharp`). Before, the sharper picture stayed where nothing
read the page again, and the page had the soft picture's lines (found by the stand-in runs on GitHub's runners, and once
in 13 runs here)."""
from __future__ import annotations

import threading
import time

import numpy as np
from helpers import EN_TEXTS, JA_TEXTS, FakeOcr
from PIL import Image, ImageFilter
from test_batch import _fake_viewer

from taslation.batch import BatchReader
from taslation.cache import CachedBubble, CacheStore
from taslation.pageimages import PageImages, pack
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

SOFT_TEXTS = ["ぼやけた一", "ぼやけた二", "ぼやけた三"]  # what the OCR reads in the soft picture (misreadings)


def _wait(what, seconds: float = 10.0) -> bool:
    end = time.monotonic() + seconds
    while not what():
        if time.monotonic() > end:
            return False
        time.sleep(0.003)
    return True


def test_a_sharper_picture_that_comes_while_the_soft_one_is_read_is_the_picture_the_page_is_read_from(
        sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    sharp = viewer.pages[0]
    soft = sharp.filter(ImageFilter.GaussianBlur(1.0))
    viewer.pages[0] = soft  # the first page drawn soft, and for longer than settle_ms
    ocr = FakeOcr()
    tr = DictTranslator({**EN_TEXTS, **{t: "Blurred." for t in SOFT_TEXTS}})
    cache = CacheStore(settings.cache_dir).open("Sharp", "fake")
    pipeline = Pipeline(settings, ocr=ocr, translator=tr, cache=cache)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True)
    soft_px = np.asarray(soft)
    read, kept_later = [], []
    scan = pipeline.scan

    def scanning(image, **kw):
        which = "soft" if np.array_equal(np.asarray(image.convert("RGB")), soft_px) else "sharp"
        read.append(which)
        later = kw.get("later")  # (what the reading would store, kept when the run keeps it: none, at once)
        (later.append if later is not None else (lambda action: action()))(lambda: kept_later.append(which))
        ocr.texts = list(SOFT_TEXTS if which == "soft" else JA_TEXTS)
        if which == "soft":
            viewer.pages[0] = sharp  # the viewer draws the page sharp while it is read ...
            assert _wait(lambda: reader.images.replaced(1) == 1)  # ... and the run takes it in the soft one's place
        return scan(image, **kw)

    pipeline.scan = scanning  # type: ignore[method-assign]
    over = threading.Event()

    def person():  # turns on once each page is on the window: the first one once its sharp picture is
        if not _wait(lambda: reader._on_show is sharp or over.is_set()):
            return
        for index in (1, 2):
            viewer.index = index
            if not _wait(lambda: reader._on_show is viewer.pages[index] or over.is_set()):
                return
        reader.finish()

    hand = threading.Thread(target=person, daemon=True)
    hand.start()
    try:
        progress = reader.run()
    finally:
        over.set()
        hand.join(5)
    assert read == ["soft", "sharp", "sharp", "sharp"]  # page 1 read again from its sharp picture, pages 2 and 3
    assert reader.read_again == 1 and kept_later == ["sharp", "sharp", "sharp"]  # nothing the soft reading kept
    assert progress.pages == 3 and progress.found == 18
    asked = [t for call in tr.calls for t in call]
    assert len(asked) == 18 and not set(asked) & set(SOFT_TEXTS)  # no line of the soft picture went to the model
    bubbles = [b.text for page in cache.pages for b in page.bubbles]
    assert len(bubbles) == 18 and "Blurred." not in bubbles


def test_a_frame_read_while_a_sharper_picture_took_its_place_is_not_marked_read():
    images = PageImages(10 * 1024 * 1024)
    soft = Image.fromarray(np.full((40, 30, 3), 100, np.uint8))
    sharp = Image.fromarray(np.full((40, 30, 3), 200, np.uint8))
    assert images.put_frame(1, pack(soft))
    began = images.replaced(1)
    assert images.replace_unread(1, pack(sharp)) and images.replaced(1) == began + 1  # (while it is read)
    assert not images.read(1, erase=False, read_from=began)  # the reading of the soft one: not the frame's
    assert images.unread() == 1 and images.replace_unread(1, pack(sharp))  # it still waits to be read
    again = images.replaced(1)
    assert images.read(1, erase=True, read_from=again) and images.unread() == 0
    assert not images.replace_unread(1, pack(soft))  # read: no picture takes its place any more
    assert images.read(2, erase=False)  # (without *read_from*: as before)


def test_what_a_scan_would_store_waits_for_its_caller_when_asked(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Later", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    pipeline.process(sample_page)  # the page translated and stored ...
    page = cache.pages[0]
    held = len(page.bubbles)
    page.bubbles.append(CachedBubble(box=(0.0, 0.0, 0.01, 0.01), text="Gone."))  # ... with a bubble no region has
    later: list = []
    scan = pipeline.scan(sample_page, skip_cached=True, later=later)
    assert scan.units and all(u.cached for u in scan.units) and sum(u.dropped for u in scan.units) == 1
    assert len(cache.pages[0].bubbles) == held + 1 and later  # nothing stored yet: the prune waits
    for action in later:
        action()
    assert len(cache.pages[0].bubbles) == held  # done by the caller: pruned
