"""The browser-type stand-in viewer (tools/standin_viewer) and its driver's plan (tools/standin_e2e.py), with no
browser, no GPU and no Ollama: the script's format, the page with nothing to fetch from anywhere, its files written
in the scratch folder alone, the window found only in the tree the tool started with its token, the guard on the
window TASlation chose, and the band's code read back from a frame."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import standin_e2e  # noqa: E402
import standin_viewer as sv  # noqa: E402
from test_side_indicator import Window, no_way_to_the_viewer  # noqa: E402,F401 - the window, and its fixture


# ---------------------------------------------------------------------------------------------------- the script
def test_script_round_trips():
    text = "g1,m1,w1200,n,w2500-3500,p,j12,f,f700,s1500,t700,b2,t,b,e"
    steps = sv.parse_script(text)
    assert sv.format_script(steps) == text
    assert sv.parse_script(sv.format_script(steps)) == steps
    assert steps[4] == sv.Step("w", 2500, 3500)
    assert steps[5] == sv.Step("p") and steps[6] == sv.Step("j", 12)
    assert steps[10:14] == [sv.Step("t", 700), sv.Step("b", 2), sv.Step("t"), sv.Step("b")]


@pytest.mark.parametrize("bad", ["x1", "w", "g", "j", "w9-3", "n5-6", "w-3", "ww1"])
def test_bad_steps_refused(bad):
    with pytest.raises(ValueError):
        sv.parse_script(bad)


def test_the_page_knows_every_step_the_script_has():
    html = sv.HTML.read_text(encoding="utf-8")
    page_ops = re.search(r"\^\(\[([a-z]+)\]\)", html)
    assert page_ops is not None and set(page_ops.group(1)) == set(sv.OPS)


def test_the_plan_foresees_the_screens_and_holds_each_scenario():
    names = standin_e2e.wanted("all")
    assert names == ["c", "a", "b", "d", "e", "r", "t", "t2", "o", "z", "x", "f", "f2"]
    count = standin_e2e.pages_needed(names)
    segments, steps = standin_e2e.build_plan(names, count + 6, cancel_first=count, soft_ms=700)
    text = sv.format_script(steps)
    for s in segments:
        assert f"g{s.go},m{s.go}," in text
    assert text.endswith(",e")
    turns = {s.name: s.screens for s in segments}
    assert turns["c"] == [(2, True), (4, True), (6, True)]
    assert turns["e"][:3] == [(48, True), (46, True), (44, True)]  # turning back
    # t: on the Translator's full screen the next page by the window's page key, t2 back by its previous one
    assert turns["t"] == [(56, True)] and turns["t2"] == [(54, True)]
    # x: the screens of little text added after the others, soft long and half as sharp, then back where it was
    assert turns["x"] == [(count, True), (count + 2, True), (count + 4, True), (64, True)]
    assert f"t700,b2,j{count},w5000," in text and ",t,b,j64,w4000," in text
    assert turns["f2"] == [(69, False), (70, False)]  # single pages once the window is narrow
    assert standin_e2e.wanted("f,a") == ["a", "f", "f2"]
    assert standin_e2e.wanted("f2") == ["f2"]  # the narrow window alone
    assert standin_e2e.wanted("t2") == standin_e2e.wanted("t") == ["t", "t2"]  # the key forward, then back
    with pytest.raises(SystemExit):
        standin_e2e.wanted("a,y")  # (q is scenario q, for a stand-in with a profile)


def _plan(wait_done=None):
    names = standin_e2e.wanted("all")
    first = standin_e2e.pages_needed(names)
    return first, standin_e2e.build_plan(names, first + 6, first, 700, wait_done)


def test_without_wait_done_the_script_is_as_written():
    first, (segments, steps) = _plan()
    assert standin_e2e.build_plan(standin_e2e.wanted("all"), first + 6, cancel_first=first, soft_ms=700)[1] == steps
    assert not any(s.op in "hk" for s in steps)  # no hold, no soft frame kept
    for s in segments:
        if s.name != "x":
            assert s.steps == standin_e2e.SCENARIOS[s.name][1]
    x = next(s for s in segments if s.name == "x")
    assert x.steps == ["t700", "b2", f"j{first}", "w5000", f"j{first + 2}", "w5000", f"j{first + 4}", "w5000", "t",
                       "b", "j64", "w4000"]


def test_wait_done_holds_every_rest_the_last_too_and_keeps_x_soft_until_asked():
    _first, (plain, _steps) = _plan()
    _first, (held, held_steps) = _plan(wait_done=60.0)
    assert [s.screens for s in held] == [s.screens for s in plain]  # the same turns to the same screens
    holds = [s.a for s in held_steps if s.op == "h"]
    assert holds == list(range(1, len(holds) + 1))  # numbered through the script
    for p, h in zip(plain, held):
        if h.name not in standin_e2e.HOLD_SCENARIOS:  # c, b, t, t2: as written
            assert h.steps == p.steps
            continue
        bare = [s for s in h.steps if not s.startswith("h")]
        if h.name == "x":
            assert bare[0] == "k15000" and "k" in bare  # (kept until asked, 15 s at most; then as before)
            bare = [{"k15000": "t700", "k": "t"}.get(s, s) for s in bare]
        assert bare == p.steps
        rests = [s for s in p.steps if s.startswith("w") and int(s[1:].split("-")[0]) >= standin_e2e.REST_MS]
        assert sum(1 for s in h.steps if s.startswith("h")) == len(rests)  # each rest a reader takes ...
        for k, step in enumerate(h.steps):
            if step.startswith("h"):
                before = h.steps[k - 1]
                assert before.startswith("w") and int(before[1:].split("-")[0]) >= standin_e2e.REST_MS
        # ... the one at the end too: the driver changes the window for the next scenario once the stand-in waits
        assert h.steps[-1].startswith("h"), h.name
    by = {s.name: s.steps for s in held}
    assert by["a"][:4] == ["n", "w6000-8000", "h1", "n"] and by["a"][-3:] == ["n", "w6000-8000", "h9"]
    assert [s for s in by["d"] if s.startswith("h")] == ["h10", "h11", "h12", "h13", "h14"]
    assert "w300" in by["d"] and by["d"][by["d"].index("w300") + 1] == "f700"  # (a quick turn: no hold)
    assert sum(1 for s in by["x"] if s.startswith("h")) == 4
    assert by["f"] == ["n", "w6000", next(s for s in by["f"] if s.startswith("h")), "n", "w6000", by["f"][-1]]
    text = sv.format_script(held_steps)  # f's last page is held before f2's narrow window comes
    f2 = next(s for s in held if s.name == "f2")
    assert f",w6000,{by['f'][-1]},g{f2.go},m{f2.go}," in text
    _first, (short, _s) = _plan(wait_done=8.0)
    assert next(s for s in short if s.name == "x").steps[0] == "k8000"  # never longer than the cap


def test_a_hold_is_over_once_its_page_is_finished_the_window_rests_without_it_or_the_cap():
    over = standin_e2e.hold_over
    shown = {"page": 4, "spread": True, "kind": "translated"}
    assert over((4, True), "sharp", shown, 0.0, 1.0, 60) == "finished"
    assert over((4, True), "sharp", {**shown, "kind": "final"}, 0.0, 1.0, 60) == "finished"
    assert over((4, True), "sharp", {**shown, "kind": "filling"}, 0.0, 1.0, 60) is None
    assert over((4, True), "sharp", {**shown, "page": 2}, 0.0, 1.0, 60) is None  # another page's picture
    assert over((4, True), "soft", shown, 9.0, 1.0, 60) is None  # (kept soft: neither finished nor at rest on it)
    assert over((4, True), "black", shown, 9.0, 1.0, 60) is None
    assert over((4, True), "sharp", {**shown, "kind": "live"}, standin_e2e.IDLE_S, 1.0, 60) == "idle"
    assert over((4, True), "sharp", {**shown, "kind": "live"}, standin_e2e.IDLE_S - 0.1, 1.0, 60) is None
    assert over((4, True), "sharp", None, 0.5, 60.0, 60) == "cap"


def test_the_control_file_is_the_go_alone_without_wait_done(tmp_path):
    me = SimpleNamespace(wait_done=None, control={"go": 0, "hold": 0, "sharp": 0}, standin_dir=tmp_path)
    standin_e2e.Director.release(me, go=3)
    control = tmp_path / sv.CONTROL
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 3});\n'
    assert sv.write_control(tmp_path, 3).read_text(encoding="utf-8") == 'standinControl({"go": 3});\n'
    me.wait_done = 60.0
    standin_e2e.Director.release(me, hold=2)
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 3, "hold": 2, "sharp": 0});\n'
    standin_e2e.Director.release(me, sharp=1)
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 3, "hold": 2, "sharp": 1});\n'
    # --k-keys: the turns released go with the rest once there is one
    standin_e2e.Director.release(me, turns=2)
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 3, "hold": 2, "sharp": 1, "turns": 2});\n'
    me.wait_done = None
    standin_e2e.Director.release(me, go=4)
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 4, "turns": 2});\n'


def test_wait_done_lets_a_hold_go_when_its_page_is_finished_and_a_soft_frame_when_the_window_asked():
    import threading

    released = []
    notes = SimpleNamespace(lock=threading.Lock(), displays=[], requests=[], jobs=[])
    me = SimpleNamespace(wait_done=60.0, holds=[], keeps=[], notes=notes, idle_since=None, screen_now=(4, True),
                         screen_state="sharp", screen_since=0.0, release=lambda **k: released.append(k))
    me.holds.append({"id": 1, "segment": "a", "page": 4, "spread": True, "at": 10.0, "why": None, "waited_ms": None})
    standin_e2e.Director.waits(me, 12.0)
    assert released == [] and me.holds[0]["why"] is None
    notes.displays.append({"t": 0, "page": 4, "spread": True, "state": "sharp", "kind": "translated", "lettered": 3})
    standin_e2e.Director.waits(me, 13.0)
    assert released == [{"hold": 1}] and me.holds[0]["why"] == "finished" and me.holds[0]["waited_ms"] == 3000
    # the window at rest with the page untranslated: let go too, and said so
    me.screen_now, me.idle_since = (6, True), 15.0
    me.holds.append({"id": 2, "segment": "a", "page": 6, "spread": True, "at": 14.0, "why": None, "waited_ms": None})
    standin_e2e.Director.waits(me, 16.0)
    assert released[-1] == {"hold": 1}
    standin_e2e.Director.waits(me, 17.0)
    assert released[-1] == {"hold": 2} and me.holds[1]["why"] == "idle"
    # a soft frame kept: let go at the window's first request on a soft frame of that screen
    me.keeps.append({"n": 1, "segment": "x", "page": 90, "spread": True, "at": 20.0, "requests_from": 0,
                     "asked_ms": None, "why": None, "waited_ms": None})
    notes.jobs += [{"id": 1, "page": 88, "spread": True}, {"id": 2, "page": 90, "spread": True}]
    notes.requests += [{"job": 1, "frame": "soft"}, {"job": 2, "frame": "sharp"}, {"job": None, "frame": None}]
    standin_e2e.Director.waits(me, 21.0)
    assert released[-1] == {"hold": 2}
    notes.requests.append({"job": 2, "frame": "soft"})
    standin_e2e.Director.waits(me, 22.5)
    assert released[-1] == {"sharp": 1} and me.keeps[0]["asked_ms"] == 2500
    standin_e2e.Director.waits(me, 23.0)
    assert len(released) == 3  # (once)


def test_a_stale_overlay_says_how_long_of_it_came_after_the_window_captured_the_new_screen():
    line = [(1000.0, (2, True), "sharp"), (5000.0, (4, True), "soft"), (5200.0, (4, True), "sharp")]
    shown = {"state": "sharp", "from": "sharp", "quick": False}
    displays = [{"t": 1500.0, "page": 2, "spread": True, "kind": "translated", "lettered": 3, **shown},
                {"t": 7000.0, "page": 4, "spread": True, "kind": "live", "lettered": 0, **shown}]
    captures = [{"t": 1100.0, "page": 2, "spread": True, "state": "sharp"},
                {"t": 6600.0, "page": 4, "spread": True, "state": "sharp"}]
    spells = standin_e2e.incidents(SimpleNamespace(displays=displays, captures=captures), line, 9000.0)
    stale = spells["stale_overlays"]
    assert len(stale) == 1 and stale[0]["ms"] == 2000 and stale[0]["seen_ms"] == 400
    spells = standin_e2e.incidents(SimpleNamespace(displays=displays, captures=captures[:1]), line, 9000.0)
    assert spells["stale_overlays"][0]["seen_ms"] is None  # (never captured within it)


def _on_show(t, page, kind, lettered=0, state="sharp"):
    return {"t": t, "page": page, "spread": True, "state": state, "kind": kind, "lettered": lettered, "from": state,
            "quick": False}


def test_a_rest_ends_where_the_driver_changed_the_window_for_the_next_scenario():
    # t2's page came back from the cache at once; then, as the stand-in waited for o, the driver left the full screen
    # and went over the book, whose live frame of the same page came before o's first turn
    turns = [{"segment": "t2", "screen": (0, True), "why": "previous", "soft_t": 1000.0, "sharp_t": 1100.0,
              "next_t": 8000.0},
             {"segment": "o", "screen": (2, True), "why": "next", "soft_t": 8000.0, "sharp_t": 8300.0,
              "next_t": 12000.0}]
    displays = [_on_show(1300.0, 0, "translated", 6), _on_show(6000.0, 0, "live"), _on_show(8500.0, 2, "reading")]
    notes = SimpleNamespace(jobs=[], displays=displays, captures=[], requests=[], status_lines=[],
                            acts=[{"t": 5000.0, "segment": "t2", "act": "left"},
                                  {"t": 5050.0, "segment": "o", "act": "entered"}])
    rows = standin_e2e.turn_rows(turns, notes, 12000.0)
    assert (rows[0]["at_rest"], rows[0]["rest_ms"], rows[0]["rest_ended_by"]) == ("translated", 3900, "t2 left")
    assert (rows[1]["at_rest"], rows[1]["rest_ms"], rows[1]["rest_ended_by"]) == ("being read", 3700, None)
    assert rows[0]["finished_ms"] == 200  # (its times are the page's own, as before)
    notes.acts = []  # without the driver's changes: the next turn ends the rest, as it always did
    rows = standin_e2e.turn_rows(turns, notes, 12000.0)
    assert (rows[0]["at_rest"], rows[0]["rest_ms"], rows[0]["rest_ended_by"]) == ("untranslated", 6900, None)
    # a change before the turn's sharp frame (the start's first scenario changing the window at once) cuts nothing
    notes.acts = [{"t": 1050.0, "segment": "f2", "act": "narrow window"}]
    assert standin_e2e.turn_rows(turns, notes, 12000.0)[0]["rest_ms"] == 6900


def test_a_turn_is_timed_from_the_turn_and_from_the_sharp_draw_and_the_way_to_its_job_is_parted():
    turns = [{"segment": "a", "screen": (4, True), "why": "next", "soft_t": 1000.0, "sharp_t": 1250.0,
              "next_t": 9000.0}]
    job = {"id": 1, "t": 1300.0, "work_t": 1320.0, "page": 4, "spread": True, "state": "sharp", "started": True,
           "result_t": 6000.0, "done_t": 6100.0, "discarded": False, "requests": 1}
    captures = [{"t": 1040.0, "page": 4, "spread": True, "state": "soft"},
                {"t": 1290.0, "page": 4, "spread": True, "state": "sharp"}]
    displays = [_on_show(1050.0, 4, "live", state="soft"), _on_show(3650.0, 4, "filling", 3),
                _on_show(6050.0, 4, "final", 9)]
    notes = SimpleNamespace(jobs=[job], displays=displays, captures=captures, requests=[{"t": 1900.0, "job": 1}],
                            status_lines=[], acts=[])
    (row,) = standin_e2e.turn_rows(turns, notes, 9000.0)
    assert (row["soft_to_sharp_ms"], row["captured_from_turn_ms"], row["captured_sharp_ms"]) == (250, 40, 40)
    assert (row["job_after_sharp_capture_ms"], row["job_queued_ms"], row["job_from_turn_ms"]) == (10, 20, 300)
    assert (row["first_request_from_turn_ms"], row["first_request_ms"]) == (900, 650)
    assert (row["lettered_from_turn_ms"], row["first_lettered_ms"]) == (2650, 2400)
    assert (row["finished_from_turn_ms"], row["finished_ms"]) == (5050, 4800)


def test_the_timing_figures_take_the_rested_turns_to_pages_not_cached_by_screen_and_say_the_viewer_s_mode():
    def row(segment, spread, cached=False, rest=5000, **times):
        return {**dict.fromkeys(standin_e2e.TIMING_KEYS), "segment": segment, "spread": spread, "cached": cached,
                "rest_ms": rest, **times}

    rows = [row("a", True, lettered_from_turn_ms=2400, first_lettered_ms=2400, finished_ms=7000),
            row("a", True, lettered_from_turn_ms=2600, first_lettered_ms=2600, finished_ms=8000),
            row("a", True, cached=True, first_lettered_ms=90),  # (a page the cache held: left out, counted)
            row("c", True, first_lettered_ms=9000),  # (the model still loading)
            row("a", True, rest=900, first_lettered_ms=40),  # (flipped past: no rest)
            row("f2", False, lettered_from_turn_ms=1500, first_lettered_ms=1500, finished_ms=4000)]
    said = [{"ev": "ready", "soft_first": "0"}, {"ev": "draw", "state": "sharp"}, {"ev": "draw", "state": "sharp"}]
    t = standin_e2e.timing_summary(rows, False, [], said, lambda v: v)
    assert (t["soft_first"], t["standin_said_soft_first"], t["standin_draws"]) == ("off", "0", {"sharp": 2})
    assert t["window_learnt_soft_first"] == 0 and t["learnt"] == [] and t["cached_turns_left_out"] == 1
    two, one = t["two_pages"], t["one_page"]
    assert two["turns"] == 2 and two["first_lettered_ms"] == {"n": 2, "median": 2500, "p90": 2600, "max": 2600}
    assert two["finished_ms"]["median"] == 7500 and two["soft_to_sharp_ms"] == {"n": 0}
    assert one["turns"] == 1 and one["lettered_from_turn_ms"]["median"] == 1500
    assert set(t["by_segment"]) == {"a", "f2"}
    learnt = [{"t": 5.0, "soft": {"page": 4, "spread": True, "state": "soft"},
               "sharp": {"page": 4, "spread": True, "state": "sharp"}}]
    assert standin_e2e.timing_summary(rows, True, learnt, [], lambda v: v)["window_learnt_soft_first"] == 1


def test_without_soft_first_the_stand_in_draws_every_turn_sharp_at_once_and_x_is_left_out(tmp_path):
    steps = sv.parse_script("g1,n,e")
    plain = sv.page_url("t1234", steps, tmp_path)
    assert "soft_first=" not in plain  # (on: the URL as it always was)
    sharp = sv.page_url("t1234", steps, tmp_path, soft_first=False)
    assert sharp.split("#")[0] == plain.split("#")[0] + "&soft_first=0" and sharp.endswith("#s=g1,n,e")
    html = sv.HTML.read_text(encoding="utf-8")
    assert 'softFirst: query.get("soft_first") !== "0"' in html
    assert "drawScreen(cfg.softFirst, why)" in html and "if (!done || !cfg.softFirst) return;" in html
    everything = standin_e2e.wanted("all")
    assert standin_e2e.soft_first_scenarios(everything, "all", True) == (everything, None)
    names, why = standin_e2e.soft_first_scenarios(standin_e2e.wanted("all"), "all", False)
    assert names == [n for n in everything if n != "x"] and "soft frames" in why
    assert standin_e2e.soft_first_scenarios(standin_e2e.wanted("a,f"), "a,f", False) == (["a", "f", "f2"], None)
    with pytest.raises(SystemExit):
        standin_e2e.soft_first_scenarios(standin_e2e.wanted("a,x"), "a,x", False)
    args = standin_e2e.parse(["--scenario", "a,f", "--soft-first", "off"])
    assert args.soft_first == "off" and standin_e2e.parse([]).soft_first == "on"


def test_a_job_whose_page_went_on_at_a_new_size_was_not_cancelled_with_its_page_on_show():
    # scenario o on a runner: the stand-in back from its monitor's size at 77.06 s, the window's first capture of the
    # new size 0.93 s later, the job on the old size's frame cancelled at 79.33 s, a job on the new frame after it
    job = {"t": 70910.0, "cancelled_t": 79330.0, "size": [1904, 1072]}
    captures = [{"t": 70000.0, "size": [1904, 1072]}, {"t": 77994.0, "size": [1904, 1024]},
                {"t": 79400.0, "size": [1904, 1024]}]
    assert standin_e2e.resized_away(job, [77060.0], captures)
    assert not standin_e2e.resized_away(job, [], captures)  # no change of size while it ran
    assert not standin_e2e.resized_away(job, [60000.0], captures)  # one before it began
    assert not standin_e2e.resized_away(job, [77060.0], captures[:1])  # the new size not captured by the cancel
    assert not standin_e2e.resized_away({**job, "cancelled_t": None}, [77060.0], captures)
    assert not standin_e2e.resized_away({**job, "size": None}, [77060.0], captures)


def test_holds_and_kept_soft_frames_are_steps_of_the_script():
    steps = sv.parse_script("g1,m1,k15000,n,w6000,h1,k,e")
    assert steps[2] == sv.Step("k", 15000) and steps[5] == sv.Step("h", 1) and steps[6] == sv.Step("k")
    assert sv.format_script(steps) == "g1,m1,k15000,n,w6000,h1,k,e"
    with pytest.raises(ValueError):
        sv.parse_script("h")  # (a hold needs its number)


def test_scenario_k_flips_fresh_pages_past_then_reads_them_back_and_is_never_in_all():
    assert "k5" not in standin_e2e.wanted("all")
    assert standin_e2e.wanted("k") == ["k5", "k1", "k2"] and standin_e2e.wanted("k1,c") == ["c", "k1"]
    names = standin_e2e.wanted("c,k")
    count = standin_e2e.pages_needed(names, 4)
    segments, _steps = standin_e2e.build_plan(names, count, k={"turns": 4, "read": 2, "soft": False, "narrow": False})
    k5 = next(s for s in segments if s.name == "k5")
    assert k5.steps == ["t0", "b1", "j8", "w8000", "n", "w500", "n", "w500", "n", "w500", "n", "w500", "j10",
                        "w8000", "n", "w8000", "t", "b"]  # (after c's pages; sharp at once; back to the first flipped)
    k1 = next(s for s in segments if s.name == "k1")
    assert k1.screens[0] == (18, True) and k1.screens[-1] == (22, True)  # (pages no scenario turned to before)
    assert all(index < count for s in segments for index, _spread in s.screens)
    narrow, _ = standin_e2e.build_plan(["k2"], 40, k={"turns": 3, "read": 3, "soft": True, "narrow": True})
    assert narrow[0].steps[:2] == ["j1", "w8000"]
    assert narrow[0].screens == [(1, False), (2, False), (3, False), (4, False), (2, False), (3, False), (4, False)]


def test_scenario_k_by_the_windows_page_key_waits_for_each_release_and_its_last_flip_may_stay(tmp_path):
    keyed = standin_e2e.k_steps("k5", 8, 2, 4, 2, False, keyed=True)  # (--k-keys: no wait of the stand-in's own)
    assert keyed == ["t0", "b1", "j8", "u", "n", "u", "n", "u", "n", "u", "n", "u", "j10", "u", "n", "u", "t", "b"]
    times = standin_e2e.k_key_times(500, 4, 2)  # (the waits of the steps without keys)
    assert times == [(8.0, "key"), (8.5, "key"), (9.0, "key"), (9.5, "key"), (10.0, "driver"), (18.0, "key"),
                     (26.0, "driver")]
    assert keyed.count("u") == len(times)
    stay = standin_e2e.k_steps("k1", 8, 2, 3, 2, True, stay_ms=6000)  # (--k-stay-ms: the last page flipped to)
    assert stay == ["j8", "w8000", "n", "w1000", "n", "w1000", "n", "w6000", "j10", "w8000", "n", "w8000"]
    assert standin_e2e.k_key_times(1000, 3, 2, stay_ms=6000)[2:4] == [(10.0, "key"), (16.0, "driver")]
    plan = {"turns": 3, "read": 3, "soft": False, "narrow": True}
    plain, _ = standin_e2e.build_plan(["k2"], 40, k=plan)
    keys, steps = standin_e2e.build_plan(["k2"], 40, k={**plan, "keys": True})
    assert keys[0].screens == plain[0].screens and sv.Step("u") in steps  # (the same turns, released otherwise)
    control = sv.write_control(tmp_path, 3, turns=2)
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 3, "turns": 2});\n'


def test_the_pages_of_little_text_come_from_the_annotation_counts_alone(tmp_path):
    import json

    dataset = tmp_path / "dataset"
    pages = []
    for series, counts in (("s1", [1, 5, 2]), ("s2", [0, 2, 1, 3, 1])):
        folder = dataset / "images" / series / "ja"
        folder.mkdir(parents=True)
        for k, n in enumerate(counts):
            (folder / f"{k:03d}.jpg").write_bytes(b"not read")
            pages.append({"image_paths": {"ja": f"images/{series}/ja/{k:03d}.jpg"}, "text": [{}] * n})
    (dataset / "annotation.json").write_text(json.dumps([{"book_title": "not read", "pages": pages}]),
                                             encoding="utf-8")
    taken = [dataset / "images" / "s2" / "ja" / "001.jpg"]
    found = standin_e2e.little_text_pages(taken, 3, dataset)
    # the last series first, in reading order; neither a page taken, nor one without text or with more than two lines
    assert [p.relative_to(dataset).as_posix() for p in found] == [
        "images/s2/ja/002.jpg", "images/s2/ja/004.jpg", "images/s1/ja/000.jpg"]
    assert len(standin_e2e.little_text_pages([], 9, dataset)) == 5  # all there are
    assert standin_e2e.little_text_pages([], 2, tmp_path / "none") == []


def test_the_hot_keys_reach_no_system_and_a_press_is_taken_only_for_a_key_held():
    notes = standin_e2e.Notes(31, 1.0)
    keys = standin_e2e.HotKeys(notes)
    assert keys.register("F5", 0x74) and keys.register("F11", 0x7A) and keys.registered == {"F5", "F11"}
    keys.press("F11")
    keys.press("Escape")  # (not held: the viewer's key)
    assert keys.take() == ["F11"] and keys.take() == []
    keys.unregister("F11")
    keys.clear()
    assert keys.registered == frozenset()
    held = [h["held"] for h in notes.hotkeys if "held" in h]
    assert held == [["F5"], ["F11", "F5"], ["F5"], []]
    assert [(h["pressed"], h["taken"]) for h in notes.hotkeys if "pressed" in h] == [("F11", True), ("Escape", False)]


def test_the_part_drawn_is_told_against_the_page_the_stand_in_drew():
    # the narrow window: the page drawn 68 rows down the canvas, which begins under the browser's 31-row title bar
    whole = standin_e2e.page_facts([0, 0, 844, 992], (118, 68, 727, 927), 54, 31)
    assert whole["page"] == [118, 99, 727, 958] and whole["content_top"] == 85 and whole["page_whole"]
    assert whole["title_bar_rows_drawn"] == 31 and whole["band_rows_drawn"] == 54
    assert whole["ground_drawn"] == [118, 99, 117, 34]
    alone = standin_e2e.page_facts([118, 99, 727, 958], (118, 68, 727, 927), 54, 31)
    assert alone["title_bar_rows_drawn"] == alone["band_rows_drawn"] == 0 and alone["ground_drawn"] == [0, 0, 0, 0]
    cut = standin_e2e.page_facts([118, 76, 700, 958], (118, 68, 727, 927), 54, 31)
    assert cut["band_rows_drawn"] == 9 and not cut["page_whole"] and cut["ground_drawn"][2] == -27
    assert standin_e2e.page_facts([0, 0, 1, 1], None, 0, 31) == {"page": None}


def _job(id_, t, state="sharp", discarded=None, result_t=None, page=4):
    return {"id": id_, "t": t, "state": state, "page": page, "spread": True, "started": True, "discarded": discarded,
            "result_t": result_t}


def _request(t, job, end, server=None, http=None, work=None):
    return {"t": t, "job": job, "frame": "x", "gate": "pending", "outcome": "ok" if server else "Cancelled",
            "end_t": end, "http_t": http, "http_end_t": end if http is not None else None, "server_ms": server,
            "work_ms": work}


def test_requests_sent_for_nothing_are_told_with_what_they_cost():
    jobs = [_job(1, 1000, "soft", True), _job(2, 1300, "sharp", True), _job(3, 1500, "sharp", False, 2600)]
    requests = [_request(1100, 1, 1250), _request(1400, 2, 1480),
                _request(1600, 3, 1900, server=250.0, http=1610, work=50.0)]
    wasted = standin_e2e.wasted_requests(requests, jobs, [1200, 1450], 5000)
    assert [(w["job"], w["why"], w["ran_ms"], w["ran_on_after_cancel_ms"]) for w in wasted] == [
        (1, "soft", 150, 50), (2, "dropped", 80, 30)]
    # the wait is the exchange less the model's work, not less Ollama's total, which takes in a wait behind another
    assert wasted[0]["next_real_after_ms"] == 350 and wasted[0]["next_real_server_wait_ms"] == 240
    assert standin_e2e.server_wait(_request(1600, 3, 1900, server=250.0, http=1610)) is None
    # the page's job is the last one on its screen whose result came and was kept
    assert standin_e2e.finishing_job(jobs, (4, True), 900, 3000)["id"] == 3
    assert standin_e2e.finishing_job(jobs, (6, True), 900, 3000) is None
    assert standin_e2e.dist([None, 5, 1, 3]) == {"n": 3, "min": 1, "p25": 3, "median": 3, "p75": 5, "max": 5}
    assert standin_e2e.dist([]) == {"n": 0}


def test_the_watch_tells_what_the_server_answers_on_a_dump(monkeypatch):
    assert standin_e2e.server_says(None) == "server: not asked"
    answers = {"/api/version": {"version": "0.40.0"},
               "/api/ps": {"models": [{"name": "plamo:2b", "size_vram": 3 * 2 ** 30, "expires_at": "12:00"}]}}
    monkeypatch.setattr(standin_e2e, "ollama_get", lambda url, path, timeout=3.0: answers.get(path))
    said = standin_e2e.server_says("http://127.0.0.1:11435")
    assert said.startswith("server: version 0.40.0 in ") and "plamo:2b (3072 MiB on the GPU, expires 12:00)" in said
    answers["/api/ps"] = {"models": []}
    assert "nothing loaded" in standin_e2e.server_says("http://127.0.0.1:11435")
    answers.clear()
    assert "version no answer" in standin_e2e.server_says("http://x:1") and "ps no answer" in \
        standin_e2e.server_says("http://x:1")

    def blocked(*_a, **_k):
        raise RuntimeError("blocked")

    monkeypatch.setattr(standin_e2e, "ollama_get", blocked)
    assert standin_e2e.server_says("http://x:1") == "server: not asked (RuntimeError)"


def test_the_log_tap_keeps_each_line_of_the_rule_for_no_answer_with_what_the_server_said(monkeypatch):
    import logging
    import threading
    import time

    notes = SimpleNamespace(lock=threading.Lock(), ocr_log=[])
    monkeypatch.setattr(standin_e2e, "server_says", lambda url: f"server: asked at {url}")
    tap = standin_e2e.LogTap(notes, "http://127.0.0.1:11435")
    log = logging.getLogger("taslation.translate.ollama")

    def emit(msg, *args):
        tap.emit(log.makeRecord(log.name, logging.WARNING, __file__, 1, msg, args, None))

    emit("no answer: %s (%s), %.1f s %s (incident %d, silence %d)", "request", "taslation-worker", 30.0,
         "without a byte", 1, 1)
    emit("no answer: %s asked again on a new connection (/api/ps answers)", "request")
    emit("a line of something else")
    deadline = time.monotonic() + 2.0
    while "server_says" not in tap.no_answer[0] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert [n["line"][:28] for n in tap.no_answer] == ["no answer: request (taslatio", "no answer: request asked aga"]
    assert tap.no_answer[0]["server_says"] == "server: asked at http://127.0.0.1:11435"  # (the silence's line only)
    assert "server_says" not in tap.no_answer[1] and tap.levels["WARNING taslation.translate.ollama"] == 3


def test_the_log_tap_keeps_the_windows_lines_of_the_viewer_kept_under_it_and_hidden_wholly(monkeypatch, capsys):
    """(the very lines `ui.order` logs, from its own calls on made-up windows)"""
    import logging
    import threading

    from taslation.ui import order

    notes = SimpleNamespace(lock=threading.Lock(), ocr_log=[])
    tap = standin_e2e.LogTap(notes)
    log = logging.getLogger(order.__name__)
    level = log.level
    log.addHandler(tap)
    log.setLevel(logging.INFO)
    try:
        monkeypatch.setattr(order, "IS_WINDOWS", True)
        monkeypatch.setattr(order, "foreground_window", lambda: 99)
        monkeypatch.setattr(order, "foreground_owner", lambda hwnd, viewer: "own")
        monkeypatch.setattr(order, "keep_viewer_under", lambda viewer, own, between=None: "placed")
        monkeypatch.setattr(order, "window_class", lambda hwnd: "Chrome_WidgetWin_1")
        monkeypatch.setattr(order, "fully_covered", lambda hwnd, opaque=False: True)
        w = SimpleNamespace(selected=SimpleNamespace(hwnd=20), _own_hwnd=lambda: 10, _raised=None,
                            _resizing=lambda: False, _frame_count=lambda: 7, _status_key=None,
                            say=lambda key: None, status=lambda text: None)
        t = 100.0
        order.turn_asked(w, 20, 7, t)  # (a page key handed on to it, whose frame does not come)
        for _ in range(order.ORDER_MOST + 1):
            order.beat(w, t)
            t += max(order.ORDER_EVERY_S, order.COVER_EVERY_S)
        order.keep_under(w, t)
    finally:
        log.removeHandler(tap)
        log.setLevel(level)
    lines = [n["line"] for n in tap.window_order]
    assert sum("put directly under" in x for x in lines) == order.ORDER_MOST
    assert sum("left as it is" in x for x in lines) == 1
    assert sum(x.startswith("the viewer is hidden wholly") for x in lines) == 1
    standin_e2e.print_table({"translator": "t", "browser": "b", "pages": 1,
                             "run": {"seconds": 1, "window_order": tap.window_order}}, Path("report.json"))
    assert (f"put under the window {order.ORDER_MOST} time(s), left as it was 1 time(s), refused 0 time(s); hidden "
            "wholly, no frame after a page key 1 time(s)") in capsys.readouterr().out


def _frames_watched(monkeypatch, tmp_path, captures, drawn_page=5, capture_n=5):
    """The frame watch on notes where the stand-in drew page *drawn_page* sharp 7 s ago and the window took
    *capture_n* frames since, the last of *captures* a moment ago; its probes' parts stand-ins."""
    import threading
    from taslation.capture import wgc

    monkeypatch.setattr(standin_e2e, "window_cover", lambda hwnd, pid, pids: {"points": {"stand-in": 64},
                                                                              "front": "x", "pids": sorted(pids())})
    monkeypatch.setattr(standin_e2e, "fresh_frame", lambda notes, hwnd: {"ms": 50, "shows": {"page": drawn_page}})
    monkeypatch.setattr(standin_e2e, "idle_seconds", lambda: 12.0)
    monkeypatch.setattr(wgc, "_session", None)
    notes = standin_e2e.Notes(0, 1.0)
    now = standin_e2e.now_ms()
    notes.drawn_last = {"t": now - 7000, "page": drawn_page, "spread": False, "state": "sharp", "capture_n": 0}
    notes.captures = [{"t": now + dt, "page": p, "spread": False, "state": "sharp", "size": [9, 9]}
                      for dt, p in captures]
    notes.capture_n, notes.last_capture_t = capture_n, now - 100
    stop = threading.Event()
    thread = standin_e2e.watch_frames(notes, 1, 2, tmp_path / "stacks.txt", stop, every=0.02,
                                      standin_pids=lambda: {30, 31})
    return notes, stop, thread


def _until(test, seconds=3.0):
    import time

    deadline = time.monotonic() + seconds
    while not test() and time.monotonic() < deadline:
        time.sleep(0.01)
    return test()


def test_the_frame_watch_finds_the_window_s_frames_standing_still_and_their_end(monkeypatch, tmp_path):
    notes, stop, thread = _frames_watched(monkeypatch, tmp_path, [(-9000, 4)])
    try:
        assert _until(lambda: notes.frame_stalls and notes.frame_stalls[0]["probes"])
        stall = notes.frame_stalls[0]
        assert stall["frozen"] == (4, False, "sharp") and stall["drawn"]["page"] == 5 and stall["until_t"] is None
        probe = stall["probes"][0]
        assert probe["cover"]["points"] == {"stand-in": 64} and probe["fresh"]["shows"] == {"page": 5}
        assert probe["cover"]["pids"] == [30, 31]  # (the stand-in browser's processes, to tell its own windows)
        assert probe["idle_s"] == 12.0 and probe["window_session"] is None and probe["drawn"]["page"] == 5
        assert "stand still on (4, False, 'sharp')" in (tmp_path / "stacks.txt").read_text(encoding="utf-8")
        with notes.lock:  # the window's frames go on: the stall ends
            notes.captures.append({"t": standin_e2e.now_ms(), "page": 5, "spread": False, "state": "sharp",
                                   "size": [9, 9]})
        assert _until(lambda: stall["until_t"] is not None)
        assert stall["shows_then"] == (5, False, "sharp") and stall["lasted_s"] >= 7.0
        assert len(notes.frame_stalls) == 1
        report = standin_e2e.stalls_report(notes, lambda t: None if t is None else round(t - stall["from_t"]))
        assert report[0]["from"] == 0 and report[0]["drawn"] == [5, False, "sharp"]
        assert report[0]["frozen"] == [4, False, "sharp"] and report[0]["probes"][0]["drawn"] == [5, False, "sharp"]
    finally:
        stop.set()
        thread.join(2)


def test_a_stall_lasts_through_a_turn_to_the_screen_it_stands_still_on_until_the_frames_move(monkeypatch, tmp_path):
    import threading
    import time

    from taslation.capture import wgc

    notes, stop, thread = _frames_watched(monkeypatch, tmp_path, [(-9000, 4)])
    session = SimpleNamespace(seq=10, hwnd=1, ended=False, started=time.monotonic(), error="",
                              _thread=threading.current_thread())
    monkeypatch.setattr(wgc, "_session", session)
    try:
        assert _until(lambda: notes.frame_stalls and notes.frame_stalls[0]["probes"])
        stall = notes.frame_stalls[0]
        assert stall["frames_at_find"] == 10 and stall["probes"][0]["window_session"]["frames"] == 10
        with notes.lock:  # the stand-in turns to the screen the frames stand still on: they have not moved
            notes.drawn_last = {**notes.drawn_last, "page": 4, "t": standin_e2e.now_ms()}
        time.sleep(0.2)
        assert stall["until_t"] is None
        session.seq = 11  # a frame of the session: they move again
        assert _until(lambda: stall["until_t"] is not None)
        assert stall["shows_then"] == (4, False, "sharp")
    finally:
        stop.set()
        thread.join(2)


@pytest.mark.parametrize("captures, capture_n", [
    ([(-9000, 4), (-6900, 5), (-3000, 4)], 5),  # the window saw the page once since it was drawn
    ([(-9000, 4)], 2),  # the window took too few frames since: it was not looking
])
def test_the_frame_watch_finds_no_stall_where_the_window_saw_the_page_or_did_not_look(monkeypatch, tmp_path,
                                                                                     captures, capture_n):
    import time

    notes, stop, thread = _frames_watched(monkeypatch, tmp_path, captures, capture_n=capture_n)
    try:
        time.sleep(0.3)
        assert notes.frame_stalls == [] and not (tmp_path / "stacks.txt").exists()
    finally:
        stop.set()
        thread.join(2)


def test_the_input_watch_notes_spells_of_input_by_the_tick_of_the_last_one(monkeypatch):
    import threading

    ticks = iter([100, 100, 100, 5000, 5000, 6000, 6000, 20000])  # (the first: before the watch's look)
    stop = threading.Event()
    monkeypatch.setattr(standin_e2e, "last_input_tick", lambda: next(ticks, None) or stop.set())
    notes = standin_e2e.Notes(0, 1.0)
    thread = standin_e2e.watch_input(notes, stop, every=0.005)
    thread.join(2)
    assert len(notes.inputs) == 2  # 5000 and 6000 within 3 s of each other, 20000 apart; 100 is no new input
    # (each tick turned into a time by the system's tick count, whose step is about 16 ms: within two steps)
    assert abs(notes.inputs[0][1] - notes.inputs[0][0] - 1000) <= 40 and notes.inputs[1][0] == notes.inputs[1][1]


def test_the_cover_s_plan_is_a_segment_a_start_and_a_length():
    import argparse

    assert standin_e2e.cover_plan("k2:12:30") == ("k2", 12.0, 30.0)
    for bad in ("k2:12", "k2:x:30", "k2:-1:30", "k2:5:0"):
        with pytest.raises(argparse.ArgumentTypeError):
            standin_e2e.cover_plan(bad)


def test_the_app_s_log_is_kept_after_an_incident_unless_it_holds_japanese_script(monkeypatch, tmp_path):
    import re as re_

    state = tmp_path / "state"
    state.mkdir()
    (state / "log.txt").write_text("2026-11-21 12:00:00 INFO taslation: page job 84 done\n", encoding="utf-8")
    assert standin_e2e.keep_app_log(state, tmp_path / "kept") == "kept: log.txt"
    assert (tmp_path / "kept" / "log.txt").read_text(encoding="utf-8").endswith("job 84 done\n")
    assert standin_e2e.JAPANESE_SCRIPT.search(chr(0x3042)) and standin_e2e.JAPANESE_SCRIPT.search(chr(0x6F22))
    assert not standin_e2e.JAPANESE_SCRIPT.search("page job 84 done")
    monkeypatch.setattr(standin_e2e, "JAPANESE_SCRIPT", re_.compile("job 84"))  # (a stand-in for the script)
    assert standin_e2e.keep_app_log(state, tmp_path / "not") == "not kept: it holds Japanese script"
    assert not (tmp_path / "not").exists()
    assert standin_e2e.keep_app_log(tmp_path / "nothing", tmp_path / "none") == "no log"


def _sized(id_, t, page, spread, size, frame="sharp", stored=0, hits=0, misses=0, requests=0, done=None):
    return {"id": id_, "t_s": t, "page": page, "spread": spread, "frame": frame, "size": size, "requests": requests,
            "cache_hits": hits, "cache_misses": misses, "stored": stored, "stored_at_cancel": None, "done_s": done}


def test_a_page_held_at_another_size_only_is_told_with_what_the_cache_gave_and_what_was_asked():
    tall, taller, narrow = [1904, 1024], [1904, 1072], [844, 992]
    jobs = [_sized(1, 0, 4, True, tall, stored=2, done=5),
            _sized(2, 6, 4, True, taller, hits=None, misses=None),  # just after the size changed: given way ...
            _sized(3, 7, 4, True, taller, misses=2, requests=3, stored=2, done=10),  # ... to this one on the same page
            _sized(4, 11, 6, True, taller, stored=1, done=12),  # (one of its two pages stored: not held whole)
            _sized(5, 20, 4, True, taller, hits=2, done=21),  # held at this size since job 3
            _sized(6, 25, 4, False, narrow, hits=1, done=26),  # the narrow window: a page of a spread held
            _sized(7, 30, 5, False, narrow, frame="soft"),
            _sized(8, 31, 5, False, narrow, hits=1, done=32),  # a turn at that size to the spread's other page
            _sized(9, 40, 6, False, narrow, misses=1, requests=1, done=41),  # never held whole: not told
            _sized(10, 45, 4, False, narrow, hits=1, done=46)]  # given by the cache before, still stored elsewhere only
    across = standin_e2e.across_sizes(jobs)
    assert [(r["id"], r["why"], r["layout"], r["held_at"]) for r in across["list"]] == [
        (2, "size change", "same", [tall]), (3, "size change", "same", [tall]),
        (6, "size change", "spread/single", [tall, taller]), (8, "turn back", "spread/single", [tall, taller]),
        (10, "turn back", "spread/single", [tall, taller])]
    assert {k: across[k] for k in ("jobs", "unit_hits", "unit_misses", "requests")} == {
        "jobs": 5, "unit_hits": 3, "unit_misses": 2, "requests": 3}
    assert across["by_why"]["size change"]["requests"] == 3 and across["by_layout"]["spread/single"]["jobs"] == 3
    assert standin_e2e.across_sizes([])["jobs"] == 0


def test_the_looks_for_a_page_as_read_at_other_sizes_are_told_with_their_time():
    looks = [{"t": 100, "job": 1, "ms": 0.2, "readings": None, "replaced": 0},  # (held as found: no reading)
             {"t": 200, "job": 2, "ms": 41.0, "readings": 12, "replaced": 0},  # (held at no size)
             {"t": 300, "job": 3, "ms": 9.5, "readings": 2, "replaced": 2}]
    told = standin_e2e.readings_on_a_miss(looks, lambda t: t / 1000)
    assert (told["looks"], told["with_readings"], told["found"]) == (3, 2, 1)
    assert told["ms"]["max"] == 41.0 and told["ms_when_found"]["n"] == 1 and told["readings"]["min"] == 2
    assert [r["job"] for r in told["list"]] == [2, 3] and told["list"][1]["t_s"] == 0.3


def test_a_long_look_at_the_viewer_is_told_with_each_call_in_it_and_the_requests_under_way(monkeypatch):
    """A look (`STEP_CALLS`) over LONG_STEP_MS is noted with each call made in it timed apart (how often, wall ms,
    the Tk thread's CPU ms), the CPU of the process in it, and the requests under way then; a short one, and a call
    made outside any look, are not."""
    notes = standin_e2e.Notes(0, 1.0)
    clock = [1000.0]
    monkeypatch.setattr(standin_e2e, "now_ms", lambda: clock[0])
    monkeypatch.setattr(standin_e2e, "LONG_STEP_MS", 30)

    def show(self, image):
        time.sleep(0.04)

    def poll(self, draws):
        for _ in range(draws):
            self.show(None)

    class Looker:
        busy = False

    Looker.show = standin_e2e.part_call(notes, "_show_live", show)
    Looker.poll = standin_e2e.step_call(notes, "_poll", poll)
    w = Looker()
    w.show(None)  # (outside a look: nothing noted)
    w.poll(0)  # (a short look: nothing noted)
    assert not notes.long_steps
    w.poll(1)
    assert len(notes.long_steps) == 1 and notes.long_steps[0]["parts"]["_show_live"][0] == 1
    w.poll(2)
    requests = [{"t": 900.0, "end_t": 1500.0, "job": None, "side": "backlog", "why": "history cut"},
                {"t": 1010.0, "end_t": None, "job": 3, "side": None, "why": "extends"},
                {"t": 5000.0, "end_t": 5100.0, "job": 4, "side": None, "why": "extends"}]
    told = standin_e2e.long_steps_report(notes, requests, lambda t: round(t / 1000, 2))
    assert told["count"] == 2 and told["over_ms"] == 30
    first = told["longest"][0]
    assert first["call"] == "_poll" and first["ms"] >= 80 and not first["job_running"]
    assert first["parts"]["_show_live"][0] == 2 and first["parts"]["_show_live"][1] >= 80
    assert {"cpu_ms", "process_cpu_ms"} <= set(first)
    assert first["requests"] == [{"t_s": 0.9, "side": "backlog", "why": "history cut"},
                                 {"t_s": 1.01, "side": "page", "why": "extends"}]


def _shown(t, page, state, kind="translated", lettered=3, from_="soft"):
    return {"t": t, "page": page, "spread": True, "state": state, "kind": kind, "lettered": lettered, "from": from_}


def _read(id_, t, page, from_, boxes, size=(1904, 1024)):
    return {"id": id_, "page": page, "spread": True, "size": list(size), "result_t": t, "result_from": from_,
            "result_boxes": boxes}


def test_lettering_on_a_soft_frame_is_told_with_how_far_its_boxes_lie_from_the_sharp_frames():
    displays = [_shown(0, 2, "sharp", from_="sharp"), _shown(1000, 4, "soft", kind="live", lettered=0, from_=None),
                _shown(1100, 4, "soft"), _shown(1400, 4, "sharp"), _shown(1600, 4, "sharp", from_="sharp")]
    assert standin_e2e.lettered_soft_ms(displays, (4, True), 1000, 3000) == 300  # (from 1100 to the sharp picture)
    assert standin_e2e.lettered_soft_ms(displays, (2, True), 0, 1000) == 0
    gone = [*displays[:3], _shown(1400, 4, "sharp", kind="live", lettered=0, from_=None), displays[4]]
    assert standin_e2e.lettering_gone_ms(gone, (4, True), 1000, 3000) == 200  # (the sharp picture before its reading)
    assert standin_e2e.lettering_gone_ms(displays, (4, True), 1000, 3000) == 0  # (lettered throughout)
    assert standin_e2e.lettering_gone_ms(gone[:4], (4, True), 1000, 3000) == 0  # (never came back: not "gone")
    jobs = [_read(1, 1100, 4, "soft", [[60, 10, 90, 40], [10, 10, 50, 40]]),
            _read(2, 1500, 4, "sharp", [[12, 9, 51, 40], [61, 10, 90, 43]], size=(1904, 1072)),  # (another size)
            _read(3, 1600, 4, "sharp", [[11, 10, 50, 41], [100, 5, 130, 30], [60, 12, 90, 40]]),
            _read(4, 2000, 6, "soft", [[5, 5, 20, 20]]), _read(5, 2400, 6, "sharp", [[30, 5, 40, 20]]),
            _read(6, 2600, 8, "soft", [[5, 5, 20, 20]])]
    told = standin_e2e.soft_lettering(jobs)
    assert [(r["job"], r["sharp_job"], r["shifts_px"], r["shift_px"]) for r in told["list"]] == [
        (1, 3, [2, 1], 2), (4, 5, [], None), (6, None, [], None)]  # (by overlap; none; no sharp job after it)
    assert (told["jobs"], told["boxes"], told["sharp_boxes"], told["unmatched"]) == (3, 4, 4, 2)
    assert told["shift_px"]["max"] == 2 and told["box_shift_px"]["n"] == 2


def _turn(page, soft_t, sharp_after=700, late=200):
    """A turn of the stand-in to the spread *page*: drawn soft at *soft_t*, sharp *sharp_after* ms later (None: never),
    and the window's captures of both, the sharp one *late* ms after the stand-in drew it."""
    sharp_t = soft_t + sharp_after if sharp_after is not None else None
    captures = [{"t": soft_t + 50, "page": page, "spread": True, "state": "soft"}]
    if sharp_t is not None:
        captures.append({"t": sharp_t + late, "page": page, "spread": True, "state": "sharp"})
    return {"screen": (page, True), "soft_t": soft_t, "sharp_t": sharp_t, "next_t": soft_t + 4000}, captures


def _ended(id_, t, page, frame="soft", gate=True, end="confirmed", final="confirmed", ever=True, over=600,
           open_for=0.0, units=(), lines=()):
    """A page job as the notes have it at the end (`Notes.gates_at_end`): its gate as it ended and as the run left it,
    whether it was ever confirmed, its end (*over* ms after its start), its open time and what it stored."""
    over_t = t + over
    return {"id": id_, "t": t, "page": page, "spread": True, "state": frame, "started": True, "gate": gate,
            "gate_end": end if gate else None, "gate_final": final if gate else None, "confirmed_ever": ever,
            "over_t": over_t, "open_for": open_for, "open_until_t": over_t + open_for * 1000 if ever else None,
            "units": list(units), "line_ids": list(lines)}


def test_a_soft_frames_job_is_judged_by_what_its_gate_and_the_cache_hold_at_the_end():
    plan = [_turn(2, 0), _turn(4, 4000), _turn(6, 8000), _turn(8, 12000), _turn(10, 16000, sharp_after=2600, late=100),
            _turn(12, 20000, sharp_after=None), _turn(14, 24000), _turn(16, 28000), _turn(18, 32000),
            _turn(20, 36000)]
    turns = [turn for turn, _ in plan]
    captures = [c for _, caps in plan for c in caps]
    jobs = [
        _ended(1, 100, 2, end="dropped", final="dropped", units=["u1"], lines=["l1"]),  # taken back while it ran
        _ended(2, 950, 2, frame="sharp", units=["u2"]),
        _ended(3, 4100, 4, final="dropped", open_for=2.0, units=["u3"]),  # ... after it: kept for now, then put back
        _ended(4, 4950, 4, frame="sharp", units=["u4"]),
        _ended(5, 8100, 6, units=["u5"], lines=["l5"]),  # kept for good as it ended: no open time
        _ended(6, 12100, 8, open_for=2.0, units=["u6"]),  # kept for now, decided for good by the next job
        _ended(7, 16100, 10, open_for=2.0, units=["u7"]),  # its sharp frame after its open time
        _ended(8, 20100, 12, units=["u8"]),  # no sharp frame came
        _ended(9, 24100, 14, units=["u9"], lines=["l9"]),  # its unit and line in the cache: stored anew by job 10 ...
        _ended(10, 24950, 14, frame="sharp", units=["u9"], lines=["l9"]),  # ... which it would not be, had they stayed
        _ended(11, 28100, 16, gate=False, ever=False, units=["u11"]),  # settled on a soft frame: not started early
        _ended(12, 32100, 18, end="dropped", final="dropped", ever=False, units=["u12"]),  # dropped, and yet
        _ended(13, 36100, 20, over=1500, units=["u13"]),  # its sharp frame came while it ran: not taken back
        _ended(14, 36200, 20, frame="black", gate=False, ever=False)]
    decides = [{"t": 12800, "job": 6, "kept": True, "by": None}, {"t": 4900, "job": 3, "kept": False, "by": 4}]
    cache = {"units": {"u2", "u4", "u5", "u6", "u7", "u8", "u9", "u11", "u12", "u13"}, "lines": {"l5", "l9"}}
    told = standin_e2e.soft_frames_at_end(jobs, turns, captures, decides, cache, lambda t: t / 1000)
    assert told["confirmed"] == 8  # (on a soft frame, confirmed at any time)
    assert told["taken_back"] == {"while_running": 1, "after_the_job": 1}
    assert [(r["id"], r["page"], r["why"], r["units_left"], r["lines_left"], r["sharp_captured_late_ms"])
            for r in told["left"]] == [
        (5, 6, "viewer not yet seen drawing soft first", 1, 1, 200), (6, 8, "decided by another job", 1, 0, 200),
        (7, 10, "later than the open time", 1, 0, 100), (8, 12, "no sharp frame", 1, 0, None),
        (11, 16, "no gate", 1, 0, 200), (12, 18, "put back, yet left", 1, 0, 200),
        (13, 20, "sharp frame not taken back", 1, 0, 200)]
    assert (told["left_in_the_cache"], told["left_though_the_sharp_frame_came"], told["cache"]) == (7, 6, "read")
    assert told["left"][0]["t_s"] == 8.1
    # nothing left once every soft frame's job was put back: the must-be-none number at 0
    clean = standin_e2e.soft_frames_at_end(jobs, turns, captures, decides, {"units": {"u2", "u4", "u9"},
                                                                            "lines": {"l9"}}, lambda t: t)
    assert (clean["left_in_the_cache"], clean["left_though_the_sharp_frame_came"], clean["left"]) == (0, 0, [])
    unread = standin_e2e.soft_frames_at_end(jobs, turns, captures, decides, {"error": "OSError"}, lambda t: t)
    assert (unread["confirmed"], unread["left_in_the_cache"], unread["cache"]) == (8, None, "OSError")


def test_a_decision_at_the_end_of_the_open_time_is_its_time_being_up():
    job = _ended(1, 0, 4, open_for=2.0)  # (over at 600, open until 2600)
    near = {"t": 2590, "job": 1, "kept": True, "by": None}
    assert standin_e2e.left_why(job, 2700, near) == "later than the open time"
    assert standin_e2e.left_why(job, 2700, {**near, "t": 900}) == "decided by another job"
    assert standin_e2e.left_why(job, 2500, None) == "sharp frame not taken back"  # (within its open time)
    assert standin_e2e.left_why(job, 500, None) == "sharp frame not taken back"  # (while it ran)


def test_the_notes_keep_a_jobs_gate_units_lines_and_decision_for_the_end():
    from taslation.pipeline import PageGate

    notes = standin_e2e.Notes(31, 1.0)
    gate = PageGate(open_for=2.0)
    job = notes.new_job(None)
    notes.job_started(job, None, True, gate)
    assert notes.take_job(None, gate) is job
    result = {"result": SimpleNamespace(translated=[], original=None, cache_hits=0, cache_misses=2),
              "stored": [("f1", 1.0), ("f2", 0.7)]}
    cancelled = {"discarded": False, "stored": [("f2", 0.7), ("f3", 1.0)]}
    for kind, data in (("result", result), ("page_cancelled", cancelled)):
        notes.tag((kind, data))
        notes.app_event(None, kind, data)
    notes.line_put("l1")
    assert gate.confirm()
    notes.job_over(job)
    notes.line_put("l2")  # (no job running: nobody's)
    assert gate.take_back()  # the sharper frame came after the job: the page kept for now put back
    notes.decided(gate, False)
    other, dropped = notes.new_job(None), PageGate()  # (a frame that changed before its confirmation)
    notes.job_started(other, None, True, dropped)
    notes.take_job(None, dropped)
    dropped.drop()
    notes.job_over(other)
    notes.gates_at_end()
    assert job["units"] == ["f1", "f2", "f3"] and job["line_ids"] == ["l1"] and other["line_ids"] == []
    assert (job["gate_end"], job["gate_final"], job["confirmed_ever"], job["open_for"]) == (
        "confirmed", "dropped", True, 2.0)
    assert 1900 < job["open_until_t"] - job["over_t"] <= 2000
    assert (other["gate_end"], other["gate_final"], other["confirmed_ever"], other["open_until_t"]) == (
        "dropped", "dropped", False, None)
    assert notes.decides == [{"t": notes.decides[0]["t"], "job": job["id"], "kept": False, "by": None}]
    assert "gate_obj" not in job and "gate_obj" not in other


def test_the_cache_at_the_end_is_read_by_its_page_units_and_its_kept_lines(tmp_path):
    from taslation.cache import CachedBubble, CachedPage, CacheStore
    from taslation.config import Settings
    from taslation.fingerprint import FINGERPRINT_HEX_LEN

    settings = Settings(state_dir=tmp_path)
    book = CacheStore(settings.cache_dir).open(standin_e2e.BOOK, standin_e2e.PLAMO, "English")
    fingerprint = ("5a" * FINGERPRINT_HEX_LEN)[:FINGERPRINT_HEX_LEN]
    book.add(CachedPage(fingerprint, 1.0, [CachedBubble((0.1, 0.1, 0.3, 0.3), "Line 1.")]))
    book.lines.put("scope", "key", "Line 1.")
    book.save()
    ring = book.lines.rings[0]
    line = standin_e2e.line_id(ring.secret, "scope", ring.digest("key"))
    assert standin_e2e.cache_at_end(settings) == {"units": {fingerprint}, "lines": {line}}
    assert re.fullmatch(r"[0-9a-f]{32}", line) and line != standin_e2e.line_id(ring.secret, "scope2",
                                                                               ring.digest("key"))
    assert standin_e2e.cache_at_end(SimpleNamespace(cache_dir=None)) == {"error": "TypeError"}


def progress_line(progress, reading=False):  # (as the window's progress line is named where it says it)
    return str(progress)


def test_a_status_line_is_told_by_its_kind_and_the_page_it_speaks_of_never_by_its_text():
    from taslation.messages import Message
    from taslation.regions import PageResult

    result = PageResult(image=Image.new("RGB", (4, 4)), original=Image.new("RGB", (4, 4)), regions=[])
    window = SimpleNamespace(_page_line=lambda r: "3 line(s)", _font_note=lambda: "")
    summary = lambda: window._page_line(result) + window._font_note()  # noqa: E731 - as the window says it
    progress, reading = Message("ollama.loading"), False
    assert standin_e2e.status_kind(summary, None) == ("page_summary", "result", result)
    assert standin_e2e.status_kind(lambda: progress_line(progress, reading), None)[:2] == ("progress", "job")
    key = "Stopped: this page was not translated, and nothing of it was kept. F5 translates it again."
    assert standin_e2e.status_kind(lambda: key, key)[:2] == ("say:Stopped_this_page_was", "job")
    assert standin_e2e.status_kind(lambda: "Viewer: x", "Viewer: {title}")[:2] == ("say:Viewer_title", None)
    message = Message("ollama.loading")
    assert standin_e2e.status_kind(lambda: str(message), None)[:2] == ("message:ollama.loading", None)
    assert standin_e2e.status_kind(None, None)[:2] == ("other", None)


def test_how_long_a_status_line_of_the_page_before_stays_after_a_turn():
    lines = [{"t": 0, "kind": "page_summary", "page": [2, True]}, {"t": 1150, "kind": "progress", "page": [2, True]},
             {"t": 1300, "kind": "say:Viewer_title", "page": None}, {"t": 1500, "kind": "progress", "page": [4, True]},
             {"t": 2600, "kind": "progress", "page": [2, True]}, {"t": 2700, "kind": "page_summary", "page": [4, True]}]
    # the turn to 4 at 1000: the summary of 2, then 2's progress, until a line of no page at 1300; 2's line again later
    assert standin_e2e.status_of_another_page(lines, (4, True), 1000, 3000) == (300, "page_summary", 400)
    assert standin_e2e.status_of_another_page(lines, (2, True), 100, 1000) == (0, None, 0)
    assert standin_e2e.status_of_another_page([], (2, True), 100, 1000) == (0, None, 0)


# ---------------------------------------------------------------------------------------------------- the files
def test_the_page_fetches_nothing_from_anywhere():
    html = sv.HTML.read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html
    assert not re.search(r"""(src|href)\s*=\s*["'](?!#)""", html), "no resource named in the markup"
    assert "fetch(" not in html and "XMLHttpRequest" not in html and "WebSocket" not in html


def test_page_list_and_control_only_in_the_scratch_folder(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    picture = tmp_path / "pictures" / "000.jpg"
    picture.parent.mkdir()
    picture.write_bytes(b"not read")
    before = {p for p in tmp_path.rglob("*")}
    listed = sv.write_page_list(scratch, [picture, (picture, "h")])
    control = sv.write_control(scratch, 3, band=54)
    made = {p for p in tmp_path.rglob("*")} - before
    assert made == {listed, control} and listed.parent == scratch.resolve() and control.parent == scratch.resolve()
    text = listed.read_text(encoding="utf-8")
    assert text.startswith("standinPages(") and sv.file_url(picture) in text and '"flip": "h"' in text
    assert control.read_text(encoding="utf-8") == 'standinControl({"go": 3, "band": 54});\n'
    assert picture.read_bytes() == b"not read"  # (named, never copied)
    with pytest.raises(ValueError):
        sv._inside(scratch, "../elsewhere.js")
    url = sv.page_url("t1234", sv.parse_script("g1,n,e"), scratch)
    assert url.startswith(sv.file_url(sv.HTML) + "?") and url.endswith("#s=g1,n,e")
    assert "http" not in url.split("#")[0].replace(sv.file_url(sv.HTML), "")


def test_the_console_line_is_read_and_others_are_not():
    line = '[1:2:1117/120000.1:INFO:CONSOLE:66] "STANDIN ev=draw t=1700000000123.4 step=3 page=4 spread=1 ' \
           'state=soft why=next wait=2", source: file:///x/standin.html (66)'
    said = sv.parse_line(line)
    assert said == {"ev": "draw", "t": "1700000000123.4", "step": "3", "page": "4", "spread": "1", "state": "soft",
                    "why": "next", "wait": "2"}
    assert sv.parse_line("[1:2:INFO:CONSOLE:1] \"something else\"") is None
    assert sv.parse_line('"STANDIN no event here"') is None


def test_the_browser_command_keeps_its_own_profile_and_window():
    cmd = sv.browser_command(Path("C:/b/chrome.exe"), "file:///p.html?token=t1", Path("C:/scratch/profile"),
                             (0, 0, 1300, 900))
    assert cmd[0].endswith("chrome.exe") and cmd[-1] == "--app=file:///p.html?token=t1"
    assert any(a.startswith("--user-data-dir=") and a.endswith("profile") for a in cmd)
    for flag in ("--no-first-run", "--disable-sync", "--disable-background-networking", "--window-size=1300,900"):
        assert flag in cmd
    assert not any(a.startswith("--force-device-scale-factor") for a in cmd)
    scaled = sv.browser_command(Path("C:/b/chrome.exe"), "file:///p.html", Path("C:/scratch/profile"),
                                (0, 0, 1300, 900), 1.5)
    assert "--force-device-scale-factor=1.5" in scaled and scaled[-1] == "--app=file:///p.html"
    assert not any("occlu" in a.lower() for a in cmd)  # (by default it stops drawing under windows, as a browser does)
    covered = sv.browser_command(Path("C:/b/chrome.exe"), "file:///p.html", Path("C:/scratch/profile"),
                                 (0, 0, 1300, 900), draws_covered=True)
    features = [a for a in covered if a.startswith("--disable-features=")]
    assert len(features) == 1 and features[0].endswith(",CalculateNativeWinOcclusion")  # (one list: the last would win)
    assert "--disable-backgrounding-occluded-windows" in covered and covered[-1] == "--app=file:///p.html"


def test_the_browser_never_offers_to_translate_the_page(tmp_path):
    import json

    html = sv.HTML.read_text(encoding="utf-8")
    assert '<html lang="en" translate="no">' in html and '<meta name="google" content="notranslate">' in html
    profile = sv.make_profile(tmp_path / "profile")
    assert json.loads((profile / "Default" / "Preferences").read_text(encoding="utf-8")) == {
        "translate": {"enabled": False}}
    assert sorted(p.name for p in profile.rglob("*")) == ["Default", "Preferences"]  # (nothing else written)
    with pytest.raises(FileExistsError):
        sv.make_profile(profile)  # (a profile is always a new one)


# ---------------------------------------------------------------------------------------------------- the window
def test_the_window_is_found_in_the_tree_started_and_by_its_token():
    windows = [(11, 500), (12, 600), (13, 601), (14, 700)]  # (window, process)
    titles = {11: "Something t9f2c0 of the owner", 12: "Stand-in reader t9f2c0", 13: "Stand-in reader",
              14: "Stand-in reader t9f2c0"}
    asked: list[int] = []

    def title(hwnd: int) -> str:
        asked.append(hwnd)
        return titles[hwnd]

    tree = sv.process_tree(600, [(600, 1), (601, 600), (602, 601), (700, 2), (500, 3)])
    assert tree == {600, 601, 602}
    assert sv.find_window(tree, "t9f2c0", windows, title) == 12
    assert set(asked) == {12, 13}, "no title of a window outside the tree is read"
    asked.clear()
    assert sv.find_window(tree, "t0000", windows, title) is None  # the token missing
    assert sv.find_window({700}, "t9f2c0", [(14, 700), (15, 700)], lambda h: "Stand-in reader t9f2c0") is None
    assert sv.find_window(tree, "t9f2", windows, title) is None  # a token is a word of its own
    assert sv.find_window(tree, "", windows, title) is None
    asked.clear()
    assert sv.find_window({999}, "t9f2c0", windows, title) is None and not asked


def test_the_guard_stops_on_any_other_window_and_stays_stopped():
    guard = sv.SelectionGuard(12)
    assert guard.check(None) == ""
    assert guard.check(SimpleNamespace(hwnd=12)) == ""
    why = guard.check(SimpleNamespace(hwnd=14))
    assert why and "not the stand-in" in why
    assert "Stand-in reader" not in why  # (no title is said)
    assert guard.check(SimpleNamespace(hwnd=12)) == why  # stopped for good
    assert sv.SelectionGuard(12).check(SimpleNamespace()) != ""  # a choice that names no window


# ---------------------------------------------------------------------------------------------------- the frames
def frame(page: int, spread: bool, soft: bool = False, spinner: bool = False, top: int = 31,
          size: tuple[int, int] = (900, 700)) -> Image.Image:
    """A frame as the browser draws the page: its title bar, the band with the code's cells, a light page."""
    image = Image.new("RGB", size, (43, 43, 43))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size[0], top - 1), fill=(32, 33, 36))
    draw.rectangle((0, top, size[0], top + 53), fill=(58, 61, 65))
    draw.rectangle((150, top + 80, size[0] - 150, size[1] - 40), fill=(240, 240, 240))
    for k, bit in enumerate(sv.cells_of(page, spread, soft, spinner)):
        x, y = sv.CODE_X + k * sv.CELL, top + sv.CODE_Y
        draw.rectangle((x, y, x + sv.CELL - 1, y + sv.CELL - 1), fill=(255, 255, 255) if bit else (0, 0, 0))
    return image


@pytest.mark.parametrize("page,spread,soft,spinner", [(0, True, False, False), (46, True, True, False),
                                                     (53, False, False, True), (511, False, True, True)])
def test_the_band_code_reads_back(page, spread, soft, spinner):
    shown = sv.decode(frame(page, spread, soft, spinner), 31)
    assert shown.known and (shown.page, shown.spread, shown.soft, shown.spinner) == (page, spread, soft, spinner)
    assert shown.state() == ("spinner" if spinner else "soft" if soft else "sharp")


def test_a_black_frame_and_a_frame_without_code():
    assert sv.decode(Image.new("RGB", (900, 700), (0, 0, 0)), 31).state() == "black"
    plain = Image.new("RGB", (900, 700), (200, 200, 200))
    assert sv.decode(plain, 31).state() == "unknown" and sv.decode(plain, 31).screen is None
    broken = frame(8, True)
    ImageDraw.Draw(broken).rectangle((sv.CODE_X + 6 * sv.CELL, 31 + sv.CODE_Y, sv.CODE_X + 7 * sv.CELL - 1,
                                      31 + sv.CODE_Y + sv.CELL - 1), fill=(255, 255, 255))
    assert sv.decode(broken, 31).known is False  # one cell wrong: the check says so
    assert sv.decode(None, 31).state() == "unknown"


def test_the_view_is_the_one_the_stand_in_says_once_its_window_is_in_place():
    """A browser at another scale starts its window at the size given in its own pixels: the view the tool reads the
    capture by is the size the page said last once the window is in place, else the one it was ready with."""
    ready = {"ev": "ready", "w": "2856", "h": "1446", "vw": "1904", "vh": "964", "dpr": "1.5", "count": "70"}
    events = [(0.0, ready), (0.1, {"ev": "draw", "state": "sharp"})]
    browser = SimpleNamespace(said=lambda since=0: events[since:])
    assert standin_e2e.placed_view(browser, ready, len(events), seconds=0.3, quiet=0.1) == ready  # (no change)
    events.append((0.2, {"ev": "size", "w": "2847", "h": "1485", "vw": "1898", "vh": "990", "dpr": "1.5"}))
    view = standin_e2e.placed_view(browser, ready, 2, seconds=0.5, quiet=0.1)
    assert view["vh"] == "990" and view["w"] == "2847" and view["count"] == "70" and view["ev"] == "ready"



# ---------------------------------------------------------------------------------------------------- the indicator
@pytest.mark.parametrize("setting", ["column", "rail"])
def test_the_indicator_is_looked_at_as_told_and_a_wrong_one_is_found(setting, hidden_root, no_way_to_the_viewer):
    """`SideCheck` on the indicator's own window (`test_side_indicator.Window`) fed by the real backlog: what it was
    told agrees with what it holds and draws, a screen that went by is drawn as such, the screen on show outlined; a
    stage the model holds that was never told is found, and so is a drop that left anything."""
    from fake_side import fingerprint, page

    from taslation.backlog import backlog_of

    w = Window(hidden_root, setting=setting, size=(1560, 900))
    hidden_root.update()
    errors: list = []
    check = standin_e2e.SideCheck(SimpleNamespace(error=lambda *a: errors.append(a)))
    handle = w._handle_event

    def handled(kind, data):  # (as the tool's hook on `App._handle_event`, the later look made at once below)
        reading = kind in ("page_on_show", "backlog") or (kind == "page_stage" and data.get("reading"))
        if reading:
            check.told_event(w, kind, data)
        out = handle(kind, data)
        if reading and kind == "backlog" and data.get("dropped") is True:
            check.drop_looked(w)
        return out

    w._handle_event = handled
    b = backlog_of(w)

    def unit(n):
        return SimpleNamespace(fingerprint=fingerprint(n), aspect=0.7)

    try:
        s1 = b.screen_for([unit(1)], 4)
        w.show(page(1))
        b.tell(s1, "read", "done", page(1))
        b.tell(s1, "translate", "working", page(1))
        b.show(s1)
        b.totals()
        gone = b.screen_for([unit(2)], 4)  # went by too fast
        gone.missed = True
        b.tell(gone, "read", "missed")
        s3 = b.screen_for([unit(3)], 4)
        w.show(page(3))
        b.tell(s3, "read", "working", page(3))
        b.show(s3)
        b.totals()
        w.pump()
        check.check(w)
        assert errors == [] and check.checks == 1
        assert check.wrong == {}, check.examples
        assert check.on_show_drawn == check.on_show_checked == 1
        assert check.missed_told == check.missed_drawn == {(2, fingerprint(2))}
        assert check.layouts == {setting: 1}
        w._side.model.screens[1].stages["translate"] = "failed"  # (never told: the model and its drawing are wrong)
        check.check(w)
        assert check.wrong["stages"] == 1
        assert check.wrong["bar" if setting == "column" else "rail_mark"] >= 1
        b.drop("another book")
        w.pump()
        assert len(check.drops) == 1 and "drop_not_cleared" not in check.wrong
        assert check.drops[0]["screens_left"] == 0 and check.drops[0]["drawn_left"] == 0
    finally:
        b.close()
        w.destroy()
