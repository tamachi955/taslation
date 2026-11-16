"""Where the OCR readers run (`taslation.ocr.place`): on the GPU when it has room for them at TASlation's peak - the
translation model whole in video memory, the page models in use, this process's context, what other programs hold, a
margin - else on the CPU; the setting ``ocr_runs_on``; a decision made when the readers load and again once the GPU
memory was let go or a setting changed; a GPU that fails moves them to the CPU for the session, the crop at hand read
there; the System page and ``taslation doctor`` say where they are and why. Everything here uses stand-ins: no GPU,
no model, no Ollama but the fake one."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import requires_ocr
from fake_ollama import FakeOllama

from taslation import devices, netguard
from taslation.config import ConfigError, Settings
from taslation.devices import stage_devices
from taslation.ocr import place, readers
from taslation.ocr.place import (CHARSPOT_MIB, CONTEXT_MIB, KNOWN_TRANSLATORS, LAMA_MIB, MARGIN_MIB, MIN_TOTAL_MIB,
                                 NAR_MIB, DeviceModels, GpuFacts, Placement, decide, judge, room_left)

OCR = CHARSPOT_MIB + NAR_MIB
PLAMO = KNOWN_TRANSLATORS[("taslation-plamo3-translate-2b", 8192)]
QWEN = KNOWN_TRANSLATORS[("qwen3.5:4b", 16384)]
GPU = "NVIDIA Test GPU"


@pytest.fixture(autouse=True)
def nothing_learnt():
    place._learnt.clear()
    yield
    place._learnt.clear()


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", **kw)


# ------------------------------------------------------------------ the rule
def test_room_is_what_is_left_at_the_peak_after_other_programs():
    facts = GpuFacts(total=6144, used=1325, translator=PLAMO, lama=True)
    assert room_left(facts, OCR) == 6144 - 1325 - (CONTEXT_MIB + PLAMO + LAMA_MIB + OCR)


def test_the_measured_card_has_room_beside_plamo_and_lama():
    """The machine the numbers were measured on: a 6 GB card with 1.3 GB held by other programs (NVML's used)."""
    decided = judge(GpuFacts(total=6144, used=1325, translator=PLAMO, lama=True), OCR)
    assert decided.device == "gpu" and decided.why == place.ROOM and decided.room >= MARGIN_MIB


def test_a_4_gb_card_is_never_shared_with_the_translator():
    for used in (0, 300, 1000):
        for lama in (False, True):
            decided = judge(GpuFacts(total=4096, used=used, translator=PLAMO, lama=lama), OCR)
            assert (decided.device, decided.why) == ("cpu", place.NO_ROOM)
    assert judge(GpuFacts(total=MIN_TOTAL_MIB - 1, used=0, translator=0), CHARSPOT_MIB).device == "cpu"


def test_the_larger_translator_leaves_no_room_on_6_gb():
    decided = judge(GpuFacts(total=6144, used=1325, translator=QWEN, lama=True), OCR)
    assert (decided.device, decided.why) == ("cpu", place.NO_ROOM) and decided.room < MARGIN_MIB


def test_other_programs_memory_counts_against_the_room():
    free = judge(GpuFacts(total=6144, used=1325, translator=PLAMO, lama=True), OCR)
    busy = judge(GpuFacts(total=6144, used=1325 + free.room, translator=PLAMO, lama=True), OCR)
    assert busy.device == "cpu" and busy.room == 0


def test_what_is_taslation_s_own_is_not_counted_twice():
    """The translator loaded, and LaMa and this process's context in memory: the same room as before they were."""
    before = room_left(GpuFacts(total=6144, used=1325, translator=PLAMO, lama=True), OCR)
    own = CONTEXT_MIB + 600
    after = room_left(GpuFacts(total=6144, used=1325 + PLAMO + own, own=own, translator=PLAMO, translator_now=PLAMO,
                               lama=True), OCR)
    assert after == before


def test_an_unknown_translator_or_card_keeps_them_on_the_cpu():
    assert judge(GpuFacts(total=12288, used=0, translator=None), OCR) == Placement("cpu", place.UNKNOWN)
    assert judge(None, OCR) == Placement("cpu", place.UNKNOWN)


def test_a_translator_kept_off_the_gpu_needs_no_room_there(tmp_path):
    need, now = place.translator_need(_settings(tmp_path, ollama_num_gpu="0"))
    assert (need, now) == (0, 0)


# ------------------------------------------------------------------ the setting
def test_the_setting_and_its_values(tmp_path):
    assert Settings().ocr_runs_on == "auto"
    for value in place.SETTING_VALUES:
        _settings(tmp_path, ocr_runs_on=value).validate()
    with pytest.raises(ConfigError):
        _settings(tmp_path, ocr_runs_on="cuda").validate()


def test_an_old_file_with_the_old_ocr_device_neither_breaks_nor_forces_the_gpu(tmp_path):
    path = tmp_path / "taslation.toml"
    for old in ("cuda", "auto", "cpu", "gpu"):
        path.write_text(f'ocr_device = "{old}"\n', encoding="utf-8")
        s = Settings.from_toml(path)
        s.validate()
        assert s.ocr_runs_on == "auto" and not s.ignored_keys  # (dropped quietly, as before)


def test_the_example_file_has_the_setting():
    example = Settings.from_toml(Path(__file__).resolve().parent.parent / "taslation.toml.example")
    assert example.ocr_runs_on == "auto"


def test_cpu_is_the_cpu_without_asking_anything(tmp_path):
    asked = []
    decided = decide(_settings(tmp_path, ocr_runs_on="cpu"), OCR, cuda=True, facts=lambda s: asked.append(s))
    assert decided == Placement("cpu", place.SET) and not asked


def test_without_cuda_nothing_is_measured(tmp_path):
    asked = []
    for value in place.SETTING_VALUES:
        decided = decide(_settings(tmp_path, ocr_runs_on=value), OCR, cuda=False, facts=lambda s: asked.append(s))
        assert decided.device == "cpu"
    assert not asked


def test_gpu_is_the_gpu_wherever_there_is_cuda(tmp_path):
    decided = decide(_settings(tmp_path, ocr_runs_on="gpu"), OCR, cuda=True, facts=lambda s: pytest.fail("measured"))
    assert decided == Placement("gpu", place.SET)


def test_auto_judges_the_facts_of_the_moment(tmp_path):
    s = _settings(tmp_path)
    room = decide(s, OCR, cuda=True, facts=lambda _s: GpuFacts(total=6144, used=1325, translator=PLAMO))
    tight = decide(s, OCR, cuda=True, facts=lambda _s: GpuFacts(total=6144, used=4000, translator=PLAMO))
    assert room.device == "gpu" and tight.device == "cpu"


def test_a_failure_this_session_is_the_cpu_whatever_the_setting(tmp_path):
    decided = decide(_settings(tmp_path, ocr_runs_on="gpu"), OCR, "OutOfMemoryError", cuda=True)
    assert decided == Placement("cpu", place.FAILED, error="OutOfMemoryError")


def test_the_suite_never_measures_this_machine(tmp_path):
    assert decide(_settings(tmp_path), OCR, cuda=True) == Placement("cpu", place.UNKNOWN)


# ------------------------------------------------------------------ the facts
@pytest.fixture
def ollama():
    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            fake.tracks_loads = True
            yield fake
        finally:
            netguard.uninstall()


def test_the_translator_s_need_while_loaded_before_and_after(tmp_path, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url)
    assert place.translator_need(s) == (PLAMO, 0)  # not loaded: as measured
    name = "taslation-plamo3-translate-2b"
    ollama.loaded.add(name)
    size = 3_000_000_000 // place.MiB  # (the fake's size)
    assert place.translator_need(s) == (size, size)  # loaded: what /api/ps says, all of it on the GPU
    ollama.loaded.clear()
    need, now = place.translator_need(s)
    assert now == 0 and need == round(size * place.RUNNER_SHARE)  # learnt, with the runner's own share
    assert not ollama.loads  # nothing was loaded to find out


def test_a_model_of_the_reader_s_own_is_not_known_until_seen_loaded(tmp_path, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="someones-model:7b")
    assert place.translator_need(s) == (None, 0)
    ollama.loaded.add("someones-model:7b")
    ollama.share = 0.5  # (split by the server: the need is all of it)
    size = 3_000_000_000 // place.MiB
    assert place.translator_need(s) == (size, int(3_000_000_000 * 0.5) // place.MiB)


def test_layers_set_by_hand_need_what_they_hold(tmp_path, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url, ollama_num_gpu="10")
    assert place.translator_need(s) == (None, 0)  # not known before it loads
    ollama.loaded.add("taslation-plamo3-translate-2b")
    ollama.share = 0.4
    now = int(3_000_000_000 * 0.4) // place.MiB
    assert place.translator_need(s) == (now, now)


def test_ollama_down_is_a_model_not_loaded(tmp_path):
    s = _settings(tmp_path, ollama_url="http://127.0.0.1:9")
    netguard.install(allowed_ports={9}, audit_hook=False)
    try:
        assert place.translator_need(s) == (PLAMO, 0)
    finally:
        netguard.uninstall()


def test_the_card_s_memory_comes_from_nvml(monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 1325))
    assert place.card_memory() == (6144, 1325)


def test_page_models_follow_the_pipeline_s_rules(tmp_path, monkeypatch):
    from taslation.detect import layout
    from taslation.render import artwork

    monkeypatch.setattr(artwork, "installed", lambda models_dir: True)
    monkeypatch.setattr(artwork, "available", lambda models_dir, setting="auto", cuda=None: setting != "off")
    monkeypatch.setattr(layout, "available", lambda models_dir: True)
    assert place.page_models_on_gpu(_settings(tmp_path)) == (True, False)
    assert place.page_models_on_gpu(_settings(tmp_path, detect_model="auto")) == (True, True)
    assert place.page_models_on_gpu(_settings(tmp_path, art_erase="off", detect_model="auto")) == (False, False)
    assert place.page_models_on_gpu(_settings(tmp_path, erase_mode="classic", detect_model="on")) == (False, True)


# ------------------------------------------------------------------ a reader's networks on a device
class FakeModels(DeviceModels):
    """A reader with networks that are names: "net@cpu", and a copy "net@<device>" that fails while *broken*."""

    def __init__(self, name="fake"):
        super().__init__()
        self.name = name
        self._cpu_models = ("net@cpu",)
        self.broken = False
        self.copy_fails = False
        self.reads: list[str] = []

    def _copy_to(self, device):
        if self.copy_fails:
            raise RuntimeError("CUDA out of memory")
        return (f"net@{device}",)

    def read(self, value="x"):
        def on(device, models):
            self.reads.append(models[0])
            if device != "cpu" and self.broken:
                raise MemoryError_("CUDA out of memory. Tried to allocate")
            return f"{value} read with {models[0]}"

        return self.run(on)


class MemoryError_(RuntimeError):  # (torch.cuda.OutOfMemoryError is a RuntimeError)
    pass


@pytest.fixture
def given_back(monkeypatch):
    calls = []
    monkeypatch.setattr(place, "give_back", lambda: calls.append(1))
    return calls


def test_a_reader_reads_on_the_copy_in_force(given_back):
    m = FakeModels()
    assert m.device == "cpu" and m.read() == "x read with net@cpu"
    assert m.to("cuda") and m.device == "cuda" and m.read() == "x read with net@cuda"
    assert m.to("cpu") and m.device == "cpu" and m.read() == "x read with net@cpu" and given_back == [1]


def test_out_of_memory_reads_that_crop_on_the_cpu_and_stays_there(given_back):
    told = []
    m = FakeModels("nar")
    m.on_gpu_failure = lambda reader, why: told.append((reader, why))
    m.to("cuda")
    m.broken = True
    assert m.read("crop") == "crop read with net@cpu"  # the page is never failed
    assert m.reads == ["net@cuda", "net@cpu"] and m.device == "cpu"
    assert m.gpu_failed == "MemoryError_" and told == [("nar", "MemoryError_")]
    assert not m.to("cuda") and m.device == "cpu"  # for the rest of the session


def test_while_the_translator_computes_they_read_on_the_cpu_and_keep_the_gpu_s_copy(given_back):
    m = FakeModels()
    m.to("cuda")
    with place.translating():
        with place.translating():  # (two requests at once)
            assert m.read() == "x read with net@cpu"
        assert m.read() == "x read with net@cpu" and m.device == "cuda"
    assert m.read() == "x read with net@cuda" and not given_back and place._translating == 0
    with pytest.raises(ValueError):
        with place.translating():
            raise ValueError("a request that failed")
    assert place._translating == 0 and m.read() == "x read with net@cuda"


def test_a_copy_that_cannot_be_made_leaves_it_on_the_cpu(given_back):
    told = []
    m = FakeModels()
    m.on_gpu_failure = lambda reader, why: told.append(why)
    m.copy_fails = True
    assert not m.to("cuda") and m.device == "cpu" and m.gpu_failed == "RuntimeError" and told == ["RuntimeError"]


def test_a_copy_dropped_during_a_read_gives_its_memory_back_once_the_read_is_done(given_back):
    m = FakeModels()
    m.to("cuda")
    inside, go = threading.Event(), threading.Event()

    def slow(device, models):
        inside.set()
        go.wait(5)
        return models[0]

    out = []
    reader = threading.Thread(target=lambda: out.append(m.run(slow)))
    reader.start()
    inside.wait(5)
    m.to("cpu")
    assert m.device == "cpu" and given_back == []  # (the read still holds the copy)
    go.set()
    reader.join(5)
    assert out == ["net@cuda"] and given_back == [1]


def test_a_cpu_error_is_not_retried(given_back):
    m = FakeModels()

    def wrong(device, models):
        raise RuntimeError("a shape that does not fit")

    with pytest.raises(RuntimeError):
        m.run(wrong)
    assert not m.gpu_failed


# ------------------------------------------------------------------ the readers
class FakeEngine(FakeModels):
    def __init__(self, model_dir, threads=0):
        super().__init__(Path(model_dir).name)

    def read_chars(self, image):
        return readers.CharspotReading(self.read(), score=1.0)


@pytest.fixture
def fake_readers(monkeypatch, given_back):
    """`Readers` over stand-in engines (all three installed) and a stand-in rule that records what it was asked."""
    from taslation.ocr import cpt, nar

    monkeypatch.setattr(readers, "CharspotEngine", FakeEngine)
    monkeypatch.setattr(readers, "missing_readers", lambda models_dir: [])
    monkeypatch.setattr(nar, "NarEngine", FakeEngine)
    monkeypatch.setattr(cpt, "CptEngine", FakeEngine)
    rule = SimpleNamespace(answer=Placement("gpu", place.ROOM, 1500), asked=[])

    def decided(settings, ocr, failed="", cuda=None, facts=None):
        rule.asked.append((settings.ocr_runs_on, ocr, failed))
        return Placement("cpu", place.FAILED, error=failed) if failed else rule.answer

    monkeypatch.setattr(place, "decide", decided)
    return rule


def test_the_decision_is_made_where_the_readers_load(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    assert fake_readers.asked == [("auto", OCR, "")]
    assert ocr.placement == Placement("gpu", place.ROOM, 1500)
    assert ocr.charspot.device == "cuda" and ocr._nar.device == "cuda" and ocr._cpt.device == "cpu"  # CPT stays
    assert ocr.charspot.read() == "x read with net@cuda"  # (the window's first reads warm the GPU's copies)


def test_readers_without_settings_stay_on_the_cpu_and_decide_nothing(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0)
    ocr.read_chars(None)
    assert not fake_readers.asked and ocr.charspot.device == "cpu" and ocr.placement.why == place.NOT_ASKED


def test_readers_loaded_first_decide_once_they_are_given_the_settings(tmp_path, fake_readers):
    """(`place_with`: the window's and the command line's load, which a test's stand-in for the readers goes through
    untouched.)"""
    ocr = readers.Readers(tmp_path, 0)
    assert readers.place_with(ocr, _settings(tmp_path)) is ocr
    assert fake_readers.asked == [("auto", OCR, "")] and ocr.charspot.device == "cuda" and ocr._nar.device == "cuda"
    stand_in = SimpleNamespace(missing=[])
    assert readers.place_with(stand_in, _settings(tmp_path)) is stand_in and len(fake_readers.asked) == 1


def test_the_command_line_s_readers_decide_with_its_settings(tmp_path, fake_readers):
    from taslation import cli

    ocr = cli.build_ocr(_settings(tmp_path, ocr_runs_on="gpu"))
    assert fake_readers.asked == [("gpu", OCR, "")] and ocr.settings.ocr_runs_on == "gpu"


def test_a_release_puts_them_on_the_cpu_and_the_next_read_decides_again(tmp_path, fake_readers, given_back):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr.release_gpu()
    assert ocr.placement.why == place.RELEASED and ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    assert given_back  # (their memory given back at once: no read was under way)
    assert len(fake_readers.asked) == 1  # nothing decided at the release itself (Ollama is about to load)
    fake_readers.answer = Placement("cpu", place.NO_ROOM, 200)
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2 and ocr.placement.why == place.NO_ROOM and ocr.charspot.device == "cpu"
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2  # once decided, not again at every read


def test_a_changed_setting_decides_again_at_the_next_read(tmp_path, fake_readers):
    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    s.target_language = "Turkish"  # (the window's own settings object: the larger translator)
    fake_readers.answer = Placement("cpu", place.NO_ROOM, -500)
    ocr.read(None)
    assert len(fake_readers.asked) == 2 and ocr.charspot.device == "cpu"
    s.ocr_runs_on = "gpu"
    fake_readers.answer = Placement("gpu", place.SET)
    ocr.settle(None, readers.CharspotReading("x", score=1.0))
    assert fake_readers.asked[-1][0] == "gpu" and ocr._nar.device == "cuda"


def test_a_failure_of_one_reader_puts_both_on_the_cpu_for_the_session(tmp_path, fake_readers):
    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    ocr._nar.broken = True
    text, _parted = readers.agree("x", readers.written(ocr._nar.read("y")), lambda: "z")
    assert ocr._nar.reads[-1] == "net@cpu"  # that crop read on the CPU
    assert ocr.placement == Placement("cpu", place.FAILED, error="MemoryError_")
    assert ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    s.target_language = "German"
    ocr.release_gpu()
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr.charspot.device == "cpu"  # never decided again this session


def test_the_window_s_first_reads_find_the_readers_where_they_are(tmp_path, fake_readers):
    from taslation.ui.jobs import first_reads

    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    first_reads(ocr)
    assert ocr.charspot.reads == ["net@cuda"] and ocr._nar.reads == ["net@cuda"] and ocr._cpt.reads == ["net@cpu"]


# ------------------------------------------------------------------ in the window: its readers, a load, a request
def test_nothing_is_decided_while_the_model_loads_or_answers(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr.release_gpu()
    for busy in (place.loading, place.translating):
        with busy():
            assert place.busy()
            ocr.read_chars(None)
            ocr.decide()
            assert len(fake_readers.asked) == 1 and ocr.charspot.device == "cpu" and ocr.placement.why == place.RELEASED
    assert not place.busy() and place._loading == place._translating == 0
    ocr.read_chars(None)  # the first read after them decides
    assert len(fake_readers.asked) == 2 and ocr.charspot.reads[-1] == "net@cuda"


def test_a_release_of_readers_on_the_cpu_decides_again_too(tmp_path, fake_readers):
    """(a model of the reader's own is not known before it was seen loaded: the read after its load finds it known)"""
    fake_readers.answer = Placement("cpu", place.UNKNOWN)
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr.release_gpu()
    assert ocr.placement.why == place.UNKNOWN and not ocr.holds_gpu()  # nothing was given back
    fake_readers.answer = Placement("gpu", place.ROOM, 1500)
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2 and ocr.holds_gpu() and ocr.charspot.reads[-1] == "net@cuda"


def test_the_window_s_readers_decide_with_its_settings_but_not_while_the_model_loads(tmp_path, fake_readers):
    """`jobs.load_readers` (the start, beside ``load_model_at_start``'s load): decided once loaded with the window's
    own settings; while the translation model loads meanwhile, the first read after that load decides."""
    from taslation.ui.jobs import load_readers

    s = _settings(tmp_path)
    ocr, error = load_readers(s)()
    assert error is None and ocr.settings is s and fake_readers.asked == [("auto", OCR, "")]
    assert ocr.charspot.device == "cuda" and ocr.charspot.reads == ["net@cuda"]  # (its first read warmed it there)
    with place.loading():
        later, error = load_readers(s)()
        later.read_chars(None)
        assert error is None and len(fake_readers.asked) == 1 and later.placement.why == place.NOT_ASKED
        assert later.charspot.reads == ["net@cpu", "net@cpu"]
    later.read_chars(None)
    assert len(fake_readers.asked) == 2 and later.charspot.reads[-1] == "net@cuda"


def test_readers_installed_later_decide_too_and_go_with_the_page_models(tmp_path, fake_readers):
    from taslation.ui.jobs import JobsMixin

    s = _settings(tmp_path)
    posted = []
    w = SimpleNamespace(settings=s, pipeline=SimpleNamespace(ocr=None, gpu_releases=[]), _ocr_failed=False,
                        _post=lambda kind, **data: posted.append(kind))
    JobsMixin._job_load_ocr(w)
    ocr = w.pipeline.ocr
    assert posted[-1] == "ocr_loaded" and ocr.settings is s and fake_readers.asked == [("auto", OCR, "")]
    assert w.pipeline.gpu_releases == [ocr.release_gpu]


def test_the_pipeline_lets_the_readers_go_with_the_page_models(tmp_path, fake_readers, given_back):
    from taslation.pipeline import Pipeline

    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    p = Pipeline(s, ocr=ocr)
    assert p.gpu_releases == [ocr.release_gpu]  # (no page model is installed here)
    p.release_gpu_models()  # (before Ollama loads its model, and Release the model now)
    assert ocr.placement.why == place.RELEASED and ocr.charspot.device == "cpu" and given_back


def test_a_load_and_a_request_find_the_readers_on_the_cpu_and_the_read_after_them_decides(tmp_path, fake_readers,
                                                                                         ollama):
    """A page that needs the model: the readers let go before Ollama loads it (`before_load`); a read while it loads
    and one while it answers (the spread's next page, read beside) read on the CPU and decide nothing; the first read
    after them decides, and finds the GPU again."""
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="qwen3.5:4b")
    ocr = readers.Readers(tmp_path, 0, settings=s)
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    Pipeline(s, ocr=ocr, translator=tr)
    during = []

    def answer(items, payload):  # (in the server's thread, while the client waits for its answer)
        ocr.read_chars(None)
        during.append((payload["messages"][-1]["content"] == "Hi", ocr.charspot.reads[-1], len(fake_readers.asked),
                       bool(place._loading), place._translating))

    ollama.answer = answer
    assert ocr.charspot.device == "cuda"
    tr.translate_page(["はい"])
    assert during == [(True, "net@cpu", 1, True, 0), (False, "net@cpu", 1, False, 1)]  # the load, then the request
    assert ocr.placement.why == place.RELEASED and ollama.loads == 1
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2 and ocr.charspot.reads[-1] == "net@cuda"


def test_a_streamed_request_is_a_request_to_its_end(tmp_path, ollama):
    from taslation.translate import OllamaTranslator

    ollama.between = 0.02
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    seen = []
    tr.translate_page(["はい", "いいえ", "そう"], on_item=lambda i, text: seen.append(place._translating),
                      cancel=threading.Event())
    assert seen == [1, 1, 1] and place._translating == place._loading == 0


def test_plamo_s_lines_are_requests_and_its_warm_up_a_load(monkeypatch):
    from taslation.translate.plamo import PlamoTranslator

    tr = PlamoTranslator("http://127.0.0.1:9", timeout=1.0)
    seen = []

    def request(path, payload=None, timeout=None):
        seen.append((bool(payload.get("prompt")), place._loading, place._translating))
        return {"response": "EN", "done": True}

    def stream(path, payload, on_text, cancel=None, on_slow=None, timeout=None):
        seen.append((bool(payload.get("prompt")), place._loading, place._translating))
        return {"message": {"content": "EN"}, "done": True}

    monkeypatch.setattr(tr, "_request", request)
    monkeypatch.setattr(tr, "_stream", stream)
    monkeypatch.setattr(tr, "ensure_loaded", lambda cancel=None, on_slow=None, quiet=False: None)
    tr.warm_up()
    tr._generate("a prompt", 16)
    tr._generate("a prompt", 16, cancel=threading.Event())
    assert seen == [(False, 1, 0), (True, 0, 1), (True, 0, 1)] and place._loading == place._translating == 0


def test_a_saved_choice_decides_again_at_the_next_read(tmp_path, fake_readers):
    from taslation.ui import app as app_mod

    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    app_mod.App._settings_saved(SimpleNamespace(settings=s), {"ocr_runs_on": "cpu"})  # (Settings... > Save)
    fake_readers.answer = Placement("cpu", place.SET)
    ocr.read_chars(None)
    assert fake_readers.asked[-1][0] == "cpu" and ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"


def test_the_system_page_shows_and_saves_where_the_ocr_runs(hidden_root, tmp_path, monkeypatch):
    from taslation.i18n import set_language
    from taslation.ui.dialogs import settings as dlg
    from taslation.ui.dialogs import system_page

    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    in_force = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert [v for v, _label in system_page.OCR_RUNS_ON_CHOICES] == list(place.SETTING_VALUES)
    assert d.system.ocr_runs_on.get() == "The GPU when it has room" and d.values()["ocr_runs_on"] == "auto"
    d.system.ocr_runs_on.set("The processor (CPU)")
    assert d.save() is True and got == [{"ocr_runs_on": "cpu"}]
    assert Settings.from_toml(in_force.config_path).ocr_runs_on == "cpu"
    d.destroy()
    set_language("ja")
    in_force.ocr_runs_on = "gpu"
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.system.ocr_runs_on.get() == "GPU" and d.values()["ocr_runs_on"] == "gpu"  # (shown in Japanese, kept as is)


# ------------------------------------------------------------------ where it is said
def _ocr_row(settings, ocr=None, cuda=True):
    return stage_devices(settings, SimpleNamespace(model="m", _loaded=lambda model: None), cuda=cuda, gpu=GPU,
                         ocr=ocr)[1]


def test_the_system_page_says_where_the_readers_are_and_why(tmp_path):
    s = _settings(tmp_path)
    on = _ocr_row(s, SimpleNamespace(placement=Placement("gpu", place.ROOM, 1500), settings=s))
    assert on.where() == f"GPU ({GPU})" and on.what.startswith("Two of the OCR readers") and "third" in on.what
    failed = _ocr_row(s, SimpleNamespace(placement=Placement("cpu", place.FAILED, error="CudaError"), settings=s))
    assert failed.where() == "CPU" and "CudaError" in failed.what
    tight = _ocr_row(s, SimpleNamespace(placement=Placement("cpu", place.NO_ROOM, 300), settings=s))
    assert tight.where() == "CPU" and "no room" in tight.what
    released = _ocr_row(s, SimpleNamespace(placement=Placement("cpu", place.RELEASED), settings=s))
    assert "next page" in released.what


def test_without_loaded_readers_the_rule_is_asked_now(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    assert _ocr_row(s, cuda=False).what == "The OCR readers"  # no GPU: as ever
    assert _ocr_row(_settings(tmp_path, ocr_runs_on="cpu")).what == "The OCR readers, as set in ocr_runs_on"
    monkeypatch.setattr(place, "gather", lambda settings: GpuFacts(total=6144, used=1325, translator=PLAMO))
    row = _ocr_row(s)
    assert row.device == "gpu" and row.gpu == GPU
    old = SimpleNamespace(settings=None)  # (readers loaded without settings, as a caller of before)
    assert _ocr_row(s, old).where() == "CPU" and _ocr_row(s, old).what == "The OCR readers"


# ------------------------------------------------------------------ the real networks on either device
def _has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 - no torch, no CUDA
        return False


requires_cuda = pytest.mark.skipif(not _has_cuda(), reason="no CUDA GPU")
DEVICES = ["cpu", pytest.param("cuda", marks=requires_cuda)]


@requires_cuda
def test_a_device_copy_has_the_same_bits_and_leaves_the_cpu_s_alone():
    import torch

    net = torch.nn.Sequential(torch.nn.Conv2d(3, 4, 3), torch.nn.BatchNorm2d(4), torch.nn.Linear(2, 2))
    net.kept = [torch.arange(6.0)]  # (a tensor beside the module's own, as `NarNet.prepare` keeps them)
    copy = place.device_copy(net, "cuda", torch.channels_last)
    assert all(p.device.type == "cpu" for p in net.parameters()) and net.kept[0].device.type == "cpu"
    assert all(p.device.type == "cuda" for p in copy.parameters()) and copy.kept[0].device.type == "cuda"
    assert copy[1].running_mean.device.type == "cuda"
    assert copy[0].weight.is_contiguous(memory_format=torch.channels_last)
    for a, b in zip(net.parameters(), copy.parameters()):
        assert torch.equal(a, b.cpu())


@pytest.fixture(scope="module")
def real_readers():
    return readers.Readers(Settings().models_dir, 0)


def _sample_crops(sample_page, sample_truth):
    out = []
    for bubble in sample_truth:
        x0, y0, x1, y1 = bubble["text_box"]
        out.append(sample_page.crop((x0 - 4, y0 - 4, x1 + 4, y1 + 4)))
    return out


@requires_ocr
@pytest.mark.parametrize("device", DEVICES)
def test_the_readers_read_the_same_on_either_device(device, real_readers, sample_page, sample_truth, given_back):
    """The CPU's readings are the reference; on *device* the texts, the characters' order, every threshold that decides
    something and the boxes come out the same (the floats within rounding)."""
    if real_readers._nar is None:
        pytest.skip("manga-ocr-nar-small not installed")
    crops = _sample_crops(sample_page, sample_truth)
    engines = real_readers._movable()
    for e in engines:
        e.to("cpu")
    want = [(real_readers.charspot.read_chars(c), real_readers._nar.read(c)) for c in crops]
    try:
        assert all(e.to(device) for e in engines)
        charspot = real_readers.charspot
        took = time.perf_counter()
        got = [(charspot.read_chars(c), real_readers._nar.read(c)) for c in crops]
        took = (time.perf_counter() - took) / len(crops)
        if device != "cpu":  # (the depthwise convolutions without cuDNN: no second a new size of crop)
            assert took < 0.5, took
    finally:
        for e in engines:
            e.to("cpu")
    thresholds = (0.65, 0.7, 0.75, 0.8, 0.9, 0.95)
    for (a, nar_a), (b, nar_b) in zip(want, got):
        assert a.text == b.text and nar_a == nar_b
        assert [c.char for c in a.chars] == [c.char for c in b.chars]
        assert all((a.score >= t) == (b.score >= t) for t in thresholds)
        assert abs(a.score - b.score) < 1e-4
        for ca, cb in zip(a.chars, b.chars):
            assert max(abs(x - y) for x, y in zip(ca.box, cb.box)) < 1e-2
            assert abs(ca.score - cb.score) < 1e-4


def test_the_new_lines_are_in_every_language():
    from taslation.i18n import CATALOGS, FEATURE_LANGUAGES
    from taslation.locales.features import ocr_release
    from taslation.ui.dialogs import system_page

    for text in (*devices.OCR_WHY.values(), *devices.OCR_SET.values()):
        for code, catalog in CATALOGS.items():
            assert code == "en" or text in catalog, (code, text)
    for key in (system_page.OCR_RUNS_ON_LABEL, system_page.OCR_RUNS_ON_TEXT,
                *(label for _value, label in system_page.OCR_RUNS_ON_CHOICES)):
        assert sorted(ocr_release.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key
