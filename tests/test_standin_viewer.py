"""The browser-type stand-in viewer (tools/standin_viewer) and its driver's plan (tools/standin_e2e.py), with no
browser, no GPU and no Ollama: the script's format, the page with nothing to fetch from anywhere, its files written
in the scratch folder alone, the window found only in the tree the tool started with its token, the guard on the
window TASlation chose, and the band's code read back from a frame."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import standin_e2e  # noqa: E402
import standin_viewer as sv  # noqa: E402


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
    assert names == ["c", "a", "b", "d", "e", "r", "t", "t2", "o", "z", "w", "w2", "x", "f", "f2"]
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
    assert turns["w2"][:2] == [(70, True), (68, True)]  # back to pages of the run, which read 64 to 72
    # x: the screens of little text added after the others, soft long and half as sharp, then back where it was
    assert turns["x"] == [(count, True), (count + 2, True), (count + 4, True), (76, True)]
    assert f"t700,b2,j{count},w5000," in text and ",t,b,j76,w4000," in text
    assert turns["f2"] == [(81, False), (82, False)]  # single pages once the window is narrow
    assert standin_e2e.wanted("f,a") == ["a", "f", "f2"]
    assert standin_e2e.wanted("f2") == ["f2"]  # the narrow window alone
    assert standin_e2e.wanted("w2") == standin_e2e.wanted("w") == ["w", "w2"]  # a run and the reading beside it
    assert standin_e2e.wanted("t2") == standin_e2e.wanted("t") == ["t", "t2"]  # the key forward, then back
    with pytest.raises(SystemExit):
        standin_e2e.wanted("a,q")


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


def test_a_turn_is_told_with_what_a_whole_book_run_did_then():
    modes = [{"t": 0, "run": False, "beside": False}, {"t": 100, "run": True, "beside": False},
             {"t": 500, "run": True, "beside": True}, {"t": 900, "run": False, "beside": False}]
    assert [standin_e2e.run_state(modes, t) for t in (50, 100, 499, 700, 950)] == [
        "no run", "run reading", "run reading", "run translating", "no run"]
    assert standin_e2e.run_state([], 10) == "no run"


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

