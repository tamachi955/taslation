"""The panel beside a bubble made larger, and the lettering up to 200 %: ``panel_font_size`` (0: the automatic size,
the very pixels of before; else points that follow Tk's scaling - the monitor's DPI times ui_scale -, at most a share
of the work area's height), the panel made to fit the work area (its text smaller, else cut), ``hover_delay_ms`` (450:
the delays of before; 0 at once; within bounds) for the panel and for the bubble shown in its place, the two rows of
the Settings dialog under the hover rows (shown, saved, refused), and the lettering size at 200 %: the bubble still
holds every line, nothing over the largest size, and the review flags as at 100 %. Parts of the App on the stand-in
of `test_bubble_zoom` (never mapped)."""
from __future__ import annotations

import copy
import tkinter as tk
import tkinter.font as tkfont

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image
from test_bubble_zoom import WORK, Page

from taslation.cache import CacheStore
from taslation.config import HOVER_DELAY_RANGE, PANEL_FONT_RANGE, ConfigError, Settings
from taslation.i18n import FEATURE_LANGUAGES, _, set_language
from taslation.locales.features import panel_size as texts
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import zoom
from taslation.ui.dialogs import settings as dlg
from taslation.ui.zoom import (
    PANEL_TEXT_LEAST,
    PANEL_TEXT_MOST,
    ZOOM_DELAY_MS,
    ZOOM_REST_MS,
    fit_panel,
    hover_delays,
    panel_text_px,
    pixels_per_point,
    zoom_text_px,
)

AT_96_DPI = 96 / 72  # Tk's pixels a point at 100 % on a 96 DPI monitor
SMALL_WORK = (0, 0, 640, 360)


# ------------------------------------------------------------------ the settings
def test_the_defaults_are_the_numbers_of_before(tmp_path):
    s = Settings(state_dir=tmp_path)
    assert s.panel_font_size == 0 and s.hover_delay_ms == ZOOM_DELAY_MS == 450
    assert hover_delays(s) == (ZOOM_DELAY_MS, ZOOM_REST_MS) == (450, 1200)
    assert hover_delays(None) == (450, 1200)  # (a stand-in without settings)
    for readable, shown in ((11, 0), (0, 0), (11, 30), (5, 0), (30, 0), (11, 12.5), (20, 80)):
        for per_point in (AT_96_DPI, 2.0, 4.0):  # the automatic size never followed the scaling: it still does not
            assert panel_text_px(0, readable, shown, per_point, WORK) == zoom_text_px(readable, shown)
    assert [zoom_text_px(*a) for a in ((11, 0), (11, 30), (5, 0), (30, 0))] == [22, 38, 16, 44]  # (as before)
    s.validate()


@pytest.mark.parametrize("key, good, bad", [
    ("panel_font_size", [0, PANEL_FONT_RANGE[0], 18, PANEL_FONT_RANGE[1]], [-1, 5, 73, 1.5, True, "12"]),
    ("hover_delay_ms", [0, 450, HOVER_DELAY_RANGE[1]], [-1, HOVER_DELAY_RANGE[1] + 1, 450.0, False, "450"]),
])
def test_the_settings_are_checked(tmp_path, key, good, bad):
    for value in good:
        Settings(state_dir=tmp_path, **{key: value}).validate()
    for value in bad:
        with pytest.raises(ConfigError, match=key):
            Settings(state_dir=tmp_path, **{key: value}).validate()
    path = tmp_path / "taslation.toml"
    path.write_text(f"{key} = {good[-1]}\n", encoding="utf-8")
    assert getattr(Settings.from_toml(path), key) == good[-1]


# ------------------------------------------------------------------ the delays
def test_the_delay_sets_both_delays_and_0_is_at_once():
    assert hover_delays(Settings(hover_delay_ms=0)) == (0, 0)
    assert hover_delays(Settings(hover_delay_ms=900)) == (900, 2400)  # 8/3 as long on a bubble that reads well
    assert hover_delays(Settings(hover_delay_ms=HOVER_DELAY_RANGE[1])) == (3000, 8000)
    assert hover_delays(Settings(hover_delay_ms=99_999)) == (3000, 8000)  # (out of bounds: the nearer bound)
    assert hover_delays(Settings(hover_delay_ms=-5)) == (0, 0)


# ------------------------------------------------------------------ the text size
def test_a_size_set_by_hand_follows_the_scaling_within_a_share_of_the_work_area():
    assert panel_text_px(18, 11, 0, AT_96_DPI, WORK) == 24  # 18 points at 96 DPI and 100 %
    assert panel_text_px(18, 11, 0, 2.0, WORK) == 36  # at 150 % (144 DPI), or 96 DPI with ui_scale 1.5
    assert panel_text_px(18, 11, 80, AT_96_DPI, WORK) == 24  # what was asked for, whatever the lettering's size
    assert panel_text_px(72, 11, 0, 2.0, WORK) == int(round(1040 * PANEL_TEXT_MOST)) == 83  # the cap: not 44 px
    assert panel_text_px(72, 11, 0, 2.0, (0, 0, 3840, 2100)) == 144  # a 4K monitor holds it
    assert panel_text_px(72, 11, 0, 4.0, SMALL_WORK) == 44  # never less room than the automatic size had
    assert panel_text_px(500, 11, 0, AT_96_DPI, WORK) == 83 and panel_text_px(1, 11, 0, AT_96_DPI, WORK) == 8
    assert panel_text_px("x", 11, 0, AT_96_DPI, WORK) == 22  # (no number: automatic)


def test_the_pixels_a_point_are_tk_s_scaling(hidden_root):
    assert pixels_per_point(hidden_root) == pytest.approx(float(hidden_root.tk.call("tk", "scaling")))


@pytest.fixture
def popup(hidden_root):
    win = tk.Toplevel(hidden_root)
    win.withdraw()
    yield win
    win.destroy()


def test_a_panel_that_fits_is_left_as_it_is(popup):
    font = tkfont.Font(popup, family="TkDefaultFont", size=-30)
    tk.Label(popup, text="A line.", font=font).pack()
    popup.update_idletasks()
    size = (popup.winfo_reqwidth(), popup.winfo_reqheight())
    assert fit_panel(popup, size, WORK, font, None) == size and font.cget("size") == -30


def test_a_panel_larger_than_the_work_area_gets_smaller_text(popup):
    font = tkfont.Font(popup, family="TkDefaultFont", size=-80)
    text = "A long line of the translation that goes on and on. " * 6
    label = tk.Label(popup, text=zoom.wrapped(text, 600, font), font=font, justify="left")
    label.pack()
    popup.update_idletasks()
    size = (popup.winfo_reqwidth(), popup.winfo_reqheight())
    assert size[1] > SMALL_WORK[3]
    w, h = fit_panel(popup, size, SMALL_WORK, font, (label, text, 600))
    assert w <= 640 and h <= 360 and PANEL_TEXT_LEAST <= -font.cget("size") < 80
    assert (w, h) == (popup.winfo_reqwidth(), popup.winfo_reqheight())  # it fits by its text alone: not cut
    assert label.cget("text") == zoom.wrapped(text, 600, font)  # wrapped again in the smaller size


def test_a_panel_that_cannot_get_small_enough_is_cut_to_the_work_area(popup):
    font = tkfont.Font(popup, family="TkDefaultFont", size=-20)
    block = tk.Frame(popup, width=900, height=700)  # (a crop of the original: no text to make smaller)
    block.pack()
    tk.Label(popup, text="A line.", font=font).pack()
    popup.update_idletasks()
    size = (popup.winfo_reqwidth(), popup.winfo_reqheight())
    cut = []
    popup.geometry = lambda *a: cut.append(a)  # (a window never mapped does not report a size set for it)
    assert fit_panel(popup, size, SMALL_WORK, font, None) == (640, 360)
    assert -font.cget("size") == PANEL_TEXT_LEAST  # made as small as the panel's text goes first
    assert cut == [("640x360",)]


# ------------------------------------------------------------------ the panel on the stand-in
@pytest.fixture
def page(hidden_root, monkeypatch):
    shown = []
    monkeypatch.setattr(zoom, "reveal", shown.append)
    monkeypatch.setattr(zoom.layout, "work_area", lambda widget, x=None, y=None: WORK)
    monkeypatch.setattr(Image.Image, "save", lambda *_a, **_k: pytest.fail("nothing of the page is written"))
    w = Page(hidden_root)
    yield w
    w._zoom_hide()
    w.destroy()


def test_by_default_the_panel_is_as_before(page):
    page.point(150, 200)  # the small bubble: hard to read where it is
    assert [ms for ms, _f in page.later] == [ZOOM_DELAY_MS]
    page.due()
    assert page._zoom_font.cget("size") == -22 and page._zoom_words[1] == "A small line."
    page.point(550, 150)  # the wide bubble: it reads well
    assert [ms for ms, _f in page.later] == [ZOOM_REST_MS]


def test_the_delay_and_the_size_set_by_hand_are_used(page, monkeypatch):
    page.settings.hover_delay_ms = 0
    page.point(150, 200)
    assert [ms for ms, _f in page.later] == [0]
    page.settings.hover_delay_ms = 900
    page.point(550, 150)
    assert [ms for ms, _f in page.later] == [2400]
    page.settings.panel_font_size = 18
    monkeypatch.setattr(zoom, "pixels_per_point", lambda widget: 2.0)  # a 144 DPI monitor, or ui_scale 1.5
    page.due()
    assert page._zoom_font.cget("size") == -36
    page.point(750, 550)
    assert page._zoom_popup is None and page._zoom_words is None


def test_a_large_panel_text_on_a_small_screen_still_fits_it(page, monkeypatch):
    monkeypatch.setattr(zoom.layout, "work_area", lambda widget, x=None, y=None: SMALL_WORK)
    monkeypatch.setattr(zoom, "pixels_per_point", lambda widget: 4.0)
    region = page.last_result.regions[1]
    region.translated_text = "A wide bubble with a long line that says a great deal more than it should. " * 3
    page.settings.panel_font_size = 72
    placed = []
    real = zoom.zoom_place
    monkeypatch.setattr(zoom, "zoom_place", lambda size, bubble, bounds: placed.append(size) or real(size, bubble, bounds))
    page.point(550, 150)
    page.due()
    assert -page._zoom_font.cget("size") < 44  # (asked: 72 points at 4 px a point, held to 44 px, then smaller)
    assert placed and all(w <= 640 and h <= 360 for w, h in placed)


def test_the_bubble_shown_in_its_place_waits_as_long():
    from taslation.ui import in_place

    assert in_place.hover_delays is hover_delays  # (the one rule for both ways of showing the other side)


# ------------------------------------------------------------------ the Settings dialog
@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def test_every_number_row_s_words_are_in_every_language():
    assert [row.key for row in dlg.NUMBER_ROWS] == ["panel_font_size", "hover_delay_ms"]
    for row in dlg.NUMBER_ROWS:
        for english in (row.label, row.tip, row.problem):
            assert sorted(texts.TEXTS[english]) == sorted(FEATURE_LANGUAGES), english
        assert all("{low}" in t and "{high}" in t for t in texts.TEXTS[row.problem].values())
        assert row.section == "window" and row.after == "bubble_zoom" and row.key in dlg.KEYS
        assert row.key not in dlg.PAGE_SETTINGS  # (the page is not lettered again for them)
    set_language("ja")
    try:
        assert _(dlg.NUMBER_ROWS[0].label) == "パネルの文字の大きさ（ポイント、0: 自動）:"
    finally:
        set_language("en")


def _descendants(widget):
    stack, found = [widget], []
    while stack:
        item = stack.pop()
        found.append(item)
        stack.extend(item.winfo_children())
    return found


def _texts_by_row(frame):
    """The text of each widget in the first column of *frame*'s grid, by its row."""
    out = {}
    for child in frame.winfo_children():
        info = child.grid_info()
        if info and int(info.get("column", 0)) == 0:
            try:
                out[str(child.cget("text"))] = int(info["row"])
            except tk.TclError:
                pass
    return out


def test_the_rows_sit_under_the_hover_rows_and_show_the_settings(hidden_root, in_force):
    in_force.panel_font_size, in_force.hover_delay_ms = 14, 600
    d = dlg.SettingsDialog(hidden_root, in_force)
    frame = next(w for w in _descendants(d) if w.winfo_class() == "TLabelframe" and str(w.cget("text")) == _("The window"))
    rows = _texts_by_row(frame)
    zoom_row = rows[_("Enlarge the bubble under the pointer")]
    assert rows[_(dlg.NUMBER_ROWS[0].label)] == zoom_row + 1 and rows[_(dlg.NUMBER_ROWS[1].label)] == zoom_row + 2
    assert d.numbers["panel_font_size"].get() == "14" and d.numbers["hover_delay_ms"].get() == "600"
    assert d.values()["panel_font_size"] == 14 and d.values()["hover_delay_ms"] == 600 and d.changed() == {}
    d.destroy()


def test_the_rows_are_saved_and_handed_on(hidden_root, in_force):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.values()["panel_font_size"] == 0 and d.values()["hover_delay_ms"] == 450
    d.numbers["panel_font_size"].set("20")
    d.numbers["hover_delay_ms"].set(" 0 ")
    assert d.save() is True and got == [{"panel_font_size": 20, "hover_delay_ms": 0}]
    again = Settings.from_toml(in_force.config_path)
    assert again.panel_font_size == 20 and again.hover_delay_ms == 0
    d.destroy()


@pytest.mark.parametrize("key, typed, low, high", [
    ("panel_font_size", "5", *PANEL_FONT_RANGE), ("panel_font_size", "73", *PANEL_FONT_RANGE),
    ("panel_font_size", "big", *PANEL_FONT_RANGE), ("panel_font_size", "", *PANEL_FONT_RANGE),
    ("hover_delay_ms", "-50", *HOVER_DELAY_RANGE), ("hover_delay_ms", "3001", *HOVER_DELAY_RANGE),
    ("hover_delay_ms", "0.5", *HOVER_DELAY_RANGE),
])
def test_a_number_that_does_not_fit_is_refused(hidden_root, in_force, key, typed, low, high):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    d.numbers[key].set(typed)
    assert d.save() is False and got == [] and not in_force.config_path.exists()
    row = next(r for r in dlg.NUMBER_ROWS if r.key == key)
    assert d.message_var.get().replace("\n", " ") == row.problem.format(low=low, high=high)
    d.destroy()


# ------------------------------------------------------------------ the lettering at 200 %
def _lettered(settings, page):
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS),
                 cache=CacheStore(settings.cache_dir).open("Scale Book", "fake"))
    p.process(page)  # translated and kept
    return p, p.process(page)  # from the cache, lettered anew


def _room(p, region):
    """The size *region*'s translation fits its bubble at, held back by nothing but the bubble and max_font_size."""
    free = copy.copy(region)
    free.size_cap = 0
    return p._set_text(None, free, region.translated_text, (255, 255, 255), None, scaled=False).size


@pytest.mark.parametrize("page_name", ["sample_page", "sample_page2"])
@pytest.mark.parametrize("largest, readable", [(64, 11), (120, 50)])  # (the defaults; room above the page's caps)
def test_at_200_percent_the_bubbles_still_hold_the_lines_and_the_flags_are_as_at_100(settings, page_name, request,
                                                                                       largest, readable):
    image = request.getfixturevalue(page_name)
    root = settings.state_dir.parent
    _p, full = _lettered(Settings(state_dir=root / "full", max_font_size=largest, readable_font_size=readable), image)
    large_settings = Settings(state_dir=root / "large", text_scale=2.0, max_font_size=largest,
                              readable_font_size=readable)
    p, large = _lettered(large_settings, image)
    before = {(r.x0, r.y0): r for r in full.translated}
    now = {(r.x0, r.y0): r for r in large.translated}
    assert set(now) == set(before) and now
    for key, r in now.items():
        assert before[key].font_size <= r.font_size <= min(largest, _room(p, r))  # never past its bubble
        assert r.flags == before[key].flags  # the review: as at 100 % (the "small" size is measured unscaled)
        assert r.size_cap == before[key].size_cap  # the page's sizes measured at 100 %
    grown = [k for k in now if now[k].font_size > before[k].font_size]
    if largest == 64:  # every line of the samples is as large as its bubble or max_font_size allows already
        assert grown == [] and np.array_equal(np.asarray(large.image), np.asarray(full.image))
    else:  # the page's caps held lines back: they grow, up to what the bubble holds
        assert grown and not np.array_equal(np.asarray(large.image), np.asarray(full.image))
    if readable == 50:  # (lines flagged "small" at 100 % stay flagged, and no other is)
        assert any("small" in r.flags for r in now.values())


def test_at_200_percent_a_line_the_page_held_back_grows_up_to_its_bubble(settings, sample_page):
    p, res = _lettered(settings, sample_page)
    region = max(res.translated, key=lambda r: r.font_size)
    region.size_cap, region.tag = 20, ""
    held = p._set_text(None, region, region.translated_text, (255, 255, 255), None).size
    settings.text_scale = 2.0  # (the pipeline shares the reader's settings)
    lifted = p._set_text(None, region, region.translated_text, (255, 255, 255), None).size
    assert held == 20 and lifted == min(40, _room(p, region))


def test_at_200_percent_the_largest_size_is_twice_what_fits_within_max_font_size(settings, monkeypatch):
    settings.text_scale = 2.0
    p = Pipeline(settings, ocr=None, translator=None)
    from taslation import pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "letter_text", lambda *a, **k: pytest.fail("measured over 100 %"))
    assert p._scaled_top(None, "Hi", None, 20, (255, 255, 255), None, "") == 40
    assert p._scaled_top(None, "Hi", None, 40, (255, 255, 255), None, "") == settings.max_font_size
    mask = np.full((200, 400), 255, np.uint8)
    full = Pipeline(Settings(state_dir=settings.state_dir.parent / "full"), ocr=None, translator=None)
    assert p.set_size(mask, "A few words", "bubble", (0, 0, 400, 200), 0, 0) == \
        full.set_size(mask, "A few words", "bubble", (0, 0, 400, 200), 0, 0)  # the review size: not scaled up
