# The network and the preprocessing here are adapted from manga-ocr-nar-small
# (https://huggingface.co/muscgab/manga-ocr-nar-small, revision 81ff4f3313263d1da349946a9dd20d14e0fb0e66; files
# manga_ocr_nar_small/model.py and preprocess.py), by its authors, under the Apache License, Version 2.0: you may not
# use those parts except in compliance with the License, a copy of which is in
# docs/licenses/Apache-2.0-manga-ocr-nar-small.txt and at http://www.apache.org/licenses/LICENSE-2.0. Unless required
# by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS"
# BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# Upstream's encoder is its re-implementation of the MonkeyOCRv2-S encoder (Apache-2.0, see the model's NOTICE.md).
# Changed from the original: one crop at a time on the CPU in fp32, images taken from memory only; the GPU, ONNX and
# CoreML backends and the int8 variant's quantisers are left out.
# The License covers code only: the WEIGHTS are CC BY-NC-SA 4.0 and are not part of this repository.
"""manga-ocr-nar-small: a line reader without a language model.

A vision encoder over at most 324 patches and four decoder blocks over 65 output slots, read off in one go: nothing
writes the line out character by character, so it cannot run away. `taslation.ocr.readers` says how it is used.

Parameter names match the weights' file. The released weights are an exact rescaling of the trained checkpoint; the
matching norm epsilons come from its config.json ("reparam.norm_eps"). ``inject``, ``loop_emb`` and ``occ`` are
training-time parameters. Imports torch: `taslation.ocr.readers` imports this file when it loads the models.
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
from torch import Tensor, nn

SLOTS = 65
ENC_DIM, ENC_HEADS, ENC_FFN, ENC_LAYERS = 384, 6, 1536, 12
DEC_DIM, DEC_HEADS, DEC_FFN, DEC_LAYERS = 512, 8, 2048, 4
UNUSED = ("inject", "loop_emb", "occ.weight", "occ.bias")
VOCAB = "nar_vocabulary_6817.json"

# ---------------------------------------------------------------- preprocessing (preprocess.py)

BUDGET, PATCH, FEAT = 324, 14, 588
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)


def pad_grid(height: int, width: int, budget: int = BUDGET) -> tuple[float, int, int]:
    """Largest uniform scale s with ceil(H*s/14) * ceil(W*s/14) <= budget -> (s, grid h, grid w)."""
    lo, hi = 1e-4, 1000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if math.ceil(height * mid / PATCH) * math.ceil(width * mid / PATCH) <= budget:
            lo = mid
        else:
            hi = mid
    return lo, math.ceil(height * lo / PATCH), math.ceil(width * lo / PATCH)


def preprocess(image: Image.Image) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, int]:
    """The crop fitted with its aspect kept to a grid of at most 324 patches of 14 x 14 px (Pillow bicubic), at the
    top left, the rest filled with the median colour of the resized image's border -> patches [324, 588], valid
    [324], patch rows and columns [324] (padded tail zero), grid height and width."""
    image = image.convert("RGB")
    s, h, w = pad_grid(image.height, image.width)
    rw, rh = max(1, min(w * PATCH, round(image.width * s))), max(1, min(h * PATCH, round(image.height * s)))
    small = np.asarray(image.resize((rw, rh), Image.Resampling.BICUBIC), np.uint8)
    border = np.concatenate([small[0], small[-1], small[:, 0], small[:, -1]])
    canvas = np.empty((h * PATCH, w * PATCH, 3), np.uint8)
    canvas[:] = np.median(border, axis=0).astype(np.uint8)
    canvas[:rh, :rw] = small
    arr = (canvas.astype(np.float32) / 255.0 - MEAN) / STD
    n = h * w
    patches = np.zeros((BUDGET, FEAT), np.float32)
    patches[:n] = arr.reshape(h, PATCH, w, PATCH, 3).transpose(0, 2, 4, 1, 3).reshape(n, FEAT)
    valid, rows, cols = np.zeros(BUDGET, bool), np.zeros(BUDGET, np.int64), np.zeros(BUDGET, np.int64)
    valid[:n] = True
    idx = np.arange(n)
    rows[:n], cols[:n] = idx // w, idx % w
    return patches, valid, rows, cols, h, w


# ---------------------------------------------------------------- the network (model.py)


class RMSNorm(nn.Module):
    def __init__(self, d: int, eps: float = 1e-6):
        super().__init__()
        self.weight, self.eps = nn.Parameter(torch.ones(d)), eps

    def forward(self, x: Tensor) -> Tensor:
        return F.rms_norm(x, (x.shape[-1],), self.weight, self.eps)


class EncRMSNorm(nn.Module):
    """MonkeyOCRv2's RMSNorm: normalise, then scale."""

    def __init__(self, d: int, eps: float = 1e-5):
        super().__init__()
        self.weight, self.eps = nn.Parameter(torch.ones(d)), eps

    def forward(self, x: Tensor) -> Tensor:
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight


def rotate_half(x: Tensor) -> Tensor:
    a, b = x.chunk(2, -1)
    return torch.cat((-b, a), -1)


class _Attn(nn.Module):
    def __init__(self):
        super().__init__()
        self.qkv, self.proj = nn.Linear(ENC_DIM, 3 * ENC_DIM, bias=False), nn.Linear(ENC_DIM, ENC_DIM, bias=False)


class _Mlp(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(ENC_DIM, ENC_FFN, bias=False)
        self.fc2 = nn.Linear(ENC_FFN, ENC_DIM, bias=False)
        self.fc3 = nn.Linear(ENC_DIM, ENC_FFN, bias=False)


class _VitBlock(nn.Module):
    def __init__(self):
        super().__init__()
        self.attn, self.mlp = _Attn(), _Mlp()
        self.norm1, self.norm2 = EncRMSNorm(ENC_DIM), EncRMSNorm(ENC_DIM)


class _Patchifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = nn.Conv2d(3, ENC_DIM, kernel_size=14, stride=14)
        self.norm = EncRMSNorm(ENC_DIM)


class _PatchEmbed(nn.Module):
    def __init__(self):
        super().__init__()
        self.patchifier = _Patchifier()


class _Rotary(nn.Module):
    def __init__(self, dim: int, theta: float = 10000.0):
        super().__init__()
        inverse = 1.0 / (theta ** (torch.arange(0, dim, 2, dtype=torch.float) / dim))
        self.register_buffer("inv_freq", inverse, persistent=False)

    def forward(self, n: int) -> Tensor:
        return torch.outer(torch.arange(n, dtype=self.inv_freq.dtype), self.inv_freq)


class _Vit(nn.Module):
    def __init__(self):
        super().__init__()
        self.patch_embed = _PatchEmbed()
        self.rotary_pos_emb = _Rotary(ENC_DIM // ENC_HEADS // 2)
        self.blocks = nn.ModuleList(_VitBlock() for _ in range(ENC_LAYERS))
        self.post_trunk_norm = EncRMSNorm(ENC_DIM)


class _Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.vit = _Vit()


class Memory(nn.Module):
    def __init__(self):
        super().__init__()
        d = DEC_DIM
        self.bridge = nn.Sequential(RMSNorm(ENC_DIM), nn.Linear(ENC_DIM, 1024, bias=False), nn.GELU(),
                                    nn.Linear(1024, d, bias=False), RMSNorm(d))
        self.pos = nn.Linear(32, d, bias=False)
        self.null = nn.Parameter(torch.zeros(2, d))
        self.norms = nn.ModuleList(RMSNorm(ENC_DIM) for _ in range(ENC_LAYERS))
        self.wo = nn.Linear(ENC_DIM, d, bias=False)
        self.gamma = nn.Parameter(torch.zeros(DEC_LAYERS, d))
        self.depth_logits = nn.Parameter(torch.zeros(DEC_LAYERS, ENC_LAYERS))

    @staticmethod
    def fourier(rows: Tensor, cols: Tensor, h: Tensor, w: Tensor) -> Tensor:
        r = (rows.float() + 0.5) / h[:, None].float()
        c = (cols.float() + 0.5) / w[:, None].float()
        f = torch.pi * 2.0 ** torch.arange(8).float()
        return torch.cat([fn(t[..., None] * f) for t in (r, c) for fn in (torch.sin, torch.cos)], -1)


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        d = DEC_DIM
        self.h, self.hd = DEC_HEADS, d // DEC_HEADS
        self.qkv, self.o1 = nn.Linear(d, 3 * d, bias=False), nn.Linear(d, d, bias=False)
        self.q, self.kv, self.o2 = nn.Linear(d, d, bias=False), nn.Linear(d, 2 * d, bias=False), nn.Linear(d, d, bias=False)
        self.sq, self.sk, self.cq, self.ck = (RMSNorm(self.hd) for _ in range(4))
        self.gate_up, self.down = nn.Linear(d, 2 * DEC_FFN, bias=False), nn.Linear(DEC_FFN, d, bias=False)

    def split(self, x: Tensor) -> Tensor:
        return x.view(x.shape[0], x.shape[1], self.h, self.hd).transpose(1, 2)

    def memory_kv(self, memory: Tensor) -> tuple[Tensor, Tensor]:
        k, v = self.kv(memory).chunk(2, -1)
        return self.ck(self.split(k)), self.split(v)


class Cond(nn.Module):
    def __init__(self):
        super().__init__()
        d = DEC_DIM
        self.n1, self.n2, self.n3 = RMSNorm(d), RMSNorm(d), RMSNorm(d)
        self.s1, self.s2, self.s3 = (nn.Parameter(torch.ones(d)) for _ in range(3))


def _rope(t: Tensor, cos: Tensor, sin: Tensor, half: int) -> Tensor:
    a, rest = t[..., :half], t[..., half:]
    return torch.cat((a * cos + rotate_half(a) * sin, rest), -1)


class NarNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = _Encoder()
        self.memory = Memory()
        self.blocks = nn.ModuleList(Block() for _ in range(DEC_LAYERS))
        self.cond = nn.ModuleList(Cond() for _ in range(DEC_LAYERS))
        self.final_norms = nn.ModuleList([RMSNorm(DEC_DIM)])
        self.slot_pos = nn.Parameter(torch.zeros(SLOTS, DEC_DIM))
        self.tok = nn.Embedding(6819, DEC_DIM)  # 6,817 characters + end of text + BLANK (input only)
        self.bias = nn.Parameter(torch.zeros(6818))
        hd = DEC_DIM // DEC_HEADS
        inv = 1.0 / (10000 ** (torch.arange(0, hd // 2, 2).float() / (hd // 2)))
        ang = torch.outer(torch.arange(SLOTS).float(), inv)
        self.register_buffer("rope_cos", torch.cat((ang, ang), -1).cos()[None, None], persistent=False)
        self.register_buffer("rope_sin", torch.cat((ang, ang), -1).sin()[None, None], persistent=False)

    @torch.no_grad()
    def prepare(self) -> None:
        """Constants computed once: concatenated encoder fc1|fc3, the RoPE table, the static depth weights, and the
        first decoder block's self-attention on the image-independent slot input."""
        vit = self.encoder.vit
        self.fc13 = [torch.cat((b.mlp.fc1.weight, b.mlp.fc3.weight), 0).contiguous() for b in vit.blocks]
        self.rope_table = vit.rotary_pos_emb(325)
        self.alpha = self.memory.depth_logits.softmax(-1)
        s0 = (self.slot_pos + self.tok.weight[6818])[None]
        blk, c = self.blocks[0], self.cond[0]
        B, S, Dm = s0.shape
        q, k, v = blk.qkv(c.n1(s0)).chunk(3, -1)
        q, k, v = blk.sq(blk.split(q)), blk.sk(blk.split(k)), blk.split(v)
        half = blk.hd // 2
        att = F.scaled_dot_product_attention(_rope(q, self.rope_cos, self.rope_sin, half),
                                             _rope(k, self.rope_cos, self.rope_sin, half), v)
        self.s_after_sa0 = (s0 + c.s1 * blk.o1(att.transpose(1, 2).reshape(B, S, Dm))).contiguous()

    def forward(self, P: Tensor, V: Tensor, R: Tensor, C: Tensor, H: Tensor, W: Tensor) -> Tensor:
        """P [B,324,588] patches, V [B,324] bool valid, R/C [B,324] long patch row/column, H/W [B] long grid size
        -> logits [B, 65, 6818]."""
        vit = self.encoder.vit
        B, N, _ = P.shape
        pe = vit.patch_embed.patchifier
        x = pe.norm(F.linear(P, pe.proj.weight.flatten(1), pe.proj.bias))
        emb = torch.stack((self.rope_table[R], self.rope_table[C]), -1).flatten(-2)
        cos = torch.cat((emb.cos(), emb.cos()), -1)[:, :, None]
        sin = torch.cat((emb.sin(), emb.sin()), -1)[:, :, None]
        mask = V[:, None, None, :]
        hd = ENC_DIM // ENC_HEADS
        states = [x]
        for blk, w13 in zip(vit.blocks, self.fc13):
            q, k, v = blk.attn.qkv(blk.norm1(x)).view(B, N, 3, ENC_HEADS, hd).unbind(2)
            q = q * cos + rotate_half(q) * sin
            k = k * cos + rotate_half(k) * sin
            att = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), attn_mask=mask)
            x = x + blk.attn.proj(att.transpose(1, 2).reshape(B, N, ENC_DIM))
            g, u = F.linear(blk.norm2(x), w13).split(ENC_FFN, -1)
            x = x + blk.mlp.fc2(F.silu(g) * u)
            states.append(x)
        states[-1] = vit.post_trunk_norm(x)
        mem = self.memory
        last = states[-1]
        base = mem.bridge(last) + mem.pos(mem.fourier(R, C, H, W))
        stacked = torch.stack([nm(s) for nm, s in zip(mem.norms, states[:-1])], 0)
        f = torch.einsum("jl,lbnd->jbnd", self.alpha, stacked)
        mems = base[None] + mem.gamma[:, None, None] * mem.wo(f)
        mems = torch.cat((mem.null.expand(mems.shape[0], B, -1, -1), mems), 2)
        kvs = [self.blocks[j].memory_kv(m) for j, m in enumerate(mems.unbind(0))]
        km = torch.cat((torch.ones(B, 2, dtype=torch.bool), V), 1)[:, None, None, :]
        s = self.s_after_sa0.expand(B, -1, -1)
        S, Dm = s.shape[1], s.shape[2]
        for i in range(len(self.blocks)):
            blk, c = self.blocks[i], self.cond[i]
            if i > 0:
                q, k, v = blk.qkv(c.n1(s)).chunk(3, -1)
                q, k, v = blk.sq(blk.split(q)), blk.sk(blk.split(k)), blk.split(v)
                half = blk.hd // 2
                att = F.scaled_dot_product_attention(_rope(q, self.rope_cos, self.rope_sin, half),
                                                     _rope(k, self.rope_cos, self.rope_sin, half), v)
                s = s + c.s1 * blk.o1(att.transpose(1, 2).reshape(B, S, Dm))
            q = blk.cq(blk.split(blk.q(c.n2(s))))
            att = F.scaled_dot_product_attention(q, *kvs[i], attn_mask=km)
            s = s + c.s2 * blk.o2(att.transpose(1, 2).reshape(B, S, Dm))
            g, u = blk.gate_up(c.n3(s)).chunk(2, -1)
            s = s + c.s3 * blk.down(F.silu(g) * u)
        return F.linear(self.final_norms[0](s), self.tok.weight[:6818]) + self.bias


class NarEngine:
    """The model on the CPU, loaded from *model_dir* (the caller checked that its files are there)."""

    def __init__(self, model_dir: Path):
        model_dir = Path(model_dir)
        cfg = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        net = NarNet()
        net.load_state_dict({k: v for k, v in load_file(str(model_dir / "model.safetensors")).items() if k not in UNUSED})
        modules = dict(net.named_modules())
        for name, eps in cfg["reparam"]["norm_eps"].items():
            modules[name].eps = eps
        self._net = net.float().eval()
        self._net.prepare()
        self._chars = json.loads((model_dir / VOCAB).read_text(encoding="utf-8"))["characters"]

    def read(self, image: Image.Image) -> str:
        """The line in *image*, as the model spells it."""
        patches, valid, rows, cols, h, w = preprocess(image)
        with torch.inference_mode():
            logits = self._net(torch.from_numpy(patches)[None], torch.from_numpy(valid)[None],
                               torch.from_numpy(rows)[None], torch.from_numpy(cols)[None],
                               torch.tensor([h]), torch.tensor([w]))
        ids = logits.argmax(-1)[0].tolist()
        end = len(self._chars)  # the id after the last character ends the text
        return "".join(self._chars[i] for i in ids[:ids.index(end) if end in ids else len(ids)])
