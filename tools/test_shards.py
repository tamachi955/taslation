"""Which test files one of several parallel jobs runs (a dev tool for .github/workflows/tests.yml; never shipped).

    python tools/test_shards.py --of 8 --shard 0          # the files of job 0 of 8, one a line
    python tools/test_shards.py --of 8 --shard 0 --split  # which part of a divided file job 0 runs ("" when none)
    python tools/test_shards.py --of 8 --table            # every job's weight and file count

The files of ``tests/test_*.py`` are dealt to the jobs so that the jobs' weights come out alike: the heaviest first,
each to the job that is lightest so far. A file's weight is the seconds it took in a measured run
(``tests/shard_seconds.json``, written by ``--learn`` from pytest's ``--durations=0`` output) and, for a file that run
did not hold, a guess from its size. A file heavier than a job's fair share is divided into parts that go to different
jobs: a job runs part I of N of FILE when ``TASLATION_TEST_SPLIT`` holds ``FILE:I/N`` (several, joined by commas),
which ``tests/conftest.py`` reads: the file's tests are counted in the order pytest collects them and the job keeps
those whose number leaves I when divided by N. Every test so runs in exactly one job, whatever the weights say.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SECONDS = TESTS / "shard_seconds.json"
SPLIT_ENV = "TASLATION_TEST_SPLIT"
BYTES_A_SECOND = 6000  # the guess for a file without a measured time: about what the measured files average
DURATION = re.compile(r"^\s*([0-9.]+)s\s+(?:call|setup|teardown)\s+(?:tests[\\/])?(test_[^:\\/]+\.py)::")


class Piece(NamedTuple):
    """A file, or part *part* of *parts* of it, and its weight in seconds."""

    path: Path
    part: int
    parts: int
    seconds: float


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


def pieces(n: int, paths: list[Path], seconds: dict[str, float]) -> list[Piece]:
    """The files as pieces: one a file, but a file heavier than a job's fair share in as many parts as it has shares
    (at most *n*: no job gets two parts of one file)."""
    fair = sum(weight(p, seconds) for p in paths) / n if paths else 0.0
    out: list[Piece] = []
    for path in paths:
        w = weight(path, seconds)
        parts = min(n, max(1, math.ceil(w / fair))) if fair > 0 and n > 1 else 1
        out += [Piece(path, i, parts, w / parts) for i in range(parts)]
    return out


def deal(n: int, paths: list[Path] | None = None, seconds: dict[str, float] | None = None) -> list[list[Piece]]:
    """The pieces of each of *n* jobs: heaviest first, each to the lightest job so far that holds no other part of
    its file (ties: the lower job)."""
    paths = files() if paths is None else paths
    seconds = measured() if seconds is None else seconds
    jobs: list[list[Piece]] = [[] for _ in range(n)]
    loads = [0.0] * n
    for piece in sorted(pieces(n, paths, seconds), key=lambda p: (-p.seconds, p.path.name, p.part)):
        free = [k for k in range(n) if all(q.path != piece.path for q in jobs[k])]
        i = min(free, key=lambda k: (loads[k], k))
        jobs[i].append(piece)
        loads[i] += piece.seconds
    return [sorted(job, key=lambda p: p.path.name) for job in jobs]


def split_spec(job: list[Piece]) -> str:
    """What ``TASLATION_TEST_SPLIT`` holds for *job*: ``FILE:I/N`` for each divided file, joined by commas."""
    return ",".join(f"{p.path.name}:{p.part}/{p.parts}" for p in job if p.parts > 1)


def kept(spec: str, name: str, index: int) -> bool:
    """Whether the test numbered *index* (from 0, in collection order) of the file *name* runs under *spec*."""
    for item in filter(None, (s.strip() for s in spec.split(","))):
        file, _, share = item.partition(":")
        part, _, parts = share.partition("/")
        if file == name:
            return index % int(parts) == int(part)
    return True


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
    ap.add_argument("--split", action="store_true", help=f"with --shard: print the job's {SPLIT_ENV} instead")
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
        for i, job in enumerate(jobs):
            print(f"{i}: {sum(p.seconds for p in job):7.0f} s  {len(job)} files  {split_spec(job)}")
        return 0
    if args.shard is None or not 0 <= args.shard < args.of:
        ap.error("--shard must be 0 .. --of minus 1")
    if args.split:
        print(split_spec(jobs[args.shard]))
        return 0
    for piece in jobs[args.shard]:
        print(piece.path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
