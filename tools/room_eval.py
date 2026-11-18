"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: whether the lettering of a page's regions runs into each other's.

Each region of a page is lettered in a room of its own (its mask, `Pipeline._set_text`). Where two rooms overlap -
bubbles drawn fused, a block of text found beside a bubble, the layout model's boxes of two bubbles that touch - two
translations can be set over each other. This tool runs detection and the OCR over pages (the OpenMantra dataset by
default, `tools/openmantra.py`; or the frames of a book's dev snapshots, ``--frames``), letters every region read as
Japanese with canned English of a realistic length (invented words, deterministic: the length of the professional
English of the gold box it matches, else 1.8 characters for each Japanese one; no model is asked), as the page's
render letters it (`Pipeline._render`), and reports, numbers only:

* ``rooms``: pairs of lettered regions whose rooms intersect (the masks the lettering was set in, as `letter_text`
  got them), their pixels and the largest share of the smaller room;
* ``ink``: pairs whose lettering's ink (the pixels each region's lettering changed, seen one region at a time) touch
  (``ink_px``: within a pixel), pairs whose lines' boxes intersect (``line_boxes``: each line of ink as its band of
  rows), and pairs whose lettering's whole boxes intersect (``ink_boxes``; reported, not a failure: two lobes offset
  diagonally have intersecting boxes and separate lines); regions whose ink lies outside their own room
  (``outside``);
* the regions' boxes that intersect (``boxes``; reported, not a failure);
* fragments: lettered regions whose text box is under ``TINY_PX`` on its short side (``tiny``), whose box lies
  ``NESTED`` inside another lettered region's (``nested``), and pairs of horizontal text regions that are adjacent
  lines of one paragraph (``paragraph``: the same glyph height within ``SAME_SIZE``, a gap under a line, overlapping
  sideways);
* against the gold boxes (OpenMantra): regions holding two gold texts or more (``merged``: each gold box at least
  ``HOLDS`` inside the region's box and its lettering meeting the region's text box) and gold texts split over two
  regions or more (``split``: two text boxes or more at least ``HOLDS`` inside one gold box);
* the sizes the lettering was set at, per gold box (``--json``), so that two runs can be compared
  (``--compare a.json b.json``: the sizes of the regions matched to the same gold box, ordinary regions only).

``--pictures DIR`` draws the worst cases (the original crop beside the lettered one, each region's room outlined in a
colour of its own, the gold boxes in blue on the original) and a fixed sample of ordinary regions (``--ordinary``) into
DIR, with ``cases.json`` listing them; ``--again cases.json`` draws those very crops again (after a change, under
``--tag``). Pictures are for the developer's eyes only: they go to the folder given (a scratch folder), never into the
repository. ``--scan FILE`` keeps the detection and the OCR (the regions and their masks; the Japanese is never
written: only its length) and letters from FILE again when the settings agree (the settings are all it checks: after
a change of the detection, start from a new FILE).

    python tools/room_eval.py --pictures <scratch>/before --json <scratch>/before.json --scan <scratch>/scan.pkl
    python tools/room_eval.py --detect-model on --pages 6
    python tools/room_eval.py --frames "~/.taslation/dev-snapshots/<book>/screen_*.png" --pictures <scratch>/frames
    python tools/room_eval.py --compare <scratch>/before.json <scratch>/after.json

Nothing goes over the network (the socket guard is installed first); the state folder should be a scratch one
(``TASLATION_STATE_DIR``): nothing is written to it.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import pickle
import random
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

import openmantra  # noqa: E402
from taslation import netguard  # noqa: E402

SCAN_VERSION = 1
TINY_PX = 10  # a lettered region whose text box is narrower than this on its short side is a fragment
NESTED = 0.8  # of a region's box inside another lettered region's: a fragment of it
SAME_SIZE = 1.35  # two lines of one paragraph have glyphs this alike in height at most
HOLDS = 0.6  # of a box inside another: held by it
OUTSIDE_PX = 20  # ink pixels outside a region's room (grown by 2 px) that count as lettering outside it
COLOURS = [(230, 25, 75), (60, 180, 75), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230),
           (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128)]
WORDS = ("I", "you", "we", "it", "the", "a", "to", "and", "of", "is", "that", "what", "this", "can't", "don't",
         "really", "never", "always", "there", "here", "about", "think", "know", "want", "going", "right", "little",
         "something", "everyone", "nothing", "together", "remember", "tonight", "yesterday", "already", "maybe",
         "please", "wait", "come", "back", "home", "school", "friend", "brother", "teacher", "morning", "should",
         "would", "could", "because", "though", "anyway", "seriously", "probably", "important", "different")

Box = tuple[int, int, int, int]


def canned(n: int, seed: str) -> str:
    """Invented English of about *n* characters (at least two), the same for the same *seed*: a sentence or two."""
    rnd = random.Random(seed)
    words: list[str] = []
    while len(" ".join(words)) < max(2, n):
        words.append(rnd.choice(WORDS))
    text = " ".join(words)
    if len(words) >= 6:
        cut = len(words) // 2
        text = " ".join(words[:cut]) + ". " + " ".join(words[cut:]).capitalize()
    return text[0].upper() + text[1:] + rnd.choice((".", "!", "?", "...", "!?"))


def inter(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def area(a: Sequence[float]) -> float:
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def japanese_chars(text: str) -> int:
    return sum(1 for ch in text if ord(ch) >= 0x3000)


# ------------------------------------------------------------------ pages
class Item:
    """A page to measure: its name, how to open it, its gold boxes (with their English lengths and whether worded)."""

    def __init__(self, series: str, index: int, opener: Any, gold: list[tuple[Box, int, bool]], margins: Any = None):
        self.series, self.index, self.open, self.gold, self.margins = series, index, opener, gold, margins

    @property
    def key(self) -> str:
        return f"{self.series}#{self.index}"


def dataset_items(root: Path, series: Sequence[str] | None, pages: int) -> list[Item]:
    from openmantra_eval import worded

    found = openmantra.load(root, series)
    groups = openmantra.by_series(found)
    out = []
    for name, group in groups.items():
        for page in group[: pages or None]:
            gold = [(b.box, len(b.en), worded(b.ja)) for b in page.bubbles]
            out.append(Item(name, page.index, page.open, gold))
    return out


def frame_items(pattern: str) -> list[Item]:
    from PIL import Image

    files = sorted(glob.glob(str(Path(pattern).expanduser())))
    out = []
    for n, path in enumerate(files, 1):
        manifest = Path(path).parent / "manifest.json"
        margins = None
        if manifest.is_file():
            margins = json.loads(manifest.read_text(encoding="utf-8")).get("margins")

        def opener(path: str = path) -> Any:
            with Image.open(path) as im:
                return im.convert("RGB")

        out.append(Item("frames", n, opener, [], margins))
    return out


# ------------------------------------------------------------------ detection and OCR, kept without the Japanese
def _strip(obj: Any, seen: set[int]) -> None:
    """Every text a region holds blanked (in place): the scan file keeps no Japanese."""
    from taslation.regions import TextRegion

    if obj is None or id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, TextRegion):
        obj.source_text = ""
        obj.translated_text = ""
        obj.reused_text = ""
        obj.ocr_reading = None
        obj.speaker = obj.remark = ""
        for name in ("adopted", "repeats", "after"):
            _strip(getattr(obj, name, None), seen)
    elif hasattr(obj, "__dict__"):
        for value in vars(obj).values():
            if hasattr(value, "__dict__"):
                _strip(value, seen)


def _no_japanese(obj: Any, seen: set[int] | None = None) -> bool:
    """Whether no string reachable from *obj* holds a CJK character (checked before the scan file is written)."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return True
    seen.add(id(obj))
    if isinstance(obj, str):
        return not any(ord(ch) >= 0x3000 for ch in obj)
    if isinstance(obj, dict):
        return all(_no_japanese(k, seen) and _no_japanese(v, seen) for k, v in obj.items())
    if isinstance(obj, (list, tuple, set, deque)):
        return all(_no_japanese(v, seen) for v in obj)
    if hasattr(obj, "__dict__"):
        return all(_no_japanese(v, seen) for v in vars(obj).values())
    return True


def detect_page(pipe: Any, item: Item, image: Any) -> dict[str, Any]:
    """The regions the page reads as Japanese text (detection and OCR as `Pipeline.process` does them), each with the
    length of its reading only, and the book's sizes after it (what `_display_size` hangs on)."""
    if item.margins is not None:
        pipe.settings.margins = tuple(item.margins)
    res = pipe.process(image, translate=False, use_cache=False)
    regions = [r for r in res.regions if r.status == "untranslated" and r.source_text]
    lengths = [max(1, japanese_chars(r.source_text)) for r in regions]
    kept = copy.deepcopy(regions)
    seen: set[int] = set()
    for r in kept:
        _strip(r, seen)
    return {"regions": kept, "lengths": lengths, "sizes": list(pipe._book_sizes), "candidates": len(res.regions)}


# ------------------------------------------------------------------ lettering, one region at a time
class Recorder:
    """`Pipeline._set_text` and the `letter_text` it calls, watched: per region, the room it was lettered in (in page
    coordinates) and the pixels its lettering changed."""

    def __init__(self, pipe: Any):
        import taslation.pipeline as pl

        self.pl = pl
        self.pipe = pipe
        self.current: Any = None
        self.rooms: dict[int, tuple[Box, np.ndarray]] = {}
        self.ink: dict[int, np.ndarray] = {}
        self._letter = pl.letter_text
        self._set = pipe._set_text

        def set_text(image, region, text, background, style, scaled=True):
            held, self.current = self.current, region
            try:
                return self._set(image, region, text, background, style, scaled)
            finally:
                self.current = held

        def letter(image, region, text, *a, **k):
            if image is None or self.current is None:
                return self._letter(image, region, text, *a, **k)
            before = np.asarray(image.convert("RGB")).copy()
            done = self._letter(image, region, text, *a, **k)
            after = np.asarray(image.convert("RGB"))
            key = id(self.current)
            self.ink[key] = np.any(after != before, axis=2)
            mask = region.mask
            if mask.shape != (region.height, region.width):
                import cv2

                mask = cv2.resize(mask, (region.width, region.height), interpolation=cv2.INTER_NEAREST)
            self.rooms[key] = (region.bbox, mask > 0)
            return done

        pipe._set_text = set_text
        pl.letter_text = letter

    def close(self) -> None:
        self.pl.letter_text = self._letter
        self.pipe._set_text = self._set


def _page_room(shape: tuple[int, int], box: Box, mask: np.ndarray) -> np.ndarray:
    out = np.zeros(shape, bool)
    x0, y0, x1, y1 = box
    h, w = shape
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if cx1 > cx0 and cy1 > cy0:
        out[cy0:cy1, cx0:cx1] = mask[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    return out


def _bbox(mask: np.ndarray) -> Box | None:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _line_boxes(ink: np.ndarray, box: Box | None) -> list[Box]:
    """The lines of a region's lettering: its ink's bands of rows (separated by a row without ink), each as a box."""
    if box is None:
        return []
    x0, y0, x1, y1 = box
    rows = ink[y0:y1, x0:x1].any(axis=1)
    out: list[Box] = []
    start = None
    for i, on in enumerate(list(rows) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            band = ink[y0 + start:y0 + i, x0:x1]
            cols = np.flatnonzero(band.any(axis=0))
            out.append((x0 + int(cols[0]), y0 + start, x0 + int(cols[-1]) + 1, y0 + i))
            start = None
    return out


def letter_page(pipe: Any, item: Item, image: Any, scan: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """The page lettered as `_render` letters it, with what each lettered region did."""
    from openmantra_eval import match

    regions = copy.deepcopy(scan["regions"])
    pipe._book_sizes = deque(scan["sizes"], maxlen=pipe._book_sizes.maxlen)
    gold = [g for g, _n, _w in item.gold]
    pairs = {ri: gi for gi, ri, _v in match(gold, [(r.bbox, r.text_box) for r in regions])}
    for i, (r, n) in enumerate(zip(regions, scan["lengths"])):
        gi = pairs.get(i)
        length = item.gold[gi][1] if gi is not None and item.gold[gi][1] else round(1.8 * n)
        r.translated_text = canned(length, f"{item.key}/{i}")
        r.status = "translated"
    rgb = np.asarray(image.convert("RGB")).copy()
    rec = Recorder(pipe)
    try:
        pipe._render(rgb, regions)
    finally:
        rec.close()
    shape = rgb.shape[:2]
    rows = []
    for i, r in enumerate(regions):
        room = rec.rooms.get(id(r))
        ink = rec.ink.get(id(r), np.zeros(shape, bool))
        page_room = _page_room(shape, *room) if room is not None else np.zeros(shape, bool)
        ib = _bbox(ink)
        rows.append({"i": i, "region": r, "room": page_room, "ink": ink, "ink_box": ib, "lines": _line_boxes(ink, ib),
                     "gold": pairs.get(i), "size": int(r.font_size), "kind": r.kind, "box": list(r.bbox),
                     "text_box": list(r.text_box), "from_model": bool(r.from_model)})
    return rgb, rows


# ------------------------------------------------------------------ the measures of a page
def measure(item: Item, rows: list[dict[str, Any]]) -> dict[str, Any]:
    import cv2

    out: dict[str, Any] = {"page": item.key, "lettered": len(rows), "rooms": [], "ink_px": [], "line_boxes": [],
                           "ink_boxes": [], "boxes": 0, "outside": [], "tiny": [], "nested": [], "paragraph": [],
                           "merged": [], "split": []}
    grown = [cv2.dilate(row["ink"].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0 for row in rows]
    for a in range(len(rows)):
        ra = rows[a]
        for b in range(a + 1, len(rows)):
            rb = rows[b]
            if inter(ra["box"], rb["box"]) > 0:
                out["boxes"] += 1
            both = int((ra["room"] & rb["room"]).sum())
            if both:
                smaller = max(1, min(int(ra["room"].sum()), int(rb["room"].sum())))
                out["rooms"].append([a, b, both, round(both / smaller, 3)])
            touching = int((grown[a] & rows[b]["ink"]).sum())
            if touching:
                out["ink_px"].append([a, b, touching])
            if any(inter(la, lb) > 0 for la in ra["lines"] for lb in rb["lines"]):
                out["line_boxes"].append([a, b])
            if ra["ink_box"] and rb["ink_box"] and inter(ra["ink_box"], rb["ink_box"]) > 0:
                out["ink_boxes"].append([a, b])
    for a, row in enumerate(rows):
        room = cv2.dilate(row["room"].astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        beyond = int((row["ink"] & ~room).sum())
        if beyond > OUTSIDE_PX:
            out["outside"].append([a, beyond])
        tb = row["text_box"]
        if min(tb[2] - tb[0], tb[3] - tb[1]) < TINY_PX:
            out["tiny"].append(a)
        for b, other in enumerate(rows):
            if b != a and inter(row["box"], other["box"]) >= NESTED * max(1.0, area(row["box"])) \
                    and area(row["box"]) <= area(other["box"]):
                out["nested"].append([a, b])
                break
    across = [a for a, row in enumerate(rows) if (row["text_box"][2] - row["text_box"][0])
              > 1.2 * (row["text_box"][3] - row["text_box"][1])]
    for p, a in enumerate(across):
        ta = rows[a]["text_box"]
        for b in across[p + 1:]:
            tb = rows[b]["text_box"]
            ha, hb = ta[3] - ta[1], tb[3] - tb[1]
            if max(ha, hb) > SAME_SIZE * max(1, min(ha, hb)):
                continue
            gap = max(tb[1] - ta[3], ta[1] - tb[3])
            sideways = min(ta[2], tb[2]) - max(ta[0], tb[0])
            if gap < max(ha, hb) and sideways > 0.3 * min(ta[2] - ta[0], tb[2] - tb[0]):
                out["paragraph"].append([a, b])
    worded = [(gi, g) for gi, (g, _n, w) in enumerate(item.gold) if w]
    for a, row in enumerate(rows):
        held = [gi for gi, g in worded if inter(g, row["box"]) >= HOLDS * max(1.0, area(g))
                and inter(g, row["text_box"]) > 0]
        if len(held) >= 2:
            out["merged"].append([a, held])
    for gi, g in worded:
        parts = [a for a, row in enumerate(rows) if inter(row["text_box"], g) >= HOLDS * max(1.0, area(row["text_box"]))]
        if len(parts) >= 2:
            out["split"].append([gi, parts])
    return out


# ------------------------------------------------------------------ pictures
def picture(original: np.ndarray, lettered: np.ndarray, crop: Box, rows: list[dict[str, Any]],
            gold: Sequence[Box], focus: Sequence[int] = ()) -> Any:
    """The original crop (gold boxes in blue, the regions' boxes in their colours) beside the lettered one (each
    region's room outlined in its colour; the regions of the case thicker), as a PIL image."""
    import cv2
    from PIL import Image

    x0, y0, x1, y1 = crop
    left = original[y0:y1, x0:x1].copy()
    right = lettered[y0:y1, x0:x1].copy()
    for g in gold:
        if inter(g, crop) > 0:
            cv2.rectangle(left, (g[0] - x0, g[1] - y0), (g[2] - x0 - 1, g[3] - y0 - 1), (40, 90, 255), 1)
    for k, row in enumerate(rows):
        sub = row["room"][y0:y1, x0:x1].astype(np.uint8)
        if not sub.any():
            continue
        colour = COLOURS[k % len(COLOURS)]
        contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(right, contours, -1, colour, 2 if row["i"] in focus else 1)
        bx0, by0, bx1, by1 = row["box"]
        cv2.rectangle(left, (bx0 - x0, by0 - y0), (bx1 - x0 - 1, by1 - y0 - 1), colour, 1)
    gap = np.full((left.shape[0], 6, 3), 255, np.uint8)
    both = np.concatenate([left, gap, right], axis=1)
    scale = min(1.0, 1400.0 / both.shape[1])
    img = Image.fromarray(both)
    if scale < 1.0:
        img = img.resize((int(both.shape[1] * scale), int(both.shape[0] * scale)), Image.LANCZOS)
    return img


def _crop_of(boxes: Sequence[Sequence[int]], shape: tuple[int, int], margin: int = 40) -> Box:
    h, w = shape
    return (max(0, min(b[0] for b in boxes) - margin), max(0, min(b[1] for b in boxes) - margin),
            min(w, max(b[2] for b in boxes) + margin), min(h, max(b[3] for b in boxes) + margin))


# ------------------------------------------------------------------ the run
def totals(pages: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("rooms", "ink_px", "line_boxes", "ink_boxes", "outside", "tiny", "nested", "paragraph", "merged", "split")
    out: dict[str, Any] = {"pages": len(pages), "lettered": sum(p["lettered"] for p in pages),
                           "boxes": sum(p["boxes"] for p in pages)}
    for k in keys:
        out[k] = sum(len(p[k]) for p in pages)
    out["rooms_px"] = sum(r[2] for p in pages for r in p["rooms"])
    out["rooms_share_max"] = max((r[3] for p in pages for r in p["rooms"]), default=0.0)
    return out


def compare(a_path: Path, b_path: Path) -> int:
    a, b = json.loads(a_path.read_text(encoding="utf-8")), json.loads(b_path.read_text(encoding="utf-8"))
    print("totals          " + "  ".join(f"{k}" for k in a["totals"]))
    for name, run in (("A", a), ("B", b)):
        print(f"  {name:13} " + "  ".join(f"{run['totals'].get(k, '')}" for k in a["totals"]))
    sa = {k: v for k, v in a["sizes"].items()}
    sb = {k: v for k, v in b["sizes"].items()}
    common = sorted(set(sa) & set(sb))
    ordinary = [k for k in common if sa[k][1] and sb[k][1]]
    diffs = [sb[k][0] - sa[k][0] for k in ordinary]
    if diffs:
        smaller = sum(1 for d in diffs if d < 0)
        larger = sum(1 for d in diffs if d > 0)
        print(f"sizes of {len(ordinary)} ordinary regions matched to the same gold box: mean A {np.mean([sa[k][0] for k in ordinary]):.2f}, "
              f"B {np.mean([sb[k][0] for k in ordinary]):.2f}; smaller in B {smaller}, larger {larger}, same {len(diffs) - smaller - larger}")
        worst = sorted(((sb[k][0] - sa[k][0], k) for k in ordinary))[:12]
        print("most shrunk: " + ", ".join(f"{k} {d:+d}" for d, k in worst if d < 0))
    return 0


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT)
    ap.add_argument("--series", action="append")
    ap.add_argument("--pages", type=int, default=0, help="only the first N pages of every series")
    ap.add_argument("--frames", help="a glob of frames (a book's dev snapshots) in place of the dataset")
    ap.add_argument("--detect-model", choices=("auto", "on", "off"))
    ap.add_argument("--scan", type=Path, help="keep the detection and the OCR here (no Japanese, no image)")
    ap.add_argument("--json", type=Path, help="the numbers, per page, and the sizes per gold box")
    ap.add_argument("--pictures", type=Path, help="a scratch folder for pictures of the worst cases")
    ap.add_argument("--worst", type=int, default=12, help="pictures per kind of case")
    ap.add_argument("--ordinary", type=int, default=12, help="pictures of ordinary regions (a fixed sample)")
    ap.add_argument("--again", type=Path, help="the cases.json of an earlier run: draw those crops again")
    ap.add_argument("--tag", default="", help="a prefix for the pictures' names")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"))
    args = ap.parse_args(argv)
    if args.compare:
        return compare(*args.compare)

    from taslation.config import Settings
    from taslation.ocr import Readers
    from taslation.pipeline import Pipeline

    s = Settings()
    s.art_erase = "off"  # (the paper fill: the rooms and the lettering do not hang on how the art is erased)
    if args.detect_model:
        s.detect_model = args.detect_model
    s.validate()
    items = frame_items(args.frames) if args.frames else dataset_items(args.root, args.series, args.pages)
    settings_key = {"version": SCAN_VERSION, "detect_model": s.detect_model, "pages": [i.key for i in items],
                    "frames": bool(args.frames)}
    scans: dict[str, Any] = {}
    if args.scan and args.scan.exists():
        with open(args.scan, "rb") as f:
            held = pickle.load(f)
        if held.get("key") == settings_key:
            scans = held["pages"]
            print(f"detection and OCR from {args.scan}", flush=True)
    pipe = Pipeline(s, ocr=None if scans else Readers(s.models_dir, s.ocr_threads), translator=None, cache=None)
    t0 = time.monotonic()
    pages: list[dict[str, Any]] = []
    sizes: dict[str, list[Any]] = {}
    cases: list[dict[str, Any]] = []
    again = json.loads(args.again.read_text(encoding="utf-8")) if args.again else []
    fresh: dict[str, Any] = {}
    rnd = random.Random(7)
    for item in items:
        image = item.open()
        scan = scans.get(item.key)
        if scan is None:
            scan = detect_page(pipe, item, image)
            fresh[item.key] = scan
        if item.margins is not None:
            pipe.settings.margins = tuple(item.margins)
        lettered, rows = letter_page(pipe, item, image, scan)
        m = measure(item, rows)
        pages.append(m)
        bad = {k for p in m["rooms"] + m["ink_px"] + m["line_boxes"] for k in p[:2]}
        for row in rows:
            if row["gold"] is not None:
                sizes[f"{item.key}/{row['gold']}"] = [row["size"], row["i"] not in bad, row["kind"]]
        print(f"  {item.key}: lettered {m['lettered']}, rooms {len(m['rooms'])}, ink {len(m['ink_px'])}, "
              f"lines {len(m['line_boxes'])}, ink boxes {len(m['ink_boxes'])}, tiny {len(m['tiny'])}, "
              f"nested {len(m['nested'])}, paragraph {len(m['paragraph'])}, merged {len(m['merged'])}, "
              f"split {len(m['split'])}", flush=True)
        if args.pictures:
            original = np.asarray(image.convert("RGB"))
            gold = [g for g, _n, _w in item.gold]
            shape = original.shape[:2]

            def add(tag: str, idx: Sequence[int], weight: float, extra: Sequence[Sequence[int]] = ()) -> None:
                boxes = [rows[k]["box"] for k in idx] + [list(b) for b in extra]
                crop = _crop_of(boxes, shape)
                cases.append({"tag": tag, "page": item.key, "crop": list(crop), "focus": [rows[k]["i"] for k in idx],
                              "weight": weight, "img": picture(original, lettered, crop, rows, gold, idx)})

            for a, b, px, _share in m["rooms"]:
                add("rooms", (a, b), px)
            for a, b, px in m["ink_px"]:
                add("ink", (a, b), px)
            for a, held_gold in m["merged"]:
                add("merged", (a,), len(held_gold), [gold[g] for g in held_gold])
            for gi, parts in m["split"]:
                add("split", parts, len(parts), [gold[gi]])
            for a, b in m["paragraph"]:
                add("paragraph", (a, b), 1)
            for c in again:
                if c["page"] == item.key:
                    crop = tuple(c["crop"])
                    cases.append({**c, "again": True, "img": picture(original, lettered, crop, rows, gold)})
            plain = [row for row in rows if row["gold"] is not None and row["i"] not in bad
                     and not any(row["i"] in p[1] for p in m["split"])]
            if plain and rnd.random() < 0.25:
                row = rnd.choice(plain)
                add("ordinary", (row["i"],), rnd.random())
            if len(cases) > 400:
                cases = _trim(cases, args.worst, args.ordinary)
        del image
    if args.scan and fresh:
        payload = {"key": settings_key, "pages": {**scans, **fresh}}
        if not _no_japanese(payload):
            raise SystemExit("the scan would hold Japanese text: not written")
        with open(args.scan, "wb") as f:
            pickle.dump(payload, f)
    tot = totals(pages)
    tot["seconds"] = round(time.monotonic() - t0, 1)
    print("totals: " + json.dumps(tot), flush=True)
    if args.json:
        args.json.write_text(json.dumps({"totals": tot, "pages": pages, "sizes": sizes,
                                         "settings": {"detect_model": s.detect_model}}, indent=1), encoding="utf-8")
    if args.pictures:
        chosen = _trim(cases, args.worst, args.ordinary)
        args.pictures.mkdir(parents=True, exist_ok=True)
        listed = []
        for c in chosen:
            img = c.pop("img")
            name = f"{args.tag + '-' if args.tag else ''}{c['tag']}-{c['page'].replace('#', '-p')}-{c['crop'][0]}-{c['crop'][1]}.png"
            img.save(args.pictures / name)
            c.pop("again", None)
            listed.append({**c, "file": name})
        (args.pictures / "cases.json").write_text(json.dumps(listed, indent=1), encoding="utf-8")
        print(f"{len(listed)} pictures in {args.pictures}")
    return 0


def _trim(cases: list[dict[str, Any]], worst: int, ordinary: int) -> list[dict[str, Any]]:
    """The cases kept for pictures: those asked again, the heaviest *worst* of each kind, *ordinary* ordinary ones."""
    out = [c for c in cases if c.get("again")]
    for tag in ("rooms", "ink", "merged", "split", "paragraph", "ordinary"):
        group = [c for c in cases if c["tag"] == tag and not c.get("again")]
        group.sort(key=lambda c: -c["weight"])
        out.extend(group[: ordinary if tag == "ordinary" else worst])
    return out


if __name__ == "__main__":
    raise SystemExit(main())
