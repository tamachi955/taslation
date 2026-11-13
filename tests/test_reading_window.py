"""The window's page canvas: the busy badge, reading mode's capture and crop, the offline guard's warning, the
area dialog's handles. Parts of the App are borrowed onto small stand-ins on the shared hidden root."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation.ui.constants import APP_TITLE
from taslation import i18n, netguard
from taslation.capture import CaptureError
from taslation.regions import PageResult
from taslation.ui import app as app_mod
from taslation.ui import area, live
from taslation.ui.preview import ImageCanvas
from taslation.ui.live import BlackViewerMixin


def _page(width=64, height=48):
    page = Image.new("RGB", (width, height), "white")
    page.paste((20, 20, 20), (10, 12, 30, 40))  # some ink
    return page


def _sized(canvas, width=400, height=300):
    """The canvas as if it were on screen at that size (it never is in the tests)."""
    canvas.winfo_width, canvas.winfo_height = (lambda: width), (lambda: height)
    return canvas


class Bar:
    running = shown = False

    def start(self, _ms=50):
        self.running = True

    def stop(self):
        self.running = False

    def pack(self, **_kw):
        self.shown = True

    def pack_forget(self):
        self.shown = False


class Window(BlackViewerMixin):
    _blank_behind = app_mod.App._blank_behind
    _raise_viewer = app_mod.App._raise_viewer
    _resizing = app_mod.App._resizing
    _window_size = app_mod.App._window_size
    _blank_lasted = app_mod.App._blank_lasted

    """The parts of the App that the worker's events, the busy band, reading mode and the guard use."""

    _handle_event = app_mod.App._handle_event
    _go_busy = app_mod.App._go_busy
    _set_busy = app_mod.App._set_busy
    _busy_text = app_mod.App._busy_text
    _hide_busy = app_mod.App._hide_busy
    _summary = staticmethod(app_mod.App._summary)
    _page_line = app_mod.App._page_line
    _capture = app_mod.App._capture
    _set_viewer_hidden = app_mod.App._set_viewer_hidden
    _redisplay = app_mod.App._redisplay
    _overlay_items = app_mod.App._overlay_items
    _page_regions = app_mod.App._page_regions
    _guard_numbers = app_mod.App._guard_numbers
    _sync_guard = app_mod.App._sync_guard
    _guard_line = app_mod.App._guard_line
    _show_progress = app_mod.App._show_progress
    _picture = app_mod.App._picture
    _same_page = app_mod.App._same_page
    _area_thumb = app_mod.App._area_thumb
    _lettered = app_mod.App._lettered
    _lettering = app_mod.App._lettering
    _settle_live = app_mod.App._settle_live
    _on_page_event = app_mod.App._on_page_event
    _flush_fill = app_mod.App._flush_fill
    _covers_viewer = app_mod.App._covers_viewer
    _set_covered = app_mod.App._set_covered
    _run_queued = app_mod.App._run_queued
    _find_page = app_mod.App._find_page
    _apply_found_margins = app_mod.App._apply_found_margins
    say = app_mod.App.say
    _init_flow_state = app_mod.App._init_flow_state
    _sync_stop = app_mod.App._sync_stop
    _set_stop = app_mod.App._set_stop
    _load_ocr_if_due = app_mod.App._load_ocr_if_due
    _flush_busy = app_mod.App._flush_busy
    _show_busy_signs = app_mod.App._show_busy_signs

    def __init__(self, root):
        self._init_flow_state()
        self.pipeline, self._batching = None, False
        self.canvas = _sized(ImageCanvas(root))
        self.translate_btn, self.batch_btn = {}, {}
        self.progress_bar = Bar()
        self.titles: list[str] = []
        self.statuses: list[str] = []
        self.status_var = tk.StringVar(master=root)
        self.guard_var = tk.StringVar(master=root)
        self.role_var = tk.StringVar(master=root, value="reader")
        self.original_var = tk.BooleanVar(master=root, value=False)
        self.settings = SimpleNamespace(margins=(0, 10, 0, 0))
        self.busy = self.reading = self._viewer_hidden = self._busy_shown = False
        self._progress, self._busy_since = "", 0.0
        self._chosen_region = self._grip_box = self._review = self.last_result = None
        self._ordering = None
        self.ready, self.batch, self._bar_shown = True, None, False
        self._live = self._live_thumb = self._job_frame = self._job_thumb = self._fill = self._queued = None
        self._fill_dirty = self._covered = False
        self._thumbs, self._lettered_memo, self._mask_memo = [], None, None
        self.selected, self._manual_area, self._page_areas = None, False, {}  # no viewer: no page is looked for

    def _own_rects(self):  # no window of its own on a screen
        return []

    def title(self, text):
        self.titles.append(text)

    def status(self, text):
        self.statuses.append(text() if callable(text) else text)

    def _area_hint_due(self):
        return False

    def _show_notes(self):
        pass

    def _font_note(self):
        return ""


def test_the_busy_lines_name_the_stage_and_the_seconds():
    assert app_mod.busy_line("Reading text 2/12...", 3.7) == "Translating... reading 12 line(s) (3 s)"
    assert app_mod.busy_line("Translating 5 bubble(s) with qwen3.5:4b...", 7) == "Translating... asking the model (7 s)"
    assert app_mod.busy_line("Rendering...", 12) == "Typesetting... (12 s)"
    assert app_mod.busy_line("", 0) == "Translating... (0 s)"
    assert app_mod.busy_line("Something new...", 1) == "Translating... Something new (1 s)"  # unknown: as it is
    assert app_mod.reads_page("Reading text 1/3...") and app_mod.reads_page("Translating 5 bubble(s)...")
    assert not app_mod.reads_page("Finding bubbles...") and not app_mod.reads_page("Rendering...")
    i18n.set_language("ja")
    try:
        assert app_mod.busy_line("Reading text 1/3...", 2) == "翻訳中... 3 行を読み取り中（2 秒）"
    finally:
        i18n.set_language("en")


def test_the_busy_badge_shows_while_a_page_is_read_and_goes_when_it_is_shown(hidden_root):
    w = Window(hidden_root)
    result = PageResult(image=_page(), original=_page(), regions=[])

    def band():
        return w.canvas.find_withtag("busy")

    assert not w.progress_bar.shown  # no job: no bar
    w._go_busy()  # a page from the cache is only found and drawn: no badge, and no busy title or bar at once
    assert w.busy and not w.titles and not w.progress_bar.shown
    w._flush_busy(w._busy_since + 0.29)
    assert not w.titles
    w._flush_busy(w._busy_since + 0.3)  # still at work after 0.3 s: the title and the bar say so
    assert w.titles[-1] == "TASlation - translating..." and w.progress_bar.running and w.progress_bar.shown
    for message in ("Finding bubbles...", "Rendering..."):
        w._handle_event("progress", {"text": message})
    assert w.canvas.band is None and not band() and w.status_var.get() == "Typesetting..."  # the stage, not the raw text
    w._handle_event("result", {"result": result})
    w._handle_event("translate_done", {})
    assert not w.busy and w.titles[-1] == APP_TITLE and not w.progress_bar.running and not w.progress_bar.shown

    w._go_busy()  # a new page: the badge comes with the reading, follows the stages, goes with the page
    w._handle_event("progress", {"text": "Finding bubbles..."})
    assert not band()
    w._handle_event("progress", {"text": "Reading text 1/3..."})
    assert band() and w.canvas.itemcget("busy-text", "text").startswith("Translating... reading 3 line(s) (")
    assert w.canvas.find_withtag("busy-arc")  # the spinner
    w._handle_event("progress", {"text": "Translating 3 bubble(s) with qwen3.5:4b..."})
    assert w.canvas.itemcget("busy-text", "text").startswith("Translating... asking the model (")
    w._handle_event("progress", {"text": "Rendering..."})
    assert w.canvas.itemcget("busy-text", "text").startswith("Typesetting... (")
    x0, y0, x1, y1 = w.canvas.bbox("busy")
    assert w.canvas.in_busy_band((x0 + x1) / 2, (y0 + y1) / 2) and not w.canvas.in_busy_band(x0 + 2, y0 - 5)
    assert 380 <= x1 <= 400 and y0 <= 12 and y1 < 60  # a badge in the top right corner, not a band across the page
    box = next(i for i in w.canvas.find_withtag("busy") if w.canvas.type(i) == "polygon")  # rounded corners
    assert w.canvas.itemcget(box, "fill") == "#202020" and w.canvas.itemcget(box, "stipple") == ""  # solid
    w._handle_event("result", {"result": result})
    assert w.busy and w.canvas.band is None and not band()  # the page is there: the badge has gone already
    w._handle_event("translate_done", {})

    w._go_busy()  # a job that fails: the badge goes as well
    w._handle_event("progress", {"text": "Reading text 1/1..."})
    assert band()
    w._handle_event("translate_done", {})
    assert not band() and not w.canvas.in_busy_band(x0 + 2, (y0 + y1) / 2) and w.titles[-1] == APP_TITLE
    assert not w.progress_bar.shown  # gone with the failed job too


def test_behind_the_reading_window_only_the_viewers_own_frame_is_taken(hidden_root, monkeypatch):
    frame = [Image.new("RGB", (64, 48), (0, 0, 0))]  # what PrintWindow gives for a window it cannot draw
    asked = []

    def capture(hwnd, client_only=True, allow_screen_fallback=True):
        asked.append(allow_screen_fallback)
        return frame[0]

    monkeypatch.setattr(live, "capture_window", capture)
    w = Window(hidden_root)
    w.reading = True
    with pytest.raises(CaptureError):
        w._capture(1)
    message = "This viewer cannot be read behind the reading window; press Esc"
    assert asked == [False] and w._viewer_hidden and w.canvas.message == message
    frame[0] = _page()
    assert w._capture(1) is frame[0] and not w._viewer_hidden and w.canvas.message == ""
    w.last_result = PageResult(image=frame[0], original=frame[0], regions=[])
    w._redisplay()  # the page alone: the area (margins 0, 10, 0, 0), enlarged to the screen
    assert w.canvas.crop == (0, 10, 64, 48) and w.canvas.enlarge and w.canvas.scale == 400 / 64
    w.reading = False
    w._redisplay()
    assert w.canvas.crop is None and not w.canvas.enlarge and w.canvas.scale == 1.0
    w._capture(1)
    assert asked[-1] is True  # the normal window keeps the screen fallback


def test_the_canvas_shows_a_part_enlarged_and_a_note(hidden_root):
    c = _sized(ImageCanvas(hidden_root))
    page = Image.new("RGB", (200, 100), "white")
    c.crop, c.enlarge = (50, 0, 150, 100), True
    c.set_image(page)
    assert c.scale == 3.0 and c.shown_box() == (50, 0, 150, 100)
    assert c.from_image_coords(50, 0) == (50, 0) and c.to_image_coords(200, 150) == (100, 50)
    assert c.inside(200, 150) and not c.inside(20, 150)  # beside the picture
    c.crop, c.enlarge = None, False
    c.set_image(page)
    assert c.scale == 1.0 and c.shown_box() == (0, 0, 200, 100) and c.inside(150, 150)
    c.set_note("Sent Left to the viewer...", 4000)
    assert c.find_withtag("note") and c.itemcget(c.find_withtag("note")[-1], "text") == "Sent Left to the viewer..."
    c.set_image(page)  # a redraw keeps it
    assert c.find_withtag("note")
    c.set_note("")
    assert not c.find_withtag("note")
    c.message = "No picture here"
    c.set_image(page)
    assert not c.inside(150, 150) and c.find_all()


def test_the_status_bar_warns_only_once_the_offline_guard_blocked_something(hidden_root, monkeypatch):
    state = netguard.GuardState(allowed_ports=frozenset({11434}), installed=True)
    monkeypatch.setattr(netguard, "state", lambda: state)
    w = Window(hidden_root)
    w._sync_guard()
    assert w.guard_var.get() == ""  # nothing blocked: nothing on screen
    assert w._guard_line() == ("Offline guard: on. Only this computer's port 11434 (Ollama) can be reached; "
                         "0 other connection attempt(s) were blocked.")
    state.blocked.append("TASlation network guard blocked connect to 203.0.113.9:443")
    w._sync_guard()
    assert w.guard_var.get() == ("TASlation blocked 1 attempt(s) to reach the internet. Nothing left this computer; "
                                 "you need do nothing.")
    i18n.set_language("ja")
    w._sync_guard()
    assert w.guard_var.get() == "TASlation はインターネットへの接続の試みを 1 回止めました。このパソコンから外には何も出ていません。何もする必要はありません。"
    i18n.set_language("en")
    monkeypatch.setattr(netguard, "state", lambda: None)
    assert w._guard_line() == "Offline guard: off."


def test_the_area_dialog_resizes_moves_and_redraws_the_area(hidden_root):
    chosen = []
    d = app_mod.AreaDialog(hidden_root, Image.new("RGB", (800, 600), "white"),
                           lambda box, size: chosen.append((box, size)), margins=(0, 85, 0, 0))
    d.withdraw()

    def drag(start, end, via=None):  # not on screen: a canvas pixel is an image pixel
        d._press(SimpleNamespace(x=start[0], y=start[1]))
        if via:
            d._drag(SimpleNamespace(x=via[0], y=via[1]))
        d._release(SimpleNamespace(x=end[0], y=end[1]))

    assert d.box == (0, 85, 800, 600) and d.margins() == (0, 85, 0, 0)
    drag((800, 600), (700, 500), via=(750, 550))  # the bottom-right handle
    assert d.box == (0, 85, 700, 500) and d.margins() == (0, 85, 100, 100)
    assert len(d.canvas.find_withtag("area")) == 3 + 1 + 8  # the shade above, below and right, the outline, handles
    drag((300, 300), (350, 320))  # inside: the area moves
    assert d.box == (50, 105, 750, 520)
    drag((780, 590), (783, 592))  # a click beside it: the area stays
    assert d.box == (50, 105, 750, 520)
    drag((20, 20), (420, 300))  # elsewhere: a new one
    assert d.box == (20, 20, 420, 300) and d.margins() == (20, 20, 380, 300)
    drag((420, 160), (5000, 160))  # the right side, as far as the capture goes
    assert d.box == (20, 20, 800, 300)
    assert not hasattr(d, "reset")  # Clear area is the way back to no area of the reader's
    d.box = (0, 0, 800, 600)
    d._draw()
    _sized(d.canvas, 400 + 2 * area.HANDLE, 300 + 2 * area.HANDLE).set_image(d.image)  # the capture at half its size
    assert d.canvas.scale == 0.5 and len(d.canvas.find_withtag("area")) == 1 + 8  # redrawn with the picture
    # Drawn clear of the canvas's edges by a handle's size, so that the handles on the capture's edges show whole.
    assert d.canvas.offset == (area.HANDLE, area.HANDLE) and d.canvas.inset == area.HANDLE
    for item in d.canvas.find_withtag("area"):
        hx0, hy0, hx1, hy1 = d.canvas.coords(item)
        assert hx0 >= 0 and hy0 >= 0 and hx1 <= 400 + 2 * area.HANDLE and hy1 <= 300 + 2 * area.HANDLE
    drag((400 + area.HANDLE, 300 + area.HANDLE), (350 + area.HANDLE, 250 + area.HANDLE))  # the bottom-right handle
    assert d.box == (0, 0, 700, 500)
    d._accept()
    assert chosen == [((0, 0, 700, 500), (800, 600))] and not d.winfo_exists()


class Shapes:
    """The parts of the App that translator mode's pointer and keys use; what they start is recorded."""

    _editing = app_mod.App._editing
    _grip_of = app_mod.App._grip_of
    _page_grip = app_mod.App._page_grip
    _turn_of = app_mod.App._turn_of
    _frame_of = app_mod.App._frame_of
    _shown_frame = app_mod.App._shown_frame
    _cancel_drag = app_mod.App._cancel_drag
    _choose = app_mod.App._choose
    _draw_chosen = app_mod.App._draw_chosen
    _draw_frame = app_mod.App._draw_frame
    _on_motion = app_mod.App._on_motion
    _on_press = app_mod.App._on_press
    _on_drag = app_mod.App._on_drag
    _on_release = app_mod.App._on_release
    _on_double = app_mod.App._on_double
    _edit_chosen = app_mod.App._edit_chosen
    _drop_chosen = app_mod.App._drop_chosen
    _region_at = app_mod.App._region_at
    _page_regions = app_mod.App._page_regions
    _on_escape = app_mod.App._on_escape
    _result_on_show = app_mod.App._result_on_show
    say = app_mod.App.say

    def __init__(self, root, regions):
        self.canvas = _sized(ImageCanvas(root))
        page = Image.new("RGB", (400, 300), "white")
        self.last_result = PageResult(image=page, original=page, regions=regions)
        self.canvas.on_redraw = self._draw_chosen
        self.role_var = tk.StringVar(master=root, value="translator")
        self.reading = self.busy = False
        self._fill = self._live = None  # the page on show is the result
        self.pipeline = object()
        self._ordering = self._drag_start = self._drag_rect = None
        self._chosen_region = self._grip = self._grip_start = self._grip_box = self._turn = self._frame_cache = None
        self.moved, self.edited, self.dropped, self.added, self.forwarded, self.statuses = [], [], [], [], [], []
        self.canvas.set_image(page)

    def _move_region(self, region, box):
        self.moved.append((region, box))

    def _open_editor(self, region):
        self.edited.append(region)

    def _drop_region(self, region):
        self.dropped.append(region)

    def _add_region(self, box):
        self.added.append(box)

    def _forward_click(self, event):
        self.forwarded.append((event.x, event.y))

    def status(self, text):
        self.statuses.append(text() if callable(text) else text)

    def stop_batch(self):
        pass

    def click(self, x, y, to=None, via=None):
        self._on_press(SimpleNamespace(x=x, y=y))
        if via or to:
            self._on_drag(SimpleNamespace(x=(via or to)[0], y=(via or to)[1]))
        end = to or (x, y)
        self._on_release(SimpleNamespace(x=end[0], y=end[1]))


def _region(box):
    from taslation.pipeline import manual_region
    import numpy as np

    r = manual_region(np.full((300, 400, 3), 255, np.uint8), box)
    r.status = "translated"
    return r


def test_translator_mode_selects_moves_resizes_edits_and_drops_regions_like_shapes(hidden_root):
    a, b = _region((50, 50, 150, 120)), _region((200, 150, 300, 250))
    w = Shapes(hidden_root, [a, b])  # the page is shown at its size: a canvas pixel is an image pixel
    w.click(100, 80)  # a click selects; nothing else happens
    assert w._chosen_region is a and not (w.moved or w.edited or w.forwarded)
    # outlined two-tone (a dark stroke under the yellow), with its eight handles and the rotate handle (its stalk
    # two-tone too)
    assert len(w.canvas.find_withtag("chosen")) == 2 + 8 + 3
    assert len(w.canvas.find_withtag("edge")) == 2
    w._on_motion(SimpleNamespace(x=150, y=120))
    assert str(w.canvas.cget("cursor")) == "size_nw_se"
    w._on_motion(SimpleNamespace(x=100, y=80))
    assert str(w.canvas.cget("cursor")) == "fleur"
    w.click(150, 120, to=(170, 140))  # the bottom-right handle: resized
    assert w.moved == [(a, (50, 50, 170, 140))] and w._grip_box == (50, 50, 170, 140)  # shown there until it is
    w._grip_box = None
    w.click(100, 80, to=(120, 90))  # inside: moved
    assert w.moved[-1] == (a, (70, 60, 170, 130))
    w._grip_box = None
    w.click(250, 200, to=(251, 201))  # another region, pressed and barely moved: only selected
    assert w._chosen_region is b and len(w.moved) == 2
    w._on_double(SimpleNamespace(x=100, y=80))  # a double-click opens the editor
    w._on_release(SimpleNamespace(x=100, y=80))
    assert w._chosen_region is a and w.edited == [a]
    w._edit_chosen()  # Enter: the editor again
    assert w.edited == [a, a]
    w._drop_chosen()  # Delete: dropped, nothing selected
    assert w.dropped == [a] and w._chosen_region is None and not w.canvas.find_withtag("chosen")
    w.click(250, 200)
    w._on_escape()  # Esc: deselected
    assert w._chosen_region is None
    w.click(250, 200)
    w.click(350, 30)  # a click on empty space: deselected, and the hint
    assert w._chosen_region is None and w.statuses
    w.click(320, 20, to=(390, 80))  # a drag on empty space: a new region
    assert w.added == [(320, 20, 390, 80)]
    w.role_var.set("reader")  # the reader's clicks go to the viewer, nothing is selected
    w.click(100, 80)
    assert w.forwarded == [(100, 80)] and w._chosen_region is None
    w.role_var.set("translator")
    w.reading = True  # nor in the reading window
    w.click(100, 80)
    assert w.forwarded[-1] == (100, 80) and w._chosen_region is None
