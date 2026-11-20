"""The indicator beside the page in normal reading (`ui.side`, `ui.side_model`, `ui.side_view`), the updated mark
(`ui.seen`) and the Reader's status slot (`ui.status_slot`): where it goes (the exit side, the column or the rail, the
room kept clear, window and full screen, one page and a spread, both directions), its marks from the engine's events,
the updated mark and its brackets on a fake clock, the slot's three cases, and the setting. Made-up pages and events
(`fake_side`); no window but the test's own, nothing sent to any other."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from fake_side import Cache, bubble_boxes, fingerprint, page, result, stage, story
from fake_strip import thumb

from taslation.capture import windows as capture_windows
from taslation.config import ConfigError, Settings
from taslation.messages import Message
from taslation.ui import reading as reading_mod
from taslation.ui import side as side_mod
from taslation.ui import status_slot
from taslation.ui import translator as translator_mod
from taslation.ui.live import LiveViewMixin
from taslation.ui.preview import ImageCanvas
from taslation.ui.progress import Filling
from taslation.ui.seen import Seen, read_time
from taslation.ui.side import SideMixin
from taslation.ui.side_model import (CELL_H, COLUMN_NEEDS, COLUMN_W, FRAME, RAIL_ROOM, RAIL_W, RAIL_W_FULL, RESERVE,
                                     BacklogPace, SideModel, natural_margin, rail_marks, room_kept, screen_tip,
                                     side_layout, summary_lines)
from taslation.ui.strip import StripMixin

SPREAD, SINGLE = (1200, 860), (600, 860)


# ------------------------------------------------------------------ where it goes
def drawn(part, canvas, room=(0, 0), enlarge=False):
    """Where `ImageCanvas` draws a picture of *part* on *canvas* with *room* kept clear (its box)."""
    from taslation.ui.area import fit

    (w, h), (x, y) = fit(part, (canvas[0] - room[0] - room[1], canvas[1]), 0, enlarge)
    return (x + room[0], y, x + room[0] + w, y + h)


@pytest.mark.parametrize("rtl, side", [(True, "left"), (False, "right")])
def test_the_indicator_goes_on_the_exit_side_as_a_column_where_the_margin_holds_one(rtl, side):
    canvas = (1560, 900)
    shown = drawn(SPREAD, canvas)
    layout = side_layout("column", True, canvas, shown, rtl, full=False)
    assert layout.kind == "column" and layout.side == side
    x0, y0, x1, y1 = layout.box
    assert x1 - x0 == COLUMN_W
    if side == "left":
        assert x1 <= shown[0] - 10 and x0 >= 6  # never on the page, never on the edge
    else:
        assert x0 >= shown[2] + 10 and x1 <= canvas[0] - 6


def test_the_column_gives_way_to_the_rail_under_its_width():
    assert COLUMN_NEEDS == 141
    for margin, kind in ((COLUMN_NEEDS, "column"), (COLUMN_NEEDS - 1, "rail"), (60, "rail"), (RAIL_ROOM, "rail")):
        shown = (margin, 20, margin + 600, 880)
        assert side_layout("column", True, (2 * margin + 600, 900), shown, True, False).kind == kind, margin
    shown = (300, 20, 900, 880)
    assert side_layout("rail", True, (1200, 900), shown, True, False).kind == "rail"  # the rail only, as set


def test_the_rail_is_narrow_beside_the_page_and_wider_on_the_full_screen():
    shown = (60, 20, 660, 880)
    window = side_layout("column", True, (720, 900), shown, True, full=False)
    full = side_layout("column", True, (720, 900), shown, True, full=True)
    assert window.rail_w == RAIL_W == 6 and full.rail_w == RAIL_W_FULL == 8
    for layout in (window, full):
        x0, y0, x1, y1 = layout.box
        assert x0 + layout.rail_x + layout.rail_w == shown[0] - 10  # the rail 10 px from the page ...
        assert x1 == shown[0] - 10 + FRAME and (y0, y1) == (20, 880)  # ... its on-show outline too; as tall as the page
    right = side_layout("rail", True, (720, 900), shown, False, full=False)
    assert right.box[0] + right.rail_x == shown[2] + 10 and right.box[0] == shown[2] + 10 - FRAME


def test_a_margin_too_narrow_for_the_rail_is_widened_on_the_exit_side_only_and_never_by_the_screens():
    canvas = (610, 900)
    assert natural_margin(SINGLE, canvas, 0, False) < RAIL_ROOM
    assert room_kept("column", True, SINGLE, canvas, rtl=True) == (RESERVE, 0)
    assert room_kept("rail", True, SINGLE, canvas, rtl=False) == (0, RESERVE)
    assert room_kept("off", True, SINGLE, canvas) == (0, 0)  # off: the page as before
    assert room_kept("column", False, SINGLE, canvas) == (0, 0)  # in a whole-book run: as before
    assert room_kept("column", True, SINGLE, (900, 900)) == (0, 0)  # room enough: nothing kept
    shown = drawn(SINGLE, canvas, (RESERVE, 0))
    layout = side_layout("column", True, canvas, shown, True, False)
    assert layout.kind == "rail" and layout.box[2] <= shown[0] and layout.box[0] >= 0  # beside the page, not on it


def test_nothing_shows_when_off_in_a_run_or_without_a_picture():
    shown = drawn(SINGLE, (1200, 900))
    assert side_layout("off", True, (1200, 900), shown, True, False).kind == ""
    assert side_layout("column", False, (1200, 900), shown, True, False).kind == ""
    assert side_layout("column", True, (1200, 900), None, True, False).kind == ""


def test_on_the_right_the_indicator_stays_below_the_badge_and_the_close_button():
    shown = drawn(SINGLE, (1200, 900))
    layout = side_layout("column", True, (1200, 900), shown, False, True, top=48)
    assert layout.side == "right" and layout.box[1] == 48


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("part", [SINGLE, SPREAD])
def test_window_and_full_screen_one_page_and_spread(full, part):
    canvas = (1920, 1040) if full else (1000, 900)
    room = room_kept("column", True, part, canvas, 0, full, True)
    shown = drawn(part, canvas, room, enlarge=full)
    layout = side_layout("column", True, canvas, shown, True, full)
    margin = shown[0]
    assert layout.kind == ("column" if margin >= COLUMN_NEEDS else "rail")
    assert layout.box[2] <= shown[0]  # never over the page


# ------------------------------------------------------------------ the marks
def model_from(events):
    model = SideModel()
    for e in events:
        model.update(e.get("seq"), e.get("fingerprint", ""), e.get("thumb"), e.get("stage"), e.get("state"))
    return model


def told(**kw):
    out = []
    story(lambda kind, data: out.append((kind, data)), **kw)
    return out


def test_marks_come_from_the_stage_events_in_any_order():
    events = [d for k, d in told(pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
              if k == "page_stage"]
    model = model_from(events)
    marks = {seq: model.screens[seq].mark for seq in model.order}
    assert [marks[s] for s in (1, 6, 7, 8, 9, 10, 11, 12)] == ["done", "done", "working", "waiting", "waiting",
                                                               "missed", "missed", "working"]
    assert model.screens[10].state("translate") == "missed"  # its T bar: nothing waits for it either
    assert model.screens[8].state("translate") == "waiting"
    reversed_model = model_from(reversed(events))  # the latest event of a stage wins, whatever the order
    assert set(reversed_model.order) == set(model.order)
    model.update(9, stage="erase", state="working")  # normal reading has no erase: nothing changes
    assert model.screens[9].mark == "waiting"
    model.update(9, stage="translate", state="failed")
    assert model.screens[9].mark == "failed"
    model.update(10, stage="read", state="merged")  # a placeholder taken all the same under another number
    assert 10 not in model.screens and 10 not in model.order
    model.update(11, stage="read", state="skipped")  # nothing new on it (it was in the cache)
    assert model.screens[11].mark == "done"


def test_the_thumbnail_is_kept_small_and_only_the_first():
    model = SideModel()
    big = page(3)
    model.update(3, fingerprint(3), thumb(big), "read", "working")
    first = model.screens[3].thumb
    assert first.height <= 80 and first.width <= 58
    model.update(3, fingerprint(3), thumb(page(4)), "read", "done")
    assert model.screens[3].thumb is first


def test_another_book_numbered_from_one_again_is_told_by_its_fingerprint():
    model = SideModel()
    model.update(1, fingerprint(1), None, "read", "done")
    assert not model.renumbered(1, fingerprint(1), 36)
    assert model.renumbered(1, fingerprint(77), 36)


def test_the_rail_has_a_mark_a_screen_or_merged_runs_and_fills_its_height():
    model = model_from(d for k, d in told(pages=12, on_show=6, missed=(10, 11), working=(7,), waiting_from=8)
                       if k == "page_stage")
    model.show(6)
    marks = rail_marks(model, 600)
    assert len(marks) == 12 and all(len(m.seqs) == 1 for m in marks)
    assert [m.on_show for m in marks].index(True) == 5
    big = model_from(d for k, d in told(pages=200, on_show=150, missed=(40, 41, 120), working=(147, 148),
                                        waiting_from=149) if k == "page_stage")
    big.show(150)
    marks = rail_marks(big, 600)
    assert len(marks) < 20  # runs of one mark merged
    assert marks[0].y0 == 0 and marks[-1].y1 == 600 and all(a.y1 == b.y0 for a, b in zip(marks, marks[1:]))
    shown = [m for m in marks if m.on_show]
    assert len(shown) == 1 and shown[0].seqs == (150,) and shown[0].y1 - shown[0].y0 >= 6
    assert sum(len(m.seqs) for m in marks) == 200
    many = SideModel()  # more runs than pixels: a row each, never more marks than pixels
    for seq in range(1, 1001):
        many.update(seq, stage="translate", state="done" if seq % 2 else "waiting")
    marks = rail_marks(many, 300)
    assert len(marks) <= 300 and marks[-1].y1 == 300 and sum(len(m.seqs) for m in marks) == 1000


def test_the_summary_says_done_backlog_time_missed_and_updated_only_when_there_is_some():
    model = model_from(d for k, d in told(pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
                       if k == "page_stage")
    model.screens[2].updated = model.screens[4].updated = True
    now = 100.0
    model.set_backlog(4, 24, False, 0, now)
    lines = summary_lines(model, now)
    assert lines[0] == "Done: 6 of 12 page(s) seen."
    assert "Working on the others: 4 page(s), 24 line(s) to go." in lines
    assert not any(line.startswith("About") for line in lines)  # not trusted yet
    assert "2 turned too fast to catch: turn back to them in the viewer to have them read." in lines
    assert "2 updated since you saw them." in lines
    model.set_backlog(3, 18, False, 0, now + 4)  # six lines done
    model.set_backlog(3, 14, False, 0, now + 10)  # ten lines done, 6 s worked
    assert not any(line.startswith("About") for line in summary_lines(model, now + 10))  # under 15 s
    model.set_backlog(2, 10, False, 0, now + 20)  # fourteen lines in 16 s
    assert "About 1 min more." in summary_lines(model, now + 20)
    model.set_backlog(2, 10, True, 3, now + 21)
    lines = summary_lines(model, now + 21)
    assert "Paused for now: the pages behind wait." in lines and not any(line.startswith("About") for line in lines)
    assert "3 left out to save memory: turn back to them in the viewer to have them read." in lines
    empty = SideModel()
    assert summary_lines(empty, 0.0) == ["Done: 0 of 0 page(s) seen."]


def test_the_pace_leaves_out_paused_time_and_counts_from_the_first_line_done():
    pace = BacklogPace()
    pace.update(40, False, 0.0)
    pace.update(40, False, 30.0)  # the model loading: no line done yet, not counted
    pace.update(30, False, 40.0)
    pace.update(30, True, 50.0)
    pace.update(30, False, 500.0)  # paused all that while
    pace.update(20, False, 510.0)
    assert pace.done == 20 and pace.worked == pytest.approx(20.0)
    assert pace.left(20, 510.0) == pytest.approx(20.0)


def test_a_thumbnail_tells_how_to_read_it_in_the_viewer():
    model = model_from(d for k, d in told(pages=6, on_show=5, missed=(3,)) if k == "page_stage")
    model.show(5)
    assert "turn to it in the viewer" in screen_tip(model, 2)
    assert screen_tip(model, 5) == "Page 5: on show now."
    assert "went by before it could be taken" in screen_tip(model, 3)
    model.screens[2].updated = True
    assert screen_tip(model, 2).endswith("Its words changed since you saw it.")


# ------------------------------------------------------------------ the updated mark
BOX = [(10, 10, 60, 40), (100, 10, 160, 40), (10, 100, 60, 140)]
SIZE = (300, 400)


def test_read_time_is_one_second_and_60_ms_a_changed_character_from_2_to_8_s():
    assert read_time(0) == 2.0 and read_time(10) == 2.0 and read_time(50) == pytest.approx(4.0)
    assert read_time(500) == 8.0


def test_a_page_seen_and_changed_behind_gets_brackets_for_its_read_time_and_its_mark_goes():
    seen = Seen()
    assert seen.look(4, list(zip(BOX, ["Hello", "", "Bye"])), SIZE, 0.0, ["f4"]) == (False, False)  # first seen
    assert seen.look(5, list(zip(BOX, ["A", "B", "C"])), SIZE, 1.0) == (False, False)  # turned to 5
    assert seen.changed_in_cache(4, ["Hello", "Hi there", "Bye"])  # the Japanese bubble translated behind
    assert not seen.changed_in_cache(4, ["Hello", "*Bye*"])  # emphasis marks are not other words
    assert not seen.changed_in_cache(9, ["anything"])  # never seen lettered: nothing to compare
    updated, changed = seen.look(4, list(zip(BOX, ["Hello", "Hi there", "Bye"])), SIZE, 10.0)  # back on 4
    assert updated and changed
    assert seen.brackets(SIZE) == [BOX[1]]
    assert seen.watch.due == pytest.approx(10.0 + read_time(len("Hi there")))
    assert not seen.due(11.0) and seen.due(12.1)
    assert seen.acknowledge() == 4 and seen.brackets(SIZE) == []
    assert seen.look(5, list(zip(BOX, ["A", "B", "C"])), SIZE, 20.0)[0] is False
    assert seen.look(4, list(zip(BOX, ["Hello", "Hi there", "Bye"])), SIZE, 30.0) == (False, False)  # seen now


def test_turned_away_before_the_read_time_the_page_stays_updated():
    seen = Seen()
    seen.look(4, list(zip(BOX, ["Hello", "", "Bye"])), SIZE, 0.0)
    seen.look(5, list(zip(BOX, ["A", "B", "C"])), SIZE, 1.0)
    assert seen.look(4, list(zip(BOX, ["Hello!", "", "Bye"])), SIZE, 2.0)[0]  # back, other words in bubble 1
    seen.look(5, list(zip(BOX, ["A", "B", "C"])), SIZE, 3.0)  # away before it was read
    assert seen.changed_in_cache(4, ["Hello!", "Bye"])
    assert seen.look(4, list(zip(BOX, ["Hello!", "", "Bye"])), SIZE, 9.0)[0]  # bracketed again


def test_what_changes_on_show_and_what_is_not_words_never_counts():
    seen = Seen()
    seen.look(4, list(zip(BOX, ["Hello  there", "", "Bye"])), SIZE, 0.0)
    assert seen.look(4, list(zip(BOX, ["Hello there", "Now", "Bye"])), SIZE, 1.0) == (False, False)  # on show
    seen.look(5, list(zip(BOX, ["A", "B", "C"])), SIZE, 2.0)
    # back at another size (the viewer's window resized), with spaces and emphasis otherwise: nothing changed
    scaled = [tuple(v * 2 for v in b) for b in BOX]
    assert seen.look(4, list(zip(scaled, ["Hello\nthere", "*Now*", "Bye"])), (600, 800), 3.0) == (False, False)
    assert seen.look(6, list(zip(BOX, ["", "", ""])), SIZE, 4.0) == (None, False)  # Japanese only: no look
    assert 6 not in seen.shown


def test_hovering_a_bracketed_bubble_reads_it():
    seen = Seen()
    seen.look(4, list(zip(BOX, ["a", "b", "c"])), SIZE, 0.0)
    seen.look(5, list(zip(BOX, ["x", "y", "z"])), SIZE, 1.0)
    seen.look(4, list(zip(BOX, ["A", "B", "c"])), SIZE, 2.0)
    assert len(seen.brackets(SIZE)) == 2
    assert not seen.hovered(BOX[0], SIZE) and seen.brackets(SIZE) == [BOX[1]]
    assert seen.hovered(BOX[1], SIZE) and seen.brackets(SIZE) == []
    assert not seen.changed_in_cache(4, ["A", "B", "c"])


# ------------------------------------------------------------------ the window's side
@pytest.fixture
def no_way_to_the_viewer(monkeypatch):
    def trap(*_a, **_k):
        raise AssertionError("something was sent to the viewer")

    for module in (capture_windows, translator_mod, reading_mod):
        for name in ("post_key", "post_click", "press_key", "press_briefly", "press_page_key"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, trap)
    return trap


class Window(SideMixin, StripMixin, tk.Frame):
    """The window's parts the indicator lives with: the page area, the strip, the status bar."""

    _picture = LiveViewMixin._picture
    _result_on_show = LiveViewMixin._result_on_show
    _fill_on_show = LiveViewMixin._fill_on_show

    def __init__(self, master, rtl=True, setting="column", size=(1000, 900)):
        tk.Frame.__init__(self, master, width=size[0], height=size[1] + 30)
        self.settings = SimpleNamespace(side_indicator=setting, hover_shows="original", fingerprint_max_distance=36)
        self.cache = Cache()
        self.pipeline = SimpleNamespace(rtl=rtl, cache=self.cache, settings=self.settings,
                                        release_page_images=lambda: None)
        self.reading = False
        self.batch = None
        self._batching = False
        self._fill = self.last_result = self._live = None
        self._ordering = self._editor = self._job_frame = None
        self._fill_dirty = False
        self.busy, self._busy_shown, self._busy_since, self._progress = False, False, 0.0, ""
        self._queued, self.ready = None, True
        self.original_var = tk.BooleanVar(value=False)
        self.role_var = tk.StringVar(value="reader")
        self.canvas = ImageCanvas(self, bg="#202020")
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: size[0]), (lambda: size[1])  # as if on screen
        self.canvas.trim = False  # (the made-up page drawn whole: its bubbles on a plain ground are not cut out)
        self.canvas.pack()
        self.status_bar = tk.Frame(self)
        self.status_bar.pack(fill="x")
        self.status_label = tk.Label(self.status_bar, text="")
        self.status_label.pack(side="left")
        self.said: list = []
        self._build_page_strip()
        self._build_side()

    def status(self, text):
        self.said.append(text() if callable(text) else text)

    def say(self, key, **values):
        self.said.append(key)

    def _shows_page(self, image, frame):
        return image is frame

    def _sharper_than(self, frame, image):
        return False

    def _same_page(self, result, live):
        return live is result.original

    def _lettered(self, result, live):
        return result.image

    def _overlay_items(self):
        return []

    def _redisplay(self):
        image, overlay, outlines = self._picture()
        self.canvas.overlay, self.canvas.outlines = overlay, outlines
        self.canvas.brackets = side_mod.on_picture(self, image)
        self.canvas.set_image(image)

    def post(self, kind, data):
        noted = side_mod.before(self, kind, data)
        if kind == "page_stage":
            self._on_page_stage(data)
        side_mod.after(self, kind, data, noted)

    def show(self, image, on_show=None):
        self._live, self.last_result = image, on_show
        self._redisplay()
        self.update()


@pytest.fixture
def window(hidden_root, no_way_to_the_viewer):
    made = []

    def make(**kw):
        w = Window(hidden_root, **kw)
        hidden_root.update()
        made.append(w)
        return w

    yield make
    for w in made:
        w.destroy()


def test_the_column_shows_beside_a_spread_with_a_cell_a_screen(window):
    w = window(size=(1560, 900))
    story(w.post, pages=12, on_show=12, spread=True, missed=(10, 11), working=(7,), waiting_from=8)
    w.show(page(12, True))
    view = w._side.view
    assert view.shown and view.layout.kind == "column" and view.layout.side == "left"
    assert view.layout.box[2] <= w.canvas._shown[0]  # beside the page, never on it
    assert len(view.find_withtag("s12")) > 0 and len(view.find_withtag("marks")) >= 2  # outline and notch
    assert len(w._side.model) == 12 and view.animating  # one being worked on: its stripe moves
    w._side.model.screens[2].updated = True
    view.redraw_marks()
    assert any(view.type(i) == "polygon" for i in view.find_withtag("s2") if "marks" in view.gettags(i))


def in_view(view, seq):
    index = view.model.order.index(seq)
    top, height = view.canvasy(0), view.layout.box[3] - view.layout.box[1]
    return top <= index * CELL_H and (index + 1) * CELL_H <= top + height


def test_the_screen_on_show_is_in_view_from_the_first_placing_on_and_as_the_person_turns(window):
    w = window(size=(1560, 900))
    story(w.post, pages=40, on_show=40, waiting_from=38)
    w.show(page(40))  # (the column placed for the first time after the events came)
    view = w._side.view
    assert view.layout.kind == "column" and in_view(view, 40)
    w.post("page_on_show", {"seq": 3})  # turned back
    assert in_view(view, 3)
    w.post("page_on_show", {"seq": 4})  # in view already: the column does not move
    top = view.canvasy(0)
    assert in_view(view, 4) and view.canvasy(0) == top
    w.post("page_on_show", {"seq": 39})
    w.update()
    assert in_view(view, 39)
    top = view.canvasy(0)
    view._wheel(SimpleNamespace(delta=120))  # the wheel scrolls the column, half a cell a notch
    assert view.canvasy(0) == top - CELL_H // 2


def test_the_page_keeps_its_size_while_screens_come_and_the_rail_shows_where_the_margin_is_narrow(window):
    w = window(size=(612, 900))
    w.show(page(1))
    before = w.canvas._shown
    assert before[0] == RESERVE  # kept clear on the exit side, from the first page on
    story(w.post, pages=30, on_show=30, missed=(3, 4), working=(27,), waiting_from=28)
    w.show(page(30))
    assert w.canvas._shown == before  # the screens never change the page's size
    view = w._side.view
    assert view.layout.kind == "rail" and view.layout.box[2] <= w.canvas._shown[0]
    assert not view.animating  # the rail does not move
    w.settings.side_indicator = "off"
    w._side_setting_changed()
    assert not view.shown and w.canvas._shown[0] < before[0]  # off: the page as before


def test_a_book_read_left_to_right_has_its_indicator_on_the_right(window):
    w = window(rtl=False, size=(1100, 900))
    story(w.post, pages=9, on_show=5, missed=(8,), working=(6,), waiting_from=7)
    w.show(page(5))
    view = w._side.view
    assert view.layout.side == "right" and view.layout.box[0] >= w.canvas._shown[2]


def test_on_the_full_screen_the_column_stops_above_the_slot(window):
    w = window(size=(1500, 900))
    w.reading = True
    w.canvas.configure(bg="#000000")
    w.canvas.enlarge = True
    story(w.post, pages=6, on_show=6)
    w.show(page(6))
    view = w._side.view
    assert view.layout.kind == "column" and view.layout.box[3] == 900 - 44
    assert str(view.cget("bg")) == "#000000"


def test_a_click_on_a_thumbnail_only_says_how_to_read_it(window):
    w = window(size=(1560, 900))
    story(w.post, pages=6, on_show=6)
    shown = page(6)
    w.show(shown)
    view = w._side.view
    x0, y0, x1, y1 = view._cell_parts(1)["thumb"]
    view._clicked(SimpleNamespace(x=(x0 + x1) // 2, y=(y0 + y1) // 2))
    assert "turn to it in the viewer" in w.said[-1]
    assert w._live is shown and w.canvas._image is shown  # the page area keeps the viewer's page


def test_the_hover_text_says_what_is_under_the_pointer(window):
    w = window(size=(1560, 900))
    story(w.post, pages=6, on_show=6)
    w.show(page(6))
    view = w._side.view
    parts = view._cell_parts(0)
    assert "turn to it in the viewer" in view.text_at(parts["thumb"][0] + 5, parts["thumb"][1] + 5)
    assert view.text_at(parts["translate"][0] + 3, parts["translate"][1] + 3) == "Translation: done"
    assert view.text_at(5, view.layout.box[3] - view.layout.box[1] - 5).startswith("Done: ")


def test_in_a_run_the_strip_takes_the_events_and_the_indicator_is_away(window):
    w = window(size=(1560, 900))
    story(w.post, pages=4, on_show=4)
    w._batching = True
    stage(w.post, 9, read="working", with_thumb=True)
    assert 9 in w._strip_model.pages and 9 not in w._side.model.screens
    w.show(page(4))
    assert not w._side.view.shown and w.canvas._shown[0] == (1560 - 600) // 2  # nothing kept clear in a run


def test_the_updated_mark_and_the_brackets_through_the_window(window, monkeypatch):
    w = window(size=(1560, 900))
    clock = [100.0]
    w._side.now = lambda: clock[0]
    story(w.post, pages=6, on_show=4, waiting_from=6)
    first = result(4, ["Who's there?", "", "Wait!"])
    w.show(first.original, first)
    assert 4 in w._side.seen.shown
    w.post("page_on_show", {"seq": 5})
    other = result(5, ["A", "B", "C"])
    w.show(other.original, other)
    w.cache.put(4, ["Who is there?", "Look.", "Wait!"])  # the work behind finished page 4
    stage(w.post, 4, translate="done")
    w.update()  # (the cache is looked at once the events are in)
    assert w._side.model.screens[4].updated
    w.post("page_on_show", {"seq": 4})
    again = result(4, ["Who is there?", "Look.", "Wait!"])
    w.show(again.original, again)
    boxes = bubble_boxes(4)
    assert sorted(w.canvas.brackets) == sorted(boxes[:2]) and w.canvas.find_withtag("brackets")
    assert w._side.model.screens[4].updated  # until it is read
    clock[0] += read_time(len("Who is there?") + len("Look.")) + 0.1
    side_mod.read(w)  # (the read time's timer)
    assert not w._side.model.screens[4].updated and not w.canvas.find_withtag("brackets")


def test_the_original_on_show_and_a_page_translated_again_are_no_look(window):
    w = window(size=(1560, 900))
    story(w.post, pages=3, on_show=3)
    seen = result(3, ["One", "Two", "Three"])
    w.original_var.set(True)
    w.show(seen.original, seen)
    assert 3 not in w._side.seen.shown  # the original on show: no lettering seen
    w.original_var.set(False)
    frame = seen.original
    w._fill = Filling(frame, seen.image, bubble_boxes(3))  # translated again over the page as shown
    w._fill.texts = {0: "Uno"}
    w._fill.states[0] = "lettered"
    w.show(frame)
    assert 3 not in w._side.seen.shown


# ------------------------------------------------------------------ the Reader's status slot
def test_the_slot_says_what_the_page_waits_for_from_one_second_and_goes_with_the_first_bubble(window):
    w = window(size=(720, 900))
    frame = page(2)
    w.show(frame)
    w.busy, w._busy_shown, w._busy_since, w._job_frame = True, True, 50.0, frame
    w._progress = Message("pipeline.stage_reading", total=3)
    state = w._side.slot
    assert status_slot.wanted(w, state, 50.9) is None  # under a second: nothing said
    assert status_slot.wanted(w, state, 51.0) == (status_slot.READING_KEY, False)
    w._progress = Message("pipeline.stage_translating", bubbles=3)
    assert status_slot.wanted(w, state, 52.0) == (status_slot.TRANSLATING_KEY, False)
    w._progress = Message("ollama.loading")
    assert status_slot.wanted(w, state, 52.0) == (status_slot.LOADING_KEY, False)
    w._fill = Filling(frame, frame, bubble_boxes(2))
    w._fill.states[0] = "lettered"
    assert status_slot.wanted(w, state, 53.0) is None  # a bubble lettered: the page is the progress
    w.role_var.set("translator")
    w._fill = None
    assert status_slot.wanted(w, state, 53.0) is None  # the Translator keeps the badge
    assert status_slot.badge_allowed(w)
    w.role_var.set("reader")
    assert not status_slot.badge_allowed(w)
    w._batching = True
    assert status_slot.badge_allowed(w) and status_slot.wanted(w, state, 53.0) is None  # a run: as before


def test_the_slot_shows_in_the_status_bar_and_on_the_full_screen(window):
    w = window(size=(720, 900))
    frame = page(2)
    w.show(frame)
    w.busy, w._busy_shown, w._job_frame = True, True, frame
    w._busy_since = __import__("time").monotonic() - 2
    status_slot.tick(w)
    label = w._side.slot_label
    assert label.winfo_manager() and label.var.get() == "Reading the page..."
    w.reading = True
    status_slot.tick(w)
    assert w.canvas.slot == ("Reading the page...", False) and w.canvas.find_withtag("slot")
    w.canvas.set_busy(lambda: "busy")
    assert w.canvas.band is None and not w.canvas.badge  # no badge in the Reader role


def test_a_page_that_could_not_be_translated_says_so_with_its_mark(window):
    w = window(size=(720, 900))
    failed = result(2, ["", "", ""], error="made-up")
    w.show(failed.original, failed)
    assert status_slot.wanted(w, w._side.slot, 0.0) == (status_slot.ERROR_KEY, True)
    frame = page(3)
    w._job_frame = frame
    w.post("error", {"text": "made-up"})
    w.show(frame)
    assert status_slot.wanted(w, w._side.slot, 0.0) == (status_slot.ERROR_KEY, True)  # the job's page on show
    w.show(page(4))
    assert status_slot.wanted(w, w._side.slot, 0.0) is None  # another page: gone


def test_nothing_to_read_is_said_for_four_seconds(window, monkeypatch):
    w = window(size=(720, 900))
    empty = result(2, [])
    empty.regions = []
    w.show(empty.original, empty)
    monkeypatch.setattr(status_slot.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(side_mod.time, "monotonic", lambda: 10.0)
    w.post("result", {"result": empty})
    assert status_slot.wanted(w, w._side.slot, 13.9) == (status_slot.NOTHING_KEY, False)
    assert status_slot.wanted(w, w._side.slot, 14.1) is None


# ------------------------------------------------------------------ the setting
def test_the_setting_has_three_values_and_a_row_in_the_dialog(tmp_path):
    from taslation.ui.dialogs import settings as dialog

    settings = Settings(state_dir=tmp_path)
    assert settings.side_indicator == "column"
    for value in ("column", "rail", "off"):
        settings.side_indicator = value
        settings.validate()
    settings.side_indicator = "sideways"
    with pytest.raises(ConfigError):
        settings.validate()
    row = next(r for r in dialog.EXTRA_ROWS if r.key == "side_indicator")
    assert [v for v, _label in row.choices] == ["column", "rail", "off"] and not row.page
