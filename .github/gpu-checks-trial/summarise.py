"""The numbers of the trial of the GPU computer's checks on GitHub's runners (.github/workflows/gpu-checks-trial.yml),
from the tools' own reports: no line of the dataset, read or translated, and nothing of a page.

    python .github/gpu-checks-trial/summarise.py standin REPORT --console FILE --facts FILE --group G --out DIR
    python .github/gpu-checks-trial/summarise.py bench RESULTS --console FILE --facts FILE --title N --out DIR
    python .github/gpu-checks-trial/summarise.py table ARTIFACTS --jobs JOBS [--caches CACHES] [--merged MERGED]
                                                      [--out FILE]

``standin`` (tools/standin_e2e.py's report.json) and ``bench`` (tools/openmantra_eval.py's results file) write
summary.json and summary.md into DIR. A report that is not there, as after a run stopped by the step's time limit, is
said, and what the console shows of the run is counted instead: its tracebacks and exception types, the tool's own
words on why a run stopped, and for the benchmark the pages read and the translation's runs so far (their seconds, and
the time all of them would take at that pace). Nothing else is read out of the console. ``table`` prints the run's
tables in Markdown for the summary job's page: each job's waiting, setting up, run and the rest by GitHub's own step
times (*JOBS*: the jobs API's jobs, one JSON object a line), the repository's caches against GitHub's limit
(*CACHES*: its list of them, one a line), the stand-in's verdicts and scenarios, the benchmark's titles and, with
*MERGED* (tools/openmantra_merge.py's file), the scores over all of them. Standard library only: the summary job has
no virtual environment.

A stand-in run "works" when it ended with the window's frames read (sharp or soft frames of the stand-in captured),
"no frames" when it ended without one, "stopped" when the tool stopped it (its reason is given), and "no report" when
the tool wrote none. Beside the verdict, what points to a fault (of the program, the tool or the runner) is kept apart
from what points to a slow computer: scenarios released by ``--timeout`` instead of at rest, rested turns whose page
was not finished within the rest the script gave it, and what each scenario was meant to show and whether it still
did (`meanings`).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

REST_MS = 2000  # standin_e2e.REST_MS: a screen on show sharp so long is one the reader rested on
TRACEBACK = "Traceback (most recent call last):"
EXCEPTION = re.compile(r"^((?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Error|Exception|Interrupt|Exit))\b")
STOPPED = re.compile(r"^run stopped: (.+)$")  # standin_e2e's Director.stop (its reasons name no window and no page)
PAGE_LINE = re.compile(r"^\s+\S.* p(\d+): gold (\d+), .*\[([0-9.]+) s\]\s*$")  # openmantra_eval, a page read
CHUNK_LINE = re.compile(r"^\s+\S.*: run (\d+)/(\d+), (\d+) lines so far, (\d+) s\s*$")  # ... a run of lines translated
OTHER_STATES = ("black", "spinner", "unknown")
AT_REST = ("a", "d", "r", "o", "z", "w2", "f", "f2")  # the scenarios whose rests are for reading translated pages


def read_json(path: Path | None) -> Any:
    if path is None or not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def read_text(path: Path | None) -> str:
    if path is None or not Path(path).is_file():
        return ""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def median(values: list[Any]) -> Any:
    kept = [v for v in values if v is not None]
    return round(statistics.median(kept)) if kept else None


def console_facts(text: str) -> dict[str, Any]:
    """What a console shows of a run's faults: tracebacks, the exception types they end in, and the stand-in tool's
    reason for a stopped run (its last one)."""
    lines = text.splitlines()
    types: Counter[str] = Counter()
    for line in lines:
        m = EXCEPTION.match(line)
        if m:
            types[m.group(1).rsplit(".", 1)[-1]] += 1
    stopped = [m.group(1).strip() for m in map(STOPPED.match, lines) if m]
    return {"lines": len(lines), "tracebacks": sum(1 for line in lines if line.startswith(TRACEBACK)),
            "exception_types": dict(types), "stopped": stopped[-1] if stopped else None}


def _run_facts(facts: dict[str, Any]) -> dict[str, Any]:
    run = facts.get("run") or {}
    return {"exit_code": run.get("exit_code"), "run_step_s": run.get("seconds"), "machine": facts.get("machine"),
            "screen": facts.get("screen"), "ollama": facts.get("ollama")}


# ------------------------------------------------------------------------------------------------- the stand-in
def _turns(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in run.get("turns") or [] if isinstance(r, dict)]


def _rested(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if (r.get("rest_ms") or 0) >= REST_MS]


def _finished_in_rest(row: dict[str, Any]) -> bool:
    return row.get("finished_ms") is not None and row["finished_ms"] <= (row.get("rest_ms") or 0)


def segment_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Per scenario: the tool's own table (`standin_e2e.segment_table`) and, from its turns, the rests the script gave
    the turns that came to rest and how many of their pages were finished within them."""
    rows = _turns(run)
    out = []
    for seg in run.get("segments") or []:
        name = seg.get("segment")
        rested = _rested([r for r in rows if r.get("segment") == name])
        out.append({"scenario": name, "turns": seg.get("turns"), "rested": seg.get("rested"),
                    "rest_ms_median": median([r.get("rest_ms") for r in rested]),
                    "finished_within_rest": sum(1 for r in rested if _finished_in_rest(r)),
                    "translated_at_rest": seg.get("translated_at_rest"),
                    "first_request_ms": [seg.get("first_request_ms_median"), seg.get("first_request_ms_max")],
                    "first_lettered_ms": [seg.get("first_lettered_ms_median"), seg.get("first_lettered_ms_max")],
                    "finished_ms": [seg.get("finished_ms_median"), seg.get("finished_ms_max")],
                    "jobs": seg.get("jobs"), "requests": seg.get("requests"),
                    "wasted_requests": seg.get("wasted_requests"), "stale": seg.get("stale"),
                    "not_following": seg.get("not_following")})
    return out


def meanings(report: dict[str, Any]) -> dict[str, str]:
    """Per scenario, whether the run still showed what the scenario is for ("holds", "partly", "lost" or "unclear",
    with the count it rests on): on a slower computer a scripted rest can be shorter than a page takes, the model can
    be loaded before the turns meant to come while it loads, a soft frame can be gone before the window asks on it."""
    run = report.get("run") or {}
    rows = _turns(run)
    segments = {s.get("segment"): s for s in run.get("segments") or []}

    def at_rest(name: str) -> str:
        seg = segments.get(name) or {}
        rested = seg.get("rested") or 0
        done = seg.get("translated_at_rest") or 0
        if not rested:
            return "unclear: no turn of it came to rest"
        if done == rested:
            return f"holds: {done} of {rested} rested turns translated at rest"
        if done:
            return f"partly: {done} of {rested} rested turns translated at rest"
        return f"lost: none of {rested} rested turns translated at rest (a page takes longer here than the rests)"

    out: dict[str, str] = {}
    for name in report.get("scenarios") or []:
        mine = [r for r in rows if r.get("segment") == name]
        if name == "c":
            ready = run.get("ready_s")
            early = [r for r in mine if ready is not None and r.get("t_s") is not None and r["t_s"] < ready]
            out[name] = (f"holds: {len(early)} of {len(mine)} turns came before the window was ready" if early
                         else f"lost: none of {len(mine)} turns came before the window was ready ({ready} s)")
        elif name == "b":
            out[name] = (f"holds: {len(mine)} quick turns" if len(mine) >= 10
                         else f"unclear: {len(mine)} of its 10 turns seen")
        elif name == "e":
            cached = sum(1 for r in mine if r.get("cached"))
            out[name] = (f"holds: {cached} of {len(mine)} turns found their page in the cache" if cached
                         else f"lost: none of {len(mine)} turns back found its page in the cache (the pages before "
                              "were not translated in time)")
        elif name in ("t", "t2"):
            keyed = name in (run.get("page_keys") or {})
            out[name] = (("holds: its turn came by the window's page key; " if keyed
                          else "lost: no turn came by the window's page key; ") + at_rest(name))
        elif name == "w":
            whole = run.get("whole_book_run") or {}
            ends = whole.get("ends") or []
            out[name] = (f"holds: the run read {whole.get('pages_got')} pages and ended "
                         f"({', '.join(str(e.get('code')) for e in ends)})" if ends
                         else f"lost: the run read {whole.get('pages_got')} pages and did not end")
        elif name == "x":
            cancel = run.get("cancel_in_flight") or {}
            soft, cut = cancel.get("requests_on_soft") or 0, cancel.get("cancelled_in_flight") or 0
            out[name] = (f"holds: {cut} requests cancelled in flight ({soft} on the soft frame)" if cut
                         else f"partly: {soft} requests on the soft frame, none cancelled in flight" if soft
                         else f"lost: no request on the soft frame within --cancel-soft-ms ({cancel.get('soft_ms')} "
                              "ms): the window read it too slowly here")
        else:
            out[name] = at_rest(name)
    return out


def faults(report: dict[str, Any]) -> dict[str, Any]:
    """What points to a fault of the program, the tool or the runner (not to a slow computer); only what was seen."""
    run = report.get("run") or {}
    guard = run.get("guard") or {}
    jobs = run.get("jobs") or {}
    cancels = run.get("cancels") or {}
    cleanup = report.get("cleanup") or {}
    log = (cleanup.get("log") or {}).get("lines") or {}
    server = report.get("server_started") or {}
    segments = run.get("segments") or []
    found = {
        "the run stopped": run.get("failed") or None,
        "calls refused by the guard": sorted(set(guard.get("refused") or [])) or None,
        "a window other than the stand-in chosen": guard.get("only_the_stand_in_chosen") is False or None,
        "errors in the tool's hooks": dict((run.get("errors") or {}).get("hooks") or {}) or None,
        "tracebacks in the window's log": log.get("tracebacks") or None,
        "errors in the window's log": log.get("error") or None,
        "exception types in the window's log": dict((cleanup.get("log") or {}).get("exception_types") or {}) or None,
        "pages lettered from a black frame, a spinner or an unknown frame":
            jobs.get("on_black_spinner_unknown_shown") or None,
        "jobs cancelled with their page still on show": len(cancels.get("page_still_on_show") or []) or None,
        "jobs kept from a frame that was not the sharp one": len(jobs.get("kept_from_unsettled_frames") or []) or None,
        "overlays left on a page the stand-in had left": sum(s.get("stale") or 0 for s in segments) or None,
        "jobs cancelled in scenario d (flashes and spinners)": (cancels.get("by_segment") or {}).get("d") or None,
        "incomplete pages in the cache at the end": cleanup.get("cache_pages_incomplete") or None,
        "the server TASlation started still answered at the end": server.get("stopped") is False or None,
        "the scratch state not deleted": cleanup.get("state_deleted") is False or None,
    }
    return {k: v for k, v in found.items() if v}


def slowness(report: dict[str, Any]) -> dict[str, Any]:
    """What points to a computer slower than the script's rests: scenarios released by --timeout instead of at rest,
    rested turns whose page was not finished within its rest or not translated at its end, spells the window showed
    another page than the stand-in for over a second, requests sent for frames that changed meanwhile."""
    run = report.get("run") or {}
    released = run.get("released") or {}
    segments = run.get("segments") or []
    rested = _rested(_turns(run))
    found = {
        "scenarios released by --timeout, not at rest": sorted(n for n, r in released.items()
                                                              if isinstance(r, dict) and r.get("timed_out")) or None,
        "rested turns not finished within their rest": sum(1 for r in rested if not _finished_in_rest(r)) or None,
        "rested turns not translated at rest": sum((s.get("rested") or 0) - (s.get("translated_at_rest") or 0)
                                                   for s in segments) or None,
        "spells the window did not follow the stand-in (over 1 s)": sum(s.get("not_following") or 0
                                                                        for s in segments) or None,
        "requests sent for nothing": (run.get("wasted_requests") or {}).get("count") or None,
    }
    return {k: v for k, v in found.items() if v}


def standin(report: Any, console: str, facts: dict[str, Any], group: str) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "standin", "group": group, **_run_facts(facts), "console": console_facts(console)}
    if not isinstance(report, dict) or not isinstance(report.get("run"), dict):
        out["verdict"] = "no report"
        out["why"] = out["console"]["stopped"] or "the tool wrote no report (stopped by the step's time limit?)"
        return out
    run = report["run"]
    captures = run.get("captures") or {}
    readable = int(captures.get("sharp") or 0) + int(captures.get("soft") or 0)
    failed = run.get("failed") or ""
    out["verdict"] = "stopped" if failed else "no frames" if not readable else "works"
    if failed:
        out["why"] = failed
    requests = run.get("requests") or {}
    jobs = run.get("jobs") or {}
    server = report.get("server_started") or {}
    placements = (run.get("ocr") or {}).get("placements") or []
    out.update({
        "translator": report.get("translator"), "browser": report.get("browser"), "pages": report.get("pages"),
        "scenarios": report.get("scenarios"), "left_out": report.get("x_left_out"),
        "seconds": run.get("seconds"), "ready_s": run.get("ready_s"),
        "captures": captures, "capture_route": run.get("capture_route"),
        "released": {name: {"waited_s": r.get("waited_s"), "timed_out": bool(r.get("timed_out"))}
                     for name, r in (run.get("released") or {}).items() if isinstance(r, dict)},
        "segments": segment_rows(run), "meaning": meanings(report), "faults": faults(report),
        "slowness": slowness(report),
        "requests": {k: requests.get(k) for k in ("total", "outside_page_jobs", "gate_pending", "warm_ups")},
        "jobs": {k: jobs.get(k) for k in ("started", "on", "discarded")},
        "server_started": {"setup": server.get("setup"), "stopped": server.get("stopped")} if server else None,
        "ocr_devices": sorted({",".join(str(e) for e in p.get("engines") or []) for p in placements
                               if isinstance(p, dict)}),
    })
    return out


def _pair(values: Any) -> str:
    values = values or [None, None]
    return "/".join("-" if v is None else str(v) for v in values)


def standin_md(s: dict[str, Any]) -> str:
    lines = [f"### Stand-in {s['group']}: {s['verdict']}", ""]
    if s.get("why"):
        lines += [f"Why: {s['why']}", ""]
    route = s.get("capture_route") or {}
    if s.get("captures") is not None:
        lines.append(f"* capture: {route.get('used')} (Windows.Graphics.Capture looks {route.get('looks')}; "
                     f"{route.get('route')}); frames by state {s['captures']}")
        lines.append(f"* the window ready after {s.get('ready_s')} s; the run {s.get('seconds')} s; translator "
                     f"{s.get('translator')}; OCR on {', '.join(s.get('ocr_devices') or []) or '-'}")
    lines.append(f"* exit code {s.get('exit_code')}, the run's step {s.get('run_step_s')} s; screen {s.get('screen')}")
    console = s.get("console") or {}
    if console.get("tracebacks"):
        lines.append(f"* console: {console['tracebacks']} tracebacks, {console.get('exception_types')}")
    if s.get("segments"):
        lines += ["", "| scenario | turns | rested (median rest ms) | finished within the rest | translated at rest | "
                  "first request ms med/max | first lettered ms med/max | finished ms med/max | requests (sent for "
                  "nothing) | meaning |", "|---|---|---|---|---|---|---|---|---|---|"]
        for row in s["segments"]:
            lines.append(f"| {row['scenario']} | {row['turns']} | {row['rested']} ({row['rest_ms_median']}) | "
                         f"{row['finished_within_rest']} | {row['translated_at_rest']} | {_pair(row['first_request_ms'])} | "
                         f"{_pair(row['first_lettered_ms'])} | {_pair(row['finished_ms'])} | {row['requests']} "
                         f"({row['wasted_requests']}) | {(s.get('meaning') or {}).get(row['scenario'], '')} |")
        lines.append("")
    for key, title in (("faults", "Points to a fault"), ("slowness", "Points to a slow computer")):
        if key in s:
            found = s[key]
            lines.append(f"* {title}: " + ("; ".join(f"{k}: {v}" for k, v in found.items()) if found else "nothing"))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------- the benchmark
def bench_progress(console: str) -> dict[str, Any]:
    """How far openmantra_eval's console got: the pages read (and their seconds) and the translation's last run of
    lines, with the time all its runs would take at that pace."""
    pages, seconds, chunk = 0, 0.0, None
    for line in console.splitlines():
        m = PAGE_LINE.match(line)
        if m:
            pages += 1
            seconds += float(m.group(3))
            continue
        m = CHUNK_LINE.match(line)
        if m:
            chunk = tuple(int(g) for g in m.groups())
    out: dict[str, Any] = {"pages_read": pages, "detection_ocr_s": round(seconds, 1)}
    if chunk:
        done, runs, lines, spent = chunk
        out["translation"] = {"runs_done": done, "runs": runs, "lines": lines, "seconds": spent,
                              "seconds_all_at_this_pace": round(spent * runs / done) if done else None}
    return out


def bench(results: Any, console: str, facts: dict[str, Any], title: str) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "benchmark", "title": title, **_run_facts(facts),
                           "progress": bench_progress(console), "console": console_facts(console)}
    if not isinstance(results, dict) or results.get("tool") != "openmantra_eval":
        out["verdict"] = "no results"
        return out
    summary = (results.get("summary") or {}).get("all") or {}
    translation = results.get("translation") or {}
    runs = translation.get("run_results") or []
    speed = (runs[0].get("speed") if runs else None) or {}
    scored = summary.get("translation") or {}
    out.update({
        "verdict": "translation failed" if translation.get("error") else "complete" if runs else "no translation",
        "series": (results.get("dataset") or {}).get("series"), "pages": (results.get("dataset") or {}).get("pages"),
        "seconds": results.get("seconds"),
        "detection": {k: summary.get(k) for k in ("precision", "recall", "f1", "found", "matched", "gold")},
        "ocr_cer": {"gold_corpus": (summary.get("ocr_gold") or {}).get("corpus"),
                    "gold_mean": (summary.get("ocr_gold") or {}).get("mean"),
                    "matched_corpus": (summary.get("ocr_matched") or {}).get("corpus")},
        "translation": {k: scored.get(k) for k in ("lines", "real", "chrf", "flagged_share")},
        "speed": {k: speed.get(k) for k in ("requests", "eval_tokens", "eval_tok_per_s", "prompt_tokens",
                                            "prompt_tok_per_s", "eval_s", "prompt_s", "s_per_page")},
        "requests_failed": translation.get("requests_failed"), "pages_incomplete": translation.get("pages_incomplete"),
        "ollama_version": translation.get("ollama"), "error": translation.get("error"),
        "detect_model": (results.get("settings") or {}).get("detect_model"),
        "server_started": (translation.get("server_started") or {}).get("setup"),
    })
    return out


def bench_md(b: dict[str, Any]) -> str:
    lines = [f"### Benchmark, title {b['title']}: {b['verdict']}", ""]
    if b.get("seconds"):
        s, d, o, t, p = b["seconds"], b["detection"], b["ocr_cer"], b["translation"], b["speed"]
        lines += [f"* {', '.join(b.get('series') or [])}: {b.get('pages')} pages; seconds {s}",
                  f"* detection F1 {d.get('f1')} (P {d.get('precision')}, R {d.get('recall')}; detect_model "
                  f"{b.get('detect_model')}); OCR CER {o.get('gold_corpus')} (corpus, gold crops; matched regions "
                  f"{o.get('matched_corpus')}); chrF {t.get('chrf')} over {t.get('lines')} lines ({t.get('real')} "
                  f"translated, flagged {t.get('flagged_share')})",
                  f"* translation: {p.get('requests')} requests, generation {p.get('eval_tok_per_s')} tok/s, prompt "
                  f"{p.get('prompt_tok_per_s')} tok/s ({p.get('s_per_page')} s a page); Ollama {b.get('ollama_version')}"
                  f"; failed requests {b.get('requests_failed')}, incomplete pages {b.get('pages_incomplete')}"]
        if b.get("error"):
            lines.append(f"* translation error: {b['error']}")
    progress = b.get("progress") or {}
    lines.append(f"* console: {progress.get('pages_read')} pages read in {progress.get('detection_ocr_s')} s"
                 + (f"; translation run {progress['translation']['runs_done']} of {progress['translation']['runs']} "
                    f"after {progress['translation']['seconds']} s (all of them at that pace: "
                    f"{progress['translation']['seconds_all_at_this_pace']} s)" if progress.get("translation") else ""))
    lines.append(f"* exit code {b.get('exit_code')}, the run's step {b.get('run_step_s')} s")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------- the run's table
def _time(text: Any) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _between(a: datetime | None, b: datetime | None) -> int | None:
    return round((b - a).total_seconds()) if a is not None and b is not None else None


def job_times(job: dict[str, Any]) -> dict[str, Any]:
    """A job's seconds by GitHub's step times: waiting for a runner, setting up (to the start of its "Run:" step),
    the run, and the rest (the summary and the upload); the "Set up: ..." steps one by one."""
    started, done = _time(job.get("started_at")), _time(job.get("completed_at"))
    steps = [s for s in job.get("steps") or [] if isinstance(s, dict)]
    run = next((s for s in steps if str(s.get("name", "")).startswith("Run:")), None)
    r0 = _time(run.get("started_at")) if run else None
    r1 = _time(run.get("completed_at")) if run else None
    if run is None or r0 is None or run.get("conclusion") == "skipped":
        setup, run_s, after = _between(started, done), None, None
    else:
        setup, run_s, after = _between(started, r0), _between(r0, r1), _between(r1, done)
    set_up = {str(s["name"])[len("Set up: "):]: _between(_time(s.get("started_at")), _time(s.get("completed_at")))
              for s in steps if str(s.get("name", "")).startswith("Set up: ") and s.get("conclusion") != "skipped"}
    return {"name": job.get("name"), "result": job.get("conclusion") or job.get("status"),
            "waited_s": _between(_time(job.get("created_at")), started), "setup_s": setup, "run_s": run_s,
            "after_s": after, "total_s": _between(started, done),
            "run_result": run.get("conclusion") if run else None, "set_up": set_up}


def _mmss(seconds: Any) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


CACHE_LIMIT_GB = 10  # what GitHub keeps of a repository's caches before it deletes the least recently used


def read_lines(path: Path | None) -> list[dict[str, Any]]:
    """A file of JSON objects, one a line (what is not one is left out)."""
    out = []
    for line in read_text(path).splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def caches_line(caches: list[dict[str, Any]]) -> str:
    """The repository's caches (GitHub's list of them): their sum against the limit, by branch and by kind (the key
    up to its first dash and a word: models, ollama-setup, ollama-store, setup-python's pip, ...)."""
    if not caches:
        return ""
    gb = lambda items: round(sum(int(c.get("size_in_bytes") or 0) for c in items) / 1e9, 2)  # noqa: E731
    refs: dict[str, list[dict[str, Any]]] = {}
    kinds: dict[str, list[dict[str, Any]]] = {}
    for c in caches:
        refs.setdefault(str(c.get("ref")), []).append(c)
        key = str(c.get("key") or "")
        kind = "-".join(key.split("-")[:2]) if key.startswith("ollama-") else key.split("-")[0]
        kinds.setdefault(kind, []).append(c)
    return (f"The repository's caches: {gb(caches)} GB in {len(caches)} caches, of the {CACHE_LIMIT_GB} GB GitHub keeps; by "
            "branch " + ", ".join(f"{ref} {gb(items)} GB" for ref, items in sorted(refs.items())) + "; by kind "
            + ", ".join(f"{kind} {gb(items)} GB ({len(items)})" for kind, items in sorted(kinds.items())) + ".")


def table(artifacts: Path, jobs_file: Path | None, merged: Any, caches_file: Path | None = None) -> str:
    summaries = [s for s in (read_json(p) for p in sorted(artifacts.rglob("summary.json"))) if isinstance(s, dict)]
    stand = sorted((s for s in summaries if s.get("kind") == "standin"), key=lambda s: str(s.get("group")))
    marks = sorted((s for s in summaries if s.get("kind") == "benchmark"), key=lambda s: str(s.get("title")))
    prepared = [f for f in (read_json(p) for p in sorted(artifacts.rglob("facts.json"))) if isinstance(f, dict)
                and f.get("caches")]
    out = ["# GPU checks on runners (trial)", ""]
    machine = next((s.get("machine") for s in summaries if s.get("machine")), None)
    if machine:
        out.append(f"Runner: {machine.get('os')}, {machine.get('cpu')} ({machine.get('cores')} cores, "
                   f"{machine.get('logical_processors')} logical processors), {machine.get('ram_gb')} GB, display "
                   f"adapters {machine.get('gpus')}; session {machine.get('session')}, interactive "
                   f"{machine.get('interactive')}.")
    if prepared:
        p = prepared[0]
        out.append(f"Ollama {p.get('ollama_tag')}; made by this run's prepare job, in GB: {p.get('caches')}.")
    line = caches_line(read_lines(caches_file))
    if line:
        out.append(line)
    out.append("")
    jobs = [job_times(job) for job in read_lines(jobs_file) if job.get("name") != "Summary"]
    if jobs:
        out += ["## Jobs (minutes:seconds, GitHub's step times)", "",
                "| job | result | waited | setting up | run | after it | total | set-up steps (s) |",
                "|---|---|---|---|---|---|---|---|"]
        for j in jobs:
            steps = ", ".join(f"{k} {v}" for k, v in j["set_up"].items())
            out.append(f"| {j['name']} | {j['result']} | {_mmss(j['waited_s'])} | {_mmss(j['setup_s'])} | "
                       f"{_mmss(j['run_s'])} | {_mmss(j['after_s'])} | {_mmss(j['total_s'])} | {steps} |")
        out.append("")
    if stand:
        out += ["## Stand-in viewer (tools/standin_e2e.py)", "",
                "| group | verdict | capture used | frames sharp/soft/black, spinner, unknown | window ready s | run s | "
                "released by --timeout | points to a fault | points to a slow computer |",
                "|---|---|---|---|---|---|---|---|---|"]
        for s in stand:
            c = s.get("captures") or {}
            frames = "/".join(str(c.get(k, 0)) for k in ("sharp", "soft", "black")) + ", " + ", ".join(
                str(c.get(k, 0)) for k in ("spinner", "unknown")) if s.get("captures") is not None else "-"
            timed = (s.get("slowness") or {}).get("scenarios released by --timeout, not at rest") or []
            out.append(f"| {s.get('group')} | {s.get('verdict')}{': ' + str(s['why']) if s.get('why') else ''} | "
                       f"{(s.get('capture_route') or {}).get('used', '-')} | {frames} | {s.get('ready_s', '-')} | "
                       f"{s.get('seconds', '-')} | {', '.join(timed) or '-'} | {len(s.get('faults') or {})} | "
                       f"{len(s.get('slowness') or {})} |")
        out += ["", "| group | scenario | turns | rested | finished within the rest | translated at rest | finished ms "
                "med/max | meaning |", "|---|---|---|---|---|---|---|---|"]
        for s in stand:
            for row in s.get("segments") or []:
                out.append(f"| {s.get('group')} | {row['scenario']} | {row['turns']} | {row['rested']} | "
                           f"{row['finished_within_rest']} | {row['translated_at_rest']} | {_pair(row['finished_ms'])} | "
                           f"{(s.get('meaning') or {}).get(row['scenario'], '')} |")
        out.append("")
    if marks or isinstance(merged, dict):
        out += ["## Benchmark (tools/openmantra_eval.py, a title a job)", "",
                "| title | verdict | pages | det+OCR s | translation s | total s | F1 | OCR CER | chrF | gen tok/s | "
                "prompt tok/s | read so far |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in marks:
            s = b.get("seconds") or {}
            prog = b.get("progress") or {}
            so_far = f"{prog.get('pages_read')} pages"
            if prog.get("translation"):
                t = prog["translation"]
                so_far += f", run {t['runs_done']}/{t['runs']} (all ~{t['seconds_all_at_this_pace']} s)"
            out.append(f"| {b.get('title')} {', '.join(b.get('series') or [])} | {b.get('verdict')} | "
                       f"{b.get('pages', '-')} | {s.get('detection_ocr', '-')} | {s.get('translation', '-')} | "
                       f"{s.get('total', '-')} | {(b.get('detection') or {}).get('f1', '-')} | "
                       f"{(b.get('ocr_cer') or {}).get('gold_corpus', '-')} | {(b.get('translation') or {}).get('chrf', '-')} | "
                       f"{(b.get('speed') or {}).get('eval_tok_per_s', '-')} | "
                       f"{(b.get('speed') or {}).get('prompt_tok_per_s', '-')} | {so_far} |")
        if isinstance(merged, dict):
            a = (merged.get("summary") or {}).get("all") or {}
            s = merged.get("seconds") or {}
            runs = (merged.get("translation") or {}).get("run_results") or []
            speed = (runs[0].get("speed") if runs else None) or {}
            out.append(f"| all, pooled ({len((merged.get('dataset') or {}).get('series') or [])} titles) | "
                       f"{'differences: ' + '; '.join(merged['differences']) if merged.get('differences') else 'joined'} | "
                       f"{(merged.get('dataset') or {}).get('pages', '-')} | {s.get('detection_ocr', '-')} | "
                       f"{s.get('translation', '-')} | longest part {s.get('longest_part', '-')} | {a.get('f1', '-')} | "
                       f"{(a.get('ocr_gold') or {}).get('corpus', '-')} | {(a.get('translation') or {}).get('chrf', '-')} | "
                       f"{speed.get('eval_tok_per_s', '-')} | {speed.get('prompt_tok_per_s', '-')} | |")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="kind", required=True)
    for kind in ("standin", "bench"):
        p = sub.add_parser(kind)
        p.add_argument("report", type=Path, help="the tool's report (results) file; it need not be there")
        p.add_argument("--console", type=Path, help="the run's console output")
        p.add_argument("--facts", type=Path, help="the job's facts.json (helpers.ps1)")
        p.add_argument("--group" if kind == "standin" else "--title", required=True)
        p.add_argument("--out", type=Path, required=True, help="the folder for summary.json and summary.md")
    p = sub.add_parser("table")
    p.add_argument("artifacts", type=Path, help="the folder the run's artifacts were downloaded into")
    p.add_argument("--jobs", type=Path, help="the run's jobs, one JSON object a line (GitHub's jobs API)")
    p.add_argument("--caches", type=Path, help="the repository's caches, one JSON object a line (GitHub's API)")
    p.add_argument("--merged", type=Path, help="tools/openmantra_merge.py's joined file")
    p.add_argument("--out", type=Path, help="also write the tables to this file")
    args = ap.parse_args(argv)
    if args.kind == "table":
        text = table(args.artifacts, args.jobs, read_json(args.merged), args.caches)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return 0
    facts = read_json(args.facts) or {}
    console = read_text(args.console)
    if args.kind == "standin":
        summary = standin(read_json(args.report), console, facts, args.group)
        text = standin_md(summary)
    else:
        summary = bench(read_json(args.report), console, facts, args.title)
        text = bench_md(summary)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (args.out / "summary.md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
