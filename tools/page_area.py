"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: see what find_page_area makes of a capture.

Prints, for each capture, its size, the page box found (or None and why), the margins the app would store and the
time taken: numbers only. No image is ever written, and nothing of a page's content is printed.

    python tools/page_area.py bench                              # timing on a synthetic 1920x1080 reader capture
    python tools/page_area.py files a.png b.jpg ...              # image files (synthetic or your own captures)
    python tools/page_area.py window --title "<tab> - Google Chrome"    # one capture of a viewer window (Windows)
    python tools/page_area.py snapshots --book "<title> 1巻"      # the screens dev_snapshots.py saved

``--debug`` adds what was measured (frame levels, viewport, boxes and side states in the 640 px working copy).
``snapshots`` also prints the union of the boxes over all screens: the area the app would keep if it follows the
union rule in taslation/detect/page_area.py. Nothing goes over the network (the socket guard is installed first).
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from taslation import netguard  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _report(name: str, image, debug: bool) -> tuple[int, int, int, int] | None:
    from taslation.detect.page_area import find_page_area, page_area_margins

    size = image.size if hasattr(image, "size") and not hasattr(image, "shape") else (image.shape[1], image.shape[0])
    info: dict = {}
    start = time.perf_counter()
    box = find_page_area(image, debug=info)
    ms = (time.perf_counter() - start) * 1000
    margins = page_area_margins(box, size)
    print(f"{name}: {size[0]}x{size[1]}  box={box}  margins={margins}  {ms:.1f} ms  ({info.get('result', '')})")
    if debug:
        for tried in info.get("tried", []):
            print("    " + ", ".join(f"{k}={v}" for k, v in tried.items()))
    return box


def _synthetic():
    """A 1920x1080 capture: dark browser bars, a black reader frame, the synthetic fixture page fitted, a header's
    letters, a slider and side arrows."""
    from PIL import Image, ImageDraw

    rng = random.Random(1)
    img = Image.new("RGB", (1920, 1080), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1919, 39), fill=(32, 33, 36))
    draw.rectangle((0, 40, 1919, 84), fill=(53, 54, 58))
    draw.rounded_rectangle((150, 47, 1700, 79), 15, fill=(32, 33, 36))
    for x in range(190, 700, 11):
        draw.line((x, 58 + rng.randint(0, 6), x + 6, 66 + rng.randint(0, 6)), fill=(232, 234, 237), width=2)
    page = Image.open(FIXTURES / "sample_page.png").convert("RGB")
    ph = 1080 - 85 - 24
    pw = page.width * ph // page.height
    img.paste(page.resize((pw, ph), Image.LANCZOS), ((1920 - pw) // 2, 97))
    for x in range(810, 1110, 12):
        draw.line((x, 100 + rng.randint(0, 8), x + 7, 108 + rng.randint(0, 8)), fill=(200, 200, 200), width=2)
    draw.rectangle((96, 1058, 1824, 1060), fill=(110, 110, 110))
    for ax, sign in ((26, 1), (1894, -1)):
        draw.line((ax + sign * 12, 558, ax, 582), fill=(180, 180, 180), width=4)
        draw.line((ax, 582, ax + sign * 12, 606), fill=(180, 180, 180), width=4)
    return img, ((1920 - pw) // 2, 97, (1920 - pw) // 2 + pw, 97 + ph)


def _bench(args: argparse.Namespace) -> int:
    import numpy as np

    from taslation.detect.page_area import find_page_area

    img, page = _synthetic()
    arr = np.asarray(img)
    start = time.perf_counter()
    first = find_page_area(arr)
    print(f"page drawn at {page}, found {first}; first call {1000 * (time.perf_counter() - start):.1f} ms")
    for name, subject in (("numpy RGB", arr), ("PIL RGB", img)):
        times = []
        for _ in range(args.runs):
            start = time.perf_counter()
            find_page_area(subject)
            times.append((time.perf_counter() - start) * 1000)
        times.sort()
        print(f"{name}: min {times[0]:.1f} ms, median {times[len(times) // 2]:.1f} ms, max {times[-1]:.1f} ms "
              f"over {args.runs} runs")
    return 0


def _files(args: argparse.Namespace) -> int:
    from PIL import Image

    for path in args.paths:
        with Image.open(path) as img:
            _report(str(path), img.convert("RGB"), args.debug)
    return 0


def _window(args: argparse.Namespace) -> int:
    from taslation.capture import capture_window, enable_dpi_awareness, match_windows

    enable_dpi_awareness()
    found = match_windows(args.title)
    if len(found) != 1:
        print(f"several windows match {args.title!r}: " + "; ".join(w.label() for w in found) if found
              else f"no window whose title contains {args.title!r}")
        return 1
    win = found[0]
    _report(win.title, capture_window(win.hwnd), args.debug)  # held in memory only
    return 0


def _snapshots(args: argparse.Namespace) -> int:
    from dev_snapshots import screens

    union: list[int] | None = None
    found = missing = 0
    for number, img in screens(args.book):
        box = _report(f"screen {number}", img, args.debug)
        if box is None:
            missing += 1
            continue
        found += 1
        union = list(box) if union is None else [min(union[0], box[0]), min(union[1], box[1]),
                                                   max(union[2], box[2]), max(union[3], box[3])]
    print(f"{found} screens with a box, {missing} without; union of the boxes: {tuple(union) if union else None}")
    return 0


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bench", help="time find_page_area on a synthetic 1920x1080 capture")
    p.add_argument("--runs", type=int, default=30)
    p.set_defaults(func=_bench)
    p = sub.add_parser("files", help="run on image files")
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=_files)
    p = sub.add_parser("window", help="run on one capture of a viewer window (Windows)")
    p.add_argument("--title", required=True, help="text in the viewer window's title (`taslation windows` lists them)")
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=_window)
    p = sub.add_parser("snapshots", help="run on the screens saved by dev_snapshots.py")
    p.add_argument("--book", required=True)
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=_snapshots)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
