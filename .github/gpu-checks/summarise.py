"""The numbers of the GPU computer's checks on GitHub's runners (.github/workflows/gpu-checks.yml), from the tools'
own reports, and their verdicts: no line of the dataset, read or translated, and nothing of a page.

    python .github/gpu-checks/summarise.py standin REPORT --console FILE --facts FILE --group G --out DIR
                                                   [--timeout S] [--check]
    python .github/gpu-checks/summarise.py bench RESULTS --console FILE --facts FILE --title N --out DIR
                                                 [--expected FILE] [--check]
    python .github/gpu-checks/summarise.py table ARTIFACTS --jobs JOBS [--caches CACHES] [--merged MERGED]
                                                 [--expected FILE] [--out FILE]

``standin`` (tools/standin_e2e.py's report.json) and ``bench`` (tools/openmantra_eval.py's results file) write
summary.json and summary.md into DIR. A report that is not there, as after a run stopped by the step's time limit, is
said, and what the console shows of the run is counted instead: its tracebacks and exception types, the tool's own
words on why a run stopped, and for the benchmark the pages read and the pages translated so far (their seconds, and
the time all of the series' pages would take at that pace). Nothing else is read out of the console. ``table`` prints the run's
tables in Markdown for the summary job's page: each job's waiting, setting up, run and the rest by GitHub's own step
times (*JOBS*: the jobs API's jobs, one JSON object a line), the repository's caches against GitHub's limit
(*CACHES*: its list of them, one a line), the stand-in's verdicts and scenarios, the benchmark's titles and, with
*MERGED* (tools/openmantra_merge.py's file), the scores over all of them against the expected ones. Standard library
only: the summary job has no virtual environment.

A stand-in run is judged by what it must show on any computer however slow (`correctness`: the run went through, the
window followed the stand-in and nothing else, nothing was kept or shown from a frame that was not the sharp one, no
request was sent for nothing, no job was cancelled with its page on show (but for one that gave its page over to the
frame of a new size, `_resized_away`), nothing of a line asked as it was read and taken back once its page was read
stayed in the page's lines or on show when the page was finished (the lines so sent and taken back are reported, never
a failure: `_streamed`), a page translated before came back without a request, each scenario did what
it is for - the modes entered and left, the page keys handed on, ...). What depends on the
computer's speed - the rested turns translated within their rest, the holds of ``--wait-done`` that reached their
cap, lettering left on a page until the window's next capture, pages left half done in the cache - is reported beside
it and never fails a run (`speed`); so is what each scenario was meant to show and whether it still did (`meanings`).
In scenario x with --wait-done, whose soft frames stay on show until the window has asked on them, what the window
shows or keeps of them is not judged by the soft frames' criteria (`_judged`: a frame on show so long has settled, for
the window as for a reader). Scenario k (pages flipped past at 0.5, 1 and 2 s a page, then read back: `K_PACES`) is
judged on what the pages turned past guarantee on any computer (`_k_correctness`): a request sent for nothing there is
only a page job's asked before its frame's confirmation and dropped as the page was flipped past (none on a frame that
was not the sharp one, none of the backlog's), the backlog holds no frame after its read, and once the window has come
to rest at the end it holds nothing and no screen is told at work; the stale lettering, the soft frames kept and left
are the criteria of all the scenarios. How many pages it caught, how the pages read back began and how long they took
are reported (`k_figures`, and its meaning). With --check, ``standin`` exits 1 when a criterion of correctness failed
(or there is no report), and only then.

A benchmark title is judged by its scores against the expected ones (`EXPECTED`, the runner's own figures per title),
within their tolerance: with --check, ``bench`` exits 1 when one of F1, CER or chrF leaves it, or the translation did
not complete. A run cut short (fewer pages than expected) is not compared.
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

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "benchmark-expected.json"
REST_MS = 2000  # standin_e2e.REST_MS: a screen on show sharp so long is one the reader rested on
STALE_MS = 1000  # standin_e2e.STALE_MS: lettering of a page left on show so long is an overlay left behind
RAN_ON_MS = 5000  # scenario x: a request cancelled in flight that ran on longer after its job's cancel did not stop
TRACEBACK = "Traceback (most recent call last):"
EXCEPTION = re.compile(r"^((?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Error|Exception|Interrupt|Exit))\b")
STOPPED = re.compile(r"^run stopped: (.+)$")  # standin_e2e's Director.stop (its reasons name no window and no page)
PAGE_LINE = re.compile(r"^\s+\S.* p(\d+): gold (\d+), .*\[([0-9.]+) s\]\s*$")  # openmantra_eval, a page read
TRANSLATED_LINE = re.compile(r"^\s+\S.*: page (\d+)/(\d+) translated, (\d+) lines so far, (\d+) s\s*$")  # ... a page
OTHER_STATES = ("black", "spinner", "unknown")
AT_REST = ("a", "d", "r", "o", "z", "f", "f2")  # the scenarios whose rests are for reading translated pages
TURNED = ("next", "previous", "jump")
K_PACES = ("k5", "k1", "k2", "k3")  # standin_e2e.K_PACES: scenario k, pages flipped past at a pace, then read back
K_STAYED_MS = 800  # standin_e2e.K_STAYED_MS: a page flipped past whose sharp frame stayed so long is one to catch


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


def _waits(run: dict[str, Any]) -> dict[str, Any]:
    """``--wait-done``'s holds and kept soft frames (`standin_e2e.Director.waits_report`); {} without it."""
    waits = run.get("waits")
    return waits if isinstance(waits, dict) else {}


# Why something a job on a frame that was not the sharp one stored is in the cache at the end (standin_e2e.left_why):
# these two are faults wherever they come (a job put back must leave nothing; a sharp frame that came while the job ran
# or within its open time takes its confirmation back); the others are the window's design for a sharp frame that came
# late (after the open time, a viewer not yet seen drawing soft first, a job without a gate on a frame that settled,
# decided by the job after it) or no sharp frame at all - a slow capture's matter, reported (`speed`).
LEFT_FAULTS = ("put back, yet left", "sharp frame not taken back")


def _segment_at(turns: list[dict[str, Any]]) -> Any:
    """The scenario at a time of the run (seconds from its start, as the report's t_s): the one of the turn before."""
    starts = [(t.get("t_s"), str(t.get("segment"))) for t in turns if t.get("t_s") is not None]

    def at(t_s: Any) -> str:
        seg = "start"
        if t_s is None:
            return seg
        for when, name in starts:
            if when <= t_s:
                seg = name
        return seg

    return at


def _judged(run: dict[str, Any]) -> Any:
    """Whether what the window showed and kept in a scenario is judged by the soft frames' criteria: not in x with
    --wait-done, whose soft frames are kept on show until the window has asked on them - a frame that stays so long is
    one that settled, for the window as for a reader, and what it then shows or keeps of it is the design's (reported)."""
    keeps = bool(_waits(run).get("keeps"))
    return lambda segment: not (keeps and segment == "x")


def _left_on_soft(run: dict[str, Any], segment_at: Any) -> list[dict[str, Any]] | None:
    """The jobs on a frame that was not the sharp one with something of theirs in the cache at the end, each with its
    scenario; None when the cache at the end was not read."""
    at_end = (run.get("jobs") or {}).get("soft_frames_at_end") or {}
    if at_end.get("left_in_the_cache") is None:
        return None
    return [{**r, "segment": segment_at(r.get("t_s"))} for r in at_end.get("left") or [] if isinstance(r, dict)]


def _resized_away(cancel: dict[str, Any], job: dict[str, Any] | None, resizes: list[Any]) -> bool:
    """Whether a page job cancelled with its page on show gave that page over to its frame at a new size of the stand-in
    (standin_e2e.resized_away, the window's design): the tool's own word where it says it; for a report of a tool
    before it, from its lists - a change of size came while the job ran (`resizes`' from_s between the job's start and
    its cancel), from the size of the job's frame, and the window had captured the new size by the cancel (its
    first_capture_ms after the change; the times are to 0.01 s)."""
    if cancel.get("resized_away") is not None:
        return bool(cancel["resized_away"])
    start, end = (job or {}).get("t_s"), cancel.get("t_s")
    if start is None or end is None:
        return False
    for r in resizes:
        if not isinstance(r, dict) or r.get("from_s") is None or r.get("first_capture_ms") is None:
            continue
        if (start <= r["from_s"] <= end and r.get("size_before") == job.get("size")
                and r["from_s"] + r["first_capture_ms"] / 1000 <= end + 0.01):
            return True
    return False


def _displays(run: dict[str, Any]) -> list[dict[str, Any]]:
    table = run.get("displays") or {}
    columns = table.get("columns") or []
    return [dict(zip(columns, row)) for row in table.get("rows") or [] if isinstance(row, list)]


def segment_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Per scenario: the tool's own table (`standin_e2e.segment_table`) and, from its turns, the rests the script gave
    the turns that came to rest and how many of their pages were finished within them; with --wait-done, the holds
    of its rests and how long they held."""
    rows = _turns(run)
    holds = [h for h in _waits(run).get("holds") or [] if isinstance(h, dict)]
    out = []
    for seg in run.get("segments") or []:
        name = seg.get("segment")
        rested = _rested([r for r in rows if r.get("segment") == name])
        mine = [h for h in holds if h.get("segment") == name]
        out.append({"scenario": name, "turns": seg.get("turns"), "rested": seg.get("rested"),
                    "rest_ms_median": median([r.get("rest_ms") for r in rested]),
                    "finished_within_rest": sum(1 for r in rested if _finished_in_rest(r)),
                    "translated_at_rest": seg.get("translated_at_rest"),
                    "first_request_ms": [seg.get("first_request_ms_median"), seg.get("first_request_ms_max")],
                    "first_lettered_ms": [seg.get("first_lettered_ms_median"), seg.get("first_lettered_ms_max")],
                    "finished_ms": [seg.get("finished_ms_median"), seg.get("finished_ms_max")],
                    "jobs": seg.get("jobs"), "requests": seg.get("requests"),
                    "wasted_requests": seg.get("wasted_requests"), "stale": seg.get("stale"),
                    "not_following": seg.get("not_following"),
                    "holds": len(mine), "held_ms": [median([h.get("waited_ms") for h in mine]),
                                                    max([h.get("waited_ms") or 0 for h in mine], default=None)],
                    "holds_by_why": dict(Counter(str(h.get("why")) for h in mine))})
    return out


def meanings(report: dict[str, Any]) -> dict[str, str]:
    """Per scenario, whether the run still showed what the scenario is for ("holds", "partly", "lost" or "unclear",
    with the count it rests on): on a slower computer a scripted rest can be shorter than a page takes, the model can
    be loaded before the turns meant to come while it loads, a soft frame can be gone before the window asks on it
    (--wait-done holds the rests until the page is finished, and the soft frames of x until the window asked)."""
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
        elif name == "x":
            cancel = run.get("cancel_in_flight") or {}
            soft, cut = cancel.get("requests_on_soft") or 0, cancel.get("cancelled_in_flight") or 0
            kept = [k for k in _waits(run).get("keeps") or [] if isinstance(k, dict)]
            how = (f"its soft frames kept until the window asked ({sum(1 for k in kept if k.get('why') == 'asked')} "
                   f"of {len(kept)})" if kept else f"within --cancel-soft-ms ({cancel.get('soft_ms')} ms)")
            out[name] = (f"holds: {cut} requests cancelled in flight ({soft} on the soft frame)" if cut
                         else f"partly: {soft} requests on the soft frame, none cancelled in flight" if soft
                         else f"lost: no request on the soft frame, {how}: the window read it too slowly here")
        elif name in K_PACES:
            out[name] = _k_meaning(_k_paces(run).get(name))
        else:
            out[name] = at_rest(name)
    return out


def _k_paces(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Scenario k's paces as the tool tells them (`standin_e2e.k_block`); {} without it."""
    paces = (run.get("scenario_k") or {}).get("paces") or {}
    return {k: v for k, v in paces.items() if isinstance(v, dict)} if isinstance(paces, dict) else {}


def _k_meaning(k: dict[str, Any] | None) -> str:
    """Whether a pace of scenario k showed what it is for: every page flipped past whose sharp frame stayed
    K_STAYED_MS caught by the backlog (or finished while on show), none that did not, and each page caught that was
    read back begun with no new read (from the cache, or from what the backlog read). On a slower computer the window
    sees a sharp frame later, and the backlog may not have finished a caught page when it is read back."""
    if not k:
        return "unclear: the tool told nothing of the pace"
    flips = k.get("flips") or 0
    if not flips:
        return "unclear: no page flipped past"
    caught, done, stayed = k.get("caught") or 0, k.get("done_on_show") or 0, k.get("stayed") or 0
    back, back_caught = k.get("read_back_caught_no_new_read") or 0, k.get("read_back_caught") or 0
    says = (f"{caught} of {flips} pages flipped past caught and {done} finished on show, {stayed} stayed "
            f"{K_STAYED_MS} ms; {back} of {back_caught} caught pages read back begun with no new read")
    if k.get("agree") == flips and back == back_caught:
        return "holds: " + says
    if caught or done or back:
        return "partly: " + says
    return ("lost: " if stayed else "unclear: ") + says


def k_figures(report: dict[str, Any]) -> dict[str, Any] | None:
    """Scenario k's figures, per pace, reported and never a failure (they depend on the computer's speed): the pages
    flipped past, those whose sharp frame stayed K_STAYED_MS, caught and finished on show; the pages read back, how
    they began, their first lettered bubble (with the backlog holding pages, and all of them); the time the backlog
    took to have nothing left after the turn back, its steps, requests and the most it held. None without k."""
    run = report.get("run") or {}
    paces = _k_paces(run)
    if not paces:
        return None
    keys = ("pace_ms", "flips", "stayed", "caught", "done_on_show", "agree", "read_back", "read_back_cached",
            "read_back_caught", "read_back_caught_no_new_read", "read_back_how", "first_lettered_read_back",
            "first_lettered_with_backlog", "backlog_pages_most", "drain_s", "drain_from_flips_end_s", "steps",
            "steps_busy_s", "waits_ms", "same_page_turn_waits_ms", "background_requests", "page_requests", "peak_mb",
            "results_unconfirmed", "lettered_soft_turns", "stale")
    out: dict[str, Any] = {name: {key: k.get(key) for key in keys} for name, k in paces.items()}
    told = (run.get("scenario_k") or {}).get("told") or {}
    out["told_done_then_working_again"] = told.get("done_told_working_again")
    return out


def _k_correctness(run: dict[str, Any], names: list[str], check: Any) -> None:
    """Scenario k's criteria, true on any computer however slow: per pace, every request sent for nothing a page job's
    asked while its frame's confirmation was pending and dropped as the page was flipped past (none on a frame that
    was not the sharp one - `standin_e2e.wasted_why` -, none of the backlog's), and no frame the backlog held after
    it was read; at the end of the run - judged when the window came to rest there within --timeout, else the hang
    is the criterion that fails - nothing held by the backlog and no screen told at work."""
    paces = _k_paces(run)
    wasted = run.get("wasted_requests") or {}
    listed = [w for w in wasted.get("list") or [] if isinstance(w, dict)]
    requests = run.get("request_list") or {}
    columns = requests.get("columns") or []
    rows = [dict(zip(columns, row)) for row in requests.get("rows") or [] if isinstance(row, list)]
    segment_at = _segment_at(_turns(run))
    mine = [n for n in names if n in K_PACES]
    for name in mine:
        k = paces.get(name)
        check(name, "the tool told the pace (its pages flipped past and read back)", isinstance(k, dict), None)
        if not isinstance(k, dict):
            continue
        if listed or not wasted.get("by_segment"):
            bad = [[w.get("t_s"), w.get("why"), w.get("gate")] for w in listed if w.get("segment") == name
                   and not (w.get("why") == "dropped" and w.get("gate") == "pending")]
        else:  # (a tool that gave the counts only: none can be told apart)
            bad = [[None, "count", n] for s, n in wasted["by_segment"].items() if s == name and n]
        bad += [[r.get("t_s"), "backlog", r.get("wasted")] for r in rows
                if r.get("side") == "backlog" and r.get("wasted") and segment_at(r.get("t_s")) == name]
        check(name, "every request sent for nothing was a page job's asked before its frame was confirmed and "
              "dropped as the page was flipped past (none on a frame that was not the sharp one, none of the "
              "backlog's)", not bad, bad)
        most = k.get("frames_held_after_read_most")
        check(name, "the backlog held no frame after it was read", not most, most)
    if not mine:
        return
    end = (run.get("released") or {}).get("end") or {}
    if isinstance(end, dict) and end.get("timed_out"):
        return
    last = paces.get(mine[-1]) or {}
    check(mine[-1], "the backlog held nothing at the end of the run, the window at rest (0 bytes)",
          not last.get("bytes_at_end"), last.get("bytes_at_end"))
    left = ((run.get("scenario_k") or {}).get("told") or {}).get("left_working")
    check(mine[-1], "no screen was left told at work at the end of the run, the window at rest", not left, left)


def _check(found: list[dict[str, Any]], scenario: str, criterion: str, ok: bool, seen: Any = None) -> None:
    found.append({"scenario": scenario, "criterion": criterion, "ok": bool(ok), "seen": None if ok else seen})


def correctness(report: dict[str, Any], timeout_s: float | None = None) -> list[dict[str, Any]]:
    """What the run must show however slow the computer, criterion by criterion ({scenario, criterion, ok, seen}:
    *seen* is what failed it). *timeout_s* is the tool's --timeout: a scenario released by it found the window not at
    rest for that long, a hang on any computer; one released because its mode was not on within the tool's
    MODE_WAIT_S is speed (`speed`)."""
    run = report.get("run") or {}
    names = [str(n) for n in report.get("scenarios") or []]
    found: list[dict[str, Any]] = []

    def check(scenario: str, criterion: str, ok: Any, seen: Any = None) -> None:
        _check(found, scenario, criterion, bool(ok), seen)

    # the run as a whole
    failed = run.get("failed") or ""
    check("all", "the run went through its scenarios (the tool did not stop it)", not failed, failed)
    captures = run.get("captures") or {}
    readable = int(captures.get("sharp") or 0) + int(captures.get("soft") or 0)
    check("all", "the window captured the stand-in's frames", readable > 0, dict(captures))
    guard = run.get("guard") or {}
    refused = sorted(set(guard.get("refused") or []))
    check("all", "the guard refused no call", not refused, refused)
    check("all", "the window chose the stand-in and nothing else", guard.get("only_the_stand_in_chosen") is not False,
          guard.get("only_the_stand_in_chosen"))
    hooks = dict((run.get("errors") or {}).get("hooks") or {})
    check("all", "no error in the tool's hooks", not hooks, hooks)
    cleanup = report.get("cleanup") or {}
    log = cleanup.get("log") or {}
    lines = {k: v for k, v in (log.get("lines") or {}).items() if k in ("tracebacks", "error", "critical") and v}
    types = dict(log.get("exception_types") or {})
    check("all", "no traceback, error or exception in the window's log", not lines and not types, {**lines, **types})
    jobs = run.get("jobs") or {}
    check("all", "no page lettered from a black frame, a spinner or a frame without the stand-in's code",
          not jobs.get("on_black_spinner_unknown_shown"), jobs.get("on_black_spinner_unknown_shown"))
    by_id = {j.get("id"): j for j in run.get("job_list") or [] if isinstance(j, dict)}
    false = [c for c in (run.get("cancels") or {}).get("page_still_on_show") or [] if isinstance(c, dict)
             and not _resized_away(c, by_id.get(c.get("id")), run.get("resizes") or [])]
    check("all", "no job cancelled while its page was on show", not false, [c.get("t_s") for c in false])
    turns = _turns(run)
    segment_at = _segment_at(turns)
    judged = _judged(run)
    left = _left_on_soft(run, segment_at)
    if left is None:  # (the cache at the end not read: what the jobs stored as they ended, the older count)
        starts = {j.get("id"): j.get("t_s") for j in run.get("job_list") or [] if isinstance(j, dict)}
        kept = [k for k in jobs.get("kept_from_unsettled_frames") or [] if judged(segment_at(starts.get(k)))]
        check("all", "nothing kept from a frame that was not the sharp one", not kept, kept)
    else:
        faults = [[r.get("segment"), r.get("page"), r.get("why")] for r in left if r.get("why") in LEFT_FAULTS
                  and judged(r.get("segment"))]
        check("all", "nothing left in the cache from a frame that was not the sharp one where the sharp frame came "
              "in time to take it back", not faults, faults)
    late = [[t.get("segment"), t.get("page"), t.get("lettered_unsettled_ms"), t.get("captured_sharp_ms")]
            for t in turns if judged(t.get("segment")) and t.get("captured_sharp_ms") is not None
            and (t.get("lettered_unsettled_ms") or 0) > t["captured_sharp_ms"] + STALE_MS]
    check("all", "no lettering read from a frame that was not the sharp one shown over 1 s after the window "
          "captured the sharp one", not late, late)
    empty = [[segment_at(row.get("t_s")), row.get("page")] for row in _displays(run)
             if row.get("kind") == "translated" and not row.get("lettered") and row.get("from") not in ("sharp", None)
             and judged(segment_at(row.get("t_s")))]
    if not run.get("displays"):  # (no list of what the window showed: the run's count)
        empty = [["all", n] for n in [run.get("empty_unsettled_results_shown") or 0] if n]
    check("all", "no empty result read from a frame that was not the sharp one shown", not empty, empty)
    wasted = {s: n for s, n in ((run.get("wasted_requests") or {}).get("by_segment") or {}).items()
              if s != "x" and s not in K_PACES and n}
    check("all", "no request sent for nothing (outside scenario x, whose point they are)", not wasted, wasted)
    # (scenario k: a page job asks before its frame is confirmed, and a page flipped past drops it - `_k_correctness`)
    # (a line asked as it was read and taken back once its unit was read - `streaming.LineStream` - is not one: the
    # tool counts it apart, `streamed_lines`; what it must leave is judged here)
    streamed = run.get("streamed_lines")
    if isinstance(streamed, dict) and streamed.get("units"):
        kept = {k: streamed.get(k) for k in ("final_from_taken_back", "early_left_at_close", "early_left_at_result")
                if streamed.get(k)}
        check("all", "nothing of a line taken back once its page was read stayed in the page's lines (and so in the "
              "cache) or on show when the page was finished", not kept, kept)
    stale = [s for s in (run.get("incidents") or {}).get("stale_overlays") or [] if isinstance(s, dict)]
    if all("seen_ms" in s for s in stale):  # (a tool before it said when the window saw the change: not looked at)
        late = [s for s in stale if (s.get("seen_ms") or 0) > STALE_MS]
        check("all", "no lettering of a page the stand-in had left on show over 1 s after the window captured the "
              "new one", not late, [[s.get("from_s"), s.get("seen_ms")] for s in late])
    priority = run.get("server_priority")
    if isinstance(priority, dict):  # (a tool before it did not watch the server's priority: not looked at)
        low = priority.get("other_requests_low") or []
        check("all", "no request but the backlog's was computed while the server was lowered for the backlog's work",
              not low, low[:5])
    server = report.get("server_started")
    if isinstance(server, dict):
        check("all", "the Ollama TASlation started was stopped at the end", server.get("stopped") is True,
              server.get("stopped"))
    check("all", "the scratch state was deleted at the end", cleanup.get("state_deleted") is not False,
          cleanup.get("state_deleted"))
    released = {k: v for k, v in (run.get("released") or {}).items() if isinstance(v, dict)}
    if timeout_s:
        hung = sorted(k for k, v in released.items() if v.get("timed_out")
                      and (k == "end" or (v.get("waited_s") or 0) >= timeout_s - 1))
        check("all", f"the window came to rest before every scenario and at the end (within --timeout {timeout_s:g} "
              "s)", not hung, hung)
    holds = [h for h in _waits(run).get("holds") or [] if isinstance(h, dict)]
    if holds:
        idle = [[h.get("segment"), h.get("page")] for h in holds if h.get("why") == "idle"]
        check("all", "no rested page left unfinished with the window at rest (--wait-done)", not idle, idle)

    # a page translated at rest before comes back without a request (the cache, or the lines kept)
    done: set[tuple[Any, Any]] = set()
    again: list[list[Any]] = []
    for t in turns:
        screen = (t.get("page"), t.get("spread"))
        if screen in done and t.get("why") in TURNED and (t.get("requests") or 0) > 0:
            again.append([t.get("segment"), t.get("page"), t.get("requests")])
        if t.get("at_rest") == "translated" and t.get("at_rest_from") == "sharp":
            done.add(screen)
    check("all", "a page translated at rest came back without a request", not again, again)

    # scenario by scenario
    by_name: dict[str, list[dict[str, Any]]] = {}
    for t in turns:
        by_name.setdefault(str(t.get("segment")), []).append(t)
    entered = (run.get("modes") or {}).get("entered") or {}
    for name in names:
        mine = by_name.get(name) or []
        check(name, "the stand-in drew its turns", bool(mine), len(mine))
        if mine:
            last = mine[-1]
            check(name, "its last page was translated once the window came to rest",
                  last.get("at_rest") == "translated" or last.get("finished_ms") is not None,
                  [last.get("page"), last.get("at_rest")])
        if name == "c":
            check(name, "the window became ready", run.get("ready_s") is not None, run.get("ready_s"))
        elif name == "b":
            check(name, "its 10 quick turns were drawn", len(mine) == 10, len(mine))
        elif name in ("t", "t2"):
            key = (run.get("page_keys") or {}).get(name) or {}
            check(name, "the window handed its page key on to the viewer", "handed_on" in key, sorted(key))
            if name == "t":
                facts = entered.get("t") or {}
                check(name, "the full screen in the Translator role, and the Reader role again after",
                      facts.get("full_screen") is True and facts.get("role_on_it") == "translator"
                      and facts.get("role_after") == "reader",
                      {k: facts.get(k) for k in ("full_screen", "role_on_it", "role_after")})
        elif name == "r":
            facts = entered.get("r") or {}
            check(name, "the full screen entered and left", facts.get("full_screen") is True and facts.get("left") is True,
                  {k: facts.get(k) for k in ("full_screen", "left")})
        elif name == "o":
            facts = entered.get("o") or {}
            check(name, "over the book entered and left by the hot key",
                  facts.get("over_before_reading") is True and facts.get("left_by_hot_key") is True,
                  {k: facts.get(k) for k in ("over_before_reading", "left_by_hot_key")})
        elif name == "x":
            cancel = run.get("cancel_in_flight") or {}
            ran_on = (cancel.get("ran_on_after_cancel_ms") or {}).get("max")
            check(name, f"a request cancelled in flight ended within {RAN_ON_MS} ms of its job's cancel",
                  ran_on is None or ran_on <= RAN_ON_MS, ran_on)
        elif name == "f":
            check(name, "the dark theme", (run.get("theme") or {}).get("after") == "dark", run.get("theme"))
        elif name == "f2":
            sizes = [r for r in run.get("resizes") or [] if isinstance(r, dict)]
            check(name, "the narrow window's page read at its new size",
                  any(r.get("first_capture_ms") is not None for r in sizes), len(sizes))
    _k_correctness(run, names, check)
    return found


def speed(report: dict[str, Any], timeout_s: float | None = None) -> dict[str, Any]:
    """What depends on the computer's speed, reported and never a failure: scenarios released because a mode was not on
    within the tool's wait for it, rested turns not finished within their rest or not translated at its end, holds of
    --wait-done that reached their cap, spells the window did not follow the stand-in, lettering of a page left until
    the window's next capture showed the change, jobs cancelled as the reader turned away, pages left half done in the
    cache at the end (their lines kept for later, by design)."""
    run = report.get("run") or {}
    released = {k: v for k, v in (run.get("released") or {}).items() if isinstance(v, dict)}
    segments = run.get("segments") or []
    rested = _rested(_turns(run))
    stale = [s for s in (run.get("incidents") or {}).get("stale_overlays") or [] if isinstance(s, dict)]
    cancels = [c for c in (run.get("cancels") or {}).get("list") or [] if isinstance(c, dict)]
    holds = [h for h in _waits(run).get("holds") or [] if isinstance(h, dict)]
    turns = _turns(run)
    segment_at, judged = _segment_at(turns), _judged(run)
    left = _left_on_soft(run, segment_at) or []
    left_late = Counter(str(r.get("why")) for r in left if r.get("why") not in LEFT_FAULTS or not judged(r.get("segment")))
    until_seen = sum(1 for t in turns if (t.get("lettered_unsettled_ms") or 0) > 0 and (
        not judged(t.get("segment")) or t.get("captured_sharp_ms") is None
        or t["lettered_unsettled_ms"] <= t["captured_sharp_ms"] + STALE_MS))
    kept_x = sum(1 for row in _displays(run) if row.get("kind") == "translated" and not row.get("lettered")
                 and row.get("from") not in ("sharp", None) and not judged(segment_at(row.get("t_s"))))
    found = {
        "scenarios released before their mode was on (the tool's wait for it)": sorted(
            k for k, v in released.items() if v.get("timed_out") and k != "end"
            and not (timeout_s and (v.get("waited_s") or 0) >= timeout_s - 1)) or None,
        "rested turns not finished within their rest": sum(1 for r in rested if not _finished_in_rest(r)) or None,
        "rested turns not translated at rest": sum((s.get("rested") or 0) - (s.get("translated_at_rest") or 0)
                                                   for s in segments) or None,
        "holds of --wait-done that reached their cap": sum(1 for h in holds if h.get("why") == "cap") or None,
        "spells the window did not follow the stand-in (over 1 s)": sum(s.get("not_following") or 0
                                                                        for s in segments) or None,
        "lettering of a page left on show over 1 s, until the window captured the new one": sum(
            1 for s in stale if (s.get("seen_ms") or 0) <= STALE_MS) or None,
        "jobs cancelled as the reader turned away": sum(1 for c in cancels if not c.get("page_on_show")) or None,
        "pages left half done in the cache at the end": (report.get("cleanup") or {}).get("cache_pages_incomplete")
        or None,
        "left in the cache from a frame not the sharp one, its sharp frame too late to take it back (by why)":
            dict(left_late) or None,
        "turns with lettering read from a frame not the sharp one, until the window captured the sharp one":
            until_seen or None,
        "empty results read from x's soft frames kept on show (--wait-done)": kept_x or None,
    }
    return {k: v for k, v in found.items() if v}


STREAMED_KEYS = ("units", "lines_sent_early", "lines_stood", "lines_taken_back", "units_first_line_taken_back",
                 "units_any_taken_back", "requests_taken_back", "withdrawn_on_show_ms")


def _streamed(run: dict[str, Any]) -> dict[str, Any] | None:
    """The lines sent as they were read, reported and never a failure but for what a finished page must not keep
    (`correctness`): the lines sent early, those that stood and those taken back (the first line of a unit among
    them), the requests whose answers were thrown away so, how long a taken-back lettering stayed on show. None
    without them (a tool or a program before the stream)."""
    s = run.get("streamed_lines")
    if not isinstance(s, dict) or not s.get("units"):
        return None
    return {k: s.get(k) for k in STREAMED_KEYS}


PRIORITY_KEYS = ("lowered", "not_lowered", "set_back", "low_ms", "backlog_requests", "backlog_requests_low")


def standin(report: Any, console: str, facts: dict[str, Any], group: str,
            timeout_s: float | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "standin", "group": group, **_run_facts(facts), "console": console_facts(console)}
    if not isinstance(report, dict) or not isinstance(report.get("run"), dict):
        out["verdict"] = "no report"
        out["why"] = out["console"]["stopped"] or "the tool wrote no report (stopped by the step's time limit?)"
        out["failed"] = [{"scenario": "all", "criterion": "the tool wrote its report", "ok": False, "seen": out["why"]}]
        return out
    run = report["run"]
    captures = run.get("captures") or {}
    readable = int(captures.get("sharp") or 0) + int(captures.get("soft") or 0)
    failed_run = run.get("failed") or ""
    criteria = correctness(report, timeout_s)
    failed = [c for c in criteria if not c["ok"]]
    out["verdict"] = "fail" if failed else "pass"
    out["run"] = "stopped" if failed_run else "no frames" if not readable else "works"
    if failed_run:
        out["why"] = failed_run
    requests = run.get("requests") or {}
    jobs = run.get("jobs") or {}
    server = report.get("server_started") or {}
    placements = (run.get("ocr") or {}).get("placements") or []
    waits = _waits(run)
    out.update({
        "translator": report.get("translator"), "browser": report.get("browser"), "pages": report.get("pages"),
        "scenarios": report.get("scenarios"), "left_out": report.get("x_left_out"),
        "seconds": run.get("seconds"), "ready_s": run.get("ready_s"),
        "captures": captures, "capture_route": run.get("capture_route"),
        "released": {name: {"waited_s": r.get("waited_s"), "timed_out": bool(r.get("timed_out"))}
                     for name, r in (run.get("released") or {}).items() if isinstance(r, dict)},
        "wait_done": {"cap_s": waits.get("cap_s"), "holds": len(waits.get("holds") or []),
                      "holds_by_why": waits.get("holds_by_why"), "held_ms": waits.get("held_ms"),
                      "keeps": len(waits.get("keeps") or []), "keeps_by_why": waits.get("keeps_by_why")}
        if waits else None,
        "segments": segment_rows(run), "meaning": meanings(report),
        "criteria": len(criteria), "failed": failed, "speed": speed(report, timeout_s),
        "scenario_k": k_figures(report),
        "streamed_lines": _streamed(run),
        "requests": {k: requests.get(k) for k in ("total", "outside_page_jobs", "gate_pending", "warm_ups")},
        "jobs": {k: jobs.get(k) for k in ("started", "on", "discarded")},
        "server_started": {"setup": server.get("setup"), "stopped": server.get("stopped")} if server else None,
        "server_priority": {k: (run.get("server_priority") or {}).get(k) for k in PRIORITY_KEYS}
        if isinstance(run.get("server_priority"), dict) else None,
        "ocr_devices": sorted({",".join(str(e) for e in p.get("engines") or []) for p in placements
                               if isinstance(p, dict)}),
    })
    return out


def _pair(values: Any) -> str:
    values = values or [None, None]
    return "/".join("-" if v is None else str(v) for v in values)


def _failed_lines(failed: list[dict[str, Any]]) -> list[str]:
    return [f"  * {c['scenario']}: {c['criterion']}" + (f" (seen: {c['seen']})" if c.get("seen") is not None else "")
            for c in failed]


def standin_md(s: dict[str, Any]) -> str:
    lines = [f"### Stand-in {s['group']}: {s['verdict'].upper()}", ""]
    if s.get("why"):
        lines += [f"Why: {s['why']}", ""]
    failed = s.get("failed") or []
    if s.get("criteria") is not None:
        lines.append(f"* correctness: {s['criteria'] - len(failed)} of {s['criteria']} criteria hold"
                     + (", failed:" if failed else ""))
    elif failed:
        lines.append("* failed:")
    lines += _failed_lines(failed)
    route = s.get("capture_route") or {}
    if s.get("captures") is not None:
        lines.append(f"* capture: {route.get('used')} (Windows.Graphics.Capture looks {route.get('looks')}; "
                     f"{route.get('route')}); frames by state {s['captures']}")
        lines.append(f"* the window ready after {s.get('ready_s')} s; the run {s.get('seconds')} s; translator "
                     f"{s.get('translator')}; OCR on {', '.join(s.get('ocr_devices') or []) or '-'}")
    if s.get("wait_done"):
        w = s["wait_done"]
        lines.append(f"* --wait-done {w.get('cap_s')} s: {w.get('holds')} rests held {w.get('holds_by_why')}, held ms "
                     f"{w.get('held_ms')}; {w.get('keeps')} soft frames kept {w.get('keeps_by_why')}")
    lines.append(f"* exit code {s.get('exit_code')}, the run's step {s.get('run_step_s')} s; screen {s.get('screen')}")
    console = s.get("console") or {}
    if console.get("tracebacks"):
        lines.append(f"* console: {console['tracebacks']} tracebacks, {console.get('exception_types')}")
    if s.get("segments"):
        lines += ["", "| scenario | turns | rested (median rest ms) | finished within the rest | translated at rest | "
                  "held (median/max ms) | first request ms med/max | finished ms med/max | requests (sent for "
                  "nothing) | meaning |", "|---|---|---|---|---|---|---|---|---|---|"]
        for row in s["segments"]:
            held = f"{row['holds']} ({_pair(row['held_ms'])})" if row.get("holds") else "-"
            lines.append(f"| {row['scenario']} | {row['turns']} | {row['rested']} ({row['rest_ms_median']}) | "
                         f"{row['finished_within_rest']} | {row['translated_at_rest']} | {held} | "
                         f"{_pair(row['first_request_ms'])} | {_pair(row['finished_ms'])} | {row['requests']} "
                         f"({row['wasted_requests']}) | {(s.get('meaning') or {}).get(row['scenario'], '')} |")
        lines.append("")
    if s.get("scenario_k"):
        lines += ["Scenario k (reported, never a failure):", "",
                  "| pace | flipped past (stayed 0.8 s) | caught, finished on show | read back (of them caught, "
                  "begun with no new read) | first bubble read back ms med/max | backlog emptied after the turn back "
                  "s | backlog requests | most held MB |", "|---|---|---|---|---|---|---|---|"]
        for name, k in s["scenario_k"].items():
            if not isinstance(k, dict):
                continue
            first = k.get("first_lettered_read_back") or {}
            drained = "-" if k.get("drain_s") is None else k.get("drain_s")
            lines.append(f"| {name} ({k.get('pace_ms')} ms) | {k.get('flips')} ({k.get('stayed')}) | "
                         f"{k.get('caught')}, {k.get('done_on_show')} | {k.get('read_back')} "
                         f"({k.get('read_back_caught')}, {k.get('read_back_caught_no_new_read')}) | "
                         f"{_pair([first.get('median'), first.get('max')])} | {drained} | "
                         f"{k.get('background_requests')} | {k.get('peak_mb')} |")
        lines.append("")
    if s.get("streamed_lines"):
        st = s["streamed_lines"]
        on_show = st.get("withdrawn_on_show_ms") or {}
        lines.append(f"* lines sent as they were read (reported): {st.get('lines_sent_early')} in {st.get('units')} "
                     f"units, {st.get('lines_stood')} stood, {st.get('lines_taken_back')} taken back (a unit's first "
                     f"line in {st.get('units_first_line_taken_back')}), {st.get('requests_taken_back')} requests "
                     f"thrown away; a taken-back lettering on show ms median/max "
                     f"{_pair([on_show.get('median'), on_show.get('max')])}")
    if s.get("server_priority"):
        sp = s["server_priority"]
        lines.append(f"* the backlog's work computed low (reported): {sp.get('backlog_requests_low')} of "
                     f"{sp.get('backlog_requests')} backlog requests; the server lowered {sp.get('lowered')} times "
                     f"({sp.get('not_lowered')} not), set back {sp.get('set_back')}, low {sp.get('low_ms')} ms in all")
    if "speed" in s:
        found = s["speed"]
        lines.append("* speed (reported, never a failure): "
                     + ("; ".join(f"{k}: {v}" for k, v in found.items()) if found else "nothing"))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------- the benchmark
def bench_progress(console: str) -> dict[str, Any]:
    """How far openmantra_eval's console got: the pages read (and their seconds) and the last page translated
    (`translate_series_page`'s line: of its series, the lines so far and the seconds), with the time all of the
    series' pages would take at that pace."""
    pages, seconds, last = 0, 0.0, None
    for line in console.splitlines():
        m = PAGE_LINE.match(line)
        if m:
            pages += 1
            seconds += float(m.group(3))
            continue
        m = TRANSLATED_LINE.match(line)
        if m:
            last = tuple(int(g) for g in m.groups())
    out: dict[str, Any] = {"pages_read": pages, "detection_ocr_s": round(seconds, 1)}
    if last:
        done, of, lines, spent = last
        out["translation"] = {"pages_done": done, "pages": of, "lines": lines, "seconds": spent,
                              "seconds_all_at_this_pace": round(spent * of / done) if done else None}
    return out


SCORES = ("f1", "cer", "chrf")


def scores_of(results: dict[str, Any]) -> dict[str, Any]:
    """F1 (detection), CER (the OCR on the gold crops, the corpus's) and chrF (the translation) of a results file."""
    summary = (results.get("summary") or {}).get("all") or {}
    return {"f1": summary.get("f1"), "cer": (summary.get("ocr_gold") or {}).get("corpus"),
            "chrf": (summary.get("translation") or {}).get("chrf")}


def compare(got: dict[str, Any], want: dict[str, Any] | None, tolerance: dict[str, Any], pages: Any = None,
            series: Any = None, setting: tuple[Any, Any] | None = None) -> dict[str, Any]:
    """*got* against the expected scores *want* within *tolerance* (each score's largest difference either way):
    {"compared", "ok", "scores": {name: {got, expected, tolerance, ok}}}. Not compared: a run of other pages than
    expected (a run cut short by its pages), of another series, or with another *setting* (the run's detect_model and
    the expected one's)."""
    if not want:
        return {"compared": False, "why": "no expected scores", "ok": True}
    if want.get("pages") is not None and pages is not None and int(pages) != int(want["pages"]):
        return {"compared": False, "why": f"{pages} pages, not the {want['pages']} expected", "ok": True}
    if want.get("series") is not None and series is not None and want["series"] not in list(series):
        return {"compared": False, "why": "another series than expected", "ok": True}
    if setting is not None and setting[1] is not None and setting[0] != setting[1]:
        return {"compared": False, "why": f"detect_model {setting[0]}, not the {setting[1]} expected", "ok": True}
    rows = {}
    for name in SCORES:
        value, expected, tol = got.get(name), want.get(name), tolerance.get(name)
        ok = value is not None and expected is not None and tol is not None and abs(value - expected) <= tol + 1e-9
        rows[name] = {"got": value, "expected": expected, "tolerance": tol, "ok": ok}
    return {"compared": True, "ok": all(r["ok"] for r in rows.values()), "scores": rows}


def bench(results: Any, console: str, facts: dict[str, Any], title: str,
          expected: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "benchmark", "title": title, **_run_facts(facts),
                           "progress": bench_progress(console), "console": console_facts(console)}
    if not isinstance(results, dict) or results.get("tool") != "openmantra_eval":
        out["verdict"] = "no results"
        return out
    summary = (results.get("summary") or {}).get("all") or {}
    translation = results.get("translation") or {}
    runs = translation.get("run_results") or []
    speed_ = (runs[0].get("speed") if runs else None) or {}
    scored = summary.get("translation") or {}
    state = "translation failed" if translation.get("error") else "complete" if runs else "no translation"
    out.update({
        "run": state,
        "series": (results.get("dataset") or {}).get("series"), "pages": (results.get("dataset") or {}).get("pages"),
        "seconds": results.get("seconds"),
        "detection": {k: summary.get(k) for k in ("precision", "recall", "f1", "found", "matched", "gold")},
        "ocr_cer": {"gold_corpus": (summary.get("ocr_gold") or {}).get("corpus"),
                    "gold_mean": (summary.get("ocr_gold") or {}).get("mean"),
                    "matched_corpus": (summary.get("ocr_matched") or {}).get("corpus")},
        "translation": {k: scored.get(k) for k in ("lines", "real", "chrf", "flagged_share")},
        "speed": {k: speed_.get(k) for k in ("requests", "eval_tokens", "eval_tok_per_s", "prompt_tokens",
                                             "prompt_tok_per_s", "eval_s", "prompt_s", "s_per_page")},
        "requests_failed": translation.get("requests_failed"), "pages_incomplete": translation.get("pages_incomplete"),
        "ollama_version": translation.get("ollama"), "error": translation.get("error"),
        "detect_model": (results.get("settings") or {}).get("detect_model"),
        "server_started": (translation.get("server_started") or {}).get("setup"),
    })
    if expected is not None:
        want = (expected.get("titles") or {}).get(str(title))
        out["expected"] = compare(scores_of(results), want, (expected.get("tolerance") or {}).get("title") or {},
                                  out["pages"], out["series"], (out["detect_model"], expected.get("detect_model")))
    ok = state == "complete" and (out.get("expected") or {}).get("ok", True)
    out["verdict"] = "pass" if ok else "fail"
    return out


def _scores_md(e: dict[str, Any] | None) -> str:
    if not e:
        return ""
    if not e.get("compared"):
        return f"not compared ({e.get('why')})"
    return "; ".join(f"{name} {r['got']} vs {r['expected']} (+-{r['tolerance']}) {'ok' if r['ok'] else 'OUTSIDE'}"
                     for name, r in e["scores"].items())


def bench_md(b: dict[str, Any]) -> str:
    lines = [f"### Benchmark, title {b['title']}: {b['verdict'].upper()}", ""]
    if b.get("seconds"):
        s, d, o, t, p = b["seconds"], b["detection"], b["ocr_cer"], b["translation"], b["speed"]
        lines += [f"* {', '.join(b.get('series') or [])}: {b.get('pages')} pages; {b.get('run')}; seconds {s}",
                  f"* detection F1 {d.get('f1')} (P {d.get('precision')}, R {d.get('recall')}; detect_model "
                  f"{b.get('detect_model')}); OCR CER {o.get('gold_corpus')} (corpus, gold crops; matched regions "
                  f"{o.get('matched_corpus')}); chrF {t.get('chrf')} over {t.get('lines')} lines ({t.get('real')} "
                  f"translated, flagged {t.get('flagged_share')})",
                  f"* translation: {p.get('requests')} requests, generation {p.get('eval_tok_per_s')} tok/s, prompt "
                  f"{p.get('prompt_tok_per_s')} tok/s ({p.get('s_per_page')} s a page); Ollama {b.get('ollama_version')}"
                  f"; failed requests {b.get('requests_failed')}, incomplete pages {b.get('pages_incomplete')}"]
        if b.get("expected"):
            lines.append(f"* against the expected scores: {_scores_md(b['expected'])}")
        if b.get("error"):
            lines.append(f"* translation error: {b['error']}")
    progress = b.get("progress") or {}
    lines.append(f"* console: {progress.get('pages_read')} pages read in {progress.get('detection_ocr_s')} s"
                 + (f"; page {progress['translation']['pages_done']} of {progress['translation']['pages']} "
                    f"translated after {progress['translation']['seconds']} s (all of them at that pace: "
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
    up to its first dash and a word: models, ollama-program, ollama-store, pip, ...)."""
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


def table(artifacts: Path, jobs_file: Path | None, merged: Any, caches_file: Path | None = None,
          expected: dict[str, Any] | None = None) -> str:
    summaries = [s for s in (read_json(p) for p in sorted(artifacts.rglob("summary.json"))) if isinstance(s, dict)]
    stand = sorted((s for s in summaries if s.get("kind") == "standin"), key=lambda s: str(s.get("group")))
    marks = sorted((s for s in summaries if s.get("kind") == "benchmark"), key=lambda s: str(s.get("title")))
    prepared = [f for f in (read_json(p) for p in sorted(artifacts.rglob("facts.json"))) if isinstance(f, dict)
                and isinstance(f.get("found"), dict)]  # (the job "prepare": the caches it found, and made on main)
    out = ["# GPU checks on runners", ""]
    machine = next((s.get("machine") for s in summaries if s.get("machine")), None)
    if machine:
        out.append(f"Runner: {machine.get('os')}, {machine.get('cpu')} ({machine.get('cores')} cores, "
                   f"{machine.get('logical_processors')} logical processors), {machine.get('ram_gb')} GB, display "
                   f"adapters {machine.get('gpus')}; session {machine.get('session')}, interactive "
                   f"{machine.get('interactive')}.")
    if prepared:
        p = prepared[0]
        found = p["found"]
        missing = [k for k, v in found.items() if not v]
        made = p.get("made") if isinstance(p.get("made"), dict) else {}
        out.append(f"Ollama {p.get('ollama_tag')}; main's caches found: {', '.join(k for k, v in found.items() if v) or 'none'}"
                   + (f", missing: {', '.join(missing)}" if missing else "")
                   + ("; made by this run, in GB: " + ", ".join(f"{k} {v}" for k, v in made.items()) if made
                      else "; none made by this run") + ".")
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
                "| group | verdict | criteria failed | the run | capture used | frames sharp/soft/black, spinner, unknown | "
                "window ready s | run s | rests held (by why) | speed notes |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for s in stand:
            c = s.get("captures") or {}
            frames = "/".join(str(c.get(k, 0)) for k in ("sharp", "soft", "black")) + ", " + ", ".join(
                str(c.get(k, 0)) for k in ("spinner", "unknown")) if s.get("captures") is not None else "-"
            w = s.get("wait_done") or {}
            held = f"{w.get('holds')} {w.get('holds_by_why')}" if w else "-"
            out.append(f"| {s.get('group')} | {str(s.get('verdict')).upper()} | {len(s.get('failed') or [])} | "
                       f"{s.get('run', '-')}{': ' + str(s['why']) if s.get('why') else ''} | "
                       f"{(s.get('capture_route') or {}).get('used', '-')} | {frames} | {s.get('ready_s', '-')} | "
                       f"{s.get('seconds', '-')} | {held} | {len(s.get('speed') or {})} |")
        failing = [s for s in stand if s.get("failed")]
        if failing:
            out += ["", "Failed criteria:"]
            for s in failing:
                out.append(f"* {s.get('group')}:")
                out += _failed_lines(s["failed"])
        out += ["", "| group | scenario | turns | rested | finished within the rest | translated at rest | held | "
                "finished ms med/max | meaning |", "|---|---|---|---|---|---|---|---|---|"]
        for s in stand:
            for row in s.get("segments") or []:
                out.append(f"| {s.get('group')} | {row['scenario']} | {row['turns']} | {row['rested']} | "
                           f"{row['finished_within_rest']} | {row['translated_at_rest']} | {row.get('holds') or '-'} | "
                           f"{_pair(row['finished_ms'])} | {(s.get('meaning') or {}).get(row['scenario'], '')} |")
        out.append("")
    if marks or isinstance(merged, dict):
        out += ["## Benchmark (tools/openmantra_eval.py, a title a job)", "",
                "| title | verdict | pages | det+OCR s | translation s | total s | F1 | OCR CER | chrF | gen tok/s | "
                "prompt tok/s | read so far | against the expected |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in marks:
            s = b.get("seconds") or {}
            prog = b.get("progress") or {}
            so_far = f"{prog.get('pages_read')} pages"
            if prog.get("translation"):
                t = prog["translation"]
                so_far += f", translated {t['pages_done']}/{t['pages']} (all ~{t['seconds_all_at_this_pace']} s)"
            out.append(f"| {b.get('title')} {', '.join(b.get('series') or [])} | {str(b.get('verdict')).upper()} | "
                       f"{b.get('pages', '-')} | {s.get('detection_ocr', '-')} | {s.get('translation', '-')} | "
                       f"{s.get('total', '-')} | {(b.get('detection') or {}).get('f1', '-')} | "
                       f"{(b.get('ocr_cer') or {}).get('gold_corpus', '-')} | {(b.get('translation') or {}).get('chrf', '-')} | "
                       f"{(b.get('speed') or {}).get('eval_tok_per_s', '-')} | "
                       f"{(b.get('speed') or {}).get('prompt_tok_per_s', '-')} | {so_far} | "
                       f"{_scores_md(b.get('expected')) or '-'} |")
        if isinstance(merged, dict):
            a = (merged.get("summary") or {}).get("all") or {}
            s = merged.get("seconds") or {}
            runs = (merged.get("translation") or {}).get("run_results") or []
            speed_ = (runs[0].get("speed") if runs else None) or {}
            pooled = None
            if expected is not None:
                pooled = compare(scores_of(merged), expected.get("pooled"),
                                 (expected.get("tolerance") or {}).get("pooled") or {},
                                 (merged.get("dataset") or {}).get("pages"), None,
                                 ((merged.get("settings") or {}).get("detect_model"), expected.get("detect_model")))
            out.append(f"| all, pooled ({len((merged.get('dataset') or {}).get('series') or [])} titles) | "
                       f"{'differences: ' + '; '.join(merged['differences']) if merged.get('differences') else 'joined'} | "
                       f"{(merged.get('dataset') or {}).get('pages', '-')} | {s.get('detection_ocr', '-')} | "
                       f"{s.get('translation', '-')} | longest part {s.get('longest_part', '-')} | {a.get('f1', '-')} | "
                       f"{(a.get('ocr_gold') or {}).get('corpus', '-')} | {(a.get('translation') or {}).get('chrf', '-')} | "
                       f"{speed_.get('eval_tok_per_s', '-')} | {speed_.get('prompt_tok_per_s', '-')} | | "
                       f"{_scores_md(pooled) or '-'} |")
        out.append("")
        if expected is not None:
            tol = expected.get("tolerance") or {}
            out.append(f"Expected scores: {EXPECTED.name} ({(expected.get('measured') or {}).get('note', '')}); "
                       f"tolerance per title {tol.get('title')}, pooled {tol.get('pooled')}.")
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
        p.add_argument("--check", action="store_true", help="exit 1 when the verdict is not a pass")
        if kind == "standin":
            p.add_argument("--timeout", type=float, help="the tool's --timeout (seconds)")
        else:
            p.add_argument("--expected", type=Path, default=EXPECTED, help="the expected scores (JSON)")
    p = sub.add_parser("table")
    p.add_argument("artifacts", type=Path, help="the folder the run's artifacts were downloaded into")
    p.add_argument("--jobs", type=Path, help="the run's jobs, one JSON object a line (GitHub's jobs API)")
    p.add_argument("--caches", type=Path, help="the repository's caches, one JSON object a line (GitHub's API)")
    p.add_argument("--merged", type=Path, help="tools/openmantra_merge.py's joined file")
    p.add_argument("--expected", type=Path, default=EXPECTED, help="the expected scores (JSON)")
    p.add_argument("--out", type=Path, help="also write the tables to this file")
    args = ap.parse_args(argv)
    if args.kind == "table":
        text = table(args.artifacts, args.jobs, read_json(args.merged), args.caches, read_json(args.expected))
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return 0
    facts = read_json(args.facts) or {}
    console = read_text(args.console)
    if args.kind == "standin":
        summary = standin(read_json(args.report), console, facts, args.group, args.timeout)
        text = standin_md(summary)
    else:
        summary = bench(read_json(args.report), console, facts, args.title, read_json(args.expected))
        text = bench_md(summary)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (args.out / "summary.md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 1 if args.check and summary.get("verdict") != "pass" else 0


if __name__ == "__main__":
    sys.exit(main())
