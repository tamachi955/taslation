"""A turn made within moments of the window becoming ready (the models loaded, `_run_queued`): the frame the live view
follows until it settles - seen while the models loaded, so not started early - is started early once they are ready
(`_settle_now`: a gate of its own, `pipeline.PageGate`), never taken at once as settled because the look matched the
follow's capture of tens of ms before. Before, a soft frame of a viewer that draws a page soft first was then read
with no gate: what its job did would have lasted had the sharp frame come after its first lines."""
from __future__ import annotations

import pytest
from test_early_start import KEEP_S, Worker, _after, _environment
from test_follow import _page


def _loading(env):
    """The window and its worker, the models loading (a start that takes long) and a page seen meanwhile waiting for
    them (`_queue`: "auto", looked at again once they are ready)."""
    w, worker = env.make(worker=Worker)
    w.pipeline.ocr = object()  # (the OCR model is there: the ready loads nothing more)
    w.ready = False
    env.show((0.0, "2", _page(2)), run=2.0)
    assert w._queued is not None and [j.name for j in worker.jobs] == ["1"]
    return w, worker


def _turn_at_ready(env, ready_s: float, sharp_s: float = 0.4):
    """Page 3 turned (soft first, sharp *sharp_s* later) while the models load; ready *ready_s* after the turn."""
    w, worker = _loading(env)
    clock = env.clock
    turned = clock.now + 0.3  # (`show`: the frames from 0.3 s on)

    def ready():
        w._handle_event("ready", {})

    clock.after(round((0.3 + ready_s) * 1000), ready)
    env.show((0.0, "3 soft", _page(3, soft=3)), (sharp_s, "3", _page(3)), run=6.0)
    return w, worker, turned


@pytest.mark.parametrize("ready_ms", list(range(0, 400, 20)))
def test_a_soft_frame_seen_as_the_window_becomes_ready_is_started_with_a_gate(hidden_root, monkeypatch, tmp_path,
                                                                              ready_ms):
    env = _environment(hidden_root, monkeypatch, tmp_path / "profiles.json")
    w, worker, turned = _turn_at_ready(env, ready_ms / 1000)
    soft = worker.of("3 soft")
    assert all(j.gate is not None for j in soft), [(j.start - turned, j.gate) for j in soft]  # never without a gate
    assert all(j.stored is None and j.gate.confirmed_at is None for j in soft)  # ... and nothing of it kept
    assert worker.kept[-1] == "3" and "3 soft" not in worker.kept
    sharp = worker.one("3")
    assert sharp.gate is not None and sharp.how == "done"  # the sharp frame started early too, and kept
    assert all(j.ended is not None for j in worker.jobs)  # (none left waiting)


@pytest.mark.parametrize("ready_ms", [100, 250])
def test_without_frame_counts_too(hidden_root, monkeypatch, tmp_path, ready_ms):
    env = _environment(hidden_root, monkeypatch, tmp_path / "profiles.json", counted=False)
    w, worker, turned = _turn_at_ready(env, ready_ms / 1000)
    assert all(j.gate is not None for j in worker.of("3 soft"))
    assert worker.kept[-1] == "3" and "3 soft" not in worker.kept


def test_a_sharp_frame_seen_as_the_window_becomes_ready_starts_at_once_and_is_kept_after_the_fixed_time(
        hidden_root, monkeypatch, tmp_path):
    """No soft frame: the page seen while the models loaded starts as soon as they are ready, with a gate, kept once
    its frame has stayed KEEP_SETTLES times settle_ms from the look that saw it first (not from the ready)."""
    env = _environment(hidden_root, monkeypatch, tmp_path / "profiles.json")
    w, worker = _loading(env)
    clock = env.clock
    turned = clock.now + 0.3
    clock.after(round((0.3 + 0.2) * 1000), lambda: w._handle_event("ready", {}))
    env.show((0.0, "3", _page(3)), run=4.0)
    job = worker.one("3")
    assert job.gate is not None and job.start - (turned + 0.2) <= 0.016  # at the ready, at once
    assert _after(job.gate.confirmed_at - turned, KEEP_S)  # kept as a page started on its first frame is
    assert worker.kept == ["1", "3"] and not worker.of("2")  # (page 2, turned from, never read)
