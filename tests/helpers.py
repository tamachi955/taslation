from __future__ import annotations

import threading
import time

from PIL import Image

from taslation import batch as batch_mod

from taslation.translate import TranslationError

JA_TEXTS = ["こんにちは", "ありがとう", "どこへ行くの", "今日はいい天気だね", "大丈夫だよ", "まだ終わってない"]
EN_TEXTS = {
    "こんにちは": "Hello there!",
    "ありがとう": "Thank you.",
    "どこへ行くの": "Where are you going?",
    "今日はいい天気だね": "Nice weather today, huh?",
    "大丈夫だよ": "It's fine.",
    "まだ終わってない": "It isn't over yet.",
}


class FakeOcr:
    """Returns canned Japanese strings in call order (the pipeline never sees coordinates)."""

    def __init__(self, texts: list[str] | None = None):
        self.texts = list(texts or JA_TEXTS)
        self.calls = 0

    def read(self, image: Image.Image) -> str:
        assert image.width > 0 and image.height > 0
        text = self.texts[self.calls % len(self.texts)]
        self.calls += 1
        return text


class FailingTranslator:
    name = "failing"

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
        raise TranslationError("cannot reach Ollama (test)")


def read_book(reader, viewer=None, patience_s: float = 1.0):
    """*reader* run with a person at the viewer (*viewer*; by default the stand-in the batch captures from): each page
    is turned once the run has taken it (a page that looks like the one before is not taken: *patience_s*), then
    Finished reading. Returns what `BatchReader.run` returns."""
    viewer = viewer if viewer is not None else batch_mod.capture_window.__self__
    over = threading.Event()

    def person():
        while not over.is_set():
            waited = time.monotonic() + patience_s
            page = viewer.pages[viewer.index]
            while reader._on_show is not page and time.monotonic() < waited and not over.is_set():
                time.sleep(0.002)
            if over.is_set():
                return
            if viewer.index >= len(viewer.pages) - 1:
                reader.finish()
                return
            viewer.index += 1

    hand = threading.Thread(target=person, daemon=True)
    hand.start()
    try:
        return reader.run()
    finally:
        over.set()
        hand.join(5)
