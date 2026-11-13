"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: score the OCR of a book against a gold transcription.

A gold file (``ocr_gold.json`` in the book's snapshot folder, see ``dev_snapshots.py``) holds, for every text
region of the saved screens, the lettering as a person transcribed it from the pixels: box, kind, text ("" for a
region that holds no text) and flags. This tool runs the pipeline's own OCR path over the saved screens, matches
its regions to the gold items by position, and prints character error rates and counts: nothing of the book's
text. Night batches can run it after any change to detection or the OCR.

    python tools/ocr_gold.py score --book "<title> 1巻"   # the pipeline's OCR against the gold file
    python tools/ocr_gold.py info --book "<title> 1巻"    # what the gold file holds
    python tools/ocr_gold.py score --book "<title> 1巻" --position-free   # and by text, whatever the box

The gold file is text of a real book: it stays with the snapshots on this machine (``dev_snapshots.py wipe``
removes the folder) and is never shared. Nothing goes over the network.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dev_snapshots import book_dir, screens  # noqa: E402
from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402

GOLD = "ocr_gold.json"
RIGHT, WRONG = 0.1, 0.5  # a reading with a CER of RIGHT or under is right, WRONG or over is wrong
PAIRED = 0.5  # position-free: a reading this close to a gold line (CER) or closer may be that line's
MARGIN = 0.02


def norm(t: str) -> str:
    """Comparison form: NFKC, common dashes and dots unified, no whitespace."""
    t = unicodedata.normalize("NFKC", t)
    for a, b in (("…", "..."), ("‥", ".."), ("～", "~"), ("〜", "~"), ("―", "-"), ("—", "-")):
        t = t.replace(a, b)
    return "".join(ch for ch in t if not ch.isspace())


def cer(hyp: str, ref: str) -> float:
    """Character error rate of *hyp* against *ref* (Levenshtein distance over the reference length)."""
    hyp, ref = norm(hyp), norm(ref)
    if not ref:
        return 0.0 if not hyp else 1.0
    d = list(range(len(ref) + 1))
    for i, hc in enumerate(hyp, 1):
        prev, d[0] = d[0], i
        for j, rc in enumerate(ref, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (hc != rc))
    return d[len(ref)] / len(ref)


def iou(a: list[int], b: list[int]) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def load_gold(book: str) -> dict:
    path = book_dir(book) / GOLD
    if not path.exists():
        raise SystemExit(f"no gold file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _info(args: argparse.Namespace) -> int:
    gold = load_gold(args.book)
    items = gold["items"]
    with_text = [it for it in items if it["text"]]
    print(f"{gold.get('book', args.book)}: made {gold.get('made', '?')} by {gold.get('judge', '?')}")
    print(f"  {len(items)} items on {len({it['screen'] for it in items})} screens; {len(with_text)} hold text "
          f"({sum(len(norm(it['text'])) for it in with_text)} characters), {len(items) - len(with_text)} none")
    print("  by kind: " + ", ".join(f"{k} {n}" for k, n in sorted(Counter(it["kind"] for it in with_text).items())))
    print("  flags: " + (", ".join(f"{k} {n}" for k, n in Counter(f for it in items for f in it.get("flags", [])).most_common()) or "none"))
    return 0


def _stats(name: str, cers: list[float]) -> None:
    if not cers:
        return
    n = len(cers)
    print(f"  {name:26} n {n:4}  mean CER {100 * sum(cers) / n:5.1f}%  capped {100 * sum(min(1.0, c) for c in cers) / n:5.1f}%  "
          f"right {sum(c <= RIGHT for c in cers):4}  wrong {sum(c >= WRONG for c in cers):4}")


def _score(args: argparse.Namespace) -> int:
    import numpy as np

    from taslation.annotations import AnnotationStore
    from taslation.ocr import Readers
    from taslation.pipeline import Pipeline
    from taslation.review import OCR_UNSURE

    gold = load_gold(args.book)
    by_screen: dict[int, list[dict]] = {}
    for it in gold["items"]:
        by_screen.setdefault(int(it["screen"]), []).append(it)
    s = Settings(margins=tuple(int(v) for v in args.margins.split(",")), detect_model=args.detect_model,
                 slant_text=not args.no_slant)
    s.validate()
    p = Pipeline(s, ocr=Readers(s.models_dir, s.ocr_threads), translator=None, cache=None,
                 annotations=AnnotationStore(s.annotations_dir).open(args.book))
    print(f"scoring against {sum(len(v) for v in by_screen.values())} gold items", flush=True)
    t0 = time.monotonic()
    rows: list[tuple[dict, object]] = []  # (gold item, region or None)
    false_text = 0
    free: list[tuple[int, int, list[float], int, int]] = []  # per screen: gold lines, read, CERs, unpaired, of them on an item
    other_regions = 0
    n_screens = 0
    for screen, img in screens(args.book):
        if args.limit and n_screens >= args.limit:
            break
        n_screens += 1
        res = p.process(img, translate=False)
        items = by_screen.get(screen, [])
        regions = [r for r in res.regions]
        used: set[int] = set()
        for it in items:
            best, best_i = 0.0, -1
            for i, r in enumerate(regions):
                if i in used:
                    continue
                v = iou(it["box"], [r.x0, r.y0, r.x1, r.y1])
                if v > best:
                    best, best_i = v, i
            if best >= args.iou:
                used.add(best_i)
                rows.append((it, regions[best_i]))
            else:
                rows.append((it, None))
        for i, r in enumerate(regions):
            if i not in used:
                other_regions += 1
                if r.status == "untranslated" and r.source_text:
                    false_text += 1
        if args.position_free:
            free.append(position_free(items, [r for r in regions if r.status == "untranslated" and r.source_text]))
    took = time.monotonic() - t0
    print(f"  {n_screens} screens in {took:.0f} s ({1000 * took / max(1, n_screens):.0f} ms a screen)", flush=True)
    text_items = [(it, r) for it, r in rows if it["text"]]
    missed = [it for it, r in text_items if r is None or r.status != "untranslated" or not r.source_text]
    missed_status = Counter("no region" if r is None else r.status for it, r in text_items if r is None or r.status != "untranslated" or not r.source_text)
    print(f"detection: {len(text_items)} gold text items, {len(text_items) - len(missed)} read as text, {len(missed)} not "
          f"({', '.join(f'{k} {n}' for k, n in missed_status.most_common())}); "
          f"{sum(1 for it, r in rows if not it['text'] and r is not None and r.status == 'untranslated' and r.source_text)} gold non-text regions read as text; "
          f"{false_text} text regions outside the gold set ({other_regions} unmatched regions in all)")
    read = [(it, r) for it, r in text_items if r is not None and r.status == "untranslated" and r.source_text]
    cers = [(it, r, cer(r.source_text, it["text"])) for it, r in read]
    print("OCR on the gold text items the pipeline read (CER against the gold):")
    _stats("all", [c for it, r, c in cers])
    for name, f in (("conf<0.7", lambda c: c < 0.7), ("0.7-0.75", lambda c: 0.7 <= c < 0.75), ("0.75-0.8", lambda c: 0.75 <= c < 0.8),
                    ("0.8-0.85", lambda c: 0.8 <= c < 0.85), ("0.85-0.9", lambda c: 0.85 <= c < 0.9),
                    ("0.9-0.95", lambda c: 0.9 <= c < 0.95), ("conf>=0.95", lambda c: c >= 0.95)):
        _stats(name, [c for it, r, c in cers if f(r.ocr_confidence)])
    for k in sorted({it["kind"] for it, r, c in cers}):
        _stats(k, [c for it, r, c in cers if it["kind"] == k])
    _stats("review flag ocr", [c for it, r, c in cers if r.ocr_confidence < OCR_UNSURE])
    _stats("readers split", [c for it, r, c in cers if r.ocr_split])
    flagged = [c for it, r, c in cers if it.get("flags")]
    _stats("flagged gold items", flagged)
    if args.position_free:
        lines, paired, ce = sum(f[0] for f in free), sum(f[1] for f in free), [c for f in free for c in f[2]]
        print(f"position-free: {lines} gold lines, {paired} read (CER {100 * sum(ce) / max(1, len(ce)):.1f} % mean over them); "
              f"{sum(f[3] for f in free)} readings with no gold line ({sum(f[4] for f in free)} of them on a gold item)")
    return 0


def position_free(items: list[dict], read: list) -> tuple[int, int, list[float], int, int]:
    """A screen scored whatever box a line was read in: its gold lines and its regions read as text pair up by their
    readings, closest first, one to one, up to a CER of `PAIRED`. (gold lines, paired, their CERs, readings left,
    of them those lying on a gold item: a fragment or a merge)."""
    texts = [it["text"] for it in items if it["text"]]
    pairs = sorted((cer(r.source_text, text), gi, ri) for gi, text in enumerate(texts) for ri, r in enumerate(read))
    golds, regions, cers = set(), set(), []
    for c, gi, ri in pairs:
        if c <= PAIRED and gi not in golds and ri not in regions:
            golds.add(gi)
            regions.add(ri)
            cers.append(c)
    left = [r for ri, r in enumerate(read) if ri not in regions]
    on_item = sum(1 for r in left if any(_inter(r.text_box, it["box"]) >= 0.5 * max(1, _area(r.text_box)) for it in items))
    return len(texts), len(golds), cers, len(left), on_item


def _inter(a, b) -> float:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(a) -> float:
    return max(0, a[2] - a[0]) * max(0, a[3] - a[1])


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("score", help="run the OCR path over the saved screens and score it against the gold file")
    p.add_argument("--book", required=True)
    p.add_argument("--margins", default="0,85,0,0", help="capture margins the snapshots were taken with")
    p.add_argument("--iou", type=float, default=0.5, help="least overlap for a region to count as a gold item")
    p.add_argument("--limit", type=int, default=0, help="only the first N screens")
    # (the default was "auto", which beside art_erase "off", the default of then, was the classical detectors alone:
    # "off" keeps that now that art_erase "auto" brings the layout model's "auto" in on a computer with a GPU)
    p.add_argument("--detect-model", choices=("auto", "on", "off"), default="off",
                   help="the setting of that name (default off, as the app's; auto follows art_erase's default)")
    p.add_argument("--no-slant", action="store_true", help="slant_text off: every region upright, as before slants")
    p.add_argument("--position-free", action="store_true",
                   help="also pair gold lines and readings by their text, whatever box they were read in (for the layout model, "
                        "whose boxes are not the gold's)")
    p.set_defaults(func=_score)
    p = sub.add_parser("info", help="what the gold file holds (counts only)")
    p.add_argument("--book", required=True)
    p.set_defaults(func=_info)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
