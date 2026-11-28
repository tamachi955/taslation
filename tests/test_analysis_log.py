"""The session's analysis log (`taslation.analysis`: one line of numbers per page, of what the person saw and of each
change they made, every defect with its level) and developer measuring on top of it (`taslation.devmeasure`,
`ui.measure`: a source checkout only, off at every start; every page read afresh and kept whole; the kinds of keys
only while the viewer or TASlation is in front; never exported)."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, JA_TEXTS
from PIL import Image

from taslation import analysis, backup, devmeasure
from taslation.config import ConfigError, Settings
from taslation.pipeline import Pipeline
from taslation.regions import PageResult, TextRegion
from taslation.translate import DictTranslator
from taslation.ui import measure

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import analysis_summary  # noqa: E402


def _region(box=(10, 10, 60, 90), **values) -> TextRegion:
    x0, y0, x1, y1 = box
    r = TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), box)
    for k, v in values.items():
        setattr(r, k, v)
    return r


def _result(regions, size=(200, 150)) -> PageResult:
    image = Image.new("RGB", size, "white")
    return PageResult(image=image, original=image.copy(), regions=list(regions),
                      timings={"detect": 0.02, "ocr": 0.01, "render": 0.005}, units=[object()], cache_misses=1)


def _lines(path: Path) -> list[dict]:
    return [json.loads(t) for t in path.read_text("utf-8").splitlines() if t.strip()]


def _strings(value, keys=True):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if keys:
                yield k
            yield from _strings(v, keys)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, keys)


# ------------------------------------------------------------------ the line
def test_a_page_line_holds_the_page_s_numbers_its_stages_helpers_and_effects(tmp_path):
    log = analysis.start(tmp_path, "on")
    assert log is not None and analysis.on()
    rgb = np.full((150, 200, 3), 255, np.uint8)
    rgb[:, :100] = (200, 30, 30)  # (half the page in colour)

    @analysis.timed("helper_a")
    def helper(region):
        analysis.acted(region, "helper_a")
        analysis.count("helper_a.px", 12)
        return 1

    lettered = _region(status="translated", source_text=JA_TEXTS[0], translated_text=EN_TEXTS[JA_TEXTS[0]],
                       fitted="turned")
    left = _region((100, 10, 150, 90), status="untranslated", source_text=JA_TEXTS[1])
    page = analysis.begin(rgb, (0, 0, 0, 0))
    assert analysis.current() is page and page.n == 1
    analysis.traced([lettered, left])
    helper(lettered)
    helper(lettered)
    with analysis.timing("block_b"):
        analysis.acted_box("block_b", (1, 2, 3, 4))
    written = analysis.end(page, _result([lettered, left]))
    assert analysis.current() is None
    (line,) = _lines(tmp_path / analysis.FILE_NAME)
    assert line == written
    for key in ("type", "v", "n", "t", "end", "ms", "outcome", "ahead", "size", "facts", "margins", "stages", "helpers",
                "counts", "effect", "regions", "cases", "minor", "units", "hits", "misses", "cached", "error",
                "self_ms", "gpu_free_mb"):
        assert key in line, key
    assert (line["type"], line["v"], line["n"], line["outcome"], line["ahead"]) == ("page", analysis.VERSION, 1,
                                                                                    "done", False)
    assert line["size"] == [200, 150] and line["margins"] == [0, 0, 0, 0]
    assert line["facts"]["colour"] == pytest.approx(0.5, abs=0.02) and 0 <= line["facts"]["ink"] <= 1
    assert line["stages"] == {"detect": 20.0, "ocr": 10.0, "render": 5.0}
    assert line["helpers"]["helper_a"][1] == 2 and line["helpers"]["block_b"][1] == 1
    assert line["counts"]["helper_a.px"] == 24 and line["counts"]["effect.helper_a"] == 2
    assert line["effect"] == {"helper_a": 1, "block_b.boxes": 1}  # (a region counts once a helper)
    assert line["regions"]["n"] == 2 and line["regions"]["status"] == {"translated": 1, "untranslated": 1}
    assert line["regions"]["fitted"] == {"turned": 1}
    assert [c["code"] for c in line["cases"]] == ["not_translated"] and line["cases"][0]["level"] == "s1"
    assert line["self_ms"] >= 0 and line["ms"] >= 0 and line["units"] == 1 and line["cached"] is False
    assert analysis.records() == [line]


def test_a_page_that_failed_or_was_lettered_ahead_says_so_and_a_slow_one_is_an_s1_case(tmp_path):
    analysis.start(tmp_path, "on")
    page = analysis.begin(None, None, ahead=True)
    page.t0 -= 100  # (100 s: past any budget)
    assert analysis.end(page, _result([]))["cases"] == []  # (lettered ahead: no reader waited for it)
    page = analysis.begin(None, None)
    page.t0 -= 100
    slow = analysis.end(page, _result([]))
    (case,) = slow["cases"]
    assert case["code"] == "page_slow" and case["level"] == "s1" and case["stage"] == "detect"
    assert case["budget_s"] in (analysis.PAGE_BUDGET_S, analysis.PAGE_BUDGET_CPU_S)
    page = analysis.begin(None, None)
    assert analysis.end(page, None, outcome="cancelled")["outcome"] == "cancelled"
    summary = analysis.summary_lines(analysis.records())
    assert any(s.startswith("pages 3 (done 2, cancelled 1; read 3") for s in summary)
    assert any(s.endswith("- (cancelled)") for s in summary)


def test_the_log_writes_nothing_and_costs_a_look_while_it_is_off(tmp_path):
    assert not analysis.on() and analysis.begin(None, None) is None
    calls = []

    @analysis.timed("x")
    def f():
        calls.append(analysis.current())
        return 3

    assert f() == 3 and calls == [None]
    analysis.count("x")
    analysis.request(lambda: calls.append("asked") or {})
    assert calls == [None] and analysis.write({"type": "ui"}) is None and analysis.records() == []
    assert not any(tmp_path.iterdir())


# ------------------------------------------------------------------ numbers only
MARKER_KINDS = (
    lambda rng: f"MARK{rng.randrange(10 ** 6)}",  # (never a name: capitals)
    lambda rng: f"マーカー{rng.randrange(1000)}",  # (Japanese)
    lambda rng: f"C:\\Users\\Mark{rng.randrange(99)}\\book.json",  # (a path)
    lambda rng: f"Mark Title Vol. {rng.randrange(9)}",  # (a title, with spaces)
    lambda rng: f"ほげ MARK {rng.randrange(99)} 「ね」",
)
TEXT_FIELDS = ("source_text", "translated_text", "speaker", "remark", "reader_note", "reused_text", "ocr_reading")
ENUM_FIELDS = ("kind", "status", "fitted", "tag", "sound")


def test_no_text_of_a_page_no_title_and_no_name_reaches_the_file_whatever_the_page_holds(tmp_path):
    """A property over random pages: the texts of its regions (any string, a lowercase one too), what its enums hold
    when they hold something else, titles and names given as helper names or keys - none reaches the file, and
    every key and string value written is one of the program's own names."""
    analysis.start(tmp_path, "on")
    rng = random.Random(20261128)
    used: set[str] = set()

    def marker(lowercase_too: bool = False) -> str:
        kinds = MARKER_KINDS + ((lambda r: "zq" + "".join(r.choice("abcdefgh") for _ in range(9))),) * lowercase_too
        text = rng.choice(kinds)(rng)
        used.add(text)
        return text

    for _round in range(60):
        regions = []
        page = analysis.begin(np.full((40, 60, 3), rng.randrange(256), np.uint8), (0, 0, 0, 0))
        for k in range(rng.randrange(1, 5)):
            r = _region((k, k, k + 20, k + 30))
            for name in TEXT_FIELDS:
                setattr(r, name, marker(lowercase_too=True))
            for name in ENUM_FIELDS:
                if rng.random() < 0.5:
                    setattr(r, name, marker())
            r.flags = [marker(), "small"]
            r.letter_flags = (marker(), "no-fit")
            r.ocr_confidence = rng.random()
            analysis.acted(r, marker())
            analysis.note(r, "readings", {"readings": [marker(lowercase_too=True)]})  # (dev only: no session here)
            regions.append(r)
        analysis.count(marker(), 1)
        with analysis.timing(marker()):
            pass
        analysis.end(page, _result(regions))
        analysis.edited(rng.choice(("edit", "drop", "add", "move", marker())), _result(regions),
                        [(regions[0], regions[-1])])
        analysis.write({"type": "ui", marker(): 1, "title": marker(), "withheld": {marker(): 2}})
    text = (tmp_path / analysis.FILE_NAME).read_text("utf-8")
    for m in used:
        assert m not in text and json.dumps(m)[1:-1] not in text, m
    for line in _lines(tmp_path / analysis.FILE_NAME):
        for value in _strings(line):
            assert analysis.NAME.fullmatch(value), value
    for line in analysis.records():
        assert "readings" not in json.dumps(line)


def test_clean_lets_numbers_and_the_program_s_names_through_and_nothing_else():
    assert analysis.clean({"a_b": 1, "x.y:z+1": 2.12345, "Bad Key": 3, "ok": "Mixed Case"}) == {
        "a_b": 1, "x.y:z+1": 2.123, "other": 3, "ok": "other"}
    assert analysis.clean({"Bad": 1, "Worse": 2}) == {"other": 3}  # (two keys made one: added)
    assert analysis.clean([np.int64(3), np.float32(0.5), True, None, float("nan"), object()]) == [3, 0.5, True, None,
                                                                                                    None, None]


# ------------------------------------------------------------------ on and off
def test_the_log_is_on_in_a_source_checkout_and_off_in_an_installed_copy(tmp_path):
    checkout, worktree, installed = tmp_path / "checkout", tmp_path / "worktree", tmp_path / "installed"
    (checkout / ".git").mkdir(parents=True)
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")  # (a worktree's .git is a file)
    installed.mkdir()  # (the release's ZIP: no .git)
    for root, auto in ((checkout, True), (worktree, True), (installed, False)):
        assert analysis.source_checkout(root) is auto
        assert analysis.wanted("auto", root) is auto and analysis.wanted(None, root) is auto
        assert analysis.wanted("on", root) is True and analysis.wanted("off", root) is False
    assert Settings().analysis_log == "auto"
    Settings(analysis_log="off").validate()
    with pytest.raises(ConfigError):
        Settings(analysis_log="sometimes").validate()
    assert analysis.start(tmp_path / "state", "off") is None and not (tmp_path / "state").exists()
    assert analysis.start(tmp_path / "state", "on") is not None
    assert analysis.start(tmp_path / "other", "on") is analysis.log()


# ------------------------------------------------------------------ the levels
def test_every_defect_carries_its_level_and_the_first_table_is_by_level(tmp_path):
    analysis.start(tmp_path, "on")
    regions = [
        _region(status="untranslated", source_text="x"),  # S1 not translated
        _region(status="detected", source_text="x", kind="bubble", ocr_confidence=1.0),  # S1 left as drawn, sure
        _region(status="detected", source_text="x", kind="bubble", ocr_confidence=0.2),  # S3 unsure, left
        _region(status="translated", source_text="x", ocr_confidence=0.2),  # S2 unsure, on the drawing (lama)
        _region(status="translated", source_text="x", letter_flags=("no-fit",), flags=["small"]),  # S2 cut, S3 small
        _region(status="translated", source_text="x"),  # S3 hyphenated, S4 turned
    ]
    page = analysis.begin(None, None)
    analysis.traced(regions)
    analysis.acted(regions[3], "lama")
    analysis.acted(regions[5], "fit_hyphenated")
    analysis.acted(regions[5], "fit_turned")
    line = analysis.end(page, _result(regions))
    assert sorted((c["code"], c["level"], c["i"]) for c in line["cases"]) == [
        ("bubble_left_as_drawn", "s1", 1), ("lettering_cut", "s2", 4), ("not_translated", "s1", 0),
        ("unsure_lettered_on_art", "s2", 3)]
    assert line["minor"] == {"hyphenated": 1, "small": 1, "turned": 1, "unsure_left_as_drawn": 1}
    assert all(analysis.LEVELS[code] in ("s3", "s4") for code in line["minor"])
    case = next(c for c in line["cases"] if c["code"] == "unsure_lettered_on_art")
    assert case["acted"] == ["lama"] and case["box"] == [10, 10, 60, 90] and case["conf"] == 0.2
    # the person's changes: added S1, retyped S2 (S1 where it had no translation), deleted over the art S2, moved S3
    result = _result(regions)
    result.analysis_n = line["n"]
    analysis.edited("add", result, [(None, _region())])
    analysis.edited("edit", result, [(regions[4], regions[4])])
    analysis.edited("edit", result, [(regions[0], regions[0])])
    analysis.edited("drop", result, [(regions[3], None)])
    analysis.edited("drop", result, [(regions[5], None)])
    analysis.edited("move", result, [(regions[1], regions[1])])
    analysis.edited("again", result, [])
    edits = [ln for ln in _lines(tmp_path / analysis.FILE_NAME) if ln["type"] == "edit"]
    assert [[c["code"] for c in e["cases"]] for e in edits] == [["edit_add"], ["edit_retyped"],
                                                               ["edit_retyped_untranslated"], ["edit_drop_on_art"], [],
                                                               [], ["edit_again"]]
    assert [e["minor"] for e in edits][4:6] == [{"edit_drop": 1}, {"edit_move": 1}]
    assert all(e["page"] == line["n"] for e in edits)
    # the right pane's Ask again: S2, S1 where the bubble had no translation
    assert (analysis.edit_code("ask", regions[4]), analysis.edit_code("ask", regions[0])) == (
        "edit_asked", "edit_asked_untranslated")
    assert analysis.LEVELS["edit_asked"] == "s2" and analysis.LEVELS["edit_asked_untranslated"] == "s1"
    assert edits[3]["regions"][0]["acted"] == ["lama"] and edits[3]["regions"][0]["w"] == 50
    table = analysis.level_lines(analysis.records())
    assert table[0] == "defects by level (1 pages, 6 regions)"
    assert table[1] == "S1 reading fails: 4"
    assert f"  page {line['n']}: edit_add (kind bubble, tier 0, w 50, h 80, acted , box 10/10/60/90)" in table
    s2 = table.index("S2 content lost or damaged: 5")
    assert table[s2 + 1].startswith(f"  page {line['n']}: edit_again")
    s3 = table.index("S3 readable but hard: 5")
    assert table[s3 + 1].startswith("  ") and "a page" in table[s3 + 1] and "per 100 regions" in table[s3 + 1]
    assert "S4 cosmetic: 1" in table
    summary = analysis.summary_lines(analysis.records())
    assert summary[:len(table)] == table  # (the first table)
    assert any(s.startswith("the log's own cost: ") for s in summary)


# ------------------------------------------------------------------ the pipeline's pages
def test_a_page_the_pipeline_reads_writes_its_line_with_its_stages_and_helpers(sample_page, settings, tmp_path):
    analysis.start(tmp_path / "log", "on")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
    result = pipeline.process(sample_page, use_cache=False)
    (line,) = analysis.records()
    assert result.analysis_n == line["n"] == 1 and line["outcome"] == "done"
    assert {"fingerprint", "detect", "ocr", "translate", "render"} <= set(line["stages"])
    assert {"bubbles", "erase", "letter", "paper_fill"} <= set(line["helpers"])
    assert line["regions"]["n"] == len(result.regions) >= 6 and line["regions"]["status"]["translated"] >= 6
    assert line["effect"].get("paper_fill", 0) >= 1 and line["counts"]["fit.draw"] >= 6
    text = (tmp_path / "log" / analysis.FILE_NAME).read_text("utf-8")
    for ja in JA_TEXTS:
        assert ja not in text and json.dumps(ja)[1:-1] not in text
    for en in EN_TEXTS.values():
        assert en not in text
    assert line["self_ms"] < 0.05 * line["ms"] + 2.0  # (what the log costs: a small share of the page)


def test_measuring_reads_every_page_afresh_and_leaves_the_cache_untouched(sample_page, settings):
    from taslation.backlog import tracking_for
    from taslation.cache import CacheStore

    cache = CacheStore(settings.cache_dir).open("Test Book", "fake")
    tr = DictTranslator(EN_TEXTS)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache)
    pipeline.measuring = True
    first = pipeline.process(sample_page)
    second = pipeline.process(sample_page)
    assert first.cache_hits == second.cache_hits == 0 and len(tr.calls) == 2  # (read and asked for both times)
    assert not cache.path.exists() and not pipeline.keep_shown(sample_page)  # (nothing written, nothing kept)
    window = SimpleNamespace(pipeline=pipeline, _post=lambda *a, **k: None, selected=None)
    assert tracking_for(window, sample_page, None) is None  # (nothing read behind the reader)
    pipeline.measuring = False
    pipeline.process(sample_page)
    assert cache.path.exists()


# ------------------------------------------------------------------ the window's lines
class _Over:
    def __init__(self):
        self.counts = {"woke": 0, "woke_failed": 0, "looks": 0}


def _window(tmp_path, result=None):
    app = SimpleNamespace(settings=Settings(state_dir=tmp_path / "state"), last_result=result, _see_through=_Over(),
                          selected=SimpleNamespace(title="Mark Title Vol. 3 - MARKVIEWER", hwnd=0),
                          book_var=SimpleNamespace(get=lambda: "Mark Book マーカー"))
    measure.start(app)
    return app


def test_the_window_line_counts_what_was_withheld_and_by_why_and_each_s1_once(tmp_path):
    analysis.start(tmp_path, "on")
    result = _result([_region(status="translated"), _region((100, 10, 150, 90), status="translated")])
    result.analysis_n = 7
    app = _window(tmp_path, result)
    app._see_unshown = {id(result.original): {
        "looks": 3, "kinds_seen": {"not drawn": 1, "bars": 2},
        "last": {"boxes": [(0, (10, 10, 60, 90)), (1, (100, 10, 150, 90))]},
        "regions": {0: {"shown_at": 1.0, "unshown_at": 2.0, "kind": "not drawn"},
                    1: {"shown_at": 3.0, "unshown_at": 2.5, "kind": "bars"}}}}
    app._see_through.counts.update(woke=4, woke_failed=1)
    app._see_pane_hid = {"its place lay over the page box of the frame on show": 2}
    app._see_guarded = {"lettering": 3}
    app._see_foreground = {"to a dialog (viewer chooser)": 1, "to a window of TASlation's (Cls1)": 1,
                           "to a window of TASlation's (Cls2)": 2}
    line = measure.ui_line(app)
    assert (line["type"], line["page"], line["looks"]) == ("ui", 7, 3)
    assert line["counts"]["foreground.to_a_dialog:viewer_chooser"] == 1  # (a dialog's kind kept, no window class)
    assert line["counts"]["foreground.to_a_window_of_taslations"] == 3 and "other" not in line["counts"]
    assert line["withheld"] == {"not_drawn": 1, "bars": 2} and line["panes"] == {"over_page": 2}
    assert [(c["code"], c["level"]) for c in line["cases"]] == [("patch_not_shown", "s1"), ("keys_not_back", "s1")]
    assert line["cases"][0]["i"] == 0 and line["cases"][0]["box"] == [10, 10, 60, 90]
    assert line["counts"]["over.woke"] == 4 and line["counts"]["guarded.lettering"] == 3 and line["dev"] is False
    again = measure.ui_line(app)  # (nothing new: nothing said twice)
    assert again["withheld"] == {} and again["cases"] == [] and again["counts"] == {} and again["panes"] == {}
    text = (tmp_path / analysis.FILE_NAME).read_text("utf-8")
    assert "Mark" not in text and "MARK" not in text
    summary = analysis.summary_lines(analysis.records())
    assert "S1 reading fails: 2" in summary and "patches withheld (looks): bars 2, not_drawn 1" in summary


def test_a_report_gets_the_analysis_section_while_the_log_is_on(tmp_path):
    from taslation.ui import report

    assert report.analysis_lines() == []
    analysis.start(tmp_path, "on")
    page = analysis.begin(None, None)
    analysis.end(page, _result([_region(status="untranslated")]))
    lines = report.analysis_lines()
    assert lines[0] == "[analysis]" and lines[1] == "table = defects by level (1 pages, 1 regions)"
    assert all(line.split(" = ")[0] in report.ANALYSIS_KEYS for line in lines[1:])
    assert len(lines) <= report.ANALYSIS_LINES + 2


# ------------------------------------------------------------------ the tool
def test_the_summary_tool_reads_a_session_folder_and_times_the_turns(tmp_path, capsys):
    pages = [{"type": "page", "n": 1, "t": 1100, "end": 2100, "ms": 1000.0, "first_letter_ms": 300.0, "units": 1,
              "stages": {"detect": 400.0}, "regions": {"n": 3}, "facts": {"colour": 0.0}},
             {"type": "page", "n": 2, "t": 5200, "end": 8200, "ms": 3000.0, "first_letter_ms": 900.0, "units": 2,
              "stages": {"ocr": 2000.0}, "regions": {"n": 9}},
             {"type": "page", "n": 3, "t": 5300, "end": 5400, "ms": 100.0, "ahead": True}]
    (tmp_path / analysis.FILE_NAME).write_text("".join(json.dumps(p) + "\n" for p in pages), encoding="utf-8")
    inputs = [{"t": 1000, "type": "key", "key": "left"}, {"t": 4000, "type": "key", "key": "other"},
              {"t": 4900, "type": "key", "key": "right"}, {"t": 5000, "type": "wheel", "ticks": -1.0}]
    (tmp_path / "input.jsonl").write_text("".join(json.dumps(i) + "\n" for i in inputs), encoding="utf-8")
    (tmp_path / "p0001-frame.png").write_bytes(b"not read")  # (never opened)
    entries = analysis_summary.turn_pages(inputs, pages)
    assert [(e["kind"], e["page"]["n"] if e["page"] else None) for e in entries] == [("left", 1), ("right", None),
                                                                                    ("wheel", 2)]
    assert (entries[0]["first_ms"], entries[0]["done_ms"]) == (400, 1100)
    assert (entries[2]["first_ms"], entries[2]["done_ms"]) == (1100, 3200)
    assert analysis_summary.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("defects by level (3 pages, 12 regions)")
    assert "turns asked for: 3 (with a page read next: 2)" in out
    assert "asked -> first lettering: median 750 ms, p90 1100 ms" in out and "slowest turns:" in out


# ------------------------------------------------------------------ developer measuring
def test_developer_measuring_exists_only_in_a_source_checkout(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    installed.mkdir()
    assert not devmeasure.available(installed) and devmeasure.available(ROOT) == (ROOT / ".git").exists()
    with pytest.raises(devmeasure.Refused):
        devmeasure.Session(tmp_path / "state", root=installed)
    assert not (tmp_path / "state").exists()  # (nothing made)
    monkeypatch.setattr(devmeasure, "available", lambda root=None: False)
    app = _window(tmp_path)
    assert measure.switch_on(app, ask=False) is False and not measure.on(app)
    assert not (tmp_path / "state" / devmeasure.FOLDER).exists()
    added = []
    menu = SimpleNamespace(add_cascade=lambda **k: added.append(k))
    measure.menu_entries(app, menu, lambda command: command)
    assert added == []  # (no entry in an installed copy)


def test_developer_measuring_is_off_at_every_start_and_has_no_setting(tmp_path):
    from dataclasses import fields

    (tmp_path / "state" / devmeasure.FOLDER / "20261128-000000").mkdir(parents=True)  # (a session kept before)
    app = _window(tmp_path)
    assert not measure.on(app) and app._measure is None
    assert not [f.name for f in fields(Settings) if "measur" in f.name]


def test_the_input_record_keeps_key_kinds_only_and_nothing_while_another_program_is_in_front(tmp_path):
    record = devmeasure.InputLog(tmp_path / "input.jsonl")
    front = [False]
    record.allowed = lambda: front[0]
    assert not record.key(0x41) and not record.key(0x25) and not record.press("left", 5, 5, True)
    assert not record.wheel(-120, True) and record.kept == 0
    front[0] = True
    assert record.key(0x41) and record.key(0x25) and record.key(0x2D) and record.key(0x0D)
    assert not record.press("left", 5, 5, ours=False) and record.press("right", 7, 8, ours=True)
    assert not record.wheel(-240, over_viewer=False) and record.wheel(-240, over_viewer=True)
    record.flush()
    lines = _lines(tmp_path / "input.jsonl")
    assert [(ln["type"], ln.get("key") or ln.get("button") or ln.get("ticks")) for ln in lines] == [
        ("key", "other"), ("key", "left"), ("key", "insert"), ("key", "enter"), ("press", "right"), ("wheel", -2.0)]
    assert all(set(ln) <= {"t", "type", "key", "button", "x", "y", "ticks"} for ln in lines)
    assert [devmeasure.key_kind(vk) for vk in (0x20, 0x21, 0x22, 0x24, 0x23, 0x1B, 0x2E, 0x26, 0x28, 0x27)] == [
        "space", "page_up", "page_down", "home", "end", "escape", "delete", "up", "down", "right"]
    assert {devmeasure.key_kind(vk) for vk in range(0x30, 0x5B)} == {"other"}  # (letters, digits: never which)
    watch = devmeasure.InputWatch(record, lambda: False, lambda h: False, lambda h: False)
    assert record.allowed() is False and not watch.hooked  # (the watch's own look decides)


def test_a_session_keeps_each_page_whole_with_its_regions_and_its_later_states(sample_page, settings, tmp_path):
    if not devmeasure.available():
        pytest.skip("not a source checkout")
    session = devmeasure.Session(settings.state_dir)
    try:
        assert session.folder.parent == settings.state_dir / devmeasure.FOLDER
        assert "private" in (session.folder.parent / devmeasure.README_NAME).read_text("utf-8")
        pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
        pipeline.measuring = True
        result = pipeline.process(sample_page)
        analysis.request(lambda: {"prompt": JA_TEXTS[0], "raw": "an answer"})  # (outside the page: the last one's)
        result.regions[0].translated_text = "Retyped"
        result.image = result.image.copy()
        analysis.edited("edit", result, [(result.regions[0], result.regions[0])])
    finally:
        session.close()
    folder = session.folder
    names = {p.name for p in folder.iterdir()}
    assert {"p0001-frame.png", "p0001-erased.png", "p0001-lettered.png", "p0001.json", "p0001-s1-lettered.png",
            "p0001-s1.json", "analysis.jsonl", "requests.jsonl", "log.txt"} <= names
    assert devmeasure.STORES not in names  # (the session's own stores deleted at its end)
    with Image.open(folder / "p0001-lettered.png") as kept:
        assert kept.size == sample_page.size  # (the whole page, every patch composed in)
    data = json.loads((folder / "p0001.json").read_text("utf-8"))
    assert data["analysis"]["n"] == 1 and len(data["regions"]) == len(result.regions)
    first = data["regions"][0]
    assert first["settled"] in JA_TEXTS and first["translation"] in EN_TEXTS.values() and first["box"]
    assert {"readings", "confidence", "flags", "acted", "fitted", "kind", "tier"} <= set(first)
    assert json.loads((folder / "p0001-s1.json").read_text("utf-8"))["change"] == "edit"
    assert json.loads((folder / "requests.jsonl").read_text("utf-8").splitlines()[0])["raw"] == "an answer"
    # the numbers-only log beside it, in the state folder: no text even while measuring
    assert not (settings.state_dir / analysis.FILE_NAME).exists() or all(
        ja not in (settings.state_dir / analysis.FILE_NAME).read_text("utf-8") for ja in JA_TEXTS)
    assert all(ja not in (folder / "analysis.jsonl").read_text("utf-8") for ja in JA_TEXTS)


def test_the_window_gives_the_pipeline_stores_of_the_session_s_own_and_takes_them_back(tmp_path, monkeypatch):
    from taslation.annotations import AnnotationStore, GlossaryStore
    from taslation.cache import CacheStore

    if not devmeasure.available():
        pytest.skip("not a source checkout")
    app = _window(tmp_path)
    state = app.settings.state_dir
    real = (CacheStore(state / "cache"), AnnotationStore(state / "annotations"), GlossaryStore(state / "glossary"))
    app.store, app.annotation_store, app.glossary_store = real
    dropped = []
    app.pipeline = SimpleNamespace(measuring=False, set_cache=dropped.append, forget_shown=lambda: dropped.append("f"))
    asked = []
    monkeypatch.setattr("taslation.ui.dialogs.caches.ask", lambda *a, **k: asked.append(a[1]) or True)
    monkeypatch.setattr(devmeasure.InputWatch, "start", lambda self: None)
    assert measure.toggle(app) is True and measure.on(app) and asked and str(state / devmeasure.FOLDER) in asked[0]
    session = app._measure
    assert app.pipeline.measuring and dropped == [None, "f"]
    assert isinstance(app.store, CacheStore) and app.store.cache_dir == session.stores / "cache"
    sheet = app.glossary_store.open("Lantern Quay", "English")
    sheet.set("灯台", "lighthouse", "")
    sheet.save()
    marks = app.annotation_store.open("Lantern Quay 1")
    marks.save()
    written = [p for p in state.rglob("*.json") if devmeasure.FOLDER not in p.parts]
    assert written == []  # (read only: nothing written)
    assert app.glossary_store.delete("Lantern Quay") is False
    measure.switch_off(app)
    assert not measure.on(app) and (app.store, app.annotation_store, app.glossary_store) == real
    assert not app.pipeline.measuring and not session.stores.exists() and session.closed


def test_an_export_never_holds_developer_measuring_s_sessions(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from taslation.annotations import AnnotationStore, GlossaryStore
    from taslation.cache import CacheStore, CachedBubble, CachedPage
    from taslation.rename import Stores

    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)
    state = tmp_path / "state"
    stores = Stores(CacheStore(state / "cache"), AnnotationStore(state / "annotations"),
                    GlossaryStore(state / "glossary"))
    cache = stores.cache.open("Lantern Quay 1", "fake", "English")
    cache.add(CachedPage(fingerprint="a" * 80, aspect=0.7, bubbles=[CachedBubble(box=(0.1, 0.1, 0.2, 0.2), text="Hi")]))
    cache.save()
    kept = state / devmeasure.FOLDER / "20261128-000000"
    kept.mkdir(parents=True)
    (kept / "p0001.json").write_text(json.dumps({"settled": "MARKDEVTEXT"}), encoding="utf-8")
    (state / analysis.FILE_NAME).write_text('{"type":"page","marker":"MARKLOGLINE"}\n', encoding="utf-8")
    out = tmp_path / "all.stcache"
    backup.export_books(stores, [("Lantern Quay 1", "English")], out, "correct horse battery staple")
    payload = backup.decrypt(out.read_bytes(), "correct horse battery staple").decode("utf-8")
    assert "Hi" in payload and "MARKDEVTEXT" not in payload and "MARKLOGLINE" not in payload
    assert "dev-measure" in backup.NEVER_EXPORTED and analysis.FILE_NAME in backup.NEVER_EXPORTED


def test_the_words_of_developer_measuring_are_english_and_japanese_only(monkeypatch):
    from taslation import i18n

    assert set(measure.WORDS) == {"en", "ja"} and set(measure.WORDS["en"]) == set(measure.WORDS["ja"])
    monkeypatch.setattr(measure, "ui_language", lambda: "ja")
    assert measure.word("menu") == "開発者計測"
    monkeypatch.setattr(measure, "ui_language", lambda: "de")
    assert measure.word("menu") == "Developer measuring"  # (any other language: English)
    for catalog in i18n.CATALOGS.values():
        assert "Developer measuring" not in catalog  # (in no catalog: the window's language test never asks for it)


# ------------------------------------------------------------------ a spread's units, the readers, the watch
def test_a_spread_s_units_are_timed_apart_with_each_reader_s_calls_and_the_translator_s_requests(tmp_path):
    """Unit 0 read and translated on the page's thread, unit 1 read beside on a thread of its own (adopting the page),
    waited for and translated: each unit's reading, wait and translation from the page's start, its readers' calls
    by device (on the processor for a request under way apart), passes with no graph and waits for the graphs, and the
    translator's requests in the page's time; the summary tables unit 0 against unit 1 and the spread's gap."""
    import threading
    import time

    analysis.start(tmp_path, "on")
    analysis.reader("charspot", 0.5)  # (no page timed: nothing)
    page = analysis.begin(None, None)
    with analysis.unit_span(0):
        analysis.reader("charspot", 0.010, "cuda")
        analysis.reader("charspot", 0.030, "cuda:0")
        analysis.reader("nar", 0.020, "cuda")
        analysis.reader_plain("charspot")
        analysis.waited(0.004)

    def beside():
        with analysis.adopt(page), analysis.unit_span(1, beside=True):
            analysis.reader("charspot", 0.080, "cpu", translating=True)
            analysis.reader("cpt", 0.300, "cpu")

    with analysis.unit_span(0, "translate"):
        t = time.perf_counter()
        analysis.requested(t, t + 0.050)
        thread = threading.Thread(target=beside)
        thread.start()
        thread.join()
    with analysis.unit_span(1, "wait"):
        pass
    analysis.reader("nar", 0.002)  # (a read outside any unit's)
    with analysis.unit_span(1, "translate"):
        t2 = time.perf_counter()
        analysis.requested(t2, t2 + 0.040)
    analysis.requested(page.t0 - 5, page.t0 - 4)  # (a request before the page: not its)
    line = analysis.end(page, _result([]))
    units = {u["unit"]: u for u in line["read_units"]}
    assert sorted(units) == [-1, 0, 1]
    zero, one = units[0], units[1]
    assert zero["beside"] is False and one["beside"] is True and zero["crops"] == 2 and one["crops"] == 1
    assert zero["readers"]["charspot"]["gpu"] == 2 and zero["readers"]["charspot"]["cpu"] == 0
    assert zero["readers"]["charspot"]["max_ms"] == pytest.approx(30.0) and zero["readers"]["charspot"]["plain"] == 1
    assert zero["readers"]["nar"]["gpu_ms"] == pytest.approx(20.0) and zero["waits"] == 1
    assert zero["wait_ms"] == pytest.approx(4.0)
    assert one["readers"]["charspot"]["cpu_translating"] == 1 and one["readers"]["cpt"]["cpu_ms"] == pytest.approx(300)
    assert zero["read_end_ms"] <= zero["translate_start_ms"] <= one["read_start_ms"] <= one["read_end_ms"]
    assert one["read_end_ms"] <= zero["translate_end_ms"] <= one["wait_start_ms"] <= one["translate_start_ms"]
    assert units[-1]["readers"]["nar"]["calls"] == 1 and "read_ms" not in units[-1]
    assert [ms for _start, ms in line["requests"]] == [pytest.approx(50.0), pytest.approx(40.0)]
    assert all(isinstance(s, str) and analysis.NAME.fullmatch(s) for s in _strings(line))
    summary = analysis.summary_lines(analysis.records())
    at = summary.index(next(s for s in summary if s.startswith("page units read (1 pages)")))
    assert summary[at + 1].lstrip().startswith("unit 0   n   1 (beside   0)")
    assert any(s.lstrip().startswith("unit 1   n   1 (beside   1)") for s in summary)
    assert any("charspot" in s and "1 for a request under way" in s for s in summary)
    assert any(s.lstrip().startswith("spreads 1:") for s in summary)
    gap = analysis._spread_gap(line)
    assert gap["first_ms"] == pytest.approx(line["requests"][1][0])
    assert gap["idle_ms"] == pytest.approx(line["requests"][1][0] - line["requests"][0][0] - 50.0, abs=0.2)


def test_the_summary_gives_the_watch_s_duty_from_the_window_s_counts():
    lines = [{"type": "ui", "t": 1000, "counts": {"over.compare_ms": 999, "over.frames": 99}},  # (its start unknown)
             {"type": "ui", "t": 6000, "counts": {"over.compare_ms": 400.0, "over.looks": 200, "over.frames": 200,
                                                  "over.compares": 20, "over.same": 180}},
             {"type": "ui", "t": 11000, "counts": {"over.compare_ms": 100.0, "over.looks": 50, "over.frames": 50,
                                                   "over.compares": 5, "over.same": 45}}]
    (said,) = analysis.watch_lines(lines)
    assert said.startswith("the see-through watch over 10 s (2 ui lines): compare 50.0 ms a second (5.0 % of a thread)")
    assert "looks 25.0 a second, frames 25.0 a second, 20.0 ms a compare (compares)" in said
    assert said.endswith("unchanged frames not compared 225")
    assert analysis.watch_lines(lines[:1]) == [] and analysis.unit_lines(lines) == []
    assert any(s.startswith("the see-through watch over 10 s") for s in analysis.summary_lines(lines))
