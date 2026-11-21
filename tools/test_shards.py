"""Which test files one of several parallel jobs runs (a dev tool for .github/workflows/tests.yml; never shipped).

    python tools/test_shards.py --of 8 --shard 0          # the files of job 0 of 8, one a line
    python tools/test_shards.py --of 8 --table            # every job's weight and file count

The files of ``tests/test_*.py`` are dealt to the jobs so that the jobs' weights come out alike: the heaviest file
first, each to the job that is lightest so far. A file's weight is the seconds it took in a measured run
(``tests/shard_seconds.json``, written by ``--learn`` from pytest's ``--durations=0`` output) and, for a file that run
did not hold, a guess from its size. Every file goes to exactly one job, whatever the weights say.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SECONDS = TESTS / "shard_seconds.json"
BYTES_A_SECOND = 6000  # the guess for a file without a measured time: about what the measured files average
DURATION = re.compile(r"^\s*([0-9.]+)s\s+(?:call|setup|teardown)\s+(?:tests[\\/])?(test_[^:\\/]+\.py)::")


def files() -> list[Path]:
    return sorted(TESTS.glob("test_*.py"))


def measured() -> dict[str, float]:
    try:
        data = json.loads(SECONDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(name): float(s) for name, s in data.items()}


def weight(path: Path, seconds: dict[str, float]) -> float:
    known = seconds.get(path.name)
    return known if known is not None else max(1.0, path.stat().st_size / BYTES_A_SECOND)


def deal(n: int, paths: list[Path] | None = None, seconds: dict[str, float] | None = None) -> list[list[Path]]:
    """The files of each of *n* jobs: heaviest first, each to the lightest job so far (ties: the lower job)."""
    paths = files() if paths is None else paths
    seconds = measured() if seconds is None else seconds
    jobs: list[list[Path]] = [[] for _ in range(n)]
    loads = [0.0] * n
    for path in sorted(paths, key=lambda p: (-weight(p, seconds), p.name)):
        i = min(range(n), key=lambda k: (loads[k], k))
        jobs[i].append(path)
        loads[i] += weight(path, seconds)
    return [sorted(job) for job in jobs]


def learn(lines: list[str]) -> dict[str, float]:
    """Seconds a file from the lines of pytest's ``--durations=0`` report (several reports may be joined)."""
    total: dict[str, float] = {}
    for line in lines:
        m = DURATION.match(line)
        if m:
            total[m.group(2)] = total.get(m.group(2), 0.0) + float(m.group(1))
    return {name: round(s, 1) for name, s in sorted(total.items())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--of", type=int, default=8, help="how many jobs")
    ap.add_argument("--shard", type=int, help="print this job's files (0-based)")
    ap.add_argument("--table", action="store_true", help="print every job's weight and file count")
    ap.add_argument("--learn", nargs="+", type=Path, metavar="LOG",
                    help="write tests/shard_seconds.json from pytest --durations=0 outputs")
    args = ap.parse_args(argv)
    if args.learn:
        lines: list[str] = []
        for log in args.learn:
            lines += log.read_text(encoding="utf-8", errors="replace").splitlines()
        seconds = learn(lines)
        SECONDS.write_text(json.dumps(seconds, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(seconds)} files, {sum(seconds.values()):.0f} s -> {SECONDS}")
        return 0
    if args.of < 1:
        ap.error("--of must be 1 or more")
    jobs = deal(args.of)
    if args.table:
        seconds = measured()
        for i, job in enumerate(jobs):
            print(f"{i}: {sum(weight(p, seconds) for p in job):7.0f} s  {len(job)} files")
        return 0
    if args.shard is None or not 0 <= args.shard < args.of:
        ap.error("--shard must be 0 .. --of minus 1")
    for path in jobs[args.shard]:
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
