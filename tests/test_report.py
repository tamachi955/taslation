"""The report a person copies to ask for help (`taslation.ui.report`): numbers and states only - no text of the page,
no title, no file name of the reader's - unless the person adds one region's text; its sections and keys stay as they
are; a region's report says why its lettering does not show; the clipboard alone, and the right pane says how many
lines; the Menu's entries and the region editor's button; the log's warnings and errors counted by kind, without
their values."""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import errorlog
from taslation.config import Settings
from taslation.regions import PageResult, TextRegion
from taslation.ui import report

W, H = 400, 300
# what must never reach a report unless the person asks for one region's text: the page's text and the reader's own
# words, the book's and the viewer's names, a path under the reader's folders, what a log call carried
MARKERS = ("MARKSOURCE", "MARKTRANS", "MARKSPEAKER", "MARKREMARK", "MARKNOTE", "MARKREAD", "MARKBOOK", "MARKTITLE",
           "MARKFONT", "MARKARG", "マーカー本文", "マーカー訳", "マーカー誤り", "MARKOTHER")


def _bubble(box, source, translated, status="translated"):
    x0, y0, x1, y1 = box
    mask = np.full((y1 - y0, x1 - x0), 255, np.uint8)
    r = TextRegion(x0, y0, x1, y1, mask, (x0 + 5, y0 + 5, x1 - 5, y1 - 5), kind="bubble", source_text=source,
                   translated_text=translated, status=status, font_size=14, flags=["ocr-unsure"])
    r.speaker, r.remark, r.reader_note = "MARKSPEAKER", "MARKREMARK", "MARKNOTE"
    return r


def _page():
    """A made-up page: two bubbles; in the first the erase left 6 dark pixels of the original, and its lettering
    changed 40 others."""
    first = _bubble((100, 40, 160, 260), "マーカー本文 MARKSOURCE", "MARKTRANS マーカー訳")
    first.ocr_reading = "MARKREAD"
    second = _bubble((220, 60, 300, 140), "MARKOTHER", "MARKOTHER line")
    original = np.full((H, W, 3), 250, np.uint8)
    original[100:102, 128:131] = 20  # (the original's dark pixels the erase left: 6)
    original[150:160, 120:140] = 30  # (lettering the erase took away)
    lettered = original.copy()
    lettered[150:160, 120:140] = 250
    lettered[200:202, 110:130] = 0  # (the new lettering)
    return PageResult(image=Image.fromarray(lettered), original=Image.fromarray(original), regions=[first, second],
                      timings={"detect": 0.12, "ocr": 0.4}, cache_hits=0, cache_misses=1,
                      fingerprints=["0123456789abcdef", "fedcba9876543210"], error="マーカー誤り",
                      notes=["MARKOTHER note"])


class _Over:
    """The see-through window as a report asks it: its last look found the page on show, a bar of the viewer's over
    the first region's patch, the second one shown."""

    def __init__(self, original, why=None):
        self.key = id(original)
        self.why = why if why is not None else {
            "key": self.key, "boxes": ((100, 40, 160, 260), (220, 60, 300, 140)),
            "valid": (1,), "barred": (0,), "bars": ((0, 44),), "covered": (), "drawn": (1,), "hover": None,
            "distance": 0.4, "limit": 2.0, "frame_at": time.monotonic(), "final": True, "hidden": ""}

    def why_not_shown(self):
        return self.why

    def report_facts(self, key=None, within_s=5.0):
        return {"on": True, "away": False, "editing": True, "takes_mouse": True, "key_held": False, "sizing": False,
                "dpi": 96, "origin": (1930, 80), "size": (W, H), "shown": (7, 1), "covers": [],
                "panes": {"left": (1700, 200, 1900, 600), "right": None}, "pane_wanted": {"left": True, "right": False},
                "frames_per_s": 12.4, "sets": 2, "counts": {},
                "patches": [((100, 40, 160, 260), 0.21), ((220, 60, 300, 140), 0.3)] if key == self.key else None}


def _app(tmp_path, result=None, why=None, editing=False):
    result = result or _page()
    regions = list(result.regions)
    state = tmp_path / "MARKBOOK state"
    settings = Settings(state_dir=state, models_dir=tmp_path / "models", hover_delay_ms=300,
                        font_path=str(tmp_path / "MARKFONT.ttf"), ollama_url="http://127.0.0.1:11999")
    said = []
    app = SimpleNamespace(
        settings=settings, last_result=result, pipeline=None, _see_through=_Over(result.original, why),
        _result_on_show=lambda: True, _page_regions=lambda: regions, _see_rest_box=(20, 10, 380, 290),
        _see_rest_size=(W, H), _see_ground=((W, H), (20, 10, 380, 290), (85, 300), (40, 40, 40), (0, W)),
        _see_bars_since=None, _see_foreground={"back to the viewer": 2},
        _see_foreground_lines=["foreground: the viewer -> a menu; 10 ms after the last job's start; editing on"],
        selected=SimpleNamespace(hwnd=0, title="MARKTITLE - a browser", class_name="Chrome_WidgetWin_1"),
        book_var=SimpleNamespace(get=lambda: "MARKBOOK 1"), say=lambda key, **values: said.append((key, values)),
        _see_hidden=editing, role_var=SimpleNamespace(get=lambda: "translator"), _role_job=None,
        _chosen_region=None, _also_chosen=[])
    app.said = said
    return app


@pytest.fixture(autouse=True)
def _no_server(monkeypatch):
    """No report of a test asks a translation program (the person's own is never reached)."""
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama: not asked in the tests")


@pytest.fixture
def counted():
    """The log's kinds of warnings and errors counted for the test (`errorlog._LastError`), as the window has it; the
    last error as it was afterwards."""
    root = logging.getLogger()
    handler = None if any(isinstance(h, errorlog._LastError) for h in root.handlers) else errorlog._LastError()
    if handler is not None:
        root.addHandler(handler)
    last, told = errorlog._last_error, errorlog._state_told
    errorlog._problems.clear()
    yield
    if handler is not None:
        root.removeHandler(handler)
    errorlog._problems.clear()
    errorlog._last_error, errorlog._state_told = last, told


def _values(text, section):
    """The first value of each key of the section *section* ("region", "page", ...) of the report *text*."""
    out, inside = {}, False
    for line in text.splitlines()[2:-1]:
        if line.startswith("[") and line.endswith("]"):
            inside = line[1:-1].split(" ")[0] == section
        elif inside and " = " in line:
            key, value = line.split(" = ", 1)
            out.setdefault(key, value)
    return out


def _sections(text):
    lines = text.splitlines()
    assert lines[0] == report.FENCE and lines[-1] == report.FENCE
    out, current = [], None
    for line in lines[2:-1]:
        if line.startswith("[") and line.endswith("]"):
            current = (line[1:-1].split(" ")[0], [])
            out.append(current)
        else:
            current[1].append(line.split(" = ", 1)[0])
    return lines[1], out


def test_the_default_report_holds_no_text_of_the_page_no_title_and_no_path(tmp_path, counted):
    logging.getLogger("taslation.ui.live").warning("could not read %s", "MARKARG")
    app = _app(tmp_path)
    for regions in (None, [app.last_result.regions[0]], app.last_result.regions):
        text = report.report_text(app, regions)
        head, _sections_found = _sections(text)
        assert head == report.HEAD == "TASlation report (no page text, no titles)"
        for marker in MARKERS:
            assert marker not in text, marker
        assert str(tmp_path) not in text and "font_path = (set)" in text and "hover_delay_ms = 300" in text
    assert "could not read %s (x1" in text  # (the warning's kind, its value left out)


def test_the_report_keeps_its_sections_and_keys(tmp_path):
    # the keys a report's lines have: changing one changes what people paste and the tools read
    assert report.PAGE_KEYS == ("key", "size", "on_show", "units", "from_cache", "regions", "kinds", "lettered",
                                "not_shown", "job", "job_before", "stream", "timings", "error", "region")
    assert report.REGION_KEYS == ("number", "status", "source", "kind", "direction", "box", "page_box", "text_box",
                                  "letter_box", "bubble", "edges", "reading", "translation", "lettering", "erase",
                                  "dark_kept", "patches", "shown", "history")
    assert report.SCREEN_KEYS == ("monitor", "viewer", "viewer_known", "viewer_window", "viewer_client", "viewer_dpi",
                                  "viewer_state", "viewer_in_front", "viewer_covered", "tab", "capture_route",
                                  "frame_size", "frames_per_s", "frame_states", "capture_area", "page_at_rest",
                                  "steady_band", "bars")
    assert report.PANES_KEYS == ("left", "right", "lettering_window", "lettering", "takes_mouse", "insert_key",
                                 "foreground", "foreground_line", "keys_guard", "hidden_root")
    assert report.PROGRAM_KEYS == ("version", "commit", "python", "tk", "os", "torch", "gpu", "ui_language",
                                   "target_language", "mode", "translator", "ocr", "layout_model", "inpainting",
                                   "stage_seconds", "server", "offline_guard", "settings_changed", "last_error")
    assert report.LOG_KEYS == ("problem",) and report.TEXT_KEYS == ("reading_text", "translation_text")
    app = _app(tmp_path)
    region = app.last_result.regions[0]
    _head, sections = _sections(report.report_text(app, [region]))
    names = [name for name, _keys in sections]
    assert names == ["region", "page", "screen", "panes", "program", "log"]  # (the region reported first)
    allowed = {"region": report.REGION_KEYS, "page": report.PAGE_KEYS, "screen": report.SCREEN_KEYS,
               "panes": report.PANES_KEYS, "program": report.PROGRAM_KEYS, "log": report.LOG_KEYS}
    for name, keys in sections:
        order = [allowed[name].index(k) for k in keys]  # (every key one of its section's, in their order)
        assert order == sorted(order), name
    region_keys = dict(sections)["region"]
    assert region_keys == list(report.REGION_KEYS)  # (a region in full: every key, once)
    program_keys = dict(sections)["program"]
    assert program_keys == list(report.PROGRAM_KEYS)
    page_keys = dict(sections)["page"]
    assert page_keys.count("region") == 1  # (the other region's one line)
    # the whole page: no region in full, a line for each
    _head, sections = _sections(report.report_text(app))
    assert [name for name, _k in sections] == ["page", "screen", "panes", "program", "log"]
    assert dict(sections)["page"].count("region") == 2


def test_the_server_line_says_whether_ollama_s_cloud_features_are_off(tmp_path, monkeypatch):
    """TASlation tells only the server it starts not to use Ollama's cloud features; a server it did not start runs
    with its own settings (English, as every value of the report)."""
    from taslation import ollama_start
    from taslation.ollama_start import ServerSetup

    app = _app(tmp_path)
    asked: list[tuple] = []
    for ours, setup, said in ((None, None, "not started by TASlation; its own settings; Ollama: not asked in the tests"),
                              ((1, 2), ServerSetup("f16", True, "256", "setting"),
                               "started by TASlation; cloud features off; window cache on; Ollama: not asked in the "
                               "tests"),
                              ((1, 2), ServerSetup("f16", False, "0", "setting", no_cloud=False),
                               "started by TASlation; cloud features not turned off; window cache off; Ollama: not "
                               "asked in the tests")):
        monkeypatch.setattr(ollama_start, "own_server", lambda url, ours=ours: ours)
        monkeypatch.setattr(ollama_start, "setup_of", lambda url, state=None, setup=setup: asked.append((url, state))
                            or setup)
        assert _values(report.report_text(app), "program")["server"] == said
    assert asked[0] == (app.settings.ollama_url, app.settings.state_dir)


def test_the_stage_seconds_are_this_session_s_else_those_kept(tmp_path):
    """The seconds a page of each stage left the System page: the report has them, this session's where the pipeline
    timed pages, else those kept when TASlation last closed (`devices.StageTimes`)."""
    from taslation.devices import StageTimes

    app = _app(tmp_path)
    assert _values(report.report_text(app), "program")["stage_seconds"] == "none yet"  # (no pipeline yet)
    app.pipeline = SimpleNamespace(stage_times=StageTimes())
    assert _values(report.report_text(app), "program")["stage_seconds"] == "none yet"
    StageTimes([{"detect": 0.5, "ocr": 1.25, "erase": 0.3}]).save(app.settings.state_dir)
    assert _values(report.report_text(app), "program")["stage_seconds"] == (
        "detect 0.50 s, ocr 1.25 s, erase 0.30 s a page; the mean of 1 page(s), kept when TASlation last closed")
    app.pipeline.stage_times = StageTimes([{"detect": 0.25, "ocr": 1.0, "translate": 3.0, "erase": 0.5},
                                           {"detect": 0.75, "ocr": 2.0, "erase": 0.5}])
    assert _values(report.report_text(app), "program")["stage_seconds"] == (
        "detect 0.50 s, ocr 1.50 s, translate 3.00 s, erase 0.50 s a page; the mean of 2 page(s), this session")


def test_a_region_report_holds_why_its_lettering_is_not_shown(tmp_path):
    from taslation.ui import seethrough as ui

    app = _app(tmp_path)
    app._see_through.why["frame_at"] = 0.0  # (a frame at rest: the regions not shown are counted)
    ui.unshown_tick(app, now=time.monotonic())
    first, second = app.last_result.regions
    text = report.report_text(app, [first])
    lines, page = _values(text, "region"), _values(text, "page")
    shown = lines["shown"]
    assert shown == "no: bars; a bar over rows 0-44; 1 patch(es)"
    assert lines["history"].startswith("shown never; not shown") and "(bars)" in lines["history"]
    assert lines["patches"] == "1; 100,40,160,260 opaque 0.21"
    assert lines["dark_kept"] == "6"  # (the original's dark pixels left inside the bubble)
    assert lines["lettering"].startswith("size 14 (cap 0, room 0); could not none; changed 110,150,140,202")
    assert lines["edges"].startswith("left 80, top 30, right 220, bottom 30")
    assert lines["number"] == "1 on its plate; 1 of 2 in the editor; index 0"
    assert lines["reading"].startswith("17 chars; confidence 1.0; readers split no; corrected by the person yes")
    assert page["not_shown"] == "bars 1"
    assert page["lettered"] == "2 lettered; 1 shown; the page on show by its sign: distance 0.4 (limit 2.0)"
    assert page["region"].startswith("2 (index 1): translated; bubble; box 220,60,300,140 (80x80); shown yes;")
    assert page["key"] == f"{id(app.last_result.original) & 0xFFFF:04x} (as the log names it)"
    # the lettering hidden, or another page on show: said so
    app._see_through.why = {"hidden": "off", "at": 0.0}
    assert _values(report.report_text(app, [first]), "region")["shown"] == "no: hidden:off"
    app._result_on_show = lambda: False
    assert (_values(report.report_text(app, [first]), "region")["shown"]
            == "not known (another page on show, or no look yet)")


def test_a_region_lettered_with_its_line_turned_or_over_its_outline_says_so(tmp_path):
    app = _app(tmp_path)
    first = app.last_result.regions[0]
    line = _values(report.report_text(app, [first]), "region")["direction"]
    assert line == "original tall; lettering auto; slant 0.0"
    first.fitted = "turned"  # (`Lettered.frame` as `Pipeline._render` keeps it)
    assert (_values(report.report_text(app, [first]), "region")["direction"]
            == "original tall; lettering auto (turned); slant 0.0")
    first.fitted = "overrun"
    assert "lettering auto (over the outline);" in _values(report.report_text(app, [first]), "region")["direction"]


def test_a_region_the_tone_fill_painted_says_so(tmp_path):
    app = _app(tmp_path)
    first = app.last_result.regions[0]
    assert _values(report.report_text(app, [first]), "region")["erase"].startswith("paper fill (")
    first.toned = True  # (its last erase painted it with its ground's pattern, `artwork.fill_tone`)
    assert _values(report.report_text(app, [first]), "region")["erase"].startswith("tone fill; mask ")


def test_with_text_adds_the_reported_region_s_reading_and_translation_alone(tmp_path):
    app = _app(tmp_path)
    first, second = app.last_result.regions
    text = report.report_text(app, [first], with_text=True)
    assert text.splitlines()[1] == report.HEAD_WITH_TEXT.format(n=1)
    assert "\nreading_text = マーカー本文 MARKSOURCE\n" in text and "\ntranslation_text = MARKTRANS マーカー訳\n" in text
    for marker in ("MARKOTHER", "MARKTITLE", "MARKBOOK", "MARKSPEAKER", "MARKREMARK", "MARKNOTE", "マーカー誤り"):
        assert marker not in text, marker
    # never for several regions at once, nor for none
    assert "reading_text" not in report.report_text(app, [first, second], with_text=True)
    assert "reading_text" not in report.report_text(app, None, with_text=True)


def test_copy_report_puts_it_on_the_clipboard_alone_and_says_how_many_lines(tmp_path, monkeypatch):
    from taslation.ui import copy_details

    put = []
    monkeypatch.setattr(copy_details, "put_on_clipboard", lambda widget, text: put.append((widget, text)))
    app = _app(tmp_path)
    n = report.copy_report(app, [app.last_result.regions[0]])
    (widget, text), = put
    assert widget is app and n == report.line_count(text) == len(text.splitlines()) - 2 and 40 < n <= report.MAX_LINES
    assert app.said == [(report.COPIED, {"n": n})]
    assert not any(tmp_path.rglob("*"))  # (nothing written)


def test_a_long_report_leaves_out_the_regions_one_lines_first(tmp_path):
    result = _page()
    result.regions += [_bubble((10 + i, 10, 20 + i, 20), "MARKOTHER", "x") for i in range(400)]
    text = report.report_text(_app(tmp_path, result))
    lines = text.splitlines()
    assert len(lines) == report.MAX_LINES + 2 and lines[-2].startswith("cut = ")
    assert any(line == "[program]" for line in lines)  # (the program's section stays)


def test_dark_kept_counts_the_original_s_dark_pixels_the_lettered_page_shows_as_they_were():
    region = _bubble((10, 10, 30, 30), "", "")
    original = np.full((40, 40, 3), 255, np.uint8)
    original[15:17, 15:20] = 10  # 10 dark pixels inside
    original[0:3, 0:3] = 0  # (outside the region: not counted)
    lettered = original.copy()
    assert report.dark_kept(original, lettered, region) == 10
    lettered[15:17, 15:18] = 255  # 6 of them erased
    assert report.dark_kept(original, lettered, region) == 4
    region.mask[:] = 0
    region.mask[15 - 10, 18 - 10:20 - 10] = 255  # (only part of the box is its interior)
    assert report.dark_kept(original, lettered, region) == 2
    region.mask = np.zeros((3, 3), np.uint8)
    assert report.dark_kept(original, lettered, region) is None


def test_the_menu_has_copy_a_report_and_while_editing_with_regions_chosen_two_more(tmp_path, monkeypatch):
    from taslation.i18n import _
    from taslation.ui import copy_details

    monkeypatch.setattr(copy_details, "put_on_clipboard", lambda widget, text: None)
    added = []
    menu = SimpleNamespace(add_command=lambda label, command: added.append((label, command)))
    app = _app(tmp_path)
    report.menu_entries(app, menu)
    assert [label for label, _c in added] == [_(report.COPY_REPORT)]
    added.clear()
    app = _app(tmp_path, editing=True)
    first, second = app.last_result.regions
    app._chosen_region = first
    report.menu_entries(app, menu)
    assert [label for label, _c in added] == [_(report.COPY_REPORT), _(report.COPY_CHOSEN), _(report.COPY_WITH_TEXT)]
    texts = []
    monkeypatch.setattr(report, "report_text", lambda app, regions=None, with_text=False, result=None:
                        texts.append((list(regions or ()), with_text)) or "```\nx\n```")
    for _label, command in added:
        command()
    assert texts == [([], False), ([first], False), ([first], True)]
    added.clear()
    app._also_chosen = [second]
    report.menu_entries(app, menu)
    assert [label for label, _c in added] == [_(report.COPY_REPORT), _(report.COPY_CHOSEN)]  # (two: no text)


def test_the_region_editor_copies_a_report_of_its_region_with_its_text_only_when_checked(hidden_root):
    from taslation.ui.dialogs import review

    region = _bubble((20, 20, 198, 199), "今日は", "Hello")
    asked = []
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                on_report=asked.append)
    assert d.report_btn is not None and not d.report_text_var.get()
    d.report_btn.invoke()
    d.report_text_var.set(True)
    d.report_btn.invoke()
    assert asked == [False, True] and d.report_btn.cget("text") == "Copied"
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.report_btn is None  # (no report asked for: no button)
    d.destroy()


def test_the_log_s_warnings_and_errors_are_counted_by_kind_without_their_values(counted):
    log = logging.getLogger("taslation.test")
    for value in ("MARKARG", "MARKOTHER", "マーカー本文"):
        log.warning("could not read %s", value)
    log.error("the model gave no answer for %d s", 30)
    logging.getLogger("taslation.test").info("not counted %s", "MARKARG")
    found = errorlog.problems()
    assert [(level, name, wording, n) for level, name, wording, n, _at in found] == [
        ("ERROR", "taslation.test", "the model gave no answer for %d s", 1),
        ("WARNING", "taslation.test", "could not read %s", 3)]
    assert errorlog.last_error() is not None  # (an error is the last error, as before)
    lines = report.log_lines()
    assert lines[0] == "[log]" and all(line.startswith("problem = ") for line in lines[1:])
    assert not any(m in "\n".join(lines) for m in ("MARKARG", "MARKOTHER", "マーカー本文"))


def test_the_report_s_words_are_in_every_language_of_the_window():
    from taslation.locales.features import report as catalog

    languages = {"ja", "es", "pt", "fr", "de", "it", "nl", "pl", "ru", "tr", "id", "vi", "zh", "zh-tw", "ko", "th"}
    for key in (report.COPY_REPORT, report.COPY_CHOSEN, report.COPY_WITH_TEXT, report.COPY_REGION, report.WITH_TEXT,
                report.COPIED, report.REPORT_TIP, report.WITH_TEXT_TIP):
        assert set(catalog.TEXTS[key]) == languages, key
        assert all("{n}" in t for t in catalog.TEXTS[key].values()) if "{n}" in key else True
    assert catalog.__doc__.rstrip().endswith("Machine-translated; no native review.")
    from taslation.ui.dialogs.help import TOPICS

    paragraph = next(p for _h, ps in TOPICS for p in ps if p.startswith("To report a problem"))
    assert set(catalog.TEXTS[paragraph]) == languages


def test_program_commit_reads_a_checkout_s_head_through_a_worktree_and_packed_refs(tmp_path):
    main = tmp_path / "main"
    git = main / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    head = "a" * 40
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(head + "\n")
    assert errorlog.program_commit(main) == "aaaaaaa"
    (git / "refs" / "heads" / "main").unlink()
    (git / "packed-refs").write_text(f"# pack-refs\n{'b' * 40} refs/heads/main\n")
    assert errorlog.program_commit(main) == "bbbbbbb"
    work = tmp_path / "work"
    work.mkdir()
    own = git / "worktrees" / "work"
    own.mkdir(parents=True)
    (work / ".git").write_text(f"gitdir: {own}\n")
    (own / "HEAD").write_text("c" * 40 + "\n")
    assert errorlog.program_commit(work) == "ccccccc"
    (own / "HEAD").write_text("ref: refs/heads/side\n")
    (own / "commondir").write_text("../..\n")
    (git / "refs" / "heads" / "side").write_text("d" * 40)
    assert errorlog.program_commit(work) == "ddddddd"
    assert errorlog.program_commit(tmp_path / "none") == ""
