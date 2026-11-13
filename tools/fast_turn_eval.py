"""How the whole-book run keeps up with a reader who turns pages fast: a stand-in viewer, in memory, shows OpenMantra
pages (or synthetic ones) and a simulated reader turns them at a steady pace; the batch's sampler watches it as it
watches a real viewer (`BatchReader._sample`), with only the capture, the frame count and the window's presence
replaced. Nothing touches a window, nothing is pressed, no page image is written anywhere, no text is printed.

    python tools/fast_turn_eval.py [--pages 40] [--rates 1,2,3] [--soft | --chrome] [--poll] [--synthetic] [--runs 1]

For every pace: pages taken (their sharp picture), pages missed and told (``page_missed``), pages lost untold, pages
told although their sharp picture stayed on show half of settle_ms or more (false missed, must be 0), placeholders the
run ended with for a page it took after all (must be 0), the strip's cells, pages taken twice, soft pictures taken as
the page while the sharp one was on show (false takes, must be 0), soft pictures taken of a page never drawn sharp,
and the sampler's CPU time (its own thread and the packer's). ``--soft`` makes the viewer draw every page soft first
(a smaller picture enlarged) for 150-400 ms, as a browser-based viewer does; ``--chrome`` draws the soft picture as
Chrome draws a canvas scaled down by ``drawImage`` and enlarged again (`chrome_soft`): from a picture of the page six
times smaller, made through a half-size step and then sampled without averaging, so it is not only blurred but
aliased, and its thumbnail differs from the sharp page's by about as much as in Chrome, a quarter more (full screen,
10 OpenMantra pages: 1.3-2.2 grey levels in Chrome, 1.6-2.7 drawn this way; in the tool's frame, which the page
fills, 3-6.6).
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from taslation import batch as batch_mod  # noqa: E402
from taslation.batch import BatchReader  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.pageimages import unpack  # noqa: E402

CANVAS = (900, 1100)  # the stand-in viewer's client area, as tools/fake_viewer.py opens it
GROUND = (0x2B, 0x2B, 0x2B)
SOFT_MS = (150, 400)


def framed(page: Image.Image, n: int, total: int, chrome: bool = False) -> Image.Image:
    """*page* as tools/fake_viewer.py shows it: fitted with 20 px round it on its dark ground, a grey counter.
    *chrome*: the page as Chrome draws it before its sharp picture (`chrome_soft`)."""
    w, h = CANVAS[0] - 40, CANVAS[1] - 40
    scale = min(w / page.width, h / page.height)
    size = (max(1, int(page.width * scale)), max(1, int(page.height * scale)))
    shown = chrome_soft(page, size) if chrome else page.resize(size, Image.LANCZOS)
    out = Image.new("RGB", CANVAS, GROUND)
    out.paste(shown, ((CANVAS[0] - shown.width) // 2, (CANVAS[1] - shown.height) // 2))
    ImageDraw.Draw(out).text((10, 10), f"page {n + 1}/{total}", fill=(0x88, 0x88, 0x88))
    return out


def soft_of(frame: Image.Image, factor: float = 2.5) -> Image.Image:
    """*frame* as a browser draws it before its sharp picture has come: a smaller picture enlarged."""
    small = frame.resize((int(frame.width / factor), int(frame.height / factor)), Image.BILINEAR)
    return small.resize(frame.size, Image.BILINEAR)


CHROME_FACTOR = 6  # the e2e viewer's soft picture: a canvas of the page this many times smaller


def chrome_soft(page: Image.Image, size: tuple[int, int], factor: int = CHROME_FACTOR) -> Image.Image:
    """*page* drawn at *size* as Chrome draws it from a canvas *factor* times smaller (``drawImage`` scaled down, then
    enlarged with smoothing): scaled down to half by averaging (its mipmap), from there to 1/*factor* by sampling two
    neighbours (bilinear, no averaging: aliased), enlarged bilinear. Measured against Chrome on 10 OpenMantra pages,
    its thumbnails differ from the sharp page's in the same order of the pages, a quarter more."""
    a = np.asarray(page.convert("RGB"))
    half = cv2.resize(a, (max(1, a.shape[1] // 2), max(1, a.shape[0] // 2)), interpolation=cv2.INTER_AREA)
    small = cv2.resize(half, (max(1, a.shape[1] // factor), max(1, a.shape[0] // factor)),
                       interpolation=cv2.INTER_LINEAR)
    return Image.fromarray(cv2.resize(small, size, interpolation=cv2.INTER_LINEAR))


def synthetic(i: int) -> Image.Image:
    rng = np.random.default_rng(i + 1)
    a = np.full((1170, 830, 3), 255, np.uint8)
    for x, y, w, h in zip(rng.integers(20, 700, 80), rng.integers(20, 1050, 80), rng.integers(10, 90, 80),
                          rng.integers(10, 90, 80)):
        a[y:y + h, x:x + w] = rng.integers(0, 120)
    return Image.fromarray(a)


def book_pages(count: int, use_synthetic: bool) -> list[Image.Image]:
    if not use_synthetic:
        try:
            import openmantra

            pages = openmantra.load()
            if len(pages) >= count:
                return [p.open("ja") for p in pages[:count]]
        except Exception:  # noqa: BLE001 - no dataset here: synthetic pages
            pass
    return [synthetic(i) for i in range(count)]


def digest(image: Image.Image) -> str:
    return hashlib.sha1(np.asarray(image.convert("RGB")).tobytes()).hexdigest()


class StandIn:
    """The viewer: the picture on show, a frame count that grows at every change (as Windows.Graphics.Capture's), and
    a reader thread that turns at *rate* pages a second."""

    def __init__(self, sharp: list[Image.Image], soft: list[Image.Image] | None, rate: float, seed: int,
                 capture_ms: float = 4.0):
        self.sharp, self.soft = sharp, soft
        self.rate = rate
        self.rng = random.Random(seed)
        self.capture_s = capture_ms / 1000.0
        self.lock = threading.Condition()
        self.image = sharp[0]
        self.seq = 1
        self.done = threading.Event()
        self.sharp_shown = [False] * len(sharp)  # the page's sharp picture was on show at some time
        self.sharp_for = [0.0] * len(sharp)  # the longest its sharp picture stayed on show at a time, seconds
        self._on = (0, True, time.monotonic())  # the picture on show: its page, sharp or not, since when
        self.captures = 0

    def show(self, image: Image.Image, index: int, sharp: bool) -> None:
        with self.lock:
            self._went()
            self.image = image
            self.seq += 1
            if sharp:
                self.sharp_shown[index] = True
            self._on = (index, sharp, time.monotonic())
            self.lock.notify_all()

    def _went(self) -> None:
        index, sharp, since = self._on
        if sharp:
            self.sharp_for[index] = max(self.sharp_for[index], time.monotonic() - since)

    def run(self) -> None:
        period = 1.0 / self.rate
        start = time.monotonic()
        self.sharp_shown[0] = True
        time.sleep(1.0)  # the first page is looked at a while
        for i in range(1, len(self.sharp)):
            due = start + 1.0 + (i - 1) * period
            time.sleep(max(0.0, due - time.monotonic()))
            if self.soft is not None:
                self.show(self.soft[i], i, False)
                soft_s = self.rng.uniform(*SOFT_MS) / 1000.0
                sharp_at = time.monotonic() + soft_s
                next_turn = start + 1.0 + i * period
                if sharp_at < next_turn or i == len(self.sharp) - 1:
                    time.sleep(max(0.0, sharp_at - time.monotonic()))
                    self.show(self.sharp[i], i, True)
            else:
                self.show(self.sharp[i], i, True)
        time.sleep(1.5)  # the last page stays a moment
        with self.lock:
            self._went()
        self.done.set()

    # the capture module's side
    def capture(self, hwnd, client_only=True, allow_screen_fallback=True):
        time.sleep(self.capture_s)
        with self.lock:
            self.captures += 1
            return self.image

    def count(self, hwnd):
        with self.lock:
            return self.seq

    def wait(self, hwnd, seq, timeout):
        with self.lock:
            self.lock.wait_for(lambda: self.seq > seq, timeout)
            return self.seq


def measure(sharp, soft, rate: float, seed: int, poll: bool = False, capture_ms: float = 4.0) -> dict:
    viewer = StandIn(sharp, soft, rate, seed, capture_ms)
    names = {digest(f): (i, True) for i, f in enumerate(sharp)}
    if soft is not None:
        names.update({digest(f): (i, False) for i, f in enumerate(soft)})
    stand_ins = {"capture_window": viewer.capture, "frame_count": (lambda hwnd: None) if poll else viewer.count,
                 "frame_wait": viewer.wait, "window_exists": lambda hwnd: True, "frames_come": lambda hwnd: True}
    before = {name: getattr(batch_mod, name) for name in stand_ins}
    for name, stand_in in stand_ins.items():
        setattr(batch_mod, name, stand_in)
    try:
        return _measure(viewer, names, sharp, rate)
    finally:
        for name, real in before.items():
            setattr(batch_mod, name, real)


def _measure(viewer: StandIn, names: dict, sharp: list, rate: float) -> dict:
    settings = Settings()
    settings.margins = (0, 0, 0, 0)
    told: list[dict] = []
    stages: list[dict] = []

    def show(kind, data):
        if kind == "page_missed":
            told.append(data)
        elif kind == "page_stage":
            stages.append(data)

    reader = BatchReader(SimpleNamespace(ocr=None, translator=None), hwnd=1, settings=settings, preflight=[], show=show)
    told_page: dict[int, int] = {}  # the seq of a page said to have gone by -> the page it was
    real_went_by = reader._went_by

    def went_by(frame):
        before = len(told)
        real_went_by(frame)
        name = names.get(digest(frame))
        if len(told) > before and name is not None:
            told_page[told[-1]["seq"]] = name[0]
    reader._went_by = went_by
    cpu: dict[str, float] = {}
    real_sample = reader._sample

    def sample():
        t0 = time.thread_time()
        real_sample()
        cpu["sampler"] = time.thread_time() - t0

    packer = getattr(reader, "_pack_loop", None)
    if packer is not None:
        def pack_loop():
            t0 = time.thread_time()
            packer()
            cpu["packer"] = time.thread_time() - t0
        reader._pack_loop = pack_loop
    turning = threading.Thread(target=viewer.run, daemon=True)
    sampler = threading.Thread(target=sample, daemon=True)
    t0 = time.monotonic()
    sampler.start()
    turning.start()
    viewer.done.wait()
    reader.finish()
    sampler.join(30)
    wall = time.monotonic() - t0
    reader._sampler_off.set()
    taken: dict[int, bool] = {}  # page -> sharp
    takes: dict[int, int] = {}  # page -> times it went on the backlog
    unknown = 0
    while not reader._backlog.empty():
        item = reader._backlog.get_nowait()
        frame = reader.images.frame(item.key)
        name = names.get(digest(frame)) if frame is not None else None
        if name is None:
            unknown += 1
            continue
        page, is_sharp = name
        taken[page] = taken.get(page, False) or is_sharp
        takes[page] = takes.get(page, 0) + 1
    n = len(sharp)
    missed_seqs = {d.get("seq") for d in told}
    missed_told = len(missed_seqs)
    sharp_taken = sum(1 for v in taken.values() if v)
    false_soft = sum(1 for p, v in taken.items() if not v and viewer.sharp_shown[p])
    soft_never_sharp = sum(1 for p, v in taken.items() if not v and not viewer.sharp_shown[p])
    not_taken = n - len(taken)
    last: dict[int, str] = {}  # seq -> its reading's last state
    for d in stages:
        if d.get("stage") == "read":
            last[d["seq"]] = d["state"]
    still_s = settings.settle_ms / 1000.0 * batch_mod.STILL_SHARE
    # told although its sharp picture stayed on show STILL_SHARE of settle_ms or more (what a page the reader turns on
    # from needs to be taken): it could have been taken, never "missed"
    false_missed = sum(1 for page in set(told_page.values()) if viewer.sharp_for[page] >= still_s)
    # placeholders the run ended with for a page it did take (the strip would show that page twice)
    left = sum(1 for seq, page in told_page.items() if last.get(seq) == "missed" and page in taken)
    return {"rate": rate, "pages": n, "taken_sharp": sharp_taken, "not_taken": not_taken, "told": missed_told,
            "untold": max(0, not_taken - missed_told), "false_missed": false_missed, "placeholders_left": left,
            "cells": sum(1 for state in last.values() if state != "merged"),
            "taken_twice": sum(1 for count in takes.values() if count > 1),
            "false_soft": false_soft, "soft_never_sharp": soft_never_sharp,
            "unknown": unknown, "never_sharp": viewer.sharp_shown.count(False),
            "cpu_sampler_s": round(cpu.get("sampler", 0.0), 2), "cpu_packer_s": round(cpu.get("packer", 0.0), 2),
            "wall_s": round(wall, 1), "captures": viewer.captures}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--rates", default="1,2,3")
    ap.add_argument("--soft", action="store_true", help="draw every page soft first for 150-400 ms")
    ap.add_argument("--chrome", action="store_true",
                    help="draw every page soft first as Chrome draws a canvas scaled down (aliased, 6 times smaller)")
    ap.add_argument("--synthetic", action="store_true", help="synthetic pages instead of OpenMantra")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--poll", action="store_true", help="no frame events: the sampler looks every sample_s (PrintWindow)")
    ap.add_argument("--capture-ms", type=float, default=4.0, help="what a capture costs (PrintWindow: about 30)")
    args = ap.parse_args(argv)
    raw = book_pages(args.pages, args.synthetic)
    sharp = [framed(p, i, len(raw)) for i, p in enumerate(raw)]
    soft = ([framed(p, i, len(raw), chrome=True) for i, p in enumerate(raw)] if args.chrome
            else [soft_of(f) for f in sharp] if args.soft else None)
    for rate in (float(r) for r in args.rates.split(",")):
        for run in range(args.runs):
            print(measure(sharp, soft, rate, seed=run, poll=args.poll, capture_ms=args.capture_ms), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
