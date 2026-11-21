"""tools/openmantra_merge.py: results of openmantra_eval.py run title by title joined into those of the whole, with no
dataset, no model and no Ollama: the pooled scores are the eval's own over all the rows (never a mean of the parts'),
compare_runs.py reads the joined file as one run, and parts that overlap or were run otherwise are refused."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import compare_runs  # noqa: E402
import openmantra_eval as ev  # noqa: E402
import openmantra_merge as om  # noqa: E402


def _line(chrf: float, flags: tuple[str, ...] = ()) -> dict:
    return {"chrf": chrf, "real": chrf > 0, "flags": list(flags), "worded": True, "open": False, "romanised": False}


def _row(series: str, page: int, gold: int, found: int, matched: int, chrfs: list[float]) -> dict:
    return {"series": series, "page": page, "size": [800, 1200], "gold": gold, "gold_worded": gold,
            "candidates": found + 1, "candidates_matched": matched, "candidates_matched_worded": matched,
            "found": found, "found_matched": matched, "found_matched_worded": matched,
            "matched_ocr": [[0.0, 5]] * matched, "gold_ocr": [[0.1, 10]] * gold, "geometry_detected": matched,
            "seconds": {"pipeline": 1.0}, "lines": [_line(c) for c in chrfs]}


def _speed(requests: int, tokens: int, seconds: float) -> dict:
    return {"requests": requests, "eval_tokens": tokens, "eval_tok_per_s": round(tokens / seconds, 1),
            "prompt_tokens": 10 * tokens, "prompt_tok_per_s": round(10 * tokens / seconds, 1), "prompt_s": seconds,
            "eval_s": seconds, "recomputed": {"requests": 0, "prompt_s": 0.0}}


def _part(series: str, rows: list[dict], seconds: float, **options) -> dict:
    rows = copy.deepcopy(rows)  # (a test may change its part's rows)
    run = {"run": 1, "seed": 1, "notes": "none", "notes_sha256": "", "requests_failed": 0, "pages_incomplete": 0,
           "seconds": seconds, "speed": _speed(10, 80, seconds), "series": ev.series_scores(rows),
           "summary": ev.summarize(rows)}
    return {"tool": "openmantra_eval", "made": "2026-11-22T10:00:00",
            "dataset": {"name": "OpenMantra", "licence": "CC BY-NC 4.0", "root": "x", "archive_sha256": "ab",
                        "series": [series], "pages": len(rows), "gold_boxes": sum(r["gold"] for r in rows)},
            "options": {"pages": 0, "series": [series], "ocr": True, "translate": True, "mode": "book",
                        "arm": "official", "geometry": "detected", "target": "en", "iou": 0.5, "runs": 1, "seed": 1,
                        "glossary": "", "names": "", **options},
            "model": "taslation-plamo3-translate-2b", "settings": {"detect_model": "on", "ollama_url": "u"},
            "translation": {"model": "taslation-plamo3-translate-2b", "ollama": "0.40.16", "mode": "book",
                            "requests_failed": 0, "pages_incomplete": 0, "run_results": [run],
                            "server_started": {"port": 11435}},
            "summary": ev.summarize(rows), "seconds": {"detection_ocr": 100.0, "translation": seconds,
                                                       "total": 100.0 + seconds},
            "rows": rows}


ROWS_A = [_row("one", 1, 10, 10, 9, [40.0, 50.0]), _row("one", 2, 4, 6, 4, [30.0])]
ROWS_B = [_row("two", 1, 20, 18, 17, [20.0, 30.0, 40.0, 60.0])]


def test_the_whole_is_scored_from_all_the_rows_not_from_the_parts_scores():
    merged = om.merge([_part("one", ROWS_A, 50.0), _part("two", ROWS_B, 70.0)])
    whole = ev.summarize(ROWS_A + ROWS_B)
    assert merged["summary"] == whole
    assert merged["translation"]["run_results"][0]["summary"] == whole
    # (pooled: 30 of 34 found regions matched, 30 of 34 gold boxes; a mean of the parts' F1 would differ)
    assert whole["all"]["f1"] == pytest.approx(30 / 34, abs=1e-4)
    parts_mean = (ev.summarize(ROWS_A)["all"]["f1"] + ev.summarize(ROWS_B)["all"]["f1"]) / 2
    assert whole["all"]["f1"] != pytest.approx(parts_mean, abs=1e-4)
    assert whole["all"]["translation"]["chrf"] == pytest.approx(sum([40, 50, 30, 20, 30, 40, 60]) / 7, abs=0.01)
    assert merged["dataset"]["series"] == ["one", "two"] and merged["dataset"]["pages"] == 3
    assert merged["seconds"]["translation"] == 120.0 and merged["seconds"]["longest_part"] == 170.0
    speed = merged["translation"]["run_results"][0]["speed"]
    assert speed["requests"] == 20 and speed["eval_tokens"] == 160 and speed["eval_tok_per_s"] == round(160 / 120, 1)
    assert [p["series"] for p in merged["parts"]] == [["one"], ["two"]]


def test_compare_runs_reads_the_joined_file_as_one_run_of_both_titles():
    merged = om.merge([_part("one", ROWS_A, 50.0), _part("two", ROWS_B, 70.0)])
    runs = compare_runs.runs_of(merged)
    assert len(runs) == 1 and runs[0]["seed"] == 1
    assert sorted(runs[0]["series"]) == ["one", "two"]
    assert runs[0]["series"]["two"] == {"lines": 4, "chrf": 37.5}


def test_a_title_in_two_parts_or_parts_run_otherwise_are_refused():
    with pytest.raises(om.MergeError, match="the title one is in part 1 and in part 2"):
        om.merge([_part("one", ROWS_A, 50.0), _part("one", ROWS_A, 50.0)])
    other = _part("two", ROWS_B, 70.0, seed=2)
    with pytest.raises(om.MergeError, match="option seed"):
        om.merge([_part("one", ROWS_A, 50.0), other])
    forced = om.merge([_part("one", ROWS_A, 50.0), other], force=True)
    assert forced["differences"] == ["option seed: part 1 1, part 2 2"]
    # where a machine keeps things is not a difference
    moved = _part("two", ROWS_B, 70.0)
    moved["settings"]["ollama_url"] = "elsewhere"
    assert om.merge([_part("one", ROWS_A, 50.0), moved])["differences"] == []


def test_a_part_without_its_translation_is_said():
    failed = _part("two", ROWS_B, 70.0)
    failed["translation"] = {"error": "Ollama is not running at x"}
    for row in failed["rows"]:
        row.pop("lines")
    merged = om.merge([_part("one", ROWS_A, 50.0), failed])
    assert merged["translation"] == {"error": "part 2: Ollama is not running at x"}
    assert merged["summary"] == ev.summarize(ROWS_A + failed["rows"])
    shown = om.printable(merged["summary"])  # (the print leaves the translation tables out, the file keeps them)
    assert "translation" not in shown["all"] and "translation" in merged["summary"]["by_series"]["one"]
    assert "Translation" not in ev.report(shown, 0.5) and "Detection" in ev.report(shown, 0.5)
    assert "lines" in ROWS_B[0]


def test_the_command_writes_the_joined_file_and_prints_numbers(tmp_path, capsys):
    paths = []
    for name, rows, seconds in (("one", ROWS_A, 50.0), ("two", ROWS_B, 70.0)):
        paths.append(tmp_path / f"{name}.json")
        paths[-1].write_text(json.dumps(_part(name, rows, seconds)), encoding="utf-8")
    out = tmp_path / "all.json"
    assert om.main([str(p) for p in paths] + ["--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "Detection" in printed and "Parts (seconds per stage" in printed and "2 titles" in printed
    assert json.loads(out.read_text(encoding="utf-8"))["summary"] == ev.summarize(ROWS_A + ROWS_B)
    assert om.main([str(paths[0]), str(paths[0])]) == 1
