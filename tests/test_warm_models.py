"""The layout model and LaMa loaded ahead of the first page (`Pipeline.warm_page_models`)."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from taslation.config import LAMA_MODEL, LAYOUT_MODEL, Settings
from taslation.detect.layout import LayoutModel
from taslation.pipeline import Pipeline
from taslation.render import artwork


class Model:
    """A stand-in for either model: `warm` counted, held up by *gate* when given."""

    def __init__(self, gate: threading.Event | None = None, ready: bool = True):
        self.warmed = 0
        self.released = 0
        self.failed = False
        self.gate = gate
        self._ready = ready
        self.started = threading.Event()

    def ready(self):
        return self._ready

    def warm(self):
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        self.warmed += 1
        return True

    def release(self):
        self.released += 1


def stand_ins(settings, detect="auto", layout=None, eraser=None):
    pipeline = Pipeline(settings)
    pipeline.settings.detect_model = detect
    pipeline.layout, pipeline.art_eraser = layout, eraser
    pipeline.gpu_releases[:] = [m.release for m in (layout, eraser) if m is not None]
    return pipeline


def test_both_models_are_warmed_on_their_own_thread(settings):
    layout, eraser = Model(), Model()
    pipeline = stand_ins(settings, layout=layout, eraser=eraser)
    thread = pipeline.warm_page_models()
    assert thread is not None and thread is not threading.current_thread()
    thread.join(5)
    assert (layout.warmed, eraser.warmed) == (1, 1) and (layout.released, eraser.released) == (0, 0)


def test_nothing_to_warm(settings):
    assert stand_ins(settings).warm_page_models() is None
    # "auto" runs the layout model only with the inpainting: without LaMa there is nothing to load ahead
    layout = Model()
    assert stand_ins(settings, layout=layout).warm_page_models() is None
    assert stand_ins(settings, layout=layout, eraser=Model(ready=False)).warm_page_models() is None
    failed = Model()
    failed.failed = True
    assert stand_ins(settings, eraser=failed).warm_page_models() is None
    assert layout.warmed == 0


def test_the_layout_model_alone_when_it_is_on(settings):
    layout = Model()
    stand_ins(settings, detect="on", layout=layout).warm_page_models().join(5)
    assert layout.warmed == 1


def test_one_warm_up_at_a_time(settings):
    gate = threading.Event()
    layout, eraser = Model(gate), Model()
    pipeline = stand_ins(settings, layout=layout, eraser=eraser)
    thread = pipeline.warm_page_models()
    assert pipeline.warm_page_models() is None  # (it is warming)
    gate.set()
    thread.join(5)
    assert layout.warmed == 1
    pipeline.warm_page_models().join(5)  # (once over, it may be asked again: what is loaded loads at once)
    assert layout.warmed == 2


def test_a_release_before_ollamas_load_ends_the_warm_up(settings):
    gate = threading.Event()
    layout, eraser = Model(gate), Model()
    pipeline = stand_ins(settings, layout=layout, eraser=eraser)
    thread = pipeline.warm_page_models()
    assert layout.started.wait(5)
    pipeline.release_gpu_models()  # Ollama's model is about to load
    gate.set()
    thread.join(5)
    assert layout.warmed == 1 and eraser.warmed == 0  # LaMa loads on first use, after Ollama's model


def test_a_release_before_the_warm_up_began_leaves_everything_to_first_use(settings):
    layout, eraser = Model(), Model()
    pipeline = stand_ins(settings, layout=layout, eraser=eraser)
    real_start = threading.Thread.start

    def start_late(thread):  # the release comes between the call and the thread's first look
        pipeline.release_gpu_models()
        real_start(thread)
    threading.Thread.start = start_late
    try:
        thread = pipeline.warm_page_models()
    finally:
        threading.Thread.start = real_start
    thread.join(5)
    assert layout.warmed == 0 and eraser.warmed == 0


def test_a_model_the_settings_replaced_meanwhile_is_let_go(settings):
    gate = threading.Event()
    layout, eraser = Model(gate), Model()
    pipeline = stand_ins(settings, layout=layout, eraser=eraser)
    thread = pipeline.warm_page_models()
    pipeline.layout = Model()  # (another model made for other settings)
    gate.set()
    thread.join(5)
    assert layout.warmed == 1 and layout.released == 1 and eraser.released == 0


def test_the_warm_up_runs_below_normal(settings):
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows thread priorities")
    from taslation import batch

    seen = []

    class Seen(Model):
        def warm(self):
            seen.append(batch.thread_priority())
            return True

    stand_ins(settings, layout=Seen(), eraser=Seen()).warm_page_models().join(5)
    assert seen == [-1, -1]


def test_the_models_warm_on_a_blank_input(tmp_path, monkeypatch):
    layout = LayoutModel(tmp_path)
    seen = []
    monkeypatch.setattr(layout, "detect", lambda rgb: seen.append(rgb.shape) or [])
    assert layout.warm() and seen and seen[0][2] == 3
    monkeypatch.setattr(layout, "detect", lambda rgb: (_ for _ in ()).throw(OSError("no file")))
    assert not layout.warm() and not layout.failed  # (the first page tries again, and says what is wrong)

    eraser = artwork.ArtEraser(tmp_path)
    monkeypatch.setattr(eraser, "ready", lambda: True)
    holes = []
    monkeypatch.setattr(eraser, "_fill", lambda part, hole: holes.append(hole.sum()) or part)
    assert eraser.warm() and holes and holes[0] > 0
    eraser.failed = True
    assert not eraser.warm() and len(holes) == 1


REAL = Settings()


@pytest.mark.page_models
@pytest.mark.skipif(bool(LAYOUT_MODEL.missing(REAL.models_dir)) or bool(LAMA_MODEL.missing(REAL.models_dir)),
                    reason="layout model or LaMa not set up")
def test_the_real_models_are_loaded_ahead(tmp_path):
    # (art_erase "lama", not "auto": both models on any computer, "auto" being "only where torch has a CUDA GPU")
    s = Settings(state_dir=tmp_path, models_dir=REAL.models_dir, detect_model="auto", art_erase="lama")
    s.validate()
    pipeline = Pipeline(s)
    assert pipeline.layout is not None and pipeline.art_eraser is not None
    pipeline.warm_page_models().join(120)
    try:
        assert pipeline.layout._net is not None and pipeline.art_eraser._model is not None
        found = pipeline.layout.detect(np.full((200, 140, 3), 255, np.uint8))
        assert isinstance(found, list)
    finally:
        pipeline.release_gpu_models()
    assert pipeline.layout._net is None and pipeline.art_eraser._model is None
