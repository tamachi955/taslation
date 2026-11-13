"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: read the OpenMantra dataset that ``fetch_openmantra.py`` fetched.

OpenMantra is the evaluation set of "Towards Fully Automated Manga Translation" (Ryota Hinami, Shonosuke
Ishiwatari, Kazuhiko Yasuda, Yusuke Matsui; AAAI 2021), published by Mantra Inc. under CC BY-NC 4.0: five Japanese
manga series with the page images and, for every text region, a box with the Japanese text and professional English
and Chinese translations. It lives outside the repository (``~/.taslation/datasets/openmantra`` by default).

``annotation.json`` is a list of series::

    [{"book_title": "<series>",
      "pages": [{"page_index": 1,                                    # 1-based, in reading order
                 "image_paths": {"ja": "images/<series>/ja/000.jpg"},  # relative to the dataset folder
                 "frame": [{"x": 9, "y": 84, "w": 733, "h": 1080}, ...],  # the panels
                 "text": [{"x": 82, "y": 952, "w": 668, "h": 107,          # a text region, page pixels
                           "text_ja": "...", "text_en": "...", "text_zh": "..."}, ...]},
                ...]},
     ...]

The boxes enclose a text region with a little margin: larger than the lettering, smaller than most bubbles. The
published archive holds the Japanese page images only; English or Chinese ones are picked up when present
(``images/<series>/en/...``). The files are data: paths in the annotation are taken only when they stay inside the
dataset folder, and the JSON is read with the json module. Standard library and Pillow only.

    python tools/openmantra.py [--root DIR]      # counts per series (no text)
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_ROOT = Path.home() / ".taslation" / "datasets" / "openmantra"
LANGUAGES = ("ja", "en", "zh")

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive), page pixels


@dataclass(frozen=True)
class Bubble:
    """One annotated text region: its box and its text in the three languages ("" where there is none)."""

    box: Box
    ja: str
    en: str
    zh: str


@dataclass
class Page:
    series: str
    index: int  # page_index as annotated (1-based)
    image: Path  # the Japanese page image
    images: dict[str, Path] = field(default_factory=dict)  # every language's page image that is on disk
    bubbles: list[Bubble] = field(default_factory=list)
    frames: list[Box] = field(default_factory=list)  # the panels

    @property
    def en_image(self) -> Path | None:
        return self.images.get("en")

    @property
    def zh_image(self) -> Path | None:
        return self.images.get("zh")

    def open(self, language: str = "ja") -> Any:
        """The page image in *language* as an RGB PIL image (in memory; the file is closed again)."""
        from PIL import Image

        path = self.image if language == "ja" else self.images.get(language)
        if path is None:
            raise FileNotFoundError(f"{self.series} page {self.index}: no {language} image")
        with Image.open(path) as im:
            return im.convert("RGB")


def _inside(root: Path, rel: str) -> Path | None:
    """*rel* (a path from the annotation) under *root*, or None when it is absolute or leads outside."""
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        return None
    rel = rel.replace("\\", "/")
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ":" in rel or any(p in ("", "..") for p in pure.parts):
        return None
    path = root.joinpath(*pure.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return path


def _box(item: dict[str, Any]) -> Box | None:
    try:
        x, y, w, h = (int(item[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, x + w, y + h)


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def _images(root: Path, listed: dict[str, Any]) -> tuple[Path | None, dict[str, Path]]:
    """The Japanese image (as annotated, even when missing on disk) and every language's image that is on disk:
    as the annotation lists it, else the Japanese path with its language folder swapped."""
    ja_rel = listed.get("ja") if isinstance(listed.get("ja"), str) else ""
    ja = _inside(root, ja_rel) if ja_rel else None
    found: dict[str, Path] = {}
    for lang in LANGUAGES:
        rel = listed.get(lang) if isinstance(listed.get(lang), str) else ""
        if not rel and ja_rel:
            parts = list(PurePosixPath(ja_rel.replace("\\", "/")).parts)
            folders = parts[:-1]
            if "ja" in folders:
                parts[len(folders) - 1 - folders[::-1].index("ja")] = lang  # the last "ja" folder on the path
                rel = "/".join(parts)
        path = _inside(root, rel) if rel else None
        if path is not None and path.is_file():
            found[lang] = path
    return ja, found


def load(root: Path | str | None = None, series: str | Iterable[str] | None = None) -> list[Page]:
    """The dataset's pages in annotation order (series by series, pages by page_index), optionally only those of
    *series* (a name or several)."""
    root = Path(root) if root is not None else DEFAULT_ROOT
    path = root / "annotation.json"
    if not path.is_file():
        raise FileNotFoundError(f"no OpenMantra annotation at {path}: run tools/fetch_openmantra.py first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("annotation.json is not a list of series")
    wanted = {series} if isinstance(series, str) else (set(series) if series is not None else None)
    pages: list[Page] = []
    for book in data:
        if not isinstance(book, dict) or not isinstance(book.get("book_title"), str):
            continue
        title = book["book_title"]
        if wanted is not None and title not in wanted:
            continue
        book_pages: list[Page] = []
        for raw in book.get("pages") or []:
            if not isinstance(raw, dict):
                continue
            listed = raw.get("image_paths") if isinstance(raw.get("image_paths"), dict) else {}
            ja, images = _images(root, listed)
            if ja is None:
                continue
            bubbles = []
            for item in raw.get("text") or []:
                box = _box(item) if isinstance(item, dict) else None
                if box is not None:
                    bubbles.append(Bubble(box, _text(item, "text_ja"), _text(item, "text_en"), _text(item, "text_zh")))
            frames = [b for b in (_box(f) for f in raw.get("frame") or [] if isinstance(f, dict)) if b is not None]
            try:
                index = int(raw.get("page_index", len(book_pages) + 1))
            except (TypeError, ValueError):
                index = len(book_pages) + 1
            book_pages.append(Page(title, index, ja, images, bubbles, frames))
        pages.extend(sorted(book_pages, key=lambda p: p.index))
    return pages


def series_names(pages: Iterable[Page]) -> list[str]:
    """The series of *pages*, in the order they first appear."""
    return list(dict.fromkeys(p.series for p in pages))


def by_series(pages: Iterable[Page]) -> dict[str, list[Page]]:
    out: dict[str, list[Page]] = {}
    for p in pages:
        out.setdefault(p.series, []).append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Counts of the OpenMantra dataset per series (no text).")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args(argv)
    pages = load(args.root)
    for name, group in by_series(pages).items():
        bubbles = [b for p in group for b in p.bubbles]
        langs = {lang: sum(1 for p in group if lang in p.images) for lang in LANGUAGES}
        print(f"{name:20} pages {len(group):3}  bubbles {len(bubbles):4}  with Japanese {sum(1 for b in bubbles if b.ja.strip()):4}  "
              f"images " + ", ".join(f"{k} {v}" for k, v in langs.items()))
    print(f"{'all':20} pages {len(pages):3}  bubbles {sum(len(p.bubbles) for p in pages):4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
