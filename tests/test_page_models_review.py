"""What the review of the layout and inpainting models found, one test each: memory given back on a GPU that is full,
the bubble's own outline kept out of its lettering, a text over a bubble's edge, a checkpoint that is not the
network, stored translations that survive the layout model coming and going, the erase checked before the layout model
runs, what counts as the same lettering, the page's usual size, releases that never wait, LaMa's work kept, the start's
line, two regions lettering one place, and the size of lettering the model found."""
from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

from taslation.cache import CachedBubble, CachedPage
from taslation.config import LAMA_MODEL, Settings
from taslation.detect import layout
from taslation.detect.layout import BUBBLE, TEXT, LayoutModel, cover_of, model_regions
from taslation.ocr.charspot import CharspotChar, CharspotReading
from taslation.pipeline import Pipeline, bubble_scores
from taslation.regions import TextRegion
from taslation.render import artwork, lama
from taslation.render.artwork import ArtEraser


def region(x0, y0, x1, y1, kind="text", text_box=None, **more):
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((y1 - y0, x1 - x0), 255, np.uint8),
                      text_box=text_box or (x0, y0, x1, y1), kind=kind, **more)


def box(x0, y0, x1, y1, kind=TEXT, score=0.9):
    return (float(x0), float(y0), float(x1), float(y1), score, kind)


class Model:
    def __init__(self, device="cpu", fails=False):
        self.device, self.fails, self.runs = device, fails, 0

    def run(self, image, mask):
        self.runs += 1
        if self.fails:
            raise RuntimeError("out of memory")
        out = image.copy()
        out[mask] = 128
        return out


def lettered():
    page = np.full((500, 500, 3), 200, np.uint8)
    page[::4] = 90
    gray = cv2.GaussianBlur(np.random.default_rng(7).integers(0, 120, (200, 100), dtype=np.uint8), (0, 0), 1.0)  # dark art
    for y in (40, 90, 140):
        cv2.rectangle(gray, (37, y - 3), (63, y + 23), 255, -1)  # a 3 px white outline
        cv2.rectangle(gray, (40, y), (60, y + 20), 0, 3)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    return page


# ------------------------------------------------------------------ 1, 4: a full GPU
def test_a_gpu_too_full_to_load_lama_moves_to_the_cpu(tmp_path, monkeypatch):
    eraser = ArtEraser(tmp_path, "lama", lambda *a: (0, 0, 0))
    monkeypatch.setattr(ArtEraser, "_device", staticmethod(lambda: "cuda"))
    tried = []

    def load(device):
        tried.append(device)
        if device == "cuda":
            raise torch.cuda.OutOfMemoryError("full")
        eraser._model = Model("cpu")

    monkeypatch.setattr(eraser, "_load", load)
    emptied = []
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: emptied.append(1))
    eraser.erase(lettered(), region(100, 100, 200, 300))
    assert tried == ["cuda", "cpu"] and not eraser.failed and eraser.counts["art"] == 1 and emptied


def test_the_layout_model_on_a_full_gpu_goes_on_on_the_cpu_after_letting_go(tmp_path, monkeypatch):
    model = LayoutModel(tmp_path)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    loads = []

    def load(device=""):
        loads.append(device)
        model._device = device
        model._net = object()

    def forward(rgb):
        if model._device == "cuda":
            raise torch.cuda.OutOfMemoryError("full")
        return [(1.0, 2.0, 3.0, 4.0, 0.9, TEXT)]

    monkeypatch.setattr(model, "_load", load)
    monkeypatch.setattr(model, "_forward", forward)
    assert model.detect(np.zeros((40, 40, 3), np.uint8)) == [(1.0, 2.0, 3.0, 4.0, 0.9, TEXT)]
    assert loads == ["cuda", "cpu"] and model._device == "cpu"


# ------------------------------------------------------------------ 2: a bubble's outline is not its lettering
def test_the_ink_of_a_bubble_without_a_text_box_leaves_its_outline_out():
    page = np.full((400, 400, 3), 255, np.uint8)
    cv2.ellipse(page, (200, 200), (150, 100), 0, 0, 360, (0, 0, 0), 3)  # an outline the 8 % inset cuts at the curves
    page[170:230, 190:210] = 0  # the lettering
    r = model_regions(page, [box(50, 100, 350, 300, BUBBLE)])[0]
    assert r.text_box == (190, 170, 210, 230)


# ------------------------------------------------------------------ 3: a text over a bubble's edge
def test_a_text_over_the_edge_of_a_bubble_with_no_text_is_that_bubbles():
    page = np.full((400, 400, 3), 255, np.uint8)
    out = model_regions(page, [box(100, 100, 300, 300, BUBBLE), box(270, 150, 350, 250)])  # 38 % in
    assert len(out) == 1 and out[0].kind == "bubble" and out[0].text_box == (270, 150, 350, 250)
    assert out[0].bbox == (100, 100, 350, 300)  # the region reaches as far as its lettering


def test_a_text_over_the_edge_of_a_bubble_with_text_of_its_own_stands_alone():
    page = np.full((400, 400, 3), 255, np.uint8)
    out = model_regions(page, [box(100, 100, 300, 300, BUBBLE), box(150, 150, 200, 250), box(270, 150, 350, 250)])
    assert len(out) == 2 and out[0].text_box == (150, 150, 200, 250) and out[1].kind == "text"


def test_two_model_regions_of_one_lettering_are_read_once(settings):
    p = Pipeline(settings, ocr=SimpleNamespace(read_chars=lambda img: CharspotReading("そうだね", score=0.95)),
                 translator=None, cache=None)
    a = region(100, 100, 200, 300, "bubble", from_model=True)
    b = region(110, 120, 190, 290, "text", from_model=True)
    regions = [a, b]
    left = p._ocr_regions(np.full((400, 400, 3), 255, np.uint8), regions, lambda m: None)
    assert regions == [a] and left == [b] and b.repeats is a


# ------------------------------------------------------------------ 5: only the network's own tensors
def test_a_checkpoint_with_a_tensor_too_many_or_too_few_is_refused(tmp_path):
    state = {k: v for k, v in lama.Lama().state_dict().items()}
    torch.save({"gen_state_dict": {**state, "model.99.weight": torch.zeros(1)}}, str(tmp_path / "more.ckpt"))
    with pytest.raises(ValueError, match="unexpected"):
        lama.convert(tmp_path / "more.ckpt", tmp_path / "more.safetensors")
    del state["model.34.bias"]
    torch.save({"gen_state_dict": state}, str(tmp_path / "less.ckpt"))
    with pytest.raises(ValueError, match="missing"):
        lama.convert(tmp_path / "less.ckpt", tmp_path / "less.safetensors")
    assert not (tmp_path / "more.safetensors").exists() and not (tmp_path / "less.safetensors").exists()


# ------------------------------------------------------------------ 6: stored translations survive
UNIT = SimpleNamespace(index=0, box=(0, 0, 1000, 1000), fingerprint="f" * 80, aspect=1.0,
                       normalize=lambda b: tuple(v / 1000 for v in b[:4]),
                       denormalize=lambda b: tuple(int(v * 1000) for v in b[:4]))


def match(live, stored):
    return bubble_scores([[b] for b in live], stored, 0.4)


def test_a_model_box_and_a_classical_box_of_one_bubble_match_either_way():
    model, classical = (0.20, 0.20, 0.26, 0.40), (0.15, 0.12, 0.35, 0.48)  # IoU 0.17: the text box and the bubble
    assert match([model], [classical])[0][0] > 0 and match([classical], [model])[0][0] > 0
    assert match([(0.6, 0.6, 0.7, 0.7)], [classical])[0][0] == 0
    assert match([classical], [classical])[0][0] > match([model], [classical])[0][0]  # an IoU match ranks first


def test_two_stored_bubbles_the_detection_now_merges_go_to_neither():
    a, b = (0.10, 0.10, 0.20, 0.30), (0.21, 0.10, 0.31, 0.30)
    merged = (0.09, 0.09, 0.32, 0.31)
    assert match([merged], [a, b]) == [[0.0, 0.0]]


def test_a_stored_bubble_the_detection_now_cuts_in_two_goes_to_neither_half():
    whole = (0.10, 0.10, 0.30, 0.30)
    assert match([(0.10, 0.10, 0.19, 0.30), (0.21, 0.10, 0.30, 0.30)], [whole]) == [[0.0], [0.0]]


def test_a_neighbour_that_merely_overlaps_gets_no_stored_translation():
    stored = (0.10, 0.10, 0.20, 0.30)
    neighbour = (0.16, 0.10, 0.40, 0.30)  # 60 % of the stored bubble on it, IoU 0.2
    assert match([neighbour], [stored]) == [[0.0]]


def test_one_bubble_among_others_finds_its_region_by_containment_alone():
    stored = [(0.15, 0.12, 0.35, 0.48), (0.50, 0.12, 0.70, 0.48)]
    live = [(0.20, 0.20, 0.26, 0.40), (0.55, 0.20, 0.61, 0.40)]  # the model's text boxes, one in each
    scores = match(live, stored)
    assert scores[0][0] > 0 and scores[1][1] > 0 and scores[0][1] == scores[1][0] == 0


def _scan(settings, regions, stored, monkeypatch):
    """`Pipeline.scan` of a page whose detection gives *regions* and whose cache holds the bubbles *stored*: what it keeps,
    what it reads again, and what it saved (pruned)."""
    from taslation import fingerprint as fp

    p = Pipeline(settings, ocr=SimpleNamespace(read_chars=lambda img: CharspotReading("そうだね", score=0.95)),
                 translator=None, cache=SimpleNamespace())
    monkeypatch.setattr(fp, "analyze", lambda rgb, margins, **k: [UNIT])
    monkeypatch.setattr(p, "_detect", lambda rgb: list(regions))
    monkeypatch.setattr(p, "_annotate", lambda rgb, rs, units: rs)
    page = CachedPage(fingerprint=UNIT.fingerprint, aspect=1.0, bubbles=list(stored))
    monkeypatch.setattr(p, "_lookup", lambda unit, before=None: (page, 0))
    saved = []
    monkeypatch.setattr(p, "_save_page", lambda fpr, aspect, bubbles, incomplete=False: saved.append(list(bubbles)))
    from PIL import Image

    scan = p.scan(Image.new("RGB", (1000, 1000), "white"))
    su = scan.units[0]
    return su, saved


def test_a_cache_of_classical_boxes_is_kept_and_not_read_again_with_the_layout_model(settings, monkeypatch):
    classical = region(150, 120, 350, 480, "bubble", text_box=(200, 200, 260, 400))
    model = region(196, 196, 264, 404, "text", text_box=(200, 200, 260, 400), from_model=True)
    hand = region(600, 600, 700, 700, "manual")  # a translation typed in the reader's own rectangle
    stored = [CachedBubble(box=(0.15, 0.12, 0.35, 0.48), text="Hello"), CachedBubble(box=(0.6, 0.6, 0.7, 0.7), text="Mine")]
    su, saved = _scan(settings, [model, classical, hand], stored, monkeypatch)
    assert [b.text for b in su.kept] == ["Hello", "Mine"] and su.dropped == 0 and not su.regions and not saved


def test_a_cache_of_model_boxes_is_kept_with_the_layout_model_off(settings, monkeypatch):
    classical = region(150, 120, 350, 480, "bubble", text_box=(200, 200, 260, 400))
    hand = region(600, 600, 700, 700, "manual")
    stored = [CachedBubble(box=(0.196, 0.196, 0.264, 0.404), text="Hello"), CachedBubble(box=(0.6, 0.6, 0.7, 0.7), text="Mine")]
    su, saved = _scan(settings, [classical, hand], stored, monkeypatch)
    assert [b.text for b in su.kept] == ["Hello", "Mine"] and su.dropped == 0 and not su.regions and not saved


def test_a_cache_of_two_bubbles_now_detected_as_one_is_read_again(settings, monkeypatch):
    merged = region(90, 90, 330, 310, "bubble", text_box=(110, 110, 310, 290))
    stored = [CachedBubble(box=(0.10, 0.10, 0.20, 0.30), text="One"), CachedBubble(box=(0.21, 0.10, 0.31, 0.30), text="Two")]
    su, _saved = _scan(settings, [merged], stored, monkeypatch)
    assert su.kept == [] and len(su.regions) == 1  # no stored line goes to it: translated again


def test_a_cache_of_one_bubble_now_cut_in_two_is_read_again(settings, monkeypatch):
    halves = [region(100, 100, 190, 300, "bubble"), region(210, 100, 300, 300, "bubble")]
    stored = [CachedBubble(box=(0.10, 0.10, 0.30, 0.30), text="Whole")]
    su, _saved = _scan(settings, halves, stored, monkeypatch)
    assert su.kept == [] and len(su.regions) == 2


def test_a_bubble_no_region_lies_on_is_still_stale(settings, monkeypatch):
    classical = region(150, 120, 350, 480, "bubble", text_box=(200, 200, 260, 400))
    stored = [CachedBubble(box=(0.15, 0.12, 0.35, 0.48), text="Hello"), CachedBubble(box=(0.8, 0.8, 0.9, 0.9), text="Gone")]
    su, saved = _scan(settings, [classical], stored, monkeypatch)
    assert [b.text for b in su.kept] == ["Hello"] and su.dropped == 1


# ------------------------------------------------------------------ 7: the erase is checked before the layout model runs
def test_weights_that_are_not_lamas_keep_the_layout_model_from_running(settings, tmp_path, monkeypatch):
    from safetensors.torch import save_file

    from taslation.config import LAMA_MODEL

    folder = tmp_path / LAMA_MODEL.dirname
    folder.mkdir()
    save_file({"model.1.ffc.convl2l.weight": torch.zeros(64, 4, 7, 7)}, str(folder / LAMA_MODEL.installed[0]))
    eraser = ArtEraser(tmp_path, "auto")
    assert not eraser.ready() and eraser.failed
    settings.detect_model = settings.art_erase = "auto"
    p = Pipeline(settings, translator=None, cache=None)
    ran = []
    p.layout, p.art_eraser = SimpleNamespace(boxes=lambda *a: ran.append(1) or []), eraser
    p._detect_classical = lambda rgb: []
    assert p._detect(np.full((100, 100, 3), 255, np.uint8)) == [] and ran == []


def test_lamas_own_weights_pass_the_check(tmp_path):
    from safetensors.torch import save_file

    state = {k: v for k, v in lama.Lama().state_dict().items() if not k.endswith("num_batches_tracked")}
    save_file(state, str(tmp_path / "w.safetensors"))
    lama.check(tmp_path / "w.safetensors")


# ------------------------------------------------------------------ 8: the same lettering
def test_lying_in_a_bubbles_box_is_not_lying_in_its_lettering():
    bubble = region(100, 100, 300, 300, "bubble", text_box=(180, 120, 220, 280))
    bubble.mask[:, :50] = 0  # the shape: the left quarter of the box is not the bubble
    inside_box_only = region(102, 150, 140, 250, text_box=(105, 160, 140, 240))
    inside_shape = region(250, 150, 290, 250, text_box=(255, 160, 290, 240))
    assert cover_of(inside_box_only, [bubble]) is None
    assert cover_of(inside_shape, [bubble]) is bubble
    assert cover_of(region(190, 130, 230, 270), [bubble]) is bubble  # text box on text box


# ------------------------------------------------------------------ 9: the page's usual size
def test_every_region_is_judged_on_the_usual_size_of_the_whole_page(settings, monkeypatch):
    p = Pipeline(settings, ocr=SimpleNamespace(read_chars=lambda img: CharspotReading("そうだね", score=0.95)),
                 translator=None, cache=None)
    monkeypatch.setattr(p, "_usual", lambda rgb, regions, cancel=None: 33.0)
    seen = []
    real = p._read_regions
    monkeypatch.setattr(p, "_read_regions", lambda rgb, rs, *a, usual=None, **k: (seen.append(usual), real(rgb, rs, *a, usual=usual, **k)))
    regions = [region(10, 10, 60, 200, from_model=True), region(300, 10, 350, 200), region(500, 10, 550, 200)]
    p._ocr_regions(np.full((400, 600, 3), 255, np.uint8), regions, lambda m: None)
    assert seen == [33.0, 33.0, 33.0]


# ------------------------------------------------------------------ 10: a release never waits
@pytest.mark.parametrize("make", [lambda d: ArtEraser(d, "lama"), lambda d: LayoutModel(d)], ids=["lama", "layout"])
def test_a_release_while_the_model_works_does_not_wait_and_is_done_after(tmp_path, make):
    model = make(tmp_path)
    model._lock.acquire()  # at work
    model.release()
    assert model._release_asked
    model._lock.release()


def test_a_release_asked_during_the_work_lets_go_after_it(tmp_path, monkeypatch):
    eraser = ArtEraser(tmp_path, "lama", lambda *a: (0, 0, 0))
    eraser._model = Model()
    eraser._release_asked = True
    eraser.erase(lettered(), region(100, 100, 200, 300))
    assert eraser._model is None and not eraser._release_asked and eraser.counts["art"] == 1


def test_the_pipeline_reads_its_models_once_per_page(settings):
    """One reference each: a model swapped by the window while the page is read is not half used."""
    import inspect

    source = inspect.getsource(Pipeline._detect) + inspect.getsource(Pipeline._erase)
    assert source.count("self.layout") == 1 and source.count("self.art_eraser") == 2


# ------------------------------------------------------------------ 11: LaMa's work is kept
def test_lettering_a_page_again_does_not_inpaint_again(tmp_path):
    eraser = ArtEraser(tmp_path, "lama", lambda *a: (0, 0, 0))
    model = eraser._model = Model()
    r = region(100, 100, 200, 300)
    first = lettered()
    eraser.erase(first, r)
    second = lettered()
    eraser.erase(second, r)
    assert model.runs == 1 and (first == second).all()
    changed = lettered()
    changed[0:5, 0:5] = 0  # the part of the page it saw is another: inpainted anew
    eraser.erase(changed, r)
    assert model.runs == 2


# ------------------------------------------------------------------ 12: the start's line
def test_no_line_about_models_that_the_settings_would_not_use(tmp_path):
    from taslation.health import page_models_missing

    real = page_models_missing.__wrapped__ if hasattr(page_models_missing, "__wrapped__") else None
    assert real is None  # (the suite stands this down; the module's own is asked below)
    import importlib

    import taslation.health as health

    fresh = importlib.reload(health)
    s = Settings(models_dir=tmp_path)  # (art_erase "auto": LaMa only with a GPU; the suite says this one has none)
    assert not fresh.page_models_missing(s)  # without a GPU the default uses neither model: nothing to say
    s.detect_model = "auto"
    assert not fresh.page_models_missing(s)  # nor does the layout model's "auto", which follows the erase
    s.art_erase = "lama"
    assert fresh.page_models_missing(s)  # LaMa on the CPU too, asked for and not installed
    s.erase_mode = "classic"
    assert not fresh.page_models_missing(s)


def test_with_a_gpu_the_default_asks_for_the_inpainting_alone(tmp_path, monkeypatch):
    import importlib

    import taslation.health as health

    fresh = importlib.reload(health)
    monkeypatch.setattr(artwork, "available", TRUE_AVAILABLE)
    monkeypatch.setattr(artwork, "_cuda", True)
    s = Settings(models_dir=tmp_path)
    assert fresh.page_models_missing(s)  # the inpainting, on by default with a GPU, is not installed: a line says so
    folder = tmp_path / LAMA_MODEL.dirname
    folder.mkdir()
    (folder / LAMA_MODEL.installed[0]).write_bytes(b"x")
    assert not fresh.page_models_missing(s)  # the layout model, off by default, is not asked for
    s.detect_model = "auto"
    assert fresh.page_models_missing(s)
    s.detect_model, s.art_erase = "auto", "off"
    assert not fresh.page_models_missing(s)


# ------------------------------------------------------------------ 16, 18: one place, one lettering; its size
def test_a_classical_region_two_model_regions_claim_gives_neither_its_shape(settings):
    """Two bubbles the classical detector took for one: each model region keeps its own lettering box, so the two
    translations are not set on one place."""
    page = np.full((400, 400, 3), 255, np.uint8)
    joined = region(90, 90, 210, 310, "bubble", text_box=(100, 100, 200, 300))
    p = Pipeline(settings, translator=None, cache=None)
    p.layout = SimpleNamespace(boxes=lambda *a: [box(95, 95, 205, 195), box(95, 205, 205, 305)])
    p.art_eraser = SimpleNamespace(ready=lambda: True)
    settings.detect_model = "on"
    p._detect_classical = lambda rgb: [joined]
    a, b, c = p._detect(page)
    assert c is joined and a.after.adopted is None and b.after.adopted is None


def test_two_regions_lettering_one_place_letter_once_and_neighbours_both_stay(settings):
    p = Pipeline(settings, ocr=SimpleNamespace(read_chars=lambda img: CharspotReading("そうだね", score=0.95)),
                 translator=None, cache=None)
    a = region(95, 95, 205, 180, from_model=True, text_box=(100, 100, 200, 170))
    b = region(98, 98, 207, 178, from_model=True, text_box=(102, 102, 198, 168))  # the same lettering again
    c = region(95, 160, 205, 260, from_model=True, text_box=(100, 160, 200, 255))  # its neighbour, a little over it
    regions = [a, b, c]
    p._ocr_regions(np.full((400, 400, 3), 255, np.uint8), regions, lambda m: None)
    assert regions == [a, c] and b.repeats is a


def test_a_model_region_takes_its_glyph_size_from_its_reading(settings):
    chars = tuple(CharspotChar(c, (0, i * 40, 38, i * 40 + 38), 0.95) for i, c in enumerate("そうだね"))
    p = Pipeline(settings, ocr=SimpleNamespace(read_chars=lambda img: CharspotReading("そうだね", chars, 0.95)),
                 translator=None, cache=None)
    r = region(100, 100, 160, 300, from_model=True)
    p._ocr_regions(np.full((400, 400, 3), 255, np.uint8), [r], lambda m: None)
    assert r.glyph == pytest.approx(38.0)


def test_the_defaults_inpaint_only_with_a_gpu_and_leave_the_layout_model_off():
    s = Settings()
    assert (s.detect_model, s.art_erase) == ("off", "auto")
    assert not TRUE_AVAILABLE(s.models_dir, "off")  # (the suite's stand-in aside, "off" is never available)
    assert not TRUE_AVAILABLE(s.models_dir, "auto", cuda=False)  # nor is "auto" without a GPU


TRUE_AVAILABLE = artwork.__dict__["available"]  # (taken before the suite's fixture stands it down)


# ------------------------------------------------------------------ 13, 15, 17: what the erase takes
def test_a_plain_box_is_painted_out_only_where_its_characters_were_read():
    page = np.full((300, 300, 3), 230, np.uint8)
    page[::6] = 120  # a drawing's hatching all over the box
    page[100:120, 100:120] = 0  # a character the reading found
    r = region(50, 50, 250, 250, "text", from_model=True, tier=3, glyph=20.0)
    r.char_boxes = [(100, 100, 120, 120)]
    before = page.copy()
    Pipeline._paper_erase(page, r)
    changed = (page != before).any(axis=2)
    assert changed[100:120, 100:120].any()
    assert not changed[:90].any() and not changed[130:].any() and not changed[:, 130:].any()  # the hatching stays
    assert (r.mask == 255).all()  # its own mask, where the translation is set, is untouched


def test_a_shaped_region_is_erased_as_before():
    page = np.full((300, 300, 3), 255, np.uint8)
    page[100:120, 100:120] = 0
    r = region(50, 50, 250, 250, "bubble", from_model=True, tier=1)
    before = page.copy()
    Pipeline._paper_erase(page, r)
    assert (page[100:120, 100:120] == 255).all() and not (page != before)[:40].any()


def test_a_stroke_the_box_cut_off_goes_with_its_glyph():
    page = lettered()
    r = region(100, 100, 200, 250)  # the box cuts the last glyph through its middle
    mask = artwork.art_mask(page, r)
    assert mask is not None and mask[255:262, 138:162].any()  # past the box, the same piece


def test_what_lies_along_a_model_bubbles_border_is_its_outline():
    page = np.full((400, 400, 3), 200, np.uint8)
    page[::4] = 90
    gray = np.zeros((200, 100), np.uint8)
    for y in (40, 90, 140):
        cv2.rectangle(gray, (37, y - 3), (63, y + 23), 255, -1)  # a 3 px white outline
        cv2.rectangle(gray, (40, y), (60, y + 20), 0, 3)
    page[100:300, 100:200] = np.dstack([gray] * 3)
    for y in range(102, 298, 12):  # a dashed outline just inside the bubble's box, each dash ringed by white
        cv2.rectangle(page, (99, y - 2), (107, y + 7), (255, 255, 255), -1)
        cv2.rectangle(page, (101, y), (105, y + 5), (0, 0, 0), -1)
    bubble = region(100, 100, 200, 300, "bubble", from_model=True, tier=3, text_box=(100, 100, 200, 300))
    mask = artwork.art_mask(page, bubble)
    assert mask is not None and not mask[100:300, 100:104].any() and mask[140:160, 140:160].any()


# ------------------------------------------------------------------ 14: titles
def read_as(r, text, size):
    r.status, r.source_text, r.char_size = "untranslated", text, size
    return r


def test_a_unit_holding_only_its_title_and_credit_leaves_them_as_print(settings):
    p = Pipeline(settings, translator=None, cache=None)
    title = read_as(region(100, 100, 700, 200, "text", from_model=True), "まちがったこを", 80.0)
    author = read_as(region(300, 300, 420, 340, "text"), "双龍", 30.0)
    regions = [title, author]
    p._titles(regions, 12.0, None)
    assert [r.status for r in regions] == ["print", "print"]


@pytest.mark.parametrize("other", [
    lambda: read_as(region(800, 100, 860, 300, "bubble"), "そうだね", 12.0),  # a line of speech in a bubble
    lambda: read_as(region(800, 100, 860, 300, "text"), "やめて!", 12.0),  # a mark of speech
    lambda: read_as(region(800, 100, 860, 300, "text"), "ドドドド", 60.0),  # a sound effect
])
def test_a_large_line_on_a_unit_with_speech_stays(settings, other):
    p = Pipeline(settings, translator=None, cache=None)
    shout = read_as(region(100, 100, 300, 600, "text", from_model=True), "許さんぞ", 90.0)
    regions = [shout, other()]
    p._titles(regions, 12.0, None)
    assert shout.status == "untranslated"


def test_lettering_of_the_pages_own_size_is_no_title(settings):
    p = Pipeline(settings, translator=None, cache=None)
    line = read_as(region(100, 100, 130, 220, "text"), "岩鼻登美", 14.0)
    p._titles([line], 12.0, None)
    assert line.status == "untranslated"



def test_a_classical_shape_reaching_into_the_next_bubble_gives_its_lettering_box_only_within_the_region():
    classical = region(460, 820, 570, 995, "bubble", text_box=(485, 832, 556, 978))
    a = region(461, 824, 545, 999, "bubble", from_model=True, text_box=(475, 838, 531, 985))
    a.after = copy_of(a)
    a.after.adopted, a.after.tier = classical, 0
    layout.take_shape(a)
    assert a.letter_box == (485, 832, 545, 978)


def copy_of(r):
    import copy

    return copy.copy(r)


def test_glyphs_near_a_model_bubbles_edge_are_still_lettering():
    page = np.full((300, 300, 3), 200, np.uint8)
    page[::4] = 90
    gray = np.zeros((60, 40), np.uint8)
    cv2.rectangle(gray, (2, 2), (37, 57), 255, -1)
    cv2.rectangle(gray, (6, 6), (33, 53), 0, 3)  # a glyph whose outline comes within 3 px of the box's edge
    page[100:160, 100:140] = np.dstack([gray] * 3)
    bubble = region(99, 99, 141, 161, "bubble", from_model=True, tier=3, text_box=(100, 100, 140, 160))
    mask = artwork.art_mask(page, bubble)
    assert mask is not None and mask[110:150, 105:135].any()


def test_a_plain_box_over_a_shaped_regions_lettering_gives_way(settings):
    p = Pipeline(settings, ocr=SimpleNamespace(read_chars=lambda img: CharspotReading("そうだね", score=0.95)),
                 translator=None, cache=None)
    plain = region(393, 665, 466, 838, "bubble", from_model=True, text_box=(393, 665, 466, 838))
    plain.after = layout.Shaper().rebuilt(np.full((1000, 1000, 3), 128, np.uint8), plain, [])
    shaped = region(360, 700, 435, 920, "text", from_model=True, text_box=(365, 720, 430, 917))
    shaped.after = copy_of(shaped)
    shaped.after.tier = 1
    regions = [plain, shaped]
    p._ocr_regions(np.full((1000, 1000, 3), 128, np.uint8), regions, lambda m: None)
    assert regions == [shaped] and plain.repeats is shaped


def test_a_model_bubble_loses_the_lettering_its_shape_left_out_but_not_its_outline():
    page = np.full((300, 300, 3), 255, np.uint8)
    cv2.rectangle(page, (50, 50), (250, 250), (0, 0, 0), 2)  # the outline, along the box's edge
    page[80:140, 70:130] = 0  # a big glyph the classical shape left out
    page[160:180, 150:170] = 0  # lettering inside the shape
    r = region(48, 48, 253, 253, "bubble", from_model=True, tier=0, text_box=(65, 75, 200, 200), glyph=20.0)
    r.mask[:] = 0
    r.mask[100:150, 90:160] = 255  # the shape: round the small lettering only
    before = page.copy()
    Pipeline._paper_erase(page, r)
    assert (page[85:135, 75:125] > 200).all()  # the big glyph is gone
    assert (page[50:53, 60:240] == before[50:53, 60:240]).all()  # the outline stays


def test_an_unclosed_model_region_counts_as_loose_lettering_for_a_title(settings):
    p = Pipeline(settings, translator=None, cache=None)
    title = read_as(region(100, 100, 300, 600, "bubble", from_model=True, tier=3), "第八話", 90.0)
    closed = read_as(region(100, 100, 300, 600, "bubble", from_model=True, tier=0), "第八話", 90.0)
    p._titles([title], 12.0, None)
    p._titles([closed], 12.0, None)
    assert title.status == "print" and closed.status == "untranslated"


def test_a_page_of_narration_set_large_is_no_title_page(settings):
    p = Pipeline(settings, translator=None, cache=None)
    lines = [read_as(region(100, 100, 300, 600, "text", from_model=True), "夢の翼は", 90.0)]
    lines += [read_as(region(400 + 60 * i, 100, 450 + 60 * i, 300, "text"), "高く翔ぶほど", 14.0) for i in range(4)]
    p._titles(lines, 12.0, None)
    assert {r.status for r in lines} == {"untranslated"}


# ------------------------------------------------------------------ the room of big lettering on the art
def _size(p, r, text="Lorem ipsum dolor sit"):
    return p._set_text(None, r, text, (255, 255, 255), None).size


def test_a_column_of_big_lettering_the_model_found_is_lettered_near_its_own_size():
    """A single column of big glyphs on the art (a shout of two or three glyphs): its translation, set across, takes a
    room grown sideways by up to two glyphs, and comes out larger than in the column alone; the box it was erased in
    is the region's own."""
    from taslation.pipeline import _art_room

    p = Pipeline(Settings(), translator=None, cache=None)
    column = region(400, 100, 480, 400, glyph=70.0, from_model=True)
    room = _art_room(column, (1000, 1000))
    assert room is not column and (room.y0, room.y1) == (100, 400) and room.x0 < 400 and room.x1 > 480
    assert room.x1 - room.x0 <= 80 + 2 * 70 + 1 and room.mask.shape == (room.height, room.width)
    assert column.bbox == (400, 100, 480, 400)
    plain = region(400, 100, 480, 400, glyph=70.0)  # the classical detectors' region: as before
    assert _art_room(plain, (1000, 1000)) is plain
    assert _size(p, column) > _size(p, plain)


def test_a_block_of_small_lettering_a_caption_and_a_bubble_keep_their_room():
    from taslation.pipeline import _art_room

    narration = region(400, 100, 520, 400, glyph=14.0, from_model=True)  # several columns: no single line
    assert _art_room(narration, (1000, 1000)) is narration
    caption = region(400, 100, 420, 400, kind="text-on-page", glyph=14.0, from_model=True)  # one column in its frame
    assert _art_room(caption, (1000, 1000), 22.0) is caption
    big = region(400, 100, 480, 400, kind="text-on-page", glyph=70.0, from_model=True)  # big lettering ringed by white
    assert _art_room(big, (1000, 1000), 22.0) is not big
    bubble = region(400, 100, 480, 400, kind="bubble", glyph=70.0, from_model=True)
    assert _art_room(bubble, (1000, 1000)) is bubble


def test_the_room_of_big_lettering_stays_on_the_page():
    from taslation.pipeline import _art_room

    room = _art_room(region(10, 100, 90, 400, glyph=70.0, from_model=True), (120, 1000))
    assert room.x0 == 0 and room.x1 == 120


def test_the_room_of_big_lettering_stays_in_its_panel():
    """Grown no further than the edge of the panel the region was put in: past it lies the next panel's drawing."""
    from taslation.pipeline import _art_room

    column = region(400, 100, 480, 400, glyph=70.0, from_model=True)
    column.panel = (380, 50, 900, 450)
    room = _art_room(column, (1000, 1000))
    assert room.x0 == 380 and room.x1 > 480 and (room.y0, room.y1) == (100, 400)
    column.panel = (400, 50, 480, 450)  # the panel is as narrow as the column: no room to grow
    assert _art_room(column, (1000, 1000)) is column
    column.panel = None  # no panels found on the page: the page's edge alone
    assert _art_room(column, (1000, 1000)).x0 < 380


def test_lettering_across_a_panels_frame_keeps_its_room_on_the_page():
    """A region that lies less than `PANEL_SURE` inside its panel's box crosses the frame as drawn (or the panel is
    not its own): the page's edge alone holds its room, and its own box is never cut."""
    from taslation.pipeline import PANEL_SURE, _art_room

    column = region(400, 100, 480, 400, glyph=70.0, from_model=True)
    column.panel = (430, 50, 900, 450)  # 50 of its 80 px across inside
    assert 50 / 80 < PANEL_SURE
    assert _art_room(column, (1000, 1000)).x0 < 400
    column.panel = (410, 50, 900, 450)  # 70 of 80 inside: grows to the right only, and keeps its own left edge
    room = _art_room(column, (1000, 1000))
    assert room.x0 == 400 and room.x1 > 480


def test_the_room_in_a_panel_is_what_the_sizes_are_kept_alike_on(settings):
    """The page's sizes (`cap_sizes`) and the lettering take the same room: one held in its panel letters smaller."""
    p = Pipeline(settings, translator=None, cache=None)
    free = region(400, 100, 480, 400, glyph=70.0, from_model=True)
    held = region(400, 100, 480, 400, glyph=70.0, from_model=True)
    held.panel = (395, 50, 485, 450)
    assert _size(p, held) < _size(p, free)


def test_regions_keep_the_panel_they_were_ordered_in():
    from taslation.detect import order_regions

    a, b = region(60, 60, 200, 160), region(400, 500, 560, 620)
    panels = [(20, 20, 320, 440), (340, 20, 620, 880)]
    order_regions([a, b], True, panels)
    assert a.panel == (20, 20, 320, 440) and b.panel == (340, 20, 620, 880)
    order_regions([a, b], True, None)  # a page without panels: none
    assert a.panel is None and b.panel is None


def test_a_region_lettered_on_its_own_takes_its_panel_along(settings, monkeypatch):
    """`letter_region` letters in a part of the page: the panel is seen from that part's corner, as the boxes are."""
    p = Pipeline(settings, translator=None, cache=None)
    page = np.full((1000, 1000, 3), 255, np.uint8)
    column = region(400, 100, 480, 400, glyph=70.0, from_model=True)
    column.panel = (390, 50, 900, 450)
    seen = []
    real = Pipeline._set_text
    monkeypatch.setattr(Pipeline, "_set_text", lambda self, image, r, *a: seen.append(r.panel) or real(self, image, r, *a))
    p.letter_region(page, column, "Lorem ipsum dolor sit")
    assert seen == [(390 - 320, 50 - 0, 900 - 320, 450 - 0)]


def test_a_thin_outline_broken_by_its_anti_aliasing_is_no_lettering_left_out():
    """A model bubble's text box reaching its thin outline: the outline breaks into glyph-sized pieces at the dark
    threshold, but joins up a little above it, and stays; a glyph the mask left out goes."""
    page = np.full((200, 200, 3), 255, np.uint8)
    page[30:170, 40] = np.where(np.arange(140)[:, None] % 12 < 9, 110, 160)  # the outline: dark dashes, grey joints
    page[90:104, 120:134] = 0  # a glyph outside the mask
    r = region(20, 20, 180, 180, kind="bubble", text_box=(30, 30, 170, 170), from_model=True, glyph=14.0)
    r.mask = np.zeros((160, 160), np.uint8)
    r.mask[30:130, 30:90] = 255  # the classical shape: neither the outline nor that glyph
    left = Pipeline._left_out(page, r)
    assert left is not None and left[75:80, 105:110].any() and not left[:, 15:25].any()


def test_lines_set_across_in_one_block_of_the_model_are_print():
    """A back cover's blurb: four lines set across that the layout model saw as one block; lettering runs down."""
    from taslation.pipeline import printed_lines

    def line(y, across=True, **more):
        r = region(100, y, 300, y + 16, text_box=(100, y, 300, y + 16) if across else (100, y, 116, y + 200), **more)
        r.status, r.source_text, r.char_size = "untranslated", "ある日", 14.0
        return r

    block = region(90, 90, 310, 200, from_model=True)
    block.status = "low-confidence"
    lines = [line(y) for y in (100, 125, 150, 175)]
    assert printed_lines([block, *lines]) == lines
    assert printed_lines(lines) == []  # no block of the model's: nothing changes
    assert printed_lines([block, *lines[:3]]) == []  # three lines: a caption may be set so
    columns = [line(100, across=False) for _ in range(4)]
    assert printed_lines([region(90, 90, 310, 310, from_model=True), *columns]) == []
