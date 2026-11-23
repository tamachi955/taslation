"""See-through mode's side panes: where they go beside the page (never over it), how wide they are, their pictures
and the controls' hit boxes (`taslation.panes`); on the Tk side what they say, what a click does, the indicators'
switch kept in the settings file, and the window put aside shown again for a dialog of its own (`ui.seethrough`).
Synthetic sizes and fake windows only."""

from types import SimpleNamespace

import numpy as np
import pytest

from taslation import config
from taslation import panes as pn
from taslation.config import Settings
from taslation.ui import seethrough as ui

FRAME = (1904, 946)  # a 1904 x 1024 window's client area under a browser's bars, as the stand-in tools have it
SPREAD = (235, 0, 1669, 946)  # a spread on it (the ground some 235 px each side)
COVER = (614, 0, 1290, 946)  # a single page
BAND = (142, 832)  # the steady band: the capture area less its top 15 % and bottom 12 %


def controls():
    return [pn.Row("translate", "Translate"), pn.Row("auto", "Auto", "toggle", on=True),
            pn.Row("language", "English", "choice"), pn.Row("lettering", "Lettering (F9)", "toggle", on=True),
            pn.Row("indicators", "Indicators", "toggle", on=True), pn.Row("area", "Set area..."),
            pn.Row("settings", "Settings..."), pn.Row("window", "TASlation window"), pn.Row("quit", "Quit")]


def words():
    return [pn.Row("", "This page: 3 of 12 lines", "text"),
            pn.Row("", "Translated 12 bubbles; the page took 4.1 s and every line was asked of the model once.",
                   "text"),
            pn.Row("", "Translator: on the GPU", "text")]


def pane(rows, size, page, dpi=96):
    left_room, right_room = pn.rooms(size, page, dpi)
    return pn.width_for(rows, "en", dpi, left_room), pn.width_for(rows, "en", dpi, right_room)


# ------------------------------------------------------------------ where they go
@pytest.mark.parametrize("page", [SPREAD, COVER], ids=["spread", "cover"])
def test_the_panes_hug_the_page_on_its_ground_and_never_cover_it(page):
    left_w = pn.width_for(controls(), "en", 96, pn.rooms(FRAME, page, 96)[0])
    right_w = pn.width_for(words(), "en", 96, pn.rooms(FRAME, page, 96)[1])
    assert left_w is not None and right_w is not None
    left = pn.render(controls(), left_w, "en", 96, pn.DARK)
    right = pn.render(words(), right_w, "en", 96, pn.DARK)
    box_left, box_right = pn.place(FRAME, page, BAND, left.size, right.size, 96)
    assert box_left is not None and box_right is not None
    for box in (box_left, box_right):
        assert pn.overlap(box, page) == 0  # (not a pixel of the page)
        assert 0 <= box[0] and box[2] <= FRAME[0] and BAND[0] <= box[1] and box[3] <= BAND[1]
    assert box_left[2] == page[0] - pn.GAP and box_right[0] == page[2] + pn.GAP  # (beside the page, GAP from it)
    assert box_left[0] >= pn.GAP and FRAME[0] - box_right[2] >= pn.GAP  # (and at least GAP from the frame's edge)
    assert (box_left[2] - box_left[0], box_left[3] - box_left[1]) == left.size


def test_a_pane_hides_where_its_ground_is_too_narrow_or_the_band_too_short():
    need = pn.width_for(controls(), "en", 96)
    narrow = (need + 2 * pn.GAP - 1, 0, FRAME[0] - 300, FRAME[1])  # (one px short on the left)
    assert pn.width_for(controls(), "en", 96, pn.rooms(FRAME, narrow, 96)[0]) is None
    just = (need + 2 * pn.GAP, 0, FRAME[0] - 300, FRAME[1])
    width = pn.width_for(controls(), "en", 96, pn.rooms(FRAME, just, 96)[0])
    assert width == need
    picture = pn.render(controls(), width, "en", 96, pn.DARK)
    assert pn.place(FRAME, just, BAND, picture.size, None, 96)[0] is not None
    assert pn.place(FRAME, narrow, BAND, picture.size, None, 96) == (None, None)  # (place checks it too)
    short = (BAND[0], BAND[0] + picture.size[1] + 2 * pn.GAP - 1)
    assert pn.place(FRAME, just, short, picture.size, None, 96) == (None, None)
    # a page across the whole frame: no ground, no panes
    assert pn.place(FRAME, (0, 0, FRAME[0], FRAME[1]), BAND, picture.size, picture.size, 96) == (None, None)


def test_a_panes_width_is_its_widest_control_its_words_wrapped_to_the_room_left():
    need = pn.width_for(controls(), "en", 96)
    assert pn.scaled(pn.MIN_W, 96) <= need <= pn.scaled(pn.MAX_W, 96)
    assert pn.width_for(controls(), "en", 96, need - 1) is None
    assert pn.width_for(controls(), "en", 96, 10_000) == need  # (no wider than its widest row)
    # words alone: as wide as the room leaves, MAX_W at the most, MIN_W at the least
    assert pn.width_for(words(), "en", 96, 10_000) == pn.scaled(pn.MAX_W, 96)
    assert pn.width_for(words(), "en", 96, 150) == 150
    assert pn.width_for(words(), "en", 96, pn.MIN_W - 1) is None
    narrow = pn.render(words(), 150, "en", 96, pn.DARK)
    wide = pn.render(words(), 240, "en", 96, pn.DARK)
    assert narrow.size[1] > wide.size[1]  # (the long line wrapped into more lines)
    # the indicators (fill): as wide as the room lets them whatever they say, so only their height changes
    short = [pn.Row("", "Ready.", "text")]
    assert pn.width_for(short, "en", 96, 10_000) == pn.scaled(pn.MIN_W, 96)
    assert pn.width_for(short, "en", 96, 10_000, fill=True) == pn.scaled(pn.MAX_W, 96)
    assert pn.width_for(short, "en", 96, 200, fill=True) == 200
    # a long language name between the arrows is cut, not a reason to hide the pane
    long_name = [pn.Row("language", "Portuguese (Brazil) and more words", "choice")]
    least = pn.width_for(long_name, "en", 96, pn.scaled(pn.MIN_W, 96))
    assert least == pn.scaled(pn.MIN_W, 96)
    assert pn.cut(pn.font("en", 13), "Portuguese (Brazil) and more words", 60).endswith("...")


def test_the_panes_sizes_go_with_the_viewers_dpi():
    at_100 = pn.render(controls(), pn.width_for(controls(), "en", 96), "en", 96, pn.DARK)
    at_150 = pn.render(controls(), pn.width_for(controls(), "en", 144), "en", 144, pn.DARK)
    assert 1.35 < at_150.size[0] / at_100.size[0] < 1.65 and 1.35 < at_150.size[1] / at_100.size[1] < 1.65
    assert pn.rooms(FRAME, SPREAD, 144) == (SPREAD[0] - 2 * 12, FRAME[0] - SPREAD[2] - 2 * 12)


# ------------------------------------------------------------------ the pictures
def test_a_pane_is_plates_with_nothing_between_and_its_controls_are_hit_where_they_are():
    rows = controls()
    picture = pn.render(rows, pn.width_for(rows, "en", 96), "en", 96, pn.LIGHT)
    alpha = picture.bgra[..., 3]
    tops = sorted({box[1] for _name, box in picture.hits})
    assert len(tops) == len(rows)  # (one plate a row; the choice's two halves share one)
    first = next(box for name, box in picture.hits if name == "translate")
    second = next(box for name, box in picture.hits if name == "auto")
    gap_row = (first[3] + second[1]) // 2
    assert first[3] < second[1] and not alpha[gap_row].any()  # (a click there is the viewer's)
    middle = (first[0] + first[2]) // 2
    assert picture.hit(middle, (first[1] + first[3]) // 2) == "translate"
    assert picture.hit(middle, gap_row) == ""
    assert alpha[(first[1] + first[3]) // 2, middle] == pn.ALPHA
    # the language: an arrow each side, the left half the one before, the right half the next
    choice = [name for name, _box in picture.hits if name.startswith("language")]
    assert choice == ["language_prev", "language_next"]
    # premultiplied: no colour brighter than its alpha
    assert (picture.bgra[..., :3].max(axis=2) <= alpha).all()


def test_a_dim_row_takes_no_click_and_a_text_row_none_either():
    picture = pn.render([pn.Row("stop", "Stop", enabled=False), pn.Row("", "Translating...", "text")], 160, "en", 96,
                        pn.DARK)
    assert picture.hits == ()


def test_the_panes_colours_follow_the_viewers_ground():
    assert pn.colours((0, 0, 0)) is pn.DARK and pn.colours((40, 40, 40)) is pn.DARK
    assert pn.colours((255, 255, 255)) is pn.LIGHT and pn.colours((230, 230, 225)) is pn.LIGHT
    assert pn.colours(None) is pn.DARK


def test_words_without_spaces_are_broken_anywhere_and_cut_after_the_last_line():
    face = pn.font("ja", 13)
    lines = pn.wrap(face, "翻訳中です。" * 30, 120)
    assert len(lines) == pn.TEXT_LINES and lines[-1].endswith("...")
    assert all(pn._text_w(face, line) <= 120 for line in lines)


# ------------------------------------------------------------------ the Tk side
class FakeOver:
    def __init__(self, clicks=()):
        self.on = True
        self.handed = []
        self.clicks = list(clicks)

    def set_panes(self, left, right):
        self.handed.append((left, right))

    def take_clicks(self):
        out, self.clicks = self.clicks, []
        return out

    def set_on(self, on):
        self.on = on


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def fake_app(tmp_path, **more):
    settings = Settings(state_dir=tmp_path / "state", config_path=tmp_path / "taslation.toml")
    app = SimpleNamespace(settings=settings, _see_through=FakeOver(), _see_pane_memo={}, _see_clicked=[],
                          _see_language=None, _see_dpi=96, _see_ground=(FRAME, SPREAD, BAND, (20, 20, 20)),
                          auto_var=Var(True), lang_var=Var("English"), status_var=Var("Ready."), said=[],
                          busy=False)
    app.say = lambda key, **values: app.said.append(key)
    for key, value in more.items():
        setattr(app, key, value)
    return app


def test_panes_tick_hands_both_panes_beside_the_page_and_the_right_one_only_when_switched_on(tmp_path):
    app = fake_app(tmp_path)
    ui.panes_tick(app)
    left, right = app._see_through.handed[-1]
    assert left is not None and right is not None
    for bgra, box in (left, right):
        assert pn.overlap(box, SPREAD) == 0 and bgra.shape[1] == box[2] - box[0]
    ui.panes_tick(app)
    assert app._see_through.handed[-1][0][0] is left[0]  # (nothing changed: the same picture, not made again)
    app.settings.see_through_indicators = False
    ui.panes_tick(app)
    assert app._see_through.handed[-1][0] is not None and app._see_through.handed[-1][1] is None
    app._see_ground = None  # (no page on a flat ground at the last rest)
    ui.panes_tick(app)
    assert app._see_through.handed[-1] == (None, None)


def test_a_click_on_a_control_acts_on_it_and_one_between_them_on_nothing(tmp_path):
    app = fake_app(tmp_path)
    ui.panes_tick(app)
    picture = app._see_pane_memo["left"][1]
    box = dict(picture.hits)["lettering"]
    x, y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    app._see_through.clicks = [("left", x, y, 0.0)]
    ui.panes_tick(app)
    assert app._see_through.on is False and [n for _t, n in app._see_clicked] == ["lettering"]
    gap = next(b for n, b in picture.hits if n == "auto")[1] - 1
    assert ui.pane_click(app, "left", x, gap) == "" and app._see_through.on is False
    assert ui.pane_click(app, "right", x, y) == ""  # (the right pane takes no click: it never has any)
    auto = dict(picture.hits)["auto"]
    assert ui.pane_click(app, "left", auto[0] + 2, auto[1] + 2) == "auto" and app.auto_var.get() is False


def test_the_left_pane_says_stop_while_a_page_can_be_stopped(tmp_path):
    class Button:
        def __init__(self, state):
            self.state = state

        def cget(self, _key):
            return self.state

    app = fake_app(tmp_path, stop_btn=Button("disabled"))
    assert ui.left_rows(app)[0].name == "translate"
    app.stop_btn = Button("normal")
    assert ui.left_rows(app)[0].name == "stop"


def test_the_indicators_switch_is_kept_in_the_settings_file_for_the_next_starts(tmp_path):
    app = fake_app(tmp_path)
    assert Settings().see_through_indicators is True and ui.indicators_on(app)
    ui._flip_indicators(app)
    assert not ui.indicators_on(app)
    again = Settings.load(tmp_path / "taslation.toml")
    assert again.see_through_indicators is False
    ui._flip_indicators(app)
    assert Settings.load(tmp_path / "taslation.toml").see_through_indicators is True and app.said == []


def test_the_language_arrows_show_at_once_and_the_choice_is_taken_once(tmp_path):
    picked = []
    app = fake_app(tmp_path, lang_shown=Var("English"), _target_picked=lambda: picked.append(app.lang_shown.get()))
    app.after = lambda _ms, _fn: (_ for _ in ()).throw(RuntimeError("no Tk loop"))  # (a test: taken at once)
    ui._pick_language(app, 1)
    assert picked and app.lang_shown.get() != "English"


def test_the_window_put_aside_is_shown_again_for_a_dialog_of_its_own(hidden_root):
    import tkinter as tk

    dialog = tk.Toplevel(hidden_root)
    dialog.withdraw()
    dialog.transient(hidden_root)
    tip = tk.Toplevel(hidden_root)
    tip.withdraw()
    tip.overrideredirect(True)
    shown = []
    app = SimpleNamespace(_see_aside=True, _quiet_decoy=None, _opening_zoomed=False, state=lambda *a: "iconic",
                          winfo_children=lambda: [tip], deiconify=lambda: shown.append("deiconify"),
                          lift=lambda: None, focus_force=lambda: shown.append("focus"))
    ui._dialog_waits(app)
    assert shown == [] and app._see_aside  # (a tip is not a dialog)
    app.winfo_children = lambda: [tip, dialog]
    ui._dialog_waits(app)
    assert shown == ["deiconify", "focus"] and not app._see_aside
    ui._dialog_waits(app)  # (the window is the reader's again: not looked at)
    assert shown == ["deiconify", "focus"]


def test_the_pane_windows_are_layered_topmost_and_never_activated_the_right_one_click_through():
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows only")
    import ctypes

    from taslation.capture import seethrough as window

    over = window.SeeThrough.start()
    assert over is not None
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetWindowLongW.restype = ctypes.c_long
        styles = {side: user32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF for side, hwnd in over.panes.items()}
        assert set(styles) == {"left", "right"}
        for style in styles.values():
            for flag in (window.WS_EX_LAYERED, window.WS_EX_NOACTIVATE, window.WS_EX_TOPMOST, window.WS_EX_TOOLWINDOW):
                assert style & flag
        assert styles["right"] & window.WS_EX_TRANSPARENT and not styles["left"] & window.WS_EX_TRANSPARENT
        assert over.own_windows() == {over.hwnd, *over.panes.values()}
        assert not any(user32.IsWindowVisible(h) for h in over.panes.values())  # (no viewer: nothing shows)
        picture = np.zeros((20, 30, 4), np.uint8)
        over.set_panes((picture, (10, 10, 40, 30)), None)
        over.set_panes((picture, (10, 10, 40, 30)), None)  # (the same: nothing to do)
        assert over._changed == 1 and over.take_clicks() == []
    finally:
        over.close()
    assert over.panes == {}


def test_a_panes_box_is_known_to_the_tools_only_while_it_shows():
    from taslation.capture import seethrough as window

    over = window.SeeThrough()
    assert over.pane_shown("left") is None
    over._pane_shown["left"] = (1, (100, 200), (150, 300))
    assert over.pane_shown("left") == (100, 200, 250, 500)


def test_the_pane_settings_entry_is_known_to_the_settings_file():
    assert "see_through_indicators" in config.setting_names()
