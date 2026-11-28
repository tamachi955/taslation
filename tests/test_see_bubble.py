"""See-through mode's bubble under the pointer, in the right pane (`ui.seethrough.bubble_tick`, `bubble_rows`,
`ask_bubble`): the bubble kept once the pointer has left it, until another one is under it or the viewer shows another
page; its plates (Copy the Japanese, Copy the translation, Ask again) and its words, each in its script's font; the
right pane taking a click on those plates alone (`capture.seethrough`); the patch under the pointer left out only once
the pointer has rested on it the hover delay; the patches made off the Tk thread (`Patcher`) with an exact changed
mask; TASlation's own page not drawn while its window is off the screen.
Synthetic pictures and fake windows only; the pointer is never moved, no text is written anywhere."""

import time
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import panes as pn
from taslation import seethrough as st
from taslation.config import Settings
from taslation.ui import seethrough as ui

FRAME = (1904, 946)
SPREAD = (235, 0, 1669, 946)
BAND = (142, 832)


class FakeOver:
    def __init__(self):
        self.on = True
        self.handed = []
        self.clicks = []
        self.hover = None
        self.key = None
        self.presented = []

    def set_panes(self, left, right):
        self.handed.append((left, right))

    def take_clicks(self):
        out, self.clicks = self.clicks, []
        return out

    def hovered(self):
        return self.hover

    def look_key(self):
        return self.key

    def present(self, key, size, patches, final=False, sign=None):
        self.presented.append((key, size, patches, final, sign))


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def region(box, japanese="", translation="", status="translated"):
    return SimpleNamespace(bbox=box, source_text=japanese, translated_text=translation, status=status, tag="")


def page_app(tmp_path, regions, **more):
    original = Image.new("RGB", FRAME, (20, 20, 20))
    result = SimpleNamespace(original=original, image=original, regions=regions)
    app = SimpleNamespace(settings=Settings(state_dir=tmp_path / "state", config_path=tmp_path / "taslation.toml"),
                          _see_through=FakeOver(), _see_pane_memo={}, _see_clicked=[], _see_dpi=96,
                          _see_ground=(FRAME, SPREAD, BAND, (20, 20, 20), (0, FRAME[0])), _see_bubble=None,
                          _see_reads={}, auto_var=Var(True), lang_var=Var("English"), status_var=Var("Ready."),
                          busy=False, last_result=result, _fill=None, pipeline=object(), said=[], copied=[])
    app.say = lambda key, **values: app.said.append(key)
    app._to_clipboard = lambda text, said: app.copied.append((text, said))
    for key, value in more.items():
        setattr(app, key, value)
    return app


# ------------------------------------------------------------------ which bubble the right pane shows
def test_the_bubble_stays_once_the_pointer_has_left_it_until_another_one_or_another_page(tmp_path, monkeypatch):
    a, b = region((300, 100, 400, 200), "あ", "Ah"), region((600, 100, 700, 200), "い", "Eh")
    app = page_app(tmp_path, [a, b])
    over, key = app._see_through, id(app.last_result.original)
    assert ui.bubble_target(app) is None and ui.bubble_rows(app) == []
    over.hover, over.key = (key, (305, 110, 395, 190)), key
    ui.bubble_tick(app, over)
    assert ui.bubble_target(app) == (app.last_result, a)
    over.hover = None  # (the pointer has gone to the pane: the patch shows again, the bubble stays)
    ui.bubble_tick(app, over)
    assert ui.bubble_target(app)[1] is a
    over.hover = (key, (602, 104, 698, 196))  # (another one under the pointer)
    ui.bubble_tick(app, over)
    assert ui.bubble_target(app)[1] is b
    over.hover, over.key = None, 12345  # (another page on show): gone once it has shown so long
    ui.bubble_tick(app, over)
    assert ui.bubble_target(app)[1] is b
    held = app._see_bubble
    app._see_bubble = (held[0], held[1], held[2], time.monotonic() - ui.BUBBLE_GONE_S - 0.1)
    ui.bubble_tick(app, over)
    assert app._see_bubble is None
    over.hover, over.key = (key, (305, 110, 395, 190)), key
    ui.bubble_tick(app, over)
    over.on = False  # (the lettering switched off: no bubble)
    ui.bubble_tick(app, over)
    assert app._see_bubble is None


def test_a_box_of_the_page_filling_in_has_its_translation_and_no_japanese_yet(tmp_path):
    from taslation.ui.progress import Filling

    frame = Image.new("RGB", FRAME, (20, 20, 20))
    fill = Filling(frame, frame, [(300, 100, 400, 200), (600, 100, 700, 200)])
    fill.letter(1, (600, 100, 700, 200), Image.new("RGB", (100, 100), (250, 250, 250)), "*Eh*?")
    app = page_app(tmp_path, [], last_result=None, _fill=fill)
    app._see_bubble = (id(frame), (610, 110, 690, 190), time.monotonic(), time.monotonic())
    assert ui.bubble_target(app) == (None, 1)
    rows = ui.bubble_rows(app)
    assert [r.name for r in rows if r.kind == "button"] == ["bubble_source", "bubble_translation", "bubble_again"]
    assert [r.enabled for r in rows if r.kind == "button"] == [False, True, False]  # (asked again once it is done)
    assert [r.text for r in rows if r.kind == "text"] == ["Eh?"]  # (the lettering's marks left out)
    app._see_bubble = (id(frame), (310, 110, 390, 190), time.monotonic(), time.monotonic())  # (not lettered yet)
    assert ui.bubble_target(app) is None


# ------------------------------------------------------------------ the block and its plates
def test_the_block_has_the_plates_first_then_the_japanese_and_the_translation_in_their_scripts(tmp_path, monkeypatch):
    a = region((300, 100, 400, 200), "おい、待てよ！", "*Hey*, wait!")
    app = page_app(tmp_path, [a], lang_var=Var("Korean"))
    app._see_bubble = (id(app.last_result.original), (305, 110, 395, 190), time.monotonic(), time.monotonic())
    monkeypatch.setattr(ui, "again_enabled", lambda app: True)
    rows = ui.bubble_rows(app)
    assert [(r.name, r.enabled) for r in rows[:3]] == [("bubble_source", True), ("bubble_translation", True),
                                                        ("bubble_again", True)]
    assert [(r.text, r.lang, r.lines) for r in rows[3:]] == [("おい、待てよ！", "ja", ui.BUBBLE_LINES),
                                                             ("Hey, wait!", "ko", ui.BUBBLE_LINES)]
    app.lang_var = Var("Arabic")  # (a script the panes cannot set as written: on the page alone)
    assert [r.text for r in ui.bubble_rows(app) if r.kind == "text"] == ["おい、待てよ！"]
    app.busy = True  # (a job at work: no asking again meanwhile)
    assert next(r for r in ui.bubble_rows(app) if r.name == "bubble_again").enabled is False


def test_a_bubble_from_the_cache_has_its_japanese_read_once_it_has_shown_a_moment(tmp_path):
    a = region((300, 100, 400, 200), "", "Hey")  # (the cache keeps no Japanese)
    asked = []
    app = page_app(tmp_path, [a])
    app._japanese_of = lambda result, r, then: asked.append(then)
    now = time.monotonic()
    app._see_bubble = (id(app.last_result.original), (305, 110, 395, 190), now, now)
    assert ui.bubble_japanese(app, (app.last_result, a)) == ("", "") and asked == []  # (not read at once)
    app._see_bubble = (app._see_bubble[0], app._see_bubble[1], now - ui.READ_AFTER_S - 0.1, now)
    assert ui.bubble_japanese(app, (app.last_result, a)) == ("", ui._(ui.READING)) and len(asked) == 1
    assert ui.bubble_japanese(app, (app.last_result, a))[1] == ui._(ui.READING) and len(asked) == 1  # (once)
    a.source_text = "おい"
    asked[0]("おい", "")
    assert ui.bubble_japanese(app, (app.last_result, a)) == ("おい", "")
    b = region((600, 100, 700, 200), "", "Eh")
    asked[0] = None
    app._japanese_of = lambda result, r, then: then("", "none")
    assert ui.bubble_japanese(app, (app.last_result, b)) == ("", ui._(ui.NOT_READ["none"]))


def test_the_right_pane_holds_the_block_above_the_indicators_and_hands_its_plates(tmp_path):
    a = region((300, 100, 400, 200), "おい", "Hey")
    app = page_app(tmp_path, [a])
    ui.panes_tick(app)
    assert app._see_through.handed[-1][1][2] == ()  # (no bubble yet: no plate)
    over, key = app._see_through, id(app.last_result.original)
    over.hover, over.key = (key, (305, 110, 395, 190)), key
    ui.panes_tick(app)
    _bgra, box, plates = over.handed[-1][1]
    picture = app._see_pane_memo["bubble"][1]
    assert app._see_right_used == "bubble" and len(plates) == 3
    assert [name for name, _b in picture.hits] == ["bubble_source", "bubble_translation", "bubble_again"]
    assert plates == tuple(b for _n, b in picture.hits) and plates[0][1] == 0  # (the plates at the pane's top)
    hit = dict(picture.hits)
    x, y = ((hit["bubble_source"][0] + hit["bubble_source"][2]) // 2, (hit["bubble_source"][1] + hit["bubble_source"][3]) // 2)
    over.clicks = [("right", x, y, 0.0)]
    ui.panes_tick(app)
    assert app.copied == [("おい", ui.JAPANESE_COPIED)] and [n for _t, n in app._see_clicked] == ["bubble_source"]
    x, y = ((hit["bubble_translation"][0] + hit["bubble_translation"][2]) // 2, hit["bubble_translation"][3] - 2)
    over.clicks = [("right", x, y, 0.0)]
    ui.panes_tick(app)
    assert app.copied[-1] == ("Hey", ui.TRANSLATION_COPIED)
    # the indicators switched off: the block goes with them
    app.settings.see_through_indicators = False
    ui.panes_tick(app)
    assert over.handed[-1][1] is None
    over.clicks = [("right", x, y, 0.0)]
    ui.panes_tick(app)
    assert len(app.copied) == 2


def test_where_the_block_does_not_fit_the_indicators_show_alone(tmp_path):
    a = region((300, 100, 400, 200), "おい" * 40, "Hey " * 60)
    short_band = (142, 330)  # (room for the indicators, not for the block above them)
    app = page_app(tmp_path, [a])
    app._see_ground = (FRAME, SPREAD, short_band, (20, 20, 20), (0, FRAME[0]))
    over, key = app._see_through, id(app.last_result.original)
    over.hover, over.key = (key, (305, 110, 395, 190)), key
    ui.panes_tick(app)
    assert app._see_right_used == "right" and over.handed[-1][1] is not None and over.handed[-1][1][2] == ()


def test_ask_again_asks_for_that_line_alone_and_keeps_the_answer_as_the_model_s(tmp_path):
    a = region((300, 100, 400, 200), "", "Hey")
    calls = []

    class Pipeline:
        def read_source(self, result, r):
            calls.append("read")
            r.source_text = "おい"
            return "おい"

        def ask_again(self, result, r):
            calls.append(("ask", r.source_text))
            return "Oi"

        def set_translation(self, result, r, text, edited=True):
            calls.append(("set", text, edited))
            r.translated_text = text
            return True

    jobs, posted = [], []
    app = page_app(tmp_path, [a], pipeline=Pipeline())
    app._jobs = SimpleNamespace(put=jobs.append)
    app._post = lambda kind, **data: posted.append((kind, data))
    app._go_busy = lambda: setattr(app, "busy", True)
    assert ui.ask_bubble(app, app.last_result, a) is True and app.said == ["Asking the model..."]
    assert ui.ask_bubble(app, app.last_result, a) is False  # (one at a time)
    jobs[0]()
    assert calls == ["read", ("ask", "おい"), ("set", "Oi", False)]
    assert [k for k, _d in posted] == ["result", "translate_done"]
    assert posted[0][1]["edited"] is True and posted[0][1]["quiet"] is True
    # no answer: said so, the cache as it was
    app.busy, posted[:] = False, []
    app.pipeline.ask_again = lambda result, r: ""
    ui.ask_bubble(app, app.last_result, a)
    jobs[-1]()
    assert posted == [("status", {"key": "The model gave no other translation."}), ("translate_done", {})]


# ------------------------------------------------------------------ the window's side
class FakeSet:
    def __init__(self, boxes, key=5):
        self.serial = 7
        self.key = key
        self.patches = [SimpleNamespace(box=b) for b in boxes]


def watching(monkeypatch, pointer):
    from taslation.capture import seethrough as window

    over = window.SeeThrough()
    drawn = []
    monkeypatch.setattr(over, "_draw", lambda chosen, shown, origin, size, *a: (
        drawn.append(("show", shown)), setattr(over, "_shown", (chosen.serial, shown, origin, size))))
    monkeypatch.setattr(over, "_hide", lambda why, *a, **k: (
        drawn.append(("hide", why)), setattr(over, "_shown", None)))
    over._pointer = pointer
    return over, drawn


def test_the_patch_under_the_pointer_is_left_out_once_the_pointer_has_rested_the_delay(monkeypatch):
    origin = (500, 300)
    chosen = FakeSet([(100, 100, 200, 160), (300, 100, 380, 160)], key=77)
    over, drawn = watching(monkeypatch, (origin[0] + 150, origin[1] + 130))
    over.set_hover_delay(450)
    look = (chosen, (0, 1), st.Seen(), 1, 0.0, origin, (900, 800), True)
    over._show_look(*look)
    assert drawn[-1] == ("show", (0, 1)) and over.hovered() is None and over.look_key() == 77
    assert over._hover_wait is not None  # (the looks go on while it waits)
    over._hover_wait = (over._hover_wait[0], time.monotonic() - 0.5)
    over._show_look(*look)
    assert drawn[-1] == ("show", (1,)) and over.hovered() == (77, (100, 100, 200, 160))
    over._show_look(*look)  # (left out: it stays so, no wait again)
    assert over._shown[1] == (1,)
    over._pointer = (origin[0] + 340, origin[1] + 130)  # (to the other one: the first back at once, the other waits)
    over._show_look(*look)
    assert over._shown[1] == (0, 1) and over.hovered() is None
    over._pointer = None
    over._show_look(*look)
    assert over._hover_wait is None and over._shown[1] == (0, 1)
    over.set_hover_delay(0)  # (0: at once, as before)
    over._pointer = (origin[0] + 150, origin[1] + 130)
    over._show_look(*look)
    assert over._shown[1] == (1,)


def test_the_right_pane_takes_a_click_only_while_the_pointer_is_on_one_of_its_plates(monkeypatch):
    from taslation.capture import seethrough as window

    styles = {9: window.EX_STYLE}
    monkeypatch.setattr(window, "_user32", SimpleNamespace(
        GetWindowLongW=lambda hwnd, index: styles[hwnd],
        SetWindowLongW=lambda hwnd, index, value: styles.__setitem__(hwnd, value) or 1,
        ShowWindow=lambda hwnd, cmd: 1))
    over = window.SeeThrough()
    over.panes["right"] = 9
    over._pane_shown["right"] = (3, (1000, 200), (200, 300))
    panes = {"right": (3, None, (10, 10, 210, 310), ((0, 0, 200, 27), (0, 31, 200, 58)))}
    over._right_plates((1050, 210), panes)  # (on the first plate)
    assert not styles[9] & window.WS_EX_TRANSPARENT and over._right_takes
    over._right_plates((1050, 230), panes)  # (between the plates: the viewer's)
    assert styles[9] & window.WS_EX_TRANSPARENT and not over._right_takes
    over._right_plates((1050, 240), panes)
    assert over._right_takes
    over._right_plates((1050, 240), {"right": (4, None, (10, 10, 210, 310), ((0, 0, 200, 27),))})  # (a new picture
    assert not over._right_takes  # not shown yet: its plates are not where the old ones were)
    over._right_plates((1050, 240), panes)
    over._pane_hide("right", "none")  # (hidden: click-through again)
    assert styles[9] & window.WS_EX_TRANSPARENT and not over._right_takes
    over._pane_shown["right"] = (3, (1000, 200), (200, 300))
    over._right_plates((1050, 210), {"right": (3, None, (10, 10, 210, 310), ())})  # (no plates: never)
    assert not over._right_takes


def test_both_panes_are_made_to_take_clicks_and_only_the_window_s_own_looks_set_the_style():
    import inspect

    from taslation.capture import seethrough as window

    source = inspect.getsource(window.SeeThrough._run)
    assert '("left", PANE_EX_STYLE), ("right", EX_STYLE)' in source and "PANE_CLASS" in source
    assert inspect.getsource(window).count("SetWindowLongW(") == 2  # (`_right_take` and `_edit_take` alone)
    for name in ("_right_take", "_edit_take"):
        assert "SetWindowLongW(" in inspect.getsource(getattr(window.SeeThrough, name))


# ------------------------------------------------------------------ the patches
def test_the_changed_mask_is_exact_to_one_level_of_one_channel():
    rng = np.random.default_rng(3)
    a = rng.integers(0, 255, (60, 90, 3), dtype=np.uint8)
    b = a.copy()
    b[10, 20, 2] ^= 1
    b[30, 40, 0] = 255 - b[30, 40, 0]
    b[50, 5] = 0
    mask = st.changed_mask(a, b)
    assert mask.dtype == bool and mask.shape == (60, 90)
    assert np.array_equal(mask, np.any(a != b, axis=2))
    assert np.array_equal(st.changed_mask(a[:, ::-1], b[:, ::-1]), np.any(a != b, axis=2)[:, ::-1])  # (a view)
    with pytest.raises(ValueError):
        st.changed_mask(a, b[:-1])


def test_the_patches_are_made_off_the_tk_thread_the_newest_state_of_a_page_once():
    over = FakeOver()
    patcher = ui.Patcher(over, run=False)
    frame = Image.new("RGB", (120, 80), (200, 200, 200))
    other = Image.new("RGB", (120, 80), (10, 10, 10))
    one, two = frame.copy(), frame.copy()
    one.paste((0, 0, 0), (10, 10, 30, 30))
    two.paste((0, 0, 0), (10, 10, 30, 30))
    two.paste((0, 0, 0), (60, 40, 90, 60))
    patcher.put(frame, one, False, 9)
    patcher.put(other, other, True, 9)
    patcher.put(frame, two, True, 9)  # (a newer state of the first page: it replaces the one waiting, and goes last)
    patcher.drain()
    assert [(key, len(patches), final) for key, _size, patches, final, _sign in over.presented] == [
        (id(other), 0, True), (id(frame), 2, True)]
    assert all(sign.area == (0, 0, 120, 80) for *_rest, sign in over.presented)  # (each with its page's sign)
    assert patcher.made == 2 and patcher._waiting == {}
    patcher.close()


def test_present_hands_a_copy_of_the_page_filling_in_and_the_finished_page_as_it_is(tmp_path):
    from taslation.ui.progress import Filling

    frame = Image.new("RGB", (120, 80), (200, 200, 200))
    fill = Filling(frame, frame, [(10, 10, 30, 30)])
    fill.letter(0, (10, 10), Image.new("RGB", (20, 20), (0, 0, 0)), "Hi")
    put = []
    app = SimpleNamespace(_see_through=FakeOver(), _see_memo=[], _fill=fill, last_result=None, _see_dpi=96,
                          _see_patcher=SimpleNamespace(put=lambda *a: put.append(a)))
    ui.present(app)
    assert len(put) == 1 and put[0][0] is frame and put[0][1] is not fill.page and put[0][2] is False
    ui.present(app)  # (nothing changed: nothing handed)
    assert len(put) == 1
    fill.final = fill.page.copy()
    ui.present(app)
    assert put[-1][1] is fill.final and put[-1][2] is True


# ------------------------------------------------------------------ TASlation's own page, off the screen
def test_with_the_window_off_the_screen_its_page_is_noted_and_never_drawn():
    from taslation.ui.live import LiveViewMixin

    drawn, kept, presented = [], [], []
    canvas = SimpleNamespace(set_image=lambda image: drawn.append(image), keep=lambda image: kept.append(image))
    result = SimpleNamespace(original=object(), image=object())
    app = SimpleNamespace(reading=False, _see_hidden=True, canvas=canvas, _fill=None, last_result=result, _live=None,
                          _status_follows_page=lambda: None)
    app._hidden_picture = lambda: LiveViewMixin._hidden_picture(app)
    app._fill_on_show = lambda: False
    real = ui.present
    try:
        ui.present = lambda app: presented.append(app)
        LiveViewMixin._redisplay(app)
    finally:
        ui.present = real
    assert drawn == [] and kept == [result.image] and presented == [app]
