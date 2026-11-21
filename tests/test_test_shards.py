"""tools/test_shards.py: every test file goes to exactly one of the parallel jobs, and the jobs come out alike."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("test_shards_tool", ROOT / "tools" / "test_shards.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_every_test_file_is_in_exactly_one_job():
    for n in (1, 3, 8):
        jobs = tool.deal(n)
        dealt = [p for job in jobs for p in job]
        assert len(jobs) == n and sorted(dealt) == tool.files() and len(set(dealt)) == len(dealt)


def test_the_jobs_weights_come_out_alike(tmp_path):
    paths = []
    for i, size in enumerate([9000, 7000, 5000, 4000, 3000, 2000, 1000, 1000]):
        p = tmp_path / f"test_{i}.py"
        p.write_bytes(b"#" * size * 6)
        paths.append(p)
    seconds = {"test_7.py": 9.0}  # a measured time wins over the size
    jobs = tool.deal(2, paths, seconds)
    loads = [sum(tool.weight(p, seconds) for p in job) for job in jobs]
    assert abs(loads[0] - loads[1]) <= 0.15 * max(loads)
    assert tool.weight(paths[7], seconds) == 9.0 and tool.weight(paths[0], seconds) == 9.0


def test_seconds_are_learnt_from_the_durations_report():
    lines = ["12.50s call     tests/test_a.py::test_one", "0.50s setup    tests/test_a.py::test_one",
             "3.00s call     tests\\test_b.py::test_two[x]", "(2 durations < 0.005s hidden)", "1 passed in 3 s"]
    assert tool.learn(lines) == {"test_a.py": 13.0, "test_b.py": 3.0}
