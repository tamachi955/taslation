"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: what a page whose translations are cached costs, stage by stage, from
the settled frame to the page drawn in the window.

A stand-in full-screen viewer, in memory, shows OpenMantra pages (or synthetic ones) on its dark ground with a page
counter, as the throwaway browser viewer of the end-to-end checks does. Every page is translated once (a stand-in
reader and translator: canned Japanese, numbered English lines; the real detectors, layout model and LaMa as the
settings ask) into a cache in a temporary folder, then shown again from a fresh capture of the same pixels as a
person turning back to it would: that second pass is timed. Nothing touches a window, nothing is pressed, no page
image is written anywhere, no text of a book is printed; the temporary folder goes at the end.

    python tools/cached_turn_profile.py [--pages 8] [--detect auto|off] [--art auto|lama|off] [--synthetic]
                                        [--frame 1920x1080] [--window 960x1000] [--ahead] [--whole]

``--ahead``: the pages are erased ahead first, as a whole-book run leaves them (`Pipeline.erased_ahead`), so that the
render takes their erase from memory. The table gives the median and the largest time of every stage in ms.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from taslation import fingerprint as fp  # noqa: E402
from taslation.cache import BookCache  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.detect.page_area import find_page_area, page_area_margins  # noqa: E402
from taslation.pageimages import PageImages, pack  # noqa: E402
from taslation.pipeline import Pipeline  # noqa: E402
from taslation.render import typeset  # noqa: E402

GROUND = (0x2B, 0x2B, 0x2B)
JA = ["こんにちは", "ありがとう", "どこへ行くの", "今日はいい天気だね", "大丈夫だよ", "まだ終わってない"]


class StandInOcr:
    """Canned Japanese in call order (the cached pass must not read anything: its calls are counted)."""

    def __init__(self) -> None:
        self.calls = 0

    def read(self, image: Image.Image) -> str:
        self.calls += 1
        return JA[self.calls % len(JA)]


class StandInTranslator:
    name = "stand-in"

    def __init__(self) -> None:
        self.calls = 0

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, **_kw):
        self.calls += 1
        return [f"This is line number {i + 1}, said here." for i in range(len(texts))]


def framed(page: Image.Image, n: int, total: int, size: tuple[int, int]) -> Image.Image:
    """*page* as the throwaway browser viewer shows it full screen: fitted to the screen on its dark ground, the page
    counter at the bottom right and a row of small status cells at the bottom left."""
    w, h = size
    scale = min(w / page.width, h / page.height)
    shown = page.convert("RGB").resize((max(1, int(page.width * scale)), max(1, int(page.height * scale))), Image.LANCZOS)
    out = Image.new("RGB", size, GROUND)
    out.paste(shown, ((w - shown.width) // 2, (h - shown.height) // 2))
    d = ImageDraw.Draw(out)
    d.text((w - 70, h - 24), f"{n + 1} / {total}", fill=(0x8A, 0x8A, 0x8A))
    for k in range(24):
        d.rectangle((8 + k * 8, h - 16, 13 + k * 8, h - 11), fill=(0x90, 0x90, 0x90) if (n >> (k % 8)) & 1 else (0x10, 0x10, 0x10))
    return out


def load_pages(count: int, synthetic: bool) -> list[Image.Image]:
    if not synthetic:
        try:
            import openmantra
            pages = openmantra.load()[:count]
            if pages:
                return [Image.open(p.image).convert("RGB") for p in pages]
        except Exception as e:  # noqa: BLE001
            print(f"(no OpenMantra pages: {type(e).__name__}; synthetic pages instead)")
    fixtures = sorted((ROOT / "tests" / "fixtures").glob("*.png"))
    return [Image.open(fixtures[i % len(fixtures)]).convert("RGB") for i in range(count)]


_ACC: dict[str, float] = defaultdict(float)


def timed(owner, name: str, label: str) -> None:
    """Wrap *owner*.*name* so that its time goes to *label* (inclusive time; nested labels are told apart)."""
    fn = getattr(owner, name)

    def wrapper(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            _ACC[label] += time.perf_counter() - t
    setattr(owner, name, wrapper)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--detect", default="auto")
    ap.add_argument("--art", default="auto", help="art_erase: auto (only where torch has a CUDA GPU, as the app's "
                                                    "default), lama (on the CPU too) or off")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--frame", default="1920x1080")
    ap.add_argument("--window", default="960x1000")
    ap.add_argument("--ahead", action="store_true")
    ap.add_argument("--whole", action="store_true", help="draw the whole frame (no trim to the page)")
    ap.add_argument("--models", default=os.environ.get("TASLATION_MODELS_DIR", str(ROOT / "models")))
    args = ap.parse_args()
    fw, fh = (int(v) for v in args.frame.split("x"))
    ww, wh = (int(v) for v in args.window.split("x"))

    pages = load_pages(args.pages, args.synthetic)
    frames = [framed(p, i, len(pages), (fw, fh)) for i, p in enumerate(pages)]
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(state_dir=Path(tmp), models_dir=Path(args.models), detect_model=args.detect,
                            art_erase=args.art)
        settings.validate()
        box = find_page_area(frames[0])
        settings.margins = page_area_margins(box, frames[0].size)
        cache = BookCache(Path(tmp) / "cache.json", "profile book", "stand-in")
        ocr, translator = StandInOcr(), StandInTranslator()
        pipe = Pipeline(settings, ocr=ocr, translator=translator, cache=cache)
        t = time.perf_counter()
        firsts = [pipe.process(f.copy()) for f in frames]
        print(f"first pass (cache filled): {len(frames)} pages in {time.perf_counter() - t:.1f} s, "
              f"{sum(len([r for r in res.regions if r.status == 'translated']) for res in firsts)} lines; "
              f"margins {tuple(settings.margins)}; layout {'on' if pipe.layout else 'off'}, "
              f"LaMa {'on' if pipe.art_eraser else 'off'}")
        if args.ahead:
            store = PageImages(1 << 33)
            for seq, f in enumerate(frames, 1):  # as the whole-book run erases a page it has read
                erasable = pipe.scan(f.copy(), skip_cached=False, keep_regions=True).erasable
                erased, records = pipe.erase_page(f, erasable)
                store.put_erased(seq, pack(Image.fromarray(erased)), records, erased.shape[:2])
            pipe.erased_ahead = store

        for owner, name, label in [
            (fp, "analyze", "fingerprint (analyze)"),
            (pipe, "_detect", "detect (all)"),
            (pipe, "_detect_classical", "  detect: classical"),
            (pipe, "_annotate", "annotate"),
            (pipe, "_lookup", "cache lookup"),
            (pipe, "_apply_cached", "apply cached"),
            (pipe, "_ocr_regions", "OCR"),
            (pipe, "_translate_regions", "translate"),
            (pipe, "_render", "render (all)"),
            (pipe, "_erased_for", "  render: erase-ahead lookup"),
            (pipe, "_erase", "  render: erase live"),
            (pipe, "cap_sizes", "  render: size caps"),
            (pipe, "_set_text", "  render: typeset (incl. caps)"),
        ]:
            timed(owner, name, label)
        if hasattr(pipe, "shown_pages"):
            timed(pipe, "_shown_key", "memo: key of the page shown")
            timed(pipe.shown_pages, "put", "memo: page kept")
            timed(pipe, "_early_look", "early look (paper fill, lettered)")
        if pipe.layout is not None:
            timed(pipe.layout, "boxes", "  detect: layout model")
        if pipe.art_eraser is not None:
            timed(pipe.art_eraser, "erase", "  render: LaMa")

        import tkinter as tk
        from taslation.ui.preview import ImageCanvas
        root = tk.Tk()
        root.withdraw()
        top = tk.Toplevel(root)
        top.geometry(f"{ww}x{wh}+-3000+-3000")  # off screen
        canvas = ImageCanvas(top, bg="#202020", width=ww - 20, height=wh - 140)
        canvas.pack(fill="both", expand=True)
        if args.whole:
            canvas.trim = False
        top.update()

        ocr.calls = translator.calls = 0
        passes = {}
        for name in ("first view (fresh session)", "shown again (same session)"):
            if name.startswith("first"):
                for memo in ("shown_pages", "erased_regions"):  # a new session: nothing lettered or erased yet
                    if hasattr(pipe, memo):
                        getattr(pipe, memo).clear()
                with typeset._LAYOUTS_LOCK:  # nor laid out
                    typeset._LAYOUTS.clear()
            times: dict[str, list[float]] = defaultdict(list)
            shown_w = []
            for f in frames:
                _ACC.clear()
                capture = Image.fromarray(np.asarray(f).copy())  # a new capture of the same pixels
                early: list[float] = []

                def events(kind, data, early=early):
                    if kind == "page" and data.get("early"):
                        early.append(time.perf_counter())
                t0 = time.perf_counter()
                res = pipe.process(capture, events=events)
                t1 = time.perf_counter()
                canvas.set_image(res.image)
                top.update_idletasks()
                t2 = time.perf_counter()
                for k, v in _ACC.items():
                    times[k].append(v * 1000)
                times["pipeline total"].append((t1 - t0) * 1000)
                times["draw (fit + PhotoImage + canvas)"].append((t2 - t1) * 1000)
                if early:
                    times["settled frame -> early look sent"].append((early[0] - t0) * 1000)
                    times["settled frame -> first page drawn"].append((early[0] - t0) * 1000 + (t2 - t1) * 1000)
                else:
                    times["settled frame -> first page drawn"].append((t2 - t0) * 1000)
                times["settled frame -> finished page drawn"].append((t2 - t0) * 1000)
                page = pages[len(shown_w) % len(pages)]
                shown_w.append(canvas.scale * page.width * min(fw / page.width, fh / page.height))
            passes[name] = (times, shown_w)
        root.destroy()

    store = pipe.erased_ahead
    if store is not None:
        print(f"erase ahead: {store.reused} region(s) reused, {store.erased_live} erased live")
    print(f"cached passes: OCR calls {ocr.calls}, translator calls {translator.calls}; detect {args.detect}, "
          f"art {args.art}, erase ahead {'yes' if args.ahead else 'no'}; {len(frames)} pages")
    order = ["fingerprint (analyze)", "detect (all)", "  detect: classical", "  detect: layout model", "annotate",
             "cache lookup", "apply cached", "OCR", "translate", "render (all)", "  render: erase-ahead lookup",
             "  render: erase live", "  render: LaMa", "  render: size caps", "  render: typeset (incl. caps)",
             "pipeline total", "draw (fit + PhotoImage + canvas)", "settled frame -> early look sent",
             "settled frame -> first page drawn", "settled frame -> finished page drawn"]
    for name, (times, shown_w) in passes.items():
        print(f"\n{name}")
        print(f"{'stage':42s} {'median':>8s} {'max':>8s}  (ms)")
        for k in order + [k for k in times if k not in order]:
            v = times.get(k)
            if v:
                print(f"{k:42s} {statistics.median(v):8.1f} {max(v):8.1f}")
        if shown_w:
            print(f"the page itself drawn {statistics.median(shown_w):.0f} px wide in a {ww}x{wh} canvas")


if __name__ == "__main__":
    main()
