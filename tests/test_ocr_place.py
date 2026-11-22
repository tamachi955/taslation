"""Where the OCR readers run (`taslation.ocr.place`): on the GPU when it has room for them at TASlation's peak - the
translation model whole in video memory, the page models in use, this process's context, what other programs hold, a
margin - else on the CPU; the setting ``ocr_runs_on``; a decision made when the readers load and again once the GPU
memory was let go or a setting changed; a GPU that fails moves them to the CPU for the session, the crop at hand read
there; the System page and ``taslation doctor`` say where they are and why. Everything here uses stand-ins: no GPU,
no model, no Ollama but the fake one."""

from __future__ import annotations

import dataclasses
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
                                 NAR_MIB, DeviceModels, GpuFacts, Placement, decide, judge, room_left, through_load)

OCR = CHARSPOT_MIB + NAR_MIB
PLAMO = KNOWN_TRANSLATORS[("taslation-plamo3-translate-2b", 8192)][("q8_0", False)][0]  # (the 6 GB card's server)
QWEN = KNOWN_TRANSLATORS[("qwen3.5:4b", 16384)][("q8_0", False)][0]
GPU = "NVIDIA Test GPU"
REAL_GATHER = place.gather  # (taken before conftest's stand-in is put in its place for every test)


@pytest.fixture(autouse=True)
def nothing_learnt():
    place._learnt.clear()
    place._kept, place._keeps = False, True
    yield
    place._learnt.clear()
    place._kept, place._keeps = False, True


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


def test_just_before_a_load_the_readers_on_the_gpu_count_once():
    """The facts the release before a load judges on (`through_load`): the model not loaded, the page models let go,
    the readers on the GPU - in the card's used memory and in this process's own alike (its context and torch's 120
    MiB for them now), so that they count once, as the rule's *ocr* at their peak. Ollama then finds the model's need
    and the margin free."""
    others, readers_now = 1325, 120
    before = GpuFacts(total=6144, used=others, translator=PLAMO, lama=True)  # (the readers never on the GPU yet)
    loading = GpuFacts(total=6144, used=others + CONTEXT_MIB + readers_now, own=CONTEXT_MIB + readers_now,
                       translator=PLAMO, translator_now=0, lama=True)
    peak = CONTEXT_MIB + PLAMO + LAMA_MIB + OCR
    assert peak == 100 + 2000 + 680 + 420 == 3200
    assert room_left(loading, OCR) == 6144 - others - peak == 1619 == room_left(before, OCR)
    assert room_left(loading, OCR) != 6144 - (others + readers_now) - peak  # (twice: in the others' memory too)
    assert room_left(loading, OCR) != 6144 - others - (peak - OCR)  # (none: their peak left out)
    kept = through_load(loading, OCR)
    assert kept == Placement("gpu", place.ROOM, 1619)
    assert loading.total - loading.used == 4599 >= PLAMO + MARGIN_MIB  # what is free at the load
    # another model in Ollama, of another program's, counts as other programs' memory: no room, let go
    crowded = GpuFacts(total=6144, used=loading.used + 1500, own=loading.own, translator=PLAMO, lama=True)
    assert room_left(crowded, OCR) == 1619 - 1500 and through_load(crowded, OCR).device == "cpu"
    # readers kept through a load are readers on the GPU: they stay down to the margin, not the return mark
    edge = dataclasses.replace(loading, used=loading.used + 1619 - MARGIN_MIB)
    assert through_load(edge, OCR) == Placement("gpu", place.ROOM, MARGIN_MIB)
    assert through_load(dataclasses.replace(edge, used=edge.used + 1), OCR).device == "cpu"


def test_the_margin_is_the_driver_s_part_and_other_programs_sway_and_the_return_mark_one_step_more():
    """Readers on the CPU go to the GPU from `RETURN_MIB` left at the peak, readers there stay down to `MARGIN_MIB`:
    other programs' usual swing (`STEP_MIB`) moves them neither way."""
    assert MARGIN_MIB == place.FLOOR_MIB + place.SWAY_MIB == 490 + 220
    assert place.RETURN_MIB == MARGIN_MIB + place.STEP_MIB == MARGIN_MIB + 100
    base = GpuFacts(total=6144, used=0, translator=PLAMO, lama=True, layout=True)

    def at(room, staying):
        return judge(dataclasses.replace(base, used=6144 - place.peak_mib(base, OCR) - room), OCR, staying)

    assert at(place.RETURN_MIB, False) == Placement("gpu", place.ROOM, place.RETURN_MIB)
    assert at(place.RETURN_MIB - 1, False) == Placement("cpu", place.NO_ROOM, place.RETURN_MIB - 1)
    assert at(MARGIN_MIB, True) == Placement("gpu", place.ROOM, MARGIN_MIB)
    assert at(MARGIN_MIB - 1, True) == Placement("cpu", place.NO_ROOM, MARGIN_MIB - 1)
    for room in range(MARGIN_MIB, place.RETURN_MIB):
        assert at(room, True).device == "gpu" and at(room, False).device == "cpu", room
    edge = dataclasses.replace(base, used=6144 - place.peak_mib(base, OCR) - MARGIN_MIB)
    assert decide(Settings(), OCR, cuda=True, facts=lambda s: edge, staying=True).device == "gpu"
    assert decide(Settings(), OCR, cuda=True, facts=lambda s: edge).device == "cpu"


def test_the_readers_are_counted_at_their_measured_peak():
    """Torch's reserved memory at the readers' peak (2026-11-22, 509 and 206 crops and the largest made-up ones):
    charspot alone 124 MiB, both 410; rounded up to 10 MiB, nothing added (their inputs are bounded)."""
    assert CHARSPOT_MIB == 130 and CHARSPOT_MIB + NAR_MIB == 420 and CONTEXT_MIB == 100


def test_the_measured_card_has_room_beside_plamo_and_both_page_models():
    """The 6 GB card with the layout model and LaMa on the GPU (their default there), its screen 1080 px high and
    1343 MiB held by other programs: room for the readers; above 1704 MiB of them not, and on a screen taller than
    1440 px (LaMa's larger windows) above 1414."""
    facts = GpuFacts(total=6144, used=1343, translator=PLAMO, lama=True, layout=True)
    assert place.peak_mib(facts, OCR) == 100 + 2000 + 680 + 430 + 420 == 3630
    assert judge(facts, OCR) == Placement("gpu", place.ROOM, 1171)
    assert judge(GpuFacts(total=6144, used=1704, translator=PLAMO, lama=True, layout=True), OCR).device == "gpu"
    assert judge(GpuFacts(total=6144, used=1705, translator=PLAMO, lama=True, layout=True), OCR).device == "cpu"
    tall = GpuFacts(total=6144, used=1343, translator=PLAMO, lama=True, layout=True, tall_screen=True)
    assert judge(tall, OCR) == Placement("gpu", place.ROOM, 1171 - (place.LAMA_TALL_MIB - LAMA_MIB)) \
        and 1171 - 290 == 881
    assert judge(dataclasses.replace(tall, used=1414), OCR).device == "gpu"
    assert judge(dataclasses.replace(tall, used=1415), OCR).device == "cpu"
    # a tall screen with LaMa off counts nothing for it
    assert place.peak_mib(GpuFacts(total=6144, used=0, translator=PLAMO, tall_screen=True), OCR) == 100 + 2000 + 420


def test_a_screen_taller_than_1440_px_or_not_known_counts_lama_s_larger_windows(monkeypatch):
    for height, tall in ((1080, False), (1440, False), (1600, True), (2160, True), (None, True)):
        monkeypatch.setattr(devices, "screen_height_px", lambda height=height: height)
        assert place.tall_screen() is tall


def test_the_screen_s_height_is_read_without_a_window(monkeypatch):
    height = devices.screen_height_px()
    assert height is None or height >= 240  # (whatever this computer's screens are; None off Windows)
    monkeypatch.setattr(devices.sys, "platform", "linux")
    assert devices.screen_height_px() is None


def test_the_facts_ask_the_screen_only_for_lama_on_the_gpu(tmp_path, monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 1325))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    monkeypatch.setattr(place, "_translator_need", lambda s, cache=None, ask=True: (PLAMO, 0, True))
    asked = []
    monkeypatch.setattr(devices, "screen_height_px", lambda: asked.append(1) or 2160)
    for lama, layout in ((True, True), (False, False)):
        monkeypatch.setattr(place, "page_models_on_gpu", lambda s, lama=lama, layout=layout: (lama, layout))
        facts = REAL_GATHER(_settings(tmp_path))
        assert facts.tall_screen is lama
    assert asked == [1]


def test_a_check_before_a_load_needs_every_fact_measured():
    assert through_load(None, OCR) == Placement("cpu", place.UNKNOWN)  # no card memory
    assert through_load(GpuFacts(total=6144, used=1325, translator=None), OCR) == Placement("cpu", place.UNKNOWN)
    unanswered = GpuFacts(total=6144, used=1325, translator=PLAMO, answered=False)
    assert judge(unanswered, OCR).device == "gpu"  # (the ordinary decision takes Ollama down for a model not loaded)
    assert through_load(unanswered, OCR) == Placement("cpu", place.UNKNOWN)


def test_the_facts_say_whether_ollama_answered(tmp_path, monkeypatch):
    monkeypatch.setattr(devices, "nvml_usage_mib", lambda: (6144, 1325))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    s = _settings(tmp_path, ollama_url="http://127.0.0.1:9")
    netguard.install(allowed_ports={9}, audit_hook=False)
    try:
        facts = REAL_GATHER(s)
    finally:
        netguard.uninstall()
    assert facts is not None and facts.translator == PLAMO and not facts.answered
    assert place._translator_need(_settings(tmp_path, ollama_num_gpu="0")) == (0, 0, True)  # (nothing to ask)


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
    assert place._translator_need(s) == (PLAMO, 0, True)  # (Ollama answered: none loaded)
    name = "taslation-plamo3-translate-2b"
    ollama.loaded.add(name)
    size = 3_000_000_000 // place.MiB  # (the fake's size)
    assert place.translator_need(s) == (size, size)  # loaded: what /api/ps says, all of it on the GPU
    ollama.loaded.clear()
    need, now = place.translator_need(s)
    assert now == 0 and need == round(size * place.RUNNER_SHARE)  # learnt, with the runner's own share
    assert not ollama.loads  # nothing was loaded to find out


def test_a_known_translator_of_the_size_it_was_measured_at_needs_what_was_measured(tmp_path, ollama):
    """PLaMo as /api/ps says it (1823 MiB): unloaded, it needs what its load was measured to add to the card's used
    memory (1933 MiB, 2000 counted), not its size with the largest runner's share (2279), which left this 6 GB card's
    readers on the CPU after the first unload."""
    s = _settings(tmp_path, ollama_url=ollama.url)
    ollama.loaded.add("taslation-plamo3-translate-2b")
    ollama.size = 1823 * place.MiB + 512 * 1024
    assert place.translator_need(s) == (1823, 1823)
    ollama.loaded.clear()
    assert place.translator_need(s) == (PLAMO, 0) == (2000, 0)
    ollama.loaded.add("taslation-plamo3-translate-2b")
    ollama.size = 1900 * place.MiB  # (a server with another cache: what that one was measured to add)
    place.translator_need(s)
    ollama.loaded.clear()
    assert place.translator_need(s) == (2100, 0)
    ollama.loaded.add("taslation-plamo3-translate-2b")
    ollama.size = 2500 * place.MiB  # (another build, larger than every cache measured: its size, the runner's share)
    place.translator_need(s)
    ollama.loaded.clear()
    assert place.translator_need(s) == (round(2500 * place.RUNNER_SHARE), 0)


PLAMO_NAME = "taslation-plamo3-translate-2b"
# what loading PLaMo added to the card's used memory and /api/ps's size, by the server's KV cache and window cache
# (Ollama 0.40.16, measured 2026-11-20): (KV type, full window) -> (MiB added, /api/ps bytes)
MEASURED = {("q8_0", False): (1933, 1912550194), ("q8_0", True): (2065, 2050500853),
            ("f16", False): (2009, 1972759429), ("f16", True): (2229, 2203446149)}


def test_plamo_is_counted_as_measured_for_each_kv_cache_and_window_cache():
    for cache, (added, size) in MEASURED.items():
        counted, ps = place.known_translator(PLAMO_NAME, 8192, cache)
        assert added <= counted < added + 100 and counted % 100 == 0, cache  # (rounded up to the next 100 MiB)
        assert size // place.MiB < ps and ps - size / place.MiB < 1, cache  # (/api/ps's size, rounded up)
    assert place.known_translator(PLAMO_NAME, 8192, ("q8_0", False)) == (2000, 1824)  # (today's figure kept)
    assert place.known_translator(PLAMO_NAME, 8192, ("q4_0", True)) == (2300, 2102)  # (a type not measured: f16's)
    assert place.known_translator(PLAMO_NAME, 4096, ("q8_0", False)) is None  # (another context: not measured)
    for cache in MEASURED:
        assert place.known_translator("qwen3.5:4b", 16384, cache) == (4000, 3203)  # (no windowed layers)


@pytest.mark.parametrize("cache", list(MEASURED))
def test_before_it_loads_plamo_needs_what_it_adds_on_the_server_it_runs_on(tmp_path, monkeypatch, ollama, cache):
    monkeypatch.setattr(place, "server_cache", lambda settings: cache)
    s = _settings(tmp_path, ollama_url=ollama.url)
    assert place.translator_need(s) == (place.known_translator(PLAMO_NAME, 8192, cache)[0], 0)
    assert place._translator_need(s, ("q8_0", False)) == (2000, 0, True)  # (a cache given: that one's)


@pytest.mark.parametrize("cache", list(MEASURED))
def test_seen_loaded_plamo_is_learnt_by_its_size_whoever_started_the_server(tmp_path, monkeypatch, ollama, cache):
    """/api/ps's size tells the caches apart: learnt at what that cache was measured to add, not at its size with the
    runner's largest share (2444 MiB for a full window with q8_0, which moved the 6 GB card's readers to the CPU at
    1.0 GB of other programs; 2351 for f16 on a larger card), even where the server's cache was guessed otherwise."""
    for expected in (cache, ("q8_0", False)):
        place._learnt.clear()
        monkeypatch.setattr(place, "server_cache", lambda settings, guess=expected: guess)
        s = _settings(tmp_path, ollama_url=ollama.url)
        ollama.loaded.add(PLAMO_NAME)
        ollama.size = MEASURED[cache][1]
        assert place.translator_need(s) == (MEASURED[cache][1] // place.MiB,) * 2
        ollama.loaded.clear()
        need, now = place.translator_need(s)
        assert now == 0 and need == place.known_translator(PLAMO_NAME, 8192, cache)[0]
        assert need < round(MEASURED[cache][1] // place.MiB * place.RUNNER_SHARE)
        assert MEASURED[cache][0] <= need < MEASURED[cache][0] + 100  # neither under nor over what it adds


def _band(other, cache, setting="auto", cuda=True, tall=False):
    """Where the readers go on the 6 GB card (LaMa and the layout model on the GPU) with *other* MiB of other
    programs, without the full window and with it."""
    s = Settings(ocr_runs_on=setting)

    def facts(settings, server):
        assert server[0] == cache
        return GpuFacts(total=6144, used=other, translator=place.known_translator(PLAMO_NAME, 8192, server)[0],
                        lama=True, layout=True, tall_screen=tall)

    return place.full_window_placements(s, cache, ocr=OCR, cuda=cuda, facts=facts)


def test_the_losing_band_is_where_only_the_window_cache_s_mib_move_the_readers():
    """On the 6 GB card, a screen up to 1440 px: the readers go to the GPU without the window cache up to 1704 MiB of
    other programs, with it up to 1604 (q8_0); between the two the window cache would cost them the GPU. (The server
    starts before the readers are anywhere: the return mark, not the margin.)"""
    peak = CONTEXT_MIB + LAMA_MIB + place.LAYOUT_MIB + OCR
    assert 6144 - 1704 - (peak + 2000) == place.RETURN_MIB == 6144 - 1604 - (peak + 2100)
    for other, wanted in ((717, ("gpu", "gpu")), (1440, ("gpu", "gpu")), (1604, ("gpu", "gpu")),
                          (1605, ("gpu", "cpu")), (1650, ("gpu", "cpu")), (1704, ("gpu", "cpu")),
                          (1705, ("cpu", "cpu"))):
        before, after = _band(other, "q8_0")
        assert (before.device, after.device) == wanted, other
        assert before.room - after.room == 100
    before, after = _band(1360, "q8_0", tall=True)  # (a taller screen: LaMa's larger windows)
    assert (before.device, after.device) == ("gpu", "cpu")
    before, after = _band(1300, "q8_0", setting="gpu")  # (the place set: the same either way)
    assert before == after == Placement("gpu", place.SET)
    before, after = _band(1300, "q8_0", cuda=False)
    assert before == after == Placement("cpu", place.NO_CUDA)


def test_on_an_8_gb_card_the_band_is_far_above_what_other_programs_hold():
    def facts(settings, server):
        return GpuFacts(total=8192, used=1340, translator=place.known_translator(PLAMO_NAME, 8192, server)[0],
                        lama=True, layout=True)

    before, after = place.full_window_placements(Settings(), "f16", ocr=OCR, cuda=True, facts=facts)
    assert before.device == after.device == "gpu" and before.room - after.room == 200


def test_ollama_s_start_asks_the_rule_with_the_facts_of_the_moment(tmp_path, monkeypatch):
    from taslation import ollama_start
    from taslation.render import artwork

    asked = []
    # the card's used memory, and this process's own: the first call only looks whether there is an NVIDIA GPU; then
    # the readers move to the GPU on another thread while the card is read (own 0, then 500), so it is read again
    readings = iter([(6144, 2494), (6144, 1994), (6144, 2494), (6144, 2494),
                     (6144, 1200), (6144, 1200), (6144, 2000)])
    owns = iter([0, 500, 500, 500, 0, 0, 0])

    def gather(settings, cache=None, memory=None, own=None, ask=True):
        assert ask is False  # (the server is about to be started: nothing is loaded in it, and it is not asked)
        asked.append((cache, memory, own))
        total, used = memory
        return GpuFacts(total=total, used=used, own=own, translator=place.known_translator(PLAMO_NAME, 8192, cache)[0],
                        lama=True, layout=True)

    monkeypatch.setattr(place, "gather", gather)
    monkeypatch.setattr(place, "card_memory", lambda: next(readings))
    monkeypatch.setattr(place, "own_mib", lambda: next(owns))
    monkeypatch.setattr(artwork, "_cuda", True)
    s = _settings(tmp_path)  # (its models folder has no second reader: charspot's 130 MiB alone)
    assert ollama_start.window_choice(s, "q8_0") == (False, ollama_start.WHY_READERS, (810, 710))
    # one snapshot for both, the card and this process's part of it of the same moment: the two differ by the
    # translation model's figure alone (other programs 1994 MiB either way, not 1494 for the second look)
    assert asked == [(("q8_0", False), (6144, 2494), 500), (("q8_0", True), (6144, 2494), 500)]
    assert ollama_start.window_choice(s, "q8_0") == (True, ollama_start.WHY_NO_LOSS, (1604, 1504))


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
    assert place.page_models_on_gpu(_settings(tmp_path)) == (True, True)  # (the defaults: both "auto")
    assert place.page_models_on_gpu(_settings(tmp_path, detect_model="off")) == (True, False)
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


def test_out_of_memory_reads_that_crop_on_the_cpu_and_stays_there_until_the_memory_is_let_go(given_back):
    told = []
    m = FakeModels("nar")
    m.on_gpu_failure = lambda reader, why: told.append((reader, why))
    m.to("cuda")
    m.broken = True
    assert m.read("crop") == "crop read with net@cpu"  # the page is never failed
    assert m.reads == ["net@cuda", "net@cpu"] and m.device == "cpu"
    assert m.gpu_full == "MemoryError_" and not m.gpu_failed and told == [("nar", "MemoryError_")]
    assert not m.to("cuda") and m.device == "cpu"  # until the GPU memory is let go (`Readers.release_gpu`) ...
    m.gpu_full, m.broken = "", False
    assert m.to("cuda") and m.read() == "x read with net@cuda"  # ... and then there again


def test_a_cuda_error_reads_that_crop_on_the_cpu_and_stays_there_for_the_session(given_back):
    told = []
    m = FakeModels("nar")
    m.on_gpu_failure = lambda reader, why: told.append((reader, why))
    m.to("cuda")
    m.broken, m.error = True, CudaError_
    assert m.read("crop") == "crop read with net@cpu"
    assert m.gpu_failed == "CudaError_" and not m.gpu_full and told == [("nar", "CudaError_")]
    assert not m.to("cuda") and m.device == "cpu"


def test_only_the_memory_running_out_is_out_of_memory():
    class OutOfMemoryError(RuntimeError):  # (torch.cuda's, by its name)
        pass

    assert place.out_of_memory(OutOfMemoryError("Tried to allocate 20.00 MiB"))
    assert place.out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
    assert place.out_of_memory(RuntimeError("CUDA error: out of memory"))
    assert place.out_of_memory(RuntimeError("CUDA error: CUBLAS_STATUS_ALLOC_FAILED when calling `cublasCreate(handle)`"))
    assert place.out_of_memory(RuntimeError("cuFFT error: CUFFT_ALLOC_FAILED"))
    assert not place.out_of_memory(RuntimeError("CUDA error: an illegal memory access was encountered"))
    assert not place.out_of_memory(RuntimeError("cuDNN error: CUDNN_STATUS_EXECUTION_FAILED"))


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
    m.copy_fails = True  # (no room for the copy: until the GPU memory is let go)
    assert not m.to("cuda") and m.device == "cpu" and m.gpu_full == "RuntimeError" and told == ["RuntimeError"]
    assert not m.gpu_failed


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


# ------------------------------------------------------------------ reads that crawl on the GPU
def test_reads_crawl_only_when_every_one_of_the_last_is_slower_than_twice_the_cpu_s():
    cpu = [50.0, 60.0, 40.0]
    assert place.SLOW_READS == 8 and place.CPU_READS == 3 and place.SLOW_FACTOR == 2.0
    assert place.crawling([101.0] * 8, cpu) == (101.0, 50.0)
    assert place.crawling([100.0] * 8, cpu) is None  # (twice the CPU's median exactly: not more)
    assert place.crawling([300.0] * 7 + [20.0], cpu) is None  # one read at the GPU's own speed: waits, not a crawl
    assert place.crawling([20.0] * 4 + [300.0] * 8, cpu) == (300.0, 50.0)  # (the last eight)
    assert place.crawling([300.0] * 7, cpu) is None  # (too few reads on the GPU)
    assert place.crawling([300.0] * 8, cpu[:2]) is None  # (the processor's time not known well enough)


class Clock:
    """`time.perf_counter` as `place` sees it, moved on by the reads themselves."""

    def __init__(self):
        self.now = 100.0

    def perf_counter(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(place, "time", SimpleNamespace(perf_counter=c.perf_counter))
    return c


def _timed(m, clock, gpu_ms, cpu_ms):
    """One read of *m* that takes *gpu_ms* on the GPU and *cpu_ms* on the CPU; the networks it read with."""
    def on(device, models):
        m.reads.append(models[0])
        clock.now += (cpu_ms if device == "cpu" else gpu_ms) / 1000
        return models[0]

    return m.run(on)


def test_reads_that_crawl_on_the_gpu_go_to_the_cpu_for_the_session(given_back, clock):
    told = []
    m = FakeModels("charspot")
    m.on_gpu_failure = lambda reader, why: told.append((reader, why))
    m.to("cuda")
    with place.loading():  # (the page waits for the translation model's load: a slower read costs it nothing)
        read = [_timed(m, clock, 15, 50) for _ in range(40)]
    # one read in nine on the CPU until three processor's times are known, none after them
    assert [k for k, net in enumerate(read) if net == "net@cpu"] == [8, 17, 26]
    assert list(m.cpu_ms) == pytest.approx([50.0] * 3) and not told and m.device == "cuda"
    # the GPU crawls (its memory in the computer's own, another program at work on it): each read slower than twice
    # the processor's; the eighth such read sends them to the CPU
    read = [_timed(m, clock, 150, 50) for _ in range(9)]
    assert read == ["net@cuda"] * 8 + ["net@cpu"]
    assert m.gpu_failed == place.SLOW_GPU and not m.gpu_full and told == [("charspot", place.SLOW_GPU)]
    assert m.device == "cpu" and given_back == [1] and not m.to("cuda")


def test_no_read_goes_to_the_cpu_for_its_time_outside_a_load_and_none_crawls_unknown(given_back, clock):
    m = FakeModels()
    m.to("cuda")
    assert [_timed(m, clock, 15, 50) for _ in range(30)] == ["net@cuda"] * 30  # (a page waits for each read now)
    assert not m.cpu_ms
    assert [_timed(m, clock, 400, 50) for _ in range(20)] == ["net@cuda"] * 20  # (no processor's time to judge by)
    assert m.device == "cuda" and not m.gpu_failed
    with place.loading():
        assert [_timed(m, clock, 15, 50) for _ in range(2)] == ["net@cpu", "net@cuda"]  # (eight and more since one)


def test_reads_that_wait_now_and_then_on_the_gpu_are_no_crawl(given_back, clock):
    m = FakeModels()
    m.to("cuda")
    with place.loading():
        for _ in range(27):
            _timed(m, clock, 15, 50)
    assert len(m.cpu_ms) == place.CPU_READS
    for k in range(40):  # (three reads in four waited behind a page model of this process)
        assert _timed(m, clock, 15 if k % 4 == 0 else 400, 50) == "net@cuda"
    assert m.device == "cuda" and not m.gpu_failed


def test_reads_while_the_translator_computes_are_the_processor_s_times(given_back, clock):
    m = FakeModels()
    m.to("cuda")
    with place.translating():
        for _ in range(3):
            assert _timed(m, clock, 15, 50) == "net@cpu"
    assert list(m.cpu_ms) == pytest.approx([50.0] * 3)
    assert [_timed(m, clock, 15, 50) for _ in range(30)] == ["net@cuda"] * 30  # (none of the CPU's needed)


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
    rule = SimpleNamespace(answer=Placement("gpu", place.ROOM, 1500), asked=[], staying=[])

    def decided(settings, ocr, failed="", cuda=None, facts=None, staying=False):
        rule.asked.append((settings.ocr_runs_on, ocr, failed))
        rule.staying.append(staying)
        return place.failed_placement(failed) if failed else rule.answer

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


def test_a_cuda_error_of_one_reader_puts_both_on_the_cpu_for_the_session(tmp_path, fake_readers):
    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    ocr._nar.broken, ocr._nar.error = True, CudaError_
    text, _parted = readers.agree("x", readers.written(ocr._nar.read("y")), lambda: "z")
    assert ocr._nar.reads[-1] == "net@cpu"  # that crop read on the CPU
    assert ocr.placement == Placement("cpu", place.FAILED, error="CudaError_")
    assert ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    s.target_language = "German"
    ocr.release_gpu()
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr.charspot.device == "cpu"  # never decided again this session


def test_an_out_of_memory_of_one_reader_puts_both_on_the_cpu_until_the_gpu_memory_is_let_go(tmp_path, fake_readers):
    """The page goes on (that crop read on the CPU); nothing decides while the room is gone (a changed setting, a read
    neither); the next release of the GPU memory - before the translation model's load, Tools > Release the model now
    - lets the next read decide again, and the rule puts them back where it finds room."""
    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    ocr._nar.broken = True
    assert ocr._nar.read("y") == "y read with net@cpu"
    assert ocr.placement == Placement("cpu", place.FAILED, error="MemoryError_")
    assert ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    s.target_language = "German"
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr.charspot.device == "cpu"  # (no room yet: nothing decided)
    ocr._nar.broken = False
    ocr.release_gpu(load=True)  # (the release before a load: not kept, the room was gone)
    assert len(fake_readers.asked) == 1 and not ocr._nar.gpu_full and not ocr.charspot.gpu_full
    ocr.read_chars(None)
    assert fake_readers.asked[-1] == ("auto", OCR, "") and ocr.placement == Placement("gpu", place.ROOM, 1500)
    assert ocr.charspot.device == "cuda" and ocr._nar.device == "cuda" and ocr._nar.read() == "x read with net@cuda"


def test_the_second_out_of_memory_of_a_session_keeps_them_on_the_cpu_for_the_rest_of_it(tmp_path, fake_readers):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    for _round in range(place.FULLS_FOR_GOOD):
        assert ocr.placement == Placement("gpu", place.ROOM, 1500)  # (the first time: back where the rule finds room)
        ocr._nar.broken = True
        assert ocr._nar.read("y") == "y read with net@cpu"
        ocr._nar.broken = False
        ocr.release_gpu()
        ocr.read_chars(None)
    assert place.FULLS_FOR_GOOD == 2 and len(fake_readers.asked) == 2
    assert ocr.placement == Placement("cpu", place.FAILED, error="MemoryError_") and ocr.charspot.device == "cpu"
    ocr.release_gpu()
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2 and ocr._nar.device == "cpu"  # never decided again this session


def test_reads_that_crawl_put_both_on_the_cpu_for_the_session_and_say_so(tmp_path, fake_readers, clock):
    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    with place.loading():
        for _ in range(27):  # (the processor's times known, during a load of the translation model)
            _timed(ocr._nar, clock, 25, 70)
    for _ in range(place.SLOW_READS):
        _timed(ocr._nar, clock, 400, 70)
    assert ocr.placement == Placement("cpu", place.SLOW, error=place.SLOW_GPU)
    assert ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    ocr.release_gpu()
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr.charspot.device == "cpu"  # never decided again this session
    row = _ocr_row(s, ocr)
    assert row.where() == "CPU" and row.what == devices.OCR_WHY["slow"]


def test_readers_the_rule_has_on_the_gpu_are_judged_as_staying_there(tmp_path, fake_readers):
    """The hysteresis (`place.judge`'s *staying*): readers on the GPU by the rule stay down to `place.MARGIN_MIB` left
    at the peak; readers anywhere else - on the CPU, not decided yet, on the GPU by the setting - go there from
    `place.RETURN_MIB`."""
    s = _settings(tmp_path)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    for language, answer in (("German", Placement("gpu", place.ROOM, 1500)),
                             ("French", Placement("cpu", place.NO_ROOM, 500)), ("Spanish", Placement("gpu", place.SET)),
                             ("Italian", Placement("gpu", place.ROOM, 900))):
        fake_readers.answer = answer
        s.target_language = language
        ocr.read_chars(None)
    s.target_language = "Dutch"
    ocr.read_chars(None)
    assert fake_readers.staying == [False, True, True, False, False, True]


def test_a_look_at_the_room_now_and_then_moves_them_where_the_rule_says(tmp_path, fake_readers, monkeypatch):
    """Where the rule placed them, a read once `place.LOOK_S` went by asks it again on a thread of its own (other
    programs grew, or let go): to the CPU below the margin, back to the GPU above the return mark."""
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr._look is None  # (`LOOK_S` not gone by)
    monkeypatch.setattr(place, "LOOK_S", 0.0)
    fake_readers.answer = Placement("cpu", place.NO_ROOM, 400)
    ocr.read_chars(None)
    ocr._look.join(5)
    assert len(fake_readers.asked) == 2 and fake_readers.staying[-1] is True
    assert ocr.placement.why == place.NO_ROOM and ocr.charspot.device == "cpu" and ocr._nar.device == "cpu"
    fake_readers.answer = Placement("gpu", place.ROOM, 700)
    ocr.read_chars(None)
    ocr._look.join(5)
    assert len(fake_readers.asked) == 3 and fake_readers.staying[-1] is False and ocr.charspot.device == "cuda"
    with place.translating():  # (not while the translation model answers: the next read after it looks)
        ocr.read_chars(None)
    ocr._look.join(5)
    assert len(fake_readers.asked) == 3
    fake_readers.answer = Placement("gpu", place.SET)
    forced = readers.Readers(tmp_path, 0, settings=_settings(tmp_path, ocr_runs_on="gpu"))
    forced.read_chars(None)
    assert forced._look is None and len(fake_readers.asked) == 4  # (a place the setting gives is never looked at)


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


# ------------------------------------------------------------------ through a load of the translation model
ROOMY = GpuFacts(total=6144, used=1325 + CONTEXT_MIB + 120, own=CONTEXT_MIB + 120, translator=PLAMO, lama=True)


@pytest.fixture
def measured(monkeypatch):
    """The facts of the moment (`place.gather`), as a test sets them (*facts*; an exception is raised), and the times
    they were asked."""
    state = SimpleNamespace(facts=ROOMY, asked=0)

    def gather(settings):
        state.asked += 1
        if isinstance(state.facts, Exception):
            raise state.facts
        return state.facts

    monkeypatch.setattr(place, "gather", gather)
    return state


def test_a_load_keeps_the_readers_the_rule_put_on_the_gpu_where_they_still_fit(tmp_path, fake_readers, measured,
                                                                              given_back):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    ocr.release_gpu(load=True)
    assert measured.asked == 1  # asked again at the release
    assert ocr.placement == Placement("gpu", place.ROOM, 1619) and ocr.holds_gpu()  # (the room of that moment)
    assert ocr.charspot.device == "cuda" and ocr._nar.device == "cuda" and not given_back and place._kept
    with place.loading():
        assert ocr.read_chars(None).text == "x read with net@cuda"  # it reads there through the load
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and measured.asked == 1  # the decision stands: nothing asked after the load


@pytest.mark.parametrize("facts", [
    GpuFacts(total=6144, used=4000, own=CONTEXT_MIB + 120, translator=PLAMO, lama=True),  # other programs grew
    None,  # no NVML
    GpuFacts(total=6144, used=1595, own=270, translator=PLAMO, lama=True, answered=False),  # /api/ps not answering
    GpuFacts(total=6144, used=1595, own=270, translator=None, lama=True),  # the model's need not known
    RuntimeError("NVML"),  # the measuring itself failed
])
def test_a_load_lets_the_readers_go_where_the_check_fails_or_cannot_be_made(tmp_path, fake_readers, measured,
                                                                            given_back, facts):
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    measured.facts = facts
    ocr.release_gpu(load=True)
    assert measured.asked == 1 and ocr.placement.why == place.RELEASED and ocr.charspot.device == "cpu"
    assert given_back and not place._kept
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 2  # decided again at the next read, as ever


def test_a_load_lets_go_readers_the_setting_forced_there_failed_ones_and_changed_settings(tmp_path, fake_readers,
                                                                                       measured):
    fake_readers.answer = Placement("gpu", place.SET)
    forced = readers.Readers(tmp_path, 0, settings=_settings(tmp_path, ocr_runs_on="gpu"))
    forced.release_gpu(load=True)
    assert forced.placement.why == place.RELEASED and forced.charspot.device == "cpu"
    fake_readers.answer = Placement("gpu", place.ROOM, 1500)
    failed = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    failed.charspot.broken = True
    failed.read_chars(None)  # (out of memory on the GPU: the CPU until this release; the next read decides again)
    failed.release_gpu(load=True)
    assert failed.placement.why == place.FAILED and failed.charspot.device == "cpu" and failed._nar.device == "cpu"
    s = _settings(tmp_path)
    changed = readers.Readers(tmp_path, 0, settings=s)
    s.target_language = "Turkish"  # (another model loads: the placement was not decided for it)
    changed.release_gpu(load=True)
    assert changed.placement.why == place.RELEASED
    assert measured.asked == 0  # none of them asked the room again


def test_a_full_release_still_lets_the_readers_go(tmp_path, fake_readers, measured, given_back):
    """Tools > Release the model now (`Pipeline.release_gpu_models`, no *load*), whatever the room."""
    from taslation.pipeline import Pipeline

    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    p = Pipeline(_settings(tmp_path), ocr=ocr)
    p.release_gpu_models()
    assert ocr.placement.why == place.RELEASED and ocr.charspot.device == "cpu" and given_back
    assert measured.asked == 0


def test_the_pipeline_s_release_before_a_load_asks_the_readers_last(tmp_path, fake_readers, measured):
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    tr = OllamaTranslator("http://127.0.0.1:9", "qwen3.5:4b", timeout=1.0)
    ocr = readers.Readers(tmp_path, 0, settings=_settings(tmp_path))
    p = Pipeline(_settings(tmp_path), ocr=ocr, translator=tr)
    assert tr.before_load == p.release_before_load
    order = []
    p.gpu_releases.append(lambda: order.append(("page model", measured.asked)))  # (a page model's, built later)
    p.release_before_load()
    assert order == [("page model", 0)] and measured.asked == 1  # the page models let go before the room is asked
    assert ocr.holds_gpu() and p._gpu_released == 1  # (a warm-up under way stops all the same)


def test_a_load_through_the_translator_keeps_them_and_reads_on_the_gpu_meanwhile(tmp_path, fake_readers, measured,
                                                                                ollama):
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="qwen3.5:4b")
    ocr = readers.Readers(tmp_path, 0, settings=s)
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    Pipeline(s, ocr=ocr, translator=tr)
    during = []

    def answer(items, payload):
        ocr.read_chars(None)
        during.append((payload["messages"][-1]["content"] == "Hi", ocr.charspot.reads[-1]))

    ollama.answer = answer
    tr.translate_page(["はい"])
    assert during == [(True, "net@cuda"), (False, "net@cpu")]  # the load on the GPU, the request on the CPU
    assert ocr.placement == Placement("gpu", place.ROOM, 1619) and ollama.loads == 1
    ocr.read_chars(None)
    assert len(fake_readers.asked) == 1 and ocr.charspot.reads[-1] == "net@cuda"


def test_a_model_that_comes_up_partly_on_the_cpu_beside_them_sends_them_to_the_cpu_for_good(tmp_path, fake_readers,
                                                                                          measured, ollama):
    """Kept through a load whose model came up half on the GPU all the same: the translator loads it again after the
    GPU models are let go (`OllamaTranslator._ensure_loaded`), and the readers go with them, there and at every load
    after it this session, room or not. Between loads the rule still puts them on the GPU."""
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="qwen3.5:4b")
    ocr = readers.Readers(tmp_path, 0, settings=s)
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    Pipeline(s, ocr=ocr, translator=tr)
    during = []

    def answer(items, payload):
        if payload["messages"][-1]["content"] == "Hi":
            ocr.read_chars(None)
            during.append(ocr.charspot.reads[-1])

    ollama.answer = answer
    ollama.shares = [0.5]  # (the first load half on the GPU, the next whole)
    tr.ensure_loaded()
    assert during == ["net@cuda", "net@cpu"] and ollama.loads == 2 and ollama.share == 1.0
    assert ocr.placement.why == place.RELEASED and not place.keeps_through_loads() and not place._kept
    assert measured.asked == 1  # (the second release asked nothing)
    ocr.read_chars(None)
    assert ocr.holds_gpu() and len(fake_readers.asked) == 2  # (after the load the rule decides, as ever)
    tr.release(wait=True)
    tr.ensure_loaded()  # the next load: let go although the room is there
    assert during[-1] == "net@cpu" and ollama.loads == 3 and ocr.placement.why == place.RELEASED
    assert measured.asked == 1


def test_a_model_partly_on_the_cpu_without_readers_kept_changes_nothing(tmp_path, fake_readers, measured, ollama):
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="qwen3.5:4b")
    measured.facts = None  # (no NVML: let go before the load)
    ocr = readers.Readers(tmp_path, 0, settings=s)
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0)
    Pipeline(s, ocr=ocr, translator=tr)
    ollama.shares = [0.5]
    tr.ensure_loaded()
    assert ollama.loads == 2 and place.keeps_through_loads()  # (they took nothing from it)
    assert not place.partly_loaded(0.5) and place.keeps_through_loads()


def test_layers_set_by_hand_never_count_as_a_model_partly_on_the_cpu(tmp_path, fake_readers, measured, ollama):
    from taslation.pipeline import Pipeline
    from taslation.translate import OllamaTranslator

    s = _settings(tmp_path, ollama_url=ollama.url, ollama_model="qwen3.5:4b")
    ocr = readers.Readers(tmp_path, 0, settings=s)
    tr = OllamaTranslator(ollama.url, "qwen3.5:4b", timeout=10.0, num_gpu=10)
    Pipeline(s, ocr=ocr, translator=tr)
    ollama.shares = [0.5]  # (split on purpose)
    tr.ensure_loaded()
    assert ollama.loads == 1 and ocr.holds_gpu() and place.keeps_through_loads()


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

    def stream(path, payload, on_text, cancel=None, on_slow=None, timeout=None, **_bounds):
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
    slow = _ocr_row(s, SimpleNamespace(placement=Placement("cpu", place.SLOW, error=place.SLOW_GPU), settings=s))
    assert slow.where() == "CPU" and "slower on the GPU" in slow.what and place.SLOW_GPU not in slow.what


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


def test_the_system_page_s_line_says_the_margin_and_the_looks_as_the_rule_has_them():
    from taslation.ui.dialogs import system_page

    assert round(MARGIN_MIB * place.MiB / 1e8) * 100 == 700 and "about 700 MB" in system_page.OCR_RUNS_ON_TEXT
    assert f"every {place.LOOK_S:.0f} seconds" in system_page.OCR_RUNS_ON_TEXT


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


# ------------------------------------------------------------------ the window cache of the Ollama TASlation starts
def test_the_system_page_shows_and_saves_the_window_cache(hidden_root, tmp_path, monkeypatch):
    from taslation import ollama_start
    from taslation.i18n import set_language
    from taslation.ui.dialogs import settings as dlg
    from taslation.ui.dialogs import system_page

    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    in_force = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert [v for v, _label in system_page.WINDOW_CACHE_CHOICES] == list(ollama_start.WINDOW_CACHE_VALUES)
    assert d.system.window_cache.get() == "On, unless the OCR then leaves the GPU"
    assert d.values()["ollama_window_cache"] == "auto"
    d.system.window_cache.set("Off")
    assert d.save() is True and got == [{"ollama_window_cache": "off"}]
    assert Settings.from_toml(in_force.config_path).ollama_window_cache == "off"
    d.destroy()
    set_language("ja")
    in_force.ollama_window_cache = "on"
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.system.window_cache.get() == "常に使う" and d.values()["ollama_window_cache"] == "on"


def test_the_translator_s_row_says_what_the_server_taslation_started_got(tmp_path, monkeypatch):
    from taslation import ollama_start
    from taslation.ollama_start import WHY_NO_GPU, WHY_READERS, WHY_SET, WHY_SETTING, ServerSetup

    s = _settings(tmp_path)
    translator = SimpleNamespace(model="m", _loaded=lambda model: None)
    assert devices._translator_device(s, translator, GPU).what == "Ollama: m"  # (an Ollama TASlation did not start)
    for setup, key in ((ServerSetup("q8_0", True, "256", WHY_NO_GPU), "on"),
                       (ServerSetup("q8_0", False, "0", WHY_READERS), "readers"),
                       (ServerSetup("f16", False, "0", WHY_SETTING), "off"),
                       (ServerSetup("f16", False, "0", WHY_SET), "off")):
        monkeypatch.setattr(ollama_start, "setup_of", lambda url, state_dir=None, setup=setup: setup)
        assert devices._translator_device(s, translator, GPU).what == "Ollama: m; " + devices.WINDOW_CACHE_ROWS[key]
    line = "\n".join(devices.lines(s, translator=translator, cuda=False, gpu=""))  # (`taslation doctor`'s lines)
    assert devices.WINDOW_CACHE_ROWS["off"] in line


def test_the_window_cache_s_lines_are_in_every_language():
    from taslation.i18n import FEATURE_LANGUAGES
    from taslation.locales.features import window_cache
    from taslation.ui.dialogs import system_page

    keys = (system_page.WINDOW_CACHE_LABEL, system_page.WINDOW_CACHE_TEXT,
            *(label for _value, label in system_page.WINDOW_CACHE_CHOICES), *devices.WINDOW_CACHE_ROWS.values())
    assert sorted(window_cache.TEXTS) == sorted(keys)
    for key in keys:
        assert sorted(window_cache.TEXTS[key]) == sorted(FEATURE_LANGUAGES), key


def test_at_ollama_s_start_the_rule_does_not_ask_the_server_what_it_has_loaded(tmp_path, monkeypatch, ollama):
    """The server is about to be started when the rule is asked for its window cache: nothing is loaded in it, and
    one that is not there takes Windows about 2 s to refuse, twice. The model is counted at its figures, not asked."""
    from taslation import ollama_start
    from taslation.render import artwork

    s = _settings(tmp_path, ollama_url=ollama.url)
    ollama.loaded.add(PLAMO_NAME)  # (were it asked, it would say the model is loaded at 3,000,000,000 bytes)
    assert place._translator_need(s, ("q8_0", False)) == (3_000_000_000 // place.MiB,) * 2 + (True,)
    place._learnt.clear()
    assert place._translator_need(s, ("q8_0", True), ask=False) == (2100, 0, True)
    monkeypatch.setattr(place, "gather", REAL_GATHER)
    monkeypatch.setattr(place, "card_memory", lambda: (6144, 1200))
    monkeypatch.setattr(place, "own_mib", lambda: 0)
    monkeypatch.setattr(place, "page_models_on_gpu", lambda settings: (True, True))
    monkeypatch.setattr(place, "tall_screen", lambda: False)
    monkeypatch.setattr(artwork, "_cuda", True)
    assert ollama_start.window_choice(s, "q8_0") == (True, ollama_start.WHY_NO_LOSS, (1604, 1504))  # (charspot alone)
