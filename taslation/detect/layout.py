"""The layout model: where the lettering and the bubbles are, as a model sees them.

ogkalu/comic-text-and-bubble-detector (RT-DETR v2, 640 px, classes bubble, text in a bubble, free text) runs over each
page unit (`LayoutModel.boxes`), and `model_regions` turns its boxes into regions: a text box inside a bubble box is
that bubble's text, several in one bubble are one region, a bubble without a text box takes its ink, a text box alone
is a text region padded a little. The classical detectors stay: the regions they find beside the model's are read too,
after them (``Pipeline._ocr_regions``: model first, the classical adds what the model missed).

The OCR reads a model region's plain box; for the erase and the lettering it then takes a classical shape (`Shaper`,
applied after the reading: a rebuilt mask in front of the OCR reads worse). That shape is the mask of a classical region
about the same size where one exists (tier 0), else what the classical detectors make of the box's crop (tier 1), else
the white area around the lettering (tier 2), else the plain box (tier 3).

The model is loaded from local files on first use, on the GPU when torch has one and on the CPU when it has none or the
GPU is full; `LayoutModel.release` gives its memory back and the next page loads it again. Nothing is fetched: the
weights are ``setup_models.py``'s to fetch, ``transformers`` reads the model's two files and no code comes with them.
"""

from __future__ import annotations

import copy
import gc
import importlib.util
import logging
import threading
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from ..config import LAYOUT_MODEL
from ..regions import Box, TextRegion
from .bubbles import BubbleDetector, DetectorConfig, fill_holes
from .textblocks import TextBlockConfig, TextBlockDetector

LOG = logging.getLogger(__name__)

SIZE = 640  # px: the model's input, a page unit resized to a square as it was trained
SMALLEST_UNIT = 32  # px: a page unit narrower than this holds nothing to look at
TEXT_SCORE = 0.7  # a text box counts from this score ...
BUBBLE_SCORE = 0.5  # ... a bubble box from this one ...
LOW_SCORE = 0.05  # ... and what lies under this one is not even kept
SAME_LETTERING = 0.6  # a box this much inside a surer one of its class repeats it; a text this much in a bubble is its text
STRADDLES = 0.3  # ... and a text this much in a bubble with no other text is its text too (lettering over the edge)
TEXT_PAD = 0.08  # a text box alone is padded by this share of its short side, at least `MIN_PAD` px
MIN_PAD = 4
CROP_PAD = 6  # px around a model box when the classical detectors look at its crop
SAME_REGION = 0.5  # IoU with a classical region that makes it the same region, half its text box in the model's
CONFIRMED = 0.5  # a classical block on the crop is the region's when this share of the text box lies in it
COVERED = 0.3  # a box this much inside what was read already reads the same lettering

TEXT, BUBBLE = "text", "bubble"
CLASSES = {0: BUBBLE, 1: TEXT, 2: TEXT}  # the model's ids: bubble, text in a bubble, free text

Detection = tuple[float, float, float, float, float, str]  # x0, y0, x1, y1 on the page, score, TEXT or BUBBLE


def available(models_dir: Path) -> bool:
    """Whether the model's files and ``transformers`` are here (nothing is imported or loaded for it)."""
    return not LAYOUT_MODEL.missing(models_dir) and importlib.util.find_spec("transformers") is not None


class LayoutModel:
    """The model in *models_dir*, loaded on first use."""

    def __init__(self, models_dir: Path):
        self.folder = Path(models_dir) / LAYOUT_MODEL.dirname
        self.failed = False  # it could not run: the classical detectors work alone from then on
        self._net: Any = None
        self._device = ""
        self._release_asked = False  # a release that came while the model was at work: done once it is free
        self._lock = threading.Lock()

    def uses_gpu(self) -> bool:
        """Whether the model runs on the GPU: where it is loaded, else where it would load (torch is imported only
        when it is loaded or when nothing else imported it yet)."""
        if self.failed:
            return False
        if self._device:
            return self._device == "cuda"
        import torch

        return bool(torch.cuda.is_available())

    def _load(self, device: str = "") -> None:
        import torch
        from transformers import RTDetrV2ForObjectDetection
        from transformers.utils import logging as hf_logging

        hf_logging.disable_progress_bar()  # (a window has no console for it)
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._device = device  # (what a failed load has to free)
        self._net = RTDetrV2ForObjectDetection.from_pretrained(str(self.folder), local_files_only=True,
                                                               use_safetensors=True,
                                                               trust_remote_code=False).eval().to(device)
        self._device = device

    def _forward(self, rgb: np.ndarray) -> list[Detection]:
        import torch

        h, w = rgb.shape[:2]
        x = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
        pixels = torch.from_numpy(x.transpose(2, 0, 1))[None].to(self._device)
        with torch.no_grad():
            out = self._net(pixel_values=pixels)
        scores, ids = out.logits.sigmoid()[0].max(-1)
        keep = scores >= LOW_SCORE
        scores, ids, boxes = scores[keep].cpu().numpy(), ids[keep].cpu().numpy(), out.pred_boxes[0][keep].cpu().numpy()
        cx, cy, bw, bh = boxes.T
        return [(float(a), float(b), float(c), float(d), float(s), CLASSES[int(i)])
                for a, b, c, d, s, i in zip((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h,
                                            scores, ids) if int(i) in CLASSES]

    def detect(self, rgb: np.ndarray) -> list[Detection]:
        """The boxes of one page unit, in its coordinates. With the GPU full (loading or running) it goes on on the
        CPU; the failed step's tensors are let go first (the exception, whose traceback holds them, is left behind)."""
        import torch

        with self._lock:
            device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            full = False
            try:
                if self._net is None:
                    self._load(device)
                return self._forward(rgb)
            except torch.cuda.OutOfMemoryError:
                if device == "cpu":
                    raise
                full = True
            finally:
                if self._release_asked and not full:
                    self._release_asked = False
                    self._drop()
            LOG.info("the GPU is full: the layout model goes on on the CPU")
            self._drop("cuda")
            self._load("cpu")
            return self._forward(rgb)

    def warm(self) -> bool:
        """Loaded, and run once on a blank square, ahead of the first page (`Pipeline.warm_page_models`): the load
        (about 5 s with the GPU's start) and the first run's set-up (0.4 s) are then paid before a page waits for them.
        A release asked meanwhile is done once it is over (`release`). Never raises: whether it worked."""
        if self.failed:
            return False
        try:
            self.detect(np.full((SMALLEST_UNIT * 2, SMALLEST_UNIT * 2, 3), 255, np.uint8))
        except Exception as e:  # noqa: BLE001 - the first page tries again, and says what is wrong
            LOG.info("the layout model could not be loaded ahead (%s)", type(e).__name__)
            return False
        return True

    def boxes(self, rgb: np.ndarray, units: Sequence[Box]) -> list[Detection] | None:
        """The boxes of the page units *units* of the page *rgb*, in page coordinates; None when the model cannot run
        (said in the log; the classical detectors work alone from then on)."""
        if self.failed:
            return None
        found: list[Detection] = []
        try:
            for x0, y0, x1, y1 in units:
                if x1 - x0 < SMALLEST_UNIT or y1 - y0 < SMALLEST_UNIT:
                    continue
                found.extend((round(a + x0, 1), round(b + y0, 1), round(c + x0, 1), round(d + y0, 1), round(s, 4), kind)
                             for a, b, c, d, s, kind in self.detect(rgb[y0:y1, x0:x1]))
        except Exception as e:  # noqa: BLE001 - the page matters more than the model: classical detection goes on
            LOG.warning("the layout model failed (%s): classical detection from now on", type(e).__name__)
            self.failed = True
            return None
        return found

    def _drop(self, device: str = "") -> None:
        import torch

        self._net = None
        gc.collect()
        if (device or self._device) == "cuda":
            torch.cuda.empty_cache()
        self._device = ""

    def release(self) -> None:
        """Give the model's memory back; the next page loads it again. Never waits: while the model is at work the
        release is done as soon as it is free."""
        if not self._lock.acquire(blocking=False):
            self._release_asked = True
            return
        try:
            if self._net is not None:
                self._drop()
        finally:
            self._lock.release()


# ------------------------------------------------------------------ boxes to regions
def _inter(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(a: Sequence[float]) -> float:
    return max(0, a[2] - a[0]) * max(0, a[3] - a[1])


def _dark_ground(gray: np.ndarray, box: Sequence[float]) -> bool:
    x0, y0, x1, y1 = (int(v) for v in box[:4])
    crop = gray[y0:y1, x0:x1]
    if crop.size < 16:
        return False
    level, _ = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return bool((crop > level).mean() < 0.5)


def _ink_box(gray: np.ndarray, box: Sequence[float], dark: bool) -> tuple[int, int, int, int]:
    """The lettering's box inside a bubble that has no text box of its own."""
    x0, y0, x1, y1 = (int(v) for v in box[:4])
    ix, iy = int(0.08 * (x1 - x0)), int(0.08 * (y1 - y0))
    crop = gray[y0 + iy:y1 - iy, x0 + ix:x1 - ix]
    if crop.size == 0:
        return x0, y0, x1, y1
    ink = ((crop > 170) if dark else (crop < 110)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    ch, cw = crop.shape
    edge = [i for i in range(1, n) if stats[i, 0] == 0 or stats[i, 1] == 0 or stats[i, 0] + stats[i, 2] == cw
            or stats[i, 1] + stats[i, 3] == ch]  # the bubble's outline, which the inset can take in at a curve
    if edge:
        ink[np.isin(labels, edge)] = 0
    ys, xs = np.nonzero(ink)
    if len(xs) < 8:
        return x0 + ix, y0 + iy, x1 - ix, y1 - iy
    return x0 + ix + int(xs.min()), y0 + iy + int(ys.min()), x0 + ix + int(xs.max()) + 1, y0 + iy + int(ys.max()) + 1


def _region(shape: tuple[int, ...], gray: np.ndarray, box: Sequence[float], text: Sequence[float],
            bubble: bool) -> TextRegion | None:
    h, w = shape[:2]
    x0, y0, x1, y1 = max(0, int(box[0])), max(0, int(box[1])), min(w, int(box[2] + 0.999)), min(h, int(box[3] + 0.999))
    tb = (max(x0, int(text[0])), max(y0, int(text[1])), min(x1, int(text[2] + 0.999)), min(y1, int(text[3] + 0.999)))
    if x1 - x0 < 6 or y1 - y0 < 6 or tb[2] - tb[0] < 3 or tb[3] - tb[1] < 3:
        return None
    dark = _dark_ground(gray, tb)
    kind = ("dark-bubble" if dark else "bubble") if bubble else ("text-dark" if dark else "text")
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box=tb,
                      kind=kind, from_model=True)


def _surest(boxes: list[Detection]) -> list[Detection]:
    """*boxes*, surest first, without those that repeat a surer one."""
    kept: list[Detection] = []
    for d in sorted(boxes, key=lambda d: -d[4]):
        if not any(_inter(d, k) > SAME_LETTERING * min(_area(d), _area(k)) for k in kept):
            kept.append(d)
    return kept


def model_regions(rgb: np.ndarray, detections: Sequence[Detection]) -> list[TextRegion]:
    """The regions the model's *detections* (page coordinates) make; the bubbles first."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    texts = _surest([d for d in detections if d[5] == TEXT and d[4] >= TEXT_SCORE])
    bubbles = _surest([d for d in detections if d[5] == BUBBLE and d[4] >= BUBBLE_SCORE])
    inside: list[list[Detection]] = [[] for _ in bubbles]
    alone: list[Detection] = []
    straddling: list[tuple[Detection, int]] = []
    for d in texts:
        best, at = 0.0, -1
        for i, b in enumerate(bubbles):
            share = _inter(d, b) / max(1.0, _area(d))
            if share > best:
                best, at = share, i
        if best >= SAME_LETTERING:
            inside[at].append(d)
        elif best >= STRADDLES:
            straddling.append((d, at))
        else:
            alone.append(d)
    for d, at in straddling:  # lettering over a bubble's edge: the bubble's, unless the bubble has text of its own
        if inside[at]:
            alone.append(d)
            continue
        inside[at].append(d)
        b = bubbles[at]  # the region reaches as far as its lettering does
        bubbles[at] = (min(b[0], d[0]), min(b[1], d[1]), max(b[2], d[2]), max(b[3], d[3]), b[4], b[5])
    out: list[TextRegion] = []
    for b, held in zip(bubbles, inside):
        if held:
            tb: Sequence[float] = (min(t[0] for t in held), min(t[1] for t in held),
                                   max(t[2] for t in held), max(t[3] for t in held))
        else:
            clipped = (max(0, b[0]), max(0, b[1]), min(gray.shape[1], b[2]), min(gray.shape[0], b[3]))
            tb = _ink_box(gray, clipped, _dark_ground(gray, (max(0, b[0]), max(0, b[1]), b[2], b[3])))
        r = _region(rgb.shape, gray, b, tb, True)
        if r is not None:
            out.append(r)
    for d in alone:
        pad = max(MIN_PAD, int(TEXT_PAD * min(d[2] - d[0], d[3] - d[1])))
        r = _region(rgb.shape, gray, (d[0] - pad, d[1] - pad, d[2] + pad, d[3] + pad), d, False)
        if r is not None:
            out.append(r)
    return out


def cover_of(region: TextRegion, read: Sequence[TextRegion]) -> TextRegion | None:
    """The first of *read* (regions read as text) whose lettering *region*'s repeats: their text boxes share `COVERED` of
    either one, or *region*'s text box lies mostly (`SAME_LETTERING`) in the other's shape (its mask, the classical shape
    it is to take where it has one); None when none does."""
    t = region.text_box
    for r in read:
        shared = _inter(t, r.text_box)
        if shared >= COVERED * max(1, _area(t)) or shared >= COVERED * max(1, _area(r.text_box)):
            return r
        mask = (r.after or r).mask
        x0, y0, x1, y1 = max(t[0], r.x0), max(t[1], r.y0), min(t[2], r.x1), min(t[3], r.y1)
        if x1 > x0 and y1 > y0 and mask.shape == (r.height, r.width):
            inside = int((mask[y0 - r.y0:y1 - r.y0, x0 - r.x0:x1 - r.x0] > 0).sum())
            if inside >= SAME_LETTERING * max(1, _area(t)):
                return r
    return None


def covered(region: TextRegion, read: Sequence[TextRegion]) -> bool:
    """Whether *region* repeats what one of *read* holds (`cover_of`)."""
    return cover_of(region, read) is not None


# ------------------------------------------------------------------ the classical shape of a model region
class Shaper:
    """Rebuilds the classical shape of a model region (the thresholds are the settings')."""

    def __init__(self, white_threshold: int = 225, dark_threshold: int = 140):
        self.white = white_threshold
        self.bubbles = BubbleDetector(DetectorConfig(white_threshold=white_threshold, dark_threshold=dark_threshold,
                                                     max_area_ratio=1.0, min_area_ratio=0.0))  # the crop is nearly all bubble
        self.blocks = TextBlockDetector(TextBlockConfig(white_threshold=white_threshold, dark_threshold=dark_threshold))

    @staticmethod
    def _adopt(r: TextRegion, classical: Sequence[TextRegion]) -> bool:
        """Tier 0: the classical region about the same as *r* gives it its mask."""
        for c in classical:
            x0, y0, x1, y1 = max(r.x0, c.x0), max(r.y0, c.y0), min(r.x1, c.x1), min(r.y1, c.y1)
            if x1 <= x0 or y1 <= y0:
                continue
            i = (x1 - x0) * (y1 - y0)
            if (i / (max(1, _area(r.bbox)) + max(1, _area(c.bbox)) - i) < SAME_REGION
                    or _inter(c.text_box, r.text_box) < SAME_REGION * max(1, _area(c.text_box))):
                continue
            mask = c.mask
            if mask.shape != (c.height, c.width):
                mask = cv2.resize(mask, (c.width, c.height), interpolation=cv2.INTER_NEAREST)
            canvas = np.zeros((r.height, r.width), np.uint8)
            canvas[y0 - r.y0:y1 - r.y0, x0 - r.x0:x1 - r.x0] = mask[y0 - c.y0:y1 - c.y0, x0 - c.x0:x1 - c.x0]
            r.mask, r.tier, r.adopted = canvas, 0, c
            return True
        return False

    def rebuilt(self, rgb: np.ndarray, region: TextRegion, classical: Sequence[TextRegion]) -> TextRegion:
        """A copy of *region* with the classical shape; its ``adopted`` is the classical region that gave it."""
        r = copy.copy(region)
        if self._adopt(r, classical):
            return r
        h, w = rgb.shape[:2]
        x0, y0, x1, y1 = max(0, r.x0 - CROP_PAD), max(0, r.y0 - CROP_PAD), min(w, r.x1 + CROP_PAD), min(h, r.y1 + CROP_PAD)
        sub = rgb[y0:y1, x0:x1]
        gray = cv2.cvtColor(sub, cv2.COLOR_RGB2GRAY)
        tb = (r.text_box[0] - x0, r.text_box[1] - y0, r.text_box[2] - x0, r.text_box[3] - y0)
        try:
            found = self.bubbles.detect(sub, inverted=r.dark)
            if r.kind not in ("bubble", "dark-bubble"):
                found = self.blocks.detect(sub, inverted=r.dark, taken=[]) + found
        except Exception:  # noqa: BLE001 - a crop the classical detectors cannot take: the white area or the plain box
            found = []
        best, score = None, 0.0
        for c in found:
            share = _inter(c.text_box, tb) / max(1, _area(tb))
            if share > score:
                best, score = c, share
        canvas = np.zeros((y1 - y0, x1 - x0), np.uint8)
        if best is not None and score >= CONFIRMED:
            mask = best.mask
            if mask.shape != (best.height, best.width):
                mask = cv2.resize(mask, (best.width, best.height), interpolation=cv2.INTER_NEAREST)
            canvas[best.y0:best.y1, best.x0:best.x1] = mask
            r.tier = 1
        else:
            area = self._white_area(255 - gray if r.dark else gray, tb)
            if area is None:
                r.tier = 3  # the plain box stays its mask
                return r
            canvas, r.tier = area, 2
        r.mask = np.ascontiguousarray(canvas[r.y0 - y0:r.y1 - y0, r.x0 - x0:r.x1 - x0])
        return r

    def _white_area(self, gray: np.ndarray, tb: tuple[int, int, int, int]) -> np.ndarray | None:
        """Tier 2: the white area most of the text box lies on, its holes filled and drawn in a little; None when
        there is none as large as the text box."""
        white = cv2.erode(((gray >= self.white) * 255).astype(np.uint8), np.ones((3, 3), np.uint8))
        _n, labels, _stats, _ = cv2.connectedComponentsWithStats(white, connectivity=4)
        x0, y0, x1, y1 = (max(0, v) for v in tb)
        ids, counts = np.unique(labels[y0:y1, x0:x1], return_counts=True)
        counts, ids = counts[ids > 0], ids[ids > 0]
        if not len(ids):
            return None
        filled = fill_holes(((labels == int(ids[counts.argmax()])) * 255).astype(np.uint8))
        inner = cv2.erode(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        return inner if cv2.countNonZero(inner) >= 0.8 * max(1, _area(tb)) else None


def take_shape(r: TextRegion) -> None:
    """*r* takes the classical shape kept for it; the classical region it agreed with gives it its kind too, and its
    lettering box as far as it lies in *r* (a classical region may reach into the next bubble)."""
    shaped = r.after
    if shaped is None:
        return
    r.after = None
    r.mask, r.tier = shaped.mask, shaped.tier
    c = shaped.adopted
    r.adopted = c
    if c is not None:
        r.kind, r.glyph, r.pieces = c.kind, c.glyph, c.pieces
        lb = c.letter_box or c.text_box
        lb = (max(lb[0], r.x0), max(lb[1], r.y0), min(lb[2], r.x1), min(lb[3], r.y1))
        r.letter_box = lb if lb[2] > lb[0] and lb[3] > lb[1] else r.text_box


__all__ = ["BUBBLE_SCORE", "LayoutModel", "SIZE", "Shaper", "TEXT_SCORE", "available", "cover_of", "covered",
           "model_regions", "take_shape"]
