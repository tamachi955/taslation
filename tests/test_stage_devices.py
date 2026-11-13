"""Where each stage of a page runs (`taslation.devices`): detection, OCR, the translator and the erase on "GPU (its
name)" or "CPU" - the layout model and LaMa on the GPU only where torch has CUDA and they are in use, the OCR readers
and the classical detectors on the CPU, Ollama's model where /api/ps says it is (all, none or a part in video memory,
never loaded to find out) - with the seconds a page from the last pages lettered (`StageTimes`, kept in the state
folder when the window closes); Tools > Settings... > System shows it and `taslation doctor` prints it."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from fake_ollama import FakeOllama
from helpers import EN_TEXTS, FakeOcr

from taslation import cli, devices, netguard
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.detect import layout
from taslation.devices import KEEP_PAGES, TIMINGS_FILE, StageDevice, StageTimes, lines, stage_devices
from taslation.i18n import set_language
from taslation.pipeline import Pipeline
from taslation.render import artwork
from taslation.translate import DictTranslator, OllamaTranslator, TranslationError
from taslation.ui.dialogs import settings as dlg
from taslation.ui.dialogs.system_page import SystemPage

GPU = "NVIDIA Test GPU"


class Ps:
    """A translator whose /api/ps says *entry* (an exception: Ollama did not answer)."""

    def __init__(self, entry, model="qwen3.5:4b"):
        self.entry, self.model = entry, model

    def _loaded(self, model):
        assert model == self.model
        if isinstance(self.entry, Exception):
            raise self.entry
        return self.entry


TRUE_AVAILABLE = artwork.__dict__["available"]  # (taken before the suite's fixture stands it down)


@pytest.fixture
def models(monkeypatch):
    """Which page models are installed: the layout model and LaMa, as the test says; whether the erase runs is the
    rule's to say (`artwork.available`, with the *cuda* the test gives)."""
    have = {"layout": False, "lama": False}
    monkeypatch.setattr(layout, "available", lambda models_dir: have["layout"])
    monkeypatch.setattr(artwork, "available", TRUE_AVAILABLE)
    monkeypatch.setattr(artwork, "installed", lambda models_dir: have["lama"])
    return have


def _settings(tmp_path, **kw):
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", **kw)


def _by_stage(rows):
    return {r.stage: r for r in rows}


# ------------------------------------------------------------------ the seconds a page
def test_a_page_s_laps_become_its_stages_and_the_mean_is_per_stage():
    times = StageTimes()
    times.add({"fingerprint": 0.01, "detect": 0.5, "ocr": 1.0, "translate": 3.0, "render": 0.2})
    times.add({"detect": 0.7, "ocr": 2.0, "render": 0.4})  # from the cache: no translation
    times.add({"fingerprint": 0.01})  # nothing of a stage: no page
    assert len(times) == 2
    assert times.per_page() == pytest.approx({"detect": 0.6, "ocr": 1.5, "translate": 3.0, "erase": 0.3})


def test_only_the_last_pages_count():
    times = StageTimes()
    for n in range(KEEP_PAGES + 5):
        times.add({"detect": float(n)})
    assert len(times) == KEEP_PAGES
    assert times.per_page()["detect"] == pytest.approx(sum(range(5, KEEP_PAGES + 5)) / KEEP_PAGES)


def test_the_seconds_are_kept_in_the_state_folder_as_numbers_alone(tmp_path):
    StageTimes().save(tmp_path)  # none: no file
    assert not (tmp_path / TIMINGS_FILE).exists()
    times = StageTimes()
    times.add({"detect": 0.12345, "ocr": 1.0, "translate": 2.0, "render": 0.5})
    times.save(tmp_path)
    data = json.loads((tmp_path / TIMINGS_FILE).read_text(encoding="utf-8"))
    assert data == {"pages": [{"detect": 0.123, "ocr": 1.0, "translate": 2.0, "erase": 0.5}]}
    again = StageTimes.load(tmp_path)
    assert len(again) == 1 and again.per_page()["erase"] == 0.5


def test_a_damaged_or_missing_file_is_no_seconds(tmp_path):
    assert len(StageTimes.load(tmp_path)) == 0
    (tmp_path / TIMINGS_FILE).write_text("{not json", encoding="utf-8")
    assert len(StageTimes.load(tmp_path)) == 0
    (tmp_path / TIMINGS_FILE).write_text('{"pages": [1, {"ocr": "x"}, {"ocr": -1}, {"ocr": 2}]}', encoding="utf-8")
    assert StageTimes.load(tmp_path).per_page() == {"ocr": 2.0}


def test_the_pipeline_times_each_page_it_letters(tmp_path, sample_page):
    settings = Settings(state_dir=tmp_path / "state")
    cache = CacheStore(settings.cache_dir).open("Timed Book", "fake")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    p.process(sample_page)
    assert len(p.stage_times) == 1
    assert set(p.stage_times.per_page()) == {"detect", "ocr", "translate", "erase"}
    devices.save_times(p, settings.state_dir)
    assert len(StageTimes.load(settings.state_dir)) == 1
    devices.save_times(SimpleNamespace(), settings.state_dir)  # a window without a pipeline: nothing to keep
    devices.save_times(None, settings.state_dir)


def test_the_list_s_seconds():
    assert devices.seconds_text(None) == "-"
    assert devices.seconds_text(0.43) == "0.4 s"
    assert devices.seconds_text(12.4) == "12 s"


# ------------------------------------------------------------------ the devices
def test_without_cuda_everything_is_on_the_cpu(tmp_path, models):
    models.update(layout=True, lama=True)
    settings = _settings(tmp_path, detect_model="on", art_erase="lama")
    rows = _by_stage(stage_devices(settings, Ps({"size": 10, "size_vram": 0}), cuda=False))
    assert [r.stage for r in stage_devices(_settings(tmp_path), Ps(None), cuda=False)] == list(devices.STAGES)
    assert {s: r.device for s, r in rows.items()} == {"detect": "cpu", "ocr": "cpu", "translate": "cpu", "erase": "cpu"}
    assert rows["detect"].what == "The layout model and the classical detectors"
    assert rows["erase"].what == "LaMa on the drawing, the paper fill in the bubbles"  # "lama": on the CPU too
    assert rows["detect"].where() == "CPU"


def test_without_cuda_the_default_inpainting_is_the_paper_fill_and_auto_takes_no_layout_model(tmp_path, models):
    models.update(layout=True, lama=True)
    rows = _by_stage(stage_devices(_settings(tmp_path), Ps(None), cuda=False))  # the defaults: art_erase "auto"
    assert rows["erase"].device == "cpu" and rows["erase"].what == "The paper fill"
    auto = _by_stage(stage_devices(_settings(tmp_path, detect_model="auto"), Ps(None), cuda=False))
    assert auto["detect"].what == "The classical detectors" and auto["erase"].what == "The paper fill"
    with_gpu = _by_stage(stage_devices(_settings(tmp_path), Ps(None), cuda=True, gpu=GPU))
    assert with_gpu["erase"].where() == f"GPU ({GPU})" and with_gpu["detect"].what == "The classical detectors"


def test_the_system_page_and_the_pipeline_ask_torch_the_same_question(tmp_path, models, monkeypatch):
    """Without *cuda*, the stages take the rule's answer (`artwork.has_cuda`, asked once a session)."""
    models.update(lama=True)
    monkeypatch.setattr(artwork, "_cuda", None)
    asked = []
    monkeypatch.setattr(devices, "cuda_available", lambda: asked.append(1) or False)
    rows = _by_stage(stage_devices(_settings(tmp_path), Ps(None), gpu=""))
    stage_devices(_settings(tmp_path), Ps(None), gpu="")
    assert rows["erase"].what == "The paper fill" and len(asked) == 1


def test_with_cuda_the_page_models_in_use_are_on_the_gpu(tmp_path, models):
    models.update(layout=True, lama=True)
    rows = _by_stage(stage_devices(_settings(tmp_path, detect_model="on", art_erase="auto"),
                                   Ps({"size": 100, "size_vram": 100}), cuda=True, gpu=GPU))
    assert rows["detect"].where() == f"GPU ({GPU})"
    assert rows["erase"].where() == f"GPU ({GPU})"
    assert rows["translate"].where() == f"GPU ({GPU})" and rows["translate"].what == "Ollama: qwen3.5:4b"
    assert rows["ocr"].where() == "CPU" and rows["ocr"].what == "The OCR readers"


def test_models_not_in_use_or_not_installed_leave_it_to_the_cpu(tmp_path, models):
    rows = _by_stage(stage_devices(_settings(tmp_path, detect_model="on", art_erase="auto"), Ps(None), cuda=True,
                                   gpu=GPU))
    assert rows["detect"].device == "cpu" and rows["detect"].what == "The classical detectors"
    assert rows["erase"].device == "cpu" and rows["erase"].what == "The paper fill"
    models.update(layout=True, lama=True)
    off = _by_stage(stage_devices(_settings(tmp_path, detect_model="off", art_erase="off"), Ps(None), cuda=True,
                                  gpu=GPU))
    assert off["detect"].device == "cpu" and off["erase"].device == "cpu"
    auto = _by_stage(stage_devices(_settings(tmp_path, detect_model="auto", art_erase="auto"), Ps(None), cuda=True,
                                   gpu=""))
    assert auto["detect"].device == "gpu" and auto["detect"].where() == "GPU"  # with LaMa, the layout model too
    classic = _by_stage(stage_devices(_settings(tmp_path, art_erase="auto", erase_mode="classic"), Ps(None), cuda=True,
                                      gpu=GPU))
    assert classic["erase"].device == "cpu"  # the classic erase has no LaMa


@pytest.mark.parametrize("entry, device, where", [
    ({"size": 100, "size_vram": 100}, "gpu", f"GPU ({GPU})"),
    ({"size": 100, "size_vram": 0}, "cpu", "CPU"),
    ({"size": 100, "size_vram": 60}, "both", "GPU and CPU (60 % on the GPU)"),
    ({"size": 100}, "", "Ollama does not say"),
    (None, "", "Not loaded now: Ollama loads it for the first line"),
    (TranslationError("down"), "", "Ollama is not answering"),
])
def test_ollama_s_model_is_where_api_ps_says(tmp_path, models, entry, device, where):
    row = _by_stage(stage_devices(_settings(tmp_path), Ps(entry), cuda=True, gpu=GPU))["translate"]
    assert (row.device, row.where()) == (device, where)


def test_a_translator_that_is_not_ollama_s_asks_for_the_settings_model(tmp_path, models):
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            fake.tracks_loads = True
            fake.loaded.add("qwen3.5:4b")
            fake.share = 0.5
            settings = _settings(tmp_path, ollama_url=fake.url, ollama_model="qwen3.5:4b")
            row = _by_stage(stage_devices(settings, DictTranslator(EN_TEXTS), cuda=True, gpu=GPU))["translate"]
            assert row.device == "both" and row.share == pytest.approx(0.5)
            fake.loaded.clear()
            row = _by_stage(stage_devices(settings, OllamaTranslator(fake.url, "qwen3.5:4b"), cuda=False))["translate"]
            assert row.why.startswith("Not loaded now") and fake.loads == 0  # asking loads nothing
            assert not fake.requests  # nor sends a request that could
        finally:
            netguard.uninstall()


def test_the_doctor_s_lines(tmp_path, models):
    settings = _settings(tmp_path)
    out = lines(settings, StageTimes(), Ps({"size": 1, "size_vram": 1}), cuda=False)
    assert out[0] == "  Finding the text: CPU (The classical detectors); not timed yet"
    assert out[2] == "  Translating: GPU (Ollama: qwen3.5:4b); not timed yet"  # no name known without CUDA in torch
    assert out[-1].startswith("  (seconds a page: none yet")
    times = StageTimes([{"detect": 0.25, "ocr": 1.5, "translate": 4.0, "erase": 0.5}])
    out = lines(settings, times, Ps(None), cuda=False)
    assert out[1] == "  Reading the text (OCR): CPU (The OCR readers); 1.5 s a page"
    assert out[2].startswith("  Translating: Not loaded now")
    assert out[-1] == "  (seconds a page: the mean of the last 1 page(s) lettered in the window)"


def test_doctor_prints_where_each_stage_runs(tmp_path, monkeypatch, capsys):
    got = []
    monkeypatch.setattr(devices, "lines", lambda settings: got.append(settings) or ["  Detection: CPU (x); not timed yet"])
    settings = _settings(tmp_path)
    cli.cmd_doctor(argparse.Namespace(), settings)
    out = capsys.readouterr().out
    assert "Where each stage runs:\n  Detection: CPU (x); not timed yet\n" in out and got == [settings]
    assert out.index("Where each stage runs:") < out.index("Result:")


def test_the_gpu_name_needs_no_cuda_context(monkeypatch):
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda: False,
                                                      get_device_name=lambda i: pytest.fail("CUDA asked")))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(devices, "nvml_name", lambda: "From NVML")
    assert devices.gpu_name() == "From NVML"
    fake_torch.cuda.is_initialized = lambda: True
    fake_torch.cuda.get_device_name = lambda i: "From torch"
    assert devices.gpu_name() == "From torch"


def test_the_stage_names_are_in_the_window_s_language(tmp_path, models):
    set_language("ja")
    try:
        assert StageDevice("ocr", "cpu", "x").where() == "CPU"
        assert StageDevice("x", "both", "x", share=0.25).where() == "GPU と CPU（25 % が GPU）"
        assert lines(_settings(tmp_path), StageTimes(), Ps(None), cuda=False)[0].startswith("  文字の検出: CPU (従来の検出)")
    finally:
        set_language("en")


# ------------------------------------------------------------------ Tools > Settings... > System
def _rows():
    return [StageDevice("detect", "gpu", "The layout model and the classical detectors", GPU),
            StageDevice("ocr", "cpu", "The OCR readers"),
            StageDevice("translate", "", "Ollama: qwen3.5:4b", why="Not loaded now: Ollama loads it for the first line"),
            StageDevice("erase", "cpu", "The paper fill")]


def test_the_system_page_lists_the_stages_with_the_window_s_seconds(hidden_root, tmp_path):
    times = StageTimes([{"detect": 0.5, "ocr": 2.0, "erase": 0.25}])
    page = SystemPage(hidden_root, _settings(tmp_path), 400, pipeline=lambda: SimpleNamespace(stage_times=times),
                      look=_rows)
    assert not page.shown_rows and not page._cells  # nothing looked at before it is shown
    page.refresh(wait=True)
    assert page.shown_rows == [
        ("Finding the text", f"GPU ({GPU})", "The layout model and the classical detectors", "0.5 s"),
        ("Reading the text (OCR)", "CPU", "The OCR readers", "2.0 s"),
        ("Translating", "Not loaded now: Ollama loads it for the first line", "Ollama: qwen3.5:4b", "-"),
        ("Erasing and lettering", "CPU", "The paper fill", "0.2 s")]
    note = page.note_var.get().replace("\n", " ")
    assert "the mean of the last 1 pages" in note and "NVIDIA" in note
    assert str(page.again_btn.cget("state")) == "normal" and page.state_var.get() == ""


def test_long_names_take_another_line_instead_of_running_off_the_page(hidden_root, tmp_path):
    long_gpu = "NVIDIA GeForce RTX 4090 Laptop GPU with a long name"
    rows = [StageDevice("detect", "gpu", "The layout model and the classical detectors", long_gpu),
            StageDevice("ocr", "cpu", "The OCR readers"),
            StageDevice("translate", "both", "Ollama: a-reader-s-own-model-with-a-very-long-name:latest", long_gpu, 0.4),
            StageDevice("erase", "cpu", "The paper fill")]
    page = SystemPage(hidden_root, _settings(tmp_path), 360, look=lambda: rows)
    page.refresh(wait=True)
    page.update_idletasks()
    assert page.table.winfo_reqwidth() <= 360
    texts = [w.cget("text") for cell in page._cells for w in (cell.winfo_children() or [cell])]
    assert any(len(str(text).splitlines()) > 1 and "NVIDIA" in str(text) for text in texts)


def test_the_seconds_column_takes_room_for_its_heading_from_the_middle_one():
    from taslation.ui.dialogs.system_page import GAP, column_widths

    plain = column_widths(400, 10)
    assert sum(plain) == 400 - 3 * GAP
    wide = column_widths(400, 110)
    assert wide[0] == plain[0] and wide[2] > plain[2] and sum(wide) == sum(plain)
    assert column_widths(400, 1000)[2] == int(400 * 0.32)  # never more than a third or so of the page


def test_the_system_page_falls_back_to_the_kept_seconds_and_says_a_failure(hidden_root, tmp_path):
    settings = _settings(tmp_path)
    StageTimes([{"ocr": 3.0}]).save(settings.state_dir)
    page = SystemPage(hidden_root, settings, 400, pipeline=lambda: None, look=_rows)
    page.refresh(wait=True)
    assert page.shown_rows[1][3] == "3.0 s"

    def broken():
        raise OSError("no")

    page.look = broken
    page.refresh(wait=True)
    assert not page.shown_rows and not page._cells and page.state_var.get() == "Could not look: OSError"
    (settings.state_dir / TIMINGS_FILE).unlink()
    page.look = _rows
    page.refresh(wait=True)
    assert page.note_var.get().startswith("Seconds a page: none yet")


def test_the_system_page_looks_on_a_thread_once_shown(hidden_root, tmp_path):
    seen = []

    def look():
        seen.append(threading.current_thread() is threading.main_thread())
        return _rows()

    page = SystemPage(hidden_root, _settings(tmp_path), 400, look=look)
    page.shown()
    assert page.state_var.get() == "Looking..." and str(page.again_btn.cget("state")) == "disabled"
    page._thread.join(5)
    end = time.monotonic() + 5
    while not page.shown_rows and time.monotonic() < end:  # the page looks every POLL_MS
        hidden_root.update()
        time.sleep(0.02)
    assert seen == [False] and len(page.shown_rows) == 4 and len(page._cells) == 12
    page.shown()  # shown again: no second look
    assert seen == [False]


def test_the_settings_dialog_has_a_system_page_that_looks_when_chosen(hidden_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    looked = []
    monkeypatch.setattr(devices, "stage_devices", lambda settings, translator=None: looked.append(translator) or _rows())
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    window_translator = object()
    d = dlg.SettingsDialog(hidden_root, settings, pipeline=lambda: SimpleNamespace(translator=window_translator,
                                                                                   stage_times=StageTimes()))
    assert [d.pages.tab(t, "text") for t in d.pages.tabs()] == ["General", "Shortcuts", "System"]
    assert not d.system.looked
    d.pages.select(d.system)
    hidden_root.update()
    assert d.system.looked
    d.system._thread.join(5)
    assert looked == [window_translator]  # the window's own translator is asked
