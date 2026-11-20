"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: read, list and delete screens a developer keeps for working on detection.

The application holds captured pages in memory only and never imports this file. A developer who tunes detection or
typesetting may keep screens of a book they own under ``~/.taslation/dev-snapshots/<book>/`` (PNG files and a
``manifest.json`` that lists them); the developer's scripts and the gated tests read them from there (``screens()``).
Nothing in this repository saves such screens. They are page images of a real book: they stay on that computer, are
never shared, and ``wipe`` removes them when the work is done.

    python tools/dev_frames.py list
    python tools/dev_frames.py wipe --book "<name>"      # or: wipe --all
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taslation.config import Settings  # noqa: E402

ROOT = Path(Settings().state_dir) / "dev-snapshots"


def book_dir(book: str) -> Path:
    return ROOT / re.sub(r'[<>:"/\\|?*\s]+', "_", book).strip("_")


def screens(book: str) -> Iterator[tuple[int, "Image.Image"]]:  # noqa: F821
    """(screen number, capture) for every kept screen of *book*, first screen first."""
    from PIL import Image

    folder = book_dir(book)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["screens"]:
        with Image.open(folder / entry["file"]) as img:
            yield int(entry["screen"]), img.convert("RGB")


def _list(_args: argparse.Namespace) -> int:
    if not ROOT.is_dir():
        print("no snapshots")
        return 0
    for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            print(f"{len(manifest['screens'])} screen(s), {manifest['captured']}  ({folder})")
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
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the kept snapshots").set_defaults(func=_list)
    p = sub.add_parser("wipe", help="delete kept snapshots")
    p.add_argument("--book")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=_wipe)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
