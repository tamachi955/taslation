"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: whether two settings translate the OpenMantra pages differently, from
the results of ``openmantra_eval.py`` (numbers only, no text).

    python tools/compare_runs.py a.json b.json                  # arm A: a.json, arm B: b.json
    python tools/compare_runs.py --a a1.json a2.json --b b1.json b2.json b3.json
    python tools/compare_runs.py --metric e2e a.json b.json     # the end-to-end arm (strict); or e2e_lenient

Every results file holds one run or more (``--runs``); the runs of an arm's files are pooled. The arms are paired by
series (the same gold lines in both). The difference B - A of the mean chrF (lines weighted as in the eval's "all")
gets a 95 % interval from a bootstrap that resamples the SERIES and, within each, the RUNS of each arm: the
translation noise moves whole series (one early reply shifts the rest of a run), so pages or lines resampled as if
independent give intervals far too narrow. The run-to-run SD of each arm is printed too.

A difference is called significant only when the interval leaves out 0 AND the arms have at least ``MIN_RUNS`` runs
each, or both ran the same fixed seeds (``--seed``). Otherwise the tool says it does not call it, whatever the
interval. (The model writes no notes since 2026-11-06: a file's ``notes_sha256`` is "" and says nothing.)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

MIN_RUNS = 3
BOOT = 10000


# ------------------------------------------------------------------------------------------------- loading
METRICS = ("official", "e2e", "e2e_lenient")


def _series_of(run: dict[str, Any], metric: str) -> dict[str, Any]:
    """A run's per-series scores in *metric*: the official arm's, or the end-to-end arm's, strict or lenient."""
    if metric == "official":
        if "series" not in run:
            raise ValueError("no official arm in this file (it ran --arm e2e)")
        return run["series"]
    e2e = run.get("e2e")
    if not e2e:
        raise ValueError("no end-to-end arm in this file (run it with --arm e2e or both)")
    return e2e["series"] if metric == "e2e" else e2e["series_lenient"]


def runs_of(results: dict[str, Any], metric: str = "official") -> list[dict[str, Any]]:
    """The runs of one results file: [{"seed", "series": {name: {"lines", "chrf"}}}, ...], in *metric* (the
    official arm, or the end-to-end arm's strict "e2e" or lenient "e2e_lenient" scores). A file from before
    ``--runs`` is one run, read from its per-series summary (no seed)."""
    tr = results.get("translation") or {}
    if tr.get("error"):
        raise ValueError(f"no translation in this file: {tr['error']}")
    if tr.get("run_results"):
        return [{"seed": r.get("seed"),
                 "series": {k: {"lines": int(v["lines"]), "chrf": float(v["chrf"])}
                            for k, v in _series_of(r, metric).items()}}
                for r in tr["run_results"]]
    if metric != "official":
        raise ValueError("no end-to-end arm in this file")
    by = (results.get("summary") or {}).get("by_series") or {}
    series = {k: {"lines": int(v["translation"]["lines"]), "chrf": float(v["translation"]["chrf"])}
              for k, v in by.items() if "translation" in v}
    if not series:
        raise ValueError("no translation in this file")
    return [{"seed": None, "series": series}]


def load_arm(paths: Sequence[Path], metric: str = "official") -> dict[str, Any]:
    """The runs of every file of one arm (scored in *metric*, `runs_of`), and what they were run with."""
    runs, settings = [], []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        runs += runs_of(data, metric)
        settings.append({**(data.get("settings") or {}), **{f"option {k}": v for k, v in (data.get("options") or {}).items()}})
    return {"runs": runs, "settings": settings}


def arm_matrix(runs: Sequence[dict[str, Any]], series: Sequence[str]) -> np.ndarray:
    """chrF per (run, series) of the series every run has."""
    return np.array([[r["series"][s]["chrf"] for s in series] for r in runs], dtype=float)


# ------------------------------------------------------------------------------------------------- statistics
def weighted(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return (values * weights).sum(axis=-1) / weights.sum(axis=-1)


def bootstrap(a: np.ndarray, b: np.ndarray, weights: Sequence[float], n_boot: int = BOOT, seed: int = 0,
              level: float = 0.95) -> dict[str, float]:
    """The difference B - A of the line-weighted mean chrF of two arms, *a* and *b* arrays of chrF per (run, series)
    with the series in the same order: its value (the mean over the runs) and the *level* interval of a bootstrap
    that draws the series with replacement and, within every drawn series, the runs of each arm with replacement."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    w = np.asarray(weights, float)
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[1] or a.shape[1] != len(w) or not len(w):
        raise ValueError("a and b need one column per series, the same series")
    diff = float(weighted(b.mean(axis=0) - a.mean(axis=0), w))
    rng = np.random.default_rng(seed)
    n_s = len(w)

    def run_means(x: np.ndarray) -> np.ndarray:  # (n_boot, series): each series' mean over runs drawn anew
        idx = rng.integers(0, x.shape[0], size=(n_boot, x.shape[0], n_s))
        return np.take_along_axis(np.broadcast_to(x, (n_boot,) + x.shape), idx, axis=1).mean(axis=1)

    d = run_means(b) - run_means(a)
    counts = rng.multinomial(n_s, np.full(n_s, 1.0 / n_s), size=n_boot)  # how often each series is drawn
    cw = counts * w
    boots = (d * cw).sum(axis=1) / cw.sum(axis=1)
    lo, hi = np.quantile(boots, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {"diff": round(diff, 3), "lo": round(float(lo), 3), "hi": round(float(hi), 3), "level": level,
            "boot": n_boot}


def run_sd(x: np.ndarray, weights: Sequence[float]) -> dict[str, float | None]:
    """Run-to-run spread of one arm: the SD over runs of the overall chrF, and the root mean square of the
    per-series SDs (None with one run)."""
    x = np.asarray(x, float)
    if x.shape[0] < 2:
        return {"overall": None, "per_series": None}
    overall = weighted(x, np.asarray(weights, float))
    return {"overall": round(float(np.std(overall, ddof=1)), 3),
            "per_series": round(float(np.sqrt(np.mean(np.var(x, axis=0, ddof=1)))), 3)}


def controlled(a_runs: Sequence[dict[str, Any]], b_runs: Sequence[dict[str, Any]]) -> bool:
    """Whether both arms ran the same seeds, every one fixed."""
    seeds_a, seeds_b = sorted(str(r["seed"]) for r in a_runs), sorted(str(r["seed"]) for r in b_runs)
    return all(r["seed"] is not None for r in list(a_runs) + list(b_runs)) and seeds_a == seeds_b


def compare(arm_a: dict[str, Any], arm_b: dict[str, Any], n_boot: int = BOOT, seed: int = 0) -> dict[str, Any]:
    """Everything the report prints, as numbers and a verdict."""
    a_runs, b_runs = arm_a["runs"], arm_b["runs"]
    common = [s for s in a_runs[0]["series"] if all(s in r["series"] for r in a_runs + b_runs)]
    if not common:
        raise ValueError("the arms have no series in common")
    lines = {s: {r["series"][s]["lines"] for r in a_runs + b_runs} for s in common}
    mismatched = sorted(s for s, n in lines.items() if len(n) > 1)
    weights = [max(lines[s]) for s in common]
    a, b = arm_matrix(a_runs, common), arm_matrix(b_runs, common)
    boot = bootstrap(a, b, weights, n_boot, seed)
    same_seeds = controlled(a_runs, b_runs)
    enough = min(len(a_runs), len(b_runs)) >= MIN_RUNS
    allowed = enough or same_seeds
    excludes_zero = boot["lo"] > 0 or boot["hi"] < 0
    if not allowed:
        verdict = (f"not called: fewer than {MIN_RUNS} runs per arm ({len(a_runs)} and {len(b_runs)}) without the same "
                   "fixed seeds in both arms; the interval is not to be trusted")
    elif excludes_zero:
        verdict = "significant: the interval leaves out 0"
    else:
        verdict = "not significant: the interval includes 0"
    caveats = []
    if min(len(a_runs), len(b_runs)) < 2:
        caveats.append("one run in an arm: the runs' noise is not in the interval, only the series'")
    if same_seeds and not enough:
        caveats.append("a fixed seed makes a run repeatable, but a setting that changes any prompt still draws anew; "
                       f"{MIN_RUNS} runs (seeds) per arm are the safer measure")
    if len(common) < 4:
        caveats.append(f"only {len(common)} series: the series bootstrap is coarse")
    if mismatched:
        caveats.append(f"different line counts in {', '.join(mismatched)}: not the same pages?")
    return {"series": common, "lines": dict(zip(common, weights)), "runs": {"a": len(a_runs), "b": len(b_runs)},
            "mean": {"a": round(float(weighted(a.mean(axis=0), np.asarray(weights, float))), 3),
                     "b": round(float(weighted(b.mean(axis=0), np.asarray(weights, float))), 3)},
            "per_series": {s: {"a": round(float(a[:, i].mean()), 3), "b": round(float(b[:, i].mean()), 3)}
                           for i, s in enumerate(common)},
            "sd": {"a": run_sd(a, weights), "b": run_sd(b, weights)}, "bootstrap": boot,
            "same_seeds": same_seeds, "significant": bool(allowed and excludes_zero),
            "called": allowed, "verdict": verdict, "caveats": caveats,
            "settings_differ": settings_differ(arm_a["settings"], arm_b["settings"])}


def settings_differ(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]]) -> list[str]:
    """The settings and options whose values differ between the arms (or within one)."""
    keys = sorted({k for d in list(a) + list(b) for k in d})
    out = []
    for k in keys:
        va = {json.dumps(d.get(k)) for d in a}
        vb = {json.dumps(d.get(k)) for d in b}
        if va != vb and k not in ("option runs", "option seed", "option notes_from"):
            out.append(f"{k}: {' | '.join(sorted(va))} -> {' | '.join(sorted(vb))}")
    return out


def report(res: dict[str, Any]) -> str:
    def sd(v: Any) -> str:
        return "-" if v is None else f"{v:.2f}"

    out = [f"chrF, arm A ({res['runs']['a']} runs) against arm B ({res['runs']['b']} runs), paired by series"]
    if res["settings_differ"]:
        out.append("what differs: " + "; ".join(res["settings_differ"]))
    out.append(f"{'series':<24}{'lines':>6}{'A':>8}{'B':>8}{'B-A':>8}")
    for s in res["series"]:
        p = res["per_series"][s]
        out.append(f"{s:<24}{res['lines'][s]:>6}{p['a']:>8.2f}{p['b']:>8.2f}{p['b'] - p['a']:>+8.2f}")
    b = res["bootstrap"]
    out.append(f"{'all':<24}{sum(res['lines'].values()):>6}{res['mean']['a']:>8.2f}{res['mean']['b']:>8.2f}{b['diff']:>+8.2f}")
    out.append(f"B - A = {b['diff']:+.2f} chrF, {int(100 * b['level'])} % interval [{b['lo']:+.2f}, {b['hi']:+.2f}] "
               f"(bootstrap over series and runs, {b['boot']} draws)")
    out.append(f"run-to-run SD of the overall chrF: A {sd(res['sd']['a']['overall'])}, B {sd(res['sd']['b']['overall'])}; "
               f"per series (RMS): A {sd(res['sd']['a']['per_series'])}, B {sd(res['sd']['b']['per_series'])}")
    out.append(f"same fixed seeds in both arms: {'yes' if res['same_seeds'] else 'no'}")
    out.append(res["verdict"])
    out += [f"note: {c}" for c in res["caveats"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", type=Path, help="A.json B.json: one results file per arm")
    ap.add_argument("--a", nargs="+", type=Path, default=[], help="the results files of arm A")
    ap.add_argument("--b", nargs="+", type=Path, default=[], help="the results files of arm B")
    ap.add_argument("--boot", type=int, default=BOOT, help="bootstrap draws")
    ap.add_argument("--metric", choices=METRICS, default="official",
                    help="official: gold text in gold order (default); e2e: the end-to-end arm, strict; e2e_lenient")
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON")
    args = ap.parse_args(argv)
    a_files, b_files = list(args.a), list(args.b)
    if args.files:
        if a_files or b_files or len(args.files) != 2:
            ap.error("give two files, or --a and --b")
        a_files, b_files = [args.files[0]], [args.files[1]]
    if not a_files or not b_files:
        ap.error("both arms need results files")
    try:
        res = compare(load_arm(a_files, args.metric), load_arm(b_files, args.metric), args.boot)
    except (ValueError, KeyError, OSError) as e:
        print(f"cannot compare: {e}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=1) if args.json else report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
