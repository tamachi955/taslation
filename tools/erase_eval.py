"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the erase on synthetic lettering, as the app runs it, numbers only.

Real lettering (alpha mattes of clean gold crops of OpenMantra) is pasted on real art of another series: 300 pairs over
plain ground, light tone and dense drawing, chosen with a fixed seed, and the same pairs again with a white outline of
2-4 px, as lettering set on art has. Each composite goes through the whole pipeline (detection and OCR), and the regions
read as text that overlap the pasted lettering are erased as the app erases them, by the paper fill alone ("paper",
`Pipeline._paper_erase`) and by the erase with LaMa on the art (`ArtEraser`: "lama"). The score is the MAE (0-255, RGB)
against the page before the paste, inside the lettering's exact mask, with what stayed outside it and the share of its
pixels left more than 40 off. (Until 2026-11-07 the paper fill was `erase_region`, which paints a model region's plain
box whole: the numbers of before are not comparable.)

    python tools/erase_eval.py                 # both sets
    python tools/erase_eval.py --set outlined --limit 40

Pages stay in memory, nothing is written, no text is printed. The dataset is CC BY-NC and never shipped.
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402

SEED = 20261102
GROUNDS = ("plain", "tone_light", "dense")
HOW_MANY = 100  # pairs per ground
PAD = 7  # px of room round a matte for its outline
SETS = ("plain", "outlined")


def pages(root: Path) -> list[dict[str, Any]]:
    data = json.loads((root / "annotation.json").read_text(encoding="utf-8"))
    return [{"series": book["book_title"], "path": str(root / page["image_paths"]["ja"]),
             "frames": [(f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]) for f in page["frame"]],
             "boxes": [(t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]) for t in page["text"]]}
            for book in data for page in book["pages"]]


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB")).copy()


def glyph_patch(gray: np.ndarray) -> np.ndarray | None:
    """The alpha matte of black lettering on white paper in a gold crop; None if it is no clean lettering on paper."""
    h, w = gray.shape
    if min(h, w) < 16:
        return None
    if (gray >= 225).mean() < 0.5 or not 0.04 <= (gray < 140).mean() <= 0.4:
        return None
    rim = np.concatenate([gray[:2].ravel(), gray[-2:].ravel(), gray[:, :2].ravel(), gray[:, -2:].ravel()])
    if (rim >= 200).mean() < 0.97:
        return None  # an outline or a drawing in the box
    n, _labels, st, _ = cv2.connectedComponentsWithStats((gray < 200).astype(np.uint8), connectivity=8)
    if n < 3 or st[1:, 4].max() > 900 or max(st[1:, 2].max(), st[1:, 3].max()) > 70:
        return None  # a line or a big figure, no lettering
    alpha = np.clip((245.0 - gray) / 215.0, 0, 1)
    alpha[alpha < 0.05] = 0
    ys, xs = np.nonzero(alpha)
    return alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)


def ground_of(gray: np.ndarray) -> str | None:
    gx, gy = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edges = float((np.hypot(gx, gy) > 120).mean())
    mean, std, dark = float(gray.mean()), float(gray.std()), float((gray < 90).mean())
    if std < 4 and edges < 0.002 and mean > 100:
        return "plain"
    if mean >= 185 and dark < 0.10 and edges >= 0.02:
        return "tone_light"
    if edges >= 0.22 or (dark > 0.25 and edges > 0.12):
        return "dense"
    return None


def pairs(ps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The lettering/art pairs: `HOW_MANY` per ground, of another series than the lettering's, away from its page's text."""
    rng = random.Random(SEED)
    glyphs: list[tuple[int, np.ndarray]] = []
    for pi, p in enumerate(ps):
        gray = cv2.cvtColor(load(p["path"]), cv2.COLOR_RGB2GRAY)
        for b in p["boxes"]:
            alpha = glyph_patch(gray[b[1]:b[3], b[0]:b[2]])
            if alpha is not None and alpha.shape[0] * alpha.shape[1] >= 800:
                glyphs.append((pi, alpha))
    out: list[dict[str, Any]] = []
    order = list(range(len(glyphs)))
    rng.shuffle(order)
    k = tries = 0
    counts: collections.Counter[str] = collections.Counter()
    held: dict[int, np.ndarray] = {}

    def page(i: int) -> np.ndarray:
        if i not in held:
            if len(held) > 40:
                held.clear()
            held[i] = load(ps[i]["path"])
        return held[i]

    while any(counts[g] < HOW_MANY for g in GROUNDS) and tries < 2000000:
        tries += 1
        gi, alpha = glyphs[order[k % len(order)]]
        pi = rng.randrange(len(ps))
        p = ps[pi]
        if p["series"] == ps[gi]["series"] or not p["frames"]:
            continue
        f = rng.choice(p["frames"])
        h, w = alpha.shape
        if f[2] - f[0] < w + 8 or f[3] - f[1] < h + 8:
            continue
        x, y = rng.randrange(f[0] + 2, f[2] - w - 2), rng.randrange(f[1] + 2, f[3] - h - 2)
        if any(x < b[2] + 6 and b[0] - 6 < x + w and y < b[3] + 6 and b[1] - 6 < y + h for b in p["boxes"]):
            continue
        img = page(pi)
        if y + h >= img.shape[0] or x + w >= img.shape[1]:
            continue
        ground = ground_of(cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_RGB2GRAY))
        if ground is None or counts[ground] >= HOW_MANY:
            continue
        counts[ground] += 1
        k += 1
        out.append({"bg": ground, "page": pi, "x": x, "y": y, "a": (alpha * 255).astype(np.uint8)})
    rng.shuffle(out)
    return out


def outlined(ps: list[dict[str, Any]], plain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same pairs with a white outline of 2-4 px."""
    rng = random.Random(SEED + 1)
    out = []
    for s in plain:
        r = rng.choice((2, 3, 3, 4))
        a = s["a"]
        x, y = s["x"] - PAD, s["y"] - PAD
        img_h, img_w = cv2.imread(ps[s["page"]]["path"]).shape[:2]
        if x < 0 or y < 0 or x + a.shape[1] + 2 * PAD > img_w or y + a.shape[0] + 2 * PAD > img_h:
            continue
        padded = cv2.copyMakeBorder(a, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=0)
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        out.append({**s, "a": padded, "halo": cv2.GaussianBlur(cv2.dilate(padded, disc), (0, 0), 0.7), "x": x, "y": y})
    return out


def composite(ps: list[dict[str, Any]], s: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The page with the lettering on it, the page as it was, and the lettering's exact mask (of the matte's box)."""
    img = load(ps[s["page"]]["path"])
    alpha = s["a"].astype(np.float32) / 255
    h, w = alpha.shape
    x, y = s["x"], s["y"]
    comp = img.copy()
    roi = comp[y:y + h, x:x + w].astype(np.float32)
    exact = s["a"] > 0
    if "halo" in s:
        halo = s["halo"].astype(np.float32)[..., None] / 255
        roi = roi * (1 - halo) + 255 * halo
        exact = exact | (s["halo"] > 12)
    comp[y:y + h, x:x + w] = (roi * (1 - alpha[..., None])).round().astype(np.uint8)
    return comp, img, exact


def score(result: np.ndarray, page: np.ndarray, exact: np.ndarray, x: int, y: int, pad: int = 8) -> tuple[float, float, float]:
    """MAE in the exact mask, MAE outside it in the box and *pad* around, share of the mask left more than 40 off."""
    h, w = exact.shape
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(page.shape[1], x + w + pad), min(page.shape[0], y + h + pad)
    d = np.abs(result[y0:y1, x0:x1].astype(np.float32) - page[y0:y1, x0:x1].astype(np.float32)).mean(axis=2)
    inside = np.zeros(d.shape, bool)
    inside[y - y0:y - y0 + h, x - x0:x - x0 + w] = exact
    return float(d[inside].mean()), float(d[~inside].mean()), float((d[inside] > 40).mean())


def over_the_lettering(regions: list[Any], s: dict[str, Any]) -> list[Any]:
    """The regions read as text that overlap the pasted lettering."""
    x, y = s["x"], s["y"]
    h, w = s["a"].shape
    hit = []
    for r in regions:
        if r.status != "untranslated" or not r.source_text:
            continue
        ix, iy = max(0, min(r.x1, x + w) - max(r.x0, x)), max(0, min(r.y1, y + h) - max(r.y0, y))
        tb = r.letter_box or r.text_box
        jx, jy = max(0, min(tb[2], x + w) - max(tb[0], x)), max(0, min(tb[3], y + h) - max(tb[1], y))
        if jx * jy >= 0.2 * w * h or (ix * iy >= 0.5 * w * h and r.kind in ("bubble", "dark-bubble")):
            hit.append(r)
    return hit


def erasers(models_dir: Path) -> dict[str, Any]:
    """The erases compared: the paper fill alone, and with LaMa on the art; each as the app does it, the paper fill of
    a layout model's region painting its lettering alone (`Pipeline._paper_erase`: a plain box is not painted whole),
    and LaMa leaving to that what it does not take."""
    from taslation.pipeline import Pipeline
    from taslation.render import artwork

    return {"paper": Pipeline._paper_erase, "lama": artwork.ArtEraser(models_dir, "lama", Pipeline._paper_erase).erase}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT, help="the dataset folder")
    ap.add_argument("--set", choices=SETS, action="append", help="only this set (default: both)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N pairs of a set")
    ap.add_argument("--detect-model", choices=("auto", "on", "off"), default="on",
                    help="the setting of that name (default: on, the layout model whatever the erase setting; auto: as "
                         "the app has it beside art_erase's default, only on a computer with a GPU)")
    args = ap.parse_args(argv)
    netguard.install()

    from taslation.detect import is_dark
    from taslation.ocr import Readers
    from taslation.pipeline import Pipeline

    s = Settings(detect_model=args.detect_model)
    s.validate()
    pipeline = Pipeline(s, ocr=Readers(s.models_dir, s.ocr_threads), translator=None, cache=None)
    print(f"layout model: {'on' if pipeline.layout is not None else 'off'}", flush=True)
    erases = erasers(s.models_dir)
    lama = erases["lama"].__self__  # (the "lama" arm's ArtEraser: what its regions went to, where it ran)
    t0 = time.monotonic()
    lama.warm()  # loaded ahead, so that the arm's seconds are the erase's alone
    print(f"LaMa loaded on {'the GPU' if lama.uses_gpu() else 'the CPU'} in {time.monotonic() - t0:.1f} s", flush=True)
    ps = pages(args.root)
    plain = pairs(ps)
    sets = {"plain": plain, "outlined": outlined(ps, plain)}
    for name in args.set or SETS:
        samples = sets[name][:args.limit or None]
        rows: dict[str, list[tuple[float, float, float]]] = {e: [] for e in erases}
        seconds = dict.fromkeys(erases, 0.0)
        found: collections.Counter[str] = collections.Counter()
        counts_before = dict(lama.counts)
        erased = 0
        t0 = time.monotonic()
        for i, smp in enumerate(samples):
            comp, page, exact = composite(ps, smp)
            regions = over_the_lettering(pipeline.process(Image.fromarray(comp), translate=False, use_cache=False).regions, smp)
            found[smp["bg"]] += bool(regions)
            erased += len(regions)
            for how, erase in erases.items():
                image = comp.copy()
                t = time.perf_counter()
                for r in regions:
                    q = copy.copy(r)
                    q.mask = r.mask.copy()
                    erase(image, q, s.erase_mode, s.white_threshold, s.dark_threshold, is_dark(r))
                seconds[how] += time.perf_counter() - t
                rows[how].append(score(image, page, exact, smp["x"], smp["y"]))
            if i % 50 == 0:
                print(f"  {name} {i}/{len(samples)} {time.monotonic() - t0:.0f} s", flush=True)
        went = {k: lama.counts[k] - counts_before[k] for k in lama.counts}
        print(f"{name}: {len(samples)} pairs, found {dict(found)}; {erased} regions erased, the lama arm's went to {went} "
              f"(art: LaMa; plain, weak, ground: the paper fill)")
        for how in erases:
            values = np.array(rows[how])
            grounds = {g: round(float(np.mean([v for v, smp in zip(values[:, 0], samples) if smp["bg"] == g])), 1) for g in GROUNDS}
            per = 1000 * seconds[how] / max(1, len(samples))
            print(f"  {how:6} MAE {values[:, 0].mean():6.2f} {grounds} outside {values[:, 1].mean():.2f} left {100 * values[:, 2].mean():.1f} %"
                  f"; erase {per:.0f} ms a pair")
    lama.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
