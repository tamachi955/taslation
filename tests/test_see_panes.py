"""See-through mode's side panes: where they go at the capture area's outer edges (never over the page, nor near it),
how wide they are, their pictures and the controls' hit boxes - the ask-again button's square among them -, and
the shown words, which name no key and no place of the former window; on the Tk side what they say, what a click does, the
indicators' switch kept in the settings file, the Menu row in place of a way back to TASlation's window, and no hot
key held (`ui.seethrough`; the window never on the screen: tests/test_see_hidden.py); the patch under the pointer
left out (`seethrough.hovered`, `capture.seethrough`).
Synthetic sizes and fake windows only; the pointer is never moved (the window's reading of it is put in its place)."""

import re
from types import SimpleNamespace

import numpy as np
import pytest

from taslation import config
from taslation import panes as pn
from taslation import seethrough as st
from taslation.config import Settings
from taslation.ui import seethrough as ui

FRAME = (1904, 946)  # a 1904 x 1024 window's client area under a browser's bars, as the stand-in tools have it
SPREAD = (235, 0, 1669, 946)  # a spread on it (the ground some 235 px each side)
COVER = (614, 0, 1290, 946)  # a single page
BAND = (142, 832)  # the steady band: the capture area less its top 15 % and bottom 12 %


def controls():
    return [pn.Row("translate", "Translate", square="again"), pn.Row("auto", "Auto", "toggle", on=True),
            pn.Row("language", "English", "list"), pn.Row("lettering", "Lettering", "toggle", on=True),
            pn.Row("indicators", "Indicators", "toggle", on=True), pn.Row("area", "Set area..."),
            pn.Row("settings", "Settings..."), pn.Row("menu", "Menu"), pn.Row("quit", "Quit")]


def words():
    return [pn.Row("", "This page: 3 of 12 lines", "text"),
            pn.Row("", "Translated 12 bubbles; the page took 4.1 s and every line was asked of the model once.",
                   "text"),
            pn.Row("", "Translator: on the GPU", "text")]


def pane(rows, size, page, dpi=96):
    left_room, right_room = pn.rooms(size, page, dpi)
    return pn.width_for(rows, "en", dpi, left_room), pn.width_for(rows, "en", dpi, right_room)


# ------------------------------------------------------------------ where they go
def boxes_for(page, columns=None, dpi=96):
    rooms = pn.rooms(FRAME, page, dpi, columns)
    left_w = pn.width_for(controls(), "en", dpi, rooms[0])
    right_w = pn.width_for(words(), "en", dpi, rooms[1], fill=True)
    left = pn.render(controls(), left_w, "en", dpi, pn.DARK) if left_w else None
    right = pn.render(words(), right_w, "en", dpi, pn.DARK) if right_w else None
    return pn.place(FRAME, page, BAND, left.size if left else None, right.size if right else None, dpi, columns)


@pytest.mark.parametrize("columns", [None, (30, 1890)], ids=["whole frame", "an area set by hand"])
def test_the_panes_lie_at_the_areas_outer_edges_where_they_are_on_a_cover_and_on_a_spread(columns):
    first, last = columns or (0, FRAME[0])
    placed = {}
    for name, page in (("spread", SPREAD), ("cover", COVER)):
        box_left, box_right = placed[name] = boxes_for(page, columns)
        assert box_left is not None and box_right is not None
        for box in (box_left, box_right):
            assert pn.overlap(box, page) == 0  # (not a pixel of the page)
            assert BAND[0] + pn.GAP == box[1] and box[3] <= BAND[1] - pn.GAP
        assert box_left[0] == first + pn.GAP and box_right[2] == last - pn.GAP  # (GAP in from the area's edges)
        assert box_left[2] + pn.GAP <= page[0] and box_right[0] - pn.GAP >= page[2]  # (and not near the page)
    # the indicators: one width whatever they say (INDICATORS_W, or the narrower ground beside the spread less the gaps)
    width = min(pn.INDICATORS_W, pn.rooms(FRAME, SPREAD, 96, columns)[1])
    assert {b[1][2] - b[1][0] for b in placed.values()} == {width}
    assert placed["spread"] == placed["cover"]  # (a page's width moves neither)


def test_the_indicators_take_the_ground_less_the_gaps_where_it_is_narrower_than_their_width():
    page = (235, 0, FRAME[0] - 150, FRAME[1])  # (150 px of ground on the right)
    _left, box_right = boxes_for(page)
    assert box_right is not None and box_right[2] - box_right[0] == 150 - 2 * pn.GAP
    assert box_right[0] == page[2] + pn.GAP and box_right[2] == FRAME[0] - pn.GAP


def test_a_pane_hides_where_it_would_come_within_a_gap_of_the_page_or_the_band_is_too_short():
    need = pn.width_for(controls(), "en", 96)
    picture = pn.render(controls(), need, "en", 96, pn.DARK)
    just = (need + 2 * pn.GAP, 0, FRAME[0] - 300, FRAME[1])
    narrow = (need + 2 * pn.GAP - 1, 0, FRAME[0] - 300, FRAME[1])  # (one px short on the left)
    assert pn.width_for(controls(), "en", 96, pn.rooms(FRAME, just, 96)[0]) == need
    assert pn.width_for(controls(), "en", 96, pn.rooms(FRAME, narrow, 96)[0]) is None
    assert pn.place(FRAME, just, BAND, picture.size, None, 96)[0] == (pn.GAP, BAND[0] + pn.GAP, pn.GAP + need,
                                                                       BAND[0] + pn.GAP + picture.size[1])
    assert pn.place(FRAME, narrow, BAND, picture.size, None, 96) == (None, None)  # (place checks it too)
    right = (need, 80)  # the right pane: within a gap of the page by one px, then not
    assert pn.place(FRAME, (0, 0, FRAME[0] - need - 2 * pn.GAP + 1, 10), BAND, None, right, 96)[1] is None
    assert pn.place(FRAME, (0, 0, FRAME[0] - need - 2 * pn.GAP, 10), BAND, None, right, 96)[1] is not None
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
    # the indicators (fill): INDICATORS_W whatever they say, or the room when it is less, so only their height changes
    short = [pn.Row("", "Ready.", "text")]
    assert pn.width_for(short, "en", 96, 10_000) == pn.scaled(pn.MIN_W, 96)
    assert pn.width_for(short, "en", 96, 10_000, fill=True) == pn.scaled(pn.INDICATORS_W, 96) == 200
    assert pn.width_for(words(), "en", 96, 10_000, fill=True) == 200
    assert pn.width_for(short, "en", 96, 150, fill=True) == 150
    assert pn.width_for(short, "en", 144, 10_000, fill=True) == 300  # (at 150 %)
    # a long language name before the list's mark is cut, not a reason to hide the pane
    long_name = [pn.Row("language", "Portuguese (Brazil) and more words", "list")]
    least = pn.width_for(long_name, "en", 96, pn.scaled(pn.MIN_W, 96))
    assert least == pn.scaled(pn.MIN_W, 96)
    assert pn.cut(pn.font("en", 13), "Portuguese (Brazil) and more words", 60).endswith("...")


def test_the_panes_sizes_go_with_the_viewers_dpi():
    at_100 = pn.render(controls(), pn.width_for(controls(), "en", 96), "en", 96, pn.DARK)
    at_150 = pn.render(controls(), pn.width_for(controls(), "en", 144), "en", 144, pn.DARK)
    assert 1.35 < at_150.size[0] / at_100.size[0] < 1.65 and 1.35 < at_150.size[1] / at_100.size[1] < 1.65
    assert pn.rooms(FRAME, SPREAD, 144) == (SPREAD[0] - 2 * 12, FRAME[0] - SPREAD[2] - 2 * 12)
    assert pn.rooms(FRAME, SPREAD, 96, (100, 1800)) == (SPREAD[0] - 100 - 16, 1800 - SPREAD[2] - 16)
    left, right = boxes_for(COVER, dpi=144)
    assert left is not None and left[0] == 12 and right is not None and right[2] == FRAME[0] - 12  # (gaps at 150 %)


# ------------------------------------------------------------------ the pictures
def test_a_pane_is_plates_with_nothing_between_and_its_controls_are_hit_where_they_are():
    rows = controls()
    picture = pn.render(rows, pn.width_for(rows, "en", 96), "en", 96, pn.LIGHT)
    alpha = picture.bgra[..., 3]
    tops = sorted({box[1] for _name, box in picture.hits})
    assert len(tops) == len(rows)  # (one plate a row)
    first = next(box for name, box in picture.hits if name == "translate")
    second = next(box for name, box in picture.hits if name == "auto")
    gap_row = (first[3] + second[1]) // 2
    assert first[3] < second[1] and not alpha[gap_row].any()  # (a click there is the viewer's)
    middle = (first[0] + first[2]) // 2
    assert picture.hit(middle, (first[1] + first[3]) // 2) == "translate"
    assert picture.hit(middle, gap_row) == ""
    assert alpha[(first[1] + first[3]) // 2, middle] == pn.ALPHA
    # the language: one plate a click opens the list on, its words from the left, an arrowhead at its right end
    language = [(name, box) for name, box in picture.hits if name.startswith("language")]
    assert [name for name, _box in language] == ["language"]
    box = language[0][1]
    assert box[0] == 0 and box[2] == picture.size[0]  # (the whole plate)
    mid = (box[1] + box[3]) // 2
    mark = pn.scaled(pn.LIST_MARK_PX, 96)
    end = picture.size[0] - pn.PAD
    # (the arrowhead's ink is drawn opaque on the plate, whose alpha is ALPHA: there at the plate's end)
    assert (picture.bgra[mid, end - mark:end + 1, 3] == 255).any() and picture.bgra[mid, end + 2, 3] == pn.ALPHA
    # premultiplied: no colour brighter than its alpha
    assert (picture.bgra[..., :3].max(axis=2) <= alpha).all()


def test_the_ask_again_button_is_a_square_plate_at_the_first_rows_end_drawn_as_a_circular_arrow():
    rows = controls()
    width = pn.width_for(rows, "en", 96)
    picture = pn.render(rows, width, "en", 96, pn.DARK)
    hits = dict(picture.hits)
    again, first = hits["again"], hits["translate"]
    side = again[3] - again[1]
    assert again[2] == width and again[2] - again[0] == side  # (square, the row's height, at its right end)
    assert again[1] == first[1] and first[2] == width - side - pn.ROW_GAP  # (the row's plate shortened for it)
    alpha = picture.bgra[..., 3]
    middle_y = (again[1] + again[3]) // 2
    assert not alpha[middle_y, first[2]:again[0]].any()  # (nothing between the two plates: the viewer's)
    assert picture.hit(again[0] + side // 2, middle_y) == "again" and picture.hit(first[2] - 2, middle_y) == "translate"
    # the glyph: a ring of the text's colour round an empty middle, open at its top right, with an arrow's head
    mark = np.asarray(pn.glyph("again", side, pn.DARK.text, 96))[..., 3]
    assert mark.shape == (side, side)
    c = side / 2

    def on_ring(degrees):  # (the ring's middle line, degrees from three o'clock, clockwise on the screen)
        t = np.radians(degrees)
        return mark[int(c + side * 0.23 * np.sin(t)), int(c + side * 0.23 * np.cos(t))]

    assert mark[int(c), int(c)] == 0  # (an empty middle)
    ring = [on_ring(d) for d in range(0, 360, 5)]
    assert 0.6 < sum(a > 128 for a in ring) / len(ring) < 0.95  # (a ring, but not a closed one)
    assert all(on_ring(d) > 128 for d in (0, 90, 180)) and min(on_ring(d) for d in range(285, 325, 5)) < 64
    square = picture.bgra[again[1]:again[3], again[0]:again[2]]
    assert (square[..., :3].max(axis=2) > 200).sum() > side  # (the glyph drawn in on its plate, light on dark)
    # the button wants its room: a row with it needs its square and a gap more
    plain = pn.width_for([pn.Row("translate", "Translate a long way round")], "en", 96)
    more = pn.width_for([pn.Row("translate", "Translate a long way round", square="again")], "en", 96)
    assert more == plain + side + pn.ROW_GAP
    with pytest.raises(ValueError):
        pn.glyph("star", 20, (0, 0, 0), 96)


def test_the_ask_again_button_dim_takes_no_click():
    picture = pn.render([pn.Row("translate", "Translate", square="again", square_enabled=False)], 160, "en", 96,
                        pn.DARK)
    assert [name for name, _box in picture.hits] == ["translate"]


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


# ------------------------------------------------------------------ the right pane by its rule
def foot(progress="", mode="Editing: turn pages with the keys", viewer="Viewer: Book"):
    return [pn.Row("", progress, "text", lines=2, alike=("This page: 888 of 888 lines",)),
            pn.Row("", mode, "text", lines=2, alike=("Editing: turn pages with the keys", "Reader mode")),
            pn.Row("", "Translator: on the GPU", "text", lines=2,
                   alike=("Translator: not loaded yet", "Translator: on the processor; OCR: on the GPU")),
            pn.Row("", viewer, "text", lines=1),
            pn.Row("", "English · Book", "text", lines=1, spare=True)]


def column(top, changing, rows, height, drop=()):
    return pn.render_column(top, changing, rows, 200, height, "en", 96, pn.DARK, drop)


def test_the_right_pane_s_foot_stands_at_the_column_s_bottom_its_rows_at_their_places_whatever_is_said():
    height = pn.column_height(FRAME, BAND, 96)
    assert height == BAND[1] - BAND[0] - 2 * pn.GAP
    quiet = column([], [], foot(), height)
    busy = column([], [pn.Row("", "Reading the page...", "text"), pn.Row("", "Translating... " * 6, "text")],
                  foot("This page: 3 of 8 lines", "Reader mode", "Viewer: Another book"), height)
    block = [pn.Row("copy_source", "Copy the Japanese"), pn.Row("", "やあ、元気？", "text", lang="ja", lines=5)]
    with_block = column(block, [pn.Row("", "Translated 8 bubbles.", "text")], foot("This page: 8 of 8 lines"), height)
    for picture in (quiet, busy, with_block):
        assert picture.size == (200, height) and len(picture.foot) == 5 and picture.foot[-1][3] == height
    assert quiet.foot == busy.foot == with_block.foot  # (each row at its place, whatever it says)
    first = quiet.foot[0]
    assert not quiet.bgra[first[1]:first[3], :, 3].any()  # (no page filling in: the row's room kept, empty)
    assert busy.bgra[first[1]:first[3], :, 3].any()
    assert not quiet.bgra[:first[1], :, 3].any()  # (nothing changing: nothing above the foot)
    assert with_block.hit(10, 5) == "copy_source"  # (the bubble's block from the top, its plate taking a click)
    assert [name for name, _box in with_block.hits] == ["copy_source"]  # (the foot takes no click: the viewer's)
    ready = [pn.Row("", "Ready.", "text")]
    assert column([], ready, [], height).size[1] == pn._measure(ready, 200, "en", 96)[0][3]  # (no foot: as its rows)


def test_the_changing_rows_that_do_not_fit_go_in_the_order_given_and_the_spare_foot_row_where_the_band_is_short():
    gap = pn.scaled(pn.ROW_GAP, 96)
    rows = [pn.Row("", f"Line {i}.", "text") for i in range(8)]
    row_h = pn._measure(rows[:1], 200, "en", 96)[0][3]
    lasting = foot()[:4]  # (no spare row: the foot as it is whatever the height)
    feet = pn._stacked(pn._measure(lasting, 200, "en", 96), gap)
    height = feet + 5 * (row_h + gap) + row_h // 2  # (room for five of the eight)
    cut = column([], rows, lasting, height, drop=(5, 2))
    kept = [rows[i] for i in (0, 1, 3, 4, 6)]  # (5 and 2 first, then the newest: 7)
    assert np.array_equal(cut.bgra, column([], kept, lasting, height).bgra) and len(cut.foot) == 4
    assert not np.array_equal(cut.bgra, column([], rows[:5], lasting, height).bgra)
    feet = pn._stacked(pn._measure(foot(), 200, "en", 96), gap)
    assert np.array_equal(column([], rows, foot(), 5000).bgra[:200], column([], rows, foot(), 6000).bgra[:200])
    short = int(feet / pn.FOOT_SHARE) - 1  # (the foot would take more than its share: the spare row goes)
    picture = column([], [], foot(), short)
    assert len(picture.foot) == 4 and picture.foot[-1][3] == short
    tall = [pn.Row("", "やあ" * 80, "text", lang="ja", lines=5)]
    assert column(tall, [], foot(), feet + 10) is None  # (the block does not fit with the foot: none)


def test_the_right_pane_s_foot_says_the_mode_the_translator_s_place_the_viewer_the_language_and_the_book(tmp_path):
    from taslation.capture import WindowInfo

    app = fake_app(tmp_path, book_var=Var("Sample"))
    assert [r.text for r in ui.foot_rows(app)] == ["", "Translator: not loaded yet", "Viewer: none chosen",
                                                   "English · Sample"]  # (TASlation's window shown: no mode)
    app._see_hidden, app.role_var, app._compute_where = True, Var("translator"), "gpu"
    rows = ui.foot_rows(app)
    assert [r.text for r in rows][1:3] == ["Editing: turn pages with the keys", "Translator: on the GPU"]
    assert rows[-1].spare and not any(r.spare for r in rows[:-1]) and all(r.alike for r in rows[:3])
    app.role_var.set("reader")
    assert ui.foot_rows(app)[1].text == "Reader mode"
    app.pipeline = SimpleNamespace(ocr=SimpleNamespace(placement=SimpleNamespace(device="cpu", why="room")))
    assert ui.foot_rows(app)[2].text == "Translator: on the GPU; OCR: on the processor"
    app.pipeline.ocr.placement = SimpleNamespace(device="gpu", why="room")
    assert ui.foot_rows(app)[2].text == "Translator: on the GPU"  # (the readers with it: said once)
    app.pipeline.ocr.placement = SimpleNamespace(device="cpu", why=ui.READERS_NOT_PLACED)
    assert ui.foot_rows(app)[2].text == "Translator: on the GPU"  # (not judged yet)
    app._fill = SimpleNamespace(final=None, states=["lettered", "read", "skipped"], filled=1)
    assert ui.foot_rows(app)[0].text == "This page: 1 of 2 lines"
    app.selected = WindowInfo(hwnd=5, title="Viewer window", class_name="Reader", pid=5, rect=(0, 0, 800, 600))
    app.book_var = Var("A book whose name goes on and on " * 4 + "Volume 9")
    rows = ui.foot_rows(app)
    fits = pn.fits_line("en", 96)
    assert rows[3].text == "Viewer: Viewer window" and "…" in rows[4].text and rows[4].text.endswith("9")
    assert fits(rows[4].text) and rows[4].text.startswith("English · A book")


def test_the_oldest_and_least_urgent_changing_rows_are_left_out_first_the_warnings_last(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ui.time, "monotonic", lambda: now[0])
    app = SimpleNamespace()
    old, new = pn.Row("", "Old.", "text"), pn.Row("", "New.", "text")
    warn = pn.Row("", "The translator is not running.", "text", warn=True)
    assert ui._drop_order(app, [old]) == (0,)
    now[0] = 105.0
    assert ui._drop_order(app, [warn, old, new]) == (1, 2, 0)
    assert ui._drop_order(app, [warn, new, old]) == (2, 1, 0)  # (by when each was first said, not by its place)
    now[0] = 110.0
    ui._drop_order(app, [new])
    assert set(app._see_row_seen) == {"New."}  # (one gone is forgotten: said again, it is new)


# ------------------------------------------------------------------ the Tk side
class FakeOver:
    def __init__(self, clicks=()):
        self.on = True
        self.handed = []
        self.clicks = list(clicks)
        self.hover = None  # (key, box) of the patch left out under the pointer
        self.key = None  # the key of the set the last look chose
        self.delay_ms = None

    def set_panes(self, left, right):
        self.handed.append((left, right))

    def hovered(self):
        return self.hover

    def look_key(self):
        return self.key

    def set_hover_delay(self, ms):
        self.delay_ms = ms

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
                          _see_dpi=96,
                          _see_ground=(FRAME, SPREAD, BAND, (20, 20, 20), (0, FRAME[0])),
                          auto_var=Var(True), lang_var=Var("English"), status_var=Var("Ready."), said=[],
                          busy=False, last_result=object(), asked=[])
    app.say = lambda key, **values: app.said.append(key)
    app.translate_now = lambda: app.asked.append("translate_now")
    for key, value in more.items():
        setattr(app, key, value)
    return app


def test_panes_tick_hands_both_panes_beside_the_page_and_the_right_one_only_when_switched_on(tmp_path):
    app = fake_app(tmp_path)
    ui.panes_tick(app)
    left, right = app._see_through.handed[-1]
    assert left is not None and right is not None
    for bgra, box, *_plates in (left, right):
        assert pn.overlap(box, SPREAD) == 0 and bgra.shape[1] == box[2] - box[0]
    assert right[2] == ()  # (no bubble under the pointer yet: the right pane has no plate to take a click)
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


class Button:
    def __init__(self, state):
        self.state = state

    def cget(self, _key):
        return self.state


def test_the_left_pane_says_stop_while_a_page_can_be_stopped(tmp_path):
    app = fake_app(tmp_path, stop_btn=Button("disabled"))
    assert ui.left_rows(app)[0].name == "translate"
    app.stop_btn = Button("normal")
    assert ui.left_rows(app)[0].name == "stop" and ui.left_rows(app)[0].square == "again"  # (the arrow stays)


def test_a_click_on_the_circular_arrow_has_the_page_translated_again_as_translate_again_does(tmp_path):
    # (not `translate_now`, which answers from the cache: the window's Translate again, whose lines are asked of the
    # translator anew and replace the cache's, in the Reader role too; its question takes the keys)
    app = fake_app(tmp_path)
    app.retranslate_page = lambda: app.asked.append(("retranslate_page", app._see_asked))
    ui.panes_tick(app)
    picture = app._see_pane_memo["left"][1]
    box = dict(picture.hits)["again"]
    app._see_through.clicks = [("left", (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, 0.0)]
    ui.panes_tick(app)
    (name, when), = app.asked
    assert name == "retranslate_page" and when > 0 and [n for _t, n in app._see_clicked] == ["again"]
    ui.PANE_ACTIONS["translate"](app)
    assert app.asked[-1] == "translate_now"  # (Translate itself: the page from the cache when it is there)


def test_translate_again_reads_the_page_anew_in_the_reader_role_too(monkeypatch):
    from taslation.ui import translator

    started, queued = [], []
    result = SimpleNamespace(original="frame", units=[])
    window = SimpleNamespace(busy=False, pipeline=SimpleNamespace(), last_result=result,
                             _page_to_work_on=lambda: True, role_var=Var("reader"),
                             _start_translate=lambda image, **k: started.append((image, k)),
                             _jobs=SimpleNamespace(put=queued.append),
                             _kept_after_reading=lambda kind, r: (SimpleNamespace(before=None), lambda: None))
    monkeypatch.setattr(translator.boxes, "ask", lambda *a, **k: True)
    translator.TranslatorMixin.retranslate_page(window)
    (image, options), = started
    assert image == "frame" and options["again"] is result and options["complete"] is True


def test_the_circular_arrow_is_dim_until_a_page_was_lettered_and_while_the_windows_translate_is(tmp_path):
    app = fake_app(tmp_path, last_result=None)
    assert ui.left_rows(app)[0].square_enabled is False
    ui.panes_tick(app)
    assert "again" not in dict(app._see_pane_memo["left"][1].hits)  # (and takes no click)
    app.last_result = object()
    assert ui.left_rows(app)[0].square_enabled is True
    app.translate_btn = Button("disabled")  # (a job at work for a while: the window greys its Translate)
    assert ui.left_rows(app)[0].square_enabled is False
    app.translate_btn = Button("normal")
    assert ui.left_rows(app)[0].square_enabled is True


def test_the_right_pane_shows_the_window_s_words_as_they_are(tmp_path):
    """Nothing is left out of a line the right pane shows: the words name the panes' controls and the Menu's entries,
    no key (`test_no_shown_word_names_a_key_or_a_place_of_the_former_window`)."""
    line = "Stopped: this page was not translated, and nothing of it was kept. Translate translates it again."
    app = fake_app(tmp_path, status_var=Var(line))
    assert line in [r.text for r in ui.right_rows(app)[0]]
    app.status_var = Var("Read 4 bubbles - 3 worth a look (with Reader mode off, Menu > Review...).")
    assert "Read 4 bubbles - 3 worth a look (with Reader mode off, Menu > Review...)." in [
        r.text for r in ui.right_rows(app)[0]]
    assert not hasattr(pn, "without_keys") and not hasattr(pn, "pane_words")


def test_see_through_mode_holds_no_hot_key_but_insert(tmp_path, monkeypatch):
    import importlib.util
    import inspect
    import re

    assert importlib.util.find_spec("taslation.capture.overlay") is None  # (the hot keys' module is gone)
    assert "RegisterHotKey" not in inspect.getsource(ui)
    calls = re.findall(r"_user32\.RegisterHotKey\(([^)]*)\)", inspect.getsource(ui.window))
    assert calls == ["self.hwnd, HOTKEY_ID, MOD_NOREPEAT, VK_INSERT"]  # (Insert alone, Add area: `test_see_add`)
    assert ui.window.VK_INSERT == 0x2D and "SetWindowsHookEx" not in inspect.getsource(ui.window)
    monkeypatch.setattr(ui.window, "viewer_dpi", lambda hwnd: 96)
    app = fake_app(tmp_path, selected=SimpleNamespace(hwnd=1234), _see_memo=[])
    app._see_through.follow = lambda hwnd: None
    monkeypatch.setattr(ui, "present", lambda app: None)
    ui.tick(app)
    for name in ("HOTKEY", "HOTKEY_VK", "_hotkey", "HotKeys"):
        assert not hasattr(ui, name)
    assert [r.text for r in ui.left_rows(app) if r.name == "lettering"] == ["Lettering"]


def test_the_indicators_switch_is_kept_in_the_settings_file_for_the_next_starts(tmp_path):
    app = fake_app(tmp_path)
    assert Settings().see_through_indicators is True and ui.indicators_on(app)
    ui._flip_indicators(app)
    assert not ui.indicators_on(app)
    again = Settings.load(tmp_path / "taslation.toml")
    assert again.see_through_indicators is False
    ui._flip_indicators(app)
    assert Settings.load(tmp_path / "taslation.toml").see_through_indicators is True and app.said == []


def test_a_language_clicked_in_the_list_is_taken_at_once_and_the_one_in_force_changes_nothing(tmp_path):
    picked, asked = [], []
    app = fake_app(tmp_path, lang_shown=Var("English"), _target_picked=lambda: picked.append(app.lang_shown.get()),
                   _plan=lambda language: None)
    ui.take_language(app, "English")  # (the language in force: nothing happens)
    assert picked == [] and app.lang_shown.get() == "English"
    ui.take_language(app, "German")
    assert picked == ["German"]  # (at once: no wait, no other click needed)
    app._plan = lambda language: asked.append(language) or "offer"  # (its model not there: the offer's dialog)
    ui.take_language(app, "Korean")
    assert picked[-1] == "Korean" and asked == ["Korean"] and app._see_asked > 0  # (that dialog takes the keys)
    # the row: the language in force, by its name in the window's language, a plate that opens the list
    row = next(r for r in ui.left_rows(app) if r.name == "language")
    assert row.kind == "list" and row.text == "English"
    assert "language" in ui.PANE_ACTIONS and not any(k.startswith("language_") for k in ui.PANE_ACTIONS)
    assert not hasattr(ui, "LANGUAGE_SETTLE_MS") and not hasattr(ui, "_pick_language")


def test_the_left_pane_ends_with_menu_and_quit_and_offers_no_way_to_taslations_window(tmp_path):
    app = fake_app(tmp_path)
    names = [r.name for r in ui.left_rows(app)]
    assert names[-4:] == ["area", "settings", "menu", "quit"] and "window" not in names
    assert "window" not in ui.PANE_ACTIONS and not hasattr(ui, "window_up") and not hasattr(ui, "aside")
    opened = []
    app.set_area = lambda: opened.append(("area", app._see_asked))
    app.open_settings = lambda: opened.append(("settings", app._see_asked))
    ui.PANE_ACTIONS["area"](app)
    ui.PANE_ACTIONS["settings"](app)
    assert [n for n, _t in opened] == ["area", "settings"] and all(t > 0 for _n, t in opened)  # (asked for)


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


def test_shown_again_or_moved_the_windows_go_under_an_open_menu_of_this_process_never_above_it(monkeypatch):
    import inspect
    import os

    from taslation.capture import seethrough as window

    if not window.IS_WINDOWS:
        pytest.skip("Windows only")
    me = os.getpid()
    menus = [(41, me + 1, True), (42, me, False), (43, me, True), (44, me, True)]  # (top first: a submenu over its
    # menu; another program's menu above them, a hidden one of this process's)
    calls = []

    def find(parent, after, cls, title):
        assert parent is None and cls == window.MENU_CLASS and title is None
        order = [m[0] for m in menus]
        i = 0 if after is None else order.index(after) + 1
        return order[i] if i < len(order) else None

    def owner(hwnd, pid):
        pid._obj.value = next(m[1] for m in menus if m[0] == hwnd)
        return 1

    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        FindWindowExW=find, GetWindowThreadProcessId=owner,
        IsWindowVisible=lambda hwnd: next(m[2] for m in menus if m[0] == hwnd),
        SetWindowPos=lambda *a: calls.append(a) or 1))
    assert window.own_menu() == 44  # (the lowest of this process's on the screen)
    window._raise(5)
    window._raise(6, (100, 200))
    flags = window.SWP_NOSIZE | window.SWP_NOACTIVATE
    assert calls == [(5, 44, 0, 0, 0, 0, flags | window.SWP_NOMOVE), (6, 44, 100, 200, 0, 0, flags)]
    menus[:] = [(41, me + 1, True)]  # (the menu ended: the top of the topmost windows again)
    calls.clear()
    window._raise(5)
    assert window.own_menu() == 0 and calls == [(5, window.HWND_TOPMOST, 0, 0, 0, 0, flags | window.SWP_NOMOVE)]
    # the lettering's window and both panes come into the order only through `_raise`
    assert inspect.getsource(window).count("_user32.SetWindowPos(") == 1


def test_the_lettering_shown_again_goes_under_the_panes_on_show(monkeypatch):
    """While editing the lettering's window takes the mouse over the whole page: shown again (the Lettering switched
    back on, say), it goes to the top of the topmost windows and the panes on show are put back over it, so that
    their controls still take a click (`SeeThrough._raise_under_panes`; a pane hidden is left as it is)."""
    import inspect

    from taslation.capture import seethrough as window

    raised = []
    monkeypatch.setattr(window, "_raise", lambda hwnd, at=None: raised.append(hwnd))
    shown = SimpleNamespace(hwnd=5, panes={"left": 6, "right": 7},
                            _pane_shown={"left": (1, (40, 80), (180, 400)), "right": None})
    window.SeeThrough._raise_under_panes(shown)
    assert raised == [5, 6]
    shown._pane_shown["right"] = (2, (1400, 80), (200, 700))
    raised.clear()
    window.SeeThrough._raise_under_panes(shown)
    assert raised == [5, 6, 7]
    assert "self._raise_under_panes()" in inspect.getsource(window.SeeThrough._draw)


def test_the_pane_settings_entry_is_known_to_the_settings_file():
    assert "see_through_indicators" in config.setting_names()


# ------------------------------------------------------------------ the shown words: no key or place that is gone
# what the former window had and the one mode has not, as the English texts named it
GONE = ("To list", "Viewer list", "Page menu", "Translator role", "Series field", "toolbar", "tool bar", "menu bar",
        "menubar", "TASlation's window", "TASlation window", "full screen", '"Translate again"',
        "Translate again applies", "Translate again taken back", "Translate again made again")
F_KEY = re.compile(r"(?<![A-Za-z0-9])F(?:1[0-2]|[1-9])(?![0-9])")
ESC = re.compile(r"(?<![A-Za-z])(?:Esc|Échap)(?![A-Za-z])")


def _shown_texts():
    """(language, English key, text) of every string the window and its messages can show, English included."""
    from taslation import i18n, messages
    from taslation.message_texts import LANGUAGES, catalog

    keys = set().union(*(set(c) for c in i18n.CATALOGS.values()))
    for key in keys:
        yield "en", key, key
        for language, cat in i18n.CATALOGS.items():
            if key in cat:
                yield language, key, cat[key]
    for code, template in messages.TEMPLATES.items():
        yield "en", template, template
        for language in LANGUAGES:
            text = catalog(language).get(code)
            if text:
                yield language, template, text


def test_no_shown_word_names_a_key_or_a_place_of_the_former_window():
    """In every language: no F key but the viewer's own reload key ("F5 in a browser": a key of the viewer's), no Esc
    but where the English names it too (inside the area editor and the dialogs, a key's own name); and no English
    text names the former window's lists, menus, role or bars (the one mode has the panes and the Menu)."""
    from taslation.ui import constants

    seen = 0
    for language, english, text in _shown_texts():
        seen += 1
        if english != constants.VIEWER_BLACK:
            assert not F_KEY.search(text), (language, english[:60], text)
        if not ESC.search(english):
            assert not ESC.search(text), (language, english[:60], text)
        if language == "en":
            assert not any(gone in text for gone in GONE), text
    assert seen > 15000  # (every language's catalogs were looked at)
    assert "(F5 in a browser)" in constants.VIEWER_BLACK  # (the viewer's key stays named)


# ------------------------------------------------------------------ the patch under the pointer
def test_the_patch_under_the_pointer_is_found_with_a_margin_and_kept_a_little_farther():
    boxes = [(100, 100, 200, 160), (230, 100, 300, 160)]
    grow, keep = 4, 10
    assert st.hovered(boxes, (150, 130), None, grow, keep) == 0
    assert st.hovered(boxes, (203, 130), None, grow, keep) == 0  # (within the margin: 4 px right of its last column)
    assert st.hovered(boxes, (204, 130), None, grow, keep) is None
    assert st.hovered(boxes, (208, 130), boxes[0], grow, keep) == 0  # (once on it: kept up to 10 px off)
    assert st.hovered(boxes, (209, 130), boxes[0], grow, keep) == 0
    assert st.hovered(boxes, (210, 130), boxes[0], grow, keep) is None
    assert st.hovered(boxes, (228, 130), boxes[0], grow, keep) == 1  # (beyond: the next one's margin)
    assert st.hovered(boxes, (50, 50), None, grow, keep) is None
    # the page lettered again, its box a little other: the same bubble stays hidden
    again = [(101, 99, 201, 161), boxes[1]]
    assert st.hovered(again, (206, 130), boxes[0], grow, keep) == 0


class FakeSet:
    def __init__(self, boxes):
        self.serial = 7
        self.key = 5
        self.patches = [SimpleNamespace(box=b) for b in boxes]


def watching(monkeypatch, pointer):
    """A see-through window (not started: no window, no thread) whose draws and hides are only noted, and whose
    reading of the pointer is the test's."""
    from taslation.capture import seethrough as window

    over = window.SeeThrough()
    drawn = []
    monkeypatch.setattr(over, "_draw", lambda chosen, shown, origin, size, *a: (
        drawn.append(("show", shown)), setattr(over, "_shown", (chosen.serial, shown, origin, size))))
    monkeypatch.setattr(over, "_hide", lambda why, *a, **k: (
        drawn.append(("hide", why)), setattr(over, "_shown", None)))
    over._pointer = pointer
    return over, drawn


def test_the_patch_under_the_pointer_is_left_out_and_back_once_it_has_gone_the_others_stay(monkeypatch):
    origin = (500, 300)
    chosen = FakeSet([(100, 100, 200, 160), (300, 100, 380, 160), (100, 400, 200, 460)])
    over, drawn = watching(monkeypatch, (origin[0] + 150, origin[1] + 130))
    look = (chosen, (0, 1, 2), [0.0] * 3, 1, 0.0, origin, (900, 800), True)
    over._show_look(*look)
    assert drawn[-1] == ("show", (1, 2)) and over.counts["hovers"] == 1
    over._pointer = (origin[0] + 207, origin[1] + 130)  # (off its edge, within the farther margin: still out)
    over._show_look(*look)
    assert over._shown[1] == (1, 2)
    over._pointer = (origin[0] + 260, origin[1] + 130)  # (gone from it: back)
    over._show_look(*look)
    assert drawn[-1] == ("show", (0, 1, 2)) and [n["on"] for n in over.notes if n["ev"] == "hover"] == [1, 0]
    over._pointer = None  # (no pointer to be told of)
    over._show_look(*look)
    assert over._shown[1] == (0, 1, 2)
    # a patch alone under the pointer: nothing shows while it is there
    over._pointer = (origin[0] + 150, origin[1] + 130)
    over._show_look(FakeSet([(100, 100, 200, 160)]), (0,), [0.0], 1, 0.0, origin, (900, 800), True)
    assert drawn[-1] == ("hide", "hover")


def test_over_a_pane_or_a_window_above_the_viewer_the_pointer_leaves_the_patches_as_they_are(monkeypatch):
    origin = (500, 300)
    chosen = FakeSet([(100, 100, 200, 160), (300, 100, 380, 160)])
    point = (origin[0] + 150, origin[1] + 130)
    over, drawn = watching(monkeypatch, point)
    over._pane_shown["left"] = (1, (point[0] - 20, point[1] - 20), (60, 60))  # (a pane over that place)
    look = (chosen, (0, 1), [0.0] * 2, 1, 0.0, origin, (900, 800), True)
    over._show_look(*look)
    assert drawn[-1] == ("show", (0, 1))
    over._pane_shown["left"] = None
    over._covers = [(point[0] - 5, point[1] - 5, point[0] + 5, point[1] + 5)]  # (another window over the viewer)
    over._show_look(*look)
    assert over._shown[1] == (0, 1) and over.counts["hovers"] == 0
    over._covers = []
    over._show_look(*look)
    assert over._shown[1] == (1,)


def test_the_window_reads_the_pointer_only_and_the_sizes_go_with_the_dpi(monkeypatch):
    import inspect

    from taslation.capture import seethrough as window

    source = inspect.getsource(window)
    assert "GetCursorPos" in source and "SetCursorPos" not in source and "SetWindowsHookEx" not in source
    assert "SendInput" not in source and "mouse_event" not in source
    assert st.scaled(window.HOVER_IN_PX, 144) == 6 and st.scaled(window.HOVER_OUT_PX, 144) == 15
    assert window.HOVER_OUT_PX > window.HOVER_IN_PX
