"""A batch stops when the viewer stops showing the book, refuses to run twice on one window, and can retranslate."""
from __future__ import annotations

import os

from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image
from test_batch import FakeViewer

from taslation import batch as batch_mod
from taslation.batch import BatchReader, ViewerLock, pid_alive
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator


def _setup(viewer, settings, monkeypatch):
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    settings.settle_ms = 10
    settings.page_turn_wait_ms = 300
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    tr = DictTranslator(EN_TEXTS, default="ok")
    return Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache), cache, tr


def test_batch_does_not_read_a_page_that_does_not_look_like_the_book(sample_page, sample_page2, settings, monkeypatch):
    store_page = Image.new("RGB", (sample_page.width * 2, sample_page.height // 2), (250, 250, 250))
    px = store_page.load()
    for x in range(40, store_page.width - 40, 3):  # a wide page with some ink: a store page, not a manga page
        for y in (40, 41, store_page.height - 40):
            px[x, y] = (20, 20, 20)
    book_pages = [sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT),
                  sample_page2.transpose(Image.FLIP_LEFT_RIGHT), sample_page.transpose(Image.ROTATE_180),
                  sample_page2.transpose(Image.ROTATE_180)]
    viewer = FakeViewer(book_pages + [store_page, sample_page.transpose(Image.FLIP_TOP_BOTTOM)])
    pipeline, cache, _ = _setup(viewer, settings, monkeypatch)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False)
    progress = read_book(reader)
    assert progress.pages == len(book_pages) + 1 and progress.reason.code == "batch.finished_reading"
    assert len(cache) == len(book_pages) + 1  # the store page was neither read nor translated; the reader came back


def test_only_one_batch_per_viewer_window(sample_page, sample_page2, settings, monkeypatch):
    viewer = FakeViewer([sample_page, sample_page2])
    pipeline, cache, _ = _setup(viewer, settings, monkeypatch)
    lock = ViewerLock(settings.state_dir, 1)
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    lock.path.write_text(str(os.getppid()), encoding="utf-8")  # a live process (not ours) holds the window
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False)
    progress = read_book(reader)
    assert progress.finished and progress.pages == 0 and "Another TASlation window" in progress.reason
    lock.path.write_text("999999999", encoding="utf-8")  # a stale lock from a process that is gone
    assert not pid_alive(999999999)
    progress = read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False))
    assert progress.pages == 2 and not lock.path.exists()


def test_retranslate_replaces_cached_pages(sample_page, sample_page2, settings, monkeypatch):
    viewer = FakeViewer([sample_page, sample_page2])
    pipeline, cache, tr = _setup(viewer, settings, monkeypatch)
    read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True))
    first_calls = len(tr.calls)
    assert len(cache) == 2 and first_calls >= 1
    viewer.index = 0
    read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True))
    assert len(tr.calls) == first_calls  # everything cached: nothing translated again
    viewer.index = 0
    tr.mapping = {k: v.upper() for k, v in tr.mapping.items()}  # the "premises" changed: a different rendering
    read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, retranslate=True))
    assert len(tr.calls) > first_calls and len(cache) == 2
    texts = [b.text for p in cache.pages for b in p.bubbles]
    assert texts and all(t == t.upper() for t in texts)


def test_retranslate_replaces_the_matched_entry_when_the_fingerprint_drifted(sample_page, sample_page2, settings, monkeypatch):
    """The page captured again differs by a few bits: --retranslate must update that entry, not add a second one."""
    import numpy as np

    from taslation import fingerprint as fp
    from taslation.cache import CachedBubble, CachedPage

    viewer = FakeViewer([sample_page, sample_page2])
    pipeline, cache, tr = _setup(viewer, settings, monkeypatch)
    drifted = []
    for i, page in enumerate((sample_page, sample_page2)):
        unit = fp.analyze(np.asarray(page))[0]
        fpr = format(int(unit.fingerprint, 16) ^ ((1 << 12) - 1), "080x")  # 12 bits off: the same page
        drifted.append(fpr)
        cache.add(CachedPage(fpr, unit.aspect, [CachedBubble((0.05, 0.05, 0.15, 0.12), "Old line")], seq=i))
    cache.save()
    read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, retranslate=True))
    assert len(cache) == 2 and sorted(p.fingerprint for p in cache.pages) == sorted(drifted)
    texts = [b.text for p in cache.pages for b in p.bubbles]
    assert "Old line" not in texts and len(texts) >= 6


def _dark_viewer_frame(kind: str, seed: int = 0) -> Image.Image:
    """A capture of a viewer with a black background: a two-page spread where the book's pages always are."""
    import random

    from PIL import ImageDraw

    rng = random.Random(seed)
    img = Image.new("RGB", (1200, 700), (0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "panel":  # a store page or panel elsewhere on the screen
        d.rectangle((150, 200, 1100, 450), fill=(245, 245, 245))
        for y in range(230, 430, 30):
            d.rectangle((180, y, 1070, y + 8), fill=(30, 30, 30))
        return img
    if kind == "end":  # the viewer's end-of-book panel opened over the spread
        img = _dark_viewer_frame("art", seed)
        d = ImageDraw.Draw(img)
        d.rectangle((860, 40, 1190, 660), fill=(245, 245, 245))
        for y in range(80, 600, 40):
            d.rectangle((890, y, 1160, y + 10), fill=(30, 30, 30))
        return img
    for x0 in (100, 508):
        d.rectangle((x0, 50, x0 + 392, 650), fill=(255, 255, 255))
        if kind == "art":  # artwork from edge to edge
            for _ in range(8):
                d.line((x0, rng.randint(50, 650), x0 + 392, rng.randint(50, 650)), fill=(20, 20, 20), width=1)
            d.rectangle((x0 + 2, 52, x0 + 390, 648), outline=(20, 20, 20), width=1)
        else:  # a page of text: one narrow column of ink
            d.rectangle((x0 + 186, 200, x0 + 206, 480), fill=(20, 20, 20))
    return img


def test_a_page_of_text_is_still_the_book(settings, monkeypatch):
    """Page units are cropped to the ink, so a page of text looks narrow; its paper is where the pages always are."""
    frames = [_dark_viewer_frame("art", i) for i in range(6)]
    frames += [_dark_viewer_frame("text"), _dark_viewer_frame("art", 6), _dark_viewer_frame("panel"),
               _dark_viewer_frame("art", 7)]
    viewer = FakeViewer(frames)
    pipeline, _cache, _ = _setup(viewer, settings, monkeypatch)
    progress = read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False))
    assert progress.pages == 9  # read the text page, not the panel


def test_the_end_of_book_panel_is_not_read(settings, monkeypatch):
    """A panel opened over the spread leaves a page of the right shape, but the paper reaches past the pages."""
    frames = [_dark_viewer_frame("art", i) for i in range(7)] + [_dark_viewer_frame("end", 7)]
    pipeline, _cache, _ = _setup(FakeViewer(frames), settings, monkeypatch)
    progress = read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False))
    assert progress.pages == 7 and progress.reason.code == "batch.finished_reading"
