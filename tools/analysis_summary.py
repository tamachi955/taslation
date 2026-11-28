"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: print the tables of a session's analysis log (`taslation.analysis`).

    python tools/analysis_summary.py                       # the state folder's analysis.jsonl
    python tools/analysis_summary.py PATH/analysis.jsonl   # a file of the log
    python tools/analysis_summary.py SESSION_FOLDER        # a developer measuring session (`taslation.devmeasure`)
    python tools/analysis_summary.py --last 200 ...        # only the newest 200 lines

Printed: the defects by level first (S1 and S2 case by case with the page's number in the session and their numbers,
S3 and S4 counted with their rates), the stages' and helpers' times (total, share, median and 95th percentile per
page), the slowest pages with their coarse facts, the regions each helper changed, the counts, the fits, the window's
lines (patches withheld, panes hidden), the edits and what the log cost (`analysis.summary_lines`).

A developer measuring session's folder adds the turns of the page the person asked for (its ``input.jsonl``: the kind
of each key and the wheel's ticks over the viewer): for each, the page read next - the first page on show (not one
lettered ahead, nor one cancelled for a newer frame) that began after it and before the next turn - and the times
from the turn to its first lettering and to its end: median, 90th percentile and the 10 slowest with their page's
facts. Only ``analysis.jsonl`` and ``input.jsonl`` are read, numbers alone: never a picture, a page's JSON, the
requests or the log's copy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from taslation import analysis  # noqa: E402
from taslation.devmeasure import FOLDER, TURN_KEYS  # noqa: E402

SLOWEST = 10


def read_input(path: Path) -> list[dict[str, Any]]:
    """The input record's lines (a line that is no JSON object left out)."""
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for text in f:
                try:
                    line = json.loads(text)
                except ValueError:
                    continue
                if isinstance(line, dict):
                    out.append(line)
    except OSError:
        pass
    return out


def turns(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The inputs that ask for another page: a turn key, a wheel tick over the viewer."""
    return [i for i in inputs if (i.get("type") == "key" and i.get("key") in TURN_KEYS) or i.get("type") == "wheel"]


def turn_pages(inputs: list[dict[str, Any]], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each turn with the page read next (see the module's notes): {"t", "kind", "page", "first_ms", "done_ms"}; a
    turn followed by another before any page began has no page (a quick flip)."""
    asked = sorted(turns(inputs), key=lambda i: int(i.get("t") or 0))
    pages = sorted((p for p in lines if p.get("type") == "page" and not p.get("ahead")
                    and (p.get("outcome") or "done") == "done"), key=lambda p: int(p.get("t") or 0))
    out: list[dict[str, Any]] = []
    for k, turn in enumerate(asked):
        t = int(turn.get("t") or 0)
        until = int(asked[k + 1].get("t") or 0) if k + 1 < len(asked) else None
        page = next((p for p in pages if int(p.get("t") or 0) >= t and (until is None or int(p.get("t") or 0) < until)),
                    None)
        kind = turn.get("key") if turn.get("type") == "key" else "wheel"
        entry: dict[str, Any] = {"t": t, "kind": kind, "page": page, "first_ms": None, "done_ms": None}
        if page is not None:
            start = int(page.get("t") or 0)
            if page.get("first_letter_ms") is not None:
                entry["first_ms"] = start + float(page["first_letter_ms"]) - t
            entry["done_ms"] = int(page.get("end") or start) - t
        out.append(entry)
    return out


def latency_lines(entries: list[dict[str, Any]], slowest: int = SLOWEST) -> list[str]:
    """The turns' table (see the module's notes)."""
    out = [f"turns asked for: {len(entries)} (with a page read next: {sum(1 for e in entries if e['page'])})"]
    kinds: dict[str, int] = {}
    for e in entries:
        kinds[str(e["kind"])] = kinds.get(str(e["kind"]), 0) + 1
    out.append("  by kind: " + (", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) or "none"))
    for name, key in (("asked -> first lettering", "first_ms"), ("asked -> done", "done_ms")):
        values = [float(e[key]) for e in entries if e[key] is not None]
        if values:
            out.append(f"  {name}: median {analysis._median(values):.0f} ms, "
                       f"p90 {analysis._quantile(values, 0.9):.0f} ms, "
                       f"most {max(values):.0f} ms ({len(values)} turns)")
        else:
            out.append(f"  {name}: none")
    timed = sorted((e for e in entries if e["done_ms"] is not None), key=lambda e: -float(e["done_ms"]))[:slowest]
    if timed:
        out.append(f"  slowest turns: {'kind':>9} {'first ms':>8} {'done ms':>8} {'page':>5} {'units':>5} {'cache':>5} "
                   f"{'colour':>6} {'ink':>5} {'dark':>5} {'regions':>7}  top stage")
        for e in timed:
            p = e["page"]
            f = p.get("facts") or {}
            stages = p.get("stages") or {}
            top = max(stages.items(), key=lambda kv: kv[1])[0] if stages else "-"
            first = f"{e['first_ms']:.0f}" if e["first_ms"] is not None else "-"
            out.append(f"  {'':14} {str(e['kind']):>9} {first:>8} {float(e['done_ms']):8.0f} {p.get('n', 0):5d} "
                       f"{p.get('units', 0):5d} {'yes' if p.get('cached') else 'no':>5} {f.get('colour', 0):6.2f} "
                       f"{f.get('ink', 0):5.2f} {f.get('dark', 0):5.2f} "
                       f"{(p.get('regions') or {}).get('n', 0):7d}  {top}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", help="an analysis.jsonl, a developer measuring session's folder or a state "
                                                "folder (default: the state folder's log)")
    parser.add_argument("--last", type=int, default=0, help="only the newest N lines")
    parser.add_argument("--slowest", type=int, default=SLOWEST)
    args = parser.parse_args(argv)
    if args.path:
        path = Path(args.path)
    else:
        from taslation.config import default_state_dir

        path = default_state_dir()
    folder = path if path.is_dir() else None
    log_file = folder / analysis.FILE_NAME if folder is not None else path
    lines = analysis.read_lines(log_file)
    if not lines:
        print(f"no lines in {log_file}")
        return 1
    if args.last:
        lines = lines[-args.last:]
    print("\n".join(analysis.summary_lines(lines, slowest=args.slowest)))
    inputs = read_input(folder / "input.jsonl") if folder is not None else []
    if inputs:
        print()
        print("\n".join(latency_lines(turn_pages(inputs, lines), args.slowest)))
    elif folder is not None and folder.parent.name == FOLDER:
        print()
        print("turns asked for: none recorded (no key or wheel of the person's while the viewer or TASlation "
              "was in front; a tool's run posts its turns to the viewer, which the hooks do not see)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
