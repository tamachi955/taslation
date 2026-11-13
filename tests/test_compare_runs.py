"""The comparison of two evaluation arms (tools/compare_runs.py), the seed option of the translator, and the eval's
book mode and repeated runs (tools/openmantra_eval.py) with a fake Ollama."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import compare_runs  # noqa: E402
import openmantra  # noqa: E402
import openmantra_eval  # noqa: E402

from fake_ollama import FakeOllama  # noqa: E402
from test_openmantra import write_dataset  # noqa: E402

LINES = [120, 300, 250, 400, 180]


def synthetic(effect: float, runs: int, rng: np.random.Generator, series_sd: float = 1.2) -> tuple[np.ndarray, np.ndarray]:
    """chrF per (run, series) of two arms: every series has its own level, every run moves every series by a noise
    of *series_sd* (as one early reply shifts a whole series); arm B is *effect* higher."""
    level = rng.uniform(25, 35, size=len(LINES))
    a = level + rng.normal(0, series_sd, size=(runs, len(LINES)))
    b = level + effect + rng.normal(0, series_sd, size=(runs, len(LINES)))
    return a, b


def arm(matrix: np.ndarray, seeds=None) -> dict:
    names = [f"s{i}" for i in range(matrix.shape[1])]
    runs = [{"seed": None if seeds is None else seeds[k],
             "series": {n: {"lines": LINES[i], "chrf": float(matrix[k, i])} for i, n in enumerate(names)}}
            for k in range(matrix.shape[0])]
    return {"runs": runs, "settings": [{}]}


# ----------------------------------------------------------------------------------------------- bootstrap
def test_bootstrap_finds_a_known_effect():
    rng = np.random.default_rng(1)
    a, b = synthetic(3.0, 5, rng)
    res = compare_runs.compare(arm(a), arm(b), n_boot=4000)
    boot = res["bootstrap"]
    assert boot["lo"] > 0 and boot["lo"] < boot["diff"] < boot["hi"]
    assert 1.5 < boot["diff"] < 4.5
    assert res["called"] and res["significant"] and res["verdict"].startswith("significant")
    assert 0.3 < res["sd"]["a"]["per_series"] < 2.5  # the run-to-run noise the data was made with


def test_bootstrap_on_pure_noise_is_rarely_significant():
    rng = np.random.default_rng(2)
    hits = 0
    for _ in range(40):
        a, b = synthetic(0.0, 3, rng)
        res = compare_runs.compare(arm(a), arm(b), n_boot=1000, seed=int(rng.integers(1 << 30)))
        assert res["called"]
        hits += res["significant"]
    assert hits <= 6  # a 95 % interval: about 2 of 40 by chance; a page bootstrap would call most of them


def test_noise_moving_whole_series_widens_the_interval():
    rng = np.random.default_rng(3)
    a, b = synthetic(0.0, 4, rng, series_sd=0.1)
    narrow = compare_runs.bootstrap(a, b, LINES, 2000)
    a, b = synthetic(0.0, 4, rng, series_sd=2.0)
    wide = compare_runs.bootstrap(a, b, LINES, 2000)
    assert wide["hi"] - wide["lo"] > 4 * (narrow["hi"] - narrow["lo"])


def test_bootstrap_value_is_the_line_weighted_mean_difference():
    a = np.array([[10.0, 20.0], [12.0, 22.0]])
    b = np.array([[11.0, 30.0], [13.0, 32.0]])
    boot = compare_runs.bootstrap(a, b, [1, 3], 200)
    assert boot["diff"] == pytest.approx((1 * 1 + 3 * 10) / 4)
    with pytest.raises(ValueError):
        compare_runs.bootstrap(a, b[:, :1], [1, 3])


def test_too_few_runs_are_not_called_without_the_same_fixed_seeds():
    rng = np.random.default_rng(4)
    a, b = synthetic(6.0, 1, rng)
    res = compare_runs.compare(arm(a), arm(b), n_boot=1000)
    assert not res["called"] and not res["significant"]
    assert res["verdict"].startswith("not called") and "3 runs" in res["verdict"]
    assert res["sd"]["a"]["overall"] is None
    assert any("one run" in c for c in res["caveats"])
    assert "not called" in compare_runs.report(res)
    # the same fixed seeds in both arms: one run each may be called (the eval writes no notes: "" for every run)
    res = compare_runs.compare(arm(a, [7]), arm(b, [7]), n_boot=1000)
    assert res["same_seeds"] and res["called"] and "same fixed seeds in both arms: yes" in compare_runs.report(res)
    # different seeds, or no fixed seed, are not the same conditions
    assert not compare_runs.compare(arm(a, [7]), arm(b, [8]), n_boot=200)["called"]
    assert not compare_runs.compare(arm(a, [None]), arm(b, [None]), n_boot=200)["called"]


def test_runs_of_the_end_to_end_arm():
    run = {"seed": 1, "series": {"x": {"lines": 10, "chrf": 40.0}},
           "e2e": {"series": {"x": {"lines": 10, "chrf": 35.0}}, "series_lenient": {"x": {"lines": 9, "chrf": 38.0}}}}
    data = {"translation": {"run_results": [run]}}
    assert compare_runs.runs_of(data)[0]["series"]["x"]["chrf"] == 40.0
    assert compare_runs.runs_of(data, "e2e")[0]["series"]["x"]["chrf"] == 35.0
    assert compare_runs.runs_of(data, "e2e_lenient")[0]["series"]["x"] == {"lines": 9, "chrf": 38.0}
    with pytest.raises(ValueError):
        compare_runs.runs_of({"translation": {"run_results": [{"seed": 1, "series": {}}]}}, "e2e")
    with pytest.raises(ValueError):
        compare_runs.runs_of({"translation": {"run_results": [{"seed": 1, "e2e": run["e2e"]}]}})


def test_runs_of_an_old_results_file():
    old = {"translation": {"model": "m"}, "summary": {"by_series": {
        "x": {"translation": {"lines": 10, "chrf": 30.5}}, "y": {"pages": 1}}}}
    assert compare_runs.runs_of(old) == [{"seed": None, "series": {"x": {"lines": 10, "chrf": 30.5}}}]
    with pytest.raises(ValueError):
        compare_runs.runs_of({"translation": {"error": "Ollama is not running"}})


# ------------------------------------------------------------------------------------------------ the seed
def test_the_seed_reaches_the_payload_only_when_set():
    from taslation.translate import OllamaTranslator

    with FakeOllama() as fake:
        OllamaTranslator(fake.url, "qwen3.5:4b").translate_page(["こんにちは"])
        assert "seed" not in fake.requests[-1]["options"]  # the app: no seed, a fresh draw
        tr = OllamaTranslator(fake.url, "qwen3.5:4b", seed=41)
        tr.translate_page(["こんにちは"])
        assert fake.requests[-1]["options"]["seed"] == 41


# ------------------------------------------------------------------------------------- book mode and runs
def test_a_series_is_translated_as_the_batch_does_it(tmp_path, settings):
    from taslation.translate.simple import DictTranslator

    write_dataset(tmp_path / "om")
    pages = openmantra.by_series(openmantra.load(tmp_path / "om"))["series_a"]
    geos = [[None] * len(p.bubbles) for p in pages]
    tr = DictTranslator({"こんにちは": "Hello"}, default="X")
    stats = openmantra_eval._Stats()
    out = openmantra_eval.translate_series_book(settings, tr, "series_a", pages, geos, stats, lambda _m: None)
    assert tr.calls and len(out) == len(pages) and stats.requests_failed == 0
    assert all(kw["notes"] == "" for kw in tr.kwargs)  # no series sheet, and no notes of the model's


def test_runs_with_a_seed(tmp_path, monkeypatch):
    from taslation import health
    from taslation.translate import models

    write_dataset(tmp_path / "om")
    monkeypatch.setattr(openmantra_eval.netguard, "install", lambda: None)
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: ["qwen3.5:4b"])
    with FakeOllama() as fake:
        real = models.make_translator

        def at_fake(settings, model=None, *, seed=None):
            return real(settings.with_overrides(ollama_url=fake.url), model, seed=seed)

        monkeypatch.setattr(models, "make_translator", at_fake)
        common = ["--root", str(tmp_path / "om"), "--no-ocr", "--detect-model", "off", "--model", "qwen3.5:4b",
                  "--runs", "2", "--seed", "5"]
        a_out, b_out = tmp_path / "a.json", tmp_path / "b.json"
        assert openmantra_eval.main(common + ["--out", str(a_out)]) == 0
        seeds = {r["options"].get("seed") for r in fake.requests if "options" in r and r.get("messages")
                 and r["options"].get("num_predict") != 1}
        assert seeds == {5, 6}  # run k: seed + k - 1
        assert not [r for r in fake.requests if r.get("messages") and "Pages:" in r["messages"][-1]["content"]]
        assert openmantra_eval.main(common + ["--out", str(b_out)]) == 0

    a = json.loads(a_out.read_text(encoding="utf-8"))
    runs = a["translation"]["run_results"]
    assert [r["seed"] for r in runs] == [5, 6] and [r["notes"] for r in runs] == ["none", "none"]
    assert a["translation"]["translator"] == "OllamaTranslator" and runs[0]["speed"]["requests"] > 0
    assert set(runs[0]["series"]) == {"series_a", "series_b"}
    assert "A short story" not in a_out.read_text(encoding="utf-8")
    res = compare_runs.compare(compare_runs.load_arm([a_out]), compare_runs.load_arm([b_out]), n_boot=200)
    assert res["same_seeds"] and res["called"] and not res["significant"]  # the same fixed seeds: called
    assert res["bootstrap"]["diff"] == 0.0  # the fake answers alike
    assert compare_runs.main([str(a_out), str(b_out)]) == 0
