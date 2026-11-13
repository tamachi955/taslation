"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: keep the screens of a book on disk while working on detection.

The application holds captured pages in memory only and never imports this file. While detection or rendering is
being tuned, walking the viewer for every experiment is slow, so this tool walks it once and saves every distinct
screen as a PNG; scripts then read the screens from disk (``screens()``). The files are page images of a real
book: keep them on this machine, never share them, and remove them with ``wipe`` when the work is done. Releases
leave this tool out.

    python tools/dev_snapshots.py snap --book "<title> 1巻" --window "<the window's title>"   # save every screen
    python tools/dev_snapshots.py list
    python tools/dev_snapshots.py wipe --book "<title> 1巻"      # or: wipe --all

The viewer window must show the book (for a browser-based viewer: its tab in a Chrome window of its own). The walk
goes back to the first screen with the Right arrow and turns pages with the Left arrow (right-to-left books), and
stops at the end of the book. Nothing goes over the network (the socket guard is installed first).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402

ROOT = Path(Settings().state_dir) / "dev-snapshots"
def book_dir(book: str) -> Path:
    return ROOT / re.sub(r'[<>:"/\\|?*\s]+', "_", book).strip("_")


def screens(book: str) -> Iterator[tuple[int, "Image.Image"]]:  # noqa: F821
    """(screen number, capture) for every saved screen of *book*, first screen first."""
    from PIL import Image

    folder = book_dir(book)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["screens"]:
        with Image.open(folder / entry["file"]) as img:
            yield int(entry["screen"]), img.convert("RGB")


def _snap(args: argparse.Namespace) -> int:
    import numpy as np

    from taslation import fingerprint as fp
    from taslation.batch import frames_differ, thumbnail
    from taslation.capture import (bring_to_front, capture_window, click_screen, client_rect_on_screen,
                                   enable_dpi_awareness, list_windows, press_key)

    enable_dpi_awareness()
    win = next((w for w in list_windows() if w.title == args.window), None)
    if win is None:
        print(f"no window titled {args.window!r}: bring the book's tab to the front", file=sys.stderr)
        return 1
    margins = tuple(int(v) for v in args.margins.split(","))

    def end_panel_open() -> bool:  # the browser-based viewer's end-of-book panel (bright, right half)
        return float(np.asarray(capture_window(win.hwnd))[300:800, 1500:1900].mean()) > 200

    def turn(key: str) -> bool:
        ref = thumbnail(capture_window(win.hwnd))
        bring_to_front(win.hwnd)  # (the developer's own key, in this dev tool)
        press_key(win.hwnd, key)
        for _ in range(16):
            time.sleep(0.25)
            if frames_differ(ref, thumbnail(capture_window(win.hwnd))):
                return True
        return False

    if end_panel_open():  # close it with its x
        gray = np.asarray(capture_window(win.hwnd).convert("L"))
        ys, xs = np.nonzero(gray[85:150, 1360:1420] > 235)
        if xs.size:
            cx, cy, _w, _h = client_rect_on_screen(win.hwnd)
            bring_to_front(win.hwnd)
            click_screen(cx + 1360 + int(xs.mean()), cy + 85 + int(ys.mean()))
            time.sleep(2.0)
    unchanged = presses = 0
    while unchanged < 2 and presses < args.max_screens + 50:
        presses += 1
        unchanged = 0 if turn("Right") else unchanged + 1
    folder = book_dir(args.book)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    entries = []
    prev = None
    repeats = 0
    while len(entries) < args.max_screens:
        img = capture_window(win.hwnd)
        if end_panel_open():
            break
        fps = [u.fingerprint for u in fp.analyze(np.asarray(img.convert("RGB")), margins)]
        if prev is not None and fps == prev:
            repeats += 1
            if repeats >= 2:
                break
            turn("Left")
            time.sleep(1.0)
            continue
        repeats = 0
        prev = fps
        name = f"screen_{len(entries) + 1:03d}.png"
        img.convert("RGB").save(folder / name, format="PNG")
        entries.append({"screen": len(entries) + 1, "file": name, "fingerprints": fps, "size": list(img.size)})
        print(f"saved screen {len(entries)}", flush=True)
        turn("Left")
        time.sleep(1.0)
    manifest = {"book": args.book, "window": args.window, "margins": list(margins),
                "captured": time.strftime("%Y-%m-%d %H:%M:%S"), "screens": entries}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(entries)} screen(s) in {folder}")
    return 0


def _list(_args: argparse.Namespace) -> int:
    if not ROOT.is_dir():
        print("no snapshots")
        return 0
    for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            print(f"{manifest['book']}: {len(manifest['screens'])} screen(s), {manifest['captured']}  ({folder})")
        except (OSError, ValueError, KeyError):
            print(f"{folder.name}: incomplete")
    return 0


def _wipe(args: argparse.Namespace) -> int:
    target = ROOT if args.all else book_dir(args.book or "")
    if args.all or args.book:
        if target.exists():
            shutil.rmtree(target)
            print(f"removed {target}")
        else:
            print("nothing to remove")
        return 0
    print("give --book or --all", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snap", help="walk the viewer and save every distinct screen")
    p.add_argument("--book", required=True, help="name for the snapshot folder (the book's title)")
    p.add_argument("--window", required=True, help="the viewer window's whole title (`taslation windows` lists them)")
    p.add_argument("--margins", default="0,85,0,0", help="capture margins left,top,right,bottom (page area)")
    p.add_argument("--max-screens", type=int, default=400)
    p.set_defaults(func=_snap)
    sub.add_parser("list", help="list saved snapshots").set_defaults(func=_list)
    p = sub.add_parser("wipe", help="delete saved snapshots")
    p.add_argument("--book")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=_wipe)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
