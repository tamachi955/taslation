"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: reading order on the OpenMantra pages, scored against the annotation.

The annotation's `text` list of a page is taken as its reading order (checked on 2026-11-01: on all 199 pages with two
or more boxes the boxes of a gold panel are consecutive, on 198 the panels come in the order of the `frame` list, and
97 % of consecutive boxes in a panel go leftwards). Prints numbers only, for each set of regions:

* gold: the gold boxes as regions, the page as one unit; pipeline: the regions the detector proposes on the page (no
  OCR; the layout model with --detect-model), in the page units the pipeline makes, scored on those that match a gold
  box at IoU >= 0.5, one to one. Without OCR that is the order before reading, of every candidate.
* rows: `order_regions` without panels. panels: with `find_panels` (for the pipeline, the order it hands over).
  gold panels: with the `frame` boxes (the bound).
* pages fully right, discordant pairs, and per series and per number of gold panels; the pages that got worse.
* the finder against the `frame` boxes, paired one to one at IoU >= 0.5: recall, precision; ms per page.

    python tools/reading_order_eval.py                     # gold boxes and the pipeline's regions
    python tools/reading_order_eval.py --no-pipeline       # gold boxes only (seconds)
    python tools/reading_order_eval.py --detect-model auto # the pipeline's regions with the layout model
    python tools/reading_order_eval.py --series NAME --pages 5

Images stay in memory. Nothing is written but what is printed, unless --out names a file (numbers only).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
from openmantra_eval import match  # noqa: E402 - the scorer's one-to-one pairing
from taslation import netguard  # noqa: E402
from taslation.detect import find_panels, order_regions  # noqa: E402
from taslation.regions import TextRegion  # noqa: E402

Box = tuple[int, int, int, int]
ORDERS = ("rows", "panels", "gold_panels")


def discordant(sequence: Sequence[int]) -> tuple[int, int]:
    """Pairs out of order in *sequence* (positions in the true order), and all pairs."""
    n = len(sequence)
    bad = sum(1 for i in range(n) for j in range(i + 1, n) if sequence[i] > sequence[j])
    return bad, n * (n - 1) // 2


def as_region(box: Box) -> TextRegion:
    x0, y0, x1, y1 = box
    return TextRegion(x0, y0, x1, y1, np.zeros((1, 1), np.uint8), box)


def sequences(regions: Sequence[Any], rank: dict[int, int], panels: dict[str, Sequence[Box] | None]) -> dict[str, list[int]]:
    """Per order, the true position (`rank`, by id of the region) of the scored regions, in that order."""
    out = {}
    for name, boxes in panels.items():
        ordered = order_regions(list(regions), panels=boxes)
        out[name] = [rank[id(r)] for r in ordered if id(r) in rank]
    return out


def shipped(found: Sequence[Any], rank: dict[int, int], frames: Sequence[Box]) -> dict[str, list[int]]:
    """As `sequences`, for the regions as the pipeline hands them over: "panels" is that very order; the others are
    worked out like it, page unit by page unit."""
    units = list(dict.fromkeys(r.unit for r in found))

    def in_units(boxes: Sequence[Box] | None) -> list[Any]:
        return [r for u in units for r in order_regions([q for q in found if q.unit == u], panels=boxes)]

    return {name: [rank[id(r)] for r in regions if id(r) in rank]
            for name, regions in (("rows", in_units(None)), ("panels", found), ("gold_panels", in_units(frames)))}


def panel_class(frames: int) -> str:
    return "0-1 panels" if frames < 2 else "2-3 panels" if frames < 4 else "4-5 panels" if frames < 6 else "6+ panels"


class Tally:
    def __init__(self) -> None:
        self.pages = 0
        self.right = dict.fromkeys(ORDERS, 0)
        self.bad = dict.fromkeys(ORDERS, 0)
        self.pairs = 0

    def add(self, seqs: dict[str, list[int]]) -> None:
        self.pages += 1
        for name, seq in seqs.items():
            bad, pairs = discordant(seq)
            self.right[name] += bad == 0
            self.bad[name] += bad
        self.pairs += pairs

    def row(self, label: str) -> str:
        cells = [f"{label:<24}{self.pages:>5}"]
        for name in ORDERS:
            cells.append(f"{100 * self.right[name] / max(1, self.pages):6.1f} %{100 * self.bad[name] / max(1, self.pairs):6.1f} %")
        return " |".join(cells)


def report(title: str, tallies: dict[str, Tally], worse: list[str], better: int) -> None:
    print(f"\n{title}: pages fully right, discordant pairs")
    print(f"{'':<24}pages | " + " | ".join(f"{n:^15}" for n in ORDERS))
    for label, tally in tallies.items():
        print(tally.row(label))
    print(f"pages better with panels: {better}; worse: {len(worse)}")
    for line in worse:
        print("  worse:", line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT)
    ap.add_argument("--series", action="append")
    ap.add_argument("--pages", type=int, default=0, help="only the first N pages of every series")
    ap.add_argument("--no-pipeline", action="store_true", help="gold boxes only")
    ap.add_argument("--detect-model", choices=("off", "auto", "on"), default="off",
                    help="the layout model for the pipeline's regions (the setting detect_model; auto with art_erase "
                         "lama, so that it runs with or without a GPU)")
    ap.add_argument("--out", type=Path, help="write the numbers as JSON")
    args = ap.parse_args(argv)
    netguard.install()

    pages = openmantra.load(args.root, args.series)
    if args.pages:
        pages = [p for v in openmantra.by_series(pages).values() for p in v[:args.pages]]
    pipeline = None
    if not args.no_pipeline:
        from taslation.config import Settings
        from taslation.pipeline import Pipeline

        settings = Settings()
        settings.detect_model = args.detect_model
        if args.detect_model == "auto":
            # auto runs the model only beside the art's erase (the eraser is not loaded): "lama", which runs on any
            # computer, as art_erase "auto" did until it came to mean "only with a GPU"
            settings.art_erase = "lama"
        settings.validate()
        pipeline = Pipeline(settings, ocr=None, translator=None, cache=None)

    sets: dict[str, dict[str, Tally]] = {"gold boxes": {"all": Tally()}}
    if pipeline is not None:
        sets["pipeline regions"] = {"all": Tally()}
    worse: dict[str, list[str]] = {k: [] for k in sets}
    better = dict.fromkeys(sets, 0)
    ms: list[float] = []
    found_panels = gold_panels = paired = 0
    for page in pages:
        image = page.open()
        rgb = np.asarray(image)
        started = time.perf_counter()
        panels = find_panels(rgb, ignore=[b.box for b in page.bubbles])
        ms.append(1000 * (time.perf_counter() - started))
        paired += len(match(page.frames, panels))
        found_panels += len(panels)
        gold_panels += len(page.frames)
        choices = {"rows": None, "panels": panels, "gold_panels": page.frames}

        regions = [as_region(b.box) for b in page.bubbles]
        scored: dict[str, dict[str, list[int]]] = {"gold boxes": sequences(regions, {id(r): i for i, r in enumerate(regions)}, choices)}
        if pipeline is not None:
            found = list(pipeline.process(image, translate=False, use_cache=False).regions)
            pairs = match([b.box for b in page.bubbles], [(r.bbox, r.text_box) for r in found])
            scored["pipeline regions"] = shipped(found, {id(found[ri]): gi for gi, ri, _v in pairs}, page.frames)
        for name, seqs in scored.items():
            if len(seqs["rows"]) < 2:
                continue
            for label in ("all", page.series, panel_class(len(page.frames))):
                sets[name].setdefault(label, Tally()).add(seqs)
            before, after = discordant(seqs["rows"])[0], discordant(seqs["panels"])[0]
            if after > before:
                worse[name].append(f"{page.series} p{page.index}: {len(seqs['rows'])} regions, {len(panels)} panels found, "
                                   f"{len(page.frames)} gold, discordant {before} -> {after}")
            better[name] += after < before

    for name, tallies in sets.items():
        ordered = {k: tallies[k] for k in sorted(tallies, key=lambda k: (k != "all", k))}
        report(name, ordered, worse[name], better[name])
    ms.sort()
    print(f"\nfinder: {found_panels} panels found, {gold_panels} gold, {paired} paired at IoU 0.5: "
          f"recall {100 * paired / max(1, gold_panels):.1f} %, precision {100 * paired / max(1, found_panels):.1f} %")
    print(f"finder, ms per page: mean {sum(ms) / max(1, len(ms)):.1f}, median {ms[len(ms) // 2]:.1f}, worst {ms[-1]:.1f}")
    if args.out:
        numbers = {name: {k: {"pages": t.pages, "pairs": t.pairs, "right": t.right, "bad": t.bad} for k, t in tallies.items()}
                   for name, tallies in sets.items()}
        args.out.write_text(json.dumps(numbers, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
