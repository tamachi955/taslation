"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: whether judging each region as soon as it is read changes anything.

The pipeline judges a page unit's regions as soon as each is read, the page's usual size taken only once a gate needs
it (`pipeline.JUDGE_AT_READ`, `pipeline._UsualLater`); before, it read all the regions for that size first. Both are
meant to give the same regions, texts, kinds, statuses, order and book's sizes on every page. This tool reads pages
both ways with one pipeline (the book's sizes put back between the two, so that each way starts from the same ones;
the OCR's memo shared: a crop read the same is read once) and compares every field of every region, the progress
told and the book's sizes after. It prints counts only: nothing of a page's text.

    python tools/judge_order_check.py                    # the repository's test pages (tests/fixtures)
    python tools/judge_order_check.py --sets repo,openmantra,gold --detect on,off

``openmantra`` is the sample dataset (~/.taslation/datasets/openmantra/images, read in place); ``gold`` the screens of
the book the OCR's gold set was made on (the dev snapshots folder that holds ``ocr_gold.json``, read in place, with
the snapshots' capture margins). Nothing is written; nothing goes over the network.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterator, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
REAL_STATE = Path.home() / ".taslation"  # read only: the sample dataset and the dev snapshots
GOLD_MARGINS = (0, 85, 0, 0)  # the capture margins the dev snapshots were taken with (tools/ocr_gold.py)


def _value(v: Any, index: dict[int, int]) -> Any:
    """A field's value as compared: an array by its shape and bytes, another region by its place in the page's list
    (or its box and kind when it is not in it), containers element by element."""
    import numpy as np

    from taslation.regions import TextRegion

    if isinstance(v, np.ndarray):
        return ("array", v.shape, str(v.dtype), hashlib.sha1(np.ascontiguousarray(v).tobytes()).hexdigest())
    if isinstance(v, TextRegion):
        return ("region", index[id(v)]) if id(v) in index else ("region", v.bbox, v.text_box, v.kind)
    if isinstance(v, (list, tuple)):
        return (type(v).__name__, tuple(_value(x, index) for x in v))
    if isinstance(v, dict):
        return ("dict", tuple(sorted((str(k), _value(x, index)) for k, x in v.items())))
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return (type(v).__name__, tuple((f.name, _value(getattr(v, f.name), index)) for f in dataclasses.fields(v)))
    if hasattr(v, "__dict__") and not isinstance(v, type):
        return (type(v).__name__, tuple(sorted((k, _value(x, index)) for k, x in vars(v).items())))
    return v


def fingerprint(regions: Sequence[Any]) -> list[tuple[Any, ...]]:
    """Every field of every region of *regions*, in their order, as compared (`_value`)."""
    index = {id(r): i for i, r in enumerate(regions)}
    return [tuple((f.name, _value(getattr(r, f.name), index)) for f in dataclasses.fields(r)) for r in regions]


def read_both_ways(pipeline: Any, image: Any) -> tuple[bool, dict[str, Any]]:
    """*image* read (`Pipeline.process`, nothing translated, no cache) the old way and the new one, each from the book's
    sizes as they were: whether every region, the progress told and the book's sizes after are the same, and counts."""
    from taslation import pipeline as pipeline_mod

    before = deque(pipeline._book_sizes, maxlen=pipeline._book_sizes.maxlen)
    out: list[tuple[Any, ...]] = []
    for judge_at_read in (False, True):
        pipeline._book_sizes = deque(before, maxlen=before.maxlen)
        told: list[Any] = []
        held = pipeline_mod.JUDGE_AT_READ
        pipeline_mod.JUDGE_AT_READ = judge_at_read
        try:
            res = pipeline.process(image, translate=False, use_cache=False,
                                   progress=lambda m: told.append((m.code, tuple(sorted(m.params.items())))))
        finally:
            pipeline_mod.JUDGE_AT_READ = held
        out.append((fingerprint(res.regions), told, list(pipeline._book_sizes), res))
    (fa, ta, sa, ra), (fb, tb, sb, rb) = out
    facts = {"regions": len(rb.regions),
             "text": sum(1 for r in rb.regions if r.status == "untranslated" and r.source_text),
             "model": sum(1 for r in rb.regions if r.from_model)}
    diffs = []
    if len(fa) != len(fb):
        diffs.append("number of regions")
    else:
        for i, (a, b) in enumerate(zip(fa, fb)):
            names = [x[0] for x, y in zip(a, b) if x != y]
            if names:
                diffs.append(f"region {i}: {', '.join(names)}")
    if ta != tb:
        diffs.append("progress told")
    if sa != sb:
        diffs.append("book's sizes")
    facts["diffs"] = diffs
    return not diffs, facts


def repo_pages() -> Iterator[tuple[str, Any]]:
    from PIL import Image

    for path in sorted(FIXTURES.rglob("*.png")):
        with Image.open(path) as img:
            yield path.relative_to(FIXTURES).as_posix(), img.convert("RGB")


def openmantra_pages(limit: int = 0) -> Iterator[tuple[str, Any]]:
    from PIL import Image

    folder = REAL_STATE / "datasets" / "openmantra" / "images"
    paths = sorted(folder.rglob("*.jpg")) if folder.is_dir() else []
    for n, path in enumerate(paths[:limit] if limit else paths):
        with Image.open(path) as img:
            yield f"openmantra #{n + 1}", img.convert("RGB")


def gold_folder() -> Path | None:
    folder = REAL_STATE / "dev-snapshots"
    if not folder.is_dir():
        return None
    return next((p for p in sorted(folder.iterdir()) if (p / "ocr_gold.json").is_file()
                 and (p / "manifest.json").is_file()), None)


def gold_pages(limit: int = 0) -> Iterator[tuple[str, Any]]:
    from PIL import Image

    folder = gold_folder()
    if folder is None:
        return
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for n, entry in enumerate(manifest["screens"]):
        if limit and n >= limit:
            break
        with Image.open(folder / entry["file"]) as img:
            yield f"gold screen #{n + 1}", img.convert("RGB")


def check(sets: Sequence[str], detects: Sequence[str], limit: int = 0, log: Any = print) -> dict[str, Any]:
    """The pages of *sets* read both ways with the layout model *detects* ("on", "off"): per set and detection, pages
    alike and different, and the regions compared. Readers as the window builds them (`ocr.Readers`)."""
    from taslation import netguard
    from taslation.config import Settings
    from taslation.ocr import Readers
    from taslation.pipeline import Pipeline

    netguard.install()
    results: dict[str, Any] = {}
    readers = None
    for name in sets:
        for detect in detects:
            margins = GOLD_MARGINS if name == "gold" else (0, 0, 0, 0)
            s = Settings(margins=margins, detect_model=detect)
            s.validate()
            readers = readers or Readers(s.models_dir, s.ocr_threads)
            p = Pipeline(s, ocr=readers, translator=None, cache=None)
            pages = {"repo": repo_pages, "openmantra": lambda: openmantra_pages(limit),
                     "gold": lambda: gold_pages(limit)}[name]()
            alike = differ = regions = text = model = 0
            t0 = time.monotonic()
            for label, image in pages:
                same, facts = read_both_ways(p, image)
                alike += same
                differ += not same
                regions += facts["regions"]
                text += facts["text"]
                model += facts["model"]
                if not same:
                    log(f"  {name}/{detect} {label}: DIFFERENT ({'; '.join(facts['diffs'])})")
            key = f"{name}/detect {detect}"
            results[key] = {"pages": alike + differ, "alike": alike, "different": differ, "regions": regions,
                            "read as text": text, "layout model's": model,
                            "seconds": round(time.monotonic() - t0, 1)}
            log(f"{key}: {results[key]}")
    return results


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sets", default="repo", help="comma-separated: repo, openmantra, gold")
    ap.add_argument("--detect", default="on,off", help="the layout model: on, off or both (on,off)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N pages of openmantra and gold")
    args = ap.parse_args(argv)
    results = check([x for x in args.sets.split(",") if x], [x for x in args.detect.split(",") if x], args.limit)
    return 0 if all(r["different"] == 0 for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
