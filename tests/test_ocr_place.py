"""What runs on the GPU for the session (`taslation.ocr.place`): one judgement at the start - the card's total, less what
other programs hold, less every part the settings put on the GPU at its measured peak and this process's context, must
leave the margin free - enough or short by N MiB; short, what does not fit goes to the processor in a fixed order
(only as many parts as it takes, never one a setting fixed), or the window asks; nothing moves during the session but
the one-way net of a failure on the GPU; the readers go where the plan has them; the System page and ``taslation
doctor`` say where they are, why, and what the start found short. Everything here uses stand-ins: no GPU, no model, no
Ollama but the fake one. (The start's dialog and the window's start: tests/test_gpu_short_dialog.py.)"""

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
from taslation.ocr.place import (CHARSPOT_MIB, CONTEXT_MIB, FLOOR_MIB, KNOWN_TRANSLATORS, LAMA_MIB, LAMA_TALL_MIB,
                                 LAYOUT_MIB, LAMA, LAYOUT, MARGIN_MIB, NAR_MIB, READERS, READERS_GRAPHS_MIB, SWAY_MIB,
                                 TRANSLATOR,
                                 DeviceModels, GpuFacts, Need, Placement, Plan, judge, left_at_peak, short_by)

OCR = CHARSPOT_MIB + NAR_MIB
PLAMO_NAME = "taslation-plamo3-translate-2b"
PLAMO = KNOWN_TRANSLATORS[(PLAMO_NAME, 8192)][("q8_0", False)][0]  # (a server without the window cache)
PLAMO_WINDOW = KNOWN_TRANSLATORS[(PLAMO_NAME, 8192)][("q8_0", True)][0]  # (the default: with it, on a 6 GB card)
GPU = "NVIDIA Test GPU"
REAL_GATHER = place.gather  # (taken before conftest's stand-in is put in its place for every test)


@pytest.fixture(autouse=True)
def nothing_learnt():
    place._learnt.clear()
    yield
    place._learnt.clear()


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", **kw)


def _needs(translator=PLAMO_WINDOW, ocr=OCR, lama=LAMA_MIB, layout=LAYOUT_MIB, fixed=(), graphs=0) -> list[Need]:
    """The default settings' needs on a 6 GB card (PLaMo with the window cache, both readers, LaMa, the layout model);
    a part given as 0 is not on the GPU; *fixed*: the parts a setting fixes there; *graphs*: the readers' CUDA graphs
    with them (their need's extra; `place.needs` counts `READERS_GRAPHS_MIB`)."""
    graphs = graphs if ocr else 0
    parts = ((TRANSLATOR, translator, 0), (READERS, ocr + graphs, graphs), (LAMA, lama, 0), (LAYOUT, layout, 0))
    return [Need(part, mib, part in fixed, extra) for part, mib, extra in parts if mib]


def _card(others: int, total: int = 6144) -> GpuFacts:
    """A card with *others* MiB held by other programs, nothing of TASlation's on it yet."""
    return GpuFacts(total=total, used=others)


# ------------------------------------------------------------------ the judgement
def test_left_at_the_peak_is_the_card_less_other_programs_every_need_and_this_process_s_context():
    assert left_at_peak(_card(1325), _needs()) == 6144 - 1325 - (PLAMO_WINDOW + OCR + LAMA_MIB + LAYOUT_MIB) - CONTEXT_MIB
    assert left_at_peak(_card(1325), _needs(ocr=0, lama=0, layout=0)) == 6144 - 1325 - PLAMO_WINDOW  # (no torch part)


def test_other_programs_are_the_used_memory_less_what_is_taslation_s_own():
    facts = GpuFacts(total=6144, used=4000, own=500, translator_now=1900)
    assert facts.others == 1600
    assert left_at_peak(facts, _needs()) == left_at_peak(_card(1600), _needs())  # (counted once, at its need)
    assert GpuFacts(total=6144, used=100, own=500).others == 0


def test_the_margin_is_the_driver_s_part_and_how_far_other_programs_rose_at_once():
    from pathlib import Path

    manual = (Path(__file__).resolve().parents[1] / "docs" / "MANUAL.md").read_text(encoding="utf-8")
    assert (FLOOR_MIB, SWAY_MIB, MARGIN_MIB) == (490, 220, 710)
    assert round(MARGIN_MIB * place.MiB / 1e8) * 100 == 700 and "with about 700 MB left over" in manual


def test_the_default_6_gb_card_is_enough_up_to_1804_mib_of_other_programs():
    """The machine the figures were measured on: PLaMo with the window cache, both readers, LaMa and the layout model
    need 3530 MiB and the context 100; with the 710 MiB margin that leaves room for 1804 MiB of other programs (1704
    before the translator was counted to 10 MiB of its measured load and the layout model at its one input's peak). One
    MiB more is short by 1; a screen taller than 1440 px (LaMa's larger windows) moves the mark to 1514; a server
    without the window cache to 1934."""
    assert short_by(_card(1804), _needs()) == 0 and short_by(_card(1805), _needs()) == 1
    assert short_by(_card(2000), _needs()) == 196
    tall = _needs(lama=LAMA_TALL_MIB)
    assert short_by(_card(1514), tall) == 0 and short_by(_card(1515), tall) == 1
    plain = _needs(translator=PLAMO)
    assert short_by(_card(1934), plain) == 0 and short_by(_card(1935), plain) == 1
    assert short_by(_card(1804, total=8192), _needs()) == 0 and short_by(_card(3852, total=8192), _needs()) == 0


def test_the_page_models_are_counted_at_their_measured_peaks():
    """What the page models' figures stand on (the module's comments; the translation models': the test of PLaMo's
    table below): the layout model, whose input is always one size (640 px square), at its measured peak rounded up
    to 10 MiB, nothing added for inputs not measured; LaMa a fifth past the largest window met."""
    from taslation.detect import layout

    assert layout.SIZE == 640 and 356 <= LAYOUT_MIB < 366
    assert LAMA_MIB >= round(564 * 1.2)  # (552-564 MiB at the largest windows met on screens up to 1440 px)


def test_the_readers_cuda_graphs_are_left_off_unasked_where_the_room_is_short_with_them():
    """On the default 6 GB card the graphs have room up to 1534 MiB of other programs (1804 less their 270); with more,
    the readers stay on the GPU without them, nothing asked, the rest judged as without graphs: still enough up to
    1804, short beyond as ever (and asked about, short by what it lacks without them). Starts on the 6 GB card the
    figures were measured on, by the other programs' memory they found (1356, 1563 and 1688 MiB in three starts of
    the program, 1382 and 1454 in two measuring runs): kept in the first and the measuring runs' (before: the first and
    1382 only), left off at 1563 and 1688."""
    with_graphs = _needs(graphs=READERS_GRAPHS_MIB)
    assert READERS_GRAPHS_MIB == 270
    room = judge(_card(1534), with_graphs)
    assert room.graphs and room.why == place.ROOM and room.left == MARGIN_MIB and READERS in room.gpu
    bare = judge(_card(1535), with_graphs)
    assert not bare.graphs and bare.why == place.ROOM and not bare.asks and READERS in bare.gpu
    assert bare.short == 0 and bare.left == MARGIN_MIB + 1804 - 1535
    assert judge(_card(1804), with_graphs) == Plan((TRANSLATOR, READERS, LAMA, LAYOUT), (), 0, MARGIN_MIB, place.ROOM,
                                                   place.TO_PROCESSOR, graphs=False)
    short = judge(_card(1805), with_graphs)
    assert short.asks and short.short == 1 and not short.graphs
    assert judge(_card(1805), _needs()).graphs  # (no graphs counted, none left off: a plan's default)
    kept = [judge(_card(others), with_graphs).graphs for others in (1356, 1382, 1454, 1563, 1688)]
    assert kept == [True, True, True, False, False]  # (the 21:06, two of today's, 21:12 and 22:02 starts' others)


def test_where_parts_go_to_the_processor_the_graphs_stay_if_the_rest_has_room_for_them():
    moved = judge(_card(1805), _needs(graphs=READERS_GRAPHS_MIB), "processor")
    assert moved.cpu == (READERS,) and not moved.graphs  # (the readers on the processor: no graphs there)
    fixed = judge(_card(1805), _needs(graphs=READERS_GRAPHS_MIB, fixed=(READERS,)), "processor")
    assert fixed.cpu == (LAMA,) and READERS in fixed.gpu and fixed.graphs  # (LaMa's room holds them)
    assert fixed.left == left_at_peak(_card(1805), _needs(lama=0, graphs=READERS_GRAPHS_MIB))
    tight = judge(_card(1804 + LAMA_MIB), _needs(graphs=READERS_GRAPHS_MIB, fixed=(READERS,)), "processor")
    assert tight.cpu == (LAMA,) and not tight.graphs and tight.left == MARGIN_MIB


def test_enough_puts_everything_on_the_gpu_and_asks_nothing():
    plan = judge(_card(1804), _needs())
    assert plan == Plan((TRANSLATOR, READERS, LAMA, LAYOUT), (), 0, MARGIN_MIB, place.ROOM, place.TO_PROCESSOR)
    assert not plan.asks


def test_short_asks_with_everything_where_the_settings_put_it_until_answered():
    plan = judge(_card(2000), _needs())
    assert plan.why == place.SHORT and plan.short == 196 and plan.asks and plan.cpu == ()
    assert plan.gpu == (TRANSLATOR, READERS, LAMA, LAYOUT)


def test_the_processor_takes_only_as_many_parts_as_it_takes_least_loss_first():
    """The order: the readers (their reads overlap the translation), LaMa, the layout model, the translation model
    last; the context goes with the last torch part."""
    assert place.TO_PROCESSOR == (READERS, LAMA, LAYOUT, TRANSLATOR)
    for short, moved in ((1, (READERS,)), (OCR, (READERS,)), (OCR + 1, (READERS, LAMA)),
                         (OCR + LAMA_MIB, (READERS, LAMA)), (OCR + LAMA_MIB + 1, (READERS, LAMA, LAYOUT)),
                         (OCR + LAMA_MIB + LAYOUT_MIB + CONTEXT_MIB, (READERS, LAMA, LAYOUT)),
                         (OCR + LAMA_MIB + LAYOUT_MIB + CONTEXT_MIB + 1, (READERS, LAMA, LAYOUT, TRANSLATOR))):
        plan = judge(_card(1804 + short), _needs(), "processor")
        assert plan.cpu == moved and plan.why == place.PROCESSOR and plan.short == short, short
        assert plan.gpu == tuple(p for p in (TRANSLATOR, READERS, LAMA, LAYOUT) if p not in moved)
        assert not plan.asks
    everything = judge(_card(6000), _needs(), "processor")  # (nothing fits: all of it on the processor)
    assert everything.cpu == place.TO_PROCESSOR and everything.gpu == () and everything.short == 6000 - 1804


def test_a_part_a_setting_fixes_is_counted_and_never_sent_to_the_processor():
    """A setting that forces a part onto the GPU never asks: the start goes on short as the settings say; with
    ``gpu_short`` "processor" the other parts go to the processor as ever."""
    for fixed in ((READERS,), (TRANSLATOR,)):  # (``ocr_runs_on`` "gpu"; a number of layers in ``ollama_num_gpu``)
        asked = judge(_card(2000), _needs(fixed=fixed))
        assert asked.why == place.SHORT and asked.short == 196 and asked.forced and not asked.asks and not asked.cpu
    plan = judge(_card(2000), _needs(fixed=(READERS,)), "processor")
    assert plan.cpu == (LAMA,) and READERS in plan.gpu and plan.could == (LAMA, LAYOUT, TRANSLATOR)
    assert not judge(_card(2000), _needs()).forced and judge(_card(2500), _needs(ocr=0)).asks  # ("cpu" forces nothing)
    every = _needs(fixed=(TRANSLATOR, READERS, LAMA, LAYOUT))
    for choice in ("ask", "processor"):
        fixed = judge(_card(2000), every, choice)  # (nothing could go: nothing asked, nothing moved)
        assert fixed.why == place.SHORT and fixed.short == 196 and not fixed.asks and fixed.cpu == ()


def test_no_nvidia_gpu_judges_and_asks_nothing(tmp_path):
    plan = judge(None, _needs())
    assert plan.why == place.NO_GPU and not plan.asks and plan.short == 0
    assert place.make_plan(_settings(tmp_path), facts=lambda s: None) == Plan(why=place.NO_GPU)
    assert place.make_plan(_settings(tmp_path), "processor", facts=lambda s: None) == Plan(why=place.NO_GPU)


def test_a_plan_is_made_on_the_facts_of_the_moment_and_the_needs_of_the_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(place, "needs", lambda settings, cuda=None, ask=True: _needs())
    s = _settings(tmp_path)
    assert place.make_plan(s, facts=lambda _s: _card(1804)).why == place.ROOM
    assert place.make_plan(s, facts=lambda _s: _card(2000)).asks
    assert place.make_plan(s, "processor", facts=lambda _s: _card(2000)).cpu == (READERS,)


def test_a_judgement_says_what_it_stood_on_in_numbers(tmp_path, monkeypatch, caplog):
    """Two starts that judged otherwise are told apart by the log alone: what other programs held, each need (LaMa's
    tall figure, the translator's by the window cache, the readers' graphs), the context - numbers, no names."""
    monkeypatch.setattr(place, "needs", lambda settings, cuda=None, ask=True: _needs(graphs=READERS_GRAPHS_MIB))
    facts = GpuFacts(total=6144, used=3700, own=0, translator_now=PLAMO_WINDOW, answered=True,
                     loaded=(place.Loaded("someones-model:7b", 900, False),))
    with caplog.at_level("INFO", logger="taslation.ocr.place"):
        place.make_plan(_settings(tmp_path), facts=lambda _s: facts)
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("the GPU at the judgement")]
    assert said == [
        f"the GPU at the judgement: total 6144 MiB, used 3700 (this process 0, the translation model {PLAMO_WINDOW}, "
        f"other programs {3700 - PLAMO_WINDOW}; Ollama answered; other models there 900); needs translator "
        f"{PLAMO_WINDOW}, readers {OCR + READERS_GRAPHS_MIB} (graphs {READERS_GRAPHS_MIB}), lama {LAMA_MIB}, layout "
        f"{LAYOUT_MIB}, the context {CONTEXT_MIB}"]
    assert "someones-model" not in said[0]


# ------------------------------------------------------------------ what the settings put on the GPU
@pytest.fixture
def page_models(monkeypatch):
    """LaMa and the layout model on the GPU by the pipeline's rules, a screen of 1080 px, PLaMo's need as measured."""
    monkeypatch.setattr(place, "page_models_on_gpu", lambda settings: (True, True))
    monkeypatch.setattr(place, "tall_screen", lambda: False)
    monkeypatch.setattr(place, "_translator_need", lambda s, cache=None, ask=True: (PLAMO_WINDOW, 0, True))


def test_the_needs_follow_the_settings(tmp_path, monkeypatch, page_models):
    from taslation.ocr import graphs

    monkeypatch.setattr(readers, "missing_readers", lambda models_dir: [])  # (all three readers installed)
    s = _settings(tmp_path)
    g = READERS_GRAPHS_MIB  # (the readers' CUDA graphs with them, the need's extra)
    assert place.needs(s, cuda=True) == _needs(graphs=g)
    assert place.needs(_settings(tmp_path, ocr_runs_on="cpu"), cuda=True) == _needs(ocr=0)
    assert place.needs(_settings(tmp_path, ocr_runs_on="gpu"), cuda=True) == _needs(fixed=(READERS,), graphs=g)
    assert place.needs(_settings(tmp_path, ollama_num_gpu="0"), cuda=True) == _needs(translator=0, graphs=g)
    assert place.needs(_settings(tmp_path, ollama_num_gpu="10"), cuda=True) == _needs(fixed=(TRANSLATOR,), graphs=g)
    assert place.needs(s, cuda=False) == _needs(ocr=0, lama=0, layout=0)  # (torch without CUDA: the model alone)
    monkeypatch.setattr(place, "tall_screen", lambda: True)
    assert place.needs(s, cuda=True) == _needs(lama=LAMA_TALL_MIB, graphs=g)
    monkeypatch.setattr(place, "tall_screen", lambda: False)
    monkeypatch.setattr(readers, "missing_readers", lambda models_dir: ["nar"])
    assert place.needs(s, cuda=True) == _needs(ocr=CHARSPOT_MIB, graphs=g)  # (charspot alone: its graphs all of it)
    monkeypatch.setattr(graphs, "ENABLED", False)
    assert place.needs(s, cuda=True) == _needs(ocr=CHARSPOT_MIB)  # (no graphs captured, none counted)


def test_a_screen_taller_than_1440_px_or_not_known_counts_lama_s_larger_windows(monkeypatch):
    for height, tall in ((1080, False), (1440, False), (1600, True), (2160, True), (None, True)):
        monkeypatch.setattr(devices, "screen_height_px", lambda height=height: height)
        assert place.tall_screen() is tall


def test_the_screen_s_height_is_read_without_a_window(monkeypatch):
    height = devices.screen_height_px()
    assert height is None or height >= 240  # (whatever this computer's screens are; None off Windows)
    monkeypatch.setattr(devices.sys, "platform", "linux")
    assert devices.screen_height_px() is None


def test_page_models_follow_the_pipeline_s_rules(tmp_path, monkeypatch):
    from taslation.detect import layout
    from taslation.render import artwork

    monkeypatch.setattr(artwork, "installed", lambda models_dir: True)
    monkeypatch.setattr(artwork, "available", lambda models_dir, setting="auto", cuda=None: setting != "off")
    monkeypatch.setattr(layout, "available", lambda models_dir: True)
    assert place.page_models_on_gpu(_settings(tmp_path)) == (True, True)  # (the defaults: both "auto")
    assert place.page_models_on_gpu(_settings(tmp_path, detect_model="off")) == (True, False)
    assert place.page_models_on_gpu(_settings(tmp_path, art_erase="off", detect_model="auto")) == (False, False)
    assert place.page_models_on_gpu(_settings(tmp_path, erase_mode="classic", detect_model="on")) == (False, True)


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


def test_the_facts_are_the_card_s_memory_this_process_s_and_the_model_s_now(tmp_path, monkeypatch, ollama):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 4000))
    monkeypatch.setattr(place, "own_mib", lambda: 500)
    s = _settings(tmp_path, ollama_url=ollama.url)
    ollama.loaded.add(PLAMO_NAME)
    ollama.size = 1956 * place.MiB
    facts = REAL_GATHER(s)
    # (the model's need on the card now: what its load was measured to add with the cache of that size, runner and all)
    assert facts == GpuFacts(total=6144, used=4000, own=500, translator_now=PLAMO_WINDOW, answered=True)
    assert facts.others == 4000 - 500 - PLAMO_WINDOW
    assert not ollama.loads  # (/api/ps only: nothing was loaded to find out)


def test_with_the_model_loaded_its_runner_s_own_memory_is_counted_once(tmp_path, monkeypatch, ollama):
    """/api/ps leaves out the runner's own memory (PLaMo's load added 2065 MiB to the card's used memory, /api/ps said
    1956): counted in the need and on the card as the need's, a start with the model loaded is judged as one without
    it, to the 10 MiB the need is rounded up to - before, those 110 MiB counted again as other programs'."""
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    s = _settings(tmp_path, ollama_url=ollama.url)
    others = 1500
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, others))
    unloaded = REAL_GATHER(s)
    ollama.loaded.add(PLAMO_NAME)
    ollama.size = 2050500853  # (/api/ps's size measured with q8_0 and the full window)
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, others + 2065))  # (what the load added)
    loaded = REAL_GATHER(s)
    need = place.needs(s, cuda=False)
    assert need == [Need(TRANSLATOR, PLAMO_WINDOW)] and loaded.translator_now == PLAMO_WINDOW
    assert unloaded.others == others and others - 10 < loaded.others <= others
    assert left_at_peak(loaded, need) >= left_at_peak(unloaded, need)
    ollama.share = 0.5  # (split by the server: what of the need is on the card, its share)
    on, size = int(2050500853 * 0.5) // place.MiB, 2050500853 // place.MiB
    assert REAL_GATHER(s).translator_now == round(PLAMO_WINDOW * on / size)


def test_other_models_ollama_holds_on_the_card_are_named_taslation_s_own_apart(tmp_path, monkeypatch, ollama):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 5000))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    s = _settings(tmp_path, ollama_url=ollama.url)
    ollama.loaded.update({PLAMO_NAME, "qwen3.5:4b", "someones-model:7b"})
    ollama.sizes = {PLAMO_NAME: 1956 * place.MiB, "qwen3.5:4b": 3203 * place.MiB, "someones-model:7b": 900 * place.MiB}
    facts = REAL_GATHER(s)
    assert facts.loaded == (place.Loaded("qwen3.5:4b", 3203, True), place.Loaded("someones-model:7b", 900, False))
    assert facts.releasable == ("qwen3.5:4b",)  # (TASlation's own: the one PLaMo's language does not use)
    assert facts.others == 5000 - PLAMO_WINDOW  # (the other models are other programs' memory, counted as such)
    named = _settings(tmp_path, ollama_url=ollama.url, ollama_model=PLAMO_NAME, target_language="English")
    assert REAL_GATHER(named).releasable == ("qwen3.5:4b",)
    mine = _settings(tmp_path, ollama_url=ollama.url, ollama_model="someones-model:7b")  # (named in the settings)
    assert [m.name for m in REAL_GATHER(mine).loaded] == ["qwen3.5:4b", PLAMO_NAME]  # (its own is no other)
    ollama.share = 0.0  # (on the processor: none of the card's memory, not named)
    assert REAL_GATHER(s).loaded == ()


def test_a_model_loaded_at_another_context_holds_what_ps_says_and_needs_what_a_load_adds(tmp_path, monkeypatch, ollama):
    """Loaded by another program or another version at another context, the server loads it again for the first
    request (`OllamaTranslator.loaded_as_asked`): what it holds now goes then, and the need is that of a load."""
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 3000))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    s = _settings(tmp_path, ollama_url=ollama.url)
    ollama.loaded.add(PLAMO_NAME)
    ollama.size = 1500 * place.MiB
    ollama.contexts[PLAMO_NAME] = 4096
    assert place.translator_need(s) == (PLAMO, 1500)  # (as before a load; /api/ps's figure on the card)
    assert REAL_GATHER(s).others == 3000 - 1500
    ollama.contexts[PLAMO_NAME] = 8192  # (as asked)
    assert place.translator_need(s) == (PLAMO, PLAMO)


def test_once_released_the_card_s_used_memory_is_followed_until_it_shows_it(monkeypatch):
    readings = iter([(6144, 4000), (6144, 3900), (6144, 2000)])
    monkeypatch.setattr(place, "card_memory", lambda: next(readings))
    assert place.wait_freed((6144, 4100), 2000, timeout=2.0) is True  # (fell by 2100 at the third look)
    monkeypatch.setattr(place, "card_memory", lambda: (6144, 4000))
    began = time.monotonic()
    assert place.wait_freed((6144, 4100), 2000, timeout=0.3) is False and time.monotonic() - began < 1.0
    assert place.wait_freed(None, 2000) is True and place.wait_freed((6144, 4100), 0) is True


def test_no_nvidia_gpu_has_no_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: None)
    monkeypatch.setattr(place.sys, "platform", "win32")  # (Windows: torch's figure is this process's alone)
    assert REAL_GATHER(_settings(tmp_path)) is None


def test_the_card_and_this_process_are_read_together(monkeypatch):
    readings, owns = iter([(6144, 2000), (6144, 2500)]), iter([0, 500, 500, 500])
    monkeypatch.setattr(place, "card_memory", lambda: next(readings))
    monkeypatch.setattr(place, "own_mib", lambda: next(owns))
    assert place.snapshot() == ((6144, 2500), 500)  # (this process moved between: read again)


def test_the_facts_say_whether_ollama_answered(tmp_path, monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 1325))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    s = _settings(tmp_path, ollama_url="http://127.0.0.1:9")
    netguard.install(allowed_ports={9}, audit_hook=False)
    try:
        facts = REAL_GATHER(s)
    finally:
        netguard.uninstall()
    assert facts == GpuFacts(total=6144, used=1325, own=0, translator_now=0, answered=False)
    assert place._translator_need(_settings(tmp_path, ollama_num_gpu="0")) == (0, 0, True)  # (nothing to ask)


def test_ollama_is_not_asked_when_the_setup_check_found_it_down(tmp_path, monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 1325))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    s = _settings(tmp_path, ollama_url="http://127.0.0.1:9")  # (were it asked, the netguard would refuse it)
    assert REAL_GATHER(s, ask=False) == GpuFacts(total=6144, used=1325)
    assert place._translator_need(s, ask=False) == (PLAMO, 0, True)


def test_the_card_s_memory_comes_from_nvml(monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 1325))
    assert place.card_memory() == (6144, 1325)


def test_the_translator_s_need_while_loaded_before_and_after(tmp_path, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url)
    assert place.translator_need(s) == (PLAMO, 0)  # not loaded: as measured
    assert place._translator_need(s) == (PLAMO, 0, True)  # (Ollama answered: none loaded)
    ollama.loaded.add(PLAMO_NAME)
    size = 3_000_000_000 // place.MiB  # (the fake's size)
    need = round(size * place.RUNNER_SHARE)
    assert place.translator_need(s) == (need, need)  # loaded: /api/ps, the runner's share; all of it on the card
    ollama.loaded.clear()
    need, now = place.translator_need(s)
    assert now == 0 and need == round(size * place.RUNNER_SHARE)  # learnt
    assert not ollama.loads  # nothing was loaded to find out


def test_a_known_translator_of_the_size_it_was_measured_at_needs_what_was_measured(tmp_path, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url)
    ollama.loaded.add(PLAMO_NAME)
    ollama.size = 1823 * place.MiB + 512 * 1024
    assert place.translator_need(s) == (PLAMO, PLAMO)  # (what its load was measured to add, not its size)
    ollama.loaded.clear()
    assert place.translator_need(s) == (PLAMO, 0)
    ollama.loaded.add(PLAMO_NAME)
    ollama.size = 1900 * place.MiB  # (a server with another cache: what that one was measured to add)
    place.translator_need(s)
    ollama.loaded.clear()
    assert place.translator_need(s) == (PLAMO_WINDOW, 0)
    ollama.loaded.add(PLAMO_NAME)
    ollama.size = 2500 * place.MiB  # (another build, larger than every cache measured: its size, the runner's share)
    place.translator_need(s)
    ollama.loaded.clear()
    assert place.translator_need(s) == (round(2500 * place.RUNNER_SHARE), 0)


# what loading PLaMo added to the card's used memory and /api/ps's size, by the server's KV cache and window cache
# (Ollama 0.40.16, measured 2026-11-20): (KV type, full window) -> (MiB added, /api/ps bytes)
MEASURED = {("q8_0", False): (1933, 1912550194), ("q8_0", True): (2065, 2050500853),
            ("f16", False): (2009, 1972759429), ("f16", True): (2229, 2203446149)}


def test_plamo_is_counted_as_measured_for_each_kv_cache_and_window_cache():
    for cache, (added, size) in MEASURED.items():
        counted, ps = place.known_translator(PLAMO_NAME, 8192, cache)
        assert added <= counted < added + 10 and counted % 10 == 0, cache  # (rounded up to 10 MiB, no further)
        assert size // place.MiB < ps and ps - size / place.MiB < 1, cache  # (/api/ps's size, rounded up)
    assert place.known_translator(PLAMO_NAME, 8192, ("q4_0", True)) == (2230, 2102)  # (a type not measured: f16's)
    assert place.known_translator(PLAMO_NAME, 4096, ("q8_0", False)) is None  # (another context: not measured)
    for cache in MEASURED:
        assert place.known_translator("qwen3.5:4b", 16384, cache) == (3940, 3203)  # (no windowed layers)


@pytest.mark.parametrize("cache", list(MEASURED))
def test_before_it_loads_plamo_needs_what_it_adds_on_the_server_it_runs_on(tmp_path, monkeypatch, ollama, cache):
    """The window cache counted once, at its real size: the server's own (as TASlation started it, else as its
    variables say)."""
    monkeypatch.setattr(place, "server_cache", lambda settings: cache)
    s = _settings(tmp_path, ollama_url=ollama.url)
    assert place.translator_need(s) == (place.known_translator(PLAMO_NAME, 8192, cache)[0], 0)
    assert place._translator_need(s, ("q8_0", False)) == (PLAMO, 0, True)  # (a cache given: that one's)


def test_a_model_of_the_reader_s_own_is_counted_by_its_file_until_seen_loaded(tmp_path, monkeypatch, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="someones-model:7b")
    assert place.translator_need(s) == (None, 0)  # (its file not listed with a size: not known, not counted)
    monkeypatch.setattr(place, "_file_mib", lambda translator, name: 2000)
    assert place.translator_need(s) == (round(2000 * place.UNKNOWN_SHARE), 0)
    ollama.loaded.add("someones-model:7b")
    ollama.share = 0.5  # (split by the server: the need is all of it, on the card its share)
    size, need = 3_000_000_000 // place.MiB, round(3_000_000_000 // place.MiB * place.RUNNER_SHARE)
    assert place.translator_need(s) == (need, round(need * (int(3_000_000_000 * 0.5) // place.MiB) / size))


def test_layers_set_by_hand_need_what_they_hold(tmp_path, ollama):
    s = _settings(tmp_path, ollama_url=ollama.url, ollama_num_gpu="10")
    ollama.loaded.add(PLAMO_NAME)
    ollama.share = 0.4
    now = int(3_000_000_000 * 0.4) // place.MiB
    assert place.translator_need(s) == (round(now * place.RUNNER_SHARE),) * 2  # (with the runner's own share)
    ollama.loaded.clear()
    assert place.translator_need(s) == (round(now * place.RUNNER_SHARE), 0)


def test_ollama_down_is_a_model_not_loaded(tmp_path):
    s = _settings(tmp_path, ollama_url="http://127.0.0.1:9")
    netguard.install(allowed_ports={9}, audit_hook=False)
    try:
        assert place.translator_need(s) == (PLAMO, 0)
    finally:
        netguard.uninstall()


# ------------------------------------------------------------------ the settings
def test_the_settings_and_their_values(tmp_path):
    assert Settings().ocr_runs_on == "auto" and Settings().gpu_short == "ask"
    for value in place.SETTING_VALUES:
        _settings(tmp_path, ocr_runs_on=value).validate()
    for value in place.SHORT_VALUES:
        _settings(tmp_path, gpu_short=value).validate()
    with pytest.raises(ConfigError):
        _settings(tmp_path, ocr_runs_on="cuda").validate()
    with pytest.raises(ConfigError):
        _settings(tmp_path, gpu_short="gpu").validate()


def test_an_old_file_with_the_old_ocr_device_neither_breaks_nor_forces_the_gpu(tmp_path):
    path = tmp_path / "taslation.toml"
    for old in ("cuda", "auto", "cpu", "gpu"):
        path.write_text(f'ocr_device = "{old}"\n', encoding="utf-8")
        s = Settings.from_toml(path)
        s.validate()
        assert s.ocr_runs_on == "auto" and not s.ignored_keys  # (dropped quietly, as before)


def test_the_example_file_has_the_settings():
    example = Settings.from_toml(Path(__file__).resolve().parent.parent / "taslation.toml.example")
    assert example.ocr_runs_on == "auto" and example.gpu_short == "ask"


# ------------------------------------------------------------------ the session's plan
def test_the_session_s_plan_says_what_may_run_on_the_gpu(tmp_path):
    assert place.session() is None and place.on_gpu(LAMA) and place.on_gpu(LAYOUT)  # (no plan: as the settings say)
    assert not place.translator_on_processor()
    place.settle(judge(_card(2700), _needs(), "processor"))  # (short by 996: the readers and LaMa go)
    assert place.session().cpu == (READERS, LAMA)
    assert not place.on_gpu(LAMA) and place.on_gpu(LAYOUT) and not place.translator_on_processor()
    place.settle(judge(_card(6000), _needs(), "processor"))
    assert place.translator_on_processor() and not place.on_gpu(LAYOUT)
    place.settle(Plan(why=place.NO_GPU))
    assert place.on_gpu(LAMA) and place.on_gpu(LAYOUT)  # (nothing judged: as the settings say)
    place.reset()
    assert place.session() is None


def test_the_one_net_is_one_way_for_the_rest_of_the_session():
    place.settle(judge(_card(1000), _needs()))
    place.failed(LAMA, "OutOfMemoryError")
    place.failed(LAMA, "RuntimeError")  # (the first failure is the one said)
    assert not place.on_gpu(LAMA) and place.failure(LAMA) == "OutOfMemoryError" and place.on_gpu(LAYOUT)
    place.settle(judge(_card(1000), _needs()))  # (a plan never brings a part back)
    assert not place.on_gpu(LAMA)
    place.reset()
    assert place.on_gpu(LAMA) and place.failure(LAMA) == ""


def test_a_command_takes_the_processor_s_way_without_asking_and_keeps_it(tmp_path, monkeypatch):
    """A command or a tool cannot ask: what does not fit goes to the processor, as "Start on the processor"; judged
    once, the first time it is wanted."""
    asked = []
    monkeypatch.setattr(place, "gather", lambda settings, memory=None, own=None, ask=True: asked.append(1) or _card(2000))
    monkeypatch.setattr(place, "needs", lambda settings, cuda=None, ask=True: _needs())
    plan = place.plan_for(_settings(tmp_path))
    assert plan.cpu == (READERS,) and plan.why == place.PROCESSOR and place.session() is plan
    assert place.plan_for(_settings(tmp_path)) is plan and asked == [1]


def test_a_plan_that_cannot_be_judged_is_as_the_settings_say(tmp_path, monkeypatch):
    monkeypatch.setattr(place, "gather", lambda settings, memory=None, own=None, ask=True: 1 / 0)
    assert place.plan_for(_settings(tmp_path)) == Plan(why=place.NO_GPU)


# ------------------------------------------------------------------ where the readers run
def test_the_readers_go_where_the_plan_has_them(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    assert place.readers_placement(_settings(tmp_path, ocr_runs_on="cpu"), cuda=True) == Placement("cpu", place.SET)
    for value in place.SETTING_VALUES:
        assert place.readers_placement(_settings(tmp_path, ocr_runs_on=value), cuda=False).device == "cpu"
    assert place.readers_placement(_settings(tmp_path, ocr_runs_on="gpu"), cuda=True) == Placement("gpu", place.SET)
    place.settle(judge(_card(1000), _needs()))
    assert place.readers_placement(s, cuda=True) == Placement("gpu", place.ROOM, place.session().left)
    place.settle(judge(_card(2000), _needs(), "processor"))
    assert place.readers_placement(s, cuda=True) == Placement("cpu", place.PROCESSOR, place.session().left)
    place.settle(judge(_card(1000), _needs(ocr=0)))  # (set to "cpu" at the start, "auto" since: not counted)
    assert place.readers_placement(s, cuda=True) == Placement("cpu", place.UNKNOWN)
    place.settle(Plan(why=place.NO_GPU))  # (CUDA, but no figures of the card: as before, the CPU)
    assert place.readers_placement(s, cuda=True) == Placement("cpu", place.UNKNOWN)
    place.failed(READERS, "CudaError")
    assert place.readers_placement(_settings(tmp_path, ocr_runs_on="gpu"), cuda=True) == Placement(
        "cpu", place.FAILED, error="CudaError")


def test_the_suite_never_measures_this_machine(tmp_path):
    assert place.readers_placement(_settings(tmp_path), cuda=True) == Placement("cpu", place.UNKNOWN)
    assert place.session().why == place.NO_GPU


# ------------------------------------------------------------------ a reader's networks on a device
class FakeModels(DeviceModels):
    """A reader with networks that are names: "net@cpu", and a copy "net@<device>" that fails while *broken*."""

    def __init__(self, name="fake"):
        super().__init__()
        self.name = name
        self._cpu_models = ("net@cpu",)
        self.broken = False
        self.copy_fails = False
        self.error: type[RuntimeError] = MemoryError_  # what a broken GPU raises
        self.reads: list[str] = []

    def _copy_to(self, device):
        if self.copy_fails:
            raise RuntimeError("CUDA out of memory")
        return (f"net@{device}",)

    def read(self, value="x"):
        def on(device, models):
            self.reads.append(models[0])
            if device != "cpu" and self.broken:
                raise self.error("CUDA out of memory. Tried to allocate" if self.error is MemoryError_
                                 else "CUDA error: an illegal memory access was encountered")
            return f"{value} read with {models[0]}"

        return self.run(on)


class MemoryError_(RuntimeError):  # (torch.cuda.OutOfMemoryError is a RuntimeError)
    pass


class CudaError_(RuntimeError):  # (a CUDA error is a RuntimeError too)
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


@pytest.mark.parametrize("error", [MemoryError_, CudaError_])
def test_a_failure_on_the_gpu_reads_that_crop_on_the_cpu_and_stays_there_for_the_session(given_back, error):
    told = []
    m = FakeModels("nar")
    m.on_gpu_failure = lambda reader, why: told.append((reader, why))
    m.to("cuda")
    m.broken, m.error = True, error
    assert m.read("crop") == "crop read with net@cpu"  # the page is never failed
    assert m.reads == ["net@cuda", "net@cpu"] and m.device == "cpu"
    assert m.gpu_failed == error.__name__ and told == [("nar", error.__name__)]
    m.broken = False
    assert not m.to("cuda") and m.device == "cpu"  # (never again this session)


def test_only_the_memory_running_out_is_out_of_memory():
    class OutOfMemoryError(RuntimeError):  # (torch.cuda's, by its name)
        pass

    assert place.out_of_memory(OutOfMemoryError("Tried to allocate 20.00 MiB"))
    assert place.out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
    assert place.out_of_memory(RuntimeError("CUDA error: CUBLAS_STATUS_ALLOC_FAILED when calling `cublasCreate(handle)`"))
    assert not place.out_of_memory(RuntimeError("CUDA error: an illegal memory access was encountered"))


def _short_start() -> Plan:
    """The session's plan of a start short of room that went on all the same (a setting forced the readers onto the
    GPU): left at the peak under the margin."""
    return place.settle(judge(_card(2000), _needs(fixed=(READERS,))))


def test_where_the_start_was_short_while_the_translator_computes_they_read_on_the_cpu_and_keep_the_gpu_s_copy(
        given_back):
    plan = _short_start()
    assert plan.why == place.SHORT and plan.left < MARGIN_MIB and not place.plain_beside_requests()
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


def test_a_copy_without_graphs_reads_on_the_gpu_through_a_request_wherever_the_plan_has_room(given_back):
    """The plain pass on the GPU beside the translator's requests read a made-up unit of 44 crops in 3.2 s against
    21.0 on the processor (2026-11-28): it needs no memory beyond the copy's own, counted in the readers' need, so it
    stays on the GPU wherever the start's plan has room for what it put there - its graphs left off for the room or
    not -, and without a plan; only a start short of room that went on all the same (forced, or nothing could go)
    reads on the processor meanwhile, and so does every copy without graphs with the tool's switch off."""
    m = FakeModels()
    m.to("cuda")
    assert place.session() is None and place.plain_beside_requests()  # (no plan: a tool's readers, a test)
    with place.translating():
        assert m.read() == "x read with net@cuda"
    bare = place.settle(judge(_card(1535), _needs(graphs=READERS_GRAPHS_MIB)))  # (the graphs left off for the room)
    assert bare.why == place.ROOM and not bare.graphs and place.plain_beside_requests()
    with place.translating():
        assert m.read() == "x read with net@cuda" and m.device == "cuda"
    moved = place.settle(judge(_card(1805), _needs(fixed=(READERS,)), "processor"))  # (LaMa sent there: room again)
    assert moved.why == place.PROCESSOR and moved.left >= MARGIN_MIB and place.plain_beside_requests()
    still = place.settle(judge(_card(5000), _needs(fixed=(READERS,)), "processor"))  # (all that could go went: short)
    assert still.why == place.PROCESSOR and still.left < MARGIN_MIB and not place.plain_beside_requests()
    with place.translating():
        assert m.read() == "x read with net@cpu" and m.device == "cuda"
    place.settle(Plan(why=place.NO_GPU))  # (nothing judged)
    assert place.plain_beside_requests()
    place.settle(bare)
    try:
        place.PLAIN_BESIDE = False  # (the tool's switch: the rule before)
        assert not place.plain_beside_requests()
        with place.translating():
            assert m.read() == "x read with net@cpu"
    finally:
        place.PLAIN_BESIDE = True
    assert m.reads == ["net@cuda", "net@cuda", "net@cpu", "net@cpu"] and not given_back


def test_a_failure_on_the_gpu_through_a_request_reads_that_crop_on_the_cpu_and_stays_there(given_back):
    """What the person sees when the GPU fails under a plain pass beside a request (out of memory, a CUDA error):
    the crop read again on the CPU at once, the same reading, the page going on; the readers on the CPU for the rest
    of the session, said to the readers' owner (the System page)."""
    told = []
    m = FakeModels("charspot")
    m.on_gpu_failure = lambda reader, why: told.append((reader, why))
    m.to("cuda")
    m.broken = True
    with place.translating():
        assert m.read("crop") == "crop read with net@cpu"
    assert m.reads == ["net@cuda", "net@cpu"] and m.device == "cpu" and told == [("charspot", "MemoryError_")]
    m.broken = False
    assert m.read() == "x read with net@cpu" and not m.to("cuda")


class GraphedModels(FakeModels):
    """A fake reader whose GPU copy holds its CUDA graphs (one kept), as charspot's and nar's do."""

    def _copy_to(self, device):
        from taslation.ocr import graphs

        self.graphs = graphs.Graphs(self.name, None)
        self.graphs._graphs["pass"] = ("graph", (), (), lambda: ())
        return (f"net@{device}", self.graphs)


def test_a_copy_with_its_cuda_graphs_reads_on_the_gpu_while_the_translator_computes_even_where_the_start_was_short(
        given_back, tmp_path):
    """A graph's replay is one launch, which takes its turn on the GPU beside the translator's work: the copy with
    graphs stays on the GPU through a request, also where the start was short; there one whose graphs were dropped (a
    replay failed) or were never captured reads on the CPU meanwhile, as before - and on the GPU where the plan has
    room. The analysis log counts each read by device, those begun while a request was under way apart (on the GPU
    through it, on the CPU for it)."""
    from taslation import analysis

    _short_start()
    m = GraphedModels("charspot")
    m.to("cuda")
    assert place.graphed(m._gpu[1]) and not place.graphed(("net@cuda", None))
    analysis.start(tmp_path, "on")
    try:
        page = analysis.begin(None, None)
        with analysis.unit_span(1, beside=True):
            with place.translating():
                assert m.read() == "x read with net@cuda"
                m.graphs.drop()  # (a replay failed: the plain pass from now on)
                assert not place.graphed(m._gpu[1]) and m.read() == "x read with net@cpu"
            assert m.read() == "x read with net@cuda"
            place.settle(judge(_card(1000), _needs()))  # (a plan with room)
            with place.translating():
                assert m.read() == "x read with net@cuda"
        (unit,) = analysis.end(page, None)["read_units"]
        counted = unit["readers"]["charspot"]
        assert (counted["gpu"], counted["cpu"], counted["cpu_translating"], counted["gpu_translating"]) == (3, 1, 1, 2)
    finally:
        analysis.stop()
    _short_start()
    plain = FakeModels("nar")
    plain.to("cuda")
    with place.translating():
        assert plain.read() == "x read with net@cpu"  # (no graphs, the start short: on the CPU while it computes)


def test_a_copy_that_cannot_be_made_leaves_it_on_the_cpu_for_the_session(given_back):
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


def test_reads_that_are_slow_on_the_gpu_never_move_anything(given_back):
    """No look at the reads' times: a crawl on a card filled past its size took 1.5-1.9 times the CPU's, below any
    factor a wait behind this process's own page models does not reach."""
    m = FakeModels()
    m.to("cuda")

    def slow(device, models):
        time.sleep(0.002)
        return models[0]

    assert all(m.run(slow) == "net@cuda" for _ in range(20)) and m.device == "cuda" and not m.gpu_failed
    for gone in ("LOOK_S", "SLOW_READS", "RETURN_MIB", "STEP_MIB", "loading", "busy", "partly_loaded", "decide",
                 "keeps_through_loads", "full_window_placements"):
        assert not hasattr(place, gone), gone


# ------------------------------------------------------------------ the readers
class FakeEngine(FakeModels):
    def __init__(self, model_dir, threads=0):
        super().__init__(Path(model_dir).name)

    def read_chars(self, image):
        return readers.CharspotReading(self.read(), score=1.0)


@pytest.fixture
def fake_readers(monkeypatch, given_back):
    """`Readers` over stand-in engines (all three installed) and a stand-in placement that records what it was
    asked."""
    from taslation.ocr import cpt, nar

    monkeypatch.setattr(readers, "CharspotEngine", FakeEngine)
    monkeypatch.setattr(readers, "missing_readers", lambda models_dir: [])
    monkeypatch.setattr(nar, "NarEngine", FakeEngine)
    monkeypatch.setattr(cpt, "CptEngine", FakeEngine)
    rule = SimpleNamespace(answer=Placement("gpu", place.ROOM, 1500), asked=[])

    def placed(settings, cuda=None):
        rule.asked.append(settings.ocr_runs_on)
        return rule.answer

    monkeypatch.setattr(place, "readers_placement", placed)
    return rule


def test_the_readers_are_placed_where_they_load(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    assert fake_readers.asked == ["auto"] and ocr.placement == Placement("gpu", place.ROOM, 1500)
    assert ocr.charspot.device == "cuda" and ocr._nar.device == "cuda" and ocr._cpt.device == "cpu"  # CPT stays
    assert ocr.gpu_mib() == OCR + READERS_GRAPHS_MIB and ocr.holds_gpu()


def test_readers_without_settings_stay_on_the_cpu_and_ask_nothing(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0)
    ocr.read_chars(None)
    assert not fake_readers.asked and ocr.charspot.device == "cpu" and ocr.placement.why == place.NOT_ASKED


def test_readers_loaded_first_are_placed_once_they_are_given_the_settings(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0)
    assert readers.place_with(ocr, _settings(tmp_path)) is ocr
    assert fake_readers.asked == ["auto"] and ocr.charspot.device == "cuda" and ocr._nar.device == "cuda"
    stand_in = SimpleNamespace(missing=[])
    assert readers.place_with(stand_in, _settings(tmp_path)) is stand_in and len(fake_readers.asked) == 1


def test_the_command_line_s_readers_are_placed_with_its_settings(tmp_path, fake_readers):
    from taslation import cli

    ocr = cli.build_ocr(_settings(tmp_path, ocr_runs_on="gpu"))
    assert fake_readers.asked == ["gpu"] and ocr.settings.ocr_runs_on == "gpu"


def test_nothing_moves_them_while_reading(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    fake_readers.answer = Placement("cpu", place.PROCESSOR, 0)  # (were it asked again, it would move them)
    for _ in range(5):
        ocr.read_chars(None)
        ocr.settle(None, readers.CharspotReading("x", score=1.0))
    assert fake_readers.asked == ["auto"] and ocr.charspot.device == "cuda"


def test_a_release_puts_them_on_the_cpu_and_the_next_read_back_where_the_plan_has_them(tmp_path, fake_readers,
                                                                                       given_back):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr.release_gpu()
    assert ocr.placement.why == place.RELEASED and ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    assert given_back and len(fake_readers.asked) == 1 and not ocr.holds_gpu()
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2 and ocr.charspot.device == "cuda" and ocr.placement.why == place.ROOM
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2


def test_a_setting_that_fixes_their_place_takes_them_there_from_the_next_read(tmp_path, fake_readers):
    from taslation.ui import app as app_mod

    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    app_mod.App._settings_saved(SimpleNamespace(settings=s), {"ocr_runs_on": "cpu"})  # (Settings... > Save)
    fake_readers.answer = Placement("cpu", place.SET)
    ocr.read_chars(None)
    assert fake_readers.asked[-1] == "cpu" and ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    s.target_language = "Turkish"  # (another language, another model: judged at the next start, nothing moves)
    ocr.read(None)
    assert len(fake_readers.asked) == 2


@pytest.mark.parametrize("error", [MemoryError_, CudaError_])
def test_a_failure_of_one_reader_puts_both_on_the_cpu_for_the_session(tmp_path, fake_readers, error):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr._nar.broken, ocr._nar.error = True, error
    assert ocr._nar.read("y") == "y read with net@cpu"  # that crop read on the CPU
    assert ocr.placement == Placement("cpu", place.FAILED, error=error.__name__)
    assert ocr.charspot.device == "cpu" and ocr._nar.device == "cpu" and place.failure(READERS) == error.__name__
    ocr.release_gpu()
    ocr.settings.ocr_runs_on = "gpu"
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr.charspot.device == "cpu"  # never placed again this session


def test_the_pipeline_lets_the_readers_go_with_the_page_models(tmp_path, fake_readers, given_back):
    from taslation.pipeline import Pipeline

    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    p = Pipeline(_settings(tmp_path, cache_enabled=False, art_erase="off", detect_model="off"), ocr=ocr,
                 translator=SimpleNamespace(model="m"))
    assert ocr.release_gpu in p.gpu_releases
    p.release_gpu_models()
    assert ocr.charspot.device == "cpu" and ocr.placement.why == place.RELEASED


def test_a_load_of_the_translation_model_lets_nothing_go(tmp_path, fake_readers, ollama):
    """The model was counted whole beside the rest at the start, and Ollama loads it whole there: nothing is let go
    before a load, nothing decided after it."""
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    p = Pipeline(_settings(tmp_path, cache_enabled=False, art_erase="off", detect_model="off"), ocr=ocr, translator=tr)
    assert p.translator is tr and not hasattr(tr, "before_load")
    tr.ensure_loaded()
    assert ollama.loads and ocr.charspot.device == "cuda" and ocr._nar.device == "cuda" and fake_readers.asked == ["auto"]


def test_a_streamed_request_is_a_request_to_its_end(tmp_path, ollama):
    from taslation.translate import OllamaTranslator

    ollama.between = 0.02
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    seen = []
    tr.translate_page(["はい", "いいえ", "そう"], on_item=lambda i, text: seen.append(place._translating),
                      cancel=threading.Event())
    assert seen == [1, 1, 1] and place._translating == 0


def test_plamo_s_lines_are_requests_and_its_warm_up_none(monkeypatch):
    from taslation.translate.plamo import PlamoTranslator

    tr = PlamoTranslator("http://127.0.0.1:9", timeout=1.0)
    seen = []

    def request(path, payload=None, timeout=None):
        seen.append((bool(payload.get("prompt")), place._translating))
        return {"response": "EN", "done": True}

    def stream(path, payload, on_text, cancel=None, on_slow=None, timeout=None, **_bounds):
        seen.append((bool(payload.get("prompt")), place._translating))
        return {"message": {"content": "EN"}, "done": True}

    monkeypatch.setattr(tr, "_request", request)
    monkeypatch.setattr(tr, "_stream", stream)
    monkeypatch.setattr(tr, "ensure_loaded", lambda cancel=None, on_slow=None, quiet=False: None)
    tr.warm_up()
    tr._generate("a prompt", 16)
    tr._generate("a prompt", 16, cancel=threading.Event())
    assert seen == [(False, 0), (True, 1), (True, 1)] and place._translating == 0


# ------------------------------------------------------------------ where it is said
def test_where_the_ocr_runs_is_the_settings_file_s_alone(hidden_root, tmp_path, monkeypatch):
    """``ocr_runs_on`` left the System page: a file that sets it loads, the readers go where it says, the OCR's row
    says so, and the dialog neither shows nor writes it."""
    from taslation.ui.dialogs import settings as dlg

    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    path = tmp_path / "taslation.toml"
    path.write_text('ocr_runs_on = "cpu"\n', encoding="utf-8")
    in_force = Settings.from_toml(path).with_overrides(state_dir=tmp_path / "state", models_dir=tmp_path / "models")
    assert in_force.ocr_runs_on == "cpu" and in_force.ignored_keys == ()
    assert set(place.SETTING_VALUES) == {"auto", "cpu", "gpu"}
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert "ocr_runs_on" not in d.values() and not hasattr(d.system, "ocr_runs_on")
    row = _ocr_row(in_force)
    assert row.device == "cpu" and row.note == "As set in ocr_runs_on"


def test_the_system_page_shows_and_saves_what_a_short_start_does(hidden_root, tmp_path, monkeypatch):
    from taslation.ui.dialogs import settings as dlg

    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    in_force = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.system.gpu_short.get() is False and d.values()["gpu_short"] == "ask"
    d.system.gpu_short.set(True)
    assert d.save() is True and got == [{"gpu_short": "processor"}]
    assert Settings.from_toml(in_force.config_path).gpu_short == "processor"
    d.destroy()
    in_force.gpu_short = "processor"
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.system.gpu_short.get() is True
    d.system.gpu_short.set(False)
    assert d.save() is True and got[-1] == {"gpu_short": "ask"}


def _ocr_row(settings, ocr=None, cuda=True):
    return stage_devices(settings, SimpleNamespace(model="m", _loaded=lambda model: None), cuda=cuda, gpu=GPU,
                         ocr=ocr)[1]


READER_NAMES = ("manga-ocr-charspot-small", "manga-ocr-nar-small", "manga-ocr-base-CPT-flex")


def test_the_system_page_says_where_the_readers_are_and_why(tmp_path):
    """Each reader by its name, with where it reads when two of them are on the GPU (CPT on the CPU always); the note
    says why they are where they are, nothing where the GPU had room."""
    s = _settings(tmp_path)

    def row(*a, missing=(), **k):
        return _ocr_row(s, SimpleNamespace(placement=Placement(*a, **k), settings=s, missing=list(missing)))

    on = row("gpu", place.ROOM, 1500)
    assert on.where() == f"GPU ({GPU})" and on.note == ""
    assert on.models == ("manga-ocr-charspot-small (GPU)", "manga-ocr-nar-small (GPU)", "manga-ocr-base-CPT-flex (CPU)")
    alone = row("gpu", place.ROOM, 1500, missing=["manga-ocr-nar-small"])  # (an install from before the three)
    assert alone.models == ("manga-ocr-charspot-small (GPU)",)
    failed = row("cpu", place.FAILED, error="CudaError")
    assert failed.where() == "CPU" and failed.models == READER_NAMES
    assert failed.note == "On the CPU since the GPU failed (CudaError)"
    short = row("cpu", place.PROCESSOR, 300)
    assert short.where() == "CPU" and short.note == "The GPU's memory was short at the start"
    assert row("cpu", place.RELEASED).note == "The GPU memory was let go; the next page puts them back"
    assert row("cpu", place.UNKNOWN).note == "The room on the GPU is not known"
    assert row("cpu", place.NO_CUDA).note == "" and row("cpu", place.NO_CUDA).models == READER_NAMES


def test_without_loaded_readers_the_plan_is_asked_now(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    no_gpu = _ocr_row(s, cuda=False)  # no GPU: as ever (charspot alone in an empty models folder)
    assert no_gpu.models == ("manga-ocr-charspot-small",) and no_gpu.note == ""
    assert _ocr_row(_settings(tmp_path, ocr_runs_on="cpu")).note == "As set in ocr_runs_on"
    assert place.session().why == place.NO_GPU  # (made by the row above: the suite's facts are none)
    place.reset()
    monkeypatch.setattr(place, "gather", lambda settings, memory=None, own=None, ask=True: _card(1000))
    monkeypatch.setattr(place, "needs", lambda settings, cuda=None, ask=True: _needs())
    row = _ocr_row(s)
    assert row.device == "gpu" and row.gpu == GPU
    old = SimpleNamespace(settings=None)  # (readers loaded without settings, as a caller of before)
    assert _ocr_row(s, old).where() == "CPU" and _ocr_row(s, old).note == ""


def test_the_page_models_rows_follow_the_plan(tmp_path, monkeypatch):
    from taslation.detect import layout
    from taslation.render import artwork

    monkeypatch.setattr(artwork, "available", lambda models_dir, setting="auto", cuda=None: True)
    monkeypatch.setattr(layout, "available", lambda models_dir: True)
    s = _settings(tmp_path)
    place.settle(judge(_card(1000), _needs()))
    rows = stage_devices(s, SimpleNamespace(model="m", _loaded=lambda model: None), cuda=True, gpu=GPU)
    assert rows[0].device == "gpu" and rows[3].device == "gpu"
    place.settle(judge(_card(2700), _needs(), "processor"))  # (the readers and LaMa to the processor)
    rows = stage_devices(s, SimpleNamespace(model="m", _loaded=lambda model: None), cuda=True, gpu=GPU)
    assert rows[0].device == "gpu" and rows[3].device == "cpu"
    place.failed(LAYOUT, "OutOfMemoryError")
    rows = stage_devices(s, SimpleNamespace(model="m", _loaded=lambda model: None), cuda=True, gpu=GPU)
    assert rows[0].device == "cpu"


def test_the_note_under_the_list_says_what_the_start_found_short_and_what_failed(tmp_path):
    from taslation.i18n import set_language

    assert devices.plan_text() == ""  # (no plan)
    place.settle(judge(_card(1000), _needs()))
    assert devices.plan_text() == ""  # (enough, nothing failed)
    place.settle(judge(_card(2700), _needs(), "processor"))  # (short by 896 MiB: the readers and LaMa go)
    assert devices.plan_text() == devices.PLAN_SHORT.format(
        mb=900, parts="the OCR readers, the erase model on the art (LaMa)")
    place.settle(judge(_card(2000), _needs(fixed=(TRANSLATOR, READERS, LAMA, LAYOUT))))
    assert devices.plan_text() == devices.PLAN_FIXED.format(mb=200)
    place.failed(LAYOUT, "OutOfMemoryError")
    assert devices.plan_text().splitlines()[-1] == devices.PLAN_FAILED.format(parts="the layout model")
    lines = devices.lines(_settings(tmp_path), translator=SimpleNamespace(model="m", _loaded=lambda model: None),
                          cuda=False, gpu="")  # (`taslation doctor`)
    assert lines[-2].strip() == devices.PLAN_FAILED.format(parts="the layout model")
    set_language("ja")
    try:
        assert "200 MB" in devices.plan_text() and "VRAM" in devices.plan_text()
    finally:
        set_language("en")
    assert devices.short_mb(1) == 10 and devices.short_mb(296) == 300 and devices.short_mb(300) == 300


def test_the_start_s_dialog_is_refused_in_a_test_that_does_not_ask_for_it():
    """(conftest's `no_gpu_dialog_unless_asked`: the window tests never meet it - their facts are none, as without an
    NVIDIA GPU - and one that would is refused; tests/test_gpu_short_dialog.py asks for it)"""
    from taslation.ui.dialogs import gpu_short

    assert gpu_short.GpuShortDialog.__init__.__name__ == "refused"


def test_the_new_lines_are_in_every_language():
    from taslation.i18n import FEATURE_LANGUAGES
    from taslation.locales.features import gpu_start, ocr_on_gpu
    from taslation.ui.dialogs import gpu_short, system_page
    from taslation.ui import status_slot

    assert sorted(ocr_on_gpu.TEXTS) == sorted(devices.OCR_NOTES.values())
    for key in devices.OCR_NOTES.values():
        assert sorted(ocr_on_gpu.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key
    keys = (gpu_short.TEXT, gpu_short.ON_PROCESSOR, gpu_short.AGAIN, gpu_short.PROCESSOR, gpu_short.QUIT,
            gpu_short.REMEMBER, gpu_short.OURS_LOADED, gpu_short.THEIRS_LOADED, gpu_short.MODEL_MB, gpu_short.RELEASE,
            *devices.PART_NAMES.values(), ", ", status_slot.MODELS_KEY, devices.PLAN_SHORT,
            devices.PLAN_FIXED, devices.PLAN_FAILED, system_page.GPU_SHORT_LABEL, system_page.GPU_SHORT_TEXT)
    assert sorted(gpu_start.TEXTS) == sorted(keys)
    for key in keys:
        assert sorted(gpu_start.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key
    assert gpu_start.TEXTS[gpu_short.TEXT]["ja"] == (
        "VRAM の空き容量が {mb} MB 不足しています。GPU を使っているほかのアプリケーションを閉じて「もう一度確認」を押すか、"
        "CPU モードで起動してください（遅くなります）。")
    assert gpu_start.TEXTS[status_slot.MODELS_KEY]["ja"] == "モデルを読み込んでいます..."


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


# ------------------------------------------------------------------ the window cache of the Ollama TASlation starts
def test_the_window_cache_is_the_settings_file_s_alone_and_the_report_says_what_the_server_got(hidden_root, tmp_path,
                                                                                               monkeypatch):
    """``ollama_window_cache`` left the System page: a file that sets it loads and the dialog neither shows nor writes
    it; what the server TASlation started got is in Copy a report's server line (`ui.report`), not on the page."""
    from taslation import errorlog, ollama_start
    from taslation.ollama_start import WHY_SET, WHY_SETTING, ServerSetup
    from taslation.ui import report
    from taslation.ui.dialogs import settings as dlg

    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama: not asked in the tests")
    monkeypatch.setattr(ollama_start, "own_server", lambda url: None)
    path = tmp_path / "taslation.toml"
    path.write_text('ollama_window_cache = "off"\n', encoding="utf-8")
    in_force = Settings.from_toml(path).with_overrides(state_dir=tmp_path / "state", models_dir=tmp_path / "models")
    assert in_force.ollama_window_cache == "off" and in_force.ignored_keys == ()
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert "ollama_window_cache" not in d.values() and not hasattr(d.system, "window_cache")
    s = _settings(tmp_path)
    translator = SimpleNamespace(model="m", _loaded=lambda model: None)
    app = SimpleNamespace(settings=s, pipeline=None)
    for setup, said in ((None, "its own settings"),
                        (ServerSetup("q8_0", True, "256", WHY_SETTING), "cloud features off; window cache on"),
                        (ServerSetup("f16", False, "0", WHY_SETTING), "cloud features off; window cache off"),
                        (ServerSetup("f16", False, "0", WHY_SET), "cloud features off; window cache off"),
                        (ServerSetup("q8_0", False, "0", "readers"), "cloud features off; window cache off")):
        monkeypatch.setattr(ollama_start, "setup_of", lambda url, state_dir=None, setup=setup: setup)
        assert devices._translator_device(s, translator, GPU).models == ("m",)  # (the page names the model alone)
        server = next(line for line in report.program_lines(app) if line.startswith("server = "))
        assert f"; {said}; " in server, server


def test_the_window_cache_is_the_setting_s_alone_and_counted_at_its_real_size(tmp_path, monkeypatch):
    """The server's window cache is never dropped for the room: it is as ``ollama_window_cache`` says (or the
    computer's own variable), and the judgement at the start counts the model with it."""
    from taslation import ollama_start

    monkeypatch.setattr(place, "gather", lambda *a, **k: pytest.fail("the room was asked for the window cache"))
    assert ollama_start.window_choice(_settings(tmp_path)) is True
    assert ollama_start.window_choice(_settings(tmp_path, ollama_window_cache="on")) is True
    assert ollama_start.window_choice(_settings(tmp_path, ollama_window_cache="off")) is False
