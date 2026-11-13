"""A stand-in of a whole-book run's page events for the page strip (`ui.strip`): the ``page_stage`` and ``batch_memory``
events `BatchReader` sends through its show callback, and the pictures it holds (`images`, which only the memory line
counts: no page of a run is shown to be read). The pages are drawn here (a grey page with its number and a few empty
bubbles): no book's page, nothing read from disk, nothing written."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from PIL import Image, ImageDraw

PAGE_SIZE = (600, 860)


def picture(seq: int) -> Image.Image:
    """A made-up page: light grey, its number large, a few white ovals as bubbles."""
    image = Image.new("RGB", PAGE_SIZE, (200 + seq % 5 * 8, 200, 196))
    draw = ImageDraw.Draw(image)
    for i in range(3):
        x, y = 60 + (seq * 37 + i * 170) % 380, 80 + i * 240
        draw.ellipse((x, y, x + 150, y + 110), fill="white", outline="black", width=3)
    draw.text((PAGE_SIZE[0] // 2 - 20, PAGE_SIZE[1] - 120), str(seq), fill="black", font_size=72)
    return image


def thumb(image: Image.Image) -> Image.Image:
    """As the run sends it: at most 96 pixels tall."""
    out = image.copy()
    out.thumbnail((96 * image.width // image.height + 1, 96))
    return out


class FakeRun:
    """The run's side of the strip. *post(kind, data)* takes each event (the window's show callback). Every
    *fail_every*-th page fails to be erased and every *skip_every*-th needs no erasing (no text); the latest *keep*
    pages' pictures are held (`images`, counted by the memory line), the older ones are gone, as a run with a memory cap
    drops them."""

    def __init__(self, post: Callable[[str, dict[str, Any]], None], pages: int = 200, fail_every: int = 37,
                 skip_every: int = 11, keep: int = 60, mb_per_page: float = 1.5, cap_mb: float = 512.0):
        self.post, self.pages = post, pages
        self.fail_every, self.skip_every, self.keep = fail_every, skip_every, keep
        self.mb_per_page, self.cap_mb = mb_per_page, cap_mb
        self.images: dict[int, Image.Image] = {}
        self.stopped = threading.Event()
        self.following = True
        self._lock = threading.Lock()

    def stop(self) -> None:
        self.stopped.set()

    def _stage(self, seq: int, stage: str, state: str, with_thumb: Image.Image | None = None) -> None:
        data: dict[str, Any] = {"seq": seq, "fingerprint": f"{seq:080x}", "stage": stage, "state": state}
        if with_thumb is not None:
            data["thumb"] = with_thumb
        self.post("page_stage", data)

    def _memory(self) -> None:
        with self._lock:
            held = len(self.images)
        self.post("batch_memory", {"used_mb": held * self.mb_per_page, "cap_mb": self.cap_mb})

    def read_page(self, seq: int, pause: Callable[[float], None] = lambda s: None) -> None:
        """Page *seq* turned and read: reading, then erasing; its translation waits for the end."""
        image = picture(seq)
        with self._lock:
            self.images[seq] = image
            for old in [s for s in self.images if s <= seq - self.keep]:
                del self.images[old]
        self._stage(seq, "read", "working", thumb(image))
        pause(0.1)
        self._stage(seq, "read", "done")
        self._stage(seq, "translate", "waiting")
        if seq % self.skip_every == 0:
            self._stage(seq, "erase", "skipped")
            self._stage(seq, "translate", "skipped")
        else:
            self._stage(seq, "erase", "working")
            pause(0.12)
            self._stage(seq, "erase", "failed" if seq % self.fail_every == 0 else "done")
        self._memory()

    def translate_all(self, pause: Callable[[float], None] = lambda s: None, group: int = 10) -> None:
        """Finished reading: the book translated together, a group of pages at a time."""
        todo = [s for s in range(1, self.pages + 1) if s % self.skip_every]
        for start in range(0, len(todo), group):
            if self.stopped.is_set():
                return
            chunk = todo[start:start + group]
            for seq in chunk:
                self._stage(seq, "translate", "working")
            pause(0.3)
            for seq in chunk:
                self._stage(seq, "translate", "done")

    def run(self, rate: float | None = 3.0) -> None:
        """The whole run: *rate* pages a second turned (None: no waiting), then the translation."""
        pause = (lambda s: time.sleep(s)) if rate else (lambda s: None)
        step = 1.0 / rate if rate else 0.0
        for seq in range(1, self.pages + 1):
            if self.stopped.is_set():
                return
            began = time.monotonic()
            self.read_page(seq, pause)
            if rate:
                time.sleep(max(0.0, step - (time.monotonic() - began)))
        self.following = False
        self.translate_all(pause)
