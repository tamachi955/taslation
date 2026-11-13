"""The window shows the viewer live: its latest frame, the translated page laid over it while it shows that page, a
page filling in as it is translated, the last good frame when the viewer hides behind TASlation, and requests that
wait for the models to load. Parts of the App are borrowed onto a stand-in on the shared hidden root."""
from __future__ import annotations

import queue
import tkinter as tk
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import i18n
from taslation.capture import WindowInfo
from taslation.regions import PageResult
from taslation.ui import app as app_mod
from taslation.ui import live
from taslation.ui.preview import ImageCanvas
from taslation.ui.live import BlackViewerMixin

COVERED = ("The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or move it so "
           "that a strip of the viewer stays visible.")
VIEWER = WindowInfo(hwnd=7, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7, rect=(100, 100, 300, 250))


def _frame(ink=(40, 30, 80, 70), toolbar=False, size=(200, 150)):
    """A capture of the viewer: a white page with a block of ink, maybe the viewer's toolbar above the area."""
    page = Image.new("RGB", size, "white")
    page.paste((20, 20, 20), ink)
    if toolbar:
        page.paste((60, 60, 160), (0, 0, size[0], 15))
    return page


def _translated(frame, box=(40, 30, 80, 70)):
    """The page as the pipeline gives it back: the capture, and a copy with the text in *box* replaced."""
    original = frame.copy()
    image = original.copy()
    image.paste((250, 250, 250), box)
    image.paste((200, 0, 0), (box[0] + 5, box[1] + 5, box[0] + 15, box[1] + 15))  # the lettering
    return PageResult(image=image, original=original, regions=[])


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

    """The parts of the App that the live view, the page events, the capture and the waiting requests use."""

    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    _handle_event = app_mod.App._handle_event
    _on_page_event = app_mod.App._on_page_event
    _flush_fill = app_mod.App._flush_fill
    _go_busy = app_mod.App._go_busy
    _set_busy = app_mod.App._set_busy
    _show_progress = app_mod.App._show_progress
    _busy_text = app_mod.App._busy_text
    _hide_busy = app_mod.App._hide_busy
    _summary = staticmethod(app_mod.App._summary)
    _page_line = app_mod.App._page_line
    _redisplay = app_mod.App._redisplay
    _picture = app_mod.App._picture
    _overlay_items = app_mod.App._overlay_items
    _page_regions = app_mod.App._page_regions
    _noted_regions = app_mod.App._noted_regions
    _result_on_show = app_mod.App._result_on_show
    _editing = app_mod.App._editing
    _same_page = app_mod.App._same_page
    _area_thumb = app_mod.App._area_thumb
    _lettered = app_mod.App._lettered
    _lettering = app_mod.App._lettering
    _settle_live = app_mod.App._settle_live
    _show_live = app_mod.App._show_live
    _tick = app_mod.App._tick
    _poll = app_mod.App._poll
    _follows_events = app_mod.App._follows_events
    _viewer_shows_book = app_mod.App._viewer_shows_book
    _say_waiting = app_mod.App._say_waiting
    _normal_status = app_mod.App._normal_status
    _capture = app_mod.App._capture
    _covers_viewer = app_mod.App._covers_viewer
    _set_covered = app_mod.App._set_covered
    _capture_failed = app_mod.App._capture_failed
    _set_viewer_hidden = app_mod.App._set_viewer_hidden
    translate_now = app_mod.App.translate_now
    _queue = app_mod.App._queue
    _run_queued = app_mod.App._run_queued
    _start_translate = app_mod.App._start_translate
    _find_page = app_mod.App._find_page
    _found_margins = app_mod.App._found_margins
    _apply_found_margins = app_mod.App._apply_found_margins
    _hand_set = app_mod.App._hand_set
    _inner_margins = app_mod.App._inner_margins
    _area_hint_due = app_mod.App._area_hint_due
    say = app_mod.App.say
    _init_flow_state = app_mod.App._init_flow_state
    _sync_stop = app_mod.App._sync_stop
    _set_stop = app_mod.App._set_stop
    _load_ocr_if_due = app_mod.App._load_ocr_if_due
    _flush_busy = app_mod.App._flush_busy
    _show_busy_signs = app_mod.App._show_busy_signs

    def __init__(self, root, own=()):
        self._init_flow_state()
        self.pipeline, self._batching = None, False
        self.canvas = ImageCanvas(root)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)  # as if on screen
        self.translate_btn, self.batch_btn = {}, {}
        self.progress_bar = Bar()
        self.titles: list[str] = []
        self.statuses: list[str] = []
        self.status_var = tk.StringVar(master=root)
        self.role_var = tk.StringVar(master=root, value="reader")
        self.original_var = tk.BooleanVar(master=root, value=False)
        self.auto_var = tk.BooleanVar(master=root, value=False)
        self.book_var = tk.StringVar(master=root, value="Book")
        self.model_var = tk.StringVar(master=root, value="m")
        self.lang_var = tk.StringVar(master=root, value="English")
        self.settings = SimpleNamespace(margins=(0, 20, 0, 0), auto_interval_ms=700, page_turn_wait_ms=3000,
                                        black_wait_s=30.0)
        self.selected = VIEWER
        self.own = list(own)  # where this program's windows are on the screen
        self.busy = self.reading = self._viewer_hidden = self._busy_shown = self._waiting = False
        self.ready, self.batch, self._bar_shown = True, None, False
        self._progress, self._busy_since = "", 0.0
        self._chosen_region = self._grip_box = self._review = self.last_result = self._ordering = None
        self._live = self._live_thumb = self._job_frame = self._job_thumb = self._fill = self._queued = None
        self._fill_dirty = self._covered = False
        self._thumbs, self._lettered_memo, self._mask_memo = [], None, None
        self._auto_last = self._auto_candidate = None
        self._manual_area, self._page_areas, self._area_hinted = True, {}, False  # the area (0, 20, 0, 0) is the reader's
        self._jobs: queue.Queue = queue.Queue()
        self.new_pages: list[Image.Image] = []
        self.batches: list[tuple] = []

    def title(self, text):
        self.titles.append(text)

    def status(self, text):
        self.statuses.append(text() if callable(text) else text)

    def _own_rects(self):
        return list(self.own)

    def _book_in_front(self):
        return True

    def _current_window(self):
        return self.selected

    def _on_new_page(self, image, thumb=None):  # as the App's in page-by-page mode
        self.new_pages.append(image)
        self._start_translate(image, thumb=thumb)

    def _start_batch(self, *options):
        self.batches.append(options)

    def _show_notes(self):
        pass

    def _font_note(self):
        return ""

    def shown(self):
        """The picture on the canvas (full size)."""
        return self.canvas._image


@pytest.fixture
def viewer(monkeypatch):
    """A viewer whose next frame the test sets; what each capture asked for is kept."""
    state = SimpleNamespace(frame=_frame(), asked=[], screen=[])

    def capture(hwnd, client_only=True, allow_screen_fallback=True):
        state.asked.append(allow_screen_fallback)
        return state.frame

    monkeypatch.setattr(live, "capture_window", capture)
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "client_rect_on_screen", lambda hwnd: (100, 100, 200, 150))
    return state


def test_the_window_shows_the_viewer_live_and_lays_the_translation_over_it(hidden_root, viewer):
    w = Window(hidden_root)
    draws: list[Image.Image | None] = []
    set_image = w.canvas.set_image
    w.canvas.set_image = lambda image: (draws.append(image), set_image(image))
    page = viewer.frame
    w._tick()  # Auto is off: the viewer is shown all the same
    assert w.shown() is page and w._live is page and draws == [page]
    w._tick()  # the same frame again: nothing is drawn
    assert len(draws) == 1
    viewer.frame = page.copy()  # another capture, the same picture: still nothing
    w._tick()
    assert len(draws) == 1 and w._live is page

    result = _translated(page)
    w._handle_event("result", {"result": result})  # the translated page replaces the frame at once
    assert w.shown() is result.image and w._live is result.original and w._result_on_show()

    viewer.frame = _frame(toolbar=True)  # the viewer's toolbar comes up above the page: the translation stays
    w._tick()
    shown = np.asarray(w.shown())
    assert shown[5, 100].tolist() == [60, 60, 160]  # the toolbar as it is now ...
    assert shown[40, 50].tolist() == [200, 0, 0] and shown[60, 70].tolist() == [250, 250, 250]  # ... the lettering
    assert w._result_on_show()
    w.original_var.set(True)  # Show original: the live frame as it is
    w._redisplay()
    assert w.shown() is viewer.frame
    w.original_var.set(False)

    viewer.frame = _frame(ink=(120, 80, 170, 130))  # a page turned in the viewer: shown as it is, no translation
    w._tick()
    assert w.shown() is viewer.frame and not w._result_on_show()
    w.role_var.set("translator")
    assert not w._editing()  # the regions of the page before are not on show: nothing to edit
    w._handle_event("result", {"result": _translated(viewer.frame)})
    assert w._editing()


def test_a_page_fills_in_on_the_frame_as_its_events_come(hidden_root, viewer):
    w = Window(hidden_root)
    w._tick()
    frame = w._live
    w._start_translate(frame, thumb=w._live_thumb)
    assert w.busy and w._job_frame is frame and w._jobs.qsize() == 1 and not w.progress_bar.shown
    w._flush_busy(w._busy_since + 0.3)  # at work for 0.3 s: the bar shows (a cached page is done before)
    assert w.progress_bar.shown
    boxes = [(40, 30, 80, 70), (120, 80, 170, 130)]
    w._handle_event("regions", {"boxes": boxes, "size": frame.size})
    w._flush_fill()
    assert w.shown() is frame and len(w.canvas.find_withtag("outline-dashed")) == 2  # found: dashed outlines
    assert w.canvas.badge and w.canvas.band is not None  # the busy line is a badge in the corner ...
    bx0, by0, bx1, by1 = w.canvas.bbox("busy")
    px0, py0, px1, py1 = w.canvas._shown
    assert bx1 > px1 and 380 <= bx1 <= 400 and by0 <= 12 and by1 < 60  # ... the canvas's top right, beside the page
    w._handle_event("read", {"index": 0, "status": "untranslated", "box": (40, 30, 80, 66)})  # read: where it is now
    w._handle_event("read", {"index": 1, "status": "ocr-noise"})  # no text: its outline goes
    w._handle_event("progress", {"text": "Translating 1 bubble(s) with qwen3.5:4b..."})
    w._flush_fill()
    assert len(w.canvas.find_withtag("outline-solid")) == 1 and not w.canvas.find_withtag("outline-dashed")
    assert w._fill.boxes[0] == (40, 30, 80, 66)
    assert w.canvas.itemcget("busy-text", "text").startswith("Translating... asking the model (")
    assert w.status_var.get() == "Translating... asking the model"
    patch = Image.new("RGB", (40, 40), (200, 0, 0))
    w._handle_event("translated", {"index": 0, "text": "Hi!", "box": boxes[0], "patch": patch})
    w._flush_fill()
    assert not w.canvas.find_withtag("outline")  # lettered: no outline left
    assert np.asarray(w.shown())[50, 60].tolist() == [200, 0, 0] and np.asarray(frame)[50, 60].tolist() == [20, 20, 20]
    assert w.canvas.itemcget("busy-text", "text").startswith("Translating... 1 of 1 line(s) done (")
    final = _translated(frame)
    w._handle_event("page", {"image": final.image})
    w._handle_event("result", {"result": final})
    w._handle_event("translate_done", {})
    w._flush_fill()
    assert w.shown() is final.image and w._fill is None and not w.canvas.find_withtag("busy")
    assert not w.busy and not w.progress_bar.shown

    w._start_translate(final.original)  # the page on show translated again: it fills in over its translation
    w._handle_event("regions", {"boxes": boxes[:1], "size": frame.size})
    w._flush_fill()
    assert w.shown() is final.image and len(w.canvas.find_withtag("outline-dashed")) == 1
    w._handle_event("translate_done", {})  # the job failed: the page as it was again, no band, no bar
    assert w._fill is None and w.shown() is final.image and not w.canvas.find_withtag("busy")
    assert not w.progress_bar.shown


def test_the_status_bar_names_the_stage_in_the_windows_language(hidden_root, viewer):
    w = Window(hidden_root)
    i18n.set_language("ja")
    try:
        w._handle_event("progress", {"text": "Reading text 7/7..."})
        assert w.status_var.get() == "翻訳中... 7 行を読み取り中"
        w._handle_event("progress", {"text": "Rendering..."})
        assert w.status_var.get() == "写植中..."
        w._handle_event("progress", {"text": "Something new..."})  # no stage known: the message as it is
        assert w.status_var.get() == "Something new..."
    finally:
        i18n.set_language("en")


def test_a_viewer_hidden_behind_taslation_keeps_the_last_good_frame(hidden_root, viewer):
    w = Window(hidden_root, own=[(0, 0, 1920, 1040)])  # TASlation maximised over the viewer
    w.auto_var.set(True)
    good = viewer.frame
    w._tick()
    assert w.shown() is good and w._auto_candidate is not None and viewer.asked == [False]  # no screen fallback
    candidate = w._auto_candidate
    viewer.frame = Image.new("RGB", (200, 150), (255, 255, 255))  # PrintWindow's blank frame: Chrome draws nothing
    w._tick()
    assert w.shown() is good and w._live is good  # never a picture of TASlation itself
    assert w.canvas.banner == COVERED and w.statuses[-1] == COVERED and w.canvas.note == ""  # a band over the page
    band = w.canvas.find_withtag("banner")
    assert band and w.canvas.itemcget("banner-text", "fill") == "#ffffff"
    box = next(i for i in band if w.canvas.type(i) == "polygon")  # in the busy badge's style: dark, rounded
    assert w.canvas.itemcget(box, "fill") == "#202020" and w.canvas.itemcget(box, "outline") == "#6a6a6a"
    x0, y0, x1, y1 = w.canvas.bbox("banner")
    assert x0 > 0 and x1 < 400 and y0 < 150 < y1  # across the middle of the canvas
    assert w._auto_candidate is candidate and w._auto_last is None and not w.new_pages  # nothing remembered
    w._tick()
    assert w.statuses.count(COVERED) == 1  # said once
    viewer.frame = good.copy()  # the viewer draws again: the band and the line go, Auto takes the page by itself
    w._tick()
    assert w.canvas.banner == "" and not w.canvas.find_withtag("banner") and w.new_pages and w._jobs.qsize() == 1
    assert COVERED not in w.statuses[-2:] and "Viewer: Yomizuq - Google Chrome" in w.statuses
    w._handle_event("translate_done", {})
    i18n.set_language("ja")
    try:
        w._set_covered(True)  # in the window's language
        assert w.canvas.banner.startswith("TASlation がビューアを完全に覆っているため")
        w.say("Translating...")  # something else said meanwhile: it stays when the viewer draws again
        w._set_covered(False)
        assert w.canvas.banner == "" and w._status_key == "Translating..."
    finally:
        i18n.set_language("en")

    w.own = [(1000, 0, 1920, 1040)]  # TASlation beside the viewer: the screen there shows the viewer
    viewer.frame = Image.new("RGB", (200, 150), (0, 0, 0))
    w._tick()
    assert viewer.asked[-1] is True and w._live is not viewer.frame  # a blank frame is neither shown nor kept
    w._black_watch = None  # (black: the heartbeat follows that now, `test_black_viewer`)
    w.reading = True  # behind the reading window: as before, a message instead of the picture
    w._tick()
    assert viewer.asked[-1] is False and w._viewer_hidden


def test_requests_wait_for_the_models_and_run_once_they_are_loaded(hidden_root, viewer):
    w = Window(hidden_root)
    w.ready = False
    w.translate_now()  # F5 in the first seconds: remembered, and the band says why nothing happens yet
    assert w._queued == ("translate", ()) and not viewer.asked and w._jobs.empty()
    assert w.canvas.itemcget("busy-text", "text").startswith("Translating... getting the Japanese reader ready (")
    assert w.progress_bar.shown
    w._handle_event("ready", {"ocr": True})  # loaded: the page is translated now
    assert w._queued is None and viewer.asked and w._jobs.qsize() == 1 and w.busy
    w.translate_now()  # pressed again while it runs: done after it
    assert w._queued == ("translate", ())
    w._handle_event("translate_done", {})
    assert w._jobs.qsize() == 2 and w._queued is None
    w._handle_event("translate_done", {})

    w = Window(hidden_root)  # Auto's first page, while the models load
    w.ready = False
    w.auto_var.set(True)
    w._tick()
    w._tick()
    assert w._queued == ("auto", ()) and not w.new_pages and w._auto_last is None
    w._queue("batch", "options")  # the batch's Start in the meantime: it outranks the page
    w._queue("auto")
    assert w._queued == ("batch", ("options",))
    w._handle_event("ready", {"ocr": True})
    assert w.batches == [("options",)] and w._queued is None

    w = Window(hidden_root)
    w.ready = False
    w.auto_var.set(True)
    w._tick()
    w._tick()
    w._handle_event("ready", {"ocr": True})
    assert w.new_pages == [viewer.frame] and w._jobs.qsize() == 1  # taken at once, not a tick later

    w = Window(hidden_root)  # the start fails altogether: what waited is dropped, and the band goes
    w.ready = False
    w.translate_now()
    w._sync_guard = lambda: None
    w._handle_event("idle", {})
    assert w._queued is None and not w.canvas.find_withtag("busy") and not w.progress_bar.shown


def test_the_busy_line_counts_the_lines_lettered():
    assert app_mod.busy_line("Translating 5 bubble(s) with m...", 3, filled=2) == "Translating... 2 of 5 line(s) done (3 s)"
    assert app_mod.busy_line("Translating 5 bubble(s) with m...", 3) == "Translating... asking the model (3 s)"
    assert app_mod.busy_line(app_mod.LOADING, 1) == "Translating... getting the Japanese reader ready (1 s)"
    assert app_mod.progress_line("Finding bubbles...") == "Looking at the page... finding the bubbles"
    i18n.set_language("ja")
    try:
        assert app_mod.busy_line("Translating 5 bubble(s) with m...", 3, filled=2) == "翻訳中... 5 行中 2 行完了（3 秒）"
    finally:
        i18n.set_language("en")
