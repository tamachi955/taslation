# The network and the preprocessing here are adapted from manga-ocr-CPT (https://github.com/muscgab/manga-ocr-CPT, files
# manga_ocr_cpt/model.py and preprocess.py, the code of the model manga-ocr-base-CPT-flex), by its authors, under the
# Apache License, Version 2.0: you may not use those parts except in compliance with the License, a copy of which is in
# docs/licenses/Apache-2.0-manga-ocr-CPT.txt and at http://www.apache.org/licenses/LICENSE-2.0. Unless required by
# applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# Changed from the original: one crop at a time on the CPU in fp32, images taken from memory only, the "aspect" input
# alone (the model manga-ocr-base-CPT-flex); the GPU paths and the "square" input are left out.
# The License covers code only: the WEIGHTS are CC BY-NC-SA 4.0 and are not part of this repository.
"""manga-ocr-base-CPT-flex: the mangaOCR architecture, a sequence reader.

A ViT-B/16 encoder over at most 196 patches and a two-layer BERT decoder with cross-attention, written in plain PyTorch
on the weights in the model's model.safetensors; no transformers. It writes the line out character by character, and
so can lose its way in a long one: `taslation.ocr.readers` says how it is used. Token ids: 0 pad, 1 unk, 2 start,
3 end, 4 mask, 5 + i = character i. Imports torch: `taslation.ocr.readers` imports this file when it loads the models.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from safetensors.torch import load_file
from torch import Tensor

D, HEADS, EPS = 768, 12, 1e-12
START, END, NSPEC = 2, 3, 5
MAX_NEW = 65  # at most 64 characters + end
VOCAB = "nar_vocabulary_6817.json"

# ---------------------------------------------------------------- preprocessing (preprocess.py)

BUDGET, PATCH, FEAT = 196, 16, 768


def grid(height: int, width: int, budget: int = BUDGET) -> tuple[float, int, int]:
    """Largest uniform scale s with ceil(H*s/16) * ceil(W*s/16) <= budget -> (s, grid h, grid w)."""
    lo, hi = 1e-4, 1000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if math.ceil(height * mid / PATCH) * math.ceil(width * mid / PATCH) <= budget:
            lo = mid
        else:
            hi = mid
    return lo, math.ceil(height * lo / PATCH), math.ceil(width * lo / PATCH)


def preprocess(image: Image.Image) -> tuple[np.ndarray, np.ndarray, int, int]:
    """The crop in grey, fitted with its aspect kept to a grid of at most 196 patches of 16 x 16 px (Pillow bilinear),
    at the top left, the rest filled with the median value of the resized image's border, normalised to [-1, 1]
    -> patches [196, 768], valid [196], grid height and width."""
    image = image.convert("L").convert("RGB")
    s, gh, gw = grid(image.height, image.width)
    rw, rh = max(1, min(gw * PATCH, round(image.width * s))), max(1, min(gh * PATCH, round(image.height * s)))
    small = np.asarray(image.resize((rw, rh), Image.Resampling.BILINEAR), np.uint8)
    border = np.concatenate([small[0], small[-1], small[:, 0], small[:, -1]])
    canvas = np.empty((gh * PATCH, gw * PATCH, 3), np.uint8)
    canvas[:] = np.median(border, axis=0).astype(np.uint8)
    canvas[:rh, :rw] = small
    arr = (canvas.astype(np.float32) / 255.0 - 0.5) / 0.5
    n = gh * gw
    patches = np.zeros((BUDGET, FEAT), np.float32)
    patches[:n] = arr.reshape(gh, PATCH, gw, PATCH, 3).transpose(0, 2, 4, 1, 3).reshape(n, -1)
    valid = np.zeros(BUDGET, bool)
    valid[:n] = True
    return patches, valid, gh, gw


# ---------------------------------------------------------------- the network (model.py)

Pair = tuple[Tensor, Tensor]


def _lin(x: Tensor, wb: Pair) -> Tensor:
    return F.linear(x, wb[0], wb[1])


def _ln(x: Tensor, wb: Pair) -> Tensor:
    return F.layer_norm(x, (D,), wb[0], wb[1], EPS)


def _heads(x: Tensor, batch: int) -> Tensor:
    return x.view(batch, -1, HEADS, D // HEADS).transpose(1, 2)


class CptNet:
    def __init__(self, w: dict[str, Tensor]):
        def pair(p: str) -> Pair:
            return w[p + ".weight"].float(), w[p + ".bias"].float()

        self.patch = pair("enc.patch")
        self.cls, self.pos = w["enc.cls"].float(), w["enc.pos"].float()  # [768], [197, 768]
        self.enc = [{n: pair(f"enc.{i}.{n}") for n in ("ln1", "q", "k", "v", "o", "ln2", "f1", "f2")} for i in range(12)]
        self.enc_ln = pair("enc.ln")
        self.word, self.posw, self.tt0 = w["dec.word"].float(), w["dec.pos"].float(), w["dec.type0"].float()
        self.ln_e = pair("dec.ln")
        self.dec = [{n: pair(f"dec.{i}.{n}") for n in ("q", "k", "v", "o", "cq", "ck", "cv", "co", "f1", "f2", "ln1", "ln2", "ln3")}
                    for i in range(2)]
        self.head_t, self.ln_h = pair("dec.head"), pair("dec.head_ln")
        self.out = (self.word, w["dec.out_bias"].float())  # tied to the input embedding
        self._pe: dict[tuple[int, int], Tensor] = {}

    def pe(self, gh: int, gw: int) -> Tensor:
        """Position rows for a gh x gw grid, [196, 768] (zeros on padded patches), cached."""
        key = (gh, gw)
        if key not in self._pe:
            table = self.pos[1:].reshape(14, 14, D).permute(2, 0, 1)[None]
            t = table if key == (14, 14) else F.interpolate(table, size=key, mode="bicubic", align_corners=False)
            out = torch.zeros(196, D)
            out[: gh * gw] = t[0].flatten(1).T
            self._pe[key] = out
        return self._pe[key]

    def encode(self, P: Tensor, V: Tensor, pe: Tensor) -> tuple[Tensor, Tensor]:
        """P [B, 196, 768], V [B, 196] bool, pe [B, 196, 768] -> memory [B, 197, 768], mask [B, 197] bool."""
        B = P.shape[0]
        x = _lin(P, self.patch) + pe
        h = torch.cat([(self.cls + self.pos[0]).expand(B, 1, D), x], 1)
        mask = torch.cat([torch.ones_like(V[:, :1]), V], 1)
        am = mask[:, None, None, :]
        for L in self.enc:
            y = _ln(h, L["ln1"])
            q, k, v = (_heads(_lin(y, L[n]), B) for n in "qkv")
            y = F.scaled_dot_product_attention(q, k, v, attn_mask=am).transpose(1, 2).reshape(B, -1, D)
            h = h + _lin(y, L["o"])
            h = h + _lin(F.gelu(_lin(_ln(h, L["ln2"]), L["f1"])), L["f2"])
        return _ln(h, self.enc_ln), mask

    def step(self, tok: Tensor, pos: Tensor, sk: list[Tensor], sv: list[Tensor], ckv: list[Pair], xm: Tensor,
             live: Tensor) -> Tensor:
        """One greedy decoder step: tok [B] ids being fed, pos [1] their index, sk/sv per layer [B, 12, S, 64] caches
        (written at pos), ckv cross K/V, xm [B, 1, 1, 197] memory mask, live [1, 1, 1, S] cache slots <= pos
        -> logits [B, tokens]."""
        B = tok.shape[0]
        x = _ln(self.word[tok][:, None] + self.posw[pos][None] + self.tt0, self.ln_e)
        for i, L in enumerate(self.dec):
            q, k, v = (_heads(_lin(x, L[n]), B) for n in "qkv")
            sk[i].index_copy_(2, pos, k)
            sv[i].index_copy_(2, pos, v)
            y = F.scaled_dot_product_attention(q, sk[i], sv[i], attn_mask=live)
            x = _ln(_lin(y.transpose(1, 2).reshape(B, 1, D), L["o"]) + x, L["ln1"])
            y = F.scaled_dot_product_attention(_heads(_lin(x, L["cq"]), B), ckv[i][0], ckv[i][1], attn_mask=xm)
            x = _ln(_lin(y.transpose(1, 2).reshape(B, 1, D), L["co"]) + x, L["ln2"])
            x = _ln(_lin(F.gelu(_lin(x, L["f1"])), L["f2"]) + x, L["ln3"])
        return _lin(_ln(F.gelu(_lin(x, self.head_t)), self.ln_h)[:, 0], self.out)

    def greedy(self, P: Tensor, V: Tensor, pe: Tensor) -> list[int]:
        """Greedy decoding of one crop -> ids, at most `MAX_NEW`."""
        mem, mask = self.encode(P, V, pe)
        ckv = [(_heads(_lin(mem, L["ck"]), 1), _heads(_lin(mem, L["cv"]), 1)) for L in self.dec]
        sk = [torch.zeros(1, HEADS, MAX_NEW + 1, D // HEADS) for _ in self.dec]
        sv = [torch.zeros(1, HEADS, MAX_NEW + 1, D // HEADS) for _ in self.dec]
        slot = torch.arange(MAX_NEW + 1)
        tok = torch.tensor([START])
        out: list[int] = []
        for t in range(MAX_NEW):
            pos = torch.tensor([t])
            tok = self.step(tok, pos, sk, sv, ckv, mask[:, None, None, :], (slot <= pos)[None, None, None, :]).argmax(-1)
            out.append(int(tok))
            if out[-1] == END:
                break
        return out


class CptEngine:
    """The model on the CPU, loaded from *model_dir* (the caller checked that its files are there)."""

    def __init__(self, model_dir: Path):
        model_dir = Path(model_dir)
        self._net = CptNet(load_file(str(model_dir / "model.safetensors")))
        self._chars = json.loads((model_dir / VOCAB).read_text(encoding="utf-8"))["characters"]

    def read(self, image: Image.Image) -> str:
        """The line in *image*, as the model spells it."""
        patches, valid, gh, gw = preprocess(image)
        with torch.inference_mode():
            ids = self._net.greedy(torch.from_numpy(patches)[None], torch.from_numpy(valid)[None], self._net.pe(gh, gw)[None])
        return "".join(self._chars[k - NSPEC] for k in ids[:ids.index(END) if END in ids else len(ids)] if k >= NSPEC)
