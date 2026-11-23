"""The stand-in viewer's behaviour profiles (``profile=dark|light`` in tools/standin_viewer/standin.html), with no
browser: the page's pure logic (the block between PROFILE LOGIC BEGIN and END, run in node when node is here), the
URL the Python side builds for a profile and its parts, the script's new steps, and the e2e tool's plan for a
stand-in with a profile (scenario q, the cover alone)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import standin_e2e  # noqa: E402
import standin_selfcheck  # noqa: E402
import standin_viewer as sv  # noqa: E402

HTML = (ROOT / "tools" / "standin_viewer" / "standin.html").read_text(encoding="utf-8")
NODE = shutil.which("node")


def logic() -> str:
    m = re.search(r"/\* PROFILE LOGIC BEGIN.*?\*/(.*?)/\* PROFILE LOGIC END \*/", HTML, re.S)
    assert m, "the page has its block of profile logic"
    return m.group(1)


def run_logic(tmp_path: Path, body: str) -> dict:
    """What *body* (JavaScript that sets ``out``) gives after the page's block of profile logic, run in node."""
    if NODE is None:
        pytest.skip("node is not on this computer")
    script = tmp_path / "logic.js"
    script.write_text('"use strict";\n' + logic() + "\nconst out = {};\n" + body +
                      "\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------------------------------- the page's logic
def test_the_block_draws_nothing_and_touches_no_page():
    block = logic()
    assert not re.search(r"\b(document|window|view|g|lg|say|setTimeout|requestAnimationFrame|fetch|location)\b\s*[.(]",
                         block)


def test_the_python_side_knows_every_part_the_page_has():
    names = re.findall(r"(\w+):", re.search(r"dark: \{(.*?)\},", logic(), re.S).group(1))
    assert tuple(names) == sv.PROFILE_OPTIONS
    light = re.findall(r"(\w+):", re.search(r"light: \{(.*?)\},", logic(), re.S).group(1))
    assert tuple(light) == sv.PROFILE_OPTIONS


def test_screens_with_the_cover_alone(tmp_path):
    out = run_logic(tmp_path, """
      out.cover = [...Array(10).keys()].map(n => screenOf(n, 10, true, 1));
      out.plain = [...Array(6).keys()].map(n => screenOf(n, 6, true, 0));
      out.single = [...Array(4).keys()].map(n => screenOf(n, 4, false, 1));
      out.pages = [0, 1, 3, 9].map(f => screenPagesOf(f, 10, true, 1));
      let f = 0; out.forward = [f]; for (let k = 0; k < 6; k++) { f = nextScreen(f, 10, true, 1); out.forward.push(f); }
      out.back = [9, 7, 1, 0].map(f => previousScreen(f, 10, true, 1));
      out.allowed = [0, 3, 9].map(f => arrowsAllowed(f, 10, true, 1));
    """)
    assert out["cover"] == [0, 1, 1, 3, 3, 5, 5, 7, 7, 9]
    assert out["plain"] == [0, 0, 2, 2, 4, 4]
    assert out["single"] == [0, 1, 2, 3]
    assert out["pages"] == [[0], [1, 2], [3, 4], [9]]  # the cover alone, a last page alone
    assert out["forward"] == [0, 1, 3, 5, 7, 9, 9]
    assert out["back"] == [7, 5, 0, 0]
    # right to left: the left arrow goes on (none on the last screen), the right one back (none on the first)
    assert out["allowed"] == [{"left": True, "right": False}, {"left": True, "right": True},
                              {"left": False, "right": True}]


def test_the_page_is_fitted_to_the_height_as_measured(tmp_path):
    out = run_logic(tmp_path, """
      const page = [667, 946];  // a page about 0.705 wide per high, as the recordings' pages
      out.window = fitRects([page, page], { x: 0, y: 54, w: 1918, h: 946 });
      out.full = fitRects([page, page], { x: 0, y: 0, w: 1920, h: 1080 });
      out.cover = fitRects([page], { x: 0, y: 54, w: 1918, h: 946 });
      out.narrow = fitRects([page, page], { x: 0, y: 54, w: 900, h: 946 });
    """)
    w = out["window"]
    assert w[0]["x"] > w[1]["x"]  # the first page on the right (a book read right to left)
    assert w[0]["h"] == w[1]["h"] == 946 and w[0]["y"] == 54
    width = w[0]["x"] + w[0]["w"] - w[1]["x"]
    assert abs(width - 1332) <= 4 and abs(w[1]["x"] - 294) <= 3  # the spread about 1332, about 294 each side
    assert abs(1918 - (w[0]["x"] + w[0]["w"]) - w[1]["x"]) <= 1
    f = out["full"]
    width = f[0]["x"] + f[0]["w"] - f[1]["x"]
    assert f[0]["h"] == 1080 and abs(width - 1524) <= 4 and abs(f[1]["x"] - 198) <= 3
    c = out["cover"][0]
    assert c["h"] == 946 and abs(c["x"] - (1918 - c["x"] - c["w"])) <= 1  # single and centred
    n = out["narrow"]
    assert n[1]["x"] == 0 and n[0]["x"] + n[0]["w"] == 900 and n[0]["h"] < 946  # narrower than the spread: its width


def test_where_a_click_or_the_pointer_is(tmp_path):
    out = run_logic(tmp_path, """
      out.thirds = [99, 100, 150, 250, 301, 400, 401].map(x => thirdOf(x, 100, 400));
      const area = { x: 0, y: 54, w: 1918, h: 946 };
      out.edge = [53, 54, 147, 148, 500, 943, 944, 1000].map(y => inEdge(y, area, 94, 56));
      out.tabs = arrowRects(area, "edge", 0, 1);
      out.inset = arrowRects(area, "inset", 180, 1);
      out.none = arrowRects(area, "none", 0, 1);
      out.in = [inside(out.tabs.left, 0, 520), inside(out.tabs.left, 32, 520), inside(null, 1, 1)];
    """)
    assert out["thirds"] == [None, "left", "left", "middle", "right", "right", None]
    assert out["edge"] == [False, True, True, False, False, False, True, True]
    tabs = out["tabs"]
    assert tabs["left"] == {"x": 0, "y": 54 + (946 - 70) // 2, "w": 32, "h": 70}
    assert tabs["right"]["x"] == 1918 - 32 and tabs["right"]["y"] == tabs["left"]["y"]
    inset = out["inset"]
    assert inset["left"]["x"] == 180 and inset["left"]["w"] == 30
    assert inset["right"]["x"] + inset["right"]["w"] == 1918 - 180
    assert out["none"] is None
    assert out["in"] == [True, False, False]


def test_the_profiles_parts_and_what_is_made_of_a_wrong_value(tmp_path):
    out = run_logic(tmp_path, """
      const none = () => null;
      out.dark = profileOptions("dark", none);
      out.light = profileOptions("light", none);
      out.nothing = profileOptions("", none);
      out.other = profileOptions("sepia", none);
      const given = { bars: "click", jump_ms: "700-300", jump_half: "5", ground: "pink", arrow_inset: "x",
                      bar_hide_ms: "250", resize_ms: "450" };
      out.switched = profileOptions("dark", k => (k in given ? given[k] : null));
      out.move = profileOptions("dark", k => (k === "bars" ? "move" : null));
    """)
    dark, light = out["dark"], out["light"]
    assert dark["ground"] == "black" and light["ground"] == "white"
    assert dark["bars"] == "edge" and light["bars"] == "move"
    assert dark["bar_hide_ms"] == 1000 and light["bar_hide_ms"] == 3000  # empty: by the bars' way
    assert dark["jump"] == "spinner" and dark["jump_ms"] == [500, 1100] and dark["resize_ms"] == [400, 500]
    assert light["jump"] == "plain" and light["preview"] == 1 and light["preview_ms"] == 200
    assert light["resize"] == "plain" and light["arrows"] == "inset" and light["arrow_show"] == "always"
    assert dark["page_clicks"] == 0 and dark["ground_clicks"] == 1 and dark["bar_key_hide"] == 1
    assert dark["focus_black"] == 0 == light["focus_black"] and dark["cover"] == 1 == light["cover"]
    assert out["nothing"] is None and out["other"] is None
    s = out["switched"]
    assert s["bars"] == "click" and s["jump_ms"] == [300, 700] and s["jump_half"] == 1
    assert s["ground"] == "black" and s["arrow_inset"] == 0  # a word not known, a number not one: its own
    assert s["bar_hide_ms"] == 250 and s["resize_ms"] == [450, 450]
    assert out["move"]["bar_hide_ms"] == 3000


# ---------------------------------------------------------------------------------------------------- the URL
def test_a_url_without_a_profile_is_what_it_always_was(tmp_path):
    url = sv.page_url("tok", sv.parse_script("n,w100"), tmp_path)
    query = parse_qs(urlparse(url).query)
    assert set(query) == {"token", "pages", "control", "seed", "band", "soft_min", "soft_max", "factor", "flash_ms",
                          "layout"}
    assert "soft_first" in parse_qs(urlparse(sv.page_url("tok", [], tmp_path, soft_first=False)).query)
    assert sv.page_url("tok", [], tmp_path, soft_first=True) == sv.page_url("tok", [], tmp_path)


def test_a_profile_and_its_parts_in_the_url(tmp_path):
    url = sv.page_url("tok", [], tmp_path, profile="dark", options={"bars": "click", "jump_ms": "600-900"})
    query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert query["profile"] == "dark" and query["bars"] == "click" and query["jump_ms"] == "600-900"
    assert "soft_first" not in query  # a profile draws sharp at once unless asked
    soft = {k: v[0] for k, v in parse_qs(urlparse(sv.page_url("tok", [], tmp_path, profile="light",
                                                               soft_first=True)).query).items()}
    assert soft["soft_first"] == "1" and soft["profile"] == "light"


@pytest.mark.parametrize("profile, options", [("sepia", {}), ("", {"bars": "edge"}), ("dark", {"colour": "red"}),
                                              ("dark", {"bars": "edge&x=1"}), ("dark", {"ground": "a b"})])
def test_a_wrong_profile_or_part_is_refused(tmp_path, profile, options):
    with pytest.raises(ValueError):
        sv.page_url("tok", [], tmp_path, profile=profile, options=options)


def test_the_parts_given_as_words():
    assert sv.parse_options(["bars=click", " jump_ms = 500-900 "]) == {"bars": "click", "jump_ms": "500-900"}
    for bad in (["bars"], ["nothing=1"], ["bars=a;b"]):
        with pytest.raises(ValueError):
            sv.parse_options(bad)


def test_the_script_has_its_steps_for_the_bars_and_the_arrows():
    assert "v" in sv.OPS and "a" in sv.OPS
    assert sv.parse_script("v,v2500,a,n") == [sv.Step("v"), sv.Step("v", 2500), sv.Step("a"), sv.Step("n")]
    ops = re.search(r"/\^\(\[(\w+)\]\)", HTML).group(1)
    assert ops == sv.OPS


# ---------------------------------------------------------------------------------------------------- the e2e plan
def test_scenario_q_comes_by_its_name_only():
    assert "q" not in standin_e2e.wanted("all")
    assert standin_e2e.wanted("q") == ["q"] and standin_e2e.wanted("q,a") == ["a", "q"]


def test_the_screens_foreseen_follow_the_cover_alone():
    count = standin_e2e.pages_needed(["a", "q"])
    assert count >= 56 + 8  # (q jumps to page 56)
    segments, steps = standin_e2e.build_plan(["a", "q"], count, cover=True)
    assert [s for s, _spread in segments[0].screens] == [1, 3, 5, 7, 9, 11, 13, 15, 17]
    assert [s for s, _spread in segments[1].screens] == [19, 21, 29, 31, 33, 43, 41, 55]
    assert {s.op for s in steps} >= {"v", "a", "j"}
    plain, _steps = standin_e2e.build_plan(["a"], 26)  # without a profile: as ever
    assert [s for s, _spread in plain[0].screens] == [2, 4, 6, 8, 10, 12, 14, 16, 18]
    assert standin_e2e.pages_needed(["a"]) == 26


def test_a_profile_draws_sharp_at_once_unless_asked():
    assert standin_e2e.parse([]).soft_first == "on"
    assert standin_e2e.parse(["--standin-profile", "dark"]).soft_first == "off"
    assert standin_e2e.parse(["--standin-profile", "light", "--soft-first", "on"]).soft_first == "on"
    args = standin_e2e.parse(["--standin-profile", "dark", "--standin-option", "bars=move",
                              "--standin-option", "jump=plain"])
    assert sv.parse_options(args.standin_option) == {"bars": "move", "jump": "plain"}


# ---------------------------------------------------------------------------------------------------- the self-check
def test_the_self_check_s_log_lines_hold_numbers_and_words_only():
    said = [(0.0, {"ev": "draw", "t": "1000.0", "step": "-1", "page": "0", "box": "1,2,3,4"}),
            (0.1, {"ev": "turn", "t": "1250.5", "step": "-1", "page": "0", "by": "key"})]
    lines = standin_selfcheck.summary_of(said)
    assert lines[0].split()[:2] == ["0.0", "draw"] and lines[1].split()[:2] == ["250.5", "turn"]
    assert "by=key" in lines[1] and "step=" not in lines[1]


def test_the_self_check_wants_a_scratch_folder_outside_the_repository():
    with pytest.raises(SystemExit):
        standin_selfcheck.main(["--out", str(ROOT / "scratch_here")])
    assert not (ROOT / "scratch_here").exists()
