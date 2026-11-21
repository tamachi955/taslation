"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: results of ``openmantra_eval.py`` run on parts of the OpenMantra
dataset (``--series``: a title or several a run, say each on a machine of its own) joined into the results of the
whole, numbers only as the parts are.

    python tools/openmantra_merge.py part1.json part2.json ... [--out all.json] [--force]

The parts' page rows are pooled and scored again as the eval scores them (`openmantra_eval.summarize`), so detection,
OCR and translation over all the titles come out as one run over the whole would give them (the "all" row is the
pooled one, never a mean of the parts'), and the per-series scores of each translation run are joined, so that
``compare_runs.py`` reads the joined file as it reads a run of the whole. Beside them: per part its titles, pages,
seconds per stage and the speed of its requests (Ollama's own counts), and the requests of all parts pooled.

The parts must be one measurement: the same options but ``--series``, the same model, settings and dataset. A title
in two parts is refused, and so are parts that differ otherwise (``--force`` joins them, and the joined file lists
what differs). Detection and OCR are per page, so their pooled scores are exactly those of one run. The translation
of a title is its own in both (in book mode a title's context never reaches another title), with two differences:
a line asked for before in another title is drawn anew in one run of the whole (`PlamoTranslator._draw`) but for
the first time in a part of its own, and each part's server started without the caches of the titles before it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra_eval as ev  # noqa: E402

# what the parts must have been run with alike (``--series`` is what tells them apart)
SAME_OPTIONS = ("pages", "ocr", "translate", "mode", "arm", "geometry", "target", "iou", "runs", "seed", "glossary",
                "names")
# where a machine keeps things, not what is measured
OWN_SETTINGS = ("state_dir", "models_dir", "ollama_url", "cache_dir")
SPEED_SUMS = ("requests", "eval_tokens", "eval_s", "prompt_tokens", "prompt_s")


class MergeError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("tool") != "openmantra_eval" or not isinstance(data.get("rows"), list):
        raise MergeError(f"{path}: not the results of openmantra_eval.py")
    return data


def _shown(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def differences(parts: list[dict[str, Any]]) -> list[str]:
    """What the parts were run with that is not alike in all of them (the series aside), one line each."""
    out: list[str] = []

    def compare(what: str, values: list[Any], known_only: bool = False) -> None:
        shown = [(i, _shown(v)) for i, v in enumerate(values) if not known_only or v is not None]
        if len({s for _i, s in shown}) > 1:
            out.append(f"{what}: " + ", ".join(f"part {i + 1} {s}" for i, s in shown))

    for key in SAME_OPTIONS:
        compare(f"option {key}", [(p.get("options") or {}).get(key) for p in parts])
    compare("model", [p.get("model") for p in parts])
    compare("dataset", [(p.get("dataset") or {}).get("archive_sha256") for p in parts])
    # (a part whose translation did not run has no Ollama to compare)
    compare("Ollama", [(p.get("translation") or {}).get("ollama") for p in parts], known_only=True)
    keys = sorted({k for p in parts for k in (p.get("settings") or {})} - set(OWN_SETTINGS))
    for key in keys:
        compare(f"setting {key}", [(p.get("settings") or {}).get(key) for p in parts])
    return out


def pooled_speed(speeds: list[dict[str, Any]]) -> dict[str, Any]:
    """The requests of several parts' runs counted together: their tokens over their time."""
    total = {key: round(sum(s.get(key) or 0 for s in speeds), 1) for key in SPEED_SUMS}
    total["requests"] = int(total["requests"])
    total["eval_tokens"] = int(total["eval_tokens"])
    total["prompt_tokens"] = int(total["prompt_tokens"])
    total["eval_tok_per_s"] = round(total["eval_tokens"] / total["eval_s"], 1) if total["eval_s"] else None
    total["prompt_tok_per_s"] = round(total["prompt_tokens"] / total["prompt_s"], 1) if total["prompt_s"] else None
    return total


def _joined(parts_runs: list[dict[str, Any]], key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for run in parts_runs:
        out.update(run.get(key) or {})
    return out


def merge_runs(parts: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The translation runs of the parts joined run by run: the per-series scores (official arm, and the end-to-end
    arm's when there is one), the failures and incomplete pages added up, the speed pooled. Run 1's summary is scored
    again from the pooled rows, which hold run 1's lines; a later run keeps its parts' per-series summaries."""
    lists = [(p.get("translation") or {}).get("run_results") or [] for p in parts]
    count = min(len(runs) for runs in lists)
    out = []
    for k in range(count):
        mine = [runs[k] for runs in lists]
        record: dict[str, Any] = {"run": k + 1, "seed": mine[0].get("seed"),
                                  "parts_seconds": [r.get("seconds") for r in mine]}
        if any("series" in r for r in mine):
            record["series"] = _joined(mine, "series")
            record["requests_failed"] = sum(r.get("requests_failed") or 0 for r in mine)
            record["pages_incomplete"] = sum(r.get("pages_incomplete") or 0 for r in mine)
            record["speed"] = pooled_speed([r.get("speed") or {} for r in mine])
        e2e = [r["e2e"] for r in mine if r.get("e2e")]
        if e2e:
            record["e2e"] = {"series": _joined(e2e, "series"), "series_lenient": _joined(e2e, "series_lenient"),
                             "requests_failed": sum(r.get("requests_failed") or 0 for r in e2e),
                             "pages_incomplete": sum(r.get("pages_incomplete") or 0 for r in e2e),
                             "speed": pooled_speed([r.get("speed") or {} for r in e2e])}
        if k == 0:
            record["summary"] = ev.summarize(rows)
        else:
            record["summary"] = {"by_series": {name: s for r in mine
                                               for name, s in ((r.get("summary") or {}).get("by_series") or {}).items()}}
        out.append(record)
    return out


def part_record(part: dict[str, Any]) -> dict[str, Any]:
    """What the joined file keeps of a part beside its rows: its titles, pages, seconds and requests' speed."""
    tr = part.get("translation") or {}
    runs = tr.get("run_results") or []
    return {"series": list((part.get("dataset") or {}).get("series") or []),
            "pages": len(part.get("rows") or []), "made": part.get("made"), "seconds": part.get("seconds") or {},
            "ollama": tr.get("ollama"), "error": tr.get("error"),
            "speed": [r.get("speed") for r in runs if r.get("speed")],
            "server_started": tr.get("server_started")}


def merge(parts: list[dict[str, Any]], force: bool = False) -> dict[str, Any]:
    """The parts' results joined (see the module's notes); MergeError for a title in two parts, or for parts that
    differ without *force*."""
    if not parts:
        raise MergeError("no parts")
    owner: dict[str, int] = {}
    for i, part in enumerate(parts):
        for name in dict.fromkeys(r["series"] for r in part["rows"]):
            if name in owner:
                raise MergeError(f"the title {name} is in part {owner[name] + 1} and in part {i + 1}")
            owner[name] = i
    differ = differences(parts)
    if differ and not force:
        raise MergeError("the parts were not run alike (--force joins them):\n  " + "\n  ".join(differ))
    rows = [row for part in parts for row in part["rows"]]
    series = list(owner)
    first = parts[0]
    translations = [p.get("translation") or {} for p in parts]
    errors = [f"part {i + 1}: {t['error']}" for i, t in enumerate(translations) if t.get("error")]
    untranslated = [i + 1 for i, t in enumerate(translations) if not t.get("error") and not t.get("run_results")]
    translation: dict[str, Any]
    if all(not t for t in translations):
        translation = {}
    elif errors or untranslated:
        translation = {"error": "; ".join(errors + [f"part {i}: no translation" for i in untranslated])}
    else:
        translation = {key: value for key, value in translations[0].items()
                       if key not in ("run_results", "server_started", "requests_failed", "pages_incomplete")}
        translation["run_results"] = merge_runs(parts, rows)
        translation["requests_failed"] = sum(t.get("requests_failed") or 0 for t in translations)
        translation["pages_incomplete"] = sum(t.get("pages_incomplete") or 0 for t in translations)
    stages = sorted({k for p in parts for k, v in (p.get("seconds") or {}).items() if isinstance(v, (int, float))
                     and not isinstance(v, bool)})
    seconds: dict[str, Any] = {key: round(sum((p.get("seconds") or {}).get(key) or 0 for p in parts), 1)
                               for key in stages}
    seconds["longest_part"] = max(((p.get("seconds") or {}).get("total") or 0 for p in parts), default=0)
    dataset = {**(first.get("dataset") or {}), "series": series, "pages": len(rows),
               "gold_boxes": sum(r["gold"] for r in rows)}
    options = {**(first.get("options") or {}), "series": series}
    return {"tool": "openmantra_merge", "made": max(str(p.get("made") or "") for p in parts),
            "parts": [part_record(p) for p in parts], "differences": differ, "dataset": dataset, "options": options,
            "model": first.get("model"), "settings": first.get("settings") or {}, "translation": translation,
            "summary": ev.summarize(rows), "seconds": seconds, "rows": rows}


def parts_table(merged: dict[str, Any]) -> str:
    rows = []
    for i, part in enumerate(merged["parts"]):
        s = part["seconds"]
        speed = part["speed"][0] if part["speed"] else {}
        rows.append([i + 1, ", ".join(part["series"]), part["pages"], ev._fmt(s.get("detection_ocr")),
                     ev._fmt(s.get("translation")), ev._fmt(s.get("total")), speed.get("requests", "-"),
                     ev._fmt(speed.get("eval_tok_per_s")), ev._fmt(speed.get("prompt_tok_per_s")),
                     part["ollama"] or "-"])
    runs = (merged.get("translation") or {}).get("run_results") or []
    pooled = runs[0].get("speed") if runs else None
    if pooled:
        s = merged["seconds"]
        rows.append(["all", f"{len(merged['dataset']['series'])} titles", merged["dataset"]["pages"],
                     ev._fmt(s.get("detection_ocr")), ev._fmt(s.get("translation")), ev._fmt(s.get("total")),
                     pooled["requests"], ev._fmt(pooled["eval_tok_per_s"]), ev._fmt(pooled["prompt_tok_per_s"]), ""])
    return ("Parts (seconds per stage; requests and tokens a second of the first run, Ollama's own counts; all: the "
            "seconds added up, the longest part " + ev._fmt(merged["seconds"].get("longest_part")) + " s)\n"
            + ev.table(["part", "titles", "pages", "det+OCR s", "translation s", "total s", "requests", "gen tok/s",
                        "prompt tok/s", "Ollama"], rows))


def printable(summary: dict[str, Any]) -> dict[str, Any]:
    """The summary as `openmantra_eval.report` can print it: when some titles have no translation (a part whose
    translation did not run) the translation tables are left out of the print (the joined file keeps them)."""
    groups = [*summary["by_series"].values(), summary["all"]]
    out = dict(summary)
    for key in ("translation", "e2e"):
        if any(key in g for g in groups) and not all(key in g for g in groups):
            out = {"by_series": {name: {k: v for k, v in s.items() if k != key} for name, s in out["by_series"].items()},
                   "all": {k: v for k, v in out["all"].items() if k != key}}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("parts", nargs="+", type=Path, help="the results files of openmantra_eval.py, one per part")
    ap.add_argument("--out", type=Path, help="the joined results file (default: printed only)")
    ap.add_argument("--force", action="store_true", help="join parts that were not run alike (listed in the file)")
    args = ap.parse_args(argv)
    try:
        merged = merge([load(p) for p in args.parts], force=args.force)
    except (MergeError, OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for line in merged["differences"]:
        print(f"differs: {line}")
    print(ev.report(printable(merged["summary"]), float((merged.get("options") or {}).get("iou") or ev.IOU)))
    print()
    print(parts_table(merged))
    if (merged.get("translation") or {}).get("error"):
        print(f"\ntranslation: {merged['translation']['error']}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        print(f"\njoined: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
