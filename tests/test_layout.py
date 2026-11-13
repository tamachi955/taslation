"""The layout model and the classical detectors together: boxes to regions, model first, the classical shape after the
reading, what stands in when the model or the erase it needs cannot run; on stand-ins, and on the real model where its
weights are installed."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from taslation.cache import CachedBubble
from taslation.config import LAYOUT_MODEL, ConfigError, Settings
from taslation.detect import layout
from taslation.detect.layout import (BUBBLE, TEXT, LayoutModel, Shaper, covered, model_regions, take_shape)
from taslation.ocr.charspot import CharspotReading
from taslation.pipeline import Pipeline, is_sound_effect
from taslation.regions import TextRegion
from taslation.render import artwork

WHITE = np.full((400, 400, 3), 255, np.uint8)


def box(x0, y0, x1, y1, kind=TEXT, score=0.9):
    return (float(x0), float(y0), float(x1), float(y1), score, kind)


def region(x0, y0, x1, y1, kind="text", text_box=None, **more):
    h, w = y1 - y0, x1 - x0
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=np.full((h, w), 255, np.uint8), text_box=text_box or (x0, y0, x1, y1),
                      kind=kind, **more)


def test_a_text_in_a_bubble_is_that_bubbles_and_several_are_one_region():
    out = model_regions(WHITE, [box(100, 100, 300, 300, BUBBLE), box(150, 120, 190, 280), box(210, 120, 250, 280)])
    assert len(out) == 1
    r = out[0]
    assert (r.kind, r.bbox, r.text_box, r.from_model) == ("bubble", (100, 100, 300, 300), (150, 120, 250, 280), True)
    assert r.mask.shape == (200, 200) and (r.mask == 255).all()


def test_a_text_alone_is_padded_and_a_box_under_its_score_is_no_region():
    out = model_regions(WHITE, [box(100, 100, 150, 300), box(200, 100, 250, 300, score=0.69), box(300, 10, 390, 390, BUBBLE, 0.49)])
    assert [r.bbox for r in out] == [(96, 96, 154, 304)]
    assert out[0].text_box == (100, 100, 150, 300)


def test_a_box_that_repeats_a_surer_one_is_left_out():
    out = model_regions(WHITE, [box(100, 100, 150, 300, score=0.8), box(102, 102, 152, 302, score=0.95)])
    assert [r.text_box for r in out] == [(102, 102, 152, 302)]


def test_a_bubble_without_a_text_box_takes_its_ink():
    page = WHITE.copy()
    page[150:250, 180:220] = 0
    out = model_regions(page, [box(100, 100, 300, 300, BUBBLE)])
    assert out[0].text_box == (180, 150, 220, 250)


def test_a_ground_darker_than_its_lettering_makes_a_dark_kind():
    page = WHITE.copy()
    page[100:300, 100:300] = 20
    page[150:250, 195:205] = 240
    out = model_regions(page, [box(100, 100, 300, 300, BUBBLE, 0.9), box(140, 140, 260, 260)])
    assert out[0].kind == "dark-bubble"


def test_covered_asks_for_a_third_of_either_box():
    read = [region(100, 100, 200, 200)]
    assert covered(region(130, 130, 240, 240), read)
    assert not covered(region(180, 180, 260, 260), read)


def test_a_classical_region_about_the_same_gives_its_mask_and_kind():
    classical = region(100, 100, 200, 300, "text-on-page", glyph=22.0, pieces=9, letter_box=(110, 110, 190, 290))
    classical.mask[:50] = 0
    model = region(98, 98, 202, 302, from_model=True)
    model.text_box = classical.text_box
    model.after = Shaper().rebuilt(WHITE, model, [classical])
    assert model.after.tier == 0 and model.after.adopted is classical
    take_shape(model)
    assert (model.kind, model.glyph, model.pieces, model.letter_box) == ("text-on-page", 22.0, 9, (110, 110, 190, 290))
    assert model.mask.shape == (204, 104) and model.mask[10, 50] == 0 and model.mask[100, 50] == 255
    assert model.after is None


def test_lettering_on_a_drawing_keeps_its_plain_box():
    noise = np.random.default_rng(1).integers(0, 90, (400, 400, 3), dtype=np.uint8)
    model = region(100, 100, 200, 200, "text", from_model=True)
    shaped = Shaper().rebuilt(noise, model, [])
    assert shaped.tier == 3 and shaped.mask is model.mask


def test_lettering_on_a_white_area_takes_the_area_as_a_second_choice():
    page = np.full((400, 400, 3), 40, np.uint8)
    page[120:280, 120:280] = 255
    model = region(110, 110, 290, 290, "bubble", text_box=(150, 150, 250, 250), from_model=True)
    shaped = Shaper().rebuilt(page, model, [])
    assert shaped.tier in (1, 2) and shaped.mask[90, 90] == 255 and shaped.mask[2, 2] == 0


# ------------------------------------------------------------------ in the pipeline, on stand-ins
class FakeLayout:
    def __init__(self, boxes):
        self.found = boxes
        self.failed = False
        self.calls = 0

    def boxes(self, rgb, units):
        self.calls += 1
        return self.found


class FakeOcr:
    """Reads what `texts` says for a crop of a certain width, *default* for the others."""

    def __init__(self, default="そうだね"):
        self.default = default
        self.crops = 0

    def read_chars(self, image):
        self.crops += 1
        return CharspotReading(text=self.default, score=0.95)


def _models(settings, fake, eraser=True):
    settings.models_dir = settings.state_dir / "no models"
    settings.detect_model = settings.art_erase = "auto"
    p = Pipeline(settings, ocr=FakeOcr(), translator=None, cache=None)
    p.layout = fake
    if eraser:
        p.art_eraser = SimpleNamespace(ready=lambda: True, release=lambda: None,
                                       erase=lambda *a: artwork.erase_region(*a))
    return p


def _page():
    page = np.full((400, 600, 3), 255, np.uint8)
    page[100:110, 100:300] = 0
    return page


def test_the_models_regions_are_read_first_and_a_classical_one_that_repeats_them_leaves(settings):
    p = _models(settings, FakeLayout([box(50, 50, 150, 250)]))
    classical = region(60, 60, 150, 250, "text-on-page", glyph=20.0, pieces=4)
    other = region(300, 50, 400, 250, "text")
    p._detect_classical = lambda rgb: [classical, other]
    rgb = _page()
    found = p._detect(rgb)
    assert [r.from_model for r in found] == [True, False, False]
    order, regions = [], list(found)
    read = p._read_regions
    p._read_regions = lambda rgb, rs, *a, **k: (order.extend(rs), read(rgb, rs, *a, **k))
    p._ocr_regions(rgb, regions, lambda m: None)
    assert order == [found[0], other]
    assert classical not in regions and classical.status == "repeated"
    assert found[0].kind == "text-on-page" and found[0].glyph == 20.0  # the shape came after the reading


def test_the_page_says_its_reading_of_every_region(settings):
    p = _models(settings, FakeLayout([box(50, 50, 150, 250)]))
    p._detect_classical = lambda rgb: [region(60, 60, 150, 250, "text"), region(300, 50, 400, 250, "text")]
    said = []
    rgb = _page()
    p._ocr_regions(rgb, p._detect(rgb), lambda m: said.append((m.params["done"], m.params["total"])))
    assert said == [(1, 3), (3, 3)]


def test_without_the_model_the_reading_is_as_it_was(settings):
    p = _models(settings, None)
    rs = [region(60, 60, 150, 250, "text"), region(300, 50, 400, 250, "text")]
    p._ocr_regions(_page(), rs, lambda m: None)
    assert len(rs) == 2 and {r.status for r in rs} == {"untranslated"}


@pytest.mark.parametrize("kind", ["text", "text-dark", "bubble", "dark-bubble"])
def test_a_models_region_passes_the_sound_effect_check_whatever_its_kind(settings, kind):
    settings.translate_sfx = False
    p = _models(settings, None)
    assert is_sound_effect("ドカン")
    r = region(50, 50, 150, 250, kind, from_model=True)
    assert p._judge(r, "ドカン", 0.95, 0) == "sfx"
    settings.translate_sfx = True
    assert p._judge(r, "ドカン", 0.95, 0) == "untranslated"


def test_a_bubble_of_the_classical_detectors_still_keeps_its_sound_effect(settings):
    settings.translate_sfx = False
    assert _models(settings, None)._judge(region(50, 50, 150, 250, "bubble"), "ドカン", 0.95, 0) == "untranslated"


def test_a_cached_page_takes_the_shape_and_shows_one_region_per_bubble(settings):
    p = _models(settings, FakeLayout([]))
    unit = SimpleNamespace(index=0, box=(0, 0, 600, 400), normalize=lambda b: (b[0] / 600, b[1] / 400, b[2] / 600, b[3] / 400))
    classical = region(60, 60, 150, 250, "text-on-page", glyph=20.0)
    model = region(50, 50, 150, 250, from_model=True)
    model.after = Shaper().rebuilt(_page(), model, [classical])
    page = SimpleNamespace(bubbles=[CachedBubble(box=unit.normalize(model.bbox), text="Hello")])
    regions = p._apply_cached(unit, page, [model, classical], _page())
    assert regions == [model] and model.kind == "text-on-page" and model.after is None


def test_a_page_with_a_translation_missing_reads_only_what_it_lacks(settings):
    p = _models(settings, FakeLayout([]))
    known = region(50, 50, 150, 250, from_model=True, status="translated")
    again = region(60, 60, 150, 250)
    new = region(300, 50, 400, 250, from_model=True)
    again.status = new.status = "unmatched"
    regions = [known, again, new]
    p._translate_regions = lambda *a, **k: ""
    page = SimpleNamespace(bubbles=[], incomplete=False, fingerprint="f", aspect=1.0)
    p._complete_page(_page(), SimpleNamespace(box=(0, 0, 600, 400)), page, regions, lambda m: None)
    assert regions == [new, known]  # (in reading order once read: the right one first)


# ------------------------------------------------------------------ what stands in
def _install(folder: Path, *models):
    for model in models:
        for name in model.installed or [name for name, _sha in model.files]:
            path = folder / model.dirname / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")


@pytest.fixture
def installed(monkeypatch, settings):
    """The real `available`s (the suite's own stand them down), on a models folder of files that only exist, on a
    computer whose torch has a CUDA GPU (art_erase "auto", the default, runs LaMa only there)."""
    monkeypatch.setattr(layout, "available", TRUE_LAYOUT)
    monkeypatch.setattr(artwork, "available", TRUE_ARTWORK)
    monkeypatch.setattr(artwork, "_cuda", True)
    settings.models_dir = settings.state_dir / "models"
    settings.detect_model = settings.art_erase = "auto"  # (the layout model: opt-in, off by default)
    return settings


TRUE_LAYOUT, TRUE_ARTWORK = layout.__dict__["available"], artwork.__dict__["available"]


def _built(settings):
    return Pipeline(settings, ocr=FakeOcr(), translator=None, cache=None)


def test_with_all_the_models_both_are_there_and_nothing_is_loaded(installed):
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    p = _built(installed)
    assert p.layout is not None and p.art_eraser is not None
    assert p.layout._net is None and p.art_eraser._model is None
    p.release_gpu_models()  # nothing to give back


def test_both_models_let_go_before_ollamas_model_loads_and_only_the_models_in_use(installed):
    from taslation.annotations import BookAnnotations
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    p = _built(installed)
    assert p.gpu_releases == [p.layout.release, p.art_eraser.release]
    let_go = []
    p.layout.release, p.art_eraser.release = (lambda: let_go.append("layout")), (lambda: let_go.append("erase"))
    p.gpu_releases[:] = [p.layout.release, p.art_eraser.release]
    p.release_gpu_models()
    assert let_go == ["layout", "erase"]
    book = BookAnnotations(installed.state_dir / "a.json", "a")
    book.settings = {"detect_model": "off"}
    p = _built(installed)
    eraser = p.art_eraser
    p.set_annotations(book)
    assert p.layout is None and p.gpu_releases == [p.art_eraser.release] and p.art_eraser is not eraser


def test_the_layout_model_never_comes_without_the_erase_by_default(installed):
    _install(installed.models_dir, LAYOUT_MODEL)  # no inpainting model at all
    p = _built(installed)
    assert p.art_eraser is None and p.layout is None


def test_without_a_gpu_auto_and_auto_use_neither_model(installed, monkeypatch):
    """The inpainting's "auto" is "off" where torch has no CUDA GPU, and the layout model's "auto" follows it; "lama"
    runs on the CPU and takes the layout model's "auto" with it."""
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    monkeypatch.setattr(artwork, "_cuda", False)
    p = _built(installed)
    assert p.art_eraser is None and p.layout is None
    installed.art_erase = "lama"
    p = _built(installed)
    assert p.art_eraser is not None and p.layout is not None


def test_the_default_layout_setting_loads_no_layout_model_on_a_gpu_machine(installed):
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    defaults = Settings()
    installed.detect_model, installed.art_erase = defaults.detect_model, defaults.art_erase  # "off" and "auto"
    p = _built(installed)
    assert p.art_eraser is not None and p.layout is None and p.gpu_releases == [p.art_eraser.release]


def test_the_layout_model_stays_out_where_transformers_is_missing(installed, monkeypatch):
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    monkeypatch.setattr(layout.importlib.util, "find_spec", lambda name: None)  # no transformers
    installed.detect_model = "on"
    p = _built(installed)
    assert p.layout is None and p.art_eraser is not None


def test_on_asks_for_the_layout_model_whatever_the_erase(installed):
    _install(installed.models_dir, LAYOUT_MODEL)
    installed.detect_model = "on"
    assert _built(installed).layout is not None


def test_off_is_the_classical_detectors_alone(installed):
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    installed.detect_model = "off"
    p = _built(installed)
    assert p.layout is None and p.art_eraser is not None


@pytest.mark.parametrize("mode", ["classic", "inpaint"])
def test_the_older_erases_stay_as_they_are_and_the_old_detection_with_them(installed, mode):
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    installed.erase_mode = mode
    p = _built(installed)
    assert p.layout is None and p.art_eraser is None


def test_a_book_of_its_own_setting_gets_its_own_models(installed):
    from taslation.annotations import BookAnnotations
    from taslation.config import PAGE_MODELS

    _install(installed.models_dir, *PAGE_MODELS)
    p = _built(installed)
    book = BookAnnotations(installed.state_dir / "a.json", "a")
    book.settings = {"erase_mode": "classic"}
    p.set_annotations(book)
    assert p.layout is None and p.art_eraser is None


def test_a_model_that_fails_leaves_the_classical_detectors_at_work(settings):
    model = LayoutModel(settings.state_dir / "no such folder")
    assert model.boxes(_page(), [(0, 0, 600, 400)]) is None and model.failed
    assert model.boxes(_page(), [(0, 0, 600, 400)]) is None  # not tried again
    p = _models(settings, FakeLayout(None))
    classical = [region(60, 60, 150, 250)]
    p._detect_classical = lambda rgb: classical
    assert p._detect(_page()) == classical


def test_an_erase_that_failed_leaves_the_classical_detectors_at_work(settings):
    fake = FakeLayout([box(50, 50, 150, 250)])
    p = _models(settings, fake)
    p.art_eraser.ready = lambda: False
    p._detect_classical = lambda rgb: []
    assert p._detect(_page()) == [] and fake.calls == 0


def test_the_settings_say_what_they_take():
    Settings(detect_model="on", art_erase="lama").validate()
    with pytest.raises(ConfigError):
        Settings(art_erase="aot").validate()
    with pytest.raises(ConfigError):
        Settings(detect_model="maybe").validate()
    with pytest.raises(ConfigError):
        Settings(art_erase="maybe").validate()


def test_a_book_may_choose_them():
    from taslation.annotations import clean_book_settings

    assert clean_book_settings({"detect_model": "off", "art_erase": "off"}) == {"detect_model": "off", "art_erase": "off"}


def test_the_window_says_so_when_pages_go_the_old_way(installed):
    from taslation import health
    from taslation.config import PAGE_MODELS
    from taslation.messages import Message

    assert TRUE_MISSING(installed)
    _install(installed.models_dir, *PAGE_MODELS)
    assert not TRUE_MISSING(installed)
    assert "install.cmd" in Message("layout.classical")
    installed.detect_model, installed.art_erase = "off", "off"
    (installed.models_dir / LAYOUT_MODEL.dirname / "config.json").unlink()
    assert not TRUE_MISSING(installed)
    assert health.__name__


from taslation.health import page_models_missing as TRUE_MISSING  # noqa: E402 - before the suite's fixture stands it down


def test_only_local_files_are_read_and_no_code_runs(monkeypatch, tmp_path):
    """What the loader asks of transformers."""
    asked = {}

    class Fake:
        def eval(self):
            return self

        def to(self, device):
            return self

        def __call__(self, pixel_values):
            import torch

            return SimpleNamespace(logits=torch.full((1, 4, 3), -9.0), pred_boxes=torch.zeros((1, 4, 4)))

    def from_pretrained(path, **options):
        asked.update(options, path=path)
        return Fake()

    import transformers

    fake = SimpleNamespace(RTDetrV2ForObjectDetection=SimpleNamespace(from_pretrained=from_pretrained), utils=transformers.utils)
    monkeypatch.setitem(sys.modules, "transformers", fake)
    model = LayoutModel(tmp_path)
    assert model.detect(np.zeros((64, 64, 3), np.uint8)) == []
    assert asked == {"path": str(tmp_path / LAYOUT_MODEL.dirname), "local_files_only": True, "use_safetensors": True,
                     "trust_remote_code": False}
    model.release()
    assert model._net is None
    model.release()


# ------------------------------------------------------------------ the real model
REAL = Settings()
needs_weights = pytest.mark.skipif(bool(LAYOUT_MODEL.missing(REAL.models_dir)), reason="layout model not downloaded")


@needs_weights
def test_the_real_model_under_the_network_guard(tmp_path):
    """Importing what it needs and running it tries nothing online."""
    code = """
import sys
from taslation import netguard
netguard.install()
import numpy as np
from PIL import Image
from taslation.config import Settings
from taslation.detect.layout import LayoutModel, model_regions
rgb = np.asarray(Image.open(sys.argv[1]).convert("RGB"))
model = LayoutModel(Settings().models_dir)
found = model.boxes(rgb, [(0, 0, rgb.shape[1], rgb.shape[0])])
assert found is not None and not model.failed
regions = model_regions(rgb, found)
model.release()
assert not netguard._state.blocked, netguard._state.blocked
print(len(regions))
"""
    fixture = Path(__file__).parent / "fixtures" / "sample_page.png"
    r = subprocess.run([sys.executable, "-c", code, str(fixture)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert int(r.stdout.split()[-1]) > 0


@needs_weights
@pytest.mark.page_models
def test_the_whole_way_on_the_sample_page(sample_page):
    """The sample page's bubbles, model first: no bubble twice, each with a real mask."""
    s = Settings(detect_model="auto", art_erase="auto")
    p = Pipeline(s, ocr=FakeOcr(), translator=None, cache=None)
    assert p.layout is not None
    rs = p.process(sample_page, translate=False, use_cache=False).regions
    p.release_gpu_models()
    assert any(r.from_model for r in rs)
    assert all(r.after is None for r in rs if r.status == "untranslated")
    boxes = [r.text_box for r in rs if r.status == "untranslated"]
    assert not any(covered(region(*a), [region(*b)]) for i, a in enumerate(boxes) for b in boxes[:i])
