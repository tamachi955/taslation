"""tools/test_shards.py: every test goes to exactly one of the parallel jobs, and the jobs come out alike."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("test_shards_tool", ROOT / "tools" / "test_shards.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def _paths(tmp_path, sizes):
    paths = []
    for i, size in enumerate(sizes):
        p = tmp_path / f"test_{i}.py"
        p.write_bytes(b"#" * size * 6)
        paths.append(p)
    return paths


def test_every_test_file_is_in_a_job_and_a_divided_file_is_whole_over_its_jobs():
    for n in (1, 3, 8):
        jobs = tool.deal(n)
        assert len(jobs) == n
        whole = sorted(p.path for job in jobs for p in job if p.parts == 1)
        divided: dict[Path, list[int]] = {}
        for job in jobs:
            assert len({p.path for p in job}) == len(job)  # no job holds two parts of one file
            for p in job:
                if p.parts > 1:
                    divided.setdefault(p.path, []).append(p.part)
        assert all(sorted(parts) == list(range(len(parts))) for parts in divided.values())
        assert sorted(whole + list(divided)) == tool.files()


def test_the_jobs_weights_come_out_alike(tmp_path):
    paths = _paths(tmp_path, [9000, 7000, 5000, 4000, 3000, 2000, 1000, 1000])
    seconds = {"test_7.py": 9.0}  # a measured time wins over the size
    jobs = tool.deal(2, paths, seconds)
    loads = [sum(p.seconds for p in job) for job in jobs]
    assert abs(loads[0] - loads[1]) <= 0.15 * max(loads)
    assert tool.weight(paths[7], seconds) == 9.0 and tool.weight(paths[0], seconds) == 9.0


def test_a_file_heavier_than_a_jobs_share_is_divided_and_each_of_its_tests_runs_once(tmp_path):
    paths = _paths(tmp_path, [1000, 1000, 1000, 1000])
    seconds = {"test_0.py": 300.0, "test_1.py": 60.0, "test_2.py": 60.0, "test_3.py": 60.0}
    jobs = tool.deal(4, paths, seconds)  # a fair share is 120 s: the first file goes in three parts
    specs = [tool.split_spec(job) for job in jobs]
    assert sorted(s for s in specs if s) == ["test_0.py:0/3", "test_0.py:1/3", "test_0.py:2/3"]
    assert max(sum(p.seconds for p in job) for job in jobs) <= 160
    for index in range(10):
        assert sum(tool.kept(s, "test_0.py", index) for s in specs if s) == 1
    assert tool.kept("test_0.py:1/3", "test_1.py", 5) and tool.kept("", "test_0.py", 5)  # other files run whole
    assert tool.kept("a.py:0/2,b.py:1/2", "b.py", 3) and not tool.kept("a.py:0/2,b.py:1/2", "b.py", 2)


def test_seconds_are_learnt_from_the_durations_report():
    lines = ["12.50s call     tests/test_a.py::test_one", "0.50s setup    tests/test_a.py::test_one",
             "3.00s call     tests\\test_b.py::test_two[x]", "(2 durations < 0.005s hidden)", "1 passed in 3 s"]
    assert tool.learn(lines) == {"test_a.py": 13.0, "test_b.py": 3.0}
