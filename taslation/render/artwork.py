"""Lettering set on the drawing: taken out by an inpainting model, the drawing under it made up.

Paint cannot do this: a bubble has paper to fill, lettering on hatching, tone or a face has none. A region whose ground,
in a ring round its box, is not one flat colour (`on_art`) goes here: `art_mask` finds its lettering, the dark pieces
ringed by white with their rings (`ring_comp`, on the negative too for light lettering), and LaMa (`lama`) fills just
that. Everything else stays with `erase_region`, bubbles on their paper; so does a region whose box holds too little
of such lettering to be sure.

A model "bubble" that the classical detectors could not close is judged here too: with its plain box as the mask (tier
3) always, with a white area (tier 2) when its ground is not flat; one that has paper between its strokes after all
(`on_paper`: an open or a thin outline) goes back to the paper fill. So does lettering whose ground right round it is
one flat colour or a smooth shading (`plain_ground`: a black or white panel, a gradient), where the model only
blotches what the fill paints as it was.

LaMa runs in torch, on the GPU when torch has one (about 0.6 s a screen) and on the CPU otherwise (about 4 s). Where
it runs at all is the setting `art_erase`, read by one rule (`runs_here`, and `available` for the weights too): "auto",
the default, only where torch has a CUDA GPU, so that a computer without one erases exactly as with "off" and never
loads the model; "lama" everywhere, on the CPU too; "off" nowhere. It is loaded on first use; `ArtEraser.release`
gives its memory back and the next erase loads it again. A failure on the GPU moves the work to the CPU for the rest
of the session (a fallback, not the rule's choice), one on the CPU leaves the regions to `erase_region`.

``erase_mode = "fill"`` only: "inpaint" and "classic" stay as they are, whole pages of them.
"""

from __future__ import annotations

import gc
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from ..config import LAMA_MODEL
from ..regions import TextRegion
from .erase import erase_region, paper_colour, paper_surface

LOG = logging.getLogger(__name__)

ART_ERASES = ("auto", "lama", "off")
ART_KINDS = ("text", "text-on-page", "text-dark", "text-on-dark")
FLAT_GROUND = 6.0  # grey levels: nine in ten pixels of a ring this close to its median are one flat colour
RING_OUT, RING_IN = 14, 2  # px: the ring round a region's box its ground is judged on
PIECE = 80  # px: a dark piece longer than this, or than 1.15 times the box's short side, is not a glyph ...
WIDE_GLYPH = 1.15  # ... (big lettering: a glyph as wide as its column)
DARK, RINGED = 150, 200  # grey levels of a stroke, and of the white ring round it
RING_SHARE = 0.55  # the share of a piece's edge that is white when it is ringed
MIN_MASK = 0.03  # of the box: less lettering than this is not worth a model
REACH = 8  # px (or a tenth of the box's short side) past the box the lettering is followed
EDGE = 4  # px along a model bubble's box edge where a piece is its outline ...
ALONG = 0.6  # ... when this share of it lies there (a glyph near the edge only touches it)
OUTLINE_LEVEL = 215  # grey level under which a pixel is ink, a thin grey outline's too (`on_paper`)
GROUND_BAND = 9  # px (a disc): the ground right round the hole, on which a flat or shaded ground is told ...
GROUND_FIT = 8.0  # ... when nine in ten of its pixels lie this close (RGB) to a smooth surface fitted to it
EDGE_INK = 0.15  # ... and the ink reaching in from its box's edge at most this share: a thin outline, not the art
PAPER_SHARE = 0.3  # of an unclosed model bubble's lettering box: the ground between its strokes, when it is paper
WINDOW = 512  # px: the part of the page the model sees (at least)
SMALLEST = 256  # px: a page narrower than this is left to the paper fill (the network pads by reflection)

Erase = Callable[..., tuple[int, int, int]]


def is_dash(st: np.ndarray, i: int, width: int, height: int) -> bool:
    """A long dash of the lettering: a straight stroke (2-16 px wide, up to 300 long) off the box's edges, in line with
    a glyph-sized piece at one of its ends. Lines of the drawing and bubble outlines touch the box's edge or stand
    alone. *st*: `connectedComponentsWithStats`'s stats of the box."""
    x, y, w, h, a = (int(v) for v in st[i])
    long, short = max(w, h), min(w, h)
    if not (2 <= short <= 16 and long >= 5 * short and long <= 300 and a >= 0.4 * w * h):
        return False
    if x < 2 or y < 2 or x + w > width - 2 or y + h > height - 2:
        return False
    down = h >= w
    cx, cy = x + w / 2, y + h / 2
    for j in range(1, len(st)):
        if j == i:
            continue
        ox, oy, ow, oh, _a = (int(v) for v in st[j])
        if max(ow, oh) > 60 or max(ow, oh) < 6:
            continue
        if down and abs(ox + ow / 2 - cx) <= 18 and min(abs(oy - (y + h)), abs(y - (oy + oh))) <= 40:
            return True
        if not down and abs(oy + oh / 2 - cy) <= 18 and min(abs(ox - (x + w)), abs(x - (ox + ow))) <= 40:
            return True
    return False


def ring_comp(gray: np.ndarray, short: int = 0) -> np.ndarray:
    """The lettering of the box *gray*: dark pieces of a glyph's size (`PIECE`, or `WIDE_GLYPH` times the box's short
    side, *short* when the crop is wider than the box; a long dash too) ringed by white, even on black art, and the ring
    goes with them."""
    return ringed(gray, short)[0]


def ringed(gray: np.ndarray, short: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """`ring_comp`'s mask, and its strokes alone (the dark pieces it took, without their rings)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats((gray < DARK).astype(np.uint8), connectivity=8)
    keep = np.zeros(gray.shape, np.uint8)
    limit = max(PIECE, WIDE_GLYPH * (short or min(gray.shape)))
    edge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 4 or (max(w, h) > limit and not is_dash(stats, i, gray.shape[1], gray.shape[0])):
            continue
        x0, y0 = max(0, x - 3), max(0, y - 3)
        piece = (labels[y0:y + h + 3, x0:x + w + 3] == i).astype(np.uint8)
        band = (cv2.dilate(piece, edge) > 0) & (piece == 0)
        if band.sum() and (gray[y0:y + h + 3, x0:x + w + 3][band] >= RINGED).mean() >= RING_SHARE:
            keep[y0:y + h + 3, x0:x + w + 3] |= piece
    grown = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))) > 0
    fringe = cv2.dilate(keep, np.ones((3, 3), np.uint8)) > 0
    return (keep > 0) | (fringe & (gray < 215)) | (grown & (gray >= 190)), keep > 0


def box_of(image: np.ndarray, region: TextRegion) -> tuple[int, int, int, int]:
    """The region's lettering box, within the page; a model region's also takes in the model's own text box (a
    classical block it took its shape from may hold only part of its lettering)."""
    b = region.letter_box or region.text_box
    if region.from_model and region.letter_box is not None:
        t = region.text_box
        b = (min(b[0], t[0]), min(b[1], t[1]), max(b[2], t[2]), max(b[3], t[3]))
    h, w = image.shape[:2]
    return max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3])


def on_art(image: np.ndarray, region: TextRegion, flat: float = FLAT_GROUND) -> bool:
    """Whether *region* is lettering on the page whose ground, in a ring round its box, is not one flat colour; a
    bubble the classical detectors could not close is judged as the module's docstring says."""
    if region.kind in ("bubble", "dark-bubble"):
        if region.tier == 3:
            return True
        if region.tier != 2:
            return False
    elif region.kind not in ART_KINDS:
        return False
    x0, y0, x1, y1 = box_of(image, region)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return False
    h, w = image.shape[:2]
    ox0, oy0, ox1, oy1 = max(0, x0 - RING_OUT), max(0, y0 - RING_OUT), min(w, x1 + RING_OUT), min(h, y1 + RING_OUT)
    gray = cv2.cvtColor(image[oy0:oy1, ox0:ox1], cv2.COLOR_RGB2GRAY).astype(np.float32)
    ring = np.ones(gray.shape, bool)
    ring[max(0, y0 - RING_IN - oy0):y1 + RING_IN - oy0, max(0, x0 - RING_IN - ox0):x1 + RING_IN - ox0] = False
    ground = gray[ring]
    if ground.size < 16:
        return False
    return float(np.percentile(np.abs(ground - np.median(ground)), 90)) >= flat


def art_mask(image: np.ndarray, region: TextRegion) -> np.ndarray | None:
    """The lettering of *region* as a boolean mask of the page; None when its box holds too little of it. It is found in
    the box (`ring_comp`); past the box (by `REACH`) only what continues a stroke it took is added: a glyph-sized dark
    piece the box's edge cut off. A model bubble's own box edge is its outline: a piece lying along it (`ALONG` of it
    within `EDGE` px) is left out; None too when that leaves too little."""
    x0, y0, x1, y1 = box_of(image, region)
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    inner, strokes = ringed(gray)
    if region.dark:  # light lettering ringed by dark: the same test on the negative
        negative, dark_strokes = ringed(255 - gray)
        inner, strokes = inner | negative, strokes | dark_strokes
    if inner.sum() < MIN_MASK * inner.size:
        return None
    reach = max(REACH, int(0.1 * min(x1 - x0, y1 - y0)))
    ox0, oy0, ox1, oy1 = max(0, x0 - reach), max(0, y0 - reach), min(w, x1 + reach), min(h, y1 + reach)
    mask = np.zeros((oy1 - oy0, ox1 - ox0), bool)
    mask[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0] = inner
    taken = np.zeros(mask.shape, bool)
    taken[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0] = strokes
    around = cv2.cvtColor(image[oy0:oy1, ox0:ox1], cv2.COLOR_RGB2GRAY)
    for ink in ((around < DARK) | (around > 255 - DARK) if region.dark else (around < DARK),):
        n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
        limit = max(PIECE, WIDE_GLYPH * min(x1 - x0, y1 - y0))
        go_on = np.zeros(n, bool)
        go_on[np.unique(labels[taken & ink])] = True
        go_on[0] = False
        go_on &= np.maximum(stats[:, 2], stats[:, 3]) <= limit
        cut = go_on[labels]
        mask |= cv2.dilate(cut.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if region.from_model and region.kind in ("bubble", "dark-bubble"):
        dark = (around > 255 - DARK) if region.dark else (around < DARK)
        n, labels = cv2.connectedComponents(dark.astype(np.uint8), connectivity=8)  # the dark pieces round the box
        border = np.ones(mask.shape, bool)
        bx0, by0, bx1, by1 = region.x0 - ox0, region.y0 - oy0, region.x1 - ox0, region.y1 - oy0
        border[max(0, by0 + EDGE):max(0, by1 - EDGE), max(0, bx0 + EDGE):max(0, bx1 - EDGE)] = False
        on_border = np.bincount(labels[border & dark].ravel(), minlength=n)
        every = np.bincount(labels.ravel(), minlength=n)
        along = on_border >= ALONG * np.maximum(1, every)  # a piece lying mostly in the band is the outline's
        along[0] = False
        if along.any():  # it stays, and so does the ring round it
            outline = along[labels]
            mask &= ~(cv2.dilate(outline.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))) > 0)
        if mask.sum() < MIN_MASK * inner.size:
            return None
    full = np.zeros(image.shape[:2], np.uint8)
    full[oy0:oy1, ox0:ox1] = mask
    return cv2.dilate(full, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0


def plain_ground(image: np.ndarray, hole: np.ndarray, box: tuple[int, int, int, int] | None = None) -> bool:
    """Whether the ground right round the lettering's *hole* (bool, the page; `GROUND_BAND`), within its lettering box
    *box* when given (what lies past it is the panel's border, the next drawing), is one colour or a smooth shading of
    it: a black or white panel, a flat tone, a gradient. There the paper fill paints what lay there and a model, which
    makes up a texture, only blotches it."""
    ys, xs = np.nonzero(hole)
    if not xs.size:
        return False
    h, w = hole.shape[:2]
    pad = GROUND_BAND
    x0, y0, x1, y1 = max(0, xs.min() - pad), max(0, ys.min() - pad), min(w, xs.max() + 1 + pad), min(h, ys.max() + 1 + pad)
    if box is not None:
        x0, y0, x1, y1 = max(x0, box[0]), max(y0, box[1]), min(x1, box[2]), min(y1, box[3])
        if x1 - x0 < 4 or y1 - y0 < 4:
            return False
    part = hole[y0:y1, x0:x1].astype(np.uint8)
    band = (cv2.dilate(part, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (GROUND_BAND, GROUND_BAND))) > 0) & (part == 0)
    if int(band.sum()) < 16:
        return False
    crop = image[y0:y1, x0:x1, :3]
    surface = paper_surface(crop, band)
    off = np.sqrt(((crop[band].astype(np.float32) - surface[band]) ** 2).sum(axis=1))
    return float(np.percentile(off, 90)) < GROUND_FIT


def on_paper(image: np.ndarray, region: TextRegion) -> bool:
    """Whether a layout model's bubble that the classical detectors could not close (tier 2 or 3) has paper under its
    lettering after all: the ground of its lettering box, all ink (`OUTLINE_LEVEL`, grown a little) left out, is one
    flat colour or a smooth shading of it (`GROUND_FIT`, as `plain_ground`) and `PAPER_SHARE` of the box, and the ink
    that reaches in from the box's edge (its outline, the drawing beyond) is no more than `EDGE_INK` of it. Its open or
    thin outline was what the detectors missed; the paper fill paints its lettering alone (`Pipeline._paper_erase`)."""
    if not region.from_model or region.kind not in ("bubble", "dark-bubble") or region.tier < 2:
        return False
    x0, y0, x1, y1 = box_of(image, region)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return False
    crop = image[y0:y1, x0:x1, :3]
    gray = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_RGB2GRAY)
    ink = (gray > 255 - OUTLINE_LEVEL) if region.dark else (gray < OUTLINE_LEVEL)
    _n, labels = cv2.connectedComponents(ink.astype(np.uint8), connectivity=8)
    rim = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    if float(np.isin(labels, rim[rim > 0]).mean()) > EDGE_INK:
        return False  # the drawing reaches in from the box's edge: lettering on the art, its white the drawing's
    ground = ~(cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    if int(ground.sum()) < PAPER_SHARE * ground.size:
        return False
    surface = paper_surface(crop, ground)
    off = np.sqrt(((crop[ground].astype(np.float32) - surface[ground]) ** 2).sum(axis=1))
    return float(np.percentile(off, 90)) < GROUND_FIT


def window(mask_shape: tuple[int, ...], x: int, y: int, h: int, w: int) -> tuple[int, int, int, int]:
    """The part of the page the model sees for a box at (*x*, *y*), *h* by *w*: `WINDOW` px, more for a larger box."""
    height, width = mask_shape[:2]
    side_h, side_w = min(max(WINDOW, h + 64), height), min(max(WINDOW, w + 64), width)
    y0 = int(np.clip(y + h // 2 - side_h // 2, 0, height - side_h))
    x0 = int(np.clip(x + w // 2 - side_w // 2, 0, width - side_w))
    return x0, y0, x0 + side_w, y0 + side_h


# ------------------------------------------------------------------ the model
_cuda: bool | None = None  # torch's answer to whether it has a CUDA GPU, once asked (`has_cuda`)


def has_cuda() -> bool:
    """Whether torch has a CUDA GPU on this computer, as the System page counts one (`devices.cuda_available`: only
    CUDA, torch imported if it is not yet, nothing loaded and no CUDA context made). Asked once, the first time an
    answer is needed (never when the config is read), and kept for the session."""
    global _cuda
    if _cuda is None:
        from ..devices import cuda_available

        _cuda = cuda_available()
    return _cuda


def runs_here(setting: str, cuda: bool | None = None) -> bool:
    """THE RULE for `art_erase`, which everything that asks whether the erase on the art runs goes by (`available`,
    `devices.stage_devices`, `health.page_models_missing`, the Settings dialog): "off" never; "lama" always, on the
    CPU too; "auto" (the default) only where torch has a CUDA GPU: *cuda* when the caller knows it, else `has_cuda`,
    asked only for "auto". The weights are `available`'s to check. A GPU that fails at run time moves the work to the
    CPU for the session (`ArtEraser._fill`): a fallback, not this rule's choice."""
    if setting == "off":
        return False
    if setting == "auto":
        return has_cuda() if cuda is None else bool(cuda)
    return True


def installed(models_dir: Path) -> bool:
    """Whether LaMa's weights are in the models folder (the file is there; nothing is read or loaded for it)."""
    return not LAMA_MODEL.missing(Path(models_dir))


def available(models_dir: Path, setting: str = "auto", cuda: bool | None = None) -> bool:
    """Whether the erase can run: LaMa's weights are here (`installed`) and the setting runs it on this computer
    (`runs_here`; *cuda* as there). The weights are looked at first, so that a computer without them never asks
    torch; nothing is loaded for it either way."""
    return setting != "off" and installed(models_dir) and runs_here(setting, cuda)


class ArtEraser:
    """`erase` for regions on the art, with LaMa in *models_dir*, loaded on first use."""

    def __init__(self, models_dir: Path, setting: str = "auto", fallback: Erase = erase_region):
        self.models_dir = Path(models_dir)
        self.setting = setting
        self.fallback = fallback
        self.failed = False  # LaMa could not run: `erase_region` does it all from then on
        self.counts = {"art": 0, "plain": 0, "weak": 0, "ground": 0}  # what the regions went to
        self._model: Any = None
        self._checked = False
        self._release_asked = False  # a release that came while the model was at work: done once it is free
        self._lock = threading.Lock()
        # called (it may wait) before the model runs on the GPU, once per region: the batch pauses the GPU while the
        # reader turns pages (`Pipeline.gpu_gate`); never on the CPU
        self.before_gpu: Callable[[], None] | None = None

    def ready(self) -> bool:
        """Whether the erase can run as far as can be known without loading it: the weights file is LaMa's (the names
        and shapes of its tensors, read from its header), and nothing failed. What lets the layout model run."""
        if not self.failed and not self._checked:
            from .lama import check

            try:
                check(self.models_dir / LAMA_MODEL.dirname / LAMA_MODEL.installed[0])
                self._checked = True
            except Exception as e:  # noqa: BLE001 - a broken or foreign file: the paper fill, and no layout model
                LOG.warning("LaMa's weights cannot be used (%s): no inpainting", type(e).__name__)
                self.failed = True
        return not self.failed

    def uses_gpu(self) -> bool:
        """Whether the model runs on the GPU: where it is loaded, else where it would load."""
        model = self._model
        return (model.device if model is not None else self._device()) != "cpu"

    @staticmethod
    def _device() -> str:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load(self, device: str) -> None:
        from .lama import LamaInpainter

        self._model = LamaInpainter(self.models_dir / LAMA_MODEL.dirname / LAMA_MODEL.installed[0], device)

    def _try(self, device: str, part: np.ndarray, hole: np.ndarray) -> tuple[np.ndarray | None, str]:
        """LaMa on *device* (loaded there first when it is not): the filled part, or None and why not. The exception is
        let go here, before anything is freed: its traceback holds the tensors of the failed step."""
        try:
            if self._model is None:
                self._load(device)
            return self._model.run(part, hole), ""
        except Exception as e:  # noqa: BLE001 - out of memory, a broken file: not worth a page
            return None, type(e).__name__

    def _fill(self, part: np.ndarray, hole: np.ndarray) -> np.ndarray | None:
        """*part* with *hole* filled; None when LaMa cannot do it. A failure on the GPU (its memory is shared with
        Ollama), loading or running, moves to the CPU."""
        gate = self.before_gpu
        if gate is not None and not self.failed and self.uses_gpu():
            gate()
        with self._lock:
            if self.failed:
                return None
            device = self._model.device if self._model is not None else self._device()
            filled, why = self._try(device, part, hole)
            if filled is None and device != "cpu":
                LOG.info("inpainting failed on the GPU (%s): on the CPU from now on", why)
                self._drop(device)
                filled, why = self._try("cpu", part, hole)
            if filled is None:
                LOG.warning("inpainting failed (%s): the paper fill from now on", why)
                self._drop("cpu")
                self.failed = True
            if self._release_asked:
                self._release_asked = False
                self._drop(device)
            return filled

    def warm(self) -> bool:
        """Loaded, and run once on a small blank part, ahead of the first page (`Pipeline.warm_page_models`), after the
        gate like any erase. A release asked meanwhile is done once it is over (`release`). Whether it worked."""
        if self.failed or not self.ready():
            return False
        part = np.full((64, 64, 3), 255, np.uint8)
        hole = np.zeros((64, 64), bool)
        hole[16:48, 16:48] = True
        return self._fill(part, hole) is not None

    def erase(self, image: np.ndarray, region: TextRegion, mode: str = "fill", white_threshold: int = 225,
              dark_threshold: int = 140, dark: bool = False) -> tuple[int, int, int]:
        """`erase_region`, but for lettering on the art: there the model fills the lettering in place, and the region's
        paper colour is what its lettering is drawn against. What the model filled is kept on the region (memory only)
        and used again while the part of the page it saw is the same (a page lettered again, a preview)."""
        app = lambda: self.fallback(image, region, mode, white_threshold, dark_threshold, dark)  # noqa: E731
        if self.failed or not on_art(image, region):
            self.counts["plain"] += 1
            return app()
        if on_paper(image, region):
            self.counts["ground"] += 1
            return app()
        full = art_mask(image, region)
        if full is None:
            self.counts["weak"] += 1
            return app()
        x0, y0, x1, y1 = box_of(image, region)
        if plain_ground(image, full, (x0, y0, x1, y1)):
            self.counts["ground"] += 1
            return app()
        wx0, wy0, wx1, wy1 = window(image.shape, x0, y0, y1 - y0, x1 - x0)
        part, hole = image[wy0:wy1, wx0:wx1], full[wy0:wy1, wx0:wx1]
        key = hashlib.sha1(np.ascontiguousarray(part).tobytes() + np.packbits(hole).tobytes()).digest()
        kept = region.inpainted
        if kept is not None and kept[0] == key:
            filled = kept[1]
        else:
            filled = self._fill(part, hole) if min(part.shape[:2]) >= SMALLEST else None
            if filled is not None:
                region.inpainted = (key, filled[hole], hole)
        if filled is None:
            self.counts["plain"] += 1
            return app()
        self.counts["art"] += 1
        part[hole] = filled if kept is not None and kept[0] == key else filled[hole]
        crop = image[region.y0:region.y1, region.x0:region.x1]
        mask = region.mask
        if crop.shape[:2] != mask.shape:
            mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
        return paper_colour(crop, mask > 0, dark)

    def _drop(self, device: str) -> None:
        self._model = None
        gc.collect()
        if device != "cpu":
            import torch

            torch.cuda.empty_cache()

    def release(self) -> None:
        """Give the model's memory back; the next erase loads it again. Never waits: while the model is at work the
        release is done as soon as it is free."""
        if not self._lock.acquire(blocking=False):
            self._release_asked = True
            return
        try:
            if self._model is not None:
                self._drop(self._model.device)
        finally:
            self._lock.release()


__all__ = ["ART_ERASES", "ArtEraser", "art_mask", "available", "has_cuda", "installed", "is_dash", "on_art", "on_paper",
           "plain_ground", "ring_comp", "runs_here", "window"]
