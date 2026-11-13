"""Lettering on the drawing: which regions go to the inpainting, what its mask takes, which model on which device, what
happens when one fails; and the two things that came with it: credits left alone, and no box for a missing glyph."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from taslation.config import LAMA_MODEL, Settings
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.render import artwork
from taslation.render.artwork import ArtEraser, art_mask, is_dash, on_art, ring_comp, window


def region(kind="text", box=(100, 100, 200, 300), **more):
    x0, y0, x1, y1 = box
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box=box, kind=kind, **more)


def flat(value=255, size=(500, 500)):
    return np.full((*size, 3), value, np.uint8)


def toned():
    page = flat(200)
    page[::4] = 90  # a tone: the ground is no flat colour
    return page


def ringed_glyphs(gray, x=40):
    """Dark strokes with a white ring on *gray*."""
    for y in (40, 90, 140):
        cv2.rectangle(gray, (x - 3, y - 3), (x + 23, y + 23), 255, -1)  # a 3 px white outline
        cv2.rectangle(gray, (x, y), (x + 20, y + 20), 0, 3)


# ------------------------------------------------------------------ the lettering's mask
def test_a_glyph_ringed_by_white_is_lettering_even_on_black():
    gray = np.zeros((200, 100), np.uint8)
    ringed_glyphs(gray)
    mask = ring_comp(gray)
    assert mask[50, 40] and mask[100, 40]  # a stroke
    assert mask[38, 38]  # its ring
    assert not mask[100, 5]  # the black around stays


def test_a_dark_area_with_no_ring_is_no_lettering():
    assert not ring_comp(np.full((200, 100), 30, np.uint8)).any()


def test_a_piece_may_be_as_wide_as_its_column_but_no_wider():
    gray = np.full((120, 300), 255, np.uint8)
    gray[50:60, 20:170] = 0  # 150 px: over 1.15 x 120 and no dash in line with a glyph
    assert not ring_comp(gray)[55, 80]
    gray = np.full((200, 300), 255, np.uint8)
    gray[50:60, 20:170] = 0  # the same on a box whose short side is 200: a wide glyph
    assert ring_comp(gray)[55, 80]


def _stats(gray):
    return cv2.connectedComponentsWithStats((gray < 150).astype(np.uint8), connectivity=8)[2]


def test_a_long_dash_in_line_with_a_glyph_is_lettering():
    gray = np.full((400, 200), 255, np.uint8)
    gray[30:60, 90:120] = 0  # the glyph
    gray[70:350, 100:106] = 0  # the dash below it
    st = _stats(gray)
    assert is_dash(st, 2, 200, 400) or is_dash(st, 1, 200, 400)
    assert ring_comp(gray)[200, 102]


def test_a_line_that_touches_the_boxs_edge_or_stands_alone_is_the_drawing():
    alone = np.full((400, 200), 255, np.uint8)
    alone[70:350, 100:106] = 0
    assert not is_dash(_stats(alone), 1, 200, 400)
    edge = np.full((400, 200), 255, np.uint8)
    edge[30:60, 90:120] = 0
    edge[70:400, 100:106] = 0
    st = _stats(edge)
    assert not any(is_dash(st, i, 200, 400) for i in (1, 2) if st[i][3] > 100)


def test_light_lettering_ringed_by_dark_is_found_on_the_negative():
    page = flat(255)
    gray = np.zeros((200, 100), np.uint8)
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([255 - gray] * 3)
    mask = art_mask(page, region("text-dark", (100, 100, 200, 300)))
    assert mask is not None and mask[150, 140]


def test_a_box_with_too_little_lettering_is_left_alone():
    page = flat(120)
    assert art_mask(page, region()) is None


def test_the_mask_is_of_the_lettering_box_where_there_is_one():
    page = flat(60)  # outlined lettering on dark art
    gray = np.full((200, 100), 60, np.uint8)
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    r = region("text", (50, 50, 400, 400), letter_box=(100, 100, 200, 300))
    mask = art_mask(page, r)
    assert not mask[:90].any() and not mask[310:].any()


def test_the_window_is_512_more_for_a_larger_box_and_stays_on_the_page():
    assert window((1000, 800), 100, 100, 50, 50) == (0, 0, 512, 512)
    assert window((1000, 800), 700, 900, 50, 50) == (288, 488, 800, 1000)
    x0, y0, x1, y1 = window((1000, 800), 100, 100, 700, 50)
    assert y1 - y0 == 764 and x1 - x0 == 512


# ------------------------------------------------------------------ which regions
@pytest.mark.parametrize("kind", ["text", "text-on-page", "text-dark", "text-on-dark"])
def test_lettering_on_a_tone_goes_to_the_model_on_flat_ground_it_does_not(kind):
    assert on_art(toned(), region(kind))
    assert not on_art(flat(), region(kind))


@pytest.mark.parametrize("kind", ["bubble", "dark-bubble"])
def test_bubbles_stay_on_paper_fill_whatever_lies_round_them(kind):
    assert not on_art(toned(), region(kind))
    assert not on_art(toned(), region(kind, tier=1))


@pytest.mark.parametrize("ground, expected", [(toned, True), (flat, True)])
def test_a_model_bubble_that_could_not_be_closed_always_goes_to_the_model(ground, expected):
    assert on_art(ground(), region("bubble", tier=3)) is expected


def test_a_model_bubble_on_a_white_area_goes_by_its_ground():
    assert on_art(toned(), region("bubble", tier=2))
    assert not on_art(flat(), region("bubble", tier=2))


@pytest.mark.parametrize("kind", ["manual", "manual-dark", "cached"])
def test_a_readers_rectangle_stays_with_the_paper_fill(kind):
    assert not on_art(toned(), region(kind))


# ------------------------------------------------------------------ the model's handling
class FakeModel:
    """Fills every hole with grey, or fails."""

    def __init__(self, fails=False, device="cpu"):
        self.fails = fails
        self.runs = 0
        self.device = device

    def run(self, image, mask):
        self.runs += 1
        if self.fails:
            raise RuntimeError("no memory")
        out = image.copy()
        out[mask] = 128
        return out


def drawn(size=(500, 500)):
    """A ground with a drawing's texture: no colour, no shading, no lettering."""
    noise = np.random.default_rng(7).integers(150, 256, size, dtype=np.uint8)
    return np.dstack([cv2.GaussianBlur(noise, (0, 0), 1.0)] * 3)


def lettered(ground=None):
    """Outlined lettering on *ground* (by default a drawing's texture) in the box (100, 100, 200, 300)."""
    page = drawn() if ground is None else ground
    gray = np.ascontiguousarray(page[100:300, 100:200, 0])
    ringed_glyphs(gray)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    return page


def fallback_calls():
    calls = []

    def erase(image, region, *args):
        calls.append(args)
        return (1, 2, 3)
    return calls, erase


def test_the_model_fills_the_lettering_only(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = lettered()
    before = page.copy()
    bg = eraser.erase(page, region())
    assert not calls and eraser.counts["art"] == 1 and len(bg) == 3
    changed = (page != before).any(axis=2)
    assert changed[100:300, 100:200].any() and not changed[:90].any() and not changed[:, :90].any()
    assert (page[changed] == 128).all()


def test_a_region_on_flat_ground_goes_to_the_app_with_all_it_was_given(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    assert eraser.erase(flat(), region(), "fill", 225, 140, False) == (1, 2, 3)
    assert calls == [("fill", 225, 140, False)] and eraser._model.runs == 0


@pytest.mark.parametrize("ground", ["black", "white", "gradient"])
def test_lettering_on_a_flat_or_shaded_ground_goes_to_the_app(tmp_path, ground):
    """A black panel, a white one, a smooth gradient: the paper fill paints what lay there, the model would blotch it."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = {"black": flat(0), "white": flat(255),
            "gradient": np.repeat(np.linspace(40, 220, 500).astype(np.uint8)[:, None, None], 500, axis=1).repeat(3, axis=2)}[ground]
    page[[88, 90, 92, 308, 310, 312], :] = 128  # lines of the panel's drawing round the box: it is on the art
    page[:, [88, 90, 92, 208, 210, 212]] = 128
    page = lettered(page)
    assert on_art(page, region())
    eraser.erase(page, region())
    assert calls and eraser.counts["ground"] == 1 and eraser._model.runs == 0


def test_too_little_lettering_goes_to_the_app(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = np.repeat(np.linspace(160, 250, 500).astype(np.uint8)[None, :, None], 500, axis=0).repeat(3, axis=2)
    eraser.erase(page, region())
    assert calls and eraser.counts["weak"] == 1


def test_a_page_too_small_for_the_models_goes_to_the_app(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    page = lettered()[:230]
    eraser.erase(page, region("text", (100, 20, 200, 200)))
    assert calls and eraser._model.runs == 0 and not eraser.failed


def test_no_model_at_all_leaves_the_page_to_the_app(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    assert eraser.erase(lettered(), region()) == (1, 2, 3)
    assert eraser.failed and not eraser.ready()


def test_a_failure_on_the_gpu_moves_to_the_cpu(tmp_path, monkeypatch):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel(fails=True, device="cuda")
    devices = []

    def load(device):
        devices.append(device)
        eraser._model = FakeModel()

    monkeypatch.setattr(eraser, "_load", load)
    eraser.erase(lettered(), region())
    assert devices == ["cpu"] and not calls and eraser.counts["art"] == 1 and not eraser.failed


def test_a_failure_on_the_cpu_gives_up_for_good(tmp_path):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    model = eraser._model = FakeModel(fails=True)
    eraser.erase(lettered(), region())
    assert calls and eraser.failed and eraser._model is None  # (and its memory given back)
    eraser.erase(lettered(), region())
    assert len(calls) == 2 and model.runs == 1


def test_release_gives_the_model_back_and_the_next_erase_loads_it(tmp_path, monkeypatch):
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    eraser.release()
    assert eraser._model is None
    eraser.release()
    loaded = []
    monkeypatch.setattr(eraser, "_load", lambda device: (loaded.append(device), setattr(eraser, "_model", FakeModel())))
    eraser.erase(lettered(), region())
    assert loaded == [ArtEraser._device()]  # the device torch has


# ------------------------------------------------------------------ the rule: where the erase runs (art_erase)
def _weights(folder: Path) -> Path:
    """LaMa's weights as a file that only exists (nothing in this part of the tests loads it)."""
    (folder / LAMA_MODEL.dirname).mkdir(parents=True, exist_ok=True)
    (folder / LAMA_MODEL.dirname / LAMA_MODEL.installed[0]).write_bytes(b"x")
    return folder


@pytest.fixture
def torch_says(monkeypatch):
    """Stands in for torch's answer to whether it has a CUDA GPU (`torch.cuda.is_available`), counting the asks; the
    rule's own memory of it starts empty (the suite's fixture already set it so for a ``page_models`` test)."""
    import torch

    asked = []

    def answer(value: bool) -> list:
        def is_available():
            asked.append(1)
            return value

        monkeypatch.setattr(torch.cuda, "is_available", is_available)
        monkeypatch.setattr(artwork, "_cuda", None)
        return asked
    return answer


@pytest.mark.page_models
@pytest.mark.parametrize("gpu", [True, False], ids=["gpu", "no-gpu"])
def test_auto_runs_lama_only_with_a_gpu_lama_always_and_off_never(tmp_path, torch_says, gpu):
    asked = torch_says(gpu)
    _weights(tmp_path)
    assert artwork.available(tmp_path, "auto") is gpu and artwork.available(tmp_path) is gpu  # ("auto": the default)
    assert artwork.available(tmp_path, "lama") and not artwork.available(tmp_path, "off")
    assert artwork.runs_here("auto") is gpu and artwork.runs_here("lama") and not artwork.runs_here("off")
    assert len(asked) == 1  # torch asked once, and only for "auto"
    assert artwork.available(tmp_path, "auto", cuda=not gpu) is (not gpu)  # (a caller that knows says so)
    assert not (tmp_path / LAMA_MODEL.dirname / LAMA_MODEL.files[0][0]).exists()  # the checkpoint is not needed


@pytest.mark.page_models
@pytest.mark.parametrize("gpu", [True, False], ids=["gpu", "no-gpu"])
def test_without_lamas_weights_nothing_runs_and_torch_is_not_asked(tmp_path, torch_says, gpu):
    asked = torch_says(gpu)
    assert not any(artwork.available(tmp_path, setting) for setting in artwork.ART_ERASES)
    assert asked == []


@pytest.mark.page_models
def test_off_and_lama_and_the_settings_themselves_never_ask_torch(tmp_path, torch_says):
    asked = torch_says(True)
    assert artwork.runs_here("lama") and not artwork.runs_here("off")
    s = Settings(state_dir=tmp_path)
    s.validate()
    (tmp_path / "taslation.toml").write_text('art_erase = "auto"\n', encoding="utf-8")
    assert Settings.from_toml(tmp_path / "taslation.toml").art_erase == "auto" == s.art_erase
    assert asked == []


@pytest.mark.page_models
def test_a_torch_that_cannot_say_counts_as_no_gpu(torch_says, monkeypatch):
    import torch

    torch_says(True)

    def broken():
        raise RuntimeError("no driver")

    monkeypatch.setattr(torch.cuda, "is_available", broken)
    assert not artwork.has_cuda() and not artwork.runs_here("auto")


def _art_page() -> tuple[np.ndarray, TextRegion]:
    """Lettering on a tone (a region `on_art`), as LaMa would take it out if it ran."""
    page = lettered()
    r = region()
    assert on_art(page, r) and art_mask(page, r) is not None
    return page, r


@pytest.mark.page_models
def test_the_default_on_a_computer_without_a_gpu_letters_byte_for_byte_as_off(tmp_path, torch_says, monkeypatch,
                                                                             sample_page):
    """Weights installed and every page model allowed to come, but no CUDA: the default settings make no eraser and no
    layout model, never load LaMa, and letter the page exactly as art_erase "off" does."""
    from helpers import EN_TEXTS, FakeOcr

    from taslation.config import PAGE_MODELS
    from taslation.translate import DictTranslator

    torch_says(False)
    for model in PAGE_MODELS:  # (the layout model too: "auto" for it would follow the erase)
        for name in model.installed or [n for n, _sha in model.files]:
            (tmp_path / "models" / model.dirname).mkdir(parents=True, exist_ok=True)
            (tmp_path / "models" / model.dirname / name).write_bytes(b"x")
    monkeypatch.setattr(ArtEraser, "_load", lambda self, device: pytest.fail("LaMa was loaded"))
    out = {}
    for name, extra in (("default", {}), ("off", {"art_erase": "off"}), ("auto, auto", {"detect_model": "auto"})):
        s = Settings(state_dir=tmp_path / name, models_dir=tmp_path / "models", **extra)
        p = Pipeline(s, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None)
        assert p.art_eraser is None and p.layout is None and p.gpu_releases == [], name
        page, r = _art_page()
        p.letter_region(page, r, "Hello")
        out[name] = (page.tobytes(), np.asarray(p.process(sample_page, use_cache=False).image).tobytes())
    assert out["default"] == out["off"] == out["auto, auto"]


def test_the_network_has_the_checkpoints_tensors_and_keeps_the_size_it_was_given():
    import torch

    from taslation.render import lama

    net = lama.Lama()
    names = {k for k in net.state_dict() if not k.endswith("num_batches_tracked")}
    assert len(names) == 837 and "model.5.conv1.ffc.convg2g.fu.conv_layer.weight" in names
    assert tuple(net.state_dict()["model.4.ffc.convl2g.weight"].shape) == (384, 256, 3, 3)
    model = lama.LamaInpainter.__new__(lama.LamaInpainter)
    model.device, model.net = "cpu", net.eval()
    image = np.full((37, 53, 3), 128, np.uint8)
    out = model.run(image, np.zeros((37, 53), bool))
    assert out.shape == image.shape and out.dtype == np.uint8
    assert torch.get_num_threads() >= 1


def test_the_fourier_unit_gives_back_what_a_neutral_spectral_step_leaves_alone():
    """With the spectral convolution set to pass its input through and nothing clipped, the unit is the identity: the
    real inverse FFT undoes the forward one (the network as trained, not an export's variant)."""
    import torch

    from taslation.render.lama import FourierUnit

    unit = FourierUnit(2).eval()
    with torch.no_grad():
        unit.conv_layer.weight.copy_(torch.eye(4)[:, :, None, None])
        unit.bn.running_mean.zero_(); unit.bn.running_var.fill_(1 - 1e-5); unit.bn.weight.fill_(1); unit.bn.bias.zero_()
        unit.relu = torch.nn.Identity()
        x = torch.randn(1, 2, 8, 6)
        assert torch.allclose(unit(x), x, atol=1e-5)


def test_weights_of_another_network_are_refused(tmp_path):
    import torch
    from safetensors.torch import save_file

    from taslation.render import lama

    save_file({"model.1.ffc.convl2l.weight": torch.zeros(64, 4, 7, 7)}, str(tmp_path / "w.safetensors"))
    with pytest.raises(ValueError, match="not this network"):
        lama.load(tmp_path / "w.safetensors", "cpu")


# ------------------------------------------------------------------ in the pipeline
def test_an_early_look_skips_the_model_and_the_finished_page_does_not(settings):
    p = Pipeline(settings, translator=None, cache=None)
    used = []
    p.art_eraser = SimpleNamespace(erase=lambda *a: used.append("model") or (255, 255, 255), release=lambda: None)
    page = flat(255, (400, 400))
    r = region("text", (50, 50, 150, 250))
    p.letter_region(page, r, "Hello", quick=True)
    assert used == []
    p.letter_region(page, r, "Hello")
    assert used == ["model"]


def test_classic_stays_byte_for_byte_with_the_models_folder_full(settings, monkeypatch):
    monkeypatch.setattr(artwork, "available", lambda *a: True)
    settings.erase_mode = "classic"
    assert Pipeline(settings, translator=None, cache=None).art_eraser is None


# ------------------------------------------------------------------ the real model
REAL = Settings()
needs_lama = pytest.mark.skipif(bool(LAMA_MODEL.missing(REAL.models_dir)), reason="LaMa not set up")


@needs_lama
def test_the_real_model_takes_the_lettering_off_a_tone():
    page = lettered()
    eraser = ArtEraser(REAL.models_dir, "lama")
    before = page.copy()
    eraser.erase(page, region())
    eraser.release()
    assert eraser.counts["art"] == 1 and not eraser.failed
    assert (page != before).any()


@needs_lama
def test_lama_under_the_network_guard_and_without_onnx_runtime():
    """Loading and running LaMa try nothing online, and nothing imports ONNX Runtime."""
    code = """
import sys
from taslation import netguard
netguard.install()
import numpy as np
from taslation.config import Settings
from taslation.render.artwork import ArtEraser
e = ArtEraser(Settings().models_dir, "lama")
e._load("cpu")
out = e._model.run(np.full((256, 256, 3), 200, np.uint8), np.zeros((256, 256), bool))
assert out.shape == (256, 256, 3)
assert not netguard._state.blocked, netguard._state.blocked
assert "onnxruntime" not in sys.modules and "onnx" not in sys.modules
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]


def _unclosed_bubble(ground):
    """Glyphs in a model bubble whose thin outline is open at the bottom (tier 3: the detectors could not close it)."""
    page = ground
    cv2.ellipse(page, (150, 190), (60, 110), 0, 200, 340 + 180, (60, 60, 60), 1)  # thin, grey, with a gap
    for y in (110, 150, 190, 230):
        cv2.rectangle(page, (140, y), (160, y + 20), (0, 0, 0), 3)
    return page


def test_a_model_bubble_with_paper_under_its_lettering_goes_to_the_paper_fill(tmp_path):
    """An unclosed model bubble whose ground between the strokes is paper: its open outline was what the detectors
    missed, and the paper fill paints the lettering alone; on a drawing's texture it is still the model's."""
    calls, app = fallback_calls()
    eraser = ArtEraser(tmp_path, "auto", app)
    eraser._model = FakeModel()
    r = region("bubble", (120, 100, 180, 260), tier=3, from_model=True)
    paper = _unclosed_bubble(flat(255))
    assert artwork.on_paper(paper, r)
    eraser.erase(paper, r)
    assert calls and eraser.counts["ground"] == 1 and eraser._model.runs == 0
    assert not artwork.on_paper(_unclosed_bubble(drawn()), r)
    assert not artwork.on_paper(paper, region("bubble", (120, 100, 180, 260), tier=0, from_model=True))
