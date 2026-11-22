"""Made-up pages and events for the indicator beside the page (`ui.side`): the engine's ``page_stage``,
``page_on_show`` and ``backlog`` events as normal reading sends them (with ``reading`` True, in the shapes
`taslation.backlog` gives them), a page or a spread drawn here (grey paper, white
ovals as bubbles, its number) with made-up English lettering for its "translation" and scribbles for its "original",
and a cache stand-in holding made-up words. No book's page, nothing read from disk, nothing written."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw

from taslation.cache import CachedBubble, CachedPage
from taslation.regions import PageResult, TextRegion

Post = Callable[[str, dict[str, Any]], None]
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
    """As the events carry it: at most 96 pixels tall."""
    out = image.copy()
    out.thumbnail((96 * image.width // image.height + 1, 96))
    return out


def fingerprint(seq: int) -> str:
    """A made-up fingerprint for screen *seq*, far from every other one (80 hex digits, as the run's)."""
    return (hashlib.sha256(f"screen {seq}".encode()).hexdigest() * 2)[:80]


def page(seq: int, spread: bool = False) -> Image.Image:
    """Screen *seq*: a made-up page, or a spread of two side by side."""
    if not spread:
        return picture(seq)
    out = Image.new("RGB", (PAGE_SIZE[0] * 2, PAGE_SIZE[1]), (90, 90, 90))
    out.paste(picture(seq * 2), (PAGE_SIZE[0], 0))  # (right to left: the first page on the right)
    out.paste(picture(seq * 2 + 1), (0, 0))
    return out


def bubble_boxes(seq: int, spread: bool = False) -> list[tuple[int, int, int, int]]:
    """The made-up bubbles of screen *seq*, as `picture` draws them (inside each oval)."""
    def one(n: int, dx: int) -> list[tuple[int, int, int, int]]:
        return [(dx + 60 + (n * 37 + i * 170) % 380 + 25, 80 + i * 240 + 25,
                 dx + 60 + (n * 37 + i * 170) % 380 + 125, 80 + i * 240 + 85) for i in range(3)]
    if not spread:
        return one(seq, 0)
    return one(seq * 2, PAGE_SIZE[0]) + one(seq * 2 + 1, 0)


def scribbled(image: Image.Image, boxes: list[tuple[int, int, int, int]]) -> Image.Image:
    """*image* with made-up "lettering" in its bubbles: short vertical strokes, not any script."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for x0, y0, x1, y1 in boxes:
        for x in range(x1 - 18, x0 + 10, -16):
            draw.line((x, y0 + 6, x, y1 - 6), fill="black", width=3)
    return out


def lettered(image: Image.Image, boxes: list[tuple[int, int, int, int]], texts: list[str]) -> Image.Image:
    """*image* with *texts* (made-up English) lettered in its bubbles, an empty text leaving the bubble as it is."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for (x0, y0, x1, y1), text in zip(boxes, texts):
        if not text:
            continue
        draw.rectangle((x0, y0, x1, y1), fill="white")
        draw.multiline_text(((x0 + x1) // 2, (y0 + y1) // 2), text.replace(" ", "\n", 1), fill="black",
                            anchor="mm", align="center", font_size=15)
    return out


def result(seq: int, texts: list[str], spread: bool = False, error: str = "") -> PageResult:
    """Screen *seq* read and translated: its scribbled original, *texts* lettered over it ("" for a bubble left in
    its original), its regions, its fingerprint."""
    boxes = bubble_boxes(seq, spread)
    original = scribbled(page(seq, spread), boxes)
    regions = [TextRegion(*box, mask=np.full((box[3] - box[1], box[2] - box[0]), 255, np.uint8), text_box=box,
                          order=i, translated_text=text, status="translated" if text else "untranslated")
               for i, (box, text) in enumerate(zip(boxes, texts))]
    return PageResult(image=lettered(original, boxes, texts), original=original, regions=regions,
                      fingerprints=[fingerprint(seq)], error=error)


def stage(post: Post, seq: int, read: str | None = None, translate: str | None = None, spread: bool = False,
          with_thumb: bool = False) -> None:
    """The ``page_stage`` events for screen *seq*: its reading stage *read*, its translation stage *translate*; as
    normal reading tells them (`taslation.backlog`)."""
    first: dict[str, Any] = {"seq": seq, "fingerprint": fingerprint(seq), "reading": True}
    if with_thumb:
        first["thumb"] = thumb(scribbled(page(seq, spread), bubble_boxes(seq, spread)))
    if read is not None:
        post("page_stage", {**first, "stage": "read", "state": read})
        first.pop("thumb", None)
    if translate is not None:
        post("page_stage", {**first, "stage": "translate", "state": translate})


def story(post: Post, pages: int = 12, on_show: int | None = None, spread: bool = False,
          missed: tuple[int, ...] = (), working: tuple[int, ...] = (), waiting_from: int | None = None) -> None:
    """Normal reading so far: *pages* screens turned, each with its thumbnail; those before *waiting_from* translated,
    those in *working* being translated, the rest waiting, those in *missed* gone by too fast; *on_show* the one the
    viewer shows (being read, when it is the last), and the backlog's totals."""
    waiting_from = pages - 3 if waiting_from is None else waiting_from
    for seq in range(1, pages + 1):
        if seq in missed:
            stage(post, seq, read="missed")
            continue
        if seq == on_show == pages:
            stage(post, seq, read="working", with_thumb=True, spread=spread)
            continue
        if seq in working:
            stage(post, seq, read="done", translate="working", with_thumb=True, spread=spread)
        elif seq < waiting_from:
            stage(post, seq, read="done", translate="done", with_thumb=True, spread=spread)
        else:
            stage(post, seq, read="done", translate="waiting", with_thumb=True, spread=spread)
    post("page_on_show", {"seq": on_show, "reading": True})
    left = [s for s in range(waiting_from, pages + 1) if s not in missed]
    post("backlog", {"pages": len(left), "lines": 6 * len(left), "paused": False, "dropped": len(missed),
                     "reading": True})


class Cache:
    """The few parts of `BookCache` the indicator reads: its pages (``fingerprint``, ``bubbles`` with their
    translations) and `lookup` (an exact fingerprint only)."""

    def __init__(self) -> None:
        self.pages: list[CachedPage] = []
        self.book = "made-up"

    def put(self, seq: int, texts: list[str]) -> None:
        self.pages = [p for p in self.pages if p.fingerprint != fingerprint(seq)]
        self.pages.append(CachedPage(fingerprint(seq), 0.7, [CachedBubble((0.1, 0.1 * i, 0.3, 0.1 * i + 0.05), t)
                                                             for i, t in enumerate(texts)], seq))

    def lookup(self, fp: str, aspect: float, within: int, hint_seq: Any = None) -> Any:
        hit = next((p for p in self.pages if p.fingerprint == fp), None)
        return (hit, 0) if hit is not None else None


def pipeline(cache: Cache | None = None, rtl: bool = True) -> SimpleNamespace:
    """A pipeline stand-in with what the indicator asks of it: the book's direction, its cache, the fingerprint
    distance."""
    return SimpleNamespace(rtl=rtl, cache=cache if cache is not None else Cache(),
                           settings=SimpleNamespace(fingerprint_max_distance=36), font_status=lambda: ("", None),
                           shown_pages=set())
