"""The m and resize scenarios' tool (tools/standin_monitors.py) with no browser and no window of its own: the
scenarios asked by name, a drag's sizes and its button, the steps' places over made-up monitors, and the tables
made from made-up looks - lettering at a stale place or scale, the panes, the jobs started while the button was held
and on the sizes between, a region's place at two sizes."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import standin_e2e  # noqa: E402
import standin_monitors as sm  # noqa: E402


def screens(*monitors):
    """A `Screens` over made-up monitors ((rect, work, primary, dpi) each), the primary first."""
    s = object.__new__(sm.Screens)
    s.monitors = [{"handle": i + 1, "rect": rect, "work": work, "primary": primary, "dpi": dpi}
                  for i, (rect, work, primary, dpi) in enumerate(monitors)]
    return s


TWO = ((0, 0, 1920, 1080), (0, 0, 1920, 1040), True, 96), ((1920, 0, 3840, 1080), (1920, 0, 3840, 1040), False, 96)


# ---------------------------------------------------------------------------------------------------- the scenarios
def test_the_window_steps_are_asked_by_name_only():
    assert standin_e2e.wanted("m") == list(standin_e2e.M_STEPS) == ["m0", "m1", "m2", "m3", "m4"]
    assert standin_e2e.wanted("resize") == list(standin_e2e.R_STEPS)
    assert standin_e2e.wanted("a,m1,r3") == ["a", "m1", "r3"]
    everything = standin_e2e.wanted("all")
    assert not set(everything) & set(standin_e2e.WINDOW_STEPS)
    assert set(standin_e2e.WINDOW_STEPS) <= set(standin_e2e.SCENARIOS)
    with pytest.raises(SystemExit, match="unknown scenario"):
        standin_e2e.wanted("a,r")  # ("r" was the former own window's: still unknown)


def test_the_start_on_another_monitor_and_maximised_are_options():
    args = standin_e2e.parse(["--canned", "--scenario", "m", "--standin-monitor", "2", "--standin-maximised"])
    assert args.standin_monitor == 2 and args.standin_maximised
    assert standin_e2e.parse(["--canned"]).standin_monitor == 1


# ---------------------------------------------------------------------------------------------------- the steps
def test_a_drag_holds_the_pointer_on_its_edge():
    rect = (100, 50, 800, 600)
    assert sm.edge_point(rect, "right") == (897, 350)
    assert sm.edge_point(rect, "bottom") == (500, 647)
    assert sm.edge_point(rect, "corner") == (897, 647)


class FakeSteps:
    def __init__(self):
        self.placed = []

    def front(self):
        return "other"

    def place(self, rect):
        self.placed.append((rect, watch.fake_button, watch.fake_point))


watch = SimpleNamespace(fake_button=False, fake_point=None)


@pytest.mark.parametrize("button", [True, False])
def test_a_drag_gives_its_sizes_with_the_button_held_and_lets_it_go(button, monkeypatch):
    monkeypatch.setattr(sm, "PRESS_LEAD_S", 0.01)
    monkeypatch.setattr(sm, "RELEASE_AFTER_S", 0.01)
    steps = FakeSteps()
    drag = sm.Drag(steps, (0, 0, 1000, 800), (0, 0, 700, 800), "right", watch, button, seconds=0.05, count=10)
    drag.start()
    drag.join(5)
    f = drag.facts
    assert f["sizes"] == 10 and len(steps.placed) == 10
    widths = [rect[2] for rect, _b, _p in steps.placed]
    assert widths == sorted(widths, reverse=True) and widths[-1] == 700 and widths[0] < 1000
    assert all(b is button for _r, b, _p in steps.placed)
    if button:
        assert all(p == sm.edge_point(rect, "right") for rect, _b, p in steps.placed)
        assert f["press_t"] <= f["first_t"] <= f["last_t"] <= f["release_t"]
    else:
        assert f["press_t"] is None and f["release_t"] is None
    assert watch.fake_button is False and watch.fake_point is None  # (let go, the pointer the tool's no more)


def test_the_places_over_two_monitors(monkeypatch):
    s = screens(*TWO)
    here = {"n": 2}
    monkeypatch.setattr(s, "of_window", lambda hwnd: here["n"])
    run = sm.WindowRun(None, 1, s, None, None, None, (1920, 0, 1300, 900), None)
    assert run._other() == 1 and run._second() == 2
    assert run._on(1, (0, 0, 1300, 900), 40, 30) == (40, 30, 1300, 900)
    assert run._on(2, (0, 0, 2500, 1200)) == (1920, 0, 1920, 1040)  # (no larger than the work area)
    x, y, w, h = run._straddle((0, 0, 1300, 900))
    assert x + w // 2 == 1920 and (w, h) == (1300, 900) and y == 30
    assert s.met((1270, 30, 2570, 930)) == [1, 2] and s.met((1800, 0, 3700, 900)) == [2, 1]
    assert s.met((-5000, -5000, -4000, -4000)) == []


def test_the_maximise_is_refused_on_the_primary(monkeypatch):
    s = screens(*TWO)
    monkeypatch.setattr(s, "of_window", lambda hwnd: 1)
    locks = []
    steps = sm.WindowSteps(1, s, lambda: set(), lambda on: locks.append(on) or True)
    assert "refused" in steps.maximise() and locks == []


class FakeTour:
    def __init__(self):
        self.started, self.steps, self.left = [], 0, 0

    def busy(self):
        return self.left > 0

    def start(self, label, items=()):
        self.started.append(label)
        self.left = 2

    def step(self):
        self.steps += 1
        self.left = max(0, self.left - 1)


def test_a_step_is_ready_once_done_at_rest_and_toured(monkeypatch):
    s = screens(*TWO)
    monkeypatch.setattr(s, "of_window", lambda hwnd: 2)
    tour = FakeTour()
    app = SimpleNamespace(_see_pane_memo={"left": (None, None, (0, 0, 120, 400))})  # (the left pane has room)
    run = sm.WindowRun(app, 1, s, None, None, tour, (1920, 0, 1300, 900), None)
    clock = {"now": 100.0}
    monkeypatch.setattr(sm, "time", SimpleNamespace(monotonic=lambda: clock["now"]))  # (the module's alone)
    run.drag = SimpleNamespace(is_alive=lambda: True)
    assert not run.ready("r1", True)  # (the drag goes on)
    run.drag = SimpleNamespace(is_alive=lambda: False)
    assert not run.ready("r1", True) and run.done_at == 100.0  # (just done)
    clock["now"] += sm.STEP_REST_S
    assert not run.ready("r1", False)  # (the window not at rest)
    assert run.ready("r1", True)
    run.drag, run.done_at = None, 100.0
    results = [run.ready("m1", True) for _ in range(5)]
    assert tour.started == ["m1"] and results[-1] is True and results.index(True) == 2
    assert run.ready("m1", True)  # (toured once)
    assert tour.started == ["m1"]
    app._see_pane_memo = {"left": (None, None, None)}  # (no room for the left pane: the taskbar button's Menu, once)
    run.done_at = 100.0
    results = [run.ready("r4", True) for _ in range(4)]
    assert tour.started == ["m1", "r4"] and results == [False, False, True, True]
    run.done_at = 100.0
    assert run.ready("r5", True) and tour.started == ["m1", "r4"]


# ---------------------------------------------------------------------------------------------------- the tables
def row(t, client=(1928, 0, 3212, 892), overlay="same", set_size=None, final=True, left=(5, 5, 90, 300),
        right=(1190, 5, 1280, 300), why="", marks=None):
    w, h = client[2] - client[0], client[3] - client[1]
    over = client if overlay == "same" else overlay
    out = {"t": t, "outer": (client[0] - 8, client[1], client[2] + 8, client[3] + 8), "client": client,
           "zoomed": False, "monitor": 2, "met": [2], "see_dpi": 96, "dialog_dpi": 96, "over_dpi": 96,
           "root": {"monitor_nearest": 1, "on_a_monitor": False}, "overlay": over}
    if over is not None:
        out["shown"] = {"origin": client[:2], "size": (w, h), "n": 3, "set_size": set_size or (w, h),
                        "final": final}

    def pane(box):
        if box is None:
            return {"box": None, "visible": False, "monitors": [], "why": why}
        b = (client[0] + box[0], client[1] + box[1], client[0] + box[2], client[1] + box[3])
        return {"box": b, "visible": True, "monitors": [2], "why": ""}

    out["panes"] = {"left": pane(left), "right": pane(right)}
    if marks is not None:
        out["marks"] = {"boxes": 3, "set_size": marks}
    return out


def test_lettering_at_another_place_or_scale_is_stale():
    assert sm._stale(row(0)) == (False, False)
    assert sm._stale(row(0, overlay=None)) == (False, False)
    assert sm._stale(row(0, overlay=(1930, 0, 3214, 892))) == (True, False)
    assert sm._stale(row(0, overlay=(1928, 0, 3000, 892))) == (False, True)
    assert sm._stale(row(0, set_size=(1000, 800))) == (False, True)  # (a set of another frame size on show)


def test_a_place_s_block():
    s = screens(*TWO)
    rows = [row(t) for t in range(0, 500, 50)] + [row(500, left=None, why="off the screen"),
                                                  row(550, overlay=(1930, 2, 3214, 894))]
    block = sm.place_block(rows, s)
    assert block["looks"] == 12 and block["monitor"] == 2 and block["monitor_dpi"] == 96
    assert block["lettering_offset_px"] == {"0,0": 11, "2,2": 1}
    assert block["stale_place_looks"] == 1 and block["stale_scale_looks"] == 0
    left, right = block["panes"]["left"], block["panes"]["right"]
    assert left["shown_looks"] == 11 and left["hidden_looks"] == 1 and left["inside_viewer"] == 11
    assert left["why_hidden"] == {"off the screen": 1} and left["monitors"] == {"2": 11}
    assert right["shown_looks"] == 12 and right["why_hidden"] == {}
    assert sm.place_block([], s) == {"looks": 0}


def test_a_drag_s_block():
    """A drag from 1000 to 2600 ms (the button let go then): the lettering hidden at once and back at the new size
    400 ms after the release, finished 900 ms after; the panes back 500 ms after; one job started while the button
    was held on a size between, the first after the release from the cache."""
    old, new = (1928, 0, 3212, 892), (1928, 0, 2852, 892)
    rows = [row(t, client=old) for t in range(800, 1000, 50)]
    rows += [row(t, client=(1928, 0, 3212 - (t - 1000) // 5, 892), overlay=None, left=None, right=None, why="no room")
             for t in range(1000, 2650, 50)]
    rows += [row(t, client=new, overlay=None, left=None, right=None) for t in range(2650, 3000, 50)]
    rows += [row(t, client=new, final=False, left=None, right=None) for t in range(3000, 3100, 50)]
    rows += [row(t, client=new, final=t >= 3500) for t in range(3100, 5000, 50)]
    lock = threading.Lock()
    notes = SimpleNamespace(lock=lock, jobs=[
        {"id": 1, "t": 1500, "started": True, "size": [1184, 892], "requests": 3, "result_from": "sharp"},
        {"id": 2, "t": 2800, "started": True, "size": [924, 892], "requests": 0, "result_from": "sharp"},
        {"id": 3, "t": 2900, "started": False, "size": [924, 892], "requests": 0, "result_from": None}],
        margins=[{"t": 1200, "size": [1184, 892], "own": [0, 85, 0, 0], "read": [0, 85, 0, 0]},
                 {"t": 2700, "size": [924, 892], "own": [0, 90, 0, 0], "read": [0, 85, 0, 0]},
                 {"t": 2950, "size": [924, 892], "own": [0, 90, 0, 0], "read": [0, 90, 0, 0]}],
        lookups=[{"t": 2810, "job": 2, "hit": 0}, {"t": 2820, "job": 2, "hit": None}, {"t": 1600, "job": 1,
                                                                                       "hit": None}])
    facts = {"edge": "right", "button": True, "sizes": 33, "press_t": 900, "first_t": 1000, "last_t": 2500,
             "release_t": 2600, "front_before": "other", "front_after": "other"}
    block = sm.drag_block(rows, facts, notes, 5000)
    assert block["end_size"] == [924, 892] and block["drag_ms"] == 1500
    assert block["stale_place_looks"] == 0 and block["stale_scale_looks"] == 0
    assert block["lettering_hidden_ms_after_first_size"] == 0
    assert block["lettering_back_at_new_size_ms_after_release"] == 400
    assert block["page_done_at_new_size_ms_after_release"] == 900
    assert block["panes"]["left"]["back_ms_after_release"] == 500 and block["panes"]["left"]["at_end"] == "shown"
    assert block["panes"]["left"]["outside_the_viewer_looks"] == 0
    assert block["jobs_started_while_pressed"] == 1 and block["requests_while_pressed"] == 3
    assert block["jobs_on_sizes_between"] == 1 and block["requests_on_sizes_between"] == 3
    first = block["first_job_after"]
    assert first["ms_after_release"] == 200 and first["cache_hits"] == 1 and first["cache_misses"] == 1
    assert block["frame_sizes_looked_at_during"] == 1
    assert block["new_size_looked_at_ms_after_release"] == 100
    assert block["own_area_at_new_size_ms_after_release"] == 350
    assert block["editor"] is None


def test_a_window_maximised_at_once_is_never_hidden_in_its_step():
    """The first look already at the new size with the overlay on: nothing hidden in the step, whatever the next
    step hides."""
    new = (1920, 0, 3840, 1032)
    rows = [row(t, client=new) for t in range(1000, 2000, 50)]
    rows += [row(t, client=new, overlay=None, left=None, right=None) for t in range(2000, 2200, 50)]  # (next step)
    notes = SimpleNamespace(lock=threading.Lock(), jobs=[], margins=[], lookups=[])
    block = sm.drag_block(rows, {"first_t": 1000, "last_t": 1000, "sizes": 1, "button": False}, notes, 2000)
    assert block["lettering_hidden_ms_after_first_size"] is None
    assert block["panes"]["left"]["hidden_ms_after_first_size"] is None


def test_a_pane_a_window_above_the_viewer_meets_is_told_covered():
    import numpy as np

    over = SimpleNamespace(_pane_want={"left": None, "right": (1, np.zeros((300, 200, 4), np.uint8), (1000, 40, 1200,
                                                                                                    340), ())},
                           _covers=[(2900, 100, 3300, 500)], client_origin=lambda: (1928, 0))
    assert sm._covered_pane(over, "right")  # (1928 + 1000 .. + 200: meets the editor at 2900..3300)
    assert not sm._covered_pane(over, "left")
    over._covers = [(3300, 100, 3500, 500)]
    assert not sm._covered_pane(over, "right")


def test_lettering_left_at_the_old_size_is_counted():
    old, new = (1928, 0, 3212, 892), (1928, 0, 2852, 892)
    rows = [row(t, client=new, overlay=old, set_size=(1284, 892)) for t in range(1000, 1300, 50)]
    rows += [row(t, client=new, marks=(1284, 892)) for t in range(1300, 1500, 50)]
    notes = SimpleNamespace(lock=threading.Lock(), jobs=[], margins=[], lookups=[])
    block = sm.drag_block(rows, {"first_t": 1000, "last_t": 1000, "sizes": 1, "button": False}, notes, 2000)
    assert block["stale_scale_looks"] == 6 and block["stale_place_looks"] == 0 and block["stale_ms"] == 250
    assert block["marks_looks"] == 4 and block["marks_of_another_size_looks"] == 4


def test_a_stale_look_is_timed_from_the_look_that_saw_the_client_so():
    """The client narrower at 1000 ms: the lettering's window still at the old size at 1000 and 1015 ms (15 ms after
    the look that saw the client so), the editing ground alone at 1015; at the new size from 1030 on."""
    old, new = (1928, 0, 3212, 892), (1928, 0, 2852, 892)
    rows = [row(t, client=old) for t in (970, 985)]
    rows += [row(1000, client=new, overlay=old, set_size=(1284, 892))]
    ground = row(1015, client=new, overlay=old)
    ground["shown"]["n"] = 0
    rows += [ground] + [row(t, client=new) for t in (1030, 1045)]
    looks = sm._stale_looks(rows, 900, 2000)
    assert [(t, p, z, a, on) for t, p, z, a, on in looks] == [(1000, False, True, 0, True), (1015, False, True, 15, False)]
    notes = SimpleNamespace(lock=threading.Lock(), jobs=[], margins=[], lookups=[])
    block = sm.drag_block(rows, {"first_t": 1000, "last_t": 1000, "sizes": 1, "button": False}, notes, 2000)
    assert block["stale_longest_ms"] == 15 and block["stale_with_patches_looks"] == 1
    assert sm.drag_block(rows[:2] + rows[4:], {"first_t": 1000, "last_t": 1000, "sizes": 1, "button": False},
                         notes, 2000)["stale_longest_ms"] is None


def test_a_region_is_carried_to_the_page_drawn_at_another_size():
    old, new, top = (0, 0, 1000, 700), (100, 0, 800, 490), 40
    assert sm.carry((100, 110, 300, 320), old, new, top) == (170, 89, 310, 236)
    assert sm.carry((0, 40, 1000, 740), old, new, top) == (100, 40, 800, 530)


def test_an_open_editor_over_a_resize():
    """The editor opened on a region of the page drawn at 1284 x 892 (the screen (3, True)); the client narrower
    from 1000 ms, let go at 1500. Its page never taken over, the step's last look is measured: the editor stayed
    where it was, its region carried to the page drawn at 924 x 892 lies in the viewer and the editor beside it, while
    the region's old box at the client's place runs past the viewer's edge. Taken over at 1700 ms: measured there,
    the box the editor has now in the viewer."""
    old, new = (1928, 0, 3212, 892), (1928, 0, 2852, 892)
    rects = {(1284, 892, 3, True): (0, 0, 1284, 852), (924, 892, 3, True): (0, 100, 924, 700)}
    page = ((1284, 892), (3, True))
    editor = (3000, 100, 3400, 600)

    def look(t, client):
        r = row(t, client=client)
        r.update(editor=editor, editor_monitors=[2], editor_box=(1100, 200, 1250, 400), editor_page=page,
                 editor_region=(client[0] + 1100, client[1] + 200, client[0] + 1250, client[1] + 400))
        return r

    rows = [look(t, old) for t in range(800, 1000, 50)] + [look(t, new) for t in range(1000, 2000, 50)]
    block = sm.editor_block(rows, 1000, 1500, 2000, rects, 40)
    assert block["moved_px"] == 0 and block["editor_monitors"] == [2] and block["measured_ms_after_release"] == 450
    assert block["changes"] == [[-200, [1284, 892], [1100, 200, 1250, 400]]]
    assert block["box_as_kept_in_viewer"] is False and block["taken_over"] is False
    assert block["region_now"] == [1928 + 792, 100 + round(160 * 600 / 852) + 40, 1928 + 900,
                                   100 + round(360 * 600 / 852) + 40]
    assert block["region_now_in_viewer"] is True and block["over_its_region_now"] is False
    assert sm.editor_block(rows, 1000, 1500, 2000, {}, 40)["region_now"] is None
    taken = [r if r["t"] < 1700 else dict(r, editor_page=((924, 892), (3, True)), editor_box=(792, 213, 900, 354),
                                          editor_region=(1928 + 792, 213, 1928 + 900, 354)) for r in rows]
    block = sm.editor_block(taken, 1000, 1500, 2000, rects, 40)  # (the editor's page the one on show now)
    assert block["taken_over"] is True and block["box_as_kept_in_viewer"] is True
    assert block["measured_ms_after_release"] == 200 and len(block["changes"]) == 2
    assert block["region_now"] == [1928 + 792, 213, 1928 + 900, 354]
    assert sm.editor_block([row(t) for t in range(0, 500, 50)], 100, 200, 500) is None


def test_a_region_lies_where_it_was_at_another_size():
    top = 40
    big, small = (0, 0, 1000, 700), (100, 0, 800, 490)  # (the page as the stand-in drew it at each frame size)

    def boxes(p):
        w, h = p[2] - p[0], p[3] - p[1]
        return [(round(p[0] + a * w), round(top + p[1] + b * h), round(p[0] + c * w), round(top + p[1] + d * h))
                for a, b, c, d in ((0.1, 0.1, 0.3, 0.4), (0.6, 0.5, 0.9, 0.8))]

    results = [{"size": (1284, 892), "screen": (3, True), "boxes": boxes(big)},
               {"size": (924, 892), "screen": (3, True), "boxes": boxes(small)},
               {"size": (924, 892), "screen": (5, True), "boxes": boxes(small)[:1]}]
    rects = {(1284, 892, 3, True): big, (924, 892, 3, True): small}
    fit = sm.region_fit(results, rects, top)
    assert fit["pairs_of_sizes"] == 1 and fit["worst_px"]["max"] <= 1.0
    moved = dict(results[1], boxes=[(b[0] + 6, b[1], b[2] + 6, b[3]) for b in boxes(small)])
    assert sm.region_fit([results[0], moved], rects, top)["worst_px"]["max"] >= 5
    assert sm.region_fit([results[0], dict(results[1], boxes=boxes(small)[:1])], rects, top)[
        "pairs_with_other_region_counts"] == 1
    assert sm.region_fit(results[:2], {}, top)["pairs_without_the_page_rect"] == 1


def test_the_report_and_its_table(monkeypatch, capsys):
    s = screens(*TWO)
    monkeypatch.setattr(s, "of_window", lambda hwnd: 2)
    monkeypatch.setattr(sm, "taskbar_setting", lambda: {"all_monitors": 1, "mode": 0, "buttons_on": "every taskbar"})
    sampler = SimpleNamespace(rows=[row(t) for t in range(0, 3000, 50)], results=[], page_rects={})
    tour = SimpleNamespace(rows=[{"segment": "m1", "item": "settings", "front_before": "other",
                                  "front_after": "other", "first": {"monitor": 2, "viewer_monitor": 2,
                                                                    "in_viewer_work_area": True, "tk_dpi": 96,
                                                                    "monitor_dpi": 96, "root_monitor_nearest": 1},
                                  "second": {"monitor": 2}},
                                 {"segment": "m1", "item": "editor", "skipped": "no region on the page"}],
                           handed={"give_foreground": 2})
    see = SimpleNamespace(over=lambda: None, delta_ms=0.0, hover={})
    run = sm.WindowRun(None, 1, s, None, sampler, tour, (1920, 0, 1300, 900), see)
    run.records = [{"name": "m1", "t": 0, "monitor_before": 1, "facts": {"t": 0, "to": [1960, 30, 1300, 900]}},
                   {"name": "r1", "t": 1000, "monitor_before": 2,
                    "facts": {"t": 1000, "drag": {"edge": "right", "button": True, "sizes": 45, "press_t": 1000,
                                                  "first_t": 1100, "last_t": 2000, "release_t": 2100}}}]
    notes = SimpleNamespace(lock=threading.Lock(), jobs=[], margins=[], lookups=[])
    report = run.report(notes, 40, 3000)
    assert [p["segment"] for p in report["places"]] == ["m1", "r1"]
    assert report["places"][0]["tour"][0]["item"] == "settings" and "resize" in report["places"][1]
    assert report["handed_over_refused"] == {"give_foreground": 2}
    standin_e2e.print_monitors(report)
    out = capsys.readouterr().out
    assert "m1: monitor 2" in out and "settings: monitor 2" in out and "resize right button True" in out
    assert "skipped (no region on the page)" in out
