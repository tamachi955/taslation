"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the typesetter on the OpenMantra pages, before and after, numbers only.

The translations come from the book caches of earlier OpenMantra runs (``~/.taslation/cache/OpenMantra_*``, read only),
the pages from the dataset (``tools/openmantra.py``; CC BY-NC, never shipped). Each cached page is found by its
fingerprint, the page's regions are detected (on the CPU, no OCR) and paired with its bubbles by
``Pipeline._apply_cached``, as for a page from the cache, erased on the page in memory as the app erases them and set
by the real typesetter, once per configuration:

* ``before``: greedy lines, no cap; ``balanced``: `typeset._balanced`; ``capped k``: `Pipeline.cap_sizes` at that k;
  ``both k``: the two together.

Printed for each: of the regions on two lines or more, the orphan rate (the last line is one word of at most
ORPHAN_LETTERS letters), those of them with a word to spare on the line before ("avoidable"), the regions with a lone
word of at most LONE_LETTERS letters on an inner line, and how thin the last lines are; the spread of the line widths
((widest - narrowest) / widest per region) and of how full each line is against its room; the mean size, the lines
below ``readable_font_size`` (share and count), the page's 90th to 10th percentile of size (pages with four regions
or more), the largest size over the median, lines wider than their room, and ms per region of the layout alone
(repeated, best run; ``cap ms``: what `Pipeline.cap_sizes` adds).

    python tools/typeset_eval.py                  # all five series, k = 1.2, 1.3, 1.4
    python tools/typeset_eval.py --pages 5 --k 1.3

No model, no GPU, no network; pages stay in memory, nothing is written anywhere, no text is printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
from taslation import fingerprint as fp  # noqa: E402
from taslation import netguard  # noqa: E402
from taslation.cache import CachedPage  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.pipeline import Pipeline, is_dark  # noqa: E402
from taslation.regions import TextRegion  # noqa: E402
from taslation.render import erase_region, script_of, typeset  # noqa: E402

CACHES = {"balloon_dream": "OpenMantra_balloon", "boureisougi": "OpenMantra_boureisougi",
          "rasetugari": "OpenMantra_rasetugari_full", "tencho_isoro": "OpenMantra_tencho",
          "tojime_no_siora": "OpenMantra_tojime"}
MATCH_BITS = 24  # a cached page is the dataset page within this many fingerprint bits
ORPHAN_LETTERS = 5
LONE_LETTERS = 3
TIMING_RUNS = 3


@dataclass
class EvalPage:
    regions: list[TextRegion] = field(default_factory=list)


def _cached_pages(series: str) -> list[CachedPage]:
    path = Path.home() / ".taslation" / "cache" / f"{CACHES[series]}.json"
    return [CachedPage.from_json(p) for p in json.loads(path.read_text(encoding="utf-8"))["pages"]]


def eval_pages(pipeline: Pipeline, root: Path | None, limit: int, series: Sequence[str]) -> list[EvalPage]:
    """Every dataset page with cached translations, erased in memory, its regions ready to be set."""
    out: list[EvalPage] = []
    s = pipeline.settings
    for name in series:
        cached = _cached_pages(name)
        done = 0
        for page in openmantra.load(root, name):
            if limit and done >= limit:
                break
            rgb = np.array(page.open())
            regions: list[TextRegion] = []
            units = fp.analyze(rgb, s.margins)
            live = pipeline._detect(rgb)
            owners = pipeline._owners(rgb, live, units)
            for unit in units:
                near = min(cached, key=lambda c: fp.hamming(unit.fingerprint, c.fingerprint), default=None)
                if near is None or fp.hamming(unit.fingerprint, near.fingerprint) > MATCH_BITS:
                    continue
                mine = [r for r in live if owners[id(r)] is unit]
                regions += pipeline._apply_cached(unit, near, mine, rgb)
            regions = [r for r in regions if r.translated_text]
            for r in regions:
                erase_region(rgb, r, s.erase_mode, s.white_threshold, s.dark_threshold, is_dark(r))
            if regions:
                out.append(EvalPage(regions))
                done += 1
    return out


def set_page(pipeline: Pipeline, regions: list[TextRegion]) -> list[Any]:
    """The `Fit` of each region as `Pipeline._set_text` would set it."""
    s = pipeline.settings
    fits = []
    for r in regions:
        lettering = pipeline.lettering_for(r.translated_text, r.tag)
        top = min(s.max_font_size, r.size_cap) if r.size_cap else s.max_font_size
        fits.append(typeset.layout_text(r.mask, r.translated_text, lettering, s.min_font_size, top, s.line_spacing,
                                        False, script_of(r.translated_text, s.target_language)))
    return fits


def _rooms(fit: Any, region: TextRegion) -> list[int] | None:
    return typeset._line_rooms(fit, typeset._shape_room(region.mask, typeset.SHAPE_PAD, None))


def score(fits_by_page: list[list[Any]], pages: list[EvalPage], readable: int) -> dict[str, float]:
    orphans = avoidable = lone = multi = thin = lines = small = over = 0
    spreads: list[float] = []
    fills: list[float] = []
    sizes: list[int] = []
    ratios: list[float] = []
    tallest: list[float] = []
    for fits, page in zip(fits_by_page, pages):
        page_sizes = [f.size for f in fits]
        sizes += page_sizes
        if len(page_sizes) >= 4:
            p10, p90 = np.percentile(page_sizes, [10, 90])
            ratios.append(float(p90 / max(1.0, p10)))
            tallest.append(max(page_sizes) / float(np.median(page_sizes)))
        for fit, r in zip(fits, page.regions):
            texts = [t for t, _x, _y in fit.lines if t]
            lines += len(texts)
            small += len(texts) if fit.size < readable else 0
            widths = [typeset.text_width(fit.font, typeset.display_form(t, "lgc")) for t in texts]
            rooms = _rooms(fit, r)
            if rooms is not None:
                over += sum(w > room for w, room in zip(widths, rooms))
            if len(texts) < 2:
                continue
            multi += 1
            words = texts[-1].split()
            orphan = len(words) == 1 and sum(c.isalpha() for c in words[0]) <= ORPHAN_LETTERS
            orphans += orphan
            avoidable += orphan and len(texts[-2].split()) >= 2
            lone += any(len(t.split()) == 1 and sum(c.isalpha() for c in t) <= LONE_LETTERS for t in texts[1:-1])
            thin += widths[-1] < 0.4 * max(widths)
            spreads.append((max(widths) - min(widths)) / max(widths))
            if rooms is not None:
                full = [w / max(1, room) for w, room in zip(widths, rooms)]
                fills.append(max(full) - min(full))
    share = 100.0 / max(1, multi)
    return {"multi": float(multi), "orphan %": orphans * share, "avoidable %": avoidable * share, "lone %": lone * share,
            "thin last %": thin * share, "width spread": float(np.mean(spreads)) if spreads else 0.0,
            "fill spread": float(np.mean(fills)) if fills else 0.0, "mean size": float(np.mean(sizes)),
            "lines": float(lines), "small lines": float(small), "below readable %": 100.0 * small / max(1, lines),
            "p90/p10": float(np.mean(ratios)) if ratios else 0.0,
            "max/median": float(np.mean(tallest)) if tallest else 0.0, "over room": float(over)}


def run(pipeline: Pipeline, pages: list[EvalPage], balance: bool, k: float | None) -> dict[str, float]:
    typeset.BALANCE_LINES, typeset.SIZE_CAP = balance, k
    n = max(1, sum(len(p.regions) for p in pages))
    capping = setting = float("inf")
    fits: list[list[Any]] = []
    for _ in range(TIMING_RUNS):
        t0 = time.perf_counter()
        for p in pages:
            pipeline.cap_sizes(p.regions, [r.translated_text for r in p.regions])
        t1 = time.perf_counter()
        fits = [set_page(pipeline, p.regions) for p in pages]
        t2 = time.perf_counter()
        capping, setting = min(capping, t1 - t0), min(setting, t2 - t1)
    return {**score(fits, pages, pipeline.settings.readable_font_size), "ms/region": 1000.0 * setting / n,
            "cap ms": 1000.0 * capping / n if k else 0.0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="the OpenMantra folder")
    parser.add_argument("--pages", type=int, default=0, help="only the first N pages of each series")
    parser.add_argument("--series", nargs="*", default=list(CACHES), choices=list(CACHES))
    parser.add_argument("--k", type=float, nargs="*", default=[1.2, 1.3, 1.4], help="the caps to try")
    args = parser.parse_args(argv)
    netguard.install()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    settings = Settings(render_unmatched_cached=True)
    pipeline = Pipeline(settings)
    pages = eval_pages(pipeline, args.root, args.pages, args.series)
    set_page(pipeline, pages[0].regions)  # the fonts loaded before the clock starts
    configs: list[tuple[str, bool, float | None]] = [("before", False, None), ("balanced", True, None)]
    for k in args.k:
        configs += [(f"capped {k}", False, k), (f"both {k}", True, k)]
    results = {name: run(pipeline, pages, balance, k) for name, balance, k in configs}
    keys = list(next(iter(results.values())))
    print(f"{len(pages)} pages")
    print(" | ".join(["config".ljust(12), *(k.rjust(max(len(k), 7)) for k in keys)]))
    for name, row in results.items():
        print(" | ".join([name.ljust(12), *(f"{row[k]:.2f}".rjust(max(len(k), 7)) for k in keys)]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
