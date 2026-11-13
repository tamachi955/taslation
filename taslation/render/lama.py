"""LaMa, the inpainting network, in plain PyTorch: the generator of a manga LaMa checkpoint and nothing else.

The architecture is the one of "Resolution-robust Large Mask Inpainting with Fourier Convolutions" (Suvorov et al.,
WACV 2022) as its authors published it in advimman/lama (Apache-2.0): the big-lama generator ("ffc_resnet", 64 base
channels, three downsamplings, 18 residual blocks of fast Fourier convolutions with three quarters of the channels
global, no local Fourier unit, reflect padding, sigmoid out). This module is written for TASlation from that structure
and the checkpoint's own tensor names and shapes; no code of a GPL project is in it. It is the network as trained,
inverse FFT and all: the ONNX export the measurements of 2026-11-03 ran (ogkalu/lama-manga-onnx-dynamic, the same
weights) builds its inverse FFT with the mirrored half of each row one bin off, and TASlation does not copy that. On
the synthetic sets of tools/erase_eval.py the two score about the same (see docs/THIRD_PARTY.md).

The weights are dreMaz/AnimeMangaInpainting's lama_large_512px.ckpt (MIT), big LaMa fine-tuned on manga and anime.
``setup_models.py`` fetches that checkpoint at a pinned revision, checks its SHA-256, reads it with
``torch.load(weights_only=True)`` once and keeps the generator as safetensors (`convert`); the application reads only
the safetensors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

import torch
from torch import nn

GLOBAL_SHARE = 0.75  # of a residual block's channels, those in the spectral (global) branch
BASE, DOWN, BLOCKS = 64, 3, 18
MOD = 8  # the network takes sizes that divide by this


class FourierUnit(nn.Module):
    """A 1x1 convolution in the frequency domain: real FFT, the real and imaginary parts as channels, back again."""

    def __init__(self, channels: int):
        super().__init__()
        self.conv_layer = nn.Conv2d(channels * 2, channels * 2, 1, bias=False)
        self.bn = nn.BatchNorm2d(channels * 2)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        spectrum = torch.fft.rfftn(x, dim=(-2, -1), norm="ortho")
        parts = torch.stack((spectrum.real, spectrum.imag), dim=-1)  # b, c, h, w/2+1, 2
        parts = parts.permute(0, 1, 4, 2, 3).reshape(b, c * 2, h, -1)  # channel by channel: real, imaginary
        parts = self.relu(self.bn(self.conv_layer(parts)))
        parts = parts.reshape(b, -1, 2, h, parts.shape[-1]).permute(0, 1, 3, 4, 2).contiguous()
        return torch.fft.irfftn(torch.complex(parts[..., 0], parts[..., 1]), s=(h, w), dim=(-2, -1), norm="ortho")


class SpectralTransform(nn.Module):
    """The global branch: halve the channels, a Fourier unit with a shortcut, back to full width."""

    def __init__(self, cin: int, cout: int):
        super().__init__()
        self.conv1 = nn.Sequential(nn.Conv2d(cin, cout // 2, 1, bias=False), nn.BatchNorm2d(cout // 2), nn.ReLU(inplace=True))
        self.fu = FourierUnit(cout // 2)
        self.conv2 = nn.Conv2d(cout // 2, cout, 1, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        return self.conv2(x + self.fu(x))


class FFC(nn.Module):
    """A fast Fourier convolution: local and global channels, each mixed into both (global to global spectrally)."""

    def __init__(self, cin: int, cout: int, kernel: int, gin: float, gout: float, stride: int = 1, padding: int = 0):
        super().__init__()
        in_g, out_g = int(cin * gin), int(cout * gout)
        in_l, out_l = cin - in_g, cout - out_g
        self.local_out, self.global_out = out_l > 0, out_g > 0

        def conv(a: int, b: int) -> nn.Module:
            if a == 0 or b == 0:
                return nn.Identity()
            return nn.Conv2d(a, b, kernel, stride, padding, bias=False, padding_mode="reflect")

        self.convl2l, self.convl2g, self.convg2l = conv(in_l, out_l), conv(in_l, out_g), conv(in_g, out_l)
        self.convg2g = SpectralTransform(in_g, out_g) if in_g and out_g else nn.Identity()

    def forward(self, x: tuple[torch.Tensor, Any]) -> tuple[Any, Any]:
        x_l, x_g = x
        out_l: Any = 0
        out_g: Any = 0
        if self.local_out:
            out_l = self.convl2l(x_l) + (self.convg2l(x_g) if torch.is_tensor(x_g) else 0)
        if self.global_out:
            out_g = self.convl2g(x_l) + (self.convg2g(x_g) if torch.is_tensor(x_g) else 0)
        return out_l, out_g


class FFCBlock(nn.Module):
    """An FFC with batch norm and ReLU on each branch (a branch with no channels stays 0)."""

    def __init__(self, cin: int, cout: int, kernel: int, gin: float, gout: float, stride: int = 1, padding: int = 0):
        super().__init__()
        self.ffc = FFC(cin, cout, kernel, gin, gout, stride, padding)
        out_g = int(cout * gout)
        self.bn_l = nn.BatchNorm2d(cout - out_g) if cout - out_g else nn.Identity()
        self.bn_g = nn.BatchNorm2d(out_g) if out_g else nn.Identity()
        self.act = nn.ReLU(inplace=True)

    def forward(self, x: Any) -> tuple[Any, Any]:
        x_l, x_g = self.ffc(x if isinstance(x, tuple) else (x, 0))
        return (self.act(self.bn_l(x_l)) if torch.is_tensor(x_l) else x_l,
                self.act(self.bn_g(x_g)) if torch.is_tensor(x_g) else x_g)


class ResidualBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = FFCBlock(channels, channels, 3, GLOBAL_SHARE, GLOBAL_SHARE, padding=1)
        self.conv2 = FFCBlock(channels, channels, 3, GLOBAL_SHARE, GLOBAL_SHARE, padding=1)

    def forward(self, x: tuple[torch.Tensor, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        x_l, x_g = self.conv2(self.conv1(x))
        return x[0] + x_l, x[1] + x_g


class Concat(nn.Module):
    def forward(self, x: tuple[torch.Tensor, torch.Tensor]) -> torch.Tensor:
        return torch.cat(x, dim=1)


def generator() -> nn.Sequential:
    """The big-lama generator; its indices are the checkpoint's ("model.<i>...")."""
    layers: list[nn.Module] = [nn.ReflectionPad2d(3), FFCBlock(4, BASE, 7, 0, 0)]
    for i in range(DOWN):
        width = BASE * 2 ** i
        layers.append(FFCBlock(width, width * 2, 3, 0, GLOBAL_SHARE if i == DOWN - 1 else 0, stride=2, padding=1))
    width = BASE * 2 ** DOWN
    layers += [ResidualBlock(width) for _ in range(BLOCKS)]
    layers.append(Concat())
    for i in range(DOWN):
        width = BASE * 2 ** (DOWN - i)
        layers += [nn.ConvTranspose2d(width, width // 2, 3, stride=2, padding=1, output_padding=1),
                   nn.BatchNorm2d(width // 2), nn.ReLU(inplace=True)]
    layers += [nn.ReflectionPad2d(3), nn.Conv2d(BASE, 3, 7), nn.Sigmoid()]
    return nn.Sequential(*layers)


class Lama(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.model = generator()

    def forward(self, image: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """*image* (b, 3, h, w) in 0..1 and *mask* (b, 1, h, w), 1 = the hole: the picture filled, 0..1."""
        return self.model(torch.cat([image * (1 - mask), mask], dim=1))


def convert(checkpoint: Path, target: Path) -> None:
    """The generator of the checkpoint (read as tensors only) into a safetensors file; the batch counters left out."""
    from safetensors.torch import save_file

    state = torch.load(str(checkpoint), map_location="cpu", weights_only=True)["gen_state_dict"]
    tensors = {k: v.contiguous() for k, v in state.items() if not k.endswith("num_batches_tracked")}
    _accounted(Lama().load_state_dict(tensors, strict=False))  # (shapes: load_state_dict raises on one that differs)
    save_file(tensors, str(target))


def _accounted(result: Any) -> None:
    """Every tensor of the network given and none else (the batch counters aside), or ValueError."""
    missing = [k for k in result.missing_keys if not k.endswith("num_batches_tracked")]
    if missing or result.unexpected_keys:
        raise ValueError(f"not this network's weights: {len(missing)} missing, {len(result.unexpected_keys)} unexpected")


def check(path: Path) -> None:
    """ValueError unless the safetensors file at *path* holds this network's tensors, names and shapes, read from its
    header (nothing is loaded)."""
    from safetensors import safe_open

    want = {k: tuple(v.shape) for k, v in Lama().state_dict().items() if not k.endswith("num_batches_tracked")}
    with safe_open(str(path), framework="pt") as f:
        have = {k: tuple(f.get_slice(k).get_shape()) for k in f.keys()}
    if have != want:
        raise ValueError(f"not this network's weights: {len(set(want) ^ set(have))} names differ")


def load(path: Path, device: str) -> Lama:
    """The network from the safetensors file of `convert`, every tensor accounted for."""
    from safetensors.torch import load_file

    net = Lama()
    _accounted(net.load_state_dict(load_file(str(path)), strict=False))
    return net.eval().to(device)


class LamaInpainter:
    """`run` fills a mask in an RGB picture of any size, on *device*."""

    def __init__(self, path: Path, device: str):
        self.device = device
        self.net = load(path, device)

    def run(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        pad_h, pad_w = (MOD - h % MOD) % MOD, (MOD - w % MOD) % MOD
        x = torch.from_numpy(np.ascontiguousarray(image)).permute(2, 0, 1)[None].float().div(255)
        y = torch.from_numpy(mask.astype(np.float32))[None, None]
        x = nn.functional.pad(x, (0, pad_w, 0, pad_h), mode="reflect")
        y = nn.functional.pad(y, (0, pad_w, 0, pad_h))
        with torch.inference_mode():
            out = self.net(x.to(self.device), y.to(self.device))[0, :, :h, :w]
        return out.mul(255).round().clamp(0, 255).byte().permute(1, 2, 0).cpu().numpy()


__all__ = ["Lama", "LamaInpainter", "check", "convert", "generator", "load"]
