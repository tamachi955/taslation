"""A batch waits while the viewer window shows something other than the book (a browser tab switched away)."""
from __future__ import annotations

import threading

from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image
from test_batch import FakeViewer

from taslation import batch as batch_mod
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

BOOK_TITLE = "Book - Browser"


class SwitchingViewer(FakeViewer):
    """A browser window: for the first *away_polls* title checks another tab is in front."""

    def __init__(self, pages: list[Image.Image], foreign: Image.Image, away_polls: int):
        super().__init__(pages)
        self.foreign = foreign
        self.away_polls = away_polls
        self.polls = 0
        self.foreign_captures = 0

    def title(self, hwnd):
        self.polls += 1
        return "Other tab - Browser" if self.polls <= self.away_polls else BOOK_TITLE

    def capture(self, hwnd):
        if self.polls <= self.away_polls:
            self.foreign_captures += 1
            return self.foreign
        return super().capture(hwnd)


def _setup(viewer, settings, monkeypatch):
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "window_title", getattr(viewer, "title", lambda hwnd: BOOK_TITLE))
    settings.settle_ms = 10
    settings.page_turn_wait_ms = 300
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache), cache


def test_batch_waits_while_another_tab_is_in_front(sample_page, sample_page2, settings, monkeypatch):
    foreign = Image.new("RGB", sample_page.size, (250, 250, 250))
    viewer = SwitchingViewer([sample_page, sample_page2], foreign, away_polls=3)
    pipeline, cache = _setup(viewer, settings, monkeypatch)
    messages: list[str] = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, on_progress=lambda p, r: messages.append(p.message), context_mode=False, title=BOOK_TITLE)
    reader.wait_poll_s = 0.01
    progress = read_book(reader)
    assert progress.finished and progress.pages == 2, progress
    assert viewer.foreign_captures == 0  # the other tab's content was never read
    assert any(m.startswith("Waiting") for m in messages) and any("back" in m for m in messages)
    assert len(cache) == 2


def test_stop_while_waiting_for_the_book(sample_page, sample_page2, settings, monkeypatch):
    viewer = SwitchingViewer([sample_page, sample_page2], sample_page, away_polls=10 ** 9)
    pipeline, cache = _setup(viewer, settings, monkeypatch)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False, title=BOOK_TITLE)
    reader.wait_poll_s = 0.01
    threading.Timer(0.1, reader.stop).start()
    progress = read_book(reader)
    assert progress.finished and progress.pages == 0 and "stopped" in progress.reason
    assert viewer.foreign_captures == 0 and len(cache) == 0


def test_without_a_title_nothing_is_checked(sample_page, sample_page2, settings, monkeypatch):
    viewer = FakeViewer([sample_page, sample_page2])
    pipeline, _cache = _setup(viewer, settings, monkeypatch)

    def no_title(hwnd):
        raise AssertionError("the title must not be looked at when none is known")

    monkeypatch.setattr(batch_mod, "window_title", no_title)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False)  # no title known
    progress = read_book(reader)
    assert progress.pages == 2


class CoveredViewer(FakeViewer):
    """A Chrome viewer under a TASlation window: for its first *blank_frames* captures it draws nothing."""

    def __init__(self, pages: list[Image.Image], blank_frames: int):
        super().__init__(pages)
        self.blank_frames = blank_frames
        self.asked: list[bool] = []

    def capture(self, hwnd, allow_screen_fallback=True):
        self.asked.append(allow_screen_fallback)
        if self.blank_frames > 0:
            self.blank_frames -= 1
            return Image.new("RGB", self.pages[0].size, (255, 255, 255))
        return super().capture(hwnd)


def test_batch_waits_while_the_viewer_draws_nothing_behind_taslation(sample_page, sample_page2, settings, monkeypatch):
    viewer = CoveredViewer([sample_page, sample_page2], blank_frames=3)
    pipeline, cache = _setup(viewer, settings, monkeypatch)
    monkeypatch.setattr(batch_mod, "client_rect_on_screen", lambda hwnd: (0, 0, 800, 600))
    monkeypatch.setattr(batch_mod, "visible_rect", lambda hwnd: (0, 0, 1920, 1040))  # TASlation maximised over it
    messages: list[str] = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, on_progress=lambda p, r: messages.append(p.message), context_mode=False, own_windows=[99])
    reader.wait_poll_s = 0.01
    progress = read_book(reader)
    assert progress.finished and progress.pages == 2, progress
    assert viewer.asked and not any(viewer.asked)  # the screen there shows TASlation: it is never copied
    assert any("draws nothing behind TASlation" in m for m in messages) and any("draws again" in m for m in messages)
    assert len(cache) == 2  # no blank frame was taken for a page
