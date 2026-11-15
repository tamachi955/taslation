"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the erase on synthetic lettering, as the app runs it, numbers only.

Real lettering (alpha mattes of clean gold crops of OpenMantra) is pasted on real art of another series: 300 pairs over
plain ground, light tone and dense drawing, chosen with a fixed seed, and the same pairs again with a white outline of
2-4 px, as lettering set on art has. Each composite goes through the whole pipeline (detection and OCR), and the regions
read as text that overlap the pasted lettering are erased as the app erases them, by the paper fill alone ("paper",
`Pipeline._paper_erase`) and by the erase with LaMa on the art (`ArtEraser`: "lama"). The score is the MAE (0-255, RGB)
against the page before the paste, inside the lettering's exact mask, with what stayed outside it and the share of its
pixels left more than 40 off. (Until 2026-11-07 the paper fill was `erase_region`, which paints a model region's plain
box whole: the numbers of before are not comparable.)

The third set, "grounds" (`grounds`), measures the erase itself, without detection: the same kind of mattes drawn on
clean grounds whose truth is the ground (flat grey, gradients, screentones of 4-8 px, line art, white line art on
black, and crops of real art, dense and light), each without an outline, with one of 3 px and with a thick one of
6 px, and a region made for each as a text block would have it (`ground_region`: its box drawn round the strokes, the
outline past it). Beside `score`'s three numbers it counts the strokes left ("ink") and the outline left white
("ghost"), the mean lightness off in the mask ("bias") and the step at the edge of what the erase changed against
the ground's own ("step", a visible seam), per ground and per outline (`ground_score`).

    python tools/erase_eval.py                 # all three sets
    python tools/erase_eval.py --set outlined --limit 40
    python tools/erase_eval.py --set grounds   # the erase alone, about three minutes with a GPU

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
SETS = ("plain", "outlined", "grounds")


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


# ------------------------------------------------------------------ the grounds set: lettering on clean grounds
GROUND_KINDS = ("flat", "gradient", "tone", "lines", "dark", "art_dense", "art_light")
OUTLINES = (0, 3, 6)  # px of white outline round the lettering: none, as lettering set on art mostly has, thick
SIDE = 640  # px: a ground's side (the model's window, 512 px, and room round it)
ART_EACH = 40  # crops of real art per kind (dense drawing, light tone), each with every outline


def halftone(pitch: float, coverage: float, angle: float, ink: int = 25, paper: int = 248,
             side: int = SIDE) -> np.ndarray:
    """A screentone of round dots, *pitch* px apart on a grid turned by *angle* degrees, *coverage* of it ink;
    anti-aliased (drawn at four times the size and averaged down)."""
    k = 4
    yy, xx = np.mgrid[0:side * k, 0:side * k].astype(np.float32) / k
    t = np.deg2rad(angle)
    u = (xx * np.cos(t) + yy * np.sin(t)) / pitch
    v = (-xx * np.sin(t) + yy * np.cos(t)) / pitch
    dot = (u - np.round(u)) ** 2 + (v - np.round(v)) ** 2 <= coverage / np.pi
    img = cv2.resize(np.where(dot, ink, paper).astype(np.float32), (side, side), interpolation=cv2.INTER_AREA)
    return np.dstack([np.round(img).astype(np.uint8)] * 3)


def shading(a: float, b: float, angle: float, side: int = SIDE) -> np.ndarray:
    """A linear gradient from grey level *a* to *b* across the ground, at *angle* degrees."""
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
    t = np.deg2rad(angle)
    s = xx * np.cos(t) + yy * np.sin(t)
    s = (s - s.min()) / (s.max() - s.min())
    return np.dstack([np.round(a + (b - a) * s).astype(np.uint8)] * 3)


def line_art(rng: random.Random, dark: bool = False, side: int = SIDE) -> np.ndarray:
    """Curves of 1-3 px and a patch of hatching, black on white (white on black with *dark*), anti-aliased."""
    ground, ink = (30, 235) if dark else (250, 20)
    big = np.full((side * 2, side * 2), ground, np.uint8)
    t = np.linspace(0, 1, 60)[:, None]
    for _ in range(rng.randint(25, 44)):
        p = np.array([[rng.uniform(0, 2 * side), rng.uniform(0, 2 * side)] for _ in range(4)])
        curve = (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]
        cv2.polylines(big, [curve.astype(np.int32)], False, ink, rng.randint(2, 5), cv2.LINE_AA)
    cx, cy, ang, gap = rng.uniform(0, 2 * side), rng.uniform(0, 2 * side), rng.uniform(0, np.pi), rng.randint(8, 13)
    for k in range(-40, 40):
        ox, oy = cx + k * gap * np.cos(ang + np.pi / 2), cy + k * gap * np.sin(ang + np.pi / 2)
        cv2.line(big, (int(ox - 400 * np.cos(ang)), int(oy - 400 * np.sin(ang))),
                 (int(ox + 400 * np.cos(ang)), int(oy + 400 * np.sin(ang))), ink, 2, cv2.LINE_AA)
    return np.dstack([cv2.resize(big, (side, side), interpolation=cv2.INTER_AREA)] * 3)


def art_crops(ps: list[dict[str, Any]], rng: random.Random) -> list[tuple[str, np.ndarray]]:
    """`ART_EACH` crops of real art per kind ("art_dense", "art_light": `ground_of`'s dense and light tone), `SIDE` px,
    from the dataset's panels, the middle 180 px free of its text boxes."""
    got: dict[str, list[np.ndarray]] = {"dense": [], "tone_light": []}
    tries = 0
    while any(len(v) < ART_EACH for v in got.values()) and tries < 20000:
        tries += 1
        p = ps[rng.randrange(len(ps))]
        if not p["frames"]:
            continue
        f = rng.choice(p["frames"])
        if f[2] - f[0] < 160 or f[3] - f[1] < 160:
            continue
        cx, cy = rng.randrange(f[0] + 60, f[2] - 60), rng.randrange(f[1] + 60, f[3] - 60)
        if any(cx - 90 < b[2] and b[0] < cx + 90 and cy - 90 < b[3] and b[1] < cy + 90 for b in p["boxes"]):
            continue
        img = load(p["path"])
        h, w = img.shape[:2]
        if h < SIDE or w < SIDE:
            continue
        kind = ground_of(cv2.cvtColor(img[cy - 40:cy + 40, cx - 40:cx + 40], cv2.COLOR_RGB2GRAY))
        if kind not in got or len(got[kind]) >= ART_EACH:
            continue
        x0, y0 = int(np.clip(cx - SIDE // 2, 0, w - SIDE)), int(np.clip(cy - SIDE // 2, 0, h - SIDE))
        got[kind].append(img[y0:y0 + SIDE, x0:x0 + SIDE].copy())
    return [("art_dense", c) for c in got["dense"]] + [("art_light", c) for c in got["tone_light"]]


def lettered(ground: np.ndarray, alpha: np.ndarray, outline: int, light: bool = False
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """*ground* with the lettering of matte *alpha* (uint8) in its middle, black (white with *light*) with a white
    (black) outline of *outline* px; and the lettering's exact mask (strokes and outline) and its strokes alone."""
    pad = outline + 3
    a = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    h, w = a.shape
    x, y = (ground.shape[1] - w) // 2, (ground.shape[0] - h) // 2
    comp = ground.copy()
    roi = comp[y:y + h, x:x + w].astype(np.float32)
    exact = a > 0
    if outline:
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * outline + 1,) * 2)
        halo = cv2.GaussianBlur(cv2.dilate(a, disc), (0, 0), 0.7)
        cover = halo.astype(np.float32)[..., None] / 255
        roi = roi * (1 - cover) + (0 if light else 255) * cover
        exact = exact | (halo > 12)
    cover = a.astype(np.float32)[..., None] / 255
    roi = roi * (1 - cover) + (255 if light else 0) * cover
    comp[y:y + h, x:x + w] = np.round(roi).astype(np.uint8)
    full, strokes = np.zeros(ground.shape[:2], bool), np.zeros(ground.shape[:2], bool)
    full[y:y + h, x:x + w], strokes[y:y + h, x:x + w] = exact, a > 0
    return comp, full, strokes


def grounds(ps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The grounds set: lettering (`glyph_patch` mattes, any series) on clean grounds, each with every outline of
    `OUTLINES`: flat grey (120, 200), four gradients, twelve screentones (4-8 px, 15-50 %), six of line art, four of
    white line art on black (light lettering on it when it has no outline), and `ART_EACH` crops of real art per
    kind; two mattes on each synthetic ground, one on each crop. The ground itself is the truth."""
    rng = random.Random(SEED + 2)
    mattes: list[np.ndarray] = []
    for p in ps:
        gray = cv2.cvtColor(load(p["path"]), cv2.COLOR_RGB2GRAY)
        for b in p["boxes"]:
            alpha = glyph_patch(gray[b[1]:b[3], b[0]:b[2]])
            if alpha is not None and alpha.shape[0] * alpha.shape[1] >= 800 and max(alpha.shape) <= 300:
                mattes.append((alpha * 255).astype(np.uint8))
    rng.shuffle(mattes)
    base: list[tuple[str, np.ndarray]] = [("flat", np.full((SIDE, SIDE, 3), v, np.uint8)) for v in (120, 200)]
    base += [("gradient", shading(rng.uniform(60, 240), rng.uniform(60, 240), rng.uniform(0, 180)))
             for _ in range(4)]
    base += [("tone", halftone(pitch, cover, 0 if pitch == 5 else 45))
             for pitch in (4, 5, 6, 8) for cover in (0.15, 0.3, 0.5)]
    base += [("lines", line_art(rng)) for _ in range(6)] + [("dark", line_art(rng, dark=True)) for _ in range(4)]
    base += art_crops(ps, rng)
    out: list[dict[str, Any]] = []
    k = 0
    for kind, ground in base:
        for outline in OUTLINES:
            for _ in range(1 if kind.startswith("art") else 2):
                light = kind == "dark" and not outline
                comp, exact, strokes = lettered(ground, mattes[k % len(mattes)], outline, light)
                k += 1
                out.append({"bg": kind, "outline": outline, "comp": comp, "page": ground, "exact": exact,
                            "strokes": strokes, "light": light})
    return out


def ground_region(s: dict[str, Any]) -> Any:
    """The region a text block of the lettering would be: its box tight on the strokes (`letter_box`, the white
    outline beyond it), its mask that box and 6 px round it."""
    from taslation.regions import TextRegion

    level = s["comp"].max(axis=2) > 105 if s["light"] else s["comp"].min(axis=2) < 150
    ys, xs = np.nonzero(s["strokes"] & level)
    if not xs.size:
        ys, xs = np.nonzero(s["strokes"])
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    x0, y0, x1, y1 = box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box=box,
                      letter_box=box, kind="text-dark" if s["light"] else "text")


def luma(img: np.ndarray) -> np.ndarray:
    return img[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def ground_score(result: np.ndarray, s: dict[str, Any], pad: int = 8) -> dict[str, float]:
    """The erase of a grounds sample against its ground: `score`'s three numbers ("mae", "outside", "left"), the
    strokes left ("ink": stroke pixels still as dark as ink and 40 darker than the ground) and the outline left
    ("ghost": outline pixels still white and 40 lighter), the mean lightness off in the mask ("bias"), and the step
    at the edge of what the erase changed ("step": the mean lightness just inside it less just outside it, against
    the same of the ground; 0 when the fill meets its surroundings as the ground does)."""
    page, exact = s["page"], s["exact"]
    ys, xs = np.nonzero(exact)
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1, y1 = min(page.shape[1], int(xs.max()) + 1 + pad), min(page.shape[0], int(ys.max()) + 1 + pad)
    r, g = result[y0:y1, x0:x1], page[y0:y1, x0:x1]
    e, ink = exact[y0:y1, x0:x1], s["strokes"][y0:y1, x0:x1]
    d = np.abs(r.astype(np.float32) - g.astype(np.float32)).mean(axis=2)
    lr, lg = luma(r), luma(g)
    if s["light"]:
        left_ink, ghost = ink & (lr > 155) & (lr > lg + 40), e & ~ink & (lr < 60) & (lr < lg - 40)
    else:
        left_ink, ghost = ink & (lr < 100) & (lr < lg - 40), e & ~ink & (lr > 200) & (lr > lg + 40)
    out = {"mae": float(d[e].mean()), "outside": float(d[~e].mean()), "left": float((d[e] > 40).mean()),
           "ink": float(left_ink.sum()), "ghost": float(ghost.sum()), "bias": float((lr - lg)[e].mean()),
           "step": np.nan}
    changed = (r != s["comp"][y0:y1, x0:x1]).any(axis=2).astype(np.uint8)
    inner = (changed > 0) & ~(cv2.erode(changed, np.ones((5, 5), np.uint8)) > 0)
    outer = (cv2.dilate(changed, np.ones((5, 5), np.uint8)) > 0) & (changed == 0)
    if inner.any() and outer.any():
        out["step"] = abs(float((lr[inner].mean() - lr[outer].mean()) - (lg[inner].mean() - lg[outer].mean())))
    return out


def run_grounds(samples: list[dict[str, Any]], erases: dict[str, Any], lama: Any, settings: Settings) -> None:
    """Each erase on each grounds sample, numbers per ground and per outline."""
    rows: dict[str, list[tuple[dict[str, Any], dict[str, float]]]] = {e: [] for e in erases}
    seconds = dict.fromkeys(erases, 0.0)
    before = dict(lama.counts)
    s_ = settings
    for s in samples:
        for how, erase in erases.items():
            image = s["comp"].copy()
            t = time.perf_counter()
            erase(image, ground_region(s), s_.erase_mode, s_.white_threshold, s_.dark_threshold, s["light"])
            seconds[how] += time.perf_counter() - t
            rows[how].append((s, ground_score(image, s)))
    went = {k: lama.counts[k] - before[k] for k in lama.counts}
    print(f"grounds: {len(samples)} samples, the lama arm's regions went to {went}")
    keys = ("mae", "outside", "left", "ink", "ghost", "bias", "step")
    for how in erases:
        print(f"  {how}: {1000 * seconds[how] / max(1, len(samples)):.0f} ms a region")
        print(f"    {'':12} {'n':>4} " + " ".join(f"{k:>8}" for k in keys))
        groups = [(g, lambda s, g=g: s["bg"] == g) for g in GROUND_KINDS]
        groups += [(f"outline {o}", lambda s, o=o: s["outline"] == o) for o in OUTLINES] + [("all", lambda s: True)]
        for name, pick in groups:
            chosen = [m for s, m in rows[how] if pick(s)]
            if not chosen:
                continue
            vals = [np.nanmean([m[k] for m in chosen]) * (100 if k == "left" else 1) for k in keys]
            print(f"    {name:12} {len(chosen):4d} " + " ".join(f"{v:8.2f}" for v in vals))


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
    ap.add_argument("--set", choices=SETS, action="append", help="only this set (default: all three)")
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
    wanted = args.set or SETS
    pipeline = None
    if any(name != "grounds" for name in wanted):  # (the grounds set needs no detection: its regions are made)
        pipeline = Pipeline(s, ocr=Readers(s.models_dir, s.ocr_threads), translator=None, cache=None)
        print(f"layout model: {'on' if pipeline.layout is not None else 'off'}", flush=True)
    erases = erasers(s.models_dir)
    lama = erases["lama"].__self__  # (the "lama" arm's ArtEraser: what its regions went to, where it ran)
    t0 = time.monotonic()
    lama.warm()  # loaded ahead, so that the arm's seconds are the erase's alone
    print(f"LaMa loaded on {'the GPU' if lama.uses_gpu() else 'the CPU'} in {time.monotonic() - t0:.1f} s", flush=True)
    ps = pages(args.root)
    if "grounds" in wanted:
        run_grounds(grounds(ps)[:args.limit or None], erases, lama, s)
    plain = pairs(ps) if pipeline is not None else []
    sets = {"plain": plain, "outlined": outlined(ps, plain) if plain else []}
    for name in (n for n in wanted if n != "grounds"):
        assert pipeline is not None
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
            by_ground = {g: round(float(np.mean([v for v, smp in zip(values[:, 0], samples) if smp["bg"] == g])), 1)
                         for g in GROUNDS}
            per = 1000 * seconds[how] / max(1, len(samples))
            print(f"  {how:6} MAE {values[:, 0].mean():6.2f} {by_ground} outside {values[:, 1].mean():.2f} left {100 * values[:, 2].mean():.1f} %"
                  f"; erase {per:.0f} ms a pair")
    lama.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
