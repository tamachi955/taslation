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
    assert names == ["c", "a", "b", "d", "e", "r", "o", "z", "w", "w2", "x", "f", "f2"]
    count = standin_e2e.pages_needed(names)
    segments, steps = standin_e2e.build_plan(names, count + 6, cancel_first=count, soft_ms=700)
    text = sv.format_script(steps)
    for s in segments:
        assert f"g{s.go},m{s.go}," in text
    assert text.endswith(",e")
    turns = {s.name: s.screens for s in segments}
    assert turns["c"] == [(2, True), (4, True), (6, True)]
    assert turns["e"][:3] == [(48, True), (46, True), (44, True)]  # turning back
    assert turns["w2"][:2] == [(70, True), (68, True)]  # back to pages of the run, which read 64 to 72
    # x: the screens of little text added after the others, soft long and half as sharp, then back where it was
    assert turns["x"] == [(count, True), (count + 2, True), (count + 4, True), (76, True)]
    assert f"t700,b2,j{count},w5000," in text and ",t,b,j76,w4000," in text
    assert turns["f2"] == [(81, False), (82, False)]  # single pages once the window is narrow
    assert standin_e2e.wanted("f,a") == ["a", "f", "f2"]
    assert standin_e2e.wanted("f2") == ["f2"]  # the narrow window alone
    assert standin_e2e.wanted("w2") == standin_e2e.wanted("w") == ["w", "w2"]  # a run and the reading beside it
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

