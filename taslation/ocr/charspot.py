# The network, the preprocessing and the decoding here are adapted from manga-ocr-charspot-small 1.0.0
# (https://huggingface.co/muscgab/manga-ocr-charspot-small, revision 72ca29202673880ca9c67b1c02c107535be4472b; files
# manga_ocr_charspot_small/core.py and model.py), by its authors, under the Apache License, Version 2.0: you may not
# use those parts except in compliance with the License, a copy of which is in
# docs/licenses/Apache-2.0-manga-ocr-charspot-small.txt and at http://www.apache.org/licenses/LICENSE-2.0. Unless
# required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# Changed from the original: one crop at a time on the CPU in PyTorch (no ONNX Runtime, no masked batches, no GPU
# backend), images taken from memory only, the results as the dataclasses below; the reader's gate is ours.
# The License covers code only: the WEIGHTS are CC BY-NC-SA 4.0 and are not part of this repository.
"""The OCR's first reader and its gate: manga-ocr-charspot-small, a character detector with a learned reading order.

The model finds each character on its own (a heatmap of character centres, boxes, a flag for furigana, which it strips
itself), classifies each and orders them; there is no language model writing the line out, so it does not lose its way
in a long line (50+ characters: CER 14.8 against 30.9 for the sequence reader it replaced, on the gold set). The price:
it reads something in almost any crop. Where there is no text it finds a few huge characters of low score, so
`charspot_accepts` holds every reading to the size of the page's lettering and to a length, on top of
``ocr_min_confidence`` and the rest of `Pipeline._judge`. Regions the reader added skip all of it.

The weights are CC BY-NC-SA 4.0: non-commercial use only, never bundled, and the application never downloads them.
``setup_models.py`` does, after a person agreed to the licence in ``install.ps1``. Without them TASlation cannot read
pages (``ocr.model_missing``, ``health.ocr_missing``).

It runs on the CPU in PyTorch, one crop at a time: the GPU stays with Ollama. Not through ONNX Runtime, the upstream's
CPU route: its official builds send telemetry from native code, where `taslation.netguard` cannot see it. The PyTorch
path reads the same as upstream's ONNX model (docs/OFFLINE_VERIFICATION.md, "The OCR model"). Crops come from memory;
nothing here writes an image.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np
from PIL import Image

from ..config import OCR_REQUIRED_FILES
from ..messages import Message, as_message

# Hiragana, katakana, CJK ideographs (+ extension A), half-width katakana.
JA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")

# ---------------------------------------------------------------- when a reading counts

# `charspot_accepts`, chosen on the 736 gold text items and the 197 gold crops without text: where there is no text
# the model finds about two characters, median size 44 px against the lettering's 17.5. With ``ocr_min_confidence``
# 0.65 on the scale of `confidence` this rule keeps 666 of the 736 on gold boxes and lets 1 of the 197 through (on the
# heat alone, at 0.7: 672 and 5). Lines of one character are lost to it on purpose: the reader adds such a region by
# hand, and regions the reader added skip it.
GATE_SIZE_RATIO = 3.0  # at most this many times the page's usual character size (the region's median)
GATE_MIN_CHARS = 2
GATE_SURE_SCORE = 0.7  # a reading this sure is lettering at any size: oversized crops without text reach 0.58 at most

# The page's usual character size: the median over the regions read with USUAL_MIN_CHARS characters or more at a
# confidence of USUAL_MIN_SCORE or more. A page without one takes the book's so far, a book without one this default (the
# gold set's median; on a sharper screen the gate is then only stricter).
USUAL_MIN_CHARS = 4
USUAL_MIN_SCORE = 0.75
DEFAULT_USUAL_SIZE = 18.0


class ModelNotInstalled(RuntimeError):
    """The OCR model is not in its folder. ``.message`` is ``ocr.model_missing`` {path}
    (``str(error)`` is its English text)."""

    message: Message

    def __init__(self, message: Message | str = ""):
        self.message = as_message(message, "ocr.error")
        super().__init__(self.message)


class OcrEngine(Protocol):
    def read(self, image: Image.Image) -> str: ...


def looks_japanese(text: str) -> bool:
    return bool(JA_RE.search(text))


def clean_ocr_text(text: str) -> str:
    return text.replace("\u3000", "").replace(" ", "").strip()


def check_model_dir(model_dir: Path) -> list[str]:
    """The files of the model that are not in *model_dir*; nothing missing means it can be loaded."""
    return [name for name in OCR_REQUIRED_FILES if not (Path(model_dir) / name).is_file()]


def import_libraries() -> None:
    """Import what loading the model needs (for a thread to do while Ollama's model loads). Touches no GPU."""
    import safetensors.torch  # noqa: F401
    import torch  # noqa: F401


@dataclass(frozen=True)
class CharspotChar:
    char: str  # one character, or a combined !? glyph of two or three
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels of the crop as given
    score: float  # the peak of the character-centre heatmap
    sure: float = 1.0  # the classifier's probability for this character


@dataclass(frozen=True)
class CharspotReading:
    """What was read in a crop, in reading order; *text* is `written` and *score* the confidence kept with a region
    (`confidence`). An engine without character boxes gives no *chars*, and then no gate applies. *split*: the readers
    gave three different lines (`taslation.ocr.readers`)."""

    text: str = ""
    chars: tuple[CharspotChar, ...] = ()
    score: float = 0.0
    split: bool = False

    @cached_property
    def size(self) -> float:
        """The median character size (the longer side of a box), in pixels of the crop as given."""
        if not self.chars:
            return 0.0
        return float(statistics.median(max(c.box[2] - c.box[0], c.box[3] - c.box[1]) for c in self.chars))


def confidence(chars: Iterable[CharspotChar]) -> float:
    """A reading's confidence: the characters' mean heat (is something lettered here) times their mean classifier
    probability (does the model know what). Together they tell wrong readings (AUROC 0.945 on the gold set) and crops
    without text (0.975) apart better than either alone."""
    chars = list(chars)
    if not chars:
        return 0.0
    return sum(c.score for c in chars) / len(chars) * sum(c.sure for c in chars) / len(chars)


def read_crop(ocr: Any, crop: Image.Image) -> CharspotReading:
    """*crop* read by *ocr*: `CharspotEngine.read_chars`, or for a simpler engine ``read_with_confidence`` or
    ``read`` (confidence 1)."""
    reader = getattr(ocr, "read_chars", None)
    if reader is not None:
        return reader(crop)
    reader = getattr(ocr, "read_with_confidence", None)
    text, confidence = reader(crop) if reader is not None else (ocr.read(crop), 1.0)
    return CharspotReading(text, score=confidence)


def charspot_accepts(reading: CharspotReading, usual: float) -> bool:
    """Whether *reading* is lettering rather than something the model saw in a drawing: long enough, and its characters
    no more than `GATE_SIZE_RATIO` times the page's *usual* size (`usual_size`), unless it is read with a confidence of
    `GATE_SURE_SCORE` or more. No region the reader added comes here."""
    if len(reading.chars) < GATE_MIN_CHARS:
        return False
    return reading.score >= GATE_SURE_SCORE or reading.size <= GATE_SIZE_RATIO * usual


def size_sample(reading: CharspotReading) -> float | None:
    """The character size *reading* gives for the usual size; None when it is too short or unsure."""
    if len(reading.chars) >= USUAL_MIN_CHARS and reading.score >= USUAL_MIN_SCORE:
        return reading.size
    return None


def usual_size(page: Iterable[float], book: Iterable[float] = ()) -> float:
    """The usual character size: the median of the *page*'s samples, else of the *book*'s so far, else the default.
    The page's samples are taken from all its regions before any is judged, so no region's fate hangs on the order
    the regions were read in."""
    for sizes in (list(page), list(book)):
        if sizes:
            return float(statistics.median(sizes))
    return DEFAULT_USUAL_SIZE


# ---------------------------------------------------------------- preprocessing and decoding (core.py)

CELL = 16  # input cell size in pixels; the dense heads run at stride 8
BUDGET = 256  # at most 256 cells per crop
HEAT_THR = 0.3  # character-centre heatmap threshold
NMS_IOU = 0.2  # box NMS IoU threshold
RUBY_THR = 0.5  # boxes flagged as furigana above this are dropped
# tate-chu-yoko !? glyphs
COMBOS = [a + b for a in "!?" for b in "!?"] + [a + b + c for a in "!?" for b in "!?" for c in "!?"]


def load_vocab(path: Path, n_cls: int) -> list[str]:
    chars = json.loads(Path(path).read_text(encoding="utf-8"))["characters"]
    return chars + [""] * (n_cls - len(chars)) + COMBOS


def pad_grid(height: int, width: int, budget: int = BUDGET) -> tuple[float, int, int]:
    """Largest scale whose 14-px grid fits in *budget* cells; cells are 16 px here."""
    lo, hi = 1e-4, 1000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if math.ceil(height * mid / 14) * math.ceil(width * mid / 14) <= budget:
            lo = mid
        else:
            hi = mid
    return lo * CELL / 14, math.ceil(height * lo / 14), math.ceil(width * lo / 14)


def preprocess(img: Image.Image) -> tuple[np.ndarray, tuple[float, float]]:
    """-> uint8 [3, H, W] (H and W multiples of 16), and (x, y) factors from input pixels back to crop pixels."""
    s, gh, gw = pad_grid(img.height, img.width)
    rw, rh = max(1, min(gw * CELL, round(img.width * s))), max(1, min(gh * CELL, round(img.height * s)))
    small = np.asarray(img.resize((rw, rh), Image.Resampling.BICUBIC), np.uint8)
    border = np.concatenate([small[0], small[-1], small[:, 0], small[:, -1]])
    arr = np.empty((gh * CELL, gw * CELL, 3), np.uint8)
    arr[:] = np.median(border, axis=0).astype(np.uint8)
    arr[:rh, :rw] = small
    return np.ascontiguousarray(arr.transpose(2, 0, 1)), (img.width / rw, img.height / rh)


def nms(b: np.ndarray, s: np.ndarray, thr: float = NMS_IOU) -> list[int]:
    """Greedy NMS by score; also drops boxes whose centre lies in the central half of a kept box."""
    order = np.argsort(-s, kind="stable")
    b = b[order]
    area = np.clip(b[:, 2] - b[:, 0], 0, None) * np.clip(b[:, 3] - b[:, 1], 0, None)
    cx, cy = (b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2
    inter = (np.clip(np.minimum(b[:, None, 2], b[None, :, 2]) - np.maximum(b[:, None, 0], b[None, :, 0]), 0, None)
             * np.clip(np.minimum(b[:, None, 3], b[None, :, 3]) - np.maximum(b[:, None, 1], b[None, :, 1]), 0, None))
    hx, hy = (b[:, 2] - b[:, 0]) * 0.25, (b[:, 3] - b[:, 1]) * 0.25
    inside = (np.abs(cx[None, :] - cx[:, None]) <= hx[:, None]) & (np.abs(cy[None, :] - cy[:, None]) <= hy[:, None])
    sup = ~(inter / (area[:, None] + area[None, :] - inter + 1e-6) < thr) | inside  # sup[i, j]: kept i removes j
    alive = np.ones(len(b), bool)
    keep = []
    for i in range(len(b)):
        if alive[i]:
            keep.append(int(order[i]))
            alive &= ~sup[i]
    return keep


def detect(heat: np.ndarray, box: np.ndarray, ruby: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Dense outputs of one crop ([1,h,w], [4,h,w], [1,h,w]) -> kept boxes [n,4] (input px), scores [n], geometry
    [n,4] for the tail; None when no character is there."""
    hm = heat[0]
    ci, cj = np.nonzero(hm > HEAT_THR)
    if not len(ci):
        return None
    bx = box[:, ci, cj]
    cx, cy = (cj + bx[0]) * 8, (ci + bx[1]) * 8
    w, h = np.exp(bx[2]) * 8, np.exp(bx[3]) * 8
    b = np.stack((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 1).astype(np.float32)
    keep = [k for k in nms(b, hm[ci, cj]) if ruby[0, ci[k], cj[k]] < RUBY_THR]
    if not keep:
        return None
    kb = b[keep]
    sc = hm[ci, cj][keep]
    sz = np.maximum(kb[:, 2] - kb[:, 0], kb[:, 3] - kb[:, 1])
    u = float(np.sort(sz)[(len(sz) - 1) // 2])
    geo = np.stack(((kb[:, 0] + kb[:, 2]) / 2 / u, (kb[:, 1] + kb[:, 3]) / 2 / u,
                    np.clip(kb[:, 2] - kb[:, 0], 1, None) / u, np.clip(kb[:, 3] - kb[:, 1], 1, None) / u),
                   1).astype(np.float32)
    return kb, sc, geo


def chain(pair: np.ndarray, st: np.ndarray, en: np.ndarray) -> list[int]:
    """Greedy reading order: start at the best start score, follow the best unused successor, restart when 'end'
    wins."""
    n = len(st)
    used = np.zeros(n, bool)
    cur = int(st.argmax())
    seq = [cur]
    used[cur] = True
    while not used.all():
        sc = np.where(used, -np.inf, pair[cur])
        j = int(np.argmax(sc))
        if en[cur] > sc[j]:
            rest = np.where(~used)[0]
            j = int(rest[np.argmax(st[rest])])
        seq.append(j)
        used[j] = True
        cur = j
    return seq


def written(text: str) -> str:
    """*text* with its marks as the rest of TASlation expects them: no spaces, full-width ASCII and digits, runs of dots
    as dots."""
    import jaconv

    text = "".join(text.split()).replace("\u2026", "...")
    text = re.sub("[\u30fb.]{2,}", lambda m: (m.end() - m.start()) * ".", text)
    return clean_ocr_text(jaconv.h2z(text, ascii=True, digit=True))


# ---------------------------------------------------------------- the network (model.py)

MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)


def _build(cfg: dict, n_out: int) -> tuple[Any, Any]:
    """The dense network and the tail, as upstream's model.py defines them. Made here because torch is imported only
    when the model loads."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    def dw(c: int, stride: int = 1) -> Any:
        return nn.Conv2d(c, c, 3, stride, 1, groups=c)

    class SE(nn.Module):
        def __init__(self, c):
            super().__init__()
            self.a, self.b = nn.Conv2d(c, c // 4, 1), nn.Conv2d(c // 4, c, 1)

        def forward(self, x):
            return x * F.hardsigmoid(self.b(F.relu(self.a(x.mean((2, 3), keepdim=True)))))

    class Block(nn.Module):
        def __init__(self, c, se=False):
            super().__init__()
            self.dw, self.se = dw(c), SE(c) if se else None
            self.pw1, self.pw2 = nn.Conv2d(c, 2 * c, 1), nn.Conv2d(2 * c, c, 1)

        def forward(self, x):
            y = self.dw(x)
            if self.se is not None:
                y = self.se(y)
            return y + self.pw2(F.hardswish(self.pw1(y)))

    class Down(nn.Module):
        def __init__(self, ci, co):
            super().__init__()
            self.dw, self.pw1, self.pw2 = dw(ci, 2), nn.Conv2d(ci, co, 1), nn.Conv2d(co, co, 1)

        def forward(self, x):
            return self.pw2(F.hardswish(self.pw1(self.dw(x))))

    class Stem(nn.Module):
        def __init__(self, c):
            super().__init__()
            self.c1 = nn.Conv2d(3, c // 2, 3, 2, 1)
            self.b1, self.b2 = nn.Conv2d(c // 2, c // 4, 2), nn.Conv2d(c // 4, c // 2, 2)
            self.c2, self.c3 = nn.Conv2d(c, c // 2, 3, 2, 1), nn.Conv2d(c // 2, c, 1)

        def forward(self, x):
            x = F.relu(self.c1(x))
            b = F.relu(self.b2(F.pad(F.relu(self.b1(F.pad(x, (0, 1, 0, 1)))), (0, 1, 0, 1))))
            m = F.max_pool2d(F.pad(x, (0, 1, 0, 1)), 2, 1)
            return F.relu(self.c3(F.relu(self.c2(torch.cat((m, b), 1)))))

    def stage(ci, co, n, down, se_first):
        mods = [Down(ci, co)] if down else []
        for k in range(n - len(mods)):
            mods.append(Block(co, se=(k % 2 == 0) and se_first))
        return nn.Sequential(*mods)

    class Backbone(nn.Module):
        def __init__(self, c, n):
            super().__init__()
            self.stem = Stem(c[0])
            self.s1, self.s2 = stage(c[0], c[0], n[0], False, True), stage(c[0], c[1], n[1], True, False)
            self.s3 = stage(c[1], c[2], n[2], True, True)

    class Attn(nn.Module):
        """Pre-norm attention + MLP block; q and k are layer-normed per head (QK-Norm)."""

        def __init__(self, d, heads):
            super().__init__()
            self.h = heads
            self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
            self.qkv, self.proj = nn.Linear(d, 3 * d), nn.Linear(d, d)
            self.fc1, self.fc2 = nn.Linear(d, 2 * d), nn.Linear(2 * d, d)
            self.qn, self.kn = nn.LayerNorm(d // heads), nn.LayerNorm(d // heads)

        def forward(self, t):
            B, N, D = t.shape
            hd = D // self.h
            q, k, v = self.qkv(self.n1(t)).view(B, N, 3, self.h, hd).permute(2, 0, 3, 1, 4).unbind(0)
            a = (self.qn(q) * hd ** -0.5) @ self.kn(k).transpose(-1, -2)
            a = a.softmax(-1) @ v
            t = t + self.proj(a.transpose(1, 2).reshape(B, N, D))
            return t + self.fc2(F.gelu(self.fc1(self.n2(t))))

    class Dense(nn.Module):
        def __init__(self, c, n, att, heads, emb):
            super().__init__()
            c1, c2, c3 = c
            self.bb = Backbone(c, n)
            self.cpe, self.att = dw(c3), Attn(c3, heads)  # first attention block (names as in training)
            self.extra = nn.ModuleList(nn.ModuleList([dw(c3), Attn(c3, heads)]) for _ in range(att - 1))
            self.lat = nn.Conv2d(c3, c2, 1)
            self.mix_dw, self.mix_pw = dw(c2), nn.Conv2d(c2, c2, 1)
            self.heat, self.box = nn.Conv2d(c2, 1, 1), nn.Conv2d(c2, 4, 1)
            self.ruby, self.emb = nn.Conv2d(c2, 1, 1), nn.Conv2d(c2, emb, 1)
            self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1) * 255)
            self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1) * 255)

        def forward(self, img):
            """img [1, 3, H, W], raw 0..255."""
            x = (img - self.mean) / self.std
            f8 = self.bb.s2(self.bb.s1(self.bb.stem(x)))
            f16 = self.bb.s3(f8)
            B, D, h, w = f16.shape
            for cpe, att in [(self.cpe, self.att)] + [(e[0], e[1]) for e in self.extra]:
                f16 = f16 + cpe(f16)
                f16 = att(f16.flatten(2).transpose(1, 2)).transpose(1, 2).reshape(B, D, h, w)
            p8 = f8 + F.interpolate(self.lat(f16), scale_factor=2.0, mode="nearest")
            p8 = F.hardswish(self.mix_pw(self.mix_dw(p8)))
            return torch.sigmoid(self.heat(p8)), self.box(p8), torch.sigmoid(self.ruby(p8)), self.emb(p8)

    class Tail(nn.Module):
        def __init__(self, n_out, emb, d, layers, heads):
            super().__init__()
            self.pool = nn.Linear(4 * emb, emb)
            self.inp = nn.Linear(emb + 4, d)
            self.blocks = nn.ModuleList(Attn(d, heads) for _ in range(layers))
            self.cls = nn.Linear(emb + d, n_out)
            self.pa, self.pb, self.pc = nn.Linear(d, d), nn.Linear(d, d, bias=False), nn.Linear(4, d, bias=False)
            self.pout = nn.Linear(d, 1)
            self.start, self.end = nn.Linear(d, 1), nn.Linear(d, 1)
            self.register_buffer("qx", torch.tensor([0.25, 0.75, 0.25, 0.75]), persistent=False)  # sample points
            self.register_buffer("qy", torch.tensor([0.25, 0.25, 0.75, 0.75]), persistent=False)  # inside each box

        def pooled(self, emb, boxes):
            """emb [B, E, H8, W8], boxes [B, N, 4] (input px) -> [B, N, E]: bilinear samples at the 4 quarter points
            of each box."""
            B, N = boxes.shape[:2]
            H8, W8 = emb.shape[-2:]
            px = boxes[..., 0:1] + self.qx * (boxes[..., 2:3] - boxes[..., 0:1])
            py = boxes[..., 1:2] + self.qy * (boxes[..., 3:4] - boxes[..., 1:2])
            grid = torch.stack((px / (W8 * 8) * 2 - 1, py / (H8 * 8) * 2 - 1), -1)
            s = F.grid_sample(emb, grid, mode="bilinear", align_corners=False)  # [B, E, N, 4]
            return self.pool(s.permute(0, 2, 3, 1).reshape(B, N, -1))

        def forward(self, e, geo):
            """e [1, N, E], geo [1, N, 4] -> class probabilities and ids [1, N], pair [1, N, N], start [1, N], end
            [1, N]."""
            h = self.inp(torch.cat((e, geo), -1))
            for blk in self.blocks:
                h = blk(h)
            sure, ids = self.cls(torch.cat((e, h), -1)).softmax(-1).max(-1)
            dd = torch.cat((geo[:, None, :, :2] - geo[:, :, None, :2],
                            torch.log(geo[:, None, :, 2:] / geo[:, :, None, 2:])), -1)
            pair = self.pout(F.relu(self.pa(h)[:, :, None] + self.pb(h)[:, None] + self.pc(dd)))[..., 0]
            return sure, ids, pair, self.start(h)[..., 0], self.end(h)[..., 0]

    a = cfg["arch"]
    return (Dense(tuple(a["c"]), tuple(a["n"]), a["att"], a["heads"], a["emb"]),
            Tail(n_out, a["emb"], a["d"], a["layers"], a["theads"]))


class CharspotEngine:
    """The model on the CPU, loaded from *model_dir*. Reads one crop at a time (the crops of a page have different
    shapes, and a page's worth takes a fraction of a second). Raises `ModelNotInstalled` when it is not there."""

    def __init__(self, model_dir: Path, threads: int = 0):
        self.model_dir = Path(model_dir)
        if check_model_dir(self.model_dir):
            raise ModelNotInstalled(Message("ocr.model_missing", path=str(self.model_dir)))
        import torch
        from safetensors.torch import load_file

        if threads > 0:
            torch.set_num_threads(threads)

        cfg = json.loads((self.model_dir / "config.json").read_text(encoding="utf-8"))
        weights = load_file(str(self.model_dir / cfg["weights"]), device="cpu")
        self._dense, self._tail = (m.eval() for m in _build(cfg, weights["tail.cls.weight"].shape[0]))
        self._dense.load_state_dict({k[6:]: v for k, v in weights.items() if k.startswith("dense.")})
        self._tail.load_state_dict({k[5:]: v for k, v in weights.items() if k.startswith("tail.")})
        self._out_str = load_vocab(self.model_dir / cfg["vocab"], cfg["n_cls"])

    def read_chars(self, image: Image.Image) -> CharspotReading:
        import torch

        pixels, (fx, fy) = preprocess(image.convert("RGB"))
        with torch.inference_mode():
            heat, box, ruby, emb = self._dense(torch.from_numpy(pixels)[None].float())
            found = detect(heat[0].numpy(), box[0].numpy(), ruby[0].numpy())
            if found is None:
                return CharspotReading()
            boxes, scores, geo = found
            e = self._tail.pooled(emb, torch.from_numpy(boxes)[None])
            sure, ids, pair, st, en = self._tail(e, torch.from_numpy(geo)[None])
            order = chain(pair[0].numpy(), st[0].numpy(), en[0].numpy())
            sure, ids = sure[0].tolist(), ids[0].tolist()
        chars = tuple(CharspotChar(self._out_str[int(ids[k])],
                                   (float(boxes[k, 0] * fx), float(boxes[k, 1] * fy),
                                    float(boxes[k, 2] * fx), float(boxes[k, 3] * fy)),
                                   float(scores[k]), sure[k]) for k in order)
        return CharspotReading(written("".join(c.char for c in chars)), chars, confidence(chars))

    def read(self, image: Image.Image) -> str:
        return self.read_chars(image).text

    def read_with_confidence(self, image: Image.Image) -> tuple[str, float]:
        reading = self.read_chars(image)
        return reading.text, reading.score
