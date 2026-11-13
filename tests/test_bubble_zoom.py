"""A translated bubble enlarged while reading (`ui.zoom`): when the pointer resting on a bubble opens its popup and
after how long, what the popup holds (the original cropped from the frame in memory, the translation at a readable
size), where it goes (beside the bubble, never over it), and what takes it away. Parts of the App are borrowed onto
a stand-in on the shared hidden root, which is never mapped: the popup is made but not shown (`zoom.reveal`)."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation.config import Settings
from taslation.regions import PageResult, TextRegion
from taslation.ui import app as app_mod
from taslation.ui import zoom
from taslation.ui.preview import ImageCanvas
from taslation.ui.zoom import (
    ZOOM_DELAY_MS,
    ZOOM_GAP,
    ZOOM_REST_MS,
    ZOOM_WATCH_MS,
    crop_shown,
    fallback_place,
    hard_to_read,
    zoom_place,
    zoom_text_px,
)

A = app_mod.App
WORK = (0, 0, 1920, 1040)


# ------------------------------------------------------------------ sizes and places (no Tk)
def test_the_text_is_twice_the_readable_size_and_never_smaller_than_on_the_screen():
    assert zoom_text_px(11, 0) == 22 and zoom_text_px(0, 0) == 22  # (0: no flag "small", the usual size)
    assert zoom_text_px(11, 30) == 38  # lettered at 30 px on the screen: larger still
    assert zoom_text_px(5, 0) == 16 and zoom_text_px(30, 0) == 44  # within the bounds


def test_a_bubble_is_hard_to_read_when_flagged_small_or_long_or_lettered_small_on_the_screen():
    region = SimpleNamespace(flags=[], font_size=30)
    assert not hard_to_read(region, 0.5, 11)  # 15 px on the screen
    assert hard_to_read(SimpleNamespace(flags=[], font_size=18), 0.5, 11)  # 9 px on the screen
    assert hard_to_read(SimpleNamespace(flags=["small"], font_size=30), 1.0, 11)
    assert hard_to_read(SimpleNamespace(flags=["long"], font_size=30), 1.0, 11)
    assert not hard_to_read(SimpleNamespace(flags=["ocr"], font_size=0), 1.0, 11)  # (a size not known)


def test_the_original_shows_larger_than_on_the_page_within_a_share_of_the_screen():
    assert crop_shown((100, 200), 1.0, WORK) == (150, 300)
    assert crop_shown((100, 200), 0.5, WORK) == (150, 300)  # never under its size on the page times the factor
    w, h = crop_shown((800, 1200), 1.4, WORK)
    assert h == 572 and w == 381  # 55 % of the work area's height at most


def test_the_popup_goes_beside_the_bubble_and_never_over_it():
    size = (300, 200)
    assert zoom_place(size, (400, 300, 600, 500), WORK) == (600 + ZOOM_GAP, 300)  # to its right, centred on it
    assert zoom_place(size, (1700, 300, 1900, 500), WORK) == (1700 - ZOOM_GAP - 300, 300)  # no room there: left
    tall = (300, 900)  # as tall as the work area leaves beside a bubble near the top: below or above instead
    assert zoom_place((1800, 200), (100, 100, 300, 300), WORK) == (0, 300 + ZOOM_GAP)
    assert zoom_place((1800, 200), (100, 800, 300, 1000), WORK) == (0, 800 - ZOOM_GAP - 200)
    assert zoom_place(tall, (0, 0, 1920, 1040), WORK) is None  # no side has room
    assert fallback_place(size, (1500, 900), WORK) == (0, 0)  # the corner farthest from the pointer
    assert fallback_place(size, (100, 100), WORK) == (1620, 840)


# ------------------------------------------------------------------ the popup on a stand-in
def _region(x0, y0, x1, y1, text="A line.", font_size=30, flags=(), status="translated"):
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), (x0, y0, x1, y1),
                      translated_text=text, font_size=font_size, flags=list(flags), status=status)


def _result():
    original = Image.new("RGB", (800, 600), "white")
    original.paste((0, 0, 0), (110, 110, 130, 190))  # some lettering in the small bubble
    regions = [_region(100, 100, 200, 300, "A *small* line.", font_size=18),  # 9 px on the screen at scale 0.5
               _region(400, 100, 700, 200, "A wide bubble with a long line.", font_size=40),
               _region(300, 400, 360, 460, "", status="untranslated")]
    return PageResult(image=original.copy(), original=original, regions=regions)


class Page(tk.Toplevel):
    """The page of the window (400 x 300 canvas pixels, the 800 x 600 frame at half size) and what the popup uses."""

    _watch_bubbles = A._watch_bubbles
    _zoom_wanted = A._zoom_wanted
    _zoom_region_at = A._zoom_region_at
    _zoom_screen_box = A._zoom_screen_box
    _zoom_motion = A._zoom_motion
    _zoom_due = A._zoom_due
    _zoom_pointer_on = A._zoom_pointer_on
    _zoom_escape = A._zoom_escape
    _zoom_show = A._zoom_show
    _zoom_watch = A._zoom_watch
    _zoom_hide = A._zoom_hide
    _page_regions = A._page_regions

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.settings = Settings()
        self.role_var = tk.StringVar(self, value="reader")
        self.reading, self.on_show = False, True
        self.later: list[tuple[int, object]] = []
        self.canvas = ImageCanvas(self)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        self.canvas.winfo_rootx, self.canvas.winfo_rooty = (lambda: 1000), (lambda: 100)
        self.pointer = (0, 0)
        self.last_result = _result()
        self.canvas.set_image(self.last_result.image)
        self._watch_bubbles()

    def _result_on_show(self):
        return self.on_show

    def winfo_pointerxy(self):
        return self.pointer

    def after(self, ms, func=None, *args):
        self.later.append((ms, func))
        return f"after#{len(self.later)}"

    def after_cancel(self, job):
        self.later = [(ms, f) for n, (ms, f) in enumerate(self.later, 1) if f"after#{n}" != job]

    def point(self, x, y):
        """The pointer at the page point (x, y) (frame pixels): the motion there, its screen point kept."""
        cx, cy = self.canvas.from_image_coords(x, y)
        self.pointer = (1000 + cx, 100 + cy)
        self._zoom_motion(SimpleNamespace(x=cx, y=cy))

    def due(self):
        """The callback put off last, now."""
        _ms, func = self.later.pop()
        func()


@pytest.fixture
def page(hidden_root, monkeypatch):
    shown = []
    monkeypatch.setattr(zoom, "reveal", shown.append)
    monkeypatch.setattr(zoom.layout, "work_area", lambda widget, x=None, y=None: WORK)

    def no_file(*_a, **_k):
        raise AssertionError("nothing of the page is written anywhere")

    monkeypatch.setattr(Image.Image, "save", no_file)
    w = Page(hidden_root)
    w.shown = shown
    return w


def _labels(widget):
    found, stack = [], [widget]
    while stack:
        item = stack.pop()
        if item.winfo_class() == "Label":
            found.append(item)
        stack.extend(item.winfo_children())
    return found


def test_a_bubble_hard_to_read_opens_sooner_than_one_that_reads_well(page):
    assert page.canvas.scale == 0.5
    page.point(150, 200)  # the small bubble
    assert [ms for ms, _f in page.later] == [ZOOM_DELAY_MS]
    page.point(160, 210)  # moved on it: nothing new
    assert len(page.later) == 1
    page.point(550, 150)  # the wide bubble: the one before is not due any more, this one after a longer rest
    assert [ms for ms, _f in page.later] == [ZOOM_REST_MS]
    page.point(330, 430)  # a bubble not translated, then the bare page: nothing
    assert page.later == [] and page._zoom_popup is None
    page.point(750, 550)
    assert page.later == []


def test_the_popup_holds_the_original_from_memory_and_the_translation_at_a_readable_size(page):
    page.point(150, 200)
    page.due()
    popup = page._zoom_popup
    assert popup is not None and page.shown == [popup] and bool(popup.overrideredirect())
    picture, words = (lbl for lbl in sorted(_labels(popup), key=lambda lbl: bool(lbl.cget("text"))))
    assert (picture.image.width(), picture.image.height()) == (150, 300)  # the 100 x 200 crop, 1.5 times
    assert str(words.cget("text")) == "A small line."  # the emphasis marks are the lettering's, not the reader's
    assert page._zoom_font.cget("size") == -22  # twice the readable size
    assert page.later[-1][0] == ZOOM_WATCH_MS


def test_the_popup_goes_with_the_pointer_a_click_esc_and_the_page(page):
    page.point(150, 200)
    page.due()
    page.point(155, 205)  # still on the bubble: it stays
    assert page._zoom_popup is not None
    page.point(750, 550)  # off it
    assert page._zoom_popup is None and page.later == []
    page.point(150, 200)
    page.due()
    assert page._zoom_escape() == "break" and page._zoom_popup is None  # Esc: the popup's only while it shows
    assert page._zoom_escape() is None  # ... then the window's as ever
    page.point(550, 150)
    page.due()
    page.last_result = _result()  # the page turned in the viewer, or read again
    page.due()  # the watch
    assert page._zoom_popup is None
    page.point(550, 150)
    page.due()
    page.pointer = (0, 0)  # the pointer off the page without a motion on it (onto another window)
    page.due()
    assert page._zoom_popup is None


def test_its_binding_tag_comes_first_and_leaves_the_pages_own_handlers(page):
    tags = page.canvas.bindtags()
    assert tags[0] == f"Zoom{page.canvas}" and tags[1] == str(page.canvas)
    page._watch_bubbles()  # once for each canvas
    assert page.canvas.bindtags() == tags
    for sequence in ("<Motion>", "<Leave>", "<ButtonPress>", "<MouseWheel>", "<KeyPress>", "<Escape>"):
        assert page.canvas.bind_class(tags[0], sequence), sequence
    assert not page.canvas.bind("<ButtonPress-1>")  # (nothing put on the page's own tag: its clicks stay its own)


def test_it_shows_in_reading_mode_and_the_reader_role_only_with_the_setting_on(page):
    assert page._zoom_wanted()
    page.role_var.set("translator")  # the Translator's pointer selects and edits the regions
    assert not page._zoom_wanted()
    page.reading = True  # ... but not in reading mode
    assert page._zoom_wanted()
    page.on_show = False  # another page than the one translated
    assert not page._zoom_wanted()
    page.on_show = True
    page.settings.bubble_zoom = False
    assert not page._zoom_wanted()
    page.point(150, 200)
    assert page.later == []
    assert Settings().bubble_zoom is True
